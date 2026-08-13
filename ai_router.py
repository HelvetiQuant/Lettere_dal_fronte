"""AI Router — router multi-modello con policy, fallback, budget e crediti.

Sceglie il provider/modello considerando:
- capacita' richieste dal task
- qualita' misurata su quel task
- disponibilita' e stato del provider
- crediti/budget residui
- costo stimato
- dimensione/tipo input
- latenza
- priorita'

Implementa:
- routing per capacita' (task types)
- fallback ordinato e configurabile
- circuit breaker per provider degradati
- stima costo pre-task
- preservazione quota di riserva
- idempotency key per task
- ledger consumi
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from database import get_conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ═══ CIRCUIT BREAKER ═══════════════════════════════════════════════════════

_breaker_state: Dict[str, Dict] = {}
# provider_code -> {"failures": int, "last_failure": float, "open_until": float}

BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN = 300  # 5 minuti


def _breaker_is_open(provider_code: str) -> bool:
    state = _breaker_state.get(provider_code)
    if not state:
        return False
    if state.get("open_until") and time.time() < state["open_until"]:
        return True
    return False


def _breaker_record_failure(provider_code: str):
    state = _breaker_state.setdefault(provider_code, {"failures": 0, "last_failure": 0})
    state["failures"] += 1
    state["last_failure"] = time.time()
    if state["failures"] >= BREAKER_THRESHOLD:
        state["open_until"] = time.time() + BREAKER_COOLDOWN


def _breaker_record_success(provider_code: str):
    if provider_code in _breaker_state:
        _breaker_state[provider_code] = {"failures": 0, "last_failure": 0, "open_until": 0}


# ═══ TASK TYPES ═══════════════════════════════════════════════════════════

TASK_TYPES = {
    "resolve_user_input": {"capabilities": ["text"], "min_quality": 0.6},
    "generate_research_plan": {"capabilities": ["text", "structured_output"], "min_quality": 0.7},
    "select_relevant_sources": {"capabilities": ["text", "structured_output"], "min_quality": 0.6},
    "search_internal_databases": {"capabilities": ["text"], "min_quality": 0.4},
    "generate_followup_queries": {"capabilities": ["text", "structured_output"], "min_quality": 0.6},
    "evaluate_search_cycle": {"capabilities": ["text", "structured_output"], "min_quality": 0.7},
    "decide_continue_or_stop": {"capabilities": ["text", "structured_output"], "min_quality": 0.7},
    "generate_entity_variants": {"capabilities": ["text", "structured_output"], "min_quality": 0.5},
    "extract_document_data": {"capabilities": ["text", "vision", "structured_output"], "min_quality": 0.7},
    "propose_claims": {"capabilities": ["text", "structured_output"], "min_quality": 0.7},
    "compare_claims": {"capabilities": ["text", "structured_output"], "min_quality": 0.8},
    "propose_entity_matches": {"capabilities": ["text", "structured_output"], "min_quality": 0.8},
    "propose_heuristic_links": {"capabilities": ["text", "structured_output"], "min_quality": 0.7},
    "generate_timeline": {"capabilities": ["text", "structured_output"], "min_quality": 0.6},
    "generate_biography": {"capabilities": ["text"], "min_quality": 0.7},
    "generate_viewpoints": {"capabilities": ["text"], "min_quality": 0.8},
    "identify_research_gaps": {"capabilities": ["text", "structured_output"], "min_quality": 0.6},
    "web_search": {"capabilities": ["web_search"], "min_quality": 0.5},
    "ocr": {"capabilities": ["vision", "ocr"], "min_quality": 0.7},
    "verify_citations": {"capabilities": ["text"], "min_quality": 0.6},
    "embeddings": {"capabilities": ["embeddings"], "min_quality": 0.5},
    "narration": {"capabilities": ["text", "structured_output"], "min_quality": 0.7},
}


# ═══ ROUTING ══════════════════════════════════════════════════════════════

def get_routing_policy(task_type: str) -> Optional[Dict]:
    """Recupera la policy di routing per un task type dal DB o dai default."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ai_routing_policies WHERE task_type=?", (task_type,)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return _default_policy(task_type)


_GENERATION_TASKS = {
    "generate_biography", "generate_viewpoints", "generate_timeline",
    "generate_research_plan", "generate_followup_queries",
    "narration",
}

