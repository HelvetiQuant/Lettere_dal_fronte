"""Pick 6 random persons from internati and 3 random events from eventi_1gm."""
import sqlite3

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row

persons = conn.execute(
    "SELECT id, cognome, nome FROM internati "
    "WHERE cognome IS NOT NULL AND cognome != '' "
    "AND nome IS NOT NULL AND nome != '' "
    "ORDER BY RANDOM() LIMIT 6"
).fetchall()

events = conn.execute(
    "SELECT nome FROM eventi_1gm ORDER BY RANDOM() LIMIT 3"
).fetchall()

print("=== PERSONS ===")
for r in persons:
    print(f"{r['cognome']} {r['nome']}")

print("=== EVENTS ===")
for r in events:
    print(r["nome"])

conn.close()
