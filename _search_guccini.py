"""Search for GUCCINI in the IMI database."""
import sqlite3

conn = sqlite3.connect("imi_internati.db")
c = conn.cursor()

# List tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"Tables: {tables}")

# Search in internati
c.execute("SELECT * FROM internati WHERE nome LIKE '%GUCCINI%' OR cognome LIKE '%GUCCINI%' LIMIT 10")
rows = c.fetchall()
print(f"\ninternati matches: {len(rows)}")
for r in rows:
    print(r)

# Also check column names
c.execute("PRAGMA table_info(internati)")
cols = [r[1] for r in c.fetchall()]
print(f"\ninternati columns: {cols}")

conn.close()
