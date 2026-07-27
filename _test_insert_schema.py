"""Test writing to canonical schema via supabase_client."""
import os, sys
from dotenv import load_dotenv
load_dotenv()

from supabase_client import insert_batch_schema, table_count_schema

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

test_rows = [
    {
        "name": "Test Repository Backfill",
        "authority_score": 0.5,
        "country_code": "IT",
        "stable_id": "sha256:0000000000000000000000000000000000000000000000000000000000000001",
        "provider_code": "test",
        "api_base_url": "https://example.org",
        "rights_contact": "test@example.org",
    }
]

print("Inserting test row into archive.repositories...")
r = insert_batch_schema("archive", "repositories", test_rows, on_conflict="ignore")
print("Result:", r)

count = table_count_schema("archive", "repositories")
print("archive.repositories count:", count)
