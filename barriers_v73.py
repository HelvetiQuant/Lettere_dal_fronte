"""V7.3 Temporal & Geographic Barriers.

Temporal barriers:
- WWI sources cannot be linked to WWII events/persons
- WWII sources cannot be linked to WWI events/persons
- Incompatible dates block merges
- Missing date is not a conflict, but not confirmation
- Death year, decoration year, publication year have different roles

Geographic barriers:
- BURIAL_PLACE != EVENT_PLACE
- DEATH_PLACE != CAPTURE_PLACE
- Place mentioned in title != place attributed to person
- Each geographic role is normalized separately
"""
from __future__ import annotations

import re
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from enum import Enum

from domain_model_v73 import WarPeriod, SemanticRole


# ─── Temporal Engine ────────────────────────────────────────────────────────

class DateRole(str, Enum):
    """The semantic role of a date — different roles have different evidential value."""
    BIRTH_DATE = "BIRTH_DATE"
    DEATH_DATE = "DEATH_DATE"
    CAPTURE_DATE = "CAPTURE_DATE"
    DECORATION_DATE = "DECORATION_DATE"
    PUBLICATION_DATE = "PUBLICATION_DATE"
    EVENT_START = "EVENT_START"
    EVENT_END = "EVENT_END"
    SERVICE_PERIOD = "SERVICE_PERIOD"
    INTERNMENT_PERIOD = "INTERNMENT_PERIOD"
    UNKNOWN = "UNKNOWN"


@dataclass
class TemporalCompatibility:
    """Result of temporal compatibility check."""
    compatible: bool
    war_match: bool
    date_overlap: bool
    conflict_reason: str = ""
    veto: bool = False  # Hard veto (official date conflict)
    source_war: str = ""
    target_war: str = ""


def parse_year(date_str: str) -> Optional[int]:
    """Extract a year from a date string."""
    if not date_str:
        return None
    # Try ISO format first
    m = re.match(r"(\d{4})-\d{2}-\d{2}", date_str)
    if m:
        return int(m.group(1))
    # Try year only
    m = re.match(r"(\d{4})", date_str)
    if m:
        return int(m.group(1))
    return None


def classify_war_period(date_str: str) -> WarPeriod:
    """Classify a date into war period."""
    year = parse_year(date_str)
    if year is None:
        return WarPeriod.UNKNOWN
    if year >= 1939:
        return WarPeriod.WWII
    if year >= 1914 and year <= 1922:
        return WarPeriod.WWI
    return WarPeriod.OTHER


def dates_overlap(
    start1: str, end1: str,
    start2: str, end2: str,
) -> bool:
    """Check if two date ranges overlap."""
    y1s = parse_year(start1) or 0
    y1e = parse_year(end1) or 9999
    y2s = parse_year(start2) or 0
    y2e = parse_year(end2) or 9999

    return y1s <= y2e and y2s <= y1e


def check_temporal_compatibility(
    source_date: str,
    source_date_role: DateRole,
    target_date_start: str,
    target_date_end: str,
    target_war: WarPeriod = WarPeriod.UNKNOWN,
) -> TemporalCompatibility:
    """Check temporal compatibility between a source and a target.

    Rules:
    1. WWI source cannot link to WWII target (hard barrier)
    2. WWII source cannot link to WWI target (hard barrier)
    3. Publication date does not prove participation in events of that year
    4. Decoration year != participation year
    5. Missing date is not a conflict, but not confirmation
    """
    source_war = classify_war_period(source_date)
    if target_war == WarPeriod.UNKNOWN:
        target_war = classify_war_period(target_date_start)

    # War period barrier
    war_match = True
    if source_war != WarPeriod.UNKNOWN and target_war != WarPeriod.UNKNOWN:
        if source_war != target_war:
            war_match = False
            return TemporalCompatibility(
                compatible=False,
                war_match=False,
                date_overlap=False,
                conflict_reason=f"WAR_PERIOD_MISMATCH: source={source_war.value}, target={target_war.value}",
                veto=True,
                source_war=source_war.value,
                target_war=target_war.value,
            )

    # Publication date does not prove participation
    if source_date_role == DateRole.PUBLICATION_DATE:
        year = parse_year(source_date)
        target_start_year = parse_year(target_date_start)
        target_end_year = parse_year(target_date_end)
        if year and target_start_year and target_end_year:
            if target_start_year <= year <= target_end_year:
                return TemporalCompatibility(
                    compatible=True,
                    war_match=war_match,
                    date_overlap=True,
                    conflict_reason="PUBLICATION_DATE_IN_RANGE: publication year falls within event range but does not prove participation",
                )
            else:
                return TemporalCompatibility(
                    compatible=False,
                    war_match=war_match,
                    date_overlap=False,
                    conflict_reason="PUBLICATION_DATE_OUT_OF_RANGE: publication year outside event range",
                )

    # Decoration date is weak evidence for participation
    if source_date_role == DateRole.DECORATION_DATE:
        year = parse_year(source_date)
        target_start_year = parse_year(target_date_start)
        target_end_year = parse_year(target_date_end)
        if year and target_start_year and target_end_year:
            if target_start_year <= year <= target_end_year:
                return TemporalCompatibility(
                    compatible=True,
                    war_match=war_match,
                    date_overlap=True,
                    conflict_reason="DECORATION_DATE_IN_RANGE: decoration year within event range — weak evidence only",
                )

    # General date overlap check
    overlap = dates_overlap(source_date, source_date, target_date_start, target_date_end)
    if not overlap and source_date:
        return TemporalCompatibility(
            compatible=False,
            war_match=war_match,
            date_overlap=False,
            conflict_reason=f"DATE_OUT_OF_RANGE: source date {source_date} outside target range {target_date_start}-{target_date_end}",
        )

    # Missing source date — not a conflict, but not confirmation
    if not source_date:
        return TemporalCompatibility(
            compatible=True,  # Not incompatible
            war_match=war_match,
            date_overlap=False,
            conflict_reason="MISSING_SOURCE_DATE: no conflict, but no confirmation either",
        )

    return TemporalCompatibility(
        compatible=True,
        war_match=war_match,
        date_overlap=overlap,
    )


