"""V7.3-Fase12: Claim states and publishability — 4 separate states.

Defines 4 claim states that are SEPARATE from:
  - identity_status (ANCHORED_RECORD, RESOLVED_IDENTITY, etc.)
  - evidence_level (verified, probable, possible, unverified)
  - validation_status (VALID, WARNING, INVALID, REJECTED)

The 4 claim states are:
  1. PUBLISHED — claim can appear in final output without caveat
  2. PUBLISHED_WITH_CAVEAT — claim can appear but must carry a caveat
  3. REVIEW_PENDING — claim cannot appear in output, awaits human review
  4. SUPPRESSED — claim cannot appear in output, suppressed by rules

Key invariants:
  1. Publishability is determined by evidence quality + validation + identity
  2. A claim from an UNRESOLVED_IDENTITY is always REVIEW_PENDING
  3. A claim with scope violation is always SUPPRESSED
  4. A claim with weak entailment is REVIEW_PENDING
  5. PUBLISHED_WITH_CAVEAT must include the caveat text
  6. State transitions are append-only (audit trail)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ─── Claim publishability states ─────────────────────────────────────────────

CLAIM_STATES = [
    "PUBLISHED",
    "PUBLISHED_WITH_CAVEAT",
    "REVIEW_PENDING",
    "SUPPRESSED",
]

# State ordering (higher = more publishable)
STATE_RANK = {
    "PUBLISHED": 4,
    "PUBLISHED_WITH_CAVEAT": 3,
    "REVIEW_PENDING": 2,
    "SUPPRESSED": 1,
}


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class ClaimState:
    """The publishability state of a claim."""
    claim_id: str
    state: str = "REVIEW_PENDING"
    caveat: str = ""
    reason: str = ""
    determined_by: str = ""  # "rules" | "validator" | "human_review"
    transition_chain: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_publishable(self) -> bool:
        return self.state in ("PUBLISHED", "PUBLISHED_WITH_CAVEAT")

    @property
    def requires_caveat(self) -> bool:
        return self.state == "PUBLISHED_WITH_CAVEAT"

    @property
    def is_suppressed(self) -> bool:
        return self.state == "SUPPRESSED"

    def transition_to(self, new_state: str, reason: str, actor: str = "rules"):
        """Append-only state transition."""
        if new_state not in CLAIM_STATES:
            raise ValueError(f"Invalid claim state: {new_state}")
        old_state = self.state
        self.transition_chain.append({
            "from": old_state,
            "to": new_state,
            "reason": reason,
            "actor": actor,
        })
        self.state = new_state
        self.reason = reason
        self.determined_by = actor

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "state": self.state,
            "caveat": self.caveat,
            "reason": self.reason,
            "determined_by": self.determined_by,
            "is_publishable": self.is_publishable,
            "requires_caveat": self.requires_caveat,
            "is_suppressed": self.is_suppressed,
            "transition_chain": self.transition_chain,
        }


# ─── Publishability rules ────────────────────────────────────────────────────

# Minimum evidence level for each state
EVIDENCE_LEVEL_TO_STATE = {
    "verified": "PUBLISHED",
    "probable": "PUBLISHED_WITH_CAVEAT",
    "possible": "REVIEW_PENDING",
    "unverified": "REVIEW_PENDING",
    "conflicting": "REVIEW_PENDING",
}

# Identity status → claim state constraint
IDENTITY_STATUS_CONSTRAINT = {
    "ANCHORED_RECORD": None,       # no constraint (best)
    "RESOLVED_IDENTITY": None,     # no constraint
    "CONFLICTED_IDENTITY": "PUBLISHED_WITH_CAVEAT",  # must carry caveat
    "AMBIGUOUS_IDENTITY": "REVIEW_PENDING",           # cannot publish
    "PARTIAL_IDENTITY": "PUBLISHED_WITH_CAVEAT",      # must carry caveat
    "UNRESOLVED_IDENTITY": "REVIEW_PENDING",          # cannot publish
}

# Validation status → claim state constraint
VALIDATION_STATUS_CONSTRAINT = {
    "VALID": None,                 # no constraint
    "WARNING": "PUBLISHED_WITH_CAVEAT",  # must carry caveat
    "INVALID": "SUPPRESSED",
    "REJECTED": "SUPPRESSED",
}

# Caveat templates
CAVEAT_TEMPLATES = {
    "conflicted_identity": "Dati attribuiti a identità con conflitti non risolti.",
    "partial_identity": "Identità parzialmente risolta. Verifica necessaria.",
    "weak_entailment": "Evidenza di supporto limitata per questa affermazione.",
    "single_source": "Affermazione basata su una sola fonte. Corroborazione necessaria.",
    "validation_warning": "Validazione semantica ha segnalato avvertenze.",
    "context_evidence_only": "Affermazione basata su evidenza contestuale, non diretta.",
    "ocr_uncertainty": "Valore estratto via OCR con incertezza residua.",
}


def determine_claim_state(
    claim_id: str,
    evidence_level: str = "unverified",
    identity_status: str = "UNRESOLVED_IDENTITY",
    validation_status: str = "VALID",
    has_scope_violation: bool = False,
    entailment_score: float = 0.0,
    source_count: int = 0,
    is_context_only: bool = False,
    has_ocr_uncertainty: bool = False,
) -> ClaimState:
    """Determine the publishability state of a claim.

    Applies rules in priority order:
      1. Scope violation → SUPPRESSED (absolute)
      2. Validation INVALID/REJECTED → SUPPRESSED (absolute)
      3. Identity status constraint
      4. Evidence level mapping
      5. Validation WARNING → caveat
      6. Additional caveats (single source, OCR, context-only)

    The most restrictive constraint wins.
    """
    state = ClaimState(claim_id=claim_id, state="REVIEW_PENDING")
    caveats: List[str] = []
    reasons: List[str] = []

    # Rule 1: Scope violation → absolute suppression
    if has_scope_violation:
        state.transition_to("SUPPRESSED", "scope_violation", "rules")
        return state

    # Rule 2: Validation INVALID/REJECTED → absolute suppression
    val_constraint = VALIDATION_STATUS_CONSTRAINT.get(validation_status)
    if val_constraint == "SUPPRESSED":
        state.transition_to("SUPPRESSED", f"validation_{validation_status}", "validator")
        return state

    # Start from evidence level
    base_state = EVIDENCE_LEVEL_TO_STATE.get(evidence_level, "REVIEW_PENDING")
    state.transition_to(base_state, f"evidence_level:{evidence_level}", "rules")

    # Rule 3: Identity status constraint (may downgrade)
    id_constraint = IDENTITY_STATUS_CONSTRAINT.get(identity_status)
    if id_constraint:
        if STATE_RANK.get(id_constraint, 0) < STATE_RANK.get(state.state, 0):
            state.transition_to(id_constraint, f"identity:{identity_status}", "rules")
            if id_constraint == "PUBLISHED_WITH_CAVEAT":
                caveat_key = "conflicted_identity" if identity_status == "CONFLICTED_IDENTITY" else "partial_identity"
                caveats.append(CAVEAT_TEMPLATES.get(caveat_key, ""))
                reasons.append(f"identity_constraint:{identity_status}")

    # Rule 4: Validation warning → caveat
    if validation_status == "WARNING":
        if state.state == "PUBLISHED":
            state.transition_to("PUBLISHED_WITH_CAVEAT", "validation_warning", "validator")
        caveats.append(CAVEAT_TEMPLATES["validation_warning"])
        reasons.append("validation_warning")

    # Rule 5: Weak entailment → downgrade
    if entailment_score < 0.5 and state.state == "PUBLISHED":
        state.transition_to("PUBLISHED_WITH_CAVEAT", "weak_entailment", "rules")
        caveats.append(CAVEAT_TEMPLATES["weak_entailment"])
        reasons.append(f"entailment_score:{entailment_score:.2f}")

    # Rule 6: Single source → caveat
    if source_count <= 1 and state.is_publishable:
        if state.state == "PUBLISHED":
            state.transition_to("PUBLISHED_WITH_CAVEAT", "single_source", "rules")
        caveats.append(CAVEAT_TEMPLATES["single_source"])
        reasons.append("single_source")

    # Rule 7: Context-only evidence → caveat
    if is_context_only and state.is_publishable:
        if state.state == "PUBLISHED":
            state.transition_to("PUBLISHED_WITH_CAVEAT", "context_evidence_only", "rules")
        caveats.append(CAVEAT_TEMPLATES["context_evidence_only"])
        reasons.append("context_evidence_only")

    # Rule 8: OCR uncertainty → caveat
    if has_ocr_uncertainty and state.is_publishable:
        if state.state == "PUBLISHED":
            state.transition_to("PUBLISHED_WITH_CAVEAT", "ocr_uncertainty", "rules")
        caveats.append(CAVEAT_TEMPLATES["ocr_uncertainty"])
        reasons.append("ocr_uncertainty")

    # Set caveat text
    state.caveat = " ".join(c for c in caveats if c).strip()
    state.reason = "; ".join(reasons) if reasons else state.reason

    return state


def filter_publishable_claims(states: List[ClaimState]) -> Tuple[List[ClaimState], List[ClaimState]]:
    """Split claims into publishable and non-publishable.

    Returns:
        (publishable, non_publishable)
    """
    publishable = [s for s in states if s.is_publishable]
    non_publishable = [s for s in states if not s.is_publishable]
    return publishable, non_publishable


def build_caveat_summary(states: List[ClaimState]) -> str:
    """Build a human-readable summary of all caveats for published claims."""
    caveats = [s.caveat for s in states if s.requires_caveat and s.caveat]
    if not caveats:
        return ""
    unique = list(dict.fromkeys(caveats))  # preserve order, deduplicate
    return " ".join(unique)
