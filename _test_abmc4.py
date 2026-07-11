"""Analisi bundle Angular ABMC per trovare endpoint API"""
import requests
import re

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

# Scarica main.js Angular
print("Scarico main.js...")
r = session.get("https://www.abmc.gov/app/aw-ui-angular/main.js", timeout=30)
print(f"Status: {r.status_code}, size: {len(r.text):,} chars")

js = r.text

# Cerca URL API/endpoint
print("\n=== URL API trovati ===")
urls = set(re.findall(r'["\'](?:https?://[^"\']{10,}|/api/[^"\']{5,}|/rest/[^"\']{5,}|/views/[^"\']{5,})["\']', js))
for u in sorted(urls)[:40]:
    print(f"  {u}")

# Cerca pattern endpoint specifici per decedent/casualty/search
print("\n=== Pattern decedent/search ===")
for m in re.finditer(r'["\']([^"\']*(?:decedent|casualty|search|burials?)[^"\']*)["\']', js, re.I):
    val = m.group(1)
    if len(val) > 5 and len(val) < 150:
        print(f"  {val}")

# Cerca base URL
print("\n=== Base URL / environment ===")
for m in re.finditer(r'(?:baseUrl|apiUrl|BASE_URL|endpoint|serviceUrl)["\s:=]+["\']([^"\']+)["\']', js, re.I):
    print(f"  {m.group()[:120]}")

# Cerca parametri di paginazione
print("\n=== Paginazione ===")
for m in re.finditer(r'(?:items_per_page|pageSize|per_page|page_size)["\s:=]+(\d+)', js, re.I):
    print(f"  {m.group()}")
