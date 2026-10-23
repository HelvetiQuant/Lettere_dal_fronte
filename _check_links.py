"""Check existing event_links for archivio_documenti."""
import sqlite3

conn = sqlite3.connect('eventi_1gm.db')
conn.row_factory = sqlite3.Row

# Check existing links to archivio_documenti
cursor = conn.execute(
    "SELECT * FROM event_links WHERE target_table='archivio_documenti' LIMIT 5"
)
rows = cursor.fetchall()
print(f"Existing archivio_documenti links: {len(rows)}")
for r in rows:
    print(dict(r))

# Check how viewpoints_service_v2 queries event_links
# Check what target_id type is used
cursor = conn.execute(
    "SELECT DISTINCT target_table FROM event_links WHERE evento_id=16"
)
tables = [r[0] for r in cursor]
print(f"\nTarget tables for event 16: {tables}")

# Check the Austrian links
cursor = conn.execute(
    "SELECT * FROM event_links WHERE evento_id=16 AND target_table='archivio_documenti' LIMIT 5"
)
rows = cursor.fetchall()
print(f"\nEvent 16 archivio_documenti links: {len(rows)}")
for r in rows:
    print(dict(r))

conn.close()
