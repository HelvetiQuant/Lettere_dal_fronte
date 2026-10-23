# Evidence Architecture Audit — IMI Extractor / Lettere dal Fronte

**Data**: 2026-08-17  
**Versione**: 1.0  
**Autore**: AI Architect  
**Stato**: AUDIT COMPLETATO — pronto per Fase 2

---

## 1. Schema DB Attuale

### 1.1 SQLite Locale (3 database)

#### imi_internati.db (1.8 GB, ~75 tabelle)

**Tabelle raw (dati primari)**:

| Tabella | Righe | Tipo | War Period |
|---------|-------|------|------------|
| `internati` | 20.465 | PERSON | WWII |
| `lebi_records` | 166.112 | PERSON | WWII |
| `caduti_albooro` | 342.555 | PERSON | WWI |
| `caduti_ministero` | 162.646 | PERSON | WWII |
| `caduti_cwgc` | 506.446 | PERSON | WWI/WWII |
| `decorati_nastroazzurro` | 279.832 | PERSON | Variabile |
| `decorati` | ~20K | PERSON | Variabile |
| `caduti_bologna` | ~12K | PERSON | WWI |
| `caduti_sardi` | ~30K | PERSON | WWI |
| `caduti_francia_ww1` | ~1.4M | PERSON | WWI |
| `fondi_archivistici` | ~5K | DOCUMENT | — |
| `menzioni` | ~50K | DOCUMENT | — |
| `archivio_documenti` | 979 | DOCUMENT | WWI |
| `fonti_risorse` | ~10K | SOURCE CATALOG | — |
| `fonti_narrative` | ~500 | SOURCE NARRATIVE | — |
| `lettere_personali` | ~2K | DOCUMENT | — |

**Tabelle legacy (derived, non probatorie)**:

| Tabella | Righe | Tipo | Problema |
|---------|-------|------|----------|
| `entita` | ~200K | ENTITY | Estrazione automatica senza provenance chain |
| `collegamenti` | ~500K | RELATION | Confidence universale 1.0, no evidence, no independence |
| `record_links` | ~1.7M | RELATION | Star topology, no evidence chain, quarantined parziale (V7.3) |
| `external_record_links` | ~10K | RELATION | Match score senza explainable scoring |
| `ai_ricerche` | ~1K | LOG | Storico ricerche AI |

**Tabelle V2 Linking (schema_v2.py — 16 tabelle)**:

| Tabella | Scopo | Stato |
|---------|-------|-------|
| `resource_registry` | Registry tipizzato risorse (person, event, source, ...) | ✅ Attivo |
| `historical_events` | Eventi canonici con conflict_code, parent_event_id | ✅ Attivo |
| `event_aliases_v2` | Alias eventi con specificity, ambiguity flag | ✅ Attivo |
| `source_artifacts` | Artefatti immutabili (SHA-256, storage locator) | ✅ Attivo |
| `ocr_observations` | Osservazioni OCR immutabili (append-only) | ✅ Attivo |
| `claims_v2` | Claim atomici con subject_resource_id, predicate, object_value | ✅ Attivo |
| `evidence_fragments` | Frammenti di evidence (page, char_start/end, quoted_fragment) | ✅ Attivo |
| `claim_evidence_v2` | Link claim ↔ evidence_fragments con support_type | ✅ Attivo |
| `review_decisions` | Decisioni umane append-only (confirm/reject/dispute) | ✅ Attivo |
| `source_families` | Famiglie di fonti (lineage tracking) | ✅ Attivo |
| `source_family_members` | Membri delle famiglie di fonti | ✅ Attivo |
| `relations` | Relazioni candidate/confirmed con features, raw_score, evidence_strength | ✅ Attivo |
| `relation_evidence` | Link relations ↔ evidence_fragments | ✅ Attivo |
| `pipeline_runs` | Run pipeline con algorithm_version, configuration_hash | ✅ Attivo |
| `legacy_relation_quarantine` | Legacy relations in quarantena | ✅ Attivo |
| `golden_dataset_labels` | Dataset etichettato per calibrazione | ✅ Attivo (8 casi seed) |

**Tabelle Graph (graph_schema.py — 5 tabelle)**:

