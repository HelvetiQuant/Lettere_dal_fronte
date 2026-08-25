"""Viewpoint Models — Data structures for Comparative Historical Reconstruction.

Defines typed dataclasses for faction-based event reconstruction:
- SourceFactionClassification (faction + role + temporal layer)
- FactionBundle (independent evidence bundle per faction)
- CommonFact (cross-faction confirmed/compatible facts)
- Divergence (classified divergences between factions)
- Omission (asymmetric omissions)
- ClaimMatrix (full claim comparison matrix)
- ViewpointResult (complete output)

EVENT ONLY. Not for PERSON lookup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class FactionAlignment(str, Enum):
    ITALIAN = "ITALIAN"
    AUSTRO_HUNGARIAN = "AUSTRO_HUNGARIAN"
    GERMAN = "GERMAN"
    ALLIED = "ALLIED"
    BRITISH = "BRITISH"
    FRENCH = "FRENCH"
    US = "US"
    SOVIET = "SOVIET"
    YUGOSLAV = "YUGOSLAV"
    GREEK = "GREEK"
    AXIS = "AXIS"
    RESISTANCE = "RESISTANCE"
    CIVILIAN = "CIVILIAN"
    NEUTRAL = "NEUTRAL"
    POSTWAR_HISTORIOGRAPHY = "POSTWAR_HISTORIOGRAPHY"
    UNKNOWN = "UNKNOWN"


class SourceRole(str, Enum):
    OPERATIONAL_ORDER = "operational_order"
    WAR_DIARY = "war_diary"
    SITUATION_REPORT = "situation_report"
    AFTER_ACTION_REPORT = "after_action_report"
    CASUALTY_REPORT = "casualty_report"
    INTELLIGENCE_REPORT = "intelligence_report"
    PRISONER_REPORT = "prisoner_report"
    PERSONAL_DIARY = "personal_diary"
    LETTER = "letter"
    PROPAGANDA = "propaganda"
    PRESS = "press"
    MEMOIR = "memoir"
    ORAL_HISTORY = "oral_history"
    POSTWAR_STUDY = "postwar_study"
    ARCHIVAL_CATALOG_METADATA = "archival_catalog_metadata"
    UNKNOWN = "unknown"


class TemporalLayer(str, Enum):
    CONTEMPORARY = "CONTEMPORARY"
    NEAR_CONTEMPORARY = "NEAR_CONTEMPORARY"
    POSTWAR_TESTIMONY = "POSTWAR_TESTIMONY"
    HISTORIOGRAPHICAL = "HISTORIOGRAPHICAL"


class CommonFactStatus(str, Enum):
    CROSS_FACTION_CONFIRMED = "CROSS_FACTION_CONFIRMED"
    CROSS_FACTION_COMPATIBLE = "CROSS_FACTION_COMPATIBLE"
    CROSS_FACTION_CONFLICT = "CROSS_FACTION_CONFLICT"
    SAME_FACTION_CORROBORATED = "SAME_FACTION_CORROBORATED"
    SINGLE_PERSPECTIVE = "SINGLE_PERSPECTIVE"
    UNRESOLVED = "UNRESOLVED"


class DivergenceType(str, Enum):
    DATE_CONFLICT = "DATE_CONFLICT"
    TIME_CONFLICT = "TIME_CONFLICT"
    LOCATION_CONFLICT = "LOCATION_CONFLICT"
    UNIT_CONFLICT = "UNIT_CONFLICT"
    CASUALTY_CONFLICT = "CASUALTY_CONFLICT"
    CAUSALITY_CONFLICT = "CAUSALITY_CONFLICT"
    INTENT_CONFLICT = "INTENT_CONFLICT"
    OUTCOME_CONFLICT = "OUTCOME_CONFLICT"
    RESPONSIBILITY_CONFLICT = "RESPONSIBILITY_CONFLICT"
    SEQUENCE_CONFLICT = "SEQUENCE_CONFLICT"
    TERMINOLOGY_CONFLICT = "TERMINOLOGY_CONFLICT"
    OMISSION_ASYMMETRY = "OMISSION_ASYMMETRY"
    PROPAGANDA_SUSPECTED = "PROPAGANDA_SUSPECTED"
    UNKNOWN_CONFLICT = "UNKNOWN_CONFLICT"


class OmissionStatus(str, Enum):
    NOT_MENTIONED = "NOT_MENTIONED"
    DENIED = "DENIED"
    CONTRADICTED = "CONTRADICTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    CORPUS_INCOMPLETE = "CORPUS_INCOMPLETE"


class DivergenceResolution(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    RESOLVED_BY_STRONGER_EVIDENCE = "RESOLVED_BY_STRONGER_EVIDENCE"


class ClaimNature(str, Enum):
    OBSERVABLE_FACT = "OBSERVABLE_FACT"
    INTERPRETATION = "INTERPRETATION"
    CAUSAL_INTERPRETATION = "CAUSAL_INTERPRETATION"
    ATTRIBUTION = "ATTRIBUTION"


class PropagandaStatus(str, Enum):
    NOT_ASSESSED = "NOT_ASSESSED"
    POSSIBLE = "POSSIBLE"
    LIKELY = "LIKELY"
    DOCUMENTED = "DOCUMENTED"


class EventPhase(str, Enum):
    PRELUDE = "PRELUDE"
    PHASE_1 = "PHASE_1"
    PHASE_2 = "PHASE_2"
    PHASE_3 = "PHASE_3"
    OUTCOME = "OUTCOME"
    AFTERMATH = "AFTERMATH"
    UNPHASED = "UNPHASED"


@dataclass
class SourceFactionClassification:
    """Classification of a source relative to an event."""
    source_id: str
    source_label: str
    faction_alignment: FactionAlignment
    source_role: SourceRole
    temporal_layer: TemporalLayer
    repository: str = ""
    source_creator_alignment: str = ""
    classification_reason: str = ""
    classification_confidence: float = 0.0
    propaganda_status: PropagandaStatus = PropagandaStatus.NOT_ASSESSED
    rhetorical_intensity: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_label": self.source_label,
            "faction_alignment": self.faction_alignment.value,
            "source_role": self.source_role.value,
            "temporal_layer": self.temporal_layer.value,
            "repository": self.repository,
            "source_creator_alignment": self.source_creator_alignment,
            "classification_reason": self.classification_reason,
            "classification_confidence": self.classification_confidence,
            "propaganda_status": self.propaganda_status.value,
            "rhetorical_intensity": self.rhetorical_intensity,
            "metadata": self.metadata,
        }


@dataclass
class FactionClaim:
    """A claim belonging to a specific faction's reconstruction."""
    claim_id: str
    predicate: str
    value: str
    raw_claim: str
    normalized_claim: str = ""
    perspective_language: str = ""
    claim_nature: ClaimNature = ClaimNature.OBSERVABLE_FACT
    event_phase: EventPhase = EventPhase.UNPHASED
    source_ids: list[str] = field(default_factory=list)
    lineage_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    temporal_proximity: float = 0.0
    specificity: float = 0.0
    relevance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "predicate": self.predicate,
            "value": self.value,
            "raw_claim": self.raw_claim,
            "normalized_claim": self.normalized_claim,
            "perspective_language": self.perspective_language,
            "claim_nature": self.claim_nature.value,
            "event_phase": self.event_phase.value,
            "source_ids": self.source_ids,
            "lineage_ids": self.lineage_ids,
            "confidence": self.confidence,
            "evidence_ids": self.evidence_ids,
            "temporal_proximity": self.temporal_proximity,
            "specificity": self.specificity,
            "relevance": self.relevance,
        }


