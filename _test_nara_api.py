"""Test NARA Catalog API v2 - After Action Reports WW2"""
import requests
import json

BASE = "https://catalog.archives.gov/api/v2"
session = requests.Session()
session.headers.update({"User-Agent": "IMI-Research/1.0 (academic research)"})

# Test 1: cerca "after action report" limitate all'Italia WW2
print("=== Test 1: After Action Reports Italy WW2 ===")
params = {
    "q": "after action report italy 1944 1945",
    "resultTypes": "item",
    "rows": 5,
    "offset": 0,
    "levelOfDescription": "item",
}
r = session.get(f"{BASE}/records/search", params=params, timeout=20)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    total = data.get("body", {}).get("hits", {}).get("total", {}).get("value", 0)
    print(f"Totale risultati: {total:,}")
    hits = data.get("body", {}).get("hits", {}).get("hits", [])
    for h in hits[:3]:
        src = h.get("_source", {})
        print(f"\n  naId: {src.get('naId')}")
        print(f"  title: {src.get('title', '')[:100]}")
        print(f"  description: {str(src.get('scopeAndContentNote', ''))[:100]}")
        objs = src.get("objects", [])
        print(f"  objects: {len(objs)}")
        if objs:
            print(f"  first obj: {objs[0].get('url') or objs[0].get('@id','')}")
else:
    print(r.text[:300])

# Test 2: cerca unità in Italia (5th Army, 36th Division, etc.)
print("\n=== Test 2: 5th Army Italy unit journals ===")
params2 = {
    "q": "\"5th Army\" Italy unit journal 1944",
    "resultTypes": "item",
    "rows": 5,
}
r2 = session.get(f"{BASE}/records/search", params=params2, timeout=20)
print(f"Status: {r2.status_code}")
if r2.status_code == 200:
    data2 = r2.json()
    total2 = data2.get("body", {}).get("hits", {}).get("total", {}).get("value", 0)
    print(f"Totale: {total2:,}")
    hits2 = data2.get("body", {}).get("hits", {}).get("hits", [])
    for h in hits2[:3]:
        src = h.get("_source", {})
        print(f"  naId={src.get('naId')} | {src.get('title','')[:80]}")

# Test 3: record series T315 (già noti) per capire struttura
print("\n=== Test 3: struttura record - naId per T315 ===")
params3 = {"q": "T315 117 Jaeger Division", "resultTypes": "item", "rows": 3}
r3 = session.get(f"{BASE}/records/search", params=params3, timeout=20)
print(f"Status: {r3.status_code}")
if r3.status_code == 200:
    data3 = r3.json()
    hits3 = data3.get("body", {}).get("hits", {}).get("hits", [])
    for h in hits3[:2]:
        src = h.get("_source", {})
        print(f"\n  naId: {src.get('naId')}")
        print(f"  title: {src.get('title','')[:100]}")
        print(f"  keys: {list(src.keys())[:15]}")
