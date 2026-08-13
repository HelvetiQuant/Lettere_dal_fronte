"""Check what data caduti_ministero already has that we're not extracting,
and check if caduti_cwgc has military details we can cross-link."""
import sqlite3, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

# caduti_ministero schema
print("=== caduti_ministero COLUMNS ===")
for r in db.execute("PRAGMA table_info(caduti_ministero)").fetchall():
    print(f"  {r['name']} ({r['type']})")

# Check coverage of existing fields
print("\n=== caduti_ministero FIELD COVERAGE ===")
total = db.execute("SELECT COUNT(*) as c FROM caduti_ministero").fetchone()['c']
for r in db.execute("PRAGMA table_info(caduti_ministero)").fetchall():
    col = r['name']
    if col in ('id', 'cross_link_source'):
        continue
    has = db.execute(f"SELECT COUNT(*) as c FROM caduti_ministero WHERE {col} IS NOT NULL AND {col} != '' AND {col} != '-'").fetchone()['c']
    print(f"  {col}: {has}/{total} ({has*100//total}%)")

# caduti_cwgc schema
print("\n=== caduti_cwgc COLUMNS ===")
for r in db.execute("PRAGMA table_info(caduti_cwgc)").fetchall():
    print(f"  {r['name']} ({r['type']})")

# Check CWGC coverage
print("\n=== caduti_cwgc FIELD COVERAGE (first 10 cols) ===")
cwgc_total = db.execute("SELECT COUNT(*) as c FROM caduti_cwgc").fetchone()['c']
cols = [r['name'] for r in db.execute("PRAGMA table_info(caduti_cwgc)").fetchall()]
for col in cols[:15]:
    has = db.execute(f"SELECT COUNT(*) as c FROM caduti_cwgc WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
    print(f"  {col}: {has}/{cwgc_total} ({has*100//cwgc_total}%)")

# Check decorati_nastroazzurro
print("\n=== decorati_nastroazzurro COLUMNS ===")
for r in db.execute("PRAGMA table_info(decorati_nastroazzurro)").fetchall():
    print(f"  {r['name']} ({r['type']})")

# Check decorati coverage
print("\n=== decorati_nastroazzurro FIELD COVERAGE ===")
dec_total = db.execute("SELECT COUNT(*) as c FROM decorati_nastroazzurro").fetchone()['c']
for r in db.execute("PRAGMA table_info(decorati_nastroazzurro)").fetchall():
    col = r['name']
    if col == 'id':
        continue
    has = db.execute(f"SELECT COUNT(*) as c FROM decorati_nastroazzurro WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
    print(f"  {col}: {has}/{dec_total} ({has*100//dec_total}%)")

# Check if caduti_ministero has data we're not using
print("\n=== caduti_ministero SAMPLE (unlinked, with data) ===")
for r in db.execute("""
    SELECT cognome, nome, data_nascita, comune_nascita, provincia_nascita,
           data_decesso, nazione_decesso, luogo_sepoltura
    FROM caduti_ministero 
    WHERE (cross_link_source = '' OR cross_link_source IS NULL)
    AND data_decesso != '' AND data_decesso IS NOT NULL
    LIMIT 5
""").fetchall():
    print(f"  {r['cognome']} {r['nome']} | nasc={r['data_nascita']} {r['comune_nascita']} ({r['provincia_nascita']}) | morte={r['data_decesso']} {r['nazione_decesso']} sep={r['luogo_sepoltura']}")

# Check lebi_records for missing fields
print("\n=== lebi_records COLUMNS ===")
for r in db.execute("PRAGMA table_info(lebi_records)").fetchall():
    print(f"  {r['name']} ({r['type']})")

# LeBI coverage
print("\n=== lebi_records FIELD COVERAGE ===")
lebi_total = db.execute("SELECT COUNT(*) as c FROM lebi_records").fetchone()['c']
for r in db.execute("PRAGMA table_info(lebi_records)").fetchall():
    col = r['name']
    if col in ('id', 'lebi_id'):
        continue
    has = db.execute(f"SELECT COUNT(*) as c FROM lebi_records WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
    print(f"  {col}: {has}/{lebi_total} ({has*100//lebi_total}%)")

db.close()