| Tabella | Scopo | Stato |
|---------|-------|-------|
| `graph_nodes` | Nodi grafo canonico (namespace, type, label, source_table/id) | ✅ Attivo |
| `graph_edges` | Archi con status (candidate/confirmed/...), confidence, evidence_json | ✅ Attivo |
| `graph_edge_reviews` | Review umane archi | ✅ Attivo |
| `graph_pipeline_runs` | Run pipeline grafo | ✅ Attivo |
| `graph_integrity_issues` | Issue automatici (severity: info/warning/error) | ✅ Attivo |
| `archival_metadata` | Metadata archivistico estensione | ✅ Attivo |

**Tabelle V7 (in-memory, non persisted)**:

| Struttura | Scopo | Stato |
|-----------|-------|-------|
| `EvidenceSnapshotV7` | Snapshot immutabile con claims, evidence, identity, lineage | ⚠️ In-memory (`_runs` dict) — NON persistito su DB |
| `_runs` dict in `unified_orchestrator_v7.py` | Cache run recenti | ⚠️ Perso al restart del server |

**Tabelle Source Authority (source_authority_registry.py)**:

| Tabella | Scopo | Stato |
|---------|-------|-------|
| `source_authority_registry` | Registry fonti con authority_tier (1-4), verification_policy | ✅ Attivo |
| `source_policies` | Policy compliance per dominio | ✅ Attivo |
| `cross_link_audit` | Audit trail cross-linking (old_value, new_value, reverted) | ✅ Attivo |

#### eventi_1gm.db (248 MB)

| Tabella | Righe | Scopo | Problema |
|---------|-------|-------|----------|
| `eventi_1gm` | 49 | Eventi WW1 canonici | ✅ OK |
| `event_aliases` | ~161 | Alias eventi | ✅ OK |
| `event_links` | 1.539.685 | Link evento ↔ target | ⚠️ Legacy, no provenance, quarantined parziale |
| `map_features` | ~200 | Feature geografiche GeoJSON | ✅ OK |

#### validazioni_ai.db (94 KB)

| Tabella | Scopo |
|---------|-------|
| `validazioni_ai` | Log validazioni AI |

### 1.2 Supabase (PostgreSQL — 6 schemi)

```
public     ← Tabelle legacy migrate (compatibilità)
archive    ← Archivio documentale canonico (7 tabelle gerarchiche)
evidence   ← Quarantine link, rights assessments
ops        ← Discovery queries, job queue, fetch cache
ai         ← Datasets, versions, items, evaluation runs
api_public ← Viste pubbliche esposte via API
```

---

## 2. Dependency Map — Moduli che creano/modificano relazioni, claim, grafi

### 2.1 Moduli che creano relazioni

| Modulo | File | Tipo relazioni | Schema target |
|--------|------|----------------|---------------|
| **Linking V2 Pipeline** | `linking/cli.py` (34K) | `relations` (candidate/accepted/needs_review) | `relations` table |
| **Candidate Generation** | `linking/candidate_generation.py` (6.6K) | CandidatePair via blocking keys | In-memory → persistence |
| **Persistence** | `linking/persistence.py` (6.5K) | `upsert_relation()` con features, score | `relations` table |
| **Legacy Record Links** | `_gen_record_links.py` (10K) | `record_links` (star topology, pairwise) | `record_links` table |
| **Legacy Event Links** | `_gen_event_links.py` (11K) | `event_links` (keyword matching) | `event_links` table |
| **Legacy Event Links V3** | `_gen_event_links_v3.py` | `event_links` con V3 columns | `event_links` table |
| **Cross-Link Safe** | `cross_link_safe.py` | `cross_link_audit` + update `internati` | `internati` + `cross_link_audit` |
| **Cross-Link Military** | `cross_link_military_data_v3.py` | Cross-link caduti_ministero←albooro, internati←lebi | `internati`, `caduti_ministero` |
| **Entity Linker** | `linker.py` | `collegamenti` (entity ↔ record) | `collegamenti` table |
| **External Link Service** | `external_link_service.py` (13 matches) | `external_record_links` | `external_record_links` table |
| **Graph Service** | `graph_service.py` (884 righe) | `graph_edges` (read-through da 5 sistemi legacy) | `graph_edges` table |

### 2.2 Moduli che generano claim

