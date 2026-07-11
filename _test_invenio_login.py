import requests
requests.packages.urllib3.disable_warnings()

s = requests.Session()
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ricerca-storica-IMI/1.0"}

# Step 1: get switch.xhtml
r1 = s.get("https://invenio.bundesarchiv.de/invenio/switch.xhtml", headers=headers, timeout=30, verify=False)
print("GET switch", r1.status_code, len(r1.text))

# Try to extract ViewState and submit the form
import re
vs = re.search(r'id="j_id1:javax\.faces\.ViewState:0" value="([^"]+)"', r1.text)
print("ViewState", vs.group(1) if vs else None)

if vs:
    data = {
        "j_idt4": "j_idt4",
        "j_idt4:j_idt5": "j_idt4:j_idt5",
        "javax.faces.ViewState": vs.group(1),
    }
    r2 = s.post("https://invenio.bundesarchiv.de/invenio/switch.xhtml", data=data, headers=headers, timeout=30, verify=False)
    print("POST switch", r2.status_code, r2.url, len(r2.text))

# Try known pages
for u in ["main.xhtml", "search.xhtml", "suche.xhtml", "login.xhtml"]:
    r = s.get(f"https://invenio.bundesarchiv.de/invenio/{u}", headers=headers, timeout=30, verify=False)
    print(u, r.status_code, r.url, len(r.text))
