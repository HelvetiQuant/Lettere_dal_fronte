"""Endpoint health check — returns non-zero exit code on failure.

Checks HTTP status AND response schema for each endpoint.
Does not print secrets, keys, or .env contents.
"""
import sys
import requests

base = "http://127.0.0.1:8000"
checks = [
    ("/api/conv-search?q=BIANCHI", {"soldiers": list}),
    ("/api/acs/registri", {"registri": (list, dict)}),
    ("/api/internati/5168/fonti", None),
    ("/api/internati/5168/opengraph", None),
    ("/api/source/stats", None),
    ("/api/research/gaps?status=open&limit=2", None),
    ("/api/memory/stats", None),
    ("/api/credits", None),
    ("/api/events", None),
    ("/api/status", None),
    ("/api/fondi", None),
    ("/api/decorati", None),
    ("/api/albooro", None),
    ("/api/cwgc", None),
    ("/api/nastroazzurro", None),
    ("/api/ministero", None),
    ("/api/sardi", None),
    ("/api/bologna", None),
    ("/api/nara", None),
    ("/api/nara_catalog", None),
    ("/api/francia_ww1", None),
    ("/api/entita/search?q=BIANCHI", None),
    ("/api/system/capabilities", {"providers": dict, "research_mode": str}),
]

failures = 0
for item in checks:
    path = item[0] if isinstance(item, tuple) else item
    expected_schema = item[1] if isinstance(item, tuple) else None
    try:
        r = requests.get(base + path, timeout=4)
        d = r.json() if r.status_code == 200 else {}
        extra = ""
        if "soldiers" in d:   extra = f" => {len(d['soldiers'])} soldiers"
        elif "count" in d:    extra = f" => count={d['count']}"
        elif "registri" in d: extra = f" => {d.get('count')} registri"
        elif "total" in d:    extra = f" => total={d['total']}"
        elif "providers" in d: extra = f" => providers={list(d.get('providers', {}).keys())}"
        elif "research_mode" in d: extra = f" => mode={d['research_mode']}"

        # Schema assertion
        schema_ok = True
        if expected_schema and r.status_code == 200:
            for key, expected_type in expected_schema.items():
                if key not in d:
                    extra += f" [FAIL: missing '{key}']"
                    schema_ok = False
                    failures += 1
                elif expected_type and not isinstance(d[key], expected_type):
                    extra += f" [FAIL: '{key}' wrong type]"
                    schema_ok = False
                    failures += 1

        if r.status_code != 200:
            failures += 1
        print(f"[{r.status_code}] {path}{extra}")
    except Exception as e:
        print(f"[ERR] {path}: {str(e)[:70]}")
        failures += 1

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
else:
    print("\nAll checks passed.")
    sys.exit(0)
