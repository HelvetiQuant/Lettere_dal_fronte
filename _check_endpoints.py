import requests
base = "http://127.0.0.1:8000"
checks = [
    "/api/conv-search?q=BIANCHI",
    "/api/acs/registri",
    "/api/internati/5168/fonti",
    "/api/internati/5168/opengraph",
    "/api/source/stats",
    "/api/research/gaps?status=open&limit=2",
    "/api/memory/stats",
    "/api/credits",
    "/api/events",
    "/api/status",
    "/api/fondi",
    "/api/decorati",
    "/api/albooro",
    "/api/cwgc",
    "/api/nastroazzurro",
    "/api/ministero",
    "/api/sardi",
    "/api/bologna",
    "/api/nara",
    "/api/nara_catalog",
    "/api/francia_ww1",
    "/api/entita/search?q=BIANCHI",
]
for path in checks:
    try:
        r = requests.get(base + path, timeout=4)
        d = r.json() if r.status_code == 200 else {}
        extra = ""
        if "soldiers" in d:   extra = f" => {len(d['soldiers'])} soldiers"
        elif "count" in d:    extra = f" => count={d['count']}"
        elif "registri" in d: extra = f" => {d.get('count')} registri"
        elif "total" in d:    extra = f" => total={d['total']}"
        elif "providers" in d: extra = f" => providers={d['providers']}"
        print(f"[{r.status_code}] {path}{extra}")
    except Exception as e:
        print(f"[ERR] {path}: {str(e)[:70]}")
