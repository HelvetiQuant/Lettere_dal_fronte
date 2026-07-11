"""Arricchisce entità (internati) con fonti esterne candidate.

Per ogni internato costruisce query che combinano nomi, date, luoghi ed eventi
(cattura, internamento) e interroga i provider autorizzati in modalità federata.
I risultati vengono salvati come metadati in `fonti_indice` tramite
`register_source_metadata()`.

Vincoli:
- nessuno scraping massivo su fonti con ToS restrittive
- solo provider con api/scraping consentito dal catalogo
- rate-limit tra chiamate
- nessun download di documenti pesanti
- resume supportato via file di stato

Uso:
    python enrich_entities.py --limit 1000 --resume
    python enrich_entities.py --offset 200 --limit 500 --skip-processed
"""
import argparse
import json
import logging
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List

from database import DB_PATH
from memory_router import extract_cues
from source_locator import register_source_metadata
from source_providers.federation import federated_search

# Provider autorizzati per query live (catalogo: ha_api=si / scraping=si)
ALLOWED_PROVIDERS = [
    "europeana",
    "tna",
    "antenati",
    "ddb",
    "memoiredeshommes",
    "grand_memorial",
]

DELAY_BETWEEN_QUERIES = 1.0  # secondi
STATE_PATH = Path(__file__).parent / "enrich_entities_state.json"
LOG_PATH = Path(__file__).parent / "enrich_entities.log"


def _setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("enrich_entities")


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_processed_id": 0}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_query(internato: dict) -> str:
    """Costruisce query nominale + luoghi + date + eventi."""
    parts = []
    for key in ("nome", "cognome"):
        if internato.get(key):
            parts.append(str(internato[key]).strip())
    for key in ("data_nascita", "luogo_nascita", "residenza"):
        if internato.get(key):
            parts.append(str(internato[key]).strip())
    # eventi di guerra
    for key in ("data_cattura", "luogo_cattura", "luogo_internamento"):
        if internato.get(key):
            parts.append(str(internato[key]).strip())
    return " ".join(parts)


def _safe_note(result: dict) -> str:
    fields = {
        k: v for k, v in result.items()
        if k not in {
            "archivio", "titolo", "tipo_fonte", "url_catalogo",
            "url_file", "iiif_manifest", "access_type", "confidence",
            "provider", "score",
        } and v not in (None, "")
    }
    if not fields:
        return ""
    try:
        return json.dumps(fields, ensure_ascii=False, default=str)[:4000]
    except Exception:
        return str(fields)[:4000]


def _result_to_meta(result: dict, internato: dict) -> dict:
    archivio = result.get("archivio") or result.get("provider", "fonte_esterna")
    titolo = result.get("titolo") or "Risultato ricerca"
    url_catalogo = result.get("catalog_url") or result.get("direct_url") or ""
    direct_url = result.get("direct_url") or ""

    meta = {
        "archivio": archivio,
        "segnatura": result.get("provider_record_id") or f"{internato.get('id')}_{result.get('provider')}",
        "titolo": titolo,
        "tipo_fonte": result.get("source_type") or "fonte_esterna",
        "url_catalogo": url_catalogo or None,
        "url_file": direct_url if direct_url != url_catalogo else None,
        "iiif_manifest": result.get("thumbnail") or None,
        "access_type": result.get("access_type") or "online",
        "confidence": min(max(result.get("score", 0.5), 0.0), 1.0),
        "soggetti_collegati": _build_query(internato),
        "note": _safe_note(result),
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {k: v for k, v in meta.items() if v not in (None, "")}


def fetch_internati(
    limit: int = 200,
    offset: int = 0,
) -> List[dict]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nome, cognome, data_nascita, luogo_nascita, residenza, "
        "data_cattura, luogo_cattura, luogo_internamento, matricola, grado "
        "FROM internati ORDER BY id LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _process_one(
    internato: dict,
    offset: int,
    idx: int,
    max_results_per_entity: int,
    rate_lock: threading.Lock,
    db_lock: threading.Lock,
    min_interval: float,
    logger: logging.Logger,
    stats: dict,
) -> int:
    """Processa un singolo internato. Thread-safe. Ritorna ultimo ID."""
    query = _build_query(internato)
    if not query.strip():
        logger.info(f"[{idx}] ID {internato['id']}: query vuota, salto")
        return internato["id"]

    # rate limiting globale
    with rate_lock:
        now = time.time()
        elapsed = now - stats["last_request_at"]
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        stats["last_request_at"] = time.time()

    cues = extract_cues(query)
    try:
        results = federated_search(
            query,
            cues=cues,
            providers=ALLOWED_PROVIDERS,
        )
    except Exception as e:
        logger.error(f"[{idx}] ID {internato['id']} ERRORE query '{query}': {e}")
        with db_lock:
            stats["errors"] += 1
        return internato["id"]

    kept = 0
    for r in results[:max_results_per_entity]:
        if r.get("error"):
            continue
        meta = _result_to_meta(r, internato)
        try:
            # DB writes serializzate per evitare sqlite locked
            with db_lock:
                res = register_source_metadata(**meta)
                if res.get("created"):
                    stats["created"] += 1
                else:
                    stats["updated"] += 1
                kept += 1
        except Exception as e2:
            logger.error(f"  ERRORE register_source_metadata: {e2}")
            with db_lock:
                stats["errors"] += 1

    logger.info(f"[{idx}] ID {internato['id']} '{query}': {kept} candidati")
    return internato["id"]


