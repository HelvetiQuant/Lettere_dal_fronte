"""NarrationEvidenceSelector — deterministic claim selection before the narrator.

The narrator must NOT receive 200-300 claims and hundreds of web leads.
This module selects a focused, diverse, and budget-limited set of claims
that are most relevant to the query, ranked by:

1. Exact relevance to the question
2. Identity resolved
3. Probative status (verified > probable > conflicting > unverified)
4. Correct semantic role
5. Temporal coherence
6. Primary/institutional source
7. Independence group diversity
8. Narrative coverage diversity
9. Data specificity

Web leads (unvalidated) are NEVER included in the main narration payload.
At most 5 are passed in a separate technical section, never as facts.

Budgets (configurable):
- FACT: max 12 direct claims + 4 conflict/limit/context
- PERSON: max 24 personal claims + 8 context/limit
- EVENT: max 60 claims (80 in deep mode), distributed across categories
- web leads: 0 in main payload, max 5 in technical section
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from evidence_snapshot_v7 import (
    EvidenceSnapshotV7, ClaimV7, ContextClaimV7,
    CLAIM_FIELDS_V7,
)
from v7_claim_rules import classify_claim_status


# ─── Claim narration policy ─────────────────────────────────────────────────

NARRATION_POLICY = {
    "APPROVED": "assert",
    "PROBABLE": "qualify",
    "NEEDS_REVIEW": "gap_only",
    "REJECTED": "excluded",
    "CONTEXT": "context_only",
}

# Reason codes for omission
OMISSION_REASONS = {
    "over_budget": "over_budget_lower_priority",
    "irrelevant": "irrelevant_to_query",
    "rejected": "rejected_by_claim_rules",
    "duplicate_chain": "duplicate_source_chain",
    "insufficient_identity": "insufficient_identity",
    "semantic_role_mismatch": "semantic_role_mismatch",
    "temporal_conflict": "temporal_conflict",
    "web_lead_unvalidated": "web_lead_not_validated",
    "needs_review_non_direct": "needs_review_not_directly_relevant",
}


@dataclass
class SelectedEvidence:
    """Result of evidence selection for narration."""
    narratable_claims: List[Dict[str, Any]] = field(default_factory=list)
    claim_allowlist: List[str] = field(default_factory=list)
    omitted_claims: List[Dict[str, str]] = field(default_factory=list)
    web_leads_technical: List[Dict[str, Any]] = field(default_factory=list)
    sources_for_claims: Dict[str, List[str]] = field(default_factory=dict)
    selection_stats: Dict[str, Any] = field(default_factory=dict)


# ─── Budget configuration ───────────────────────────────────────────────────

DEFAULT_BUDGETS = {
    "FACT": {
        "direct": 12,
        "conflict_limit_context": 4,
        "web_leads": 0,
        "web_leads_technical": 5,
    },
    "PERSON": {
        "personal": 24,
        "context_limit": 8,
        "web_leads": 0,
        "web_leads_technical": 5,
    },
    "EVENT": {
        "total": 60,
        "total_deep": 80,
        "web_leads": 0,
        "web_leads_technical": 5,
    },
}


# ─── Priority scoring ───────────────────────────────────────────────────────

CLAIM_STATUS_PRIORITY = {
    "APPROVED": 100,
    "PROBABLE": 80,
    "CONTEXT": 60,
    "NEEDS_REVIEW": 40,
    "REJECTED": 0,
}

PREDICATE_RELEVANCE_PERSON = {
    "full_birth_date": 95,
    "birth_date": 92,
    "birth_year": 90,
    "birth_place": 88,
    "paternity": 85,
    "rank": 82,
    "unit": 80,
    "military_unit": 80,
    "service_number": 75,
    "military_id": 75,
    "death_date": 92,
    "death_year": 88,
    "death_place": 85,
    "death_cause": 82,
    "fate": 85,
    "captivity": 78,
    "internment_place": 82,
    "burial": 82,
    "capture_place": 78,
    "capture_date": 76,
    "residence": 72,
    "date_note": 70,
    "work_command": 68,
    "assignment": 65,
    "decoration_type": 65,
    "decoration_year": 60,
    "draft_class": 72,
    "municipality": 68,
    "archive_letter": 50,
    "source_document": 55,
    "source_page": 45,
    "source_text": 40,
    "data_quality_note": 35,
}

PREDICATE_RELEVANCE_EVENT = {
    "event_start_date": 95,
    "event_end_date": 92,
    "event_location": 90,
    "event_description": 88,
    "event_phase_count": 75,
    "event_actors": 80,
}

PREDICATE_RELEVANCE_FACT = {
    # Fact depends on the predicate asked — all are relevant if they match
}


def _claim_to_narratable_dict(c: ClaimV7, snapshot: EvidenceSnapshotV7) -> Dict[str, Any]:
    """Convert a ClaimV7 to the narratable dict format for the AI input."""
    cd = {
        "claim_id": c.claim_id,
        "subject_id": c.subject_id,
        "predicate": c.predicate,
        "value_raw": c.value_raw or c.value_normalized,
        "value_normalized": c.value_normalized,
        "value_precision": c.normalization_status or "unknown",
        "semantic_role": c.context_scope or "",
        "verification_status": c.status.lower(),
        "status": c.status.upper(),
        "confidence": c.confidence,
        "source_ids": c.evidence_ids[:],
        "source_function": c.source_function or "person_evidence",
        "decision_reason": c.anomaly_note or "",
        "independence_group": "",
        "identity_confidence": "strong" if c.confidence >= 0.8 else ("medium" if c.confidence >= 0.5 else "weak"),
        "narration_policy": NARRATION_POLICY.get(classify_claim_status({
            "status": c.status, "confidence": c.confidence,
        }), "gap_only"),
    }
    return cd


def _context_claim_to_dict(c) -> Dict[str, Any]:
    """Convert a ContextClaimV7 (or ClaimV7 in context_claims) to narratable dict format."""
    # Handle ContextClaimV7
    if hasattr(c, "scope"):
        return {
            "claim_id": c.claim_id,
            "subject_id": "",
            "predicate": c.predicate,
            "value_raw": c.value,
            "value_normalized": c.value,
            "value_precision": "unknown",
            "semantic_role": c.scope or "",
            "verification_status": "context",
            "status": "CONTEXT",
            "confidence": 0.0,
            "source_ids": c.source_refs[:] if hasattr(c, "source_refs") else [],
            "source_function": "event_context",
            "decision_reason": "",
            "independence_group": "",
            "identity_confidence": "weak",
            "narration_policy": "context_only",
        }
    # Handle ClaimV7 that ended up in context_claims
    return {
        "claim_id": c.claim_id,
        "subject_id": c.subject_id,
        "predicate": c.predicate,
        "value_raw": c.value_raw or c.value_normalized,
        "value_normalized": c.value_normalized,
        "value_precision": c.normalization_status or "unknown",
        "semantic_role": c.context_scope or "",
        "verification_status": c.status.lower(),
        "status": c.status,
        "confidence": c.confidence,
        "source_ids": c.evidence_ids[:] if hasattr(c, "evidence_ids") else [],
        "source_function": c.source_function or "event_context",
        "decision_reason": c.anomaly_note or "",
        "independence_group": "",
        "identity_confidence": "strong" if c.confidence >= 0.8 else ("medium" if c.confidence >= 0.5 else "weak"),
        "narration_policy": "context_only",
    }


def _score_claim(claim_dict: Dict[str, Any], request_type: str) -> float:
    """Score a claim for narration priority. Higher = more relevant."""
    status = claim_dict.get("status", claim_dict.get("verification_status", "asserted")).upper()
    bucket = classify_claim_status(claim_dict)
    score = CLAIM_STATUS_PRIORITY.get(bucket, 30)

    # Predicate relevance
    predicate = claim_dict.get("predicate", "")
    if request_type == "PERSON":
        score += PREDICATE_RELEVANCE_PERSON.get(predicate, 50)
    elif request_type == "EVENT":
        score += PREDICATE_RELEVANCE_EVENT.get(predicate, 50)
    elif request_type == "FACT":
        score += 70  # All claims potentially relevant for FACT

    # Identity confidence bonus
    id_conf = claim_dict.get("identity_confidence", "weak")
    if id_conf == "strong":
        score += 10
    elif id_conf == "medium":
        score += 5

    # Source function penalty
    src_func = claim_dict.get("source_function", "")
    if src_func in ("research_lead", "homonym_candidate", "rejected_identity_link"):
        score -= 50

    # Temporal scope check
    temporal = claim_dict.get("temporal_scope", {})
    if temporal and temporal.get("conflict"):
        score -= 80

    return max(score, 0)


def _deduplicate_by_chain(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate claims by independence group / source chain.

    If two claims share the same independence_group and predicate,
    keep only the highest-scored one.
    """
    seen = {}
    result = []
    for c in sorted(claims, key=lambda x: x.get("_score", 0), reverse=True):
        key = (c.get("independence_group", ""), c.get("predicate", ""))
        if key in seen:
            continue
        seen[key] = True
        result.append(c)
    return result


