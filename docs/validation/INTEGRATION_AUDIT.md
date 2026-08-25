# Evidence Architecture Integration Audit

**Campaign ID:** `validation_20260817_v1`  
**Date:** 2026-08-17  
**Auditor:** Cascade (automated code analysis)  
**Scope:** Verify that declared Evidence-Centric Architecture modules (Phases 2-7) are implemented AND integrated into the V7 pipeline decision path.

---

## Methodology

For each declared module, the audit verifies:
1. **File exists** — physical .py file present
2. **Classes/functions defined** — API surface as declared
3. **Imported by production code** — `grep` for `from <module>` / `import <module>` across all .py files
4. **In decision path** — called during `unified_orchestrator_v7.py` execution stages
5. **Classification:** `IMPLEMENTED_AND_USED` | `IMPLEMENTED_NOT_IN_DECISION_PATH` | `PARTIALLY_IMPLEMENTED` | `NOT_IMPLEMENTED` | `BYPASSABLE`

---

## Module Audit

### 1. `evidence_contract.py` — Evidence Contract & Validators

| Check | Result |
|-------|--------|
| File exists | YES (574 lines) |
| Classes defined | `ClaimStatus`, `EvidenceContract`, `AnswerEvidenceBundle`, `ClaimRef`, `EvidenceRef`, `SourceRef`, `ObservationRef`, `TemporalGate`, `RelationOrigin`, `SourceOriginType` |
| Imported by production code | **NO** — zero imports found across entire codebase |
| In decision path | **NO** |
| Classification | **IMPLEMENTED_NOT_IN_DECISION_PATH** |

**Details:** The module defines the canonical evidence chain (SOURCE → OBSERVATION → EVIDENCE → CLAIM → RELATION → ANSWER) with validators and 10 key invariants. However, no file in the codebase imports it. The `ClaimStatus` enum defined here is never used by the orchestrator or narrator — the narrator uses its own ad-hoc status strings (`APPROVED`, `PROBABLE`, `NEEDS_REVIEW`, `REJECTED`, `CONTEXT`) via `v7_claim_rules.classify_claim_status()` instead.

**Impact:** The 10 architectural invariants (e.g., "No claim without evidence", "No verified status without evidence + provenance", "No AI answer without AnswerEvidenceBundle") are declared but never enforced.

---

### 2. `source_lineage_service.py` — DB-backed Source Lineage

| Check | Result |
|-------|--------|
| File exists | YES (663 lines) |
| Classes defined | `LineageRegistry`, `LineageBootstrap`, `LineageAwareAssessor`, `LineageSync` |
| Imported by production code | **NO** — zero imports found |
| In decision path | **NO** |
| Classification | **IMPLEMENTED_NOT_IN_DECISION_PATH** |

