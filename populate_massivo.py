"""Popolamento massivo fonti_indice da Arolsen, TNA, Internet Archive.

Strategia:
- Legge un campione di internati dal DB (batch configurabile)
- Per ogni internato, cerca su Arolsen (per cognome), TNA (per cognome + Italian), IA (per cognome + Italian prisoner)
- Registra i risultati in fonti_indice tramite upsert_source_locator
- Rate limiting: 1s tra internati, 0.5s tra provider
- Resume: salta internati già processati (tabella progress)
"""
import sys
import time
import logging
import warnings
import sqlite3
from datetime import datetime

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("populate")

from database import get_conn
from source_providers.providers import (
    ProviderArolsen,
    ProviderNationalArchivesUK,
    ProviderInternetArchive,
)
from research_to_index import upsert_source_locator

BATCH_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 100
OFFSET = int(sys.argv[2]) if len(sys.argv) > 2 else 0


def get_internati_batch(limit, offset):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, cognome, nome FROM internati WHERE cognome IS NOT NULL AND cognome != '' ORDER BY id LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_processed_ids():
    """Restituisce set di ID già processati da progress table."""
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
        "INSERT OR REPLACE INTO populate_progress (internato_id, status, found_count, processed_at) VALUES (?, ?, ?, ?)",
        (internato_id, "done", found_count, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def main():
    print(f"{'='*60}")
    print(f"  POPOLAMENTO MASSIVO FONTI_INDICE")
    print(f"  Batch: {BATCH_SIZE} internati (offset {OFFSET})")
    print(f"{'='*60}")

    # Init providers
    print("  Inizializzazione provider...")
    arolsen = ProviderArolsen()
    tna = ProviderNationalArchivesUK()
    ia = ProviderInternetArchive()
    print("  OK")

    # Get batch
    internati = get_internati_batch(BATCH_SIZE, OFFSET)
    print(f"  Internati da processare: {len(internati)}")

    # Resume: skip already processed
    processed = get_processed_ids()
    if processed:
        print(f"  Già processati (skip): {len(processed)}")

    total_new = 0
    total_queries = 0
    errors = 0

    for idx, inter in enumerate(internati):
        iid = inter["id"]
        cognome = inter["cognome"] or ""
        nome = inter["nome"] or ""

        if iid in processed:
            continue

        query_arolsen = cognome
        query_tna = "Italian prisoner of war"  # cognomi singoli causano HTTP 500
        query_ia = f"{cognome} Italian prisoner of war"

        found = 0

        # 1. Arolsen
        try:
            results = arolsen.search(query_arolsen)
            for r in results:
                upsert_source_locator(r)
                found += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning("Arolsen error for %s: %s", cognome, e)

        time.sleep(0.3)

        # 2. TNA (ogni 10 internati — TNA è lento per WAF)
        if idx % 10 == 0:
            try:
                results = tna.search(query_tna)
                for r in results:
                    upsert_source_locator(r)
                    found += 1
            except Exception as e:
                errors += 1
                if errors <= 10:
                    logger.warning("TNA error for %s: %s", cognome, e)

            time.sleep(0.5)

        # 3. Internet Archive (ogni 5 internati)
        if idx % 5 == 0:
            try:
                results = ia.search(query_ia)
                for r in results:
                    upsert_source_locator(r)
                    found += 1
            except Exception as e:
                errors += 1
                if errors <= 10:
                    logger.warning("IA error for %s: %s", cognome, e)

            time.sleep(0.3)

        total_new += found
        total_queries += 1
        mark_processed(iid, found)

        if (idx + 1) % 10 == 0:
            print(f"  [{idx+1}/{len(internati)}] {cognome} {nome} → +{found} fonti (total: {total_new})")

    # Final stats
    print(f"\n{'='*60}")
    print(f"  RIASSUNTO")
    print(f"{'='*60}")
    print(f"  Internati processati: {total_queries}")
    print(f"  Nuove fonti inserite: {total_new}")
    print(f"  Errori: {errors}")

    conn = get_conn()
    for arch in ["Arolsen", "TNA", "Internet Archive"]:
        count = conn.execute(
            "SELECT COUNT(*) FROM fonti_indice WHERE archivio LIKE ?", (f"%{arch}%",)
        ).fetchone()[0]
        print(f"  {arch}: {count} record totali")
    total = conn.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
    print(f"  TOTALE fonti_indice: {total}")
    conn.close()


if __name__ == "__main__":
    main()
