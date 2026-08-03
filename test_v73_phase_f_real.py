"""V7.3 Phase F — Test end-to-end con nomi ed eventi reali (diversi dai 9 baseline).

Esegue la pipeline V7.3 completa (text matching -> barriers -> identity ->
claim selection -> coverage -> narration planning -> validation) su 9 nuovi casi:

PERSON (6):
1. ALTA Antonio — internato WWII, deceduto a Brandemburg
2. ARMANNO Luigi A — internato WWII, sorte ignota
3. AMAROTTI Enrico — internato WWII, deceduto a Wasungen
4. ANFOSSO Carlo — internato WWII, deceduto a Kiel
5. ARTI Saverio — internato WWII, sorte ignota
6. ANVISIO Remo — internato WWII, deceduto

EVENT (3):
7. Battaglia del Monte Ortigara (evt_0051) — WWI, 10-25 giu 1917
8. Battaglia di Vittorio Veneto (evt_0020) — WWI, 24 ott - 4 nov 1918
9. Guerra bianca (evt_0061) — WWI, 1915-1918, fronte alpino

Per ogni caso:
- Esegue text matching con keyword/alias dal registro eventi
- Valida barriere temporali e geografiche
- Crea IdentityCandidate e valuta identity resolution
- Crea Claim e Evidence
- Esegue ClaimSelector
- Esegue CoveragePlanner
- Esegue NarrationPlanner
- Esegue SemanticValidator + GlobalValidator
- Riporta metriche
"""
import sys
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from domain_model_v73 import (
    IdentityCandidate, IdentifierMatch, IdentifierStrength, IdentityStatus,
    Claim, ClaimStatus, ClaimType, Evidence, EvidenceType,
    Entity, Relation, RelationStatus, ReviewDecision,
    evaluate_identity, can_combine_claims,
    WarPeriod, SemanticRole,
)
from text_matching_v73 import (
    normalize_text, tokenize, matches_word_boundary,
    classify_keyword_specificity, has_sufficient_specificity,
    parse_name, names_compatible, match_aliases, has_specific_alias_match,
    evaluate_keyword_matches,
)
from barriers_v73 import (
    DateRole, check_temporal_compatibility, check_geographic_compatibility,
    evaluate_match, MatchEvaluation,
)
from narration_planner_v73 import (
    ClaimSelector, CoveragePlanner, NarrationPlanner,
    SemanticValidator, GlobalValidator,
    SelectedClaim, CoverageReport, NarrationPlan,
    PERSON_CLAIM_FIELDS, EVENT_CLAIM_FIELDS,
)

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"

# ─── Test cases ─────────────────────────────────────────────────────────────

PERSON_CASES = [
    {
        "id": 2344,
        "cognome": "ALTA",
        "nome": "Antonio",
        "luogo_internamento": "Brandemburg",
        "sorte": "deceduto",
        "query": "ALTA Antonio",
    },
    {
        "id": 2357,
        "cognome": "ARMANNO",
        "nome": "Luigi A",
        "luogo_internamento": None,
        "sorte": None,
        "query": "ARMANNO Luigi A",
    },
    {
        "id": 2360,
        "cognome": "AMAROTTI",
        "nome": "Enrico",
        "luogo_internamento": "Wasungen",
        "sorte": "deceduto",
        "query": "AMAROTTI Enrico",
    },
    {
        "id": 2353,
        "cognome": "ANFOSSO",
        "nome": "Carlo",
        "luogo_internamento": "Kiel",
        "sorte": "deceduto",
        "query": "ANFOSSO Carlo",
    },
    {
        "id": 2350,
        "cognome": "ARTI",
        "nome": "Saverio",
        "luogo_internamento": None,
        "sorte": None,
        "query": "ARTI Saverio",
    },
    {
        "id": 2356,
        "cognome": "ANVISIO",
        "nome": "Remo",
        "luogo_internamento": None,
        "sorte": "deceduto",
        "query": "ANVISIO Remo",
    },
]

