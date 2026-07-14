from database import get_conn
conn = get_conn()
conn.row_factory = lambda c,r: dict(zip([col[0] for col in c.description],r))
tot = conn.execute("SELECT COUNT(*) as n FROM fonti_indice").fetchone()
url_ok = conn.execute("SELECT COUNT(*) as n FROM fonti_indice WHERE url_catalogo IS NOT NULL AND url_catalogo != ''").fetchone()
top = conn.execute("SELECT archivio, COUNT(*) as n FROM fonti_indice GROUP BY archivio ORDER BY n DESC LIMIT 10").fetchall()
wdog = None
try:
    import json, pathlib
    snap = pathlib.Path("watchdog_snapshot.json")
    if snap.exists():
        wdog = json.loads(snap.read_text(encoding="utf-8"))
except: pass
print("=== FONTI_INDICE ===")
print(f"  Totale:   {tot['n']:,}")
print(f"  Con URL:  {url_ok['n']:,}")
print("  Top archivi:")
for r in top: print(f"    {r['archivio']:30s} {r['n']:6,}")
if wdog:
    print("\n=== WATCHDOG SNAPSHOT ===")
    print(f"  Check #{wdog.get('check')} @ {wdog.get('ts')}")
    p = wdog.get('pipeline',{})
    print(f"  Pipeline: running={p.get('running')} mode={p.get('mode')} error={p.get('error')}")
else:
    print("\n(nessun snapshot watchdog trovato)")
conn.close()
