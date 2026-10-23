"""Check eventi_1gm schema and keywords."""
import sqlite3

conn = sqlite3.connect("eventi_1gm.db")
conn.row_factory = sqlite3.Row

cols = conn.execute("PRAGMA table_info(eventi_1gm)").fetchall()
print("=== COLUMNS ===")
for c in cols:
    print(f"  {c['name']:30s} {c['type']}")

print("\n=== EVENTS ===")
rows = conn.execute("SELECT * FROM eventi_1gm ORDER BY id").fetchall()
for r in rows:
    d = dict(r)
    print(f"id={d.get('id'):3d} | {d.get('nome',''):40s}")
    print(f"      keywords={d.get('keywords','')}")
    print(f"      aliases={d.get('aliases','')}")
    print()

conn.close()
