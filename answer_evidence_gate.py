"""Answer Evidence Gate — converts EvidenceSnapshotV7 into AnswerEvidenceBundle.

This module sits between the V7 pipeline and the AI narrator. It:

  1. Converts EvidenceSnapshotV7 claims → ClaimRef (evidence_contract)
  2. Maps ClaimV7 status → verification_status (8-level)
  3. Builds AnswerEvidenceBundle with verified/probable/disputed/unsupported groups
  4. Generates the mandatory AI prompt context (to_prompt_context)
  5. Blocks legacy/unverified claims from reaching the AI
  6. Computes evidence hash for integrity verification

Key principle: The AI receives ONLY the AnswerEvidenceBundle, never raw records
or unvalidated legacy relations.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from evidence_contract import (
    AnswerEvidenceBundle,
    ClaimRef,
    ClaimStatus,
    EvidenceRef,
    SourceRef,
    SourceOriginType,
    RelationOrigin,
    EvidenceContract,
)

logger = logging.getLogger(__name__)

GATE_VERSION = "1.0.0"


# ─── Status mapping: ClaimV7 → EvidenceContract ──────────────────────────────

CLAIM_V7_STATUS_MAP = {
    "ACCEPTED": ClaimStatus.PROBABLE,       # Multi-source accepted → probable
    "ASSERTED": ClaimStatus.SUPPORTED,      # Single-source asserted → supported
    "CONFLICTING": ClaimStatus.DISPUTED,    # Conflicting → disputed
    "REJECTED": ClaimStatus.REJECTED,       # Rejected → rejected
    "CANDIDATE": ClaimStatus.CANDIDATE,     # Candidate → candidate
    "DISCOVERED": ClaimStatus.CANDIDATE,    # Discovered → candidate
    "SUPPORTED": ClaimStatus.SUPPORTED,     # Supported → supported
    "VERIFIED": ClaimStatus.VERIFIED,       # Verified → verified
    "PROBABLE": ClaimStatus.PROBABLE,       # Probable → probable
    "UNSUPPORTED": ClaimStatus.UNSUPPORTED, # Unsupported → unsupported
}


def map_claim_v7_status(v7_status: str) -> str:
    """Map a ClaimV7 status to EvidenceContract verification_status."""
    return CLAIM_V7_STATUS_MAP.get(v7_status.upper(), ClaimStatus.CANDIDATE)


# ─── Evidence hash computation ────────────────────────────────────────────────

def compute_evidence_hash(bundle: AnswerEvidenceBundle) -> str:
    """Compute SHA-256 hash of the evidence bundle for integrity verification."""
    hasher = hashlib.sha256()

    for claim in bundle.verified_claims:
        hasher.update(f"V:{claim.claim_id}:{claim.predicate}:{claim.object_value}".encode())
    for claim in bundle.probable_claims:
        hasher.update(f"P:{claim.claim_id}:{claim.predicate}:{claim.object_value}".encode())
    for claim in bundle.disputed_claims:
        hasher.update(f"D:{claim.claim_id}:{claim.predicate}:{claim.object_value}".encode())
    for claim in bundle.unsupported_claims:
        hasher.update(f"U:{claim.claim_id}:{claim.predicate}:{claim.object_value}".encode())
    for src in bundle.sources:
        hasher.update(f"S:{src.source_id}:{src.provider}".encode())

    return hasher.hexdigest()


# ─── Answer Evidence Gate ─────────────────────────────────────────────────────

class AnswerEvidenceGate:
    """Converts EvidenceSnapshotV7 into AnswerEvidenceBundle.

    This is the ONLY structure the AI narrator should receive.
    Raw records, unvalidated legacy relations, and unverified claims are blocked.
    """

    VERSION = GATE_VERSION

    def __init__(self, conn=None):
        self.conn = conn

    def build_bundle(
        self,
        snapshot: Any,  # EvidenceSnapshotV7
        query: str = "",
        intent: str = "PERSON_LOOKUP",
    ) -> AnswerEvidenceBundle:
        """Build an AnswerEvidenceBundle from an EvidenceSnapshotV7.

        Converts claims, evidence, and sources into the evidence contract format.
        Groups claims by verification_status for AI consumption.
        """
        # Convert sources
        sources = self._convert_sources(snapshot)

        # Convert claims
        all_claims: List[ClaimRef] = []
        conflicts: List[Dict[str, Any]] = []
        gaps: List[Dict[str, Any]] = []

        # Person claims
        for claim_v7 in getattr(snapshot, "person_claims", []):
            claim_ref = self._convert_claim(claim_v7, evidence_scope="person_evidence")
            all_claims.append(claim_ref)

        # Context claims
        for claim_v7 in getattr(snapshot, "context_claims", []):
            claim_ref = self._convert_claim(claim_v7, evidence_scope="context_evidence")
            all_claims.append(claim_ref)

        # Extract conflicts from conflicting claims
        for claim in all_claims:
            if claim.verification_status in ClaimStatus.CONFLICTED:
                conflicts.append({
                    "claim_id": claim.claim_id,
                    "predicate": claim.predicate,
                    "object_value": claim.object_value,
                    "conflict_status": claim.conflict_status,
                    "description": f"Conflitto su {claim.predicate}: {claim.object_value}",
                })

        # Extract gaps from snapshot
        for gap in getattr(snapshot, "conditional_gaps", []):
            gaps.append({
                "description": str(gap) if not isinstance(gap, dict) else gap.get("description", str(gap)),
            })

        # Build bundle
        bundle = EvidenceContract.build_answer_bundle(
            claims=all_claims,
            sources=sources,
            conflicts=conflicts,
            gaps=gaps,
            snapshot_id=getattr(snapshot, "snapshot_id", ""),
        )

        # Compute hashes
        bundle.context_hash = compute_evidence_hash(bundle)
        bundle.answer_hash = ""  # Will be set after AI generates answer

        return bundle

    def _convert_sources(self, snapshot: Any) -> List[SourceRef]:
        """Convert EvidenceSnapshotV7 evidence items into SourceRef list."""
        sources: List[SourceRef] = []
        seen_source_ids = set()

        for evidence in getattr(snapshot, "accepted_evidence", []):
            source_id = getattr(evidence, "source_id", "") or getattr(evidence, "provider", "")
            if not source_id or source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)

            provider = getattr(evidence, "provider", "unknown")
            source_type = getattr(evidence, "source_type", "archive")

            # Determine authority tier from provider
            authority_tier = 4  # default: unofficial
            provider_lower = provider.lower()
            if any(k in provider_lower for k in ["lebi", "anrp", "icrc", "ministero"]):
                authority_tier = 1
            elif any(k in provider_lower for k in ["albo", "cwgc", "nastro", "imi"]):
                authority_tier = 2
            elif any(k in provider_lower for k in ["fonti", "archivio", "ocr", "lettere"]):
                authority_tier = 3

            sources.append(SourceRef(
                source_id=source_id,
                provider=provider,
                source_type=source_type,
                authority_tier=authority_tier,
                url=getattr(evidence, "locator", "") or "",
            ))

        # Also check web leads
        for lead in getattr(snapshot, "web_leads", []):
            url = getattr(lead, "url_canonical", "") or getattr(lead, "url", "")
            if not url:
                continue
            source_id = f"web_{hashlib.sha256(url.encode()).hexdigest()[:8]}"
            if source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            sources.append(SourceRef(
                source_id=source_id,
                provider="web_search",
                source_type="web",
                authority_tier=4,
                url=url,
            ))

        return sources

    def _convert_claim(self, claim_v7: Any, evidence_scope: str = "person_evidence") -> ClaimRef:
        """Convert a ClaimV7 into a ClaimRef (evidence contract format)."""
        # Map status
        v7_status = getattr(claim_v7, "status", "CANDIDATE")
        verification_status = map_claim_v7_status(v7_status)

        # Extract evidence IDs
        evidence_ids = getattr(claim_v7, "evidence_ids", []) or []

        # Extract provenance chain
        provenance_chain = getattr(claim_v7, "provenance_chain", []) or []

        # Determine conflict status
        conflict_status = "none"
        if verification_status == ClaimStatus.DISPUTED:
            conflict_status = "factual"
        elif verification_status == ClaimStatus.CONTRADICTED:
            conflict_status = "source"

        # Compute support score
        confidence = getattr(claim_v7, "confidence", 0.5) or 0.5
        support_score = float(confidence)

        # Generate claim_id if not present
        claim_id = getattr(claim_v7, "claim_id", "") or f"claim_{uuid4().hex[:16]}"

        return ClaimRef(
            claim_id=claim_id,
            subject_id=getattr(claim_v7, "subject_id", "") or "",
            predicate=getattr(claim_v7, "predicate", "") or "",
            object_value=getattr(claim_v7, "value_normalized", "") or getattr(claim_v7, "value_raw", "") or "",
            normalized_value=getattr(claim_v7, "value_normalized", "") or "",
            temporal_context="",  # Extracted from snapshot if available
            geographic_context="",
            evidence_ids=evidence_ids,
            support_score=support_score,
            conflict_status=conflict_status,
            verification_status=verification_status,
            identity_cluster_id=getattr(claim_v7, "subject_id", "") or "",
            source_lineage_ids=[],  # Populated from lineage service if available
            provenance_chain=provenance_chain,
        )

    # ─── Gate validation ──────────────────────────────────────────────────────

    def validate_bundle(self, bundle: AnswerEvidenceBundle) -> List[str]:
        """Validate an AnswerEvidenceBundle before passing to AI.

        Returns list of violation descriptions (empty if valid).
        """
        violations = []

        # Check: no legacy relations in verified claims
        for claim in bundle.verified_claims:
            if not claim.evidence_ids:
                violations.append(
                    f"VERIFIED claim {claim.claim_id} has no evidence_ids"
                )
            if not claim.provenance_chain:
                violations.append(
                    f"VERIFIED claim {claim.claim_id} has no provenance_chain"
                )

        # Check: unsupported claims should not have verified status
        for claim in bundle.unsupported_claims:
            if claim.verification_status not in (ClaimStatus.UNSUPPORTED, ClaimStatus.CANDIDATE):
                violations.append(
                    f"UNSUPPORTED claim {claim.claim_id} has status {claim.verification_status}"
                )

        # Check: rejected claims should not be in any other group
        for claim in bundle.rejected_claims:
            if claim in bundle.verified_claims or claim in bundle.probable_claims:
                violations.append(
                    f"REJECTED claim {claim.claim_id} also in verified/probable"
                )

        return violations

    # ─── AI prompt generation ─────────────────────────────────────────────────

    def build_ai_prompt(self, bundle: AnswerEvidenceBundle, query: str = "") -> str:
        """Build the complete AI system prompt with evidence bundle context.

        This replaces the raw snapshot input with a structured, gated prompt.
        """
        prompt_parts = [
            bundle.to_prompt_context(),
            "",
            f"QUERY: {query}" if query else "",
            "",
            "RULES:",
            "1. Use ONLY claims listed above. Do NOT invent or assume facts.",
            "2. Cite sources as [ID] where ID is the source_id.",
            "3. For VERIFIED claims, state as fact.",
            "4. For PROBABLE claims, use 'probabilmente', 'verosimilmente'.",
            "5. For DISPUTED claims, show the conflict explicitly.",
            "6. For UNSUPPORTED claims, do NOT present as fact.",
            "7. Do NOT mix WWI and WWII data.",
            "8. If information is missing, say 'non documentato'.",
            f"9. Evidence hash: {bundle.context_hash}",
        ]

        return "\n".join(prompt_parts)

    # ─── Post-generation verification ─────────────────────────────────────────

    def verify_answer(
        self,
        bundle: AnswerEvidenceBundle,
        ai_output: str,
    ) -> Tuple[bool, List[str]]:
        """Verify that AI output is consistent with the evidence bundle.

        Returns (is_valid, list_of_violations).
        """
        violations = []

        # Check: AI should not state unsupported claims as fact
        for claim in bundle.unsupported_claims:
            # Simple check: if the object_value appears in a factual statement
            if claim.object_value and claim.object_value in ai_output:
                # Check if it's stated as fact (not hedged)
                hedging_words = ["probabilmente", "verosimilmente", "forse", "non documentato",
                                 "secondo", "risulterebbe"]
                context_start = max(0, ai_output.index(claim.object_value) - 100)
                context_end = min(len(ai_output), ai_output.index(claim.object_value) + 100)
                context = ai_output[context_start:context_end].lower()
                if not any(h in context for h in hedging_words):
                    violations.append(
                        f"UNSUPPORTED claim '{claim.predicate}: {claim.object_value}' "
                        f"stated as fact without hedging"
                    )

        # Check: AI should not mention rejected claims
        for claim in bundle.rejected_claims:
            if claim.object_value and claim.object_value in ai_output:
                violations.append(
                    f"REJECTED claim '{claim.predicate}: {claim.object_value}' "
                    f"mentioned in output"
                )

        # Check: AI should acknowledge disputes
        for claim in bundle.disputed_claims:
            if claim.object_value and claim.object_value in ai_output:
                dispute_words = ["conflitto", "discordanza", "divergenza", "versioni contrastanti",
                                 "fonti diverse"]
                context_start = max(0, ai_output.index(claim.object_value) - 150)
                context_end = min(len(ai_output), ai_output.index(claim.object_value) + 150)
                context = ai_output[context_start:context_end].lower()
                if not any(d in context for d in dispute_words):
                    violations.append(
                        f"DISPUTED claim '{claim.predicate}: {claim.object_value}' "
                        f"mentioned without acknowledging dispute"
                    )

        is_valid = len(violations) == 0
        return is_valid, violations

    def compute_answer_hash(self, bundle: AnswerEvidenceBundle, ai_output: str) -> str:
        """Compute the answer hash for the evidence bundle."""
        hasher = hashlib.sha256()
        hasher.update(bundle.context_hash.encode())
        hasher.update(ai_output.encode())
        return hasher.hexdigest()
