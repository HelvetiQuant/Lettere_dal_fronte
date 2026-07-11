"""Verifica dimensioni dei PDF dell'Ufficio Storico prima del download."""
import urllib3
import requests

from scrape_esercito import BASE_URL, HEADERS, fetch_html, find_links

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def head_size(url: str) -> int:
    try:
        r = requests.head(url, headers=HEADERS, timeout=30, verify=False, allow_redirects=True)
        return int(r.headers.get("Content-Length", 0))
    except Exception:
        return -1


if __name__ == "__main__":
    html = fetch_html(BASE_URL)
    pdfs, _ = find_links(html, BASE_URL)
    total = 0
    rows = []
    for u in pdfs:
        size = head_size(u)
        total += max(size, 0)
        name = u.rsplit("/", 1)[-1]
        rows.append((size, name))
    rows.sort(reverse=True)
    for size, name in rows:
        mb = size / (1024 * 1024) if size > 0 else 0
        print(f"{mb:8.2f} MB  {name}")
    print(f"\nTOTALE: {total/(1024*1024):.1f} MB su {len(pdfs)} file")
