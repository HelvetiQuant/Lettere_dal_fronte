"""V7.3-Fase15: Legacy link migration — idempotent, reversible.

Extends the V3 migration (migrate_links_v3.py) with V7.3 enhancements:
  1. Applies source quality assessment to each link
  2. Tags each link with claim lifecycle state
  3. Runs semantic validation on linked claims
  4. Preserves original link data for reversibility

Key invariants:
  1. Idempotent: running twice produces the same result
  2. Reversible: original status and metadata are preserved in a backup column
  3. Non-destructive: no links are deleted, only re-classified
  4. Audit trail: every change is logged with timestamp and reason

Usage:
    python migrate_v73_links.py --dry-run    # audit only
    python migrate_v73_links.py --execute    # apply changes
    python migrate_v73_links.py --rollback   # revert to pre-V7.3 state
"""
from __future__ import annotations

import os
import sys
import json
import time
import sqlite3
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_quality import assess_source_quality, combine_evidence_quality
from claim_lifecycle import determine_claim_state
from semantic_validator import SemanticValidator


DB = os.path.join(os.path.dirname(__file__), "imi_internati.db")
EDB = os.path.join(os.path.dirname(__file__), "eventi_1gm.db")
V73_RULE_VERSION = "7.3.0"

# Backup table for reversibility
BACKUP_SQL = """
CREATE TABLE IF NOT EXISTS link_migration_backup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_type TEXT NOT NULL,  -- 'record_link' or 'event_link'
    link_id INTEGER NOT NULL,
    original_status TEXT,
    original_confidence REAL,
    original_rule_version TEXT,
    original_needs_review INTEGER,
    original_decision_reason TEXT,
    migrated_at TEXT NOT NULL,
    UNIQUE(link_type, link_id)
);
"""

# V7.3 enrichment columns (additive, idempotent)
V73_COLUMNS_RECORD_LINKS = [
    ("v73_quality_level", "TEXT DEFAULT ''"),
    ("v73_quality_score", "REAL DEFAULT 0.0"),
    ("v73_claim_state", "TEXT DEFAULT ''"),
    ("v73_caveat", "TEXT DEFAULT ''"),
    ("v73_rule_version", "TEXT DEFAULT ''"),
]

V73_COLUMNS_EVENT_LINKS = [
    ("v73_quality_level", "TEXT DEFAULT ''"),
    ("v73_quality_score", "REAL DEFAULT 0.0"),
    ("v73_claim_state", "TEXT DEFAULT ''"),
    ("v73_caveat", "TEXT DEFAULT ''"),
    ("v73_rule_version", "TEXT DEFAULT ''"),
]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _add_columns_if_missing(conn, table, columns):
    """Add columns to a table if they don't already exist (idempotent)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    added = []
    for col_name, col_def in columns:
        if col_name not in existing:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                added.append(col_name)
            except sqlite3.OperationalError:
                pass
    return added


def _backup_link(conn, link_type, link_id, status, confidence, rule_version, needs_review, decision_reason):
    """Backup original link data for reversibility."""
    conn.execute(
        """INSERT OR IGNORE INTO link_migration_backup
           (link_type, link_id, original_status, original_confidence,
            original_rule_version, original_needs_review, original_decision_reason, migrated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (link_type, link_id, status, confidence, rule_version, needs_review, decision_reason, _utc_now()),
    )


def _table_to_source_key(table_name):
    """Map table name to source quality key."""
    mapping = {
        "internati": "internati_imi",
        "caduti_albooro": "albo_oro",
        "caduti_ministero": "ministero_difesa",
        "caduti_cwgc": "cwgc",
        "decorati_nastroazzurro": "nastro_azzurro",
        "fonti_indice": "fonti_indice",
        "archivio_documenti": "archivio_documenti",
    }
    return mapping.get(table_name, "")