def enrich(
    limit: int = 200,
    offset: int = 0,
    max_results_per_entity: int = 5,
    delay: float = DELAY_BETWEEN_QUERIES,
    workers: int = 5,
    logger: logging.Logger = None,
) -> dict:
    logger = logger or logging.getLogger("enrich_entities")
    internati = fetch_internati(limit=limit, offset=offset)
    total = len(internati)

    stats = {
        "created": 0,
        "updated": 0,
        "errors": 0,
        "last_request_at": 0.0,
    }
    rate_lock = threading.Lock()
    db_lock = threading.Lock()
    last_id = offset

    # minimo intervallo tra l'inizio di due query (globale su tutti i worker)
    min_interval = delay / workers if workers > 0 else delay

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(
                _process_one,
                internato,
                offset,
                offset + i + 1,
                max_results_per_entity,
                rate_lock,
                db_lock,
                min_interval,
                logger,
                stats,
            ): i
            for i, internato in enumerate(internati)
        }

        for future in as_completed(future_to_idx):
            try:
                last_id = max(last_id, future.result())
            except Exception as e:
                logger.error(f"Errore worker: {e}")
                with db_lock:
                    stats["errors"] += 1
            # salva stato periodicamente
            _save_state({"last_processed_id": last_id, "offset": offset + len(internati)})

    return {
        "processed": total,
        "created": stats["created"],
        "updated": stats["updated"],
        "errors": stats["errors"],
        "last_processed_id": last_id,
    }


def main():
    parser = argparse.ArgumentParser(description="Arricchisci entità con fonti esterne.")
    parser.add_argument("--limit", type=int, default=200, help="Numero di internati da processare")
    parser.add_argument("--offset", type=int, default=0, help="Offset iniziale")
    parser.add_argument("--max-results", type=int, default=5, help="Max candidati per entità")
    parser.add_argument("--resume", action="store_true", help="Riprendi dallo stato salvato")
    parser.add_argument("--delay", type=float, default=DELAY_BETWEEN_QUERIES,
                        help="Secondi di attesa tra una query e l'altra")
    parser.add_argument("--workers", type=int, default=5, help="Thread worker concorrenti")
    args = parser.parse_args()

    logger = _setup_logging()
    state = _load_state()
    offset = state.get("offset", 0) if args.resume else args.offset

    logger.info(f"Inizio arricchimento: offset={offset}, limit={args.limit}, delay={args.delay}, workers={args.workers}")
    stats = enrich(
        limit=args.limit,
        offset=offset,
        max_results_per_entity=args.max_results,
        delay=args.delay,
        workers=args.workers,
        logger=logger,
    )
    logger.info("Riepilogo:")
    logger.info(f"  processati: {stats['processed']}")
    logger.info(f"  creati:     {stats['created']}")
    logger.info(f"  aggiornati: {stats['updated']}")
    logger.info(f"  errori:     {stats['errors']}")
    logger.info(f"  ultimo ID:  {stats['last_processed_id']}")


if __name__ == "__main__":
    main()
