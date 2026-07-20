import sqlite3
conn = sqlite3.connect('imi_internati.db')
conn.row_factory = sqlite3.Row

print('=== caduti_albooro columns ===')
for r in conn.execute('PRAGMA table_info(caduti_albooro)').fetchall():
    print(f'  {r["name"]:25s} {r["type"]}')

print('\n=== decorati_nastroazzurro columns ===')
for r in conn.execute('PRAGMA table_info(decorati_nastroazzurro)').fetchall():
    print(f'  {r["name"]:25s} {r["type"]}')

print('\n=== Top 10 luoghi_morte ===')
for r in conn.execute(
    "SELECT luogo_morte, COUNT(*) as n FROM caduti_albooro "
    "WHERE luogo_morte IS NOT NULL AND luogo_morte != '' AND luogo_morte != '-' "
    "GROUP BY luogo_morte ORDER BY n DESC LIMIT 10"
).fetchall():
    print(f'  {r["luogo_morte"]:40s} {r["n"]:>6}')

print('\n=== anno_morte distribution ===')
for r in conn.execute(
    "SELECT anno_morte, COUNT(*) as n FROM caduti_albooro "
    "WHERE anno_morte IS NOT NULL AND anno_morte != '' "
    "GROUP BY anno_morte ORDER BY anno_morte"
).fetchall():
    print(f'  {r["anno_morte"]:10s} {r["n"]:>6}')

print('\n=== Total caduti ===')
print(f'  {conn.execute("SELECT COUNT(*) FROM caduti_albooro").fetchone()[0]:>8}')

print('\n=== Total decorati ===')
print(f'  {conn.execute("SELECT COUNT(*) FROM decorati_nastroazzurro").fetchone()[0]:>8}')

print('\n=== anno_decorazione distribution ===')
for r in conn.execute(
    "SELECT anno_decorazione, COUNT(*) as n FROM decorati_nastroazzurro "
    "WHERE anno_decorazione IS NOT NULL AND anno_decorazione != '' "
    "GROUP BY anno_decorazione ORDER BY anno_decorazione"
).fetchall():
    print(f'  {r["anno_decorazione"]:10s} {r["n"]:>6}')

conn.close()
