"""Test CWGC: approccio con solo Surname (senza filtri data), poi paginazione"""
import requests
import re
import csv
import io
import time

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Referer": "https://www.cwgc.org/find/find-war-dead/",
})

BASE = "https://www.cwgc.org"
SEARCH_URL = f"{BASE}/find-records/find-war-dead/search-results/"
EXPORT_URL = f"{BASE}/ExportCasualtySearch"

# Test 1: UK WW1, Surname="Sm" (common prefix)
params = {
    "ServedWith": "United Kingdom", "WarSelect": "1",
    "Surname": "Sm", "SurnameExact": "false",
    "Page": "1"
}
r = session.get(SEARCH_URL, params=params, timeout=30)
m = re.search(r'of\s+([\d,]+)\s+war\s+dead', r.text, re.I)
total = int(m.group(1).replace(",", "")) if m else 0
print(f"UK WW1 Surname='Sm*': {total}")

# Test 2: Export CSV UK WW1 Surname="Smi"
time.sleep(1.5)
r2 = session.get(EXPORT_URL, params={"ServedWith": "United Kingdom", "WarSelect": "1", "Surname": "Smi", "SurnameExact": "false"}, timeout=60)
print(f"\nExport UK WW1 'Smi*': Status={r2.status_code}, CT={r2.headers.get('Content-Type')}")
if 'csv' in r2.headers.get('Content-Type', '').lower():
    lines = r2.text.strip().split('\n')
    print(f"  Rows: {len(lines)-1}")

# Test 3: How about just WW1 alone (no nationality), surname = "Zz"
time.sleep(1.5)
params3 = {"WarSelect": "1", "Surname": "Zz", "SurnameExact": "false", "Page": "1"}
r3 = session.get(SEARCH_URL, params=params3, timeout=30)
m3 = re.search(r'of\s+([\d,]+)\s+war\s+dead', r3.text, re.I)
print(f"\nWW1 Surname='Zz*': {int(m3.group(1).replace(',','')) if m3 else 0}")

# Test 4: WW1 alone with UK, no surname, page 1
time.sleep(1.5)
params4 = {"ServedWith": "United Kingdom", "WarSelect": "1", "Page": "1"}
r4 = session.get(SEARCH_URL, params=params4, timeout=30)
m4 = re.search(r'of\s+([\d,]+)\s+war\s+dead', r4.text, re.I)
uk_ww1_total = int(m4.group(1).replace(",", "")) if m4 else 0
print(f"\nUK WW1 total (no surname): {uk_ww1_total:,}")

# Test 5: UK WW1, Surname starts with each letter
time.sleep(1.5)
print("\n=== UK WW1 per lettera ===")
total_check = 0
for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    params_l = {"ServedWith": "United Kingdom", "WarSelect": "1", "Surname": letter, "SurnameExact": "false", "Page": "1"}
    rl = session.get(SEARCH_URL, params=params_l, timeout=30)
    ml = re.search(r'of\s+([\d,]+)\s+war\s+dead', rl.text, re.I)
    tl = int(ml.group(1).replace(",", "")) if ml else 0
    total_check += tl
    print(f"  {letter}: {tl:,}")
    time.sleep(1.0)

print(f"\nSomma lettere: {total_check:,} vs totale: {uk_ww1_total:,}")
