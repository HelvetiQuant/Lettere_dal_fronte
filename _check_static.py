import requests
base = "http://127.0.0.1:8000"
checks = [
    ("/", "text/html"),
    ("/support.js", "javascript"),
    ("/voci-data.js", "javascript"),
    ("/static/support.js", "javascript"),
]
for path, ctype in checks:
    try:
        r = requests.get(base + path, timeout=5)
        ct = r.headers.get("content-type", "")
        ok = "OK" if ctype in ct else "WARN"
        print(f"[{r.status_code}] {path} => {ct[:45]} {ok} ({len(r.content)} B)")
    except Exception as e:
        print(f"[ERR] {path}: {str(e)[:60]}")
