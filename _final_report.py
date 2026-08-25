"""Validation Campaign — Sections 18-24: Final Report Generator.

Aggregates all test results, computes mandatory metrics,
generates failure corpus, and produces machine-readable summary.

Output:
  docs/validation/FINAL_REPORT.md
  docs/validation/failure_corpus.json
  docs/validation/machine_readable_summary.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_ID = "validation_20260817_v1"
OUTPUT_DIR = Path("docs/validation")


def load_results():
    """Load all test result files."""
    all_results = []

    for f in ["test_results_abc.json", "test_results_nt.json", "test_results_uz.json"]:
        path = OUTPUT_DIR / f
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                all_results.extend(data["results"])

    return all_results


def compute_metrics(results):
    """Compute mandatory metrics."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    critical = sum(1 for r in results if r.get("critical") and not r["passed"])

    # Module integration metrics
    modules_implemented = 9
    modules_in_path = 0

    # Legacy data metrics
    legacy_metrics = {
        "total_legacy_links": 4059286,  # 169184 + 2349417 + 1539685 (from tests)
        "links_with_quarantine_columns": 1710869,  # record_links + event_links
        "links_without_quarantine_columns": 2349417,  # collegamenti
        "quarantine_columns_checked_by_orchestrator": 0,
        "cross_war_contaminated_links": 12759,
        "war_period_column_populated": 0,
        "evidence_snapshots_persisted": 0,
    }

    # Security metrics
    security_metrics = {
        "answer_evidence_gate_active": False,
        "claim_status_filtering_in_narrator": "partial",  # REJECTED excluded, but NEEDS_REVIEW included
        "claim_status_filtering_in_followup": False,
        "temporal_barrier_in_pipeline": False,
        "geographic_barrier_in_pipeline": False,
        "source_lineage_db_backed": False,
        "snapshot_persistence_active": False,
        "provenance_chain_validated": False,
        "post_generation_verification": "partial",  # hallucination check only, no verify_answer
    }

    # Risk assessment
    risk = {
        "legacy_data_becoming_verified": "HIGH — orchestrator doesn't check usable_as_evidence",
        "cross_war_contamination": "HIGH — 12,759 WWII links in WWI DB, no temporal barrier in pipeline",
        "rejected_claims_in_narration": "MEDIUM — REJECTED excluded by NarrationEvidenceSelector, but included in follow-up",
        "unsupported_claims_as_fact": "HIGH — no AnswerEvidenceGate.verify_answer()",
        "dependent_sources_as_independent": "MEDIUM — in-memory heuristic only, no DB lineage",
        "cross_linked_fields_as_original": "HIGH — 4,448 internati with cross-linked fields, no provenance distinction",
        "snapshot_reproducibility": "CRITICAL — _stage_persist is pass, 0 snapshots saved",
    }

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "critical_failures": critical,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "modules_implemented": modules_implemented,
        "modules_in_decision_path": modules_in_path,
        "module_integration_rate": 0.0,
        "legacy_data": legacy_metrics,
        "security": security_metrics,
        "risk_assessment": risk,
    }


def generate_failure_corpus(results):
    """Generate failure corpus from failed tests."""
    corpus = []
    for r in results:
        if not r["passed"]:
            entry = {
                "test_id": r["test_id"],
                "test_name": r["name"],
                "description": r["description"],
                "finding": r["finding"],
                "critical": r.get("critical", False),
                "pass_criteria": r.get("pass_criteria", ""),
                "metrics": r.get("metrics", {}),
                "checks": r.get("checks", {}),
            }
            if "note" in r:
                entry["note"] = r["note"]
            corpus.append(entry)
    return corpus


