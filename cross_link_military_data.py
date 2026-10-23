"""
Cross-link military data between tables.
- caduti_ministero ← caduti_albooro: add grado, reparto, anno_morte, luogo_morte, causa_morte
- internati ← lebi_records: add grado (when empty), reparto, arma, luogo_cattura, data_cattura

Uses strict matching: normalized name + birth year (classe for albooro).
Adds columns if missing, updates matched records.
"""
import sqlite3, time, warnings, logging, re
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

def normalize_name(cognome: str, nome: str) -> str:
    """Normalize name for matching: uppercase, no spaces, no DI patronymic."""
    cognome = cognome or ''
    nome = nome or ''
    base = nome.split(' DI ')[0].strip()
    return f"{cognome.upper().replace(' ','')}{base.upper().replace(' ','')}"

def extract_year(date_str: str) -> str:
    """Extract year from date string (dd/mm/yyyy or dd-mm-yyyy)."""
    if not date_str:
        return ""
    m = re.search(r'(\d{4})$', date_str.strip())
    return m.group(1) if m else ""

# ─── 1. Add military columns to caduti_ministero if missing ─────────────────
print("=== STEP 1: Add military columns to caduti_ministero ===")
existing_cols = [r['name'] for r in db.execute("PRAGMA table_info(caduti_ministero)").fetchall()]
new_cols = [
    ("grado", "TEXT"),
    ("reparto", "TEXT"),
    ("anno_morte", "TEXT"),
    ("luogo_morte", "TEXT"),
    ("causa_morte", "TEXT"),
    ("cross_link_source", "TEXT DEFAULT ''"),
]
for col, ctype in new_cols:
    if col not in existing_cols:
        db.execute(f"ALTER TABLE caduti_ministero ADD COLUMN {col} {ctype}")
        print(f"  Added column: {col} ({ctype})")
    else:
        print(f"  Column already exists: {col}")

# ─── 2. Build albooro index ─────────────────────────────────────────────────
print("\n=== STEP 2: Build caduti_albooro index ===")
t0 = time.time()
albooro_rows = db.execute("""
    SELECT id, nominativo, paternita, classe, grado, reparto, 
           anno_morte, luogo_morte, causa_morte
    FROM caduti_albooro 
    WHERE (grado != '' AND grado != '-') OR (reparto != '' AND reparto != '-')
""").fetchall()
print(f"  Records with military data: {len(albooro_rows)}")

albooro_index = {}
for r in albooro_rows:
    # Normalize: COGNOMENOME + CLASSE
    nom = r['nominativo'].upper().replace(' ', '')
    # Remove DI patronymic
    parts = nom.split('DI')
    base = parts[0] if parts else nom
    classe = r['classe'] or ''
    key = f"{base}_{classe}"
    if key not in albooro_index:
        albooro_index[key] = r

print(f"  Index size: {len(albooro_index)} unique keys")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 3. Cross-link caduti_ministero ← caduti_albooro ────────────────────────
print("\n=== STEP 3: Cross-link caduti_ministero ← caduti_albooro ===")
t0 = time.time()
ministero_rows = db.execute("SELECT id, cognome, nome, data_nascita FROM caduti_ministero WHERE cross_link_source = '' OR cross_link_source IS NULL").fetchall()
print(f"  Records to process: {len(ministero_rows)}")

matched = 0
updated = 0
batch = []
for mr in ministero_rows:
    year = extract_year(mr['data_nascita'])
    if not year:
        continue
    key = f"{normalize_name(mr['cognome'], mr['nome'])}_{year}"
    
    match = albooro_index.get(key)
    if match:
        matched += 1
        grado = match['grado'] if match['grado'] and match['grado'] != '-' else ''
        reparto = match['reparto'] if match['reparto'] and match['reparto'] != '-' else ''
        anno_morte = str(match['anno_morte']) if match['anno_morte'] else ''
        luogo_morte = match['luogo_morte'] if match['luogo_morte'] and match['luogo_morte'] != '-' else ''
        causa_morte = match['causa_morte'] if match['causa_morte'] and match['causa_morte'] != '-' else ''
        
        if grado or reparto:
            batch.append((grado, reparto, anno_morte, luogo_morte, causa_morte, 'caduti_albooro', mr['id']))
            updated += 1
    
    if len(batch) >= 500:
        db.executemany("""
            UPDATE caduti_ministero 
            SET grado=?, reparto=?, anno_morte=?, luogo_morte=?, causa_morte=?, cross_link_source=?
            WHERE id=?
        """, batch)
        db.commit()
        batch = []

if batch:
    db.executemany("""
        UPDATE caduti_ministero 
        SET grado=?, reparto=?, anno_morte=?, luogo_morte=?, causa_morte=?, cross_link_source=?
        WHERE id=?
    """, batch)
    db.commit()

