import archivio_fonti
from database import get_conn

q = archivio_fonti.query_archivio(tipo_documento="Lagebericht", teatro="Balcani", limit=3)
print(f"Lagebericht Balcani: {q['total']} risultati")
for r in q["risultati"]:
    print(f"  [{r['segnatura']}] {r['titolo']} | {r['data_inizio']} | ocr={r['ocr_status']} | readable={r['readable']}")
    print(f"    file_url={r['file_url']}")
    ant = (r["testo_anteprima"] or "")[:100]
    print(f"    anteprima: {ant}")

print()
print("Distribuzione ocr_status:")
conn = get_conn()
for row in conn.execute("SELECT ocr_status, readable, COUNT(*) as n FROM archivio_fonti GROUP BY ocr_status, readable ORDER BY n DESC").fetchall():
    print(f"  ocr={row[0]} readable={row[1]}: {row[2]}")

print()
print("Distribuzione tipo_documento:")
for row in conn.execute("SELECT tipo_documento, COUNT(*) as n FROM archivio_fonti GROUP BY tipo_documento ORDER BY n DESC LIMIT 10").fetchall():
    print(f"  {row[0]}: {row[1]}")
conn.close()
