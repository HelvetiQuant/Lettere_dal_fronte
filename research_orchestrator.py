"""Research Orchestrator — motore agentico di ricerca multi-fonte.

Implementa il ciclo Plan-Retrieve-Extract-Resolve-Validate-Expand-Stop:
  Plan     — stabilisce cosa cercare e dove
  Retrieve — usa gli strumenti disponibili (DB interni, API, web)
  Extract  — ricava frammenti strutturati
  Resolve  — valuta identita' ed entita'
  Validate — confronta le fonti
  Expand   — genera nuove piste e query
  Stop     — applica criteri espliciti
  Synthesize — produce la ricostruzione

Ogni passaggio e' idempotente, osservabile, ripetibile e non distruttivo.
L'orchestratore conserva lo stato della ricerca, sa perche' ha interrogato
una fonte e puo' spiegare perche' ha interrotto o proseguito.

L'IA non puo' inventare risultati: ogni risultato proviene da una chiamata
reale a uno strumento, da un record interno o da un apporto umano tracciato.
"""
import hashlib
import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from database import get_conn, search_all
from search_service import search_entities, get_entity_network
from claim_service import (
    create_claim, add_evidence, detect_conflicts, build_timeline,
    save_narrative, get_claims_for_entity,
)
from entity_resolution import (
    generate_variants, compute_match_score, save_match_candidate,
    save_variants, normalize_name,
)
from archive_registry import recommend_sources, get_connector
from ai_router import select_model, record_task_run, check_budget_before_task
from ai_client import call_ai, call_ai_json, is_any_provider_available
from fact_extractor import (
    extract_claims_from_record, extract_claims_from_text_ai,
    extract_claims_from_fragments, extract_facts_for_entity,
    auto_build_timeline,
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ═══ INPUT RESOLUTION ═════════════════════════════════════════════════════

def resolve_input(user_input: str) -> Dict:
    """Risolve l'input dell'utente: identifica tipo entita' e cerca match interni.

    Ritorna:
    - entity_type: persona | evento | luogo | reparto | campo | organizzazione | documento
    - entity_id: id se trovato nel DB
    - candidates: lista di candidati trovati
    - is_new: True se nessun match esatto
    - context: indizi estratti (periodo, luogo, reparto, ecc.)
    """
    user_input = (user_input or "").strip()
    if not user_input:
        return {"error": "input vuoto"}

    # Estrai indizi (riusa memory_router se disponibile)
    context = _extract_context(user_input)

    # Determina tipo entita' da euristiche
    entity_type = _guess_entity_type(user_input, context)

    # Cerca nei DB interni
    candidates = []

    # 1. Ricerca esatta per nome su entita
    try:
        conn = get_conn()
        if entity_type == "persona":
            # Cerca in internati, caduti, decorati
            parts = user_input.split()
            cognome = parts[0] if parts else user_input
            nome = " ".join(parts[1:]) if len(parts) > 1 else ""
            for table in ["internati", "caduti_albooro", "decorati"]:
                if not _table_exists(conn, table):
                    continue
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE "
                    f"(cognome LIKE ? OR nominativo LIKE ?) "
                    f"LIMIT 10",
                    (f"{cognome}%", f"{user_input}%")
                ).fetchall()
                for r in rows:
                    r = dict(r)
                    candidates.append({
                        "table": table,
                        "id": r.get("id"),
                        "label": r.get("nominativo") or f"{r.get('cognome','')} {r.get('nome','')}",
                        "score": 1.0 if r.get("cognome","").lower() == cognome.lower() else 0.7,
                        "source": "internal_db",
                    })
        elif entity_type == "evento":
            # Cerca in eventi_1gm
            edb = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='eventi_1gm'"
            ).fetchone()
            if edb:
                rows = conn.execute(
                    "SELECT id, nome, descrizione FROM eventi_1gm "
                    "WHERE nome LIKE ? OR descrizione LIKE ? LIMIT 10",
                    (f"%{user_input}%", f"%{user_input}%")
                ).fetchall()
                for r in rows:
                    r = dict(r)
                    candidates.append({
                        "table": "eventi_1gm",
                        "id": r["id"],
                        "label": r["nome"],
                        "score": 0.8,
                        "source": "internal_db",
                    })
        conn.close()
    except Exception as e:
        candidates.append({"error": f"internal_search: {e}"})

    # 2. FTS search su entita
    try:
        fts_results = search_entities(user_input, limit=10)
        for r in fts_results:
            candidates.append({
                "table": r.get("fonte_tabella", "entita"),
                "id": r.get("fonte_id") or r.get("entita_id"),
                "label": r.get("valore") or r.get("nome") or user_input,
                "score": 0.5 + (r.get("rank", 0) * 0.3),
                "source": "fts",
                "entity_type": r.get("tipo"),
            })
    except Exception:
        pass

    # Deduplica candidati
    seen = set()
    unique_candidates = []
    for c in candidates:
        key = f"{c.get('table')}:{c.get('id')}"
        if key not in seen and "error" not in c:
            seen.add(key)
            unique_candidates.append(c)

    is_new = len(unique_candidates) == 0
    entity_id = unique_candidates[0]["id"] if unique_candidates and not is_new else None

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "candidates": unique_candidates[:20],
        "is_new": is_new,
        "context": context,
        "input": user_input,
    }


