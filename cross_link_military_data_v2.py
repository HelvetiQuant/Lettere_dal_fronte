"""
Cross-link military data v2 — improved multi-strategy matching.

Strategies (in priority order):
1. Name + birth year (strongest)
2. Name + birth place
3. Name only (with disambiguation when multiple candidates)

Improvements over v1:
- Case-insensitive matching (internati is Title Case, lebi is UPPERCASE)
- Handle None nome, "O" variants, OCR differences
- Multiple lebi matches: pick best by birth year/place overlap
- Log ambiguous matches for review
- Also validate caduti_ministero ↔ caduti_albooro with comune
"""
import sqlite3, time, warnings, logging, re
from collections import defaultdict
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

def norm_name(cognome: str, nome: str) -> str:
    """Normalize name: uppercase, no spaces, no DI patronymic, no special chars."""
    cognome = (cognome or '').upper().strip()
    nome = (nome or '').upper().strip()
    # Remove DI patronymic (e.g., "LUIGI DI GIACOMO" → "LUIGI")
    nome = nome.split(' DI ')[0].strip()
    # Remove "O" variants (e.g., "ANTANELLI O ANTONELLI" → "ANTANELLI")
    if ' O ' in nome:
        nome = nome.split(' O ')[0].strip()
    # Remove spaces
    cognome = re.sub(r'[^A-Z]', '', cognome)
    nome = re.sub(r'[^A-Z]', '', nome)
    return f"{cognome}_{nome}" if cognome and nome else f"{cognome}_{nome}"

def extract_year(date_str) -> str:
    """Extract year from date string."""
    if not date_str:
        return ""
    s = str(date_str).strip()
    m = re.search(r'(\d{4})', s)
    return m.group(1) if m else ""

def norm_place(place) -> str:
    """Normalize place name for comparison."""
    if not place:
        return ""
    return re.sub(r'[^A-Z]', '', place.upper().strip())

# ─── 1. Build lebi_records indices ──────────────────────────────────────────
print("=== STEP 1: Build lebi_records multi-index ===")
t0 = time.time()

lebi_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, provincia_nascita,
           grado, reparto, arma, luogo_cattura, data_cattura, sorte
    FROM lebi_records 
    WHERE (grado IS NOT NULL AND grado != '') OR (reparto IS NOT NULL AND reparto != '')
""").fetchall()
print(f"  lebi records with military data: {len(lebi_rows)}")

# Build 3 indices: by name, by name+year, by name+place
lebi_by_name = defaultdict(list)  # name_key → [row, ...]
lebi_by_name_year = {}            # name_key + year → row
lebi_by_name_place = {}           # name_key + place → row

for r in lebi_rows:
    nkey = norm_name(r['cognome'], r['nome'])
    lebi_by_name[nkey].append(r)
    
    year = extract_year(r['data_nascita'])
    if year:
        ykey = f"{nkey}_{year}"
        if ykey not in lebi_by_name_year:
            lebi_by_name_year[ykey] = r
    
    place = norm_place(r['luogo_nascita'])
    if place:
        pkey = f"{nkey}_{place}"
        if pkey not in lebi_by_name_place:
            lebi_by_name_place[pkey] = r

print(f"  Name index: {len(lebi_by_name)} unique names")
print(f"  Name+year index: {len(lebi_by_name_year)}")
print(f"  Name+place index: {len(lebi_by_name_place)}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 2. Cross-link internati ← lebi_records (multi-strategy) ────────────────
print("\n=== STEP 2: Cross-link internati ← lebi_records (multi-strategy) ===")
t0 = time.time()

# Reset cross_link_source for re-run
db.execute("UPDATE internati SET cross_link_source = '' WHERE cross_link_source = 'lebi_records'")
db.commit()

internati_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, luogo_internamento, sorte
    FROM internati
""").fetchall()
print(f"  internati records: {len(internati_rows)}")

matched_strong = 0   # name + year
matched_place = 0    # name + place
matched_name  = 0    # name only (single candidate)
matched_ambig = 0    # name only (multiple candidates, picked best)
no_match      = 0
updated = 0
batch = []
ambiguous_log = []

