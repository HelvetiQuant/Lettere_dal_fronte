import requests
import re

# Try the new site's API - Arkothèque v8 uses Elasticsearch
# Look for API calls in the page JS
url = "https://www.memoiredeshommes.defense.gouv.fr/conflits-operations/telechargement-des-bases"
resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# Find all script sources
scripts = re.findall(r'src="([^"]*\.js[^"]*)"', resp.text)
print("=== SCRIPTS ===")
for s in scripts:
    print(s)

# Find any API-like URLs in the page
api_urls = re.findall(r'["\'](https?://[^"\']*api[^"\']*|https?://[^"\']*search[^"\']*|https?://[^"\']*elastic[^"\']*)["\']', resp.text, re.IGNORECASE)
print("\n=== API URLS ===")
for u in api_urls:
    print(u)

# Find any inline JS with fetch/ajax/xhr
fetch_calls = re.findall(r'(?:fetch|ajax|xhr|XMLHttpRequest|axios)\([^)]*\)', resp.text)
print(f"\n=== FETCH/AJAX CALLS ({len(fetch_calls)}) ===")
for f in fetch_calls[:10]:
    print(f)

# Find data-image or download links
img_links = re.findall(r'(https?://[^\s"\'<>]+/(?:image|download|telecharg)[^\s"\'<>]*)', resp.text)
print(f"\n=== IMAGE/DOWNLOAD LINKS ({len(img_links)}) ===")
for l in img_links[:20]:
    print(l)

# Find any base64 or JSON data blocks
json_blocks = re.findall(r'data-(?:resultats|items|download)-json="([^"]*)"', resp.text)
print(f"\n=== JSON DATA BLOCKS ({len(json_blocks)}) ===")
for j in json_blocks[:5]:
    print(j[:200])

# Print raw HTML around "telechargement" or "download" or "zip"
for keyword in ['zip', 'download', 'telecharg', 'csv', 'opendata']:
    idx = resp.text.lower().find(keyword)
    if idx > 0:
        print(f"\n=== '{keyword}' found at pos {idx} ===")
        print(resp.text[max(0,idx-100):idx+300])
