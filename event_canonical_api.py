"""API canonica per eventi con stable_id, gerarchia, alias, e stato epistemico."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from database_registry import EVENTS_DB_PATH, connect_database, table_exists

router = APIRouter(prefix="/api/canonical-events", tags=["eventi-canonici"])


def _row_to_event(row: sqlite3.Row, *, include_aliases: bool = True) -> Dict[str, Any]:
    d = dict(row)
    event_id = d["id"]

    aliases_raw = d.get("aliases") or "[]"
    try:
        aliases_list = json.loads(aliases_raw)
    except (json.JSONDecodeError, TypeError):
        aliases_list = []

    localities = d.get("localities_json") or "[]"
    try:
        localities_list = json.loads(localities)
    except (json.JSONDecodeError, TypeError):
        localities_list = []

    subjects = d.get("subjects_json") or "[]"
    try:
        subjects_list = json.loads(subjects)
    except (json.JSONDecodeError, TypeError):
        subjects_list = []

    units = d.get("units_json") or "[]"
    try:
        units_list = json.loads(units)
    except (json.JSONDecodeError, TypeError):
        units_list = []

    result = {
        "stable_id": d.get("stable_id") or f"evt_{event_id:04d}",
        "id": event_id,
        "preferred_name": d["nome"],
        "aliases": [{"name": a, "type": "alias"} for a in aliases_list],
        "conflict": d.get("conflict") or "WWI",
        "event_type": d.get("event_type") or "battaglia",
        "parent_event_id": d.get("parent_event_id"),
        "child_event_ids": [],
        "date_start": d.get("data_inizio"),
        "date_end": d.get("data_fine"),
        "temporal_precision": d.get("temporal_precision") or "day",
        "general_location": d.get("general_location") or d.get("luogo"),
        "localities": localities_list,
        "subjects": subjects_list,
        "units": units_list,
        "description": d.get("descrizione"),
        "review_status": d.get("review_status") or "candidate",
        "narrative_version": d.get("narrative_version"),
        "narrative_updated_at": d.get("narrative_updated_at"),
    }

    if include_aliases:
        conn = connect_database("events", read_only=True)
        try:
            if table_exists(conn, "event_aliases"):
                alias_rows = conn.execute(
                    "SELECT alias, alias_type FROM event_aliases WHERE event_id=? ORDER BY alias",
                    (event_id,),
                ).fetchall()
                result["aliases"] = [
                    {"name": r["alias"], "type": r["alias_type"]} for r in alias_rows
                ]
        finally:
            conn.close()

    return result


@router.get("")
@router.get("/")
def list_canonical_events(
    conflict: Optional[str] = Query(None, description="Filter by conflict: WWI, WWII, other"),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    conn = connect_database("events", read_only=True)
    try:
        where = []
        params = []
        if conflict:
            where.append("conflict = ?")
            params.append(conflict)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"SELECT * FROM eventi_1gm {where_clause} ORDER BY data_inizio LIMIT ?",
            (*params, limit),
        ).fetchall()
        return {"events": [_row_to_event(r, include_aliases=False) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.get("/{stable_id}")
def get_canonical_event(stable_id: str):
    conn = connect_database("events", read_only=True)
    try:
        row = conn.execute(
            "SELECT * FROM eventi_1gm WHERE stable_id=? OR id=?",
            (stable_id, stable_id if stable_id.isdigit() else -1),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Evento non trovato: {stable_id}")
        return _row_to_event(row)
    finally:
        conn.close()


@router.get("/{stable_id}/children")
def get_event_children(stable_id: str):
    """Returns child events based on parent_event_id."""
    conn = connect_database("events", read_only=True)
    try:
        row = conn.execute(
            "SELECT * FROM eventi_1gm WHERE stable_id=? OR id=?",
            (stable_id, stable_id if stable_id.isdigit() else -1),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Evento non trovato: {stable_id}")
        parent_stable = row["stable_id"] or f"evt_{row['id']:04d}"
        children = conn.execute(
            "SELECT * FROM eventi_1gm WHERE parent_event_id=?",
            (parent_stable,),
        ).fetchall()
        return {
            "parent": _row_to_event(row, include_aliases=False),
            "children": [_row_to_event(c, include_aliases=False) for c in children],
        }
    finally:
        conn.close()


@router.put("/{stable_id}")
def update_canonical_event(stable_id: str, body: Dict[str, Any]):
    """Update canonical event fields (review_status, event_type, conflict, etc.)."""
    conn = connect_database("events", read_only=False)
    try:
        row = conn.execute(
            "SELECT * FROM eventi_1gm WHERE stable_id=? OR id=?",
            (stable_id, stable_id if stable_id.isdigit() else -1),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Evento non trovato: {stable_id}")

        allowed_fields = {
            "conflict", "event_type", "parent_event_id", "temporal_precision",
            "general_location", "review_status", "narrative_version",
            "narrative_updated_at",
        }
        updates = []
        params = []
        for key, value in body.items():
            if key in allowed_fields:
                updates.append(f'"{key}"=?')
                params.append(value)

        if not updates:
            raise HTTPException(400, "Nessun campo aggiornabile fornito")

        params.append(row["id"])
        conn.execute(
            f"UPDATE eventi_1gm SET {', '.join(updates)} WHERE id=?",
            params,
        )
        conn.commit()

        updated = conn.execute("SELECT * FROM eventi_1gm WHERE id=?", (row["id"],)).fetchone()
        return _row_to_event(updated)
    finally:
        conn.close()
