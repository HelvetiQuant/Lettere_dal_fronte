"""Check canonical tables existence via SQL."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# We cannot get SELECT results from exec_sql, so create a small table-count function
r = execute_sql("""
CREATE OR REPLACE FUNCTION _check_canonical_tables()
RETURNS TABLE(schema_name text, table_name text, row_count bigint) AS $$
BEGIN
    RETURN QUERY
    SELECT n.nspname::text, c.relname::text, 0::bigint
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r'
      AND n.nspname IN ('archive','evidence','ops','ai','api_public','legacy')
    ORDER BY n.nspname, c.relname;
END;
$$ LANGUAGE plpgsql
""")
print("Create check function:", r)

# Call via PostgREST RPC
import httpx
from supabase_client import SUPABASE_URL, _rest_headers
url = f"{SUPABASE_URL}/rest/v1/rpc/_check_canonical_tables"
r = httpx.post(url, headers=_rest_headers(), json={}, timeout=15)
print("RPC result:", r.status_code)
if r.status_code == 200:
    for row in r.json():
        print(f"  {row['schema_name']}.{row['table_name']}")
else:
    print(r.text[:300])

# Drop helper
execute_sql("DROP FUNCTION IF EXISTS _check_canonical_tables()")
