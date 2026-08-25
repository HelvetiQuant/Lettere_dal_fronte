"""Viewpoints Service V2 — Comparative Historical Reconstruction Engine.

Orchestrates:
1. Source faction classification
2. Faction bundle building
3. Common fact resolution
4. Divergence detection
5. Omission detection
6. Comparative narration
7. Claim matrix construction
8. Metrics computation
9. Evidence snapshot integration

EVENT ONLY. Not for PERSON lookup.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from viewpoint_models import (
    ViewpointResult,
    ViewpointMetrics,
    FactionBundle,
    FactionAlignment,
    CommonFact,
    CommonFactStatus,
    Divergence,
    Omission,
    OmissionStatus,
    ClaimMatrixEntry,
    ClaimNature,
    EventPhase,
)
from faction_bundle_builder import build_faction_bundles
from common_fact_resolver import resolve_common_facts
from divergence_engine import detect_divergences
from omission_detector import detect_omissions
from comparative_narrator import (
    generate_faction_narrative,
    generate_common_ground_narrative,
    generate_divergence_narrative,
    generate_omission_narrative,
    try_ai_narration,
)

ALGORITHM_VERSION = "2.0.0"


def _get_event_from_db(event_id: str) -> dict[str, Any]:
    """Retrieve event from eventi_1gm.db."""
    db_path = Path(__file__).parent / "eventi_1gm.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM eventi_1gm WHERE id = ? OR stable_id = ?",
            (event_id, event_id),
        ).fetchone()
        if row:
            return dict(row)
    finally:
        conn.close()
    return {}


def _gather_event_sources(event_id: str, event_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Gather all sources linked to an event from event_links and archivio_documenti."""
    sources: list[dict[str, Any]] = []
    events_db = Path(__file__).parent / "eventi_1gm.db"
    imi_db = Path(__file__).parent / "imi_internati.db"

    # Event links
    conn_ev = sqlite3.connect(str(events_db))
    conn_ev.row_factory = sqlite3.Row
    try:
        # Limit to 500 sources, prioritizing archivio_documenti (which may include cross-faction sources)
        rows = conn_ev.execute(
            """SELECT el.id, el.target_table, el.target_id, el.link_type,
                      el.confidence, el.match_field, el.match_value,
                      el.usable_as_evidence, el.war_period
               FROM event_links el
               WHERE el.evento_id = ?
               ORDER BY CASE WHEN el.target_table = 'archivio_documenti' THEN 0 ELSE 1 END,
                        el.confidence DESC
               LIMIT 500""",
            (event_id,),
        ).fetchall()

        # Batch fetch archivio_documenti content
        archivio_ids = [dict(r)["target_id"] for r in rows if dict(r)["target_table"] == "archivio_documenti"]
        archivio_content = {}
        if archivio_ids:
            conn_imi = sqlite3.connect(str(imi_db))
            conn_imi.row_factory = sqlite3.Row
            try:
                placeholders = ",".join("?" * len(archivio_ids))
                docs = conn_imi.execute(
                    f"SELECT rowid, * FROM archivio_documenti WHERE rowid IN ({placeholders})",
                    archivio_ids,
                ).fetchall()
                for doc in docs:
                    archivio_content[doc["rowid"]] = dict(doc)
            finally:
                conn_imi.close()

        for row in rows:
            r = dict(row)
            # Fetch target record for content
            target_content = {}
            if r["target_table"] == "archivio_documenti":
                target_content = archivio_content.get(r["target_id"], {})

            sources.append({
                "source_id": f"el_{r['id']}",
                "label": f"{r['target_table']}:{r['target_id']} ({r['link_type']})",
                "metadata": {
                    "target_table": r["target_table"],
                    "target_id": r["target_id"],
                    "link_type": r["link_type"],
                    "match_field": r["match_field"],
                    "match_value": r["match_value"],
                    "confidence": r["confidence"],
                    "war_period": r["war_period"],
                    "usable_as_evidence": r.get("usable_as_evidence", 0),
                    "repository": target_content.get("provider", ""),
                    "provider": target_content.get("provider", ""),
                    "description": target_content.get("title", ""),
                    "text": target_content.get("description", ""),
                    "date": target_content.get("date_text", ""),
                    "content": str(target_content),
                },
            })
    finally:
        conn_ev.close()

    return sources


