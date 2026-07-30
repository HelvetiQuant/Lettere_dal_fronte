"""Sync WW1 documents and event_links from local SQLite to Supabase.
Creates tables if needed, then upserts all rows.

Kill switch: set SYNC_EVENT_LINKS_SUPABASE=false in .env to suspend
legacy event_links sync until linking v2 migration is complete.
"""
import json
import os
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

from supabase_client import execute_sql, insert_batch, table_exists_on_supabase

EDB = Path(__file__).parent / "eventi_1gm.db"
DB_PATH = Path(__file__).parent / "imi_internati.db"

# ─── Schema DDL ──────────────────────────────────────────────────────────────

ARCHIVIO_DOCS_DDL = """
CREATE TABLE IF NOT EXISTS "archivio_documenti" (
    "provider"        TEXT NOT NULL,
    "external_id"     TEXT NOT NULL,
    "doc_type"        TEXT,
    "title"           TEXT,
    "description"     TEXT,
    "creator"         TEXT,
    "date_text"       TEXT,
    "year_start"      INTEGER,
    "year_end"        INTEGER,
    "place"           TEXT,
    "war"             TEXT DEFAULT 'WWI',
    "language"        TEXT,
    "rights"          TEXT,
    "source_url"      TEXT NOT NULL,
    "thumbnail_url"   TEXT,
    "iiif_manifest"   TEXT,
    "provider_collection" TEXT,
    "retrieved_at"    TEXT,
    "raw_json"        TEXT,
    PRIMARY KEY ("provider", "external_id")
);
"""

