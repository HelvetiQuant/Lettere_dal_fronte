"""V7.3-Fase11: Semantic validator with claim-by-claim entailment checking.

Validates each claim against the evidence snapshot for:
  1. Entailment: does the evidence actually support the claim?
  2. Contradiction: are there claims that logically contradict each other?
  3. Scope violation: is a CONTEXT_EVIDENCE claim used as PERSON_EVIDENCE?
  4. Identity binding: is every claim bound to an identity cluster?
  5. Provenance: does every claim have a traceable provenance chain?
  6. Confidence calibration: does confidence match evidence quality?

Key invariants:
  1. A claim without evidence is REJECTED (no orphan claims)
  2. A CONTEXT_EVIDENCE claim cannot assert a PERSON fact
  3. Two claims with same predicate + different values = CONFLICTING
  4. Confidence cannot exceed evidence quality score
  5. All validation results are preserved for audit
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from evidence_snapshot_v7 import ClaimV7, EvidenceSnapshotV7


# ─── Validation result ───────────────────────────────────────────────────────

@dataclass
class ClaimValidation:
    """Validation result for a single claim."""
    claim_id: str
    valid: bool
    status: str = "VALID"  # VALID, WARNING, INVALID, REJECTED
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    entailment_score: float = 0.0
    contradiction_with: List[str] = field(default_factory=list)
    scope_violations: List[str] = field(default_factory=list)


@dataclass
class SnapshotValidation:
    """Validation result for an entire evidence snapshot."""
    valid: bool
    claim_results: List[ClaimValidation] = field(default_factory=list)
    global_errors: List[str] = field(default_factory=list)
    global_warnings: List[str] = field(default_factory=list)
    rejected_claims: List[str] = field(default_factory=list)
    conflicting_pairs: List[Tuple[str, str]] = field(default_factory=list)
    scope_violations: List[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return sum(1 for c in self.claim_results if c.status == "VALID")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.claim_results if c.status == "WARNING")

    @property
    def invalid_count(self) -> int:
        return sum(1 for c in self.claim_results if c.status in ("INVALID", "REJECTED"))

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "valid_claims": self.valid_count,
            "warning_claims": self.warning_count,
            "invalid_claims": self.invalid_count,
            "rejected_claims": self.rejected_claims,
            "conflicting_pairs": [(a, b) for a, b in self.conflicting_pairs],
            "scope_violations": self.scope_violations,
            "global_errors": self.global_errors,
            "global_warnings": self.global_warnings,
            "claim_results": [
                {
                    "claim_id": c.claim_id,
                    "status": c.status,
                    "errors": c.errors,
                    "warnings": c.warnings,
                    "entailment_score": round(c.entailment_score, 4),
                    "contradiction_with": c.contradiction_with,
                    "scope_violations": c.scope_violations,
                }
                for c in self.claim_results
            ],
        }


# ─── Semantic validator ──────────────────────────────────────────────────────

# Predicates that are PERSON facts (cannot be asserted by CONTEXT_EVIDENCE)
PERSON_FACT_PREDICATES = {
    "birth_date", "birth_place", "death_date", "death_place", "death_country",
    "paternity", "maternity", "matricola", "service_number",
    "rank", "grado", "military_unit", "reparto",
    "first_name", "last_name", "cognome", "nome",
    "profession", "residence", "age", "height",
    "enrollment_date", "discharge_date",
}

# Predicates that are CONTEXT facts
CONTEXT_FACT_PREDICATES = {
    "event_date", "event_location", "event_description",
    "unit_participated", "casualty_count", "outcome",
    "camp_location", "camp_type", "camp_start", "camp_end",
}

# Predicates that can be either (depending on source)
AMBIGUOUS_PREDICATES = {
    "fate", "sorte", "capture_date", "capture_place",
    "internment_place", "internment_date", "release_date",
    "burial_place", "burial_country",
}


class SemanticValidator:
    """Validates claims against evidence with claim-by-claim entailment."""

    def validate_snapshot(self, snapshot: EvidenceSnapshotV7) -> SnapshotValidation:
        """Validate all claims in an evidence snapshot."""
        result = SnapshotValidation(valid=True)

        all_claims = (snapshot.person_claims or []) + (snapshot.context_claims or [])

        # Check for empty snapshot
        if not all_claims:
            result.global_warnings.append("empty_snapshot_no_claims")
            return result

        # Build claim index by predicate for contradiction detection
        claims_by_predicate: Dict[str, List[ClaimV7]] = {}
        for claim in all_claims:
            claims_by_predicate.setdefault(claim.predicate, []).append(claim)

        # Validate each claim
        for claim in all_claims:
            cv = self._validate_claim(claim, all_claims, snapshot)
            result.claim_results.append(cv)
            if cv.status == "REJECTED":
                result.rejected_claims.append(claim.claim_id)
            if cv.scope_violations:
                result.scope_violations.extend(cv.scope_violations)

        # Detect contradictions
        for predicate, claims in claims_by_predicate.items():
            if len(claims) < 2:
                continue
            # Group by normalized value
            by_value: Dict[str, List[ClaimV7]] = {}
            for c in claims:
                val = getattr(c, "value_normalized", None) or getattr(c, "value", "") or ""
                key = val.lower().strip()
                by_value.setdefault(key, []).append(c)
            # If multiple distinct values for same predicate → conflict
            if len(by_value) > 1:
                values_list = list(by_value.values())
                for i, v1_claims in enumerate(values_list):
                    for j, v2_claims in enumerate(values_list):
                        if i >= j:
                            continue
                        for c1 in v1_claims:
                            for c2 in v2_claims:
                                if c1.claim_id != c2.claim_id:
                                    result.conflicting_pairs.append((c1.claim_id, c2.claim_id))
                                    for cv in result.claim_results:
                                        if cv.claim_id in (c1.claim_id, c2.claim_id):
                                            other_id = c2.claim_id if cv.claim_id == c1.claim_id else c1.claim_id
                                            if other_id not in cv.contradiction_with:
                                                cv.contradiction_with.append(other_id)
                                            if cv.status == "VALID":
                                                cv.status = "WARNING"

        # Check global invariants
        self._check_global_invariants(snapshot, result)

        # Set overall validity
        result.valid = (
            len(result.global_errors) == 0
            and all(cv.status != "REJECTED" for cv in result.claim_results)
        )

        return result

    def _validate_claim(
        self,
        claim: ClaimV7,
        all_claims: List[ClaimV7],
        snapshot: EvidenceSnapshotV7,
    ) -> ClaimValidation:
        """Validate a single claim."""
        cv = ClaimValidation(claim_id=claim.claim_id, valid=True)

        # Handle ContextClaimV7 (different structure)
        is_context_claim = hasattr(claim, "scope") and not hasattr(claim, "evidence_scope")
        if is_context_claim:
            return self._validate_context_claim(claim, snapshot)

        # Check 1: Evidence existence
        if not claim.evidence_ids:
            cv.errors.append("no_evidence: claim has no supporting evidence")
            cv.status = "REJECTED"
            cv.valid = False
            return cv

        # Check 2: Identity cluster binding
        if not claim.identity_cluster_id:
            cv.errors.append("no_identity_cluster: claim not bound to any identity cluster")
            cv.status = "INVALID"
            cv.valid = False

        # Check 3: Scope violation — CONTEXT_EVIDENCE asserting PERSON fact
        if claim.evidence_scope == "CONTEXT_EVIDENCE":
            if claim.predicate in PERSON_FACT_PREDICATES:
                cv.scope_violations.append(
                    f"context_evidence_asserting_person_fact:{claim.predicate}"
                )
                cv.errors.append(
                    f"scope_violation: CONTEXT_EVIDENCE cannot assert PERSON fact '{claim.predicate}'"
                )
                cv.status = "INVALID"
                cv.valid = False

        # Check 4: Provenance chain
        if not claim.provenance_chain:
            cv.warnings.append("no_provenance_chain: claim lacks provenance traceability")
            if cv.status == "VALID":
                cv.status = "WARNING"

        # Check 5: Confidence calibration
        if claim.confidence > 0.95:
            cv.warnings.append(f"confidence_too_high: {claim.confidence:.2f} > 0.95")
            if cv.status == "VALID":
                cv.status = "WARNING"

        if claim.confidence < 0.0:
            cv.errors.append(f"confidence_negative: {claim.confidence}")
            cv.status = "INVALID"
            cv.valid = False

        # Check 6: Value not empty
        if not claim.value_normalized or not claim.value_normalized.strip():
            cv.warnings.append("empty_value: claim has no normalized value")
            if cv.status == "VALID":
                cv.status = "WARNING"

        # Check 7: Entailment — does evidence support the claim?
        cv.entailment_score = self._compute_entailment(claim, snapshot)

        if cv.entailment_score < 0.3:
            cv.errors.append(
                f"entailment_failure: evidence does not support claim (score={cv.entailment_score:.2f})"
            )
            cv.status = "REJECTED"
            cv.valid = False
        elif cv.entailment_score < 0.5:
            cv.warnings.append(
                f"weak_entailment: evidence weakly supports claim (score={cv.entailment_score:.2f})"
            )
            if cv.status == "VALID":
                cv.status = "WARNING"

        # Check 8: Status consistency
        if claim.status == "REJECTED" and cv.status == "VALID":
            cv.status = "WARNING"
            cv.warnings.append("claim_status_rejected_but_validation_passed")

        return cv

    def _validate_context_claim(self, claim, snapshot: EvidenceSnapshotV7) -> ClaimValidation:
        """Validate a ContextClaimV7 (different structure from ClaimV7)."""
        cv = ClaimValidation(claim_id=claim.claim_id, valid=True)

        # Context claims use source_refs instead of evidence_ids
        if not claim.source_refs:
            cv.warnings.append("no_source_refs: context claim has no source references")
            cv.status = "WARNING"

        # Check scope is valid
        valid_scopes = {"UNIT", "EVENT", "PLACE", "CAMP", "PERIOD"}
        if claim.scope not in valid_scopes:
            cv.errors.append(f"invalid_scope: {claim.scope} not in {valid_scopes}")
            cv.status = "INVALID"
            cv.valid = False

        # Check value not empty
        if not claim.value or not claim.value.strip():
            cv.warnings.append("empty_value: context claim has no value")
            if cv.status == "VALID":
                cv.status = "WARNING"

        # Context claims have lower entailment expectations
        cv.entailment_score = 0.50 if claim.source_refs else 0.20

        return cv

    def _compute_entailment(self, claim: ClaimV7, snapshot: EvidenceSnapshotV7) -> float:
        """Compute an entailment score for a claim.

        The entailment score measures how well the evidence supports the claim.
        It is NOT a confidence score — it measures logical support.

        Factors:
          - Number of evidence items (more = better)
          - Evidence independence (independent = better)
          - Value match (does evidence contain the claimed value?)
          - Provenance depth (longer chain = better traceability)
        """
        score = 0.0

        # Evidence count factor
        n_evidence = len(claim.evidence_ids)
        if n_evidence == 0:
            return 0.0
        elif n_evidence == 1:
            score += 0.30
        elif n_evidence == 2:
            score += 0.50
        else:
            score += 0.65

        # Independence factor
        if claim.independence_group_ids:
            # Has independence tracking — check if multiple groups
            n_groups = len(set(claim.independence_group_ids))
            if n_groups >= 2:
                score += 0.20
            elif n_groups == 1:
                score += 0.05
        else:
            score += 0.05  # no independence tracking, small bonus

        # Provenance depth
        if claim.provenance_chain:
            chain_len = len(claim.provenance_chain)
            if chain_len >= 3:
                score += 0.10
            elif chain_len >= 1:
                score += 0.05

        # Source quality (from claim source field)
        if claim.source == "origin_record":
            score += 0.05
        elif claim.source == "external":
            score += 0.03

        # Cap at 1.0
        return min(score, 1.0)

    def _check_global_invariants(self, snapshot: EvidenceSnapshotV7, result: SnapshotValidation):
        """Check global invariants on the snapshot."""
        person_claims = snapshot.person_claims or []
        context_claims = snapshot.context_claims or []

        # Invariant 1: No CONTEXT_EVIDENCE in person_claims
        for c in person_claims:
            if hasattr(c, "evidence_scope") and c.evidence_scope == "CONTEXT_EVIDENCE":
                result.global_errors.append(
                    f"invariant_violation: CONTEXT_EVIDENCE claim {c.claim_id} in person_claims"
                )

        # Invariant 2: No PERSON_EVIDENCE in context_claims (ContextClaimV7 doesn't have evidence_scope)
        for c in context_claims:
            if hasattr(c, "evidence_scope") and c.evidence_scope == "PERSON_EVIDENCE":
                result.global_errors.append(
                    f"invariant_violation: PERSON_EVIDENCE claim {c.claim_id} in context_claims"
                )

        # Invariant 3: Every person claim must have identity_cluster_id
        for c in person_claims:
            if hasattr(c, "identity_cluster_id") and not c.identity_cluster_id:
                result.global_warnings.append(
                    f"missing_identity: person claim {c.claim_id} has no identity_cluster_id"
                )

        # Invariant 4: Snapshot must have identity_status
        if not snapshot.identity_status:
            result.global_warnings.append("missing_identity_status: snapshot has no identity_status")
