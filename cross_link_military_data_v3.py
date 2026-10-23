"""
Cross-link v3: resolve ambiguous duplicates + fuzzy matching for remaining.

Handles:
1. Ambiguous with identical candidates (same name, same DOB) → pick first
2. Ambiguous with same DOB but different place → pick first (place may be OCR variant)
3. Remaining: try partial name matching (first 6 chars of cognome + first 4 of nome)
"""
import sqlite3, time, warnings, logging, re
from collections import defaultdict
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

def norm_name(cognome, nome):
    cognome = (cognome or '').upper().strip()
    nome = (nome or '').upper().strip()
    nome = nome.split(' DI ')[0].strip()
    if ' O ' in nome:
        nome = nome.split(' O ')[0].strip()
    cognome = re.sub(r'[^A-Z]', '', cognome)
    nome = re.sub(r'[^A-Z]', '', nome)
    return f"{cognome}_{nome}" if cognome or nome else "_"

def extract_year(s):
    if not s: return ""
    m = re.search(r'(\d{4})', str(s).strip())
    return m.group(1) if m else ""

def extract_dob_key(s):
    """Extract normalized date (DDMMYYYY) for duplicate detection."""
    if not s: return ""
    s = str(s).strip()
    # Try dd-mm-yyyy or dd/mm/yyyy
    m = re.match(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""

# ─── Build lebi indices ─────────────────────────────────────────────────────
print("=== Building lebi_records indices ===")
t0 = time.time()
lebi_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, provincia_nascita,
           grado, reparto, arma, luogo_cattura, data_cattura, sorte
    FROM lebi_records 
    WHERE (grado IS NOT NULL AND grado != '') OR (reparto IS NOT NULL AND reparto != '')
""").fetchall()

lebi_by_name = defaultdict(list)
lebi_by_name_year = {}
lebi_by_name_dob = {}  # name + DOB for duplicate detection

for r in lebi_rows:
    nkey = norm_name(r['cognome'], r['nome'])
    lebi_by_name[nkey].append(r)
    year = extract_year(r['data_nascita'])
    if year:
        lebi_by_name_year[f"{nkey}_{year}"] = r
    dob = extract_dob_key(r['data_nascita'])
    if dob:
        lebi_by_name_dob[f"{nkey}_{dob}"] = r

# Also build partial name index for fuzzy matching
lebi_partial = defaultdict(list)
for r in lebi_rows:
    cognome = re.sub(r'[^A-Z]', '', (r['cognome'] or '').upper())
    nome = re.sub(r'[^A-Z]', '', (r['nome'] or '').upper().split(' DI ')[0].split(' O ')[0])
    if len(cognome) >= 4 and len(nome) >= 3:
        pkey = f"{cognome[:6]}_{nome[:4]}"
        lebi_partial[pkey].append(r)

print(f"  lebi records: {len(lebi_rows)}, names: {len(lebi_by_name)}, partial: {len(lebi_partial)}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── Process internati ──────────────────────────────────────────────────────
print("\n=== Cross-link internati ← lebi (v3) ===")
t0 = time.time()

# Only process unlinked records
internati_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, luogo_internamento, sorte
    FROM internati 
    WHERE cross_link_source = '' OR cross_link_source IS NULL
""").fetchall()
print(f"  Unlinked internati: {len(internati_rows)}")

stats = {"name_year": 0, "name_dob": 0, "name_unique": 0, "ambig_same_dob": 0, 
         "ambig_resolved_place": 0, "fuzzy": 0, "no_match": 0, "updated": 0}
batch = []