@dataclass
class FactionBundle:
    """Independent evidence bundle for a single faction's reconstruction."""
    faction_alignment: FactionAlignment
    sources: list[SourceFactionClassification] = field(default_factory=list)
    claims: list[FactionClaim] = field(default_factory=list)
    narrative: str = ""
    event_model: dict[str, Any] = field(default_factory=dict)
    raw_source_count: int = 0
    independent_lineage_count: int = 0
    coverage_dimensions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alignment": self.faction_alignment.value,
            "sources": [s.to_dict() for s in self.sources],
            "claims": [c.to_dict() for c in self.claims],
            "narrative": self.narrative,
            "event_model": self.event_model,
            "raw_source_count": self.raw_source_count,
            "independent_lineage_count": self.independent_lineage_count,
            "coverage_dimensions": self.coverage_dimensions,
        }


@dataclass
class CommonFact:
    """A fact confirmed or compatible across factions."""
    fact_id: str
    predicate: str
    normalized_value: str
    status: CommonFactStatus
    supporting_factions: list[str] = field(default_factory=list)
    supporting_claims: list[dict[str, Any]] = field(default_factory=list)
    independent_lineage_count: int = 0
    independent_faction_count: int = 0
    event_phase: EventPhase = EventPhase.UNPHASED
    claim_nature: ClaimNature = ClaimNature.OBSERVABLE_FACT
    evidence_strength: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "predicate": self.predicate,
            "normalized_value": self.normalized_value,
            "status": self.status.value,
            "supporting_factions": self.supporting_factions,
            "supporting_claims": self.supporting_claims,
            "independent_lineage_count": self.independent_lineage_count,
            "independent_faction_count": self.independent_faction_count,
            "event_phase": self.event_phase.value,
            "claim_nature": self.claim_nature.value,
            "evidence_strength": self.evidence_strength,
            "note": self.note,
        }


