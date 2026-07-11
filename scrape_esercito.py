"""Scraper per l'archivio documentale dell'Ufficio Storico dello Stato Maggiore
dell'Esercito Italiano. Individua e scarica i PDF collegati alla pagina."""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE_URL = "https://www.esercito.difesa.it/storia/ufficio-storico-sme/archivio-documentale/93917.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_html(url: str) -> str:
    s = requests.Session()
    try:
        r = s.get(url, headers=HEADERS, timeout=60)
    except requests.exceptions.SSLError:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = s.get(url, headers=HEADERS, timeout=60, verify=False)
    r.raise_for_status()
    return r.text


def find_links(html: str, base: str):
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    pdfs, pages = [], []
    for h in hrefs:
        absu = urljoin(base, h)
        if absu.lower().endswith(".pdf"):
            pdfs.append(absu)
        elif re.search(r"\.(html?|aspx)(\?|$)", absu, re.IGNORECASE):
            pages.append(absu)
    return sorted(set(pdfs)), sorted(set(pages))


if __name__ == "__main__":
    html = fetch_html(BASE_URL)
    print("HTML length:", len(html))
    pdfs, pages = find_links(html, BASE_URL)
    print(f"\n=== {len(pdfs)} PDF trovati ===")
    for p in pdfs:
        print(p)
    # Show internal pages that may contain more PDFs
    internal = [p for p in pages if "esercito.difesa.it" in p and "93917" not in p]
    print(f"\n=== {len(internal)} pagine interne collegate ===")
    for p in internal[:40]:
        print(p)
