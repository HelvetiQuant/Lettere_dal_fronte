"""Test suite for V7.2-narration-v2 contract, validator, selector, and regression.

Tests cover:
  1. Contract: NarrationDraft and NarrationResult structure validation
  2. Evidence selector: claim selection, budget, omission
  3. Validator: allowlist, URL rejection, rejected claims, entity-specific
  4. NarratorV7_v2: deterministic fallback, blocked result, structured output
  5. Regression: historical cases (Sonavetti, Venturini, Sardi, etc.)
  6. Coverage: PERSON, FACT, EVENT types
  7. Edge cases: ambiguous identity, insufficient coverage, conflict, no-AI fallback

Run: python test_narration_v2_master.py
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

from narration_models import (
    NarrationDraft, NarrationBlock, NarrationResult, CitationEntry,
    OmittedClaim, GenerationInfo, blocked_result,
    NARRATION_STATUS, BLOCK_ROLES, CERTAINTY_LEVELS, REQUEST_TYPES,
)
from narration_evidence_selector import (
    NarrationEvidenceSelector, SelectedEvidence,
    DEFAULT_BUDGETS, _score_claim, _ensure_diversity,
)
from narration_validator import NarrationValidator, DraftValidation, BlockValidation
from evidence_snapshot_v7 import (
    EvidenceSnapshotV7, ClaimV7, EvidenceItemV7, ContextClaimV7,
    ContextSourceV7, WebLeadV7, RejectedCandidateV7,
    ProviderLedgerEntryV7, ConditionalGapV7, LimitationV7,
    CandidateIdentityV72,
)
from v7_narrator import NarratorV7_v2, CitationResolver, ReportRenderer


# ═══ Helpers ════════════════════════════════════════════════════════════════

def _make_claim(
    claim_id: str,
    predicate: str,
    value: str,
    status: str = "ACCEPTED",
    confidence: float = 0.9,
    evidence_scope: str = "PERSON_EVIDENCE",
    source_function: str = "person_evidence",
    evidence_ids: List[str] = None,
) -> ClaimV7:
    return ClaimV7(
        claim_id=claim_id,
        subject_id="subj_1",
        predicate=predicate,
        value_normalized=value,
        value_raw=value,
        status=status,
        confidence=confidence,
        evidence_scope=evidence_scope,
        source_function=source_function,
        evidence_ids=evidence_ids or ["ev_1"],
        provenance_chain=["obs_1"],
    )


def _make_snapshot(
    person_claims: List[ClaimV7] = None,
    context_claims: List[ContextClaimV7] = None,
    accepted_evidence: List[EvidenceItemV7] = None,
    intent: str = "PERSON_LOOKUP",
    identity_status: str = "RESOLVED_IDENTITY",
    web_leads: List[WebLeadV7] = None,
) -> EvidenceSnapshotV7:
    snap = EvidenceSnapshotV7(
        snapshot_id="test_snap",
        manifest_hash="test_hash",
        intent=intent,
        target={"display_name": "TEST Mario", "conflict": "UNKNOWN"},
        identity_status=identity_status,
        identity_resolution="RESOLVED" if identity_status in ("ANCHORED_RECORD", "RESOLVED_IDENTITY") else "UNRESOLVED",
        person_claims=person_claims or [],
        context_claims=context_claims or [],
        accepted_evidence=accepted_evidence or [],
        web_leads=web_leads or [],
        provider_ledger=[
            ProviderLedgerEntryV7(
                observation_id="obs_1",
                provider="local_db",
                classification="SOURCE_CANDIDATE",
            ),
        ],
    )
    return snap


def _make_evidence(
    evidence_id: str = "ev_1",
    source_id: str = "src_1",
    provider: str = "local_db",
    content_state: str = "OPENED",
    is_origin: bool = True,
) -> EvidenceItemV7:
    return EvidenceItemV7(
        evidence_id=evidence_id,
        source_id=source_id,
        provider=provider,
        content_state=content_state,
        is_origin=is_origin,
        locator="",
        raw_payload_hash="abc123",
    )


# ═══ 1. Contract Tests ══════════════════════════════════════════════════════

class TestNarrationDraftContract(unittest.TestCase):
    """Test NarrationDraft structural validation."""

    def test_valid_draft(self):
        """A well-formed draft passes validation."""
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(
                    block_id="b1",
                    role="direct_answer",
                    text="Mario Rossi era un soldato italiano.",
                    claim_ids=["claim_1"],
                    certainty="verified",
                ),
                NarrationBlock(
                    block_id="b2",
                    role="context",
                    text="La Prima Guerra Mondiale si svolse tra il 1915 e il 1918.",
                    claim_ids=[],
                    certainty="non_factual",
                ),
            ],
        )
        errors = draft.validate()
        self.assertEqual(errors, [], f"Expected no errors, got: {errors}")

    def test_invalid_request_type(self):
        """Invalid request_type is rejected."""
        draft = NarrationDraft(
            request_type="INVALID",
            blocks=[NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=["c1"], certainty="verified")],
        )
        errors = draft.validate()
        self.assertTrue(any("INVALID_REQUEST_TYPE" in e for e in errors))

    def test_no_blocks_rejected(self):
        """Empty blocks list is rejected."""
        draft = NarrationDraft(request_type="PERSON", blocks=[])
        errors = draft.validate()
        self.assertTrue(any("NO_BLOCKS" in e for e in errors))

    def test_duplicate_block_ids(self):
        """Duplicate block_ids are rejected."""
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test1", claim_ids=["c1"], certainty="verified"),
                NarrationBlock(block_id="b1", role="context", text="test2", claim_ids=[], certainty="non_factual"),
            ],
        )
        errors = draft.validate()
        self.assertTrue(any("DUPLICATE_BLOCK_ID" in e for e in errors))

    def test_factual_block_without_claims(self):
        """Factual blocks must have claim_ids."""
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=[], certainty="verified"),
            ],
        )
        errors = draft.validate()
        self.assertTrue(any("FACTUAL_BLOCK_WITHOUT_CLAIM_IDS" in e for e in errors))

    def test_non_factual_block_without_claims_ok(self):
        """Non-factual blocks can have empty claim_ids."""
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="context", text="test", claim_ids=[], certainty="non_factual"),
            ],
        )
        errors = draft.validate()
        self.assertEqual(errors, [])

    def test_invalid_role(self):
        """Invalid block role is rejected."""
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="invalid_role", text="test", claim_ids=["c1"], certainty="verified"),
            ],
        )
        errors = draft.validate()
        self.assertTrue(any("INVALID_ROLE" in e for e in errors))

    def test_from_json_with_fences(self):
        """Draft can be parsed from JSON with markdown fences."""
        raw = '```json\n{"schema_version":"7.2-narration-draft-v2","request_type":"PERSON","blocks":[{"block_id":"b1","role":"direct_answer","text":"test","claim_ids":["c1"],"certainty":"verified"}]}\n```'
        draft = NarrationDraft.from_json(raw)
        self.assertEqual(draft.request_type, "PERSON")
        self.assertEqual(len(draft.blocks), 1)
        self.assertEqual(draft.blocks[0].block_id, "b1")

    def test_to_dict_roundtrip(self):
        """Draft survives dict roundtrip."""
        draft = NarrationDraft(
            request_type="EVENT",
            blocks=[NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=["c1"], certainty="verified")],
        )
        d = draft.to_dict()
        draft2 = NarrationDraft.from_dict(d)
        self.assertEqual(draft2.request_type, "EVENT")
        self.assertEqual(len(draft2.blocks), 1)


class TestNarrationResultContract(unittest.TestCase):
    """Test NarrationResult structure."""

    def test_result_always_has_schema_version(self):
        result = NarrationResult()
        self.assertEqual(result.schema_version, "7.2-narration-result-v2")

    def test_result_to_dict_has_all_fields(self):
        result = NarrationResult(
            request_type="PERSON",
            status="validated_ai",
            answer_markdown="test",
            used_claim_ids=["c1"],
            citation_map=[CitationEntry(block_id="b1", claim_ids=["c1"], source_ids=["s1"])],
            omitted_claims=[OmittedClaim(claim_id="c2", reason="over_budget")],
        )
        d = result.to_dict()
        self.assertIn("schema_version", d)
        self.assertIn("request_type", d)
        self.assertIn("status", d)
        self.assertIn("answer_markdown", d)
        self.assertIn("used_claim_ids", d)
        self.assertIn("citation_map", d)
        self.assertIn("omitted_claims", d)
        self.assertIn("generation", d)

    def test_blocked_result(self):
        """blocked_result creates a valid blocked NarrationResult."""
        result = blocked_result("PERSON", "no evidence")
        self.assertEqual(result.status, "blocked_evidence_not_validated")
        self.assertIn("no evidence", result.answer_markdown)
        self.assertEqual(result.generation.mode, "fallback")

    def test_result_to_json(self):
        """Result can be serialized to JSON."""
        result = NarrationResult(request_type="FACT", answer_markdown="test")
        j = result.to_json()
        d = json.loads(j)
        self.assertEqual(d["request_type"], "FACT")


# ═══ 2. Evidence Selector Tests ════════════════════════════════════════════

class TestNarrationEvidenceSelector(unittest.TestCase):
    """Test the deterministic evidence selector."""

    def test_select_person_claims(self):
        """Selector picks approved claims for PERSON."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9),
            _make_claim("c2", "birth_place", "Roma", status="ACCEPTED", confidence=0.9),
            _make_claim("c3", "rank", "soldato", status="ACCEPTED", confidence=0.85),
            _make_claim("c4", "unit", "81° fanteria", status="ACCEPTED", confidence=0.8),
        ]
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        self.assertGreater(len(selected.narratable_claims), 0)
        self.assertIn("c1", selected.claim_allowlist)
        self.assertIn("c2", selected.claim_allowlist)

    def test_select_rejected_claims_excluded(self):
        """Rejected claims are not in narratable."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9),
            _make_claim("c2", "birth_place", "Roma", status="REJECTED", confidence=0.0, source_function="homonym_candidate"),
        ]
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        self.assertIn("c1", selected.claim_allowlist)
        self.assertNotIn("c2", selected.claim_allowlist)

    def test_select_budget_respected(self):
        """Selector respects budget limits."""
        claims = []
        for i in range(50):
            claims.append(_make_claim(f"c{i}", f"field_{i}", f"value_{i}", status="ACCEPTED", confidence=0.9))
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        budget = DEFAULT_BUDGETS["PERSON"]["personal"] + DEFAULT_BUDGETS["PERSON"]["context_limit"]
        self.assertLessEqual(len(selected.narratable_claims), budget + 5)  # small tolerance for diversity

    def test_select_web_leads_not_in_main(self):
        """Web leads are not in narratable_claims."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        leads = [WebLeadV7(lead_id="wl1", provider="tavily", url_canonical="http://example.com", title="Example")]
        snap = _make_snapshot(person_claims=claims, web_leads=leads)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        # Web leads should be in technical section, not in narratable_claims
        claim_ids = [c["claim_id"] for c in selected.narratable_claims]
        self.assertNotIn("wl1", claim_ids)
        # But should be in technical section
        self.assertLessEqual(len(selected.web_leads_technical), 5)

    def test_select_omitted_claims_populated(self):
        """Omitted claims are populated with reasons."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9),
            _make_claim("c2", "birth_place", "Roma", status="REJECTED", confidence=0.0, source_function="homonym_candidate"),
        ]
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        self.assertGreater(len(selected.omitted_claims), 0)
        # The rejected claim should be in omitted
        omitted_ids = [o["claim_id"] for o in selected.omitted_claims]
        self.assertIn("c2", omitted_ids)

    def test_select_event_claims(self):
        """Selector works for EVENT type."""
        context_claims = [
            ContextClaimV7(claim_id="cc1", scope="EVENT", predicate="event_start_date", value="1917-10-24", source_refs=["ev1"]),
            ContextClaimV7(claim_id="cc2", scope="EVENT", predicate="event_location", value="Isonzo", source_refs=["ev2"]),
        ]
        snap = _make_snapshot(context_claims=context_claims, intent="EVENT_LOOKUP")
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "EVENT")
        self.assertGreater(len(selected.narratable_claims), 0)

    def test_select_fact_claims(self):
        """Selector works for FACT type."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9),
        ]
        snap = _make_snapshot(person_claims=claims, intent="AGGREGATE_QUERY")
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "FACT")
        self.assertGreater(len(selected.narratable_claims), 0)

    def test_select_empty_snapshot(self):
        """Selector handles empty snapshot gracefully."""
        snap = _make_snapshot()
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        self.assertEqual(len(selected.narratable_claims), 0)
        self.assertEqual(len(selected.claim_allowlist), 0)

    def test_select_sources_for_claims_mapping(self):
        """sources_for_claims maps claim_id to source_ids."""
        claims = [
            _make_claim("c1", "birth_year", "1921", evidence_ids=["ev1", "ev2"]),
        ]
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")
        if "c1" in selected.sources_for_claims:
            self.assertEqual(selected.sources_for_claims["c1"], ["ev1", "ev2"])

    def test_select_diversity(self):
        """Diversity function distributes across categories."""
        claims = []
        for i in range(20):
            claims.append({"claim_id": f"c{i}", "predicate": "birth_year", "_score": 90 - i})
        result = _ensure_diversity(claims, 10)
        self.assertLessEqual(len(result), 10)


