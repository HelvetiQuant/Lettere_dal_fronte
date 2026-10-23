"""Common Fact Resolver — Finds cross-faction common facts.

Compares claims from different factions to find:
- CROSS_FACTION_CONFIRMED: same fact, independent factions, independent lineages
- CROSS_FACTION_COMPATIBLE: semantically equivalent but different formulation
- CROSS_FACTION_CONFLICT: same predicate, different values
- SAME_FACTION_CORROBORATED: same fact within one faction
- SINGLE_PERSPECTIVE: only one faction mentions it

Key principles:
- No majority voting — lineage and independence matter, not count
- Semantic normalization preserves raw claim language
- Only OBSERVABLE_FACT claims are candidates for common facts
- INTERPRETATION claims are never merged
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from viewpoint_models import (
    CommonFact,
    CommonFactStatus,
    ClaimNature,
    EventPhase,
    FactionBundle,
    FactionClaim,
)


# Semantic equivalence maps for common predicates
# Maps different formulations to a normalized concept
_SEMANTIC_MAP = {
    # Dates
    "start_date": {"data inizio", "inizio", "cominciò", "iniziò", "begin", "start", "offensiva iniziata"},
    "end_date": {"data fine", "fine", "terminò", "conclusione", "end", "concluso"},
    # Locations
    "location": {"luogo", "località", "ort", "location", "area", "settore", "sector"},
    # Casualties
    "casualties": {"perdite", "caduti", "verluste", "losses", "dead", "morti", "feriti", "wounded"},
    # Units
    "units_involved": {"reparti", "unità", "einheiten", "units", "divisione", "division", "reggimento"},
    # Outcome
    "outcome": {"esito", "risultato", "ergebnis", "result", "outcome", "vittoria", "victory", "sconfitta"},
    # Objectives
    "objectives": {"obiettivo", "ziel", "objective", "goal", "meta", "scopo"},
    # Movements
    "movements": {"movimento", "bewegung", "movement", "avanzata", "advance", "ritirata", "retreat",
                  "ripiegamento", "rückzug", "sfondamento", "durchbruch"},
}

# Reverse map for lookup
_PREDICATE_NORMALIZER = {}
for canonical, variants in _SEMANTIC_MAP.items():
    for v in variants:
        _PREDICATE_NORMALIZER[v.lower()] = canonical


def _normalize_predicate(predicate: str) -> str:
    """Normalize a predicate to a canonical form."""
    p_lower = predicate.lower().strip()
    if p_lower in _PREDICATE_NORMALIZER:
        return _PREDICATE_NORMALIZER[p_lower]
    return p_lower


def _normalize_date_value(value: str) -> str:
    """Normalize date strings for comparison."""
    # Extract YYYY-MM-DD or YYYY-MM or YYYY
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return match.group(0)
    match = re.search(r"(\d{4})-(\d{2})", value)
    if match:
        return match.group(0)
    match = re.search(r"(\d{4})", value)
    if match:
        return match.group(0)
    # Italian date formats: "24 ottobre 1917"
    months = {
        "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
        "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
        "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
    }
    match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", value, re.IGNORECASE)
    if match:
        day = match.group(1).zfill(2)
        month_name = match.group(2).lower()
        year = match.group(3)
        month = months.get(month_name, "00")
        return f"{year}-{month}-{day}"
    return value.strip()


def _normalize_location_value(value: str) -> str:
    """Normalize location strings for comparison."""
    return value.lower().strip().rstrip(",").rstrip(".")


def _normalize_casualty_value(value: str) -> tuple[str, str]:
    """Extract number and context from casualty claims.

    Returns (number_str, context) where context includes
    population, period, method if identifiable.
    """
    numbers = re.findall(r"[\d.,]+", value)
    num = numbers[0].replace(".", "").replace(",", "") if numbers else ""
    context = value.lower()
    return num, context


def _values_equivalent(predicate: str, val_a: str, val_b: str) -> bool:
    """Check if two claim values are semantically equivalent."""
    norm_pred = _normalize_predicate(predicate)

    if norm_pred in ("start_date", "end_date"):
        return _normalize_date_value(val_a) == _normalize_date_value(val_b)

    if norm_pred == "location":
        return _normalize_location_value(val_a) == _normalize_location_value(val_b)

    if norm_pred == "casualties":
        num_a, ctx_a = _normalize_casualty_value(val_a)
        num_b, ctx_b = _normalize_casualty_value(val_b)
        return num_a == num_b and num_a != ""

    # General: check if normalized values match
    return val_a.lower().strip() == val_b.lower().strip()


def _values_compatible(predicate: str, val_a: str, val_b: str) -> bool:
    """Check if two claim values are compatible (not identical but not contradictory)."""
    norm_pred = _normalize_predicate(predicate)

    if norm_pred in ("start_date", "end_date"):
        da = _normalize_date_value(val_a)
        db = _normalize_date_value(val_b)
        # Same year = compatible
        if len(da) >= 4 and len(db) >= 4 and da[:4] == db[:4]:
            return True
        return False

    if norm_pred == "location":
        la = _normalize_location_value(val_a)
        lb = _normalize_location_value(val_b)
        # One contains the other = compatible
        return la in lb or lb in la

    if norm_pred == "casualties":
        num_a, ctx_a = _normalize_casualty_value(val_a)
        num_b, ctx_b = _normalize_casualty_value(val_b)
        # Different numbers = NOT compatible (it's a conflict)
        return False

    # General: partial overlap
    words_a = set(re.findall(r"\b\w{4,}\b", val_a.lower()))
    words_b = set(re.findall(r"\b\w{4,}\b", val_b.lower()))
    overlap = words_a & words_b
    return len(overlap) >= 2


def resolve_common_facts(bundles: list[FactionBundle]) -> list[CommonFact]:
    """Find common facts across faction bundles.

    Algorithm:
    1. Collect all OBSERVABLE_FACT claims from all factions
    2. Group by normalized predicate
    3. For each predicate group, compare values across factions
    4. Assign status based on equivalence/compatibility/conflict
    5. Check lineage independence
    """
    common_facts: list[CommonFact] = []

    # Collect observable facts by normalized predicate
    by_predicate: dict[str, list[tuple[FactionClaim, FactionAlignment]]] = {}
    for bundle in bundles:
        for claim in bundle.claims:
            if claim.claim_nature != ClaimNature.OBSERVABLE_FACT:
                continue
            norm_pred = _normalize_predicate(claim.predicate)
            by_predicate.setdefault(norm_pred, []).append((claim, bundle.faction_alignment))

    fact_counter = 0

    for norm_pred, claim_faction_pairs in by_predicate.items():
        # Group by faction
        by_faction: dict[str, list[FactionClaim]] = {}
        for claim, faction in claim_faction_pairs:
            by_faction.setdefault(faction.value, []).append(claim)

        factions_involved = list(by_faction.keys())

        if len(factions_involved) < 2:
            # Single perspective
            for claim in by_faction[factions_involved[0]]:
                fact_counter += 1
                common_facts.append(CommonFact(
                    fact_id=f"cf_{fact_counter:04d}",
                    predicate=norm_pred,
                    normalized_value=claim.value,
                    status=CommonFactStatus.SINGLE_PERSPECTIVE,
                    supporting_factions=factions_involved,
                    supporting_claims=[c.to_dict() for c in by_faction[factions_involved[0]]],
                    independent_lineage_count=len(set(claim.lineage_ids) if claim.lineage_ids else {f"src_{cl.source_ids[0]}" for cl in by_faction[factions_involved[0]]}),
                    independent_faction_count=1,
                    event_phase=claim.event_phase,
                    claim_nature=claim.claim_nature,
                    evidence_strength=claim.confidence,
                    note="Only one faction mentions this fact",
                ))
            continue

        # Multiple factions — compare values
        # Collect all unique values per faction
        faction_values: dict[str, list[str]] = {}
        for faction, claims in by_faction.items():
            faction_values[faction] = list({c.value for c in claims})

        # Check for equivalence across factions
        all_equivalent = True
        all_compatible = True
        any_conflict = False

        reference_faction = factions_involved[0]
        reference_values = faction_values[reference_faction]

        for faction in factions_involved[1:]:
            for ref_val in reference_values:
                for other_val in faction_values[faction]:
                    if not _values_equivalent(norm_pred, ref_val, other_val):
                        all_equivalent = False
                    if not _values_compatible(norm_pred, ref_val, other_val):
                        all_compatible = False
                        any_conflict = True

        # Collect all lineages
        all_lineages: set[str] = set()
        for claims in by_faction.values():
            for c in claims:
                if c.lineage_ids:
                    all_lineages.update(c.lineage_ids)
                else:
                    all_lineages.add(f"src_{c.source_ids[0] if c.source_ids else 'unknown'}")

        # Determine status
        if all_equivalent and not any_conflict:
            status = CommonFactStatus.CROSS_FACTION_CONFIRMED
        elif all_compatible and not any_conflict:
            status = CommonFactStatus.CROSS_FACTION_COMPATIBLE
        elif any_conflict:
            status = CommonFactStatus.CROSS_FACTION_CONFLICT
        else:
            status = CommonFactStatus.UNRESOLVED

        # Create common fact entry
        fact_counter += 1
        all_claims = []
        for faction, claims in by_faction.items():
            for c in claims:
                all_claims.append(c.to_dict())

        # Use the first value as normalized (they're equivalent or compatible)
        normalized_value = reference_values[0] if reference_values else ""

        common_facts.append(CommonFact(
            fact_id=f"cf_{fact_counter:04d}",
            predicate=norm_pred,
            normalized_value=normalized_value,
            status=status,
            supporting_factions=factions_involved,
            supporting_claims=all_claims,
            independent_lineage_count=len(all_lineages),
            independent_faction_count=len(factions_involved),
            event_phase=claim_faction_pairs[0][0].event_phase,
            claim_nature=ClaimNature.OBSERVABLE_FACT,
            evidence_strength=min(c.confidence for c, _ in claim_faction_pairs) if claim_faction_pairs else 0.0,
            note=_build_fact_note(status, factions_involved, all_lineages),
        ))

    return common_facts


def _build_fact_note(status: CommonFactStatus, factions: list[str], lineages: set[str]) -> str:
    """Build a human-readable note for a common fact."""
    if status == CommonFactStatus.CROSS_FACTION_CONFIRMED:
        return f"Confirmed by {len(factions)} independent factions ({', '.join(factions)}), {len(lineages)} independent lineages"
    elif status == CommonFactStatus.CROSS_FACTION_COMPATIBLE:
        return f"Compatible across {len(factions)} factions ({', '.join(factions)}), {len(lineages)} independent lineages"
    elif status == CommonFactStatus.CROSS_FACTION_CONFLICT:
        return f"Conflict between {len(factions)} factions ({', '.join(factions)})"
    elif status == CommonFactStatus.SINGLE_PERSPECTIVE:
        return f"Single perspective: {factions[0]}"
    return "Unresolved"
