"""Test NARA Catalog API - endpoint proxy/records/search"""
import requests
import json

BASE = "https://catalog.archives.gov/proxy/records/search"
session = requests.Session()
session.headers.update({
    "User-Agent": "IMI-Research/1.0 (academic historical research)",
    "Accept": "application/json",
})

def search(q, rows=5, offset=0, **kwargs):
    params = {"q": q, "rows": rows, "offset": offset}
    params.update(kwargs)
    r = session.get(BASE, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# Test 1: After Action Reports unità USA in Italia
print("=== Test 1: AAR Italy 1944-1945 ===")
d = search("after action report italy 1944 1945", rows=5)
total = d["body"]["hits"]["total"]["value"]
print(f"Totale: {total:,}")
for h in d["body"]["hits"]["hits"][:3]:
    rec = h["_source"].get("record", {})
    print(f"\n  naId: {h['_id']}")
    print(f"  title: {rec.get('title','')[:100]}")
    print(f"  description: {str(rec.get('scopeAndContentNote',''))[:120]}")
    print(f"  date: {rec.get('inclusiveDates','')}")
    objs = rec.get("objects", []) or []
    print(f"  objects: {len(objs)}")
    if objs:
        url = objs[0].get("url") or objs[0].get("path","")
        print(f"  first file: {url[:100]}")

# Test 2: Unit Journals 5th Army Italy
print("\n=== Test 2: 5th Army Italy unit journal ===")
d2 = search('"5th Army" italy "unit journal"', rows=5)
total2 = d2["body"]["hits"]["total"]["value"]
print(f"Totale: {total2:,}")
for h in d2["body"]["hits"]["hits"][:3]:
    rec = h["_source"].get("record", {})
    print(f"  naId={h['_id']} | {rec.get('title','')[:80]} | {rec.get('inclusiveDates','')}")

# Test 3: Morning Reports Italy WW2
print("\n=== Test 3: Morning Reports Italy ===")
d3 = search('"morning report" italy 1944 1945 prisoners', rows=5)
total3 = d3["body"]["hits"]["total"]["value"]
print(f"Totale: {total3:,}")
for h in d3["body"]["hits"]["hits"][:3]:
    rec = h["_source"].get("record", {})
    print(f"  naId={h['_id']} | {rec.get('title','')[:80]}")

# Test 4: Record Groups rilevanti - RG 92, 94, 407
print("\n=== Test 4: Record Group 407 (AAR WW2) ===")
d4 = search("after action report italy", rows=5, recordGroupNumber="407")
total4 = d4["body"]["hits"]["total"]["value"]
print(f"Totale RG407 italy: {total4:,}")
for h in d4["body"]["hits"]["hits"][:3]:
    rec = h["_source"].get("record", {})
    print(f"  naId={h['_id']} | {rec.get('title','')[:80]} | {rec.get('inclusiveDates','')}")
    objs = rec.get("objects", []) or []
    if objs:
        print(f"    file: {str(objs[0])[:150]}")