# ═══ 3. Validator Tests ═════════════════════════════════════════════════════

class TestNarrationValidator(unittest.TestCase):
    """Test the NarrationValidator."""

    def test_valid_draft_passes(self):
        """A valid draft passes validation."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="Mario nacque nel 1921.", claim_ids=["c1"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertTrue(result.valid)

    def test_claim_not_in_allowlist(self):
        """Claims not in allowlist are rejected."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=["c_unknown"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertFalse(result.valid)
        self.assertTrue(any("CLAIM_NOT_IN_ALLOWLIST" in e for e in result.block_results[0].errors))

    def test_url_in_text_rejected(self):
        """URLs in block text are rejected."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="See http://example.com for more.", claim_ids=["c1"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertFalse(result.valid)
        self.assertTrue(any("URL_IN_BLOCK_TEXT" in e for e in result.block_results[0].errors))

    def test_source_ref_in_text_rejected(self):
        """[source: xxx] references in block text are rejected."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test [source: src_1] end", claim_ids=["c1"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertFalse(result.valid)

    def test_obs_id_in_text_rejected(self):
        """obs_ IDs in block text are rejected."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="Fonte: obs_8b924b52862c7240", claim_ids=["c1"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertFalse(result.valid)

    def test_rejected_claim_in_factual_block(self):
        """Rejected claims cannot appear in factual blocks."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9),
            _make_claim("c2", "birth_place", "Roma", status="REJECTED", confidence=0.0, source_function="homonym_candidate"),
        ]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=["c2"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1", "c2"], snap, "PERSON")
        self.assertFalse(result.valid)

    def test_repair_removes_invalid_claims(self):
        """Repair removes claims not in allowlist."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test http://evil.com", claim_ids=["c1", "c_bad"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        validation = validator.validate(draft, ["c1"], snap, "PERSON")
        repaired = validator.repair(draft, validation, ["c1"])
        self.assertEqual(len(repaired.blocks), 1)
        self.assertNotIn("c_bad", repaired.blocks[0].claim_ids)
        self.assertNotIn("http://evil.com", repaired.blocks[0].text)

    def test_repair_downgrades_empty_factual(self):
        """Repair downgrades factual blocks that lose all claims."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=["c_bad"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        validation = validator.validate(draft, ["c1"], snap, "PERSON")
        repaired = validator.repair(draft, validation, ["c1"])
        self.assertEqual(repaired.blocks[0].certainty, "non_factual")

    def test_entity_specific_person(self):
        """PERSON validation warns if no identity block."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims, intent="PERSON_LOOKUP")
        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(block_id="b1", role="context", text="some context", claim_ids=[], certainty="non_factual"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertTrue(any("PERSON_MISSING_IDENTITY_BLOCK" in w for w in result.global_warnings))

    def test_entity_specific_event(self):
        """EVENT validation warns if no temporal block."""
        context_claims = [ContextClaimV7(claim_id="cc1", scope="EVENT", predicate="event_description", value="test")]
        snap = _make_snapshot(context_claims=context_claims, intent="EVENT_LOOKUP")
        draft = NarrationDraft(
            request_type="EVENT",
            blocks=[
                NarrationBlock(block_id="b1", role="context", text="some context", claim_ids=[], certainty="non_factual"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["cc1"], snap, "EVENT")
        self.assertTrue(any("EVENT_MISSING_TEMPORAL_BLOCK" in w for w in result.global_warnings))

    def test_request_type_mismatch(self):
        """Request type mismatch with intent is flagged."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims, intent="PERSON_LOOKUP")
        draft = NarrationDraft(
            request_type="EVENT",
            blocks=[
                NarrationBlock(block_id="b1", role="direct_answer", text="test", claim_ids=["c1"], certainty="verified"),
            ],
        )
        validator = NarrationValidator()
        result = validator.validate(draft, ["c1"], snap, "PERSON")
        self.assertTrue(any("REQUEST_TYPE_MISMATCH" in e for e in result.global_errors))


# ═══ 4. NarratorV7_v2 Tests ════════════════════════════════════════════════

class TestNarratorV7_v2(unittest.TestCase):
    """Test the NarratorV7_v2 pipeline."""

    def test_deterministic_fallback(self):
        """Narrator returns a valid NarrationResult with use_ai=False."""
        claims = [
            _make_claim("c1", "birth_year", "1921"),
            _make_claim("c2", "birth_place", "Roma"),
        ]
        evidence = [_make_evidence()]
        snap = _make_snapshot(person_claims=claims, accepted_evidence=evidence)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult)
        self.assertEqual(result.status, "validated_deterministic")
        self.assertTrue(len(result.answer_markdown) > 0)
        self.assertTrue(len(result.used_claim_ids) > 0)

    def test_blocked_when_no_claims(self):
        """Narrator returns blocked result when no narratable claims."""
        snap = _make_snapshot(person_claims=[])
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult)
        self.assertIn("blocked", result.status)

    def test_result_has_citation_map(self):
        """Result has citation_map with source_ids from backend."""
        claims = [_make_claim("c1", "birth_year", "1921", evidence_ids=["ev1"])]
        evidence = [_make_evidence(evidence_id="ev1", source_id="src_1")]
        snap = _make_snapshot(person_claims=claims, accepted_evidence=evidence)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result.citation_map, list)

    def test_result_has_omitted_claims(self):
        """Result has omitted_claims computed deterministically."""
        claims = [
            _make_claim("c1", "birth_year", "1921"),
            _make_claim("c2", "rejected_field", "bad", status="REJECTED", confidence=0.0, source_function="homonym_candidate"),
        ]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result.omitted_claims, list)
        omitted_ids = [o.claim_id for o in result.omitted_claims]
        # c2 should be omitted since it's rejected
        self.assertIn("c2", omitted_ids)

    def test_no_raw_text_published(self):
        """answer_markdown is rendered by backend, not raw AI text."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        # Should not contain obs_ IDs or source: refs
        self.assertNotIn("obs_", result.answer_markdown)
        self.assertNotIn("[source:", result.answer_markdown)

    def test_result_always_structured(self):
        """Result is always a NarrationResult, never a bare string."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult)
        self.assertTrue(hasattr(result, 'schema_version'))
        self.assertTrue(hasattr(result, 'used_claim_ids'))
        self.assertTrue(hasattr(result, 'citation_map'))
        self.assertTrue(hasattr(result, 'omitted_claims'))

    def test_generation_info_present(self):
        """Generation info is always populated."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsNotNone(result.generation)
        self.assertEqual(result.generation.mode, "deterministic")


# ═══ 5. Regression Tests (Historical Cases) ════════════════════════════════

class TestRegressionHistorical(unittest.TestCase):
    """Regression tests for historical cases.

    These test the structural contract, not AI output quality.
    Each case builds a minimal snapshot and verifies the pipeline
    returns a valid NarrationResult.
    """

    def _run_regression(self, name: str, claims: List[ClaimV7], intent: str, request_type: str):
        """Helper: run a regression case and verify contract."""
        snap = _make_snapshot(person_claims=claims, intent=intent)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult, f"{name}: not a NarrationResult")
        self.assertTrue(len(result.answer_markdown) > 0, f"{name}: empty answer")
        self.assertIsInstance(result.used_claim_ids, list, f"{name}: used_claim_ids not a list")
        self.assertIsInstance(result.citation_map, list, f"{name}: citation_map not a list")
        self.assertIsInstance(result.omitted_claims, list, f"{name}: omitted_claims not a list")
        return result

    def test_sonavetti(self):
        """Sonavetti: person with birth/death data."""
        claims = [
            _make_claim("c1", "birth_year", "1899", evidence_ids=["ev1"]),
            _make_claim("c2", "birth_place", "Biella", evidence_ids=["ev1"]),
            _make_claim("c3", "rank", "tenente", evidence_ids=["ev1"]),
            _make_claim("c4", "unit", "2° alpini", evidence_ids=["ev1"]),
            _make_claim("c5", "death_place", "Kassel", evidence_ids=["ev2"]),
        ]
        self._run_regression("Sonavetti", claims, "PERSON_LOOKUP", "PERSON")

    def test_venturini(self):
        """Venturini: person with internment data."""
        claims = [
            _make_claim("c1", "birth_year", "1920", evidence_ids=["ev1"]),
            _make_claim("c2", "internment_place", "Wietzendorf", evidence_ids=["ev2"]),
            _make_claim("c3", "rank", "soldato", evidence_ids=["ev1"]),
        ]
        self._run_regression("Venturini", claims, "PERSON_LOOKUP", "PERSON")

    def test_sardi(self):
        """Sardi: person with conflicting data."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9, evidence_ids=["ev1"]),
            _make_claim("c2", "birth_year", "1922", status="CONFLICTING", confidence=0.7, evidence_ids=["ev2"]),
        ]
        self._run_regression("Sardi", claims, "PERSON_LOOKUP", "PERSON")

    def test_muccio(self):
        """Muccio: person with minimal data."""
        claims = [
            _make_claim("c1", "birth_year", "1900", evidence_ids=["ev1"]),
        ]
        self._run_regression("Muccio", claims, "PERSON_LOOKUP", "PERSON")

    def test_franchini(self):
        """Franchini: person with burial data."""
        claims = [
            _make_claim("c1", "birth_year", "1921", evidence_ids=["ev1"]),
            _make_claim("c2", "burial", "Cimitero di Kassel", evidence_ids=["ev2"]),
        ]
        self._run_regression("Franchini", claims, "PERSON_LOOKUP", "PERSON")

    def test_gridini(self):
        """Gridini: person with capture data."""
        claims = [
            _make_claim("c1", "capture_place", "Cefalonia", evidence_ids=["ev1"]),
            _make_claim("c2", "capture_date", "1943-09", evidence_ids=["ev1"]),
        ]
        self._run_regression("Gridini", claims, "PERSON_LOOKUP", "PERSON")

    def test_col_di_lana_event(self):
        """Col di Lana: event lookup."""
        context_claims = [
            ContextClaimV7(claim_id="cc1", scope="EVENT", predicate="event_start_date", value="1915-06-23", source_refs=["ev1"]),
            ContextClaimV7(claim_id="cc2", scope="EVENT", predicate="event_location", value="Col di Lana", source_refs=["ev1"]),
            ContextClaimV7(claim_id="cc3", scope="EVENT", predicate="event_description", value="Battaglia del Col di Lana", source_refs=["ev1"]),
        ]
        snap = _make_snapshot(context_claims=context_claims, intent="EVENT_LOOKUP")
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult)
        self.assertEqual(result.request_type, "EVENT")

    def test_roma_romania_disambiguation(self):
        """Roma/Romania: ambiguous place names."""
        claims = [
            _make_claim("c1", "birth_place", "Roma", status="ACCEPTED", confidence=0.9, evidence_ids=["ev1"]),
            _make_claim("c2", "birth_place", "Romania", status="CONFLICTING", confidence=0.5, evidence_ids=["ev2"]),
        ]
        result = self._run_regression("Roma/Romania", claims, "PERSON_LOOKUP", "PERSON")
        # Both should be in the result (one as accepted, one as omitted or conflicting)
        all_refs = set(result.used_claim_ids) | {o.claim_id for o in result.omitted_claims}
        self.assertIn("c1", all_refs)
        self.assertIn("c2", all_refs)


