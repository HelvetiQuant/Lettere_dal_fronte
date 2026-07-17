import sqlite3
conn = sqlite3.connect("imi_internati.db")
print(f"record_links: {conn.execute('SELECT COUNT(*) FROM record_links').fetchone()[0]}")
print("\nPer link_type:")
for r in conn.execute("SELECT link_type, COUNT(*) as n FROM record_links GROUP BY link_type ORDER BY n DESC").fetchall():
    print(f"  {r[0]:30s} {r[1]:>8}")
print("\nPer from_table -> to_table:")
for r in conn.execute("SELECT from_table, to_table, COUNT(*) as n FROM record_links GROUP BY from_table, to_table ORDER BY n DESC LIMIT 15").fetchall():
    print(f"  {r[0]:20s} -> {r[1]:20s} {r[2]:>8}")
conn.close()
