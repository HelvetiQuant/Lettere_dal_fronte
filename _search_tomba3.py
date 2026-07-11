import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "imi_internati.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Search caduti_ministero by cognome='GAIASCHI'
print("=== Ricerca per cognome GAIASCHI in caduti_ministero ===")
cur.execute("SELECT * FROM caduti_ministero WHERE cognome LIKE '%GAIASCHI%' OR cognome LIKE '%Gaiaschi%'")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print(f"Trovati {len(rows)} record")
for r in rows:
    print("\n--- Record ---")
    for i, v in enumerate(r):
        if v is not None and str(v).strip():
            print(f"  {cols[i]}: {v}")

# Also search by nome containing GIUSEPPE and cognome containing GAI
print("\n\n=== Ricerca per cognome contenente 'GAI' in caduti_ministero ===")
cur.execute("SELECT * FROM caduti_ministero WHERE cognome LIKE 'GAI%'")
rows = cur.fetchall()
print(f"Trovati {len(rows)} record")
for r in rows:
    print("\n--- Record ---")
    for i, v in enumerate(r):
        if v is not None and str(v).strip():
            print(f"  {cols[i]}: {v}")

# Check if luogo_sepoltura is ever populated
print("\n\n=== Verifica campo luogo_sepoltura in caduti_ministero ===")
cur.execute("SELECT COUNT(*) FROM caduti_ministero WHERE luogo_sepoltura IS NOT NULL AND luogo_sepoltura != ''")
print(f"Record con luogo_sepoltura valorizzato: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM caduti_ministero WHERE luogo_sepoltura IS NOT NULL AND TRIM(luogo_sepoltura) != ''")
print(f"Record con luogo_sepoltura non vuoto: {cur.fetchone()[0]}")

# Show some examples with luogo_sepoltura
cur.execute("SELECT * FROM caduti_ministero WHERE luogo_sepoltura IS NOT NULL AND TRIM(luogo_sepoltura) != '' LIMIT 5")
rows = cur.fetchall()
for r in rows:
    print("\n--- Esempio con luogo_sepoltura ---")
    for i, v in enumerate(r):
        if v is not None and str(v).strip():
            print(f"  {cols[i]}: {v}")

# Also check data_decesso field
print("\n\n=== Verifica campo data_decesso in caduti_ministero ===")
cur.execute("SELECT COUNT(*) FROM caduti_ministero WHERE data_decesso IS NOT NULL AND TRIM(data_decesso) != ''")
print(f"Record con data_decesso valorizzato: {cur.fetchone()[0]}")

conn.close()