| Modulo | File | Tipo claim | Schema target |
|--------|------|------------|---------------|
| **V7 Pipeline EXTRACT** | `person_source_schemas.py` (622 righe) | ClaimV7 con predicate, value_raw, value_normalized | `EvidenceSnapshotV7.person_claims` (in-memory) |
| **V7 Fusion Engine** | `v7_fusion_engine.py` (477 righe) | FusedClaims con status, confidence, evidence_ids | `EvidenceSnapshotV7.accepted_claims` (in-memory) |
| **Event Evidence Pipeline** | `event_evidence_pipeline.py` (1238 righe) | Claim da fonti eventi (date, luoghi, reparti) | `EvidencePackage.claims` (in-memory) |
| **Claims V2 Schema** | `linking/schema_v2.py` | `claims_v2` con subject_resource_id, predicate, object_value | `claims_v2` table |
| **Claim Service** | `claim_service.py` (if exists) | Claim V2 | `claims_v2` table |

### 2.3 Moduli che leggono collegamenti legacy

| Modulo | File | Tabelle legacy lette | Come vengono usate |
|--------|------|---------------------|-------------------|
| **Graph Service** | `graph_service.py` | `collegamenti`, `record_links`, `event_links`, `external_record_links` | Proiettate in `graph_edges` con status `to_review` per legacy |
| **Event Evidence Pipeline** | `event_evidence_pipeline.py` | `event_links` (fonte_archivistica, documento) | Fonti legacy → `verification_status="non_verificata"`, fallback dopo V2 |
| **Research Orchestrator** | `research_orchestrator.py` (1436 righe) | `record_links`, `event_links` | Ciclo agentico Plan→Retrieve→Extract→Resolve→Validate |
| **V7 Quarantine** | `v7_quarantine.py` (339 righe) | `record_links`, `event_links`, `collegamenti`, `graph_nodes`, `graph_edges` | Inventaria e quarantina (rename to `_quarantine_*`) |

### 2.4 Moduli che costruiscono grafi

| Modulo | File | Input | Output |
|--------|------|-------|--------|
| **Graph Service** | `graph_service.py` | 5 sistemi legacy + graph_edges | `GraphResponse` con nodi, archi, evidence, issues |
| **Graph Schema** | `graph_schema.py` | — | DDL per graph_nodes, graph_edges, reviews, pipeline_runs, integrity_issues |
| **V7 Fusion Engine** | `v7_fusion_engine.py` | SourceFamilyGraph | Source lineage groups, independence groups |

### 2.5 Moduli che alimentano report PERSON

| Modulo | File | Input | Output |
|--------|------|-------|--------|
| **V7 Narrator** | `v7_narrator.py` (1774 righe) | `EvidenceSnapshotV7` | Report markdown con citazioni, hallucination check |
| **V7 Orchestrator** | `unified_orchestrator_v7.py` | Query utente → 9-stage pipeline | `EvidenceSnapshotV7` + `NarrationResult` |
| **Narration Planner** | `narration_planner_v73.py` | Claims per identity cluster | ClaimSelector, CoveragePlanner |
| **Report Engine** | `report_engine.py` | Ricerca risultati | Report con citazioni fonti |

### 2.6 Moduli che alimentano report EVENT

| Modulo | File | Input | Output |
|--------|------|-------|--------|
| **Event Evidence Pipeline** | `event_evidence_pipeline.py` | Event name → 4-level evidence | `EvidencePackage` con sources, claims, concordances |
| **Event Narrative Builder** | `event_narrative_builder.py` (610 righe) | `EvidencePackage` | `NarrativeReport` con 13 sezioni |
| **Event Query Engine** | `event_query_engine.py` | Event query | Risultati con temporal filtering |

### 2.7 Moduli che alimentano risposte AI / contesto AI

| Modulo | File | Come entra nel prompt AI |
|--------|------|--------------------------|
| **V7 Narrator** | `v7_narrator.py` | Claims dal snapshot → system prompt evidence-locked |
| **V7 Follow-up** | `unified_orchestrator_v7.py:execute_followup()` | Snapshot claims + evidence → system prompt multi-turn |
| **AI Client** | `ai_client.py` (18.792 righe) | `call_ai()` e `call_ai_chat()` per multi-turn |
| **RAG Pipeline** | `rag_pipeline.py` (476 righe) | Retrieval FTS5 + semantic → context builder con citazioni |
| **Memory Router** | `memory_router.py` | Route query → layer di ricerca (LeBI, fonti, ecc.) |

---

## 3. Legacy Paths — Percorsi non probatori

### 3.1 Path: record_links → graph → report

```
record_links (1.7M righe, confidence=0.5-0.9, no evidence chain)
  ↓ graph_service.py: add_record_links()
graph_edges (status="to_review" per legacy, algorithm_version="legacy")
  ↓ graph_service.py: get_entity_network()
GraphResponse → frontend GraphEntityPage
  ↓ (utente vede relazioni legacy con status "to_review")
```

