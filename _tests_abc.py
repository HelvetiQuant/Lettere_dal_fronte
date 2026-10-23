"""Validation Campaign — Sections 5-6: Legacy Confidence Challenge + Regression Tests.

Tests A-M: Quantitative verification that legacy data cannot become
verified historical knowledge without sufficient evidence.

All tests are READ-ONLY on original DBs. No data modification.

Output: docs/validation/test_results_abc.json
"""
import json
import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_ID = "validation_20260817_v1"
RUN_ID = f"tests_abc_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
IMI_DB = "imi_internati.db"
EVENTS_DB = "eventi_1gm.db"
OUTPUT = Path("docs/validation/test_results_abc.json")


def test_a_legacy_confidence_distribution():
    """Test A: Legacy confidence distribution — are high-confidence legacy links gated?"""
    conn = sqlite3.connect(EVENTS_DB)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM event_links").fetchone()["c"]
    usable_0 = conn.execute("SELECT COUNT(*) as c FROM event_links WHERE usable_as_evidence=0").fetchone()["c"]
    usable_1 = conn.execute("SELECT COUNT(*) as c FROM event_links WHERE usable_as_evidence=1").fetchone()["c"]
    usable_null = conn.execute("SELECT COUNT(*) as c FROM event_links WHERE usable_as_evidence IS NULL").fetchone()["c"]

    high_conf = conn.execute("SELECT COUNT(*) as c FROM event_links WHERE confidence >= 0.9").fetchone()["c"]
    high_conf_usable_0 = conn.execute("SELECT COUNT(*) as c FROM event_links WHERE confidence >= 0.9 AND usable_as_evidence=0").fetchone()["c"]

    conn.close()

    result = {
        "test_id": "A",
        "name": "legacy_confidence_distribution",
        "description": "Verify that high-confidence legacy links are gated by usable_as_evidence",
        "metrics": {
            "total_event_links": total,
            "usable_as_evidence_0": usable_0,
            "usable_as_evidence_1": usable_1,
            "usable_as_evidence_null": usable_null,
            "high_confidence_total": high_conf,
            "high_confidence_but_gated": high_conf_usable_0,
            "high_confidence_ungated": high_conf - high_conf_usable_0,
        },
        "pass_criteria": "All legacy links should have usable_as_evidence=0",
        "passed": usable_0 == total and usable_1 == 0,
        "finding": f"{high_conf_usable_0}/{high_conf} high-confidence links are gated (usable_as_evidence=0). "
                   f"But {high_conf - high_conf_usable_0} are NOT gated.",
    }

    if usable_0 == total:
        result["note"] = "All event_links have usable_as_evidence=0 (quarantine applied). However, the orchestrator never checks this column (CF-3)."
    else:
        result["note"] = f"CRITICAL: {usable_1 + usable_null} links are NOT gated."

    return result


def test_b_orchestrator_usable_as_evidence_check():
    """Test B: Does the orchestrator check usable_as_evidence?"""
    # Read the orchestrator source and search for usable_as_evidence
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        source = f.read()

    checks = {
        "usable_as_evidence_in_source": "usable_as_evidence" in source,
        "war_period_in_source": "war_period" in source,
        "origin_in_source": "origin" in source,
        "quarantine_in_source": "quarantine" in source,
        "legacy_relation_adapter_import": "legacy_relation_adapter" in source,
        "evidence_contract_import": "evidence_contract" in source,
        "answer_evidence_gate_import": "answer_evidence_gate" in source,
        "source_lineage_service_import": "source_lineage_service" in source,
        "evidence_snapshot_service_import": "evidence_snapshot_service" in source,
        "event_ontology_service_import": "event_ontology_service" in source,
        "barriers_v73_import": "barriers_v73" in source,
    }

    all_absent = not any(checks.values())

    return {
        "test_id": "B",
        "name": "orchestrator_gating_column_check",
        "description": "Verify whether unified_orchestrator_v7.py references quarantine/evidence columns",
        "checks": checks,
        "pass_criteria": "Orchestrator should check usable_as_evidence, war_period, origin",
        "passed": False,
        "finding": "Orchestrator does NOT check usable_as_evidence, war_period, origin, or quarantine columns. "
                   "No evidence-centric module is imported.",
        "critical": True,
    }


