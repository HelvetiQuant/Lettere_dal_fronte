"""Check pgcrypto extension and fix digest functions."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Check installed extensions
r = execute_sql("SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'")
print("Installed pgcrypto:", r)

r = execute_sql("SELECT extname FROM pg_available_extensions WHERE extname = 'pgcrypto'")
print("Available pgcrypto:", r)

# Try creating extension
r = execute_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
print("CREATE EXTENSION pgcrypto:", r)

# Test digest explicitly
r = execute_sql("SELECT encode(digest('test'::bytea, 'sha256'::text), 'hex') AS h")
print("digest test:", r)

sys.exit(0)