_VALIDATION_TASKS = {
    "compare_claims", "propose_entity_matches", "evaluate_search_cycle",
    "decide_continue_or_stop", "verify_citations",
}


def _default_policy(task_type: str) -> Dict:
    """Policy di default: Ollama per generazione, OpenAI per validazione."""
    task_def = TASK_TYPES.get(task_type, {})
    caps = task_def.get("capabilities", ["text"])

    if "web_search" in caps:
        primary, fallback = "perplexity", ["openai", "anthropic", "mistral", "gemini"]
    elif "vision" in caps and "ocr" in caps:
        primary, fallback = "ollama", ["mistral", "gemini", "openai", "anthropic"]
    elif "embeddings" in caps:
        primary, fallback = "openai", ["gemini", "mistral"]
    elif task_type in _GENERATION_TASKS:
        # Generazione/ragionamento: Ollama (gemma4) primary, Mistral fallback
        primary, fallback = "ollama", ["mistral", "gemini", "anthropic", "openai"]
    elif task_type in _VALIDATION_TASKS:
        # Validazione: OpenAI primary, Mistral fallback
        primary, fallback = "openai", ["mistral", "anthropic", "gemini", "ollama"]
    else:
        primary, fallback = "ollama", ["mistral", "openai", "anthropic", "gemini"]

    return {
        "task_type": task_type,
        "min_requirements_json": json.dumps({"capabilities": caps,
                                              "min_quality": task_def.get("min_quality", 0.5)}),
        "primary_model": primary,
        "fallback_models": json.dumps(fallback),
        "max_cost": 0.50,
        "min_reserve_credit": 5.0,
        "timeout_seconds": 60,
        "max_retries": 2,
        "quality_criterion": "structured_output_valid",
        "version": "default-v1",
    }


def select_model(task_type: str, input_size: int = 0,
                 requires_vision: bool = False,
                 requires_web: bool = False,
                 strategy: str = "balanced") -> Dict:
    """Seleziona il modello migliore per un task.

    strategy: quality_max | balanced | economic
    Returns: {provider_code, model_identifier, reason, policy_version}
    """
    policy = get_routing_policy(task_type)
    caps_required = json.loads(policy.get("min_requirements_json") or "{}").get("capabilities", [])
    if requires_vision:
        caps_required = list(set(caps_required + ["vision"]))
    if requires_web:
        caps_required = list(set(caps_required + ["web_search"]))

    conn = get_conn()

    # Recupera provider attivi
    providers = conn.execute(
        "SELECT * FROM ai_providers WHERE status='active' ORDER BY priority"
    ).fetchall()

    candidates = []
    for p in providers:
        p = dict(p)
        if _breaker_is_open(p["code"]):
            continue

        # Verifica capacita'
        declared_caps = json.loads(p.get("declared_capabilities_json") or "[]")
        if not all(c in declared_caps for c in caps_required):
            continue

        # Verifica budget
        budget = p.get("budget_configured", 50.0)
        reserve = p.get("budget_reserve", 5.0)
        # Stima consumo (semplificata)
        estimated_cost = _estimate_cost(p["code"], task_type, input_size)
        available = budget - reserve
        if estimated_cost > available:
            continue

        # Recupera modelli
        models = conn.execute(
            "SELECT * FROM ai_models WHERE provider_id=? AND status='enabled' "
            "ORDER BY quality_score DESC",
            (p["id"],)
        ).fetchall()

        for m in models:
            m = dict(m)
            model_caps = json.loads(m.get("capabilities_json") or "[]")
            if not all(c in model_caps for c in caps_required):
                continue

            quality = m.get("quality_score", 0.5)
            cost = m.get("cost_per_unit", 0.0)
            latency = m.get("latency_score", 0.5)

            # Score combinato secondo strategy
            if strategy == "quality_max":
                combined = quality * 0.7 + (1 - cost / 10) * 0.2 + (1 - latency) * 0.1
            elif strategy == "economic":
                combined = (1 - cost / 10) * 0.6 + quality * 0.3 + (1 - latency) * 0.1
            else:  # balanced
                combined = quality * 0.4 + (1 - cost / 10) * 0.3 + (1 - latency) * 0.3

            candidates.append({
                "provider_code": p["code"],
                "provider_id": p["id"],
                "model_id": m["id"],
                "model_identifier": m["model_identifier"],
                "quality": quality,
                "cost": cost,
                "latency": latency,
                "combined_score": combined,
                "estimated_cost": estimated_cost,
            })

    conn.close()

    if not candidates:
        return {
            "provider_code": None,
            "model_identifier": None,
            "reason": "no_model_available",
            "policy_version": policy.get("version", "default"),
        }

    # V7.4: Respect policy primary_model_id if specified
    primary_provider = policy.get("primary_model_id")
    if primary_provider:
        primary_candidates = [c for c in candidates if c["provider_code"] == primary_provider]
        if primary_candidates:
            best = primary_candidates[0]  # Already sorted by quality_score DESC
            return {
                "provider_code": best["provider_code"],
                "model_identifier": best["model_identifier"],
                "model_id": best["model_id"],
                "reason": f"policy_primary={primary_provider} "
                          f"(quality={best['quality']}, cost={best['cost']})",
                "policy_version": policy.get("version", "default"),
                "estimated_cost": best["estimated_cost"],
            }

    # Fallback: best combined score
    candidates.sort(key=lambda x: x["combined_score"], reverse=True)
    best = candidates[0]
    return {
        "provider_code": best["provider_code"],
        "model_identifier": best["model_identifier"],
        "model_id": best["model_id"],
        "reason": f"best_combined_score={best['combined_score']:.3f} "
                  f"(quality={best['quality']}, cost={best['cost']}, latency={best['latency']})",
        "policy_version": policy.get("version", "default"),
        "estimated_cost": best["estimated_cost"],
    }


