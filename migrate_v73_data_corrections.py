"""V7.3-FIX DB Migration: data_corrections table + Supabase parity check.

This migration is:
- Additive (no columns or tables dropped)
- Idempotent (can be run multiple times)
- Non-destructive (no data deleted)

Changes:
1. Create `data_corrections` table in imi_internati.db — persistent store
   for CorrectionEntry objects from v7_identity_model.CorrectionLedger.
   Raw data is never modified; corrections are stored as overlays.
2. Create `sync_parity_audit` table — tracks SQLite vs Supabase row counts
   for parity verification.
3. Add indexes on data_corrections for identity_id, field_name, verified.

Usage:
    python migrate_v73_data_corrections.py --dry-run   # Show what would change
    python migrate_v73_data_corrections.py --execute    # Apply changes
    python migrate_v73_data_corrections.py --parity     # Check Supabase parity
"""
from __future__ import annotations

import argparse
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"

MIGRATION_VERSION = "7.3.1"
MIGRATION_NAME = "data_corrections_and_parity"


# ─── SQL ────────────────────────────────────────────────────────────────────

CREATE_DATA_CORRECTIONS = """
CREATE TABLE IF NOT EXISTS data_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_id TEXT UNIQUE NOT NULL,
    target_identity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT NOT NULL,
    correction_source TEXT DEFAULT 'MANUAL',
    corrected_by TEXT,
    corrected_at TEXT NOT NULL,
    reason TEXT,
    confidence REAL DEFAULT 0.0,
    verified INTEGER DEFAULT 0,
    supersedes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEX_CORRECTIONS_IDENTITY = """
