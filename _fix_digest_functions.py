"""Fix canonical helper functions to use qualified extensions.digest."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION archive.generate_stable_id(p_provider TEXT, p_external_id TEXT)
RETURNS TEXT LANGUAGE plpgsql SET search_path = archive, extensions, pg_catalog AS $$
DECLARE raw TEXT;
BEGIN
    IF p_provider IS NOT NULL THEN
        raw := lower(trim(p_provider)) || ':' || lower(trim(p_external_id));
    ELSE
        raw := 'id:' || lower(trim(p_external_id));
    END IF;
    RETURN 'sha256:' || encode(extensions.digest(raw::bytea, 'sha256'::text), 'hex');
END;
$$""",
    """CREATE OR REPLACE FUNCTION archive.content_hash(p_text TEXT)
RETURNS TEXT LANGUAGE plpgsql SET search_path = archive, extensions, pg_catalog AS $$
BEGIN
    RETURN 'sha256:' || encode(extensions.digest(p_text::bytea, 'sha256'::text), 'hex');
END;
$$""",
    """CREATE OR REPLACE FUNCTION archive.content_hash(p_text TEXT, p_salt TEXT)
RETURNS TEXT LANGUAGE plpgsql SET search_path = archive, extensions, pg_catalog AS $$
BEGIN
    RETURN 'sha256:' || encode(extensions.digest((p_text || coalesce(p_salt, ''))::bytea, 'sha256'::text), 'hex');
END;
$$""",
]

ok = fail = 0
for sql in FUNCTIONS:
    first = sql.split("\n")[0][:70]
    print(f"{first}...")
    r = execute_sql(sql, timeout=60)
    data = r.get("data") or {}
    if r.get("ok") and data.get("ok") is not False:
        print("  OK")
        ok += 1
    else:
        print(f"  FAIL: {data.get('error', r.get('error', ''))[:120]}")
        fail += 1

# Test
r = execute_sql("SELECT archive.generate_stable_id('provider','ext-123') AS sid, archive.content_hash('hello') AS ch")
print("\nTest functions:", r)

print(f"\nFunctions: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