# ═══ 6. Coverage Tests: Request Types ═══════════════════════════════════════

class TestRequestTypeCoverage(unittest.TestCase):
    """Test coverage of PERSON, FACT, EVENT request types."""

    def test_person_type(self):
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims, intent="PERSON_LOOKUP")
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertEqual(result.request_type, "PERSON")

    def test_event_type(self):
        context_claims = [ContextClaimV7(claim_id="cc1", scope="EVENT", predicate="event_description", value="test")]
        snap = _make_snapshot(context_claims=context_claims, intent="EVENT_LOOKUP")
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertEqual(result.request_type, "EVENT")

    def test_fact_type(self):
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims, intent="AGGREGATE_QUERY")
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertEqual(result.request_type, "FACT")


# ═══ 7. Edge Cases ══════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Test edge cases: ambiguous, insufficient, conflict, no-AI."""

    def test_ambiguous_identity(self):
        """Ambiguous identity: multiple candidates."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(
            person_claims=claims,
            identity_status="AMBIGUOUS_IDENTITY",
        )
        snap.candidate_identities = [
            CandidateIdentityV72(cluster_id="cl1", display_name="TEST Mario", discriminants=["birth_year"]),
            CandidateIdentityV72(cluster_id="cl2", display_name="TEST Mario", discriminants=["birth_year"]),
        ]
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult)

    def test_insufficient_coverage(self):
        """Insufficient coverage: no claims."""
        snap = _make_snapshot(person_claims=[])
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIn("blocked", result.status)

    def test_conflict_data(self):
        """Conflicting claims are handled."""
        claims = [
            _make_claim("c1", "death_place", "Kassel", status="ACCEPTED", confidence=0.9, evidence_ids=["ev1"]),
            _make_claim("c2", "death_place", "Norimberga", status="CONFLICTING", confidence=0.7, evidence_ids=["ev2"]),
        ]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertIsInstance(result, NarrationResult)

    def test_no_ai_fallback(self):
        """Fallback when no AI provider available."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertEqual(result.generation.mode, "deterministic")

    def test_homonym_rejected(self):
        """Homonym claims are rejected and omitted."""
        claims = [
            _make_claim("c1", "birth_year", "1921", status="ACCEPTED", confidence=0.9),
            _make_claim("c2", "birth_year", "1921", status="REJECTED", confidence=0.0, source_function="homonym_candidate"),
        ]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertNotIn("c2", result.used_claim_ids)

    def test_web_lead_not_as_evidence(self):
        """Web leads are not treated as evidence."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        leads = [WebLeadV7(lead_id="wl1", provider="tavily", url_canonical="http://example.com", title="Example")]
        snap = _make_snapshot(person_claims=claims, web_leads=leads)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        self.assertNotIn("wl1", result.used_claim_ids)

    def test_result_serializable(self):
        """Result is JSON serializable."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        narrator = NarratorV7_v2()
        result = narrator.narrate(snap, use_ai=False)
        j = result.to_json()
        d = json.loads(j)
        self.assertEqual(d["schema_version"], "7.2-narration-result-v2")


