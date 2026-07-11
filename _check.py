import requests
r1 = requests.get('http://127.0.0.1:8020/api/albooro').json()
print(f"Albo d'Oro: {r1['count']} | {r1['progress']['status']} | {r1['progress']['processed']}/{r1['progress']['total']} | vol: {r1['progress']['volume']}")
r2 = requests.get('http://127.0.0.1:8020/api/bologna').json()
print(f"Bologna: {r2['count']} | {r2['progress']['status']} | {r2['progress']['processed']}/{r2['progress']['total']}")
r3 = requests.get('http://127.0.0.1:8020/api/status').json()
print(f"Internati: {r3['total_internati']}")
