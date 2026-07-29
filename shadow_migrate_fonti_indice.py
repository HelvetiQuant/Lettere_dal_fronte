"""
Shadow migration fonti_indice → archive.external_items.

Migra i record SQLite fonti_indice (35K+ righe) nel nuovo schema canonico
Supabase archive.external_items. Shadow migration: non cancella i dati legacy,
sincronizza solo in lettura.

Mapping campi:
  - archivio/fondo/segnatura → holding_institution/collection_or_fonds/archival_signature
  - titolo → title
  - tipo_fonte → item_type
  - url_catalogo/url_file → canonical_url
  - iiif_manifest → iiif_manifest
  - page_start/page_end → page_range
  - hash_se_disponibile → content_checksum
  - access_type → access_status
  - fetch_status → review_status
  - confidence → confidence
  - created_at → first_seen_at

Usage:
  python shadow_migrate_fonti_indice.py --dry-run
  python shadow_migrate_fonti_indice.py --batch 1000
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("shadow_migrate_fonti_indice")


# ─── Config ────────────────────────────────────────────────────────────────

SQLITE_DB_PATH = Path(__file__).parent / "imi_internati.db"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


# ─── Supabase RPC helpers ─────────────────────────────────────────────────────

def _exec_sql_returning(sql: str) -> list | dict:
    """Execute SQL that returns rows via exec_sql_returning RPC."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql_returning"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=120)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


