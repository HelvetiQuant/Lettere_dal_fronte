"""Apply V3 source authority schema migration to SQLite databases.

Idempotent: creates source_registry table and adds V3 columns to
record_links and event_links without deleting existing data.
"""
import sqlite3
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_authority_registry import (
    apply_source_registry_schema,
    migrate_record_links_schema,
    migrate_event_links_schema,
    SourceAuthorityRegistry,
    DEFAULT_SOURCES,
)


def main():
    db_main = Path(__file__).parent / "imi_internati.db"
    db_events = Path(__file__).parent / "eventi_1gm.db"

    # ─── Main DB: source_registry + record_links migration ──────────────
    print(f"=== Migrating main DB: {db_main} ===")
    conn = sqlite3.connect(str(db_main), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # 1. source_registry table
    print("\n[source_registry]")
    apply_source_registry_schema(conn)

    # 2. record_links V3 columns
    print("\n[record_links V3 columns]")
    try:
        migrate_record_links_schema(conn)
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            print("  record_links table does not exist yet — skipping column migration")
        else:
            raise

    # 3. Verify source_registry loaded
    registry = SourceAuthorityRegistry(conn)
    sources = registry.all_sources()
    print(f"\n  source_registry: {len(sources)} sources loaded")
    for s in sources:
        print(f"    {s.source_key:25s} tier={s.authority_tier} score={s.authority_score:.2f} official={s.is_official} provider={s.provider}")

    conn.close()

    # ─── Events DB: event_links migration ────────────────────────────────
    print(f"\n=== Migrating events DB: {db_events} ===")
    conn_ev = sqlite3.connect(str(db_events), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_ev.execute("PRAGMA journal_mode=WAL")

    # Also add source_registry to events DB
    print("\n[source_registry in events DB]")
    apply_source_registry_schema(conn_ev)

    # event_links V3 columns
    print("\n[event_links V3 columns]")
    try:
        migrate_event_links_schema(conn_ev)
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            print("  event_links table does not exist yet — skipping column migration")
        else:
            raise

    conn_ev.close()

    print("\n=== Migration complete ===")
    print("All changes are additive and idempotent. No existing data was deleted.")


if __name__ == "__main__":
    main()
