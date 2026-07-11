import requests
r3 = requests.get('http://127.0.0.1:8020/api/ministero').json()
print(f"Ministero: {r3['count']} | {r3['progress']['status']} | {r3['progress']['current']}")
r4 = requests.get('http://127.0.0.1:8020/api/sardi').json()
print(f"Sardi: {r4['count']} | {r4['progress']['status']} | {r4['progress']['current']}")
