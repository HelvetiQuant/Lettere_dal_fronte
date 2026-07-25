"""API per map features canoniche con provenienza."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database_registry import connect_database, table_exists

EDB = Path(__file__).parent / "eventi_1gm.db"

router = APIRouter(prefix="/api/map-features", tags=["map-features"])


class MapFeatureCreate(BaseModel):
    id: str
    event_id: str
    phase: str = ""
    feature_type: str
    geojson: Dict[str, Any]
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    label: str
    description: Optional[str] = None
    certainty: str = "verified"
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    source_url: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/event/{event_id}")
def list_map_features(event_id: str):
    """List all map features for an event."""
    conn = connect_database("events", read_only=True)
    try:
        if not table_exists(conn, "map_features"):
            return {"features": [], "total": 0}
        rows = conn.execute(
            "SELECT * FROM map_features WHERE event_id=? ORDER BY phase, label",
            (event_id,),
        ).fetchall()
        features = []
        for row in rows:
            d = dict(row)
            try:
                d["geojson"] = json.loads(d["geojson"])
            except (json.JSONDecodeError, TypeError):
                pass
            features.append(d)
        return {"features": features, "total": len(features)}
    finally:
        conn.close()


@router.post("/")
def create_map_feature(body: MapFeatureCreate):
    """Create or update a map feature."""
    conn = sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row
    try:
        now = _now()
        geojson_str = json.dumps(body.geojson, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO map_features
                (id, event_id, phase, feature_type, geojson, date_start, date_end,
                 label, description, certainty, source_table, source_id, source_url,
                 review_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                phase=excluded.phase,
                feature_type=excluded.feature_type,
                geojson=excluded.geojson,
                date_start=excluded.date_start,
                date_end=excluded.date_end,
                label=excluded.label,
                description=excluded.description,
                certainty=excluded.certainty,
                source_table=excluded.source_table,
                source_id=excluded.source_id,
                source_url=excluded.source_url,
                updated_at=excluded.updated_at
            """,
            (body.id, body.event_id, body.phase, body.feature_type, geojson_str,
             body.date_start, body.date_end, body.label, body.description,
             body.certainty, body.source_table, body.source_id, body.source_url,
             now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM map_features WHERE id=?", (body.id,)).fetchone()
        d = dict(row)
        try:
            d["geojson"] = json.loads(d["geojson"])
        except (json.JSONDecodeError, TypeError):
            pass
        return d
    finally:
        conn.close()


@router.put("/{feature_id}/review")
def review_map_feature(feature_id: str, body: Dict[str, Any]):
    """Review a map feature (accept/reject/needs_more_evidence)."""
    conn = sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM map_features WHERE id=?", (feature_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Feature non trovata: {feature_id}")
        review_status = body.get("review_status", "reviewed")
        reviewed_by = body.get("reviewed_by", "system")
        reviewed_at = _now()
        conn.execute(
            "UPDATE map_features SET review_status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
            (review_status, reviewed_by, reviewed_at, feature_id),
        )
        conn.commit()
        d = dict(conn.execute("SELECT * FROM map_features WHERE id=?", (feature_id,)).fetchone())
        try:
            d["geojson"] = json.loads(d["geojson"])
        except (json.JSONDecodeError, TypeError):
            pass
        return d
    finally:
        conn.close()
