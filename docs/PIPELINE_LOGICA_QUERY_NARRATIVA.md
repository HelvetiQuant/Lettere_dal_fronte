# Pipeline Logica — Query Narrativa su 8 Personaggi

## Data: 2026-08-06
## Commit: 5a65f44 (fix/provenance-linking-v2)
## File di riferimento: `unified_orchestrator_v7.py`, `v7_narrator.py`, `v7_identity_model.py`

---

## Diagramma Flusso

```
INPUT (nome + table + source_id)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: PLAN (_stage_plan)                                │
│  SemanticQueryPlan ← build_plan(user_input, intent)        │
│  • TargetSpec: display_name, target_type, target_id        │
│  • Intent: PERSON_LOOKUP                                    │
│  • Provider routes: DISCOVERY_WEB, ARCHIVE_SEARCH           │
│  • _lookup_origin_record(): query internati per cognome+nome│
│  → Output: plan con routes + origin_record                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: DISCOVER (_stage_discover)                        │
│  • build_query_family(): varianti query (nominativo,        │
│    event-based, OCR, geografico)                            │
│  • _query_local_db(): query su 5 tabelle PERSON:            │
│    - internati (cognome=? AND nome=?)                       │
│    - caduti_albooro (nominativo LIKE "COGNOME%")            │
│    - decorati_nastroazzurro (cognome=? AND nome=?)          │
│    - caduti_cwgc, caduti_ministero                           │
│  • AdapterRegistry.search_all():                            │
│    - LocalDbAdapter → osservazioni da SQLite                │
│    - FederationAdapter → 27 provider (ICRC, Arolsen, NARA,  │
│      ABMC, Gallica, Archive.org, Bundesarchiv, ecc.)        │
│    - WebSearchAdapter[tavily] → search API                  │
│    - WebSearchAdapter[serpapi] → search API                 │
│  • Varianti query family → web adapters per ogni variante   │
│  → Output: List[ProviderObservation] (50-200 per target)    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 3: FETCH (_stage_fetch)                              │
│  • Filtra search-page URLs (_is_search_page_url)            │
│  • Se ha snippet/excerpt → METADATA_ONLY                    │
│  • Se no content → FAILED + reason NO_CONTENT_AVAILABLE     │
│  → Output: osservazioni con content_state classificato      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 4: EXTRACT (_stage_extract + _stage_extract_person)  │
│                                                             │
│  4a. Anomaly detection (v7_record_anomaly.py):              │
│    - INCOMPLETE_NAME: cognome/nome vuoto                    │
│    - OCR_DEFORMED_PLACE: toponimi con cifre/OCR errori      │
│    - Divergenza fonti (es. Belgrado vs Grecia)              │
│                                                             │
│  4b. Identity classification (IdentityResolver):            │
│    - FULL_NAME_CANDIDATE → obs.classification = SOURCE_CANDIDATE│
│    - SURNAME_ONLY_NON_CANDIDATE → nascosto                  │
│    - Cluster-based: cognome+nome+discriminanti (data, luogo)│
│                                                             │
│  4c. Claim extraction (person_source_schemas.py):           │
│    - PERSON_SOURCE_SCHEMAS: registry per 5 tabelle           │
│    - extract_claims_from_record(): mappa campi → predicati  │
│    - PersonCandidate: cognome, nome, war_period              │
│    - FactEvidence: predicate, value, source_table, source_id│
│    - SourceProvenance: archivio, URL, authority_tier        │
│    - Dedup: per cluster+predicate+normalized_value          │
│    - ConflictSet: conflitti attivi tra claim                │
│  → Output: person_claims, context_claims, provenance_items  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 5: RESOLVE (_stage_resolve)                          │
│  IdentityResolver.resolve():                                │
│    - ANCHORED_RECORD: singolo cluster, record di origine    │
│    - RESOLVED_IDENTITY: singolo cluster con discriminanti   │
│    - PARTIAL_IDENTITY: singolo cluster, senza discriminanti │
│    - AMBIGUOUS_IDENTITY: 2+ cluster non separabili          │
│    - UNRESOLVED_IDENTITY: 0 cluster                          │
│                                                             │
│  Homonym rejection:                                         │
│    - reject_homonym() per cluster non-risolto               │
│    - conflicting_fields: data_nascita, luogo, paternità     │
│  → Output: identity_status, resolved_cluster, rejected[]    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 6: FUSE (_stage_fuse)                                │
│  • Se AMBIGUOUS_IDENTITY → BLOCKED, usa solo asserted claims│
│  • Filtra osservazioni al cluster risolto                   │
│  • SourceFamilyGraph: rileva same-archive relations         │
│  • FusionEngine.fuse():                                     │
│    - accepted: claim corroborati da fonti indipendenti      │
│    - conflicting: claim con valori divergenti               │
│    - asserted: claim singoli non corroborati                │
│  • IndependenceAssessor: gruppi di indipendenza             │
│  → Output: accepted[], conflicting[], asserted[]            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 7: VALIDATE (_stage_validate)                        │
│  • EvidenceSnapshotV7.validate_invariants():                 │
│    - No cross-cluster contamination                         │
│    - No legacy leakage (quarantined links)                  │
│    - Temporal consistency (WWI vs WWII)                     │
│    - Geographic consistency                                 │
│  → Output: violations[] (aggiunte a ctx.errors)             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 8: NARRATE (_stage_narrate)                          │
│  NarratorV7_v2.narrate(snapshot, use_ai=True):              │
│                                                             │
│  8a. Build snapshot (EvidenceSnapshotV7):                   │
│    - identity_status, corroboration_status                  │
│    - person_claims (con evidence_scope=PERSON_EVIDENCE)     │
│    - context_claims                                         │
│    - provider_ledger (tutte le osservazioni)                │
│    - conditional_gaps (campi mancanti)                      │
│    - limitations (NO_AI_PROVIDER, ecc.)                     │
│                                                             │
│  8b. AI Draft (se provider disponibile):                    │
│    - _call_openai / _call_mistral / _call_anthropic         │
│    - Schema: NarrationDraft (blocchi atomici)               │
│    - Payload: snapshot → contesto strutturato               │
│    - Evidence-locked: AI riceve solo claim con ID, non URL  │
│    - Circuit breaker: se provider fallisce → fallback       │
│                                                             │
│  8c. Validation (OutputValidatorV7):                        │
│    - _validate_payload(): schema JSON valido                │
│    - _compute_evidence_hash(): hash claim usati             │
│    - _post_gen_hallucination_check():                       │
│      * Date non in evidenza → HALLUCINATED_DATE             │
│      * Luoghi/nomi non in evidenza → HALLUCINATED_PLACE     │
│      * Skip list: decorazioni (Croce, Valor, Medaglia)      │
│      * Word boundary: "Lana" ≠ "Castellana"                 │
│    - Repair: se errori strutturali → retry con fix          │
│                                                             │
│  8d. Render (ReportRenderer):                               │
│    - Blocchi → markdown narrativo                            │
│    - Citazioni [fonte: table#id]                            │
│    - Sezione Provenienza (snapshot ID, schema, contract)    │
│    - Sezione Fonti (provider ledger)                        │
│                                                             │
│  8e. Fallback deterministico (se AI non disponibile):       │
│    - _deterministic_fallback_report()                       │
│    - Template strutturato con claim APPROVED/PROBABLE/      │
│      NEEDS_REVIEW/GAP                                       │
│                                                             │
│  → Output: NarrationResult (answer_markdown + metadata)     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 9: PERSIST (_stage_persist)                          │
│  • Attualmente no-op (in-memory)                            │
│  • Futuro: save snapshot + report su DB/Supabase            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  POST-PROCESSING: _compute_semantic_counts()                │
│  • unique_person_facts: dedup per predicate+value           │
│  • supporting_evidence_records: totale evidenze             │
│  • unique_source_records: record distinti                   │
│  • provenance_items: count separato                         │
│  • conflict_sets: conflitti attivi                          │
│  • rejected_observations: homonyms + failed                 │
│  → Output: dict con metriche semantic_counts                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
OUTPUT (JSON)
{
  "run_id": "run_v7_...",
  "plan_id": "...",
  "snapshot": { identity_status, corroboration_status, ... },
  "report": "## Rapporto narrativo...",
  "errors": [],
  "warnings": ["NARRATION_FLAG: HALLUCINATED_DATE:19..."],
  "semantic_counts": { ... },
  "stage_timings": { plan, discover, fetch, extract, resolve, fuse, validate, narrate, total }
}
```

