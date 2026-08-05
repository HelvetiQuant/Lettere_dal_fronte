"""Semantic Validator V6 — multi-level validation for AI output.

Validation levels:
  schema_valid: JSON parses and has required fields
  semantic_valid: no internal markers, no forbidden tokens
  grounding_valid: every factual statement has claim_id
  render_valid: no internal tokens visible to user
  conversation_valid: response is coherent with conversation state

responses_valid is True only when ALL required levels are True.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ValidationV6Result:
    schema_valid: bool = True
    semantic_valid: bool = True
    grounding_valid: bool = True
    render_valid: bool = True
    conversation_valid: bool = True
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    detected_markers: List[str] = field(default_factory=list)
    unsupported_facts: List[str] = field(default_factory=list)
    fallback_used: bool = False

    @property
    def responses_valid(self) -> bool:
        return all([
            self.schema_valid,
            self.semantic_valid,
            self.grounding_valid,
            self.render_valid,
            self.conversation_valid,
        ])

    def to_dict(self) -> dict:
        return {
            "schema_valid": self.schema_valid,
            "semantic_valid": self.semantic_valid,
            "grounding_valid": self.grounding_valid,
            "render_valid": self.render_valid,
            "conversation_valid": self.conversation_valid,
            "responses_valid": self.responses_valid,
            "violations": self.violations,
            "warnings": self.warnings,
            "detected_markers": self.detected_markers,
            "unsupported_facts": self.unsupported_facts,
            "fallback_used": self.fallback_used,
        }


# ─── Forbidden internal tokens ──────────────────────────────────────────────

FORBIDDEN_TOKENS = [
    "suggested_research_action",
    "claim_id",
    "source_id",
    "authority_id",
    "internal_error",
    "MODEL_LEAD",
    "SEARCH_RESULT",
    "SOURCE_CANDIDATE",
    "NOT_OPENED",
    "METADATA_ONLY",
    "OCR_EXTRACTED",
    "PROVIDER_CONTRACT_VIOLATION",
    "INCOMPLETE_LEDGER",
    "NO_AGGREGATE_DATA",
]

# Factual statement patterns that require claim backing
FACTUAL_PATTERNS = [
    (r'(?:circa|approssimativamente|approssimativamente)\s+(\d[\d\.]*)\s*(soldati|prigionieri|uomini|caduti|feriti)', "casualty_count"),
    (r'\b(\d[\d\.]*)\s*(km|chilometri)\b', "distance"),
    (r'\b(\d{1,2})\s+(ottobre|novembre|dicembre|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre)\s+(\d{4})\b', "date"),
    (r'\b(\d{4})\b', "year"),
    (r'(?:nato|nata)\s+(?:il|a)\b', "birth_info"),
    (r'(?:morto|morta|deceduto|deceduta)\s+(?:il|a)\b', "death_info"),
    (r'(?:decorato|decorata|medaglia|croce)\b', "decoration"),
    (r'(?:reggimento|brigata|divisione|battaglione|compagnia)\b', "military_unit"),
]


def validate_v6(
    ai_output: str,
    snapshot_dict: dict,
    is_structured: bool = False,
    conversation_history: Optional[List[dict]] = None,
) -> ValidationV6Result:
    """Validate AI output at all levels.

    Args:
        ai_output: Raw text from the AI model (or JSON string if structured)
        snapshot_dict: EvidenceSnapshotV6 as dict
        is_structured: Whether the output is expected to be JSON
        conversation_history: Previous messages for conversation validation

    Returns:
        ValidationV6Result with per-level flags and details.
    """
    result = ValidationV6Result()

    if not ai_output or not ai_output.strip():
        result.schema_valid = False
        result.semantic_valid = False
        result.render_valid = False
        result.violations.append("EMPTY_AI_OUTPUT")
        result.fallback_used = True
        return result

    # ── 1. Schema validation ──
    parsed = None
    if is_structured:
        try:
            parsed = json.loads(ai_output)
            required_fields = ["answer"]
            for rf in required_fields:
                if rf not in parsed:
                    result.schema_valid = False
                    result.violations.append(f"MISSING_REQUIRED_FIELD: {rf}")
        except json.JSONDecodeError:
            result.schema_valid = False
            result.violations.append("INVALID_JSON")
            result.fallback_used = True
    else:
        # For non-structured, try to detect if it's accidentally JSON
        stripped = ai_output.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
                if "answer" in parsed:
                    # Model returned structured when not expected — extract answer
                    ai_output = parsed["answer"]
            except json.JSONDecodeError:
                pass

    # ── 2. Semantic validation: no forbidden internal tokens ──
    output_lower = ai_output.lower()
    for token in FORBIDDEN_TOKENS:
        if token.lower() in output_lower:
            result.semantic_valid = False
            result.render_valid = False
            result.detected_markers.append(token)
            result.violations.append(f"INTERNAL_TOKEN_VISIBLE: {token}")

    # ── 3. Grounding validation: factual statements need claim backing ──
    accepted_claim_predicates = {
        c.get("predicate", "") for c in snapshot_dict.get("accepted_claims", [])
    }
    asserted_claim_predicates = {
        c.get("predicate", "") for c in snapshot_dict.get("asserted_claims", [])
    }
    all_claim_predicates = accepted_claim_predicates | asserted_claim_predicates

    has_accepted_evidence = len(snapshot_dict.get("accepted_evidence", [])) > 0
    has_context_sources = len(snapshot_dict.get("context_sources", [])) > 0

    for pattern, fact_type in FACTUAL_PATTERNS:
        matches = re.findall(pattern, ai_output, re.IGNORECASE)
        if matches:
            # Check if this fact type is backed by claims
            fact_to_claim_map = {
                "casualty_count": "casualty_count",
                "distance": "distance",
                "date": "event_start_date",
                "year": "birth_year",
                "birth_info": "birth_year",
                "death_info": "death_date",
                "decoration": "decoration_type",
                "military_unit": "unit",
            }
            claim_field = fact_to_claim_map.get(fact_type, "")
            # Check both accepted AND asserted claims (origin record data is valid grounding)
            if claim_field and claim_field not in all_claim_predicates:
                # This factual statement is not backed by any claim
                # Check if it's explicitly marked as uncertain
                is_uncertain = any(
                    kw in output_lower
                    for kw in ["forse", "probabilmente", "non è noto", "non disponiamo", "incerto", "ignoto",
                               "non verificato", "non corroborati", "non sono stati corroborati"]
                )
                if not is_uncertain and not has_context_sources:
                    result.grounding_valid = False
                    result.unsupported_facts.append(f"UNSUPPORTED_FACT: {fact_type} — pattern matched but no claim backs it")
                    result.violations.append(f"FACTUAL_STATEMENT_WITHOUT_CLAIM: {fact_type}")

    # Special check: if the snapshot has NO accepted evidence, NO context sources,
    # AND NO asserted claims from origin record, any factual statement about the target is unsupported
    has_asserted_claims = bool(snapshot_dict.get("asserted_claims", []))
    if not has_accepted_evidence and not has_context_sources and not has_asserted_claims and not snapshot_dict.get("aggregate_result"):
        # Allow uncertainty formulas
        uncertainty_keywords = [
            "non ci sono informazioni", "non disponiamo", "non è noto",
            "non abbiamo dati", "nessun dato disponibile",
            "lo snapshot non contiene", "non è stato possibile",
            "sarebbe necessario", "consigliamo di consultare",
            "non verificato", "non sono stati corroborati", "non corroborati",
            "record d'origine non verificato", "provigono da un record",
            "provengono da un record", "non ci sono fonti esterne",
        ]
        has_uncertainty = any(kw in output_lower for kw in uncertainty_keywords)
        if not has_uncertainty and len(ai_output) > 100:
            # Check if output contains factual assertions about the target
            target_name = snapshot_dict.get("target", {}).get("display_name", "")
            if target_name and target_name.lower() in output_lower:
                # Long output about target with no evidence = potential hallucination
                result.grounding_valid = False
                result.unsupported_facts.append("FACTS_ABOUT_TARGET_WITHOUT_EVIDENCE")
                result.violations.append("FACTUAL_OUTPUT_WITHOUT_EVIDENCE_OR_UNCERTAINTY")

    # ── 4. Render validation: no internal tokens in user-visible text ──
    # Already checked in semantic validation, but double-check
    if result.detected_markers:
        result.render_valid = False

    # ── 5. Conversation validation ──
    if conversation_history and len(conversation_history) > 0:
        # Check if the response acknowledges previous context
        last_user_msg = ""
        for msg in reversed(conversation_history):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        if last_user_msg:
            # If user asked a specific question, check the response is not a generic template
            if len(ai_output) < 20 and not parsed:
                result.conversation_valid = False
                result.violations.append("RESPONSE_TOO_SHORT_FOR_QUESTION")

    # ── Determine fallback ──
    if result.violations and not result.fallback_used:
        # Don't auto-set fallback; let caller decide
        pass

    return result


def _format_claim_value(predicate: str, value: str) -> str:
    """Translate predicate keys to human-readable Italian labels."""
    labels = {
        "birth_year": "anno di nascita",
        "birth_place": "luogo di nascita",
        "death_year": "anno di morte",
        "death_place": "luogo di morte",
        "death_cause": "causa di morte",
        "rank": "grado militare",
        "unit": "reparto",
        "internment_place": "luogo di internamento",
        "fate": "sorte",
        "decoration_type": "tipo di decorazione",
        "service_number": "matricola",
        "event_start_date": "data di inizio",
        "event_end_date": "data di fine",
        "event_location": "luogo",
        "event_description": "descrizione",
        "event_phase_count": "numero di fasi",
        "event_actors": "forze in campo",
    }
    return labels.get(predicate, predicate.replace("_", " "))


def _detect_question_type(question: str) -> str:
    """Classify the user's question to tailor the conversational response."""
    q = question.lower().strip()
    if any(kw in q for kw in ["chi era", "chi è", "cosa successe", "cosa è successo", "racconta", "parlami"]):
        return "WHO_IS"
    if any(kw in q for kw in ["dati certi", "dati sicuri", "cosa sappiamo", "informazioni"]):
        return "FACTS"
    if any(kw in q for kw in ["prigionia", "internamento", "cattura", "campo"]):
        return "PRISON"
    if any(kw in q for kw in ["fonti", "archivio", "consultare", "dove trovare"]):
        return "SOURCES"
    if any(kw in q for kw in ["date", "quando", "in che anno", "periodo"]):
        return "DATES"
    if any(kw in q for kw in ["quanti", "conteggio", "numero", "totale"]):
        return "COUNT"
    if any(kw in q for kw in ["quali tipi", "quali cause", "quali campi", "classificazione"]):
        return "BREAKDOWN"
    return "GENERAL"


