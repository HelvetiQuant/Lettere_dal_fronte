"""Cerca i link ai file ZIP/CSV nella pagina di download Mémoire des Hommes.
La pagina usa Arkothèque che carica il contenuto via AJAX."""
import requests
import re
import json

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# Step 1: Get the page and extract any AJAX loading URLs
url = "https://www.memoiredeshommes.defense.gouv.fr/conflits-operations/telechargement-des-bases"
resp = session.get(url, timeout=30)

# Find the data-resultats section ID
resultats_match = re.search(r'id="(arko_default_[^"]+)"[^>]*data-mode="mode-restitution-normal"', resp.text)
if resultats_match:
    print(f"Resultats ID: {resultats_match.group(1)}")

# Find the AJAX endpoint in JS
# Look for JS that loads the opendata/download content
js_blocks = re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.DOTALL)
for i, block in enumerate(js_blocks):
    if 'arko' in block.lower() or 'ajax' in block.lower() or 'opendata' in block.lower():
        print(f"\n=== Script block {i} ===")
        print(block[:2000])

# Try to find fosjsrouting routes
routing_resp = session.get("https://www.memoiredeshommes.defense.gouv.fr/js/routing?callback=fos.Router.setData", timeout=30)
if routing_resp.status_code == 200:
    # Extract the JSON from the JSONP callback
    jsonp = routing_resp.text
    json_start = jsonp.find('{')
    json_end = jsonp.rfind('}') + 1
    if json_start >= 0:
        data = json.loads(jsonp[json_start:json_end])
        routes = data.get('routes', {})
        print(f"\n=== Symfony Routes ({len(routes)}) ===")
        for name, route in routes.items():
            path = route.get('path', '')
            if any(k in name.lower() or k in path.lower() for k in ['search', 'result', 'download', 'telecharg', 'base', 'opendata', 'fiche', 'image']):
                print(f"  {name}: {path}")

# Try specific Arkothèque endpoints
arko_urls = [
    "/arkotheque/navigation_facette/index.php?f=opendata",
    "/arkotheque/client/mdh/base_morts_pour_la_france_premiere_guerre/index.php",
    "/api/arkotheque/search",
    "/fr/arkotheque/navigation_facette/index.php?f=opendata",
]
for path in arko_urls:
    full_url = f"https://www.memoiredeshommes.defense.gouv.fr{path}"
    try:
        r = session.get(full_url, timeout=15)
        print(f"\n{path}: {r.status_code} ({len(r.text)} bytes)")
        if r.status_code == 200 and len(r.text) > 500:
            # Look for download links
            zips = re.findall(r'href="([^"]*\.zip[^"]*)"', r.text)
            csvs = re.findall(r'href="([^"]*\.csv[^"]*)"', r.text)
            print(f"  ZIP: {zips[:5]}")
            print(f"  CSV: {csvs[:5]}")
    except Exception as e:
        print(f"\n{path}: ERROR {e}")
