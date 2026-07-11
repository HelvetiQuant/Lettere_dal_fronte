"""Analisi risultati test research-to-index."""
from database import get_conn

conn = get_conn()

print("=== FONTI INDICE PER ARCHIVIO ===")
rows = conn.execute(
    "SELECT archivio, COUNT(*) as n, COUNT(DISTINCT titolo) as distinct_titoli "
    "FROM fonti_indice GROUP BY archivio ORDER BY n DESC"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} record, {r[2]} titoli diversi")

print("\n=== TNA: primi 10 record (diversi?) ===")
rows = conn.execute(
    "SELECT DISTINCT id, segnatura, titolo, confidence FROM fonti_indice "
    "WHERE archivio='TNA' ORDER BY id LIMIT 10"
).fetchall()
for r in rows:
    print(f"  [{r[0]}] {r[1]}: {r[2][:60]} conf={r[3]}")

print("\n=== TNA: quanti titoli unici? ===")
n_unique = conn.execute(
    "SELECT COUNT(DISTINCT titolo) FROM fonti_indice WHERE archivio='TNA'"
).fetchone()[0]
n_total = conn.execute(
    "SELECT COUNT(*) FROM fonti_indice WHERE archivio='TNA'"
).fetchone()[0]
print(f"  {n_total} record totali, {n_unique} titoli unici")

print("\n=== INTERNET ARCHIVE: primi 10 ===")
rows = conn.execute(
    "SELECT DISTINCT id, segnatura, titolo, confidence FROM fonti_indice "
    "WHERE archivio='Internet Archive' ORDER BY id LIMIT 10"
).fetchall()
for r in rows:
    print(f"  [{r[0]}] {r[1]}: {r[2][:60]} conf={r[3]}")

print("\n=== RESEARCH SUBJECTS: status distribution ===")
rows = conn.execute(
    "SELECT status, COUNT(*) FROM research_subjects GROUP BY status"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

print("\n=== RESEARCH GAPS: distribution ===")
rows = conn.execute(
    "SELECT missing_field, suggested_provider, COUNT(*) FROM research_gaps "
    "GROUP BY missing_field, suggested_provider ORDER BY 3 DESC"
).fetchall()
for r in rows:
    print(f"  {r[0]} → {r[1]}: {r[2]}")

print("\n=== SUBJECT SOURCE LINKS: relation types ===")
rows = conn.execute(
    "SELECT relation_type, COUNT(*) FROM research_subject_sources GROUP BY relation_type"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

print("\n=== ESEMPIO: subject_id=1, fonti collegate ===")
rows = conn.execute(
    """SELECT fi.archivio, fi.titolo, fi.confidence, fi.access_type, fi.url_catalogo
       FROM research_subject_sources rs
       JOIN fonti_indice fi ON rs.source_locator_id = fi.id
       WHERE rs.subject_id = 1 LIMIT 10"""
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1][:50]} [{r[3]}] conf={r[2]}")
    if r[4]:
        print(f"    URL: {r[4][:80]}")

conn.close()
