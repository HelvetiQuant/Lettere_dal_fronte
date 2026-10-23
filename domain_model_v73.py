"""V7.3 Canonical Domain Model — typed entities for the probatory pipeline.

All pipeline stages, API endpoints, narrator, validator, and renderer
operate on these types. No raw DB rows are passed directly.

Key invariants:
- SourceArtifact is immutable once created
- Observations are immutable once created
- ReviewDecisions are append-only
- Claims have explicit status lifecycle: CANDIDATE -> VERIFIED/PROBABLE/CONFLICTING/REJECTED
- IdentityCandidates are distinct per homonym
- Evidence has separated confidence dimensions
"""
from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from enum import Enum


# ─── Enums ──────────────────────────────────────────────────────────────────

class ClaimStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    PROBABLE = "PROBABLE"
    CONFLICTING = "CONFLICTING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class ClaimType(str, Enum):
    RECORD_ASSERTION = "RECORD_ASSERTION"
    PERSON_CLAIM = "PERSON_CLAIM"
    EVENT_CLAIM = "EVENT_CLAIM"
    CONTEXT_CLAIM = "CONTEXT_CLAIM"
    RESEARCH_LEAD = "RESEARCH_LEAD"


class RelationStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class IdentityStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED_HOMONYM = "REJECTED_HOMONYM"
    CONFLICTING = "CONFLICTING"


class EvidenceType(str, Enum):
    PERSON_EVIDENCE = "PERSON_EVIDENCE"
    FACT_EVIDENCE = "FACT_EVIDENCE"
    EVENT_CONTEXT = "EVENT_CONTEXT"
    PLACE_NORMALIZATION_EVIDENCE = "PLACE_NORMALIZATION_EVIDENCE"
    RESEARCH_LEAD = "RESEARCH_LEAD"
    HOMONYM_CANDIDATE = "HOMONYM_CANDIDATE"
    REJECTED_IDENTITY_LINK = "REJECTED_IDENTITY_LINK"


class SemanticRole(str, Enum):
    BIRTH_PLACE = "BIRTH_PLACE"
    RESIDENCE_PLACE = "RESIDENCE_PLACE"
    CAPTURE_PLACE = "CAPTURE_PLACE"
    DETENTION_PLACE = "DETENTION_PLACE"
    WORK_PLACE = "WORK_PLACE"
    DEATH_PLACE = "DEATH_PLACE"
    BURIAL_PLACE = "BURIAL_PLACE"
    EVENT_PLACE = "EVENT_PLACE"
    SOURCE_PUBLICATION_PLACE = "SOURCE_PUBLICATION_PLACE"


class WarPeriod(str, Enum):
    WWI = "WWI"
    WWII = "WWII"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class EventType(str, Enum):
    WAR = "WAR"
    THEATER = "THEATER"
    CAMPAIGN = "CAMPAIGN"
    BATTLE_SERIES = "BATTLE_SERIES"
    BATTLE = "BATTLE"
    PHASE = "PHASE"
    MILITARY_OPERATION = "MILITARY_OPERATION"
    HISTORICAL_PROCESS = "HISTORICAL_PROCESS"
    PLACE = "PLACE"


# ─── Identifier strength ────────────────────────────────────────────────────

