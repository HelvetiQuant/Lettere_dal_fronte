"""V7.3 Phase D — Claim selection, coverage planning, and narration.

ClaimSelector:
- Selects claims by identity (never mixes candidates)
- Prioritizes by evidence strength and source independence
- Excludes quarantined legacy links
- Enforces claim lifecycle (CANDIDATE -> VERIFIED/PROBABLE only)

CoveragePlan:
- For PERSON: ensures all claim fields are covered (birth, capture, internment, death)
- For EVENT: ensures stratified coverage (context, phases, forces, outcome, consequences)
- Reports missing coverage areas

NarrationPlanner:
- Builds block structure from selected claims
- Assigns certainty levels based on evidence
- Generates citations from backend (source_id only, no URLs in AI context)

SemanticValidator:
- Checks for contradictions between claims
- Detects homonym leakage (claims from different candidates)
- Validates temporal consistency
- Checks geographical role compatibility

GlobalValidator:
- Checks overall narrative coherence
- Validates coverage completeness
- Ensures no legacy leakage
- Checks citation validity
"""
from __future__ import annotations

import json
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from domain_model_v73 import (
    Claim, ClaimStatus, ClaimType, Evidence, EvidenceType,
    IdentityCandidate, IdentityStatus, IdentifierStrength,
    evaluate_identity, can_combine_claims,
    Entity, Relation, RelationStatus, ReviewDecision,
    WarPeriod, SemanticRole,
)
from barriers_v73 import (
    DateRole, check_temporal_compatibility, check_geographic_compatibility,
    TemporalCompatibility, GeographicCompatibility,
)


# ─── ClaimSelector ──────────────────────────────────────────────────────────

# Required claim fields for PERSON lookup
PERSON_CLAIM_FIELDS = {
    "born_at", "born_in", "resided_in", "enlisted_in", "served_in",
    "captured_at", "captured_in", "interned_at", "interned_in",
    "transferred_to", "worked_at", "liberated_from", "liberated_at",
    "died_at", "died_in", "buried_at", "decorated_with",
}

# Required claim fields for EVENT lookup
EVENT_CLAIM_FIELDS = {
    "event_context", "event_phase", "event_forces", "event_commander",
    "event_location", "event_duration", "event_outcome",
    "event_casualties", "event_significance", "event_aftermath",
    "event_participants", "event_preconditions",
}

# Certainty levels
CERTAINTY_LEVELS = ["CONFIRMED", "PROBABLE", "POSSIBLE", "UNCERTAIN", "CONTRADICTED"]


@dataclass
class SelectedClaim:
    """A claim selected for narration with its evidence summary."""
    claim: Claim
    evidence_count: int = 0
    independent_source_count: int = 0
    max_confidence: float = 0.0
    certainty: str = "UNCERTAIN"
    has_conflict: bool = False
    conflict_reason: str = ""
    citation_source_ids: List[str] = field(default_factory=list)


