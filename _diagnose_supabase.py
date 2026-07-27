"""Diagnose Supabase schema exposure and extensions."""
import os, sys, json
from dotenv import load_dotenv
load_dotenv()
import httpx

URL = os.environ.get("SUPABASE_URL", "")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", os.environ.get("SUPABASE_ANON_KEY", ""))

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Accept": "application/vnd.pgrst.object+json",
}

print(f"URL: {URL[:40]}...")
print(f"KEY len: {len(KEY)}")
print()

# 1. Check pgcrypto extension
r = httpx.post(
    f"{URL}/rest/v1/rpc/exec_sql",
    headers=headers,
    json={"query": "SELECT name FROM pg_available_extensions WHERE name = 'pgcrypto' UNION ALL SELECT name FROM pg_extension WHERE name = 'pgcrypto'"},
    timeout=15
)
print("pgcrypto availability:", r.status_code, r.text[:300])

# 2. Try schema switching via Accept-Profile
h2 = dict(headers)
h2["Accept-Profile"] = "archive"
r2 = httpx.head(
    f"{URL}/rest/v1/repositories?select=count",
    headers=h2,
    timeout=15
)
print("Accept-Profile archive.repositories:", r2.status_code, r2.text[:300])

# 3. Try with schema in path and accept-profile
h3 = dict(headers)
h3["Accept-Profile"] = "evidence"
r3 = httpx.head(
    f"{URL}/rest/v1/link_quarantine?select=count",
    headers=h3,
    timeout=15
)
print("Accept-Profile evidence.link_quarantine:", r3.status_code, r3.text[:300])

# 4. List schemas created
r4 = httpx.post(
    f"{URL}/rest/v1/rpc/exec_sql",
    headers=headers,
    json={"query": "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('archive','evidence','ops','ai','api_public','legacy')"},
    timeout=15
)
print("Schemas:", r4.status_code, r4.text[:500])
