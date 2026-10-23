import sqlite3, os

conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "imi_internati.db"))
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, matricola, grado,
           luogo_cattura, data_cattura, luogo_internamento, sorte, residenza
    FROM internati
    WHERE cognome IS NOT NULL AND cognome != '' AND LENGTH(cognome) > 2
    ORDER BY RANDOM() LIMIT 6
""").fetchall()
for i, r in enumerate(rows, 1):
    d = dict(r)
    print(f"NOME {i}/6: {d['cognome']} {d['nome']} (ID={d['id']})")
    print(f"  nato={d['data_nascita']} luogo={d['luogo_nascita']} matr={d['matricola']} grado={d['grado']}")
    print(f"  residenza={d['residenza']} cattura={d['data_cattura']} a={d['luogo_cattura']}")
    print(f"  internamento={d['luogo_internamento']} sorte={d['sorte']}")
    print()
conn.close()