print(f"  Matched: {matched}")
print(f"  Updated with military data: {updated}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 4. Add military columns to internati if missing ────────────────────────
print("\n=== STEP 4: Add military columns to internati ===")
existing_internati_cols = [r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()]
new_internati_cols = [
    ("reparto", "TEXT DEFAULT ''"),
    ("arma", "TEXT DEFAULT ''"),
    ("cross_link_source", "TEXT DEFAULT ''"),
]
for col, ctype in new_internati_cols:
    if col not in existing_internati_cols:
        db.execute(f"ALTER TABLE internati ADD COLUMN {col} {ctype}")
        print(f"  Added column: {col} ({ctype})")
    else:
        print(f"  Column already exists: {col}")

# ─── 5. Build lebi index ────────────────────────────────────────────────────
print("\n=== STEP 5: Build lebi_records index ===")
t0 = time.time()
lebi_rows = db.execute("""
    SELECT id, cognome, nome, data_nascita, grado, reparto, arma, luogo_cattura, data_cattura
    FROM lebi_records 
    WHERE grado != '' OR reparto != ''
""").fetchall()
print(f"  Records with military data: {len(lebi_rows)}")

lebi_index = {}
for r in lebi_rows:
    year = extract_year(r['data_nascita'])
    key = f"{normalize_name(r['cognome'], r['nome'])}_{year}" if year else f"{normalize_name(r['cognome'], r['nome'])}_NORYEAR"
    if key not in lebi_index:
        lebi_index[key] = r

print(f"  Index size: {len(lebi_index)}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 6. Cross-link internati ← lebi_records ─────────────────────────────────
print("\n=== STEP 6: Cross-link internati ← lebi_records ===")
t0 = time.time()
internati_rows = db.execute("SELECT id, cognome, nome, data_nascita, grado FROM internati WHERE cross_link_source = '' OR cross_link_source IS NULL").fetchall()
print(f"  Records to process: {len(internati_rows)}")

matched2 = 0
updated2 = 0
batch2 = []
for ir in internati_rows:
    year = extract_year(ir['data_nascita'] or '')
    # Try with year first, then without
    key = f"{normalize_name(ir['cognome'], ir['nome'])}_{year}" if year else None
    key_noyear = f"{normalize_name(ir['cognome'], ir['nome'])}_NORYEAR"
    
    match = None
    if key and key in lebi_index:
        match = lebi_index[key]
    elif key_noyear in lebi_index:
        match = lebi_index[key_noyear]
    
    if match:
        matched2 += 1
        grado = match['grado'] if match['grado'] else ''
        reparto = match['reparto'] if match['reparto'] else ''
        arma = match['arma'] if match['arma'] else ''
        
        # Only update if we have new data
        has_new = (grado and not ir['grado']) or reparto or arma
        if has_new:
            # Keep existing grado if already set
            final_grado = ir['grado'] if ir['grado'] else grado
            batch2.append((final_grado, reparto, arma, 'lebi_records', ir['id']))
            updated2 += 1
    
    if len(batch2) >= 500:
        db.executemany("""
            UPDATE internati SET grado=?, reparto=?, arma=?, cross_link_source=? WHERE id=?
        """, batch2)
        db.commit()
        batch2 = []

if batch2:
    db.executemany("""
        UPDATE internati SET grado=?, reparto=?, arma=?, cross_link_source=? WHERE id=?
    """, batch2)
    db.commit()

print(f"  Matched: {matched2}")
print(f"  Updated with military data: {updated2}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── Summary ────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("CROSS-LINK SUMMARY")
print(f"{'='*60}")
print(f"  caduti_ministero ← caduti_albooro: {updated}/{matched} enriched")
print(f"  internati ← lebi_records:          {updated2}/{matched2} enriched")

# Verify
count_m = db.execute("SELECT COUNT(*) as c FROM caduti_ministero WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
count_i = db.execute("SELECT COUNT(*) as c FROM internati WHERE cross_link_source != '' AND cross_link_source IS NOT NULL").fetchone()['c']
print(f"\n  Verified in DB:")
print(f"    caduti_ministero with cross_link_source: {count_m}")
print(f"    internati with cross_link_source: {count_i}")

# Sample
print(f"\n  Sample caduti_ministero enriched:")
for r in db.execute("SELECT cognome, nome, grado, reparto, anno_morte, luogo_morte FROM caduti_ministero WHERE cross_link_source='caduti_albooro' LIMIT 3").fetchall():
    print(f"    {r['cognome']} {r['nome']} | grado={r['grado']} | reparto={r['reparto']} | morte={r['anno_morte']} {r['luogo_morte']}")

print(f"\n  Sample internati enriched:")
for r in db.execute("SELECT cognome, nome, grado, reparto, arma FROM internati WHERE cross_link_source='lebi_records' LIMIT 3").fetchall():
    print(f"    {r['cognome']} {r['nome']} | grado={r['grado']} | reparto={r['reparto']} | arma={r['arma']}")

db.close()
print("\nDone.")