def _execute_sql(sql: str) -> dict:
    """Execute SQL on Supabase via exec_sql RPC."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=120)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


# ─── SQLite helpers ───────────────────────────────────────────────────────────

def get_sqlite_conn():
    """Get SQLite connection."""
    if not SQLITE_DB_PATH.exists():
        raise FileNotFoundError(f"SQLite DB not found: {SQLITE_DB_PATH}")
    return sqlite3.connect(SQLITE_DB_PATH)


def count_fonti_indice(conn: sqlite3.Connection) -> int:
    """Count total rows in fonti_indice."""
    cur = conn.execute("SELECT COUNT(*) FROM fonti_indice")
    return cur.fetchone()[0]


def fetch_fonti_indice_batch(conn: sqlite3.Connection, offset: int, limit: int):
    """Fetch a batch of fonti_indice rows."""
    cur = conn.execute(
        f"SELECT * FROM fonti_indice ORDER BY id LIMIT {limit} OFFSET {offset}"
    )
    columns = [desc[0] for desc in cur.description]
    for row in cur:
        yield dict(zip(columns, row))


# ─── Mapping functions ───────────────────────────────────────────────────────

def map_to_external_item(row: dict) -> dict:
    """Map SQLite fonti_indice row to archive.external_item schema."""
    from source_pipeline import compute_stable_id

    # Build stable_id from archivio+segnatura+titolo (UNIQUE constraint in SQLite)
    archivio = row.get("archivio", "") or ""
    segnatura = row.get("segnatura", "") or ""
    titolo = row.get("titolo", "") or ""
    external_id = f"{archivio}:{segnatura}:{titolo}"
    stable_id = compute_stable_id("ext", external_id, "fonti_indice")

    # Map fields
    return {
        "stable_id": stable_id,
        "provider_code": "fonti_indice",  # Legacy source
        "external_id": external_id,
        "item_type": row.get("tipo_fonte", "document") or "document",
        "title": row.get("titolo", "") or "",
        "description": row.get("note", "") or "",
        "date_text": "",  # Could derive from data_inizio/data_fine
        "date_from": None,
        "date_to": None,
        "language": "it",
        "reference_code": row.get("segnatura", "") or "",
        "canonical_url": row.get("url_catalogo", "") or row.get("url_file", "") or "",
        "parent_external_id": None,
        "access_status": row.get("access_type", "online") or "online",
        "review_status": row.get("fetch_status", "mai_scaricato") or "candidate",
        "metadata_hash": row.get("hash_se_disponibile", "") or "",
        "http_status": None,
        # New columns from 003 migration
        "holding_institution": row.get("archivio", "") or "",
        "collection_or_fonds": row.get("fondo", "") or "",
        "archival_signature": row.get("segnatura", "") or "",
        "persistent_identifier": row.get("iiif_manifest", "") or "",
        "rights_uri": "",  # Unknown for legacy sources
        "source_version": "shadow_migration_001",
        "content_checksum": row.get("hash_se_disponibile", "") or "",
        "raw_metadata": {
            "serie": row.get("serie", "") or "",
            "soggetti_collegati": row.get("soggetti_collegati", "") or "",
            "persone_possibili": row.get("persone_possibili", "") or "",
            "reparto": row.get("reparto", "") or "",
            "luogo": row.get("luogo", "") or "",
            "data_inizio": row.get("data_inizio", "") or "",
            "data_fine": row.get("data_fine", "") or "",
            "page_start": row.get("page_start") or None,
            "page_end": row.get("page_end") or None,
            "confidence": row.get("confidence", 0.5),
            "created_at": row.get("created_at", "") or "",
        },
    }


def upsert_external_item(item: dict) -> int | None:
    """Upsert a single external_item to Supabase."""

    stable_id = item["stable_id"]
    provider_code = item["provider_code"]
    external_id = item["external_id"].replace("'", "''")
    item_type = item["item_type"]
    title = item["title"].replace("'", "''")
    description = item["description"].replace("'", "''")[:500]
    canonical_url = item["canonical_url"].replace("'", "''")
    holding_institution = item["holding_institution"].replace("'", "''")
    collection_or_fonds = item["collection_or_fonds"].replace("'", "''")
    archival_signature = item["archival_signature"].replace("'", "''")
    persistent_identifier = item["persistent_identifier"].replace("'", "''")
    rights_uri = item["rights_uri"].replace("'", "''")
    source_version = item["source_version"].replace("'", "''")
    content_checksum = item["content_checksum"].replace("'", "''")
    raw_json = json.dumps(item["raw_metadata"], ensure_ascii=False)[:5000]
    access_status = item["access_status"].replace("'", "''")
    review_status = item["review_status"].replace("'", "''")
    reference_code = item["reference_code"].replace("'", "''")

    sql = f"""
    WITH x AS (
        INSERT INTO archive.external_items
            (stable_id, provider_code, external_id, item_type, title, description,
             canonical_url, holding_institution, collection_or_fonds, archival_signature,
             persistent_identifier, rights_uri, source_version, content_checksum,
             raw_metadata, access_status, review_status, reference_code)
        VALUES
            ('{stable_id}', '{provider_code}', '{external_id}', '{item_type}',
             '{title}', '{description}', '{canonical_url}',
             '{holding_institution}', '{collection_or_fonds}', '{archival_signature}',
             '{persistent_identifier}', '{rights_uri}', '{source_version}', '{content_checksum}',
             $${raw_json}$$::jsonb, '{access_status}', '{review_status}', '{reference_code}')
        ON CONFLICT (stable_id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            canonical_url = EXCLUDED.canonical_url,
            raw_metadata = EXCLUDED.raw_metadata,
            updated_at = now()
        RETURNING id
    )
    SELECT json_agg(row_to_json(x)) FROM x;
    """
    result = _exec_sql_returning(sql)
    if isinstance(result, list) and result:
        return result[0].get("id")
    if isinstance(result, dict) and result.get("__error__"):
        logger.error("Upsert failed: %s", result.get("error", ""))
        return None

    # Fallback: query after insert
    check_sql = f"SELECT json_agg(row_to_json(x)) FROM (SELECT id FROM archive.external_items WHERE stable_id = '{stable_id}' LIMIT 1) x;"
    existing = _exec_sql_returning(check_sql)
    if isinstance(existing, list) and existing:
        return existing[0].get("id")
    return None


# ─── Main migration ───────────────────────────────────────────────────────────

def main(dry_run: bool = False, batch_size: int = 1000):
    """Run shadow migration."""
    logger.info("Starting shadow migration fonti_indice → archive.external_items")
    logger.info(f"SQLite DB: {SQLITE_DB_PATH}")
    logger.info(f"Supabase: {SUPABASE_URL}")
    logger.info(f"Dry run: {dry_run}, Batch size: {batch_size}")

    conn = get_sqlite_conn()
    total = count_fonti_indice(conn)
    logger.info(f"Total fonti_indice rows: {total}")

    if dry_run:
        logger.info("DRY RUN: No data will be written to Supabase")
        # Sample first 10 rows
        for i, row in enumerate(fetch_fonti_indice_batch(conn, 0, 10)):
            item = map_to_external_item(row)
            logger.info(f"Sample {i+1}: stable_id={item['stable_id'][:32]}... title={item['title'][:50]}")
        logger.info("DRY RUN complete")
        return

    migrated = 0
    skipped = 0
    errors = 0

    for offset in range(0, total, batch_size):
        logger.info(f"Processing batch {offset}-{offset+batch_size}/{total}")
        batch_count = 0

        for row in fetch_fonti_indice_batch(conn, offset, batch_size):
            try:
                item = map_to_external_item(row)
                item_id = upsert_external_item(item)
                if item_id:
                    migrated += 1
                    batch_count += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error(f"Error processing row {row.get('id')}: {e}")
                errors += 1

        logger.info(f"Batch complete: {batch_count} migrated")
        if batch_count == 0:
            skipped += batch_size

    logger.info(f"Migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Shadow migration fonti_indice → archive.external_items")
    parser.add_argument("--dry-run", action="store_true", help="Dry run, no writes")
    parser.add_argument("--batch", type=int, default=1000, help="Batch size")
    args = parser.parse_args()

    main(dry_run=args.dry_run, batch_size=args.batch)