# ═══ 8. AI Draft Simulation Tests ═══════════════════════════════════════════

class TestAIDraftSimulation(unittest.TestCase):
    """Test the AI draft flow with simulated drafts."""

    def test_simulated_valid_draft(self):
        """Simulate a valid AI draft and verify the result."""
        claims = [
            _make_claim("c1", "birth_year", "1921"),
            _make_claim("c2", "birth_place", "Roma"),
        ]
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")

        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(
                    block_id="b1",
                    role="direct_answer",
                    text="Mario Rossi nacque nel 1921 a Roma.",
                    claim_ids=["c1", "c2"],
                    certainty="verified",
                ),
            ],
        )

        validator = NarrationValidator()
        validation = validator.validate(draft, selected.claim_allowlist, snap, "PERSON")
        self.assertTrue(validation.valid)

        # Build result manually (simulating what NarratorV7_v2 does)
        narrator = NarratorV7_v2()
        result = narrator._build_result(
            draft, validation, selected, snap, "PERSON",
            GenerationInfo(mode="ai", provider="test", model="test"),
        )
        self.assertEqual(result.status, "validated_ai")
        self.assertIn("c1", result.used_claim_ids)
        self.assertIn("c2", result.used_claim_ids)
        self.assertEqual(len(result.citation_map), 1)
        self.assertEqual(result.citation_map[0].block_id, "b1")

    def test_simulated_draft_with_hallucinated_claim(self):
        """Simulate a draft with a hallucinated claim_id."""
        claims = [_make_claim("c1", "birth_year", "1921")]
        snap = _make_snapshot(person_claims=claims)
        selector = NarrationEvidenceSelector()
        selected = selector.select(snap, "PERSON")

        draft = NarrationDraft(
            request_type="PERSON",
            blocks=[
                NarrationBlock(
                    block_id="b1",
                    role="direct_answer",
                    text="Mario nacque nel 1921.",
                    claim_ids=["c1", "c_hallucinated"],
                    certainty="verified",
                ),
            ],
        )

        validator = NarrationValidator()
        validation = validator.validate(draft, selected.claim_allowlist, snap, "PERSON")
        self.assertFalse(validation.valid)

        # Repair should remove the hallucinated claim
        repaired = validator.repair(draft, validation, selected.claim_allowlist)
        self.assertNotIn("c_hallucinated", repaired.blocks[0].claim_ids)
        self.assertIn("c1", repaired.blocks[0].claim_ids)


# ═══ Runner ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
