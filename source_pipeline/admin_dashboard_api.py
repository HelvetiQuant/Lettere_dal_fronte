"""Admin Dashboard API — endpoint di amministrazione per monitorare e gestire
lo stato del sistema: providers, claims, evidence, job queue, golden dataset,
shadow migration, consumer adapter.

Endpoint:
  GET /api/admin/dashboard          — KPI riassuntivi
  GET /api/admin/providers          — lista provider con stats
  GET /api/admin/claims             — lista claim con filtri
  GET /api/admin/claims/{id}        — dettaglio claim con evidence
  PATCH /api/admin/claims/{id}      — aggiorna claim_status
  GET /api/admin/evidence           — lista evidence con filtri
  GET /api/admin/jobs               — job queue status
  GET /api/admin/golden-dataset     — golden dataset validation
  GET /api/admin/migration-status   — shadow migration status
  GET /api/admin/external-items     — external items con filtri
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

load_dotenv()

log = logging.getLogger("admin_dashboard")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Helpers ────────────────────────────────────────────────────────────────

def _exec_sql_returning(sql: str) -> list:
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql_returning"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=60)
    if r.status_code in (200, 201, 204):
        try:
            data = r.json()
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []
    log.error("exec_sql_returning failed: %s", r.text[:500])
    return []


def _execute_sql(sql: str) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=60)
    if r.status_code in (200, 201, 204):
        return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


# ─── Models ─────────────────────────────────────────────────────────────────

class ClaimUpdate(BaseModel):
    claim_status: Optional[str] = None
    conflict_code: Optional[str] = None


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def admin_dashboard():
    """KPI riassuntivi del sistema."""
    sql = """
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            (SELECT COUNT(*) FROM archive.providers) AS provider_count,
            (SELECT COUNT(*) FROM archive.external_items) AS external_item_count,
            (SELECT COUNT(*) FROM evidence.claims) AS claim_count,
            (SELECT COUNT(*) FROM evidence.evidence) AS evidence_count,
            (SELECT COUNT(*) FROM evidence.editorial_decisions) AS editorial_decision_count,
            (SELECT COUNT(*) FROM ops.job_queue) AS job_count,
            (SELECT COUNT(*) FROM ops.job_queue WHERE status = 'running') AS jobs_running,
            (SELECT COUNT(*) FROM ops.job_queue WHERE status = 'failed') AS jobs_failed,
            (SELECT COUNT(*) FROM ops.job_queue WHERE status = 'completed') AS jobs_completed,
            (SELECT COUNT(*) FROM evidence.claims WHERE claim_status = 'discovered') AS claims_discovered,
            (SELECT COUNT(*) FROM evidence.claims WHERE claim_status = 'candidate') AS claims_candidate,
            (SELECT COUNT(*) FROM evidence.claims WHERE claim_status = 'supported') AS claims_supported,
            (SELECT COUNT(*) FROM evidence.claims WHERE claim_status = 'verified') AS claims_verified,
            (SELECT COUNT(*) FROM evidence.claims WHERE claim_status = 'rejected') AS claims_rejected,
            (SELECT COUNT(*) FROM evidence.evidence WHERE review_status = 'pending') AS evidence_pending,
            (SELECT COUNT(*) FROM evidence.evidence WHERE review_status = 'accepted') AS evidence_accepted,
            (SELECT COUNT(*) FROM evidence.evidence WHERE review_status = 'rejected') AS evidence_rejected
    ) x;
    """
    rows = _exec_sql_returning(sql)
    if rows and rows[0]:
        return rows[0]
    return {"error": "Unable to fetch dashboard data"}


@router.get("/providers")
async def admin_providers(
    active_only: bool = Query(False, description="Solo provider attivi"),
):
    """Lista provider con statistiche."""
    where = "WHERE enabled = true" if active_only else ""
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            p.id, p.provider_code, p.provider_name, p.authority_class, p.access_mode,
            p.independence_group, p.enabled,
            (SELECT COUNT(*) FROM archive.external_items ei
             WHERE ei.provider_id = p.id) AS item_count,
            (SELECT COUNT(*) FROM evidence.evidence ev
             JOIN archive.external_items ei ON ei.id = ev.source_item_id
             WHERE ei.provider_id = p.id) AS evidence_count
        FROM archive.providers p
        {where}
        ORDER BY p.provider_code
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return rows if rows else []


@router.get("/claims")
async def admin_claims(
    status: Optional[str] = Query(None, description="Filtra per claim_status"),
    predicate: Optional[str] = Query(None, description="Filtra per predicate"),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """Lista claim con filtri e paginazione."""
    conditions = []
    if status:
        conditions.append(f"c.claim_status = '{status}'")
    if predicate:
        conditions.append(f"c.predicate = '{predicate}'")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            c.id, c.stable_id, c.predicate, c.claim_status,
            c.object_value, c.valid_from::text, c.valid_to::text,
            c.conflict_code, c.created_at::text, c.updated_at::text,
            e_s.name AS subject_name,
            e_o.name AS object_name,
            (SELECT COUNT(*) FROM evidence.evidence ev WHERE ev.claim_id = c.id) AS evidence_count,
            (SELECT ed.decision FROM evidence.editorial_decisions ed
             WHERE ed.claim_id = c.id ORDER BY ed.decided_at DESC LIMIT 1) AS latest_decision
        FROM evidence.claims c
        LEFT JOIN core.entities e_s ON e_s.id = c.subject_entity_id
        LEFT JOIN core.entities e_o ON e_o.id = c.object_entity_id
        WHERE {where}
        ORDER BY c.updated_at DESC
        LIMIT {limit} OFFSET {offset}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return rows if rows else []


@router.get("/claims/{claim_id}")
async def admin_claim_detail(claim_id: int):
    """Dettaglio claim con evidence e editorial decisions."""
    # Claim
    claim_sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            c.id, c.stable_id, c.predicate, c.claim_status,
            c.object_value, c.valid_from::text, c.valid_to::text,
            c.conflict_code, c.extraction_method, c.pipeline_run_id,
            c.created_at::text, c.updated_at::text,
            e_s.name AS subject_name, e_s.entity_type AS subject_type,
            e_o.name AS object_name, e_o.entity_type AS object_type
        FROM evidence.claims c
        LEFT JOIN core.entities e_s ON e_s.id = c.subject_entity_id
        LEFT JOIN core.entities e_o ON e_o.id = c.object_entity_id
        WHERE c.id = {claim_id}
    ) x;
    """
    claim_rows = _exec_sql_returning(claim_sql)
    if not claim_rows or not claim_rows[0]:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    claim = claim_rows[0]

    # Evidence
    ev_sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            ev.id, ev.evidence_type, ev.text_span, ev.normalized_value,
            ev.review_status, ev.human_verified, ev.independence_group,
            ev.page_or_canvas, ev.line_or_region, ev.ocr_confidence,
            ev.created_at::text,
            ei.title AS source_item_title,
            ei.canonical_url AS source_item_url,
            p.provider_code AS provider_code
        FROM evidence.evidence ev
        LEFT JOIN archive.external_items ei ON ei.id = ev.source_item_id
        LEFT JOIN archive.providers p ON p.id = ei.provider_id
        WHERE ev.claim_id = {claim_id}
        ORDER BY ev.id
    ) x;
    """
    evidence = _exec_sql_returning(ev_sql)

    # Editorial decisions
    ed_sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            ed.id, ed.decision, ed.reviewer_id, ed.reason,
            ed.decided_at::text
        FROM evidence.editorial_decisions ed
        WHERE ed.claim_id = {claim_id}
        ORDER BY ed.decided_at DESC
    ) x;
    """
    decisions = _exec_sql_returning(ed_sql)

    return {
        "claim": claim,
        "evidence": evidence if evidence else [],
        "editorial_decisions": decisions if decisions else [],
    }


