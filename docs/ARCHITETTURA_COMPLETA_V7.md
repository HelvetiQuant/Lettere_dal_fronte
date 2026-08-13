# Architettura Completa del Sistema IMI Extractor

**Versione documento:** 7.4-ollama-integration  
**Data:** 10 Agosto 2026  
**Autore:** AI Architect  

---

## 1. Visione d'Insieme

IMI Extractor è un sistema di ricerca storica su internati militari italiani (IMI), caduti, decorati ed eventi della Prima e Seconda Guerra Mondiale. Il sistema integra 27 provider di fonti esterne, un pipeline di linking provenance-aware, un motore di narrazione AI con validazione strutturata, e un layer di persistenza duale SQLite + Supabase/PostgreSQL.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React/TS)                          │
│  Dossier · Ricerca · Eventi · Grafo · Mappe · Admin · Riconoscimenti │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ REST API (163 endpoint)
┌──────────────────────────────┴──────────────────────────────────────┐
│                         APP.PY (FastAPI)                             │
│  163 endpoint: /api/search, /api/v7/*, /api/events/*, /api/lebi/*  │
│  /api/graph/*, /api/rag/*, /api/map-features/*, /api/rc/*          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼─────────┐ ┌───────▼───────┐ ┌──────────▼──────────┐
│  V7 ORCHESTRATOR   │ │  RESEARCH     │ │  MODULE RC          │
│  (9-stage pipeline)│ │  ENGINE (V4)  │ │  (Riconoscimenti)   │
│  PLAN→DISCOVER→    │ │  Agent loop   │ │  Candidati · Fonti  │
│  FETCH→EXTRACT→    │ │  Budget cycle │ │  Valutazioni · AI   │
│  RESOLVE→FUSE→     │ │  Multi-source │ │  Pratiche · Audit   │
│  VALIDATE→NARRATE→ │ │               │ │                     │
│  PERSIST            │ │               │ │                     │
└─────────┬──────────┘ └───────┬───────┘ └──────────┬──────────┘
          │                    │                    │
    ┌─────┴──────┐      ┌──────┴──────┐      ┌──────┴──────┐
    │ V7 MODULES │      │ V4/V6 MODS  │      │ RC MODULES  │
    │ Identity    │      │ Snapshot V4 │      │ rc_ai_ana.. │
    │ Fusion      │      │ Validator   │      │ rc_dossier  │
    │ NarratorV2  │      │ Protocol    │      │ rc_state    │
    │ Evidence    │      │ Orchestr.   │      │             │
    │ Selector    │      │             │      │             │
    │ Validator   │      │             │      │             │
    └─────┬──────┘      └──────┬──────┘      └──────┬──────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼─────────┐ ┌───────▼───────┐ ┌──────────▼──────────┐
│  SOURCE FEDERATION │ │  LINKING V2   │ │  AI CLIENT (V7.5)   │
│  27 providers:     │ │  Temporal     │ │  OpenAI (gen)       │
│  NARA · ICRC · LeBI│ │  filter +     │ │  OpenAI (validator) │
│  CWGC · Arolsen    │ │  scoring +    │ │  Mistral (fallback) │
│  Antenati · SHD    │ │  decide()     │ │  Gemini · Perplexity│
│  DDB · IWM · etc.  │ │               │ │  Fallback chain     │
└─────────┬──────────┘ └───────┬───────┘ └─────────────────────┘
          │                    │
          └────────────────────┤
                               │
     ┌─────────────────────────┼─────────────────────────┐
     │                         │                         │
┌────▼──────┐          ┌──────▼──────┐          ┌───────▼───────┐
│  SQLite    │          │  Supabase   │          │  File System  │
│  imi_int.  │          │  PostgreSQL │          │  PDF · OCR    │
│  eventi_1gm│          │  6 schemi   │          │  Cache · FTS  │
│  75 tabelle│          │  21 tabelle │          │  Storage      │
└───────────┘          └─────────────┘          └───────────────┘
```

---

## 2. Database

### 2.1 SQLite — `imi_internati.db` (1.8 GB)

Il database principale. 75 tabelle organizzate in layer funzionali.

#### Layer 1: Dati Primari (estratti da fonti)

| Tabella | Descrizione | Righe (approx) |
|---------|-------------|------|
| `internati` | IMI internati (lettere A-Z, estratti da PDF) | ~970K |
| `decorati` | Decorati Albi della Memoria (ISTORECO) | ~12K |
| `decorati_nastroazzurro` | Decorati Nastro Azzurro | ~3K |
| `caduti_albooro` | Caduti Albo d'Oro | ~40K |
| `caduti_bologna` | Caduti Bologna | ~3K |
| `caduti_cwgc` | Caduti CWGC (Commonwealth) | ~1K |
| `caduti_ministero` | Caduti Ministero Difesa | ~5K |
| `caduti_sardi` | Caduti Sardi | ~2K |
| `caduti_francia_ww1` | Caduti Francesi WW1 | ~1K |
| `fondi_archivistici` | Fondi Ufficio Storico SME | ~5K |
| `menzioni` | Menzioni da fondi archivistici | ~50K |
| `fonti_narrative` | Fonti narrative personali | ~1K |
| `lettere_personali` | Lettere personali OCR | ~500 |
| `documenti_nara_t315` | Documenti NARA T315 (OCR) | ~10K |
| `documenti_nara_catalog` | Catalogo NARA | ~5K |

#### Layer 2: Entità e Collegamenti

| Tabella | Descrizione |
|---------|-------------|
| `entita` | Entità estratte (persone, luoghi, eventi) |
| `collegamenti` | Collegamenti entità ↔ record |
| `record_links` | Record-to-record linking (V1/V2/V3) con 9+ colonne probatorie |
| `event_links` | Event-to-source linking (V1/V3) con colonne probatorie |
| `external_record_links` | Link esterni ↔ record interni |

#### Layer 3: Fonti Esterne Federate

| Tabella | Descrizione |
|---------|-------------|
| `fonti_risorse` | Catalogo metadati e URL fonti esterne |
| `fonti_indice` | Indice fonti con coverage temporale (6 colonne V2) |
| `external_source_records` | Record archivistici esterni (CRI, Archimista, etc.) |
| `external_person_mentions` | Nominativi estratti da metadati esterni |
| `external_source_facts` | Fatti descritti in metadati esterni |
| `external_digital_objects` | Oggetti digitali rilevati |
| `external_access_requests` | Richieste di accesso |
| `external_import_jobs` | Tracking job import incrementali |

#### Layer 4: Source Authority & Provenance (V3)

| Tabella | Descrizione |
|---------|-------------|
| `source_authority_registry` | 12 fonti default con authority_tier (1-4), score, policy |

#### Layer 5: Linking V2 (Schema Canonico)

16 tabelle UUID-based, append-only, candidate-first:

| Tabella | Descrizione |
|---------|-------------|
| `resource_registry` | Registry tipizzato di tutte le risorse |
| `historical_events` | Eventi canonici (WWI/WW2/other) |
| `event_aliases_v2` | Alias eventi con ambiguità e validità |
| `source_artifacts` | Artefatti immutabili (append-only) |
| `ocr_observations` | Osservazioni OCR immutabili |
| `claims_v2` | Claim atomici con status (proposed/confirmed/rejected) |
| `evidence_fragments` | Frammenti di evidenza con hash |
| `claim_evidence_v2` | Relazione claim ↔ evidence |
| `review_decisions` | Decisioni di review (append-only) |
| `source_families` | Famiglie di fonti derivate |
| `source_family_members` | Membri delle famiglie |
| `relations` | Relazioni candidate/confirmed con features e calibration |
| `relation_evidence` | Evidenza per relazioni |
| `pipeline_runs` | Tracking esecuzioni pipeline |
| `legacy_relation_quarantine` | Quarantine relazioni legacy |
| `golden_dataset_labels` | Dataset etichettato per calibrazione |

#### Layer 6: Research Engine (V4)

| Tabella | Descrizione |
|---------|-------------|
| `archive_connectors` | Registry unificato fonti (27 provider) |
| `research_plans` | Piani di ricerca con budget |
| `research_sessions` | Sessioni per connector |
| `research_queries` | Query individuali |
| `research_results` | Risultati con fingerprint |
| `research_cycles` | Tracking cicli di ricerca |
| `entity_variants` | Varianti d'identità |
| `entity_match_candidates` | Match scoring con breakdown |
| `document_extractions` | Estrazioni strutturate |
| `claims` | Claim atomici (subject-predicate-object) |
| `claim_evidence` | Evidenze per claim |
| `claim_relations` | Relazioni tra claim |
| `generated_narratives` | Narrazioni versionate |
| `ai_providers` | Provider AI (6: OpenAI, Anthropic, Mistral, Perplexity, Gemini, LMStudio) |
| `ai_models` | Modelli AI per provider |
| `ai_routing_policies` | Policy di routing per task type |
| `ai_task_runs` | Esecuzioni task AI con cost tracking |
| `ai_usage_ledger` | Ledger consumi per periodo |

#### Layer 7: Grafo Canonico

| Tabella | Descrizione |
|---------|-------------|
| `graph_nodes` | Nodi (namespace, type, label, source_table, source_id) |
| `graph_edges` | Edge (relation_type, confidence, evidence, status) |
| `graph_edge_reviews` | Review decisioni su edge |
| `graph_pipeline_runs` | Tracking esecuzioni pipeline grafo |
| `graph_integrity_issues` | Issue di integrità |
| `archival_metadata` | Metadati archivistici (ISAD/ISIA) |

#### Layer 8: Percorso Riconoscimenti (RC)

| Tabella | Descrizione |
|---------|-------------|
| `rc_candidates` | Candidati riconoscimento |
| `rc_historical_events` | Eventi storici del candidato |
| `rc_sources` | Fonti del candidato |
| `rc_recognition_types` | Catalogo riconoscimenti |
| `rc_recognition_assessments` | Valutazioni riconoscimento |
| `rc_ai_analyses` | Analisi AI dettagliate |
| `rc_family_persons` | Persone famiglia |
| `rc_kinship_links` | Legami parentela |
| `rc_contact_attempts` | Tentativi contatto |
| `rc_descendant_cases` | Casi discendenti |
| `rc_administrative_cases` | Pratiche amministrative |
| `rc_audit_log` | Audit log |
| `rc_state_transitions` | Transizioni di stato |

#### Layer 9: Map Features

| Tabella | Descrizione |
|---------|-------------|
| `map_features` | Feature geografiche con provenienza (eventi_1gm.db) |

#### Layer 10: Utility

| Tabella | Descrizione |
|---------|-------------|
| `progress` | Tracking elaborazione PDF |
| `ai_ricerche` | Log ricerche AI |
| `_menzioni_field_stats` | Statistiche campi menzioni |

### 2.2 SQLite — `eventi_1gm.db` (248 MB)

Database eventi della Prima Guerra Mondiale.

| Tabella | Descrizione | Righe |
|---------|-------------|-------|
| `eventi_1gm` | Eventi canonici (12 colonne additive V2) | 49 |
| `event_aliases` | Alias eventi | 161 |
| `map_features` | Feature geografiche eventi | — |
| `event_links` | Link evento ↔ fonte (con colonne V3) | ~1.5M |

### 2.3 Supabase/PostgreSQL — `wyqesimzxieykmyhfvqs`

Schema canonico 001: 6 schemi, 21 tabelle, 40+ indici, RLS.

| Schema | Tabelle | Descrizione |
|--------|---------|-------------|
| `archive` | `repositories`, `collections`, `external_items`, `external_item_revisions`, `representations`, `document_units`, `text_versions`, `passages`, `chunks` | Archivio documentale canonico |
| `evidence` | `link_quarantine`, `rights_assessments` | Quarantine e diritti |
| `ops` | `discovery_queries`, `discovery_candidates`, `job_queue`, `fetch_cache` | Operazioni |
| `ai` | `datasets`, `dataset_versions`, `dataset_items`, `dataset_item_sources`, `evaluation_runs` | Training/eval |
| `api_public` | (views) | API pubblico |
| `legacy` | (views compatibilità) | Tabelle legacy sincronizzate |

**Stato sync:**
- `archivio_documenti`: 979 righe sincronizzate
- `eventi_1gm`: 49 righe sincronizzate
- `event_aliases`: 161 righe sincronizzate
- `event_links`: ~18% sincronizzato (in corso)

---

## 3. Pipeline V7 — 9 Stage

Il `UnifiedResearchOrchestratorV7` è il singolo punto di ingresso per ricerca, narrazione e validazione.

### Flow diagram

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. PLAN — SemanticQueryPlan                             │
│    semantic_query_plan.py → build_plan()                │
│    Intent: PERSON_LOOKUP | EVENT_LOOKUP | AGGREGATE     │
│    Output: plan_id, target, routes, budget              │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 2. DISCOVER — Multi-provider query                      │
│    v7_provider_adapters.py → V7AdapterRegistry          │
│    WebSearchAdapter · LocalDbAdapter · FederationAdapter│
│    Output: List[ProviderObservation]                    │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 3. FETCH — Open sources, extract content                │
│    OCR/metadata extraction from fetched content         │
│    Output: observations with content_state              │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 4. EXTRACT — Extract claims from content                │
│    fact_extractor.py → atomic claims with provenance    │
│    Output: claims with evidence_ids                     │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 5. RESOLVE — Identity resolution, homonym rejection     │
│    v7_identity_model.py → IdentityResolver              │
│    CanonicalIdentity · CorrectionLedger · RejectedHomonym│
│    Output: resolved_identity, rejected_homonyms         │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 6. FUSE — Multi-provider fusion                         │
│    v7_fusion_engine.py → FusionEngine                   │
│    SourceFamilyGraph · IndependenceAssessor             │
│    PRESERVE_CONTRADICTIONS · MAJORITY_VOTE              │
│    Output: fused claims with independence groups        │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 7. VALIDATE — Check invariants, detect contradictions   │
│    evidence_snapshot_v7.py → validate_invariants()      │
│    v7_claim_rules.py → apply_claim_rules()              │
│    classify_claim_status() → APPROVED|PROBABLE|REVIEW   │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 8. NARRATE — Generate report (V7.2-narration-v2)        │
│                                                         │
│    ┌─────────────────────────────────────┐              │
│    │ NarrationEvidenceSelector           │              │
│    │ → selected claims + allowlist       │              │
│    └──────────────┬──────────────────────┘              │
│                   ▼                                     │
│    ┌─────────────────────────────────────┐              │
│    │ AI Provider (draft-only)            │              │
│    │ → NarrationDraft (atomic blocks)    │              │
│    └──────────────┬──────────────────────┘              │
│                   ▼                                     │
│    ┌─────────────────────────────────────┐              │
│    │ NarrationValidator                  │              │
│    │ → allowlist check, URL rejection    │              │
│    │ → repair if invalid                 │              │
│    └──────────────┬──────────────────────┘              │
│            ┌──────┴──────┐                              │
│            ▼             ▼                              │
│       valid         invalid → repair                    │
│            │             │                              │
│            ▼             ▼                              │
│    ┌─────────────────────────────────────┐              │
│    │ Backend: render + compute metadata  │              │
│    │ → NarrationResult (always structured)│              │
│    │   answer_markdown (backend-rendered) │              │
│    │   citation_map (claim→evidence→src)  │              │
│    │   omitted_claims (deterministic)     │              │
│    │   generation_info (mode, provider)   │              │
│    └─────────────────────────────────────┘              │
│                                                         │
│    Fallback: deterministic rendering if AI fails        │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 9. PERSIST — Save snapshot + report                     │
│    In-memory per ora; persistenza via API layer         │
└─────────────────────────────────────────────────────────┘
```

### Moduli V7

| File | Classe/Function | Responsabilità |
|------|----------------|----------------|
| `semantic_query_plan.py` | `build_plan()` | Parsing input → SemanticQueryPlan |
| `evidence_snapshot_v7.py` | `EvidenceSnapshotV7` | DTO unificato: claim, evidence, identity, gaps |
| `v7_provider_adapters.py` | `V7AdapterRegistry` | Adapter per WebSearch, LocalDb, Federation |
| `v7_identity_model.py` | `IdentityResolver` | Risoluzione identità, rejection omonimi |
| `v7_fusion_engine.py` | `FusionEngine` | Fusione multi-provider con grafo indipendenza |
| `v7_claim_rules.py` | `classify_claim_status()` | Classificazione claim: APPROVED/PROBABLE/REVIEW/REJECTED |
| `v7_event_aggregate.py` | `AggregateDefinitionRegistry` | 7 definizioni aggregate deterministiche |
| `v7_narrator.py` | `NarratorV7_v2` | Pipeline draft→validate→render→result |
| `narration_models.py` | `NarrationDraft`, `NarrationResult` | Modelli Pydantic per draft e result |
| `narration_evidence_selector.py` | `NarrationEvidenceSelector` | Selezione deterministica claim con budget |
| `narration_validator.py` | `NarrationValidator` | Validazione draft: allowlist, URL, entity-specific |
| `v7_narrator_prompt_v2.py` | `SYSTEM_PROMPT_V2` | Prompt draft-only per AI |
| `v7_security_audit.py` | `LegacySecurityAuditor` | Audit sicurezza, kill switch, immutability |
| `v7_quarantine.py` | `QuarantineManager` | Quarantine derived data |

---

## 4. Pipeline Linking V2

### 4.1 Linking Record-to-Record (V3)

```
_gen_record_links_v3.py
    │
    ├── SourceAuthorityRegistry → authority_tier per fonte
    ├── TemporalConstraintEngine → hard/soft date constraints
    │     └── Official date = HARD VETO
    ├── LinkDecisionEngine → evaluate_record_link()
    │     └── Richiede 2° identificatore (date/place/paternity/matricola)
    └── Output: record_links con status, confidence, evidence_json
```

### 4.2 Linking Event-to-Source (V2)

```
linking/cli.py (Phase 3)
    │
    ├── linking/temporal_filter.py
    │     └── keyword classification: distinctive/ambiguous/opposite_conflict
    │     └── temporal_relation: overlap/conflict/unknown
    │
    ├── linking/feature_extraction.py
    │     └── extract_features_source_event()
    │     └── ConflictFlags: temporal_conflict, mixed_era, ambiguous_only
    │
    ├── linking/scoring.py
    │     └── decide() → DecisionResult
    │     └── 7-step: accepted | needs_review | rejected
    │
    └── Output: relations table (candidate/accepted/needs_review/to_review)
```

### 4.3 Grafo Canonico

```
graph_service.py
    │
    ├── Read-through adapter per 5 tabelle legacy
    │     record_links → graph_edges (status=legacy_candidate)
    │     event_links → graph_edges (status=to_review)
    │     collegamenti → graph_edges
    │     external_record_links → graph_edges
    │
    ├── graph_schema.py → 6 tabelle, 8 indici
    └── graph_api.py → /api/graph/entity/{table}/{id}
```

---

## 5. Source Federation — 27 Provider

```
source_providers/federation.py
    │
    ├── ProviderNARA          (NARA - National Archives USA)
    ├── ProviderAntenati      (Antenati.san.beniculturali.it)
    ├── ProviderCWGC          (Commonwealth War Graves Commission)
    ├── ProviderWikiTree      (WikiTree.com)
    ├── ProviderArolsen       (Arolsen Archives - ITS)
    ├── ProviderBundesarchiv  (Bundesarchiv.de)
    ├── ProviderSHD           (Service Historique de la Défense)
    ├── ProviderNationalArchivesUK
    ├── ProviderEuropeana
    ├── ProviderGallica       (BnF)
    ├── ProviderInternetArchive
    ├── ProviderGoogleBooks
    ├── ProviderABMC          (American Battle Monuments)
    ├── ProviderLibraryCanada
    ├── ProviderAustralianWarMemorial
    ├── ProviderArchivportalD
    ├── ProviderInternetCulturale
    ├── ProviderHathiTrust
    ├── ProviderUSSME         (Ufficio Storico SME)
    ├── ProviderArchivioDiStato
    ├── ProviderMemoireDesHommes
    ├── ProviderDDB           (Deutsche Digitale Bibliothek)
    ├── ProviderIWMLives      (Imperial War Museum)
    ├── ProviderGrandMemorial
    ├── ProviderICRCWW1       (ICRC WW1 Prisoners)
    ├── ProviderCRIMilano     (Croce Rossa Italiana - Milano)
    └── ProviderLeBI          (Lessico Biografico IMI - ANRP)
```

### Authority Tiers

| Tier | Nome | Score | Esempi |
|------|------|-------|--------|
| 1 | Official | 0.95 | ANRP, ICRC, State Archives |
| 2 | Primary | 0.80 | Albo d'Oro, CWGC, NARA |
| 3 | Secondary | 0.50 | Web sources, OCR-derived |
| 4 | Unofficial | 0.25 | User-submitted, unverified |

---

## 6. AI Client

```
ai_client.py
    │
    ├── call_ai() → text completion, JSON mode, image input
    ├── call_ai_json() → JSON mode with auto-parse
    ├── validate_ai_output() → V7.4 AI cross-validation (OpenAI primary, Mistral fallback)
    ├── get_available_providers() → check API keys
    ├── is_any_provider_available() → bool
    │
    ├── Providers supportati:
    │     OpenAI (GPT-4o, GPT-5.5) — validatore primario
    │     Anthropic (Claude)
    │     Mistral (Mistral Large/Nemo) — validatore fallback
    │     Perplexity (Sonar)
    │     Gemini (Google)
    │     Ollama (local, Gemma 4 e2b-it-qat) — generatore primario V7.4
    │     LM Studio (local)
    │
    └── Fallback chain: primary → secondary → local
```

### V7.4: Routing AI con Policy DB

```
ai_router.py
    │
    ├── select_model() → seleziona provider+modello da DB
    │     1. Legge routing policy da ai_routing_policies (task_type → primary_model_id)
    │     2. Rispetta primary_model_id della policy (non solo score)
    │     3. Verifica capabilities, budget, circuit breaker
    │     4. Fallback: best combined score se primary non disponibile
    │
    ├── check_budget_before_task() → skip per provider locali (cost=0)
    │
    ├── Task types:
    │     narration → OpenAI primary, Mistral fallback (Ollama escluso)
    │     generate_biography → OpenAI primary, Mistral fallback
    │     generate_viewpoints → OpenAI primary, Mistral fallback
    │     generate_timeline → OpenAI primary, Mistral fallback
    │     generate_research_plan → OpenAI primary, Mistral fallback
    │     generate_followup_queries → OpenAI primary, Mistral fallback
    │     validate_output → OpenAI primary, Mistral fallback
    │     verify_citations → OpenAI primary, Mistral fallback
    │
    └── Policy version: v7.5-openai-primary
```

### V7.4: AI Cross-Validation Pipeline

```
v7_narrator.py → _ai_cross_validate()
    │
    ├── Dopo generazione AI (OpenAI/Mistral) + hallucination check
    ├── validate_ai_output() chiama OpenAI (Mistral fallback)
    │     - Verifica accuratezza storica e scope temporale
    │     - Coerenza con claim dati
    │     - Allucinazioni non catturate dai check deterministici
    │
    ├── Risultato: valid/invalid + severity (minor/major/critical)
    │     valid → narrazione approvata con flags opzionali
    │     invalid + major → flags aggiunti al risultato
    │     invalid + critical → fallback a narrazione deterministica
    │
    └── Metadata salvato in GenerationInfo.ai_validation
```

### RAG Pipeline

```
rag_pipeline.py
    │
    ├── Hybrid retrieval: FTS5 + metadata filtering
    ├── Reranking: cross-encoder scoring
    ├── Context builder: [fonte: table#id] citations
    └── Output validation: no hallucinated URLs
```

---

## 7. API Endpoints (163 totali)

### Categorie principali

| Categoria | Endpoint count | Esempi |
|-----------|---------------|--------|
| Ricerca | 15 | `/api/search`, `/api/search/ww1`, `/api/conv-search` |
| V7 Pipeline | 5 | `/api/v7/health`, `/api/v7/research`, `/api/v7/narrate` |
| Eventi | 8 | `/api/events/{name}`, `/api/events/1gm/{name}` |
| Fonti Esterne | 12 | `/api/fonti-risorse`, `/api/lebi/search`, `/api/icrc/search` |
| Grafo | 3 | `/api/graph/entity/{table}/{id}`, `/api/graph/edges/{id}/review` |
| RAG | 2 | `/api/rag/retrieve`, `/api/rag/validate` |
| Mappe | 4 | `/api/map-features` (CRUD + review) |
| Riconoscimenti (RC) | 20+ | `/api/rc/candidates`, `/api/rc/assessments` |
| AI Runtime | 4 | `/api/ai-runtime` (health, config, benchmark) |
| Admin | 10 | `/api/admin/*` (source pipeline dashboard) |
| Fondi | 6 | `/api/fondi`, `/api/fondi/extract-all` |
| Decorati | 4 | `/api/decorati`, `/api/decorati/scrape` |
| Entità | 4 | `/api/entita`, `/api/entita/search` |
| AI Research | 4 | `/api/ai-research`, `/api/ai-web-search` |
| Download | 2 | `/api/download/{letter}`, `/api/download-all` |

---

## 8. Frontend

```
frontend/ (React + TypeScript + Vite)
    │
    ├── pages/
    │     EventsPage.tsx       — Eventi con tag conflitto/tipo
    │     GraphEntityPage.tsx  — Visualizzazione grafo (ForceGraph)
    │     DossierPage          — Dossier persona
    │     SearchPage           — Ricerca multi-fonte
    │
    ├── api/
    │     client.ts            — 15+ metodi API
    │     canonical-types.ts   — Tipi TypeScript (CanonicalEvent, GraphEntity, RAGContext)
    │
    └── components/
          ForceGraph.tsx       — Visualizzazione grafo interattivo
          EventTags           — Tag conflitto/event_type
          LeBITab             — Tab LeBI nel dossier
```

---

## 9. Sicurezza e Governance

### Kill Switches

| Switch | File | Stato |
|--------|------|-------|
| `LEGACY_JOB_LEGACY_EVENT_LINKS` | kill_switch.py | FROZEN |
| `SYNC_EVENT_LINKS_SUPABASE` | sync_ww1_to_supabase.py | OFF |

### Regole Enforced

1. **Raw data è immutabile** — correzioni sono overlay in `CorrectionLedger`
2. **Identity resolution è backend-only** — AI non decide identità
3. **Contraddizioni preservate** — `FusionEngine` non risolve conflitti
4. **Aggregate deterministiche** — AI non inventa definizioni
5. **Output AI validato** — URL hallucinated e fonti sconosciute flaggati
6. **Fallback deterministico sempre disponibile** — no dipendenza da AI
7. **Script legacy frozen** — kill switch previene esecuzione accidentale
8. **Derived data quarantined** — pronto per rigenerazione V7
9. **Data ufficiale = hard veto** — `TEMPORAL_VETO_OFFICIAL_DATE`
10. **Name-only match → needs_review** — mai verified senza 2° identificatore
11. **Web/unofficial non sovrascrive ufficiale** — lead only
12. **AI produce solo draft** — backend renderizza e computa metadati

---

## 10. Test Suite

| File | Test count | Coverage |
|------|-----------|----------|
| `test_v7_master.py` | 26 | Security, identity, fusion, narration, events, regression |
| `test_narration_v2_master.py` | 61 | Contract, selector, validator, narrator, regression, edge cases |
| `test_source_authority_master.py` | 33 | Source registry, temporal, homonyms, conflicts, migration |
| `test_linking_v2_master.py` | 46 | Temporal filter, keyword, decide(), migration, kill switch |
| `test_research_protocol_v4_master.py` | 82 | V4 snapshot, relevance, validation, fallback |
| `test_research_protocol_v3_master.py` | 149 | V3 regression + V4 compat |
| `test_research_engine_master.py` | — | Research engine, entity matching |
| `test_event_research_master.py` | — | Event research, narrative |
| `test_source_pipeline.py` | — | Source pipeline, admin dashboard |
| `test_v5_master.py` | — | V5 features |
| `test_v6_master.py` | — | V6 features |

---

## 11. Versioning

| Versione | Componente | Stato |
|----------|-----------|-------|
| 7.5-openai-primary | OpenAI primary for report generation, Mistral fallback, Ollama excluded | ATTIVO |
| 7.4-ollama-e2b | Ollama integration + AI cross-validation | SUPERSEDED |
| 7.3 | Structural Correction (quarantine, barriers, canonical) | ATTIVO |
| 7.2-narration-v2 | Narrator pipeline | ATTIVO |
| 7.2 | Evidence Snapshot | ATTIVO |
| 7.1 | Orchestrator | ATTIVO |
| 4.0 | Research Protocol | ATTIVO (legacy compat) |
| 3.0.0 | Source Authority | ATTIVO |
| 2.0 | Linking Schema | ATTIVO |
| 1.0.0 | Canonical Supabase Schema | DEPLOYED |

---

## 12. File System — Asset

```
imi_extractor/
├── imi_internati.db          (1.8 GB — SQLite principale)
├── eventi_1gm.db             (248 MB — SQLite eventi WW1)
├── research_conversations.db (212 KB — conversazioni)
├── validazioni_ai.db         (94 KB — validazioni AI)
├── pdfs/                     (20 file — PDF lettere IMI)
├── fondi_pdfs/               (48 file — PDF fondi SME)
├── frontend/                 (60 file — React/TS)
├── source_providers/         (15 file — provider federati)
├── linking/                  (14 file — linking V2)
├── sql/                      (9 file — migrazioni SQL)
├── docs/                     (33 file — documentazione)
├── templates/                (14 file — template HTML/JS)
├── config/                   (2 file — config provider)
├── source_cache/             (cache fonti esterne)
├── archivio_storage/         (storage archivio)
├── snapshots/                (snapshot V7)
├── artifacts/                (artefatti pipeline)
└── data/                     (dati ausiliari)
```
