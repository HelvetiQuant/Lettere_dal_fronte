"""Typed data contracts for PERSON pipeline V7.3.

PersonCandidate: a candidate identity from a single source record.
PersonFact: a unique biographical fact with supporting evidence.
FactEvidence: a single piece of evidence supporting a fact.
SourceProvenance: provenance metadata for a source record.
ConflictSet: a set of conflicting values for the same predicate.
RejectedObservation: an observation rejected with documented reasons.

Key invariants:
  1. PersonFact has 1+ FactEvidence — no orphan facts.
  2. FactEvidence always links to a source record — no unattributable evidence.
  3. SourceProvenance preserves raw_value — never overwritten.
  4. ConflictSet tracks all conflicting values — no silent resolution.
  5. RejectedObservation has reason_codes — no undocumented rejections.
  6. PersonCandidate has war_period — for temporal barrier enforcement.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple


# ─── PersonCandidate ────────────────────────────────────────────────────────

@dataclass
class PersonCandidate:
    """A candidate person identity from a single source record.

    One DB record = one PersonCandidate.
    Candidates are grouped into clusters by the identity resolver.
    """
    candidate_id: str  # stable hash of source_table:record_id
    source_table: str
    record_id: Any
    cognome: str = ""
    nome: str = ""
    nominativo: str = ""
    war_period: str = ""  # WWI | WWII | BOTH | UNKNOWN
    authority_tier: int = 2
    raw_record: Dict[str, Any] = field(default_factory=dict)
    identity_fields: Dict[str, str] = field(default_factory=dict)  # field_name → value
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.candidate_id:
            raw = f"{self.source_table}:{self.record_id}"
            self.candidate_id = f"cand_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    @property
    def display_name(self) -> str:
        if self.nominativo:
            return self.nominativo
        return f"{self.cognome} {self.nome}".strip()

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "source_table": self.source_table,
            "record_id": self.record_id,
            "cognome": self.cognome,
            "nome": self.nome,
            "nominativo": self.nominativo,
            "war_period": self.war_period,
            "authority_tier": self.authority_tier,
            "display_name": self.display_name,
            "identity_fields": self.identity_fields,
        }


# ─── FactEvidence ───────────────────────────────────────────────────────────

@dataclass
class FactEvidence:
    """A single piece of evidence supporting a PersonFact.

    Always links to a specific source record — no unattributable evidence.
    """
    evidence_id: str
    candidate_id: str  # links to PersonCandidate
    source_table: str
    record_id: Any
    source_field: str  # DB column name
    value_raw: str  # original value, never modified
    value_normalized: str  # normalized value (may equal value_raw)
    normalizer_note: str = ""  # description of normalization (if any)
    authority_tier: int = 2
    war_period: str = ""

    def __post_init__(self):
        if not self.evidence_id:
            raw = f"{self.candidate_id}:{self.source_field}:{self.value_raw}"
            self.evidence_id = f"ev_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "candidate_id": self.candidate_id,
            "source_table": self.source_table,
            "record_id": self.record_id,
            "source_field": self.source_field,
            "value_raw": self.value_raw,
            "value_normalized": self.value_normalized,
            "normalizer_note": self.normalizer_note,
            "authority_tier": self.authority_tier,
            "war_period": self.war_period,
        }


# ─── SourceProvenance ───────────────────────────────────────────────────────

@dataclass
class SourceProvenance:
    """Provenance metadata for a source record.

    Provenance is NOT a claim — it describes WHERE the data came from,
    not WHAT the data says about the person.
    """
    provenance_id: str
    candidate_id: str
    source_table: str
    record_id: Any
    predicate: str  # archive_letter, source_document, source_page, source_url, etc.
    value_raw: str
    value_normalized: str
    source_field: str  # DB column name

    def __post_init__(self):
        if not self.provenance_id:
            raw = f"{self.candidate_id}:{self.predicate}:{self.value_raw}"
            self.provenance_id = f"prov_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    def to_dict(self) -> dict:
        return {
            "provenance_id": self.provenance_id,
            "candidate_id": self.candidate_id,
            "source_table": self.source_table,
            "record_id": self.record_id,
            "predicate": self.predicate,
            "value_raw": self.value_raw,
            "value_normalized": self.value_normalized,
            "source_field": self.source_field,
        }


# ─── PersonFact ─────────────────────────────────────────────────────────────

@dataclass
class PersonFact:
    """A unique biographical fact about a person.

    A fact is unique per (cluster_id, predicate, normalized_value).
    Multiple evidence records can support the same fact.
    """
    fact_id: str
    cluster_id: str  # identity cluster this fact belongs to
    predicate: str  # birth_date, rank, military_unit, etc.
    value_normalized: str  # the canonical normalized value
    value_raw_first: str  # first raw value seen (for audit)
    evidence: List[FactEvidence] = field(default_factory=list)
    conflict_set_id: Optional[str] = None  # links to ConflictSet if conflicting
    status: str = "ASSERTED"  # ASSERTED | VERIFIED | PROBABLE | CONFLICTING | REJECTED
    confidence: float = 0.85

    def __post_init__(self):
        if not self.fact_id:
            raw = f"{self.cluster_id}:{self.predicate}:{self.value_normalized}"
            self.fact_id = f"fact_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    @property
    def source_tables(self) -> List[str]:
        return list(set(e.source_table for e in self.evidence))

    @property
    def is_multi_source(self) -> bool:
        """True if fact is supported by evidence from 2+ different tables."""
        return len(self.source_tables) >= 2

    def add_evidence(self, ev: FactEvidence):
        """Add evidence, avoiding duplicates."""
        existing_ids = {e.evidence_id for e in self.evidence}
        if ev.evidence_id not in existing_ids:
            self.evidence.append(ev)
            # Upgrade confidence if multi-source
            if self.is_multi_source:
                self.confidence = max(self.confidence, 0.9)
                if self.status == "ASSERTED":
                    self.status = "VERIFIED"

    def to_dict(self) -> dict:
        return {
            "fact_id": self.fact_id,
            "cluster_id": self.cluster_id,
            "predicate": self.predicate,
            "value_normalized": self.value_normalized,
            "value_raw_first": self.value_raw_first,
            "evidence": [e.to_dict() for e in self.evidence],
            "evidence_count": self.evidence_count,
            "source_tables": self.source_tables,
            "is_multi_source": self.is_multi_source,
            "conflict_set_id": self.conflict_set_id,
            "status": self.status,
            "confidence": self.confidence,
        }


# ─── ConflictSet ────────────────────────────────────────────────────────────

@dataclass
class ConflictEntry:
    """A single value in a conflict set."""
    value: str
    candidate_id: str
    source_table: str
    record_id: Any
    source_field: str

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "candidate_id": self.candidate_id,
            "source_table": self.source_table,
            "record_id": self.record_id,
            "source_field": self.source_field,
        }


@dataclass
class ConflictSet:
    """A set of conflicting values for the same predicate within a cluster.

    All values are preserved — no silent resolution.
    The narrator must present all conflicting values with their provenance.
    """
    conflict_id: str
    cluster_id: str
    predicate: str
    entries: List[ConflictEntry] = field(default_factory=list)

    def __post_init__(self):
        if not self.conflict_id:
            raw = f"{self.cluster_id}:{self.predicate}:conflict"
            self.conflict_id = f"conf_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    @property
    def values(self) -> List[str]:
        """Unique conflicting values."""
        return list(set(e.value for e in self.entries))

    @property
    def is_active(self) -> bool:
        """True if there are 2+ distinct values."""
        return len(self.values) >= 2

    def add_entry(self, value: str, candidate_id: str, source_table: str, record_id: Any, source_field: str):
        """Add a conflicting value entry."""
        self.entries.append(ConflictEntry(
            value=value,
            candidate_id=candidate_id,
            source_table=source_table,
            record_id=record_id,
            source_field=source_field,
        ))

    def to_dict(self) -> dict:
        return {
            "conflict_id": self.conflict_id,
            "cluster_id": self.cluster_id,
            "predicate": self.predicate,
            "values": self.values,
            "entries": [e.to_dict() for e in self.entries],
            "is_active": self.is_active,
        }


# ─── RejectedObservation ────────────────────────────────────────────────────

@dataclass
class RejectedObservation:
    """An observation rejected with documented reasons."""
    candidate_name: str
    source_table: str
    record_id: Any
    reason_codes: List[str]
    conflicting_features: List[str]
    candidate_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "candidate_name": self.candidate_name,
            "source_table": self.source_table,
            "record_id": self.record_id,
            "reason_codes": self.reason_codes,
            "conflicting_features": self.conflicting_features,
            "candidate_fields": self.candidate_fields,
        }


# ─── PersonPipelineResult ───────────────────────────────────────────────────

@dataclass
class PersonPipelineResult:
    """Complete result of PERSON pipeline execution.

    Separates facts, evidence, provenance, conflicts, and rejections
    into distinct collections with clear semantics.
    """
    query_name: str = ""
    identity_status: str = "UNRESOLVED_IDENTITY"  # ANCHORED_RECORD | RESOLVED_IDENTITY | AMBIGUOUS_IDENTITY | PARTIAL_IDENTITY | UNRESOLVED_IDENTITY
    candidates: List[PersonCandidate] = field(default_factory=list)
    facts: List[PersonFact] = field(default_factory=list)
    all_evidence: List[FactEvidence] = field(default_factory=list)
    provenance: List[SourceProvenance] = field(default_factory=list)
    conflicts: List[ConflictSet] = field(default_factory=list)
    rejected: List[RejectedObservation] = field(default_factory=list)
    cluster_id: Optional[str] = None
    war_period: str = ""

    @property
    def unique_facts_count(self) -> int:
        return len(self.facts)

    @property
    def evidence_records_count(self) -> int:
        return len(self.all_evidence)

    @property
    def provenance_items_count(self) -> int:
        return len(self.provenance)

    @property
    def conflict_sets_count(self) -> int:
        return len([c for c in self.conflicts if c.is_active])

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def candidate_clusters_count(self) -> int:
        """Number of distinct candidate clusters."""
        return len(set(c.candidate_id for c in self.candidates))

    @property
    def facts_with_provenance_count(self) -> int:
        """Facts that have at least one provenance item from their evidence."""
        provenance_candidates = {p.candidate_id for p in self.provenance}
        facts_with_prov = 0
        for fact in self.facts:
            if any(e.candidate_id in provenance_candidates for e in fact.evidence):
                facts_with_prov += 1
        return facts_with_prov

    def to_dict(self) -> dict:
        return {
            "query_name": self.query_name,
            "identity_status": self.identity_status,
            "cluster_id": self.cluster_id,
            "war_period": self.war_period,
            "candidates": [c.to_dict() for c in self.candidates],
            "facts": [f.to_dict() for f in self.facts],
            "all_evidence": [e.to_dict() for e in self.all_evidence],
            "provenance": [p.to_dict() for p in self.provenance],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "rejected": [r.to_dict() for r in self.rejected],
            "metrics": {
                "unique_person_facts": self.unique_facts_count,
                "supporting_evidence_records": self.evidence_records_count,
                "unique_source_records": self.candidate_clusters_count,
                "provenance_items": self.provenance_items_count,
                "conflict_sets": self.conflict_sets_count,
                "rejected_observations": self.rejected_count,
                "facts_with_provenance": self.facts_with_provenance_count,
            },
        }
