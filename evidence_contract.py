"""Evidence Contract — central definition and validators for the evidence-centric model.

This module enforces the architectural principle:

    SOURCE → OBSERVATION → EVIDENCE → CLAIM → RELATION → ANSWER

with PROVENANCE, SOURCE LINEAGE, CONFLICTS, ASSESSMENT, and EVIDENCE SNAPSHOT
as transversal structures.

Key invariants:
    1. No claim without evidence.
    2. No evidence without observation.
    3. No observation without source.
    4. No relation without claim(s).
    5. No verified status without evidence + provenance.
    6. No AI answer without AnswerEvidenceBundle.
    7. AUTHORITY ≠ RELEVANCE — high authority + low relevance = no evidence.
    8. MULTIPLE SOURCES ≠ INDEPENDENT SOURCES — same lineage = 1 independent.
    9. RETRIEVAL ≠ VERIFICATION — finding a result ≠ proving a fact.
   10. No legacy shortcut to truth — legacy relations must be revalidated.

Usage:
    from evidence_contract import EvidenceContract, ClaimStatus, VerificationStatus

    contract = EvidenceContract()
    contract.validate_claim(claim)  # raises ContractViolation if invalid
    contract.can_be_verified(claim, evidence_items)  # returns bool
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


# ─── Enums / Constants ────────────────────────────────────────────────────────

CONTRACT_VERSION = "1.0.0"


class ClaimStatus:
    """Verification status for a claim."""
    UNSUPPORTED = "unsupported"
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    PROBABLE = "probable"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    DISPUTED = "disputed"
    REJECTED = "rejected"

    ALL = [UNSUPPORTED, CANDIDATE, SUPPORTED, PROBABLE, VERIFIED, CONTRADICTED, DISPUTED, REJECTED]
    VERIFIED_OR_HIGHER = {VERIFIED}
    PROBABLE_OR_HIGHER = {VERIFIED, PROBABLE}
    SUPPORTED_OR_HIGHER = {VERIFIED, PROBABLE, SUPPORTED}
    NOT_VERIFIED = {UNSUPPORTED, CANDIDATE, REJECTED}
    CONFLICTED = {CONTRADICTED, DISPUTED}


class EvidenceSupportType:
    """How evidence relates to a claim."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"
    CONTEXT = "context"


class SourceOriginType:
    """Source lineage classification."""
    INDEPENDENT = "independent"
    DERIVED = "derived"
    REPUBLICATION = "republication"
    MIRROR = "mirror"
    UNKNOWN = "unknown"


class TemporalGate:
    """Temporal compatibility classification."""
    DIRECT_CONTEMPORARY = "direct_contemporary"
    RETROSPECTIVE = "retrospective"
    TEMPORALLY_COMPATIBLE = "temporally_compatible"
    TEMPORALLY_AMBIGUOUS = "temporally_ambiguous"
    TEMPORALLY_INCOMPATIBLE = "temporally_incompatible"

    BLOCKING = {TEMPORALLY_INCOMPATIBLE}


class RelationOrigin:
    """Origin of a relation."""
    V2 = "v2"
    LEGACY = "legacy"
    LEGACY_REVALIDATED = "legacy_revalidated"
    MANUAL = "manual"
    IMPORTED = "imported"


# ─── Contract data classes ────────────────────────────────────────────────────

@dataclass
class SourceRef:
    """Reference to a source in the evidence chain."""
    source_id: str
    provider: str
    source_type: str  # archive|document|web|ocr|ai_extracted|user_submitted
    authority_tier: int = 4  # 1=official, 2=primary, 3=secondary, 4=unofficial
    lineage_id: str = ""
    origin_type: str = SourceOriginType.UNKNOWN
    url: str = ""
    archival_reference: str = ""


@dataclass
class ObservationRef:
    """Reference to an observation extracted from a source."""
    observation_id: str
    source_id: str
    observation_type: str  # field_extraction|entity_mention|date|place|unit|matricola|event_ref
    field_name: str
    raw_value: str
    normalized_value: str = ""
    extraction_method: str = ""
    extractor_version: str = ""
    page: Optional[int] = None
    excerpt: str = ""


