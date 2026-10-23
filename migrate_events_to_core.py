"""migrate_events_to_core.py — Migra eventi_1gm.db (SQLite, fonte reale) in
Supabase core.entities / core.events / core.entity_names.

Idempotente: usa UNIQUE(source_system, source_id) su core.events e
UNIQUE(stable_id) su core.entities come chiavi di upsert (ON CONFLICT DO
UPDATE). Rieseguibile senza duplicare righe.

Due passate:
1. Upsert entities + events (parent_event_id lasciato NULL alla prima passata,
   perché il riferimento è a un altro evento non ancora garantito presente).
2. Risolve parent_event_id per stable_id e aggiorna core.events.

Usage:
    python migrate_events_to_core.py              # esegue la migrazione
    python migrate_events_to_core.py --dry-run     # mostra cosa farebbe
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EDB = Path(__file__).parent / "eventi_1gm.db"
SOURCE_SYSTEM = "sqlite:eventi_1gm"


def _sql_str(value: Optional[str]) -> str:
    """Safely quote a string literal for inline SQL (escape single quotes)."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _sql_json(value: Any) -> str:
    if value is None:
        return "'[]'::jsonb"
    if isinstance(value, str):
        try:
            json.loads(value)
            return _sql_str(value) + "::jsonb"
        except (json.JSONDecodeError, TypeError):
            return "'[]'::jsonb"
    return _sql_str(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def _call_rpc(fn_name: str, query: str) -> Any:
    from supabase_client import SUPABASE_URL, _rest_headers
    import httpx

    url = f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}"
    r = httpx.post(url, headers=_rest_headers(), json={"query": query}, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"{fn_name} HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    if isinstance(data, dict) and data.get("__error__"):
        raise RuntimeError(f"{fn_name} SQL error: {data.get('error')} ({data.get('detail')})")
    return data


def exec_sql_query(query: str) -> List[Dict[str, Any]]:
    """Execute a plain read-only SELECT via exec_sql_query RPC (returns rows)."""
    data = _call_rpc("exec_sql_query", query)
    return data or []


def exec_sql_returning(query: str) -> List[Dict[str, Any]]:
    """Execute a query that must end with `SELECT json_agg(row_to_json(x)) FROM x`.

    Needed for WITH ... INSERT ... RETURNING ... SELECT patterns, since Postgres
    requires data-modifying CTEs to be at the top level of the executed string
    (exec_sql_query wraps queries in an outer subquery, which breaks this rule).
    """
    data = _call_rpc("exec_sql_returning", query)
    return data or []


def load_events() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, nome, data_inizio, data_fine, luogo, aliases, keywords,
               descrizione, conflict, event_type, parent_event_id,
               temporal_precision, general_location, localities_json,
               subjects_json, units_json, review_status, stable_id,
               narrative_version, narrative_updated_at
        FROM eventi_1gm
        ORDER BY id
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_event(ev: Dict[str, Any], *, dry_run: bool) -> Dict[str, Any]:
    stable_id = ev["stable_id"] or f"evt_{ev['id']:04d}"
    entity_stable_id = f"entity:event:{stable_id}"
    canonical_name = ev["nome"]
    conflict_code = ev["conflict"]
    event_type = ev["event_type"] or "battaglia"
    review_status = ev["review_status"] or "candidate"
    date_start = ev["data_inizio"]
    date_end = ev["data_fine"]
    temporal_precision = ev["temporal_precision"] or "day"
    general_location = ev["general_location"] or ev["luogo"]
    description = ev["descrizione"]
    localities = ev["localities_json"]
    subjects = ev["subjects_json"]
    units = ev["units_json"]
    narrative_version = ev["narrative_version"]
    narrative_updated_at = ev["narrative_updated_at"]
    source_id = str(ev["id"])

    if dry_run:
        print(f"  [DRY-RUN] upsert entity+event: {stable_id} — {canonical_name} ({conflict_code})")
        return {"stable_id": stable_id, "aliases": ev.get("aliases")}

    entity_sql = f"""
        WITH ins AS (
            INSERT INTO core.entities
                (stable_id, entity_type, canonical_name, created_by_kind,
                 verification_status, confidence, source_system, source_table, source_id)
            VALUES
                ({_sql_str(entity_stable_id)}, 'event', {_sql_str(canonical_name)}, 'migration',
                 {_sql_str(review_status)}, 0.6, {_sql_str(SOURCE_SYSTEM)}, 'eventi_1gm', {_sql_str(source_id)})
            ON CONFLICT (stable_id) DO UPDATE SET
                canonical_name = EXCLUDED.canonical_name,
                verification_status = EXCLUDED.verification_status
            RETURNING id
        )
        SELECT json_agg(row_to_json(ins)) FROM ins
    """
    result = exec_sql_returning(entity_sql)
    if not result:
        raise RuntimeError(f"Entity upsert returned no id for {stable_id}")
    entity_id = result[0]["id"]

    event_sql = f"""
        WITH ins AS (
            INSERT INTO core.events
                (entity_id, stable_id, preferred_name, conflict_code, event_type,
                 date_start, date_end, temporal_precision, general_location,
                 localities, subjects, units, description, review_status,
                 narrative_version, narrative_updated_at, source_system, source_id)
            VALUES
                ({entity_id}, {_sql_str(stable_id)}, {_sql_str(canonical_name)}, {_sql_str(conflict_code)},
                 {_sql_str(event_type)}, {_sql_str(date_start)}::date, {_sql_str(date_end)}::date,
                 {_sql_str(temporal_precision)}, {_sql_str(general_location)},
                 {_sql_json(localities)}, {_sql_json(subjects)}, {_sql_json(units)},
                 {_sql_str(description)}, {_sql_str(review_status)},
                 {_sql_str(narrative_version)}, {_sql_str(narrative_updated_at)}::timestamptz,
                 {_sql_str(SOURCE_SYSTEM)}, {_sql_str(source_id)})
            ON CONFLICT (source_system, source_id) DO UPDATE SET
                preferred_name = EXCLUDED.preferred_name,
                conflict_code = EXCLUDED.conflict_code,
                event_type = EXCLUDED.event_type,
                date_start = EXCLUDED.date_start,
                date_end = EXCLUDED.date_end,
                general_location = EXCLUDED.general_location,
                description = EXCLUDED.description,
                review_status = EXCLUDED.review_status
            RETURNING id
        )
        SELECT json_agg(row_to_json(ins)) FROM ins
    """
    result = exec_sql_returning(event_sql)
    if not result:
        raise RuntimeError(f"Event upsert returned no id for {stable_id}")

    # Alias
    aliases_raw = ev.get("aliases")
    aliases: List[str] = []
    if aliases_raw:
        try:
            aliases = json.loads(aliases_raw)
        except (json.JSONDecodeError, TypeError):
            aliases = []
    for alias in aliases:
        alias = (alias or "").strip()
        if not alias or alias == canonical_name:
            continue
        alias_sql = f"""
            INSERT INTO core.entity_names (entity_id, name, name_type, provenance)
            VALUES ({entity_id}, {_sql_str(alias)}, 'alias', 'sqlite:eventi_1gm.aliases')
            ON CONFLICT (entity_id, name) DO NOTHING
        """
        execute_sql(alias_sql)

    return {"stable_id": stable_id, "entity_id": entity_id}


def link_parents(events: List[Dict[str, Any]], *, dry_run: bool) -> int:
    updated = 0
    for ev in events:
        parent_stable_id = ev.get("parent_event_id")
        if not parent_stable_id:
            continue
        stable_id = ev["stable_id"] or f"evt_{ev['id']:04d}"
        if dry_run:
            print(f"  [DRY-RUN] link parent: {stable_id} -> {parent_stable_id}")
            continue
        sql = f"""
            UPDATE core.events SET parent_event_id = (
                SELECT id FROM core.events WHERE stable_id = {_sql_str(parent_stable_id)}
            )
            WHERE stable_id = {_sql_str(stable_id)}
        """
        result = execute_sql(sql)
        if result.get("ok"):
            updated += 1
        else:
            print(f"  WARN: failed to link {stable_id} -> {parent_stable_id}: {result.get('error')}")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Migrate eventi_1gm.db events to Supabase core schema")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not EDB.exists():
        print(f"ERROR: {EDB} not found")
        return 1

    events = load_events()
    print(f"Loaded {len(events)} events from eventi_1gm.db")
    print("=" * 72)

    migrated = 0
    for ev in events:
        try:
            upsert_event(ev, dry_run=args.dry_run)
            migrated += 1
        except Exception as e:
            print(f"  ERROR migrating event id={ev['id']} ({ev['nome']}): {e}")

    print("=" * 72)
    print(f"Entities+events upserted: {migrated}/{len(events)}")

    linked = link_parents(events, dry_run=args.dry_run)
    print(f"Parent links resolved: {linked}")

    if not args.dry_run:
        counts = exec_sql_query("SELECT COUNT(*) AS n FROM core.events")
        names_counts = exec_sql_query("SELECT COUNT(*) AS n FROM core.entity_names")
        by_conflict = exec_sql_query(
            "SELECT conflict_code, COUNT(*) AS n FROM core.events GROUP BY conflict_code ORDER BY conflict_code"
        )
        print(f"core.events total: {counts[0]['n'] if counts else '?'}")
        print(f"core.entity_names total: {names_counts[0]['n'] if names_counts else '?'}")
        print("By conflict:", by_conflict)

    return 0


if __name__ == "__main__":
    sys.exit(main())
