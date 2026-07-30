import sqlite3

# Search internati for Mauthausen
conn = sqlite3.connect('imi_internati.db')
rows = conn.execute(
    "SELECT id, cognome, nome, luogo_internamento, sorte, raw_text "
    "FROM internati "
    "WHERE luogo_internamento LIKE '%mauthausen%' "
    "OR luogo_internamento LIKE '%mathausen%' "
    "OR raw_text LIKE '%mauthausen%' "
    "OR raw_text LIKE '%mathausen%' LIMIT 20"
).fetchall()
print(f'Internati con Mauthausen/mathausen: {len(rows)}')
for r in rows:
    print(f'  id={r[0]} {r[1]} {r[2]} | luogo_internamento={r[3]} | sorte={r[4]}')
    if r[5]:
        print(f'    raw_text snippet: {r[5][:200]}')

# Also search for campi in Austria
rows2 = conn.execute(
    "SELECT DISTINCT luogo_internamento, COUNT(*) as n "
    "FROM internati "
    "WHERE luogo_internamento LIKE '%austria%' "
    "OR luogo_internamento LIKE '%ungheria%' "
    "OR luogo_internamento LIKE '%boemia%' "
    "OR luogo_internamento LIKE '%moravia%' "
    "GROUP BY luogo_internamento ORDER BY n DESC LIMIT 30"
).fetchall()
print(f'\nCampi in Austria-Ungheria (top 30):')
for r in rows2:
    print(f'  {r[0]:50s} {r[1]:>6}')

# Check for concentration camp references
rows3 = conn.execute(
    "SELECT DISTINCT luogo_internamento, COUNT(*) as n "
    "FROM internati "
    "WHERE luogo_internamento LIKE '%concentramento%' "
    "OR luogo_internamento LIKE '%konzentrations%' "
    "GROUP BY luogo_internamento ORDER BY n DESC LIMIT 20"
).fetchall()
print(f'\nCampi di concentramento riferiti:')
for r in rows3:
    print(f'  {r[0]:50s} {r[1]:>6}')

conn.close()
