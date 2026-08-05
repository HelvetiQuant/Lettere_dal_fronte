import os, sys
sys.path.insert(0, '.')

# 1. Check if eventi_1gm is accessible via get_conn()
from database import get_conn
conn = get_conn()
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
event_tables = [t for t in tables if 'event' in t.lower()]
print(f"Tables in get_conn() DB with 'event': {event_tables}")
all_tables = sorted(tables)
print(f"All tables ({len(all_tables)}): {all_tables[:20]}...")
conn.close()

# 2. Check if Tavily is available
from web_search_providers import available_providers
print(f"\nWeb search providers available: {available_providers()}")

# 3. Check TAVILY_API_KEY
from extractor import _load_env
env = _load_env()
tavily_key = env.get('TAVILY_API_KEY', '')
print(f"TAVILY_API_KEY set: {bool(tavily_key)} (len={len(tavily_key)})")

# 4. Check AI providers
from ai_client import is_any_provider_available
print(f"AI providers available: {is_any_provider_available()}")

# 5. Check what database.py get_conn returns
import database
db_path = getattr(database, '_DB_PATH', 'not set')
print(f"\ndatabase._DB_PATH: {db_path}")
print(f"database.get_conn source: {database.get_conn.__code__.co_filename}")
