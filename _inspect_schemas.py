import sqlite3
conn = sqlite3.connect('imi_internati.db')
for t in ['internati','caduti_albooro','decorati_nastroazzurro','caduti_cwgc','caduti_ministero']:
    print(f"=== {t} ===")
    try:
        for r in conn.execute(f"PRAGMA table_info({t})").fetchall():
            print(f"  {r[1]} {r[2]}")
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  -- rows: {cnt}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
conn.close()
