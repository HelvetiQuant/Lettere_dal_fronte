"""V7.3-Fase7: Versioned candidate linking for person ↔ unit ↔ event.

Implements a probatory hierarchy for linking:
  1. PERSON_EVIDENCE (strongest): direct record assertions about a person
  2. UNIT_EVIDENCE: unit membership from person records (personal_duty)
  3. EVENT_CONTEXT_EVIDENCE: event-unit associations from event records
  4. INFERRED_LINK: derived link (person→event via unit chain)

Key invariants:
  - All candidates are versioned (algorithm_name + algorithm_version)
  - Candidates start as 'candidate', never 'confirmed'
  - No destructive updates — superseded candidates get status='superseded'
  - Evidence hierarchy: direct > unit > event_context > inferred
  - Person→Event links via unit chain are always 'needs_review'
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ─── Evidence hierarchy ──────────────────────────────────────────────────────

EVIDENCE_HIERARCHY = {
    "PERSON_EVIDENCE": 4,      # direct record assertion
    "UNIT_EVIDENCE": 3,        # unit membership from person record
    "EVENT_CONTEXT_EVIDENCE": 2,  # event-unit association
    "INFERRED_LINK": 1,        # derived via chain
}

# Relation types for person ↔ unit ↔ event
RELATION_TYPES = {
    "person_served_in_unit": "person → unit (personal_duty)",
    "unit_participated_in_event": "unit → event (event context)",
    "person_participated_in_event": "person → event (direct or inferred)",
    "person_witnessed_event": "person → event (direct witness)",
}

# Algorithm metadata
ALGORITHM_NAME = "v73_fase7_linking"
ALGORITHM_VERSION = "1.0.0"


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class LinkCandidate:
    """A versioned candidate link between two resources."""
    candidate_id: str = field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:16]}")
    source_resource_id: str = ""
    target_resource_id: str = ""
    relation_type: str = ""
    evidence_tier: str = "INFERRED_LINK"  # EVIDENCE_HIERARCHY key
    evidence_strength: str = "weak"  # weak, moderate, strong
    raw_score: float = 0.0
    status: str = "candidate"  # candidate, needs_review, accepted, rejected, superseded
    algorithm_name: str = field(default=ALGORITHM_NAME, init=False)
    algorithm_version: str = field(default=ALGORITHM_VERSION, init=False)
    decision_reason: str = ""
    evidence_chain: List[Dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    superseded_by: str = ""  # ID of candidate that supersedes this one

    @property
    def evidence_rank(self) -> int:
        return EVIDENCE_HIERARCHY.get(self.evidence_tier, 0)

    @property
    def is_direct(self) -> bool:
        return self.evidence_tier in ("PERSON_EVIDENCE", "UNIT_EVIDENCE")

    @property
    def is_inferred(self) -> bool:
        return self.evidence_tier == "INFERRED_LINK"

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "source_resource_id": self.source_resource_id,
            "target_resource_id": self.target_resource_id,
            "relation_type": self.relation_type,
            "evidence_tier": self.evidence_tier,
            "evidence_strength": self.evidence_strength,
            "raw_score": self.raw_score,
            "status": self.status,
            "algorithm_name": self.algorithm_name,
            "algorithm_version": self.algorithm_version,
            "decision_reason": self.decision_reason,
            "evidence_chain": self.evidence_chain,
            "created_at": self.created_at,
            "superseded_by": self.superseded_by,
            "evidence_rank": self.evidence_rank,
            "is_direct": self.is_direct,
            "is_inferred": self.is_inferred,
        }


@dataclass
class PersonUnitLink:
    """Person → Unit link derived from person record."""
    person_resource_id: str = ""
    unit_resource_id: str = ""
    unit_name: str = ""
    unit_normalized: str = ""
    ontology_class: str = "personal_duty"  # from military_ontology
    source_table: str = ""
    source_record_id: str = ""
    confidence: float = 0.0

    def to_candidate(self) -> LinkCandidate:
        return LinkCandidate(
            source_resource_id=self.person_resource_id,
            target_resource_id=self.unit_resource_id,
            relation_type="person_served_in_unit",
            evidence_tier="UNIT_EVIDENCE",
            evidence_strength="strong" if self.confidence >= 0.8 else "moderate",
            raw_score=self.confidence,
            decision_reason=f"unit_from_person_record:{self.source_table}:{self.source_record_id}",
            evidence_chain=[{
                "source": f"{self.source_table}:{self.source_record_id}",
                "field": "reparto",
                "value": self.unit_name,
                "ontology": self.ontology_class,
            }],
        )


@dataclass
class UnitEventLink:
    """Unit → Event link derived from event record or event registry."""
    unit_resource_id: str = ""
    event_resource_id: str = ""
    event_name: str = ""
    unit_name: str = ""
    source: str = ""  # "event_registry" | "event_record" | "keyword_match"
    confidence: float = 0.0
    temporal_compatible: bool = True

    def to_candidate(self) -> LinkCandidate:
        tier = "EVENT_CONTEXT_EVIDENCE"
        strength = "moderate"
        if self.source == "event_registry":
            strength = "strong"
        elif self.source == "keyword_match":
            strength = "weak"

        return LinkCandidate(
            source_resource_id=self.unit_resource_id,
            target_resource_id=self.event_resource_id,
            relation_type="unit_participated_in_event",
            evidence_tier=tier,
            evidence_strength=strength,
            raw_score=self.confidence,
            decision_reason=f"unit_event_from:{self.source}",
            evidence_chain=[{
                "source": self.source,
                "event": self.event_name,
                "unit": self.unit_name,
                "temporal_compatible": str(self.temporal_compatible),
            }],
        )


@dataclass
class PersonEventLink:
    """Person → Event link, either direct or inferred via unit chain."""
    person_resource_id: str = ""
    event_resource_id: str = ""
    event_name: str = ""
    link_path: str = ""  # "direct" | "via_unit"
    intermediate_unit_id: str = ""
    intermediate_unit_name: str = ""
    confidence: float = 0.0
    is_inferred: bool = False

    def to_candidate(self) -> LinkCandidate:
        if self.link_path == "direct":
            tier = "PERSON_EVIDENCE"
            strength = "strong" if self.confidence >= 0.7 else "moderate"
            status = "candidate"
            reason = "direct_person_event_link"
        else:
            tier = "INFERRED_LINK"
            strength = "weak"
            status = "needs_review"
            reason = f"inferred_via_unit:{self.intermediate_unit_name}"

        return LinkCandidate(
            source_resource_id=self.person_resource_id,
            target_resource_id=self.event_resource_id,
            relation_type="person_participated_in_event",
            evidence_tier=tier,
            evidence_strength=strength,
            raw_score=self.confidence,
            status=status,
            decision_reason=reason,
            evidence_chain=self._build_chain(),
        )

    def _build_chain(self) -> List[Dict[str, str]]:
        chain = []
        if self.link_path == "via_unit":
            chain.append({
                "step": "person→unit",
                "unit": self.intermediate_unit_name,
                "unit_id": self.intermediate_unit_id,
            })
            chain.append({
                "step": "unit→event",
                "event": self.event_name,
            })
        else:
            chain.append({
                "step": "person→event",
                "event": self.event_name,
            })
        return chain


# ─── Link resolver ───────────────────────────────────────────────────────────

class LinkResolver:
    """Resolves person→event links via unit chains with versioned candidates.

    The resolver builds a graph:
      person → unit (from person records, UNIT_EVIDENCE)
      unit → event (from event registry, EVENT_CONTEXT_EVIDENCE)
      person → event (inferred via unit chain, INFERRED_LINK)

    All candidates are versioned. When a new candidate is generated for
    the same (source, target, relation_type), the old one is superseded.
    """

    def __init__(self):
        self._person_unit_links: List[PersonUnitLink] = []
        self._unit_event_links: List[UnitEventLink] = []
        self._person_event_links: List[PersonEventLink] = []
        self._candidates: Dict[str, LinkCandidate] = {}  # candidate_id → LinkCandidate
        self._semantic_index: Dict[Tuple[str, str, str], str] = {}  # (src, tgt, type) → candidate_id

    def add_person_unit_link(self, link: PersonUnitLink):
        self._person_unit_links.append(link)
        cand = link.to_candidate()
        self._register_candidate(cand)

    def add_unit_event_link(self, link: UnitEventLink):
        self._unit_event_links.append(link)
        cand = link.to_candidate()
        self._register_candidate(cand)

    def add_person_event_link(self, link: PersonEventLink):
        self._person_event_links.append(link)
        cand = link.to_candidate()
        self._register_candidate(cand)

    def _register_candidate(self, candidate: LinkCandidate):
        """Register a candidate, superseding any existing one with same semantic key."""
        semantic_key = (
            candidate.source_resource_id,
            candidate.target_resource_id,
            candidate.relation_type,
        )
        existing_id = self._semantic_index.get(semantic_key)
        if existing_id and existing_id in self._candidates:
            existing = self._candidates[existing_id]
            # Supersede only if new candidate has higher or equal evidence rank
            if candidate.evidence_rank >= existing.evidence_rank:
                existing.status = "superseded"
                existing.superseded_by = candidate.candidate_id
                self._candidates[candidate.candidate_id] = candidate
                self._semantic_index[semantic_key] = candidate.candidate_id
            else:
                # New candidate is weaker — keep existing, mark new as superseded
                candidate.status = "superseded"
                candidate.superseded_by = existing_id
                self._candidates[candidate.candidate_id] = candidate
        else:
            self._candidates[candidate.candidate_id] = candidate
            self._semantic_index[semantic_key] = candidate.candidate_id

    def infer_person_event_links(self) -> List[PersonEventLink]:
        """Infer person→event links via unit chains.

        For each person→unit link, find all unit→event links for the same unit.
        Create an inferred person→event link with combined confidence.

        Confidence formula:
          inferred_confidence = person_unit_confidence * unit_event_confidence * 0.7
          (0.7 factor because inference is weaker than direct evidence)
        """
        inferred = []

        # Build unit→event index
        unit_event_by_unit: Dict[str, List[UnitEventLink]] = {}
        for ue in self._unit_event_links:
            unit_event_by_unit.setdefault(ue.unit_resource_id, []).append(ue)

        for pu in self._person_unit_links:
            if pu.unit_resource_id not in unit_event_by_unit:
                continue
            for ue in unit_event_by_unit[pu.unit_resource_id]:
                if not ue.temporal_compatible:
                    continue
                confidence = pu.confidence * ue.confidence * 0.7
                link = PersonEventLink(
                    person_resource_id=pu.person_resource_id,
                    event_resource_id=ue.event_resource_id,
                    event_name=ue.event_name,
                    link_path="via_unit",
                    intermediate_unit_id=pu.unit_resource_id,
                    intermediate_unit_name=pu.unit_name,
                    confidence=confidence,
                    is_inferred=True,
                )
                inferred.append(link)
                self.add_person_event_link(link)

        return inferred

    def get_active_candidates(self) -> List[LinkCandidate]:
        """Get all non-superseded candidates."""
        return [c for c in self._candidates.values() if c.status != "superseded"]

    def get_candidates_by_relation(self, relation_type: str) -> List[LinkCandidate]:
        """Get active candidates for a specific relation type."""
        return [
            c for c in self._candidates.values()
            if c.relation_type == relation_type and c.status != "superseded"
        ]

    def get_person_event_candidates(self, person_resource_id: str) -> List[LinkCandidate]:
        """Get all active person→event candidates for a specific person."""
        return [
            c for c in self._candidates.values()
            if c.source_resource_id == person_resource_id
            and c.relation_type == "person_participated_in_event"
            and c.status != "superseded"
        ]

    def get_evidence_chain_for_person_event(
        self,
        person_resource_id: str,
        event_resource_id: str,
    ) -> List[Dict[str, str]]:
        """Get the full evidence chain for a person→event link."""
        chain = []
        for c in self._candidates.values():
            if (c.source_resource_id == person_resource_id
                    and c.target_resource_id == event_resource_id
                    and c.relation_type == "person_participated_in_event"
                    and c.status != "superseded"):
                chain.extend(c.evidence_chain)
        return chain

    def all_candidates(self) -> List[LinkCandidate]:
        return list(self._candidates.values())

    def stats(self) -> Dict[str, int]:
        """Get statistics about candidates."""
        active = self.get_active_candidates()
        return {
            "total": len(self._candidates),
            "active": len(active),
            "superseded": sum(1 for c in self._candidates.values() if c.status == "superseded"),
            "person_unit": sum(1 for c in active if c.relation_type == "person_served_in_unit"),
            "unit_event": sum(1 for c in active if c.relation_type == "unit_participated_in_event"),
            "person_event": sum(1 for c in active if c.relation_type == "person_participated_in_event"),
            "inferred": sum(1 for c in active if c.is_inferred),
            "direct": sum(1 for c in active if c.is_direct),
            "needs_review": sum(1 for c in active if c.status == "needs_review"),
        }
