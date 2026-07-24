"""Research Engine API — router FastAPI per il motore agentico di ricerca.

Tutti gli endpoint sono tipizzati, paginati, con errori coerenti e
compatibili con gli endpoint esistenti in app.py.

Prefix: /api/research-engine (per evitare collisioni con /api/research esistente)
"""
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

from fastapi import APIRouter, Body, HTTPException, Query

from research_orchestrator import (
    resolve_input, create_research_plan, create_session, run_cycle,
    run_research, record_query, record_result, update_result_status,
    get_session_trace, get_plan_cycles,
)
from claim_service import (
    create_claim, add_evidence, get_claims_for_entity, get_claim_evidence,
    review_claim, get_conflicts, build_timeline, save_narrative,
    get_narratives,
)
from entity_resolution import (
    generate_variants, save_variants, compute_match_score,
    save_match_candidate, review_match, get_match_candidates,
)
from archive_registry import (
    list_connectors, get_connector, get_connector_capabilities,
    health_check_connector, recommend_sources, update_connector,
)
from ai_router import (
    select_model, record_task_run, get_credits_summary,
    check_budget_before_task, health_check_provider,
    get_ai_providers, get_ai_models, get_routing_policy,
)

router = APIRouter(prefix="/api/research-engine", tags=["research-engine"])


# ═══ INPUT RESOLUTION ═════════════════════════════════════════════════════

@router.post("/resolve-input")
def api_resolve_input(body: dict = Body(...)):
    """Risolve l'input dell'utente: identifica entita' e cerca match interni."""
    user_input = body.get("input", "").strip()
    if not user_input:
        raise HTTPException(400, "input mancante")
    return resolve_input(user_input)


# ═══ RESEARCH PLANS ═══════════════════════════════════════════════════════

@router.post("/plans")
def api_create_plan(body: dict = Body(...)):
    """Crea un piano di ricerca."""
    user_input = body.get("input", "").strip()
    if not user_input:
        raise HTTPException(400, "input mancante")
    plan_id = create_research_plan(
        user_input,
        entity_type=body.get("entity_type"),
        entity_id=body.get("entity_id"),
        objective=body.get("objective", ""),
        budget_cycles=body.get("budget_cycles", 10),
        budget_time_seconds=body.get("budget_time_seconds", 300),
        budget_cost_usd=body.get("budget_cost_usd", 5.0),
        generated_by=body.get("generated_by", "user"),
    )
    return {"plan_id": plan_id, "ok": True}


@router.post("/plans/{plan_id}/run")
def api_run_research(plan_id: int, body: dict = Body(default={})):
    """Esegue una ricerca completa per un piano esistente."""
    max_cycles = body.get("max_cycles", 5)
    strategy = body.get("strategy", "balanced")
    session_id = create_session(plan_id)
    cycles = []
    for i in range(1, max_cycles + 1):
        result = run_cycle(plan_id, session_id, i, strategy)
        cycles.append(result)
        if result.get("decision") == "stop":
            break
    return {
        "plan_id": plan_id,
        "session_id": session_id,
        "cycles": cycles,
        "total_cycles": len(cycles),
    }


@router.post("/search")
def api_search(body: dict = Body(...)):
    """Ricerca completa end-to-end da input libero."""
    user_input = body.get("input", "").strip()
    if not user_input:
        raise HTTPException(400, "input mancante")
    max_cycles = body.get("max_cycles", 5)
    strategy = body.get("strategy", "balanced")
    return run_research(user_input, max_cycles=max_cycles, strategy=strategy)


# ═══ SESSIONS ═════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/trace")
def api_session_trace(session_id: int):
    """Traccia completa di una sessione."""
    trace = get_session_trace(session_id)
    if "error" in trace:
        raise HTTPException(404, trace["error"])
    return trace


@router.get("/plans/{plan_id}/cycles")
def api_plan_cycles(plan_id: int):
    """Cicli di un piano."""
    return {"cycles": get_plan_cycles(plan_id)}