def generate_deterministic_v6(snapshot_dict: dict, question: str = "") -> str:
    """Generate a deterministic conversational report when AI is unavailable or invalid.

    Produces natural Italian text from snapshot data.
    No internal tokens, no hallucinated facts.
    Responses vary based on question type and available data.
    """
    target_name = snapshot_dict.get("target", {}).get("display_name", "il soggetto")
    intent = snapshot_dict.get("intent", "PERSON_LOOKUP")
    identity = snapshot_dict.get("identity_resolution", "UNRESOLVED")
    origin_presence = snapshot_dict.get("origin", {}).get("presence", "ABSENT")
    origin_provenance = snapshot_dict.get("origin", {}).get("provenance", "UNVERIFIED")
    accepted = snapshot_dict.get("accepted_claims", [])
    asserted = snapshot_dict.get("asserted_claims", [])
    conflicting = snapshot_dict.get("conflicting_claims", [])
    gaps = snapshot_dict.get("conditional_gaps", [])
    next_steps = snapshot_dict.get("next_steps", [])
    aggregate = snapshot_dict.get("aggregate_result")
    limitations = snapshot_dict.get("limitations", [])
    q_type = _detect_question_type(question)

    # ── AGGREGATE QUERY ──
    if intent == "AGGREGATE_QUERY":
        if aggregate:
            result_data = aggregate.get("result", {})
            table_name = aggregate.get("table_name", "database locale")
            total = result_data.get("total", 0)
            if q_type == "COUNT":
                lines = [
                    f"Per la query \"{target_name}\", il database locale ({table_name}) restituisce un totale di {total} record.",
                ]
                if len(result_data) > 1:
                    breakdown = {k: v for k, v in result_data.items() if k != "total" and isinstance(v, (int, float))}
                    if breakdown:
                        top_items = sorted(breakdown.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)[:5]
                        lines.append("Ecco i primi risultati per categoria:")
                        for k, v in top_items:
                            lines.append(f"  • {k}: {v}")
                lines.append(f"\nQuesti dati provengono dal database locale e non sono stati corroborati da fonti esterne.")
                return "\n".join(lines)
            elif q_type == "BREAKDOWN":
                breakdown = {k: v for k, v in result_data.items() if k != "total" and isinstance(v, (int, float))}
                if breakdown:
                    lines = [f"Ecco la ripartizione per \"{target_name}\" (database: {table_name}, totale: {total}):"]
                    for k, v in sorted(breakdown.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True):
                        lines.append(f"  • {k}: {v}")
                    return "\n".join(lines)
                return f"Il database locale ({table_name}) restituisce {total} record per la query \"{target_name}\", ma non è disponibile una ripartizione dettagliata per categoria."
            elif q_type == "SOURCES":
                lines = [
                    f"I dati per questa query aggregata provengono dal database locale \"{table_name}\".",
                    "Al momento non ci sono fonti esterne verificate disponibili nello snapshot per approfondire questa ricerca.",
                ]
                if next_steps:
                    lines.append("\nPer ampliare la ricerca, potresti consultare:")
                    for s in next_steps[:3]:
                        lines.append(f"  • {s.get('description', 'N/D')} — {s.get('archive', '')} (accesso: {s.get('access_mode', 'N/D')})")
                return "\n".join(lines)
            else:
                lines = [
                    f"Per la query \"{target_name}\", il database locale ({table_name}) restituisce {total} record.",
                ]
                breakdown = {k: v for k, v in result_data.items() if k != "total" and isinstance(v, (int, float))}
                if breakdown:
                    top = sorted(breakdown.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)[:5]
                    lines.append("Principali categorie:")
                    for k, v in top:
                        lines.append(f"  • {k}: {v}")
                lines.append("\nQuesti dati non sono stati corroborati da fonti esterne.")
                return "\n".join(lines)
        else:
            lines = [
                f"Non sono disponibili dati aggregati nel database locale per la query: \"{target_name}\".",
                "Si consiglia di consultare direttamente gli archivi competenti o i database nazionali.",
            ]
            return "\n".join(lines)

    # ── PERSON / EVENT LOOKUP ──
    has_origin = origin_presence in ("PRESENT_LOCAL", "VERIFIED")
    has_asserted = bool(asserted)
    has_accepted = bool(accepted)
    has_conflicts = bool(conflicting)
    blocking_gaps = [g for g in gaps if g.get("blocking")]
    non_blocking_gaps = [g for g in gaps if not g.get("blocking")]

    # Build claim lookup
    all_claims = {}
    for c in asserted:
        all_claims[c.get("predicate", "")] = c.get("value_normalized", "")
    for c in accepted:
        all_claims[c.get("predicate", "")] = c.get("value_normalized", "")

    lines = []

    # ── Opening: varies by question type ──
    if q_type == "WHO_IS":
        if has_origin:
            provenance_note = "verificato" if origin_provenance == "VERIFIED" else "non ancora verificato"
            lines.append(f"{target_name} è presente nei nostri database locali con un record d'origine {provenance_note}.")
            if has_asserted:
                lines.append("Ecco ciò che emerge dai dati in nostro possesso:")
            else:
                lines.append("Tuttavia, il record non contiene dati strutturati dettagliati.")
        else:
            lines.append(f"Non è presente un record d'origine verificato per {target_name} nei database locali.")
            lines.append("Al momento non disponiamo di informazioni certe su questa persona.")
    elif q_type == "FACTS":
        if has_origin and has_asserted:
            lines.append(f"I dati certi su {target_name}, dal record d'origine nei database locali, sono i seguenti:")
        elif has_origin and has_accepted:
            lines.append(f"Per {target_name}, i claim supportati da evidenza sono:")
        elif has_origin:
            lines.append(f"Il record d'origine per {target_name} è presente ma non contiene dati strutturati certi.")
        else:
            lines.append(f"Non ci sono dati certi disponibili su {target_name} nello snapshot attuale.")
    elif q_type == "PRISON":
        prison_fields = {k: v for k, v in all_claims.items() if k in ("internment_place", "fate", "rank", "unit")}
        if prison_fields:
            lines.append(f"Per quanto riguarda la prigionia di {target_name}, dai dati del record d'origine risulta:")
            for pred, val in prison_fields.items():
                lines.append(f"  • {_format_claim_value(pred, val)}: {val}")
            if "internment_place" not in prison_fields:
                lines.append("  • Il luogo di internamento non è specificato nel record.")
        else:
            lines.append(f"Non ci sono informazioni disponibili sulla prigionia di {target_name} nel record d'origine.")
            lines.append("I dati sul luogo di internamento e sulla sorte non sono presenti nello snapshot attuale.")
    elif q_type == "DATES":
        date_fields = {k: v for k, v in all_claims.items() if "date" in k or "year" in k}
        if date_fields:
            lines.append(f"Per {target_name}, le date disponibili dal record d'origine sono:")
            for pred, val in date_fields.items():
                lines.append(f"  • {_format_claim_value(pred, val)}: {val}")
        else:
            lines.append(f"Non ci sono date certe disponibili su {target_name} nello snapshot attuale.")
    elif q_type == "SOURCES":
        lines.append(f"Per approfondire la ricerca su {target_name}, ecco le fonti e gli archivi consultabili:")
        if next_steps:
            for s in next_steps[:5]:
                access = s.get("access_mode", "N/D")
                access_desc = {
                    "OPEN": "accesso libero",
                    "REGISTERED": "registrazione richiesta",
                    "REQUEST_REQUIRED": "richiesta formale necessaria",
                }.get(access, access)
                lines.append(f"  • {s.get('description', 'N/D')} — {s.get('archive', 'N/D')} ({access_desc})")
        else:
            lines.append("  • Al momento non ci sono fonti esterne verificate disponibili nello snapshot.")
        if has_origin:
            lines.append(f"\nIl record d'origine nei database locali rimane il punto di partenza per ogni verifica ulteriore.")
        return "\n".join(lines)
    else:
        # GENERAL
        if has_origin:
            lines.append(f"{target_name} è presente nei database locali.")
            if has_asserted:
                lines.append("Ecco i dati disponibili:")
            else:
                lines.append("Il record non contiene dati strutturati dettagliati al momento.")
        else:
            lines.append(f"Non ci sono informazioni disponibili su {target_name} nello snapshot fornito.")

    # ── Data section ──
    if q_type in ("WHO_IS", "FACTS", "GENERAL") and has_asserted:
        for c in asserted:
            pred = c.get("predicate", "campo")
            val = c.get("value_normalized", "N/D")
            lines.append(f"  • {_format_claim_value(pred, val)}: {val}")

    if has_accepted and q_type in ("WHO_IS", "FACTS", "GENERAL"):
        if has_asserted:
            lines.append("\nInoltre, alcuni dati sono supportati da evidenza di supporto:")
        for c in accepted:
            pred = c.get("predicate", "campo")
            val = c.get("value_normalized", "N/D")
            lines.append(f"  • {_format_claim_value(pred, val)}: {val}")

    # ── Conflicts ──
    if has_conflicts:
        lines.append("\nAttenzione: ci sono dati discordanti tra le fonti:")
        for c in conflicting:
            pred = c.get("predicate", "campo")
            val = c.get("value_normalized", "N/D")
            lines.append(f"  • {_format_claim_value(pred, val)}: {val} (in conflitto)")

    # ── Gaps ──
    if blocking_gaps and q_type in ("WHO_IS", "FACTS", "GENERAL"):
        gap_names = [_format_claim_value(g.get("field_name", ""), "") for g in blocking_gaps]
        lines.append(f"\nNon sono ancora disponibili: {', '.join(gap_names)}.")

    # ── Limitations ──
    if limitations and q_type in ("WHO_IS", "FACTS", "GENERAL"):
        for lim in limitations[:2]:
            desc = lim.get("description", "") if isinstance(lim, dict) else str(lim)
            if desc:
                lines.append(f"\n{desc}")

    # ── Research status closing ──
    corroboration = snapshot_dict.get("external_corroboration", "NONE")
    corroboration_desc = {
        "NONE": "nessuna corroborazione esterna",
        "PARTIAL": "corrobazione esterna parziale",
        "ACCEPTED": "corrobazione esterna accettata",
        "CONFLICTING": "corrobazione esterna in conflitto",
    }.get(corroboration, corroboration)
    identity_desc = {
        "RESOLVED": "identità risolta",
        "PARTIAL": "identità parzialmente ricostruita",
        "UNRESOLVED": "identità non risolta",
        "INCOMPLETE_TARGET": "dati insufficienti per identificare il soggetto",
    }.get(identity, identity)

    if q_type in ("WHO_IS", "FACTS", "GENERAL"):
        lines.append(f"\nStato complessivo della ricerca: {identity_desc}, {corroboration_desc}.")

    return "\n".join(lines)
