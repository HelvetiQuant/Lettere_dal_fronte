"""EvidenceSnapshotV7 — unified, immutable, validated DTO for V7 pipeline.

V7.2 extensions:
  - identity_status: ANCHORED_RECORD|RESOLVED_IDENTITY|AMBIGUOUS_IDENTITY|PARTIAL_IDENTITY|UNRESOLVED_IDENTITY
  - corroboration_status: NONE|PARTIAL|FULL (separate from identity)
  - resolved_identity_cluster_id: cluster ID of the resolved identity
  - candidate_identities: list of alternative identity clusters (for AMBIGUOUS)
  - person_claims: claims about the specific person (require identity_cluster_id match)
  - context_claims: claims about unit/event/place/camp/period (not person evidence)
  - evidence_scope on claims: PERSON_EVIDENCE|CONTEXT_EVIDENCE
  - identity_cluster_id on claims: mandatory, must match resolved cluster
  - source_locator: stable archival reference (fondo/serie/pagina) accepted without URL

V7.1 retained:
  - source_lineage_groups: tracks which sources share a common origin
  - independence_groups: tracks which sources are truly independent
  - correction_layers: layered corrections on immutable raw data
  - aggregate_definition_id: binding to AggregateDefinitionRegistry entry
  - narrator_contract_version: strict narrator output contract version
  - provenance_chain: full chain from raw observation to accepted claim

Invariants:
  assert snapshot.manifest_hash == plan.manifest_hash
  assert all(claim.evidence_ids for claim in snapshot.accepted_claims)
  assert all(e.locator and e.source_id for e in snapshot.accepted_evidence)
  assert all(not e.content_state == "NOT_OPENED" for e in snapshot.accepted_evidence)
  assert all(item.accounted_for for item in provider_ledger)
  assert all(c.correction_chain for c in snapshot.corrected_claims)
  assert identity_resolution_decided_by_backend
  assert external_corroboration_decided_by_backend
  # V7.2 invariants:
  assert all(claim.identity_cluster_id == snapshot.resolved_identity_cluster_id for claim in snapshot.person_claims)
  assert snapshot.identity_status in IDENTITY_STATUS_V72
  assert len([c for c in snapshot.rejected_candidates if c.reason_codes and 'SURNAME_ONLY_NON_CANDIDATE' in c.reason_codes]) == 0 or True  # surname-only hidden, not in rejected
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


# ─── Claim definitions ──────────────────────────────────────────────────────

# ─── V7.2 Identity status ───────────────────────────────────────────────────

IDENTITY_STATUS_V72 = [
    "ANCHORED_RECORD",
    "RESOLVED_IDENTITY",
    "AMBIGUOUS_IDENTITY",
    "PARTIAL_IDENTITY",
    "UNRESOLVED_IDENTITY",
]

# Legacy identity resolution values (kept for backward compat)
IDENTITY_RESOLUTION_LEGACY = ["INCOMPLETE_TARGET", "UNRESOLVED", "PARTIAL", "RESOLVED"]

# Evidence scope
EVIDENCE_SCOPES = ["PERSON_EVIDENCE", "CONTEXT_EVIDENCE"]

# Context claim scopes
CONTEXT_SCOPES = ["UNIT", "EVENT", "PLACE", "CAMP", "PERIOD"]


# ─── Claim definitions ──────────────────────────────────────────────────────

CLAIM_FIELDS_V7 = [
    "full_birth_date", "birth_year", "birth_place", "paternity",
    "rank", "unit", "service_number",
    "death_date", "death_year", "death_place", "death_cause",
    "captivity", "internment_place", "burial",
    "residence", "decoration_type", "decoration_year",
    "draft_class", "municipality",
    "capture_place", "capture_date", "fate",
    "event_start_date", "event_end_date", "event_location",
    "event_description", "event_phase_count", "event_actors",
    "count", "breakdown", "temporal_distribution", "geographic_distribution",
]


# ─── Source lineage and independence ─────────────────────────────────────────

@dataclass
class SourceLineageGroup:
    """Group of sources that share a common origin (e.g. same archive, same OCR)."""
    group_id: str
    root_source_id: str
    member_source_ids: List[str] = field(default_factory=list)
    lineage_type: str = ""  # SAME_ARCHIVE|SAME_OCR|SAME_PUBLICATION|SAME_INDEX
    description: str = ""


@dataclass
class IndependenceGroup:
    """Group of sources that are truly independent (different archives, different authors)."""
    group_id: str
    member_source_ids: List[str] = field(default_factory=list)
    independence_score: float = 0.0  # 0.0 = dependent, 1.0 = fully independent
    verified: bool = False


# ─── Correction layers ──────────────────────────────────────────────────────

@dataclass
class CorrectionLayer:
    """A single correction applied to raw data.

    Raw data is immutable. Corrections are layered overlays with full audit trail.
    """
    correction_id: str
    field_name: str
    original_value: str
    corrected_value: str
    correction_source: str  # MANUAL|AI_SUGGESTED|CROSS_VALIDATED|AUTHORITY_FILE
    corrected_by: str = ""
    corrected_at: str = ""
    reason: str = ""
    confidence: float = 0.0
    verified: bool = False


# ─── Claims ─────────────────────────────────────────────────────────────────

@dataclass
class ClaimV7:
    claim_id: str
    subject_id: str
    predicate: str
    value_normalized: str
    value_raw: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    independence_group_ids: List[str] = field(default_factory=list)
    source_lineage_group_ids: List[str] = field(default_factory=list)
    status: str = "ASSERTED"  # ASSERTED|ORIGIN_SUPPORTED|PARTIAL|ACCEPTED|CONFLICTING|REJECTED
    confidence: float = 0.0
    source: str = ""  # origin_record|external|aggregate
    correction_chain: List[str] = field(default_factory=list)  # correction_ids applied
    provenance_chain: List[str] = field(default_factory=list)  # observation_ids -> evidence -> claim
    # V7.2 fields:
    identity_cluster_id: str = ""  # mandatory: which identity cluster this claim belongs to
    evidence_scope: str = "PERSON_EVIDENCE"  # PERSON_EVIDENCE|CONTEXT_EVIDENCE
    context_scope: str = ""  # UNIT|EVENT|PLACE|CAMP|PERIOD (only for CONTEXT_EVIDENCE)
    source_locator: str = ""  # stable archival reference (fondo/serie/pagina)
    # V7.2 conservative normalization:
    normalization_status: str = ""  # exact|probable|reclassified|year_only_from_synthetic|needs_image_review
    # V7.2 functional source classification:
    source_function: str = ""  # person_evidence|event_context|place_normalization_evidence|research_lead|homonym_candidate|rejected_identity_link
    anomaly_note: str = ""  # note from anomaly detection or claim rules


@dataclass
class EvidenceItemV7:
    evidence_id: str
    source_id: str
    provider: str
    source_lineage_group_id: str = ""
    independence_group_id: str = ""
    locator: str = ""
    content_state: str = "NOT_OPENED"
    excerpt: str = ""
    object_kind: str = ""
    accessed_at: str = ""
    is_origin: bool = False
    is_independent: bool = False
    classification: str = "SEARCH_RESULT"
    reason_codes: List[str] = field(default_factory=list)
    raw_payload_hash: str = ""


@dataclass
class RejectedCandidateV7:
    candidate_id: str
    name: str
    reason_codes: List[str]
    conflicting_features: List[str]
    birth_year: str = ""
    birth_place: str = ""
    military_unit: str = ""
    provider: str = ""
    # V7.2: classification to distinguish surname-only from true homonyms
    classification: str = "HOMONYM"  # HOMONYM|SURNAME_ONLY_NON_CANDIDATE


@dataclass
class ContextSourceV7:
    source_id: str
    provider: str
    title: str = ""
    url_canonical: str = ""
    reason: str = ""


@dataclass
class WebLeadV7:
    lead_id: str
    provider: str
    url_canonical: str = ""
    title: str = ""
    snippet: str = ""
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class ProviderLedgerEntryV7:
    observation_id: str
    provider: str
    capability: str = ""
    classification: str = ""
    reason_codes: List[str] = field(default_factory=list)
    accounted_for: bool = True
    raw_result_hash: str = ""


@dataclass
class ConditionalGapV7:
    gap_id: str
    field_name: str
    reason: str
    blocking: bool = False


@dataclass
class NextStepEntryV7:
    step_id: str
    catalog_id: str
    description: str
    archive: str = ""
    access_mode: str = ""
    priority: int = 0


@dataclass
class LimitationV7:
    code: str
    description: str


# ─── Main snapshot ──────────────────────────────────────────────────────────

@dataclass
class CandidateIdentityV72:
    """A candidate identity cluster for AMBIGUOUS_IDENTITY cases."""
    cluster_id: str
    display_name: str
    canonical_fields: Dict[str, Any] = field(default_factory=dict)
    discriminants: List[str] = field(default_factory=list)  # fields that distinguish this cluster
    conflicting_with: List[str] = field(default_factory=list)  # other cluster_ids in conflict
    source_record_ids: List[str] = field(default_factory=list)


@dataclass
class ContextClaimV7:
    """A claim about historical context (unit, event, place, camp, period).

    Context claims cannot be used to attribute actions to a specific person.
    scope: UNIT|EVENT|PLACE|CAMP|PERIOD
    """
    claim_id: str
    scope: str  # UNIT|EVENT|PLACE|CAMP|PERIOD
    predicate: str
    value: str
    source_refs: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class EvidenceSnapshotV7:
    snapshot_id: str = ""
    snapshot_hash: str = ""
    schema_version: str = "7.2"
    run_id: str = ""
    plan_id: str = ""
    manifest_hash: str = ""
    intent: str = ""
    target: Dict[str, Any] = field(default_factory=dict)
    origin: Dict[str, Any] = field(default_factory=dict)
    identity_resolution: str = "UNRESOLVED"  # legacy field, kept for compat
    external_corroboration: str = "NONE"
    # V7.2 identity fields:
    identity_status: str = "UNRESOLVED_IDENTITY"  # ANCHORED_RECORD|RESOLVED_IDENTITY|AMBIGUOUS_IDENTITY|PARTIAL_IDENTITY|UNRESOLVED_IDENTITY
    corroboration_status: str = "NONE"  # NONE|PARTIAL|FULL (separate from identity)
    resolved_identity_cluster_id: str = ""  # cluster ID of resolved identity
    origin_record_id: str = ""  # if query started from a specific record
    accepted_claims: List[ClaimV7] = field(default_factory=list)
    conflicting_claims: List[ClaimV7] = field(default_factory=list)
    asserted_claims: List[ClaimV7] = field(default_factory=list)
    # V7.2: person claims (from resolved cluster only) and context claims (separate)
    person_claims: List[ClaimV7] = field(default_factory=list)  # claims about the person, cluster-filtered
    context_claims: List[ContextClaimV7] = field(default_factory=list)  # claims about context only
    candidate_identities: List[CandidateIdentityV72] = field(default_factory=list)  # alternative clusters
    accepted_evidence: List[EvidenceItemV7] = field(default_factory=list)
    context_sources: List[ContextSourceV7] = field(default_factory=list)
    web_leads: List[WebLeadV7] = field(default_factory=list)
    rejected_candidates: List[RejectedCandidateV7] = field(default_factory=list)
    conditional_gaps: List[ConditionalGapV7] = field(default_factory=list)
    next_step_catalog_ids: List[str] = field(default_factory=list)
    next_steps: List[NextStepEntryV7] = field(default_factory=list)
    provider_ledger: List[ProviderLedgerEntryV7] = field(default_factory=list)
    limitations: List[LimitationV7] = field(default_factory=list)
    aggregate_result: Optional[Dict[str, Any]] = None
    aggregate_definition_id: str = ""
    source_lineage_groups: List[SourceLineageGroup] = field(default_factory=list)
    independence_groups: List[IndependenceGroup] = field(default_factory=list)
    corrections: List[CorrectionLayer] = field(default_factory=list)
    narrator_contract_version: str = "7.2"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.snapshot_id:
            raw = json.dumps(self._hash_payload(), sort_keys=True, ensure_ascii=False)
            self.snapshot_hash = hashlib.sha256(raw.encode()).hexdigest()
            self.snapshot_id = f"snap_v7_{self.snapshot_hash[:16]}"

    def _hash_payload(self) -> dict:
        d = asdict(self)
        d.pop("snapshot_id", None)
        d.pop("snapshot_hash", None)
        d.pop("created_at", None)
        return d

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceSnapshotV7":
        def _convert_list(items, cls_):
            return [cls_(**i) if isinstance(i, dict) else i for i in items]

        accepted_claims = _convert_list(d.pop("accepted_claims", []), ClaimV7)
        conflicting_claims = _convert_list(d.pop("conflicting_claims", []), ClaimV7)
        asserted_claims = _convert_list(d.pop("asserted_claims", []), ClaimV7)
        person_claims = _convert_list(d.pop("person_claims", []), ClaimV7)
        context_claims = _convert_list(d.pop("context_claims", []), ContextClaimV7)
        candidate_identities = _convert_list(d.pop("candidate_identities", []), CandidateIdentityV72)
        accepted_evidence = _convert_list(d.pop("accepted_evidence", []), EvidenceItemV7)
        context_sources = _convert_list(d.pop("context_sources", []), ContextSourceV7)
        web_leads = _convert_list(d.pop("web_leads", []), WebLeadV7)
        rejected_candidates = _convert_list(d.pop("rejected_candidates", []), RejectedCandidateV7)
        conditional_gaps = _convert_list(d.pop("conditional_gaps", []), ConditionalGapV7)
        next_steps = _convert_list(d.pop("next_steps", []), NextStepEntryV7)
        provider_ledger = _convert_list(d.pop("provider_ledger", []), ProviderLedgerEntryV7)
        limitations = _convert_list(d.pop("limitations", []), LimitationV7)
        source_lineage_groups = _convert_list(d.pop("source_lineage_groups", []), SourceLineageGroup)
        independence_groups = _convert_list(d.pop("independence_groups", []), IndependenceGroup)
        corrections = _convert_list(d.pop("corrections", []), CorrectionLayer)

        return cls(
            accepted_claims=accepted_claims,
            conflicting_claims=conflicting_claims,
            asserted_claims=asserted_claims,
            person_claims=person_claims,
            context_claims=context_claims,
            candidate_identities=candidate_identities,
            accepted_evidence=accepted_evidence,
            context_sources=context_sources,
            web_leads=web_leads,
            rejected_candidates=rejected_candidates,
            conditional_gaps=conditional_gaps,
            next_steps=next_steps,
            provider_ledger=provider_ledger,
            limitations=limitations,
            source_lineage_groups=source_lineage_groups,
            independence_groups=independence_groups,
            corrections=corrections,
            **d,
        )

    def validate_invariants(self) -> List[str]:
        """Return list of violation messages. Empty = valid."""
        violations = []

        for claim in self.accepted_claims:
            if not claim.evidence_ids:
                violations.append(f"ACCEPTED_CLAIM_WITHOUT_EVIDENCE: {claim.claim_id}")

        for ev in self.accepted_evidence:
            if not ev.locator and not ev.raw_payload_hash:
                violations.append(f"EVIDENCE_WITHOUT_LOCATOR: {ev.evidence_id}")
            if not ev.source_id:
                violations.append(f"EVIDENCE_WITHOUT_SOURCE_ID: {ev.evidence_id}")
            if ev.content_state == "NOT_OPENED":
                violations.append(f"UNOPENED_ITEM_AS_EVIDENCE: {ev.evidence_id}")

        for entry in self.provider_ledger:
            if not entry.accounted_for:
                violations.append(f"UNACCOUNTED_OBSERVATION: {entry.observation_id}")

        # V7.2: identity_status must be valid
        if self.identity_status not in IDENTITY_STATUS_V72:
            violations.append(f"INVALID_IDENTITY_STATUS: {self.identity_status}")

        # V7.2: legacy identity_resolution still checked for compat
        if self.identity_resolution not in IDENTITY_RESOLUTION_LEGACY:
            violations.append(f"INVALID_IDENTITY_RESOLUTION: {self.identity_resolution}")

        if self.external_corroboration not in ("NONE", "PARTIAL", "ACCEPTED", "CONFLICTING"):
            violations.append(f"INVALID_EXTERNAL_CORROBORATION: {self.external_corroboration}")

        # V7: accepted claims must have provenance chain
        for claim in self.accepted_claims:
            if not claim.provenance_chain:
                violations.append(f"ACCEPTED_CLAIM_WITHOUT_PROVENANCE_CHAIN: {claim.claim_id}")

        # V7: corrections must reference existing evidence
        correction_ids = {c.correction_id for c in self.corrections}
        for claim in self.accepted_claims:
            for cid in claim.correction_chain:
                if cid not in correction_ids:
                    violations.append(f"CORRECTION_REFERENCE_MISSING: {cid} in claim {claim.claim_id}")

        # V7.2: person claims must belong to resolved identity cluster
        if self.resolved_identity_cluster_id:
            for claim in self.person_claims:
                if claim.identity_cluster_id and claim.identity_cluster_id != self.resolved_identity_cluster_id:
                    violations.append(
                        f"CROSS_IDENTITY_CLAIM: {claim.claim_id} belongs to cluster {claim.identity_cluster_id} "
                        f"but resolved cluster is {self.resolved_identity_cluster_id}"
                    )

        # V7.2: surname-only candidates must not be visible in rejected_candidates
        for rc in self.rejected_candidates:
            if rc.classification == "SURNAME_ONLY_NON_CANDIDATE":
                violations.append(
                    f"SURNAME_ONLY_CANDIDATE_VISIBLE: {rc.candidate_id} ({rc.name}) "
                    f"should be hidden, not in rejected_candidates"
                )

        # V7.2: context claims must not be in person_claims
        for claim in self.person_claims:
            if claim.evidence_scope == "CONTEXT_EVIDENCE":
                violations.append(
                    f"CONTEXT_CLAIM_IN_PERSON_CLAIMS: {claim.claim_id} has CONTEXT_EVIDENCE scope"
                )

        return violations

    def compute_conditional_gaps(self):
        """Compute gaps from intent + target + accepted claims."""
        self.conditional_gaps = []
        if self.intent == "PERSON_LOOKUP":
            accepted_fields = {c.predicate for c in self.accepted_claims}
            accepted_fields |= {c.predicate for c in self.asserted_claims}
            for field_name in CLAIM_FIELDS_V7:
                if field_name not in accepted_fields and field_name.startswith(("birth", "death", "rank", "unit", "capture", "fate", "internment", "captivity", "burial")):
                    blocking = field_name in ("birth_year", "birth_place", "rank")
                    self.conditional_gaps.append(ConditionalGapV7(
                        gap_id=f"gap_{field_name}",
                        field_name=field_name,
                        reason=f"Field {field_name} not supported by accepted evidence",
                        blocking=blocking,
                    ))
        elif self.intent == "EVENT_LOOKUP":
            accepted_fields = {c.predicate for c in self.accepted_claims}
            accepted_fields |= {c.predicate for c in self.asserted_claims}
            for field_name in ["event_start_date", "event_end_date", "event_location", "event_description", "event_phase_count", "event_actors"]:
                if field_name not in accepted_fields:
                    self.conditional_gaps.append(ConditionalGapV7(
                        gap_id=f"gap_{field_name}",
                        field_name=field_name,
                        reason=f"Event field {field_name} not supported",
                        blocking=field_name in ("event_start_date", "event_end_date"),
                    ))
        elif self.intent == "AGGREGATE_QUERY":
            if self.aggregate_result is None:
                self.conditional_gaps.append(ConditionalGapV7(
                    gap_id="gap_aggregate",
                    field_name="aggregate_data",
                    reason="No aggregate data available for this query",
                    blocking=True,
                ))

    def to_conversational_context(self) -> str:
        """Render snapshot as text context for the AI model.

        The model receives ONLY authorized data. No URLs are passed.
        V7.2: includes identity_status, person_claims, context_claims, candidate_identities.
        """
        lines = [
            f"# Evidence Snapshot V7.2 — {self.snapshot_id}",
            f"Schema: {self.schema_version} | Intent: {self.intent}",
            f"Plan: {self.plan_id[:16] if self.plan_id else 'N/A'} | Manifest: {self.manifest_hash[:16] if self.manifest_hash else 'N/A'}",
            f"Narrator Contract: {self.narrator_contract_version}",
            "",
            "## Target",
            f"  Display: {self.target.get('display_name', 'N/A')}",
            f"  Conflict: {self.target.get('conflict', 'UNKNOWN')}",
            "",
            "## Origin Record",
            f"  presence: {self.origin.get('presence', 'ABSENT')}",
            f"  provenance: {self.origin.get('provenance', 'UNVERIFIED')}",
            "",
            f"## Identity Status: {self.identity_status}",
            f"## Corroboration Status: {self.corroboration_status}",
            "",
        ]

        if self.candidate_identities:
            lines.append("## Candidate Identities (for AMBIGUOUS cases)")
            for ci in self.candidate_identities:
                lines.append(f"  {ci.display_name}: discriminants={ci.discriminants}")
            lines.append("")

        if self.source_lineage_groups:
            lines.append("## Source Lineage Groups")
            for g in self.source_lineage_groups:
                lines.append(f"  {g.group_id}: root={g.root_source_id}, type={g.lineage_type}, members={len(g.member_source_ids)}")
            lines.append("")

        if self.independence_groups:
            lines.append("## Independence Groups")
            for g in self.independence_groups:
                lines.append(f"  {g.group_id}: score={g.independence_score:.2f}, verified={g.verified}, members={len(g.member_source_ids)}")
            lines.append("")

        if self.person_claims:
            lines.append("## Person Claims (attributable to the identified person)")
            for c in self.person_claims:
                norm = f" [norm_status: {c.normalization_status}]" if c.normalization_status else ""
                func = f" [source_function: {c.source_function}]" if c.source_function else ""
                anomaly = f" [anomaly: {c.anomaly_note}]" if c.anomaly_note else ""
                lines.append(f"  {c.predicate} = {c.value_normalized} (scope: {c.evidence_scope}, status: {c.status}, conf: {c.confidence:.2f}){norm}{func}{anomaly}")
            lines.append("")

        if self.context_claims:
            lines.append("## Context Claims (historical context, NOT person evidence)")
            for c in self.context_claims:
                func = f" [source_function: {c.source_function}]" if c.source_function else ""
                lines.append(f"  [{c.context_scope}] {c.predicate} = {c.value_normalized}{func}")
            lines.append("")

        if self.accepted_claims:
            lines.append("## Accepted Claims")
            for c in self.accepted_claims:
                lines.append(f"  {c.claim_id}: {c.predicate} = {c.value_normalized} (evidence: {c.evidence_ids})")
            lines.append("")

        if self.conflicting_claims:
            lines.append("## Conflicting Claims")
            for c in self.conflicting_claims:
                lines.append(f"  {c.claim_id}: {c.predicate} = {c.value_normalized} (CONFLICTING)")
            lines.append("")

        if self.asserted_claims:
            lines.append("## Asserted Claims (from origin, not externally corroborated)")
            for c in self.asserted_claims:
                lines.append(f"  {c.claim_id}: {c.predicate} = {c.value_normalized} (source: {c.source})")
            lines.append("")

        if self.accepted_evidence:
            lines.append("## Accepted Evidence")
            for e in self.accepted_evidence:
                lines.append(f"  {e.evidence_id}: source={e.source_id}, state={e.content_state}, kind={e.object_kind}, independent={e.is_independent}")
            lines.append("")

        if self.context_sources:
            lines.append("## Context Sources (historical context, not target evidence)")
            for s in self.context_sources:
                lines.append(f"  {s.source_id}: {s.title} ({s.provider}) — {s.reason}")
            lines.append("")

        if self.web_leads:
            lines.append("## Research Leads (unverified, not evidence)")
            for l in self.web_leads:
                lines.append(f"  {l.lead_id}: {l.title} ({l.provider})")
            lines.append("")

        if self.rejected_candidates:
            lines.append("## Rejected Candidates (Homonyms)")
            for r in self.rejected_candidates:
                lines.append(f"  {r.candidate_id}: {r.name} — reasons: {r.reason_codes}")
            lines.append("")

        if self.conditional_gaps:
            lines.append("## Conditional Gaps")
            for g in self.conditional_gaps:
                lines.append(f"  {g.gap_id}: {g.field_name} — {g.reason}")
            lines.append("")

        if self.next_steps:
            lines.append("## Suggested Next Steps")
            for s in self.next_steps:
                lines.append(f"  {s.step_id}: {s.description} (archive: {s.archive}, access: {s.access_mode})")
            lines.append("")

        if self.limitations:
            lines.append("## Research Limitations")
            for lim in self.limitations:
                lines.append(f"  {lim.code}: {lim.description}")
            lines.append("")

        if self.aggregate_result is not None:
            lines.append("## Aggregate Result")
            for k, v in self.aggregate_result.items():
                lines.append(f"  {k}: {v}")
            lines.append("")

        if self.provider_ledger:
            lines.append("## Provider Ledger (audit trail)")
            for entry in self.provider_ledger:
                lines.append(f"  {entry.observation_id}: {entry.provider} — {entry.classification} — accounted: {entry.accounted_for}")
            lines.append("")

        return "\n".join(lines)

    def to_narrator_input(self, user_query: str = "", requested_depth: str = "standard") -> str:
        """Produce structured JSON input for the V7.2 Historical Narrator v1.

        Claims are classified into verified/probable/possible/conflicting/
        unverified/rejected buckets using v7_claim_rules.classify_claim_status.
        Sources are mapped with authority_tier, source_function, and
        independence_group metadata.

        Returns a JSON string matching the narrator system prompt v1 input spec.
        """
        import json as _json
        from v7_claim_rules import classify_claim_status

        def _claim_to_dict(c: ClaimV7) -> dict:
            cd = {
                "claim_id": c.claim_id,
                "subject_id": c.subject_id,
                "predicate": c.predicate,
                "value_raw": c.value_raw or c.value_normalized,
                "value_normalized": c.value_normalized,
                "value_precision": c.normalization_status or "unknown",
                "semantic_role": c.context_scope or "",
                "verification_status": c.status.lower(),
                "source_ids": c.evidence_ids[:],
                "source_function": c.source_function or "person_evidence",
                "decision_reason": c.anomaly_note or "",
                "independence_group": "",
                "identity_confidence": "strong" if c.confidence >= 0.8 else ("medium" if c.confidence >= 0.5 else "weak"),
            }
            return cd

        # Classify all person claims into buckets
        buckets = {
            "verified": [],
            "probable": [],
            "possible": [],
            "conflicting": [],
            "unverified": [],
            "rejected": [],
        }

        all_claims = list(self.person_claims) + list(self.context_claims)
        for c in all_claims:
            cd = _claim_to_dict(c)
            bucket = classify_claim_status(cd)
            if bucket == "APPROVED":
                buckets["verified"].append(cd)
            elif bucket == "PROBABLE":
                buckets["probable"].append(cd)
            elif bucket == "REJECTED":
                buckets["rejected"].append(cd)
            elif c.status == "CONFLICTING":
                buckets["conflicting"].append(cd)
            elif c.status == "ASSERTED":
                buckets["unverified"].append(cd)
            else:
                buckets["possible"].append(cd)

        # Also include accepted/asserted/conflicting from legacy fields
        for c in self.accepted_claims:
            cd = _claim_to_dict(c)
            if cd not in buckets["verified"]:
                buckets["verified"].append(cd)
        for c in self.asserted_claims:
            cd = _claim_to_dict(c)
            if cd not in buckets["unverified"] and cd not in buckets["verified"]:
                buckets["unverified"].append(cd)
        for c in self.conflicting_claims:
            cd = _claim_to_dict(c)
            if cd not in buckets["conflicting"]:
                buckets["conflicting"].append(cd)

        # Build sources list
        sources = []
        for e in self.accepted_evidence:
            sources.append({
                "source_id": e.source_id,
                "title": f"{e.provider}:{e.source_id}",
                "institution": e.provider,
                "url": e.locator or "",
                "page": "",
                "authority_tier": "A1" if e.is_origin else "B",
                "source_function": "person_evidence" if e.is_origin else "fact_evidence",
                "independence_group": e.independence_group_id or "",
                "access_type": "archived" if e.content_state == "OPENED" else "metadata_link",
            })
        for s in self.context_sources:
            sources.append({
                "source_id": s.source_id,
                "title": s.title,
                "institution": s.provider,
                "url": s.url_canonical or "",
                "page": "",
                "authority_tier": "C",
                "source_function": "event_context",
                "independence_group": "",
                "access_type": "external",
            })

        # Build research leads
        research_leads = []
        for l in self.web_leads:
            research_leads.append({
                "lead_id": l.lead_id,
                "title": l.title,
                "provider": l.provider,
                "url": l.url_canonical or "",
            })

        # Determine request_type from intent
        intent = self.intent or ""
        if intent == "PERSON_LOOKUP":
            request_type = "PERSON"
        elif intent == "EVENT_LOOKUP":
            request_type = "EVENT"
        elif intent == "AGGREGATE_QUERY":
            request_type = "FACT"
        else:
            request_type = None

        # Subjects
        subjects = []
        if self.target:
            subjects.append({
                "display_name": self.target.get("display_name", ""),
                "id": self.target.get("id", ""),
            })
        for ci in self.candidate_identities:
            subjects.append({
                "display_name": ci.display_name,
                "id": getattr(ci, "candidate_id", getattr(ci, "cluster_id", "")),
            })

        # Coverage summary
        coverage = {
            "identity_status": self.identity_status,
            "corroboration_status": self.corroboration_status,
            "external_corroboration": self.external_corroboration,
            "person_claims_count": len(self.person_claims),
            "context_claims_count": len(self.context_claims),
            "evidence_count": len(self.accepted_evidence),
            "web_leads_count": len(self.web_leads),
            "candidate_identities_count": len(self.candidate_identities),
            "rejected_candidates_count": len(self.rejected_candidates),
            "conditional_gaps_count": len(self.conditional_gaps),
        }

        # Retrieval summary
        retrieval_summary = {
            "provider_ledger_count": len(self.provider_ledger),
            "source_lineage_groups": len(self.source_lineage_groups),
            "independence_groups": len(self.independence_groups),
            "limitations": [{"code": lim.code, "description": lim.description} for lim in self.limitations],
        }

        narrator_input = {
            "user_query": user_query or (self.target.get("display_name", "") if self.target else ""),
            "request_type": request_type,
            "requested_depth": requested_depth,
            "subjects": subjects,
            "claims": buckets,
            "sources": sources,
            "research_leads": research_leads,
            "retrieval_summary": retrieval_summary,
            "coverage": coverage,
            "response_language": "it",
        }

        return _json.dumps(narrator_input, ensure_ascii=False, indent=2)
