"""Divergence Engine — Classifies divergences between faction reconstructions.

Divergence types:
- DATE_CONFLICT, TIME_CONFLICT, LOCATION_CONFLICT, UNIT_CONFLICT
- CASUALTY_CONFLICT, CAUSALITY_CONFLICT, INTENT_CONFLICT
- OUTCOME_CONFLICT, RESPONSIBILITY_CONFLICT, SEQUENCE_CONFLICT
- TERMINOLOGY_CONFLICT, OMISSION_ASYMMETRY, PROPAGANDA_SUSPECTED

Key principles:
- No majority voting — number of sources doesn't decide
- No averaging of conflicting values
- DISPUTED_QUANTIFICATION preserves both values with provenance
- RESOLVED_BY_STRONGER_EVIDENCE only with explicit probatory criterion
- Fact vs interpretation separation maintained
"""
from __future__ import annotations

import re
from typing import Any

from viewpoint_models import (
    Divergence,
    DivergenceType,
    DivergenceResolution,
    ClaimNature,
    EventPhase,
    FactionBundle,
    FactionClaim,
    CommonFact,
    CommonFactStatus,
)
from common_fact_resolver import _normalize_predicate


# Maps predicates to divergence types
_PREDICATE_DIVERGENCE_MAP = {
    "start_date": DivergenceType.DATE_CONFLICT,
    "end_date": DivergenceType.DATE_CONFLICT,
    "data_inizio": DivergenceType.DATE_CONFLICT,
    "data_fine": DivergenceType.DATE_CONFLICT,
    "time": DivergenceType.TIME_CONFLICT,
    "ora": DivergenceType.TIME_CONFLICT,
    "location": DivergenceType.LOCATION_CONFLICT,
    "luogo": DivergenceType.LOCATION_CONFLICT,
    "località": DivergenceType.LOCATION_CONFLICT,
    "units_involved": DivergenceType.UNIT_CONFLICT,
    "reparti": DivergenceType.UNIT_CONFLICT,
    "casualties": DivergenceType.CASUALTY_CONFLICT,
    "perdite": DivergenceType.CASUALTY_CONFLICT,
    "causes": DivergenceType.CAUSALITY_CONFLICT,
    "cause": DivergenceType.CAUSALITY_CONFLICT,
    "objectives": DivergenceType.INTENT_CONFLICT,
    "obiettivo": DivergenceType.INTENT_CONFLICT,
    "outcome": DivergenceType.OUTCOME_CONFLICT,
    "esito": DivergenceType.OUTCOME_CONFLICT,
    "responsibility": DivergenceType.RESPONSIBILITY_CONFLICT,
    "movements": DivergenceType.SEQUENCE_CONFLICT,
    "sequence": DivergenceType.SEQUENCE_CONFLICT,
}


def _classify_divergence_type(predicate: str, claims_a: list[FactionClaim], claims_b: list[FactionClaim]) -> DivergenceType:
    """Classify the type of divergence based on predicate and claim content."""
    norm_pred = _normalize_predicate(predicate)

    if norm_pred in _PREDICATE_DIVERGENCE_MAP:
        return _PREDICATE_DIVERGENCE_MAP[norm_pred]

    # Check if it's a terminology issue (same fact, different words)
    val_a = claims_a[0].value.lower() if claims_a else ""
    val_b = claims_b[0].value.lower() if claims_b else ""
    words_a = set(re.findall(r"\b\w{4,}\b", val_a))
    words_b = set(re.findall(r"\b\w{4,}\b", val_b))
    overlap = words_a & words_b

    if len(overlap) >= 2 and len(words_a) >= 3 and len(words_b) >= 3:
        return DivergenceType.TERMINOLOGY_CONFLICT

    # Check for interpretation conflicts
    if any(c.claim_nature in (ClaimNature.INTERPRETATION, ClaimNature.CAUSAL_INTERPRETATION) for c in claims_a + claims_b):
        return DivergenceType.CAUSALITY_CONFLICT

    return DivergenceType.UNKNOWN_CONFLICT


def _determine_resolution(
    claims_a: list[FactionClaim],
    claims_b: list[FactionClaim],
    divergence_type: DivergenceType,
) -> tuple[DivergenceResolution, str]:
    """Determine if a divergence can be resolved and how.

    RESOLVED_BY_STRONGER_EVIDENCE only when:
    - One side has contemporary primary source, other has postwar memoir
    - One side has multiple independent lineages, other has single dependent source
    - Explicit probatory criterion is met
    """
    # Check temporal layer advantage
    temporal_a = [c.temporal_proximity for c in claims_a]
    temporal_b = [c.temporal_proximity for c in claims_b]
    avg_temp_a = sum(temporal_a) / len(temporal_a) if temporal_a else 0
    avg_temp_b = sum(temporal_b) / len(temporal_b) if temporal_b else 0

    # Check lineage independence
    lineages_a = set()
    lineages_b = set()
    for c in claims_a:
        if c.lineage_ids:
            lineages_a.update(c.lineage_ids)
        else:
            lineages_a.add(f"src_{c.source_ids[0] if c.source_ids else 'a'}")
    for c in claims_b:
        if c.lineage_ids:
            lineages_b.update(c.lineage_ids)
        else:
            lineages_b.add(f"src_{c.source_ids[0] if c.source_ids else 'b'}")

    # Strong evidence resolution
    if avg_temp_a > 0.8 and avg_temp_b < 0.3 and len(lineages_a) >= 2:
        return (
            DivergenceResolution.RESOLVED_BY_STRONGER_EVIDENCE,
            f"Faction A has contemporary primary sources ({len(lineages_a)} independent lineages) "
            f"vs Faction B postwar testimony ({len(lineages_b)} lineage). "
            f"Temporal proximity: A={avg_temp_a:.2f}, B={avg_temp_b:.2f}",
        )
    if avg_temp_b > 0.8 and avg_temp_a < 0.3 and len(lineages_b) >= 2:
        return (
            DivergenceResolution.RESOLVED_BY_STRONGER_EVIDENCE,
            f"Faction B has contemporary primary sources ({len(lineages_b)} independent lineages) "
            f"vs Faction A postwar testimony ({len(lineages_a)} lineage). "
            f"Temporal proximity: A={avg_temp_a:.2f}, B={avg_temp_b:.2f}",
        )

    # Partial resolution: same date but different detail level
    if divergence_type in (DivergenceType.DATE_CONFLICT, DivergenceType.TIME_CONFLICT):
        return (
            DivergenceResolution.PARTIALLY_RESOLVED,
            "Dates partially overlap — core timeframe agreed, precise timing differs",
        )

    return (DivergenceResolution.UNRESOLVED, "")