**Problema**: Le relazioni legacy appaiono nel grafo con status `to_review`, ma il frontend non filtra attivamente questo status. L'utente può vederle come se fossero valide.

### 3.2 Path: event_links → event_evidence_pipeline → report EVENT

```
event_links (1.5M righe, keyword matching, no provenance)
  ↓ event_evidence_pipeline.py: _internal_sources() line 266-278
fonti_indice (legacy_fonti_ids, verification_status="non_verificata")
  ↓ _extract_claims_from_sources()
Claim (senza evidence_ids, senza independence_group)
  ↓ event_narrative_builder.py
NarrativeReport (13 sezioni con citazioni)
```

**Problema**: I claim derivati da fonti legacy `event_links` entrano nel report EVENT senza evidence chain. La `verification_status="non_verificata"` è impostata ma non blocca l'inclusione nei claim.

### 3.3 Path: collegamenti → graph → AI context

```
collegamenti (~500K righe, confidence=1.0 default, no evidence)
  ↓ graph_service.py: add_entity_links() line 427-465
graph_edges (status="to_review" per collegamenti senza algorithm_version)
  ↓ GraphResponse → potenziale contesto AI
```

**Problema**: `collegamenti` ha `confidenza REAL DEFAULT 1.0` — confidence universale senza distinzione. Non c'è evidence chain.

### 3.4 Path: external_record_links → graph → report

```
external_record_links (~10K, match_score senza explainable scoring)
  ↓ graph_service.py: add_external_links() line 591-620
graph_edges (status="candidate")
  ↓ GraphResponse
```

**Problema**: `match_score` non è explainable. Non ci sono features salvate, né algorithm_version tracciata.

### 3.5 Path: search result → AI context (no evidence gate)

```
FederatedSearchContext → provider.search()
  ↓ risultati federati (metadata, snippet)
ai_client.py: call_ai() con contesto raw
  ↓ AI genera risposta basandosi su snippet/search results
```

**Problema**: I risultati di ricerca federata (snippet, metadata) possono entrare direttamente nel contesto AI senza essere qualificati come evidence. Non c'è un gate esplicito che separa retrieval da verification.

### 3.6 Path: V7 snapshot → AI (corretto ma non persistito)

```
EvidenceSnapshotV7 (in-memory, _runs dict)
  ↓ v7_narrator.py: NarratorV7
AI riceve claims con evidence_ids, provenance_chain
  ↓ OutputValidatorV7: hallucination check
Report ✅ (corretto)
  MA: snapshot perso al restart del server
```

**Problema**: Il path V7 è architetturalmente corretto (evidence-locked, provenance chain, hallucination check), ma gli snapshot non sono persistiti su DB. Non sono riproducibili dopo un restart.

---

## 4. Decision Paths — Come i dati entrano in claims/graph/report/AI

### 4.1 Path corretto (V7 Pipeline — PERSON_LOOKUP)

```
Query → PLAN → DISCOVER (5 tabelle) → FETCH → EXTRACT (person_source_schemas)
  → RESOLVE (IdentityResolver, cluster-based, homonym rejection)
  → FUSE (FusionEngine, PRESERVE_CONTRADICTIONS, independence groups)
  → VALIDATE (hallucination check, evidence hash)
  → NARRATE (AI evidence-locked o deterministic fallback)
  → PERSIST (EvidenceSnapshotV7 — in-memory only ⚠️)
```

**Stato**: ✅ Architetturalmente corretto, ⚠️ non persistito

### 4.2 Path legacy (EVENT_LOOKUP)

```
Query → event_resolver → _internal_sources()
  ├── V2 relations (source_describes_event) — preferred ✅
  ├── Legacy event_links → fonti_indice — fallback, "non_verificata" ⚠️
  └── Legacy event_links → archivio_documenti — ancora usato ⚠️
  → _extract_claims_from_sources() — claim senza evidence_ids ⚠️
  → _analyze_concordances()
  → event_narrative_builder.py → NarrativeReport
```

**Stato**: ⚠️ Misto V2/legacy, claim senza evidence chain

### 4.3 Path graph (tutti i lookup)

```
graph_service.py: get_entity_network()
  ├── graph_edges (V2, status=candidate/confirmed) ✅
  ├── collegamenti → "to_review" ⚠️
  ├── record_links → "to_review" ⚠️
  ├── event_links → "to_review" ⚠️
  └── external_record_links → "candidate" ⚠️
```