**Details:** The module provides DB-backed lineage tracking with `source_lineages` and `source_lineage_members` tables, independence scoring, and a bootstrap from known sources (ANRP, CICR, Ministero, Albo d'Oro, CWGC, etc.). It imports from `evidence_contract` but is itself imported by nothing.

The orchestrator's `_stage_fuse()` uses the in-memory `SourceFamilyGraph` and `IndependenceAssessor` from `v7_fusion_engine.py` instead. The in-memory version has no persistence and no DB lineage lookup. The `LineageAwareAssessor` that would replace it is never called.

**Impact:** The principle "MULTIPLE SOURCES ≠ INDEPENDENT SOURCES" is only enforced heuristically via in-memory edge types (SAME_ARCHIVE, SAME_OCR, etc.). The DB-backed lineage with authority levels and canonical origins is unused. Source independence counting may be inaccurate.

---

### 3. `legacy_relation_adapter.py` — Legacy Quarantine & Revalidation

| Check | Result |
|-------|--------|
| File exists | YES |
| Classes defined | `LegacyRelationAdapter`, `LegacyRelation`, `AdapterStats` |
| Imported by production code | **NO** — zero imports found |
| In decision path | **NO** |
| Classification | **IMPLEMENTED_NOT_IN_DECISION_PATH** |

**Details:** The adapter reads legacy tables (`record_links`, `collegamenti`, `event_links`), parses rows into `LegacyRelation` objects, and imports them into the V2 `relations` table with `origin='legacy'`, `status='legacy_candidate'`. It supports scan (audit-only), read, and import (with dry_run).

However, no pipeline stage calls it. The orchestrator does not quarantine or revalidate legacy relations through this adapter. The V7.3 quarantine migration (`migrate_v73_quarantine.py`) added `usable_as_evidence=0` columns to legacy tables, but the orchestrator never checks `usable_as_evidence` when building observations or claims.

**Impact:** Legacy relations are not systematically revalidated through the evidence pipeline. The `usable_as_evidence` flag exists in the DB but is never queried by the orchestrator. Legacy data can enter the pipeline without passing through the adapter's quarantine checks.

---

### 4. `answer_evidence_gate.py` — Answer Evidence Gate

| Check | Result |
|-------|--------|
| File exists | YES (373 lines) |
| Classes defined | `AnswerEvidenceGate` |
| Imported by production code | **NO** — zero imports found |
| In decision path | **NO** |
| Classification | **IMPLEMENTED_NOT_IN_DECISION_PATH** |

**Details:** This is the most critical finding. The `AnswerEvidenceGate` is designed to:
1. Convert `EvidenceSnapshotV7` → `AnswerEvidenceBundle` (evidence contract format)
2. Group claims by verification status (verified/probable/disputed/unsupported/rejected)
3. Block legacy/unverified claims from reaching the AI
4. Build a gated AI prompt with evidence hash
5. Post-generation verification (check AI output against bundle)

**None of this is used.** The actual narrator (`NarratorV7_v2` in `v7_narrator.py`) uses:
- `NarrationEvidenceSelector` (from `narration_evidence_selector.py`) — selects claims by budget and priority, excludes REJECTED
- `NarrationValidator` (from `narration_validator.py`) — validates draft against claim allowlist
- `_validate_payload()` — checks claim IDs exist in snapshot, no REJECTED status
- `_post_gen_hallucination_check()` — checks for hallucinated dates/places, temporal contamination
- `_ai_cross_validate()` — AI cross-validation via OpenAI/Mistral

The narrator's own validation is **weaker** than what `AnswerEvidenceGate` would provide:
- No `AnswerEvidenceBundle` structure is built
- No evidence hash is computed for the bundle (only a claim-ID hash)
- No verification status grouping (verified/probable/disputed/unsupported)
- No provenance chain validation
- No `ClaimStatus` enum enforcement (uses ad-hoc strings)
- No post-generation check for unsupported claims stated as fact
- No check for rejected claims mentioned in output

**Impact:** CRITICAL. The AI narrator receives claims filtered by `NarrationEvidenceSelector` but without the structured evidence gate. Unsupported claims can be narrated as fact. The gate's `verify_answer()` method (checking that unsupported claims are hedged, rejected claims are not mentioned, disputed claims acknowledge conflict) is never called.

---

### 5. `evidence_snapshot_service.py` — Persistent Snapshot Storage

| Check | Result |
|-------|--------|
| File exists | YES |
| Classes defined | (to verify) |
| Imported by production code | **NO** — zero imports found |
| In decision path | **NO** |
| Classification | **IMPLEMENTED_NOT_IN_DECISION_PATH** |

**Details:** The module is designed to persist `EvidenceSnapshotV7` to the `evidence_snapshots` table (defined in `schema_v2.py` with `context_hash`, `answer_hash`, `snapshot_json` columns). However, the orchestrator's `_stage_persist()` method is a **pass** statement — it does nothing.

```python
def _stage_persist(self, ctx: RunContext):
    """Stage 9: Save snapshot + report to DB."""
    # Persistence is done via the existing report_conversation_provider
    # or a new V7 persistence layer. For now, we keep it in-memory.
    pass
```

**Impact:** Snapshots are ephemeral (in-memory only via `RunContext`). No persistent evidence trail. The `evidence_snapshots` table exists in schema but is never populated. Snapshot reproducibility (Section 16 of validation campaign) cannot be tested because snapshots are not saved or reloadable.

---

### 6. `event_ontology_service.py` — Hierarchical Event Ontology

| Check | Result |
|-------|--------|
| File exists | YES |
| Classes defined | `EventOntologyService` |
| Imported by production code | **NO** — zero imports found |
| In decision path | **NO** |
| Classification | **IMPLEMENTED_NOT_IN_DECISION_PATH** |

**Details:** The service provides hierarchical event management with parent-child relationships, cycle detection, temporal containment validation, alias management, and tree queries. It operates on the `eventi_1gm` table with `parent_event_id` and `event_aliases` columns.

The orchestrator uses `v7_event_aggregate.EventOntology` (from `v7_event_aggregate.py`) instead, which is a different, simpler event model. The `event_resolver.py` has a hardcoded `HIERARCHY` dictionary that is used for event resolution, not the DB-backed service.

**Impact:** The hierarchical event ontology (WAR → THEATER → CAMPAIGN → BATTLE → SECTOR → ACTION) is defined but not consulted during event resolution or narration. Event parent-child relationships in the DB are not validated through the service. Cycles, invalid parents, and temporal containment violations may exist undetected.

---

## Existing V7 Modules — Integration Status

### Modules IN the decision path

| Module | Imported by | Used in stage | Status |
|--------|-------------|---------------|--------|
| `v7_identity_model.py` | `unified_orchestrator_v7.py:49` | `_stage_resolve()` | IMPLEMENTED_AND_USED |
| `v7_fusion_engine.py` | `unified_orchestrator_v7.py:50` | `_stage_fuse()` | IMPLEMENTED_AND_USED |
| `v7_narrator.py` | `unified_orchestrator_v7.py:52` | `_stage_narrate()` | IMPLEMENTED_AND_USED |
| `person_source_schemas.py` | `unified_orchestrator_v7.py:814` | `_stage_extract_person_claims()` | IMPLEMENTED_AND_USED |
| `evidence_snapshot_v7.py` | `unified_orchestrator_v7.py:38` | snapshot construction | IMPLEMENTED_AND_USED |
| `v7_provider_adapters.py` | `unified_orchestrator_v7.py:48` | `_stage_discover()` | IMPLEMENTED_AND_USED |
| `narration_evidence_selector.py` | `v7_narrator.py:32` | narrate v2 | IMPLEMENTED_AND_USED |
| `narration_validator.py` | `v7_narrator.py:33` | narrate v2 | IMPLEMENTED_AND_USED |

### Modules NOT in the orchestrator decision path

| Module | Used by | Status |
|--------|---------|--------|
| `barriers_v73.py` | `narration_planner_v73.py`, tests only | IMPLEMENTED_NOT_IN_DECISION_PATH |
| `narration_planner_v73.py` | `conversational_renderer_v73.py`, `run_v73_conversational.py` | IMPLEMENTED_NOT_IN_DECISION_PATH (not used by main orchestrator) |
| `v7_quarantine.py` | standalone tool | IMPLEMENTED_NOT_IN_DECISION_PATH |
| `graph_service.py` | `graph_api.py` (separate API) | IMPLEMENTED_NOT_IN_DECISION_PATH (not in orchestrator) |
| `domain_model_v73.py` | `narration_planner_v73.py`, tests | IMPLEMENTED_NOT_IN_DECISION_PATH (not in main orchestrator) |
| `text_matching_v73.py` | `narration_planner_v73.py`, tests | IMPLEMENTED_NOT_IN_DECISION_PATH |

---

## Follow-Up Chat Security Analysis

The `execute_followup()` method in `unified_orchestrator_v7.py` (line 223) builds a system prompt via `_build_followup_system_prompt()` (line 356) that includes:

- **All** `person_claims` (regardless of status — no filtering by APPROVED/REJECTED)
- **All** `context_claims` (no status filtering)
- Previous report (truncated to 2000 chars)
- Instructions: "don't invent", "cite sources", "don't mix wars", "say non documentato"

**Critical gaps:**
1. No `AnswerEvidenceGate` — all claims passed to AI regardless of verification status
2. No claim status filtering — REJECTED and UNSUPPORTED claims are included in the prompt
3. No evidence hash verification
4. No post-generation validation (no `verify_answer()` call)
5. No `NarrationEvidenceSelector` — no budget limiting or priority scoring
6. Leading questions or false presuppositions are not detected or blocked
7. The AI can be asked to "complete" missing information, potentially hallucinating
8. Multi-turn contamination: conversation history is passed directly without evidence constraint checking

---

## Graph Legacy Leakage Analysis

`graph_service.py` `_status_from_row()` (line 151):
- Legacy `record_links` with `legacy_unverified=1` or `algorithm_version='legacy'` → `to_review` ✓
- Legacy `event_links` with no `algorithm_version` → `to_review` ✓
- Legacy `event_links` with `algorithm_version != 'legacy'` → `candidate` ✓

**Gaps:**
1. `usable_as_evidence` column is **never checked** — quarantined links can still appear as `candidate`
2. `origin` column is **never checked** — legacy relations are not distinguished from V2 relations
3. `war_period` column is **never checked** — cross-war contaminated links can appear without warning
4. The `include_to_review` parameter defaults to `True` — legacy edges are shown by default
5. No `confirmed` or `verified` status is assigned without explicit review, which is correct
6. BUT: edges with `confidence >= 0.8` get `confidence_label = "alta"` regardless of legacy status

---

## Summary Classification

| Module | Classification | Risk |
|--------|---------------|------|
| `evidence_contract.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | CRITICAL |
| `source_lineage_service.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | HIGH |
| `legacy_relation_adapter.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | HIGH |
| `answer_evidence_gate.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | CRITICAL |
| `evidence_snapshot_service.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | HIGH |
| `event_ontology_service.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | MEDIUM |
| `barriers_v73.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | HIGH (temporal/geographic barriers not in main pipeline) |
| `narration_planner_v73.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | HIGH (claim selection/validation not in main pipeline) |
| `v7_quarantine.py` | IMPLEMENTED_NOT_IN_DECISION_PATH | MEDIUM |
| `graph_service.py` | IMPLEMENTED_AND_USED (by graph API, not orchestrator) | MEDIUM (usable_as_evidence not checked) |

---

## Critical Findings

### CF-1: AnswerEvidenceGate is completely bypassed
The AI narrator receives claims via `NarrationEvidenceSelector`, not via `AnswerEvidenceGate`. The gate's features (evidence bundle, status grouping, provenance validation, post-generation verification) are never invoked. Unsupported claims can be narrated as fact.

### CF-2: Evidence Contract invariants are never enforced
The 10 invariants (no claim without evidence, no verified without provenance, no AI answer without bundle, etc.) are declared but never checked. The pipeline uses ad-hoc validation instead.

### CF-3: Legacy quarantine flag is ignored by the orchestrator
`usable_as_evidence=0` exists on legacy links but the orchestrator never queries this column. Legacy data flows into observations and claims without quarantine checks.

### CF-4: Follow-up chat has no evidence gating
All claims (including REJECTED and UNSUPPORTED) are passed to the AI in follow-up questions. No filtering, no hash verification, no post-generation validation.

### CF-5: Snapshot persistence is a no-op
`_stage_persist()` is `pass`. Snapshots are ephemeral. No evidence trail, no reproducibility.

### CF-6: Source lineage is in-memory only
DB-backed lineage service is unused. Independence assessment is heuristic only. Authority levels and canonical origins are not consulted.

### CF-7: Event ontology service is unused
Hierarchical event validation (cycles, temporal containment, alias dedup) is not performed during pipeline execution.

### CF-8: V7.3 barriers (temporal/geographic) not in main orchestrator
`barriers_v73.py` is only used by `narration_planner_v73.py`, which is not imported by `unified_orchestrator_v7.py`. The main pipeline does not apply WWI/WWII temporal barriers or geographic semantic role checks during claim extraction or fusion.

---

## Recommendation

**Phase 8 should be BLOCKED** until at minimum:
1. `AnswerEvidenceGate` is integrated into `_stage_narrate()` (CF-1)
2. `usable_as_evidence` is checked in `_stage_extract()` and `_stage_extract_person_claims()` (CF-3)
3. Follow-up chat filters claims by status (CF-4)
4. `_stage_persist()` calls `evidence_snapshot_service` (CF-5)

These are not optional enhancements — they are the core safety mechanisms that the Evidence-Centric Architecture was designed to provide. Without them, the pipeline operates in "legacy mode" with weaker validation than declared.