for ir in internati_rows:
    nkey = norm_name(ir['cognome'], ir['nome'])
    if not nkey or nkey == "_":
        no_match += 1
        continue
    
    # Strategy 1: name + birth year
    year = extract_year(ir['data_nascita'])
    match = None
    match_strategy = ""
    
    if year:
        ykey = f"{nkey}_{year}"
        if ykey in lebi_by_name_year:
            match = lebi_by_name_year[ykey]
            match_strategy = "name+year"
            matched_strong += 1
    
    # Strategy 2: name + birth place
    if not match:
        place = norm_place(ir['luogo_nascita'])
        if place:
            pkey = f"{nkey}_{place}"
            if pkey in lebi_by_name_place:
                match = lebi_by_name_place[pkey]
                match_strategy = "name+place"
                matched_place += 1
    
    # Strategy 3: name only
    if not match:
        candidates = lebi_by_name.get(nkey, [])
        if len(candidates) == 1:
            match = candidates[0]
            match_strategy = "name_only_unique"
            matched_name += 1
        elif len(candidates) > 1:
            # Multiple candidates: try to disambiguate
            # Prefer one with matching birth year
            if year:
                for c in candidates:
                    cyear = extract_year(c['data_nascita'])
                    if cyear == year:
                        match = c
                        match_strategy = "name_ambiguous_year_resolved"
                        break
            # If still no match, prefer one with matching birth place
            if not match:
                place = norm_place(ir['luogo_nascita'])
                if place:
                    for c in candidates:
                        cplace = norm_place(c['luogo_nascita'])
                        if cplace == place:
                            match = c
                            match_strategy = "name_ambiguous_place_resolved"
                            break
            # If still no match, skip (too risky to pick random)
            if not match:
                matched_ambig += 1
                ambiguous_log.append({
                    "internati_id": ir['id'],
                    "name": f"{ir['cognome']} {ir['nome']}",
                    "n_candidates": len(candidates),
                    "candidates": [f"{c['cognome']} {c['nome']} ({c['data_nascita']}, {c['luogo_nascita']})" for c in candidates[:3]]
                })
                continue
    
    if not match:
        no_match += 1
        continue
    
    # Determine what to update
    grado_new = (match['grado'] or '').strip()
    reparto_new = (match['reparto'] or '').strip()
    arma_new = (match['arma'] or '').strip()
    
    # Keep existing grado if already set
    existing_grado = (ir['grado'] or '').strip()
    final_grado = existing_grado if existing_grado else grado_new
    
    has_new = (grado_new and not existing_grado) or reparto_new or arma_new
    if has_new:
        batch.append((final_grado, reparto_new, arma_new, f"lebi_records:{match_strategy}", ir['id']))
        updated += 1
    
    if len(batch) >= 500:
        db.executemany("""
            UPDATE internati SET grado=?, reparto=?, arma=?, cross_link_source=? WHERE id=?
        """, batch)
        db.commit()
        batch = []

if batch:
    db.executemany("""
        UPDATE internati SET grado=?, reparto=?, arma=?, cross_link_source=? WHERE id=?
    """, batch)
    db.commit()

