import sqlite3
conn = sqlite3.connect('imi_internati.db')
cur = conn.cursor()
# Check new tables
new_tables = ['decorati_nastroazzurro', 'caduti_francia_ww1']
for t in new_tables:
    try:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {cnt:,}")
    except Exception as e:
        print(f"{t}: {e}")
# Total across all tables
all_tables = ['internati','decorati','caduti_albooro','caduti_ministero','caduti_sardi',
              'caduti_bologna','caduti_cwgc','documenti_nara_t315','decorati_nastroazzurro',
              'caduti_francia_ww1']
total = 0
for t in all_tables:
    try:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        total += cnt
    except:
        pass
print(f"\nTOTALE RECORD: {total:,}")
conn.close()
