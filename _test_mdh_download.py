"""Download e test dei file CSV Mémoire des Hommes da data.gouv.fr"""
import requests
import os

URLS = {
    "base_morts": "https://www.data.gouv.fr/api/1/datasets/r/7fb4e959-df14-4a28-b7fc-f7b6c9cae93b",
    "annotations": "https://www.data.gouv.fr/api/1/datasets/r/e9f5409a-589a-478c-99da-6aea9b12c70a",
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data_mdh")
os.makedirs(DATA_DIR, exist_ok=True)

for name, url in URLS.items():
    print(f"Checking {name}...")
    # HEAD request to check size and content type
    resp = requests.head(url, allow_redirects=True, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0"})
    print(f"  Status: {resp.status_code}")
    print(f"  Content-Type: {resp.headers.get('Content-Type')}")
    print(f"  Content-Length: {resp.headers.get('Content-Length')}")
    print(f"  Content-Disposition: {resp.headers.get('Content-Disposition')}")
    
    # Download first 5000 bytes to check format
    resp2 = requests.get(url, timeout=30, stream=True,
                        headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-4999"})
    print(f"  Partial Status: {resp2.status_code}")
    text = resp2.text
    print(f"  First 1000 chars:")
    print(text[:1000])
    print(f"  ---")
    print()