---

## Flusso Dati Reale per Target

### Esempio: GAIASCHI LUIGI (internati #22808)

```
INPUT: "GAIASCHI LUIGI", PERSON_LOOKUP, internati#22808
│
├── STAGE 1 PLAN
│   ├── _lookup_origin_record() → internati row:
│   │   cognome=GAIASCHI, nome=LUIGI, luogo_nascita=Nibbiano (Piacenza)
│   │   data_nascita=1912-01-09, luogo_cattura=Grecia, data_cattura=1943-09-12
│   └── SemanticQueryPlan: intent=PERSON_LOOKUP, routes=[local_db, web, federation]
│
├── STAGE 2 DISCOVER
│   ├── LocalDbAdapter: 5 observations
│   │   ├── internati#22808 (GAIASCHI LUIGI)
│   │   ├── caduti_albooro#102126 (GAIASCHI GIUSEPPE) ← omonimo
│   │   ├── caduti_albooro#161075 (GAIASCHI GIUSEPPE) ← omonimo
│   │   ├── caduti_albooro#102125 (GAIASCHI CAMILLO) ← cognome match
│   │   └── caduti_albooro#161074 (GAIASCHI GIOVANNI) ← cognome match
│   ├── FederationAdapter: 16 observations (ICRC, Arolsen, NARA, ABMC...)
│   ├── WebSearchAdapter[tavily]: 9 observations in 1.69s
│   └── WebSearchAdapter[serpapi]: 9 observations in 17.73s
│   TOTAL: ~39 observations
│
├── STAGE 3 FETCH
│   ├── Local DB → METADATA_ONLY (raw_record disponibile)
│   ├── Federation → METADATA_ONLY (snippet/excerpt)
│   └── Web → METADATA_ONLY (snippet)
│
├── STAGE 4 EXTRACT
│   ├── Anomaly detection: INCOMPLETE_NAME su caduti_albooro (cognome vuoto)
│   ├── Identity classification:
│   │   ├── GAIASCHI LUIGI (internati#22808) → FULL_NAME_CANDIDATE → cluster_1
│   │   ├── GAIASCHI GIUSEPPE (albooro#102126) → FULL_NAME_CANDIDATE → cluster_2
│   │   ├── GAIASCHI GIUSEPPE (albooro#161075) → FULL_NAME_CANDIDATE → cluster_3
│   │   ├── GAIASCHI CAMILLO → SURNAME_ONLY_NON_CANDIDATE → nascosto
│   │   └── GAIASCHI GIOVANNI → SURNAME_ONLY_NON_CANDIDATE → nascosto
│   ├── Claim extraction (person_source_schemas):
│   │   ├── cluster_1 (LUIGI):
│   │   │   ├── birth_place: Nibbiano (Piacenza) [internati#22808]
│   │   │   ├── birth_date: 1912-01-09 [internati#22808]
│   │   │   ├── capture_place: Grecia [internati#22808]
│   │   │   ├── capture_date: 1943-09-12 [internati#22808]
│   │   │   ├── fate: altro (IMI, lavoro forzato) [internati#22808]
│   │   │   └── data_quality_note: divergenza Belgrado vs Grecia
│   │   └── cluster_2/3 (GIUSEPPE): claim separati, non fusi con LUIGI
│   └── Provenance: fonti italiane vs Asse, authority_tier tracking
│
├── STAGE 5 RESOLVE
│   ├── cluster_1 (LUIGI): cognome+nome match esatto + discriminanti
│   │   → RESOLVED_IDENTITY
│   ├── cluster_2/3 (GIUSEPPE): omonimi, cluster separati
│   │   → reject_homonym: HOMONYM_DIFFERENT_IDENTITY
│   └── Output: identity_status=RESOLVED_IDENTITY, resolved_cluster=cluster_1
│
├── STAGE 6 FUSE
│   ├── Filter: solo cluster_1 observations
│   ├── SourceFamilyGraph: internati (1 fonte), web (fonti indipendenti)
│   ├── FusionEngine: accepted=8 claim, conflicting=0, asserted=8
│   └── Independence: internati è fonte primaria, web sono context
│
├── STAGE 7 VALIDATE
│   ├── No cross-cluster contamination ✓
│   ├── No legacy leakage ✓
│   ├── Temporal: WWII consistent (1943) ✓
│   └── 0 violations
│
├── STAGE 8 NARRATE
│   ├── Snapshot: identity=RESOLVED, corroboration=PARTIAL
│   │   person_claims=8, provider_ledger=39 observations
│   ├── AI Draft (OpenAI GPT-4o):
│   │   → Fallback deterministico (AI non produce draft valido)
│   ├── Deterministic fallback:
│   │   → Template strutturato con claim APPROVED/PROBABLE/NEEDS_REVIEW
│   ├── Hallucination check: 0 warnings (tutti i claim in evidenza)
│   └── Render: markdown con sezioni APPROVED, PROBABLE, NEEDS REVIEW, GAP
│
└── OUTPUT
    ├── identity_status: RESOLVED_IDENTITY
    ├── report: "# Rapporto di Ricerca — snap_v7_89882fc9c070268b..."
    │   ├── APPROVED: birth_place, birth_date, capture_place, capture_date, fate
    │   ├── PROBABLE: birth_place (corroborato)
    │   ├── NEEDS REVIEW: source_text (testo grezzo)
    │   ├── Gap condizionali: rank, unit, death_date (non supportati)
    │   └── Provenienza: snapshot ID, schema 7.2, narrator contract
    └── elapsed: 15.2s
```

