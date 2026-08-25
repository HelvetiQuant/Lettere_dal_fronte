"""Omission Detector — Detects asymmetric omissions between factions.

Key principles:
- NOT_MENTIONED ≠ DENIED ≠ CONTRADICTED
- Absence of evidence ≠ evidence of absence
- Silence is not denial
- Distinguish: source consulted but silent, source unavailable, corpus incomplete

EVENT ONLY.
"""
from __future__ import annotations

from typing import Any

from viewpoint_models import (
    Omission,
    OmissionStatus,
    FactionBundle,
    FactionClaim,
    ClaimNature,
)
from common_fact_resolver import _normalize_predicate


# Predicates that are significant for omission detection
_SIGNIFICANT_PREDICATES = {
    "casualties", "perdite", "prisoners", "prigionieri",
    "civilians_killed", "civili_uccisi",
    "massacre", "eccidio", "strage",
    "surrender", "resa", "capitulation",
    "retreat", "ritirata", "ripiegamento",
    "defeat", "sconfitta",
    "war_crimes", "crimini_di_guerra",
    "summary_execution", "fucilazione",
    "deportation", "deportazione",
}


def detect_omissions(
    bundles: list[FactionBundle],
    all_predicates: set[str] | None = None,
) -> list[Omission]:
    """Detect asymmetric omissions between factions.

    For each significant predicate:
    - If one faction mentions it and another doesn't → NOT_MENTIONED
    - If one faction explicitly negates it → DENIED
    - If one faction contradicts the other's claim → CONTRADICTED

    Args:
        bundles: Faction bundles
        all_predicates: Optional set of all known predicates (for corpus completeness check)
    """
    omissions: list[Omission] = []

    # Collect predicates by faction
    faction_predicates: dict[str, set[str]] = {}
    faction_claims_by_pred: dict[str, dict[str, list[FactionClaim]]] = {}

    for bundle in bundles:
        faction = bundle.faction_alignment.value
        faction_predicates[faction] = set()
        faction_claims_by_pred[faction] = {}

        for claim in bundle.claims:
            norm_pred = _normalize_predicate(claim.predicate)
            faction_predicates[faction].add(norm_pred)
            faction_claims_by_pred[faction].setdefault(norm_pred, []).append(claim)

    all_factions = list(faction_predicates.keys())
    if len(all_factions) < 2:
        return omissions

    # Find all predicates mentioned by any faction
    all_mentioned = set()
    for preds in faction_predicates.values():
        all_mentioned.update(preds)

    # Filter to significant predicates
    significant = all_mentioned & _SIGNIFICANT_PREDICATES
    # Also include any predicate that's only mentioned by some factions
    for pred in all_mentioned:
        if pred not in significant:
            mentioning = sum(1 for f in all_factions if pred in faction_predicates[f])
            if mentioning < len(all_factions):
                significant.add(pred)

    om_counter = 0

    for pred in significant:
        mentioning_factions = [f for f in all_factions if pred in faction_predicates[f]]
        silent_factions = [f for f in all_factions if pred not in faction_predicates[f]]

        # Case 1: One mentions, others are silent -> NOT_MENTIONED
        if mentioning_factions and silent_factions:
            for mentioning in mentioning_factions:
                claims = faction_claims_by_pred[mentioning].get(pred, [])

                for claim in claims:
                    status = OmissionStatus.NOT_MENTIONED
                    note = f"Predicate '{pred}' is mentioned by {mentioning} but not by {', '.join(silent_factions)}"

                    # Check for explicit denial in silent factions' other claims
                    for silent in silent_factions:
                        for other_pred, other_claims in faction_claims_by_pred[silent].items():
                            for other_claim in other_claims:
                                if _is_explicit_denial(claim.value, other_claim.value):
                                    status = OmissionStatus.DENIED
                                    note = f"Predicate '{pred}': {mentioning} claims '{claim.value}', {silent} explicitly denies"
                                    break
                                if _is_contradiction(claim.value, other_claim.value, pred):
                                    status = OmissionStatus.CONTRADICTED
                                    note = f"Predicate '{pred}': {mentioning} claims '{claim.value}', {silent} contradicts with '{other_claim.value}'"
                                    break

                    om_counter += 1
                    omissions.append(Omission(
                        omission_id=f"om_{om_counter:04d}",
                        predicate=pred,
                        mentioning_faction=mentioning,
                        mentioning_claim=claim.to_dict(),
                        silent_factions=silent_factions,
                        status=status,
                        note=note,
                    ))

        # Case 2: Both factions mention the predicate but one explicitly denies
        # This is NOT an omission per se, but a denial/contradiction detected
        if len(mentioning_factions) >= 2:
            for i, faction_a in enumerate(mentioning_factions):
                for faction_b in mentioning_factions[i+1:]:
                    claims_a = faction_claims_by_pred[faction_a].get(pred, [])
                    claims_b = faction_claims_by_pred[faction_b].get(pred, [])
                    for claim_a in claims_a:
                        for claim_b in claims_b:
                            if _is_explicit_denial(claim_a.value, claim_b.value):
                                om_counter += 1
                                omissions.append(Omission(
                                    omission_id=f"om_{om_counter:04d}",
                                    predicate=pred,
                                    mentioning_faction=faction_a,
                                    mentioning_claim=claim_a.to_dict(),
                                    silent_factions=[faction_b],
                                    status=OmissionStatus.DENIED,
                                    note=f"Predicate '{pred}': {faction_a} claims '{claim_a.value}', {faction_b} explicitly denies with '{claim_b.value}'",
                                ))
                            elif _is_contradiction(claim_a.value, claim_b.value, pred):
                                om_counter += 1
                                omissions.append(Omission(
                                    omission_id=f"om_{om_counter:04d}",
                                    predicate=pred,
                                    mentioning_faction=faction_a,
                                    mentioning_claim=claim_a.to_dict(),
                                    silent_factions=[faction_b],
                                    status=OmissionStatus.CONTRADICTED,
                                    note=f"Predicate '{pred}': {faction_a} claims '{claim_a.value}', {faction_b} contradicts with '{claim_b.value}'",
                                ))

    return omissions


def _is_explicit_denial(value_a: str, value_b: str) -> bool:
    """Check if value_b explicitly denies value_a."""
    import re
    denial_markers = ["non", "negato", "negata", "negates", "denied", "false", "falso", "mai", "never", "no "]
    value_b_lower = value_b.lower()
    value_a_lower = value_a.lower()

    has_denial = any(m in value_b_lower for m in denial_markers)
    # Check if B references the same topic as A (use word matching to handle punctuation)
    words_a = set(re.findall(r"\b\w+\b", value_a_lower))
    words_b = set(re.findall(r"\b\w+\b", value_b_lower))
    # Remove common stop words from overlap
    stop_words = {"no", "not", "were", "was", "the", "a", "an", "of", "in", "on", "at", "by", "for", "and", "or", "to", "is", "it", "that", "this", "report", "false"}
    overlap = (words_a & words_b) - stop_words

    return has_denial and len(overlap) >= 1


def _is_contradiction(value_a: str, value_b: str, predicate: str) -> bool:
    """Check if value_b contradicts value_a on the same predicate."""
    # For casualties: different numbers = contradiction, not omission
    if predicate in ("casualties", "perdite"):
        import re
        nums_a = re.findall(r"\d+", value_a)
        nums_b = re.findall(r"\d+", value_b)
        if nums_a and nums_b and nums_a[0] != nums_b[0]:
            return True

    # For dates: different dates = contradiction
    if predicate in ("start_date", "end_date", "data_inizio", "data_fine"):
        return value_a.strip() != value_b.strip()

    return False
