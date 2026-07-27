"""Test qualified pgcrypto digest."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

queries = [
    "SELECT encode(extensions.digest('test'::bytea, 'sha256'::text), 'hex') AS h",
    "SELECT encode(digest('test'::bytea, 'sha256'::text), 'hex') AS h",
    "SELECT current_setting('search_path') AS sp",
]

for q in queries:
    print(f"Query: {q}")
    r = execute_sql(q)
    print(f"  -> {r}")
    print()

sys.exit(0)