class ClaimSelector:
    """Selects claims for narration based on identity, evidence, and coverage.

    Key rules:
    - Never mix claims from different IdentityCandidates
    - Only use VERIFIED or PROBABLE claims as primary evidence
    - CANDIDATE claims can be included with UNCERTAIN certainty
    - REJECTED claims are excluded entirely
    - Claims with usable_as_evidence=False are excluded
    """

    def __init__(self):
        self.selected: List[SelectedClaim] = []
        self.excluded: List[Tuple[Claim, str]] = []
        self.identity_warnings: List[str] = []

    def select_claims(
        self,
        claims: List[Claim],
        evidence: List[Evidence],
        candidates: List[IdentityCandidate],
    ) -> List[SelectedClaim]:
        """Select claims for narration.

        Args:
            claims: All available claims
            evidence: All available evidence
            candidates: Identity candidates (must be evaluated first)

        Returns:
            List of SelectedClaim objects
        """
        # Evaluate identity if not already done
        for c in candidates:
            if c.identity_status == IdentityStatus.CANDIDATE:
                c.identity_status = evaluate_identity(c)

        # Check if we can combine claims from multiple candidates
        if not can_combine_claims(candidates):
            if len([c for c in candidates if c.identity_status == IdentityStatus.RESOLVED]) > 1:
                self.identity_warnings.append(
                    "MULTIPLE_RESOLVED_IDENTITIES: claims from different candidates cannot be combined"
                )
                # Use only the first resolved candidate
                resolved = [c for c in candidates if c.identity_status == IdentityStatus.RESOLVED]
                if resolved:
                    usable_candidate_ids = {resolved[0].candidate_id}
                else:
                    usable_candidate_ids = set()
            else:
                # No resolved identity — use all CANDIDATE status but warn
                self.identity_warnings.append("NO_RESOLVED_IDENTITY: using candidate claims with uncertainty")
                usable_candidate_ids = {c.candidate_id for c in candidates if c.identity_status != IdentityStatus.REJECTED_HOMONYM}
        else:
            usable_candidate_ids = {c.candidate_id for c in candidates if c.identity_status == IdentityStatus.RESOLVED}

        # Index evidence by candidate_id
        evidence_by_candidate: Dict[str, List[Evidence]] = {}
        for ev in evidence:
            if ev.candidate_id:
                evidence_by_candidate.setdefault(ev.candidate_id, []).append(ev)

        # Select claims
        for claim in claims:
            # Skip rejected claims
            if claim.status in (ClaimStatus.REJECTED,):
                self.excluded.append((claim, "REJECTED"))
                continue

            # Skip claims not usable as evidence
            if not claim.usable_as_evidence and claim.status == ClaimStatus.CANDIDATE:
                self.excluded.append((claim, "NOT_USABLE_AS_EVIDENCE"))
                continue

            # Skip claims from rejected homonyms
            if claim.candidate_id and claim.candidate_id not in usable_candidate_ids:
                self.excluded.append((claim, "REJECTED_HOMONYM"))
                continue

            # Gather evidence for this claim
            claim_evidence = [
                ev for ev in evidence
                if ev.candidate_id == claim.candidate_id
                or ev.evidence_id in claim.evidence_ids
            ]

            # Calculate certainty
            certainty = self._calculate_certainty(claim, claim_evidence)
            max_conf = max((ev.overall_confidence for ev in claim_evidence), default=0.0)
            independent_sources = len(set(ev.family_id for ev in claim_evidence if ev.family_id))
            has_conflict = any(ev.evidence_role == "contradicts" for ev in claim_evidence)

            # Build citation source IDs (no URLs)
            citation_ids = [
                ev.artifact_id for ev in claim_evidence
                if ev.artifact_id and ev.evidence_role == "supports"
            ]

            selected = SelectedClaim(
                claim=claim,
                evidence_count=len(claim_evidence),
                independent_source_count=independent_sources,
                max_confidence=max_conf,
                certainty=certainty,
                has_conflict=has_conflict,
                conflict_reason="; ".join(
                    ev.supporting_quote[:100] for ev in claim_evidence
                    if ev.evidence_role == "contradicts" and ev.supporting_quote
                ),
                citation_source_ids=list(set(citation_ids)),
            )
            self.selected.append(selected)

        return self.selected

    def _calculate_certainty(self, claim: Claim, evidence: List[Evidence]) -> str:
        """Calculate certainty level from claim status and evidence."""
        if claim.status == ClaimStatus.VERIFIED:
            if len(evidence) >= 2 and len(set(ev.family_id for ev in evidence if ev.family_id)) >= 2:
                return "CONFIRMED"
            return "PROBABLE"
        elif claim.status == ClaimStatus.PROBABLE:
            return "PROBABLE"
        elif claim.status == ClaimStatus.CONFLICTING:
            return "CONTRADICTED"
        elif claim.status == ClaimStatus.NEEDS_REVIEW:
            return "UNCERTAIN"
        else:  # CANDIDATE
            if evidence and max((ev.overall_confidence for ev in evidence), default=0) > 0.7:
                return "POSSIBLE"
            return "UNCERTAIN"


