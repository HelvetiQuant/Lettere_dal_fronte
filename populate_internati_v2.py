"""Comprehensive cross-linking to populate internati with missing fields.

Sources:
1. internati ← lebi_records (aggressive: name-only + year, fuzzy, partial)
2. internati ← caduti_ministero (birth date, birth place, death info)
3. internati ← decorati_nastroazzurro (decoration info)
"""
import sqlite3, re, time, warnings, logging
from collections import defaultdict, Counter
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

DB_PATH = 'imi_internati.db'
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

TOTAL = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']

def norm_name(cognome, nome):
    """Normalize name for matching."""
    c = (cognome or '').upper().strip()
    n = (nome or '').upper().strip()
    # Remove common prefixes
    for prefix in ['DI ', "DELL'", "DELLA ", "DE ", "D'"]:
        c = c.replace(prefix, '') if c.startswith(prefix) else c
    return c, n

def norm_year(date_str):
    """Extract year from date string."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    # Try DD-MM-YYYY or DD/MM/YYYY
    m = re.search(r'(\d{4})', date_str)
    if m:
        return int(m.group(1))
    return None

def norm_place(place):
    """Normalize place name."""
    if not place:
        return None
    p = place.upper().strip().rstrip(',')
    # Remove province suffix
    p = re.sub(r'\s*\([A-Z]{2}\)$', '', p)
    return p

# ─── 1. internati ← lebi_records (aggressive) ──────────────────────────────
print("=== 1. internati ← lebi_records (aggressive matching) ===")
t0 = time.time()

# Get existing columns
existing_cols = {r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()}

# Add columns we'll need
for col in ['fronte_cattura', 'campi_internamento', 'data_rientro', 'decorazione', 'anno_decorazione', 'anno_morte']:
    if col not in existing_cols:
        db.execute(f"ALTER TABLE internati ADD COLUMN {col} TEXT")
        existing_cols.add(col)
        print(f"  Pre-added column: {col}")
db.commit()

internati = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, reparto, arma,
           luogo_cattura, data_cattura, matricola, sorte,
           data_decesso, causa_morte, luogo_morte, luogo_sepoltura, campi_internamento,
           data_rientro, fronte_cattura
    FROM internati
""").fetchall()

# Build lebi index by normalized cognome
lebi_by_cognome = defaultdict(list)
lebi_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, provincia_nascita,
           grado, reparto, arma, fronte_cattura, luogo_cattura, data_cattura,
           matricola, campi_internamento, sorte, data_decesso, luogo_decesso,
           causa_morte, luogo_sepoltura, data_rientro
    FROM lebi_records