@dataclass
class Divergence:
    """A divergence between faction reconstructions."""
    divergence_id: str
    divergence_type: DivergenceType
    predicate: str
    event_phase: EventPhase = EventPhase.UNPHASED
    faction_positions: list[dict[str, Any]] = field(default_factory=list)
    resolution: DivergenceResolution = DivergenceResolution.UNRESOLVED
    resolution_reason: str = ""
    claim_nature: ClaimNature = ClaimNature.OBSERVABLE_FACT
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergence_id": self.divergence_id,
            "divergence_type": self.divergence_type.value,
            "predicate": self.predicate,
            "event_phase": self.event_phase.value,
            "faction_positions": self.faction_positions,
            "resolution": self.resolution.value,
            "resolution_reason": self.resolution_reason,
            "claim_nature": self.claim_nature.value,
            "note": self.note,
        }


@dataclass
class Omission:
    """An asymmetric omission — one faction mentions, another doesn't."""
    omission_id: str
    predicate: str
    mentioning_faction: str
    mentioning_claim: dict[str, Any] = field(default_factory=dict)
    silent_factions: list[str] = field(default_factory=list)
    status: OmissionStatus = OmissionStatus.NOT_MENTIONED
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "omission_id": self.omission_id,
            "predicate": self.predicate,
            "mentioning_faction": self.mentioning_faction,
            "mentioning_claim": self.mentioning_claim,
            "silent_factions": self.silent_factions,
            "status": self.status.value,
            "note": self.note,
        }


@dataclass
class ClaimMatrixEntry:
    """Single entry in the claim comparison matrix."""
    predicate: str
    faction_support: dict[str, str] = field(default_factory=dict)
    neutral_support: str = ""
    status: CommonFactStatus = CommonFactStatus.SINGLE_PERSPECTIVE
    claim_nature: ClaimNature = ClaimNature.OBSERVABLE_FACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "faction_support": self.faction_support,
            "neutral_support": self.neutral_support,
            "status": self.status.value,
            "claim_nature": self.claim_nature.value,
        }


@dataclass
class ViewpointMetrics:
    """Metrics for viewpoint analysis."""
    viewpoint_sources_total: int = 0
    sources_by_faction: dict[str, int] = field(default_factory=dict)
    independent_lineages_by_faction: dict[str, int] = field(default_factory=dict)
    claims_by_faction: dict[str, int] = field(default_factory=dict)
    cross_faction_confirmed_claims: int = 0
    cross_faction_compatible_claims: int = 0
    cross_faction_conflicts: int = 0
    single_perspective_claims: int = 0
    not_mentioned_claims: int = 0
    explicit_denials: int = 0
    interpretation_conflicts: int = 0
    common_ground_coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewpoint_sources_total": self.viewpoint_sources_total,
            "sources_by_faction": self.sources_by_faction,
            "independent_lineages_by_faction": self.independent_lineages_by_faction,
            "claims_by_faction": self.claims_by_faction,
            "cross_faction_confirmed_claims": self.cross_faction_confirmed_claims,
            "cross_faction_compatible_claims": self.cross_faction_compatible_claims,
            "cross_faction_conflicts": self.cross_faction_conflicts,
            "single_perspective_claims": self.single_perspective_claims,
            "not_mentioned_claims": self.not_mentioned_claims,
            "explicit_denials": self.explicit_denials,
            "interpretation_conflicts": self.interpretation_conflicts,
            "common_ground_coverage": self.common_ground_coverage,
        }


@dataclass
class ViewpointResult:
    """Complete output of the viewpoint analysis."""
    event_id: str
    event_name: str
    conflict: str = ""
    perspectives: list[FactionBundle] = field(default_factory=list)
    common_ground: list[CommonFact] = field(default_factory=list)
    common_ground_narrative: str = ""
    divergences: list[Divergence] = field(default_factory=list)
    omissions: list[Omission] = field(default_factory=list)
    neutral_evidence: list[dict[str, Any]] = field(default_factory=list)
    claim_matrix: list[ClaimMatrixEntry] = field(default_factory=list)
    metrics: ViewpointMetrics = field(default_factory=ViewpointMetrics)
    snapshot_id: str = ""
    algorithm_version: str = "2.0.0"
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": {
                "event_id": self.event_id,
                "event_name": self.event_name,
                "conflict": self.conflict,
            },
            "perspectives": [p.to_dict() for p in self.perspectives],
            "common_ground": {
                "claims": [c.to_dict() for c in self.common_ground],
                "narrative": self.common_ground_narrative,
            },
            "divergences": [d.to_dict() for d in self.divergences],
            "omissions": [o.to_dict() for o in self.omissions],
            "neutral_evidence": self.neutral_evidence,
            "claim_matrix": [m.to_dict() for m in self.claim_matrix],
            "metrics": self.metrics.to_dict(),
            "snapshot_id": self.snapshot_id,
            "algorithm_version": self.algorithm_version,
            "generated_at": self.generated_at,
        }