def _extract_context(text: str) -> Dict:
    """Estrae indizi dal testo: date, luoghi, reparti, parole chiave."""
    context = {}

    # Date
    date_match = re.search(r"\b(1[89]\d{2})\b", text)
    if date_match:
        year = int(date_match.group(1))
        context["period"] = "ww1" if year < 1939 else "ww2"
        context["year"] = year

    # Luoghi (semplificato)
    place_patterns = [
        r"\b(?:a|ad|in|presso)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ]
    for pat in place_patterns:
        m = re.search(pat, text)
        if m:
            context["geography"] = m.group(1)
            break

    # Reparti
    unit_match = re.search(r"\b(\d+[°\.\s]*(?:divisione|reggimento|battaglione|brigata))", text, re.I)
    if unit_match:
        context["unit"] = unit_match.group(1)

    # Campi
    camp_match = re.search(r"\b(stalag|stalag\s+[ivxlc]+|oflag|marlag|ilag)\s*([a-z])?", text, re.I)
    if camp_match:
        context["camp"] = camp_match.group(0)

    # Nazionalita'
    if any(w in text.lower() for w in ["italia", "italian", "imi", "internati militari"]):
        context["nationality"] = "italian"
    elif any(w in text.lower() for w in ["german", "tedesco", "deutsch"]):
        context["nationality"] = "german"
    elif any(w in text.lower() for w in ["british", "uk", "commonwealth"]):
        context["nationality"] = "british"

    return context


def _guess_entity_type(text: str, context: Dict) -> str:
    """Euristica per determinare il tipo di entita'."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["battaglia", "battle", "operazione", "operation",
                                      "offensiva", "sbarco", "assalto", "evento"]):
        return "evento"
    if any(w in text_lower for w in ["stalag", "oflag", "campo", "lager", "prigione"]):
        return "campo"
    if any(w in text_lower for w in ["divisione", "reggimento", "battaglione",
                                      "brigata", "reparto", "unita"]):
        return "reparto"
    if any(w in text_lower for w in ["chiesa", "comune", "citta", "paese", "regione"]):
        return "luogo"
    if any(w in text_lower for w in ["azienda", "societa", "fabbrica", "industria"]):
        return "organizzazione"
    if any(w in text_lower for w in ["lettera", "diario", "documento", "rapporto"]):
        return "documento"
    # Default: persona (nome e cognome)
    return "persona"


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ═══ RESEARCH PLAN ════════════════════════════════════════════════════════

def create_research_plan(
    user_input: str,
    entity_type: str = None,
    entity_id: int = None,
    objective: str = "",
    budget_cycles: int = 10,
    budget_time_seconds: int = 300,
    budget_cost_usd: float = 5.0,
    generated_by: str = "system",
) -> int:
    """Crea un piano di ricerca."""
    conn = get_conn()
    now = _now()
    resolution = resolve_input(user_input) if not entity_type else {
        "entity_type": entity_type, "entity_id": entity_id,
        "context": _extract_context(user_input), "input": user_input,
    }

    gaps = _identify_initial_gaps(resolution)
    context_json = json.dumps(resolution.get("context", {}))

    conn.execute(
        """INSERT INTO research_plans (
            original_input, entity_type, entity_id, objective,
            initial_context, gaps_to_fill, budget_cycles,
            budget_time_seconds, budget_cost_usd, status,
            generated_by, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_input, resolution.get("entity_type"), resolution.get("entity_id"),
         objective or f"Ricerca su: {user_input}",
         context_json, json.dumps(gaps),
         budget_cycles, budget_time_seconds, budget_cost_usd,
         "active", generated_by, now, now)
    )
    plan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return plan_id


def _identify_initial_gaps(resolution: Dict) -> List[str]:
    """Identifica lacune iniziali dalla risoluzione dell'input."""
    gaps = []
    ctx = resolution.get("context", {})
    if resolution.get("is_new"):
        gaps.append("identity_verification")
    if not ctx.get("year"):
        gaps.append("date")
    if not ctx.get("geography"):
        gaps.append("place")
    if not ctx.get("unit"):
        gaps.append("military_unit")
    if not ctx.get("camp"):
        gaps.append("camp")
    if not ctx.get("nationality"):
        gaps.append("nationality")
    gaps.append("biography")
    gaps.append("sources")
    return gaps


# ═══ RESEARCH SESSION ═════════════════════════════════════════════════════

def create_session(plan_id: int, connector_id: int = None,
                   mode: str = "auto") -> int:
    """Crea una sessione di ricerca per un piano."""
    conn = get_conn()
    now = _now()
    conn.execute(
        """INSERT INTO research_sessions (
            plan_id, connector_id, mode, status, started_at, created_at
        ) VALUES (?,?,?,?,?,?)""",
        (plan_id, connector_id, mode, "running", now, now)
    )
    session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return session_id


# ═══ RESEARCH CYCLE ═══════════════════════════════════════════════════════

