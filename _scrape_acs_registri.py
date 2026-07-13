"""Scarica tutti gli UUID dei registri IMI dalla Teca Digitale ACS
cercando pattern UUID nell'HTML/JSON inline (SPA Vue.js)."""
import re
import json
import requests

URL = (
    "https://tecadigitaleacs.cultura.gov.it/media/ricercadl"
    "?rictree=MINISTERO%20DELLA%20DIFESA/COMMISSARIATO%20GENERALE%20PER%20LE%20ONORANZE%20AI%20CADUTI%20(ONORCADUTI)/Internati%20militari%20italiani%20(IMI)"
    "&rictip=registro"
)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml",
}

r = requests.get(URL, headers=headers, timeout=30)
print(f"HTTP {r.status_code} — {len(r.text)} char")

html = r.text

# 1. Cerca pattern uuid nelle stringhe JSON inline (Vue SPA inietta i dati nel HTML)
uuid_pattern = re.compile(r'["\']([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})["\']')
uuids_all = uuid_pattern.findall(html)
print(f"UUID trovati nell'HTML: {len(uuids_all)}")

# 2. Cerca blocchi JSON con campo "title" o "label" vicini agli UUID
# Pattern: {"id":"uuid","title":"Provincia"} o simili
obj_pattern = re.compile(
    r'\{[^{}]*?"(?:id|uuid|iid)"\s*:\s*"([0-9a-f-]{36})"[^{}]*?"(?:title|label|name|descrizione)"\s*:\s*"([^"]+)"[^{}]*?\}',
    re.DOTALL
)
obj_matches = obj_pattern.findall(html)
print(f"Oggetti id+title trovati: {len(obj_matches)}")
for uuid, title in obj_matches[:20]:
    print(f"  {title}: {uuid}")

# 3. Prova anche con ordine invertito (title prima di id)
obj_pattern2 = re.compile(
    r'\{[^{}]*?"(?:title|label|name)"\s*:\s*"([^"]+)"[^{}]*?"(?:id|uuid)"\s*:\s*"([0-9a-f-]{36})"[^{}]*?\}',
    re.DOTALL
)
obj_matches2 = obj_pattern2.findall(html)
print(f"Oggetti title+id trovati: {len(obj_matches2)}")
for title, uuid in obj_matches2[:20]:
    print(f"  {title}: {uuid}")

# 4. Dump dei primi 3000 char del body per analisi
print("\n--- SNIPPET HTML (inizio body) ---")
idx = html.find("<body")
print(html[idx:idx+2000] if idx > 0 else html[:2000])

