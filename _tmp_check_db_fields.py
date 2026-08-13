"""Check DB record vs extracted claims for military fields."""
import sqlite3, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

# Check BURBA LUIGI in caduti_ministero
print("=== caduti_ministero: BURBA LUIGI ===")
rows = db.execute("SELECT * FROM caduti_ministero WHERE cognome='BURBA' AND nome LIKE 'LUIGI%' LIMIT 3").fetchall()
for r in rows:
    print(f"  id={r['id']}")
    for k in r.keys():
        if r[k]:
            print(f"    {k} = {r[k]}")

# Check MAVONE in internati
print("\n=== internati: MAVONE LUIGI ===")
rows = db.execute("SELECT * FROM internati WHERE cognome='MAVONE' AND nome LIKE 'LUIGI%' LIMIT 3").fetchall()
for r in rows:
    print(f"  id={r['id']}")
    for k in r.keys():
        if r[k]:
            print(f"    {k} = {r[k]}")

# Check what fields caduti_ministero has
print("\n=== caduti_ministero columns ===")
cols = db.execute("PRAGMA table_info(caduti_ministero)").fetchall()
for c in cols:
    print(f"  {c['name']} ({c['type']})")

# Check what fields internati has
print("\n=== internati columns ===")
cols = db.execute("PRAGMA table_info(internati)").fetchall()
for c in cols:
    print(f"  {c['name']} ({c['type']})")

db.close()