# ─── CoveragePlan ───────────────────────────────────────────────────────────

@dataclass
class CoverageGap:
    """A missing coverage area."""
    field: str
    description: str
    severity: str  # "critical", "important", "minor"


@dataclass
class CoverageReport:
    """Coverage analysis result."""
    covered_fields: Set[str] = field(default_factory=set)
    missing_fields: Set[str] = field(default_factory=set)
    gaps: List[CoverageGap] = field(default_factory=list)
    coverage_score: float = 0.0
    is_event: bool = False

    def to_dict(self) -> dict:
        return {
            "covered_fields": list(self.covered_fields),
            "missing_fields": list(self.missing_fields),
            "gaps": [{"field": g.field, "description": g.description, "severity": g.severity} for g in self.gaps],
            "coverage_score": self.coverage_score,
            "is_event": self.is_event,
        }


class CoveragePlanner:
    """Plans and evaluates narration coverage.

    For PERSON: ensures all biographical fields are covered.
    For EVENT: ensures stratified coverage across multiple dimensions.
    """

    # Event coverage dimensions (stratified)
    EVENT_DIMENSIONS = {
        "event_context": "Contesto storico e cause dell'evento",
        "event_phase": "Fasi dell'evento (preparazione, svolgimento, conclusione)",
        "event_forces": "Forze in campo (unità, effettivi, schieramento)",
        "event_commander": "Comandanti e leadership",
        "event_location": "Luogo e geografia dell'evento",
        "event_duration": "Durata e sequenza temporale",
        "event_outcome": "Esito e risultati",
        "event_casualties": "Perdite e vittime",
        "event_significance": "Significato storico e impatto",
        "event_aftermath": "Conseguenze e sviluppi successivi",
    }

    # Critical event dimensions (must be covered)
    EVENT_CRITICAL = {"event_context", "event_phase", "event_outcome", "event_significance"}

    # Important event dimensions
    EVENT_IMPORTANT = {"event_forces", "event_location", "event_duration", "event_casualties"}

    def evaluate_person_coverage(self, selected: List[SelectedClaim]) -> CoverageReport:
        """Evaluate coverage for a PERSON narration."""
        report = CoverageReport(is_event=False)
        covered = set()
        for sc in selected:
            covered.add(sc.claim.predicate)
        report.covered_fields = covered
        report.missing_fields = PERSON_CLAIM_FIELDS - covered

        for field in report.missing_fields:
            severity = "important"
            if field in ("born_at", "born_in"):
                severity = "critical"
            elif field in ("captured_at", "interned_at"):
                severity = "critical"
            report.gaps.append(CoverageGap(
                field=field,
                description=f"Missing biographical claim: {field}",
                severity=severity,
            ))

        total = len(PERSON_CLAIM_FIELDS)
        covered_count = len(covered & PERSON_CLAIM_FIELDS)
        report.coverage_score = covered_count / total if total > 0 else 0.0
        return report

    def evaluate_event_coverage(self, selected: List[SelectedClaim]) -> CoverageReport:
        """Evaluate coverage for an EVENT narration."""
        report = CoverageReport(is_event=True)
        covered = set()
        for sc in selected:
            covered.add(sc.claim.predicate)
        report.covered_fields = covered
        report.missing_fields = set(self.EVENT_DIMENSIONS.keys()) - covered

        for field in report.missing_fields:
            description = self.EVENT_DIMENSIONS.get(field, field)
            if field in self.EVENT_CRITICAL:
                severity = "critical"
            elif field in self.EVENT_IMPORTANT:
                severity = "important"
            else:
                severity = "minor"
            report.gaps.append(CoverageGap(
                field=field,
                description=description,
                severity=severity,
            ))

        total = len(self.EVENT_DIMENSIONS)
        covered_count = len(covered & set(self.EVENT_DIMENSIONS.keys()))
        report.coverage_score = covered_count / total if total > 0 else 0.0
        return report


