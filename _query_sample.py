"""Query internati sample for test case selection."""
import sqlite3
conn = sqlite3.connect("imi_internati.db")
cur = conn.cursor()
cur.execute("SELECT id, cognome, nome, luogo_nascita, data_nascita, luogo_cattura, luogo_internamento, sorte FROM internati WHERE cognome IS NOT NULL AND cognome != '' ORDER BY id LIMIT 20")
for r in cur.fetchall():
    print(r)
conn.close()
