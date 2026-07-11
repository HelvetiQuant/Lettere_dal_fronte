import requests, time

# Avvia Albo d'Oro (con fix lettere)
r1 = requests.post('http://127.0.0.1:8020/api/albooro/scrape')
print(f"Albo d'Oro: {r1.status_code} {r1.json()}")
time.sleep(1)

# Avvia Caduti Bolognesi (fixato)
r2 = requests.post('http://127.0.0.1:8020/api/bologna/scrape')
print(f"Bologna: {r2.status_code} {r2.json()}")
time.sleep(1)

# Avvia Ministero Difesa
r3 = requests.post('http://127.0.0.1:8020/api/ministero/scrape')
print(f"Ministero: {r3.status_code} {r3.json()}")
time.sleep(1)

# Avvia Caduti Sardi
r4 = requests.post('http://127.0.0.1:8020/api/sardi/scrape')
print(f"Sardi: {r4.status_code} {r4.json()}")
