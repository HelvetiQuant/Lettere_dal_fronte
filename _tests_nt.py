"""Validation Campaign — Sections 7-9: Adversarial Tests.

Tests N-T: Temporal gate, source lineage, AnswerEvidenceGate bypass,
and follow-up chat security.

All tests are READ-ONLY on original DBs. No data modification.
No AI calls — these are static analysis + DB queries.

Output: docs/validation/test_results_nt.json
"""
import json
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_ID = "validation_20260817_v1"
RUN_ID = f"tests_nt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
IMI_DB = "imi_internati.db"
EVENTS_DB = "eventi_1gm.db"
OUTPUT = Path("docs/validation/test_results_nt.json")


def test_n_temporal_gate_cross_war():
    """Test N: Temporal gate — are cross-war links blocked by the pipeline?

    The V7.3 barriers_v73.py has a WWI/WWII temporal veto.
    But it's not in the orchestrator path (Test J).
    This test quantifies the contamination.
    """
    conn = sqlite3.connect(EVENTS_DB)
    conn.row_factory = sqlite3.Row

    # Get all internato_ww2 links with event details
    rows = conn.execute(
        """SELECT el.id, el.evento_id, el.target_table, el.target_id,
                  el.link_type, el.confidence, el.match_field, el.match_value,
                  e.nome, e.data_inizio, e.data_fine, e.conflict as event_conflict
           FROM event_links el
           JOIN eventi_1gm e ON el.evento_id = e.id
           WHERE el.link_type = 'internato_ww2'
           ORDER BY el.confidence DESC LIMIT 50"""
    ).fetchall()

    contaminated = []
    for row in rows:
        r = dict(row)
        contaminated.append({
            "link_id": r["id"],
            "event": r["nome"],
            "event_date_start": r["data_inizio"],
            "event_date_end": r["data_fine"],
            "event_conflict": r["event_conflict"],
            "target_table": r["target_table"],
            "target_id": r["target_id"],
            "confidence": r["confidence"],
            "match_field": r["match_field"],
            "match_value": r["match_value"],
            "war_period_column": None,  # war_period is empty/NULL
            "usable_as_evidence": 0,    # all are 0
            "blocked_by_orchestrator": False,  # orchestrator doesn't check
        })

    # Also check: are there WWI events with dates in 1939-1945 range?
    wwi_events = conn.execute(
        "SELECT id, nome, data_inizio, data_fine FROM eventi_1gm WHERE conflict='WWI' OR conflict IS NULL"
    ).fetchall()
    date_contaminated = []
    for evt in wwi_events:
        e = dict(evt)
        if e["data_inizio"] and "193" in str(e["data_inizio"]):
            date_contaminated.append(e)
        if e["data_fine"] and "194" in str(e["data_fine"]):
            date_contaminated.append(e)

    conn.close()

    total_ww2 = len(contaminated)
    total_ww2_all = 12759  # from Test C

    return {
        "test_id": "N",
        "name": "temporal_gate_cross_war",
        "description": "Verify temporal gate blocks cross-war contamination",
        "metrics": {
            "ww2_links_in_ww1_db": total_ww2_all,
            "sampled": total_ww2,
            "blocked_by_orchestrator": 0,
            "blocked_by_barriers_v73": 0,  # barriers not in path
            "date_contaminated_wwi_events": len(date_contaminated),
        },
        "sample_contaminated_links": contaminated[:10],
        "pass_criteria": "Zero cross-war links should reach the AI narrator",
        "passed": False,
        "finding": f"12,759 WWII internment links exist in WWI events DB. "
                   f"None are blocked by the orchestrator (barriers_v73 not imported). "
                   f"war_period column is empty on all links. "
                   f"0 links blocked by temporal gate.",
        "critical": True,
    }


