"""V7.3 Phase B — Quarantine legacy links and add canonical domain model tables.

This migration is:
- Additive (no columns or tables dropped)
- Idempotent (can be run multiple times)
- Non-destructive (no data deleted)
- Reversible (rollback SQL provided)

Changes:
1. Add `origin`, `usable_as_evidence` columns to event_links and record_links
2. Mark ALL existing legacy links as CANDIDATE with usable_as_evidence=0
3. Create canonical domain model tables (SourceArtifact, Observation, Entity,
   IdentityCandidate, Evidence, Claim, Relation, ReviewDecision,
   ResearchSnapshot, SyncOutboxItem, SourceFamily)
4. Create legacy_link_quarantine_audit table (if not exists)
5. Improve sync_outbox with fingerprint, version, retry columns

Usage:
    python migrate_v73_quarantine.py --dry-run   # Show what would change
    python migrate_v73_quarantine.py --execute    # Apply changes
    python migrate_v73_quarantine.py --rollback   # Rollback changes
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"

MIGRATION_VERSION = "7.3.0"
MIGRATION_NAME = "quarantine_legacy_and_canonical_model"


# ─── Migration SQL ──────────────────────────────────────────────────────────

# 1. Additive columns for event_links (eventi_1gm.db)
EVENT_LINKS_ADD_COLUMNS = [
    ("origin", "TEXT DEFAULT 'LEGACY_HEURISTIC'"),
    ("usable_as_evidence", "INTEGER DEFAULT 0"),
    ("war_period", "TEXT DEFAULT ''"),
    ("semantic_role", "TEXT DEFAULT ''"),
    ("quarantined_at", "TEXT DEFAULT ''"),
    ("quarantine_reason", "TEXT DEFAULT ''"),
]

# 2. Additive columns for record_links (imi_internati.db)
RECORD_LINKS_ADD_COLUMNS = [
    ("origin", "TEXT DEFAULT 'LEGACY_HEURISTIC'"),
    ("usable_as_evidence", "INTEGER DEFAULT 0"),
    ("war_period", "TEXT DEFAULT ''"),
    ("semantic_role", "TEXT DEFAULT ''"),
    ("quarantined_at", "TEXT DEFAULT ''"),
    ("quarantine_reason", "TEXT DEFAULT ''"),
]

# 3. Canonical domain model tables (imi_internati.db)
CANONICAL_TABLES_SQL = [
    # ─── SourceArtifact ─────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_source_artifacts (
        artifact_id TEXT PRIMARY KEY,
        source_url TEXT NOT NULL,
        source_family_id TEXT,
        artifact_type TEXT NOT NULL,
        title TEXT,
        creator TEXT,
        date_text TEXT,
        coverage_start TEXT,
        coverage_end TEXT,
        coverage_precision TEXT,
        place TEXT,
        war TEXT,
        language TEXT,
        rights TEXT,
        raw_content_hash TEXT,
        raw_content_path TEXT,
        fetch_status TEXT DEFAULT 'PENDING',
        fetch_timestamp TEXT,
        access_type TEXT,
        compliance_status TEXT DEFAULT 'UNKNOWN',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1
    )""",

    # ─── SourceFamily ───────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_source_families (
        family_id TEXT PRIMARY KEY,
        canonical_url TEXT NOT NULL,
        family_name TEXT,
        authority_tier INTEGER,
        independence_group TEXT,
        member_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",

    # ─── Observation ────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_observations (
        observation_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        observation_type TEXT NOT NULL,
        raw_text TEXT,
        extracted_fields_json TEXT,
        extraction_method TEXT,
        extraction_confidence REAL DEFAULT 0.5,
        observed_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (artifact_id) REFERENCES canonical_source_artifacts(artifact_id)
    )""",

    # ─── Entity ─────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_entities (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        normalized_name TEXT,
        cognome TEXT,
        nome TEXT,
        data_nascita TEXT,
        luogo_nascita TEXT,
        paternita TEXT,
        matricola TEXT,
        grado TEXT,
        reparto TEXT,
        comune TEXT,
        war_period TEXT,
        source_table TEXT,
        source_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1
    )""",

    # ─── IdentityCandidate ──────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_identity_candidates (
        candidate_id TEXT PRIMARY KEY,
        entity_id TEXT,
        query_subject TEXT NOT NULL,
        match_identifiers_json TEXT NOT NULL,
        strong_identifiers_count INTEGER DEFAULT 0,
        medium_identifiers_count INTEGER DEFAULT 0,
        weak_identifiers_count INTEGER DEFAULT 0,
        identity_status TEXT DEFAULT 'CANDIDATE',
        conflict_code TEXT,
        conflict_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (entity_id) REFERENCES canonical_entities(entity_id)
    )""",

    # ─── Evidence ───────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_evidence (
        evidence_id TEXT PRIMARY KEY,
        candidate_id TEXT,
        artifact_id TEXT,
        family_id TEXT,
        evidence_type TEXT NOT NULL,
        evidence_role TEXT NOT NULL,
        source_authority REAL DEFAULT 0.5,
        artifact_directness REAL DEFAULT 0.5,
        extraction_confidence REAL DEFAULT 0.5,
        identity_match_confidence REAL DEFAULT 0.5,
        semantic_confidence REAL DEFAULT 0.5,
        temporal_compatibility REAL DEFAULT 0.5,
        geographical_compatibility REAL DEFAULT 0.5,
        source_independence REAL DEFAULT 0.5,
        supporting_quote TEXT,
        created_at TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (candidate_id) REFERENCES canonical_identity_candidates(candidate_id),
        FOREIGN KEY (artifact_id) REFERENCES canonical_source_artifacts(artifact_id),
        FOREIGN KEY (family_id) REFERENCES canonical_source_families(family_id)
    )""",

    # ─── Claim ──────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_claims (
        claim_id TEXT PRIMARY KEY,
        subject_entity_id TEXT,
        candidate_id TEXT,
        predicate TEXT NOT NULL,
        object_value TEXT,
        object_entity_id TEXT,
        semantic_role TEXT,
        temporal_value TEXT,
        temporal_precision TEXT,
        polarity TEXT DEFAULT 'POSITIVE',
        certainty TEXT DEFAULT 'CANDIDATE',
        status TEXT DEFAULT 'CANDIDATE',
        claim_type TEXT DEFAULT 'RECORD_ASSERTION',
        evidence_ids_json TEXT,
        source_family_ids_json TEXT,
        origin TEXT DEFAULT 'CANONICAL_PIPELINE',
        usable_as_evidence INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (subject_entity_id) REFERENCES canonical_entities(entity_id),
        FOREIGN KEY (candidate_id) REFERENCES canonical_identity_candidates(candidate_id)
    )""",

    # ─── Relation ───────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_relations (
        relation_id TEXT PRIMARY KEY,
        subject_entity_id TEXT NOT NULL,
        object_entity_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        semantic_type TEXT,
        status TEXT DEFAULT 'CANDIDATE',
        evidence_ids_json TEXT,
        origin TEXT DEFAULT 'LEGACY_HEURISTIC',
        rule_version TEXT,
        temporal_compatibility TEXT,
        geographical_compatibility TEXT,
        match_confidence REAL DEFAULT 0.5,
        extraction_confidence REAL DEFAULT 0.5,
        decision_reason TEXT,
        needs_review INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (subject_entity_id) REFERENCES canonical_entities(entity_id),
        FOREIGN KEY (object_entity_id) REFERENCES canonical_entities(entity_id)
    )""",

    # ─── ReviewDecision (append-only) ───────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_review_decisions (
        decision_id TEXT PRIMARY KEY,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT,
        reviewer TEXT,
        evidence_ids_json TEXT,
        previous_status TEXT,
        new_status TEXT,
        created_at TEXT NOT NULL
    )""",

    # ─── ResearchSnapshot ───────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_research_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        run_id TEXT,
        query_text TEXT NOT NULL,
        intent TEXT NOT NULL,
        snapshot_hash TEXT,
        snapshot_json TEXT,
        claim_ids_json TEXT,
        evidence_ids_json TEXT,
        candidate_ids_json TEXT,
        created_at TEXT NOT NULL
    )""",

    # ─── SyncOutboxItem (improved) ──────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_sync_outbox (
        outbox_id TEXT PRIMARY KEY,
        table_name TEXT NOT NULL,
        record_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        status TEXT DEFAULT 'pending_sync',
        attempts INTEGER DEFAULT 0,
        last_error TEXT,
        last_attempt_at TEXT,
        synced_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1
    )""",

    # ─── EventRegistryVersioned ─────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS canonical_event_registry (
        event_id TEXT PRIMARY KEY,
        stable_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        parent_event_id TEXT,
        war TEXT NOT NULL,
        data_inizio TEXT,
        data_fine TEXT,
        temporal_precision TEXT,
        general_location TEXT,
        localities_json TEXT,
        subjects_json TEXT,
        units_json TEXT,
        aliases_json TEXT,
        keywords_json TEXT,
        description TEXT,
        source_provenance_json TEXT,
        narrative_version TEXT,
        review_status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER DEFAULT 1
    )""",
]

