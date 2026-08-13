"""Search for GUCCINI across all person tables."""
import sqlite3

conn = sqlite3.connect("imi_internati.db")
c = conn.cursor()

tables_to_search = [
    "internati", "caduti_albooro", "caduti_bologna", "caduti_cwgc",
    "caduti_ministero", "caduti_sardi", "decorati", "decorati_nastroazzurro",
    "caduti_francia_ww1",
]

for table in tables_to_search:
    try:
        # Get columns
        c.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in c.fetchall()]
        # Search in all text columns
        text_cols = [col for col in cols if col not in ("id",)]
        conditions = " OR ".join([f"{col} LIKE '%GUCCINI%'" for col in text_cols])
        c.execute(f"SELECT * FROM {table} WHERE {conditions} LIMIT 5")
        rows = c.fetchall()
        if rows:
            print(f"\n=== {table} ({len(rows)} matches) ===")
            print(f"Columns: {cols}")
            for r in rows:
                print(r)
    except Exception as e:
        print(f"  {table}: error - {e}")

conn.close()
