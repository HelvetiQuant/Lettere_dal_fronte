import sqlite3
conn = sqlite3.connect('imi_internati.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in c.fetchall()]
print("Tabelle nel DB:")
for t in tables:
    try:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        n = c.fetchone()[0]
        print(f"  {t}: {n:,}")
    except:
        print(f"  {t}: (errore)")
conn.close()
