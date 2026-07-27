"""Check archive.repositories column names."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

q = """SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'archive' AND table_name = 'repositories'
ORDER BY ordinal_position"""

r = execute_sql(q)
print(r)
