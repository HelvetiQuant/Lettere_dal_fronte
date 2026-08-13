"""Audit cross-linking quality: check if any matches are likely wrong (homonyms).

Conservative check: for each internati←lebi match, verify that birth year or place 
is consistent. Flag records where matched data conflicts with existing data.
"""
import sqlite3, re, warnings, logging
from collections import Counter
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

# Check: did the first run (populate_internati_v2.py) already apply data?
# The second run showed 0 updates from lebi, meaning first run applied everything.
# But the first run used 'name_unique' (4218 matches) and 'fuzzy_first3' (571 matches)
# which are RISKY — they could match different people.

# Let's check: for records that got data_nascita from lebi, does the birth year 
# make sense for WWII internees? (born 1900-1927, captured 1943)

print("=== AUDIT: internati with data_nascita from cross-linking ===")
suspicious = 0
total_with_birth = 0

for r in db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, reparto,
           data_decesso, causa_morte, luogo_morte, campi_internamento,
           fronte_cattura, data_cattura, data_rientro
    FROM internati 
    WHERE data_nascita IS NOT NULL AND data_nascita != ''
""").fetchall():
    total_with_birth += 1
    year = None
    m = re.search(r'(\d{4})', r['data_nascita'])
    if m:
        year = int(m.group(1))
    
    if year and (year < 1890 or year > 1928):
        suspicious += 1
        if suspicious <= 10:
            print(f"  SUSPICIOUS: {r['cognome']} {r['nome']} | birth={r['data_nascita']} (year={year})")

print(f"\n  Total with birth_date: {total_with_birth}")
print(f"  Suspicious (year < 1890 or > 1928): {suspicious}")

# Check for data conflicts: if internati had luogo_nascita and lebi gave a different one
print("\n=== CONFLICT CHECK: birth_place mismatches ===")
conflicts = 0
# We can't directly check this since we overwrote empty fields only.
# But we can check if any record has data that seems inconsistent.

# Check: records with death_date but no sort (fate) — should have sorte="Morto"
print("\n=== CONSISTENCY: death_date vs sorte ===")
has_death_no_morto = db.execute("""
    SELECT COUNT(*) as c FROM internati 
    WHERE data_decesso IS NOT NULL AND data_decesso != ''
    AND (sorte IS NULL OR sorte = '' OR sorte NOT LIKE '%Morto%')
""").fetchone()['c']
print(f"  Has death_date but sorte != Morto: {has_death_no_morto}")

# Check: records with campi_internamento — do they look like real camp names?
print("\n=== SAMPLE: campi_internamento values ===")
for r in db.execute("""
    SELECT cognome, nome, campi_internamento FROM internati 
    WHERE campi_internamento IS NOT NULL AND campi_internamento != ''
    LIMIT 10
""").fetchall():
    print(f"  {r['cognome']} {r['nome']}: {r['campi_internamento'][:80]}")

# Check: fronte_cattura values
print("\n=== SAMPLE: fronte_cattura values ===")
for r in db.execute("""
    SELECT cognome, nome, fronte_cattura FROM internati 
    WHERE fronte_cattura IS NOT NULL AND fronte_cattura != ''
    LIMIT 10
""").fetchall():
    print(f"  {r['cognome']} {r['nome']}: {r['fronte_cattura']}")

# Check: data_rientro values
print("\n=== SAMPLE: data_rientro values ===")
for r in db.execute("""
    SELECT cognome, nome, data_rientro FROM internati 
    WHERE data_rientro IS NOT NULL AND data_rientro != ''
    LIMIT 10
""").fetchall():
    print(f"  {r['cognome']} {r['nome']}: {r['data_rientro']}")

# Key question: how many records got data from RISKY matches (name_unique, fuzzy)?
# We can't directly tell, but we can check records that have lebi-sourced data 
# but NO birth_date match (meaning they were matched by name only)
print("\n=== RISK ASSESSMENT: records with cross-linked data but no strong ID ===")
# Records that got data_nascita but had NO data_nascita before (all came from lebi)
# These are fine IF the birth year is plausible for WWII internees
# The real risk is records matched by fuzzy_first3 — those have no birth year verification

# Check: records with cross-linked fields but birth year doesn't match WWII pattern
risky = db.execute("""
    SELECT COUNT(*) as c FROM internati 
    WHERE data_nascita IS NOT NULL AND data_nascita != ''
    AND data_nascita NOT GLOB '*19[0-2][0-9]*'
    AND data_nascita NOT GLOB '*193[0-9]*'
""").fetchone()['c']
print(f"  Records with implausible birth year: {risky}")

# Verify: sample records with full data from cross-linking
print("\n=== SAMPLE: fully enriched records ===")
for r in db.execute("""
    SELECT cognome, nome, data_nascita, luogo_nascita, grado, reparto, arma,
           data_cattura, fronte_cattura, campi_internamento, sorte,
           data_decesso, causa_morte, luogo_morte, luogo_sepoltura, data_rientro
    FROM internati 
    WHERE data_nascita != '' AND grado != '' AND reparto != '' AND campi_internamento != ''
    LIMIT 5
""").fetchall():
    print(f"\n  {r['cognome']} {r['nome']}")
    print(f"    nascita: {r['data_nascita']} a {r['luogo_nascita']}")
    print(f"    grado: {r['grado']}, reparto: {r['reparto']}, arma: {r['arma']}")
    print(f"    cattura: {r['data_cattura']} sul fronte {r['fronte_cattura']}")
    print(f"    campi: {r['campi_internamento'][:60]}")
    print(f"    sorte: {r['sorte']}")
    if r['data_decesso']:
        print(f"    decesso: {r['data_decesso']} causa {r['causa_morte']} a {r['luogo_morte']}")
    if r['data_rientro']:
        print(f"    rientro: {r['data_rientro']}")

db.close()
