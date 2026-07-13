"""Trova i 5 internati con più fonti in fonti_indice per testare la biografia."""
from database import get_conn

conn = get_conn()

# Top candidati: più fonti Arolsen + hanno luogo nascita + sorte compilata
rows = conn.execute("""
    SELECT i.id, i.cognome, i.nome, i.luogo_nascita, i.luogo_internamento,
           i.sorte, i.grado, i.matricola,
           COUNT(f.id) as n_fonti
    FROM internati i
    JOIN populate_progress pp ON pp.internato_id = i.id AND pp.status='done'
    JOIN fonti_indice f ON LOWER(f.titolo) LIKE '%' || LOWER(i.cognome) || '%'
                       OR LOWER(f.persone_possibili) LIKE '%' || LOWER(i.cognome) || '%'
    WHERE i.cognome IS NOT NULL AND i.nome IS NOT NULL
      AND i.luogo_nascita IS NOT NULL
      AND i.sorte IS NOT NULL AND i.sorte != ''
    GROUP BY i.id
    ORDER BY n_fonti DESC
    LIMIT 10
""").fetchall()

conn.close()

print(f"{'ID':>6} {'COGNOME':<18} {'NOME':<14} {'LUOGO NASC.':<20} {'SORTE':<18} {'FONTI':>6}")
print("-" * 90)
for r in rows:
    print(f"{r['id']:>6} {r['cognome']:<18} {r['nome']:<14} {r['luogo_nascita']:<20} {r['sorte']:<18} {r['n_fonti']:>6}")