""").fetchall()
for lr in lebi_rows:
    nc, nn = norm_name(lr['cognome'], lr['nome'])
    lebi_by_cognome[nc].append((lr, nn))

print(f"  internati: {len(internati)}, lebi_records: {len(lebi_rows)}")

updates_lebi = []  # (col, value, internati_id)
matched_lebi = 0
match_methods = Counter()

for ir in internati:
    ic, in_ = norm_name(ir['cognome'], ir['nome'])
    if not ic:
        continue
    
    candidates = lebi_by_cognome.get(ic, [])
    if not candidates:
        continue
    
    i_year = norm_year(ir['data_nascita'])
    i_place = norm_place(ir['luogo_nascita'])
    
    best_match = None
    best_score = 0
    best_method = None
    
    for lr, ln in candidates:
        # Strategy 1: exact name + same birth year
        if ln == in_ and i_year and norm_year(lr['data_nascita']) == i_year:
            best_match = lr
            best_score = 100
            best_method = 'name+year'
            break
        
        # Strategy 2: exact name + same birth place
        if ln == in_ and i_place and norm_place(lr['luogo_nascita']) == i_place:
            best_match = lr
            best_score = 90
            best_method = 'name+place'
            break
    
    if not best_match:
        # Strategy 3: exact full name match, unique candidate
        exact = [(lr, ln) for lr, ln in candidates if ln == in_]
        if len(exact) == 1:
            best_match = exact[0][0]
            best_score = 70
            best_method = 'name_unique'
        elif len(exact) > 1:
            # Strategy 4: multiple exact name matches, try year
            if i_year:
                for lr, ln in exact:
                    if norm_year(lr['data_nascita']) == i_year:
                        best_match = lr
                        best_score = 80
                        best_method = 'name+year_ambiguous'
                        break
            # Strategy 5: multiple exact, try place
            if not best_match and i_place:
                for lr, ln in exact:
                    if norm_place(lr['luogo_nascita']) == i_place:
                        best_match = lr
                        best_score = 75
                        best_method = 'name+place_ambiguous'
                        break
    
    if not best_match:
        # Strategy 6: fuzzy first name (first 3 chars)
        if in_:
            i_first3 = in_[:3]
            fuzzy = [(lr, ln) for lr, ln in candidates if ln and ln.startswith(i_first3)]
            if len(fuzzy) == 1:
                best_match = fuzzy[0][0]
                best_score = 50
                best_method = 'fuzzy_first3'
            elif len(fuzzy) > 1 and i_year:
                for lr, ln in fuzzy:
                    if norm_year(lr['data_nascita']) == i_year:
                        best_match = lr
                        best_score = 60
                        best_method = 'fuzzy3+year'
                        break
    
    if not best_match:
        # Strategy 7: cognome only, single candidate
        if len(candidates) == 1 and candidates[0][1] and in_ and candidates[0][1].startswith(in_[:4]):
            best_match = candidates[0][0]
            best_score = 40
            best_method = 'cognome_single_partial'
    
    if best_match:
        matched_lebi += 1
        match_methods[best_method] += 1
        
        # Apply fields that are empty in internati
        field_map = {
            'data_nascita': 'data_nascita',
            'luogo_nascita': 'luogo_nascita',
            'grado': 'grado',
            'reparto': 'reparto',
            'arma': 'arma',
            'fronte_cattura': 'fronte_cattura',
            'luogo_cattura': 'luogo_cattura',
            'data_cattura': 'data_cattura',
            'matricola': 'matricola',
            'campi_internamento': 'campi_internamento',
            'sorte': 'sorte',
            'data_decesso': 'data_decesso',
            'causa_morte': 'causa_morte',
            'luogo_sepoltura': 'luogo_sepoltura',
            'data_rientro': 'data_rientro',
        }
        
        # Add new columns if they don't exist
        for lebi_col, int_col in [('luogo_decesso', 'luogo_morte'), ('fronte_cattura', 'fronte_cattura')]:
            if lebi_col not in field_map:
                field_map[lebi_col] = int_col
        
        for lebi_col, int_col in field_map.items():
            current = ir[int_col] if int_col in ir.keys() else None
            lebi_val = best_match[lebi_col] if lebi_col in best_match.keys() else None
            if (not current or str(current).strip() == '') and lebi_val and str(lebi_val).strip() != '':
                updates_lebi.append((int_col, str(lebi_val).strip(), ir['id']))

print(f"  Matched: {matched_lebi}/{len(internati)} ({matched_lebi*100//len(internati)}%)")
print(f"  Updates: {len(updates_lebi)}")
print(f"  Methods: {dict(match_methods.most_common())}")
print(f"  Time: {time.time()-t0:.1f}s")

# Apply lebi updates
if updates_lebi:
    # Ensure columns exist
    existing = {r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()}
    new_cols = ['fronte_cattura', 'campi_internamento', 'data_rientro']
    for col in new_cols:
        if col not in existing:
            db.execute(f"ALTER TABLE internati ADD COLUMN {col} TEXT")
            print(f"  Added column: {col}")
    
    # Apply by column
    col_groups = defaultdict(list)
    for col, val, rid in updates_lebi:
        col_groups[col].append((val, rid))
    
    for col, batch in col_groups.items():
        db.executemany(f"UPDATE internati SET {col}=? WHERE id=?", batch)
        db.commit()
        print(f"    {col}: {len(batch)} updates")

# ─── 2. internati ← caduti_ministero ────────────────────────────────────────
print(f"\n=== 2. internati ← caduti_ministero ===")
t0 = time.time()

# Build caduti_ministero index by cognome
cm_by_cognome = defaultdict(list)
cm_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, comune_nascita, provincia_nascita,
           data_decesso, nazione_decesso, luogo_sepoltura, grado, reparto,
           anno_morte, luogo_morte, causa_morte, paternita, maternita
    FROM caduti_ministero
    WHERE cognome IS NOT NULL AND cognome != ''
""").fetchall()
for cr in cm_rows:
    nc, nn = norm_name(cr['cognome'], cr['nome'])
    cm_by_cognome[nc].append((cr, nn))