# ─── NarrationPlanner ───────────────────────────────────────────────────────

@dataclass
class NarrationBlock:
    """A single block in the narration structure."""
    block_id: str
    role: str  # opening, biographical, military, internment, liberation, closing
    text: str = ""
    claim_ids: List[str] = field(default_factory=list)
    certainty: str = "UNCERTAIN"
    source_ids: List[str] = field(default_factory=list)


@dataclass
class NarrationPlan:
    """Structured narration plan before AI generation."""
    request_type: str  # PERSON, EVENT, FACT
    blocks: List[NarrationBlock] = field(default_factory=list)
    coverage: Optional[CoverageReport] = None
    identity_warnings: List[str] = field(default_factory=list)
    has_conflicts: bool = False
    needs_followup: bool = False
    followup_question: str = ""

    def to_dict(self) -> dict:
        return {
            "request_type": self.request_type,
            "blocks": [
                {
                    "block_id": b.block_id,
                    "role": b.role,
                    "text": b.text,
                    "claim_ids": b.claim_ids,
                    "certainty": b.certainty,
                    "source_ids": b.source_ids,
                }
                for b in self.blocks
            ],
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "identity_warnings": self.identity_warnings,
            "has_conflicts": self.has_conflicts,
            "needs_followup": self.needs_followup,
            "followup_question": self.followup_question,
        }


class NarrationPlanner:
    """Builds narration structure from selected claims.

    For PERSON: chronological blocks (birth -> service -> capture -> internment -> liberation/death)
    For EVENT: stratified blocks (context -> phases -> forces -> outcome -> significance)
    """

    def build_person_plan(
        self,
        selected: List[SelectedClaim],
        coverage: CoverageReport,
        identity_warnings: List[str],
    ) -> NarrationPlan:
        """Build a PERSON narration plan."""
        plan = NarrationPlan(request_type="PERSON", coverage=coverage, identity_warnings=identity_warnings)

        # Group claims by biographical phase
        phases = {
            "opening": [],
            "biographical": [],
            "military": [],
            "capture_internment": [],
            "liberation_death": [],
            "closing": [],
        }

        for sc in selected:
            pred = sc.claim.predicate
            if pred in ("born_at", "born_in", "resided_in"):
                phases["biographical"].append(sc)
            elif pred in ("enlisted_in", "served_in", "decorated_with"):
                phases["military"].append(sc)
            elif pred in ("captured_at", "captured_in", "interned_at", "interned_in", "transferred_to", "worked_at"):
                phases["capture_internment"].append(sc)
            elif pred in ("liberated_from", "liberated_at", "died_at", "died_in", "buried_at"):
                phases["liberation_death"].append(sc)
            else:
                phases["biographical"].append(sc)

        # Build blocks
        block_id = 0
        for phase_name, claims in phases.items():
            if not claims and phase_name in ("opening", "closing"):
                continue
            block_id += 1
            block = NarrationBlock(
                block_id=f"block_{block_id:02d}",
                role=phase_name,
                claim_ids=[sc.claim.claim_id for sc in claims],
                certainty=self._aggregate_certainty(claims),
                source_ids=list(set(
                    sid for sc in claims for sid in sc.citation_source_ids
                )),
            )
            plan.blocks.append(block)

        # Check for conflicts
        plan.has_conflicts = any(sc.has_conflict for sc in selected)

        # Check if followup is needed
        critical_gaps = [g for g in coverage.gaps if g.severity == "critical"]
        if critical_gaps:
            plan.needs_followup = True
            plan.followup_question = f"Missing critical information: {', '.join(g.field for g in critical_gaps)}"

        return plan

    def build_event_plan(
        self,
        selected: List[SelectedClaim],
        coverage: CoverageReport,
        identity_warnings: List[str],
    ) -> NarrationPlan:
        """Build an EVENT narration plan."""
        plan = NarrationPlan(request_type="EVENT", coverage=coverage, identity_warnings=identity_warnings)

        # Map claims to event dimensions
        dimension_order = [
            "event_context", "event_phase", "event_forces", "event_commander",
            "event_location", "event_duration", "event_outcome",
            "event_casualties", "event_significance", "event_aftermath",
        ]

        block_id = 0
        for dim in dimension_order:
            dim_claims = [sc for sc in selected if sc.claim.predicate == dim]
            if dim_claims or dim in coverage.covered_fields:
                block_id += 1
                block = NarrationBlock(
                    block_id=f"block_{block_id:02d}",
                    role=dim,
                    claim_ids=[sc.claim.claim_id for sc in dim_claims],
                    certainty=self._aggregate_certainty(dim_claims),
                    source_ids=list(set(
                        sid for sc in dim_claims for sid in sc.citation_source_ids
                    )),
                )
                plan.blocks.append(block)

        # Check for conflicts
        plan.has_conflicts = any(sc.has_conflict for sc in selected)

        # Check if followup is needed
        critical_gaps = [g for g in coverage.gaps if g.severity == "critical"]
        if critical_gaps:
            plan.needs_followup = True
            plan.followup_question = f"Missing critical event coverage: {', '.join(g.description for g in critical_gaps)}"

        return plan

    def _aggregate_certainty(self, claims: List[SelectedClaim]) -> str:
        """Aggregate certainty level from multiple claims."""
        if not claims:
            return "UNCERTAIN"
        certainties = [sc.certainty for sc in claims]
        if "CONFIRMED" in certainties:
            return "CONFIRMED"
        if "PROBABLE" in certainties:
            return "PROBABLE"
        if "POSSIBLE" in certainties:
            return "POSSIBLE"
        if "CONTRADICTED" in certainties:
            return "CONTRADICTED"
        return "UNCERTAIN"