EVENT_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS "event_links" (
    "id"          SERIAL PRIMARY KEY,
    "evento_id"   INTEGER NOT NULL,
    "target_table" TEXT NOT NULL,
    "target_id"   INTEGER NOT NULL,
    "link_type"   TEXT NOT NULL,
    "match_field"  TEXT,
    "match_value"  TEXT,
    "confidence"   REAL DEFAULT 0.5,
    "created_at"   TEXT
);
"""

INDEXES_SQL = [
    'CREATE INDEX IF NOT EXISTS "idx_doc_type" ON "archivio_documenti"("doc_type");',
    'CREATE INDEX IF NOT EXISTS "idx_doc_year" ON "archivio_documenti"("year_start");',
    'CREATE INDEX IF NOT EXISTS "idx_doc_provider" ON "archivio_documenti"("provider");',
    'CREATE INDEX IF NOT EXISTS "idx_evlink_evento" ON "event_links"("evento_id");',
    'CREATE INDEX IF NOT EXISTS "idx_evlink_type" ON "event_links"("link_type");',
]


def create_supabase_schema():
    """Create tables and indexes on Supabase."""
    print("=" * 70)
    print("FASE 1: Creazione schema su Supabase")
    print("=" * 70)

    for name, ddl in [("archivio_documenti", ARCHIVIO_DOCS_DDL), ("event_links", EVENT_LINKS_DDL)]:
        print(f"  Creazione tabella {name}...", end=" ")
        r = execute_sql(ddl)
        if r.get("ok"):
            print("OK")
        else:
            print(f"ERRORE: {r.get('error', 'unknown')}")

    for idx_sql in INDEXES_SQL:
        r = execute_sql(idx_sql)
        if not r.get("ok"):
            print(f"  [WARN] Index: {r.get('error', 'unknown')}")

    print("  Schema creato.\n")


def sync_archivio_documenti(batch_size: int = 500):
    """Sync all rows from local archivio_documenti to Supabase."""
    print("=" * 70)
    print("FASE 2: Sync archivio_documenti → Supabase")
    print("=" * 70)

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM archivio_documenti").fetchone()[0]
    print(f"  Documenti locali: {total}")

    if total == 0:
        print("  [SKIP] Nessun documento da sincronizzare.")
        conn.close()
        return 0

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(archivio_documenti)").fetchall()]
    col_list = ", ".join(f'"{c}"' for c in cols)

    offset = 0
    synced = 0
    errors = 0

    while offset < total:
        rows = conn.execute(
            f'SELECT {col_list} FROM "archivio_documenti" LIMIT {batch_size} OFFSET {offset}'
        ).fetchall()

        if not rows:
            break

        batch = []
        for row in rows:
            record = {}
            for c in cols:
                val = row[c]
                if isinstance(val, bytes):
                    val = val.hex()
                record[c] = val
            batch.append(record)

        # Use insert_batch with merge to upsert
        r = insert_batch("archivio_documenti", batch, on_conflict="merge")
        if r.get("ok"):
            synced += r["count"]
            pct = (synced / total) * 100
            print(f"  {synced}/{total} ({pct:.0f}%)")
        else:
            errors += 1
            print(f"  [ERR] offset {offset}: {r.get('error', 'unknown')[:200]}")
            if errors > 10:
                print("  [ABORT] Troppi errori.")
                break

        offset += batch_size
        time.sleep(0.5)  # rate limit

    conn.close()
    print(f"  Sync completato: {synced} documenti, {errors} errori.\n")
    return synced


def sync_event_links(batch_size: int = 500):
    """Sync all rows from local event_links to Supabase.
    
    Kill switch: SYNC_EVENT_LINKS_SUPABASE=false in .env suspends this sync
    until linking v2 migration is complete.
    """
    # Kill switch check
    if os.getenv("SYNC_EVENT_LINKS_SUPABASE", "true").lower() == "false":
        print("=" * 70)
        print("FASE 3: Sync event_links → Supabase [SUSPENDED]")
        print("=" * 70)
        print("  [KILL SWITCH] SYNC_EVENT_LINKS_SUPABASE=false")
        print("  Legacy event_links sync suspended until linking v2 migration complete.")
        print("  Set SYNC_EVENT_LINKS_SUPABASE=true to re-enable.\n")
        return 0
    
    print("=" * 70)
    print("FASE 3: Sync event_links → Supabase")
    print("=" * 70)

    conn = sqlite3.connect(str(EDB), timeout=30)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
    print(f"  Link locali: {total}")

    if total == 0:
        print("  [SKIP] Nessun link da sincronizzare.")
        conn.close()
        return 0

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(event_links)").fetchall()]
    # Remove 'id' (auto-increment SERIAL on Supabase)
    if "id" in cols:
        cols.remove("id")
    col_list = ", ".join(f'"{c}"' for c in cols)

    offset = 0
    synced = 0
    errors = 0

    while offset < total:
        rows = conn.execute(
            f'SELECT {col_list} FROM "event_links" LIMIT {batch_size} OFFSET {offset}'
        ).fetchall()

        if not rows:
            break

        batch = []
        for row in rows:
            record = {}
            for c in cols:
                val = row[c]
                if isinstance(val, bytes):
                    val = val.hex()
                record[c] = val
            batch.append(record)

        # Use insert_batch with ignore (avoid duplicates)
        r = insert_batch("event_links", batch, on_conflict="ignore")
        if r.get("ok"):
            synced += r["count"]
            pct = (synced / total) * 100
            print(f"  {synced}/{total} ({pct:.0f}%)")
        else:
            errors += 1
            print(f"  [ERR] offset {offset}: {r.get('error', 'unknown')[:200]}")
            if errors > 10:
                print("  [ABORT] Troppi errori.")
                break

        offset += batch_size
        time.sleep(0.5)

    conn.close()
    print(f"  Sync completato: {synced} link, {errors} errori.\n")
    return synced


if __name__ == "__main__":
    create_supabase_schema()
    docs = sync_archivio_documenti()
    links = sync_event_links()

    print("=" * 70)
    print("RIEPILOGO SYNC SUPABASE")
    print("=" * 70)
    print(f"  Documenti sincronizzati: {docs}")
    print(f"  Event links sincronizzati: {links}")
