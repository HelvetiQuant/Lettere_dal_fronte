import requests

print("=== /api/graph/luoghi ===")
r = requests.get('http://localhost:8201/api/graph/luoghi?limit=5')
print(f"Status: {r.status_code}")
d = r.json()
print(f"Nodes: {d['total']}")
for n in d['nodes']:
    print(f"  {n['luogo']:30s} count={n['count']:>6} eventi={len(n['eventi'])}")

print("\n=== /api/graph/mesi ===")
r = requests.get('http://localhost:8201/api/graph/mesi')
print(f"Status: {r.status_code}")
d = r.json()
for n in d['nodes']:
    print(f"  {n['anno']} caduti={n['caduti']:>6} decorati={n['decorati']:>6} totale={n['totale']:>6}")

print("\n=== /api/graph/paesi ===")
r = requests.get('http://localhost:8201/api/graph/paesi')
print(f"Status: {r.status_code}")
d = r.json()
for n in d['nodes']:
    print(f"  {n['teatro']:20s} count={n['count']:>6} luoghi={n['luoghi_count']}")

print("\n=== /api/graph/soldati/architecture ===")
r = requests.get('http://localhost:8201/api/graph/soldati/architecture')
print(f"Status: {r.status_code}")
d = r.json()
print(f"Total soldati: {d['total_soldati']}")
print(f"With luogo: {d['with_luogo']}")
print(f"With reparto: {d['with_reparto']}")
print(f"Strategy: {d['strategy']['approach']}")
print(f"Top luoghi: {d['top_clusters']['luoghi'][:3]}")

print("\n=== /api/graph/soldati/clusters ===")
r = requests.get('http://localhost:8201/api/graph/soldati/clusters?field=luogo_morte&limit=5')
print(f"Status: {r.status_code}")
d = r.json()
for c in d['clusters']:
    print(f"  {c['cluster']:30s} count={c['count']}")

print("\n=== /api/graph/soldati/cluster/luogo_morte/Carso ===")
r = requests.get('http://localhost:8201/api/graph/soldati/cluster/luogo_morte/Carso?page=1&limit=3')
print(f"Status: {r.status_code}")
d = r.json()
print(f"Total: {d['total']}, Pages: {d['total_pages']}")
for s in d['soldati']:
    print(f"  {s['nominativo']:30s} grado={s['grado']} anno={s['anno_morte']}")
