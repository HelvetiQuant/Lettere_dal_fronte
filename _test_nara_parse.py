import requests, nara_catalog
session = requests.Session()
session.headers.update({"Accept": "application/json", "User-Agent": "IMI/1.0"})
params = {"q": "after action report italy 1944", "rows": 3, "offset": 0}
r = session.get("https://catalog.archives.gov/proxy/records/search", params=params, timeout=20)
hits = r.json()["body"]["hits"]["hits"]
for h in hits:
    try:
        rec = nara_catalog._parse_hit(h, "test")
        print(f"OK naId={rec['na_id']} rg={rec['record_group']} title={rec['title'][:60]}")
    except Exception as e:
        print(f"ERRORE: {e}")
