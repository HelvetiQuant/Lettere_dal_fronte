"""Migration: person_source_matches table — additive, idempotent.

Creates the person_source_matches table for tracking deterministic
identity-resolved links between person records and sources.

Run: python migrate_person_source_matches.py [--dry-run]
"""
import os
import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "imi_internati.db"

MIGRATION_SQL = """
-- person_source_matches: deterministic identity-resolved links
CREATE TABLE IF NOT EXISTS person_source_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_table TEXT NOT NULL DEFAULT 'internati',
    person_id INTEGER NOT NULL,
    source_table TEXT NOT NULL DEFAULT '',
    source_id INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('confirmed','probable','ambiguous','rejected')),
    source_kind TEXT NOT NULL DEFAULT 'web',
    normalized_name TEXT NOT NULL DEFAULT '',
    matched_features_json TEXT DEFAULT '[]',
    conflicting_features_json TEXT DEFAULT '[]',
    reason_codes_json TEXT DEFAULT '[]',
    resolver_version TEXT NOT NULL DEFAULT '1.0.0',
    manually_reviewed INTEGER NOT NULL DEFAULT 0,
    reviewed_by TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    url TEXT DEFAULT '',
    title TEXT DEFAULT '',
    query_used TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(person_table, person_id, source_table, source_id)
);

-- Indexes for fast lookup
CREATE INDEX IF NOT EXISTS idx_psm_person ON person_source_matches(person_table, person_id);
CREATE INDEX IF NOT EXISTS idx_psm_source ON person_source_matches(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_psm_status ON person_source_matches(status);
CREATE INDEX IF NOT EXISTS idx_psm_version ON person_source_matches(resolver_version);
CREATE INDEX IF NOT EXISTS idx_psm_review ON person_source_matches(manually_reviewed) WHERE manually_reviewed = 0;
"""


def run(dry_run: bool = True):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Check if table exists
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='person_source_matches'"
    ).fetchone()

    if exists:
        print("person_source_matches already exists.")
        # Check columns
        cols = [c["name"] for c in conn.execute("PRAGMA table_info(person_source_matches)").fetchall()]
        print(f"  Columns: {cols}")
        conn.close()
        return

    if dry_run:
        print("[DRY-RUN] Would create person_source_matches table with:")
        print(MIGRATION_SQL)
        conn.close()
        return

    print("Creating person_source_matches table...")
    conn.executescript(MIGRATION_SQL)
    conn.commit()

    # Verify
    cols = [c["name"] for c in conn.execute("PRAGMA table_info(person_source_matches)").fetchall()]
    print(f"  Created with columns: {cols}")
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='person_source_matches'"
    ).fetchall()
    print(f"  Indexes: {[i['name'] for i in idx]}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "--execute" not in sys.argv
    run(dry_run=dry)
