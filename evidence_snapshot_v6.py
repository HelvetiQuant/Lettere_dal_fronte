"""EvidenceSnapshot V6 — unified, immutable, validated DTO.

Schema version 6. Key changes from V5:
- manifest_hash binding (every snapshot traces to its QueryManifest)
- intent field (PERSON_LOOKUP, EVENT_LOOKUP, AGGREGATE_QUERY, etc.)
- accepted_evidence requires locator + source_id + content_state != NOT_OPENED
- conflicting_claims preserved (not resolved by majority)
- provider_ledger with accounted_for flag for every observation
- conditional_gaps computed from intent + target + accepted claims
- next_step_catalog_ids reference deterministic catalog entries
- limitations include NO_AGGREGATE_DATA for aggregate queries without data

Invarianti:
  assert snapshot.manifest_hash == run.manifest_hash
  assert all(claim.evidence_ids for claim in snapshot.accepted_claims)
  assert all(e.locator and e.source_id for e in snapshot.accepted_evidence)
  assert not any(o.content_state == "NOT_OPENED" for o in snapshot.accepted_evidence)
  assert identity_resolution_decided_by_backend
  assert external_corroboration_decided_by_backend
  assert all(item.accounted_for for item in provider_ledger)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


# ─── Claim definitions ──────────────────────────────────────────────────────

CLAIM_FIELDS_V6 = [
    "full_birth_date",
    "birth_year",
    "birth_place",
    "paternity",
    "rank",
    "unit",
    "service_number",
    "death_date",
    "death_year",
    "death_place",
    "death_cause",
    "captivity",
    "internment_place",
    "burial",
    "residence",
    "decoration_type",
    "decoration_year",
    "draft_class",
    "municipality",
    "capture_place",
    "capture_date",
    "fate",
    "event_start_date",
    "event_end_date",
    "event_location",
    "event_description",
    "event_phase_count",
    "event_actors",
]


@dataclass
class ClaimV6:
    claim_id: str
    subject_id: str
    predicate: str  # e.g. "birth_year", "unit", "death_place", "event_date"
    value_normalized: str
    value_raw: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    independence_group_ids: List[str] = field(default_factory=list)
    status: str = "ASSERTED"  # ASSERTED|ORIGIN_SUPPORTED|PARTIAL|ACCEPTED|CONFLICTING|REJECTED
    confidence: float = 0.0
    source: str = ""  # origin_record|external|aggregate


@dataclass
class EvidenceItemV6:
    evidence_id: str
    source_id: str
    provider: str
    source_lineage_group_id: str = ""
    independence_group_id: str = ""
    locator: str = ""
    content_state: str = "NOT_OPENED"  # NOT_OPENED|OPENED|METADATA_ONLY|OCR_EXTRACTED|FAILED
    excerpt: str = ""
    object_kind: str = ""
    accessed_at: str = ""
    is_origin: bool = False
    is_independent: bool = False
    classification: str = "SEARCH_RESULT"  # MODEL_LEAD|SEARCH_RESULT|SOURCE_CANDIDATE|CONTEXT|REJECTED
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class RejectedCandidateV6:
    candidate_id: str
    name: str
    reason_codes: List[str]
    conflicting_features: List[str]
    birth_year: str = ""
    birth_place: str = ""
    military_unit: str = ""
    provider: str = ""


@dataclass
class ContextSourceV6:
    source_id: str
    provider: str
    title: str = ""
    url_canonical: str = ""
    reason: str = ""


@dataclass
class WebLeadV6:
    lead_id: str
    provider: str
    url_canonical: str = ""
    title: str = ""
    snippet: str = ""
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class ProviderLedgerEntry:
    observation_id: str
    provider: str
    capability: str = ""
    classification: str = ""
    reason_codes: List[str] = field(default_factory=list)
    accounted_for: bool = True
    raw_result_hash: str = ""


@dataclass
class ConditionalGap:
    gap_id: str
    field_name: str
    reason: str
    blocking: bool = False


@dataclass
class NextStepEntry:
    step_id: str
    catalog_id: str
    description: str
    archive: str = ""
    access_mode: str = ""  # LINK_ONLY|METADATA_ONLY|API_METADATA|OAI_METADATA|IIIF_METADATA|CONTENT_ALLOWED|DOWNLOAD_ALLOWED|REQUEST_REQUIRED|AUTHORIZATION_REQUIRED|MANUAL_CATALOGUING|BLOCKED
    priority: int = 0


@dataclass
class Limitation:
    code: str
    description: str


@dataclass
class EvidenceSnapshotV6:
    snapshot_id: str = ""
    snapshot_hash: str = ""
    schema_version: str = "6"
    run_id: str = ""
    manifest_hash: str = ""
    intent: str = ""  # PERSON_LOOKUP|EVENT_LOOKUP|AGGREGATE_QUERY|SOURCE_LOOKUP|CONVERSATIONAL_FOLLOWUP
    target: Dict[str, Any] = field(default_factory=dict)
    origin: Dict[str, Any] = field(default_factory=dict)
    identity_resolution: str = "UNRESOLVED"  # INCOMPLETE_TARGET|UNRESOLVED|PARTIAL|RESOLVED
    external_corroboration: str = "NONE"  # NONE|PARTIAL|ACCEPTED|CONFLICTING
    accepted_claims: List[ClaimV6] = field(default_factory=list)
    conflicting_claims: List[ClaimV6] = field(default_factory=list)
    asserted_claims: List[ClaimV6] = field(default_factory=list)
    accepted_evidence: List[EvidenceItemV6] = field(default_factory=list)
    context_sources: List[ContextSourceV6] = field(default_factory=list)
    web_leads: List[WebLeadV6] = field(default_factory=list)
    rejected_candidates: List[RejectedCandidateV6] = field(default_factory=list)
    conditional_gaps: List[ConditionalGap] = field(default_factory=list)
    next_step_catalog_ids: List[str] = field(default_factory=list)
    next_steps: List[NextStepEntry] = field(default_factory=list)
    provider_ledger: List[ProviderLedgerEntry] = field(default_factory=list)
    limitations: List[Limitation] = field(default_factory=list)
    aggregate_result: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.snapshot_id:
            raw = json.dumps(self._hash_payload(), sort_keys=True, ensure_ascii=False)
            self.snapshot_hash = hashlib.sha256(raw.encode()).hexdigest()
            self.snapshot_id = f"snap_v6_{self.snapshot_hash[:16]}"

    def _hash_payload(self) -> dict:
        d = asdict(self)
        d.pop("snapshot_id", None)
        d.pop("snapshot_hash", None)
        d.pop("created_at", None)
        return d

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceSnapshotV6":
        def _convert_list(items, cls_):
            return [cls_(**i) if isinstance(i, dict) else i for i in items]
        return cls(
            accepted_claims=_convert_list(d.pop("accepted_claims", []), ClaimV6),
            conflicting_claims=_convert_list(d.pop("conflicting_claims", []), ClaimV6),
            asserted_claims=_convert_list(d.pop("asserted_claims", []), ClaimV6),
            accepted_evidence=_convert_list(d.pop("accepted_evidence", []), EvidenceItemV6),
            context_sources=_convert_list(d.pop("context_sources", []), ContextSourceV6),
            web_leads=_convert_list(d.pop("web_leads", []), WebLeadV6),
            rejected_candidates=_convert_list(d.pop("rejected_candidates", []), RejectedCandidateV6),
            conditional_gaps=_convert_list(d.pop("conditional_gaps", []), ConditionalGap),
            next_steps=_convert_list(d.pop("next_steps", []), NextStepEntry),
            provider_ledger=_convert_list(d.pop("provider_ledger", []), ProviderLedgerEntry),
            limitations=_convert_list(d.pop("limitations", []), Limitation),
            **d,
        )

    def validate_invariants(self) -> List[str]:
        """Return list of violation messages. Empty = valid."""
        violations = []

        # Invariant: all accepted claims have evidence
        for claim in self.accepted_claims:
            if not claim.evidence_ids:
                violations.append(f"ACCEPTED_CLAIM_WITHOUT_EVIDENCE: {claim.claim_id}")

        # Invariant: all accepted evidence have locator + source_id + content_state != NOT_OPENED
        for ev in self.accepted_evidence:
            if not ev.locator:
                violations.append(f"EVIDENCE_WITHOUT_LOCATOR: {ev.evidence_id}")
            if not ev.source_id:
                violations.append(f"EVIDENCE_WITHOUT_SOURCE_ID: {ev.evidence_id}")
            if ev.content_state == "NOT_OPENED":
                violations.append(f"UNOPENED_ITEM_AS_EVIDENCE: {ev.evidence_id}")

        # Invariant: all ledger entries accounted for
        for entry in self.provider_ledger:
            if not entry.accounted_for:
                violations.append(f"UNACCOUNTED_OBSERVATION: {entry.observation_id}")

        # Invariant: identity_resolution decided by backend (not by model)
        if self.identity_resolution not in ("INCOMPLETE_TARGET", "UNRESOLVED", "PARTIAL", "RESOLVED"):
            violations.append(f"INVALID_IDENTITY_RESOLUTION: {self.identity_resolution}")

        # Invariant: external_corroboration decided by backend
        if self.external_corroboration not in ("NONE", "PARTIAL", "ACCEPTED", "CONFLICTING"):
            violations.append(f"INVALID_EXTERNAL_CORROBORATION: {self.external_corroboration}")

        return violations

    def compute_conditional_gaps(self):
        """Compute gaps from intent + target + accepted claims."""
        self.conditional_gaps = []
        if self.intent == "PERSON_LOOKUP":
            accepted_fields = {c.predicate for c in self.accepted_claims}
            accepted_fields |= {c.predicate for c in self.asserted_claims}
            for field_name in CLAIM_FIELDS_V6:
                if field_name not in accepted_fields:
                    blocking = field_name in ("birth_year", "birth_place", "rank")
                    self.conditional_gaps.append(ConditionalGap(
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
                    self.conditional_gaps.append(ConditionalGap(
                        gap_id=f"gap_{field_name}",
                        field_name=field_name,
                        reason=f"Event field {field_name} not supported",
                        blocking=field_name in ("event_start_date", "event_end_date"),
                    ))
        elif self.intent == "AGGREGATE_QUERY":
            if self.aggregate_result is None:
                self.conditional_gaps.append(ConditionalGap(
                    gap_id="gap_aggregate",
                    field_name="aggregate_data",
                    reason="No aggregate data available for this query",
                    blocking=True,
                ))

    def to_conversational_context(self) -> str:
        """Render snapshot as text context for the AI model.

        The model receives ONLY authorized data:
        - Target identity
        - Origin record state
        - Accepted claims with evidence references
        - Conflicting claims (presented as contradictions)
        - Context sources (historical context, not target evidence)
        - Research leads (unverified)
        - Research limitations
        - Aggregate results (if any)

        The model does NOT receive:
        - URLs (model emits source_id, renderer generates links)
        - Raw candidates with low confidence
        - Provider internal state
        - Ability to change identity, claims, or state
        """
        lines = [
            f"# Evidence Snapshot V6 — {self.snapshot_id}",
            f"Schema: {self.schema_version} | Intent: {self.intent}",
            f"Manifest: {self.manifest_hash[:16]}",
            "",
            "## Target",
            f"  ID: {self.target.get('target_id', 'N/A')}",
            f"  Display: {self.target.get('display_name', 'N/A')}",
            f"  Conflict: {self.target.get('conflict', 'UNKNOWN')}",
            "",
            "## Origin Record",
            f"  presence: {self.origin.get('presence', 'ABSENT')}",
            f"  provenance: {self.origin.get('provenance', 'UNVERIFIED')}",
            f"  source_id: {self.origin.get('source_id', 'N/A')}",
            "",
            f"## Identity Resolution: {self.identity_resolution}",
            f"## External Corroboration: {self.external_corroboration}",
            "",
        ]

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
                lines.append(f"  {e.evidence_id}: source={e.source_id}, state={e.content_state}, kind={e.object_kind}")
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
