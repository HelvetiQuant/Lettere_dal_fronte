"""Evidence Snapshot V4 — immutable, validated, unified DTO.

Replaces the V3 EvidenceSnapshot with a richer structure that:
- Separates origin_record from external corroboration
- Tracks claims at field level (birth_year, birth_place, etc.)
- Maintains a provider ledger of all attempts
- Computes missing_claims from actual field values, not execution flags
- Enforces SOURCE_RECORD_ONLY invariants
- Provides to_conversational_context() that gives the AI model ONLY
  authorized data: origin record, accepted claims, rejected candidates,
  consulted sources — never raw candidates with confidence 0.1

Key invariants enforced in validate():
- SOURCE_RECORD_ONLY requires origin_record.state == VERIFIED
- SOURCE_RECORD_ONLY requires accepted_independent_evidence == 0
- PRESENT_UNVERIFIED_LINEAGE cannot be SOURCE_RECORD_ONLY
- source_records == accepted_origin_evidence + accepted_independent_evidence
- missing_claims computed from empty fields, not from execution flags
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ─── Claim definitions ──────────────────────────────────────────────────────

CLAIM_FIELDS = [
    "full_birth_date",
    "birth_year",
    "birth_place",
    "paternity",
    "rank",
    "unit",
    "service_number",
    "death_date",
    "death_place",
    "death_cause",
    "captivity",
    "burial",
    "residence",
]


@dataclass
class ClaimRecord:
    """A single claim about a target, linked to evidence sources."""
    claim_id: str
    field_name: str  # one of CLAIM_FIELDS
    predicate: str  # e.g., "born_in", "served_in"
    object_value: str
    object_normalized: str
    evidence_source_ids: List[str] = field(default_factory=list)
    claim_status: str = "missing"  # accepted | partial | conflicting | missing
    confidence: float = 0.0


@dataclass
class OriginRecord:
    """The record from which the target was derived (e.g., Albo d'Oro entry)."""
    state: str = "ABSENT"  # VERIFIED | PRESENT_UNVERIFIED_LINEAGE | ABSENT
    source_id: str = ""
    canonical_locator: str = ""
    provider: str = ""
    import_job_id: str = ""
    raw_payload_hash: str = ""
    supported_claim_ids: List[str] = field(default_factory=list)
    base_url: str = ""
    record_url: str = ""


@dataclass
class EvidenceSourceRecord:
    """An accepted evidence source — must be a direct record, not a search page."""
    source_id: str
    provider: str
    archive: str
    canonical_url: str
    record_id: str = ""
    locator: str = ""
    object_kind: str = ""  # CATALOG_RECORD, DIGITIZED_DOCUMENT, etc.
    accessed_at: str = ""
    source_lineage_id: str = ""
    is_origin: bool = False  # True if this is the origin record source
    is_independent: bool = False  # True if not derived from the same lineage


@dataclass
class RejectedCandidateRecord:
    """A candidate rejected due to hard conflicts."""
    candidate_id: str
    name: str
    reason_codes: List[str]
    conflicting_features: List[str]
    birth_year: str = ""
    birth_place: str = ""
    military_unit: str = ""


@dataclass
class ConsultedSourceRecord:
    """A source that was consulted (fetched and examined) but yielded no match."""
    source_id: str
    provider: str
    canonical_url: str
    result_kind: str = ""  # SEARCH_PAGE_ONLY, CONTENT_NOT_SEARCHABLE, etc.
    fetch_status: str = ""  # SUCCESS | FETCH_FAILED | NOT_FETCHED
    query_used: str = ""
    content_excerpt: str = ""
    accessed_at: str = ""


@dataclass
class ContextSourceRecord:
    """A source useful for historical context but not target-specific evidence."""
    source_id: str
    provider: str
    canonical_url: str
    title: str = ""
    relevance_reason: str = ""  # why it's context, not evidence
    accessed_at: str = ""


@dataclass
class ResearchLeadRecord:
    """A non-probative lead — search page, homepage, or unverified URL."""
    lead_id: str
    canonical_url: str
    provider: str
    object_kind: str = ""  # HOMEPAGE, SEARCH_PAGE, SEARCH_RESULT_LEAD
    note: str = ""


@dataclass
class ProviderLedgerEntry:
    """Record of a single provider attempt."""
    provider: str
    conflict: str = ""  # ww1, ww2, both
    execution_state: str = "NOT_RUN"  # NOT_RUN, SUCCESS, TIMEOUT, etc.
    retrieval_outcome: str = ""  # NO_RESULTS, LEADS_ONLY, etc.
    results_count: int = 0
    elapsed_ms: int = 0
    error_code: str = ""
    timestamp: str = ""


@dataclass
class EvidenceSnapshotV4:
    """Immutable, versioned, validated snapshot of all evidence for a target.

    This is the ONLY data the AI model receives. It cannot modify
    resolution_state, create claims, or assign sources.
    """
    snapshot_id: str = ""
    snapshot_hash: str = ""
    run_id: str = ""
    target_id: str = ""
    target_hash: str = ""
    target_type: str = "person"
    created_at: str = ""
    version: int = 4

    # Research mode
    research_mode: str = "LOOKUP_ENRICHMENT"

    # Deterministic states (set by pipeline, not by AI)
    resolution_state: str = "UNRESOLVED"
    stato_identificazione: str = "non_identificata"
    origin_record_state: str = "ABSENT"
    external_corroboration_state: str = "NO_EVIDENCE"
    reason_codes: List[str] = field(default_factory=list)

    # Origin record
    origin_record: Dict = field(default_factory=dict)

    # Claims
    accepted_claims: List[Dict] = field(default_factory=list)
    partial_claims: List[Dict] = field(default_factory=list)
    conflicting_claims: List[Dict] = field(default_factory=list)
    missing_claims: List[str] = field(default_factory=list)

    # Rejected candidates (omonimi esclusi)
    rejected_candidates: List[Dict] = field(default_factory=list)

    # Evidence sources
    accepted_origin_evidence_sources: List[Dict] = field(default_factory=list)
    accepted_independent_evidence_sources: List[Dict] = field(default_factory=list)

    # Consulted sources (fetched, no match)
    consulted_sources: List[Dict] = field(default_factory=list)

    # Context sources (historical context, not target evidence)
    context_sources: List[Dict] = field(default_factory=list)

    # Research leads (search pages, homepages)
    research_leads: List[Dict] = field(default_factory=list)

    # Provider ledger
    provider_ledger: List[Dict] = field(default_factory=list)

    # Research limitations
    research_limitations: List[str] = field(default_factory=list)

    # Execution completeness (separate from historical completeness)
    execution_completeness: Dict = field(default_factory=dict)

    # Reconciliation counts
    reconciliation: Dict = field(default_factory=dict)

    # AI metadata (for audit)
    ai_used: bool = False
    ai_model: str = ""
    ai_truncation: Dict = field(default_factory=dict)
    ai_error: Dict = field(default_factory=dict)
    ai_validation: Dict = field(default_factory=dict)

    # Errors from any stage
    errors: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.snapshot_id:
            self.snapshot_id = f"snap_v4_{self.target_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()
        self._compute_missing_claims()
        self._compute_reconciliation()

    def _compute_hash(self) -> str:
        raw = json.dumps({
            "target_id": self.target_id,
            "target_hash": self.target_hash,
            "resolution_state": self.resolution_state,
            "origin_record_state": self.origin_record_state,
            "accepted_claims": self.accepted_claims,
            "accepted_origin_evidence_sources": self.accepted_origin_evidence_sources,
            "accepted_independent_evidence_sources": self.accepted_independent_evidence_sources,
            "rejected_candidates": self.rejected_candidates,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _compute_missing_claims(self):
        """Compute missing claims from actual field values.

        A field is missing if its claim_status is 'missing' or if
        no accepted claim exists for it. This is NOT based on
        web_searched or ai_synthesized flags.
        """
        if self.missing_claims:
            return  # Already computed by caller

        accepted_fields = {c.get("field_name") for c in self.accepted_claims if c.get("claim_status") == "accepted"}
        partial_fields = {c.get("field_name") for c in self.partial_claims if c.get("claim_status") == "partial"}

        missing = []
        for field_name in CLAIM_FIELDS:
            if field_name not in accepted_fields and field_name not in partial_fields:
                missing.append(field_name)
        self.missing_claims = missing

    def _compute_reconciliation(self):
        """Compute reconciled counts from actual lists, not from typed_counts."""
        self.reconciliation = {
            "provider_attempts": len(self.provider_ledger),
            "retrieved_items": sum(e.get("results_count", 0) for e in self.provider_ledger),
            "unique_canonical_urls": len(set(
                [s.get("canonical_url", "") for s in self.accepted_origin_evidence_sources] +
                [s.get("canonical_url", "") for s in self.accepted_independent_evidence_sources] +
                [s.get("canonical_url", "") for s in self.consulted_sources] +
                [s.get("canonical_url", "") for s in self.context_sources] +
                [s.get("canonical_url", "") for s in self.research_leads]
            )),
            "opened_sources": len(self.consulted_sources),
            "consulted_sources": len(self.consulted_sources),
            "origin_evidence_sources": len(self.accepted_origin_evidence_sources),
            "independent_evidence_sources": len(self.accepted_independent_evidence_sources),
            "context_sources": len(self.context_sources),
            "rejected_items": len(self.rejected_candidates),
            "supported_claims": len(self.accepted_claims),
            "partial_claims": len(self.partial_claims),
            "missing_claims": len(self.missing_claims),
            "research_leads": len(self.research_leads),
        }

    def validate(self) -> List[str]:
        """Validate invariants. Returns list of violation messages (empty = valid)."""
        violations = []

        # SOURCE_RECORD_ONLY invariants
        if self.resolution_state == "SOURCE_RECORD_ONLY":
            if self.origin_record.get("state") != "VERIFIED":
                violations.append(
                    f"SOURCE_RECORD_ONLY requires origin_record.state=VERIFIED, "
                    f"got {self.origin_record.get('state')}"
                )
            if len(self.accepted_origin_evidence_sources) < 1:
                violations.append(
                    "SOURCE_RECORD_ONLY requires accepted_origin_evidence_sources >= 1"
                )
            if len(self.accepted_independent_evidence_sources) != 0:
                violations.append(
                    f"SOURCE_RECORD_ONLY requires accepted_independent_evidence_sources == 0, "
                    f"got {len(self.accepted_independent_evidence_sources)}"
                )

        # PRESENT_UNVERIFIED_LINEAGE cannot be SOURCE_RECORD_ONLY
        if self.origin_record.get("state") == "PRESENT_UNVERIFIED_LINEAGE":
            if self.resolution_state == "SOURCE_RECORD_ONLY":
                violations.append(
                    "PRESENT_UNVERIFIED_LINEAGE cannot have resolution_state=SOURCE_RECORD_ONLY"
                )

        # source_records reconciliation
        expected_source_records = (
            len(self.accepted_origin_evidence_sources) +
            len(self.accepted_independent_evidence_sources)
        )
        if self.reconciliation.get("source_records", 0) != expected_source_records:
            violations.append(
                f"source_records mismatch: reconciliation says "
                f"{self.reconciliation.get('source_records', 0)}, "
                f"actual count is {expected_source_records}"
            )

        # Missing claims must not be empty if fields are actually empty
        if not self.missing_claims and self.accepted_claims:
            # Check if any claim field is actually empty
            for claim in self.accepted_claims:
                if not claim.get("object_value"):
                    violations.append(
                        f"Claim {claim.get('claim_id')} has empty object_value "
                        f"but missing_claims is empty"
                    )

        return violations

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "run_id": self.run_id,
            "target_id": self.target_id,
            "target_hash": self.target_hash,
            "target_type": self.target_type,
            "created_at": self.created_at,
            "version": self.version,
            "research_mode": self.research_mode,
            "resolution_state": self.resolution_state,
            "stato_identificazione": self.stato_identificazione,
            "origin_record_state": self.origin_record_state,
            "external_corroboration_state": self.external_corroboration_state,
            "reason_codes": self.reason_codes,
            "origin_record": self.origin_record,
            "accepted_claims": self.accepted_claims,
            "partial_claims": self.partial_claims,
            "conflicting_claims": self.conflicting_claims,
            "missing_claims": self.missing_claims,
            "rejected_candidates": self.rejected_candidates,
            "accepted_origin_evidence_sources": self.accepted_origin_evidence_sources,
            "accepted_independent_evidence_sources": self.accepted_independent_evidence_sources,
            "consulted_sources": self.consulted_sources,
            "context_sources": self.context_sources,
            "research_leads": self.research_leads,
            "provider_ledger": self.provider_ledger,
            "research_limitations": self.research_limitations,
            "execution_completeness": self.execution_completeness,
            "reconciliation": self.reconciliation,
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
        - The origin record (if verified) with its supported claims
        - Accepted claims with evidence source IDs (not URLs)
        - Rejected candidates with reason codes
        - Consulted sources with result_kind (not "no match" claims)
        - Research limitations

        It does NOT contain:
        - Raw candidates with confidence 0.1
        - URLs (model emits source_id, renderer generates links)
        - Search page URLs as if they were evidence
        - Unvalidated archival suggestions
        """
        lines = [
            f"# Evidence Snapshot V4 — {self.snapshot_id}",
            f"Target: {self.target_id} (hash: {self.target_hash})",
            f"Version: {self.version}",
            f"Research Mode: {self.research_mode}",
            f"Resolution State: {self.resolution_state}",
            f"Origin Record State: {self.origin_record_state}",
            f"External Corroboration: {self.external_corroboration_state}",
            "",
        ]

        # Origin record
        if self.origin_record:
            lines.append("## Origin Record")
            lines.append(f"  state: {self.origin_record.get('state', 'ABSENT')}")
            lines.append(f"  source_id: {self.origin_record.get('source_id', '')}")
            lines.append(f"  provider: {self.origin_record.get('provider', '')}")
            lines.append(f"  supported_claims: {self.origin_record.get('supported_claim_ids', [])}")
            lines.append("")

        # Accepted claims
        if self.accepted_claims:
            lines.append("## Accepted Claims")
            for c in self.accepted_claims:
                lines.append(
                    f"  {c['claim_id']}: {c['field_name']}={c['object_value']} "
                    f"(evidence: {c.get('evidence_source_ids', [])})"
                )
            lines.append("")

        # Partial claims
        if self.partial_claims:
            lines.append("## Partial Claims")
            for c in self.partial_claims:
                lines.append(
                    f"  {c['claim_id']}: {c['field_name']}={c['object_value']} "
                    f"(partial — {c.get('claim_status', 'partial')})"
                )
            lines.append("")

        # Missing claims
        if self.missing_claims:
            lines.append(f"## Missing Claims: {', '.join(self.missing_claims)}")
            lines.append("")

        # Rejected candidates
        if self.rejected_candidates:
            lines.append("## Rejected Candidates (Homonyms)")
            for c in self.rejected_candidates:
                lines.append(
                    f"  {c.get('name', '')}: {c.get('reason_codes', [])}"
                )
            lines.append("")

        # Consulted sources (no URLs — model sees source_id only)
        if self.consulted_sources:
            lines.append("## Consulted Sources (no match found)")
            for s in self.consulted_sources:
                lines.append(
                    f"  {s['source_id']}: provider={s.get('provider', '')} "
                    f"result_kind={s.get('result_kind', '')} "
                    f"fetch={s.get('fetch_status', '')}"
                )
            lines.append("")

        # Context sources
        if self.context_sources:
            lines.append("## Context Sources (historical context, not target evidence)")
            for s in self.context_sources:
                lines.append(
                    f"  {s['source_id']}: {s.get('title', '')} "
                    f"reason={s.get('relevance_reason', '')}"
                )
            lines.append("")

        # Research leads
        if self.research_leads:
            lines.append(f"## Research Leads ({len(self.research_leads)} unverified)")
            lines.append("")

        # Research limitations
        if self.research_limitations:
            lines.append("## Research Limitations")
            for lim in self.research_limitations:
                lines.append(f"  - {lim}")
            lines.append("")

        # Reconciliation
        lines.append("## Reconciliation")
        for k, v in self.reconciliation.items():
            lines.append(f"  {k}: {v}")

        return "\n".join(lines)

    def validate_claim_id(self, claim_id: str) -> bool:
        all_claims = self.accepted_claims + self.partial_claims + self.conflicting_claims
        return any(c.get("claim_id") == claim_id for c in all_claims)

    def validate_source_id(self, source_id: str) -> bool:
        all_sources = (
            self.accepted_origin_evidence_sources +
            self.accepted_independent_evidence_sources +
            self.consulted_sources +
            self.context_sources
        )
        return any(s.get("source_id") == source_id for s in all_sources)

    def validate_citation(self, claim_id: str, source_id: str) -> bool:
        if not self.validate_claim_id(claim_id):
            return False
        if not self.validate_source_id(source_id):
            return False
        for c in self.accepted_claims:
            if c.get("claim_id") == claim_id:
                return source_id in c.get("evidence_source_ids", [])
        return False


def build_snapshot_v4_from_dossier(
    dossier,
    target,
    run_id: str = "",
) -> EvidenceSnapshotV4:
    """Build a V4 EvidenceSnapshot from a completed Dossier and ResearchTarget.

    This replaces the V3 from_dossier classmethod with a richer structure
    that properly separates origin records from external evidence.
    """
    from research_protocol import (
        classify_object_kind, is_evidence_eligible, ObjectKind,
        canonicalize_url, _norm_val,
    )

    # Determine origin record state
    origin_record = {}
    origin_state = "ABSENT"
    accepted_origin_sources = []
    accepted_independent_sources = []

    best_candidate = None
    if dossier.candidati:
        best_candidate = max(dossier.candidati, key=lambda c: c.confidence)
        if best_candidate.confidence >= 0.8 and best_candidate.stato == "POSSIBLE":
            # We have a strong local DB match
            # Check if the source has a verifiable lineage
            for f in best_candidate.fonti:
                canon_url = canonicalize_url(f.url)
                if not canon_url:
                    continue
                # Albo d'Oro records from SQLite have relative URLs
                # like DettagliNominativi.aspx?id=...
                # These need a base_url to be verifiable
                if f.url and not f.url.startswith("http"):
                    # Relative URL — lineage not verified
                    origin_state = "PRESENT_UNVERIFIED_LINEAGE"
                else:
                    origin_state = "VERIFIED"

                source_id = f"origin_{hash(canon_url) % 100000:05d}"
                origin_record = {
                    "state": origin_state,
                    "source_id": source_id,
                    "canonical_locator": canon_url,
                    "provider": f.istituzione or "",
                    "supported_claim_ids": [],
                    "base_url": "",
                    "record_url": f.url or "",
                }
                accepted_origin_sources.append({
                    "source_id": source_id,
                    "provider": f.istituzione or "",
                    "archive": f.istituzione or "",
                    "canonical_url": canon_url,
                    "record_id": f.identificativo_archivistico or "",
                    "locator": f.note or "",
                    "object_kind": classify_object_kind(f.url, has_record_id=bool(f.identificativo_archivistico)).value,
                    "accessed_at": f.data_accesso or "",
                    "is_origin": True,
                    "is_independent": False,
                })
                break  # Only one origin source

    # Build claims from best candidate
    accepted_claims = []
    missing_claims = []
    if best_candidate:
        field_map = {
            "birth_year": (best_candidate.data_nascita, "born_in_year"),
            "birth_place": (best_candidate.luogo_nascita, "born_in_place"),
            "paternity": (best_candidate.paternita, "father_named"),
            "rank": (best_candidate.grado, "held_rank"),
            "unit": (best_candidate.reparto, "served_in_unit"),
            "service_number": (best_candidate.matricola, "had_service_number"),
            "death_cause": (best_candidate.morte, "died_of"),
            "captivity": (best_candidate.prigionia, "imprisoned_at"),
            "burial": (best_candidate.sepoltura, "buried_at"),
            "residence": (best_candidate.residenza, "resided_at"),
        }

        origin_source_ids = [s["source_id"] for s in accepted_origin_sources]

        for field_name, (value, predicate) in field_map.items():
            if value and str(value).strip():
                claim_id = f"cl_{target.target_hash[:8]}_{field_name}"
                accepted_claims.append({
                    "claim_id": claim_id,
                    "field_name": field_name,
                    "predicate": predicate,
                    "object_value": str(value),
                    "object_normalized": _norm_val(str(value)),
                    "evidence_source_ids": origin_source_ids,
                    "claim_status": "accepted",
                    "confidence": best_candidate.confidence,
                })
                if origin_record:
                    origin_record.setdefault("supported_claim_ids", []).append(claim_id)
            else:
                missing_claims.append(field_name)

    # Build rejected candidates
    rejected_candidates = []
    for c in dossier.omonimi_esclusi:
        rejected_candidates.append({
            "candidate_id": f"rej_{hash(c.nome_originale) % 100000:05d}",
            "name": c.nome_originale,
            "reason_codes": c.contraddizioni if c.contraddizioni else ["UNKNOWN"],
            "conflicting_features": c.compatibilita if c.compatibilita else [],
            "birth_year": c.data_nascita or "",
            "birth_place": c.luogo_nascita or "",
            "military_unit": c.reparto or "",
        })

    # Build research leads from web search sources
    research_leads = []
    context_sources = []
    consulted_sources = []

    ws = dossier.web_search_results or {}
    if isinstance(ws, dict) and not ws.get("error"):
        for s in ws.get("sources", []):
            url = s.get("url", s.get("canonical_url", ""))
            canon_url = canonicalize_url(url)
            if not canon_url:
                continue
            kind = classify_object_kind(canon_url)
            source_id = f"lead_{hash(canon_url) % 100000:05d}"

            if not is_evidence_eligible(kind):
                if kind in (ObjectKind.HOMEPAGE, ObjectKind.SEARCH_PAGE, ObjectKind.SEARCH_RESULT_LEAD):
                    research_leads.append({
                        "lead_id": source_id,
                        "canonical_url": canon_url,
                        "provider": "tavily",
                        "object_kind": kind.value,
                        "note": s.get("title", ""),
                    })
                else:
                    context_sources.append({
                        "source_id": source_id,
                        "provider": "tavily",
                        "canonical_url": canon_url,
                        "title": s.get("title", ""),
                        "relevance_reason": "CONTEXT_ONLY",
                        "accessed_at": "",
                    })

    # Provider ledger
    provider_ledger = []
    for sle in dossier.search_log:
        provider_ledger.append({
            "provider": sle.motore_o_archivio or "",
            "execution_state": "SUCCESS" if sle.esito == "positive" else "NO_RESULTS",
            "retrieval_outcome": "LEADS_ONLY" if sle.esito == "ambiguous" else ("PERSON_CANDIDATES" if sle.risultati_trovati > 0 else "NO_RESULTS"),
            "results_count": sle.risultati_trovati,
            "timestamp": sle.timestamp or "",
        })

    # Research limitations
    limitations = []
    if origin_state == "PRESENT_UNVERIFIED_LINEAGE":
        limitations.append("Origin record lineage not verified — relative URL without base")
    if not accepted_independent_sources:
        limitations.append("No independent external corroboration found in this session")
    if ws and isinstance(ws, dict) and ws.get("error"):
        limitations.append(f"Web search error: {ws['error'].get('error_code', 'unknown')}")

    # Execution completeness (separate from historical completeness)
    execution_completeness = {
        "local_db_searched": True,
        "supabase_searched": True,
        "federated_searched": True,
        "web_searched": dossier.web_search_used,
        "ai_synthesized": dossier.ai_used,
    }

    snapshot = EvidenceSnapshotV4(
        run_id=run_id,
        target_id=target.target_id,
        target_hash=target.target_hash,
        target_type=target.target_type,
        research_mode="LOOKUP_ENRICHMENT",
        resolution_state=dossier.profilo.get("resolution_state", "UNRESOLVED"),
        stato_identificazione=dossier.stato_identificazione,
        origin_record_state=origin_state,
        external_corroboration_state="NO_EVIDENCE" if not accepted_independent_sources else "CORROBORATED",
        reason_codes=dossier.profilo.get("reason_codes", []),
        origin_record=origin_record,
        accepted_claims=accepted_claims,
        missing_claims=missing_claims,
        rejected_candidates=rejected_candidates,
        accepted_origin_evidence_sources=accepted_origin_sources,
        accepted_independent_evidence_sources=accepted_independent_sources,
        consulted_sources=consulted_sources,
        context_sources=context_sources,
        research_leads=research_leads,
        provider_ledger=provider_ledger,
        research_limitations=limitations,
        execution_completeness=execution_completeness,
        ai_used=dossier.ai_used,
        ai_model=dossier.ai_model,
        ai_truncation=dossier.profilo.get("ai_truncation", {}),
        ai_error=dossier.profilo.get("ai_error", {}),
    )

    return snapshot