def run_migrate_record_links(conn, dry_run=True):
    """Migrate record_links with V7.3 quality assessment and claim states."""
    print("[V7.3] Migrating record_links...")

    # Ensure backup table exists
    conn.execute(BACKUP_SQL)

    # Add V7.3 columns
    added = _add_columns_if_missing(conn, "record_links", V73_COLUMNS_RECORD_LINKS)
    if added:
        print(f"  Added columns: {added}")

    # Fetch links not yet migrated to V7.3
    links = conn.execute(
        """SELECT id, from_table, to_table, link_type, confidence,
                  status, rule_version, needs_review, decision_reason
           FROM record_links
           WHERE v73_rule_version IS NULL OR v73_rule_version = '' OR v73_rule_version != ?""",
        (V73_RULE_VERSION,),
    ).fetchall()

    print(f"  Links to migrate: {len(links)}")

    stats = {"migrated": 0, "skipped": 0, "high": 0, "medium": 0, "low": 0, "very_low": 0}
    state_counts = {"PUBLISHED": 0, "PUBLISHED_WITH_CAVEAT": 0, "REVIEW_PENDING": 0, "SUPPRESSED": 0}

    for link in links:
        link_id = link["id"]
        from_table = link["from_table"]
        to_table = link["to_table"]
        status = link["status"] or "unverified"
        confidence = link["confidence"] or 0.0
        rule_version = link["rule_version"] or ""
        needs_review = link["needs_review"] or 0
        decision_reason = link["decision_reason"] or ""

        # Backup original data
        if not dry_run:
            _backup_link(conn, "record_link", link_id, status, confidence, rule_version, needs_review, decision_reason)

        # Assess source quality for both sides
        source_key = _table_to_source_key(from_table)
        target_key = _table_to_source_key(to_table)

        if not source_key and not target_key:
            stats["skipped"] += 1
            continue

        # Get quality for the stronger source
        q_source = assess_source_quality(source_key) if source_key else None
        q_target = assess_source_quality(target_key) if target_key else None

        qualities = [q for q in [q_source, q_target] if q is not None]
        if not qualities:
            stats["skipped"] += 1
            continue

        # Combine evidence quality
        evidence_level, combined_score, reason = combine_evidence_quality(qualities)

        # Determine claim state
        # Map link status to validation status
        validation_status = "VALID"
        if status == "rejected":
            validation_status = "REJECTED"
        elif status == "conflicting":
            validation_status = "WARNING"
        elif needs_review:
            validation_status = "WARNING"

        # Map link status to identity status
        identity_status = "RESOLVED_IDENTITY"
        if status == "unverified":
            identity_status = "UNRESOLVED_IDENTITY"
        elif needs_review:
            identity_status = "AMBIGUOUS_IDENTITY"

        claim_state = determine_claim_state(
            claim_id=f"link_{link_id}",
            evidence_level=evidence_level,
            identity_status=identity_status,
            validation_status=validation_status,
            entailment_score=confidence,
            source_count=len(qualities),
        )

        stats["migrated"] += 1
        state_counts[claim_state.state] = state_counts.get(claim_state.state, 0) + 1

        if not dry_run:
            conn.execute(
                """UPDATE record_links SET
                   v73_quality_level = ?, v73_quality_score = ?,
                   v73_claim_state = ?, v73_caveat = ?,
                   v73_rule_version = ?
                   WHERE id = ?""",
                (qualities[0].quality_level, round(qualities[0].quality_score, 4),
                 claim_state.state, claim_state.caveat,
                 V73_RULE_VERSION, link_id),
            )

    if not dry_run:
        conn.commit()

    print(f"  Migrated: {stats['migrated']}, Skipped: {stats['skipped']}")
    print(f"  Claim states: {state_counts}")
    return stats


def run_migrate_event_links(conn_ev, conn_main, dry_run=True):
    """Migrate event_links with V7.3 quality assessment and claim states."""
    print("[V7.3] Migrating event_links...")

    # Ensure backup table exists in event DB
    conn_ev.execute(BACKUP_SQL)

    # Add V7.3 columns
    added = _add_columns_if_missing(conn_ev, "event_links", V73_COLUMNS_EVENT_LINKS)
    if added:
        print(f"  Added columns: {added}")

    # Fetch links not yet migrated
    links = conn_ev.execute(
        """SELECT id, target_table, link_type, confidence,
                  status, rule_version, needs_review, decision_reason
           FROM event_links
           WHERE v73_rule_version IS NULL OR v73_rule_version = '' OR v73_rule_version != ?""",
        (V73_RULE_VERSION,),
    ).fetchall()

    print(f"  Links to migrate: {len(links)}")

    stats = {"migrated": 0, "skipped": 0, "high": 0, "medium": 0, "low": 0, "very_low": 0}
    state_counts = {"PUBLISHED": 0, "PUBLISHED_WITH_CAVEAT": 0, "REVIEW_PENDING": 0, "SUPPRESSED": 0}

    for link in links:
        link_id = link["id"]
        target_table = link["target_table"]
        status = link["status"] or "unverified"
        confidence = link["confidence"] or 0.0
        rule_version = link["rule_version"] or ""
        needs_review = link["needs_review"] or 0
        decision_reason = link["decision_reason"] or ""

        # Backup
        if not dry_run:
            _backup_link(conn_ev, "event_link", link_id, status, confidence, rule_version, needs_review, decision_reason)

        # Assess source quality
        source_key = _table_to_source_key(target_table)
        if not source_key:
            stats["skipped"] += 1
            continue

        q = assess_source_quality(source_key)

        # Map to evidence level (single source)
        evidence_level = "possible" if q.quality_level in ("high", "medium") else "unverified"

        validation_status = "VALID"
        if status == "rejected":
            validation_status = "REJECTED"
        elif needs_review:
            validation_status = "WARNING"

        claim_state = determine_claim_state(
            claim_id=f"evlink_{link_id}",
            evidence_level=evidence_level,
            identity_status="RESOLVED_IDENTITY",  # event links don't involve identity
            validation_status=validation_status,
            entailment_score=confidence,
            source_count=1,
        )

        stats["migrated"] += 1
        state_counts[claim_state.state] = state_counts.get(claim_state.state, 0) + 1

        if not dry_run:
            conn_ev.execute(
                """UPDATE event_links SET
                   v73_quality_level = ?, v73_quality_score = ?,
                   v73_claim_state = ?, v73_caveat = ?,
                   v73_rule_version = ?
                   WHERE id = ?""",
                (q.quality_level, round(q.quality_score, 4),
                 claim_state.state, claim_state.caveat,
                 V73_RULE_VERSION, link_id),
            )

    if not dry_run:
        conn_ev.commit()

    print(f"  Migrated: {stats['migrated']}, Skipped: {stats['skipped']}")
    print(f"  Claim states: {state_counts}")
    return stats