---

## Componenti Chiave Invocate

| Componente | File | Ruolo |
|---|---|---|
| `UnifiedResearchOrchestratorV7` | `unified_orchestrator_v7.py` | Orchestratore 9 stage |
| `SemanticQueryPlan` | `semantic_query_plan.py` | Piano di query con routes |
| `V7AdapterRegistry` | `v7_provider_adapters.py` | Dispatch provider (local, web, federation) |
| `build_query_family` | `v7_query_family.py` | Varianti query (nominativo, OCR, geo) |
| `IdentityResolver` | `v7_identity_model.py` | Risoluzione identità cluster-based |
| `PERSON_SOURCE_SCHEMAS` | `person_source_schemas.py` | Registry mapping 5 tabelle → predicati |
| `PersonCandidate` | `person_pipeline_models.py` | Modello tipizzato candidato |
| `FactEvidence` | `person_pipeline_models.py` | Evidenza con predicato+valore+fonte |
| `SourceProvenance` | `person_pipeline_models.py` | Provenienza con authority_tier |
| `SourceFamilyGraph` | `v7_fusion_engine.py` | Grafo relazioni same-archive |
| `FusionEngine` | `v7_fusion_engine.py` | Fusione multi-provider con indipendenza |
| `EvidenceSnapshotV7` | `evidence_snapshot_v7.py` | DTO snapshot con invarianti |
| `NarratorV7_v2` | `v7_narrator.py` | Narratore AI + fallback deterministico |
| `OutputValidatorV7` | `v7_narrator.py` | Validazione output (hallucination check) |
| `ReportRenderer` | `v7_narrator.py` | Render markdown con citazioni |
| `detect_anomalies` | `v7_record_anomaly.py` | Detection anomalie su record DB |
| `MemoryRouter` | `memory_router.py` | Router retrieval (SQL, FTS, graph, LeBI) |
| `SourceLocator` | `source_locator.py` | Domini autorizzati per source fetch |
| `ReportEngine` | `report_engine.py` | Generazione report con citazioni LeBI |

