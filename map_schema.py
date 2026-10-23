"""Schema additivo per map features canoniche.

Persiste le feature geografiche generate dalla pipeline di mappa con
provenienza, stato di verifica e revisione.

Usage:
    python map_schema.py              # deploy (additive, safe)
    python map_schema.py --dry-run    # show what would be created
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

EDB = Path(__file__).parent / "eventi_1gm.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS map_features (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT '',
    feature_type TEXT NOT NULL,
    geojson TEXT NOT NULL,
    date_start TEXT,
    date_end TEXT,
    label TEXT NOT NULL,
    description TEXT,
    certainty TEXT NOT NULL DEFAULT 'verified',
    source_table TEXT,
    source_id INTEGER,
    source_url TEXT,
    review_status TEXT NOT NULL DEFAULT 'proposed',
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_map_features_event ON map_features(event_id);
CREATE INDEX IF NOT EXISTS idx_map_features_type ON map_features(feature_type);
CREATE INDEX IF NOT EXISTS idx_map_features_certainty ON map_features(certainty);
"""


def init_map_schema(conn=None) -> None:
    own = conn is None
    conn = conn or sqlite3.connect(str(EDB))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        if own:
            conn.close()


def map_schema_available(conn=None) -> bool:
    own = conn is None
    conn = conn or sqlite3.connect(str(EDB), uri=True)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='map_features'"
        ).fetchone()
        return bool(row)
    finally:
        if own:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Map features schema migration")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        conn = sqlite3.connect(str(EDB), uri=True)
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='map_features'"
        ).fetchone()
        conn.close()
        if exists:
            print("map_features table already exists.")
        else:
            print("Would create: map_features table + 3 indexes")
        return

    print("Deploying map features schema (additive, safe)...")
    init_map_schema()
    conn = sqlite3.connect(str(EDB), uri=True)
    if map_schema_available(conn):
        print("OK: map features schema deployed successfully.")
    else:
        print("ERROR: schema deployment failed verification.")
    conn.close()


if __name__ == "__main__":
    main()
