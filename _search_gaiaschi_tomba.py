import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "imi_internati.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Get all tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tabelle disponibili:", tables)
print()

for table in tables:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    # Search for Gaiaschi in all text columns
    text_cols = []
    for col in cols:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE CAST({col} AS TEXT) LIKE '%Gaiaschi%'")
            cnt = cur.fetchone()[0]
            if cnt > 0:
                text_cols.append(col)
        except:
            pass
    if text_cols:
        print(f"=== Tabella: {table} ===")
        print(f"Colonne con 'Gaiaschi': {text_cols}")
        for col in text_cols:
            cur.execute(f"SELECT * FROM {table} WHERE CAST({col} AS TEXT) LIKE '%Gaiaschi%'")
            rows = cur.fetchall()
            all_cols = [d[0] for d in cur.description]
            for r in rows:
                print(f"\n--- Record (match su colonna '{col}') ---")
                for i, v in enumerate(r):
                    if v is not None and str(v).strip():
                        print(f"  {all_cols[i]}: {v}")
                print()

# Also search for any column containing 'tomba' or 'sepolt' or 'cimitero' or 'sacrario'
print("\n\n=== Ricerca colonne relate a sepoltura ===")
for table in tables:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    for col in cols:
        col_lower = col.lower()
        if any(k in col_lower for k in ['tomb', 'sepol', 'cimiter', 'sacrari', 'burial', 'grave', 'tumul']):
            print(f"  Tabella {table}, colonna: {col}")

conn.close()