**Stato**: ⚠️ Legacy proiettato con status `to_review` ma non bloccato

---

## 5. Strutture Esistenti Riutilizzabili

### 5.1 Schema V2 (linking/schema_v2.py) — PARZIALMENTE ALLINEATO

| Tabella V2 | Corrispondenza Evidence Contract | Stato |
|------------|----------------------------------|-------|
| `resource_registry` | SOURCE (parziale) | ✅ Riutilizzabile |
| `source_artifacts` | SOURCE (artefatti immutabili) | ✅ Riutilizzabile |
| `ocr_observations` | OBSERVATION (parziale) | ✅ Estendibile |
| `evidence_fragments` | EVIDENCE (parziale) | ✅ Estendibile |
| `claims_v2` | CLAIM (parziale) | ⚠️ Mancano: temporal_context, geographic_context, support_score, conflict_status, verification_status estesi |
| `claim_evidence_v2` | EVIDENCE→CLAIM link | ✅ Riutilizzabile |
| `relations` | RELATION | ⚠️ Mancano: explainable scoring dettagliato, relation_evidence link effettivamente popolati |
| `relation_evidence` | RELATION→EVIDENCE link | ✅ Schema OK, ⚠️ non popolato |
| `source_families` | SOURCE LINEAGE | ✅ Riutilizzabile |
| `source_family_members` | SOURCE LINEAGE members | ✅ Riutilizzabile |
| `pipeline_runs` | PIPELINE RUN tracking | ✅ Riutilizzabile |
| `legacy_relation_quarantine` | LEGACY QUARANTINE | ✅ Riutilizzabile |
| `golden_dataset_labels` | GOLDEN DATASET | ✅ Riutilizzabile (8 casi, da espandere) |
| `review_decisions` | HUMAN REVIEW | ✅ Riutilizzabile |

### 5.2 EvidenceSnapshotV7 (evidence_snapshot_v7.py) — ALLINEATO

| Struttura V7 | Corrispondenza Evidence Contract | Stato |
|--------------|----------------------------------|-------|
| `ClaimV7` | CLAIM atomico | ✅ Ha: subject_id, predicate, value, evidence_ids, provenance_chain, status, identity_cluster_id |
| `EvidenceItemV7` | EVIDENCE | ✅ Ha: source_id, provider, locator, content_state, classification, is_independent |
| `SourceLineageGroup` | SOURCE LINEAGE | ✅ Ha: root_source_id, member_source_ids, lineage_type |
| `IndependenceGroup` | INDEPENDENCE | ✅ Ha: member_source_ids, independence_score, verified |
| `CorrectionLayer` | CORRECTION | ✅ Append-only con audit trail |
| `ContextClaimV7` | CONTEXT CLAIM | ✅ Separato da person_claims |
| `RejectedCandidateV7` | REJECTED CANDIDATE | ✅ Con reason_codes, classification |
| `WebLeadV7` | WEB LEAD (non evidence) | ✅ Separato da evidence |
| `ConditionalGapV7` | GAP | ✅ Con blocking flag |

### 5.3 Source Authority Registry (source_authority_registry.py) — ALLINEATO

| Struttura | Corrispondenza | Stato |
|-----------|----------------|-------|
| `SourceEntry` | SOURCE con authority_tier (1-4) | ✅ |
| `TemporalConstraint` | TEMPORAL GATE | ✅ Veto gate, non solo score |
| `LINK_STATES` | VERIFICATION STATUS | ⚠️ Mancano: UNSUPPORTED, PROBABLE, VERIFIED, DISPUTED (parzialmente presenti) |

### 5.4 Linking V2 Modules — ALLINEATI

| Modulo | Corrispondenza | Stato |
|--------|----------------|-------|
| `candidate_generation.py` | CANDIDATE GENERATION | ✅ Blocking keys, pairwise |
| `feature_extraction.py` | FEATURE EXTRACTION | ✅ Features + ConflictFlags con veto |
| `scoring.py` | EXPLAINABLE SCORING | ✅ raw_score, evidence_strength, conflict_flags, can_be_confirmed |
| `persistence.py` | PERSISTENCE | ✅ upsert_relation con features JSON, pipeline_run_id |
| `temporal_filter.py` | TEMPORAL HARD GATE | ✅ keyword classification, temporal_relation (overlap/conflict/unknown) |
| `golden_dataset.py` | GOLDEN DATASET | ✅ 8 casi seed, da espandere a 100-200 |

---

