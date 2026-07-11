"""Test CWGC: paginazione diretta WW1 senza filtro cognome"""
import requests
import re
import time
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Referer": "https://www.cwgc.org/find/find-war-dead/",
})

BASE = "https://www.cwgc.org"
SEARCH_URL = f"{BASE}/find-records/find-war-dead/search-results/"
EXPORT_URL = f"{BASE}/ExportCasualtySearch"

# Test: UK WW1 page 1
params = {"ServedWith": "United Kingdom", "WarSelect": "1", "Page": "1"}
r = session.get(SEARCH_URL, params=params, timeout=30)
print(f"UK WW1 p1: {r.status_code}, {len(r.text)} bytes")

# Total
m = re.search(r'of\s+([\d,]+)\s+war\s+dead', r.text, re.I)
total = int(m.group(1).replace(",", "")) if m else 0
print(f"Total: {total:,}")

# Parse page structure
soup = BeautifulSoup(r.text, "html.parser")

# Check for result items
results = soup.find_all("li", class_=lambda c: c and "result" in str(c).lower())
print(f"Result items (li.result): {len(results)}")

# Check for table rows
table = soup.find("table")
if table:
    rows = table.find_all("tr")
    print(f"Table rows: {len(rows)}")
else:
    print("No table found")

# Check cards or other containers
cards = soup.find_all(class_=lambda c: c and ("card" in str(c).lower() or "casualty" in str(c).lower()))
print(f"Cards/casualty elements: {len(cards)}")

# Look for links to individual casualty pages
casualty_links = soup.find_all("a", href=re.compile(r'/find-records/find-war-dead/casualty-details/'))
print(f"Casualty detail links: {len(casualty_links)}")

if casualty_links:
    # Print first 3
    for i, link in enumerate(casualty_links[:3]):
        print(f"  {i}: {link.get('href')} | {link.get_text(strip=True)[:100]}")

# Look for pagination info
pag = soup.find(class_=lambda c: c and "pagination" in str(c).lower())
if pag:
    print(f"\nPagination: {pag.get_text(' ', strip=True)[:200]}")
else:
    # Look for page numbers
    page_links = soup.find_all("a", href=re.compile(r'Page=\d+', re.I))
    print(f"\nPage links: {len(page_links)}")
    if page_links:
        for pl in page_links[-5:]:
            print(f"  {pl.get('href')}")

# Check max page accessible
time.sleep(1.5)
params1000 = {"ServedWith": "United Kingdom", "WarSelect": "1", "Page": "1000"}
r2 = session.get(SEARCH_URL, params=params1000, timeout=30)
soup2 = BeautifulSoup(r2.text, "html.parser")
links2 = soup2.find_all("a", href=re.compile(r'/find-records/find-war-dead/casualty-details/'))
print(f"\nPage 1000: {len(links2)} casualty links")

# Export CSV test without surname
time.sleep(1.5)
r3 = session.get(EXPORT_URL, params={"ServedWith": "United Kingdom", "WarSelect": "1"}, timeout=60)
print(f"\nExport UK WW1 (no surname): Status={r3.status_code}, CT={r3.headers.get('Content-Type')}")
if 'csv' in r3.headers.get('Content-Type', '').lower():
    lines = r3.text.strip().split('\n')
    print(f"  Rows: {len(lines)-1}")
    if len(lines) > 1:
        print(f"  First: {lines[1][:200]}")
    if len(lines) > 1000:
        print(f"  Last: {lines[-1][:200]}")
elif r3.status_code == 200:
    print(f"  Response: {r3.text[:500]}")