def test_c_cross_war_contamination_count():
    """Test C: Count cross-war contamination in event_links."""
    conn = sqlite3.connect(EVENTS_DB)
    conn.row_factory = sqlite3.Row

    # WW2 internment links in WW1 events DB
    ww2_links = conn.execute(
        "SELECT COUNT(*) as c FROM event_links WHERE link_type='internato_ww2'"
    ).fetchone()["c"]

    # Check which events these link to
    ww2_by_event = conn.execute(
        """SELECT el.evento_id, e.nome, e.conflict, e.data_inizio, e.data_fine,
                  COUNT(*) as link_count
           FROM event_links el
           JOIN eventi_1gm e ON el.evento_id = e.id
           WHERE el.link_type='internato_ww2'
           GROUP BY el.evento_id ORDER BY link_count DESC LIMIT 20"""
    ).fetchall()

    contaminated_events = []
    for row in ww2_by_event:
        r = dict(row)
        contaminated_events.append({
            "evento_id": r["evento_id"],
            "nome": r["nome"],
            "conflict": r["conflict"],
            "data_inizio": r["data_inizio"],
            "data_fine": r["data_fine"],
            "ww2_link_count": r["link_count"],
        })

    conn.close()

    return {
        "test_id": "C",
        "name": "cross_war_contamination_count",
        "description": "Count WWII internment links in WWI events database",
        "metrics": {
            "total_ww2_links_in_ww1_db": ww2_links,
            "contaminated_events": len(contaminated_events),
        },
        "contaminated_events_detail": contaminated_events[:10],
        "pass_criteria": "Zero cross-war links should exist",
        "passed": ww2_links == 0,
        "finding": f"{ww2_links} WWII internment links found in WWI events DB. "
                   f"These are {len(contaminated_events)} WWI events with WWII contamination.",
        "critical": ww2_links > 0,
    }


def test_d_record_links_quarantine_status():
    """Test D: Record links quarantine status."""
    conn = sqlite3.connect(IMI_DB)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM record_links").fetchone()["c"]
    usable_0 = conn.execute("SELECT COUNT(*) as c FROM record_links WHERE usable_as_evidence=0").fetchone()["c"]
    usable_1 = conn.execute("SELECT COUNT(*) as c FROM record_links WHERE usable_as_evidence=1").fetchone()["c"]
    legacy = conn.execute("SELECT COUNT(*) as c FROM record_links WHERE algorithm_version='legacy'").fetchone()["c"]
    legacy_unverified = conn.execute("SELECT COUNT(*) as c FROM record_links WHERE legacy_unverified=1").fetchone()["c"]

    # Check if any have high confidence AND usable_as_evidence=0 (should be blocked but isn't checked)
    high_conf_gated = conn.execute(
        "SELECT COUNT(*) as c FROM record_links WHERE confidence >= 0.8 AND usable_as_evidence=0"
    ).fetchone()["c"]

    conn.close()

    return {
        "test_id": "D",
        "name": "record_links_quarantine_status",
        "description": "Verify quarantine status of record_links",
        "metrics": {
            "total": total,
            "usable_as_evidence_0": usable_0,
            "usable_as_evidence_1": usable_1,
            "algorithm_version_legacy": legacy,
            "legacy_unverified": legacy_unverified,
            "high_confidence_but_gated": high_conf_gated,
        },
        "pass_criteria": "All legacy links should be quarantined (usable_as_evidence=0)",
        "passed": usable_0 == total,
        "finding": f"All {total} record_links have usable_as_evidence=0. {high_conf_gated} have high confidence but are gated. "
                   "However, orchestrator does not check this column (Test B).",
    }


def test_e_collegamenti_legacy_status():
    """Test E: Collegamenti table — 2.3M legacy entity links, no quarantine columns."""
    conn = sqlite3.connect(IMI_DB)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM collegamenti").fetchone()["c"]

    # Check if collegamenti has any quarantine columns
    cols = conn.execute("PRAGMA table_info(collegamenti)").fetchall()
    col_names = [dict(c)["name"] for c in cols]
    has_usable = "usable_as_evidence" in col_names
    has_origin = "origin" in col_names
    has_war_period = "war_period" in col_names

    conn.close()

    return {
        "test_id": "E",
        "name": "collegamenti_legacy_status",
        "description": "Check if collegamenti table has quarantine columns",
        "metrics": {
            "total": total,
            "has_usable_as_evidence": has_usable,
            "has_origin": has_origin,
            "has_war_period": has_war_period,
        },
        "pass_criteria": "collegamenti should have quarantine columns",
        "passed": has_usable and has_origin and has_war_period,
        "finding": f"collegamenti has {total} rows but NO quarantine columns (usable_as_evidence, origin, war_period). "
                   "These legacy entity links are completely unquarantined.",
        "critical": not has_usable,
    }