## 6. Rischi Identificati

### 6.1 Rischi critici

| # | Rischio | Modulo | Gravità | Impatto |
|---|---------|--------|---------|---------|
| R1 | **EvidenceSnapshotV7 non persistito** | `unified_orchestrator_v7.py` `_runs` dict | 🔴 ALTA | Snapshot perso al restart, non riproducibile, non verificabile |
| R2 | **Legacy event_links → claim senza evidence chain** | `event_evidence_pipeline.py:266-278` | 🔴 ALTA | Claim in report EVENT senza provenance verificabile |
| R3 | **collegamenti con confidence=1.0 default** | `database.py:175` | 🟡 MEDIA | Confidence universale senza distinzione |
| R4 | **Search results/snippet → AI context senza evidence gate** | `ai_client.py`, `memory_router.py` | 🟡 MEDIA | AI può usare snippet come se fossero evidence |
| R5 | **Graph frontend non filtra attivamente legacy** | `graph_service.py`, frontend | 🟡 MEDIA | Utente vede relazioni legacy come valide |
| R6 | **external_record_links senza explainable scoring** | `external_link_service.py` | 🟡 MEDIA | match_score non spiegabile |
| R7 | **Golden dataset troppo piccolo (8 casi)** | `linking/golden_dataset.py` | 🟡 MEDIA | Calibrazione non significativa |
| R8 | **relation_evidence non popolato** | `linking/persistence.py` | 🟡 MEDIA | Schema esiste ma nessun evidence link effettivo |

### 6.2 Rischi strutturali

| # | Rischio | Descrizione |
|---|---------|-------------|
| R9 | **Dual schema confusion** | V7 pipeline usa `EvidenceSnapshotV7` (in-memory), V2 linking usa `relations` + `claims_v2` (DB). Non c'è integrazione tra i due |
| R10 | **No source lineage in event pipeline** | `event_evidence_pipeline.py` non usa `source_families` per independence check |
| R11 | **No temporal hard gate in event pipeline** | Temporal check è feature, non gate (tranne in linking V2) |
| R12 | **No geographic authority layer** | Place matching basato su stringhe, no place_id canonico |
| R13 | **No event ontology gerarchica** | `historical_events` ha `parent_event_id` ma non popolato gerarchicamente |
| R14 | **No answer gate esplicito** | AI riceve claims dal snapshot ma non c'è un AnswerEvidenceBundle separato con verified/probable/disputed/unsupported |

---

## 7. Piano di Migrazione (10 fasi)

### FASE 1: Audit + schema compatibility ✅ (questo documento)

**Stato**: COMPLETATO

### FASE 2: Evidence Contract

**Obiettivo**: Definire un contratto centrale SOURCE→OBSERVATION→EVIDENCE→CLAIM→RELATION→ANSWER

**Azioni**:
1. Estendere `claims_v2` con: `temporal_context`, `geographic_context`, `support_score`, `conflict_status`, `verification_status` (UNSUPPORTED/CANDIDATE/SUPPORTED/PROBABLE/VERIFIED/CONTRADICTED/DISPUTED/REJECTED)
2. Estendere `evidence_fragments` con: `observation_type`, `field_name`, `extraction_method`, `extractor_version`
3. Creare `evidence_contract.py` con validatori e invarianti
4. Creare `docs/architecture/EVIDENCE_MODEL.md`

**Moduli**: `linking/schema_v2.py`, nuovo `evidence_contract.py`

### FASE 3: Source Lineage

**Obiettivo**: Implementare source lineage completo

**Azioni**:
1. Estendere `source_families` con: `origin_type` (independent/derived/republication/mirror/unknown), `authority_level`
2. Popolare `source_families` da `source_authority_registry` esistente
3. Integrare `SourceFamilyGraph` (v7_fusion_engine.py) con `source_families` DB
4. Implementare `independent_lineage_count` vs `evidence_count` in fusion engine
5. Creare `docs/architecture/SOURCE_LINEAGE.md`

**Moduli**: `linking/schema_v2.py`, `v7_fusion_engine.py`, `source_authority_registry.py`

### FASE 4: Legacy Quarantine

**Obiettivo**: Quarantena logica completa di record_links, event_links, collegamenti

