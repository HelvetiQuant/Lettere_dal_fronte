import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "imi_internati.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check caduti_ministero for Gaiaschi
print("=== Tabella caduti_ministero - ricerca Gaiaschi ===")
cur.execute("PRAGMA table_info(caduti_ministero)")
cols = [r[1] for r in cur.fetchall()]
print("Colonne:", cols)
print()

for col in cols:
    try:
        cur.execute(f"SELECT COUNT(*) FROM caduti_ministero WHERE CAST({col} AS TEXT) LIKE '%Gaiaschi%'")
        cnt = cur.fetchone()[0]
        if cnt > 0:
            print(f"Match su colonna '{col}': {cnt} record")
            cur.execute(f"SELECT * FROM caduti_ministero WHERE CAST({col} AS TEXT) LIKE '%Gaiaschi%'")
            rows = cur.fetchall()
            all_cols = [d[0] for d in cur.description]
            for r in rows:
                print("\n--- Record ---")
                for i, v in enumerate(r):
                    if v is not None and str(v).strip():
                        print(f"  {all_cols[i]}: {v}")
    except Exception as e:
        print(f"  Errore su colonna {col}: {e}")

# Also check caduti_cwgc
print("\n\n=== Tabella caduti_cwgc - ricerca Gaiaschi ===")
cur.execute("PRAGMA table_info(caduti_cwgc)")
cols2 = [r[1] for r in cur.fetchall()]
print("Colonne:", cols2)
for col in cols2:
    try:
        cur.execute(f"SELECT COUNT(*) FROM caduti_cwgc WHERE CAST({col} AS TEXT) LIKE '%Gaiaschi%'")
        cnt = cur.fetchone()[0]
        if cnt > 0:
            print(f"Match su colonna '{col}': {cnt} record")
            cur.execute(f"SELECT * FROM caduti_cwgc WHERE CAST({col} AS TEXT) LIKE '%Gaiaschi%'")
            rows = cur.fetchall()
            all_cols = [d[0] for d in cur.description]
            for r in rows:
                print("\n--- Record ---")
                for i, v in enumerate(r):
                    if v is not None and str(v).strip():
                        print(f"  {all_cols[i]}: {v}")
    except Exception as e:
        print(f"  Errore su colonna {col}: {e}")

# Check how many records are in caduti_ministero
cur.execute("SELECT COUNT(*) FROM caduti_ministero")
print(f"\n\nTotale record in caduti_ministero: {cur.fetchone()[0]}")

# Show a sample to understand the data
cur.execute("SELECT * FROM caduti_ministero LIMIT 3")
sample_cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    print("\n--- Esempio record ---")
    for i, v in enumerate(r):
        if v is not None and str(v).strip():
            print(f"  {sample_cols[i]}: {v}")

conn.close()
