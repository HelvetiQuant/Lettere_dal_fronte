"""
API v2 router per linking provenance e status.

Espone endpoint con provenance-aware responses:
- GET /api/v2/status/manifest — stato reale del sistema
- GET /api/v2/events — eventi con conflict_code e status
- GET /api/v2/relations — relazioni candidate/confirmed con features
- GET /api/v2/kill-switch — stato kill switch legacy jobs
"""
import json
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from linking.kill_switch import list_jobs

router = APIRouter(prefix="/api/v2", tags=["v2"])

ROOT = Path(__file__).resolve().parent


def _get_conn():
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _get_event_conn():
    conn = sqlite3.connect(str(ROOT / "eventi_1gm.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/status/manifest")
async def status_manifest():
    """System status derived from real data, not hardcoded constants."""
    conn = _get_conn()
    event_conn = _get_event_conn()
    
    try:
        # Table counts
        internati_count = conn.execute("SELECT COUNT(*) FROM internati").fetchone()[0]
        relations_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        resource_count = conn.execute("SELECT COUNT(*) FROM resource_registry").fetchone()[0]
        claims_count = conn.execute("SELECT COUNT(*) FROM claims_v2").fetchone()[0]
        quarantine_count = conn.execute("SELECT COUNT(*) FROM legacy_relation_quarantine").fetchone()[0]
        pipeline_runs = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
        
        # Relations by status
        try:
            status_rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM relations GROUP BY status ORDER BY n DESC"
            ).fetchall()
            relations_by_status = {r["status"]: r["n"] for r in status_rows}
        except Exception:
            relations_by_status = {}
        
        # Relations by evidence_strength
        try:
            strength_rows = conn.execute(
                "SELECT evidence_strength, COUNT(*) as n FROM relations GROUP BY evidence_strength ORDER BY n DESC"
            ).fetchall()
            relations_by_strength = {r["evidence_strength"]: r["n"] for r in strength_rows}
        except Exception:
            relations_by_strength = {}
        
        # Pipeline runs
        try:
            run_rows = conn.execute(
                "SELECT pipeline_name, status, started_at, finished_at, candidate_count, confirmed_count "
                "FROM pipeline_runs ORDER BY started_at DESC LIMIT 5"
            ).fetchall()
            recent_runs = [dict(r) for r in run_rows]
        except Exception:
            recent_runs = []
        
        # Kill switch status
        ks = list_jobs()
        
        return {
            "schema_version": "v2",
            "tables": {
                "internati": internati_count,
                "resource_registry": resource_count,
                "relations": relations_count,
                "claims_v2": claims_count,
                "legacy_quarantine": quarantine_count,
                "pipeline_runs": pipeline_runs,
            },
            "relations_by_status": relations_by_status,
            "relations_by_evidence_strength": relations_by_strength,
            "recent_pipeline_runs": recent_runs,
            "kill_switch": ks,
            "mode": "staging",
        }
    finally:
        conn.close()
        event_conn.close()


@router.get("/events")
async def list_events(
    conflict_code: str | None = Query(None, description="Filter by ww1/ww2/other"),
    limit: int = Query(50, le=200),
):
    """List historical events with provenance metadata."""
    conn = _get_conn()
    
    try:
        # Try v2 table first
        try:
            query = "SELECT id, canonical_name, conflict_code, event_type, start_date, end_date, status FROM historical_events"
            params = []
            if conflict_code:
                query += " WHERE conflict_code = ?"
                params.append(conflict_code)
            query += " ORDER BY start_date NULLS LAST LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            if rows:
                return {"events": [dict(r) for r in rows], "source": "v2"}
        except Exception:
            pass
        
        # Fallback to legacy eventi_1gm in eventi_1gm.db
        event_conn = _get_event_conn()
        query = "SELECT id, nome, data_inizio, data_fine, luogo, descrizione FROM eventi_1gm"
        params = []
        if conflict_code == "ww1":
            query += " WHERE data_inizio LIKE '191%' OR data_inizio LIKE '1914%' OR data_inizio LIKE '1915%' OR data_inizio LIKE '1916%' OR data_inizio LIKE '1917%' OR data_inizio LIKE '1918%'"
        elif conflict_code == "ww2":
            query += " WHERE data_inizio LIKE '193%' OR data_inizio LIKE '194%'"
        query += " ORDER BY data_inizio LIMIT ?"
        params.append(limit)
        
        rows = event_conn.execute(query, params).fetchall()
        return {"events": [dict(r) for r in rows], "source": "legacy_eventi_1gm"}
    finally:
        conn.close()


@router.get("/relations")
async def list_relations(
    status: str = Query("candidate", description="candidate/confirmed/rejected/disputed/legacy_candidate"),
    limit: int = Query(50, le=200),
    relation_type: str | None = None,
):
    """List relations with full provenance metadata."""
    conn = _get_conn()
    
    try:
        query = """
            SELECT r.id, r.source_resource_id, r.target_resource_id,
                   r.relation_type, r.direction, r.status,
                   r.algorithm_name, r.algorithm_version,
                   r.raw_score, r.confidence_calibrated,
                   r.evidence_strength, r.conflict_flags,
                   r.pipeline_run_id, r.created_at, r.reviewed_at,
                   rs.resource_kind as source_kind, rs.source_namespace as source_ns,
                   rt.resource_kind as target_kind, rt.source_namespace as target_ns
            FROM relations r
            LEFT JOIN resource_registry rs ON r.source_resource_id = rs.id
            LEFT JOIN resource_registry rt ON r.target_resource_id = rt.id
            WHERE r.status = ?
        """
        params = [status]
        
        if relation_type:
            query += " AND r.relation_type = ?"
            params.append(relation_type)
        
        query += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        return {
            "relations": [dict(r) for r in rows],
            "count": len(rows),
            "status_filter": status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/kill-switch")
async def kill_switch_status():
    """Show legacy job kill switch status."""
    return {"jobs": list_jobs()}