**Azioni**:
1. Estendere `v7_quarantine.py` per marcare tutte le legacy relations con `origin=legacy`, `verification_status=unverified_legacy`
2. Creare `LegacyRelationAdapter` che espone vecchi link come candidate relation
3. Implementare pipeline: LEGACY → candidate → feature extraction → temporal/geographic/identity gate → accepted/needs_review/rejected
4. Bloccare legacy relations da: verified_sources, AI evidence context, dossier finale
5. Produrre statistiche: legacy_total, legacy_revalidated, legacy_rejected, legacy_needs_review
6. Creare `docs/migration/LEGACY_TO_V2.md`

**Moduli**: `v7_quarantine.py`, nuovo `legacy_relation_adapter.py`, `linking/persistence.py`

### FASE 5: AnswerEvidenceBundle

**Obiettivo**: Gate narrativo AI con bundle strutturato

**Azioni**:
1. Creare `AnswerEvidenceBundle` dataclass con: verified_claims, probable_claims, disputed_claims, unsupported_claims, sources, conflicts, gaps
2. Modificare `v7_narrator.py` per ricevere bundle invece di snapshot raw
3. Implementare prompt AI obbligatorio: VERIFIED→fatto, PROBABLE→probabilistico, DISPUTED→conflitto, UNSUPPORTED→non presentare
4. Estendere a `execute_followup` per conversational follow-up

**Moduli**: nuovo `answer_evidence_bundle.py`, `v7_narrator.py`, `unified_orchestrator_v7.py`

### FASE 6: EvidenceSnapshot Persistente

**Obiettivo**: Snapshot immutabile persistito su DB

**Azioni**:
1. Creare tabella `evidence_snapshots` su SQLite: id, query, intent, created_at, pipeline_version, source_ids JSON, observation_ids JSON, evidence_ids JSON, claim_ids JSON, relation_ids JSON, rejected_candidates JSON, conflicts JSON, context_hash, answer_hash
2. Modificare `unified_orchestrator_v7.py` per persistire snapshot dopo ogni run
3. Modificare `execute_followup` per recuperare snapshot da DB se non in memoria
4. Implementare TTL cleanup (24h)
5. Aggiungere `snapshot_id` a ogni risposta API

**Moduli**: `evidence_snapshot_v7.py`, `unified_orchestrator_v7.py`, `v7_api.py`

### FASE 7: Event Ontology Gerarchica

**Obiettivo**: Ristrutturare eventi in gerarchia WAR→THEATER→CAMPAIGN→BATTLE→SECTOR→ACTION

**Azioni**:
1. Popolare `historical_events.parent_event_id` con gerarchia
2. Aggiungere `event_type` (war/theater/campaign/battle/sector/action)
3. Aggiungere `participating_units`, `place_authority_ids`
4. Implementare relation types: present_in_theater, unit_present, participated, directly_documented, captured_during, killed_during, mentioned_in_event_source
5. Creare `docs/architecture/EVENT_ONTOLOGY.md`

**Moduli**: `linking/schema_v2.py`, `v7_event_aggregate.py`, nuovo `event_ontology.py`

### FASE 8: Migration Batch Legacy → V2

**Obiettivo**: Migrare legacy relations tramite pipeline V2

**Azioni**:
1. Eseguire `LegacyRelationAdapter` su tutte le tabelle legacy
2. Per ogni legacy relation: feature extraction → temporal gate → geographic gate → identity gate → evidence check → accepted/needs_review/rejected
3. Batch processing con checkpoint/resume
4. Statistiche finali: legacy_total, legacy_revalidated, legacy_rejected, legacy_needs_review, legacy_unprocessed
5. Deprecare linker legacy (read-only)

**Moduli**: `legacy_relation_adapter.py`, `linking/cli.py`, `linking/persistence.py`

### FASE 9: Frontend Graph States

**Obiettivo**: Frontend distingue chiaramente VERIFIED/PROBABLE/CANDIDATE/DISPUTED/LEGACY_UNVERIFIED/REJECTED

**Azioni**:
1. Aggiungere filtri status al frontend GraphEntityPage
2. Default: mostrare VERIFIED + PROBABLE
3. Legacy/candidate attivabili manualmente
4. Semantica grafica diversa per legacy vs verified
5. API `/api/relations/{id}/explain` per explainable scoring

**Moduli**: frontend `GraphEntityPage.tsx`, `graph_service.py`, `linking_v2_api.py`

### FASE 10: Golden Dataset + Regression Tests

**Obiettivo**: Espandere golden dataset e aggiungere regression test specifici

