# V7_2_ACTIVE_CALL_PATH.md — Call Path Reale Pipeline V7.2

**Data:** 2026-08-03
**Repository:** imi_extractor
**Schema version:** 7.2

---

## Call path end-to-end: `UnifiedResearchOrchestratorV7.execute()`

```
execute(user_input, intent, conflict)
│
├── _stage_plan()
│   └── semantic_query_plan.build_plan()
│       └── TargetSpec(origin_record_id, display_name, conflict)
│
├── _stage_discover()
│   └── v7_provider_adapters.V7AdapterRegistry.search_all()
│       ├── LocalDbAdapter.search()
│       │   └── database.get_conn() → SQLite
│       │       ├── PERSON_LOOKUP: exact full-name + surname prefix (discovery)
│       │       │   ├── internati (cognome+nome exact → SOURCE_CANDIDATE)
│       │       │   ├── caduti_albooro (nominativo exact → SOURCE_CANDIDATE)
│       │       │   ├── decorati_nastroazzurro
│       │       │   ├── caduti_cwgc
│       │       │   └── caduti_ministero
│       │       │   Surname-only matches → SURNAME_ONLY_NON_CANDIDATE
│       │       └── EVENT_LOOKUP: eventi_1gm
│       ├── WebSearchAdapter.search()
│       │   └── web_search_providers.search_tavily/brave/serper/serpapi
│       └── FederationAdapter.search()
│           └── source_providers.federation.federated_search()
│
├── _stage_fetch()
│   └── For each observation:
│       ├── OPENED → content extracted with locator
│       ├── METADATA_ONLY → snippet/excerpt only
│       └── FAILED → reason code
│
├── _stage_extract()
│   └── v7_identity_model.IdentityResolver.resolve_observation()
│       └── Assign identity_cluster_id to each observation
│
├── _stage_resolve()
│   └── Identity clustering:
│       ├── Exact full-name match → candidate cluster
│       ├── Surname-only → SURNAME_ONLY_NON_CANDIDATE (hidden)
│       ├── Discriminants: birth_year, birth_place, paternity, unit+period, death_year/place
│       ├── If 1 cluster + discriminant → RESOLVED_IDENTITY
│       ├── If 1 cluster, no discriminant → PARTIAL_IDENTITY or ANCHORED_RECORD
│       ├── If 2+ clusters same name → AMBIGUOUS_IDENTITY
│       └── If 0 clusters → UNRESOLVED_IDENTITY
│
├── _stage_fuse()  [BLOCKED if AMBIGUOUS_IDENTITY]
│   └── v7_fusion_engine.FusionEngine.fuse()
│       ├── Only observations from resolved_identity_cluster_id
│       ├── Other clusters → candidate_identities[]
│       ├── Person claims → person_claims
│       ├── Context claims → context_claims (scope=UNIT|EVENT|PLACE|CAMP|PERIOD)
│       └── Source lineage: document fingerprint, content similarity, derived_from
│
├── _stage_validate()
│   └── evidence_snapshot_v7.validate_invariants()
│       ├── cross_identity_claims = 0
│       ├── all claims have identity_cluster_id == resolved_identity_cluster_id
│       └── all evidence has stable_source_reference OR precise_locator
│
├── _stage_narrate()
│   └── v7_narrator.NarratorV7.narrate()
│       ├── _try_ai_narration() → ai_client.call_ai()
│       │   └── JSON structured output:
│       │       { identity_status, opening, reconstruction, decisive_uncertainties, next_steps, sources }
│       ├── OutputValidatorV7.validate()
│       │   ├── No internal IDs/enums in visible text
│       │   ├── No surname-only candidates visible
│       │   ├── Max 5 uncertainties, 4 next steps
│       │   ├── Every sentence maps to person_claim or context_claim
│       │   └── No context misattributed to person
│       └── ReportRenderer.render_discursive_markdown()
│           └── Opening → Reconstruction → Uncertainties → Next steps → Sources
│
└── _stage_persist()
    └── (in-memory)
```

---

## Moduli attivi V7.2

| File | Classe/Funzione | Stadio | Modifica V7.2 |
|------|----------------|--------|---------------|
| `semantic_query_plan.py` | `TargetSpec`, `build_plan()` | PLAN | +origin_record_id |
| `v7_provider_adapters.py` | `LocalDbAdapter`, `WebSearchAdapter` | DISCOVER | +exact full-name, +SURNAME_ONLY_NON_CANDIDATE |
| `v7_identity_model.py` | `IdentityResolver`, `IdentityCluster` | RESOLVE | +clustering, +5 new states, +tie handling |
| `v7_fusion_engine.py` | `FusionEngine` | FUSE | +cluster-only fusion, +person/context split |
| `evidence_snapshot_v7.py` | `EvidenceSnapshotV7` | VALIDATE | +cluster_id, +candidate_identities, +context_claims |
| `v7_narrator.py` | `NarratorV7`, `ReportRenderer` | NARRATE | +JSON structured, +discursive renderer |
| `unified_orchestrator_v7.py` | `UnifiedResearchOrchestratorV7` | ALL | +block pre-FUSE, +new identity states |
| `run_canary_v7.py` | Canary runner | TEST | +6 frozen targets, +semantic oracles |

---

## Endpoint pubblico

```python
orch = UnifiedResearchOrchestratorV7()
result = orch.execute(
    user_input="EGINETI ARTURO",
    intent="PERSON_LOOKUP",
    conflict="WWI",
)
# result["report"] → discursive Markdown
# result["snapshot"] → EvidenceSnapshotV7 dict
```

---

## 6 canary target congelati

| # | Nome | Conflict | Expected identity_status |
|---|------|----------|------------------------|
| 1 | CAIS Arduino | WWII | ANCHORED_RECORD |
| 2 | BROGNARA Cristino | WWII | ANCHORED_RECORD |
| 3 | TONIOLI Pasquale | WWII | PARTIAL_IDENTITY |
| 4 | DEVINCENZI GIOVANNI | WWI | AMBIGUOUS_IDENTITY |
| 5 | EGINETI ARTURO | WWI | ANCHORED_RECORD |
| 6 | RIGAMONTI PIETRO | WWI | AMBIGUOUS_IDENTITY |
