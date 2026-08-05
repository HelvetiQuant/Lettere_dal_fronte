"""Backfill person_source_matches from existing internati records.

Idempotent: only inserts new matches, never deletes or overwrites.
Dry-run by default: use --execute to write to DB.

Run: python backfill_person_source_matches.py [--dry-run|--execute]
"""
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

from person_identity_resolver import PersonIdentityResolver, build_person_queries

DB_PATH = Path(__file__).parent / "imi_internati.db"


def backfill(dry_run: bool = True):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat(timespec="seconds")

    # Get all internati with cognome and nome
    rows = conn.execute(
        "SELECT * FROM internati WHERE cognome IS NOT NULL AND cognome != '' AND nome IS NOT NULL AND nome != ''"
    ).fetchall()

    print(f"Found {len(rows)} internati records with cognome+nome")

    inserted = 0
    skipped = 0
    errors = 0

    for row in rows:
        record = dict(row)
        cognome = record.get("cognome", "").strip()
        nome = record.get("nome", "").strip()
        person_id = record.get("id", 0)

        if not cognome or not nome:
            skipped += 1
            continue

        # Check if already exists
        existing = conn.execute(
            "SELECT 1 FROM person_source_matches WHERE person_table='internati' AND person_id=? AND source_table='internati' AND source_id=?",
            (person_id, person_id)
        ).fetchone()

        if existing:
            skipped += 1
            continue

        # Self-match: the internati record is a confirmed source for itself
        resolver = PersonIdentityResolver()
        resolver.set_target(cognome, nome, record=record, target_id=str(person_id))
        result = resolver.evaluate_source(
            source=record,
            source_kind="local_db",
            source_table="internati",
            source_id=str(person_id),
            provider="local_db",
        )

        if dry_run:
            print(f"  [DRY-RUN] Would insert: person_id={person_id} status={result.status} features={result.matched_features}")
            inserted += 1
            continue

        try:
            conn.execute(
                """INSERT OR IGNORE INTO person_source_matches
                (person_table, person_id, source_table, source_id, status, source_kind,
                 normalized_name, matched_features_json, conflicting_features_json,
                 reason_codes_json, resolver_version, manually_reviewed,
                 url, title, query_used, provider, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "internati", person_id, "internati", person_id,
                    result.status, "local_db",
                    f"{cognome} {nome}".strip(),
                    json.dumps(result.matched_features),
                    json.dumps(result.conflicting_features),
                    json.dumps(result.reason_codes),
                    result.resolver_version, 0,
                    "", f"{cognome} {nome}", "", "local_db", now, now,
                )
            )
            inserted += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR for person_id={person_id}: {e}")

    if not dry_run:
        conn.commit()

    conn.close()
    print(f"\nSummary: inserted={inserted}, skipped={skipped}, errors={errors}")
    if dry_run:
        print("[DRY-RUN] No changes written. Use --execute to apply.")


if __name__ == "__main__":
    dry = "--execute" not in sys.argv
    backfill(dry_run=dry)