print(f"  caduti_ministero indexed: {len(cm_rows)}")

# Re-fetch internati with updated fields
internati2 = db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, reparto,
           data_decesso, causa_morte, luogo_morte, luogo_sepoltura
    FROM internati
""").fetchall()

updates_cm = []
matched_cm = 0

for ir in internati2:
    ic, in_ = norm_name(ir['cognome'], ir['nome'])
    if not ic:
        continue
    
    candidates = cm_by_cognome.get(ic, [])
    if not candidates:
        continue
    
    i_year = norm_year(ir['data_nascita'])
    
    best_match = None
    best_score = 0
    
    for cr, cn in candidates:
        # Strategy 1: exact name + same birth year
        if cn == in_ and i_year and norm_year(cr['data_nascita']) == i_year:
            best_match = cr
            best_score = 100
            break
        
        # Strategy 2: exact name + same birth year (year from comune)
        if cn == in_ and not i_year:
            # If internati has no birth year, accept any exact name match if unique
            exact_count = sum(1 for _, cn2 in candidates if cn2 == in_)
            if exact_count == 1:
                best_match = cr
                best_score = 70
                break
    
    if not best_match:
        # Strategy 3: exact name, unique
        exact = [(cr, cn) for cr, cn in candidates if cn == in_]
        if len(exact) == 1:
            best_match = exact[0][0]
            best_score = 60
    
    if not best_match and in_:
        # Strategy 4: fuzzy first 4 chars + year
        i_first4 = in_[:4]
        fuzzy = [(cr, cn) for cr, cn in candidates if cn and cn.startswith(i_first4)]
        if len(fuzzy) == 1 and (not i_year or norm_year(fuzzy[0][0]['data_nascita']) == i_year):
            best_match = fuzzy[0][0]
            best_score = 50
    
    if best_match:
        matched_cm += 1
        field_map = {
            'data_nascita': 'data_nascita',
            'comune_nascita': 'luogo_nascita',
            'grado': 'grado',
            'reparto': 'reparto',
            'anno_morte': 'anno_morte',
            'luogo_morte': 'luogo_morte',
            'causa_morte': 'causa_morte',
        }
        
        for cm_col, int_col in field_map.items():
            current = ir[int_col] if int_col in ir.keys() else None
            cm_val = best_match[cm_col] if cm_col in best_match.keys() else None
            if (not current or str(current).strip() == '') and cm_val and str(cm_val).strip() != '' and str(cm_val).strip() != '-':
                updates_cm.append((int_col, str(cm_val).strip(), ir['id']))

print(f"  Matched: {matched_cm}/{len(internati2)} ({matched_cm*100//len(internati2)}%)")
print(f"  Updates: {len(updates_cm)}")
print(f"  Time: {time.time()-t0:.1f}s")

# Apply cm updates
if updates_cm:
    existing = {r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()}
    for col in ['anno_morte']:
        if col not in existing:
            db.execute(f"ALTER TABLE internati ADD COLUMN {col} TEXT")
            print(f"  Added column: {col}")
    
    col_groups = defaultdict(list)
    for col, val, rid in updates_cm:
        col_groups[col].append((val, rid))
    
    for col, batch in col_groups.items():
        db.executemany(f"UPDATE internati SET {col}=? WHERE id=?", batch)
        db.commit()
        print(f"    {col}: {len(batch)} updates")

# ─── 3. internati ← decorati_nastroazzurro ──────────────────────────────────
print(f"\n=== 3. internati ← decorati_nastroazzurro ===")
t0 = time.time()

# Build decorati index by cognome
dec_by_cognome = defaultdict(list)
dec_rows = db.execute("""
    SELECT id, cognome, nome, arma, anno_decorazione, tipo_decorazione
    FROM decorati_nastroazzurro
    WHERE cognome IS NOT NULL AND cognome != ''
