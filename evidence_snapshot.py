"""Evidence Snapshot — immutable, versioned snapshot of accepted evidence.

Before generating a conversational GPT report, an EvidenceSnapshot is created
from the deterministic backend results. The snapshot is immutable and versioned.

The GPT conversational report can ONLY reference claims and evidence from the
snapshot. It cannot modify resolution_state, create claims, or assign sources.

Key invariants:
- snapshot_hash is deterministic and changes when evidence/states change
- GPT cannot modify resolution_state or create claims
- All cited claim_ids and evidence_source_ids must exist in the snapshot
- Rejected candidates appear only in "rejected_candidates" section
- Search pages/homepages appear only in "research_leads", never in evidence
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class AcceptedClaim:
    """A claim supported by accepted evidence."""
    claim_id: str
    predicate: str  # e.g., "born_in", "served_in", "died_on"
    object_value: str
    object_normalized: str
    evidence_source_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    claim_status: str = "accepted"  # accepted | conflicting | uncertain


@dataclass
class AcceptedEvidenceSource:
    """An accepted evidence source — must be a direct record, not a search page."""
    source_id: str
    provider: str
    archive: str
    url: str
    record_id: str
    locator: str  # page, image, section
    object_kind: str  # CATALOG_RECORD, DIGITIZED_DOCUMENT, etc.
    accessed_at: str
    source_lineage_id: str = ""


@dataclass
class RejectedCandidate:
    """A candidate rejected due to hard conflicts — shown only in 'omonimi esclusi'."""
    candidate_id: str
    name: str
    reason_codes: List[str]
    conflicting_features: List[str]
    birth_year: str = ""
    birth_place: str = ""
    military_unit: str = ""


@dataclass
class ResearchLead:
    """A non-probative lead — search page, homepage, or unverified URL."""
    lead_id: str
    url: str
    provider: str
    object_kind: str  # HOMEPAGE, SEARCH_PAGE, SEARCH_RESULT_LEAD
    note: str = ""


@dataclass
class EvidenceSnapshot:
    """Immutable, versioned snapshot of all accepted evidence for a target.

    Created BEFORE GPT report generation. GPT can only read from this snapshot.
    """
    snapshot_id: str = ""
    snapshot_hash: str = ""
    run_id: str = ""
    target_id: str = ""
    target_hash: str = ""
    target_type: str = "person"
    created_at: str = ""

    # States from deterministic backend
    states: Dict = field(default_factory=dict)

    # Accepted evidence and claims
    accepted_claims: List[Dict] = field(default_factory=list)
    conflicting_claims: List[Dict] = field(default_factory=list)
    uncertain_observations: List[Dict] = field(default_factory=list)

    # Rejected candidates (omonimi esclusi)
    rejected_candidates: List[Dict] = field(default_factory=list)

    # Accepted evidence sources
    accepted_evidence_sources: List[Dict] = field(default_factory=list)

    # Non-probative leads (search pages, homepages)
    research_leads: List[Dict] = field(default_factory=list)

    # Coverage and counts
    coverage: Dict = field(default_factory=dict)

    # Errors from any stage
    errors: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.snapshot_id:
            self.snapshot_id = f"snap_{self.target_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Deterministic hash of snapshot content."""
        raw = json.dumps({
            "target_id": self.target_id,
            "target_hash": self.target_hash,
            "states": self.states,
            "accepted_claims": self.accepted_claims,
            "accepted_evidence_sources": self.accepted_evidence_sources,
            "rejected_candidates": self.rejected_candidates,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "run_id": self.run_id,
            "target_id": self.target_id,
            "target_hash": self.target_hash,
            "target_type": self.target_type,
            "created_at": self.created_at,
            "states": self.states,
            "accepted_claims": self.accepted_claims,
            "conflicting_claims": self.conflicting_claims,
            "uncertain_observations": self.uncertain_observations,
            "rejected_candidates": self.rejected_candidates,
            "accepted_evidence_sources": self.accepted_evidence_sources,
            "research_leads": self.research_leads,
            "coverage": self.coverage,
            "errors": self.errors,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def validate_claim_id(self, claim_id: str) -> bool:
        """Check if a claim_id exists in this snapshot."""
        all_claims = self.accepted_claims + self.conflicting_claims + self.uncertain_observations
        return any(c.get("claim_id") == claim_id for c in all_claims)

    def validate_evidence_source_id(self, source_id: str) -> bool:
        """Check if an evidence_source_id exists in this snapshot."""
        return any(s.get("source_id") == source_id for s in self.accepted_evidence_sources)

    def validate_citation(self, claim_id: str, evidence_source_id: str) -> bool:
        """Validate that a citation references existing claim and evidence."""
        if not self.validate_claim_id(claim_id):
            return False
        if not self.validate_evidence_source_id(evidence_source_id):
            return False
        # Check that the evidence is linked to the claim
        for c in self.accepted_claims:
            if c.get("claim_id") == claim_id:
                return evidence_source_id in c.get("evidence_source_ids", [])
        return False


def build_snapshot_from_dossier(
    dossier,
    target,
    run_id: str = "",
) -> EvidenceSnapshot:
    """Build an EvidenceSnapshot from a completed Dossier and ResearchTarget.

    Extracts:
    - States from dossier.profilo
    - Accepted claims from candidates with evidence
    - Rejected candidates from dossier.omonimi_esclusi
    - Research leads from web search sources classified as non-evidence
    - Errors from AI and web search
    """
    from research_protocol import classify_object_kind, is_evidence_eligible, ObjectKind

    states = {
        "local_match": dossier.profilo.get("local_match_state", "NOT_SEARCHED"),
        "external_validation": dossier.profilo.get("external_validation_state", "NOT_RUN"),
        "resolution": dossier.profilo.get("resolution_state", "UNRESOLVED"),
        "run": dossier.profilo.get("run_state", "PARTIAL"),
    }

    # Accepted claims — only from candidates with accepted evidence
    accepted_claims = []
    accepted_evidence_sources = []

    for c in dossier.candidati:
        if c.stato in ("CONFIRMED", "PROBABLE"):
            # Only create claims if candidate has evidence-eligible sources
            evidence_sources = []
            for f in c.fonti:
                kind = classify_object_kind(f.url)
                if is_evidence_eligible(kind):
                    source_id = f"ev_{hash(f.url) % 100000:05d}"
                    evidence_sources.append({
                        "source_id": source_id,
                        "provider": f.istituzione or "",
                        "archive": f.istituzione or "",
                        "url": f.url,
                        "record_id": str(f.id) if hasattr(f, 'id') else "",
                        "locator": f.note or "",
                        "object_kind": kind.value,
                        "accessed_at": f.data_accesso or "",
                    })
                    accepted_evidence_sources.extend(evidence_sources)

            if evidence_sources:
                claim_id = f"cl_{target.target_id}_{hash(c.nome_originale) % 100000:05d}"
                accepted_claims.append({
                    "claim_id": claim_id,
                    "predicate": "identified_as",
                    "object_value": c.nome_originale,
                    "object_normalized": c.nome_originale,
                    "evidence_source_ids": [es["source_id"] for es in evidence_sources],
                    "confidence": c.confidence,
                    "claim_status": "accepted",
                })

    # Rejected candidates
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

    # Research leads — non-evidence sources from web search
    research_leads = []
    if dossier.web_search_results and not dossier.web_search_results.get("error"):
        for s in dossier.web_search_results.get("sources", []):
            kind = classify_object_kind(s.get("url", ""))
            if not is_evidence_eligible(kind):
                research_leads.append({
                    "lead_id": f"lead_{hash(s.get('url', '')) % 100000:05d}",
                    "url": s.get("url", ""),
                    "provider": "openai_web_search",
                    "object_kind": kind.value,
                    "note": s.get("title", ""),
                })

    # Errors
    errors = []
    if dossier.profilo.get("ai_error"):
        errors.append(dossier.profilo["ai_error"])
    if dossier.web_search_results and dossier.web_search_results.get("error"):
        errors.append(dossier.web_search_results["error"])

    # Coverage
    typed_counts = dossier.profilo.get("typed_counts", {})
    coverage = {
        "provider_attempts": typed_counts.get("provider_attempts", 0),
        "retrieved_items": typed_counts.get("retrieved_items", 0),
        "person_candidates": len(dossier.candidati),
        "rejected_person_candidates": len(dossier.omonimi_esclusi),
        "search_leads": len(research_leads),
        "source_records": typed_counts.get("source_records", 0),
        "accepted_evidence_sources": len(accepted_evidence_sources),
        "independent_evidence_lineages": typed_counts.get("independent_evidence_lineages", 0),
        "supported_claims": len(accepted_claims),
    }

    return EvidenceSnapshot(
        run_id=run_id,
        target_id=target.target_id,
        target_hash=target.target_hash,
        target_type=target.target_type,
        states=states,
        accepted_claims=accepted_claims,
        accepted_evidence_sources=accepted_evidence_sources,
        rejected_candidates=rejected_candidates,
        research_leads=research_leads,
        coverage=coverage,
        errors=errors,
    )
