import requests
import re
import json

# Get the Symfony JS routing data
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# First get the routing config
resp = session.get("https://www.memoiredeshommes.defense.gouv.fr/js/routing?callback=fos.Router.setData", timeout=30)
print(f"Routing: Status={resp.status_code}, Length={len(resp.text)}")
if resp.status_code == 200:
    # This is JS that sets routing data
    # Find all route definitions
    routes = re.findall(r'"([^"]+)":\s*\{"path":\s*"([^"]*)"', resp.text)
    print(f"\nRoutes found: {len(routes)}")
    for name, path in routes:
        if any(k in name.lower() or k in path.lower() for k in ['search', 'api', 'download', 'telecharg', 'result', 'base', 'morts', 'fiche']):
            print(f"  {name}: {path}")
    
    # Also print all routes
    print("\n=== ALL ROUTES ===")
    for name, path in routes:
        print(f"  {name}: {path}")

# Also try the main JS file
resp2 = session.get("https://www.memoiredeshommes.defense.gouv.fr/jscript/dist/js-front/es/main.js?cb8107", timeout=30)
print(f"\nMain JS: Status={resp2.status_code}, Length={len(resp2.text)}")
if resp2.status_code == 200:
    # Find API endpoints
    api_patterns = re.findall(r'(?:fetch|ajax|url|endpoint)\s*[:(=]\s*["\']([^"\']+)["\']', resp2.text)
    print(f"API patterns: {api_patterns[:30]}")