class IdentifierStrength(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"


STRONG_IDENTIFIERS = {
    "data_nascita_complete", "matricola", "paternita", "maternita",
    "luogo_nascita + data_nascita", "archival_id_personal",
}

MEDIUM_IDENTIFIERS = {
    "classe", "comune", "reparto", "grado", "professione",
    "campo", "arbeitskommando", "coniuge", "residenza_precisa",
}

WEAK_IDENTIFIERS = {
    "nome_cognome", "solo_cognome", "anno_generico",
    "luogo_generico", "guerra_generica",
}


# ─── Data classes ───────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class SourceArtifact:
    """Immutable record of a source document or metadata."""
    artifact_id: str = field(default_factory=_uuid)
    source_url: str = ""
    source_family_id: Optional[str] = None
    artifact_type: str = ""  # document, metadata, web_page, pdf, image
    title: str = ""
    creator: str = ""
    date_text: str = ""
    coverage_start: str = ""
    coverage_end: str = ""
    coverage_precision: str = ""
    place: str = ""
    war: str = ""
    language: str = ""
    rights: str = ""
    raw_content_hash: str = ""
    raw_content_path: str = ""
    fetch_status: str = "PENDING"
    fetch_timestamp: str = ""
    access_type: str = ""
    compliance_status: str = "UNKNOWN"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceFamily:
    """Group of URLs/copies deriving from the same origin."""
    family_id: str = field(default_factory=_uuid)
    canonical_url: str = ""
    family_name: str = ""
    authority_tier: int = 4
    independence_group: str = ""
    member_count: int = 0
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Observation:
    """What was read/extracted from an artifact — not truth, just observation."""
    observation_id: str = field(default_factory=_uuid)
    artifact_id: str = ""
    observation_type: str = ""  # field_extraction, ocr, metadata, web_snippet
    raw_text: str = ""
    extracted_fields: Dict[str, Any] = field(default_factory=dict)
    extraction_method: str = ""
    extraction_confidence: float = 0.5
    observed_at: str = field(default_factory=_utc_now)
    created_at: str = field(default_factory=_utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["extracted_fields_json"] = json.dumps(d.pop("extracted_fields"), ensure_ascii=False)
        return d


@dataclass
class Entity:
    """A canonical entity (person, place, event, unit)."""
    entity_id: str = field(default_factory=_uuid)
    entity_type: str = ""  # person, place, event, unit
    canonical_name: str = ""
    normalized_name: str = ""
    cognome: str = ""
    nome: str = ""
    data_nascita: str = ""
    luogo_nascita: str = ""
    paternita: str = ""
    matricola: str = ""
    grado: str = ""
    reparto: str = ""
    comune: str = ""
    war_period: str = ""
    source_table: str = ""
    source_id: int = 0
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdentifierMatch:
    """A single identifier used for identity resolution."""
    identifier_type: str = ""
    value: str = ""
    strength: IdentifierStrength = IdentifierStrength.WEAK
    compatible: bool = True
    conflict_reason: str = ""


@dataclass
class IdentityCandidate:
    """A distinct candidate for identity resolution.

    Each homonym gets its own IdentityCandidate. Claims from different
    candidates cannot be combined in the same narration.
    """
    candidate_id: str = field(default_factory=_uuid)
    entity_id: Optional[str] = None
    query_subject: str = ""
    match_identifiers: List[IdentifierMatch] = field(default_factory=list)
    identity_status: IdentityStatus = IdentityStatus.CANDIDATE
    conflict_code: str = ""
    conflict_reason: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = 1

    @property
    def strong_count(self) -> int:
        return sum(1 for m in self.match_identifiers if m.strength == IdentifierStrength.STRONG)

    @property
    def medium_count(self) -> int:
        return sum(1 for m in self.match_identifiers if m.strength == IdentifierStrength.MEDIUM)

    @property
    def weak_count(self) -> int:
        return sum(1 for m in self.match_identifiers if m.strength == IdentifierStrength.WEAK)

    @property
    def has_conflict(self) -> bool:
        return any(not m.compatible for m in self.match_identifiers)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["match_identifiers_json"] = json.dumps(
            [{"identifier_type": m.identifier_type, "value": m.value,
              "strength": m.strength.value, "compatible": m.compatible,
              "conflict_reason": m.conflict_reason}
             for m in self.match_identifiers],
            ensure_ascii=False
        )
        d.pop("match_identifiers")
        d["identity_status"] = self.identity_status.value
        d["strong_identifiers_count"] = self.strong_count
        d["medium_identifiers_count"] = self.medium_count
        d["weak_identifiers_count"] = self.weak_count
        return d


@dataclass
class Evidence:
    """A single piece of evidence with separated confidence dimensions."""
    evidence_id: str = field(default_factory=_uuid)
    candidate_id: Optional[str] = None
    artifact_id: Optional[str] = None
    family_id: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.PERSON_EVIDENCE
    evidence_role: str = "supports"  # supports, contradicts, contextual
    source_authority: float = 0.5
    artifact_directness: float = 0.5
    extraction_confidence: float = 0.5
    identity_match_confidence: float = 0.5
    semantic_confidence: float = 0.5
    temporal_compatibility: float = 0.5
    geographical_compatibility: float = 0.5
    source_independence: float = 0.5
    supporting_quote: str = ""
    created_at: str = field(default_factory=_utc_now)
    version: int = 1

    @property
    def overall_confidence(self) -> float:
        """Weighted average of confidence dimensions."""
        weights = {
            "source_authority": 0.20,
            "artifact_directness": 0.15,
            "extraction_confidence": 0.10,
            "identity_match_confidence": 0.20,
            "semantic_confidence": 0.10,
            "temporal_compatibility": 0.10,
            "geographical_compatibility": 0.10,
            "source_independence": 0.05,
        }
        return sum(getattr(self, k) * v for k, v in weights.items())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_type"] = self.evidence_type.value
        d["overall_confidence"] = self.overall_confidence
        return d


@dataclass
class Claim:
    """A structured claim with explicit status lifecycle."""
    claim_id: str = field(default_factory=_uuid)
    subject_entity_id: Optional[str] = None
    candidate_id: Optional[str] = None
    predicate: str = ""
    object_value: str = ""
    object_entity_id: Optional[str] = None
    semantic_role: str = ""
    temporal_value: str = ""
    temporal_precision: str = ""
    polarity: str = "POSITIVE"
    certainty: str = "CANDIDATE"
    status: ClaimStatus = ClaimStatus.CANDIDATE
    claim_type: ClaimType = ClaimType.RECORD_ASSERTION
    evidence_ids: List[str] = field(default_factory=list)
    source_family_ids: List[str] = field(default_factory=list)
    origin: str = "CANONICAL_PIPELINE"
    usable_as_evidence: bool = False
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_ids_json"] = json.dumps(d.pop("evidence_ids"), ensure_ascii=False)
        d["source_family_ids_json"] = json.dumps(d.pop("source_family_ids"), ensure_ascii=False)
        d["status"] = self.status.value
        d["claim_type"] = self.claim_type.value
        d["usable_as_evidence"] = 1 if self.usable_as_evidence else 0
        return d


@dataclass
class Relation:
    """A typed relation between two entities."""
    relation_id: str = field(default_factory=_uuid)
    subject_entity_id: str = ""
    object_entity_id: str = ""
    relation_type: str = ""
    semantic_type: str = ""
    status: RelationStatus = RelationStatus.CANDIDATE
    evidence_ids: List[str] = field(default_factory=list)
    origin: str = "LEGACY_HEURISTIC"
    rule_version: str = ""
    temporal_compatibility: str = ""
    geographical_compatibility: str = ""
    match_confidence: float = 0.5
    extraction_confidence: float = 0.5
    decision_reason: str = ""
    needs_review: bool = True
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_ids_json"] = json.dumps(d.pop("evidence_ids"), ensure_ascii=False)
        d["status"] = self.status.value
        d["needs_review"] = 1 if self.needs_review else 0
        return d


@dataclass
class ReviewDecision:
    """Append-only review decision."""
    decision_id: str = field(default_factory=_uuid)
    target_type: str = ""  # claim, relation, identity_candidate
    target_id: str = ""
    decision: str = ""  # approve, reject, needs_review
    reason: str = ""
    reviewer: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    previous_status: str = ""
    new_status: str = ""
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_ids_json"] = json.dumps(d.pop("evidence_ids"), ensure_ascii=False)
        return d


@dataclass
class EventRegistryEntry:
    """A versioned event in the canonical registry."""
    event_id: str = field(default_factory=_uuid)
    stable_id: str = ""
    name: str = ""
    event_type: str = ""
    parent_event_id: str = ""
    war: str = "WWI"
    data_inizio: str = ""
    data_fine: str = ""
    temporal_precision: str = "day"
    general_location: str = ""
    localities: List[Dict] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)
    units: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    description: str = ""
    source_provenance: Dict[str, Any] = field(default_factory=dict)
    narrative_version: str = ""
    review_status: str = "active"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["localities_json"] = json.dumps(d.pop("localities"), ensure_ascii=False)
        d["subjects_json"] = json.dumps(d.pop("subjects"), ensure_ascii=False)
        d["units_json"] = json.dumps(d.pop("units"), ensure_ascii=False)
        d["aliases_json"] = json.dumps(d.pop("aliases"), ensure_ascii=False)
        d["keywords_json"] = json.dumps(d.pop("keywords"), ensure_ascii=False)
        d["source_provenance_json"] = json.dumps(d.pop("source_provenance"), ensure_ascii=False)
        return d


# ─── Identity resolution rules ──────────────────────────────────────────────

def evaluate_identity(candidate: IdentityCandidate) -> IdentityStatus:
    """Evaluate identity status based on identifier strength and conflicts.

    Rules:
    - name only -> NEEDS_REVIEW
    - surname only -> CANDIDATE (weak)
    - strong conflict -> REJECTED_HOMONYM
    - name + independent compatible identifier -> can evaluate
    - missing data -> not conflict, but not confirmation
    """
    if candidate.has_conflict:
        # Check if any STRONG identifier conflicts
        strong_conflicts = any(
            not m.compatible and m.strength == IdentifierStrength.STRONG
            for m in candidate.match_identifiers
        )
        if strong_conflicts:
            return IdentityStatus.REJECTED_HOMONYM
        # Medium conflict -> needs review
        return IdentityStatus.CONFLICTING

    # No conflicts
    if candidate.strong_count >= 1:
        return IdentityStatus.RESOLVED
    if candidate.medium_count >= 2:
        return IdentityStatus.RESOLVED
    if candidate.medium_count >= 1:
        return IdentityStatus.CANDIDATE
    if candidate.weak_count >= 1 and candidate.strong_count == 0 and candidate.medium_count == 0:
        return IdentityStatus.NEEDS_REVIEW
    return IdentityStatus.UNRESOLVED


def can_combine_claims(candidates: List[IdentityCandidate]) -> bool:
    """Check if claims from multiple candidates can be combined.

    Claims from different candidates can NEVER be combined in the same narration.
    """
    resolved = [c for c in candidates if c.identity_status == IdentityStatus.RESOLVED]
    if len(resolved) > 1:
        return False  # Multiple resolved identities — ambiguity
    if len(resolved) == 1:
        return True  # One resolved identity — use its claims
    # No resolved identities — cannot combine
    return False
