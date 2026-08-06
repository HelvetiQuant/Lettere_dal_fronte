"""V7 API endpoints — unified research, narration, and system capabilities.

All V7 endpoints are prefixed with /api/v7/ to coexist with legacy endpoints.
Once convergence is complete, legacy endpoints will be deprecated.

Endpoints:
  POST /api/v7/research          — Execute full research pipeline
  GET  /api/v7/research/{run_id} — Get run status and results
  POST /api/v7/narrate           — Generate report from existing snapshot
  GET  /api/v7/system/capabilities — V7 capability snapshot
  GET  /api/v7/health            — V7 health check

V7.3 endpoints:
  POST /api/v7/validate-snapshot  — Semantic validation of evidence snapshot
  POST /api/v7/claim-states       — Determine publishability states for claims
  POST /api/v7/build-response     — Build 11-section final response
  GET  /api/v7/source-quality/{source_key} — Get source quality assessment
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Body
from typing import Optional, Dict, Any, List

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7
from semantic_query_plan import INTENT_TYPES
from evidence_snapshot_v7 import EvidenceSnapshotV7
from source_quality import assess_source_quality, combine_evidence_quality
from semantic_validator import SemanticValidator
from claim_lifecycle import (
    determine_claim_state, filter_publishable_claims,
    build_caveat_summary, ClaimState,
)
from response_structure import ResponseBuilder, SECTION_IDS, SECTION_TITLES

router = APIRouter(prefix="/api/v7", tags=["v7"])

# Singleton orchestrator
_orchestrator: Optional[UnifiedResearchOrchestratorV7] = None


def get_orchestrator() -> UnifiedResearchOrchestratorV7:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = UnifiedResearchOrchestratorV7()
    return _orchestrator


@router.get("/health")
async def health():
    """V7 health check."""
    orch = get_orchestrator()
    return {
        "status": "ok",
        "orchestrator_class": orch.ORCHESTRATOR_CLASS,
        "schema_version": orch.SCHEMA_VERSION,
        "narrator_contract_version": "7.1",
    }


@router.get("/system/capabilities")
async def system_capabilities():
    """V7 system capabilities — reports contract versions and orchestrator class."""
    orch = get_orchestrator()
    return orch.get_capabilities()


@router.post("/research")
async def execute_research(
    user_input: str = Body(..., embed=True),
    intent: str = Body("PERSON_LOOKUP", embed=True),
    target_id: str = Body("", embed=True),
    conflict: str = Body("UNKNOWN", embed=True),
    manifest_hash: str = Body("", embed=True),
    metadata: Optional[Dict[str, Any]] = Body(None, embed=True),
):
    """Execute a full V7 research pipeline.

    This is the single entry point for all research requests.
    Legacy endpoints (/api/research-protocol, /api/research/*) should
    eventually route through here.
    """
    if intent not in INTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid intent: {intent}. Must be one of {INTENT_TYPES}",
        )

    orch = get_orchestrator()
    result = orch.execute(
        user_input=user_input,
        intent=intent,
        target_id=target_id,
        conflict=conflict,
        manifest_hash=manifest_hash,
        metadata=metadata,
    )
    return result


@router.get("/research/{run_id}")
async def get_run_status(run_id: str):
    """Get status and results of a V7 research run."""
    orch = get_orchestrator()
    ctx = orch.get_run(run_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return ctx.to_dict()


@router.post("/narrate")
async def narrate_snapshot(
    snapshot_dict: Dict[str, Any] = Body(...),
):
    """Generate a report from an existing EvidenceSnapshotV7.

    Useful for re-narrating a snapshot with a different AI provider
    or after corrections have been applied.
    """
    try:
        snapshot = EvidenceSnapshotV7.from_dict(snapshot_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid snapshot: {e}")

    orch = get_orchestrator()
    report = orch._deterministic_fallback_report(snapshot)
    return {
        "report": report,
        "snapshot_id": snapshot.snapshot_id,
        "narrator_contract_version": snapshot.narrator_contract_version,
    }


# ─── V7.3 endpoints ──────────────────────────────────────────────────────────

@router.get("/source-quality/{source_key}")
async def get_source_quality(source_key: str):
    """Get multi-dimensional quality assessment for a source."""
    q = assess_source_quality(source_key)
    return q.to_dict()


@router.post("/validate-snapshot")
async def validate_snapshot(
    snapshot_dict: Dict[str, Any] = Body(...),
):
    """Run semantic validation on an evidence snapshot.

    Checks entailment, contradictions, scope violations, and provenance
    for every claim in the snapshot.
    """
    try:
        snapshot = EvidenceSnapshotV7.from_dict(snapshot_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid snapshot: {e}")

    validator = SemanticValidator()
    result = validator.validate_snapshot(snapshot)
    return result.to_dict()


@router.post("/claim-states")
async def compute_claim_states(
    claims: List[Dict[str, Any]] = Body(...),
    identity_status: str = Body("UNRESOLVED_IDENTITY", embed=True),
    evidence_level: str = Body("unverified", embed=True),
):
    """Determine publishability states (PUBLISHED, PUBLISHED_WITH_CAVEAT,
    REVIEW_PENDING, SUPPRESSED) for a list of claims.

    Each claim dict should contain:
      - claim_id
      - evidence_level (optional, overrides global)
      - validation_status (optional, defaults to VALID)
      - has_scope_violation (optional, defaults to False)
      - entailment_score (optional)
      - source_count (optional)
      - is_context_only (optional)
      - has_ocr_uncertainty (optional)
    """
    states = []
    for claim in claims:
        claim_id = claim.get("claim_id", "")
        s = determine_claim_state(
            claim_id=claim_id,
            evidence_level=claim.get("evidence_level", evidence_level),
            identity_status=identity_status,
            validation_status=claim.get("validation_status", "VALID"),
            has_scope_violation=claim.get("has_scope_violation", False),
            entailment_score=claim.get("entailment_score", 0.0),
            source_count=claim.get("source_count", 0),
            is_context_only=claim.get("is_context_only", False),
            has_ocr_uncertainty=claim.get("has_ocr_uncertainty", False),
        )
        states.append(s.to_dict())

    publishable, non_publishable = filter_publishable_claims(
        [ClaimState(**s) for s in states]
    )
    caveat_summary = build_caveat_summary(
        [ClaimState(**s) for s in states]
    )

    return {
        "states": states,
        "publishable_count": len(publishable),
        "non_publishable_count": len(non_publishable),
        "caveat_summary": caveat_summary,
    }


@router.post("/build-response")
async def build_response(
    request_type: str = Body("PERSON", embed=True),
    query: str = Body("", embed=True),
    identity_status: str = Body("UNRESOLVED_IDENTITY", embed=True),
    evidence_level: str = Body("unverified", embed=True),
    claims: List[Dict[str, Any]] = Body(...),
    claim_states: List[Dict[str, Any]] = Body([]),
    validation_errors: List[str] = Body([], embed=True),
    caveat_summary: str = Body("", embed=True),
):
    """Build the 11-section final response from claims and states.

    Returns the structured response with all sections, metadata, and
    optional markdown rendering.
    """
    builder = ResponseBuilder()
    response = builder.build(
        request_type=request_type,
        query=query,
        identity_status=identity_status,
        evidence_level=evidence_level,
        claims=claims,
        claim_states=claim_states,
        validation_errors=validation_errors,
        caveat_summary=caveat_summary,
    )
    result = response.to_dict()
    result["markdown"] = response.to_markdown()
    return result


@router.get("/response-schema")
async def get_response_schema():
    """Get the 11-section response schema definition."""
    return {
        "schema_version": "7.3-response-v1",
        "sections": [
            {"id": sid, "title": SECTION_TITLES.get(sid, sid)}
            for sid in SECTION_IDS
        ],
    }
