"""Analyze internati data to understand why matching is low."""
import sqlite3, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

# Check how many internati have data_nascita
total = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']
with_dob = db.execute("SELECT COUNT(*) as c FROM internati WHERE data_nascita IS NOT NULL AND data_nascita != ''").fetchone()['c']
with_grado = db.execute("SELECT COUNT(*) as c FROM internati WHERE grado IS NOT NULL AND grado != ''").fetchone()['c']
with_luogo_nascita = db.execute("SELECT COUNT(*) as c FROM internati WHERE luogo_nascita IS NOT NULL AND luogo_nascita != ''").fetchone()['c']
with_matricola = db.execute("SELECT COUNT(*) as c FROM internati WHERE matricola IS NOT NULL AND matricola != ''").fetchone()['c']

print(f"=== INTERNATI DATA COVERAGE ===")
print(f"  Total records: {total}")
print(f"  With data_nascita: {with_dob} ({with_dob*100//total}%)")
print(f"  With luogo_nascita: {with_luogo_nascita} ({with_luogo_nascita*100//total}%)")
print(f"  With grado: {with_grado} ({with_grado*100//total}%)")
print(f"  With matricola: {with_matricola} ({with_matricola*100//total}%)")

# Check lebi_records coverage
lebi_total = db.execute("SELECT COUNT(*) as c FROM lebi_records").fetchone()['c']
lebi_dob = db.execute("SELECT COUNT(*) as c FROM lebi_records WHERE data_nascita IS NOT NULL AND data_nascita != ''").fetchone()['c']
lebi_grado = db.execute("SELECT COUNT(*) as c FROM lebi_records WHERE grado IS NOT NULL AND grado != ''").fetchone()['c']
lebi_reparto = db.execute("SELECT COUNT(*) as c FROM lebi_records WHERE reparto IS NOT NULL AND reparto != ''").fetchone()['c']
lebi_matricola = db.execute("SELECT COUNT(*) as c FROM lebi_records WHERE matricola IS NOT NULL AND matricola != ''").fetchone()['c']

print(f"\n=== LEBI_RECORDS DATA COVERAGE ===")
print(f"  Total records: {lebi_total}")
print(f"  With data_nascita: {lebi_dob} ({lebi_dob*100//lebi_total}%)")
print(f"  With grado: {lebi_grado} ({lebi_grado*100//lebi_total}%)")
print(f"  With reparto: {lebi_reparto} ({lebi_reparto*100//lebi_total}%)")
print(f"  With matricola: {lebi_matricola} ({lebi_matricola*100//lebi_total}%)")

# Sample internati without data_nascita
print(f"\n=== SAMPLE INTERNATI WITHOUT data_nascita ===")
for r in db.execute("SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, luogo_internamento, sorte FROM internati WHERE (data_nascita IS NULL OR data_nascita = '') LIMIT 10").fetchall():
    print(f"  id={r['id']}: {r['cognome']} {r['nome']} | luogo_nasc={r['luogo_nascita']} | grado={r['grado']} | int={r['luogo_internamento']} | sorte={r['sorte']}")

# Check name format differences
print(f"\n=== NAME FORMAT COMPARISON (first 20 internati) ===")
for r in db.execute("SELECT cognome, nome FROM internati LIMIT 20").fetchall():
    print(f"  internati: '{r['cognome']}' '{r['nome']}'")

print(f"\n=== NAME FORMAT COMPARISON (first 20 lebi) ===")
for r in db.execute("SELECT cognome, nome FROM lebi_records LIMIT 20").fetchall():
    print(f"  lebi: '{r['cognome']}' '{r['nome']}'")

# Check if names match without year
print(f"\n=== NAME-ONLY MATCH COUNT ===")
# Build lebi index by name only
lebi_rows = db.execute("SELECT id, cognome, nome, data_nascita, grado, reparto, arma FROM lebi_records WHERE grado != '' OR reparto != ''").fetchall()
lebi_name_index = {}
for r in lebi_rows:
    key = f"{(r['cognome'] or '').upper().strip()}_{(r['nome'] or '').upper().strip()}"
    if key not in lebi_name_index:
        lebi_name_index[key] = r

internati_rows = db.execute("SELECT id, cognome, nome FROM internati").fetchall()
name_only_matches = 0
for ir in internati_rows:
    key = f"{(ir['cognome'] or '').upper().strip()}_{(ir['nome'] or '').upper().strip()}"
    if key in lebi_name_index:
        name_only_matches += 1

print(f"  Name-only exact matches: {name_only_matches} / {total}")

# Check with normalized name (no spaces, no DI)
import re
def norm(cognome, nome):
    cognome = (cognome or '').upper().replace(' ', '').strip()
    nome = (nome or '').upper().replace(' ', '').strip()
    # Remove DI patronymic
    nome = nome.split('DI')[0]
    return f"{cognome}_{nome}"

lebi_norm_index = {}
for r in lebi_rows:
    key = norm(r['cognome'], r['nome'])
    if key not in lebi_norm_index:
        lebi_norm_index[key] = r

norm_matches = 0
for ir in internati_rows:
    key = norm(ir['cognome'], ir['nome'])
    if key in lebi_norm_index:
        norm_matches += 1

print(f"  Normalized name matches: {norm_matches} / {total}")

# Check with first-name prefix matching
prefix_matches = 0
for ir in internati_rows:
    ikey = norm(ir['cognome'], ir['nome'])
    # Also try with just first 4 chars of nome
    cognome = (ir['cognome'] or '').upper().replace(' ', '').strip()
    nome = (ir['nome'] or '').upper().replace(' ', '').strip().split('DI')[0]
    if len(nome) >= 4:
        prefix_key = f"{cognome}_{nome[:4]}"
        for lkey in lebi_norm_index:
            if lkey.startswith(prefix_key):
                prefix_matches += 1
                break

print(f"  Prefix (4-char) name matches: {prefix_matches} / {total}")

db.close()
