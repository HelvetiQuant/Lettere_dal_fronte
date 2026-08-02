"""Find best candidates — uses provenance-aware associations, not LIKE '%cognome%'.

A surname in a title is NOT a source for the person.
Uses accepted evidence associations and verified provenance.
"""
from database import get_conn

conn = get_conn()

# Try v2 relations first (provenance-aware)
try:
    rows = conn.execute("""
        SELECT i.id, i.cognome, i.nome, i.luogo_nascita, i.luogo_internamento,
               i.sorte, i.grado, i.matricola,
               COUNT(DISTINCT r.relation_id) as n_relations
        FROM internati i
        JOIN populate_progress pp ON pp.internato_id = i.id AND pp.status='done'
        LEFT JOIN relations r ON r.subject_type='internati' AND r.subject_id=i.id
            AND r.status='accepted'
        WHERE i.cognome IS NOT NULL AND i.nome IS NOT NULL
          AND i.luogo_nascita IS NOT NULL
          AND i.sorte IS NOT NULL AND i.sorte != ''
        GROUP BY i.id
        HAVING n_relations > 0
        ORDER BY n_relations DESC
        LIMIT 10
    """).fetchall()
except Exception:
    # Fallback: use collegamenti (legacy but better than LIKE)
    rows = conn.execute("""
        SELECT i.id, i.cognome, i.nome, i.luogo_nascita, i.luogo_internamento,
               i.sorte, i.grado, i.matricola,
               COUNT(DISTINCT c.id) as n_collegamenti
        FROM internati i
        JOIN populate_progress pp ON pp.internato_id = i.id AND pp.status='done'
        JOIN collegamenti c ON c.tabella_origine='internati' AND c.record_id=i.id
        WHERE i.cognome IS NOT NULL AND i.nome IS NOT NULL
          AND i.luogo_nascita IS NOT NULL
          AND i.sorte IS NOT NULL AND i.sorte != ''
        GROUP BY i.id
        ORDER BY n_collegamenti DESC
        LIMIT 10
    """).fetchall()

conn.close()

print(f"{'ID':>6} {'COGNOME':<18} {'NOME':<14} {'LUOGO NASC.':<20} {'SORTE':<18} {'FONTI':>6}")
print("-" * 90)
for r in rows:
    n = r['n_relations'] if 'n_relations' in r.keys() else r['n_collegamenti']
    print(f"{r['id']:>6} {r['cognome']:<18} {r['nome']:<14} {r['luogo_nascita']:<20} {r['sorte']:<18} {n:>6}")
