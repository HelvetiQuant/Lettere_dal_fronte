import sqlite3, json

conn = sqlite3.connect('imi_internati.db')
conn.row_factory = sqlite3.Row

print("=== INTERNATI ===")
rows = conn.execute("SELECT id, cognome, nome, grado, luogo_nascita, data_nascita, luogo_internamento, sorte FROM internati WHERE cognome LIKE '%GAIASCHI%' OR nome LIKE '%GAIASCHI%' ORDER BY id").fetchall()
for r in rows:
    print(dict(r))
print(f"Total: {len(rows)}")

print("\n=== CADUTI ALBO ORO ===")
rows2 = conn.execute("SELECT id, nominativo, grado, reparto, anno_morte, luogo_morte FROM caduti_albooro WHERE nominativo LIKE '%GAIASCHI%' ORDER BY id LIMIT 10").fetchall()
for r in rows2:
    print(dict(r))
print(f"Total: {len(rows2)}")

print("\n=== CADUTI MINISTERO ===")
rows3 = conn.execute("SELECT id, cognome, nome, grado, reparto FROM caduti_ministero WHERE cognome LIKE '%GAIASCHI%' ORDER BY id LIMIT 10").fetchall()
for r in rows3:
    print(dict(r))
print(f"Total: {len(rows3)}")

print("\n=== DECORATI ===")
rows4 = conn.execute("SELECT id, cognome, nome, tipo_decorazione, anno_decorazione FROM decorati_nastroazzurro WHERE cognome LIKE '%GAIASCHI%' ORDER BY id LIMIT 10").fetchall()
for r in rows4:
    print(dict(r))
print(f"Total: {len(rows4)}")

print("\n=== LEBI ===")
rows5 = conn.execute("SELECT id, cognome, nome FROM lebi_records WHERE cognome LIKE '%GAIASCHI%' ORDER BY id LIMIT 10").fetchall()
for r in rows5:
    print(dict(r))
print(f"Total: {len(rows5)}")

conn.close()
