import requests
from database import get_conn

# Test endpoint fonti per ALTA Antonio (id=2344, Bolzano)
r = requests.get("http://127.0.0.1:8000/api/internati/2344/fonti?limit=10")
d = r.json()
print(f"ALTA Antonio — fonti total: {d.get('total')}")
for arch, items in list((d.get("by_archive") or {}).items())[:4]:
    print(f"  {arch}: {len(items)} fonti")
    if items:
        print(f"    prima: {items[0]['titolo'][:60]} | {items[0]['url'][:60]}")

# Verifica fonti_indice
conn = get_conn()
n_onor = conn.execute("SELECT COUNT(*) FROM fonti_indice WHERE archivio LIKE '%ONORCADUTI%'").fetchone()[0]
n_tot  = conn.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
conn.close()
print(f"\nfonti_indice ONORCADUTI: {n_onor}")
print(f"fonti_indice TOTALE:     {n_tot}")