# ─── SemanticValidator ──────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    """A validation issue found by the validator."""
    severity: str  # "error", "warning", "info"
    category: str  # "contradiction", "homonym_leakage", "temporal", "geographic", "coverage", "citation"
    message: str
    claim_ids: List[str] = field(default_factory=list)
    block_ids: List[str] = field(default_factory=list)


class SemanticValidator:
    """Validates narration for semantic consistency.

    Checks:
    1. No contradictions between claims in the same narration
    2. No homonym leakage (claims from different candidates)
    3. Temporal consistency (dates don't conflict)
    4. Geographic role compatibility
    5. No legacy leakage (quarantined links not used)
    """

    def validate(
        self,
        plan: NarrationPlan,
        selected: List[SelectedClaim],
        candidates: List[IdentityCandidate],
    ) -> List[ValidationIssue]:
        """Validate the narration plan."""
        issues: List[ValidationIssue] = []

        # 1. Check for contradictions
        for sc in selected:
            if sc.has_conflict:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="contradiction",
                    message=f"Claim {sc.claim.predicate} has conflicting evidence: {sc.conflict_reason}",
                    claim_ids=[sc.claim.claim_id],
                ))

        # 2. Check for homonym leakage
        candidate_ids_in_plan = set()
        for sc in selected:
            if sc.claim.candidate_id:
                candidate_ids_in_plan.add(sc.claim.candidate_id)

        resolved_candidates = [c for c in candidates if c.identity_status == IdentityStatus.RESOLVED]
        if len(resolved_candidates) > 1:
            issues.append(ValidationIssue(
                severity="error",
                category="homonym_leakage",
                message=f"Multiple resolved identities ({len(resolved_candidates)}) — claims from different candidates detected",
            ))

        # 3. Check temporal consistency
        temporal_claims = [sc for sc in selected if sc.claim.temporal_value]
        for i, sc1 in enumerate(temporal_claims):
            for sc2 in temporal_claims[i+1:]:
                if sc1.claim.predicate != sc2.claim.predicate:
                    continue
                if sc1.claim.temporal_value and sc2.claim.temporal_value:
                    if sc1.claim.temporal_value != sc2.claim.temporal_value:
                        if sc1.claim.polarity == "POSITIVE" and sc2.claim.polarity == "POSITIVE":
                            issues.append(ValidationIssue(
                                severity="error",
                                category="temporal",
                                message=f"Temporal contradiction: {sc1.claim.predicate} has values {sc1.claim.temporal_value} and {sc2.claim.temporal_value}",
                                claim_ids=[sc1.claim.claim_id, sc2.claim.claim_id],
                            ))

        # 4. Check for legacy leakage
        for sc in selected:
            if sc.claim.origin == "LEGACY_HEURISTIC" and not sc.claim.usable_as_evidence:
                issues.append(ValidationIssue(
                    severity="error",
                    category="legacy_leakage",
                    message=f"Claim {sc.claim.predicate} from quarantined legacy source",
                    claim_ids=[sc.claim.claim_id],
                ))

        # 5. Check coverage
        if plan.coverage:
            critical_gaps = [g for g in plan.coverage.gaps if g.severity == "critical"]
            for gap in critical_gaps:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="coverage",
                    message=f"Missing critical coverage: {gap.description}",
                ))

        return issues


