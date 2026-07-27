"""Test inserting via exec_sql to bypass PostgREST schema switching."""
import sys
from supabase_client import execute_sql, table_count_schema

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sql = """
INSERT INTO archive.repositories (name, authority_score, country, stable_id, website_url, contact_email)
VALUES ('Test Repo ExecSQL', 0.5, 'IT', 'sha256:0000000000000000000000000000000000000000000000000000000000000002', 'https://example.org', 'test@example.org')
ON CONFLICT (stable_id) DO NOTHING
"""

print("Inserting via exec_sql...")
r = execute_sql(sql, timeout=60)
print("Result:", r)

print("archive.repositories count:", table_count_schema("archive", "repositories"))
