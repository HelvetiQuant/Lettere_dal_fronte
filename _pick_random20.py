"""Pick 20 random persons from various DB tables."""
import sqlite3
import random

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row

persons = []

# internati (8)
rows = conn.execute(
    "SELECT cognome, nome FROM internati "
    "WHERE cognome IS NOT NULL AND cognome != '' "
    "AND nome IS NOT NULL AND nome != '' "
    "ORDER BY RANDOM() LIMIT 8"
).fetchall()
for r in rows:
    persons.append(f"{r['cognome']} {r['nome']}")

# caduti_albooro (4) — has nominativo
try:
    rows = conn.execute(
        "SELECT nominativo FROM caduti_albooro "
        "WHERE nominativo IS NOT NULL AND nominativo != '' "
        "ORDER BY RANDOM() LIMIT 4"
    ).fetchall()
    for r in rows:
        persons.append(r["nominativo"])
except Exception:
    pass

# decorati_nastroazzurro (4)
try:
    rows = conn.execute(
        "SELECT cognome, nome FROM decorati_nastroazzurro "
        "WHERE cognome IS NOT NULL AND cognome != '' "
        "AND nome IS NOT NULL AND nome != '' "
        "ORDER BY RANDOM() LIMIT 4"
    ).fetchall()
    for r in rows:
        persons.append(f"{r['cognome']} {r['nome']}")
except Exception:
    pass

# caduti_cwgc (2)
try:
    rows = conn.execute(
        "SELECT cognome, nome FROM caduti_cwgc "
        "WHERE cognome IS NOT NULL AND cognome != '' "
        "AND nome IS NOT NULL AND nome != '' "
        "ORDER BY RANDOM() LIMIT 2"
    ).fetchall()
    for r in rows:
        persons.append(f"{r['cognome']} {r['nome']}")
except Exception:
    pass

# caduti_ministero (2)
try:
    rows = conn.execute(
        "SELECT cognome, nome FROM caduti_ministero "
        "WHERE cognome IS NOT NULL AND cognome != '' "
        "AND nome IS NOT NULL AND nome != '' "
        "ORDER BY RANDOM() LIMIT 2"
    ).fetchall()
    for r in rows:
        persons.append(f"{r['cognome']} {r['nome']}")
except Exception:
    pass

# If we don't have 20 yet, top up from internati
if len(persons) < 20:
    remaining = 20 - len(persons)
    rows = conn.execute(
        "SELECT cognome, nome FROM internati "
        "WHERE cognome IS NOT NULL AND cognome != '' "
        "AND nome IS NOT NULL AND nome != '' "
        "ORDER BY RANDOM() LIMIT ?",
        (remaining,)
    ).fetchall()
    for r in rows:
        persons.append(f"{r['cognome']} {r['nome']}")

conn.close()

# Shuffle and take 20
random.shuffle(persons)
persons = persons[:20]

for i, p in enumerate(persons, 1):
    print(f"{i:2d}. {p}")
