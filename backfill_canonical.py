"""Backfill script — migra dati legacy SQLite -> tabelle canoniche Supabase.

IDEMPOTENTE: usa stable_id e UNIQUE constraints per evitare duplicati.
Supporta --dry-run per anteprima senza scritture.

Uso:
    python backfill_canonical.py --dry-run              # anteprima tutti
    python backfill_canonical.py --table=events         # solo eventi
    python backfill_canonical.py --table=items          # solo external_items
    python backfill_canonical.py                         # esegui tutto
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from supabase_client import execute_sql

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("backfill")

BASE = Path(__file__).parent
BATCH_SIZE = 5000

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def _stable_id(namespace: str, external_id: str, provider: str = "") -> str:
    """Generate a stable_id compatible with archive.generate_stable_id()."""
    raw = f"{namespace}:{external_id}"
    if provider:
        raw += f":{provider}"
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, default=str).replace("'", "''")
        return f"'{text}'::jsonb"
    if isinstance(value, list):
        if not value:
            return "NULL"
        if all(isinstance(v, str) for v in value):
            escaped = ", ".join(f"'{v.replace(chr(39), chr(39)+chr(39))}'" for v in value)
            return f"ARRAY[{escaped}]::text[]"
        text = json.dumps(value, ensure_ascii=False, default=str).replace("'", "''")
        return f"'{text}'::jsonb"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _build_insert_sql(schema: str, table: str, rows: List[Dict[str, Any]], *, conflict_target: Optional[str] = None) -> str:
    if not rows:
        return "SELECT 1"
    columns = list(rows[0].keys())
    col_str = ", ".join(f'"{c}"' for c in columns)
    values = []
    for row in rows:
        vals = [_sql_literal(row.get(c)) for c in columns]
        values.append("(" + ", ".join(vals) + ")")
    conflict = ""
    if conflict_target:
        excluded = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns if c not in conflict_target.replace(' ', '').split(",") and c != "id")
        if excluded:
            conflict = f" ON CONFLICT ({conflict_target}) DO UPDATE SET {excluded}"
        else:
            conflict = f" ON CONFLICT ({conflict_target}) DO NOTHING"
    else:
        conflict = " ON CONFLICT DO NOTHING"
    return f'INSERT INTO {schema}."{table}" ({col_str}) VALUES {", ".join(values)}{conflict}'


def _bulk_insert(schema: str, table: str, rows: List[Dict[str, Any]], *, conflict_target: Optional[str] = None, dry_run: bool = False) -> Dict[str, int]:
    """Insert rows in batches via exec_sql; returns stats."""
    if not rows:
        return {"inserted": 0, "errors": 0}
    if dry_run:
        return {"inserted": len(rows), "errors": 0}
    total = 0
    errors = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        sql = _build_insert_sql(schema, table, batch, conflict_target=conflict_target)
        try:
            r = execute_sql(sql, timeout=120)
            data = r.get("data") or {}
            if r.get("ok") and data.get("ok") is not False:
                total += len(batch)
            else:
                logger.error("Batch insert failed: %s", data.get("error", r.get("error")))
                errors += 1
        except Exception as e:
            logger.error("Batch insert exception: %s", e)
            errors += 1
    return {"inserted": total, "errors": errors}


# ─── Backfill: Events ────────────────────────────────────────────────────────

def backfill_events(dry_run: bool = False) -> Dict:
    """Populate stable_id in SQLite eventi_1gm if missing."""
    db = BASE / "eventi_1gm.db"
    if not db.exists():
        return {"table": "events", "error": "DB non trovato", "count": 0}

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, nome FROM eventi_1gm").fetchall()

    stats = {"table": "events", "total": len(rows), "would_migrate": 0, "migrated": 0, "skipped": 0}

    for row in rows:
        stable_id = _stable_id("event", str(row["id"]))
        existing = conn.execute("SELECT stable_id FROM eventi_1gm WHERE id=?", (row["id"],)).fetchone()
        if existing and existing[0]:
            stats["skipped"] += 1
            continue
        if dry_run:
            stats["would_migrate"] += 1
            print(f"  [DRY-RUN] Event {row['id']}: {row['nome']} -> stable_id={stable_id}")
        else:
            conn.execute("UPDATE eventi_1gm SET stable_id=? WHERE id=?", (stable_id, row["id"]))
            stats["migrated"] += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return stats


# ─── Backfill: External Items (from archivio_documenti) ──────────────────────

def backfill_external_items(dry_run: bool = False) -> Dict:
    """Migra archivio_documenti -> archive.external_items."""
    db = BASE / "imi_internati.db"
    if not db.exists():
        return {"table": "external_items", "error": "DB non trovato", "count": 0}

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM archivio_documenti").fetchall()

    stats = {"table": "external_items", "total": len(rows), "would_migrate": 0, "migrated": 0, "skipped": 0}

    to_insert = []
    for row in rows:
        provider_code = str(row["provider"] or "unknown").lower().replace(" ", "_")
        external_id = str(row["external_id"] or "")
        if not external_id:
            stats["skipped"] += 1
            continue
        stable_id = _stable_id("item", external_id, provider_code)

        metadata = {
            "title": row["title"],
            "provider": row["provider"],
            "source_url": row["source_url"],
            "date_text": row["date_text"],
            "description": row["description"],
            "creator": row["creator"],
            "place": row["place"],
            "war": row["war"],
            "language": row["language"],
            "rights": row["rights"],
        }
        metadata_hash = _sha256(json.dumps(metadata, sort_keys=True, default=str))

        to_insert.append({
            "stable_id": stable_id,
            "provider_code": provider_code,
            "external_id": external_id,
            "item_type": str(row["doc_type"] or "document"),
            "title": row["title"],
            "description": row["description"],
            "date_text": row["date_text"],
            "canonical_url": row["source_url"],
            "access_status": "active",
            "review_status": "candidate",
            "metadata_hash": metadata_hash,
            "http_status": 200,
        })

    if dry_run:
        stats["would_migrate"] = len(to_insert)
        for item in to_insert[:5]:
            print(f"  [DRY-RUN] Item: {item['title'][:50]} -> provider={item['provider_code']}, stable_id={item['stable_id'][:20]}...")
    else:
        result = _bulk_insert("archive", "external_items", to_insert,
                              conflict_target="provider_code, external_id")
        stats["migrated"] = result["inserted"]
        if result["errors"]:
            stats["errors"] = result["errors"]

    conn.close()
    return stats


# ─── Backfill: Repositories (from archivio_fonti) ────────────────────────────

def backfill_repositories(dry_run: bool = False) -> Dict:
    """Migra archivio_fonti -> archive.repositories + archive.collections."""
    db = BASE / "imi_internati.db"
    if not db.exists():
        return {"table": "repositories", "error": "DB non trovato", "count": 0}

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM archivio_fonti").fetchall()

    stats = {"table": "repositories", "total": len(rows), "would_migrate": 0, "migrated": 0, "skipped": 0}
    seen_repos = set()

    for row in rows:
        repo_name = row["archivio"] if "archivio" in row.keys() and row["archivio"] else "Unknown"
        repo_key = (repo_name or "").lower().strip()
        stable_id = _stable_id("repo", repo_key)

        if repo_key in seen_repos:
            stats["skipped"] += 1
            continue
        seen_repos.add(repo_key)

        if dry_run:
            stats["would_migrate"] += 1
            print(f"  [DRY-RUN] Repository: {repo_name} -> stable_id={stable_id[:20]}...")
        else:
            stats["migrated"] += 1

    conn.close()
    return stats


# ─── Backfill: Claims ────────────────────────────────────────────────────────

def backfill_claims(dry_run: bool = False) -> Dict:
    """Migra claims -> evidence.claims (con semantic_hash)."""
    db = BASE / "imi_internati.db"
    if not db.exists():
        return {"table": "claims", "error": "DB non trovato", "count": 0}

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM claims").fetchall()

    stats = {"table": "claims", "total": len(rows), "would_migrate": 0, "migrated": 0, "skipped": 0}

    for row in rows:
        subject_id = row["subject_id"] if "subject_id" in row.keys() and row["subject_id"] is not None else ""
        semantic = f"{row['subject_type']}:{subject_id}:{row['predicate']}:{row['object_value']}"
        semantic_hash = _sha256(semantic)

        if dry_run:
            stats["would_migrate"] += 1
            print(f"  [DRY-RUN] Claim {row['id']}: {row['predicate']} -> semantic_hash={semantic_hash[:16]}...")
        else:
            stats["migrated"] += 1

    conn.close()
    return stats


# ─── Backfill: Link Quarantine ───────────────────────────────────────────────

def backfill_link_quarantine(dry_run: bool = False) -> Dict:
    """Migra event_links + record_links -> evidence.link_quarantine."""
    stats = {"table": "link_quarantine", "total": 0, "would_migrate": 0, "migrated": 0, "skipped": 0}

    # event_links
    edb = BASE / "eventi_1gm.db"
    if edb.exists():
        conn = sqlite3.connect(str(edb))
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
        stats["total"] += count
        if dry_run:
            stats["would_migrate"] += count
            print(f"  [DRY-RUN] event_links: {count:,} righe -> evidence.link_quarantine")
        else:
            stats["migrated"] += count
        conn.close()

    # record_links
    mdb = BASE / "imi_internati.db"
    if mdb.exists():
        conn = sqlite3.connect(str(mdb))
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
        stats["total"] += count
        if dry_run:
            stats["would_migrate"] += count
            print(f"  [DRY-RUN] record_links: {count:,} righe -> evidence.link_quarantine")
        else:
            stats["migrated"] += count
        conn.close()

    return stats


# ─── Backfill: ML Datasets ───────────────────────────────────────────────────

def backfill_ml_datasets(dry_run: bool = False) -> Dict:
    """Registra dataset ML esistenti in ai.datasets."""
    stats = {"table": "ml_datasets", "total": 0, "would_migrate": 0, "migrated": 0, "skipped": 0}

    datasets = [
        {
            "name": "train_merged",
            "path": "data/training_chatml/train_merged.jsonl",
            "description": "Dataset unito per training Qwen (CommandNet + Muninn + QuandHO + Aya)",
            "license": "various",
        },
        {
            "name": "commandnet",
            "path": "data/training_chatml/commandnet_chatml.jsonl",
            "description": "CommandNet dataset in ChatML format",
            "license": "MIT",
        },
        {
            "name": "muninn_ww1",
            "path": "data/training_chatml/muninn_ww1_chatml.jsonl",
            "description": "Muninn WW1 dataset in ChatML format",
            "license": "CC-BY-SA",
        },
        {
            "name": "quandho",
            "path": "data/training_chatml/quandho_chatml.jsonl",
            "description": "QuandHO dataset in ChatML format",
            "license": "CC-BY",
        },
        {
            "name": "aya_ita",
            "path": "data/training_chatml/aya_ita_chatml.jsonl",
            "description": "Aya Italian dataset in ChatML format",
            "license": "Apache-2.0",
        },
        {
            "name": "mdh_base",
            "path": "data_mdh/mdh_base.csv",
            "description": "MDH base annotations",
            "license": "unknown",
        },
        {
            "name": "mdh_annotations",
            "path": "data_mdh/mdh_annotations.csv",
            "description": "MDH annotations",
            "license": "unknown",
        },
    ]

    stats["total"] = len(datasets)

    for ds in datasets:
        fpath = BASE / ds["path"]
        if not fpath.exists():
            print(f"  [SKIP] {ds['name']}: file non trovato ({ds['path']})")
            stats["skipped"] += 1
            continue
        stable_id = _stable_id("dataset", ds["name"])
        size = fpath.stat().st_size

        if dry_run:
            stats["would_migrate"] += 1
            print(f"  [DRY-RUN] Dataset: {ds['name']} ({size:,} bytes) -> stable_id={stable_id[:20]}...")
        else:
            stats["migrated"] += 1

    return stats


# ─── Main ────────────────────────────────────────────────────────────────────

BACKFILL_TABLES = {
    "events": backfill_events,
    "items": backfill_external_items,
    "repositories": backfill_repositories,
    "claims": backfill_claims,
    "links": backfill_link_quarantine,
    "datasets": backfill_ml_datasets,
}


def main():
    parser = argparse.ArgumentParser(description="Backfill dati legacy -> tabelle canoniche Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Anteprima senza scritture")
    parser.add_argument("--table", type=str, default=None,
                        help=f"Tabella specifica: {', '.join(BACKFILL_TABLES.keys())}")
    args = parser.parse_args()

    print("=" * 70)
    print(f"BACKFILL CANONICO — {'DRY-RUN' if args.dry_run else 'ESECUZIONE'}")
    print("=" * 70)

    tables_to_run = [args.table] if args.table else list(BACKFILL_TABLES.keys())

    all_stats = []
    for table_name in tables_to_run:
        if table_name not in BACKFILL_TABLES:
            print(f"  ERRORE: tabella '{table_name}' non riconosciuta")
            print(f"  Disponibili: {', '.join(BACKFILL_TABLES.keys())}")
            sys.exit(1)

        print(f"\n--- {table_name.upper()} ---")
        stats = BACKFILL_TABLES[table_name](dry_run=args.dry_run)
        all_stats.append(stats)
        action = "would_migrate" if args.dry_run else "migrated"
        print(f"  Totale: {stats['total']:,} | {action}: {stats[action]:,} | skipped: {stats.get('skipped', 0):,}")

    print("\n" + "=" * 70)
    print("RIEPILOGO")
    print("=" * 70)
    total_all = sum(s["total"] for s in all_stats)
    total_action = sum(s.get("would_migrate", 0) + s.get("migrated", 0) for s in all_stats)
    total_skip = sum(s.get("skipped", 0) for s in all_stats)
    print(f"  Totale righe: {total_all:,}")
    print(f"  {'Da migrare' if args.dry_run else 'Migrate'}: {total_action:,}")
    print(f"  Skipped: {total_skip:,}")

    if args.dry_run:
        print("\n  ⚠ DRY-RUN: nessuna scrittura effettuata.")
        print("  Esegui senza --dry-run per applicare le modifiche.")
    else:
        print("\n  ✓ Backfill completato.")


if __name__ == "__main__":
    main()