""").fetchall()
for dr in dec_rows:
    nc, nn = norm_name(dr['cognome'], dr['nome'])
    dec_by_cognome[nc].append((dr, nn))

print(f"  decorati indexed: {len(dec_rows)}")

# Re-fetch internati
internati3 = db.execute("""
    SELECT id, cognome, nome, data_nascita, arma, decorazione, anno_decorazione
    FROM internati
""").fetchall()

updates_dec = []
matched_dec = 0

for ir in internati3:
    ic, in_ = norm_name(ir['cognome'], ir['nome'])
    if not ic:
        continue
    
    candidates = dec_by_cognome.get(ic, [])
    if not candidates:
        continue
    
    i_year = norm_year(ir['data_nascita'])
    
    best_match = None
    
    for dr, dn in candidates:
        # Exact name + year match
        if dn == in_:
            # If we have birth year, try to match decoration year (should be before or during service)
            best_match = dr
            break
    
    if not best_match and in_:
        exact = [(dr, dn) for dr, dn in candidates if dn == in_]
        if len(exact) == 1:
            best_match = exact[0][0]
    
    if best_match:
        matched_dec += 1
        # Add decoration info
        if (not ir['arma'] or str(ir['arma']).strip() == '') and best_match['arma']:
            updates_dec.append(('arma', best_match['arma'], ir['id']))
        if best_match['tipo_decorazione']:
            updates_dec.append(('decorazione', best_match['tipo_decorazione'], ir['id']))
        if best_match['anno_decorazione']:
            updates_dec.append(('anno_decorazione', best_match['anno_decorazione'], ir['id']))

print(f"  Matched: {matched_dec}/{len(internati3)} ({matched_dec*100//len(internati3)}%)")
print(f"  Updates: {len(updates_dec)}")
print(f"  Time: {time.time()-t0:.1f}s")

# Apply decorati updates
if updates_dec:
    existing = {r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()}
    for col in ['decorazione', 'anno_decorazione']:
        if col not in existing:
            db.execute(f"ALTER TABLE internati ADD COLUMN {col} TEXT")
            print(f"  Added column: {col}")
    
    col_groups = defaultdict(list)
    for col, val, rid in updates_dec:
        col_groups[col].append((val, rid))
    
    for col, batch in col_groups.items():
        db.executemany(f"UPDATE internati SET {col}=? WHERE id=?", batch)
        db.commit()
        print(f"    {col}: {len(batch)} updates")

# ─── FINAL COVERAGE ─────────────────────────────────────────────────────────
print(f"\n=== FINAL internati FIELD COVERAGE ===")
all_cols = [r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()]
for col in sorted(all_cols):
    if col in ('id', 'raw_text', 'source_file', 'page_number', 'cross_link_source'):
        continue
    has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
    pct = has * 100 // TOTAL
    if pct > 0:
        print(f"  {col}: {has}/{TOTAL} ({pct}%)")

db.close()
print(f"\nDone. Total time: {time.time()-t0:.1f}s")
