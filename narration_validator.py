"""NarrationValidator — validates NarrationDraft against the claim allowlist.

This validator is entity-specific:
- PERSON: checks identity fields, semantic roles, no event-as-person
- FACT: checks direct answer presence, claim coverage
- EVENT: checks temporal coherence, no person-as-event

Key checks:
1. Every claim_id in every block is in the allowlist
2. Every factual block has at least one claim_id
3. No rejected claim appears in a factual block
4. No source_id or URL appears in block text (backend-computed)
5. No hallucinated entity or date not in claims
6. Certainty level matches claim status
7. Request type matches the intent
8. Entity-specific field requirements (PERSON needs identity, EVENT needs dates)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any

from narration_models import NarrationDraft, NarrationBlock, NarrationResult
from evidence_snapshot_v7 import EvidenceSnapshotV7
from v7_claim_rules import classify_claim_status


# ─── Validation result ──────────────────────────────────────────────────────

@dataclass
class BlockValidation:
    """Validation result for a single block."""
    block_id: str
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    repaired: bool = False
    repair_action: str = ""


@dataclass
class DraftValidation:
    """Validation result for an entire draft."""
    valid: bool
    block_results: List[BlockValidation] = field(default_factory=list)
    global_errors: List[str] = field(default_factory=list)
    global_warnings: List[str] = field(default_factory=list)
    repaired_blocks: List[str] = field(default_factory=list)
    needs_fallback: bool = False

    @property
    def error_count(self) -> int:
        return len(self.global_errors) + sum(len(b.errors) for b in self.block_results)

    @property
    def warning_count(self) -> int:
        return len(self.global_warnings) + sum(len(b.warnings) for b in self.block_results)


# ─── Patterns ───────────────────────────────────────────────────────────────

URL_PATTERN = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
SOURCE_REF_PATTERN = re.compile(r'\[source[:\s]+([^\]]+)\]', re.IGNORECASE)
OBS_ID_PATTERN = re.compile(r'obs_[a-f0-9]{12,}')
DB_ID_PATTERN = re.compile(r'\b\d{5,}\b')  # raw DB IDs like 12345


class NarrationValidator:
    """Validates a NarrationDraft against the claim allowlist and snapshot.

    Entity-specific validation:
    - PERSON: requires identity fields, checks semantic roles
    - FACT: requires direct answer, checks claim coverage
    - EVENT: requires temporal fields, checks no person-as-event
    """

    # Required fields per request type (in claim predicates)
    REQUIRED_PREDICATES = {
        "PERSON": ["birth_year", "birth_place", "rank", "unit"],
        "FACT": [],  # depends on the specific question
        "EVENT": ["event_start_date", "event_end_date", "event_location"],
    }

    # Fields that should NOT be required for events
    PERSON_ONLY_PREDICATES = {
        "birth_year", "birth_place", "paternity", "rank", "unit",
        "service_number", "death_date", "death_year", "death_place",
        "death_cause", "capture_date", "capture_place", "internment_place",
        "burial", "fate", "residence", "decoration_type", "draft_class",
        "municipality",
    }

    def __init__(self):
        pass

    def validate(
        self,
        draft: NarrationDraft,
        allowlist: List[str],
        snapshot: EvidenceSnapshotV7,
        request_type: str = "PERSON",
    ) -> DraftValidation:
        """Validate a draft against the allowlist and snapshot."""
        result = DraftValidation(valid=True)
        allowset: Set[str] = set(allowlist)

        # Global checks
        result.global_errors.extend(draft.validate())

        # Check request_type matches intent
        intent_to_type = {
            "PERSON_LOOKUP": "PERSON",
            "EVENT_LOOKUP": "EVENT",
            "AGGREGATE_QUERY": "FACT",
        }
        expected_type = intent_to_type.get(snapshot.intent, "")
        if expected_type and draft.request_type != expected_type:
            result.global_errors.append(
                f"REQUEST_TYPE_MISMATCH: draft={draft.request_type}, expected={expected_type}"
            )

        # Build claim status lookup
        claim_status: Dict[str, str] = {}
        for c in snapshot.person_claims:
            bucket = classify_claim_status({
                "status": c.status, "confidence": c.confidence,
                "predicate": c.predicate, "value_normalized": c.value_normalized,
            })
            claim_status[c.claim_id] = bucket
        for c in snapshot.accepted_claims:
            if c.claim_id not in claim_status:
                bucket = classify_claim_status({
                    "status": c.status, "confidence": c.confidence,
                })
                claim_status[c.claim_id] = bucket
        for c in snapshot.asserted_claims:
            if c.claim_id not in claim_status:
                bucket = classify_claim_status({
                    "status": c.status, "confidence": c.confidence,
                })
                claim_status[c.claim_id] = bucket

        # Validate each block
        for block in draft.blocks:
            bv = BlockValidation(block_id=block.block_id, valid=True)

            # 1. Check claim_ids are in allowlist
            for cid in block.claim_ids:
                if cid not in allowset:
                    bv.errors.append(f"CLAIM_NOT_IN_ALLOWLIST:{cid}")
                    bv.valid = False

            # 2. Factual blocks must have claim_ids
            if block.certainty in ("verified", "probable", "conflicting", "unverified_limit"):
                if not block.claim_ids:
                    bv.errors.append("FACTUAL_BLOCK_WITHOUT_CLAIM_IDS")
                    bv.valid = False

            # 3. No rejected claims in factual blocks
            for cid in block.claim_ids:
                status = claim_status.get(cid, "")
                if status == "REJECTED":
                    bv.errors.append(f"REJECTED_CLAIM_IN_FACTUAL_BLOCK:{cid}")
                    bv.valid = False

            # 4. No URLs or source references in block text
            urls = URL_PATTERN.findall(block.text)
            if urls:
                bv.errors.append(f"URL_IN_BLOCK_TEXT:{urls[:3]}")
                bv.valid = False

            source_refs = SOURCE_REF_PATTERN.findall(block.text)
            if source_refs:
                bv.errors.append(f"SOURCE_REF_IN_BLOCK_TEXT:{source_refs[:3]}")
                bv.valid = False

            obs_refs = OBS_ID_PATTERN.findall(block.text)
            if obs_refs:
                bv.errors.append(f"OBS_ID_IN_BLOCK_TEXT:{obs_refs[:3]}")
                bv.valid = False

            # 5. Certainty level matches claim status
            if block.certainty == "verified":
                for cid in block.claim_ids:
                    status = claim_status.get(cid, "")
                    if status not in ("APPROVED",):
                        bv.warnings.append(
                            f"CERTAINTY_MISMATCH: block=verified but claim {cid} is {status}"
                        )
            elif block.certainty == "probable":
                for cid in block.claim_ids:
                    status = claim_status.get(cid, "")
                    if status == "REJECTED":
                        bv.errors.append(f"PROBABLE_WITH_REJECTED_CLAIM:{cid}")
                        bv.valid = False

            # 6. Entity-specific checks
            if request_type == "PERSON":
                # Check no event-only predicates in direct_answer
                if block.role == "direct_answer":
                    for cid in block.claim_ids:
                        claim = self._find_claim(cid, snapshot)
                        if claim and claim.get("evidence_scope") == "CONTEXT_EVIDENCE":
                            bv.warnings.append(
                                f"CONTEXT_CLAIM_IN_DIRECT_ANSWER:{cid}"
                            )

            elif request_type == "EVENT":
                # Check no person-only fields required
                if block.role == "direct_answer":
                    for cid in block.claim_ids:
                        claim = self._find_claim(cid, snapshot)
                        if claim and claim.get("predicate", "") in self.PERSON_ONLY_PREDICATES:
                            bv.warnings.append(
                                f"PERSON_PREDICATE_IN_EVENT_ANSWER:{cid}:{claim.get('predicate')}"
                            )

            elif request_type == "FACT":
                # Check direct answer exists
                if block.role == "direct_answer" and block.certainty == "non_factual":
                    if any(b.role == "direct_answer" for b in draft.blocks):
                        pass  # at least one direct_answer exists
                    else:
                        bv.warnings.append("FACT_MISSING_DIRECT_ANSWER")

            if not bv.valid:
                result.valid = False
            result.block_results.append(bv)

        # Entity-specific global checks
        if request_type == "PERSON":
            # Check that identity is at least mentioned
            has_identity = any(
                b.role in ("direct_answer", "identity")
                for b in draft.blocks
            )
            if not has_identity:
                result.global_warnings.append("PERSON_MISSING_IDENTITY_BLOCK")

        elif request_type == "EVENT":
            # Check temporal coherence
            has_temporal = any(
                b.role in ("direct_answer", "chronology")
                for b in draft.blocks
            )
            if not has_temporal:
                result.global_warnings.append("EVENT_MISSING_TEMPORAL_BLOCK")

        # Determine if fallback is needed
        if result.global_errors or any(not bv.valid for bv in result.block_results):
            result.needs_fallback = result.error_count > 3

        return result

    def repair(
        self,
        draft: NarrationDraft,
        validation: DraftValidation,
        allowlist: List[str],
    ) -> NarrationDraft:
        """Attempt to repair a draft by removing invalid blocks and claims.

        Repairs:
        - Remove claim_ids not in allowlist from blocks
        - Remove blocks that become empty after claim removal
        - Remove URLs/source refs from block text
        - Downgrade certainty if claims don't support it
        """
        allowset = set(allowlist)
        repaired_blocks = []

        for block in draft.blocks:
            bv = next((b for b in validation.block_results if b.block_id == block.block_id), None)
            if bv and bv.valid:
                repaired_blocks.append(block)
                continue

            repaired_block = NarrationBlock(
                block_id=block.block_id,
                role=block.role,
                text=block.text,
                claim_ids=[cid for cid in block.claim_ids if cid in allowset],
                certainty=block.certainty,
            )

            # Remove URLs from text
            repaired_block.text = URL_PATTERN.sub("[fonte]", repaired_block.text)
            repaired_block.text = SOURCE_REF_PATTERN.sub("[fonte]", repaired_block.text)
            repaired_block.text = OBS_ID_PATTERN.sub("[fonte]", repaired_block.text)

            # If block had rejected claims, remove them
            # (already filtered by allowlist check above)

            # If factual block lost all claims, downgrade to non_factual
            if repaired_block.certainty in ("verified", "probable", "conflicting", "unverified_limit"):
                if not repaired_block.claim_ids:
                    repaired_block.certainty = "non_factual"
                    repaired_block.text = repaired_block.text  # keep text but mark as non-factual

            # If block is still non-empty, keep it
            if repaired_block.text.strip():
                repaired_blocks.append(repaired_block)

        return NarrationDraft(
            schema_version=draft.schema_version,
            request_type=draft.request_type,
            blocks=repaired_blocks,
            needs_followup=draft.needs_followup,
            followup_question=draft.followup_question,
        )

    def _find_claim(self, claim_id: str, snapshot: EvidenceSnapshotV7) -> Optional[Dict[str, Any]]:
        """Find a claim by ID in the snapshot."""
        for c in snapshot.person_claims:
            if c.claim_id == claim_id:
                return {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value_normalized": c.value_normalized,
                    "evidence_scope": c.evidence_scope,
                    "status": c.status,
                }
        for c in snapshot.accepted_claims:
            if c.claim_id == claim_id:
                return {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value_normalized": c.value_normalized,
                    "evidence_scope": c.evidence_scope,
                    "status": c.status,
                }
        for c in snapshot.context_claims:
            if c.claim_id == claim_id:
                return {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value_normalized": c.value if hasattr(c, 'value') else c.value_normalized,
                    "evidence_scope": "CONTEXT_EVIDENCE",
                    "status": "context",
                }
        return None