def run_cycle(plan_id: int, session_id: int, cycle_number: int,
              strategy: str = "balanced") -> Dict:
    """Esegue un ciclo di ricerca: Plan-Retrieve-Extract-Validate-Expand.

    Ritorna il risultato del ciclo con decisione continue/stop.
    """
    conn = get_conn()
    now = _now()

    # Recupera piano
    plan = conn.execute(
        "SELECT * FROM research_plans WHERE id=?", (plan_id,)
    ).fetchone()
    conn.close()
    if not plan:
        return {"error": "plan not found"}
    plan = dict(plan)

    context = json.loads(plan.get("initial_context") or "{}")
    gaps = json.loads(plan.get("gaps_to_fill") or "[]")
    entity_type = plan.get("entity_type")
    entity_id = plan.get("entity_id")
    user_input = plan.get("original_input", "")

    # ─── 1. PLAN: seleziona fonti pertinenti ───────────────────────────────
    recommended = recommend_sources(
        entity_type or "persona", context, clues=[], gaps=gaps
    )

    # ─── 2. RETRIEVE: ricerca interna ─────────────────────────────────────
    internal_results = _search_internal(user_input, context, entity_type, entity_id)

    # ─── 2b. RETRIEVE: ricerca esterna (federated) ────────────────────────
    external_results = []
    try:
        from source_providers.federation import federated_search
        fed = federated_search(user_input, cues=context)
        for r in fed[:10]:
            external_results.append({
                "type": "federated",
                "provider": r.get("provider"),
                "title": r.get("titolo") or r.get("title"),
                "url": r.get("catalog_url") or r.get("url"),
                "score": r.get("score", 0.3),
            })
    except Exception:
        pass

    # ─── 3. EXTRACT: frammenti strutturati ────────────────────────────────
    fragments = _extract_fragments(internal_results, external_results, context)

    # ─── 4. RESOLVE: entity resolution ────────────────────────────────────
    if entity_id and entity_type:
        variants = generate_variants(user_input)
        save_variants(entity_type, entity_id, "name", user_input, variants)

    # ─── 5. VALIDATE: conflitti ───────────────────────────────────────────
    conflicts = []
    if entity_id and entity_type:
        conflicts = detect_conflicts(entity_type, entity_id)

    # ─── 6. EXPAND: nuove query da indizi ─────────────────────────────────
    new_queries = _generate_followup_queries(fragments, context, gaps)

    # ─── 7. STOP decision ─────────────────────────────────────────────────
    stop_reason = None
    decision = "continue"

    # Hard limits prima di AI
    if cycle_number >= plan.get("budget_cycles", 10):
        decision = "stop"
        stop_reason = "budget_cycles_exhausted"
    elif not fragments and not new_queries and cycle_number > 1:
        decision = "stop"
        stop_reason = "no_new_fragments"
    else:
        # AI-powered stop decision se disponibile
        if is_any_provider_available() and cycle_number > 1:
            ai_decision = _decide_continue_or_stop_ai(
                fragments, new_queries, gaps, cycle_number,
                plan.get("budget_cycles", 10),
                research_plan_id=plan_id, session_id=session_id,
            )
            if ai_decision:
                decision = ai_decision.get("decision", "continue")
                stop_reason = ai_decision.get("stop_reason")
        elif not external_results and cycle_number > 2:
            decision = "stop"
            stop_reason = "no_external_results"

    # Salva ciclo
    conn = get_conn()
    conn.execute(
        """INSERT INTO research_cycles (
            plan_id, session_id, cycle_number, initial_knowledge_json,
            gaps_selected_json, sources_selected_json, sources_motivation,
            queries_executed_json, new_fragments_json, utility_metrics_json,
            decision, stop_reason, created_at, completed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (plan_id, session_id, cycle_number,
         json.dumps(context), json.dumps(gaps),
         json.dumps(recommended[:5]),
         "; ".join(", ".join(r.get("reasons", [])[:3]) for r in recommended[:3] if r.get("reasons")),
         json.dumps(new_queries),
         json.dumps(fragments),
         json.dumps({"internal_count": len(internal_results),
                     "external_count": len(external_results),
                     "fragment_count": len(fragments),
                     "conflict_count": len(conflicts)}),
         decision, stop_reason, now, _now())
    )
    cycle_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Aggiorna piano
    if decision == "stop":
        conn.execute(
            "UPDATE research_plans SET status='completed', updated_at=? WHERE id=?",
            (_now(), plan_id)
        )
        conn.execute(
            "UPDATE research_sessions SET status='completed', completed_at=?, "
            "stop_reason=? WHERE id=?",
            (_now(), stop_reason, session_id)
        )
    else:
        conn.execute(
            "UPDATE research_plans SET updated_at=? WHERE id=?",
            (_now(), plan_id)
        )
        conn.execute(
            "UPDATE research_sessions SET cycle_number=?, updated_at=? WHERE id=?",
            (cycle_number, _now(), session_id)
        )

    conn.commit()
    conn.close()

    return {
        "cycle_id": cycle_id,
        "cycle_number": cycle_number,
        "decision": decision,
        "stop_reason": stop_reason,
        "internal_results": len(internal_results),
        "external_results": len(external_results),
        "fragments": fragments[:10],
        "conflicts": conflicts[:5],
        "new_queries": new_queries[:10],
        "recommended_sources": recommended[:5],
    }


def _search_internal(query: str, context: Dict, entity_type: str,
                     entity_id: int) -> List[Dict]:
    """Cerca nei database interni."""
    results = []

    # FTS su entita
    try:
        fts = search_entities(query, limit=20)
        for r in fts:
            results.append({
                "source": "fts_entita",
                "entity_id": r.get("entita_id"),
                "type": r.get("tipo"),
                "value": r.get("valore"),
                "table": r.get("fonte_tabella"),
                "record_id": r.get("fonte_id"),
                "rank": r.get("rank"),
            })
    except Exception:
        pass

    # Graph traversal se abbiamo un entity_id
    if entity_id:
        try:
            network = get_entity_network(entity_id, max_depth=2)
            if network:
                results.append({
                    "source": "graph_traversal",
                    "entity_id": entity_id,
                    "network": network,
                })
        except Exception:
            pass

    # Ricerca diretta su tabelle
    try:
        conn = get_conn()
        for table in ["internati", "caduti_albooro", "decorati"]:
            if not _table_exists(conn, table):
                continue
            parts = query.split()
            if not parts:
                continue
            cognome = parts[0]
            rows = conn.execute(
                f"SELECT id, cognome, nome, nominativo FROM {table} "
                f"WHERE cognome LIKE ? LIMIT 5",
                (f"{cognome}%",)
            ).fetchall()
            for r in rows:
                r = dict(r)
                results.append({
                    "source": f"db_{table}",
                    "id": r["id"],
                    "label": r.get("nominativo") or f"{r.get('cognome','')} {r.get('nome','')}",
                })
        conn.close()
    except Exception:
        pass

    return results


def _extract_fragments(internal: List, external: List,
                       context: Dict) -> List[Dict]:
    """Estrae frammenti strutturati dai risultati."""
    fragments = []

    for r in internal:
        if r.get("source", "").startswith("db_"):
            fragments.append({
                "type": "person_record",
                "source": r["source"],
                "id": r.get("id"),
                "label": r.get("label"),
                "clue": f"Record trovato in {r['source']}: {r.get('label')}",
            })
        elif r.get("source") == "fts_entita":
            fragments.append({
                "type": "entity_match",
                "source": "fts",
                "entity_id": r.get("entity_id"),
                "value": r.get("value"),
                "clue": f"Entita' trovata: {r.get('value')} (tipo: {r.get('type')})",
            })
        elif r.get("source") == "graph_traversal":
            fragments.append({
                "type": "graph_connection",
                "source": "graph",
                "clue": "Collegamenti nel grafo entita' trovati",
            })

    for r in external:
        fragments.append({
            "type": "external_source",
            "source": r.get("provider", "external"),
            "title": r.get("title"),
            "url": r.get("url"),
            "score": r.get("score", 0.3),
            "clue": f"Fonte esterna: {r.get('title')} ({r.get('provider')})",
        })

    return fragments


def _generate_followup_queries(fragments: List[Dict], context: Dict,
                               gaps: List[str]) -> List[Dict]:
    """Genera nuove query mirate dai frammenti trovati.

    Se un provider AI e' disponibile, usa AI per generare query piu' intelligenti.
    Altrimenti fallback su regole euristiche.
    """
    # Se AI disponibile, genera query con AI
    if is_any_provider_available():
        ai_queries = _generate_followup_queries_ai(fragments, context, gaps)
        if ai_queries:
            return ai_queries

    # Fallback: regole euristiche
    queries = []

    for frag in fragments:
        if frag.get("type") == "person_record":
            label = frag.get("label", "")
            queries.append({
                "query": f'"{label}"',
                "motivation": "ricerca esatta tra virgolette",
                "source": "person_record",
                "priority": 8,
            })
            if context.get("geography"):
                queries.append({
                    "query": f'"{label}" {context["geography"]}',
                    "motivation": "nome + luogo",
                    "source": "person_record+context",
                    "priority": 7,
                })
            if context.get("year"):
                queries.append({
                    "query": f'"{label}" {context["year"]}',
                    "motivation": "nome + anno",
                    "source": "person_record+context",
                    "priority": 7,
                })

        elif frag.get("type") == "external_source":
            title = frag.get("title", "")
            if title:
                queries.append({
                    "query": f'"{title}"',
                    "motivation": "approfondimento fonte esterna",
                    "source": "external_source",
                    "priority": 5,
                })

    if "camp" in gaps and context.get("nationality"):
        queries.append({
            "query": f'internati {context.get("nationality","")} campo prigionia',
            "motivation": "gap: camp",
            "source": "gap_camp",
            "priority": 4,
        })

    return queries


def _generate_followup_queries_ai(fragments: List[Dict], context: Dict,
                                   gaps: List[str]) -> List[Dict]:
    """Usa AI per generare query di follow-up intelligenti."""
    frag_summary = json.dumps([
        {"type": f.get("type"), "source": f.get("source"),
          "label": f.get("label"), "clue": f.get("clue", "")[:200]}
        for f in fragments[:10]
    ], ensure_ascii=False)
    ctx_summary = json.dumps(context, ensure_ascii=False)

    system = (
        "Sei un ricercatore storico esperto di IMI (Internati Militari Italiani) "
        "e conflitti del '900. Generi query di ricerca mirate per approfondire "
        "le piste trovate. Restituisci SOLO un array JSON di oggetti con campi: "
        "query (string), motivation (string), priority (int 1-10). "
        "Non inventare nomi: usa solo quelli presenti nei frammenti. "
        "Massimo 8 query."
    )
    user = (
        f"Frammenti trovati:\n{frag_summary}\n\n"
        f"Contesto estratto:\n{ctx_summary}\n\n"
        f"Lacune da colmare: {', '.join(gaps)}\n\n"
        f"Genera query di ricerca per il prossimo ciclo. Solo JSON array."
    )

    result = call_ai_json(
        task_type="generate_followup_queries",
        system=system, user=user,
        max_tokens=1024, temperature=0.2,
    )
    if not result.get("ok") or not result.get("data"):
        return []

    data = result["data"]
    if isinstance(data, dict):
        data = data.get("queries", [data])
    if not isinstance(data, list):
        return []

    queries = []
    for q in data[:8]:
        if isinstance(q, dict) and q.get("query"):
            queries.append({
                "query": q["query"],
                "motivation": q.get("motivation", "AI-generated"),
                "source": "ai_followup",
                "priority": q.get("priority", 5),
            })
    return queries


# ═══ AI-POWERED DECISIONS ═══════════════════════════════════════════════════

def _decide_continue_or_stop_ai(
    fragments: List[Dict], new_queries: List[Dict], gaps: List[str],
    cycle_number: int, budget_cycles: int,
    research_plan_id: int = None, session_id: int = None,
) -> Optional[Dict]:
    """Usa AI per decidere se continuare o fermare la ricerca.

    Returns: {"decision": "continue"|"stop", "stop_reason": str|None}
    """
    frag_summary = json.dumps([
        {"type": f.get("type"), "source": f.get("source"),
          "clue": f.get("clue", "")[:150]}
        for f in fragments[:10]
    ], ensure_ascii=False)
    query_summary = json.dumps([
        {"query": q.get("query"), "priority": q.get("priority")}
        for q in new_queries[:5]
    ], ensure_ascii=False)

    system = (
        "Sei un supervisore di ricerca storica. Valuti se un ciclo di ricerca "
        "ha prodotto abbastanza materiale per fermarsi o se ci sono piste "
        "promettenti da seguire. Restituisci SOLO un JSON con campi: "
        "decision (\"continue\" o \"stop\"), stop_reason (string o null), "
        "rationale (string). Non inventare informazioni."
    )
    user = (
        f"Ciclo {cycle_number} di {budget_cycles}.\n"
        f"Frammenti trovati ({len(fragments)}):\n{frag_summary}\n\n"
        f"Nuove query generate ({len(new_queries)}):\n{query_summary}\n\n"
        f"Lacune ancora aperte: {', '.join(gaps)}\n\n"
        f"Decidi se continuare o fermare. Solo JSON."
    )

    result = call_ai_json(
        task_type="decide_continue_or_stop",
        system=system, user=user,
        max_tokens=512, temperature=0.1,
        research_plan_id=research_plan_id,
        session_id=session_id,
    )
    if not result.get("ok") or not result.get("data"):
        return None

    data = result["data"]
    if not isinstance(data, dict):
        return None

    decision = data.get("decision", "continue")
    if decision not in ("continue", "stop"):
        decision = "continue"

    return {
        "decision": decision,
        "stop_reason": data.get("stop_reason") if decision == "stop" else None,
    }


def _generate_narrative_synthesis(
    user_input: str, plan: Dict, cycles: List[Dict],
    timeline: List[Dict],
    research_plan_id: int = None, session_id: int = None,
) -> Optional[Dict]:
    """Genera una sintesi narrativa finale della ricerca usando AI.

    Returns: {"text": str, "provider": str, "model": str, "cost": float}
    """
    all_fragments = []
    for cy in cycles:
        all_fragments.extend(cy.get("fragments", []))

    frag_summary = json.dumps([
        {"type": f.get("type"), "source": f.get("source"),
          "clue": f.get("clue", "")[:200]}
        for f in all_fragments[:20]
    ], ensure_ascii=False)

    timeline_summary = json.dumps([
        {"date": t.get("date_start"), "predicate": t.get("predicate"),
          "object": t.get("object_value"), "status": t.get("epistemic_status")}
        for t in timeline[:15]
    ], ensure_ascii=False)

    cycle_count = len(cycles)
    stop_reasons = [c.get("stop_reason") for c in cycles if c.get("stop_reason")]

    system = (
        "Sei un ricercatore storico esperto di IMI (Internati Militari Italiani) "
        "e conflitti del '900. Produci una sintesi narrativa della ricerca "
        "condotta, basandoti ESCLUSIVAMENTE sui frammenti e sulla timeline "
        "trovati. Non inventare dati non presenti nei risultati. "
        "Struttura la risposta in sezioni: SINTESI, PERSONE, LUOGHI, EVENTI, "
        "FONTI CONSULTATE, LACUNE, APPROFONDIMENTI CONSIGLIATI."
    )
    user = (
        f"Query originale: \"{user_input}\"\n"
        f"Tipo entita': {plan.get('entity_type', 'sconosciuto')}\n"
        f"Cicli eseguiti: {cycle_count}\n"
        f"Motivi di stop: {', '.join(stop_reasons) if stop_reasons else 'nessuno'}\n\n"
        f"Frammenti raccolti ({len(all_fragments)}):\n{frag_summary}\n\n"
        f"Timeline ({len(timeline)} eventi):\n{timeline_summary}\n\n"
        f"Produci la sintesi narrativa della ricerca."
    )

    result = call_ai(
        task_type="generate_biography",
        system=system, user=user,
        max_tokens=4096, temperature=0.3,
        research_plan_id=research_plan_id,
        session_id=session_id,
    )
    if not result.get("ok"):
        return None

    return {
        "text": result["text"],
        "provider": result["provider"],
        "model": result["model"],
        "cost": result["cost"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }


# ═══ RUN FULL RESEARCH ════════════════════════════════════════════════════

def run_research(user_input: str, max_cycles: int = 5,
                 strategy: str = "balanced") -> Dict:
    """Esegue una ricerca completa end-to-end.

    Crea piano, sessione, e iterazione di cicli fino a stop o budget.
    """
    plan_id = create_research_plan(user_input, budget_cycles=max_cycles)
    session_id = create_session(plan_id)

    cycles = []
    for i in range(1, max_cycles + 1):
        result = run_cycle(plan_id, session_id, i, strategy)
        cycles.append(result)
        if result.get("decision") == "stop":
            break

    # Recupera piano
    conn = get_conn()
    plan = conn.execute(
        "SELECT * FROM research_plans WHERE id=?", (plan_id,)
    ).fetchone()
    conn.close()
    plan = dict(plan) if plan else {}

    # ─── FACT EXTRACTION ──────────────────────────────────────────────────
    # Estrae claim strutturati dai record DB e frammenti di ricerca
    fact_result = None
    if plan.get("entity_type") and plan.get("entity_id"):
        all_fragments = []
        for cy in cycles:
            all_fragments.extend(cy.get("fragments", []))

        fact_result = extract_facts_for_entity(
            entity_type=plan["entity_type"],
            entity_id=plan["entity_id"],
            entity_label=user_input,
            research_plan_id=plan_id,
            session_id=session_id,
        )

        # Also extract from research fragments
        if all_fragments:
            frag_result = extract_claims_from_fragments(
                fragments=all_fragments,
                entity_type=plan["entity_type"],
                entity_id=plan["entity_id"],
                entity_label=user_input,
                research_plan_id=plan_id,
                session_id=session_id,
            )
            if fact_result:
                fact_result["claims_created"] += frag_result.get("claims_created", 0)
                fact_result["claims_existing"] += frag_result.get("claims_existing", 0)
                fact_result["claim_ids"].extend(frag_result.get("claim_ids", []))

    # ─── TIMELINE ─────────────────────────────────────────────────────────
    timeline = []
    if plan.get("entity_type") and plan.get("entity_id"):
        timeline = auto_build_timeline(plan["entity_type"], plan["entity_id"])

    # ─── NARRATIVE SYNTHESIS ──────────────────────────────────────────────
    narrative = None
    if is_any_provider_available() and cycles:
        narrative = _generate_narrative_synthesis(
            user_input, plan, cycles, timeline,
            research_plan_id=plan_id, session_id=session_id,
        )

    return {
        "plan_id": plan_id,
        "session_id": session_id,
        "entity_type": plan.get("entity_type"),
        "entity_id": plan.get("entity_id"),
        "cycles": cycles,
        "total_cycles": len(cycles),
        "timeline": timeline,
        "facts": fact_result,
        "narrative": narrative,
        "status": plan.get("status"),
    }


# ═══ QUERY RECORDING ══════════════════════════════════════════════════════

def record_query(session_id: int, query_text: str,
                  query_language: str = "it",
                  filters: Dict = None,
                  variant_used: str = None,
                  generated_from_claim_id: int = None,
                  generated_from_fragment: str = None,
                  priority: int = 5,
                  motivation: str = "",
                  search_tool: str = None,
                  assisted_search_url: str = None) -> int:
    """Registra una query di ricerca."""
    conn = get_conn()
    now = _now()
    conn.execute(
        """INSERT INTO research_queries (
            session_id, query_text, query_language, filters_json,
            variant_used, generated_from_claim_id, generated_from_fragment,
            priority, motivation, search_tool, assisted_search_url, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session_id, query_text, query_language,
         json.dumps(filters) if filters else None,
         variant_used, generated_from_claim_id, generated_from_fragment,
         priority, motivation, search_tool, assisted_search_url, now)
    )
    qid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return qid


