import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'imi_internati.db'
conn = sqlite3.connect(str(DB_PATH))
c = conn.cursor()

TABLES = [
    ('caduti_cwgc', '~1.763.187'),
    ('caduti_albooro', '~342.555'),
    ('caduti_ministero', '~162.646'),
    ('caduti_sardi', '~20.435'),
    ('caduti_bologna', '~9.656'),
    ('internati', '20.464'),
    ('documenti_nara_t315', '1.153'),
    ('decorati', '1.286'),
    ('entita', '-'),
    ('collegamenti', '-'),
]

print("=== STATUS IMI DATABASE ===\n")
total_db = 0
for tbl, target in TABLES:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        total_db += n
        pct = f"{n/int(target.replace('~','').replace('.','').replace(',',''))*100:.1f}%" if target not in ('-',) and target[0] != '~' else ""
        if target.startswith('~'):
            t = int(target[1:].replace('.','').replace(',',''))
            pct = f"{n/t*100:.1f}%"
        print(f"  {tbl:<28} {n:>10,}  target={target}  {pct}")
    except Exception as e:
        print(f"  {tbl:<28} ERRORE: {e}")

print(f"\n  TOTALE DB: {total_db:,}")

print("\n--- CWGC per guerra ---")
for r in conn.execute("SELECT guerra, COUNT(*) FROM caduti_cwgc GROUP BY guerra").fetchall():
    print(f"  {r[0] or '(non assegnato)'}: {r[1]:,}")

print("\n--- CWGC top nazionalita ---")
for r in conn.execute("SELECT nationality, COUNT(*) FROM caduti_cwgc GROUP BY nationality ORDER BY COUNT(*) DESC LIMIT 10").fetchall():
    print(f"  {r[0]}: {r[1]:,}")

conn.close()
