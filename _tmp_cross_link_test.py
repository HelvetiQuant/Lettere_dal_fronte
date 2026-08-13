"""Cross-link tables to recover military fields (grado, reparto) from matching records."""
import sqlite3, time, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

# ─── 1. caduti_ministero ↔ caduti_albooro ───────────────────────────────────
# Match by: cognome + nome (first 10 chars) + data_nascita (year)
# caduti_ministero has NO military fields; caduti_albooro has grado, reparto, anno_morte, luogo_morte, causa_morte

print("=== CROSS-LINK: caduti_ministero ↔ caduti_albooro ===")
t0 = time.time()

# Build index of albooro records by normalized name
albooro_rows = db.execute("SELECT id, nominativo, grado, reparto, anno_morte, luogo_morte, causa_morte FROM caduti_albooro WHERE grado != '' OR reparto != ''").fetchall()
print(f"  caduti_albooro records with military data: {len(albooro_rows)}")

# Index by normalized nominativo (uppercase, no spaces)
albooro_index = {}
for r in albooro_rows:
    key = r['nominativo'].upper().replace(' ', '').replace('DI', '')[:20]
    if key not in albooro_index:
        albooro_index[key] = r

# Scan caduti_ministero and find matches
ministero_rows = db.execute("SELECT id, cognome, nome, data_nascita, data_decesso, provincia_nascita, comune_nascita FROM caduti_ministero").fetchall()
print(f"  caduti_ministero records to scan: {len(ministero_rows)}")

matched = 0
enriched = 0
for mr in ministero_rows:
    # Try matching by name
    name_key = f"{mr['cognome']}{mr['nome']}".upper().replace(' ', '').replace('DI', '')[:20]
    
    # Also try without "DI X" patronymic
    base_name = mr['nome'].split(' DI ')[0].strip()
    name_key2 = f"{mr['cognome']}{base_name}".upper().replace(' ', '').replace('DI', '')[:20]
    
    match = None
    for key in [name_key, name_key2]:
        if key in albooro_index:
            match = albooro_index[key]
            break
    
    if match:
        matched += 1
        # Check if we can enrich with military data
        has_military = match['grado'] or match['reparto']
        if has_military:
            enriched += 1

print(f"  Matched by name: {matched}")
print(f"  Would enrich with military data: {enriched}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 2. internati ↔ lebi_records ────────────────────────────────────────────
# Match by: cognome + nome
# internati has grado often empty; lebi_records has grado, reparto, arma, luogo_cattura, data_cattura

print("\n=== CROSS-LINK: internati ↔ lebi_records ===")
t0 = time.time()

lebi_rows = db.execute("SELECT id, cognome, nome, grado, reparto, arma, luogo_cattura, data_cattura, matricola, sorte FROM lebi_records WHERE grado != '' OR reparto != ''").fetchall()
print(f"  lebi_records with military data: {len(lebi_rows)}")

lebi_index = {}
for r in lebi_rows:
    key = f"{r['cognome']}{r['nome']}".upper().replace(' ', '')[:20]
    if key not in lebi_index:
        lebi_index[key] = r

internati_rows = db.execute("SELECT id, cognome, nome, grado, luogo_internamento, sorte FROM internati").fetchall()
print(f"  internati records to scan: {len(internati_rows)}")

matched2 = 0
enriched2 = 0
would_add_grado = 0
would_add_reparto = 0
for ir in internati_rows:
    key = f"{ir['cognome']}{ir['nome']}".upper().replace(' ', '')[:20]
    if key in lebi_index:
        match = lebi_index[key]
        matched2 += 1
        if match['grado'] and not ir['grado']:
            would_add_grado += 1
        if match['reparto']:
            would_add_reparto += 1
        if (match['grado'] and not ir['grado']) or match['reparto']:
            enriched2 += 1

print(f"  Matched by name: {matched2}")
print(f"  Would add grado: {would_add_grado}")
print(f"  Would add reparto: {would_add_reparto}")
print(f"  Would enrich: {enriched2}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── 3. Show sample matches ─────────────────────────────────────────────────
print("\n=== SAMPLE MATCHES (internati ↔ lebi) ===")
count = 0
for ir in internati_rows[:5000]:
    key = f"{ir['cognome']}{ir['nome']}".upper().replace(' ', '')[:20]
    if key in lebi_index and count < 5:
        match = lebi_index[key]
        if match['reparto']:
            print(f"  {ir['cognome']} {ir['nome']} (internati id={ir['id']})")
            print(f"    internati: grado='{ir['grado']}', luogo_int='{ir['luogo_internamento']}'")
            print(f"    lebi: grado='{match['grado']}', reparto='{match['reparto']}', arma='{match['arma']}', cattura='{match['luogo_cattura']}'")
            print()
            count += 1

print("\n=== SAMPLE MATCHES (caduti_ministero ↔ caduti_albooro) ===")
count = 0
for mr in ministero_rows[:5000]:
    name_key = f"{mr['cognome']}{mr['nome']}".upper().replace(' ', '').replace('DI', '')[:20]
    base_name = mr['nome'].split(' DI ')[0].strip()
    name_key2 = f"{mr['cognome']}{base_name}".upper().replace(' ', '').replace('DI', '')[:20]
    
    for key in [name_key, name_key2]:
        if key in albooro_index and count < 5:
            match = albooro_index[key]
            if match['reparto']:
                print(f"  {mr['cognome']} {mr['nome']} (ministero id={mr['id']})")
                print(f"    ministero: nascita={mr['data_nascita']}, comune={mr['comune_nascita']}")
                print(f"    albooro: grado='{match['grado']}', reparto='{match['reparto']}', anno_morte={match['anno_morte']}, luogo_morte={match['luogo_morte']}")
                print()
                count += 1
                break

db.close()
print("\nDone.")