@dataclass
class EvidenceRef:
    """Reference to evidence qualified from an observation."""
    evidence_id: str
    observation_id: str
    support_type: str  # supports|contradicts|mentions|context
    evidence_type: str = "direct"  # direct|indirect|contextual|metadata
    is_independent: bool = False
    lineage_id: str = ""
    verification_status: str = "unverified"


@dataclass
class ClaimRef:
    """Reference to an atomic historical claim."""
    claim_id: str
    subject_id: str
    predicate: str
    object_value: str
    normalized_value: str = ""
    temporal_context: str = ""
    geographic_context: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    support_score: float = 0.0
    conflict_status: str = "none"
    verification_status: str = ClaimStatus.UNSUPPORTED
    identity_cluster_id: str = ""
    source_lineage_ids: List[str] = field(default_factory=list)
    pipeline_run_id: str = ""
    provenance_chain: List[str] = field(default_factory=list)


@dataclass
class RelationRef:
    """Reference to a structured relation derived from claims/evidence."""
    relation_id: str
    source_resource_id: str
    target_resource_id: str
    relation_type: str
    claim_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    temporal_gate: str = TemporalGate.TEMPORALLY_AMBIGUOUS
    geographic_gate: str = "unknown"
    identity_gate: str = "unverified"
    origin: str = RelationOrigin.V2
    raw_score: float = 0.0
    verification_status: str = ClaimStatus.CANDIDATE


@dataclass
class AnswerEvidenceBundle:
    """Structured bundle passed to the AI narrator.

    Contains ONLY verified/probable/disputed/unsupported claims.
    The AI must NOT receive raw records or unvalidated legacy relations.
    """
    verified_claims: List[ClaimRef] = field(default_factory=list)
    probable_claims: List[ClaimRef] = field(default_factory=list)
    disputed_claims: List[ClaimRef] = field(default_factory=list)
    unsupported_claims: List[ClaimRef] = field(default_factory=list)
    rejected_claims: List[ClaimRef] = field(default_factory=list)
    sources: List[SourceRef] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    snapshot_id: str = ""
    context_hash: str = ""
    answer_hash: str = ""

    @property
    def total_claims(self) -> int:
        return len(self.verified_claims) + len(self.probable_claims) + \
               len(self.disputed_claims) + len(self.unsupported_claims)

    @property
    def has_verified_evidence(self) -> bool:
        return len(self.verified_claims) > 0

    def to_prompt_context(self) -> str:
        """Generate the mandatory AI prompt context string."""
        lines = [
            "EVIDENCE BUNDLE — AI NARRATION RULES",
            "====================================",
            "",
            "STATUS DEFINITIONS:",
            "- VERIFIED: Can be stated as fact.",
            "- PROBABLE: Use probabilistic phrasing ('likely', 'probably').",
            "- DISPUTED: Show the conflict explicitly.",
            "- UNSUPPORTED: Do NOT present as fact.",
            "- REJECTED: Do NOT use.",
            "",
        ]

        if self.verified_claims:
            lines.append("VERIFIED CLAIMS:")
            for c in self.verified_claims:
                lines.append(f"  [V] {c.predicate}: {c.object_value} (evidence: {len(c.evidence_ids)})")
            lines.append("")

        if self.probable_claims:
            lines.append("PROBABLE CLAIMS:")
            for c in self.probable_claims:
                lines.append(f"  [P] {c.predicate}: {c.object_value} (evidence: {len(c.evidence_ids)})")
            lines.append("")

        if self.disputed_claims:
            lines.append("DISPUTED CLAIMS:")
            for c in self.disputed_claims:
                lines.append(f"  [D] {c.predicate}: {c.object_value} (conflict: {c.conflict_status})")
            lines.append("")

        if self.unsupported_claims:
            lines.append("UNSUPPORTED CLAIMS (do NOT present as fact):")
            for c in self.unsupported_claims:
                lines.append(f"  [U] {c.predicate}: {c.object_value}")
            lines.append("")

        if self.conflicts:
            lines.append("CONFLICTS:")
            for conf in self.conflicts:
                lines.append(f"  - {conf.get('description', 'Unknown conflict')}")
            lines.append("")

        if self.gaps:
            lines.append("INFORMATION GAPS:")
            for gap in self.gaps:
                lines.append(f"  - {gap.get('description', 'Unknown gap')}")
            lines.append("")

        return "\n".join(lines)