def _extract_observations_from_sources(
    sources: list[dict[str, Any]],
    event_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract observations (claims) from source content.

    Maps event_links match fields to event-relevant predicates.
    """
    import re
    observations: list[dict[str, Any]] = []

    # Predicate mapping from match_field to event-relevant predicates
    _PREDICATE_MAP = {
        "luogo_morte": "location",
        "luogo_nascita": "origin_location",
        "data_morte": "casualty_date",
        "data_nascita": "birth_date",
        "unit": "unit",
        "reggimento": "unit",
        "brigata": "unit",
        "corpo": "unit",
        "arma": "unit",
        "grado": "rank",
        "cause_morte": "casualty_cause",
        "note": "note",
    }

    # Skip generic text_match predicates — they're keyword matches, not structured claims
    _SKIP_PREDICATES = {"text_match", "keyword_match", "generic_match"}

    for src in sources:
        meta = src.get("metadata", {})
        content = meta.get("text", "") or meta.get("description", "")
        match_field = meta.get("match_field", "")
        match_value = meta.get("match_value", "")
        target_table = meta.get("target_table", "")

        # Map match_field to event-relevant predicate
        if match_field and match_value:
            pred_lower = match_field.lower()
            if pred_lower in _SKIP_PREDICATES:
                # Generic keyword match — only use as location if value is a place name
                if match_value.lower() in ("caporetto", "kobarid", "isonzo", "piave", "carso", "karfreit", "tolmino", "gorizia"):
                    observations.append({
                        "source_id": src["source_id"],
                        "predicate": "location_reference",
                        "value": match_value,
                        "raw_text": f"location reference: {match_value}",
                        "confidence": meta.get("confidence", 0.5),
                        "lineage_ids": [],
                        "evidence_ids": [],
                        "temporal_proximity": 0.5,
                        "specificity": 0.3,
                        "relevance": 0.4,
                    })
            elif pred_lower in _PREDICATE_MAP:
                mapped_pred = _PREDICATE_MAP[pred_lower]
                observations.append({
                    "source_id": src["source_id"],
                    "predicate": mapped_pred,
                    "value": match_value,
                    "raw_text": f"{match_field}: {match_value}",
                    "confidence": meta.get("confidence", 0.5),
                    "lineage_ids": [],
                    "evidence_ids": [],
                    "temporal_proximity": 0.5,
                    "specificity": 0.7,
                    "relevance": 0.6,
                })

        # Extract dates from content
        if content:
            date_matches = re.findall(r"\b(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})\b", content)
            for dm in date_matches[:3]:
                observations.append({
                    "source_id": src["source_id"],
                    "predicate": "date_reference",
                    "value": dm,
                    "raw_text": f"Date mentioned: {dm}",
                    "confidence": 0.6,
                    "lineage_ids": [],
                    "evidence_ids": [],
                    "temporal_proximity": 0.7,
                    "specificity": 0.5,
                    "relevance": 0.6,
                })

            # Location extraction
            content_lower = content.lower()
            event_loc = event_context.get("luogo") or event_context.get("general_location") or ""
            if event_loc and event_loc.lower() in content_lower:
                observations.append({
                    "source_id": src["source_id"],
                    "predicate": "location",
                    "value": event_loc,
                    "raw_text": f"Location mentioned: {event_loc}",
                    "confidence": 0.6,
                    "lineage_ids": [],
                    "evidence_ids": [],
                    "temporal_proximity": 0.5,
                    "specificity": 0.5,
                    "relevance": 0.7,
                })

    return observations


def _build_claim_matrix(
    bundles: list[FactionBundle],
    common_facts: list[CommonFact],
    divergences: list[Divergence],
) -> list[ClaimMatrixEntry]:
    """Build the claim comparison matrix."""
    matrix: list[ClaimMatrixEntry] = []
    seen_predicates: set[str] = set()

    # From common facts
    for cf in common_facts:
        if cf.predicate in seen_predicates:
            continue
        seen_predicates.add(cf.predicate)

        faction_support: dict[str, str] = {}
        for faction, claims_list in _group_claims_by_faction_for_predicate(bundles, cf.predicate).items():
            values = list({c.value for c in claims_list})
            faction_support[faction] = " | ".join(values)

        matrix.append(ClaimMatrixEntry(
            predicate=cf.predicate,
            faction_support=faction_support,
            neutral_support="",
            status=cf.status,
            claim_nature=cf.claim_nature,
        ))

    # From divergences not already in matrix
    for div in divergences:
        if div.predicate in seen_predicates:
            continue
        seen_predicates.add(div.predicate)

        faction_support: dict[str, str] = {}
        for pos in div.faction_positions:
            faction_support[pos["faction"]] = pos["value"]

        matrix.append(ClaimMatrixEntry(
            predicate=div.predicate,
            faction_support=faction_support,
            neutral_support="",
            status=CommonFactStatus.CROSS_FACTION_CONFLICT,
            claim_nature=div.claim_nature,
        ))

    # Add single-perspective claims
    for bundle in bundles:
        for claim in bundle.claims:
            if claim.predicate not in seen_predicates:
                seen_predicates.add(claim.predicate)
                matrix.append(ClaimMatrixEntry(
                    predicate=claim.predicate,
                    faction_support={bundle.faction_alignment.value: claim.value},
                    neutral_support="",
                    status=CommonFactStatus.SINGLE_PERSPECTIVE,
                    claim_nature=claim.claim_nature,
                ))

    return matrix


def _group_claims_by_faction_for_predicate(
    bundles: list[FactionBundle],
    predicate: str,
) -> dict[str, list]:
    """Group claims by faction for a specific predicate."""
    from common_fact_resolver import _normalize_predicate
    norm = _normalize_predicate(predicate)
    result: dict[str, list] = {}
    for bundle in bundles:
        matching = [c for c in bundle.claims if _normalize_predicate(c.predicate) == norm]
        if matching:
            result[bundle.faction_alignment.value] = matching
    return result


def _compute_metrics(
    bundles: list[FactionBundle],
    common_facts: list[CommonFact],
    divergences: list[Divergence],
    omissions: list[Omission],
) -> ViewpointMetrics:
    """Compute viewpoint metrics."""
    metrics = ViewpointMetrics()

    # Sources
    metrics.viewpoint_sources_total = sum(b.raw_source_count for b in bundles)
    metrics.sources_by_faction = {b.faction_alignment.value: b.raw_source_count for b in bundles}
    metrics.independent_lineages_by_faction = {
        b.faction_alignment.value: b.independent_lineage_count for b in bundles
    }
    metrics.claims_by_faction = {b.faction_alignment.value: len(b.claims) for b in bundles}

    # Common facts
    metrics.cross_faction_confirmed_claims = sum(
        1 for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_CONFIRMED
    )
    metrics.cross_faction_compatible_claims = sum(
        1 for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_COMPATIBLE
    )
    metrics.cross_faction_conflicts = sum(
        1 for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_CONFLICT
    )
    metrics.single_perspective_claims = sum(
        1 for f in common_facts if f.status == CommonFactStatus.SINGLE_PERSPECTIVE
    )

    # Omissions
    metrics.not_mentioned_claims = sum(
        1 for o in omissions if o.status == OmissionStatus.NOT_MENTIONED
    )
    metrics.explicit_denials = sum(
        1 for o in omissions if o.status == OmissionStatus.DENIED
    )

    # Interpretation conflicts
    metrics.interpretation_conflicts = sum(
        1 for d in divergences if d.claim_nature in (ClaimNature.INTERPRETATION, ClaimNature.CAUSAL_INTERPRETATION)
    )

    # Common ground coverage
    # Percentage of event dimensions with at least 2 independent perspectives compatible
    event_dimensions = {
        "start_date", "end_date", "location", "objectives", "units_involved",
        "commanders", "movements", "casualties", "outcome", "causes", "consequences",
    }
    covered = 0
    for dim in event_dimensions:
        dim_facts = [f for f in common_facts if f.predicate == dim]
        has_cross = any(
            f.status in (CommonFactStatus.CROSS_FACTION_CONFIRMED, CommonFactStatus.CROSS_FACTION_COMPATIBLE)
            and f.independent_faction_count >= 2
            and f.independent_lineage_count >= 2
            for f in dim_facts
        )
        if has_cross:
            covered += 1

    metrics.common_ground_coverage = round(covered / len(event_dimensions) * 100, 1) if event_dimensions else 0.0

    return metrics


def _build_neutral_evidence(
    bundles: list[FactionBundle],
    all_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract neutral/independent evidence (NEUTRAL, POSTWAR_HISTORIOGRAPHY, CIVILIAN)."""
    neutral_factions = {
        FactionAlignment.NEUTRAL,
        FactionAlignment.POSTWAR_HISTORIOGRAPHY,
        FactionAlignment.CIVILIAN,
    }

    neutral: list[dict[str, Any]] = []
    for bundle in bundles:
        if bundle.faction_alignment in neutral_factions:
            for claim in bundle.claims:
                neutral.append({
                    "faction": bundle.faction_alignment.value,
                    "predicate": claim.predicate,
                    "value": claim.value,
                    "source_ids": claim.source_ids,
                    "confidence": claim.confidence,
                })

    return neutral


def compare_viewpoints_v2(
    event_id: str,
    *,
    use_ai: bool = False,
    custom_sources: list[dict[str, Any]] | None = None,
    custom_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Main entry point for viewpoint comparison.

    Args:
        event_id: Event ID from eventi_1gm
        use_ai: If True, attempt AI narration (deterministic fallback always available)
        custom_sources: Override source gathering with custom sources
        custom_observations: Override observation extraction with custom observations

    Returns:
        ViewpointResult as dict
    """
    # 1. Get event context
    event_context = _get_event_from_db(event_id)
    if not event_context and custom_sources:
        event_context = {"id": event_id, "nome": event_id}

    if not event_context:
        return {
            "ok": False,
            "error": f"Event not found: {event_id}",
        }

    # 2. Gather sources
    if custom_sources:
        sources = custom_sources
    else:
        sources = _gather_event_sources(event_id, event_context)

    if not sources:
        return {
            "ok": False,
            "error": "No sources found for this event",
            "event": event_context,
        }

    # 3. Extract observations
    if custom_observations:
        observations = custom_observations
    else:
        observations = _extract_observations_from_sources(sources, event_context)

    # 4. Build faction bundles
    bundles = build_faction_bundles(sources, observations, event_context)

    if not bundles:
        return {
            "ok": False,
            "error": "No faction bundles could be built",
            "event": event_context,
        }

    # 5. Resolve common facts
    common_facts = resolve_common_facts(bundles)

    # 6. Detect divergences
    divergences = detect_divergences(bundles, common_facts)

    # 7. Detect omissions
    omissions = detect_omissions(bundles)

    # 8. Build claim matrix
    claim_matrix = _build_claim_matrix(bundles, common_facts, divergences)

    # 9. Generate narratives
    # Try AI first if requested
    ai_result = None
    if use_ai:
        ai_result = try_ai_narration(
            bundles, common_facts, divergences, omissions,
            event_context.get("nome", event_id),
        )

    # Always generate deterministic fallbacks
    for bundle in bundles:
        if ai_result and ai_result.get("sections"):
            faction_lower = bundle.faction_alignment.value.lower()
            sections = ai_result["sections"]
            # Try multiple key variants the AI might use
            candidate_keys = [
                faction_lower,
                faction_lower.replace("_hungarian", ""),
                f"ricostruzione {faction_lower}",
                f"prospettiva {faction_lower}",
                f"narrazione {faction_lower}",
                faction_lower.replace("_", " "),
            ]
            # Also try Italian translations
            it_map = {
                "italian": "italiana",
                "german": "tedesca",
                "austro_hungarian": "austro-ungarica",
                "unknown": "sconosciuta",
            }
            it_name = it_map.get(faction_lower)
            if it_name:
                candidate_keys.extend([
                    it_name,
                    f"ricostruzione {it_name}",
                    f"prospettiva {it_name}",
                    f"narrazione {it_name}",
                ])
            # Also try partial matching: any section key containing the faction name
            matched = None
            for ck in candidate_keys:
                if ck in sections:
                    matched = sections[ck]
                    break
            if not matched:
                for sk in sections:
                    if faction_lower in sk or (it_name and it_name in sk):
                        matched = sections[sk]
                        break
            bundle.narrative = matched or ""
        if not bundle.narrative:
            bundle.narrative = generate_faction_narrative(bundle)

    common_ground_narrative = ""
    if ai_result and ai_result.get("sections"):
        sections = ai_result["sections"]
        for ck in ("ricostruzione comune", "comune", "common ground", "fatti comuni"):
            if ck in sections:
                common_ground_narrative = sections[ck]
                break
        if not common_ground_narrative:
            for sk in sections:
                if "comun" in sk:
                    common_ground_narrative = sections[sk]
                    break
    if not common_ground_narrative:
        common_ground_narrative = generate_common_ground_narrative(common_facts)

    divergence_narrative = ""
    if ai_result and ai_result.get("sections"):
        sections = ai_result["sections"]
        for dk in ("divergenze", "narrazione delle divergenze", "divergence"):
            if dk in sections:
                divergence_narrative = sections[dk]
                break
        if not divergence_narrative:
            for sk in sections:
                if "diverg" in sk:
                    divergence_narrative = sections[sk]
                    break
    if not divergence_narrative:
        divergence_narrative = generate_divergence_narrative(divergences)

    omission_narrative = ""
    if ai_result and ai_result.get("sections"):
        sections = ai_result["sections"]
        for ok in ("omissioni", "narrazione delle omissioni", "omission"):
            if ok in sections:
                omission_narrative = sections[ok]
                break
        if not omission_narrative:
            for sk in sections:
                if "omiss" in sk or " omission" in sk:
                    omission_narrative = sections[sk]
                    break
    if not omission_narrative:
        omission_narrative = generate_omission_narrative(omissions)

    # 10. Build neutral evidence
    neutral_evidence = _build_neutral_evidence(bundles, sources)

    # 11. Compute metrics
    metrics = _compute_metrics(bundles, common_facts, divergences, omissions)

    # 12. Build result
    result = ViewpointResult(
        event_id=str(event_context.get("id", event_id)),
        event_name=event_context.get("nome", event_id),
        conflict=event_context.get("conflict", ""),
        perspectives=bundles,
        common_ground=common_facts,
        common_ground_narrative=common_ground_narrative,
        divergences=divergences,
        omissions=omissions,
        neutral_evidence=neutral_evidence,
        claim_matrix=claim_matrix,
        metrics=metrics,
        snapshot_id=f"vp_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
        algorithm_version=ALGORITHM_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    output = result.to_dict()
    output["ok"] = True
    output["common_ground_narrative"] = common_ground_narrative
    output["divergence_narrative"] = divergence_narrative
    output["omission_narrative"] = omission_narrative

    if ai_result:
        output["ai_used"] = ai_result.get("used", False)
        output["ai_provider"] = ai_result.get("provider")
        output["ai_model"] = ai_result.get("model")
    else:
        output["ai_used"] = False

    return output
