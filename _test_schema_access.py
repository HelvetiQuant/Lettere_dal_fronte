"""Test schema-aware access via supabase-py."""
import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(url, key)

try:
    r = client.schema("archive").table("repositories").select("*").limit(1).execute()
    print("archive.repositories accessible:", r.data)
except Exception as e:
    print("archive.repositories error:", type(e).__name__, str(e)[:200])

try:
    r = client.schema("public").table("eventi_1gm").select("count").limit(1).execute()
    print("public.eventi_1gm accessible:", r.data)
except Exception as e:
    print("public.eventi_1gm error:", type(e).__name__, str(e)[:200])
