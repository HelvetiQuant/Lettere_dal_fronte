import sqlite3
from datetime import datetime

conn = sqlite3.connect('imi_internati.db')
conn.row_factory = sqlite3.Row
now = datetime.now().isoformat(timespec="seconds")

# 1. Fix internati table — overlay correction, raw_text IMMUTABLE
# Aggiorna il campo normalizzato (luogo_nascita) ma NON raw_text
conn.execute("UPDATE internati SET luogo_nascita = 'Nibbiano (Piacenza)' WHERE id = 22808")
conn.execute("UPDATE internati SET review_reason = 'Divergenza fonti: italiane=Belgrado, Asse=Grecia. Confermata Grecia. Luogo nascita corretto: Nibbiano (Piacenza) non Bergamo.' WHERE id = 22808")

# Registra la correzione come overlay in entity_variants (non tocca raw_text)
conn.execute("""
    INSERT OR REPLACE INTO entity_variants
        (entity_type, entity_id, field_name, original_value, variant_value, variant_type, origin, confidence, verified, created_at)
    VALUES ('internati', 22808, 'luogo_nascita', 'Nibbiaño (Bergamo)', 'Nibbiano (Piacenza)', 'correction', 'manual_review', 1.0, 1, ?)
""", (now,))

# 2. Fix entita table — aggiorna luogo normalizzato, non contesto originale
conn.execute("UPDATE entita SET luogo = 'Nibbiano (Piacenza)' WHERE fonte_tabella = 'internati' AND fonte_id = 22808")
# Registra anche variant per entita.contesto
conn.execute("""
    INSERT OR REPLACE INTO entity_variants
        (entity_type, entity_id, field_name, original_value, variant_value, variant_type, origin, confidence, verified, created_at)
    VALUES ('entita', NULL, 'contesto', 'Nibbiaño (Bergamo)', 'Nibbiano (Piacenza)', 'correction', 'manual_review', 1.0, 1, ?)
""", (now,))

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
