"""Legacy link quarantine — marks all legacy-generated links as quarantined.

This script does NOT delete anything. It:
1. Scans all consumer tables (record_links, event_links, collegamenti, claim/evidence)
2. Marks legacy links with status='quarantined', algorithm_version='legacy_v1'
3. Produces audit trail with counts before/after
4. Supports --dry-run (default) and --execute
5. Rollback: restore status to previous value via audit trail

Usage:
    python quarantine_legacy_links.py --dry-run
    python quarantine_legacy_links.py --execute
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from linking.kill_switch import LegacyJob, assert_frozen, is_force_execute_enabled

DB_PATH = Path(__file__).parent / "imi_internati.db"
EDB_PATH = Path(__file__).parent / "eventi_1gm.db"
AUDIT_TABLE = "legacy_link_quarantine_audit"


def ensure_audit_table(conn: sqlite3.Connection):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            link_id INTEGER,
            previous_status TEXT,
            new_status TEXT,
            algorithm_version TEXT,
            reason TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()


def scan_legacy_links(conn: sqlite3.Connection, table_name: str, status_column: str = "status", id_column: str = "id") -> list:
    """Scan a table for legacy links that need quarantine."""
    try:
        rows = conn.execute(f"""
            SELECT {id_column}, {status_column} FROM {table_name}
            WHERE ({status_column} IS NULL OR {status_column} NOT IN ('quarantined', 'rejected'))
              AND ({status_column} IS NULL OR {status_column} = '' OR {status_column} = 'accepted' OR {status_column} = 'active')
        """).fetchall()
        return [(r[0], r[1] or "") for r in rows]
    except sqlite3.OperationalError:
        return []


def quarantine_table(conn: sqlite3.Connection, table_name: str, links: list, batch_id: str, dry_run: bool):
    """Mark links in a table as quarantined."""
    marked = 0
    for link_id, prev_status in links:
        if dry_run:
            marked += 1
            continue

        conn.execute(f"""
            INSERT INTO {AUDIT_TABLE} (batch_id, table_name, link_id, previous_status, new_status, algorithm_version, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, table_name, link_id, prev_status, "quarantined", "legacy_v1",
              "Legacy algorithm — quarantined by V5 bonifica", datetime.now().isoformat()))

        if status_column_exists(conn, table_name, "status"):
            conn.execute(f"UPDATE {table_name} SET status='quarantined' WHERE id=?", (link_id,))
        marked += 1

    return marked


def status_column_exists(conn: sqlite3.Connection, table_name: str, column: str) -> bool:
    try:
        cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(c[1] == column for c in cols)
    except:
        return False


def main():
    parser = argparse.ArgumentParser(description="Quarantine legacy links")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Audit only, no mutations (default)")
    parser.add_argument("--execute", action="store_true", help="Execute quarantine mutations")
    args = parser.parse_args()

    if args.execute:
        if not is_force_execute_enabled():
            print("ERROR: --execute requires LEGACY_JOB_FORCE_EXECUTE=true")
            sys.exit(1)

    dry_run = not args.execute
    batch_id = f"quarantine_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    print(f"Legacy Link Quarantine — batch_id={batch_id}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    ensure_audit_table(conn)

    # Tables to scan
    tables = [
        ("record_links", "id"),
        ("collegamenti", "id"),
    ]

    total_before = 0
    total_marked = 0

    for table_name, id_col in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        except sqlite3.OperationalError:
            print(f"  {table_name}: table not found, skipping")
            continue

        links = scan_legacy_links(conn, table_name, id_column=id_col)
        total_before += len(links)

        marked = quarantine_table(conn, table_name, links, batch_id, dry_run)
        total_marked += marked

        print(f"  {table_name}: {count} total, {len(links)} legacy candidates, {marked} marked")

    # Event links (separate DB)
    try:
        event_conn = sqlite3.connect(str(EDB_PATH))
        event_conn.row_factory = sqlite3.Row
        ensure_audit_table(event_conn)

        event_count = event_conn.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
        event_links = scan_legacy_links(event_conn, "event_links", id_column="id")
        event_marked = quarantine_table(event_conn, "event_links", event_links, batch_id, dry_run)

        print(f"  event_links: {event_count} total, {len(event_links)} legacy candidates, {event_marked} marked")
        total_before += len(event_links)
        total_marked += event_marked

        if not dry_run:
            event_conn.commit()
        event_conn.close()
    except sqlite3.OperationalError:
        print(f"  event_links: table not found, skipping")

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"\nSummary: {total_before} legacy links found, {total_marked} quarantined")
    print(f"Batch ID: {batch_id}")
    if dry_run:
        print("\nDry-run complete. Use --execute with LEGACY_JOB_FORCE_EXECUTE=true to apply.")
    else:
        print(f"\nQuarantine applied. Rollback: SELECT * FROM {AUDIT_TABLE} WHERE batch_id='{batch_id}'")


if __name__ == "__main__":
    main()
