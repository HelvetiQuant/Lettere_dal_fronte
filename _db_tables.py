from database import get_conn
conn = get_conn()
tabs = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("Tabelle nel DB:")
for r in tabs:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {r[0]}").fetchone()[0]
        print(f"  {r[0]}: {n:,}")
    except:
        print(f"  {r[0]}: (errore)")
conn.close()
