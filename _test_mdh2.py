import requests
import re

url = "https://www.memoiredeshommes.defense.gouv.fr/conflits-operations/telechargement-des-bases"
resp = requests.get(url, timeout=30, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-FR,fr;q=0.9",
})
print(f"Status: {resp.status_code}")
print(f"Length: {len(resp.text)}")

# Find all href links containing .zip or .csv or download
all_links = re.findall(r'href="([^"]*)"', resp.text)
zip_links = [l for l in all_links if '.zip' in l.lower() or '.csv' in l.lower() or 'download' in l.lower() or 'telecharg' in l.lower()]
print(f"\n--- ZIP/CSV/DOWNLOAD LINKS ({len(zip_links)}) ---")
for link in zip_links:
    print(link)

# Also search for onclick or data attributes
data_attrs = re.findall(r'data-[a-z]+="([^"]*)"', resp.text)
print(f"\n--- DATA ATTRS ({len(data_attrs)}) ---")
for attr in data_attrs[:20]:
    print(attr)

# Search for any URL ending in .zip
zip_urls = re.findall(r'https?://[^\s"\'<>]+\.zip', resp.text)
print(f"\n--- ZIP URLs ({len(zip_urls)}) ---")
for u in zip_urls:
    print(u)

# Print a section around "Morts pour la France" or "Premiere Guerre"
idx = resp.text.lower().find("morts pour la france")
if idx > 0:
    print(f"\n--- Context around 'Morts pour la France' (pos {idx}) ---")
    print(resp.text[max(0,idx-200):idx+1000])
else:
    print("\n'Morts pour la France' not found in page text")
    # Print middle section
    mid = len(resp.text) // 2
    print(f"\n--- Middle section ---")
    print(resp.text[mid:mid+2000])
