"""Check Supabase status via PostgREST API."""
import sys
import httpx
from supabase_client import SUPABASE_URL, _rest_headers, execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# List all tables from OpenAPI spec
r = httpx.get(f"{SUPABASE_URL}/rest/v1/", headers=_rest_headers(), timeout=30)
if r.status_code == 200:
    spec = r.json()
    if "definitions" in spec:
        tables = sorted(spec["definitions"].keys())
        print(f"Tables visible in PostgREST: {len(tables)}")
        for t in tables:
            try:
                cr = httpx.head(
                    f"{SUPABASE_URL}/rest/v1/{t}?select=count",
                    headers={**_rest_headers(), "Prefer": "count=exact"},
                    timeout=10
                )
                count = "?"
                if cr.status_code == 200:
                    cr_header = cr.headers.get("content-range", "")
                    if "/" in cr_header:
                        count = cr_header.split("/")[-1]
                print(f"  {t:45s} rows={count}")
            except Exception as e:
                print(f"  {t:45s} error={str(e)[:50]}")
    else:
        print("Keys in spec:", list(spec.keys())[:10])
else:
    print(f"Failed to get spec: {r.status_code}")

# Try to create a small test table to verify we can write
r3 = execute_sql("CREATE TABLE IF NOT EXISTS _migration_test (id serial primary key, test text)")
print("\nCreate test table:", r3)

# Clean up
r5 = execute_sql("DROP TABLE IF EXISTS _migration_test")
print("Cleanup:", r5)
