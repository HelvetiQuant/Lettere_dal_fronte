"""Faction Bundle Builder — Constructs independent evidence bundles per faction.

For each faction, builds a FactionBundle containing:
- Sources classified to that faction
- Claims extracted from those sources
- Event model (chronology, objectives, units, locations, losses, results)
- Independent lineage count

Does NOT merge claims across factions. Each bundle is independent.

EVENT ONLY.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from viewpoint_models import (
    FactionAlignment,
    FactionBundle,
    FactionClaim,
    SourceFactionClassification,
    ClaimNature,
    EventPhase,
)
from source_faction_classifier import classify_source


# Predicates that describe an event dimension
_EVENT_DIMENSIONS = [
    "event_name", "start_date", "end_date", "location", "objectives",
    "units_involved", "commanders", "movements", "casualties",
    "outcome", "causes", "consequences", "terminology",
]

# Maps predicates to event phases
_PHASE_PREDICATES = {
    "prelude_context": EventPhase.PRELUDE,
    "initial_attack": EventPhase.PHASE_1,
    "main_assault": EventPhase.PHASE_2,
    "counterattack": EventPhase.PHASE_3,
    "outcome": EventPhase.OUTCOME,
    "aftermath": EventPhase.AFTERMATH,
    "start_date": EventPhase.PRELUDE,
    "end_date": EventPhase.OUTCOME,
    "casualties": EventPhase.AFTERMATH,
    "consequences": EventPhase.AFTERMATH,
}


def _determine_claim_nature(predicate: str, value: str) -> ClaimNature:
    """Determine if a claim is an observable fact or an interpretation."""
    interpretation_markers = [
        "perché", "because", "a causa di", "due to", "caused by",
        "dopo aver", "after having", "colpa di", "fault of",
        "incapacità", "incompetence", "codardia", "cowardice",
        "eroismo", "heroism", "tradimento", "betrayal",
    ]
    value_lower = value.lower()
    if any(m in value_lower for m in interpretation_markers):
        if any(m in value_lower for m in ["causa", "cause", "perché", "because", "due to"]):
            return ClaimNature.CAUSAL_INTERPRETATION
        return ClaimNature.INTERPRETATION

    # Attribution markers
    attribution_markers = ["responsabile", "responsible", "colpa", "fault", "deciso da", "decided by"]
    if any(m in value_lower for m in attribution_markers):
        return ClaimNature.ATTRIBUTION

    return ClaimNature.OBSERVABLE_FACT


def _determine_event_phase(predicate: str) -> EventPhase:
    """Determine the event phase for a predicate."""
    return _PHASE_PREDICATES.get(predicate, EventPhase.UNPHASED)


def _normalize_claim_text(predicate: str, value: str) -> tuple[str, str]:
    """Normalize claim text, preserving raw form.

    Returns (normalized_claim, perspective_language).
    """
    # Perspective language detection — keep original terminology
    perspective_language = ""

    # Italian military terminology that signals perspective
    italian_terms = ["ripiegamento", "ritirata strategica", "occupazione", "resistenza"]
    german_terms = ["rückzug", "abwehr", "durchbruch", "gefangennahme"]

    value_lower = value.lower()
    if any(t in value_lower for t in italian_terms):
        perspective_language = "italian_military"
    elif any(t in value_lower for t in german_terms):
        perspective_language = "german_military"

    # Normalized form: strip perspective-laden language
    normalized = value
    # Keep as-is for now — semantic normalization happens in CommonFactResolver
    return normalized, perspective_language


def build_faction_claims(
    faction: FactionAlignment,
    sources: list[SourceFactionClassification],
    raw_observations: list[dict[str, Any]],
) -> list[FactionClaim]:
    """Build claims for a faction from its sources and observations.

    Args:
        faction: The faction alignment
        sources: Sources classified to this faction
        raw_observations: Observation dicts with predicate, value, source_id, etc.
    """
    faction_source_ids = {s.source_id for s in sources}
    claims: list[FactionClaim] = []

    for obs in raw_observations:
        obs_source_id = obs.get("source_id", "")
        if obs_source_id not in faction_source_ids:
            continue

        predicate = obs.get("predicate", "")
        value = obs.get("value", "")
        raw_claim = obs.get("raw_text", f"{predicate}: {value}")

        if not predicate or not value:
            continue

        normalized, perspective_lang = _normalize_claim_text(predicate, value)
        nature = _determine_claim_nature(predicate, value)
        phase = _determine_event_phase(predicate)

        claim = FactionClaim(
            claim_id=f"claim_{faction.value}_{len(claims):04d}",
            predicate=predicate,
            value=value,
            raw_claim=raw_claim,
            normalized_claim=normalized,
            perspective_language=perspective_lang,
            claim_nature=nature,
            event_phase=phase,
            source_ids=[obs_source_id],
            lineage_ids=obs.get("lineage_ids", []),
            confidence=obs.get("confidence", 0.5),
            evidence_ids=obs.get("evidence_ids", []),
            temporal_proximity=obs.get("temporal_proximity", 0.5),
            specificity=obs.get("specificity", 0.5),
            relevance=obs.get("relevance", 0.5),
        )
        claims.append(claim)

    return claims


def build_faction_event_model(claims: list[FactionClaim]) -> dict[str, Any]:
    """Build a structured event model from a faction's claims."""
    model = {
        "event_identification": "",
        "chronology": {},
        "objectives": [],
        "movements": [],
        "units": [],
        "locations": [],
        "casualties": {},
        "declared_results": "",
        "attributed_causes": [],
        "consequences": [],
        "terminology": [],
    }

    for claim in claims:
        if claim.predicate == "event_name" and not model["event_identification"]:
            model["event_identification"] = claim.value
        elif claim.predicate in ("start_date", "end_date"):
            model["chronology"][claim.predicate] = claim.value
        elif claim.predicate == "objectives":
            model["objectives"].append(claim.value)
        elif claim.predicate == "movements":
            model["movements"].append(claim.value)
        elif claim.predicate == "units_involved":
            model["units"].append(claim.value)
        elif claim.predicate == "location":
            model["locations"].append(claim.value)
        elif claim.predicate == "casualties":
            model["casualties"].setdefault("values", []).append(claim.value)
        elif claim.predicate == "outcome":
            model["declared_results"] = claim.value
        elif claim.predicate == "causes":
            model["attributed_causes"].append(claim.value)
        elif claim.predicate == "consequences":
            model["consequences"].append(claim.value)
        elif claim.predicate == "terminology":
            model["terminology"].append({"term": claim.value, "raw": claim.raw_claim})

    return model


