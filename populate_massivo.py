"""Popolamento massivo fonti_indice — versione concorrente, solo Arolsen.

Provider attivi:
  - Arolsen Archives: 1 query per internato (cognome) — stabile, ~3s/query
  (TNA disabilitato: WAF blocca il batch)
  (IA disabilitato: timeout variabili bloccano i worker)
Usa ThreadPoolExecutor (WORKERS thread) con chunk da 200.
Resume: salta internati già presenti in populate_progress.
"""
import sys
import time
import logging
import warnings
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("populate")

from database import get_conn
from source_providers.providers import ProviderArolsen
from research_to_index import upsert_source_locator

BATCH_SIZE  = int(sys.argv[1]) if len(sys.argv) > 1 else 20464
OFFSET      = int(sys.argv[2]) if len(sys.argv) > 2 else 0
WORKERS     = int(sys.argv[3]) if len(sys.argv) > 3 else 2
QUERY_FAST_THRESHOLD = 8.0   # se query < 8s, aggiungi 1s delay
QUERY_SLOW_DELAY     = 0.0   # se query >= 8s (già throttlata), delay 0

_lock = threading.Lock()
_total_new = 0
_total_queries = 0
_errors = 0


def get_internati_batch(limit, offset):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, cognome, nome FROM internati "
        "WHERE cognome IS NOT NULL AND cognome != '' ORDER BY id LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_processed_ids():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT internato_id FROM populate_progress WHERE status = 'done'"
        ).fetchall()
        return {r[0] for r in rows}
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def mark_processed(internato_id, found_count):
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS populate_progress (
            internato_id INTEGER PRIMARY KEY,
            status TEXT,
            found_count INTEGER,
            processed_at TEXT
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO populate_progress "
        "(internato_id, status, found_count, processed_at) VALUES (?, ?, ?, ?)",
        (internato_id, "done", found_count, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()



def process_one(inter, arolsen):
    global _total_new, _total_queries, _errors
    iid = inter["id"]
    cognome = inter["cognome"] or ""
    found = 0

    t_query = time.time()
    try:
        for r in arolsen.search(cognome):
            try:
                upsert_source_locator(r)
                found += 1
            except Exception:
                pass
    except Exception:
        with _lock:
            _errors += 1
    # delay adattivo: solo se Arolsen ha risposto subito (non throttlato)
    elapsed = time.time() - t_query
    if elapsed < QUERY_FAST_THRESHOLD:
        time.sleep(1.0)

    mark_processed(iid, found)
    with _lock:
        _total_new += found
        _total_queries += 1
    return iid, cognome, found


def main():
    global _total_new, _total_queries, _errors

    print(f"{'='*60}")
    print(f"  POPOLAMENTO MASSIVO FONTI_INDICE (concorrente)")
    print(f"  Batch: {BATCH_SIZE} | Offset: {OFFSET} | Workers: {WORKERS}")
    print(f"{'='*60}")

    print("  Inizializzazione provider...")
    arolsen_pool = [ProviderArolsen() for _ in range(WORKERS)]
    print(f"  OK — Arolsen×{WORKERS} (delay adattivo, TNA e IA disabilitati)")

    internati = get_internati_batch(BATCH_SIZE, OFFSET)
    processed_ids = get_processed_ids()
    todo = [i for i in internati if i["id"] not in processed_ids]
    print(f"  Da processare: {len(todo)} / {len(internati)} (già fatti: {len(processed_ids)})")

    if not todo:
        print("  Niente da fare.")
        return

    t0 = time.time()
    done_count = 0
    CHUNK = 200
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for chunk_start in range(0, len(todo), CHUNK):
            chunk = todo[chunk_start:chunk_start + CHUNK]
            futures = {
                ex.submit(process_one, inter, arolsen_pool[(chunk_start + i) % WORKERS]): inter
                for i, inter in enumerate(chunk)
            }
            for fut in as_completed(futures):
                try:
                    iid, cognome, found = fut.result()
                except Exception:
                    pass
                done_count += 1
                if done_count % 50 == 0:
                    elapsed = time.time() - t0
                    rate = done_count / elapsed if elapsed else 0
                    eta = (len(todo) - done_count) / rate if rate else 0
                    print(f"  [{done_count}/{len(todo)}] "
                          f"{rate:.2f} int/s | "
                          f"ETA {eta/60:.0f}m | "
                          f"fonti: {_total_new}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  RIASSUNTO")
    print(f"{'='*60}")
    print(f"  Processati: {_total_queries} in {elapsed:.0f}s ({_total_queries/elapsed:.1f}/s)")
    print(f"  Nuove fonti: {_total_new}")
    print(f"  Errori: {_errors}")

    conn = get_conn()
    for arch in ["Arolsen Archives"]:
        count = conn.execute(
            "SELECT COUNT(*) FROM fonti_indice WHERE archivio LIKE ?", (f"%{arch}%",)
        ).fetchone()[0]
        print(f"  {arch}: {count}")
    print(f"  TOTALE fonti_indice: {conn.execute('SELECT COUNT(*) FROM fonti_indice').fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
