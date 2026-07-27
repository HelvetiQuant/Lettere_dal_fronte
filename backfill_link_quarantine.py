"""Backfill legacy links -> evidence.link_quarantine (idempotent).

Sources:
- eventi_1gm.db:event_links (~891k rows)
- imi_internati.db:record_links (~169k rows)

Destination: Supabase evidence.link_quarantine
Strategy: bulk INSERT via exec_sql with ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
BATCH_SIZE = 5000


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return _sql_literal(json.dumps(value, ensure_ascii=False, default=str))
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _build_insert(rows: List[Dict[str, Any]]) -> str:
    columns = [
        "source_table", "source_id", "target_table", "target_id",
        "link_type", "raw_data_json", "algorithm", "algorithm_version", "quarantine_reason"
    ]
    col_str = ", ".join(columns)
    values = []
    for row in rows:
        vals = [row[c] for c in columns]
        values.append("(" + ", ".join(_sql_literal(v) for v in vals) + ")")
    return f"""
    INSERT INTO evidence.link_quarantine ({col_str})
    VALUES {", ".join(values)}
    ON CONFLICT (source_table, source_id, target_table, target_id, link_type) DO NOTHING
    """


def _backfill_table(db_path: Path, query: str, mapper, table_name: str, dry_run: bool = False) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(query)

    total = 0
    inserted = 0
    skipped = 0
    errors = 0
    batch: List[Dict[str, Any]] = []

    def flush():
        nonlocal inserted, errors, batch
        if not batch:
            return
        if dry_run:
            inserted += len(batch)
            batch.clear()
            return
        sql = _build_insert(batch)
        try:
            r = execute_sql(sql, timeout=120)
            if r.get("ok") and (r.get("data") or {}).get("ok") is not False:
                inserted += len(batch)
            else:
                err = (r.get("data") or {}).get("error", r.get("error", "unknown"))
                print(f"    BATCH ERROR: {err[:200]}")
                errors += 1
        except Exception as e:
            print(f"    BATCH EXCEPTION: {e}")
            errors += 1
        batch.clear()

    print(f"Backfilling {table_name} from {db_path.name}...")
    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        for row in rows:
            mapped = mapper(dict(row))
            if mapped:
                batch.append(mapped)
            else:
                skipped += 1
            total += 1
        if len(batch) >= BATCH_SIZE:
            flush()
            print(f"  {table_name}: processed {total:,}, inserted {inserted:,}, errors {errors}")

    flush()
    conn.close()
    print(f"  {table_name} DONE: total={total:,}, inserted={inserted:,}, skipped={skipped:,}, errors={errors}")
    return {"total": total, "inserted": inserted, "skipped": skipped, "errors": errors}


def _map_event_link(row: Dict[str, Any]) -> Dict[str, Any] | None:
    return {
        "source_table": "eventi_1gm",
        "source_id": int(row["evento_id"]),
        "target_table": str(row["target_table"] or ""),
        "target_id": int(row["target_id"]),
        "link_type": str(row["link_type"] or ""),
        "raw_data_json": {
            "match_field": row["match_field"],
            "match_value": row["match_value"],
            "confidence": row["confidence"],
            "legacy_id": row["id"],
        },
        "algorithm": "legacy_event_link",
        "algorithm_version": "1.0",
        "quarantine_reason": "Migrated from event_links; awaiting human review",
    }


def _map_record_link(row: Dict[str, Any]) -> Dict[str, Any] | None:
    return {
        "source_table": str(row["from_table"] or ""),
        "source_id": int(row["from_id"]),
        "target_table": str(row["to_table"] or ""),
        "target_id": int(row["to_id"]),
        "link_type": str(row["link_type"] or ""),
        "raw_data_json": {
            "confidence": row["confidence"],
            "match_status": row["match_status"],
            "match_method": row["match_method"],
            "matched_fields_json": row["matched_fields_json"],
            "conflicting_fields_json": row["conflicting_fields_json"],
            "evidence_json": row["evidence_json"],
            "explanation": row["explanation"],
            "review_status": row["review_status"],
            "legacy_unverified": row["legacy_unverified"],
            "nature": row["nature"],
            "direction": row["direction"],
            "legacy_id": row["id"],
        },
        "algorithm": "legacy_record_link",
        "algorithm_version": str(row["algorithm_version"] or "1.0"),
        "quarantine_reason": "Migrated from record_links; awaiting human review",
    }


def main(dry_run: bool = False):
    print("=" * 70)
    print(f"BACKFILL evidence.link_quarantine — {'DRY-RUN' if dry_run else 'ESECUZIONE'}")
    print("=" * 70)

    stats_event = _backfill_table(
        BASE / "eventi_1gm.db",
        "SELECT * FROM event_links",
        _map_event_link,
        "event_links",
        dry_run=dry_run,
    )

    stats_record = _backfill_table(
        BASE / "imi_internati.db",
        "SELECT * FROM record_links",
        _map_record_link,
        "record_links",
        dry_run=dry_run,
    )

    print("\n" + "=" * 70)
    print("RIEPILOGO")
    print("=" * 70)
    total = stats_event["total"] + stats_record["total"]
    inserted = stats_event["inserted"] + stats_record["inserted"]
    skipped = stats_event["skipped"] + stats_record["skipped"]
    errors = stats_event["errors"] + stats_record["errors"]
    print(f"  Total processed: {total:,}")
    print(f"  {'Would insert' if dry_run else 'Inserted'}: {inserted:,}")
    print(f"  Skipped: {skipped:,}")
    print(f"  Batch errors: {errors}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill link_quarantine from legacy link tables")
    parser.add_argument("--dry-run", action="store_true", help="Anteprima senza scritture")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