def generate_final_report(results, metrics, failure_corpus):
    """Generate markdown final report."""
    lines = []
    lines.append("# Evidence-Centric Architecture Validation Campaign — Final Report")
    lines.append("")
    lines.append(f"**Campaign ID:** `{CAMPAIGN_ID}`")
    lines.append(f"**Date:** 2026-08-17")
    lines.append(f"**Status:** COMPLETED")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"The validation campaign executed **{metrics['total_tests']} tests** across 3 test suites:")
    lines.append(f"- Tests A-M: Legacy confidence challenge + regression")
    lines.append(f"- Tests N-T: Adversarial tests (temporal gate, source lineage, gate bypass)")
    lines.append(f"- Tests U-Z: Policy analysis, cross-link audit, event ontology, snapshot, graph leakage")
    lines.append("")
    lines.append(f"**Results: {metrics['passed']} PASS, {metrics['failed']} FAIL, {metrics['critical_failures']} CRITICAL**")
    lines.append(f"**Pass rate: {metrics['pass_rate']}%**")
    lines.append("")
    lines.append(f"**Module integration: {metrics['modules_in_decision_path']}/{metrics['modules_implemented']} evidence-centric modules in V7 decision path (0%)**")
    lines.append("")
    lines.append("### Verdict: **FAIL — Evidence-Centric Architecture is NOT integrated**")
    lines.append("")
    lines.append("All 9 evidence-centric modules (Phases 2-7) are implemented as standalone files but have **zero imports** from any production code. The V7 pipeline operates with weaker, ad-hoc validation that does not enforce the declared architectural invariants.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Critical Findings")
    lines.append("")

    critical_findings = [
        ("CF-1", "AnswerEvidenceGate completely bypassed",
         "The AI narrator receives claims via NarrationEvidenceSelector, not AnswerEvidenceGate. "
         "No evidence bundle, no status grouping, no provenance validation, no post-generation verification. "
         "Unsupported claims can be narrated as fact."),
        ("CF-2", "Evidence Contract invariants never enforced",
         "10 invariants declared (no claim without evidence, no verified without provenance, etc.) but none checked. "
         "Pipeline uses ad-hoc validation with weaker criteria."),
        ("CF-3", "Legacy quarantine flag ignored by orchestrator",
         "usable_as_evidence=0 exists on 1.71M legacy links but orchestrator never queries this column. "
         "Legacy data flows into observations and claims without quarantine checks."),
        ("CF-4", "Follow-up chat has no evidence gating",
         "execute_followup passes ALL claims (including REJECTED and UNSUPPORTED) to AI. "
         "No filtering, no hash verification, no post-generation validation."),
        ("CF-5", "Snapshot persistence is a no-op",
         "_stage_persist() is literally `pass`. evidence_snapshots table has 0 rows. "
         "No evidence trail, no reproducibility."),
        ("CF-6", "Source lineage is in-memory only",
         "DB-backed LineageAwareAssessor unused. Independence assessment is heuristic only. "
         "Dependent sources may be counted as independent."),
        ("CF-7", "Event ontology service unused",
         "29/49 events have parent_event_id, 29 have invalid parent references. "
         "EventOntologyService (which would validate) is not called."),
        ("CF-8", "V7.3 barriers not in main orchestrator",
         "Temporal veto (WWI/WWII) and geographic semantic roles are not in the main pipeline. "
         "12,759 cross-war links are unblocked."),
        ("CF-9", "2.3M collegamenti completely unquarantined",
         "collegamenti table has NO quarantine columns (usable_as_evidence, origin, war_period). "
         "All 2.3M entity links are accessible as candidates."),
        ("CF-10", "war_period column never populated",
         "war_period exists on event_links and record_links but is empty on all 1.71M rows. "
         "Orchestrator doesn't check it anyway."),
    ]

    for cf_id, title, description in critical_findings:
        lines.append(f"### {cf_id}: {title}")
        lines.append(f"{description}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Test Results Summary")
    lines.append("")
    lines.append("| Test | Name | Result | Critical |")
    lines.append("|------|------|--------|----------|")

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        crit = "YES" if r.get("critical") and not r["passed"] else ""
        lines.append(f"| {r['test_id']} | {r['name']} | {status} | {crit} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Legacy Data Exposure")
    lines.append("")
    lines.append("| Dataset | Rows | Quarantined | Quarantine Checked |")
    lines.append("|---------|------|-------------|-------------------|")
    lines.append(f"| record_links | 169,184 | YES (usable_as_evidence=0) | NO |")
    lines.append(f"| event_links | 1,539,685 | YES (usable_as_evidence=0) | NO |")
    lines.append(f"| collegamenti | 2,349,417 | NO (no columns) | N/A |")
    lines.append(f"| **Total** | **4,058,286** | **1,708,869 (42%)** | **0** |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Cross-War Contamination")
    lines.append("")
    lines.append(f"- **12,759** WWII internment links (`internato_ww2`) in WWI events database")
    lines.append(f"- **18** WWI events contaminated with WWII data")
    lines.append(f"- **0** blocked by temporal gate (barriers_v73 not in pipeline)")
    lines.append(f"- **war_period** column empty on all 1.71M links")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Cross-Link Audit")
    lines.append("")
    lines.append(f"- **4,448/20,465** (21.7%) internati have active cross-linked fields")
    lines.append(f"- **40,587** active field changes from external sources (lebi, caduti, decorati)")
    lines.append(f"- **0** provenance distinctions between original and cross-linked fields")
    lines.append(f"- Orchestrator treats cross-linked data as original")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Module Integration Status")
    lines.append("")
    lines.append("| Module | Implemented | In Decision Path | Classification |")
    lines.append("|--------|-------------|------------------|----------------|")
    lines.append("| evidence_contract.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| source_lineage_service.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| legacy_relation_adapter.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| answer_evidence_gate.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| evidence_snapshot_service.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| event_ontology_service.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| barriers_v73.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| narration_planner_v73.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("| v7_quarantine.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Risk Assessment")
    lines.append("")
    lines.append("| Risk | Level | Description |")
    lines.append("|------|-------|-------------|")
    for risk_name, risk_level in metrics["risk_assessment"].items():
        desc = risk_level.split("—")[1].strip() if "—" in risk_level else risk_level
        lines.append(f"| {risk_name.replace('_', ' ')} | {risk_level.split('—')[0].strip()} | {desc} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    lines.append("### Immediate (P0 — must fix before any production use)")
    lines.append("")
    lines.append("1. **Integrate AnswerEvidenceGate into _stage_narrate()** — Replace raw claim passing with AnswerEvidenceBundle construction")
    lines.append("2. **Check usable_as_evidence in _stage_extract()** — Filter out quarantined legacy links before claim extraction")
    lines.append("3. **Filter claims by status in execute_followup()** — Exclude REJECTED and UNSUPPORTED from follow-up prompts")
    lines.append("4. **Implement _stage_persist()** — Call evidence_snapshot_service to save snapshots")
    lines.append("5. **Import barriers_v73 into orchestrator** — Apply temporal veto during fusion and extraction")
    lines.append("")
    lines.append("### Short-term (P1)")
    lines.append("")
    lines.append("6. **Populate war_period column** on all event_links and record_links")
    lines.append("7. **Add quarantine columns to collegamenti** — 2.3M unquarantined links")
    lines.append("8. **Integrate SourceLineageService** — Replace in-memory IndependenceAssessor with DB-backed version")
    lines.append("9. **Integrate EventOntologyService** — Validate hierarchy during event resolution")
    lines.append("10. **Add provenance tracking for cross-linked fields** — Mark internati fields as derived/secondary")
    lines.append("")
    lines.append("### Long-term (P2)")
    lines.append("")
    lines.append("11. **Migrate collegamenti to V2 relations table** via LegacyRelationAdapter")
    lines.append("12. **Implement ClaimStatus enum throughout pipeline** — Replace ad-hoc status strings")
    lines.append("13. **Add post-generation verify_answer()** — Check AI output against evidence bundle")
    lines.append("14. **Full evidence contract enforcement** — All 10 invariants checked at each stage")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("| Artifact | Path |")
    lines.append("|----------|------|")
    lines.append("| Integration Audit | docs/validation/INTEGRATION_AUDIT.md |")
    lines.append("| Pilot Dataset | docs/validation/pilot_dataset.json |")
    lines.append("| Test Results A-M | docs/validation/test_results_abc.json |")
    lines.append("| Test Results N-T | docs/validation/test_results_nt.json |")
    lines.append("| Test Results U-Z | docs/validation/test_results_uz.json |")
    lines.append("| Failure Corpus | docs/validation/failure_corpus.json |")
    lines.append("| Machine-Readable Summary | docs/validation/machine_readable_summary.json |")
    lines.append("| This Report | docs/validation/FINAL_REPORT.md |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**Campaign completed:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Campaign ID:** `{CAMPAIGN_ID}`")

    return "\n".join(lines)


def main():
    print("=== Final Report Generation ===")
    print(f"Campaign: {CAMPAIGN_ID}")
    print()

    results = load_results()
    print(f"Loaded {len(results)} test results")

    metrics = compute_metrics(results)
    failure_corpus = generate_failure_corpus(results)
    report = generate_final_report(results, metrics, failure_corpus)

    # Write final report
    report_path = OUTPUT_DIR / "FINAL_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Written: {report_path}")

    # Write failure corpus
    corpus_path = OUTPUT_DIR / "failure_corpus.json"
    with open(corpus_path, "w", encoding="utf-8") as f:
        json.dump({
            "campaign_id": CAMPAIGN_ID,
            "total_failures": len(failure_corpus),
            "critical_failures": sum(1 for f in failure_corpus if f["critical"]),
            "corpus": failure_corpus,
        }, f, ensure_ascii=False, indent=2)
    print(f"Written: {corpus_path}")

    # Write machine-readable summary
    summary_path = OUTPUT_DIR / "machine_readable_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "campaign_id": CAMPAIGN_ID,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": "FAIL",
            "metrics": metrics,
            "module_integration": {
                "evidence_contract": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "source_lineage_service": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "legacy_relation_adapter": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "answer_evidence_gate": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "evidence_snapshot_service": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "event_ontology_service": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "barriers_v73": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "narration_planner_v73": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
                "v7_quarantine": {"implemented": True, "in_decision_path": False, "classification": "IMPLEMENTED_NOT_IN_DECISION_PATH"},
            },
            "critical_findings_count": 10,
            "total_tests": metrics["total_tests"],
            "tests_passed": metrics["passed"],
            "tests_failed": metrics["failed"],
            "critical_test_failures": metrics["critical_failures"],
            "legacy_data_total_links": 4058286,
            "legacy_data_quarantined": 1708869,
            "legacy_data_quarantine_checked_by_orchestrator": 0,
            "cross_war_contaminated_links": 12759,
            "evidence_snapshots_persisted": 0,
            "modules_in_decision_path": 0,
            "modules_implemented": 9,
        }, f, ensure_ascii=False, indent=2)
    print(f"Written: {summary_path}")

    print()
    print(f"=== Campaign Complete ===")
    print(f"Verdict: FAIL")
    print(f"Tests: {metrics['passed']}/{metrics['total_tests']} passed ({metrics['pass_rate']}%)")
    print(f"Critical failures: {metrics['critical_failures']}")
    print(f"Modules in decision path: 0/9")


if __name__ == "__main__":
    main()
