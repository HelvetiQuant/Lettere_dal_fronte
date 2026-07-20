import sqlite3

conn = sqlite3.connect('imi_internati.db')

# 1. Fix internati table
conn.execute("UPDATE internati SET luogo_nascita = 'Nibbiano (Piacenza)' WHERE id = 22808")
conn.execute("UPDATE internati SET raw_text = REPLACE(raw_text, 'Nibbiaño (Bergamo)', 'Nibbiano (Piacenza)') WHERE id = 22808")
conn.execute("UPDATE internati SET review_reason = 'Divergenza fonti: italiane=Belgrado, Asse=Grecia. Confermata Grecia. Luogo nascita corretto: Nibbiano (Piacenza) non Bergamo.' WHERE id = 22808")

# 2. Fix entita table
conn.execute("UPDATE entita SET luogo = 'Nibbiano (Piacenza)' WHERE fonte_tabella = 'internati' AND fonte_id = 22808")
conn.execute("UPDATE entita SET contesto = REPLACE(contesto, 'Nibbiaño (Bergamo)', 'Nibbiano (Piacenza)') WHERE fonte_tabella = 'internati' AND fonte_id = 22808")

conn.commit()

# Verify
conn.row_factory = sqlite3.Row
r = conn.execute("SELECT id, cognome, nome, data_nascita, luogo_nascita, luogo_cattura, data_cattura, sorte, raw_text, review_reason FROM internati WHERE id=22808").fetchone()
print("AFTER FIX:")
print(f"  id: {r['id']}")
print(f"  cognome: {r['cognome']}")
print(f"  nome: {r['nome']}")
print(f"  data_nascita: {r['data_nascita']}")
print(f"  luogo_nascita: {r['luogo_nascita']}")
print(f"  luogo_cattura: {r['luogo_cattura']}")
print(f"  data_cattura: {r['data_cattura']}")
print(f"  sorte: {r['sorte']}")
print(f"  raw_text: {r['raw_text'][:200]}")
print(f"  review_reason: {r['review_reason']}")

e = conn.execute("SELECT * FROM entita WHERE fonte_tabella='internati' AND fonte_id=22808").fetchone()
if e:
    print(f"\n  entita.luogo: {e['luogo']}")
    print(f"  entita.contesto: {e['contesto']}")

# Check for any other records with Nibbiaño
other = conn.execute("SELECT id, cognome, nome, luogo_nascita FROM internati WHERE luogo_nascita LIKE '%Nibbiaño%' OR luogo_nascita LIKE '%Bergamo%' AND luogo_nascita LIKE '%Nibbiano%'").fetchall()
if other:
    print(f"\n  Other records with same issue: {len(other)}")
    for o in other:
        print(f"    id={o['id']} {o['cognome']} {o['nome']} luogo={o['luogo_nascita']}")

conn.close()
print("\nDONE - DB corrected.")