EVENT_CASES = [
    {
        "stable_id": "evt_0051",
        "name": "Battaglia del Monte Ortigara",
        "war": "WWI",
        "data_inizio": "1917-06-10",
        "data_fine": "1917-06-25",
        "keywords": ["Ortigara", "Ortigana", "Altopiano", "Asiago"],
    },
    {
        "stable_id": "evt_0020",
        "name": "Battaglia di Vittorio Veneto",
        "war": "WWI",
        "data_inizio": "1918-10-24",
        "data_fine": "1918-11-04",
        "keywords": ["Vittorio Veneto", "Piave", "ritirata", "Grappa"],
    },
    {
        "stable_id": "evt_0061",
        "name": "Guerra bianca",
        "war": "WWI",
        "data_inizio": "1915-06-23",
        "data_fine": "1918-11-04",
        "keywords": ["Guerra bianca", "Adamello", "Marmolada", "alpini", "ghiaccio"],
    },
]


# ─── Run tests ──────────────────────────────────────────────────────────────

results = []

def run_person_test(case):
    """Run V7.3 pipeline for a PERSON case."""
    print(f"\n{'='*80}")
    print(f"PERSON CASE: {case['query']} (id={case['id']})")
    print(f"{'='*80}")

    result = {
        "case": case["query"],
        "type": "PERSON",
        "id": case["id"],
        "steps": {},
        "metrics": {},
        "issues": [],
    }

    # ─── Step 1: Text matching — name parsing ───────────────────────────
    cognome, nome = parse_name(case["query"])
    print(f"\n  [1] Name parsing: cognome={cognome}, nome={nome}")
    result["steps"]["name_parsing"] = {"cognome": cognome, "nome": nome}
    test_ok = cognome == case["cognome"] and (nome == case["nome"] or case["nome"] is None)
    result["steps"]["name_parsing"]["correct"] = test_ok

    # ─── Step 2: Identity candidate ─────────────────────────────────────
    identifiers = [
        IdentifierMatch(
            identifier_type="nome_cognome",
            value=f"{cognome} {nome}".strip(),
            strength=IdentifierStrength.WEAK,
        ),
    ]

    # Add internment location as medium identifier if available
    if case.get("luogo_internamento"):
        identifiers.append(IdentifierMatch(
            identifier_type="luogo_internamento",
            value=case["luogo_internamento"],
            strength=IdentifierStrength.MEDIUM,
        ))

    # Add sorte as weak context
    if case.get("sorte"):
        identifiers.append(IdentifierMatch(
            identifier_type="sorte",
            value=case["sorte"],
            strength=IdentifierStrength.WEAK,
        ))

    candidate = IdentityCandidate(
        query_subject=case["query"],
        match_identifiers=identifiers,
    )
    candidate.identity_status = evaluate_identity(candidate)
    print(f"\n  [2] Identity: status={candidate.identity_status.value}, strong={candidate.strong_count}, medium={candidate.medium_count}, weak={candidate.weak_count}")
    result["steps"]["identity"] = {
        "status": candidate.identity_status.value,
        "strong": candidate.strong_count,
        "medium": candidate.medium_count,
        "weak": candidate.weak_count,
    }

    # ─── Step 3: Create claims from DB record ───────────────────────────
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM internati WHERE id = ?", (case["id"],))
    row = cur.fetchone()
    conn.close()

    claims = []
    if row:
        r = dict(row)
        if r.get("luogo_internamento"):
            claims.append(Claim(
                predicate="interned_at",
                object_value=r["luogo_internamento"],
                candidate_id=candidate.candidate_id,
                status=ClaimStatus.PROBABLE,
                usable_as_evidence=True,
                semantic_role=SemanticRole.DETENTION_PLACE.value,
            ))
        if r.get("sorte"):
            claims.append(Claim(
                predicate="died_at" if r["sorte"] == "deceduto" else "liberated_from",
                object_value=r["sorte"],
                candidate_id=candidate.candidate_id,
                status=ClaimStatus.PROBABLE,
                usable_as_evidence=True,
            ))
        if r.get("luogo_nascita"):
            claims.append(Claim(
                predicate="born_in",
                object_value=r["luogo_nascita"],
                candidate_id=candidate.candidate_id,
                status=ClaimStatus.CANDIDATE,
                usable_as_evidence=True,
                semantic_role=SemanticRole.BIRTH_PLACE.value,
            ))
        if r.get("grado"):
            claims.append(Claim(
                predicate="served_in",
                object_value=r["grado"],
                candidate_id=candidate.candidate_id,
                status=ClaimStatus.CANDIDATE,
                usable_as_evidence=True,
            ))

    print(f"\n  [3] Claims created: {len(claims)}")
    result["steps"]["claims_created"] = len(claims)

    # ─── Step 4: Create evidence ────────────────────────────────────────
    evidence = []
    for claim in claims:
        ev = Evidence(
            candidate_id=candidate.candidate_id,
            evidence_type=EvidenceType.PERSON_EVIDENCE,
            evidence_role="supports",
            source_authority=0.7,
            artifact_directness=0.8,
            extraction_confidence=0.9,
            identity_match_confidence=0.6 if candidate.strong_count == 0 else 0.9,
            semantic_confidence=0.8,
            temporal_compatibility=1.0,
            geographical_compatibility=0.8,
            source_independence=0.5,
            family_id="db_internati",
        )
        claim.evidence_ids.append(ev.evidence_id)
        evidence.append(ev)

    print(f"  [4] Evidence created: {len(evidence)}")
    result["steps"]["evidence_created"] = len(evidence)

    # ─── Step 5: Claim selection ────────────────────────────────────────
    selector = ClaimSelector()
    selected = selector.select_claims(claims, evidence, [candidate])
    print(f"\n  [5] Claim selection: {len(selected)} selected, {len(selector.excluded)} excluded")
    if selector.identity_warnings:
        print(f"      Warnings: {selector.identity_warnings}")
        result["issues"].extend(selector.identity_warnings)
    result["steps"]["claim_selection"] = {
        "selected": len(selected),
        "excluded": len(selector.excluded),
        "warnings": selector.identity_warnings,
    }

    # ─── Step 6: Coverage ───────────────────────────────────────────────
    planner = CoveragePlanner()
    coverage = planner.evaluate_person_coverage(selected)
    print(f"\n  [6] Coverage: score={coverage.coverage_score:.2f}, covered={len(coverage.covered_fields)}, missing={len(coverage.missing_fields)}")
    critical_gaps = [g for g in coverage.gaps if g.severity == "critical"]
    if critical_gaps:
        print(f"      Critical gaps: {[g.field for g in critical_gaps]}")
    result["steps"]["coverage"] = {
        "score": round(coverage.coverage_score, 2),
        "covered": len(coverage.covered_fields),
        "missing": len(coverage.missing_fields),
        "critical_gaps": [g.field for g in critical_gaps],
    }

    # ─── Step 7: Narration planning ─────────────────────────────────────
    narr_planner = NarrationPlanner()
    plan = narr_planner.build_person_plan(selected, coverage, selector.identity_warnings)
    print(f"\n  [7] Narration plan: {len(plan.blocks)} blocks, needs_followup={plan.needs_followup}")
    for b in plan.blocks:
        print(f"      block {b.block_id}: role={b.role}, certainty={b.certainty}, claims={len(b.claim_ids)}, sources={len(b.source_ids)}")
    result["steps"]["narration_plan"] = {
        "blocks": len(plan.blocks),
        "needs_followup": plan.needs_followup,
        "followup_question": plan.followup_question,
        "block_roles": [b.role for b in plan.blocks],
    }

    # ─── Step 8: Validation ─────────────────────────────────────────────
    sem_validator = SemanticValidator()
    sem_issues = sem_validator.validate(plan, selected, [candidate])

    glob_validator = GlobalValidator()
    glob_issues = glob_validator.validate(plan, selected)

    all_issues = sem_issues + glob_issues
    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]
    infos = [i for i in all_issues if i.severity == "info"]

    print(f"\n  [8] Validation: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")
    for i in all_issues:
        print(f"      [{i.severity}] {i.category}: {i.message}")
    result["steps"]["validation"] = {
        "errors": len(errors),
        "warnings": len(warnings),
        "infos": len(infos),
        "issues": [{"severity": i.severity, "category": i.category, "message": i.message} for i in all_issues],
    }

    # ─── Metrics ────────────────────────────────────────────────────────
    result["metrics"] = {
        "execution_success": True,
        "identity_resolved": candidate.identity_status == IdentityStatus.RESOLVED,
        "identity_status": candidate.identity_status.value,
        "claims_selected": len(selected),
        "coverage_score": round(coverage.coverage_score, 2),
        "narration_blocks": len(plan.blocks),
        "has_conflicts": plan.has_conflicts,
        "needs_followup": plan.needs_followup,
        "validation_errors": len(errors),
        "validation_warnings": len(warnings),
        "legacy_leakage": any(i.category == "legacy_leakage" for i in all_issues),
        "homonym_leakage": any(i.category == "homonym_leakage" for i in all_issues),
    }

    return result