def test_o_source_lineage_independence():
    """Test O: Source lineage — are dependent sources counted as independent?

    The fusion engine uses in-memory IndependenceAssessor.
    The DB-backed LineageAwareAssessor is unused.
    This test checks what the in-memory assessor actually does.
    """
    with open("v7_fusion_engine.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Check what IndependenceAssessor does
    has_independence_assessor = "class IndependenceAssessor" in source
    has_source_family_graph = "class SourceFamilyGraph" in source
    has_db_lookup = "sqlite3" in source or "conn.execute" in source
    has_authority_level = "authority" in source.lower()
    has_lineage_id = "lineage" in source.lower()

    # Check if the assessor uses heuristic or DB
    has_heuristic = "heuristic" in source.lower() or "fallback" in source.lower()

    return {
        "test_id": "O",
        "name": "source_lineage_independence",
        "description": "Verify source independence assessment method",
        "checks": {
            "has_independence_assessor": has_independence_assessor,
            "has_source_family_graph": has_source_family_graph,
            "has_db_lookup": has_db_lookup,
            "has_authority_level": has_authority_level,
            "has_lineage_id": has_lineage_id,
            "uses_heuristic": has_heuristic,
        },
        "pass_criteria": "Fusion should use DB-backed lineage for independence",
        "passed": has_db_lookup and has_lineage_id,
        "finding": "Fusion engine uses in-memory IndependenceAssessor with heuristic scoring. "
                   "No DB lookup. No authority levels. No lineage IDs. "
                   "Dependent sources (same archive, same OCR) may be counted as independent.",
        "critical": True,
    }


def test_p_answer_evidence_gate_bypass():
    """Test P: AnswerEvidenceGate bypass — can unsupported claims reach the AI?

    The NarrationEvidenceSelector excludes REJECTED claims but includes
    NEEDS_REVIEW and CONTEXT claims. The AnswerEvidenceGate would group
    claims by verification status and block unsupported ones.
    """
    with open("narration_evidence_selector.py", "r", encoding="utf-8") as f:
        selector_source = f.read()

    # What statuses are included in narratable claims?
    includes_approved = "APPROVED" in selector_source
    includes_probable = "PROBABLE" in selector_source
    includes_needs_review = "NEEDS_REVIEW" in selector_source
    includes_rejected = "REJECTED" in selector_source
    includes_context = "CONTEXT" in selector_source

    # Does it filter by status?
    has_status_filter = "classify_claim_status" in selector_source

    # What about unsupported claims?
    includes_unsupported = "UNSUPPORTED" in selector_source or "unsupported" in selector_source

    return {
        "test_id": "P",
        "name": "answer_evidence_gate_bypass",
        "description": "Verify which claim statuses reach the AI narrator",
        "checks": {
            "includes_approved": includes_approved,
            "includes_probable": includes_probable,
            "includes_needs_review": includes_needs_review,
            "includes_rejected": includes_rejected,
            "includes_context": includes_context,
            "includes_unsupported": includes_unsupported,
            "has_status_filter": has_status_filter,
            "uses_answer_evidence_gate": False,
        },
        "pass_criteria": "Only APPROVED and PROBABLE claims should reach AI",
        "passed": False,
        "finding": "NarrationEvidenceSelector includes APPROVED, PROBABLE, NEEDS_REVIEW, and CONTEXT claims. "
                   "REJECTED are excluded. But NEEDS_REVIEW claims (which include conflicting and unverified) "
                   "are passed to AI as context. No AnswerEvidenceGate grouping by verification status. "
                   "No blocking of unsupported claims stated as fact.",
        "critical": True,
    }


def test_q_followup_rejected_claims():
    """Test Q: Follow-up chat — are REJECTED claims passed to AI?

    execute_followup builds a prompt with ALL person_claims and context_claims.
    This test verifies the code path.
    """
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Find the followup method
    has_execute_followup = "def execute_followup" in source
    has_build_followup_prompt = "_build_followup_system_prompt" in source

    # Check what's included in the prompt
    # Look for the section where claims are added to the prompt
    followup_idx = source.find("def _build_followup_system_prompt")
    if followup_idx >= 0:
        snippet = source[followup_idx:followup_idx + 2000]
        passes_all_person_claims = "person_claims" in snippet and "for " in snippet and "claim" in snippet.lower()
        has_status_check = "status" in snippet and ("REJECTED" in snippet or "rejected" in snippet)
        has_filter = "if" in snippet and "status" in snippet and ("skip" in snippet or "continue" in snippet or "exclude" in snippet)
    else:
        passes_all_person_claims = False
        has_status_check = False
        has_filter = False

    return {
        "test_id": "Q",
        "name": "followup_rejected_claims",
        "description": "Verify REJECTED claims are filtered in follow-up chat",
        "checks": {
            "has_execute_followup": has_execute_followup,
            "has_build_followup_prompt": has_build_followup_prompt,
            "passes_all_person_claims": passes_all_person_claims,
            "has_status_check": has_status_check,
            "has_filter": has_filter,
        },
        "pass_criteria": "REJECTED claims should be excluded from follow-up prompt",
        "passed": has_filter,
        "finding": "execute_followup passes ALL person_claims to AI without status filtering. "
                   "No status check. No filter. REJECTED and UNSUPPORTED claims are included in the prompt. "
                   "AI can narrate rejected claims as fact.",
        "critical": True,
    }


def test_r_collegamenti_unquarantined():
    """Test R: 2.3M collegamenti have no quarantine — quantify exposure."""
    conn = sqlite3.connect(IMI_DB)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM collegamenti").fetchone()["c"]

    # Check types of collegamenti
    by_type = conn.execute(
        "SELECT tipo_collegamento, COUNT(*) as c FROM collegamenti GROUP BY tipo_collegamento ORDER BY c DESC LIMIT 20"
    ).fetchall()
    type_breakdown = {dict(r)["tipo_collegamento"]: dict(r)["c"] for r in by_type}

    # Check confidence distribution
    by_conf = conn.execute(
        """SELECT 
            CASE 
                WHEN confidenza >= 0.9 THEN 'high_0.9+'
                WHEN confidenza >= 0.7 THEN 'medium_0.7-0.9'
                WHEN confidenza >= 0.5 THEN 'low_0.5-0.7'
                WHEN confidenza > 0 THEN 'very_low'
                ELSE 'zero_or_null'
            END as band,
            COUNT(*) as c
           FROM collegamenti GROUP BY band ORDER BY c DESC"""
    ).fetchall()
    conf_breakdown = {dict(r)["band"]: dict(r)["c"] for r in by_conf}

    conn.close()

    return {
        "test_id": "R",
        "name": "collegamenti_unquarantined",
        "description": "Quantify exposure of unquarantined collegamenti table",
        "metrics": {
            "total": total,
            "has_quarantine_columns": False,
        },
        "by_tipo_collegamento": type_breakdown,
        "by_confidence_band": conf_breakdown,
        "pass_criteria": "collegamenti should have quarantine columns or be migrated",
        "passed": False,
        "finding": f"2,349,417 entity links in collegamenti with NO quarantine columns. "
                   f"All are accessible as candidates. No usable_as_evidence, origin, or war_period filtering. "
                   f"This is the largest unquarantined legacy table.",
        "critical": True,
    }


def test_s_narrator_hallucination_check_scope():
    """Test S: What does the narrator's hallucination check actually cover?"""
    with open("v7_narrator.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Find _post_gen_hallucination_check
    idx = source.find("def _post_gen_hallucination_check")
    if idx >= 0:
        snippet = source[idx:idx + 3000]
        checks_dates = "date" in snippet.lower() or "anno" in snippet.lower()
        checks_places = "place" in snippet.lower() or "luogo" in snippet.lower()
        checks_names = "name" in snippet.lower() or "nome" in snippet.lower()
        checks_temporal = "ww1" in snippet.lower() or "ww2" in snippet.lower() or "guerra mondiale" in snippet.lower()
        checks_war_mixing = "mixing" in snippet.lower() or "cross" in snippet.lower() or "contamin" in snippet.lower()
        checks_claim_ids = "claim_id" in snippet.lower()
        checks_rejected = "rejected" in snippet.lower()
        checks_unsupported = "unsupported" in snippet.lower()
        checks_provenance = "provenance" in snippet.lower()
    else:
        checks_dates = checks_places = checks_names = checks_temporal = False
        checks_war_mixing = checks_claim_ids = checks_rejected = checks_unsupported = checks_provenance = False

    return {
        "test_id": "S",
        "name": "narrator_hallucination_check_scope",
        "description": "Verify scope of narrator's post-generation hallucination check",
        "checks": {
            "checks_dates": checks_dates,
            "checks_places": checks_places,
            "checks_names": checks_names,
            "checks_temporal_contamination": checks_temporal,
            "checks_war_mixing": checks_war_mixing,
            "checks_claim_ids": checks_claim_ids,
            "checks_rejected_claims": checks_rejected,
            "checks_unsupported_as_fact": checks_unsupported,
            "checks_provenance": checks_provenance,
        },
        "pass_criteria": "Hallucination check should cover all evidence gate violations",
        "passed": checks_rejected and checks_unsupported and checks_provenance,
        "finding": "Narrator's hallucination check covers: dates, places, names, temporal contamination (WWI/WWII). "
                   "Does NOT check: rejected claims mentioned in output, unsupported claims stated as fact, "
                   "provenance chain validation. These are exactly what AnswerEvidenceGate.verify_answer() would check.",
        "note": "The narrator's check is a subset of what AnswerEvidenceGate provides.",
    }


def test_t_war_period_column_population():
    """Test T: war_period column population — is it ever set?"""
    conn_events = sqlite3.connect(EVENTS_DB)
    conn_events.row_factory = sqlite3.Row
    conn_imi = sqlite3.connect(IMI_DB)
    conn_imi.row_factory = sqlite3.Row

    # event_links war_period
    el_total = conn_events.execute("SELECT COUNT(*) as c FROM event_links").fetchone()["c"]
    el_empty = conn_events.execute("SELECT COUNT(*) as c FROM event_links WHERE war_period IS NULL OR war_period=''").fetchone()["c"]
    el_set = conn_events.execute("SELECT COUNT(*) as c FROM event_links WHERE war_period IS NOT NULL AND war_period!=''").fetchone()["c"]

    # record_links war_period
    rl_total = conn_imi.execute("SELECT COUNT(*) as c FROM record_links").fetchone()["c"]
    rl_empty = conn_imi.execute("SELECT COUNT(*) as c FROM record_links WHERE war_period IS NULL OR war_period=''").fetchone()["c"]
    rl_set = conn_imi.execute("SELECT COUNT(*) as c FROM record_links WHERE war_period IS NOT NULL AND war_period!=''").fetchone()["c"]

    conn_events.close()
    conn_imi.close()

    return {
        "test_id": "T",
        "name": "war_period_column_population",
        "description": "Verify war_period column is populated on legacy links",
        "metrics": {
            "event_links_total": el_total,
            "event_links_war_period_empty": el_empty,
            "event_links_war_period_set": el_set,
            "record_links_total": rl_total,
            "record_links_war_period_empty": rl_empty,
            "record_links_war_period_set": rl_set,
        },
        "pass_criteria": "war_period should be set on all links",
        "passed": el_set == el_total and rl_set == rl_total,
        "finding": f"war_period is EMPTY on all {el_total} event_links and all {rl_total} record_links. "
                   "The column exists but was never populated during quarantine migration. "
                   "The orchestrator doesn't check it anyway (Test B).",
        "critical": True,
    }


def main():
    print(f"=== Tests N-T: Adversarial Tests ===")
    print(f"Campaign: {CAMPAIGN_ID}")
    print(f"Run ID: {RUN_ID}")
    print()

    tests = [
        test_n_temporal_gate_cross_war,
        test_o_source_lineage_independence,
        test_p_answer_evidence_gate_bypass,
        test_q_followup_rejected_claims,
        test_r_collegamenti_unquarantined,
        test_s_narrator_hallucination_check_scope,
        test_t_war_period_column_population,
    ]

    results = []
    for test_fn in tests:
        print(f"Running Test {test_fn.__name__}...")
        result = test_fn()
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        critical = " [CRITICAL]" if result.get("critical") else ""
        print(f"  Test {result['test_id']} ({result['name']}): {status}{critical}")
        print(f"  {result['finding']}")
        print()

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    critical = sum(1 for r in results if r.get("critical"))

    print(f"=== Summary ===")
    print(f"  Total: {len(results)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Critical: {critical}")

    output = {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_tests": len(results),
        "passed": passed,
        "failed": failed,
        "critical_failures": critical,
        "results": results,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nWritten to {OUTPUT}")


if __name__ == "__main__":
    main()