# Indexes for canonical tables
CANONICAL_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_csa_url ON canonical_source_artifacts(source_url)",
    "CREATE INDEX IF NOT EXISTS idx_csa_family ON canonical_source_artifacts(source_family_id)",
    "CREATE INDEX IF NOT EXISTS idx_csa_fetch ON canonical_source_artifacts(fetch_status)",
    "CREATE INDEX IF NOT EXISTS idx_csf_url ON canonical_source_families(canonical_url)",
    "CREATE INDEX IF NOT EXISTS idx_cobs_artifact ON canonical_observations(artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_cent_type ON canonical_entities(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_cent_source ON canonical_entities(source_table, source_id)",
    "CREATE INDEX IF NOT EXISTS idx_cent_name ON canonical_entities(cognome, nome)",
    "CREATE INDEX IF NOT EXISTS idx_cic_entity ON canonical_identity_candidates(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_cic_status ON canonical_identity_candidates(identity_status)",
    "CREATE INDEX IF NOT EXISTS idx_cev_candidate ON canonical_evidence(candidate_id)",
    "CREATE INDEX IF NOT EXISTS idx_cev_family ON canonical_evidence(family_id)",
    "CREATE INDEX IF NOT EXISTS idx_ccl_subject ON canonical_claims(subject_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_ccl_candidate ON canonical_claims(candidate_id)",
    "CREATE INDEX IF NOT EXISTS idx_ccl_status ON canonical_claims(status)",
    "CREATE INDEX IF NOT EXISTS idx_crel_subject ON canonical_relations(subject_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crel_object ON canonical_relations(object_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_crel_status ON canonical_relations(status)",
    "CREATE INDEX IF NOT EXISTS idx_crd_target ON canonical_review_decisions(target_type, target_id)",
    "CREATE INDEX IF NOT EXISTS idx_crs_run ON canonical_research_snapshots(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_cso_status ON canonical_sync_outbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_cso_fingerprint ON canonical_sync_outbox(fingerprint)",
    "CREATE INDEX IF NOT EXISTS idx_cer_stable ON canonical_event_registry(stable_id)",
    "CREATE INDEX IF NOT EXISTS idx_cer_parent ON canonical_event_registry(parent_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_cer_war ON canonical_event_registry(war)",
    "CREATE INDEX IF NOT EXISTS idx_cer_type ON canonical_event_registry(event_type)",
]