def run_event_test(case):
    """Run V7.3 pipeline for an EVENT case."""
    print(f"\n{'='*80}")
    print(f"EVENT CASE: {case['name']} ({case['stable_id']})")
    print(f"{'='*80}")

    result = {
        "case": case["name"],
        "type": "EVENT",
        "stable_id": case["stable_id"],
        "steps": {},
        "metrics": {},
        "issues": [],
    }

    # ─── Step 1: Load event from canonical registry ─────────────────────
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM canonical_event_registry WHERE stable_id = ?", (case["stable_id"],))
    evt = cur.fetchone()
    conn.close()

    if not evt:
        print(f"  ERROR: Event {case['stable_id']} not found in registry")
        result["metrics"]["execution_success"] = False
        return result

    evt = dict(evt)
    aliases = json.loads(evt.get("aliases_json") or "[]")
    keywords = json.loads(evt.get("keywords_json") or "[]")
    all_keywords = list(set(aliases + keywords + case["keywords"]))

    print(f"\n  [1] Event loaded: {evt['name']} | {evt['data_inizio']} -> {evt['data_fine']} | war={evt['war']}")
    print(f"      Aliases: {aliases}")
    print(f"      Keywords: {keywords}")
    result["steps"]["event_loaded"] = {
        "name": evt["name"],
        "data_inizio": evt["data_inizio"],
        "data_fine": evt["data_fine"],
        "war": evt["war"],
        "aliases": aliases,
        "keywords": keywords,
    }

    # ─── Step 2: Text matching — keyword specificity ────────────────────
    text_fields = {
        "luogo_text": evt.get("general_location", ""),
        "description": evt.get("description", ""),
    }

    # Simulate matching against a sample document text
    sample_text = f"Documenti relativi alla {evt['name']}. {evt.get('description', '')}"
    keyword_matches = evaluate_keyword_matches(all_keywords, sample_text)
    specific_matches = [m for m in keyword_matches if m.matched and m.specificity == "specific"]
    generic_matches = [m for m in keyword_matches if m.matched and m.specificity == "generic"]

    print(f"\n  [2] Text matching: {len(keyword_matches)} keywords, {len(specific_matches)} specific, {len(generic_matches)} generic")
    for m in keyword_matches:
        if m.matched:
            print(f"      MATCH: '{m.keyword}' (specificity={m.specificity})")
    result["steps"]["text_matching"] = {
        "total_keywords": len(keyword_matches),
        "specific_matches": len(specific_matches),
        "generic_matches": len(generic_matches),
        "has_sufficient_specificity": len(specific_matches) > 0,
    }

    # ─── Step 3: Temporal barrier check ─────────────────────────────────
    # Check: WWII source vs WWI event
    wwii_temporal = check_temporal_compatibility(
        source_date="1943-09-08",
        source_date_role=DateRole.EVENT_START,
        target_date_start=evt["data_inizio"],
        target_date_end=evt["data_fine"],
        target_war=WarPeriod(evt["war"]),
    )
    # Check: same war period
    same_war_temporal = check_temporal_compatibility(
        source_date=evt["data_inizio"],
        source_date_role=DateRole.EVENT_START,
        target_date_start=evt["data_inizio"],
        target_date_end=evt["data_fine"],
        target_war=WarPeriod(evt["war"]),
    )
    print(f"\n  [3] Temporal barriers:")
    print(f"      WWII source vs WWI event: veto={wwii_temporal.veto}, compatible={wwii_temporal.compatible}")
    print(f"      Same war source: veto={same_war_temporal.veto}, compatible={same_war_temporal.compatible}")
    result["steps"]["temporal_barriers"] = {
        "cross_war_veto": wwii_temporal.veto,
        "same_war_compatible": same_war_temporal.compatible,
    }

    # ─── Step 4: Geographic barrier check ───────────────────────────────
    geo_death = check_geographic_compatibility(
        "luogo_morte", "Roma", "luogo", evt.get("general_location", ""),
    )
    geo_birth = check_geographic_compatibility(
        "luogo_nascita", "Torino", "luogo", evt.get("general_location", ""),
    )
    print(f"\n  [4] Geographic barriers:")
    print(f"      Death place as event place: compatible={geo_death.compatible}")
    print(f"      Birth place as event place: compatible={geo_birth.compatible}")
    result["steps"]["geographic_barriers"] = {
        "death_as_event_compatible": geo_death.compatible,
        "birth_as_event_compatible": geo_birth.compatible,
    }

    # ─── Step 5: Create event claims ────────────────────────────────────
    # Simulate claims for stratified event coverage
    event_claims = []
    coverage_data = {
        "event_context": f"Contesto: {evt.get('description', 'N/D')[:100]}",
        "event_location": evt.get("general_location", "N/D"),
        "event_duration": f"{evt['data_inizio']} - {evt['data_fine']}",
    }

    for pred, value in coverage_data.items():
        event_claims.append(Claim(
            predicate=pred,
            object_value=value,
            status=ClaimStatus.PROBABLE,
            usable_as_evidence=True,
            claim_type=ClaimType.EVENT_CLAIM,
        ))

    print(f"\n  [5] Event claims created: {len(event_claims)}")
    result["steps"]["claims_created"] = len(event_claims)

    # ─── Step 6: Evidence ───────────────────────────────────────────────
    event_evidence = []
    for claim in event_claims:
        ev = Evidence(
            evidence_type=EvidenceType.EVENT_CONTEXT,
            evidence_role="supports",
            source_authority=0.9,
            artifact_directness=0.8,
            extraction_confidence=0.85,
            identity_match_confidence=1.0,
            semantic_confidence=0.9,
            temporal_compatibility=1.0,
            geographical_compatibility=0.9,
            source_independence=0.7,
            family_id="canonical_event_registry",
        )
        claim.evidence_ids.append(ev.evidence_id)
        event_evidence.append(ev)

    # ─── Step 7: Claim selection (no identity for events) ───────────────
    selector = ClaimSelector()
    # For events, use a single dummy candidate
    event_candidate = IdentityCandidate(
        query_subject=evt["name"],
        match_identifiers=[IdentifierMatch("event_name", evt["name"], IdentifierStrength.STRONG)],
    )
    event_candidate.identity_status = IdentityStatus.RESOLVED
    for c in event_claims:
        c.candidate_id = event_candidate.candidate_id

    selected = selector.select_claims(event_claims, event_evidence, [event_candidate])
    print(f"\n  [6] Claim selection: {len(selected)} selected")
    result["steps"]["claim_selection"] = {"selected": len(selected)}

    # ─── Step 8: Coverage ───────────────────────────────────────────────
    planner = CoveragePlanner()
    coverage = planner.evaluate_event_coverage(selected)
    print(f"\n  [7] Event coverage: score={coverage.coverage_score:.2f}")
    covered_dims = list(coverage.covered_fields)
    missing_dims = list(coverage.missing_fields)
    critical_gaps = [g for g in coverage.gaps if g.severity == "critical"]
    print(f"      Covered: {covered_dims}")
    print(f"      Missing: {missing_dims}")
    if critical_gaps:
        print(f"      Critical gaps: {[g.field for g in critical_gaps]}")
    result["steps"]["coverage"] = {
        "score": round(coverage.coverage_score, 2),
        "covered": covered_dims,
        "missing": missing_dims,
        "critical_gaps": [g.field for g in critical_gaps],
    }

    # ─── Step 9: Narration planning ─────────────────────────────────────
    narr_planner = NarrationPlanner()
    plan = narr_planner.build_event_plan(selected, coverage, [])
    print(f"\n  [8] Narration plan: {len(plan.blocks)} blocks, needs_followup={plan.needs_followup}")
    for b in plan.blocks:
        print(f"      block {b.block_id}: role={b.role}, certainty={b.certainty}")
    result["steps"]["narration_plan"] = {
        "blocks": len(plan.blocks),
        "needs_followup": plan.needs_followup,
        "block_roles": [b.role for b in plan.blocks],
    }

    # ─── Step 10: Validation ────────────────────────────────────────────
    sem_validator = SemanticValidator()
    sem_issues = sem_validator.validate(plan, selected, [event_candidate])
    glob_validator = GlobalValidator()
    glob_issues = glob_validator.validate(plan, selected)
    all_issues = sem_issues + glob_issues
    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    print(f"\n  [9] Validation: {len(errors)} errors, {len(warnings)} warnings")
    for i in all_issues:
        print(f"      [{i.severity}] {i.category}: {i.message}")
    result["steps"]["validation"] = {
        "errors": len(errors),
        "warnings": len(warnings),
        "issues": [{"severity": i.severity, "category": i.category, "message": i.message} for i in all_issues],
    }

    # ─── Metrics ────────────────────────────────────────────────────────
    result["metrics"] = {
        "execution_success": True,
        "text_match_specific": len(specific_matches) > 0,
        "cross_war_temporal_veto": wwii_temporal.veto,
        "geographic_barrier_death": not geo_death.compatible,
        "claims_selected": len(selected),
        "coverage_score": round(coverage.coverage_score, 2),
        "narration_blocks": len(plan.blocks),
        "needs_followup": plan.needs_followup,
        "validation_errors": len(errors),
        "validation_warnings": len(warnings),
        "legacy_leakage": any(i.category == "legacy_leakage" for i in all_issues),
        "critical_coverage_gaps": len(critical_gaps),
    }

    return result