# ─── Geographic Role Engine ─────────────────────────────────────────────────

# Mapping of DB fields to semantic roles
FIELD_TO_SEMANTIC_ROLE: Dict[str, SemanticRole] = {
    "luogo_nascita": SemanticRole.BIRTH_PLACE,
    "residenza": SemanticRole.RESIDENCE_PLACE,
    "luogo_cattura": SemanticRole.CAPTURE_PLACE,
    "luogo_internamento": SemanticRole.DETENTION_PLACE,
    "arbeitskommando": SemanticRole.WORK_PLACE,
    "luogo_morte": SemanticRole.DEATH_PLACE,
    "luogo_sepoltura": SemanticRole.BURIAL_PLACE,
    "luogo": SemanticRole.EVENT_PLACE,  # Generic — needs context
    "luogo_text": SemanticRole.EVENT_PLACE,  # Generic — needs context
    "place": SemanticRole.EVENT_PLACE,
    "general_location": SemanticRole.EVENT_PLACE,
}


@dataclass
class GeographicCompatibility:
    """Result of geographic compatibility check."""
    compatible: bool
    same_role: bool
    conflict_reason: str = ""
    source_role: SemanticRole = SemanticRole.EVENT_PLACE
    target_role: SemanticRole = SemanticRole.EVENT_PLACE


def get_semantic_role(field_name: str) -> SemanticRole:
    """Get the semantic role of a geographic field."""
    return FIELD_TO_SEMANTIC_ROLE.get(field_name.lower(), SemanticRole.EVENT_PLACE)


def check_geographic_compatibility(
    source_field: str,
    source_value: str,
    target_field: str,
    target_value: str,
) -> GeographicCompatibility:
    """Check if a geographic match is semantically valid.

    Key rules:
    - BURIAL_PLACE != EVENT_PLACE (burial at a location != participation in battle there)
    - DEATH_PLACE != CAPTURE_PLACE (death in hospital != combat at that location)
    - DETENTION_PLACE != EVENT_PLACE (internment in Austria != participation in Austrian event)
    - Place in title != place attributed to person
    """
    source_role = get_semantic_role(source_field)
    target_role = get_semantic_role(target_field)

    # Same role is always compatible
    if source_role == target_role:
        return GeographicCompatibility(
            compatible=True,
            same_role=True,
            source_role=source_role,
            target_role=target_role,
        )

    # BURIAL_PLACE cannot substitute for EVENT_PLACE
    if source_role == SemanticRole.BURIAL_PLACE and target_role == SemanticRole.EVENT_PLACE:
        return GeographicCompatibility(
            compatible=False,
            same_role=False,
            conflict_reason="BURIAL_PLACE_AS_EVENT: burial at location does not prove participation in battle there",
            source_role=source_role,
            target_role=target_role,
        )

    # DEATH_PLACE cannot substitute for CAPTURE_PLACE or EVENT_PLACE
    if source_role == SemanticRole.DEATH_PLACE and target_role in (SemanticRole.CAPTURE_PLACE, SemanticRole.EVENT_PLACE):
        return GeographicCompatibility(
            compatible=False,
            same_role=False,
            conflict_reason=f"DEATH_PLACE_AS_{target_role.value}: death at location does not prove capture or combat there",
            source_role=source_role,
            target_role=target_role,
        )

    # DETENTION_PLACE cannot substitute for EVENT_PLACE
    if source_role == SemanticRole.DETENTION_PLACE and target_role == SemanticRole.EVENT_PLACE:
        return GeographicCompatibility(
            compatible=False,
            same_role=False,
            conflict_reason="DETENTION_PLACE_AS_EVENT: internment in location does not prove participation in event there",
            source_role=source_role,
            target_role=target_role,
        )

    # RESIDENCE_PLACE cannot substitute for EVENT_PLACE
    if source_role == SemanticRole.RESIDENCE_PLACE and target_role == SemanticRole.EVENT_PLACE:
        return GeographicCompatibility(
            compatible=False,
            same_role=False,
            conflict_reason="RESIDENCE_PLACE_AS_EVENT: residence at location does not prove participation in event there",
            source_role=source_role,
            target_role=target_role,
        )

    # SOURCE_PUBLICATION_PLACE is irrelevant for event participation
    if source_role == SemanticRole.SOURCE_PUBLICATION_PLACE:
        return GeographicCompatibility(
            compatible=False,
            same_role=False,
            conflict_reason="SOURCE_PUBLICATION_PLACE: publication location is irrelevant to event participation",
            source_role=source_role,
            target_role=target_role,
        )

    # Different but compatible roles (e.g., BIRTH_PLACE and RESIDENCE_PLACE)
    return GeographicCompatibility(
        compatible=True,
        same_role=False,
        conflict_reason=f"DIFFERENT_ROLES: source={source_role.value}, target={target_role.value} — compatible but not equivalent",
        source_role=source_role,
        target_role=target_role,
    )


