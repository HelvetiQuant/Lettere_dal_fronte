import sqlite3

# Check eventi_1gm for Mauthausen or concentration camps
conn = sqlite3.connect('eventi_1gm.db')
rows = conn.execute(
    "SELECT id, nome, data_inizio, data_fine, luogo, descrizione "
    "FROM eventi_1gm "
    "WHERE nome LIKE '%mauthausen%' OR nome LIKE '%mathausen%' "
    "OR luogo LIKE '%mauthausen%' OR luogo LIKE '%mathausen%' "
    "OR descrizione LIKE '%mauthausen%' OR descrizione LIKE '%mathausen%' "
    "OR descrizione LIKE '%concentramento%' LIMIT 20"
).fetchall()
print(f'Eventi con Mauthausen/concentramento: {len(rows)}')
for r in rows:
    print(f'  id={r[0]} | {r[1]} | {r[2]}-{r[3]} | {r[4]}')
    if r[5]:
        print(f'    {r[5][:300]}')

print()
# Also check for campo/campi/prigionia
rows2 = conn.execute(
    "SELECT id, nome, data_inizio, data_fine, luogo, descrizione "
    "FROM eventi_1gm "
    "WHERE nome LIKE '%campo%' OR nome LIKE '%prigio%' OR nome LIKE '%intern%' LIMIT 10"
).fetchall()
print(f'Eventi con campo/prigionia/intern: {len(rows2)}')
for r in rows2:
    print(f'  id={r[0]} | {r[1]} | {r[2]}-{r[3]} | {r[4]}')
    if r[5]:
        print(f'    {r[5][:300]}')

# Check event_links for Mauthausen
rows3 = conn.execute(
    "SELECT el.link_type, el.target_table, el.target_id, el.match_field, el.match_value "
    "FROM event_links el "
    "WHERE el.match_value LIKE '%mauthausen%' OR el.match_value LIKE '%mathausen%' LIMIT 20"
).fetchall()
print(f'\nevent_links con Mauthausen: {len(rows3)}')
for r in rows3:
    print(f'  type={r[0]} table={r[1]} id={r[2]} field={r[3]} value={r[4]}')

conn.close()
