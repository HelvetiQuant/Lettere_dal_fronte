"""Test: sotto-partizionamento per lettera cognome + export CSV"""
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

# Test: UK WW1 1916 July, surname starting with "A"
params = {
    "ServedWith": "United Kingdom", "WarSelect": "1", "AgeOfDeath": "0",
    "DateDeathFromYear": "1916", "DateDeathFromMonth": "7", "DateDeathFromDay": "1",
    "DateDeathToYear": "1916", "DateDeathToMonth": "7", "DateDeathToDay": "31",
    "Surname": "A",
    "SurnameExact": "false",
    "Page": "1"
}

r = session.get(SEARCH_URL, params=params, timeout=30)
m = re.search(r'of\s+([\d,]+)\s+war\s+dead', r.text, re.I)
total_a = int(m.group(1).replace(",", "")) if m else 0
print(f"UK WW1 1916 July, surname 'A*': {total_a} war dead")

# Test export CSV with surname filter
time.sleep(1)
export_params = {
    "ServedWith": "United Kingdom", "WarSelect": "1",
    "DateDeathFromYear": "1916", "DateDeathFromMonth": "7", "DateDeathFromDay": "1",
    "DateDeathToYear": "1916", "DateDeathToMonth": "7", "DateDeathToDay": "31",
    "Surname": "Ab",
    "SurnameExact": "false",
}
r2 = session.get(EXPORT_URL, params=export_params, timeout=60)
print(f"\nExport 'Ab*': Status={r2.status_code}, CT={r2.headers.get('Content-Type')}")
if 'csv' in r2.headers.get('Content-Type', '').lower():
    lines = r2.text.strip().split('\n')
    print(f"  Rows: {len(lines)-1}")
    if len(lines) > 1:
        print(f"  First: {lines[1][:200]}")

# Test with "Aa" to see very small partition
time.sleep(1)
export_params2 = {**export_params, "Surname": "Aa"}
r3 = session.get(EXPORT_URL, params=export_params2, timeout=60)
if 'csv' in r3.headers.get('Content-Type', '').lower():
    lines3 = r3.text.strip().split('\n')
    print(f"\nExport 'Aa*': {len(lines3)-1} rows")

# Test full "A" export (will likely be capped at 1000)
time.sleep(1)
export_params3 = {**export_params, "Surname": "A"}
r4 = session.get(EXPORT_URL, params=export_params3, timeout=60)
if 'csv' in r4.headers.get('Content-Type', '').lower():
    lines4 = r4.text.strip().split('\n')
    print(f"\nExport 'A*' (should be capped): {len(lines4)-1} rows (total={total_a})")

# Conclusione: verifichiamo la strategia 2-letter prefix per partizionare sotto 1000
time.sleep(1)
print("\n\n=== Verifica strategia 2-letter prefix ===")
# Check some 2-letter combos for UK WW1 1916 July
for prefix in ["Ba", "Be", "Bi", "Bo", "Br", "Bu", "Ca", "Ch", "Cl", "Co", "Cr", "Cu"]:
    params_p = {
        "ServedWith": "United Kingdom", "WarSelect": "1",
        "DateDeathFromYear": "1916", "DateDeathFromMonth": "7", "DateDeathFromDay": "1",
        "DateDeathToYear": "1916", "DateDeathToMonth": "7", "DateDeathToDay": "31",
        "Surname": prefix, "SurnameExact": "false", "Page": "1"
    }
    rp = session.get(SEARCH_URL, params=params_p, timeout=30)
    mp = re.search(r'of\s+([\d,]+)\s+war\s+dead', rp.text, re.I)
    tp = int(mp.group(1).replace(",", "")) if mp else 0
    print(f"  '{prefix}*': {tp}")
    time.sleep(0.8)
