"""V7.3 Phase D Tests — claim selection, coverage, narration planning, validation."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from domain_model_v73 import (
    Claim, ClaimStatus, ClaimType, Evidence, EvidenceType,
    IdentityCandidate, IdentifierMatch, IdentifierStrength, IdentityStatus,
    evaluate_identity, can_combine_claims,
)
from narration_planner_v73 import (
    ClaimSelector, CoveragePlanner, NarrationPlanner,
    SemanticValidator, GlobalValidator,
    SelectedClaim, CoverageReport, NarrationPlan, NarrationBlock,
    ValidationIssue, PERSON_CLAIM_FIELDS, EVENT_CLAIM_FIELDS,
)

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} — {detail}")


# ─── Helper: create test data ───────────────────────────────────────────────

def make_candidate(query, identifiers, status=None):
    c = IdentityCandidate(query_subject=query, match_identifiers=identifiers)
    if status:
        c.identity_status = status
    else:
        c.identity_status = evaluate_identity(c)
    return c

def make_claim(predicate, value, candidate_id=None, status=ClaimStatus.CANDIDATE, usable=True):
    return Claim(
        predicate=predicate,
        object_value=value,
        candidate_id=candidate_id,
        status=status,
        usable_as_evidence=usable,
    )

def make_evidence(candidate_id, confidence=0.8, role="supports", family_id="fam1"):
    return Evidence(
        candidate_id=candidate_id,
        source_authority=0.9,
        artifact_directness=0.8,
        extraction_confidence=0.9,
        identity_match_confidence=confidence,
        semantic_confidence=0.8,
        temporal_compatibility=1.0,
        geographical_compatibility=0.9,
        source_independence=0.7,
        evidence_role=role,
        family_id=family_id,
    )


# ─── 1. ClaimSelector ───────────────────────────────────────────────────────

print("\n=== 1. ClaimSelector ===")

# Single resolved identity -> claims selected
cand1 = make_candidate("Mario Rossi", [
    IdentifierMatch("nome_cognome", "Mario Rossi", IdentifierStrength.WEAK),
    IdentifierMatch("data_nascita", "1912-01-09", IdentifierStrength.STRONG),
])
claims1 = [
    make_claim("born_at", "1912-01-09", cand1.candidate_id, ClaimStatus.VERIFIED),
    make_claim("captured_at", "Grecia", cand1.candidate_id, ClaimStatus.PROBABLE),
    make_claim("interned_at", "Mauthausen", cand1.candidate_id, ClaimStatus.CANDIDATE),
]
evidence1 = [
    make_evidence(cand1.candidate_id, 0.9, "supports", "fam1"),
    make_evidence(cand1.candidate_id, 0.85, "supports", "fam2"),
]

selector = ClaimSelector()
selected = selector.select_claims(claims1, evidence1, [cand1])
test("3 claims selected for resolved identity", len(selected) == 3, f"got {len(selected)}")
test("No identity warnings for single resolved", len(selector.identity_warnings) == 0)
test("Verified claim with 2 evidence -> CONFIRMED", selected[0].certainty == "CONFIRMED", f"got {selected[0].certainty}")
test("Probable claim -> PROBABLE", selected[1].certainty == "PROBABLE", f"got {selected[1].certainty}")

# Rejected homonym -> claims excluded
cand2 = make_candidate("Luigi Bianchi", [
    IdentifierMatch("nome_cognome", "Luigi Bianchi", IdentifierStrength.WEAK),
    IdentifierMatch("data_nascita", "1910-05-15", IdentifierStrength.STRONG, compatible=False, conflict_reason="different birth date"),
])
claims2 = [
    make_claim("born_at", "1910-05-15", cand2.candidate_id, ClaimStatus.CANDIDATE),
]
selector2 = ClaimSelector()
selected2 = selector2.select_claims(claims2, [], [cand2])
test("Rejected homonym claims excluded", len(selected2) == 0, f"got {len(selected2)}")

# Multiple resolved -> warning, only first used
cand3 = make_candidate("Other Person", [
    IdentifierMatch("data_nascita", "1920-03-10", IdentifierStrength.STRONG),
])
cand3.identity_status = IdentityStatus.RESOLVED
selector3 = ClaimSelector()
selected3 = selector3.select_claims(claims1 + [make_claim("born_at", "1920-03-10", cand3.candidate_id, ClaimStatus.VERIFIED)], evidence1, [cand1, cand3])
test("Multiple resolved -> warning", len(selector3.identity_warnings) > 0)
test("Multiple resolved -> only first candidate claims", all(sc.claim.candidate_id == cand1.candidate_id for sc in selected3 if sc.claim.candidate_id))

# Rejected claim excluded
selector4 = ClaimSelector()
rejected_claim = make_claim("died_at", "1945-01-01", cand1.candidate_id, ClaimStatus.REJECTED)
selected4 = selector4.select_claims([rejected_claim], [], [cand1])
test("Rejected claim excluded", len(selected4) == 0)

# Claim with contradicting evidence
selector5 = ClaimSelector()
conflicting_claim = make_claim("born_at", "1912-01-09", cand1.candidate_id, ClaimStatus.CONFLICTING)
conflicting_evidence = [
    make_evidence(cand1.candidate_id, 0.9, "supports", "fam1"),
    make_evidence(cand1.candidate_id, 0.8, "contradicts", "fam2"),
]
selected5 = selector5.select_claims([conflicting_claim], conflicting_evidence, [cand1])
test("Conflicting claim has has_conflict=True", selected5[0].has_conflict if selected5 else False)
test("Conflicting claim -> CONTRADICTED", selected5[0].certainty == "CONTRADICTED" if selected5 else False)


# ─── 2. CoveragePlanner ─────────────────────────────────────────────────────

print("\n=== 2. CoveragePlanner ===")

planner = CoveragePlanner()

# Person coverage with partial claims
partial_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", "c1"), evidence_count=2, certainty="CONFIRMED"),
    SelectedClaim(claim=make_claim("captured_at", "Grecia", "c1"), evidence_count=1, certainty="PROBABLE"),
]
report = planner.evaluate_person_coverage(partial_selected)
test("Person coverage < 1.0 with partial claims", report.coverage_score < 1.0, f"got {report.coverage_score:.2f}")
test("Person coverage has missing fields", len(report.missing_fields) > 0)
test("Person coverage has critical gaps", any(g.severity == "critical" for g in report.gaps))

# Full person coverage
full_selected = [
    SelectedClaim(claim=make_claim(pred, "val", "c1"), evidence_count=1, certainty="PROBABLE")
    for pred in PERSON_CLAIM_FIELDS
]
report_full = planner.evaluate_person_coverage(full_selected)
test("Person coverage = 1.0 with all fields", report_full.coverage_score == 1.0, f"got {report_full.coverage_score:.2f}")

# Event coverage
event_selected = [
    SelectedClaim(claim=make_claim("event_context", "ctx", "c1"), evidence_count=1, certainty="PROBABLE"),
    SelectedClaim(claim=make_claim("event_outcome", "outcome", "c1"), evidence_count=1, certainty="PROBABLE"),
]
report_evt = planner.evaluate_event_coverage(event_selected)
test("Event coverage < 1.0 with partial", report_evt.coverage_score < 1.0)
test("Event coverage has critical gaps", any(g.severity == "critical" for g in report_evt.gaps))
test("Event report is_event=True", report_evt.is_event)


# ─── 3. NarrationPlanner ────────────────────────────────────────────────────

print("\n=== 3. NarrationPlanner ===")

narr_planner = NarrationPlanner()

# Person plan
person_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912-01-09", "c1"), evidence_count=2, certainty="CONFIRMED", citation_source_ids=["src1"]),
    SelectedClaim(claim=make_claim("captured_at", "Grecia", "c1"), evidence_count=1, certainty="PROBABLE", citation_source_ids=["src2"]),
    SelectedClaim(claim=make_claim("interned_at", "Mauthausen", "c1"), evidence_count=1, certainty="PROBABLE", citation_source_ids=["src2"]),
]
person_coverage = planner.evaluate_person_coverage(person_selected)
person_plan = narr_planner.build_person_plan(person_selected, person_coverage, [])
test("Person plan has blocks", len(person_plan.blocks) > 0)
test("Person plan type = PERSON", person_plan.request_type == "PERSON")
test("Person plan has biographical block", any(b.role == "biographical" for b in person_plan.blocks))
test("Person plan has capture_internment block", any(b.role == "capture_internment" for b in person_plan.blocks))
test("Person plan needs followup (missing critical)", person_plan.needs_followup)

# Event plan
event_selected2 = [
    SelectedClaim(claim=make_claim("event_context", "ctx", "c1"), evidence_count=1, certainty="PROBABLE"),
    SelectedClaim(claim=make_claim("event_outcome", "vittoria", "c1"), evidence_count=1, certainty="PROBABLE"),
    SelectedClaim(claim=make_claim("event_significance", "importante", "c1"), evidence_count=1, certainty="PROBABLE"),
]
event_coverage = planner.evaluate_event_coverage(event_selected2)
event_plan = narr_planner.build_event_plan(event_selected2, event_coverage, [])
test("Event plan has blocks", len(event_plan.blocks) > 0)
test("Event plan type = EVENT", event_plan.request_type == "EVENT")
test("Event plan has event_context block", any(b.role == "event_context" for b in event_plan.blocks))
test("Event plan has event_outcome block", any(b.role == "event_outcome" for b in event_plan.blocks))
test("Event plan needs followup (missing critical)", event_plan.needs_followup)


# ─── 4. SemanticValidator ───────────────────────────────────────────────────

print("\n=== 4. SemanticValidator ===")

sem_validator = SemanticValidator()

# Contradiction detection
contradiction_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", "c1"), evidence_count=1, certainty="PROBABLE", has_conflict=True, conflict_reason="different dates"),
]
contradiction_plan = NarrationPlan(request_type="PERSON")
issues = sem_validator.validate(contradiction_plan, contradiction_selected, [cand1])
test("Contradiction detected", any(i.category == "contradiction" for i in issues))

# Homonym leakage detection
homonym_candidates = [cand1, cand3]
homonym_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", cand1.candidate_id), evidence_count=1, certainty="PROBABLE"),
    SelectedClaim(claim=make_claim("born_at", "1920", cand3.candidate_id), evidence_count=1, certainty="PROBABLE"),
]
issues2 = sem_validator.validate(NarrationPlan(request_type="PERSON"), homonym_selected, homonym_candidates)
test("Homonym leakage detected", any(i.category == "homonym_leakage" for i in issues2))

# Legacy leakage detection
legacy_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", "c1", usable=False), evidence_count=0, certainty="UNCERTAIN"),
]
# Set origin to legacy
legacy_selected[0].claim.origin = "LEGACY_HEURISTIC"
issues3 = sem_validator.validate(NarrationPlan(request_type="PERSON"), legacy_selected, [cand1])
test("Legacy leakage detected", any(i.category == "legacy_leakage" for i in issues3))

# Coverage gap detection
coverage_plan = NarrationPlan(request_type="PERSON", coverage=person_coverage)
issues4 = sem_validator.validate(coverage_plan, person_selected, [cand1])
test("Coverage gap detected", any(i.category == "coverage" for i in issues4))


# ─── 5. GlobalValidator ─────────────────────────────────────────────────────

print("\n=== 5. GlobalValidator ===")

glob_validator = GlobalValidator()

# Claim without evidence
no_evidence_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", "c1", ClaimStatus.CANDIDATE), evidence_count=0, certainty="UNCERTAIN"),
]
issues5 = glob_validator.validate(NarrationPlan(request_type="PERSON"), no_evidence_selected)
test("Claim without evidence -> warning", any(i.category == "evidence" for i in issues5))

# CONFIRMED with insufficient evidence
low_evidence_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", "c1", ClaimStatus.VERIFIED), evidence_count=1, certainty="CONFIRMED"),
]
issues6 = glob_validator.validate(NarrationPlan(request_type="PERSON"), low_evidence_selected)
test("CONFIRMED with 1 evidence -> warning", any(i.category == "certainty" for i in issues6))

# Hallucination detection (AI output with unknown claim IDs)
ai_output = {
    "blocks": [
        {"block_id": "b1", "claim_ids": ["real_claim_1", "hallucinated_claim_1"]},
    ]
}
real_selected = [
    SelectedClaim(claim=make_claim("born_at", "1912", "c1"), evidence_count=1, certainty="PROBABLE"),
]
real_selected[0].claim.claim_id = "real_claim_1"
issues7 = glob_validator.validate(NarrationPlan(request_type="PERSON"), real_selected, ai_output)
test("Hallucination detected", any(i.category == "hallucination" for i in issues7))

# Identity warning propagation
warning_plan = NarrationPlan(request_type="PERSON", identity_warnings=["NO_RESOLVED_IDENTITY"])
issues8 = glob_validator.validate(warning_plan, [])
test("Identity warning propagated", any(i.category == "identity" for i in issues8))


# ─── Summary ────────────────────────────────────────────────────────────────

print(f"\n{'='*80}")
print(f"V7.3 Phase D Tests: {passed} PASS, {failed} FAIL")
print(f"{'='*80}")

if errors:
    print("\nFailures:")
    for e in errors:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)
