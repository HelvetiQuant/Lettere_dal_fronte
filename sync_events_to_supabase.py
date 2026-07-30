"""Sync eventi_1gm, event_aliases, and map_features to Supabase."""
import json
import os
import sqlite3
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
from supabase_client import execute_sql, insert_batch

EDB = Path(__file__).parent / "eventi_1gm.db"

# ─── DDL ──────────────────────────────────────────────────────────────────────

EVENTI_DDL = """
CREATE TABLE IF NOT EXISTS "eventi_1gm" (
    "id" SERIAL PRIMARY KEY,
    "nome" TEXT NOT NULL,
    "descrizione" TEXT,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "luogo" TEXT,
    "tipo" TEXT,
    "conflitto" TEXT DEFAULT 'WW1',
    "keywords" TEXT,
    "aliases" TEXT,
    "parent_event_id" INTEGER,
    "event_type" TEXT,
    "stable_id" TEXT,
    "conflict" TEXT DEFAULT 'ww1',
    "preferred_name" TEXT,
    "general_location" TEXT,
    "localities" TEXT,
    "subjects" TEXT,
    "units" TEXT,
    "temporal_precision" TEXT,
    "review_status" TEXT DEFAULT 'candidate',
    "narrative_version" TEXT,
    "narrative_updated_at" TEXT,
    "date_start" TEXT,
    "date_end" TEXT
);
"""

EVENT_ALIASES_DDL = """
CREATE TABLE IF NOT EXISTS "event_aliases" (
    "id" SERIAL PRIMARY KEY,
    "evento_id" INTEGER NOT NULL,
    "alias" TEXT NOT NULL,
    "alias_type" TEXT DEFAULT 'historical',
    "created_at" TEXT
);
"""

MAP_FEATURES_DDL = """
CREATE TABLE IF NOT EXISTS "map_features" (
    "id" TEXT PRIMARY KEY,
    "event_id" TEXT,
    "phase" TEXT,
    "feature_type" TEXT,
    "geojson" TEXT,
    "date_start" TEXT,
    "date_end" TEXT,
    "label" TEXT,
    "description" TEXT,
    "certainty" TEXT,
    "source_table" TEXT,
    "source_id" INTEGER,
    "source_url" TEXT,
    "review_status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "created_at" TEXT,
    "updated_at" TEXT
);
"""


def sync_table(ddl: str, table_name: str, db_path: Path, batch_size: int = 500):
    """Create table on Supabase and sync all rows from SQLite."""
    print(f"\n{'='*60}")
    print(f"Sync: {table_name}")
    print(f"{'='*60}")
    
    # Create table
    print(f"  Creating table...", end=" ")
    r = execute_sql(ddl)
    if r.get("ok") and (r.get("data") is None or r["data"].get("ok") is not False):
        print("OK")
    else:
        print(f"ERR: {r.get('data', r).get('error', 'unknown')[:100]}")
        return 0
    
    # Read from SQLite
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    
    # Get table info
    cols_info = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    if not cols_info:
        print(f"  [SKIP] Table {table_name} not found in SQLite")
        conn.close()
        return 0
    
    cols = [c["name"] for c in cols_info]
    col_list = ", ".join(f'"{c}"' for c in cols)
    
    total = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    print(f"  Rows: {total}")
    
    if total == 0:
        conn.close()
        return 0
    
    offset = 0
    synced = 0
    errors = 0
    
    while offset < total:
        rows = conn.execute(
            f'SELECT {col_list} FROM "{table_name}" LIMIT {batch_size} OFFSET {offset}'
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
        
        r = insert_batch(table_name, batch, on_conflict="ignore")
        if r.get("ok"):
            synced += r["count"]
            print(f"  {synced}/{total}")
        else:
            errors += 1
            print(f"  [ERR] offset {offset}: {r.get('error', 'unknown')[:150]}")
            if errors > 5:
                print("  [ABORT]")
                break
        
        offset += batch_size
        time.sleep(0.3)
    
    conn.close()
    print(f"  Done: {synced} synced, {errors} errors")
    return synced


if __name__ == "__main__":
    # Sync eventi_1gm
    sync_table(EVENTI_DDL, "eventi_1gm", EDB)
    
    # Sync event_aliases
    sync_table(EVENT_ALIASES_DDL, "event_aliases", EDB)
    
    # Sync map_features
    sync_table(MAP_FEATURES_DDL, "map_features", EDB)
    
    print(f"\n{'='*60}")
    print("Sync eventi completato.")
    print(f"{'='*60}")
