"""Validate cross-link quality with stricter matching (name + birth year + comune)."""
import sqlite3, time, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

# ─── caduti_ministero ↔ caduti_albooro: strict match ────────────────────────
print("=== STRICT MATCH: caduti_ministero ↔ caduti_albooro ===")
print("  Criteria: cognome + first name (before DI) + year of birth\n")

# Build albooro index with birth year extraction
# caduti_albooro has no data_nascita, but has anno_morte which helps validation
# We match on name + comune_nascita if available

# Actually caduti_albooro columns:
cols = [r['name'] for r in db.execute("PRAGMA table_info(caduti_albooro)").fetchall()]
print(f"  caduti_albooro columns: {cols}")

# Get a sample of albooro records
sample_albooro = db.execute("SELECT * FROM caduti_albooro LIMIT 3").fetchall()
for r in sample_albooro:
    print(f"\n  Sample albooro record:")
    for k in r.keys():
        if r[k]:
            print(f"    {k} = {r[k]}")

# ─── Better approach: match by normalized name + check comune if available ──
print("\n\n=== MATCHING WITH BIRTH YEAR VALIDATION ===\n")

# caduti_ministero has data_nascita (dd/mm/yyyy)
# caduti_albooro doesn't have data_nascita but has class (draft class ≈ birth year)
# Let's check if 'classe' exists
print(f"  caduti_albooro has 'classe' column: {'classe' in cols}")

if 'classe' in cols:
    # Match by name + classe (draft year ≈ birth year)
    albooro_rows = db.execute("""
        SELECT id, nominativo, grado, reparto, anno_morte, luogo_morte, causa_morte, classe
        FROM caduti_albooro 
        WHERE (grado != '' OR reparto != '') AND classe != ''
    """).fetchall()
    print(f"  caduti_albooro with classe + military: {len(albooro_rows)}")
    
    # Index by name + classe
    albooro_index = {}
    for r in albooro_rows:
        # Normalize name: remove DI/Maria etc
        nom = r['nominativo'].upper().replace(' ', '')
        # Remove DI patronymic
        parts = nom.split('DI')
        base = parts[0] if parts else nom
        key = f"{base}_{r['classe']}"
        if key not in albooro_index:
            albooro_index[key] = r
    
    # Scan ministero
    ministero_rows = db.execute("SELECT id, cognome, nome, data_nascita, comune_nascita FROM caduti_ministero LIMIT 10000").fetchall()
    
    strict_matched = 0
    for mr in ministero_rows:
        # Extract birth year from data_nascita
        dn = mr['data_nascita'] or ''
        year = ''
        if '/' in dn:
            parts = dn.split('/')
            if len(parts) == 3:
                year = parts[2].strip()
        
        # Normalize name
        base_name = mr['nome'].split(' DI ')[0].strip()
        key = f"{mr['cognome'].upper().replace(' ','')}{base_name.upper().replace(' ','')}_{year}"
        
        if key in albooro_index:
            strict_matched += 1
            if strict_matched <= 5:
                match = albooro_index[key]
                print(f"  ✅ {mr['cognome']} {mr['nome']} (ministero id={mr['id']})")
                print(f"     nascita={dn}, comune={mr['comune_nascita']}")
                print(f"     albooro: grado='{match['grado']}', reparto='{match['reparto']}', classe={match['classe']}, anno_morte={match['anno_morte']}")
                print()
    
    print(f"\n  Strict matches (name+year) in first 10K ministero: {strict_matched}")

# ─── internati ↔ lebi: strict match with birth year ─────────────────────────
print("\n=== STRICT MATCH: internati ↔ lebi_records ===")
lebi_cols = [r['name'] for r in db.execute("PRAGMA table_info(lebi_records)").fetchall()]
print(f"  lebi_records has 'data_nascita': {'data_nascita' in lebi_cols}")
print(f"  internati has 'data_nascita': {'data_nascita' in [r['name'] for r in db.execute('PRAGMA table_info(internati)').fetchall()]}")

# Check sample lebi record
sample_lebi = db.execute("SELECT cognome, nome, data_nascita, grado, reparto FROM lebi_records WHERE reparto != '' LIMIT 3").fetchall()
for r in sample_lebi:
    print(f"  lebi: {r['cognome']} {r['nome']} | nascita={r['data_nascita']} | grado={r['grado']} | reparto={r['reparto']}")

db.close()