def compute_independent_lineages(sources: list[SourceFactionClassification]) -> int:
    """Count independent lineages among a faction's sources."""
    lineage_ids = set()
    for s in sources:
        lid = s.metadata.get("lineage_id")
        if lid:
            lineage_ids.add(lid)
        else:
            # Each source without explicit lineage is its own
            lineage_ids.add(f"source_{s.source_id}")
    return len(lineage_ids)


def build_faction_bundles(
    all_sources: list[dict[str, Any]],
    all_observations: list[dict[str, Any]],
    event_context: dict[str, Any],
) -> list[FactionBundle]:
    """Build independent FactionBundles for all factions present in the data.

    Args:
        all_sources: List of source dicts with source_id, label, metadata
        all_observations: List of observation dicts with predicate, value, source_id
        event_context: Event metadata (id, nome, data_inizio, data_fine, conflict)

    Returns:
        List of FactionBundle, one per faction found.
    """
    # Step 1: Classify all sources
    classifications: list[SourceFactionClassification] = []
    for src in all_sources:
        cls = classify_source(
            source_id=src.get("source_id", ""),
            source_label=src.get("label", src.get("name", "")),
            source_metadata=src.get("metadata", src),
            event_context=event_context,
        )
        classifications.append(cls)

    # Step 2: Group sources by faction
    faction_sources: dict[FactionAlignment, list[SourceFactionClassification]] = {}
    for cls in classifications:
        faction_sources.setdefault(cls.faction_alignment, []).append(cls)

    # Step 3: Build a bundle for each faction
    bundles: list[FactionBundle] = []
    for faction, sources in faction_sources.items():
        if faction == FactionAlignment.UNKNOWN and len(sources) == 0:
            continue

        claims = build_faction_claims(faction, sources, all_observations)
        event_model = build_faction_event_model(claims)
        independent_count = compute_independent_lineages(sources)

        # Determine coverage dimensions
        coverage = list({c.predicate for c in claims if c.predicate in _EVENT_DIMENSIONS})

        bundle = FactionBundle(
            faction_alignment=faction,
            sources=sources,
            claims=claims,
            event_model=event_model,
            raw_source_count=len(sources),
            independent_lineage_count=independent_count,
            coverage_dimensions=coverage,
        )
        bundles.append(bundle)

    # Sort bundles by raw_source_count descending (most documented first)
    bundles.sort(key=lambda b: b.raw_source_count, reverse=True)

    return bundles
