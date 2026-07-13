import requests, time

BASE = "https://discovery.nationalarchives.gov.uk/API/search/records"
headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

tests = [
    {"sps.searchQuery": "Italian prisoner", "sps.resultsPageSize": 5},
    {"sps.searchQuery": "Italian prisoner", "sps.resultsPageSize": 5,
     "sps.dateFrom": "1939", "sps.dateTo": "1945"},
    {"sps.searchQuery": "ALTA Italian", "sps.resultsPageSize": 5},
    {"sps.searchQuery": "ALTA Italian", "sps.resultsPageSize": 5,
     "sps.dateFrom": "1939", "sps.dateTo": "1945"},
    {"sps.searchQuery": "Italian prisoner", "sps.resultsPageSize": 5,
     "sps.recordSeries[0]": "WO 392"},
    {"sps.searchQuery": "*", "sps.resultsPageSize": 5,
     "sps.dateFrom": "1939", "sps.dateTo": "1945",
     "sps.recordSeries[0]": "WO 392"},
]

for p in tests:
    try:
        r = requests.get(BASE, params=p, headers=headers, timeout=15)
        count = ""
        try:
            count = f"count={r.json().get('count', '?')}"
        except Exception:
            count = r.text[:60]
        print(f"HTTP {r.status_code} | {count} | {list(p.items())[:2]}")
    except Exception as e:
        print(f"ERR {e} | {list(p.items())[:2]}")
    time.sleep(1.5)