**Azioni**:
1. Espandere golden dataset a 100-200 casi PERSON + 50 casi EVENT
2. Includere: omonimi, date incompatibili, luoghi omonimi, reparti incompatibili, fonti derivate, documenti retrospettivi, WWI vs WWII, falsi positivi
3. Implementare TEST A-L (12 regression test specifici)
4. Metriche: precision, recall, FPR, FNR, unsupported claim rate, wrong-era contamination, legacy leakage rate
5. Creare `docs/testing/GOLDEN_DATASET.md`
6. Creare `audit_evidence_integrity.py` con exit code != 0 per violazioni critiche

**Moduli**: `linking/golden_dataset.py`, nuovo `test_evidence_regression.py`, nuovo `audit_evidence_integrity.py`

---

## 8. Mappa Moduli → Fasi

| Fase | Moduli nuovi | Moduli modificati | Documenti |
|------|-------------|-------------------|-----------|
| 1 | — | — | Questo documento |
| 2 | `evidence_contract.py` | `linking/schema_v2.py` | `EVIDENCE_MODEL.md` |
| 3 | — | `v7_fusion_engine.py`, `source_authority_registry.py` | `SOURCE_LINEAGE.md` |
| 4 | `legacy_relation_adapter.py` | `v7_quarantine.py`, `linking/persistence.py` | `LEGACY_TO_V2.md` |
| 5 | `answer_evidence_bundle.py` | `v7_narrator.py`, `unified_orchestrator_v7.py` | — |
| 6 | — | `evidence_snapshot_v7.py`, `unified_orchestrator_v7.py`, `v7_api.py` | — |
| 7 | `event_ontology.py` | `linking/schema_v2.py`, `v7_event_aggregate.py` | `EVENT_ONTOLOGY.md` |
| 8 | — | `legacy_relation_adapter.py`, `linking/cli.py` | — |
| 9 | — | frontend, `graph_service.py`, `linking_v2_api.py` | — |
| 10 | `test_evidence_regression.py`, `audit_evidence_integrity.py` | `linking/golden_dataset.py` | `GOLDEN_DATASET.md` |

---

## 9. Segreti e Sicurezza

**Verifica `.gitignore`**: ✅ `.env`, `*.env` ignorati  
**Verifica `git ls-files`**: ✅ Nessun file `.env` tracciato  
**Verifica codice**: ✅ Nessuna API key hardcoded (tutte da `os.environ`)  
**Verifica `.env.example`**: ✅ Placeholder only (`sk-...`, `sb_publishable_...`)  
**Verifica log**: ✅ Nessuna key loggata nei moduli auditati  
**Verifica API responses**: ✅ Nessuna key restituita negli endpoint  

**Raccomandazione**: Ruotare eventuali chiavi esposte in commit precedenti (verifica cronologia GitHub con `git log --all -p -- '*.env'`).

---

## 10. Conclusioni

### Stato attuale

Il sistema ha già una struttura V2/V7 architetturalmente allineata al modello evidence-centric:

- ✅ **Schema V2** (16 tabelle) con resource_registry, claims_v2, evidence_fragments, relations, source_families
- ✅ **EvidenceSnapshotV7** con ClaimV7, EvidenceItemV7, SourceLineageGroup, IndependenceGroup
- ✅ **Linking V2 pipeline** con candidate generation, feature extraction, scoring, persistence
- ✅ **Source Authority Registry** con authority tiers e temporal veto gates
- ✅ **V7 Narrator** evidence-locked con hallucination check
- ✅ **Legacy quarantine** parziale (record_links V7.3, v7_quarantine.py)

### Gap principali

1. **EvidenceSnapshotV7 non persistito** (R1) — priorità #1
2. **Legacy event_links ancora in pipeline EVENT** (R2) — richiede LegacyRelationAdapter
3. **Dual schema V7/V2 non integrato** (R9) — richiede evidence contract unificante
4. **No AnswerEvidenceBundle esplicito** (R14) — AI riceve snapshot raw
5. **Golden dataset troppo piccolo** (R7) — 8 casi vs 100-200 target
6. **No event ontology gerarchica** (R13) — parent_event_id non popolato
7. **No geographic authority layer** (R12) — place matching su stringhe

### Principio guida

> Il sistema non deve essere progettato per trovare il maggior numero possibile di collegamenti.
> Deve essere progettato per trovare, verificare, spiegare e conservare il maggior numero possibile di collegamenti STORICAMENTE DIFENDIBILI.
>
> **Precision first. Provenance always. No silent inference. No legacy shortcut to truth.**

---

*Audit completato 2026-08-17 — pronto per Fase 2: Evidence Contract*
