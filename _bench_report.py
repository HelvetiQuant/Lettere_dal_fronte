from database import get_conn
import os, time
from collections import Counter

db = "imi_internati.db"
size_mb = os.path.getsize(db) / 1024**2
print(f"DB size: {size_mb:.1f} MB")
print(f"DB WAL size: {os.path.getsize(db+'-wal')/1024:.1f} KB")

conn = get_conn()

tables = [
    "internati","decorati","caduti_albooro","caduti_bologna","caduti_ministero",
    "caduti_sardi","caduti_cwgc","fondi_archivistici","menzioni",
    "decorati_nastroazzurro","documenti_nara_t315","documenti_nara_catalog",
    "archivio_fonti","entita","collegamenti","progress","ai_ricerche"
]
print("\n--- CONTEGGI TABELLE ---")
totale = 0
for t in tables:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n:,}")
        totale += n
    except Exception as e:
        print(f"  {t}: N/A ({e})")
print(f"  TOTALE: {totale:,}")

print("\n--- PRAGMA DB ---")
for pragma in ["page_size","cache_size","journal_mode","synchronous","wal_autocheckpoint","compile_options"]:
    try:
        val = conn.execute(f"PRAGMA {pragma}").fetchone()
        print(f"  {pragma}: {val[0] if val else 'N/A'}")
    except Exception:
        pass

print("\n--- INDICI PER TABELLA ---")
idxs = conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name").fetchall()
print(f"  Totale indici: {len(idxs)}")
per_tab = Counter(t for _, t in idxs)
for tab, n in per_tab.most_common(12):
    print(f"    {tab}: {n}")

print("\n--- DIMENSIONE TABELLE (pagine stimate) ---")
try:
    rows = conn.execute("SELECT name, SUM(payload) as bytes FROM dbstat GROUP BY name ORDER BY bytes DESC LIMIT 15").fetchall()
    for name, b in rows:
        print(f"  {name}: {(b or 0)/1024**2:.2f} MB")
except Exception as e:
    print(f"  dbstat non disponibile: {e}")

print("\n--- QUERY BENCHMARK ---")
queries = [
    ("SELECT cognome FROM caduti_cwgc WHERE cognome LIKE 'Rossi%' LIMIT 100", "cwgc cognome LIKE (indexed)"),
    ("SELECT * FROM entita WHERE tipo='persona' LIMIT 1000", "entita 1k persone"),
    ("SELECT e.valore, c.tabella_origine FROM entita e JOIN collegamenti c ON e.id=c.entita_id WHERE e.tipo='persona' LIMIT 500", "JOIN entita+collegamenti 500"),
    ("SELECT tipo_documento, COUNT(*) FROM archivio_fonti GROUP BY tipo_documento", "archivio_fonti GROUP BY"),
    ("SELECT * FROM caduti_cwgc WHERE cognome='Bianchi' AND guerra='World War 2'", "cwgc cognome exact WW2"),
    ("SELECT COUNT(*) FROM caduti_cwgc", "cwgc COUNT(*)"),
    ("SELECT * FROM documenti_nara_t315 WHERE tipo_documento='Lagebericht' LIMIT 50", "nara_t315 tipo_doc filter"),
    ("SELECT tabella_origine, COUNT(*) FROM collegamenti GROUP BY tabella_origine", "collegamenti GROUP BY source"),
]
for sql, label in queries:
    t0 = time.perf_counter()
    res = conn.execute(sql).fetchall()
    ms = (time.perf_counter()-t0)*1000
    print(f"  [{ms:6.1f} ms] {label} ({len(res)} righe)")

print("\n--- EXPLAIN QUERY PLAN (cwgc cognome) ---")
for row in conn.execute("EXPLAIN QUERY PLAN SELECT * FROM caduti_cwgc WHERE cognome='Bianchi'").fetchall():
    print(f"  {row}")

print("\n--- EXPLAIN QUERY PLAN (JOIN entita+collegamenti) ---")
for row in conn.execute("EXPLAIN QUERY PLAN SELECT e.valore, c.tabella_origine FROM entita e JOIN collegamenti c ON e.id=c.entita_id WHERE e.tipo='persona' LIMIT 100").fetchall():
    print(f"  {row}")

conn.close()
