"""DEPRECATED — Legacy bad links cleanup.

This script is FROZEN. It has known issues:
- Compares fonti_indice.id with collegamenti.entita_id without proving namespaces match
- Destructive DELETE without quarantine
- No typed resource UUIDs
- No restore mechanism

Use the new quarantine pipeline instead:
    python -m linking.cli legacy-relations audit
    python -m linking.cli legacy-relations quarantine --dry-run

To run in audit-only mode:
    LEGACY_JOB_LEGACY_CLEAN_BAD_LINKS=true python _clean_bad_links.py --dry-run
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from linking.kill_switch import LegacyJob, assert_frozen

assert_frozen(LegacyJob.CLEAN_BAD_LINKS, "_clean_bad_links.py is deprecated")

import argparse
import sqlite3
from pathlib import Path
from mass_index import _is_search_page_url
from database import DB_PATH


def run(dry_run: bool = True, delete_links: bool = False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) Elenca tutte le fonti il cui URL catalogo è una pagina di ricerca
    rows = cur.execute("SELECT id, archivio, titolo, url_catalogo FROM fonti_indice").fetchall()
    bad_ids = []
    for r in rows:
        url = r["url_catalogo"] or ""
        if _is_search_page_url(url):
            bad_ids.append(r["id"])

    print(f"Fonti identificate come URL di ricerca: {len(bad_ids)}")
    if not bad_ids:
        conn.close()
        return

    def _in_batches(lst, size=500):
        for i in range(0, len(lst), size):
            yield lst[i:i+size]

    # 2) Conta collegamenti che verrebbero rimossi
    total_links = 0
    link_rows_map = {}
    for batch in _in_batches(bad_ids):
        placeholders = ",".join("?" * len(batch))
        rows = cur.execute(
            f"SELECT tabella_origine, COUNT(*) as n FROM collegamenti WHERE entita_id IN ({placeholders}) GROUP BY tabella_origine",
            batch,
        ).fetchall()
        for r in rows:
            k = r["tabella_origine"]
            link_rows_map[k] = link_rows_map.get(k, 0) + r["n"]
            total_links += r["n"]
    print(f"Collegamenti da rimuovere: {total_links}")
    for k, n in sorted(link_rows_map.items(), key=lambda x: -x[1]):
        print(f"  {k}: {n}")

    # 3) Mostra prime 5 fonti problematiche
    print("\nPrime 5 fonti problematiche:")
    for bid in bad_ids[:5]:
        r = cur.execute("SELECT id, archivio, titolo, url_catalogo FROM fonti_indice WHERE id=?", (bid,)).fetchone()
        print(f"  id={r['id']} | {r['archivio']} | {(r['titolo'] or '')[:60]}")
        print(f"    URL: {(r['url_catalogo'] or '')[:120]}")
        links = cur.execute("SELECT tabella_origine, record_id FROM collegamenti WHERE entita_id=?", (bid,)).fetchall()
        print(f"    collegamenti: {len(links)}")

    if dry_run:
        print("\nDry-run: nessuna modifica apportata. Usa --execute per marcare, --execute --delete-links per rimuovere.")
        conn.close()
        return

    # 4) Esecuzione
    print("\n>>> Esecuzione marcatura fonti come 'url_ricerca' (reversibile)...")
    for batch in _in_batches(bad_ids):
        placeholders = ",".join("?" * len(batch))
        cur.execute(
            f"UPDATE fonti_indice SET confidence=0.0, fetch_status='url_ricerca' WHERE id IN ({placeholders})",
            batch,
        )
    marked = len(bad_ids)
    print(f"Marcate {marked} fonti come 'url_ricerca' con confidence=0.0.")

    if delete_links:
        # V7.3-FIX: Replace DELETE with quarantine — mark as unusable, never delete
        print(">>> Quarantine collegamenti associati (non destructivo)...")
        quarantined_links = 0
        for batch in _in_batches(bad_ids):
            placeholders = ",".join("?" * len(batch))
            # Mark collegamenti as quarantined instead of deleting
            try:
                cur.execute(
                    f"UPDATE collegamenti SET confidenza=0.0 WHERE entita_id IN ({placeholders})",
                    batch,
                )
                quarantined_links += cur.rowcount
            except sqlite3.OperationalError:
                pass

        # Mark fonti as quarantined instead of deleting
        for batch in _in_batches(bad_ids):
            placeholders = ",".join("?" * len(batch))
            try:
                cur.execute(
                    f"UPDATE fonti_indice SET confidence=0.0, fetch_status='quarantined' WHERE id IN ({placeholders})",
                    batch,
                )
            except sqlite3.OperationalError:
                pass
        print(f"Quarantined {quarantined_links} collegamenti (confidence=0.0).")
        print(f"Fonti marcate come 'quarantined' (non eliminate).")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Esegui davvero la marcatura/quarantena")
    parser.add_argument("--delete-links", action="store_true", help="Quarantena collegamenti e fonti (non destructivo)")
    args = parser.parse_args()
    run(dry_run=not args.execute, delete_links=args.delete_links)