def _estimate_cost(provider_code: str, task_type: str, input_size: int) -> float:
    """Stima il costo di un task."""
    # Stima token basata su input_size
    est_tokens = max(1000, input_size // 4 + 500)  # ~4 char/token + output
    cost_per_1k = {
        "openai": 0.001,
        "anthropic": 0.003,
        "mistral": 0.001,
        "perplexity": 0.002,
        "gemini": 0.001,
        "lmstudio": 0.0,
        "ollama": 0.0,
    }
    rate = cost_per_1k.get(provider_code, 0.002)
    return est_tokens / 1000 * rate


# ═══ TASK RUN RECORDING ═══════════════════════════════════════════════════

def record_task_run(
    task_type: str,
    provider_code: str,
    model_identifier: str,
    selection_reason: str = "",
    policy_version: str = "",
    input_fingerprint: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_estimated: float = 0.0,
    cost_actual: float = None,
    credit_before: str = "unknown",
    credit_after: str = "unknown",
    latency_ms: int = 0,
    outcome: str = "success",
    validation_result: Dict = None,
    fallback_from: str = None,
    fallback_to: str = None,
    idempotency_key: str = None,
    research_plan_id: int = None,
    session_id: int = None,
    cycle_id: int = None,
) -> int:
    """Registra un task run nel database."""
    conn = get_conn()
    now = _now()
    conn.execute(
        """INSERT INTO ai_task_runs (
            research_plan_id, session_id, cycle_id, task_type,
            provider_code, model_identifier, selection_reason,
            policy_version, input_fingerprint, input_tokens, output_tokens,
            cost_estimated, cost_actual, credit_before, credit_after,
            latency_ms, outcome, validation_result_json,
            fallback_from, fallback_to, idempotency_key, created_at, completed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (research_plan_id, session_id, cycle_id, task_type,
         provider_code, model_identifier, selection_reason,
         policy_version, input_fingerprint, input_tokens, output_tokens,
         cost_estimated, cost_actual, credit_before, credit_after,
         latency_ms, outcome, json.dumps(validation_result) if validation_result else None,
         fallback_from, fallback_to, idempotency_key, now, now)
    )
    run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Aggiorna ledger
    if cost_actual is not None:
        period = now[:7]  # YYYY-MM
        conn.execute(
            "INSERT INTO ai_usage_ledger (provider_code, model_identifier, period, "
            "units_consumed, cost, data_source, task_run_id, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (provider_code, model_identifier, period,
             input_tokens + output_tokens, cost_actual, "internal_estimate",
             run_id, now)
        )

    conn.commit()
    conn.close()

    # Circuit breaker
    if outcome == "success":
        _breaker_record_success(provider_code)
    else:
        _breaker_record_failure(provider_code)

    return run_id


# ═══ CREDITS ══════════════════════════════════════════════════════════════

def get_credits_summary() -> Dict:
    """Riepilogo crediti/budget per tutti i provider."""
    conn = get_conn()
    providers = conn.execute(
        "SELECT * FROM ai_providers WHERE status='active' ORDER BY priority"
    ).fetchall()
    result = []
    for p in providers:
        p = dict(p)
        # Consumo del mese corrente
        now = _now()
        period = now[:7]
        spent_row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) as total FROM ai_usage_ledger "
            "WHERE provider_code=? AND period=?",
            (p["code"], period)
        ).fetchone()
        spent = spent_row[0] if spent_row else 0
        budget = p.get("budget_configured", 50.0)
        reserve = p.get("budget_reserve", 5.0)
        available = budget - spent
        credit_method = p.get("credit_detection_method", "unknown")

        result.append({
            "provider_code": p["code"],
            "name": p["name"],
            "budget_configured": budget,
            "budget_reserve": reserve,
            "spent_this_month": round(spent, 4),
            "available": round(available - reserve, 4),
            "credit_status": "real" if credit_method == "api_header" else "estimated",
            "credit_value": "unknown" if credit_method == "unknown" else available,
        })
    conn.close()
    return {"providers": result}


def check_budget_before_task(provider_code: str, estimated_cost: float) -> Dict:
    """Verifica se c'e' budget sufficiente per un task."""
    conn = get_conn()
    p = conn.execute(
        "SELECT * FROM ai_providers WHERE code=?", (provider_code,)
    ).fetchone()
    conn.close()
    if not p:
        return {"ok": False, "reason": "provider_not_found"}
    p = dict(p)
    now = _now()
    period = now[:7]
    conn = get_conn()
    spent_row = conn.execute(
        "SELECT COALESCE(SUM(cost), 0) as total FROM ai_usage_ledger "
        "WHERE provider_code=? AND period=?",
        (provider_code, period)
    ).fetchone()
    conn.close()
    spent = spent_row[0] if spent_row else 0
    budget = p.get("budget_configured", 50.0)
    reserve = p.get("budget_reserve", 5.0)
    available = budget - spent - reserve
    if estimated_cost > available and estimated_cost > 0:
        return {"ok": False, "reason": "insufficient_budget",
                "available": available, "estimated": estimated_cost,
                "reserve": reserve}
    return {"ok": True, "available": available, "estimated": estimated_cost}


# ═══ HEALTH CHECK ═════════════════════════════════════════════════════════

def health_check_provider(provider_code: str) -> Dict:
    """Verifica lo stato di salute di un provider."""
    conn = get_conn()
    p = conn.execute(
        "SELECT * FROM ai_providers WHERE code=?", (provider_code,)
    ).fetchone()
    conn.close()
    if not p:
        return {"ok": False, "error": "provider not found"}
    p = dict(p)

    breaker_open = _breaker_is_open(provider_code)
    now = _now()

    # Aggiorna last_health_check
    conn = get_conn()
    conn.execute(
        "UPDATE ai_providers SET last_health_check=? WHERE code=?",
        (now, provider_code)
    )
    conn.commit()
    conn.close()

    return {
        "ok": not breaker_open,
        "provider_code": provider_code,
        "status": p.get("status"),
        "breaker_open": breaker_open,
        "last_health_check": now,
    }


def get_ai_providers() -> List[Dict]:
    """Lista tutti i provider IA."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ai_providers ORDER BY priority"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ai_models(provider_code: str = None) -> List[Dict]:
    """Lista modelli IA, opzionalmente filtrati per provider."""
    conn = get_conn()
    if provider_code:
        rows = conn.execute(
            "SELECT m.*, p.code as provider_code FROM ai_models m "
            "JOIN ai_providers p ON m.provider_id = p.id "
            "WHERE p.code=? ORDER BY m.quality_score DESC",
            (provider_code,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.*, p.code as provider_code FROM ai_models m "
            "JOIN ai_providers p ON m.provider_id = p.id "
            "ORDER BY p.priority, m.quality_score DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