def _ensure_diversity(claims: List[Dict[str, Any]], budget: int) -> List[Dict[str, Any]]:
    """Select claims ensuring diversity across predicate categories.

    Instead of taking the top-N by score, distribute across categories:
    identity, chronology, location, military, fate, context.
    """
    categories = {
        "identity": ["full_birth_date", "birth_date", "birth_year", "birth_place", "paternity", "residence", "municipality", "draft_class"],
        "military": ["rank", "unit", "military_unit", "service_number", "military_id", "decoration_type", "decoration_year"],
        "chronology": ["capture_date", "capture_place", "death_date", "death_year", "date_note", "event_start_date", "event_end_date"],
        "location": ["internment_place", "death_place", "burial", "event_location", "captivity", "work_command"],
        "fate": ["fate", "death_cause"],
        "assignment": ["assignment"],
        "provenance": ["archive_letter", "source_document", "source_page", "source_text", "data_quality_note"],
        "event": ["event_description", "event_phase_count", "event_actors"],
        "context": ["web_context"],
    }

    cat_buckets: Dict[str, List[Dict[str, Any]]] = {k: [] for k in categories}
    uncategorized = []

    for c in claims:
        pred = c.get("predicate", "")
        placed = False
        for cat, preds in categories.items():
            if pred in preds:
                cat_buckets[cat].append(c)
                placed = True
                break
        if not placed:
            uncategorized.append(c)

    # Sort each bucket by score
    for cat in cat_buckets:
        cat_buckets[cat].sort(key=lambda x: x.get("_score", 0), reverse=True)

    uncategorized.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # Distribute budget across non-empty categories
    non_empty = [cat for cat in cat_buckets if cat_buckets[cat]]
    total_cats = len(non_empty) + (1 if uncategorized else 0)
    if total_cats == 0:
        return []

    per_cat = max(1, budget // total_cats)
    selected = []

    for cat in non_empty:
        selected.extend(cat_buckets[cat][:per_cat])

    # Fill remaining budget from uncategorized
    remaining = budget - len(selected)
    if remaining > 0:
        selected.extend(uncategorized[:remaining])

    # If still under budget, top up from all buckets
    if len(selected) < budget:
        all_remaining = []
        for cat in non_empty:
            all_remaining.extend(cat_buckets[cat][per_cat:])
        all_remaining.extend(uncategorized[len(uncategorized[:remaining]):])
        all_remaining.sort(key=lambda x: x.get("_score", 0), reverse=True)
        selected.extend(all_remaining[:budget - len(selected)])

    return selected[:budget]


class NarrationEvidenceSelector:
    """Deterministic, testable claim selection for narration.

    Usage:
        selector = NarrationEvidenceSelector()
        selected = selector.select(snapshot, request_type="PERSON")
        # selected.narratable_claims → list of claim dicts for AI
        # selected.claim_allowlist → list of valid claim_ids
        # selected.omitted_claims → list of {claim_id, reason}
    """

    def __init__(self, budgets: Optional[Dict[str, Any]] = None):
        self._budgets = budgets or DEFAULT_BUDGETS

    def select(
        self,
        snapshot: EvidenceSnapshotV7,
        request_type: str = "PERSON",
        requested_depth: str = "standard",
    ) -> SelectedEvidence:
        """Select claims for narration based on request type and budget."""
        result = SelectedEvidence()

        # Collect all candidate claims
        all_person_claims = []
        all_context_claims = []

        for c in snapshot.person_claims:
            cd = _claim_to_narratable_dict(c, snapshot)
            all_person_claims.append(cd)

        for c in snapshot.context_claims:
            cd = _context_claim_to_dict(c)
            all_context_claims.append(cd)

        # Also include accepted/asserted/conflicting from legacy fields
        for c in snapshot.accepted_claims:
            cd = _claim_to_narratable_dict(c, snapshot)
            if cd not in all_person_claims:
                all_person_claims.append(cd)
        for c in snapshot.asserted_claims:
            cd = _claim_to_narratable_dict(c, snapshot)
            if cd not in all_person_claims:
                all_person_claims.append(cd)
        for c in snapshot.conflicting_claims:
            cd = _claim_to_narratable_dict(c, snapshot)
            if cd not in all_person_claims:
                all_person_claims.append(cd)

        # Score all claims
        for cd in all_person_claims:
            cd["_score"] = _score_claim(cd, request_type)
        for cd in all_context_claims:
            cd["_score"] = _score_claim(cd, request_type)

        # Separate by status
        approved_claims = [c for c in all_person_claims if classify_claim_status(c) == "APPROVED"]
        probable_claims = [c for c in all_person_claims if classify_claim_status(c) == "PROBABLE"]
        conflicting_claims = [c for c in all_person_claims if classify_claim_status(c) == "NEEDS_REVIEW" and c.get("verification_status") == "conflicting"]
        needs_review_claims = [c for c in all_person_claims if classify_claim_status(c) == "NEEDS_REVIEW" and c.get("verification_status") != "conflicting"]
        rejected_claims = [c for c in all_person_claims if classify_claim_status(c) == "REJECTED"]

        # Deduplicate by chain
        approved_claims = _deduplicate_by_chain(approved_claims)
        probable_claims = _deduplicate_by_chain(probable_claims)
        conflicting_claims = _deduplicate_by_chain(conflicting_claims)

        # Apply budgets based on request type
        if request_type == "FACT":
            budget = self._budgets["FACT"]
            direct_budget = budget["direct"]
            conflict_budget = budget["conflict_limit_context"]

            # For FACT, prioritize claims matching the asked predicate
            # (all claims are candidates since we don't know the exact predicate)
            direct_pool = approved_claims + probable_claims
            direct_pool.sort(key=lambda x: x.get("_score", 0), reverse=True)
            selected_direct = direct_pool[:direct_budget]

            conflict_pool = conflicting_claims + needs_review_claims
            conflict_pool.sort(key=lambda x: x.get("_score", 0), reverse=True)
            selected_conflict = conflict_pool[:conflict_budget]

            narratable = selected_direct + selected_conflict

        elif request_type == "PERSON":
            budget = self._budgets["PERSON"]
            personal_budget = budget["personal"]
            context_budget = budget["context_limit"]

            personal_pool = approved_claims + probable_claims
            personal_pool.sort(key=lambda x: x.get("_score", 0), reverse=True)
            selected_personal = _ensure_diversity(personal_pool, personal_budget)

            context_pool = all_context_claims + conflicting_claims + needs_review_claims
            context_pool.sort(key=lambda x: x.get("_score", 0), reverse=True)
            selected_context = context_pool[:context_budget]

            narratable = selected_personal + selected_context

        elif request_type == "EVENT":
            budget = self._budgets["EVENT"]
            total_budget = budget["total_deep"] if requested_depth == "deep" else budget["total"]

            event_pool = approved_claims + probable_claims + all_context_claims + conflicting_claims
            event_pool.sort(key=lambda x: x.get("_score", 0), reverse=True)
            narratable = _ensure_diversity(event_pool, total_budget)

        else:
            narratable = []

        # Build allowlist
        allowlist = [c["claim_id"] for c in narratable]

        # Build omitted list
        all_candidate_ids = {c["claim_id"] for c in all_person_claims + all_context_claims}
        selected_ids = set(allowlist)
        omitted_ids = all_candidate_ids - selected_ids

        for cid in omitted_ids:
            # Find the claim to determine reason
            reason = "over_budget_lower_priority"
            for c in rejected_claims:
                if c["claim_id"] == cid:
                    reason = "rejected_by_claim_rules"
                    break
            else:
                for c in needs_review_claims:
                    if c["claim_id"] == cid:
                        reason = "needs_review_not_directly_relevant"
                        break
            result.omitted_claims.append({
                "claim_id": cid,
                "reason": reason,
            })

        # Build web leads technical section (max 5, never as facts)
        web_leads_tech = []
        for l in snapshot.web_leads[:self._budgets.get(request_type, {}).get("web_leads_technical", 5)]:
            web_leads_tech.append({
                "lead_id": l.lead_id,
                "title": l.title,
                "provider": l.provider,
                "url": l.url_canonical or "",
            })

        # Build sources_for_claims mapping (claim_id → source_ids)
        sources_for_claims = {}
        for c in narratable:
            sources_for_claims[c["claim_id"]] = c.get("source_ids", [])

        # Strip internal _score from output
        for c in narratable:
            c.pop("_score", None)

        result.narratable_claims = narratable
        result.claim_allowlist = allowlist
        result.web_leads_technical = web_leads_tech
        result.sources_for_claims = sources_for_claims
        result.selection_stats = {
            "total_candidates": len(all_candidate_ids),
            "selected": len(narratable),
            "omitted": len(omitted_ids),
            "approved_available": len(approved_claims),
            "probable_available": len(probable_claims),
            "conflicting_available": len(conflicting_claims),
            "needs_review_available": len(needs_review_claims),
            "rejected_available": len(rejected_claims),
            "web_leads_total": len(snapshot.web_leads),
            "web_leads_technical": len(web_leads_tech),
        }

        return result
