"""Find best candidates — import-safe, read-only.

Uses provenance-aware associations, not LIKE '%cognome%'.
A surname in a title is NOT a source for the person.
Uses accepted evidence associations and verified provenance.

All work is inside main(). Importing this module has zero side effects.
"""


def main():
    from database import get_conn

    conn = get_conn()

    # Try v2 relations first (provenance-aware)
    try:
        rows = conn.execute("""
            SELECT i.id, i.cognome, i.nome, i.luogo_nascita, i.luogo_internamento,
                   i.sorte, i.grado, i.matricola,
                   COUNT(DISTINCT r.id) as n_relations
            FROM internati i
            JOIN populate_progress pp ON pp.internato_id = i.id AND pp.status='done'
            JOIN resource_registry rr ON rr.source_namespace='internati'
                AND rr.source_record_key=CAST(i.id AS TEXT)
            LEFT JOIN relations r ON r.source_resource_id=rr.id
                AND r.status IN ('candidate','confirmed','accepted')
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
            HAVING n_collegamenti > 0
            ORDER BY n_collegamenti DESC
            LIMIT 10
        """).fetchall()

    for r in rows:
        print(f"  id={r['id']} {r['cognome']} {r['nome']} - {r['luogo_nascita']} - {r['sorte']}")

    conn.close()


if __name__ == "__main__":
    main()
