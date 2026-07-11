import requests
import re
import json

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# Get full routing data
resp = session.get("https://www.memoiredeshommes.defense.gouv.fr/js/routing?callback=fos.Router.setData", timeout=30)
jsonp = resp.text
json_start = jsonp.find('{')
json_end = jsonp.rfind('}') + 1
data = json.loads(jsonp[json_start:json_end])
routes = data.get('routes', {})

# Print specific routes with full details
target_routes = ['rec_api_search', 'rec_api_search_simple', 'rec_api_search_html',
                 'arkotheque_fichier_download', 'arkotheque_fichier_download_path',
                 'arkotheque_fs_download', 'rec_fichier_download',
                 'admin_base_recherche_search', 'rec_api_redirect_fiche_principale',
                 'rec_api_render_fiche']

for name in target_routes:
    if name in routes:
        print(f"\n=== {name} ===")
        print(json.dumps(routes[name], indent=2, ensure_ascii=False))

# Now try the search API
base_url = data.get('base_url', '')
print(f"\nBase URL: {base_url}")
print(f"Host: {data.get('host', '')}")
print(f"Scheme: {data.get('scheme', '')}")
