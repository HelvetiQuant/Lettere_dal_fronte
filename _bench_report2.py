from database import get_conn
import os, time

conn = get_conn()

print("--- EXPLAIN QUERY PLAN ---")
queries_plan = [
    ("SELECT * FROM caduti_cwgc WHERE cognome LIKE 'Rossi%' LIMIT 100", "cwgc LIKE"),
    ("SELECT * FROM caduti_cwgc WHERE cognome='Bianchi' AND guerra='World War 2'", "cwgc exact"),
    ("SELECT e.valore, c.tabella_origine FROM entita e JOIN collegamenti c ON e.id=c.entita_id WHERE e.tipo='persona' LIMIT 100", "JOIN entita+collegamenti"),
    ("SELECT tabella_origine, COUNT(*) FROM collegamenti GROUP BY tabella_origine", "collegamenti GROUP BY"),
]
for sql, label in queries_plan:
    print(f"\n[{label}]")
    for row in conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall():
        print(f"  {tuple(row)}")

print("\n--- DIMENSIONE FILE MODULI (KB) ---")
moduli = [
    "app.py","database.py","linker.py","caduti_cwgc.py","search_service.py",
    "archivio_fonti.py","nara_catalog.py","nara_t315_ocr.py","ai_research.py",
    "extractor.py","caduti_albooro.py","decorati_nastroazzurro.py",
]
for m in moduli:
    try:
        kb = os.path.getsize(m)/1024
        print(f"  {m}: {kb:.1f} KB")
    except Exception:
        pass

print("\n--- THREAD BACKGROUND ATTIVI ---")
import threading
for t in threading.enumerate():
    print(f"  {t.name} daemon={t.daemon} alive={t.is_alive()}")

print("\n--- MEMORIA PROCESSO PYTHON ---")
try:
    import psutil, os as _os
    proc = psutil.Process(_os.getpid())
    mem = proc.memory_info()
    print(f"  RSS: {mem.rss/1024**2:.1f} MB")
    print(f"  VMS: {mem.vms/1024**2:.1f} MB")
    print(f"  CPU%: {proc.cpu_percent(interval=0.5):.1f}%")
except ImportError:
    print("  psutil non installato — stima non disponibile")

conn.close()