---

## Provider Invocati per Discovery

| Provider | Tipo | Osservazioni tipiche |
|---|---|---|
| LocalDbAdapter | SQLite | 3-10 (5 tabelle PERSON) |
| FederationAdapter | 27 provider federati | 16-30 (ICRC, Arolsen, NARA, ABMC, Gallica...) |
| WebSearchAdapter[tavily] | Search API | 9-20 |
| WebSearchAdapter[serpapi] | Search API | 7-10 |

---

## Metriche per Target

| Target | Osservazioni | Claim | Identity | Tempo |
|---|---|---|---|---|
| TARISE Giuseppe | 63 | 7 | RESOLVED | 18.5s |
| POMPA Gianfranco | 72 | 6 | RESOLVED | 17.4s |
| ROBERTI Nicola | 138 | 50 | RESOLVED | 15.4s |
| CARBONE Giuseppe | 195 | 210 | AMBIGUOUS | 12.2s |
| BASAVECCHIA Corrado | 57 | 3 | RESOLVED | 25.5s |
| NERINI Giuseppe | 96 | 20 | AMBIGUOUS | 16.6s |
| GAIASCHI Luigi | 39 | 8 | RESOLVED | 15.2s |
| GAIASCHI Giuseppe | 59 | 16 | AMBIGUOUS | 28.0s |

---

## Regole Enforce dalla Pipeline

1. **Evidence-locked**: AI riceve solo claim con ID, mai URL dirette
2. **Cluster-based identity**: omonimi non fusi (GAIASCHI LUIGI ≠ GIUSEPPE)
3. **War-period aware**: WWI e WWII non contaminano (barriere temporali)
4. **Hallucination check**: date/luoghi non in evidenza vengono flaggati
5. **Decoration skip**: Croce, Valor, Medaglia non flaggati come allucinazioni
6. **Quarantine**: legacy links con usable_as_evidence=0 non usati come evidenza
7. **Non-destructive**: correzioni via data_corrections overlay, mai UPDATE diretto
8. **Circuit breaker**: se AI provider fallisce → fallback deterministico
9. **Schema-driven**: 5 tabelle PERSON mappate via registry, non hardcoded
10. **Word boundary**: "Lana" ≠ "Castellana", "Roma" ≠ "Romania"