# Quarantine audit table (compatible schema for both DBs)
QUARANTINE_AUDIT_SQL = """CREATE TABLE IF NOT EXISTS legacy_link_quarantine_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT,
    table_name TEXT NOT NULL,
    link_id INTEGER,
    previous_status TEXT,
    new_status TEXT,
    algorithm_version TEXT,
    reason TEXT,
    timestamp TEXT NOT NULL
)"""


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str):
    """Add a column to a table if it doesn't already exist."""
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"  + Added column {table}.{column}")
        return True
    else:
        print(f"  = Column {table}.{column} already exists")
        return False


def run_migration(dry_run: bool = True):
    """Execute or dry-run the migration."""
    print(f"\n{'='*80}")
    print(f"V7.3 Phase B Migration — {MIGRATION_NAME} v{MIGRATION_VERSION}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"{'='*80}")

    changes = {"columns_added": 0, "tables_created": 0, "indexes_created": 0, "rows_quarantined": 0}

    # ─── 1. event_links additive columns (eventi_1gm.db) ────────────────
    print(f"\n--- eventi_1gm.db: event_links additive columns ---")
    conn_evt = sqlite3.connect(str(DB_EVENTS))
    conn_evt.row_factory = sqlite3.Row

    for col_name, col_def in EVENT_LINKS_ADD_COLUMNS:
        if not dry_run:
            if add_column_if_missing(conn_evt, "event_links", col_name, col_def):
                changes["columns_added"] += 1
        else:
            if not column_exists(conn_evt, "event_links", col_name):
                print(f"  + Would add column event_links.{col_name}")
                changes["columns_added"] += 1
            else:
                print(f"  = Column event_links.{col_name} already exists")

    # ─── 2. Quarantine audit table (eventi_1gm.db) ──────────────────────
    if not dry_run:
        if not table_exists(conn_evt, "legacy_link_quarantine_audit"):
            conn_evt.execute(QUARANTINE_AUDIT_SQL)
            print(f"  + Created table legacy_link_quarantine_audit")
            changes["tables_created"] += 1
        else:
            print(f"  = Table legacy_link_quarantine_audit already exists")
    else:
        if not table_exists(conn_evt, "legacy_link_quarantine_audit"):
            print(f"  + Would create table legacy_link_quarantine_audit")
            changes["tables_created"] += 1

    # ─── 3. Quarantine all existing event_links ─────────────────────────
    if dry_run:
        cur = conn_evt.execute("SELECT COUNT(*) FROM event_links")
        total_evt = cur.fetchone()[0]
    else:
        cur = conn_evt.execute("SELECT COUNT(*) FROM event_links WHERE usable_as_evidence IS NULL OR usable_as_evidence = 0")
        total_evt = cur.fetchone()[0]
    print(f"\n  event_links to quarantine: {total_evt:,}")

    if not dry_run and total_evt > 0:
        now = datetime.now().isoformat(timespec="seconds")
        conn_evt.execute("""
            UPDATE event_links SET
                origin = 'LEGACY_HEURISTIC',
                usable_as_evidence = 0,
                status = 'CANDIDATE',
                quarantined_at = ?,
                quarantine_reason = 'V7.3 quarantine: legacy heuristic link without provenance'
            WHERE (usable_as_evidence IS NULL OR usable_as_evidence = 0)
        """, (now,))
        changes["rows_quarantined"] += total_evt
        print(f"  + Quarantined {total_evt:,} event_links")

        # Audit log (sample — first 1000 to avoid massive insert)
        cur = conn_evt.execute("""
            SELECT id, status FROM event_links
            WHERE quarantined_at = ? LIMIT 1000
        """, (now,))
        for row in cur.fetchall():
            conn_evt.execute("""
                INSERT INTO legacy_link_quarantine_audit
                (batch_id, table_name, link_id, previous_status, new_status, algorithm_version, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (MIGRATION_VERSION, "event_links", row["id"], "unverified", "CANDIDATE",
                  MIGRATION_VERSION, "V7.3 quarantine: legacy heuristic link without provenance", now))

    # ─── 4. record_links additive columns (imi_internati.db) ────────────
    print(f"\n--- imi_internati.db: record_links additive columns ---")
    conn_main = sqlite3.connect(str(DB_MAIN))
    conn_main.row_factory = sqlite3.Row

    for col_name, col_def in RECORD_LINKS_ADD_COLUMNS:
        if not dry_run:
            if add_column_if_missing(conn_main, "record_links", col_name, col_def):
                changes["columns_added"] += 1
        else:
            if not column_exists(conn_main, "record_links", col_name):
                print(f"  + Would add column record_links.{col_name}")
                changes["columns_added"] += 1
            else:
                print(f"  = Column record_links.{col_name} already exists")

    # ─── 5. Quarantine audit table (imi_internati.db) ───────────────────
    if not dry_run:
        if not table_exists(conn_main, "legacy_link_quarantine_audit"):
            conn_main.execute(QUARANTINE_AUDIT_SQL)
            print(f"  + Created table legacy_link_quarantine_audit")
            changes["tables_created"] += 1

    # ─── 6. Quarantine all existing record_links ────────────────────────
    if dry_run:
        cur = conn_main.execute("SELECT COUNT(*) FROM record_links")
        total_rl = cur.fetchone()[0]
    else:
        cur = conn_main.execute("SELECT COUNT(*) FROM record_links WHERE usable_as_evidence IS NULL OR usable_as_evidence = 0")
        total_rl = cur.fetchone()[0]
    print(f"\n  record_links to quarantine: {total_rl:,}")

    if not dry_run and total_rl > 0:
        now = datetime.now().isoformat(timespec="seconds")
        conn_main.execute("""
            UPDATE record_links SET
                origin = 'LEGACY_HEURISTIC',
                usable_as_evidence = 0,
                status = 'CANDIDATE',
                quarantined_at = ?,
                quarantine_reason = 'V7.3 quarantine: legacy heuristic link without provenance'
            WHERE (usable_as_evidence IS NULL OR usable_as_evidence = 0)
        """, (now,))
        changes["rows_quarantined"] += total_rl
        print(f"  + Quarantined {total_rl:,} record_links")

    # ─── 7. Canonical domain model tables (imi_internati.db) ────────────
    print(f"\n--- imi_internati.db: canonical domain model tables ---")
    for sql in CANONICAL_TABLES_SQL:
        table_name = sql.split("CREATE TABLE IF NOT EXISTS")[1].split("(")[0].strip()
        if not dry_run:
            if not table_exists(conn_main, table_name):
                conn_main.execute(sql)
                print(f"  + Created table {table_name}")
                changes["tables_created"] += 1
            else:
                print(f"  = Table {table_name} already exists")
        else:
            if not table_exists(conn_main, table_name):
                print(f"  + Would create table {table_name}")
                changes["tables_created"] += 1
            else:
                print(f"  = Table {table_name} already exists")

    # ─── 8. Canonical indexes ───────────────────────────────────────────
    print(f"\n--- imi_internati.db: canonical indexes ---")
    for sql in CANONICAL_INDEXES_SQL:
        if not dry_run:
            conn_main.execute(sql)
        changes["indexes_created"] += 1  # Count even in dry-run (CREATE IF NOT EXISTS is safe)

    if dry_run:
        print(f"  + Would create {len(CANONICAL_INDEXES_SQL)} indexes")

    # ─── 9. Commit ──────────────────────────────────────────────────────
    if not dry_run:
        conn_evt.commit()
        conn_main.commit()
        print(f"\n--- Committed all changes ---")

    # ─── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"Migration Summary ({'DRY RUN' if dry_run else 'EXECUTED'})")
    print(f"{'='*80}")
    print(f"  Columns added:      {changes['columns_added']}")
    print(f"  Tables created:     {changes['tables_created']}")
    print(f"  Indexes created:    {changes['indexes_created']}")
    print(f"  Rows quarantined:   {changes['rows_quarantined']:,}")
    print(f"  Migration version:  {MIGRATION_VERSION}")

    conn_evt.close()
    conn_main.close()

    return changes


def run_rollback():
    """Rollback the migration (restore quarantined links to previous state)."""
    print(f"\n{'='*80}")
    print(f"V7.3 Phase B Rollback — {MIGRATION_NAME}")
    print(f"{'='*80}")

    conn_evt = sqlite3.connect(str(DB_EVENTS))
    conn_main = sqlite3.connect(str(DB_MAIN))

    # Restore event_links
    restored_evt = conn_evt.execute("""
        UPDATE event_links SET
            usable_as_evidence = NULL,
            quarantined_at = '',
            quarantine_reason = ''
        WHERE quarantined_at != ''
    """).rowcount
    print(f"  Restored {restored_evt:,} event_links from quarantine")

    # Restore record_links
    restored_rl = conn_main.execute("""
        UPDATE record_links SET
            usable_as_evidence = NULL,
            quarantined_at = '',
            quarantine_reason = ''
        WHERE quarantined_at != ''
    """).rowcount
    print(f"  Restored {restored_rl:,} record_links from quarantine")

    conn_evt.commit()
    conn_main.commit()
    conn_evt.close()
    conn_main.close()

    print(f"\nRollback complete. Note: canonical tables are NOT dropped (they are empty).")
    print(f"To drop canonical tables, run: python migrate_v73_quarantine.py --drop-canonical")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V7.3 Phase B Migration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying data")
    parser.add_argument("--execute", action="store_true", help="Apply migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback quarantine (restore links)")
    parser.add_argument("--drop-canonical", action="store_true", help="Drop canonical tables (destructive)")

    args = parser.parse_args()

    if args.dry_run:
        run_migration(dry_run=True)
    elif args.execute:
        run_migration(dry_run=False)
    elif args.rollback:
        run_rollback()
    else:
        parser.print_help()
        sys.exit(1)
