"""Test real insert of first 1000 event_links into evidence.link_quarantine."""
import sys
import sqlite3
from pathlib import Path
from backfill_link_quarantine import _map_event_link, _build_insert
from supabase_client import execute_sql, table_count_schema

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
conn = sqlite3.connect(str(BASE / "eventi_1gm.db"))
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM event_links LIMIT 1000").fetchall()
conn.close()

batch = [_map_event_link(dict(r)) for r in rows]
sql = _build_insert(batch)

print(f"Inserting {len(batch)} test rows...")
count_before = table_count_schema("evidence", "link_quarantine")
print(f"Count before: {count_before}")

r = execute_sql(sql, timeout=60)
print("Result:", r)

count_after = table_count_schema("evidence", "link_quarantine")
print(f"Count after: {count_after}")

if count_after - count_before != len(batch):
    print("WARNING: count mismatch")
    sys.exit(1)

print("Test insert OK")