for ir in internati_rows:
    nkey = norm_name(ir['cognome'], ir['nome'])
    if nkey == "_":
        stats["no_match"] += 1
        continue
    
    match = None
    strategy = ""
    
    # 1. name + year
    year = extract_year(ir['data_nascita'])
    if year:
        ykey = f"{nkey}_{year}"
        if ykey in lebi_by_name_year:
            match = lebi_by_name_year[ykey]
            strategy = "name+year"
            stats["name_year"] += 1
    
    # 2. name + DOB (exact date)
    if not match:
        dob = extract_dob_key(ir['data_nascita'])
        if dob:
            dkey = f"{nkey}_{dob}"
            if dkey in lebi_by_name_dob:
                match = lebi_by_name_dob[dkey]
                strategy = "name+dob"
                stats["name_dob"] += 1
    
    # 3. name only — unique
    if not match:
        candidates = lebi_by_name.get(nkey, [])
        if len(candidates) == 1:
            match = candidates[0]
            strategy = "name_unique"
            stats["name_unique"] += 1
        elif len(candidates) > 1:
            # Check if all candidates have same DOB → duplicates
            dobs = set(extract_dob_key(c['data_nascita']) for c in candidates)
            if len(dobs) == 1 and "" not in dobs:
                # All same DOB → pick first (they're the same person)
                match = candidates[0]
                strategy = "ambig_same_dob"
                stats["ambig_same_dob"] += 1
            else:
                # Try disambiguating by year
                if year:
                    for c in candidates:
                        if extract_year(c['data_nascita']) == year:
                            match = c
                            strategy = "ambig_year"
                            break
                # Try by place
                if not match:
                    place = re.sub(r'[^A-Z]', '', (ir['luogo_nascita'] or '').upper())
                    if place:
                        for c in candidates:
                            cplace = re.sub(r'[^A-Z]', '', (c['luogo_nascita'] or '').upper())
                            if cplace and cplace == place:
                                match = c
                                strategy = "ambig_place"
                                break
                if match:
                    stats["ambig_resolved_place"] += 1
    
    # 4. Fuzzy: partial name match (6-char cognome + 4-char nome)
    if not match:
        cognome = re.sub(r'[^A-Z]', '', (ir['cognome'] or '').upper())
        nome = re.sub(r'[^A-Z]', '', (ir['nome'] or '').upper().split(' DI ')[0].split(' O ')[0])
        if len(cognome) >= 4 and len(nome) >= 3:
            pkey = f"{cognome[:6]}_{nome[:4]}"
            partial_candidates = lebi_partial.get(pkey, [])
            if len(partial_candidates) == 1:
                match = partial_candidates[0]
                strategy = "fuzzy_unique"
                stats["fuzzy"] += 1
            elif len(partial_candidates) > 1 and year:
                for c in partial_candidates:
                    if extract_year(c['data_nascita']) == year:
                        match = c
                        strategy = "fuzzy_year"
                        stats["fuzzy"] += 1
                        break
    
    if not match:
        stats["no_match"] += 1
        continue
    
    # Update
    grado_new = (match['grado'] or '').strip()
    reparto_new = (match['reparto'] or '').strip()
    arma_new = (match['arma'] or '').strip()
    existing_grado = (ir['grado'] or '').strip()
    final_grado = existing_grado if existing_grado else grado_new
    
    if (grado_new and not existing_grado) or reparto_new or arma_new:
        batch.append((final_grado, reparto_new, arma_new, f"lebi:{strategy}", ir['id']))
        stats["updated"] += 1
    
    if len(batch) >= 500:
        db.executemany("UPDATE internati SET grado=?, reparto=?, arma=?, cross_link_source=? WHERE id=?", batch)
        db.commit()
        batch = []

if batch:
    db.executemany("UPDATE internati SET grado=?, reparto=?, arma=?, cross_link_source=? WHERE id=?", batch)
    db.commit()

