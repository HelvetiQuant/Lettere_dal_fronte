"""Scarica tutti i link /item/UUID dalla Teca Digitale ACS usando Playwright
(necessario: il portale è ASP.NET SPA che carica i dati via JS)."""
import re
import sys
from playwright.sync_api import sync_playwright

URL = (
    "https://tecadigitaleacs.cultura.gov.it/media/ricercadl"
    "?rictree=MINISTERO%20DELLA%20DIFESA/COMMISSARIATO%20GENERALE%20PER%20LE%20ONORANZE%20AI%20CADUTI%20(ONORCADUTI)/Internati%20militari%20italiani%20(IMI)"
    "&rictip=registro"
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    print(f"Carico {URL[:80]}...")
    page.goto(URL, wait_until="networkidle", timeout=60000)

    # Aspetta che i risultati siano caricati
    try:
        page.wait_for_selector("a[href*='/item/']", timeout=15000)
    except Exception:
        print("TIMEOUT — dump HTML:")
        print(page.content()[:3000])
        browser.close()
        sys.exit(1)

    seen = {}

    def harvest():
        for link in page.query_selector_all("a[href*='/item/']"):
            href = link.get_attribute("href") or ""
            text = (link.inner_text() or "").strip()
            m = re.search(r"/item/([0-9a-f-]{36})", href)
            if m and text and text not in seen:
                seen[text] = m.group(1)

    BASE_URL = (
        "https://tecadigitaleacs.cultura.gov.it/media/ricercadl"
        "?rictree=MINISTERO%20DELLA%20DIFESA/COMMISSARIATO%20GENERALE%20PER%20LE%20ONORANZE%20AI%20CADUTI%20(ONORCADUTI)/Internati%20militari%20italiani%20(IMI)"
        "&rictip=registro"
    )

    for page_num in range(1, 9):  # 8 pagine (12 item/pagina × 8 = 96 ≥ 85)
        url_page = f"{BASE_URL}&page={page_num}"
        page.goto(url_page, wait_until="networkidle", timeout=30000)
        try:
            page.wait_for_selector("a[href*='/item/']", timeout=8000)
        except Exception:
            print(f"  Pagina {page_num}: nessun item trovato — fine")
            break
        harvest()
        print(f"  Pagina {page_num}: {len(seen)} totali finora")

    browser.close()

print(f"\nTrovate {len(seen)} province/registri unici:")
print("\n_ACS_IMI_REGISTRI: Dict[str, str] = {")
for prov in sorted(seen.keys()):
    print(f'    "{prov}": "{seen[prov]}",')
print("}")