def detect_divergences(
    bundles: list[FactionBundle],
    common_facts: list[CommonFact],
) -> list[Divergence]:
    """Detect and classify divergences between faction bundles.

    Args:
        bundles: Faction bundles with claims
        common_facts: Already resolved common facts

    Returns:
        List of classified Divergence objects.
    """
    divergences: list[Divergence] = []

    # Collect claims by predicate across factions
    by_predicate: dict[str, dict[str, list[FactionClaim]]] = {}
    for bundle in bundles:
        for claim in bundle.claims:
            norm_pred = _normalize_predicate(claim.predicate)
            by_predicate.setdefault(norm_pred, {}).setdefault(
                bundle.faction_alignment.value, []
            ).append(claim)

    # Find predicates with conflicts (different values across factions)
    conflict_predicates = set()
    for cf in common_facts:
        if cf.status == CommonFactStatus.CROSS_FACTION_CONFLICT:
            conflict_predicates.add(cf.predicate)

    div_counter = 0

    for pred, faction_claims in by_predicate.items():
        if len(faction_claims) < 2:
            continue

        # Check if values differ
        all_values = []
        for faction, claims in faction_claims.items():
            for c in claims:
                all_values.append((faction, c.value, c))

        # Check for value conflicts
        unique_values = set(v for _, v, _ in all_values)
        if len(unique_values) <= 1:
            continue  # No divergence

        # This is a divergence
        div_counter += 1
        div_type = _classify_divergence_type(
            pred,
            list(faction_claims.values())[0],
            list(faction_claims.values())[1] if len(faction_claims) > 1 else [],
        )

        # Build faction positions
        faction_positions = []
        for faction, claims in faction_claims.items():
            for c in claims:
                faction_positions.append({
                    "faction": faction,
                    "value": c.value,
                    "raw_claim": c.raw_claim,
                    "source_ids": c.source_ids,
                    "claim_nature": c.claim_nature.value,
                    "confidence": c.confidence,
                })

        # Determine resolution
        claims_list_a = list(faction_claims.values())[0]
        claims_list_b = list(faction_claims.values())[1] if len(faction_claims) > 1 else []
        resolution, reason = _determine_resolution(claims_list_a, claims_list_b, div_type)

        # Determine claim nature
        natures = [c.claim_nature for c in claims_list_a + claims_list_b]
        if ClaimNature.INTERPRETATION in natures or ClaimNature.CAUSAL_INTERPRETATION in natures:
            claim_nature = ClaimNature.INTERPRETATION
        else:
            claim_nature = ClaimNature.OBSERVABLE_FACT

        # Determine event phase
        phases = [c.event_phase for c in claims_list_a + claims_list_b]
        event_phase = phases[0] if phases else EventPhase.UNPHASED

        divergences.append(Divergence(
            divergence_id=f"div_{div_counter:04d}",
            divergence_type=div_type,
            predicate=pred,
            event_phase=event_phase,
            faction_positions=faction_positions,
            resolution=resolution,
            resolution_reason=reason,
            claim_nature=claim_nature,
            note=_build_divergence_note(div_type, faction_positions, resolution),
        ))

    return divergences


def _build_divergence_note(
    div_type: DivergenceType,
    positions: list[dict[str, Any]],
    resolution: DivergenceResolution,
) -> str:
    """Build a human-readable note for a divergence."""
    factions = [p["faction"] for p in positions]
    values = [p["value"] for p in positions]

    if div_type == DivergenceType.CASUALTY_CONFLICT:
        return (
            f"DISPUTED_QUANTIFICATION: factions report different casualty figures. "
            f"No averaging applied. Values: {', '.join(f'{f}={v}' for f, v in zip(factions, values))}. "
            f"Each value preserved with its source and method context."
        )
    elif div_type == DivergenceType.DATE_CONFLICT:
        return f"Date conflict: {', '.join(f'{f}={v}' for f, v in zip(factions, values))}"
    elif div_type == DivergenceType.CAUSALITY_CONFLICT:
        return (
            f"Interpretation conflict: factions attribute different causes. "
            f"These are INTERPRETATIONS, not observable facts. "
            f"Both preserved as attributed perspectives."
        )
    elif div_type == DivergenceType.TERMINOLOGY_CONFLICT:
        return (
            f"Terminology divergence: same event described with different terms. "
            f"Original formulations preserved."
        )

    return f"Divergence between {len(factions)} factions"
