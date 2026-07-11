"""Quick test: verify _fetch_and_parse returns records for UK WW1 page 1"""
import sys
sys.path.insert(0, '.')
import requests
import caduti_cwgc as cwgc

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
    "Referer": "https://www.cwgc.org/find/find-war-dead/",
})

params = {"ServedWith": "United Kingdom", "WarSelect": "1"}
records, total_pages = cwgc._fetch_and_parse(session, {**params, "Page": "1"}, 1)
print(f"Records: {len(records)}, Total pages: {total_pages}")

if records:
    for i, r in enumerate(records[:3]):
        print(f"\n  Record {i}:")
        for k, v in r.items():
            if v:
                print(f"    {k}: {v}")
else:
    print("NO RECORDS PARSED!")
    # Debug: get raw page
    import re
    from bs4 import BeautifulSoup
    resp = session.get(cwgc.SEARCH_URL, params={**params, "Page": "1"}, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        print(f"\n  Table has {len(rows)} rows")
        for i, row in enumerate(rows[:3]):
            cells = row.find_all(["td", "th"])
            print(f"  Row {i}: {len(cells)} cells")
            for j, c in enumerate(cells):
                print(f"    Cell {j}: {c.get_text(' ', strip=True)[:100]}")
    links = soup.find_all("a", href=lambda h: h and 'casualty-details' in h)
    print(f"\n  Casualty links: {len(links)}")
