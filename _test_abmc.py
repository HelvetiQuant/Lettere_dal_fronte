"""Test ABMC API endpoints"""
import requests
import json

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

# Test 1: API root
print("=== Test 1: API root ===")
r = session.get("https://api.abmc.gov/", timeout=15)
print(f"Status: {r.status_code}")
print(r.text[:500])

# Test 2: database-search-results con items_per_page=25
print("\n=== Test 2: search all ===")
params = {
    "field_last_name": "",
    "field_first_name": "",
    "items_per_page": 25,
    "page": 0,
    "_format": "json",
}
r2 = session.get("https://api.abmc.gov/database-search-results", params=params, timeout=15)
print(f"Status: {r2.status_code}")
print(f"Content-Type: {r2.headers.get('Content-Type','')}")
if r2.status_code == 200:
    try:
        data = r2.json()
        if isinstance(data, list):
            print(f"Records: {len(data)}")
            if data:
                print("First record keys:", list(data[0].keys()))
                print("First record:", json.dumps(data[0], indent=2)[:600])
        elif isinstance(data, dict):
            print("Keys:", list(data.keys()))
            print(str(data)[:600])
    except Exception as e:
        print(f"JSON error: {e}")
        print(r2.text[:500])
else:
    print(r2.text[:300])

# Test 3: try with _format=json on different path
print("\n=== Test 3: /api/decedents ===")
r3 = session.get("https://api.abmc.gov/api/decedents", params={"page": 0, "per_page": 10}, timeout=15)
print(f"Status: {r3.status_code}")
print(r3.text[:300])
