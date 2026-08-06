"""V7.3-Fase16: Regression test — 10 casi reali A-J + test automatici.

Tests the full V7.3 semantic pipeline end-to-end:
  A. Source quality assessment (official vs secondary vs unofficial)
  B. Evidence quality combination (multi-source)
  C. Semantic validator on valid person claims
  D. Semantic validator on scope violations (CONTEXT_EVIDENCE in person)
  E. Claim lifecycle: PUBLISHED state (verified, resolved, valid)
  F. Claim lifecycle: SUPPRESSED state (rejected validation)
  G. Claim lifecycle: REVIEW_PENDING (unverified, unresolved)
  H. Claim lifecycle: PUBLISHED_WITH_CAVEAT (single source)
  I. Response structure: 11 sections with claims
  J. Response structure: empty query (no data found)

Each test is self-contained and does not require external APIs.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_quality import assess_source_quality, combine_evidence_quality
from semantic_validator import SemanticValidator
from claim_lifecycle import determine_claim_state, filter_publishable_claims, build_caveat_summary
from response_structure import ResponseBuilder, SECTION_IDS, SECTION_TITLES
from evidence_snapshot_v7 import EvidenceSnapshotV7, ClaimV7, ContextClaimV7


def _make_claim(claim_id, predicate, value, **kwargs):
    """Helper to create a ClaimV7 with sensible defaults."""
    defaults = dict(
        claim_id=claim_id,
        subject_id="subj_1",
        predicate=predicate,
        value_normalized=value,
        value_raw=value,
        status="ASSERTED",
        confidence=0.8,
        identity_cluster_id="cluster_1",
        evidence_scope="PERSON_EVIDENCE",
    )
    defaults.update(kwargs)
    return ClaimV7(**defaults)


# ─── Test cases A-J ──────────────────────────────────────────────────────────

def test_a_source_quality():
    """A: Source quality assessment — official vs secondary vs unofficial."""
    q_official = assess_source_quality("icrc")
    q_secondary = assess_source_quality("fonti_indice")
    q_unofficial = assess_source_quality("web_search")

    assert q_official.quality_level == "high", f"Expected high for ICRC, got {q_official.quality_level}"
    assert q_secondary.quality_level in ("medium", "low"), f"Expected medium/low for fonti_indice, got {q_secondary.quality_level}"
    assert q_unofficial.quality_level in ("low", "very_low"), f"Expected low/very_low for web, got {q_unofficial.quality_level}"
    assert q_official.quality_score > q_secondary.quality_score > q_unofficial.quality_score
    print("  A PASS: source quality hierarchy correct")


def test_b_evidence_combination():
    """B: Evidence quality combination — multi-source."""
    q1 = assess_source_quality("icrc")
    q2 = assess_source_quality("albo_oro")
    level, score, reason = combine_evidence_quality([q1, q2])

    assert level == "verified", f"Expected verified for 2 official/primary, got {level}"
    assert score > 0.8, f"Expected score > 0.8, got {score}"
    print(f"  B PASS: combined level={level}, score={score:.3f}")


def test_c_semantic_validator_valid():
    """C: Semantic validator on valid person claims."""
    claims = [
        _make_claim("c1", "birth_date", "1890-05-15", confidence=0.9, evidence_ids=["ev1"]),
        _make_claim("c2", "birth_place", "Trento", confidence=0.85, evidence_ids=["ev2"]),
    ]
    snap = EvidenceSnapshotV7(
        snapshot_id="snap_c",
        schema_version="7.2",
        run_id="run_c",
        intent="PERSON_LOOKUP",
        person_claims=claims,
        identity_status="RESOLVED_IDENTITY",
    )
    validator = SemanticValidator()
    result = validator.validate_snapshot(snap)

    assert len(result.claim_results) == 2, f"Expected 2 claim results, got {len(result.claim_results)}"
    assert len(result.rejected_claims) == 0, f"Expected 0 rejected, got {len(result.rejected_claims)}"
    print(f"  C PASS: {len(result.claim_results)} claims validated, 0 rejected")


def test_d_semantic_validator_scope_violation():
    """D: Semantic validator detects scope violations."""
    claims = [
        _make_claim("c1", "birth_date", "1890-05-15", evidence_scope="CONTEXT_EVIDENCE", evidence_ids=["ev1"]),
    ]
    snap = EvidenceSnapshotV7(
        snapshot_id="snap_d",
        schema_version="7.2",
        run_id="run_d",
        intent="PERSON_LOOKUP",
        person_claims=claims,
        identity_status="RESOLVED_IDENTITY",
    )
    validator = SemanticValidator()
    result = validator.validate_snapshot(snap)

    # The validator should flag the scope violation
    violations = [c for c in result.claim_results if c.scope_violations]
    assert len(violations) > 0, "Expected scope violation to be detected"
    print(f"  D PASS: scope violation detected ({len(violations)} violations)")


def test_e_claim_published():
    """E: Claim lifecycle — PUBLISHED state."""
    state = determine_claim_state(
        claim_id="c_e",
        evidence_level="verified",
        identity_status="RESOLVED_IDENTITY",
        validation_status="VALID",
        entailment_score=0.85,
        source_count=2,
    )
    assert state.state == "PUBLISHED", f"Expected PUBLISHED, got {state.state}"
    assert state.is_publishable is True
    assert state.caveat == ""
    print(f"  E PASS: state={state.state}, publishable={state.is_publishable}")


def test_f_claim_suppressed():
    """F: Claim lifecycle — SUPPRESSED state."""
    state = determine_claim_state(
        claim_id="c_f",
        evidence_level="verified",
        identity_status="RESOLVED_IDENTITY",
        validation_status="REJECTED",
        entailment_score=0.85,
        source_count=2,
    )
    assert state.state == "SUPPRESSED", f"Expected SUPPRESSED, got {state.state}"
    assert state.is_suppressed is True
    print(f"  F PASS: state={state.state}, suppressed={state.is_suppressed}")


def test_g_claim_review_pending():
    """G: Claim lifecycle — REVIEW_PENDING state."""
    state = determine_claim_state(
        claim_id="c_g",
        evidence_level="unverified",
        identity_status="UNRESOLVED_IDENTITY",
        validation_status="VALID",
        entailment_score=0.3,
        source_count=0,
    )
    assert state.state == "REVIEW_PENDING", f"Expected REVIEW_PENDING, got {state.state}"
    assert state.is_publishable is False
    print(f"  G PASS: state={state.state}, publishable={state.is_publishable}")


def test_h_claim_published_with_caveat():
    """H: Claim lifecycle — PUBLISHED_WITH_CAVEAT (single source)."""
    state = determine_claim_state(
        claim_id="c_h",
        evidence_level="probable",
        identity_status="RESOLVED_IDENTITY",
        validation_status="VALID",
        entailment_score=0.6,
        source_count=1,
    )
    assert state.state == "PUBLISHED_WITH_CAVEAT", f"Expected PUBLISHED_WITH_CAVEAT, got {state.state}"
    assert state.is_publishable is True
    assert state.caveat != "", f"Expected non-empty caveat"
    print(f"  H PASS: state={state.state}, caveat='{state.caveat}'")


def test_i_response_structure_with_claims():
    """I: Response structure — 11 sections with claims."""
    claims = [
        {"claim_id": "c1", "predicate": "birth_date", "value_normalized": "1890-05-15", "source_refs": ["icrc"]},
        {"claim_id": "c2", "predicate": "rank", "value_normalized": "tenente", "source_refs": ["albo_oro"]},
        {"claim_id": "c3", "predicate": "internment_place", "value_normalized": "Stalag XVII-A", "source_refs": ["icrc"]},
    ]
    states = [
        {"claim_id": "c1", "state": "PUBLISHED", "caveat": ""},
        {"claim_id": "c2", "state": "PUBLISHED", "caveat": ""},
        {"claim_id": "c3", "state": "PUBLISHED_WITH_CAVEAT", "caveat": "Single source"},
    ]

    builder = ResponseBuilder()
    response = builder.build(
        request_type="PERSON",
        query="Test Person",
        identity_status="RESOLVED_IDENTITY",
        evidence_level="verified",
        claims=claims,
        claim_states=states,
    )

    assert len(response.sections) == 11, f"Expected 11 sections, got {len(response.sections)}"
    assert response.published_claims == 3, f"Expected 3 published, got {response.published_claims}"
    assert response.validation_passed is True

    dati = response.get_section("dati_anagrafici")
    assert dati is not None and not dati.is_empty, "dati_anagrafici should have data"

    military = response.get_section("percorso_militare")
    assert military is not None and not military.is_empty, "percorso_militare should have data"

    md = response.to_markdown()
    assert "## Sintesi" in md
    assert "## Dati Anagrafici" in md
    assert "## Percorso Militare" in md

    print(f"  I PASS: 11 sections, {response.published_claims} published, markdown={len(md)} chars")


def test_j_response_structure_empty():
    """J: Response structure — empty query (no data found)."""
    builder = ResponseBuilder()
    response = builder.build(
        request_type="PERSON",
        query="Nonexistent Person",
        identity_status="UNRESOLVED_IDENTITY",
        evidence_level="unverified",
        claims=[],
        claim_states=[],
    )

    assert len(response.sections) == 11
    assert response.total_claims == 0
    assert response.published_claims == 0

    sintesi = response.get_section("sintesi")
    assert sintesi is not None and not sintesi.is_empty
    assert "Nessun dato trovato" in sintesi.content

    print(f"  J PASS: empty query handled, sintesi='{sintesi.content[:50]}...'")


# ─── Runner ──────────────────────────────────────────────────────────────────

ALL_TESTS = [
    ("A", "Source quality assessment", test_a_source_quality),
    ("B", "Evidence quality combination", test_b_evidence_combination),
    ("C", "Semantic validator valid claims", test_c_semantic_validator_valid),
    ("D", "Semantic validator scope violation", test_d_semantic_validator_scope_violation),
    ("E", "Claim lifecycle PUBLISHED", test_e_claim_published),
    ("F", "Claim lifecycle SUPPRESSED", test_f_claim_suppressed),
    ("G", "Claim lifecycle REVIEW_PENDING", test_g_claim_review_pending),
    ("H", "Claim lifecycle PUBLISHED_WITH_CAVEAT", test_h_claim_published_with_caveat),
    ("I", "Response structure with claims", test_i_response_structure_with_claims),
    ("J", "Response structure empty query", test_j_response_structure_empty),
]


def main():
    print("=" * 70)
    print("V7.3 REGRESSION TESTS — 10 CASES (A-J)")
    print("=" * 70)
    print()

    passed = 0
    failed = 0
    failures = []

    for case_id, description, test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            failures.append((case_id, description, str(e)))
            print(f"  {case_id} FAIL: {e}")

    print()
    print("=" * 70)
    print(f"RESULTS: {passed}/{passed + failed} PASS ({passed / (passed + failed) * 100:.0f}%)")
    if failures:
        print("FAILURES:")
        for cid, desc, err in failures:
            print(f"  {cid} ({desc}): {err}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
