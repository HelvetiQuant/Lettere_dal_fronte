"""Test manuale dell'API CWGC - verifica struttura risposta e export CSV"""
import requests
import re
import csv
import io

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Referer": "https://www.cwgc.org/find/find-war-dead/",
})

BASE = "https://www.cwgc.org"
SEARCH_URL = f"{BASE}/find-records/find-war-dead/search-results/"
EXPORT_URL = f"{BASE}/ExportCasualtySearch"

# Test 1: WW1 Italian, dovrebbe essere ~639 caduti
params_it_ww1 = {"ServedWith": "Italian", "WarSelect": "1", "AgeOfDeath": "0", "Page": "1"}
r = session.get(SEARCH_URL, params=params_it_ww1, timeout=30)
print(f"IT WW1 page 1: {r.status_code}, {len(r.text)} bytes")
m = re.search(r'of\s+([\d,]+)\s+war\s+dead', r.text, re.I)
if m:
    print(f"  Total: {m.group(1)} war dead")
else:
    # Try other patterns
    m2 = re.search(r'(\d[\d,]*)\s+(?:results?|casualties?|records?)', r.text, re.I)
    if m2:
        print(f"  Total (alt): {m2.group(1)}")
    else:
        print("  No total found in page")
        # Print around search-results
        idx = r.text.lower().find('result')
        if idx > 0:
            clean = re.sub(r'<[^>]+>', ' ', r.text[max(0,idx-200):idx+500])
            clean = re.sub(r'\s+', ' ', clean).strip()
            print(f"  Context: {clean[:400]}")

# Test 2: Export CSV for Italian WW1
print("\n--- Export CSV Italian WW1 ---")
r2 = session.get(EXPORT_URL, params={"ServedWith": "Italian", "WarSelect": "1"}, timeout=60)
print(f"  Status: {r2.status_code}, Content-Type: {r2.headers.get('Content-Type')}")
print(f"  Length: {len(r2.text)}")
if 'csv' in r2.headers.get('Content-Type', '').lower() or r2.text.startswith('"'):
    lines = r2.text.strip().split('\n')
    print(f"  Rows: {len(lines)} (incl header)")
    if lines:
        print(f"  Header: {lines[0][:300]}")
    if len(lines) > 1:
        print(f"  First row: {lines[1][:300]}")
else:
    print(f"  Response (first 500): {r2.text[:500]}")

# Test 3: UK WW1 1916 July (should be large - Battle of the Somme)
print("\n--- UK WW1 1916 July total ---")
params_uk = {
    "ServedWith": "United Kingdom", "WarSelect": "1", "AgeOfDeath": "0",
    "DateDeathFromYear": "1916", "DateDeathFromMonth": "7", "DateDeathFromDay": "1",
    "DateDeathToYear": "1916", "DateDeathToMonth": "7", "DateDeathToDay": "31",
    "Page": "1"
}
r3 = session.get(SEARCH_URL, params=params_uk, timeout=30)
print(f"  Status: {r3.status_code}, Length: {len(r3.text)}")
m3 = re.search(r'of\s+([\d,]+)\s+war\s+dead', r3.text, re.I)
if m3:
    print(f"  Total: {m3.group(1)} war dead")
else:
    m3b = re.search(r'(\d[\d,]*)\s+(?:results?|casualties?|records?)', r3.text, re.I)
    if m3b:
        print(f"  Total (alt): {m3b.group(1)}")
    else:
        print("  No total found")
        # Check if page structure changed
        if 'no results' in r3.text.lower() or 'no casualties' in r3.text.lower():
            print("  PAGE SAYS: no results")
        # Look for any number > 1000
        big_nums = re.findall(r'[\d,]{4,}', r3.text)
        print(f"  Big numbers in page: {big_nums[:10]}")