def record_result(session_id: int, query_id: int = None,
                  external_id: str = None,
                  result_type: str = "search_hit",
                  record_url: str = None,
                  document_url: str = None,
                  canonical_url: str = None,
                  title: str = None,
                  author_or_entity: str = None,
                  raw_metadata: Dict = None,
                  fingerprint: str = None,
                  source_quality: float = 0.5,
                  authority_score: float = 0.5,
                  independence_group: str = None) -> int:
    """Registra un risultato di ricerca."""
    conn = get_conn()
    now = _now()
    conn.execute(
        """INSERT INTO research_results (
            session_id, query_id, external_id, result_type,
            record_url, document_url, canonical_url, title,
            author_or_entity, retrieved_at, raw_metadata_json,
            fingerprint, source_quality, authority_score,
            independence_group, status, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session_id, query_id, external_id, result_type,
         record_url, document_url, canonical_url, title,
         author_or_entity, now,
         json.dumps(raw_metadata) if raw_metadata else None,
         fingerprint, source_quality, authority_score,
         independence_group, "new", now, now)
    )
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return rid


def update_result_status(result_id: int, status: str, reason: str = "") -> Dict:
    """Aggiorna lo stato di un risultato.
    status: new | linked | excluded | duplicate | to_verify
    """
    conn = get_conn()
    now = _now()
    r = conn.execute(
        "SELECT id FROM research_results WHERE id=?", (result_id,)
    ).fetchone()
    if not r:
        conn.close()
        return {"error": "result not found"}
    conn.execute(
        "UPDATE research_results SET status=?, status_reason=?, last_seen_at=? WHERE id=?",
        (status, reason, now, result_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "result_id": result_id, "status": status}


# ═══ TRACE ════════════════════════════════════════════════════════════════

def get_session_trace(session_id: int) -> Dict:
    """Recupera la traccia completa di una sessione."""
    conn = get_conn()
    session = conn.execute(
        "SELECT * FROM research_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not session:
        conn.close()
        return {"error": "session not found"}
    session = dict(session)

    queries = conn.execute(
        "SELECT * FROM research_queries WHERE session_id=? ORDER BY created_at",
        (session_id,)
    ).fetchall()
    results = conn.execute(
        "SELECT * FROM research_results WHERE session_id=? ORDER BY first_seen_at",
        (session_id,)
    ).fetchall()
    cycles = conn.execute(
        "SELECT * FROM research_cycles WHERE session_id=? ORDER BY cycle_number",
        (session_id,)
    ).fetchall()
    conn.close()

    return {
        "session": session,
        "queries": [dict(q) for q in queries],
        "results": [dict(r) for r in results],
        "cycles": [dict(c) for c in cycles],
    }


def get_plan_cycles(plan_id: int) -> List[Dict]:
    """Recupera tutti i cicli di un piano."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM research_cycles WHERE plan_id=? ORDER BY cycle_number",
        (plan_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══ V2 COMPONENTS ═════════════════════════════════════════════════════════
# Componenti specifici del prompt V2 non presenti nella versione precedente.

# ─── LocatorValidator ────────────────────────────────────────────────────────

_SEARCH_PAGE_PATTERNS = [
    "/search", "/find", "/query", "?q=", "/advanced", "/form",
    "/ricerca", "/suche", "/recherche", "action=search",
    "/caduti/search", "/find?", "/search?",
]
_ALLOWED_SCHEMES = {"http", "https"}

_VIEWER_PATTERNS = [
    "/viewer", "/view", "/read", "/browse", "/leggi",
    "/showpdf", "/show_pdf", "/document/view", "/reader",
]

_DOWNLOAD_PATTERNS = [
    "/download", "/dl/", "/get/", "/fetch/", "/export/",
    ".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".tif",
    ".tiff", ".gif", ".webp",
]

_CATALOG_PATTERNS = [
    "/catalog", "/catalogo", "/inventario", "/inventory",
    "/collection", "/collezione", "/fondo/", "/series/",
    "/archiv/", "/bestand/",
]

_DOCUMENT_INDICATORS = [
    "/document/", "/documento/", "/lettera/", "/carta/",
    "/foto/", "/image/", "/scan/", "/page/", "/pag/",
    "/atto/", "/verbale/", "/scheda/",
]


def classify_url(url: str) -> str:
    """Classifica URL secondo la tassonomia canonica.

    Returns: document | record | catalog_entry | search_page |
             homepage | download | viewer | broken | unknown | empty
    """
    if not url:
        return "empty"
    url_lower = url.lower().strip()

    if url_lower in ("none", "null", "n/a", "-"):
        return "broken"
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        return "broken"

    for pattern in _SEARCH_PAGE_PATTERNS:
        if pattern in url_lower:
            return "search_page"

    for pattern in _DOWNLOAD_PATTERNS:
        if pattern in url_lower:
            return "download"

    for pattern in _VIEWER_PATTERNS:
        if pattern in url_lower:
            return "viewer"

    for pattern in _CATALOG_PATTERNS:
        if pattern in url_lower:
            return "catalog_entry"

    from urllib.parse import urlparse
    try:
        parsed = urlparse(url_lower)
        if parsed.path in ("", "/") and not parsed.query and not parsed.fragment:
            return "homepage"
    except Exception:
        pass

    path = parsed.path if parsed else ""
    if path:
        segments = [s for s in path.split("/") if s]
        if segments:
            last = segments[-1].split("?")[0].split("#")[0]
            if last.isdigit() or (len(last) > 4 and any(c.isdigit() for c in last) and any(c.isalpha() for c in last)):
                return "record"

    for ind in _DOCUMENT_INDICATORS:
        if ind in url_lower:
            return "document"

    return "unknown"


def is_valid_locator(url: str) -> bool:
    """True se l'URL è un locator diretto a un oggetto fonte (non search/homepage)."""
    if not url:
        return False
    scheme = url.split("://")[0].lower() if "://" in url else ""
    if scheme not in _ALLOWED_SCHEMES:
        return False
    kind = classify_url(url)
    return kind in ("record", "document", "catalog_entry", "download", "viewer")


def validate_locator(url: str, domain: str = None) -> Dict:
    """Valida un URL come locator e ritorna diagnosi completa."""
    kind = classify_url(url)
    valid_kinds = {"record", "document", "catalog_entry", "download", "viewer"}
    is_valid = kind in valid_kinds
    scheme = url.split("://")[0].lower() if "://" in url else ""
    scheme_ok = scheme in _ALLOWED_SCHEMES
    extracted_domain = ""
    if "://" in url:
        parts = url.split("/")
        if len(parts) > 2:
            extracted_domain = parts[2]
    return {
        "url": url,
        "url_kind": kind,
        "is_valid_locator": is_valid,
        "scheme_ok": scheme_ok,
        "domain": domain or extracted_domain,
        "issues": [] if is_valid else [f"url_kind={kind}", f"scheme_ok={scheme_ok}"],
    }


# ─── Normalizer ──────────────────────────────────────────────────────────────

def normalize_hit(raw: Dict, connector_code: str) -> Dict:
    """Converte output eterogeneo in envelope comune senza perdere originali."""
    return {
        "connector_code": connector_code,
        "external_id": str(raw.get("id") or raw.get("external_id") or raw.get("record_id") or ""),
        "title": raw.get("title") or raw.get("titolo") or raw.get("name") or "",
        "description": raw.get("description") or raw.get("descrizione") or "",
        "url": raw.get("url") or raw.get("canonical_record_url") or raw.get("source_url") or "",
        "url_kind": classify_url(raw.get("url") or raw.get("canonical_record_url") or ""),
        "metadata": {k: v for k, v in raw.items()
                     if k not in ("id", "title", "titolo", "name", "url",
                                  "description", "descrizione", "source_url")},
        "raw_preserved": raw,
    }


def normalize_record(raw: Dict, connector_code: str) -> Dict:
    """Normalizza un record dettagliato preservando raw."""
    return {
        "connector_code": connector_code,
        "external_id": str(raw.get("external_id") or raw.get("id") or ""),
        "title": raw.get("title") or raw.get("titolo") or "",
        "canonical_url": raw.get("canonical_record_url") or raw.get("url") or "",
        "metadata": raw,
        "people": raw.get("people_metadata_json") or raw.get("people") or [],
        "places": raw.get("places_metadata_json") or raw.get("places") or [],
        "military_units": raw.get("military_units_metadata_json") or [],
        "camps": raw.get("camps_metadata_json") or [],
        "digital_object_url": raw.get("digital_object_url") or "",
        "digital_object_available": raw.get("digital_object_available") or 0,
    }


# ─── Compliance Preflight with permitted_operations ──────────────────────────

def preflight_compliance(connector_code: str, operation: str,
                         target_url: str = None, user_role: str = "operator") -> Dict:
    """Preflight compliance gate per operazione specifica.

    Usa source_policies + permitted_operations per determinare se
    l'operazione è permessa per il dominio target.
    """
    conn = get_conn()
    domain = ""
    if target_url and "://" in target_url:
        parts = target_url.split("/")
        if len(parts) > 2:
            domain = parts[2]

    # Trova policy per dominio
    policy = None
    if domain:
        for p in conn.execute("SELECT * FROM source_policies").fetchall():
            p = dict(p)
            if domain in (p.get("domain") or ""):
                policy = p
                break

    if not policy:
        conn.close()
        return {
            "allowed": True,
            "decision": "no_policy_default_allow",
            "reason": "Nessuna policy specifica per il dominio. Default: allow con logging.",
            "policy_id": None,
        }

    # Cerca permitted_operations
    perm_op = conn.execute(
        "SELECT * FROM permitted_operations WHERE policy_id=? AND operation=?",
        (policy["id"], operation)
    ).fetchone()

    conn.close()

    if perm_op:
        decision = perm_op["decision"]
    else:
        # Fallback ai flag nella policy
        op_to_flag = {
            "search": "metadata_indexing_allowed",
            "fetch_metadata": "metadata_indexing_allowed",
            "download": "document_download_allowed",
            "ocr": "document_download_allowed",
            "send_to_cloud_ai": "automated_access_allowed",
            "publish_summary": "republication_allowed",
        }
        flag_col = op_to_flag.get(operation, "metadata_indexing_allowed")
        flag_val = policy.get(flag_col)
        decision = "allow" if flag_val else "require_human"

    allowed = decision == "allow"
    return {
        "allowed": allowed,
        "decision": decision,
        "reason": f"Policy for {domain}: operation '{operation}' → {decision}",
        "policy_id": policy["id"],
        "policy_version": policy.get("valid_from", ""),
    }


# ─── Stable Locator Registration ─────────────────────────────────────────────

def register_stable_locator(source_item_id: int, source_table: str,
                            locator_kind: str, locator_value: str,
                            canonical_url: str = None, domain: str = None,
                            verified_by: str = "system") -> int:
    """Registra o aggiorna un locator stabile per un oggetto fonte."""
    conn = get_conn()
    now = _now()
    try:
        conn.execute("""
            INSERT INTO stable_locators
                (source_item_id, source_table, locator_kind, locator_value,
                 canonical_url, domain, is_stable, verified_at, verified_by,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """, (source_item_id, source_table, locator_kind, locator_value,
              canonical_url, domain, now, verified_by, now, now))
        conn.commit()
        loc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception:
        # Already exists — update
        conn.execute("""
            UPDATE stable_locators SET locator_value=?, canonical_url=?, domain=?,
                   is_stable=1, verified_at=?, verified_by=?, updated_at=?
            WHERE source_item_id=? AND source_table=? AND locator_kind=?
        """, (locator_value, canonical_url, domain, now, verified_by, now,
              source_item_id, source_table, locator_kind))
        conn.commit()
        loc_id = conn.execute(
            "SELECT id FROM stable_locators WHERE source_item_id=? AND source_table=? AND locator_kind=?",
            (source_item_id, source_table, locator_kind)
        ).fetchone()[0]
    conn.close()
    return loc_id


# ─── Content Fingerprint ────────────────────────────────────────────────────

def compute_content_fingerprint(content: str, source_item_id: int = None,
                                source_table: str = None) -> str:
    """Calcola e registra fingerprint SHA-256 del contenuto."""
    if not content:
        return ""
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if source_item_id:
        conn = get_conn()
        now = _now()
        conn.execute("""
            INSERT OR IGNORE INTO content_fingerprints
                (source_item_id, source_table, content_hash, hash_algorithm,
                 content_type, content_size, created_at)
            VALUES (?, ?, ?, 'sha256', 'text', ?, ?)
        """, (source_item_id, source_table, h, len(content.encode("utf-8")), now))
        conn.commit()
        conn.close()
    return h


# ─── Budget Reservation ──────────────────────────────────────────────────────

def reserve_budget(plan_id: int, task_type: str, provider_code: str,
                   amount: float, currency: str = "USD") -> int:
    """Prenota budget per un task. Ritorna reservation_id."""
    conn = get_conn()
    now = _now()
    cur = conn.execute("""
        INSERT INTO budget_reservations
            (plan_id, task_type, provider_code, reserved_amount,
             currency, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
    """, (plan_id, task_type, provider_code, amount, currency, now, now))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def consume_budget(reservation_id: int, consumed: float) -> Dict:
    """Registra consumo di budget prenotato."""
    conn = get_conn()
    now = _now()
    conn.execute("""
        UPDATE budget_reservations
        SET consumed_amount = consumed_amount + ?, updated_at = ?
        WHERE id = ?
    """, (consumed, now, reservation_id))
    conn.commit()
    row = conn.execute("SELECT * FROM budget_reservations WHERE id=?", (reservation_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"error": "not found"}


# ─── Prompt Versioning ──────────────────────────────────────────────────────

def register_prompt_version(prompt_name: str, version: str,
                            system_prompt: str, user_prompt_template: str,
                            variables: List[str] = None,
                            constraints: List[str] = None) -> int:
    """Registra una nuova versione di prompt."""
    conn = get_conn()
    now = _now()
    # Disattiva versioni precedenti
    conn.execute("UPDATE prompt_versions SET active=0 WHERE prompt_name=?", (prompt_name,))
    cur = conn.execute("""
        INSERT OR REPLACE INTO prompt_versions
            (prompt_name, version, system_prompt, user_prompt_template,
             variables_json, constraints_json, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (prompt_name, version, system_prompt, user_prompt_template,
          json.dumps(variables or []), json.dumps(constraints or []), now, now))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def get_active_prompt(prompt_name: str) -> Optional[Dict]:
    """Recupera la versione attiva di un prompt."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM prompt_versions WHERE prompt_name=? AND active=1",
        (prompt_name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Edge Evidence ──────────────────────────────────────────────────────────

def add_edge_evidence(edge_id: int, evidence_type: str,
                      source_item_id: int = None, source_table: str = None,
                      claim_id: int = None, supporting_quote: str = "",
                      evidence_role: str = "supports", strength: float = 0.5) -> int:
    """Aggiunge evidenza a un edge esistente (record_links)."""
    conn = get_conn()
    now = _now()
    cur = conn.execute("""
        INSERT INTO edge_evidence
            (edge_id, evidence_type, source_item_id, source_table,
             claim_id, supporting_quote, evidence_role, strength, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (edge_id, evidence_type, source_item_id, source_table,
          claim_id, supporting_quote, evidence_role, strength, now))
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid


# ─── Source Access Audit ────────────────────────────────────────────────────

def log_source_access(connector_code: str, operation: str,
                      target_url: str = None, target_domain: str = None,
                      policy_version_id: int = None, decision: str = "",
                      response_status: int = None, response_time_ms: int = None,
                      error_message: str = "", operator_user: str = "") -> int:
    """Registra accesso a fonte per audit."""
    conn = get_conn()
    now = _now()
    if not target_domain and target_url and "://" in target_url:
        parts = target_url.split("/")
        if len(parts) > 2:
            target_domain = parts[2]
    cur = conn.execute("""
        INSERT INTO source_access_audit
            (connector_code, operation, target_url, target_domain,
             policy_version_id, decision, response_status, response_time_ms,
             error_message, operator_user, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (connector_code, operation, target_url, target_domain,
          policy_version_id, decision, response_status, response_time_ms,
          error_message, operator_user, now))
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid
