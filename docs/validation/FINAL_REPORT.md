# Evidence-Centric Architecture Validation Campaign — Final Report

**Campaign ID:** `validation_20260817_v1`
**Date:** 2026-08-17
**Status:** COMPLETED

---

## Executive Summary

The validation campaign executed **26 tests** across 3 test suites:
- Tests A-M: Legacy confidence challenge + regression
- Tests N-T: Adversarial tests (temporal gate, source lineage, gate bypass)
- Tests U-Z: Policy analysis, cross-link audit, event ontology, snapshot, graph leakage

**Results: 3 PASS, 23 FAIL, 17 CRITICAL**
**Pass rate: 11.5%**

**Module integration: 0/9 evidence-centric modules in V7 decision path (0%)**

### Verdict: **FAIL — Evidence-Centric Architecture is NOT integrated**

All 9 evidence-centric modules (Phases 2-7) are implemented as standalone files but have **zero imports** from any production code. The V7 pipeline operates with weaker, ad-hoc validation that does not enforce the declared architectural invariants.

---

## Critical Findings

### CF-1: AnswerEvidenceGate completely bypassed
The AI narrator receives claims via NarrationEvidenceSelector, not AnswerEvidenceGate. No evidence bundle, no status grouping, no provenance validation, no post-generation verification. Unsupported claims can be narrated as fact.

### CF-2: Evidence Contract invariants never enforced
10 invariants declared (no claim without evidence, no verified without provenance, etc.) but none checked. Pipeline uses ad-hoc validation with weaker criteria.

### CF-3: Legacy quarantine flag ignored by orchestrator
usable_as_evidence=0 exists on 1.71M legacy links but orchestrator never queries this column. Legacy data flows into observations and claims without quarantine checks.

### CF-4: Follow-up chat has no evidence gating
execute_followup passes ALL claims (including REJECTED and UNSUPPORTED) to AI. No filtering, no hash verification, no post-generation validation.

### CF-5: Snapshot persistence is a no-op
_stage_persist() is literally `pass`. evidence_snapshots table has 0 rows. No evidence trail, no reproducibility.

### CF-6: Source lineage is in-memory only
DB-backed LineageAwareAssessor unused. Independence assessment is heuristic only. Dependent sources may be counted as independent.

### CF-7: Event ontology service unused
29/49 events have parent_event_id, 29 have invalid parent references. EventOntologyService (which would validate) is not called.

### CF-8: V7.3 barriers not in main orchestrator
Temporal veto (WWI/WWII) and geographic semantic roles are not in the main pipeline. 12,759 cross-war links are unblocked.

### CF-9: 2.3M collegamenti completely unquarantined
collegamenti table has NO quarantine columns (usable_as_evidence, origin, war_period). All 2.3M entity links are accessible as candidates.

### CF-10: war_period column never populated
war_period exists on event_links and record_links but is empty on all 1.71M rows. Orchestrator doesn't check it anyway.

---

## Test Results Summary

| Test | Name | Result | Critical |
|------|------|--------|----------|
| A | legacy_confidence_distribution | PASS |  |
| B | orchestrator_gating_column_check | FAIL | YES |
| C | cross_war_contamination_count | FAIL | YES |
| D | record_links_quarantine_status | PASS |  |
| E | collegamenti_legacy_status | FAIL | YES |
| F | narrator_status_filtering | FAIL | YES |
| G | followup_claim_filtering | PASS |  |
| H | persistence_stage | FAIL | YES |
| I | graph_service_quarantine_check | FAIL | YES |
| J | v73_barriers_in_orchestrator | FAIL | YES |
| K | cross_link_audit_active | FAIL |  |
| L | event_ontology_service_usage | FAIL |  |
| M | source_lineage_in_fusion | FAIL | YES |
| N | temporal_gate_cross_war | FAIL | YES |
| O | source_lineage_independence | FAIL | YES |
| P | answer_evidence_gate_bypass | FAIL | YES |
| Q | followup_rejected_claims | FAIL | YES |
| R | collegamenti_unquarantined | FAIL | YES |
| S | narrator_hallucination_check_scope | FAIL |  |
| T | war_period_column_population | FAIL | YES |
| U | verified_policy_analysis | FAIL |  |
| V | cross_link_field_provenance | FAIL |  |
| W | event_ontology_hierarchy | FAIL |  |
| X | snapshot_persistence | FAIL | YES |
| Y | graph_legacy_leakage | FAIL | YES |
| Z | summary_metrics | FAIL | YES |

---

## Legacy Data Exposure

| Dataset | Rows | Quarantined | Quarantine Checked |
|---------|------|-------------|-------------------|
| record_links | 169,184 | YES (usable_as_evidence=0) | NO |
| event_links | 1,539,685 | YES (usable_as_evidence=0) | NO |
| collegamenti | 2,349,417 | NO (no columns) | N/A |
| **Total** | **4,058,286** | **1,708,869 (42%)** | **0** |

---

## Cross-War Contamination

- **12,759** WWII internment links (`internato_ww2`) in WWI events database
- **18** WWI events contaminated with WWII data
- **0** blocked by temporal gate (barriers_v73 not in pipeline)
- **war_period** column empty on all 1.71M links

---

## Cross-Link Audit

- **4,448/20,465** (21.7%) internati have active cross-linked fields
- **40,587** active field changes from external sources (lebi, caduti, decorati)
- **0** provenance distinctions between original and cross-linked fields
- Orchestrator treats cross-linked data as original

---

## Module Integration Status

| Module | Implemented | In Decision Path | Classification |
|--------|-------------|------------------|----------------|
| evidence_contract.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| source_lineage_service.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| legacy_relation_adapter.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| answer_evidence_gate.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| evidence_snapshot_service.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| event_ontology_service.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| barriers_v73.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| narration_planner_v73.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |
| v7_quarantine.py | YES | NO | IMPLEMENTED_NOT_IN_DECISION_PATH |

---

## Risk Assessment

| Risk | Level | Description |
|------|-------|-------------|
| legacy data becoming verified | HIGH | orchestrator doesn't check usable_as_evidence |
| cross war contamination | HIGH | 12,759 WWII links in WWI DB, no temporal barrier in pipeline |
| rejected claims in narration | MEDIUM | REJECTED excluded by NarrationEvidenceSelector, but included in follow-up |
| unsupported claims as fact | HIGH | no AnswerEvidenceGate.verify_answer() |
| dependent sources as independent | MEDIUM | in-memory heuristic only, no DB lineage |
| cross linked fields as original | HIGH | 4,448 internati with cross-linked fields, no provenance distinction |
| snapshot reproducibility | CRITICAL | _stage_persist is pass, 0 snapshots saved |

---

## Recommendations

### Immediate (P0 — must fix before any production use)

1. **Integrate AnswerEvidenceGate into _stage_narrate()** — Replace raw claim passing with AnswerEvidenceBundle construction
2. **Check usable_as_evidence in _stage_extract()** — Filter out quarantined legacy links before claim extraction
3. **Filter claims by status in execute_followup()** — Exclude REJECTED and UNSUPPORTED from follow-up prompts
4. **Implement _stage_persist()** — Call evidence_snapshot_service to save snapshots
5. **Import barriers_v73 into orchestrator** — Apply temporal veto during fusion and extraction

### Short-term (P1)

6. **Populate war_period column** on all event_links and record_links
7. **Add quarantine columns to collegamenti** — 2.3M unquarantined links
8. **Integrate SourceLineageService** — Replace in-memory IndependenceAssessor with DB-backed version
9. **Integrate EventOntologyService** — Validate hierarchy during event resolution
10. **Add provenance tracking for cross-linked fields** — Mark internati fields as derived/secondary

### Long-term (P2)

11. **Migrate collegamenti to V2 relations table** via LegacyRelationAdapter
12. **Implement ClaimStatus enum throughout pipeline** — Replace ad-hoc status strings
13. **Add post-generation verify_answer()** — Check AI output against evidence bundle
14. **Full evidence contract enforcement** — All 10 invariants checked at each stage

---

## Artifacts

| Artifact | Path |
|----------|------|
| Integration Audit | docs/validation/INTEGRATION_AUDIT.md |
| Pilot Dataset | docs/validation/pilot_dataset.json |
| Test Results A-M | docs/validation/test_results_abc.json |
| Test Results N-T | docs/validation/test_results_nt.json |
| Test Results U-Z | docs/validation/test_results_uz.json |
| Failure Corpus | docs/validation/failure_corpus.json |
| Machine-Readable Summary | docs/validation/machine_readable_summary.json |
| This Report | docs/validation/FINAL_REPORT.md |

---

**Campaign completed:** 2026-08-17T17:48:42.411256+00:00
**Campaign ID:** `validation_20260817_v1`