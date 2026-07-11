"""Test ABMC sito principale - ricerca caduti"""
import requests
from bs4 import BeautifulSoup
import json

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
    "Referer": "https://www.abmc.gov/",
})

# Test 1: cerca Drupal JSON API
print("=== Test 1: Drupal JSON API ===")
urls = [
    "https://www.abmc.gov/api/decedents?page=0",
    "https://www.abmc.gov/database-search?_format=json",
    "https://www.abmc.gov/database-search-results?_format=json&items_per_page=10&page=0",
    "https://www.abmc.gov/decedent-search?_format=json",
]
for url in urls:
    r = session.get(url, timeout=15)
    ct = r.headers.get("Content-Type", "")
    print(f"  {url[:60]} -> {r.status_code} {ct[:30]}")
    if r.status_code == 200 and "json" in ct:
        print(f"    JSON: {r.text[:200]}")

# Test 2: weremember.abmc.gov (Angular app)
print("\n=== Test 2: weremember.abmc.gov ===")
r2 = session.get("https://weremember.abmc.gov/", timeout=15)
print(f"Status: {r2.status_code}, len={len(r2.text)}")

# Test 3: cerca API JS nel sito
print("\n=== Test 3: JS sources ===")
r3 = session.get("https://www.abmc.gov/database-search-results", timeout=15)
print(f"Status: {r3.status_code}")
if r3.status_code == 200:
    soup = BeautifulSoup(r3.text, "html.parser")
    # Cerca endpoint API nei tag script
    for s in soup.find_all("script", src=True):
        src = s.get("src", "")
        if any(k in src for k in ["api", "search", "data"]):
            print(f"  Script: {src}")
    # Cerca JSON inline
    for s in soup.find_all("script", src=False):
        txt = s.get_text()
        if "apiUrl" in txt or "baseUrl" in txt or "endpoint" in txt.lower():
            print(f"  Inline JS snippet: {txt[:300]}")
    # Cerca link ai dati
    total_text = soup.get_text(" ", strip=True)
    for kw in ["decedent", "casualty", "api", "json", "total"]:
        idx = total_text.lower().find(kw)
        if idx > 0:
            print(f"  [{kw}]: ...{total_text[max(0,idx-30):idx+60]}...")
            break
