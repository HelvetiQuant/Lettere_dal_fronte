import sqlite3
conn = sqlite3.connect('imi_internati.db')
cur = conn.cursor()
tables = ['internati','decorati','caduti_albooro','caduti_ministero','caduti_sardi','caduti_bologna','caduti_cwgc','documenti_nara_t315','entita','collegamenti']
for t in tables:
    try:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {cnt:,}")
    except Exception as e:
        print(f"{t}: ERROR {e}")
conn.close()