CREATE INDEX IF NOT EXISTS idx_data_corrections_identity
ON data_corrections(target_identity_id)
"""

CREATE_INDEX_CORRECTIONS_FIELD = """
CREATE INDEX IF NOT EXISTS idx_data_corrections_field
ON data_corrections(target_identity_id, field_name)
"""

CREATE_INDEX_CORRECTIONS_VERIFIED = """
CREATE INDEX IF NOT EXISTS idx_data_corrections_verified
ON data_corrections(verified)
"""

CREATE_SYNC_PARITY_AUDIT = """
CREATE TABLE IF NOT EXISTS sync_parity_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    sqlite_count INTEGER,
    supabase_count INTEGER,
    parity_ok INTEGER,
    checked_at TEXT NOT NULL,
    notes TEXT
)
"""


def apply_migration(db_path: Path, dry_run: bool = True) -> list:
    """Apply migration to a single DB. Returns list of actions taken."""
    conn = sqlite3.connect(str(db_path))
    actions = []

    statements = [
        ("CREATE_DATA_CORRECTIONS", CREATE_DATA_CORRECTIONS),
        ("CREATE_INDEX_CORRECTIONS_IDENTITY", CREATE_INDEX_CORRECTIONS_IDENTITY),
        ("CREATE_INDEX_CORRECTIONS_FIELD", CREATE_INDEX_CORRECTIONS_FIELD),
        ("CREATE_INDEX_CORRECTIONS_VERIFIED", CREATE_INDEX_CORRECTIONS_VERIFIED),
        ("CREATE_SYNC_PARITY_AUDIT", CREATE_SYNC_PARITY_AUDIT),
    ]

    for name, sql in statements:
        try:
            # Check if already exists
            if "CREATE TABLE" in sql:
                table_name = sql.split("IF NOT EXISTS")[1].split("(")[0].strip()
                existing = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                ).fetchone()
                if existing:
                    actions.append(f"[SKIP] {name}: table {table_name} already exists")
                    continue
            elif "CREATE INDEX" in sql:
                index_name = sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
                existing = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                    (index_name,)
                ).fetchone()
                if existing:
                    actions.append(f"[SKIP] {name}: index {index_name} already exists")
                    continue

            if not dry_run:
                conn.execute(sql)
                conn.commit()
            actions.append(f"[{'APPLIED' if not dry_run else 'DRY-RUN'}] {name}")
        except sqlite3.OperationalError as e:
            actions.append(f"[ERROR] {name}: {e}")

    conn.close()
    return actions


def check_supabase_parity(db_path: Path) -> list:
    """Check parity between SQLite and Supabase for key tables.

    Reads Supabase credentials from .env and queries row counts.
    Returns list of parity results.
    """
    results = []

    # Load .env for Supabase credentials
    env_path = Path(__file__).parent / ".env"
    sb_url = None
    sb_key = None

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("sb_publishable=") or line.startswith("SUPABASE_URL="):
                    sb_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("sb_secret=") or line.startswith("SUPABASE_ANON_KEY="):
                    sb_key = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not sb_url or not sb_key:
        results.append("[SKIP] Supabase credentials not found in .env — parity check skipped")
        return results

    # Tables to check
    parity_tables = [
        "archivio_documenti",
        "eventi_1gm",
        "event_aliases",
        "internati",
        "decorati_nastroazzurro",
        "caduti_albooro",
        "caduti_cwgc",
        "caduti_ministero",
    ]

    conn = sqlite3.connect(str(db_path))

    for table in parity_tables:
        try:
            # SQLite count
            sqlite_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            sqlite_count = -1
            results.append(f"[WARN] Table {table} not found in SQLite")

        # Supabase count (via REST API)
        try:
            import urllib.request
            import json as _json

            url = f"{sb_url}/rest/v1/{table}?select=count"
            req = urllib.request.Request(
                url,
                headers={
                    "apikey": sb_key,
                    "Authorization": f"Bearer {sb_key}",
                    "Range": "0-0",
                    "Prefer": "count=exact",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content_range = resp.headers.get("Content-Range", "")
                # Content-Range: 0-0/1234
                if "/" in content_range:
                    supabase_count = int(content_range.split("/")[-1])
                else:
                    supabase_count = -1

            parity_ok = 1 if sqlite_count == supabase_count else 0
            status = "OK" if parity_ok else "MISMATCH"

            results.append(
                f"[{status}] {table}: SQLite={sqlite_count}, Supabase={supabase_count}"
            )

            # Record in sync_parity_audit
            if sqlite_count >= 0 and supabase_count >= 0:
                try:
                    conn.execute(
                        "INSERT INTO sync_parity_audit (table_name, sqlite_count, supabase_count, parity_ok, checked_at, notes) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (table, sqlite_count, supabase_count, parity_ok,
                         datetime.now().isoformat(), f"V7.3.1 parity check")
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # table might not exist yet

        except Exception as e:
            results.append(f"[ERROR] {table}: Supabase query failed: {e}")

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="V7.3.1 DB migration: data_corrections + parity")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Show what would change (default)")
    parser.add_argument("--execute", action="store_true", default=False,
                        help="Apply changes to DB")
    parser.add_argument("--parity", action="store_true", default=False,
                        help="Check Supabase parity (requires .env credentials)")
    args = parser.parse_args()

    if args.execute:
        args.dry_run = False

    print(f"V7.3.1 Migration: {MIGRATION_NAME}")
    print(f"Mode: {'EXECUTE' if not args.dry_run else 'DRY-RUN'}")
    print("=" * 60)

    # Apply to main DB
    print(f"\n[imi_internati.db]")
    actions = apply_migration(DB_MAIN, dry_run=args.dry_run)
    for a in actions:
        print(f"  {a}")

    # Apply to events DB
    print(f"\n[eventi_1gm.db]")
    actions = apply_migration(DB_EVENTS, dry_run=args.dry_run)
    for a in actions:
        print(f"  {a}")

    # Parity check
    if args.parity:
        print(f"\n[Supabase Parity Check]")
        print("-" * 60)
        parity = check_supabase_parity(DB_MAIN)
        for p in parity:
            print(f"  {p}")

    print("\nDONE")


if __name__ == "__main__":
    main()
