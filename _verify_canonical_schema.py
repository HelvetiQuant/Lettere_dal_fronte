"""Verify canonical schemas/tables/indexes on Supabase."""
import sys
import httpx
from supabase_client import SUPABASE_URL, _rest_headers, execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXPECTED = {
    "archive": ["repositories", "collections", "external_items", "external_item_revisions",
                "representations", "document_units", "text_versions", "passages", "chunks"],
    "evidence": ["link_quarantine", "rights_assessments"],
    "ops": ["discovery_queries", "discovery_candidates", "job_queue", "fetch_cache"],
    "ai": ["datasets", "dataset_versions", "dataset_items", "dataset_item_sources", "evaluation_runs"],
}

print("Checking schemas/tables via PostgREST...")
all_ok = True
for schema, tables in EXPECTED.items():
    for t in tables:
        url = f"{SUPABASE_URL}/rest/v1/{schema}.{t}?select=count&limit=0"
        r = httpx.head(url, headers={**_rest_headers(), "Prefer": "count=exact"}, timeout=10)
        status = "OK" if r.status_code == 200 else f"FAIL {r.status_code}"
        print(f"  {schema}.{t:35s} {status}")
        if r.status_code != 200:
            all_ok = False

print("\nChecking helper functions via exec_sql...")
for fn in ["archive.generate_stable_id", "archive.content_hash", "archive.set_updated_at"]:
    r = execute_sql(f"SELECT {fn}('test','x')")
    print(f"  {fn:40s} {r.get('data')}")

print("\n" + ("Canonical schema verified." if all_ok else "Some tables missing."))
sys.exit(0 if all_ok else 1)