@router.post("/sessions/{session_id}/continue")
def api_continue_session(session_id: int, body: dict = Body(default={})):
    """Continua una sessione per un altro ciclo."""
    # Recupera session
    from database import get_conn
    conn = get_conn()
    sess = conn.execute(
        "SELECT * FROM research_sessions WHERE id=?", (session_id,)
    ).fetchone()
    conn.close()
    if not sess:
        raise HTTPException(404, "session not found")
    sess = dict(sess)
    next_cycle = (sess.get("cycle_number") or 0) + 1
    result = run_cycle(sess["plan_id"], session_id, next_cycle,
                       body.get("strategy", "balanced"))
    return result


@router.post("/sessions/{session_id}/stop")
def api_stop_session(session_id: int):
    """Ferma una sessione."""
    from database import get_conn
    conn = get_conn()
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE research_sessions SET status='stopped', completed_at=?, "
        "stop_reason='user_requested' WHERE id=?",
        (now, session_id)
    )
    conn.execute(
        "UPDATE research_plans SET status='stopped', updated_at=? "
        "WHERE id=(SELECT plan_id FROM research_sessions WHERE id=?)",
        (now, session_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "session_id": session_id, "status": "stopped"}


# ═══ QUERIES & RESULTS ════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/queries")
def api_record_query(session_id: int, body: dict = Body(...)):
    """Registra una query."""
    qid = record_query(
        session_id,
        body.get("query_text", ""),
        query_language=body.get("query_language", "it"),
        filters=body.get("filters"),
        variant_used=body.get("variant_used"),
        generated_from_claim_id=body.get("generated_from_claim_id"),
        generated_from_fragment=body.get("generated_from_fragment"),
        priority=body.get("priority", 5),
        motivation=body.get("motivation", ""),
        search_tool=body.get("search_tool"),
        assisted_search_url=body.get("assisted_search_url"),
    )
    return {"query_id": qid, "ok": True}


@router.post("/sessions/{session_id}/results")
def api_record_result(session_id: int, body: dict = Body(...)):
    """Registra un risultato."""
    rid = record_result(
        session_id,
        query_id=body.get("query_id"),
        external_id=body.get("external_id"),
        result_type=body.get("result_type", "search_hit"),
        record_url=body.get("record_url"),
        document_url=body.get("document_url"),
        canonical_url=body.get("canonical_url"),
        title=body.get("title"),
        author_or_entity=body.get("author_or_entity"),
        raw_metadata=body.get("raw_metadata"),
        fingerprint=body.get("fingerprint"),
        source_quality=body.get("source_quality", 0.5),
        authority_score=body.get("authority_score", 0.5),
        independence_group=body.get("independence_group"),
    )
    return {"result_id": rid, "ok": True}


@router.patch("/results/{result_id}")
def api_update_result(result_id: int, body: dict = Body(...)):
    """Aggiorna stato di un risultato."""
    status = body.get("status")
    if not status:
        raise HTTPException(400, "status mancante")
    return update_result_status(result_id, status, body.get("reason", ""))


# ═══ CLAIMS ═══════════════════════════════════════════════════════════════

@router.get("/entities/{entity_type}/{entity_id}/claims")
def api_get_claims(entity_type: str, entity_id: int,
                   epistemic_status: str = None,
                   review_status: str = None):
    """Claim per un'entita'."""
    return {"claims": get_claims_for_entity(
        entity_type, entity_id, epistemic_status, review_status
    )}


@router.post("/claims")
def api_create_claim(body: dict = Body(...)):
    """Crea un claim atomico."""
    result = create_claim(
        subject_type=body.get("subject_type", ""),
        subject_id=body.get("subject_id"),
        subject_label=body.get("subject_label", ""),
        predicate=body.get("predicate", ""),
        object_type=body.get("object_type"),
        object_id=body.get("object_id"),
        object_label=body.get("object_label", ""),
        object_value=body.get("object_value", ""),
        original_value=body.get("original_value", ""),
        temporal_range_start=body.get("temporal_range_start", ""),
        temporal_range_end=body.get("temporal_range_end", ""),
        temporal_precision=body.get("temporal_precision"),
        temporal_uncertainty=body.get("temporal_uncertainty"),
        place=body.get("place", ""),
        epistemic_status=body.get("epistemic_status", "possible"),
        confidence=body.get("confidence", 0.3),
        extraction_method=body.get("extraction_method", "manual"),
        extraction_id=body.get("extraction_id"),
        created_by=body.get("created_by", "user"),
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/claims/{claim_id}/evidence")
def api_get_evidence(claim_id: int):
    """Evidenze di un claim."""
    return {"evidence": get_claim_evidence(claim_id)}


@router.post("/claims/{claim_id}/evidence")
def api_add_evidence(claim_id: int, body: dict = Body(...)):
    """Aggiungi evidenza a un claim."""
    eid = add_evidence(
        claim_id,
        source_id=body.get("source_id"),
        source_table=body.get("source_table"),
        document_id=body.get("document_id"),
        document_table=body.get("document_table"),
        extraction_id=body.get("extraction_id"),
        page_or_frame=body.get("page_or_frame", ""),
        coordinates=body.get("coordinates", ""),
        supporting_quote=body.get("supporting_quote", ""),
        evidence_role=body.get("evidence_role", "supports"),
        source_independence_group=body.get("source_independence_group"),
        strength=body.get("strength", 0.5),
        note=body.get("note", ""),
    )
    return {"evidence_id": eid, "ok": True}


@router.post("/claims/{claim_id}/review")
def api_review_claim(claim_id: int, body: dict = Body(...)):
    """Revisione umana di un claim."""
    decision = body.get("decision")
    if decision not in ("confirmed", "rejected", "under_review"):
        raise HTTPException(400, "decision must be: confirmed, rejected, under_review")
    return review_claim(claim_id, decision, body.get("reviewer", ""),
                        body.get("reason", ""))


@router.get("/entities/{entity_type}/{entity_id}/conflicts")
def api_get_conflicts(entity_type: str, entity_id: int):
    """Conflitti tra claim di un'entita'."""
    return get_conflicts(entity_type, entity_id)


# ═══ TIMELINE & NARRATIVES ════════════════════════════════════════════════

@router.get("/entities/{entity_type}/{entity_id}/timeline")
def api_get_timeline(entity_type: str, entity_id: int):
    """Timeline delle affermazioni documentate."""
    return {"timeline": build_timeline(entity_type, entity_id)}


@router.post("/entities/{entity_type}/{entity_id}/narratives/generate")
def api_generate_narrative(entity_type: str, entity_id: int,
                           body: dict = Body(...)):
    """Genera e salva una narrazione."""
    nid = save_narrative(
        entity_type, entity_id,
        narrative_type=body.get("narrative_type", "biography"),
        structured_text=body.get("structured_text", ""),
        claim_ids=body.get("claim_ids", []),
        gaps=body.get("gaps"),
        deductions=body.get("deductions"),
        confidence_level=body.get("confidence_level", 0.3),
        model_version=body.get("model_version", ""),
        prompt_version=body.get("prompt_version", ""),
        audience=body.get("audience", "public"),
    )
    return {"narrative_id": nid, "ok": True}


@router.get("/entities/{entity_type}/{entity_id}/narratives")
def api_get_narratives(entity_type: str, entity_id: int,
                       narrative_type: str = None):
    """Recupera narrazioni di un'entita'."""
    return {"narratives": get_narratives(entity_type, entity_id, narrative_type)}


# ═══ ENTITY VARIANTS & MATCHES ════════════════════════════════════════════

@router.post("/entities/{entity_type}/{entity_id}/variants")
def api_generate_variants(entity_type: str, entity_id: int,
                          body: dict = Body(...)):
    """Genera e salva varianti per un'entita'."""
    name = body.get("name", "")
    field = body.get("field", "name")
    variants = generate_variants(name, field)
    save_variants(entity_type, entity_id, field, name, variants)
    return {"variants": variants, "count": len(variants)}


@router.get("/entities/{entity_type}/{entity_id}/match-candidates")
def api_get_matches(entity_type: str, entity_id: int):
    """Candidati di match per un'entita'."""
    return {"candidates": get_match_candidates(entity_type, entity_id)}


@router.post("/entity-matches/{match_id}/review")
def api_review_match(match_id: int, body: dict = Body(...)):
    """Revisione umana di un match."""
    decision = body.get("decision")
    if decision not in ("confirmed", "rejected", "open", "omonymy"):
        raise HTTPException(400, "decision must be: confirmed, rejected, open, omonymy")
    return review_match(match_id, decision, body.get("reviewer", ""),
                        body.get("reason", ""))


# ═══ ARCHIVE CONNECTORS ═══════════════════════════════════════════════════

@router.get("/archive-connectors")
def api_list_connectors(status: str = "active"):
    """Lista connector archivio."""
    return {"connectors": list_connectors(status)}


@router.get("/archive-connectors/{code}")
def api_get_connector(code: str):
    """Dettaglio connector."""
    c = get_connector(code)
    if not c:
        raise HTTPException(404, "connector not found")
    return c


@router.get("/archive-connectors/{code}/capabilities")
def api_connector_capabilities(code: str):
    """Capabilities di un connector."""
    caps = get_connector_capabilities(code)
    if "error" in caps:
        raise HTTPException(404, caps["error"])
    return caps


@router.get("/archive-connectors/{code}/health")
def api_connector_health(code: str):
    """Health check di un connector."""
    return health_check_connector(code)


@router.get("/source-registry/recommendations")
def api_source_recommendations(
    entity_type: str = "persona",
    period: str = Query(None),
    geography: str = Query(None),
    nationality: str = Query(None),
    war: str = Query(None),
    gaps: str = Query(None),
):
    """Raccomandazione fonti dinamiche."""
    context = {}
    if period:
        context["period"] = period
    if geography:
        context["geography"] = geography
    if nationality:
        context["nationality"] = nationality
    if war:
        context["war"] = war
    gap_list = gaps.split(",") if gaps else []
    return {"recommendations": recommend_sources(
        entity_type, context, gaps=gap_list
    )}


# ═══ AI PROVIDERS & ROUTER ════════════════════════════════════════════════

@router.get("/ai/providers")
def api_ai_providers():
    """Lista provider IA."""
    return {"providers": get_ai_providers()}


@router.get("/ai/models")
def api_ai_models(provider_code: str = None):
    """Lista modelli IA."""
    return {"models": get_ai_models(provider_code)}


@router.get("/ai/credits")
def api_ai_credits():
    """Riepilogo crediti/budget."""
    return get_credits_summary()


@router.get("/ai/usage")
def api_ai_usage(period: str = None):
    """Usage ledger."""
    from database import get_conn
    conn = get_conn()
    if period:
        rows = conn.execute(
            "SELECT * FROM ai_usage_ledger WHERE period=? ORDER BY updated_at DESC",
            (period,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ai_usage_ledger ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    conn.close()
    return {"usage": [dict(r) for r in rows]}


@router.get("/ai/routing-policies")
def api_routing_policies(task_type: str = None):
    """Policy di routing."""
    if task_type:
        return get_routing_policy(task_type)
    from ai_router import TASK_TYPES
    policies = {}
    for tt in TASK_TYPES:
        policies[tt] = get_routing_policy(tt)
    return {"policies": policies}


@router.post("/ai/providers/{code}/health-check")
def api_ai_health_check(code: str):
    """Health check di un provider IA."""
    return health_check_provider(code)


@router.get("/ai/tasks/{task_id}")
def api_get_task(task_id: int):
    """Dettaglio di un task run."""
    from database import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ai_task_runs WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "task not found")
    return dict(row)