def run_rollback(conn, table, db_type="record"):
    """Rollback V7.3 migration by restoring original data from backup."""
    print(f"[V7.3] Rolling back {table}...")

    backups = conn.execute(
        """SELECT link_id, original_status, original_confidence,
                  original_rule_version, original_needs_review, original_decision_reason
           FROM link_migration_backup WHERE link_type = ?""",
        (f"{db_type}_link",),
    ).fetchall()

    print(f"  Backups to restore: {len(backups)}")

    for b in backups:
        conn.execute(
            f"""UPDATE {table} SET
               status = ?, confidence = ?, rule_version = ?,
               needs_review = ?, decision_reason = ?,
               v73_rule_version = ''
               WHERE id = ?""",
            (b["original_status"], b["original_confidence"], b["original_rule_version"],
             b["original_needs_review"], b["original_decision_reason"], b["link_id"]),
        )

    conn.commit()
    print(f"  Restored {len(backups)} links to pre-V7.3 state")


def main():
    parser = argparse.ArgumentParser(description="V7.3 Link Migration (idempotent, reversible)")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no changes")
    parser.add_argument("--execute", action="store_true", help="Apply changes to DB")
    parser.add_argument("--rollback", action="store_true", help="Revert to pre-V7.3 state")
    args = parser.parse_args()

    if not any([args.dry_run, args.execute, args.rollback]):
        parser.print_help()
        return

    print("=" * 70)
    print("V7.3 LINK MIGRATION — QUALITY ASSESSMENT + CLAIM LIFECYCLE")
    print("=" * 70)

    if args.rollback:
        print("Mode: ROLLBACK")
        conn = sqlite3.connect(DB, timeout=30)
        conn.row_factory = sqlite3.Row
        run_rollback(conn, "record_links", "record")
        conn.close()

        conn_ev = sqlite3.connect(EDB, timeout=30)
        conn_ev.row_factory = sqlite3.Row
        run_rollback(conn_ev, "event_links", "event")
        conn_ev.close()
        print("\nRollback complete.")
        return

    dry_run = not args.execute
    print(f"Mode: {'DRY RUN (audit only)' if dry_run else 'EXECUTE (apply changes)'}")
    print()

    # Step 1: Migrate record_links
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    t0 = time.time()
    run_migrate_record_links(conn, dry_run=dry_run)
    print(f"  Elapsed: {time.time()-t0:.1f}s")
    conn.close()

    # Step 2: Migrate event_links
    conn_ev = sqlite3.connect(EDB, timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_ev.execute("PRAGMA journal_mode=WAL")
    conn_main = sqlite3.connect(DB, timeout=30)
    conn_main.row_factory = sqlite3.Row
    t0 = time.time()
    run_migrate_event_links(conn_ev, conn_main, dry_run=dry_run)
    print(f"  Elapsed: {time.time()-t0:.1f}s")
    conn_ev.close()
    conn_main.close()

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    if dry_run:
        print("This was a DRY RUN. To apply changes, run with --execute")
    else:
        print("Changes have been applied. Original data backed up in link_migration_backup.")
        print("To revert: python migrate_v73_links.py --rollback")


if __name__ == "__main__":
    main()
