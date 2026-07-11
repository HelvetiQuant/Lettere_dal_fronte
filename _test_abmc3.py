"""Analisi profonda della pagina ABMC database-search-results"""
import requests
from bs4 import BeautifulSoup
import re

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

r = session.get("https://www.abmc.gov/database-search-results", timeout=20)
soup = BeautifulSoup(r.text, "html.parser")

# 1. Cerca tutti gli script src
print("=== Script src ===")
for s in soup.find_all("script", src=True):
    src = s.get("src", "")
    print(f"  {src[:100]}")

# 2. Cerca drupalSettings o drupal.settings
print("\n=== drupalSettings ===")
for s in soup.find_all("script", src=False):
    txt = s.get_text()
    if "drupalSettings" in txt or "drupal" in txt.lower():
        # Estrai URL da settings
        urls = re.findall(r'"(https?://[^"]+)"', txt)
        for u in urls[:20]:
            print(f"  {u}")
        # Mostra snippet
        idx = txt.find("drupalSettings")
        if idx >= 0:
            print(f"\n  Snippet:\n{txt[idx:idx+500]}")
        break

# 3. Cerca il form di ricerca
print("\n=== Form ===")
for f in soup.find_all("form"):
    print(f"  action={f.get('action','')} method={f.get('method','')}")
    for inp in f.find_all("input")[:5]:
        print(f"    input name={inp.get('name','')} type={inp.get('type','')} value={inp.get('value','')[:30]}")

# 4. Conta risultati visibili
print("\n=== Contenuto visibile ===")
rows = soup.find_all("tr")
print(f"  Righe tabella: {len(rows)}")
divs_result = soup.find_all("div", class_=lambda c: c and ("result" in str(c) or "decedent" in str(c).lower()))
print(f"  Div result/decedent: {len(divs_result)}")

# 5. Cerca pager
pager = soup.find(class_=lambda c: c and "pager" in str(c).lower())
if pager:
    print(f"\n  Pager: {pager.get_text()[:200]}")

# 6. Cerca link JSON / endpoint nei commenti HTML
comments = soup.find_all(string=lambda t: isinstance(t, str) and ("json" in t.lower() or "api" in t.lower()))
for c in comments[:5]:
    print(f"\n  Comment/text: {c[:200]}")

# 7. Cerca path Drupal views
print("\n=== Views paths ===")
for m in re.finditer(r'(/views/ajax[^"\']+|/rest/[^"\']+|path["\']:\s*["\']([^"\']+))', r.text):
    print(f"  {m.group()[:100]}")
    if len(list(re.finditer(r'(/views/ajax[^"\']+|/rest/[^"\']+|path["\']:\s*["\']([^"\']+))', r.text))) > 10:
        break
