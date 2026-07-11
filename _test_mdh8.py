import requests
import json

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
})

BASE = "https://www.memoiredeshommes.defense.gouv.fr"

# The page uses search with an ID parameter
# We need to find the moteur ID - let's check the page source
resp = session.get(f"{BASE}/recherche-globale/rechercher-dans-les-bases-nominatives", timeout=30)
import re
# Find moteur references
moteur_ids = re.findall(r'data-moteur="(\d+)"', resp.text)
search_ids = re.findall(r'"(?:moteur|search|recherche)"\s*:\s*(\d+)', resp.text)
ref_ids = re.findall(r'"ref_unique_moteur"\s*:\s*"([^"]+)"', resp.text)
arko_ids = re.findall(r'arko_default_([a-f0-9]+)', resp.text)
section_ids = re.findall(r'data-section-id="(\d+)"', resp.text)

print(f"moteur_ids: {moteur_ids}")
print(f"search_ids: {search_ids}")
print(f"ref_ids: {ref_ids}")
print(f"arko_ids: {list(set(arko_ids))}")
print(f"section_ids: {section_ids}")

# Also look for the search page specific form/config
config_matches = re.findall(r'data-[a-zA-Z-]+="([^"]*)"', resp.text)
config_filtered = [c for c in config_matches if c and len(c) < 50 and any(k in c for k in ['moteur', 'search', 'base', 'nominat'])]
print(f"\nConfig hints: {config_filtered}")

# Find JSON config blocks
json_configs = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
print(f"\nJSON configs: {len(json_configs)}")
for i, jc in enumerate(json_configs):
    try:
        d = json.loads(jc)
        print(f"\n  Config {i}: {json.dumps(d, indent=2, ensure_ascii=False)[:1000]}")
    except:
        print(f"\n  Config {i} (raw): {jc[:500]}")

# Try different search endpoint IDs
for search_id in [1, 2, 3, 5, 10]:
    url = f"{BASE}/_recherche-api/search-simple/{search_id}"
    try:
        r = session.get(url, timeout=10, params={"q": "VALLON"})
        print(f"\nSearch ID {search_id}: {r.status_code} ({len(r.text)} bytes)")
        if r.status_code == 200 and len(r.text) > 100:
            print(r.text[:1000])
    except Exception as e:
        print(f"\nSearch ID {search_id}: ERROR {e}")