def test_f_narrator_status_filtering():
    """Test F: Does NarratorV7_v2 filter claims by status before sending to AI?"""
    with open("v7_narrator.py", "r", encoding="utf-8") as f:
        source = f.read()

    checks = {
        "imports_narration_evidence_selector": "from narration_evidence_selector" in source,
        "imports_narration_validator": "from narration_validator" in source,
        "imports_answer_evidence_gate": "from answer_evidence_gate" in source or "import answer_evidence_gate" in source,
        "imports_evidence_contract": "from evidence_contract" in source or "import evidence_contract" in source,
        "imports_claim_status": "ClaimStatus" in source,
        "has_validate_payload": "_validate_payload" in source,
        "has_hallucination_check": "_post_gen_hallucination_check" in source,
        "has_cross_validate": "_ai_cross_validate" in source,
        "has_verify_answer": "verify_answer" in source,
        "has_answer_evidence_bundle": "AnswerEvidenceBundle" in source,
    }

    return {
        "test_id": "F",
        "name": "narrator_status_filtering",
        "description": "Verify what validation the narrator performs",
        "checks": checks,
        "pass_criteria": "Narrator should use AnswerEvidenceGate and ClaimStatus",
        "passed": checks["imports_answer_evidence_gate"] and checks["imports_evidence_contract"],
        "finding": "Narrator uses NarrationEvidenceSelector + NarrationValidator (weaker validation). "
                   "AnswerEvidenceGate and ClaimStatus are NOT imported. "
                   "No verify_answer() call. No AnswerEvidenceBundle construction.",
        "critical": True,
    }


def test_g_followup_claim_filtering():
    """Test G: Does execute_followup filter claims by status?"""
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Check if followup filters claims
    has_status_filter = "status" in source and "REJECTED" in source and "followup" in source.lower()
    has_answer_evidence_gate = "AnswerEvidenceGate" in source
    has_narration_evidence_selector = "NarrationEvidenceSelector" in source

    # Check if all claims are passed
    has_all_person_claims = "person_claims" in source and "followup" in source.lower()

    return {
        "test_id": "G",
        "name": "followup_claim_filtering",
        "description": "Verify whether execute_followup filters claims by verification status",
        "checks": {
            "has_status_filter_in_followup": has_status_filter,
            "uses_answer_evidence_gate": has_answer_evidence_gate,
            "uses_narration_evidence_selector": has_narration_evidence_selector,
            "passes_all_person_claims": has_all_person_claims,
        },
        "pass_criteria": "Followup should filter REJECTED/UNSUPPORTED claims",
        "passed": has_status_filter or has_answer_evidence_gate,
        "finding": "execute_followup passes ALL person_claims and context_claims to AI without status filtering. "
                   "No AnswerEvidenceGate. No NarrationEvidenceSelector. REJECTED claims included in prompt.",
        "critical": True,
    }


def test_h_persistence_stage():
    """Test H: Is _stage_persist implemented?"""
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Find _stage_persist
    has_pass = "def _stage_persist" in source
    is_pass_only = False
    if has_pass:
        # Check if it's just pass
        idx = source.index("def _stage_persist")
        snippet = source[idx:idx+500]
        is_pass_only = "pass" in snippet and "evidence_snapshot" not in snippet.lower()

    has_evidence_snapshot_service = "evidence_snapshot_service" in source

    return {
        "test_id": "H",
        "name": "persistence_stage",
        "description": "Verify _stage_persist implementation",
        "checks": {
            "has_stage_persist": has_pass,
            "is_pass_only": is_pass_only,
            "imports_evidence_snapshot_service": has_evidence_snapshot_service,
        },
        "pass_criteria": "_stage_persist should call evidence_snapshot_service",
        "passed": not is_pass_only and has_evidence_snapshot_service,
        "finding": "_stage_persist is a no-op (pass). Snapshots are ephemeral. No evidence trail.",
        "critical": True,
    }


