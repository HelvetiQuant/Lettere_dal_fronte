"""Remove test rows from canonical archive."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

r = execute_sql("DELETE FROM archive.repositories WHERE name LIKE 'Test Repo%'")
print("Deleted test repositories:", r)

r = execute_sql("DELETE FROM archive.repositories WHERE stable_id LIKE 'sha256:0000000000000000000000000000%'")
print("Deleted zero-padded stable_id repositories:", r)