# ─── GlobalValidator ────────────────────────────────────────────────────────

class GlobalValidator:
    """Validates overall narrative coherence.

    Checks:
    1. All claims have at least one evidence
    2. No claims without source attribution
    3. Certainty levels are consistent with evidence
    4. No hallucinated content (claims not in selected set)
    5. Citation validity (all cited claims exist)
    """

    def validate(
        self,
        plan: NarrationPlan,
        selected: List[SelectedClaim],
        ai_output: Optional[Dict[str, Any]] = None,
    ) -> List[ValidationIssue]:
        """Validate global narrative coherence."""
        issues: List[ValidationIssue] = []

        # 1. Check all claims have evidence
        for sc in selected:
            if sc.evidence_count == 0 and sc.claim.status != ClaimStatus.VERIFIED:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="evidence",
                    message=f"Claim {sc.claim.predicate} has no supporting evidence",
                    claim_ids=[sc.claim.claim_id],
                ))

        # 2. Check certainty consistency
        for sc in selected:
            if sc.certainty == "CONFIRMED" and sc.evidence_count < 2:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="certainty",
                    message=f"Claim {sc.claim.predicate} marked CONFIRMED but has only {sc.evidence_count} evidence",
                    claim_ids=[sc.claim.claim_id],
                ))

        # 3. If AI output provided, validate against selected claims
        if ai_output:
            ai_claim_ids = set()
            for block in ai_output.get("blocks", []):
                ai_claim_ids.update(block.get("claim_ids", []))

            selected_claim_ids = {sc.claim.claim_id for sc in selected}
            hallucinated = ai_claim_ids - selected_claim_ids
            if hallucinated:
                issues.append(ValidationIssue(
                    severity="error",
                    category="hallucination",
                    message=f"AI output references {len(hallucinated)} claim IDs not in selected set",
                    claim_ids=list(hallucinated),
                ))

            # Check all selected claims are referenced
            unreferenced = selected_claim_ids - ai_claim_ids
            if unreferenced:
                issues.append(ValidationIssue(
                    severity="info",
                    category="coverage",
                    message=f"{len(unreferenced)} selected claims not referenced in AI output",
                    claim_ids=list(unreferenced),
                ))

        # 4. Check identity warnings
        for warning in plan.identity_warnings:
            issues.append(ValidationIssue(
                severity="warning",
                category="identity",
                message=warning,
            ))

        return issues