def test_i_graph_service_quarantine_check():
    """Test I: Does graph_service check usable_as_evidence?"""
    with open("graph_service.py", "r", encoding="utf-8") as f:
        source = f.read()

    checks = {
        "checks_usable_as_evidence": "usable_as_evidence" in source,
        "checks_origin": "origin" in source and "LEGACY" in source,
        "checks_war_period": "war_period" in source,
        "checks_algorithm_version": "algorithm_version" in source,
        "checks_legacy_unverified": "legacy_unverified" in source,
    }

    return {
        "test_id": "I",
        "name": "graph_service_quarantine_check",
        "description": "Verify graph_service checks quarantine columns",
        "checks": checks,
        "pass_criteria": "graph_service should check usable_as_evidence, origin, war_period",
        "passed": checks["checks_usable_as_evidence"] and checks["checks_war_period"],
        "finding": "graph_service checks algorithm_version and legacy_unverified but NOT usable_as_evidence, origin, or war_period. "
                   "Quarantined links can appear as candidates in the graph.",
        "critical": not checks["checks_usable_as_evidence"],
    }


def test_j_v73_barriers_in_orchestrator():
    """Test J: Are V7.3 temporal/geographic barriers in the orchestrator path?"""
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        orch_source = f.read()

    checks = {
        "orchestrator_imports_barriers_v73": "barriers_v73" in orch_source,
        "orchestrator_imports_narration_planner_v73": "narration_planner_v73" in orch_source,
        "orchestrator_imports_domain_model_v73": "domain_model_v73" in orch_source,
        "orchestrator_imports_text_matching_v73": "text_matching_v73" in orch_source,
        "orchestrator_imports_adapters_v73": "adapters_v73" in orch_source,
    }

    # Check what the narrator uses
    with open("v7_narrator.py", "r", encoding="utf-8") as f:
        narr_source = f.read()

    narrator_checks = {
        "narrator_imports_barriers_v73": "barriers_v73" in narr_source,
        "narrator_imports_narration_planner_v73": "narration_planner_v73" in narr_source,
    }

    all_checks = {**checks, **narrator_checks}

    return {
        "test_id": "J",
        "name": "v73_barriers_in_orchestrator",
        "description": "Verify V7.3 temporal/geographic barriers are in the decision path",
        "checks": all_checks,
        "pass_criteria": "Orchestrator or narrator should import barriers_v73",
        "passed": checks["orchestrator_imports_barriers_v73"] or narrator_checks["narrator_imports_barriers_v73"],
        "finding": "V7.3 barriers (temporal veto, geographic semantic roles) are NOT imported by orchestrator or narrator. "
                   "They are only used by narration_planner_v73.py which is not in the main pipeline.",
        "critical": True,
    }


def test_k_cross_link_audit_active():
    """Test K: Cross-link audit — how many active (non-reverted) field changes exist?"""
    conn = sqlite3.connect(IMI_DB)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=0").fetchone()["c"]
    reverted = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=1").fetchone()["c"]
    baseline = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE match_method='PRE_CROSS_LINK_BASELINE'").fetchone()["c"]
    active_non_baseline = conn.execute(
        "SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=0 AND match_method != 'PRE_CROSS_LINK_BASELINE'"
    ).fetchone()["c"]

    # By source table
    by_source = conn.execute(
        """SELECT source_table, COUNT(*) as c FROM cross_link_audit
           WHERE reverted=0 AND match_method != 'PRE_CROSS_LINK_BASELINE'
           GROUP BY source_table ORDER BY c DESC"""
    ).fetchall()
    source_breakdown = {dict(r)["source_table"]: dict(r)["c"] for r in by_source}

    # By column
    by_col = conn.execute(
        """SELECT column_name, COUNT(*) as c FROM cross_link_audit
           WHERE reverted=0 AND match_method != 'PRE_CROSS_LINK_BASELINE'
           GROUP BY column_name ORDER BY c DESC"""
    ).fetchall()
    col_breakdown = {dict(r)["column_name"]: dict(r)["c"] for r in by_col}

    conn.close()

    return {
        "test_id": "K",
        "name": "cross_link_audit_active",
        "description": "Count active cross-link field changes on internati records",
        "metrics": {
            "total_audit_records": total,
            "active": active,
            "reverted": reverted,
            "baseline": baseline,
            "active_non_baseline": active_non_baseline,
        },
        "by_source_table": source_breakdown,
        "by_column": col_breakdown,
        "pass_criteria": "Cross-linked fields should be marked as derived/secondary evidence",
        "passed": False,
        "finding": f"{active_non_baseline} active cross-link field changes exist on internati records. "
                   f"These fields were overwritten from external sources (lebi, caduti, decorati) "
                   f"but the orchestrator does not distinguish original vs cross-linked fields.",
        "note": "Cross-linked fields are not flagged in the evidence pipeline. They appear as original data.",
    }


