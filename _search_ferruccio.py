"""Search for FERRUCCIO in internati."""
import sqlite3
conn = sqlite3.connect("imi_internati.db")
c = conn.cursor()
c.execute("SELECT id, cognome, nome FROM internati WHERE nome LIKE '%FERRUCCIO%' LIMIT 10")
rows = c.fetchall()
print(f"FERRUCCIO in internati: {len(rows)}")
for r in rows:
    print(r)
conn.close()