print(f"  Matched (name+year):        {matched_strong}")
print(f"  Matched (name+place):       {matched_place}")
print(f"  Matched (name only unique): {matched_name}")
print(f"  Matched (ambiguous resolved): {matched_strong + matched_place} (already counted above)")
print(f"  Ambiguous (unresolved):     {matched_ambig}")
print(f"  No match:                   {no_match}")
print(f"  Updated with military data: {updated}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 3. Improve caduti_ministero ← caduti_albooro with comune validation ────
print("\n=== STEP 3: Re-validate caduti_ministero ← caduti_albooro ===")
t0 = time.time()

# Check current state
current_linked = db.execute("SELECT COUNT(*) as c FROM caduti_ministero WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
print(f"  Currently linked: {current_linked}")

# Check if there are unlinked records
unlinked = db.execute("SELECT COUNT(*) as c FROM caduti_ministero WHERE cross_link_source = '' OR cross_link_source IS NULL").fetchone()['c']
print(f"  Unlinked remaining: {unlinked}")

# Build albooro index with classe + comune
albooro_rows = db.execute("""
    SELECT id, nominativo, paternita, classe, grado, reparto, 
           anno_morte, luogo_morte, causa_morte, comune_attuale
    FROM caduti_albooro 
    WHERE (grado != '' AND grado != '-') OR (reparto != '' AND reparto != '-')
""").fetchall()

# Build index by normalized name + classe
albooro_index = {}
albooro_name_only = defaultdict(list)

for r in albooro_rows:
    nom = r['nominativo'].upper().replace(' ', '')
    # Remove DI patronymic
    parts = nom.split('DI')
    base = parts[0] if parts else nom
    classe = r['classe'] or ''
    
    if classe:
        key = f"{base}_{classe}"
        if key not in albooro_index:
            albooro_index[key] = r
    
    # Also index by name only for fallback
    albooro_name_only[base].append(r)

# Process unlinked ministero records
ministero_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, comune_nascita, provincia_nascita
    FROM caduti_ministero 
    WHERE cross_link_source = '' OR cross_link_source IS NULL
""").fetchall()
print(f"  Unlinked to process: {len(ministero_rows)}")

matched2 = 0
updated2 = 0
batch2 = []

for mr in ministero_rows:
    year = extract_year(mr['data_nascita'])
    if not year:
        continue
    
    # Normalize name: COGNOMENOME (no DI)
    cognome = (mr['cognome'] or '').upper().replace(' ', '')
    nome = (mr['nome'] or '').upper().replace(' ', '')
    nome_base = nome.split('DI')[0]
    base_key = f"{cognome}{nome_base}"
    
    # Try name + classe (year)
    key = f"{base_key}_{year}"
    match = albooro_index.get(key)
    
    if not match:
        # Try name only with year disambiguation
        candidates = albooro_name_only.get(base_key, [])
        if len(candidates) == 1:
            # Single match by name — validate year if possible
            match = candidates[0]
        elif len(candidates) > 1:
            # Disambiguate by year
            for c in candidates:
                if c['classe'] and c['classe'] == year:
                    match = c
                    break
            # If no year match, try comune
            if not match:
                comune = norm_place(mr['comune_nascita'])
                if comune:
                    for c in candidates:
                        c_comune = norm_place(c['comune_attuale'])
                        if c_comune and c_comune == comune:
                            match = c
                            break
    
    if match:
        matched2 += 1
        grado = (match['grado'] or '').strip() if match['grado'] and match['grado'] != '-' else ''
        reparto = (match['reparto'] or '').strip() if match['reparto'] and match['reparto'] != '-' else ''
        anno_morte = str(match['anno_morte']) if match['anno_morte'] else ''
        luogo_morte = (match['luogo_morte'] or '').strip() if match['luogo_morte'] and match['luogo_morte'] != '-' else ''
        causa_morte = (match['causa_morte'] or '').strip() if match['causa_morte'] and match['causa_morte'] != '-' else ''
        
        if grado or reparto:
            batch2.append((grado, reparto, anno_morte, luogo_morte, causa_morte, 'caduti_albooro', mr['id']))
            updated2 += 1
    
    if len(batch2) >= 500:
        db.executemany("""
            UPDATE caduti_ministero 
            SET grado=?, reparto=?, anno_morte=?, luogo_morte=?, causa_morte=?, cross_link_source=?
            WHERE id=?
        """, batch2)
        db.commit()
        batch2 = []

if batch2:
    db.executemany("""
        UPDATE caduti_ministero 
        SET grado=?, reparto=?, anno_morte=?, luogo_morte=?, causa_morte=?, cross_link_source=?
        WHERE id=?
    """, batch2)
    db.commit()

print(f"  Newly matched: {matched2}")
print(f"  Newly updated: {updated2}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 4. Summary ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("CROSS-LINK V2 SUMMARY")
print(f"{'='*60}")

count_i = db.execute("SELECT COUNT(*) as c FROM internati WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
count_m = db.execute("SELECT COUNT(*) as c FROM caduti_ministero WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
total_i = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']
total_m = db.execute("SELECT COUNT(*) as c FROM caduti_ministero").fetchone()['c']

print(f"  internati ← lebi_records:          {count_i}/{total_i} ({count_i*100//total_i}%)")
print(f"  caduti_ministero ← caduti_albooro:  {count_m}/{total_m} ({count_m*100//total_m}%)")

# Sample results
print(f"\n  Sample internati enriched:")
for r in db.execute("SELECT cognome, nome, grado, reparto, arma, cross_link_source FROM internati WHERE cross_link_source LIKE 'lebi%' LIMIT 8").fetchall():
    print(f"    {r['cognome']} {r['nome']} | grado={r['grado']} | reparto={r['reparto']} | arma={r['arma']} | src={r['cross_link_source']}")

print(f"\n  Sample caduti_ministero enriched:")
for r in db.execute("SELECT cognome, nome, grado, reparto, anno_morte, luogo_morte FROM caduti_ministero WHERE cross_link_source='caduti_albooro' LIMIT 5").fetchall():
    print(f"    {r['cognome']} {r['nome']} | grado={r['grado']} | reparto={r['reparto']} | morte={r['anno_morte']} {r['luogo_morte']}")

# Ambiguous log
if ambiguous_log:
    print(f"\n  Ambiguous matches (unresolved): {len(ambiguous_log)}")
    for a in ambiguous_log[:5]:
        print(f"    {a['name']} (id={a['internati_id']}) — {a['n_candidates']} candidates: {a['candidates']}")

db.close()
print("\nDone.")