@router.patch("/claims/{claim_id}")
async def admin_update_claim(claim_id: int, update: ClaimUpdate):
    """Aggiorna claim_status o conflict_code di una claim."""
    sets = []
    if update.claim_status:
        valid_statuses = ['discovered', 'ingested', 'candidate', 'supported',
                          'verified', 'conflicting', 'rejected', 'superseded', 'legacy_unverified']
        if update.claim_status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid claim_status. Valid: {valid_statuses}")
        sets.append(f"claim_status = '{update.claim_status}'")
    if update.conflict_code is not None:
        cc = update.conflict_code.replace("'", "''")
        sets.append(f"conflict_code = '{cc}'")

    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets.append("updated_at = now()")
    set_clause = ", ".join(sets)
    sql = f"UPDATE evidence.claims SET {set_clause} WHERE id = {claim_id};"
    result = _execute_sql(sql)
    if isinstance(result, dict) and result.get("ok"):
        return {"ok": True, "claim_id": claim_id, "updated": update.dict(exclude_none=True)}
    raise HTTPException(status_code=500, detail=f"Update failed: {result}")


@router.get("/evidence")
async def admin_evidence(
    review_status: Optional[str] = Query(None),
    claim_id: Optional[int] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """Lista evidence con filtri."""
    conditions = []
    if review_status:
        conditions.append(f"ev.review_status = '{review_status}'")
    if claim_id:
        conditions.append(f"ev.claim_id = {claim_id}")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            ev.id, ev.claim_id, ev.evidence_type, ev.text_span,
            ev.normalized_value, ev.review_status, ev.human_verified,
            ev.independence_group, ev.ocr_confidence,
            ev.created_at::text,
            c.predicate AS claim_predicate,
            c.claim_status AS claim_status,
            ei.title AS source_item_title,
            p.provider_code AS provider_code
        FROM evidence.evidence ev
        LEFT JOIN evidence.claims c ON c.id = ev.claim_id
        LEFT JOIN archive.external_items ei ON ei.id = ev.source_item_id
        LEFT JOIN archive.providers p ON p.id = ei.provider_id
        WHERE {where}
        ORDER BY ev.created_at DESC
        LIMIT {limit} OFFSET {offset}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return rows if rows else []


@router.get("/jobs")
async def admin_jobs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Job queue status."""
    where = f"WHERE status = '{status}'" if status else ""
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            j.id, j.job_type, j.status, j.priority,
            j.attempts, j.max_attempts, j.created_at::text,
            j.started_at::text, j.completed_at::text,
            j.last_error, j.idempotency_key,
            p.provider_code AS provider_code
        FROM ops.job_queue j
        LEFT JOIN archive.providers p ON p.id = j.provider_id
        {where}
        ORDER BY j.created_at DESC
        LIMIT {limit}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return rows if rows else []


@router.get("/golden-dataset")
async def admin_golden_dataset():
    """Golden dataset validation status."""
    from golden_dataset import validate_golden_dataset, GOLDEN_CASES
    results = validate_golden_dataset()
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "cases": results,
    }


@router.get("/external-items")
async def admin_external_items(
    provider_code: Optional[str] = Query(None),
    item_type: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """External items con filtri."""
    conditions = []
    if provider_code:
        conditions.append(f"i.provider_code = '{provider_code}'")
    if item_type:
        conditions.append(f"i.item_type = '{item_type}'")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            i.id, i.stable_id, i.provider_code, i.external_id,
            i.item_type, i.title, i.description,
            i.canonical_url, i.access_status, i.review_status,
            i.created_at::text, i.updated_at::text,
            p.provider_name AS provider_name
        FROM archive.external_items i
        LEFT JOIN archive.providers p ON p.id = i.provider_id
        WHERE {where}
        ORDER BY i.id DESC
        LIMIT {limit} OFFSET {offset}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return rows if rows else []


@router.get("/migration-status")
async def admin_migration_status():
    """Shadow migration status — conteggi fonti_indice vs external_items."""
    # Count from SQLite
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent / "imi_internati.db"
    sqlite_count = 0
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()
            sqlite_count = row[0] if row else 0
        except Exception:
            pass
        finally:
            conn.close()

    # Count from Supabase
    sb_sql = """
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            COUNT(*) AS total_items,
            COUNT(*) FILTER (WHERE item_type = 'archival_source') AS archival_sources,
            COUNT(*) FILTER (WHERE provider_code IS NOT NULL) AS with_provider
        FROM archive.external_items
    ) x;
    """
    rows = _exec_sql_returning(sb_sql)
    supabase_stats = rows[0] if rows and rows[0] else {}

    return {
        "sqlite_fonti_indice": sqlite_count,
        "supabase_external_items": supabase_stats.get("total_items", 0),
        "migration_progress": round(
            (supabase_stats.get("total_items", 0) / sqlite_count * 100) if sqlite_count > 0 else 0, 2
        ),
        "supabase_breakdown": supabase_stats,
    }
