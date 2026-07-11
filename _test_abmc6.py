"""Test api.abmc.gov con URL esatto dalla web search"""
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.abmc.gov/",
    "Origin": "https://www.abmc.gov",
})

# URL esatto da web search risultato
base_url = "http://api.abmc.gov/database-search-results"

print("=== Test 1: URL esatto da web search (cemetery 93791) ===")
params = {
    "field_cemetery": "93791",
    "field_cemetery2": "93791",
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
    "items_per_page": "10",
    "sort_bef_combine": "field_last_name_ASC",
    "sort_by": "field_last_name",
    "sort_order": "ASC",
    "page": "0",
}
try:
    r = session.get(base_url, params=params, timeout=15, allow_redirects=True)
    print(f"Status: {r.status_code}")
    print(f"URL finale: {r.url}")
    print(f"CT: {r.headers.get('Content-Type','')}")
    print(f"Content[:500]: {r.text[:500]}")
except Exception as e:
    print(f"Errore: {e}")

print("\n=== Test 2: senza cemetery ===")
params2 = {k: v for k, v in params.items() if "cemetery" not in k}
try:
    r2 = session.get(base_url, params=params2, timeout=15)
    print(f"Status: {r2.status_code}")
    print(f"CT: {r2.headers.get('Content-Type','')}")
    print(f"Content[:500]: {r2.text[:500]}")
except Exception as e:
    print(f"Errore: {e}")

print("\n=== Test 3: HTTPS api.abmc.gov con Accept JSON ===")
session.headers["Accept"] = "application/json"
try:
    r3 = session.get("https://api.abmc.gov/database-search-results", params=params2, timeout=15)
    print(f"Status: {r3.status_code}")
    print(f"CT: {r3.headers.get('Content-Type','')}")
    print(f"Content[:500]: {r3.text[:500]}")
except Exception as e:
    print(f"Errore: {e}")
