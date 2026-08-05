"""Inspect internati schema and sample records."""
import sqlite3, json

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row

print("=== internati schema ===")
for c in conn.execute("PRAGMA table_info(internati)").fetchall():
    print(f"  {c['name']:30s} {c['type']:15s} notnull={c['notnull']} default={c['dflt_value']}")

print("\n=== sample records (IDs 2344, 2357, 2360, 2353, 2350, 2356) ===")
for rid in [2344, 2357, 2360, 2353, 2350, 2356]:
    r = conn.execute("SELECT * FROM internati WHERE id=?", (rid,)).fetchone()
    if r:
        d = dict(r)
        print(f"\n--- id={rid} ---")
        for k, v in d.items():
            if v is not None and v != "":
                print(f"  {k}: {v}")

print("\n=== fonti_indice schema ===")
for c in conn.execute("PRAGMA table_info(fonti_indice)").fetchall():
    print(f"  {c['name']:30s} {c['type']:15s}")

print("\n=== person_source_matches exists? ===")
try:
    conn.execute("SELECT COUNT(*) FROM person_source_matches").fetchone()
    print("  YES")
except:
    print("  NO - needs migration")

conn.close()
