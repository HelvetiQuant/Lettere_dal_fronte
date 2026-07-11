import requests, time

BASE = "http://127.0.0.1:8020"

# Start Ministero
r = requests.post(f"{BASE}/api/ministero/scrape")
print(f"Ministero: {r.status_code} {r.json()}")

time.sleep(3)

# Start Sardi
r2 = requests.post(f"{BASE}/api/sardi/scrape")
print(f"Sardi: {r2.status_code} {r2.json()}")

time.sleep(5)

# Check progress
r3 = requests.get(f"{BASE}/api/ministero").json()
print(f"Ministero: {r3['count']} | {r3['progress']['status']} | {r3['progress']['current']}")

r4 = requests.get(f"{BASE}/api/sardi").json()
print(f"Sardi: {r4['count']} | {r4['progress']['status']} | {r4['progress']['current']}")
