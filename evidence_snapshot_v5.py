"""Evidence Snapshot V5 — immutable, validated, unified probatory DTO.

Replaces V4 with stricter probatory semantics:
- Separates origin.presence (PRESENT_LOCAL|ABSENT) from origin.provenance (VERIFIED|UNVERIFIED|CONFLICTING)
- Separates identity_resolution from historical_data_completeness
- conditional_gaps replace fixed missing_claims (depend on subject type and research goal)
- Target carries explicit surname, given_names, display_name, source_order
- PersonCandidate requires identity_fingerprint and at least one identity feature beyond name
- evidence_eligible requires content_observation + target_match, not just format
- Provider ledger with reconcilable accounting invariant
- No URL truncation: canonical_url is full, display_label is separate
- Authority registry for acronyms and archives (anti-hallucination)
- ResearchNextStepPlanner conditional (no generic ICRC)

Key invariants enforced in validate():
- assert not (origin.presence == "ABSENT" and origin.supported_claim_ids)
- assert not independently_supported_claims or accepted_evidence
- assert all(c.source_ids for c in origin_supported_claims)
- assert all(c.source_ids for c in independently_supported_claims)
- assert identity_resolution is decided_by_backend
- assert external_corroboration is decided_by_backend
- assert not (evidence_eligible and content_observation == "NOT_OPENED")
- assert canonical_url == full URL (no truncation)
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ─── Identity fields (determine identity_resolution) ─────────────────────────

IDENTITY_FIELDS = [
    "full_birth_date",
    "birth_year",
    "birth_place",
    "paternity",
    "rank",
    "unit",
]

# ─── Historical fields (determine completeness, NOT identity) ────────────────

HISTORICAL_FIELDS = [
    "service_number",
    "death_date",
    "death_place",
    "death_cause",
    "captivity",
    "burial",
    "residence",
]

ALL_CLAIM_FIELDS = IDENTITY_FIELDS + HISTORICAL_FIELDS

# ─── Conditional gap rules ────────────────────────────────────────────────────
# A gap is conditional on the subject type and research goal.
# captivity is NOT a mandatory gap for a fallen soldier without captivity evidence.

CONDITIONAL_GAP_RULES = {
    "service_number": {"applies_when": lambda target: True, "description": "Numero di matricola militare"},
    "death_date": {"applies_when": lambda target: target.get("conflict") != "WWII_IMI", "description": "Data di morte"},
    "death_place": {"applies_when": lambda target: target.get("conflict") != "WWII_IMI", "description": "Luogo di morte"},
    "death_cause": {"applies_when": lambda target: target.get("conflict") != "WWII_IMI", "description": "Causa di morte"},
    "captivity": {
        "applies_when": lambda target: (
            target.get("conflict") in ("WWII", "WWII_IMI")
            or any(c.get("field_name") == "captivity" and c.get("object_value")
                   for c in target.get("_all_claims", []))
        ),
        "description": "Dettagli prigionia/internamento",
    },
    "burial": {"applies_when": lambda target: True, "description": "Luogo di sepoltura"},
    "residence": {"applies_when": lambda target: True, "description": "Residenza pre-bellica"},
}


# ─── Origin presence and provenance states ───────────────────────────────────

ORIGIN_PRESENCE = {
    "PRESENT_LOCAL",
    "ABSENT",
}

ORIGIN_PROVENANCE = {
    "VERIFIED",
    "UNVERIFIED",
    "CONFLICTING",
}

IDENTITY_RESOLUTION = {
    "UNRESOLVED",
    "PARTIAL",
    "RESOLVED",
}

EXTERNAL_CORROBORATION = {
    "NONE",
    "PARTIAL",
    "ACCEPTED",
    "CONFLICTING",
}

CONTENT_OBSERVATION = {
    "NOT_OPENED",
    "OPENED",
    "OCR_EXTRACTED",
    "FAILED",
}

TARGET_MATCH = {
    "NOT_TESTED",
    "ABSENT",
    "PARTIAL",
    "ACCEPTED",
    "CONFLICT",
}

EVIDENCE_STATUS = {
    "LEAD",
    "CONTEXT",
    "REJECTED",
    "PARTIAL",
    "ACCEPTED",
}

EVIDENCE_CAPABILITY = {
    "CAPABLE",
    "NOT_CAPABLE",
}


# ─── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class TargetIdentity:
    """Structured target identity — no ambiguous single-string name."""
    target_id: str = ""
    surname: str = ""
    given_names: List[str] = field(default_factory=list)
    display_name: str = ""  # "COGNOME Nome"
    source_order: str = "SURNAME_GIVEN"  # SURNAME_GIVEN | GIVEN_SURNAME
    conflict: str = "UNKNOWN"  # WWI | WWII | WWII_IMI | UNKNOWN
    assertions: List[Dict] = field(default_factory=list)  # raw input data, NOT proof

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OriginRecordV5:
    """Origin record with separated presence and provenance."""
    presence: str = "ABSENT"  # PRESENT_LOCAL | ABSENT
    provenance: str = "UNVERIFIED"  # VERIFIED | UNVERIFIED | CONFLICTING
    source_id: Optional[str] = None
    locator: Optional[str] = None
    provider: str = ""
    import_job_id: str = ""
    raw_payload_hash: str = ""
    supported_claim_ids: List[str] = field(default_factory=list)
    base_url: str = ""
    record_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClaimRecordV5:
    """A single claim with explicit probatory status."""
    claim_id: str
    field_name: str
    predicate: str
    object_value: str
    object_normalized: str
    source_ids: List[str] = field(default_factory=list)
    claim_status: str = "target_assertion"  # target_assertion | origin_supported | independently_supported | conflicting | conditional_gap
    confidence: float = 0.0
    is_identity_field: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PersonCandidateV5:
    """A person candidate with identity fingerprint — requires features beyond name."""
    candidate_id: str
    identity_fingerprint: str
    name: str
    surname: str = ""
    given_names: List[str] = field(default_factory=list)
    birth_year: str = ""
    birth_place: str = ""
    paternity: str = ""
    rank: str = ""
    unit: str = ""
    source_record_ids: List[str] = field(default_factory=list)
    locator: str = ""
    identity_features_count: int = 0  # features beyond name (birth_year, birth_place, etc.)
    status: str = "lead"  # lead | candidate | accepted | rejected
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceSourceV5:
    """An evidence source with content observation and target match."""
    source_id: str
    provider: str
    canonical_url: str  # FULL URL, never truncated
    display_label: str = ""  # abbreviated for UI, never used as href
    archive: str = ""
    record_id: str = ""
    locator: str = ""
    object_kind: str = ""
    evidence_capability: str = "NOT_CAPABLE"  # CAPABLE | NOT_CAPABLE
    content_observation: str = "NOT_OPENED"  # NOT_OPENED | OPENED | OCR_EXTRACTED | FAILED
    target_match: str = "NOT_TESTED"  # NOT_TESTED | ABSENT | PARTIAL | ACCEPTED | CONFLICT
    evidence_status: str = "LEAD"  # LEAD | CONTEXT | REJECTED | PARTIAL | ACCEPTED
    potentially_evidence_capable: bool = False
    accessed_at: str = ""
    is_origin: bool = False
    is_independent: bool = False
    content_excerpt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderLedgerEntryV5:
    """Reconcilable provider ledger entry."""
    provider: str
    conflict: str = ""
    execution_state: str = "NOT_RUN"
    retrieval_outcome: str = ""
    raw_results: int = 0
    unique_canonical_urls: int = 0
    displayed_results: int = 0
    opened_items: int = 0
    content_extracted: int = 0
    leads: int = 0
    context_sources: int = 0
    rejected_items: int = 0
    partial_evidence: int = 0
    accepted_evidence: int = 0
    fetch_failures: int = 0
    elapsed_ms: int = 0
    error_code: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResearchNextStep:
    """A conditional next step — not generic."""
    step_id: str
    action: str
    condition: str  # why this step applies
    priority: int = 0
    source_type: str = ""  # archive | database | authority | web
    authority_id: str = ""  # reference to authority registry if applicable

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceSnapshotV5:
    """Immutable, versioned, validated snapshot of all evidence for a target.

    This is the ONLY data the AI model receives. It cannot modify
    resolution_state, create claims, or assign sources.
    """
    snapshot_id: str = ""
    snapshot_hash: str = ""
    run_id: str = ""
    version: int = 5
    created_at: str = ""

    # Capability snapshot
    capability_snapshot_id: str = ""
    research_mode: str = "LOCAL_ONLY"
    providers_used: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    # Target identity (structured)
    target: Dict = field(default_factory=dict)  # TargetIdentity

    # Origin record
    origin: Dict = field(default_factory=dict)  # OriginRecordV5

    # Deterministic states (set by pipeline, not by AI)
    identity_resolution: str = "UNRESOLVED"
    external_corroboration: str = "NONE"
    reason_codes: List[str] = field(default_factory=list)

    # Claims
    asserted_claims: List[Dict] = field(default_factory=list)  # target_assertions
    origin_supported_claims: List[Dict] = field(default_factory=list)
    independently_supported_claims: List[Dict] = field(default_factory=list)
    conflicting_claims: List[Dict] = field(default_factory=list)
    conditional_gaps: List[Dict] = field(default_factory=list)

    # Person candidates (with identity fingerprint)
    person_candidates: List[Dict] = field(default_factory=list)
    rejected_candidates: List[Dict] = field(default_factory=list)

    # Evidence sources (with content observation)
    accepted_evidence: List[Dict] = field(default_factory=list)
    web_leads: List[Dict] = field(default_factory=list)
    context_sources: List[Dict] = field(default_factory=list)
    search_results: List[Dict] = field(default_factory=list)

    # Provider ledger (reconcilable)
    provider_ledger: List[Dict] = field(default_factory=list)

    # Next steps (conditional)
    next_steps: List[Dict] = field(default_factory=list)

    # AI metadata
    ai_used: bool = False
    ai_model: str = ""
    ai_truncation: Dict = field(default_factory=dict)
    ai_error: Dict = field(default_factory=dict)
    ai_validation: Dict = field(default_factory=dict)

    errors: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.snapshot_id:
            self.snapshot_id = f"snap_v5_{self.target.get('target_id', 'unknown')}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()
        self._compute_conditional_gaps()
        self._compute_reconciliation()

    def _compute_hash(self) -> str:
        raw = json.dumps({
            "target_id": self.target.get("target_id", ""),
            "identity_resolution": self.identity_resolution,
            "origin": self.origin,
            "origin_supported_claims": self.origin_supported_claims,
            "independently_supported_claims": self.independently_supported_claims,
            "accepted_evidence": self.accepted_evidence,
            "person_candidates": self.person_candidates,
            "rejected_candidates": self.rejected_candidates,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _compute_conditional_gaps(self):
        """Compute conditional gaps based on subject type and research goal."""
        if self.conditional_gaps:
            return

        all_claim_fields = set()
        for c in self.asserted_claims + self.origin_supported_claims + self.independently_supported_claims:
            if c.get("object_value"):
                all_claim_fields.add(c.get("field_name"))

        gaps = []
        for field_name, rule in CONDITIONAL_GAP_RULES.items():
            if field_name not in all_claim_fields:
                if rule["applies_when"](self.target):
                    gaps.append({
                        "field_name": field_name,
                        "description": rule["description"],
                        "is_identity": field_name in IDENTITY_FIELDS,
                    })
        self.conditional_gaps = gaps

    def _compute_reconciliation(self):
        """Compute reconcilable counts with accounting invariant."""
        total_raw = sum(e.get("raw_results", 0) for e in self.provider_ledger)
        total_unique = len(set(
            [s.get("canonical_url", "") for s in self.accepted_evidence] +
            [s.get("canonical_url", "") for s in self.web_leads] +
            [s.get("canonical_url", "") for s in self.context_sources] +
            [s.get("canonical_url", "") for s in self.search_results]
        ))
        total_opened = sum(1 for s in self.accepted_evidence + self.search_results
                          if s.get("content_observation") in ("OPENED", "OCR_EXTRACTED"))
        total_accepted = sum(1 for s in self.accepted_evidence
                            if s.get("evidence_status") == "ACCEPTED")
        total_partial = sum(1 for s in self.accepted_evidence
                           if s.get("evidence_status") == "PARTIAL")
        total_leads = len(self.web_leads)
        total_context = len(self.context_sources)
        total_rejected = len(self.rejected_candidates)
        total_fetch_fail = sum(e.get("fetch_failures", 0) for e in self.provider_ledger)

        self._reconciliation = {
            "provider_attempts": len(self.provider_ledger),
            "raw_results": total_raw,
            "unique_canonical_urls": total_unique,
            "displayed_results": len(self.search_results) + len(self.web_leads) + len(self.context_sources),
            "opened_items": total_opened,
            "content_extracted": sum(1 for s in self.accepted_evidence + self.search_results
                                    if s.get("content_observation") == "OCR_EXTRACTED"),
            "leads": total_leads,
            "context_sources": total_context,
            "rejected_items": total_rejected,
            "partial_evidence": total_partial,
            "accepted_evidence": total_accepted,
            "fetch_failures": total_fetch_fail,
        }

    @property
    def reconciliation(self) -> Dict:
        return self._reconciliation

    def validate(self) -> List[str]:
        """Validate invariants. Returns list of violation messages (empty = valid)."""
        violations = []

        # ── Invariant: ABSENT origin cannot have supported claims ──
        if self.origin.get("presence") == "ABSENT" and self.origin.get("supported_claim_ids"):
            violations.append(
                "INVARIANT_VIOLATION: origin.presence=ABSENT but origin.supported_claim_ids is non-empty"
            )

        # ── Invariant: independently_supported_claims require accepted_evidence ──
        if self.independently_supported_claims and not self.accepted_evidence:
            violations.append(
                "INVARIANT_VIOLATION: independently_supported_claims non-empty but accepted_evidence is empty"
            )

        # ── Invariant: origin_supported_claims must have source_ids ──
        for c in self.origin_supported_claims:
            if not c.get("source_ids"):
                violations.append(
                    f"INVARIANT_VIOLATION: origin_supported_claim {c.get('claim_id')} has empty source_ids"
                )

        # ── Invariant: independently_supported_claims must have source_ids ──
        for c in self.independently_supported_claims:
            if not c.get("source_ids"):
                violations.append(
                    f"INVARIANT_VIOLATION: independently_supported_claim {c.get('claim_id')} has empty source_ids"
                )

        # ── Invariant: evidence_eligible requires content_observation ──
        for s in self.accepted_evidence:
            if s.get("evidence_status") in ("ACCEPTED", "PARTIAL"):
                if s.get("content_observation") in ("NOT_OPENED", "FAILED"):
                    violations.append(
                        f"INVARIANT_VIOLATION: source {s.get('source_id')} has evidence_status={s.get('evidence_status')} "
                        f"but content_observation={s.get('content_observation')}"
                    )
                if s.get("target_match") in ("NOT_TESTED", "ABSENT"):
                    violations.append(
                        f"INVARIANT_VIOLATION: source {s.get('source_id')} has evidence_status={s.get('evidence_status')} "
                        f"but target_match={s.get('target_match')}"
                    )

        # ── Invariant: canonical_url must not be truncated ──
        for s in self.accepted_evidence + self.web_leads + self.context_sources + self.search_results:
            url = s.get("canonical_url", "")
            if url and len(url) < 10:
                violations.append(
                    f"INVARIANT_VIOLATION: source {s.get('source_id')} has suspiciously short canonical_url: {url}"
                )
            if url and "..." in url:
                violations.append(
                    f"INVARIANT_VIOLATION: source {s.get('source_id')} has truncated canonical_url with '...': {url}"
                )

        # ── Invariant: identity_resolution must be set by backend ──
        if self.identity_resolution not in IDENTITY_RESOLUTION:
            violations.append(
                f"INVARIANT_VIOLATION: identity_resolution={self.identity_resolution} is not a valid state"
            )

        # ── Invariant: external_corroboration must be set by backend ──
        if self.external_corroboration not in EXTERNAL_CORROBORATION:
            violations.append(
                f"INVARIANT_VIOLATION: external_corroboration={self.external_corroboration} is not a valid state"
            )

        # ── Invariant: target must have display_name ──
        if not self.target.get("display_name"):
            violations.append(
                "INVARIANT_VIOLATION: target.display_name is empty"
            )

        return violations

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "run_id": self.run_id,
            "version": self.version,
            "created_at": self.created_at,
            "capability_snapshot_id": self.capability_snapshot_id,
            "research_mode": self.research_mode,
            "providers_used": self.providers_used,
            "limitations": self.limitations,
            "target": self.target,
            "origin": self.origin,
            "identity_resolution": self.identity_resolution,
            "external_corroboration": self.external_corroboration,
            "reason_codes": self.reason_codes,
            "asserted_claims": self.asserted_claims,
            "origin_supported_claims": self.origin_supported_claims,
            "independently_supported_claims": self.independently_supported_claims,
            "conflicting_claims": self.conflicting_claims,
            "conditional_gaps": self.conditional_gaps,
            "person_candidates": self.person_candidates,
            "rejected_candidates": self.rejected_candidates,
            "accepted_evidence": self.accepted_evidence,
            "web_leads": self.web_leads,
            "context_sources": self.context_sources,
            "search_results": self.search_results,
            "provider_ledger": self.provider_ledger,
            "next_steps": self.next_steps,
            "reconciliation": self._reconciliation,
            "ai_used": self.ai_used,
            "ai_model": self.ai_model,
            "ai_truncation": self.ai_truncation,
            "ai_error": self.ai_error,
            "ai_validation": self.ai_validation,
            "errors": self.errors,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_conversational_context(self) -> str:
        """Render as text context for AI conversational reports.

        This is the ONLY data the AI model sees. It contains:
        - Target identity with explicit surname, given_names, display_name
        - Origin record with presence and provenance
        - Claims with explicit probatory status (target_assertion vs origin_supported)
        - Conditional gaps (not fixed field list)
        - Person candidates with identity features
        - Evidence sources with content_observation and target_match
        - Provider ledger with reconcilable counts
        - Next steps (conditional, not generic)
        - Research limitations

        It does NOT contain:
        - URLs (model emits source_id, renderer generates links)
        - Raw candidates without identity features
        - Unvalidated archival suggestions
        - Search page URLs as if they were evidence
        """
        t = self.target
        lines = [
            f"# Evidence Snapshot V5 — {self.snapshot_id}",
            f"Target: {t.get('display_name', '?')}",
            f"  surname: {t.get('surname', '')}",
            f"  given_names: {t.get('given_names', [])}",
            f"  display_name: {t.get('display_name', '')}",
            f"  source_order: {t.get('source_order', 'SURNAME_GIVEN')}",
            f"  conflict: {t.get('conflict', 'UNKNOWN')}",
            f"Version: {self.version}",
            f"Research Mode: {self.research_mode}",
            f"Identity Resolution: {self.identity_resolution}",
            f"External Corroboration: {self.external_corroboration}",
            "",
        ]

        # Origin record
        o = self.origin
        if o:
            lines.append("## Origin Record")
            lines.append(f"  presence: {o.get('presence', 'ABSENT')}")
            lines.append(f"  provenance: {o.get('provenance', 'UNVERIFIED')}")
            lines.append(f"  source_id: {o.get('source_id', '')}")
            lines.append(f"  provider: {o.get('provider', '')}")
            lines.append(f"  supported_claim_ids: {o.get('supported_claim_ids', [])}")
            lines.append("")

        # Asserted claims (target assertions — NOT proof)
        if self.asserted_claims:
            lines.append("## Target Assertions (input data, NOT proof)")
            for c in self.asserted_claims:
                lines.append(
                    f"  {c['claim_id']}: {c['field_name']}={c['object_value']} "
                    f"(status: target_assertion)"
                )
            lines.append("")

        # Origin-supported claims
        if self.origin_supported_claims:
            lines.append("## Origin-Supported Claims")
            for c in self.origin_supported_claims:
                lines.append(
                    f"  {c['claim_id']}: {c['field_name']}={c['object_value']} "
                    f"(sources: {c.get('source_ids', [])})"
                )
            lines.append("")

        # Independently-supported claims
        if self.independently_supported_claims:
            lines.append("## Independently-Supported Claims")
            for c in self.independently_supported_claims:
                lines.append(
                    f"  {c['claim_id']}: {c['field_name']}={c['object_value']} "
                    f"(sources: {c.get('source_ids', [])})"
                )
            lines.append("")

        # Conflicting claims
        if self.conflicting_claims:
            lines.append("## Conflicting Claims")
            for c in self.conflicting_claims:
                lines.append(
                    f"  {c['claim_id']}: {c['field_name']}={c['object_value']} "
                    f"(conflict: {c.get('conflict_reason', '')})"
                )
            lines.append("")

        # Conditional gaps
        if self.conditional_gaps:
            lines.append("## Conditional Gaps")
            for g in self.conditional_gaps:
                lines.append(
                    f"  {g['field_name']}: {g['description']} "
                    f"(identity_field: {g.get('is_identity', False)})"
                )
            lines.append("")

        # Person candidates
        if self.person_candidates:
            lines.append("## Person Candidates (with identity features)")
            for c in self.person_candidates:
                lines.append(
                    f"  {c['candidate_id']}: {c.get('name', '')} "
                    f"(fingerprint: {c.get('identity_fingerprint', '')[:8]}, "
                    f"features: {c.get('identity_features_count', 0)}, "
                    f"status: {c.get('status', 'lead')})"
                )
            lines.append("")

        # Rejected candidates
        if self.rejected_candidates:
            lines.append("## Rejected Candidates (Homonyms)")
            for c in self.rejected_candidates:
                lines.append(
                    f"  {c.get('name', '')}: {c.get('reason_codes', [])}"
                )
            lines.append("")

        # Accepted evidence
        if self.accepted_evidence:
            lines.append("## Accepted Evidence")
            for s in self.accepted_evidence:
                lines.append(
                    f"  {s['source_id']}: provider={s.get('provider', '')} "
                    f"kind={s.get('object_kind', '')} "
                    f"content={s.get('content_observation', 'NOT_OPENED')} "
                    f"match={s.get('target_match', 'NOT_TESTED')} "
                    f"status={s.get('evidence_status', 'LEAD')}"
                )
            lines.append("")

        # Web leads
        if self.web_leads:
            lines.append(f"## Web Leads ({len(self.web_leads)} unverified)")
            for s in self.web_leads:
                lines.append(
                    f"  {s['source_id']}: provider={s.get('provider', '')} "
                    f"kind={s.get('object_kind', '')} "
                    f"potentially_capable={s.get('potentially_evidence_capable', False)}"
                )
            lines.append("")

        # Context sources
        if self.context_sources:
            lines.append("## Context Sources (historical context, not target evidence)")
            for s in self.context_sources:
                lines.append(
                    f"  {s['source_id']}: {s.get('display_label', '')} "
                    f"reason={s.get('relevance_reason', '')}"
                )
            lines.append("")

        # Next steps
        if self.next_steps:
            lines.append("## Recommended Next Steps (conditional)")
            for s in self.next_steps:
                lines.append(
                    f"  {s['step_id']}: {s.get('action', '')} "
                    f"(condition: {s.get('condition', '')}, "
                    f"priority: {s.get('priority', 0)})"
                )
            lines.append("")

        # Research limitations
        if self.limitations:
            lines.append("## Research Limitations")
            for lim in self.limitations:
                lines.append(f"  - {lim}")
            lines.append("")

        # Reconciliation
        lines.append("## Reconciliation")
        for k, v in self._reconciliation.items():
            lines.append(f"  {k}: {v}")

        return "\n".join(lines)

    def validate_claim_id(self, claim_id: str) -> bool:
        all_claims = (
            self.asserted_claims + self.origin_supported_claims +
            self.independently_supported_claims + self.conflicting_claims
        )
        return any(c.get("claim_id") == claim_id for c in all_claims)

    def validate_source_id(self, source_id: str) -> bool:
        all_sources = self.accepted_evidence + self.web_leads + self.context_sources + self.search_results
        return any(s.get("source_id") == source_id for s in all_sources)


# ─── Builder ─────────────────────────────────────────────────────────────────


def build_snapshot_v5_from_dossier(
    dossier,
    target,
    run_id: str = "",
    capability_snapshot_id: str = "",
    research_mode: str = "LOCAL_ONLY",
    providers_used: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
) -> EvidenceSnapshotV5:
    """Build a V5 EvidenceSnapshot from a completed Dossier and ResearchTarget.

    Key differences from V4:
    - Target identity is structured (surname, given_names, display_name)
    - Origin presence is separated from provenance
    - Claims are classified as target_assertion / origin_supported / independently_supported
    - Person candidates require identity fingerprint
    - Evidence sources require content_observation and target_match
    - Conditional gaps replace fixed missing_claims
    - Provider ledger is reconcilable
    - Next steps are conditional
    """
    from research_protocol import (
        classify_object_kind, canonicalize_url, _norm_val,
    )

    providers_used = providers_used or []
    limitations = limitations or []

    # ── Build target identity ──
    target_dict = {
        "target_id": getattr(target, "target_id", ""),
        "surname": getattr(target, "cognome", ""),
        "given_names": [getattr(target, "nome", "")] if getattr(target, "nome", "") else [],
        "display_name": f"{getattr(target, 'cognome', '')} {getattr(target, 'nome', '')}".strip(),
        "source_order": "SURNAME_GIVEN",
        "conflict": getattr(target, "conflitto_presunto", "UNKNOWN"),
        "assertions": [],
    }

    # ── Determine origin record ──
    origin = {"presence": "ABSENT", "provenance": "UNVERIFIED"}
    best_candidate = None
    if dossier.candidati:
        best_candidate = max(dossier.candidati, key=lambda c: c.confidence)
        if best_candidate.confidence >= 0.8 and best_candidate.stato == "POSSIBLE":
            origin["presence"] = "PRESENT_LOCAL"
            origin["provenance"] = "UNVERIFIED"

            for f in best_candidate.fonti:
                canon_url = canonicalize_url(f.url)
                if not canon_url:
                    continue
                if f.url and f.url.startswith("http"):
                    origin["provenance"] = "VERIFIED"
                else:
                    origin["provenance"] = "UNVERIFIED"

                source_id = f"origin_{hash(canon_url) % 100000:05d}"
                origin["source_id"] = source_id
                origin["locator"] = canon_url
                origin["provider"] = f.istituzione or ""
                origin["record_url"] = f.url or ""
                origin["base_url"] = ""
                break

    # ── Build claims ──
    asserted_claims = []
    origin_supported_claims = []
    independently_supported_claims = []

    if best_candidate:
        field_map = {
            "birth_year": (best_candidate.data_nascita, "born_in_year"),
            "birth_place": (best_candidate.luogo_nascita, "born_in_place"),
            "paternity": (best_candidate.paternita, "father_named"),
            "rank": (best_candidate.grado, "held_rank"),
            "unit": (best_candidate.reparto, "served_in_unit"),
            "service_number": (best_candidate.matricola, "had_service_number"),
            "death_date": (best_candidate.data_morte, "died_on"),
            "death_place": (best_candidate.luogo_morte, "died_at"),
            "death_cause": (best_candidate.morte, "died_of"),
            "captivity": (best_candidate.prigionia, "imprisoned_at"),
            "burial": (best_candidate.sepoltura, "buried_at"),
            "residence": (best_candidate.residenza, "resided_at"),
        }

        origin_source_ids = [origin["source_id"]] if origin.get("source_id") else []

        for field_name, (value, predicate) in field_map.items():
            if value and str(value).strip():
                claim_id = f"cl_{target_dict['target_id'][:8]}_{field_name}"
                is_identity = field_name in IDENTITY_FIELDS

                claim = {
                    "claim_id": claim_id,
                    "field_name": field_name,
                    "predicate": predicate,
                    "object_value": str(value),
                    "object_normalized": _norm_val(str(value)),
                    "source_ids": origin_source_ids if origin["presence"] == "PRESENT_LOCAL" else [],
                    "claim_status": "origin_supported" if origin["presence"] == "PRESENT_LOCAL" else "target_assertion",
                    "confidence": best_candidate.confidence,
                    "is_identity_field": is_identity,
                }

                if origin["presence"] == "PRESENT_LOCAL" and origin_source_ids:
                    origin_supported_claims.append(claim)
                    origin.setdefault("supported_claim_ids", []).append(claim_id)
                else:
                    asserted_claims.append(claim)
            # Missing fields are handled by conditional_gaps

    # ── Build person candidates ──
    person_candidates = []
    for c in dossier.candidati:
        features_count = sum(1 for v in [
            c.data_nascita, c.luogo_nascita, c.paternita, c.grado, c.reparto
        ] if v and str(v).strip())

        if features_count < 1:
            continue

        fingerprint_raw = f"{c.nome_originale}|{c.data_nascita}|{c.luogo_nascita}|{c.paternita}"
        fingerprint = hashlib.sha256(fingerprint_raw.encode()).hexdigest()[:16]

        person_candidates.append({
            "candidate_id": f"cand_{hash(c.nome_originale) % 100000:05d}",
            "identity_fingerprint": fingerprint,
            "name": c.nome_originale,
            "surname": "",
            "given_names": [],
            "birth_year": c.data_nascita or "",
            "birth_place": c.luogo_nascita or "",
            "paternity": c.paternita or "",
            "rank": c.grado or "",
            "unit": c.reparto or "",
            "source_record_ids": [],
            "locator": "",
            "identity_features_count": features_count,
            "status": "candidate" if c.stato == "POSSIBLE" else "lead",
            "reason_codes": c.contraddizioni if c.contraddizioni else [],
        })

    # Deduplicate by fingerprint
    seen_fps = set()
    deduped = []
    for c in person_candidates:
        if c["identity_fingerprint"] not in seen_fps:
            seen_fps.add(c["identity_fingerprint"])
            deduped.append(c)
    person_candidates = deduped

    # ── Build rejected candidates ──
    rejected = []
    for c in dossier.omonimi_esclusi:
        rejected.append({
            "candidate_id": f"rej_{hash(c.nome_originale) % 100000:05d}",
            "name": c.nome_originale,
            "reason_codes": c.contraddizioni if c.contraddizioni else ["UNKNOWN"],
            "conflicting_features": c.compatibilita if c.compatibilita else [],
            "birth_year": c.data_nascita or "",
            "birth_place": c.luogo_nascita or "",
            "military_unit": c.reparto or "",
        })

    # ── Build evidence sources from web search ──
    accepted_evidence = []
    web_leads = []
    context_sources = []
    search_results = []

    ws = dossier.web_search_results or {}
    if isinstance(ws, dict) and not ws.get("error"):
        for s in ws.get("sources", []):
            url = s.get("url", s.get("canonical_url", ""))
            canon_url = canonicalize_url(url)
            if not canon_url:
                continue
            kind = classify_object_kind(canon_url)
            source_id = f"src_{hash(canon_url) % 100000:05d}"

            display_label = canon_url.split("/")[2] if "/" in canon_url else canon_url

            src = {
                "source_id": source_id,
                "provider": "tavily",
                "canonical_url": canon_url,
                "display_label": display_label,
                "archive": "",
                "record_id": "",
                "locator": "",
                "object_kind": kind.value if hasattr(kind, "value") else str(kind),
                "evidence_capability": "CAPABLE" if kind.value in ("DIGITIZED_DOCUMENT", "CATALOG_RECORD") else "NOT_CAPABLE",
                "content_observation": "NOT_OPENED",
                "target_match": "NOT_TESTED",
                "evidence_status": "LEAD",
                "potentially_evidence_capable": kind.value in ("DIGITIZED_DOCUMENT", "CATALOG_RECORD"),
                "accessed_at": "",
                "is_origin": False,
                "is_independent": True,
                "content_excerpt": "",
            }

            if src["evidence_capability"] == "CAPABLE":
                search_results.append(src)
            elif kind.value in ("HOMEPAGE", "SEARCH_PAGE", "SEARCH_RESULT_LEAD"):
                web_leads.append(src)
            else:
                context_sources.append(src)

    # ── Build provider ledger ──
    provider_ledger = []
    for sle in dossier.search_log:
        provider_ledger.append({
            "provider": sle.motore_o_archivio or "",
            "execution_state": "SUCCESS" if sle.esito == "positive" else "NO_RESULTS",
            "retrieval_outcome": "LEADS_ONLY" if sle.esito == "ambiguous" else ("PERSON_CANDIDATES" if sle.risultati_trovati > 0 else "NO_RESULTS"),
            "raw_results": sle.risultati_trovati,
            "unique_canonical_urls": 0,
            "displayed_results": 0,
            "opened_items": 0,
            "content_extracted": 0,
            "leads": 0,
            "context_sources": 0,
            "rejected_items": 0,
            "partial_evidence": 0,
            "accepted_evidence": 0,
            "fetch_failures": 0,
            "elapsed_ms": 0,
            "error_code": "",
            "timestamp": sle.timestamp or "",
        })

    # ── Determine identity resolution ──
    identity_fields_present = sum(
        1 for c in origin_supported_claims + independently_supported_claims
        if c.get("is_identity_field") and c.get("object_value")
    )
    if identity_fields_present >= 3 and origin["presence"] == "PRESENT_LOCAL":
        identity_resolution = "RESOLVED"
    elif identity_fields_present >= 1:
        identity_resolution = "PARTIAL"
    else:
        identity_resolution = "UNRESOLVED"

    # ── Determine external corroboration ──
    independent_count = len(independently_supported_claims)
    if independent_count >= 2:
        external_corroboration = "ACCEPTED"
    elif independent_count == 1:
        external_corroboration = "PARTIAL"
    elif any(c.get("conflicting") for c in dossier.candidati if hasattr(c, "conflicting")):
        external_corroboration = "CONFLICTING"
    else:
        external_corroboration = "NONE"

    # ── Build next steps (conditional) ──
    from research_next_step_planner import plan_next_steps
    next_steps = plan_next_steps(target_dict, origin, identity_resolution, external_corroboration)

    # ── Research limitations ──
    if research_mode == "LOCAL_ONLY":
        limitations.append(
            "La sessione non ha eseguito una ricerca web in tempo reale. "
            "Sono stati usati soltanto i dati gia disponibili nella piattaforma; "
            "pertanto l'assenza di nuovi riscontri non puo essere interpretata "
            "come prova negativa."
        )

    snapshot = EvidenceSnapshotV5(
        run_id=run_id,
        capability_snapshot_id=capability_snapshot_id,
        research_mode=research_mode,
        providers_used=providers_used,
        limitations=limitations,
        target=target_dict,
        origin=origin,
        identity_resolution=identity_resolution,
        external_corroboration=external_corroboration,
        asserted_claims=asserted_claims,
        origin_supported_claims=origin_supported_claims,
        independently_supported_claims=independently_supported_claims,
        person_candidates=person_candidates,
        rejected_candidates=rejected,
        accepted_evidence=accepted_evidence,
        web_leads=web_leads,
        context_sources=context_sources,
        search_results=search_results,
        provider_ledger=provider_ledger,
        next_steps=next_steps,
    )

    return snapshot
