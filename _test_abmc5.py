"""Test ABMC con URL completo trovato nella web search + varianti Drupal Views"""
import requests
import json
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "X-Requested-With": "XMLHttpRequest",
})

# Test con l'URL esatto trovato nel search result (ha field_cemetery=93791)
# Proviamo senza cemetery per avere tutti
print("=== Test 1: database-search-results params base ===")
params = {
    "field_first_name": "",
    "field_last_name": "",
    "service_number": "",
    "field_place_of_entry": "All",
    "field_branch_of_service": "All",
    "search_api_fulltext": "",
    "field_dod_day": "All",
    "field_dod_month": "All",
    "field_dod_year": "",
    "field_missing_status": "All",
    "field_medal_of_honor_recipient": "0",
    "field_abmc_burial_unit": "",
    "items_per_page": "25",
    "sort_bef_combine": "field_last_name_ASC",
    "sort_by": "field_last_name",
    "sort_order": "ASC",
    "page": "0",
}
r = session.get("https://www.abmc.gov/database-search-results", params=params, timeout=20)
print(f"Status: {r.status_code}, CT: {r.headers.get('Content-Type','')[:40]}")

soup = BeautifulSoup(r.text, "html.parser")
rows = soup.find_all("tr")
print(f"Righe tabella: {len(rows)}")
# Cerca qualsiasi testo utile
text = soup.get_text(" ", strip=True)[:1000]
print(f"Testo pagina: {text[:500]}")

# Test Views AJAX endpoint (Drupal standard)
print("\n=== Test 2: Views AJAX ===")
ajax_params = {**params, "_drupal_ajax": "1"}
r2 = session.post("https://www.abmc.gov/views/ajax", data={
    "view_name": "decedent_search",
    "view_display_id": "page_1",
    "view_args": "",
    "view_path": "/database-search-results",
    "view_dom_id": "1",
    "pager_element": "0",
    "page": "0",
    "_drupal_ajax": "1",
}, timeout=20)
print(f"Status: {r2.status_code}, CT: {r2.headers.get('Content-Type','')[:40]}")
print(r2.text[:300])

# Test Solr/Search API endpoint
print("\n=== Test 3: Solr search endpoint ===")
solr_urls = [
    "https://www.abmc.gov/search/site?keys=&_format=json",
    "https://www.abmc.gov/api/node/decedent?_format=json&page=0",
    "https://www.abmc.gov/api/node/decedent?_format=json",
]
for url in solr_urls:
    r3 = session.get(url, timeout=15)
    print(f"  {url[:60]} -> {r3.status_code} {r3.headers.get('Content-Type','')[:30]}")
    if r3.status_code == 200 and "json" in r3.headers.get("Content-Type", ""):
        d = r3.json()
        print(f"    Records: {len(d) if isinstance(d, list) else 'dict'}")
        print(f"    {str(d)[:200]}")