# ─── Main ───────────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("V7.3 PHASE F — TEST END-TO-END CON NOMI ED EVENTI REALI")
print("=" * 80)

all_results = []

# Run PERSON cases
for case in PERSON_CASES:
    result = run_person_test(case)
    all_results.append(result)

# Run EVENT cases
for case in EVENT_CASES:
    result = run_event_test(case)
    all_results.append(result)

# ─── Summary ────────────────────────────────────────────────────────────────

print(f"\n\n{'='*80}")
print("SUMMARY — V7.3 PIPELINE RESULTS")
print(f"{'='*80}")
print(f"{'Case':<35} {'Type':<8} {'Identity':<15} {'Claims':<7} {'Cover':<7} {'Blocks':<7} {'Errors':<7} {'Leak':<6}")
print("-" * 80)

for r in all_results:
    m = r["metrics"]
    case_name = r["case"][:33]
    case_type = r["type"]
    identity = m.get("identity_status", "N/A")
    claims = m.get("claims_selected", 0)
    coverage = m.get("coverage_score", 0)
    blocks = m.get("narration_blocks", 0)
    errors = m.get("validation_errors", 0)
    leak = "YES" if m.get("legacy_leakage", False) else "NO"
    print(f"{case_name:<35} {case_type:<8} {identity:<15} {claims:<7} {coverage:<7} {blocks:<7} {errors:<7} {leak:<6}")

