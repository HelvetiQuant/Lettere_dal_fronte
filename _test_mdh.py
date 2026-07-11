import requests
import re
import urllib3
urllib3.disable_warnings()

url = "https://www.memoiredeshommes.sga.defense.gouv.fr/fr/fr/article.php?laref=1380&titre=page-previsu&pr=1"
resp = requests.get(url, verify=False, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
print(f"Status: {resp.status_code}")
print(f"Length: {len(resp.text)}")
print("---FIRST 5000 CHARS---")
print(resp.text[:5000])
print("---LAST 2000 CHARS---")
print(resp.text[-2000:])
# Find all links to CSV files
csv_links = re.findall(r'href="([^"]*\.csv[^"]*)"', resp.text, re.IGNORECASE)
print(f"\n--- CSV LINKS ({len(csv_links)}) ---")
for link in csv_links[:10]:
    print(link)
if len(csv_links) > 10:
    print(f"... and {len(csv_links)-10} more")
# Also find any download links
dl_links = re.findall(r'href="([^"]*download[^"]*)"', resp.text, re.IGNORECASE)
print(f"\n--- DOWNLOAD LINKS ({len(dl_links)}) ---")
for link in dl_links[:10]:
    print(link)