# ─── Contract violations ──────────────────────────────────────────────────────

class ContractViolation(Exception):
    """Raised when the evidence contract is violated."""
    def __init__(self, code: str, description: str, context: str = ""):
        self.code = code
        self.description = description
        self.context = context
        super().__init__(f"[{code}] {description}")


# ─── Contract validator ───────────────────────────────────────────────────────

class EvidenceContract:
    """Central evidence contract validator.

    Enforces the SOURCE → OBSERVATION → EVIDENCE → CLAIM → RELATION → ANSWER chain.
    """

    VERSION = CONTRACT_VERSION

    # ─── Claim validation ─────────────────────────────────────────────────────

    @staticmethod
    def validate_claim(claim: ClaimRef,
                       evidence_items: Optional[List[EvidenceRef]] = None) -> List[ContractViolation]:
        """Validate a claim against the evidence contract.

        Returns a list of violations (empty if valid).
        """
        violations: List[ContractViolation] = []

        # Invariant 1: No claim without evidence (for verified/probable/supported)
        if claim.verification_status in ClaimStatus.SUPPORTED_OR_HIGHER:
            if not claim.evidence_ids:
                violations.append(ContractViolation(
                    "NO_EVIDENCE_FOR_VERIFIED_CLAIM",
                    f"Claim {claim.claim_id} has status '{claim.verification_status}' but no evidence_ids",
                ))
            elif evidence_items:
                actual_evidence = [e for e in evidence_items if e.evidence_id in claim.evidence_ids]
                if not actual_evidence:
                    violations.append(ContractViolation(
                        "EVIDENCE_NOT_FOUND",
                        f"Claim {claim.claim_id} references evidence_ids but none found in provided items",
                    ))
                # Check that at least one evidence supports the claim
                supporting = [e for e in actual_evidence if e.support_type == EvidenceSupportType.SUPPORTS]
                if not supporting:
                    violations.append(ContractViolation(
                        "NO_SUPPORTING_EVIDENCE",
                        f"Claim {claim.claim_id} has evidence but none with support_type='supports'",
                    ))

        # Invariant 5: No verified status without evidence + provenance
        if claim.verification_status == ClaimStatus.VERIFIED:
            if not claim.evidence_ids:
                violations.append(ContractViolation(
                    "VERIFIED_WITHOUT_EVIDENCE",
                    f"Claim {claim.claim_id} is VERIFIED but has no evidence_ids",
                ))
            if not claim.provenance_chain:
                violations.append(ContractViolation(
                    "VERIFIED_WITHOUT_PROVENANCE",
                    f"Claim {claim.claim_id} is VERIFIED but has empty provenance_chain",
                ))

        # Invariant: VERIFIED requires at least 1 independent evidence
        if claim.verification_status == ClaimStatus.VERIFIED and evidence_items:
            independent = [
                e for e in evidence_items
                if e.evidence_id in claim.evidence_ids and e.is_independent
            ]
            if not independent:
                violations.append(ContractViolation(
                    "VERIFIED_WITHOUT_INDEPENDENT_EVIDENCE",
                    f"Claim {claim.claim_id} is VERIFIED but no evidence is marked is_independent",
                ))

        return violations

    # ─── Evidence validation ──────────────────────────────────────────────────

    @staticmethod
    def validate_evidence(evidence: EvidenceRef,
                          observation: Optional[ObservationRef] = None) -> List[ContractViolation]:
        """Validate an evidence item against the contract."""
        violations: List[ContractViolation] = []

        # Invariant 2: No evidence without observation
        if not evidence.observation_id:
            violations.append(ContractViolation(
                "EVIDENCE_WITHOUT_OBSERVATION",
                f"Evidence {evidence.evidence_id} has no observation_id",
            ))
        elif observation and observation.observation_id != evidence.observation_id:
            violations.append(ContractViolation(
                "OBSERVATION_MISMATCH",
                f"Evidence {evidence.evidence_id} references observation {evidence.observation_id} "
                f"but provided observation is {observation.observation_id}",
            ))

        return violations

    # ─── Observation validation ───────────────────────────────────────────────

    @staticmethod
    def validate_observation(observation: ObservationRef,
                             source: Optional[SourceRef] = None) -> List[ContractViolation]:
        """Validate an observation against the contract."""
        violations: List[ContractViolation] = []

        # Invariant 3: No observation without source
        if not observation.source_id:
            violations.append(ContractViolation(
                "OBSERVATION_WITHOUT_SOURCE",
                f"Observation {observation.observation_id} has no source_id",
            ))
        elif source and source.source_id != observation.source_id:
            violations.append(ContractViolation(
                "SOURCE_MISMATCH",
                f"Observation {observation.observation_id} references source {observation.source_id} "
                f"but provided source is {source.source_id}",
            ))

        if not observation.raw_value:
            violations.append(ContractViolation(
                "EMPTY_OBSERVATION",
                f"Observation {observation.observation_id} has empty raw_value",
            ))

        return violations

    # ─── Relation validation ──────────────────────────────────────────────────

    @staticmethod
    def validate_relation(relation: RelationRef,
                          claims: Optional[List[ClaimRef]] = None) -> List[ContractViolation]:
        """Validate a relation against the contract."""
        violations: List[ContractViolation] = []

        # Invariant 4: No relation without claim(s) — unless legacy
        if relation.origin != RelationOrigin.LEGACY:
            if not relation.claim_ids:
                violations.append(ContractViolation(
                    "RELATION_WITHOUT_CLAIMS",
                    f"Relation {relation.relation_id} (origin={relation.origin}) has no claim_ids",
                ))

        # Legacy relations must not be verified
        if relation.origin == RelationOrigin.LEGACY and \
           relation.verification_status in ClaimStatus.VERIFIED_OR_HIGHER:
            violations.append(ContractViolation(
                "LEGACY_RELATION_VERIFIED",
                f"Relation {relation.relation_id} has origin='legacy' but status='{relation.verification_status}'",
            ))

        # Temporal gate check
        if relation.temporal_gate == TemporalGate.TEMPORALLY_INCOMPATIBLE:
            violations.append(ContractViolation(
                "TEMPORAL_INCOMPATIBILITY",
                f"Relation {relation.relation_id} has temporal_gate='temporally_incompatible'",
            ))

        return violations

    # ─── Scoring policy (AUTHORITY ≠ RELEVANCE) ───────────────────────────────

    @staticmethod
    def authority_relevance_gate(authority_tier: int, relevance_score: float) -> bool:
        """Determine if a source can produce evidence based on authority + relevance.

        AUTHORITY ≠ RELEVANCE: high authority + low relevance = NO evidence.
        This is a GATED policy, not a weighted average.
        """
        # Authority tier → max authority score
        authority_scores = {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.25}
        authority = authority_scores.get(authority_tier, 0.25)

        # Gate: if relevance is too low, authority cannot compensate
        if relevance_score < 0.1:
            return False  # Irrelevant source = no evidence, regardless of authority

        # Gate: if authority is too low AND relevance is moderate, still no evidence
        if authority < 0.3 and relevance_score < 0.7:
            return False

        # Gate: both must be at least moderate
        if authority * relevance_score < 0.15:
            return False

        return True

    # ─── Independence check ───────────────────────────────────────────────────

    @staticmethod
    def count_independent_lineages(evidence_items: List[EvidenceRef]) -> Tuple[int, int]:
        """Count evidence_count and independent_lineage_count.

        MULTIPLE SOURCES ≠ INDEPENDENT SOURCES.
        Same lineage = 1 independent source.
        """
        evidence_count = len(evidence_items)
        lineages = set()
        for e in evidence_items:
            if e.lineage_id:
                lineages.add(e.lineage_id)
            elif e.is_independent:
                lineages.add(f"ind_{e.evidence_id}")
        independent_lineage_count = len(lineages)
        return evidence_count, independent_lineage_count

    @staticmethod
    def independence_corroboration_bonus(evidence_items: List[EvidenceRef]) -> float:
        """Calculate corroboration bonus based on INDEPENDENT lineages only."""
        _, n_independent = EvidenceContract.count_independent_lineages(evidence_items)
        if n_independent <= 1:
            return 0.0
        # Logarithmic bonus: 2 independent = +0.1, 3 = +0.16, 4 = +0.2
        import math
        return min(0.2, 0.1 * math.log2(n_independent))

    # ─── Answer gate ──────────────────────────────────────────────────────────

    @staticmethod
    def build_answer_bundle(claims: List[ClaimRef],
                           sources: List[SourceRef],
                           conflicts: Optional[List[Dict]] = None,
                           gaps: Optional[List[Dict]] = None,
                           snapshot_id: str = "") -> AnswerEvidenceBundle:
        """Build an AnswerEvidenceBundle from claims, grouped by verification status.

        This is the ONLY structure the AI narrator should receive.
        """
        verified = [c for c in claims if c.verification_status == ClaimStatus.VERIFIED]
        probable = [c for c in claims if c.verification_status == ClaimStatus.PROBABLE]
        disputed = [c for c in claims if c.verification_status in ClaimStatus.CONFLICTED]
        unsupported = [c for c in claims if c.verification_status == ClaimStatus.UNSUPPORTED]
        rejected = [c for c in claims if c.verification_status == ClaimStatus.REJECTED]

        return AnswerEvidenceBundle(
            verified_claims=verified,
            probable_claims=probable,
            disputed_claims=disputed,
            unsupported_claims=unsupported,
            rejected_claims=rejected,
            sources=sources,
            conflicts=conflicts or [],
            gaps=gaps or [],
            snapshot_id=snapshot_id,
        )

    # ─── Full chain validation ────────────────────────────────────────────────

    @staticmethod
    def validate_chain(
        sources: List[SourceRef],
        observations: List[ObservationRef],
        evidence_items: List[EvidenceRef],
        claims: List[ClaimRef],
        relations: List[RelationRef],
    ) -> List[ContractViolation]:
        """Validate the entire evidence chain end-to-end."""
        violations: List[ContractViolation] = []

        # Build lookup maps
        source_map = {s.source_id: s for s in sources}
        obs_map = {o.observation_id: o for o in observations}
        evidence_map = {e.evidence_id: e for e in evidence_items}
        claim_map = {c.claim_id: c for c in claims}

        # Validate observations
        for obs in observations:
            src = source_map.get(obs.source_id)
            violations.extend(EvidenceContract.validate_observation(obs, src))

        # Validate evidence
        for ev in evidence_items:
            obs = obs_map.get(ev.observation_id)
            violations.extend(EvidenceContract.validate_evidence(ev, obs))

        # Validate claims
        for claim in claims:
            claim_evidence = [evidence_map[eid] for eid in claim.evidence_ids if eid in evidence_map]
            violations.extend(EvidenceContract.validate_claim(claim, claim_evidence))

        # Validate relations
        for rel in relations:
            rel_claims = [claim_map[cid] for cid in rel.claim_ids if cid in claim_map]
            violations.extend(EvidenceContract.validate_relation(rel, rel_claims))

        return violations

    # ─── Legacy quarantine check ──────────────────────────────────────────────

    @staticmethod
    def is_legacy_safe_for_verified(relation: RelationRef) -> bool:
        """Check if a legacy relation is safe to use as verified.

        Legacy relations MUST be revalidated through the V2 pipeline
        before they can be used as verified.
        """
        if relation.origin == RelationOrigin.LEGACY:
            return False
        if relation.origin == RelationOrigin.LEGACY_REVALIDATED and \
           relation.verification_status in ClaimStatus.SUPPORTED_OR_HIGHER:
            return True
        if relation.origin == RelationOrigin.V2 and \
           relation.verification_status in ClaimStatus.SUPPORTED_OR_HIGHER:
            return True
        return False