# ─── Aggregate metrics ──────────────────────────────────────────────────────

print(f"\n{'='*80}")
print("AGGREGATE METRICS")
print(f"{'='*80}")

total = len(all_results)
exec_success = sum(1 for r in all_results if r["metrics"].get("execution_success"))
identity_resolved = sum(1 for r in all_results if r["metrics"].get("identity_resolved") or r["type"] == "EVENT")
no_legacy_leakage = sum(1 for r in all_results if not r["metrics"].get("legacy_leakage", False))
no_homonym_leakage = sum(1 for r in all_results if not r["metrics"].get("homonym_leakage", False))
no_validation_errors = sum(1 for r in all_results if r["metrics"].get("validation_errors", 0) == 0)
cross_war_veto_works = sum(1 for r in all_results if r["type"] == "EVENT" and r["metrics"].get("cross_war_temporal_veto"))

print(f"  execution_success:         {exec_success}/{total}")
print(f"  identity_resolved:         {identity_resolved}/{total}")
print(f"  no_legacy_leakage:         {no_legacy_leakage}/{total}")
print(f"  no_homonym_leakage:        {no_homonym_leakage}/{total}")
print(f"  no_validation_errors:      {no_validation_errors}/{total}")
print(f"  cross_war_temporal_veto:   {cross_war_veto_works}/3 (events)")

# ─── Save results ───────────────────────────────────────────────────────────

output = {
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "version": "7.3.0",
    "total_cases": total,
    "results": all_results,
    "aggregate": {
        "execution_success": exec_success,
        "identity_resolved": identity_resolved,
        "no_legacy_leakage": no_legacy_leakage,
        "no_homonym_leakage": no_homonym_leakage,
        "no_validation_errors": no_validation_errors,
    },
}

output_path = Path(__file__).parent / "V73_PHASE_F_RESULTS.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nResults saved to {output_path}")