print(f"  name+year:          {stats['name_year']}")
print(f"  name+dob:           {stats['name_dob']}")
print(f"  name unique:        {stats['name_unique']}")
print(f"  ambig same DOB:     {stats['ambig_same_dob']}")
print(f"  ambig resolved:     {stats['ambig_resolved_place']}")
print(f"  fuzzy:              {stats['fuzzy']}")
print(f"  no match:           {stats['no_match']}")
print(f"  Updated:            {stats['updated']}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── Also improve caduti_ministero with fuzzy ───────────────────────────────
print("\n=== Cross-link caduti_ministero ← caduti_albooro (v3 fuzzy) ===")
t0 = time.time()

# Build albooro partial index
albooro_rows = db.execute("""
    SELECT id, nominativo, paternita, classe, grado, reparto, 
           anno_morte, luogo_morte, causa_morte, comune_attuale
    FROM caduti_albooro 
    WHERE (grado != '' AND grado != '-') OR (reparto != '' AND reparto != '-')
""").fetchall()

albooro_by_name_year = {}
albooro_partial = defaultdict(list)

for r in albooro_rows:
    nom = re.sub(r'[^A-Z]', '', r['nominativo'].upper())
    nome_base = nom.split('DI')[0]
    classe = r['classe'] or ''
    if classe:
        albooro_by_name_year[f"{nome_base}_{classe}"] = r
    if len(nome_base) >= 8:
        pkey = nome_base[:10]
        albooro_partial[pkey].append(r)

ministero_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, comune_nascita
    FROM caduti_ministero 
    WHERE cross_link_source = '' OR cross_link_source IS NULL
""").fetchall()
print(f"  Unlinked ministero: {len(ministero_rows)}")

m_matched = 0
m_updated = 0
batch_m = []

for mr in ministero_rows:
    year = extract_year(mr['data_nascita'])
    cognome = re.sub(r'[^A-Z]', '', (mr['cognome'] or '').upper())
    nome = re.sub(r'[^A-Z]', '', (mr['nome'] or '').upper())
    nome_base = nome.split('DI')[0]
    base_key = f"{cognome}{nome_base}"
    
    # 1. name + year
    match = albooro_by_name_year.get(f"{base_key}_{year}") if year else None
    
    # 2. fuzzy: first 10 chars of name
    if not match and len(base_key) >= 8:
        candidates = albooro_partial.get(base_key[:10], [])
        if len(candidates) == 1:
            match = candidates[0]
        elif len(candidates) > 1 and year:
            for c in candidates:
                if c['classe'] == year:
                    match = c
                    break
    
    if match:
        m_matched += 1
        grado = (match['grado'] or '').strip() if match['grado'] and match['grado'] != '-' else ''
        reparto = (match['reparto'] or '').strip() if match['reparto'] and match['reparto'] != '-' else ''
        anno_morte = str(match['anno_morte']) if match['anno_morte'] else ''
        luogo_morte = (match['luogo_morte'] or '').strip() if match['luogo_morte'] and match['luogo_morte'] != '-' else ''
        causa_morte = (match['causa_morte'] or '').strip() if match['causa_morte'] and match['causa_morte'] != '-' else ''
        
        if grado or reparto:
            batch_m.append((grado, reparto, anno_morte, luogo_morte, causa_morte, 'caduti_albooro:fuzzy', mr['id']))
            m_updated += 1
    
    if len(batch_m) >= 500:
        db.executemany("UPDATE caduti_ministero SET grado=?, reparto=?, anno_morte=?, luogo_morte=?, causa_morte=?, cross_link_source=? WHERE id=?", batch_m)
        db.commit()
        batch_m = []

if batch_m:
    db.executemany("UPDATE caduti_ministero SET grado=?, reparto=?, anno_morte=?, luogo_morte=?, causa_morte=?, cross_link_source=? WHERE id=?", batch_m)
    db.commit()

print(f"  Newly matched: {m_matched}")
print(f"  Newly updated: {m_updated}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── Final summary ──────────────────────────────────────────────────────────
count_i = db.execute("SELECT COUNT(*) as c FROM internati WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
count_m = db.execute("SELECT COUNT(*) as c FROM caduti_ministero WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
total_i = 20465
total_m = 162646

print(f"\n{'='*60}")
print("CROSS-LINK V3 FINAL SUMMARY")
print(f"{'='*60}")
print(f"  internati ← lebi_records:          {count_i}/{total_i} ({count_i*100//total_i}%)")
print(f"  caduti_ministero ← caduti_albooro:  {count_m}/{total_m} ({count_m*100//total_m}%)")

# Quality check: sample
print(f"\n  Sample internati (new):")
for r in db.execute("SELECT cognome, nome, grado, reparto, arma, cross_link_source FROM internati WHERE cross_link_source LIKE 'lebi%' AND cross_link_source NOT LIKE 'lebi_records:name_only%' LIMIT 5").fetchall():
    print(f"    {r['cognome']} {r['nome']} | {r['grado']} | {r['reparto']} | {r['arma']} | {r['cross_link_source']}")

print(f"\n  Sample internati (fuzzy):")
for r in db.execute("SELECT cognome, nome, grado, reparto, arma, cross_link_source FROM internati WHERE cross_link_source LIKE 'lebi:fuzzy%' LIMIT 5").fetchall():
    print(f"    {r['cognome']} {r['nome']} | {r['grado']} | {r['reparto']} | {r['arma']} | {r['cross_link_source']}")

db.close()
print("\nDone.")
