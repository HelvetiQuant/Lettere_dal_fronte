"""Verify canonical schemas/tables/indexes on Supabase."""
import sys
from supabase_client import (
    table_exists_schema, table_count_schema, execute_sql
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXPECTED = {
    "archive": ["repositories", "collections", "external_items", "external_item_revisions",
                "representations", "document_units", "text_versions", "passages", "chunks"],
    "evidence": ["link_quarantine", "rights_assessments"],
    "ops": ["discovery_queries", "discovery_candidates", "job_queue", "fetch_cache"],
    "ai": ["datasets", "dataset_versions", "dataset_items", "dataset_item_sources", "evaluation_runs"],
}

print("Checking schemas/tables via PostgREST (Accept-Profile)...")
all_ok = True
for schema, tables in EXPECTED.items():
    for t in tables:
        exists = table_exists_schema(schema, t)
        status = "OK" if exists else "FAIL 404"
        count = table_count_schema(schema, t) if exists else -1
        print(f"  {schema}.{t:35s} {status:8s} rows={count}")
        if not exists:
            all_ok = False

print("\nChecking helper functions via exec_sql...")
for fn, args in [
    ("archive.generate_stable_id", "'provider','ext-123'"),
    ("archive.content_hash", "'test text'"),
]:
    r = execute_sql(f"SELECT {fn}({args})")
    data = r.get("data") or {}
    print(f"  {fn:40s} ok={r.get('ok')} data={data}")

print("\nChecking set_updated_at trigger function...")
r = execute_sql("SELECT proname FROM pg_proc WHERE proname = 'set_updated_at' AND pronamespace = 'archive'::regnamespace")
data = r.get("data") or {}
print(f"  archive.set_updated_at exists: {data}")

print("\n" + ("Canonical schema verified." if all_ok else "Some tables missing."))
sys.exit(0 if all_ok else 1)
