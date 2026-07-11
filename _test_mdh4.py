import requests
import re
import json

# The site uses Arkothèque v8 with Elasticsearch
# Try to find the search API endpoint
# Common Arkothèque API patterns: /api/search, /api/arkotheque, /fr/arkotheque/client/mdh/

# Try 1: The global search API
urls_to_try = [
    "https://www.memoiredeshommes.defense.gouv.fr/api/search?q=*&base=morts_premiere_guerre",
    "https://www.memoiredeshommes.defense.gouv.fr/recherche-globale/rechercher-dans-les-bases-nominatives",
    "https://www.memoiredeshommes.defense.gouv.fr/fr/arkotheque/client/mdh/base_morts_pour_la_france_premiere_guerre/index.php",
]

for url in urls_to_try:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json"})
        print(f"\n=== {url} ===")
        print(f"Status: {resp.status_code}, Length: {len(resp.text)}")
        if resp.status_code == 200:
            # Check if JSON
            try:
                data = resp.json()
                print(f"JSON keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
            except:
                # HTML - look for form action or API hints
                forms = re.findall(r'action="([^"]*)"', resp.text)
                print(f"Forms: {forms}")
                # Look for any API endpoint in JS
                api_hints = re.findall(r'(?:url|endpoint|api)\s*[:=]\s*["\']([^"\']+)["\']', resp.text)
                print(f"API hints: {api_hints[:10]}")
                # Print first 2000 chars
                print(resp.text[:2000])
    except Exception as e:
        print(f"\n=== {url} === ERROR: {e}")