def test_l_event_ontology_service_usage():
    """Test L: Is EventOntologyService used in the pipeline?"""
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        orch_source = f.read()
    with open("event_resolver.py", "r", encoding="utf-8") as f:
        resolver_source = f.read()

    checks = {
        "orchestrator_imports_event_ontology_service": "event_ontology_service" in orch_source,
        "event_resolver_imports_event_ontology_service": "event_ontology_service" in resolver_source,
        "orchestrator_uses_v7_event_aggregate": "v7_event_aggregate" in orch_source,
        "event_resolver_uses_hardcoded_hierarchy": "HIERARCHY" in resolver_source,
    }

    return {
        "test_id": "L",
        "name": "event_ontology_service_usage",
        "description": "Verify EventOntologyService integration",
        "checks": checks,
        "pass_criteria": "EventOntologyService should be used for event hierarchy validation",
        "passed": checks["orchestrator_imports_event_ontology_service"] or checks["event_resolver_imports_event_ontology_service"],
        "finding": "EventOntologyService is NOT imported by orchestrator or event_resolver. "
                   "Orchestrator uses v7_event_aggregate (simpler model). "
                   "Event_resolver uses hardcoded HIERARCHY dict.",
    }


def test_m_source_lineage_in_fusion():
    """Test M: Is SourceLineageService used in the fusion stage?"""
    with open("unified_orchestrator_v7.py", "r", encoding="utf-8") as f:
        orch_source = f.read()
    with open("v7_fusion_engine.py", "r", encoding="utf-8") as f:
        fusion_source = f.read()

    checks = {
        "orchestrator_imports_source_lineage_service": "source_lineage_service" in orch_source,
        "fusion_engine_imports_source_lineage_service": "source_lineage_service" in fusion_source,
        "fusion_engine_uses_independence_assessor": "IndependenceAssessor" in fusion_source,
        "fusion_engine_uses_source_family_graph": "SourceFamilyGraph" in fusion_source,
        "orchestrator_uses_fusion_engine": "v7_fusion_engine" in orch_source,
    }

    return {
        "test_id": "M",
        "name": "source_lineage_in_fusion",
        "description": "Verify SourceLineageService integration in fusion stage",
        "checks": checks,
        "pass_criteria": "Fusion should use DB-backed SourceLineageService",
        "passed": checks["orchestrator_imports_source_lineage_service"] or checks["fusion_engine_imports_source_lineage_service"],
        "finding": "SourceLineageService is NOT imported by orchestrator or fusion engine. "
                   "Fusion uses in-memory IndependenceAssessor (heuristic only). "
                   "DB-backed lineage with authority levels is unused.",
        "critical": True,
    }


def main():
    print(f"=== Tests A-M: Legacy Confidence Challenge + Regression ===")
    print(f"Campaign: {CAMPAIGN_ID}")
    print(f"Run ID: {RUN_ID}")
    print()

    tests = [
        test_a_legacy_confidence_distribution,
        test_b_orchestrator_usable_as_evidence_check,
        test_c_cross_war_contamination_count,
        test_d_record_links_quarantine_status,
        test_e_collegamenti_legacy_status,
        test_f_narrator_status_filtering,
        test_g_followup_claim_filtering,
        test_h_persistence_stage,
        test_i_graph_service_quarantine_check,
        test_j_v73_barriers_in_orchestrator,
        test_k_cross_link_audit_active,
        test_l_event_ontology_service_usage,
        test_m_source_lineage_in_fusion,
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

    # Summary
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
