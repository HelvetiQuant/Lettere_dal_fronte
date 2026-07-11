"""Arricchisce entità (internati) con fonti esterne candidate.

Legge i primi N internati dal DB, per ognuno costruisce una query
nome+cognome+luogo+data e interroga i provider autorizzati in modalità
federata. I risultati vengono salvati come metadati in `fonti_indice`
usando `register_source_metadata()`.

Vincoli:
- nessuno scraping massivo su fonti con ToS restrittive
- solo provider con api/scraping consentito dal catalogo
- rate-limit tra chiamate
- nessun download di documenti pesanti

Uso:
    python enrich_entities.py --limit 200
"""
import argparse
import json
import time
import sqlite3
from datetime import datetime
from typing import List, Optional

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


def _build_query(internato: dict) -> str:
    parts = []
    if internato.get("nome"):
        parts.append(str(internato["nome"]).strip())
    if internato.get("cognome"):
        parts.append(str(internato["cognome"]).strip())
    if internato.get("luogo_nascita"):
        parts.append(str(internato["luogo_nascita"]).strip())
    if internato.get("data_nascita"):
        parts.append(str(internato["data_nascita"]).strip())
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


def fetch_internati(limit: int = 200) -> List[dict]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nome, cognome, data_nascita, luogo_nascita, residenza, "
        "luogo_cattura, luogo_internamento, matricola, grado "
        "FROM internati ORDER BY id LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def enrich(limit: int = 200, max_results_per_entity: int = 5) -> dict:
    internati = fetch_internati(limit)
    total_created = 0
    total_updated = 0
    errors = 0

    for idx, internato in enumerate(internati, 1):
        query = _build_query(internato)
        if not query.strip():
            continue

        cues = extract_cues(query)
        try:
            results = federated_search(
                query,
                cues=cues,
                providers=ALLOWED_PROVIDERS,
            )
        except Exception as e:
            print(f"[{idx}/{limit}] ERRORE query '{query}': {e}")
            errors += 1
            continue

        kept = 0
        for r in results[:max_results_per_entity]:
            if r.get("error"):
                continue
            meta = _result_to_meta(r, internato)
            try:
                res = register_source_metadata(**meta)
                if res.get("created"):
                    total_created += 1
                else:
                    total_updated += 1
                kept += 1
            except Exception as e2:
                print(f"  ERRORE register_source_metadata: {e2}")
                errors += 1

        print(f"[{idx}/{limit}] {query}: {kept} candidati")
        time.sleep(DELAY_BETWEEN_QUERIES)

    return {
        "processed": len(internati),
        "created": total_created,
        "updated": total_updated,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Arricchisci entità con fonti esterne.")
    parser.add_argument("--limit", type=int, default=200, help="Numero di internati da processare")
    parser.add_argument("--max-results", type=int, default=5, help="Max candidati per entità")
    args = parser.parse_args()

    print(f"Inizio arricchimento per i primi {args.limit} internati...")
    stats = enrich(limit=args.limit, max_results_per_entity=args.max_results)
    print("\nRiepilogo:")
    print(f"  processati: {stats['processed']}")
    print(f"  creati:     {stats['created']}")
    print(f"  aggiornati: {stats['updated']}")
    print(f"  errori:     {stats['errors']}")


if __name__ == "__main__":
    main()