# ─── Combined check ─────────────────────────────────────────────────────────

@dataclass
class MatchEvaluation:
    """Combined evaluation of temporal, geographic, and text matching."""
    text_match: bool
    temporal_compatible: bool
    geographic_compatible: bool
    temporal_veto: bool
    geographic_veto: bool
    has_specific_keyword: bool
    confidence: float
    decision: str  # "CONFIRMED", "CANDIDATE", "NEEDS_REVIEW", "REJECTED"
    reasons: List[str]


def evaluate_match(
    text_match: bool,
    has_specific_keyword: bool,
    temporal: TemporalCompatibility,
    geographic: GeographicCompatibility,
) -> MatchEvaluation:
    """Evaluate a complete match considering all barriers.

    Decision logic:
    - Temporal veto -> REJECTED
    - Geographic veto -> REJECTED
    - No text match -> REJECTED
    - Text match but only generic keywords -> NEEDS_REVIEW
    - Text match with specific keyword + temporal + geographic OK -> CANDIDATE
    - All checks pass with strong evidence -> CONFIRMED (requires review)
    """
    reasons = []

    if temporal.veto:
        reasons.append(f"TEMPORAL_VETO: {temporal.conflict_reason}")
        return MatchEvaluation(
            text_match=text_match,
            temporal_compatible=False,
            geographic_compatible=geographic.compatible,
            temporal_veto=True,
            geographic_veto=False,
            has_specific_keyword=has_specific_keyword,
            confidence=0.0,
            decision="REJECTED",
            reasons=reasons,
        )

    if not geographic.compatible:
        reasons.append(f"GEOGRAPHIC_INCOMPATIBLE: {geographic.conflict_reason}")
        return MatchEvaluation(
            text_match=text_match,
            temporal_compatible=temporal.compatible,
            geographic_compatible=False,
            temporal_veto=False,
            geographic_veto=True,
            has_specific_keyword=has_specific_keyword,
            confidence=0.1,
            decision="REJECTED",
            reasons=reasons,
        )

    if not text_match:
        reasons.append("NO_TEXT_MATCH")
        return MatchEvaluation(
            text_match=False,
            temporal_compatible=temporal.compatible,
            geographic_compatible=geographic.compatible,
            temporal_veto=False,
            geographic_veto=False,
            has_specific_keyword=False,
            confidence=0.0,
            decision="REJECTED",
            reasons=reasons,
        )

    if not has_specific_keyword:
        reasons.append("ONLY_GENERIC_KEYWORDS")
        return MatchEvaluation(
            text_match=True,
            temporal_compatible=temporal.compatible,
            geographic_compatible=geographic.compatible,
            temporal_veto=False,
            geographic_veto=False,
            has_specific_keyword=False,
            confidence=0.3,
            decision="NEEDS_REVIEW",
            reasons=reasons,
        )

    if not temporal.compatible:
        reasons.append(f"TEMPORAL_INCOMPATIBLE: {temporal.conflict_reason}")
        return MatchEvaluation(
            text_match=True,
            temporal_compatible=False,
            geographic_compatible=geographic.compatible,
            temporal_veto=False,
            geographic_veto=False,
            has_specific_keyword=has_specific_keyword,
            confidence=0.2,
            decision="REJECTED",
            reasons=reasons,
        )

    # All checks pass
    confidence = 0.5
    if temporal.date_overlap:
        confidence += 0.15
    if geographic.same_role:
        confidence += 0.15
    if has_specific_keyword:
        confidence += 0.1
    confidence = min(confidence, 0.9)

    reasons.append("ALL_CHECKS_PASS")
    return MatchEvaluation(
        text_match=True,
        temporal_compatible=True,
        geographic_compatible=True,
        temporal_veto=False,
        geographic_veto=False,
        has_specific_keyword=True,
        confidence=confidence,
        decision="CANDIDATE",
        reasons=reasons,
    )
