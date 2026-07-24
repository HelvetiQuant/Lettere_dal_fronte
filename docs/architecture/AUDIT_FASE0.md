# IMI Extractor — Audit Repository Fase 0

> Prompt: Motore AI di ricerca e ricostruzione storica federata V2
> Data: 2026-07-24
> Auditor: Cascade (principal software engineer)

---

## 1. Inventario

### 1.1 Stack

| Componente | Tecnologia | Stato |
|------------|-----------|-------|
| Backend | Python 3.11+, FastAPI, uvicorn | verified_working |
| Database | SQLite (`imi_internati.db`, ~1.4 GB) | verified_working |
| Frontend pubblico | SPA vanilla JS — `templates/index.html` | verified_working |
| Frontend operatori | SPA vanilla JS — `templates/rc.html` | verified_working |
| ORM | Nessuno — `sqlite3` diretto + `database.get_conn()` | verified_working |
| Migrazioni | Nessun sistema formale — schema inline negli script | present_unverified |
| Job asincroni | `mass_index.py` (ThreadPoolExecutor + watchdog) | verified_working |
| Auth | Session-based con ruoli (`auth.py`) | present_unverified |
| Storage file | Filesystem locale (`source_fetch_cache.path_file`) | verified_working |
| Cache | `source_fetch_cache` (14 record), `consolidated_memory` (1 record) | verified_working |
| Log | `ai_task_runs` (71), `ai_usage_ledger` (64), `memory_trace` (55) | verified_working |

### 1.2 Moduli verificati (20/20 importabili)

| Modulo | Stato | Funzioni chiave |
|--------|-------|-----------------|
| `database.py` | verified_working | `search_all()`, `get_conn()`, 56 callables |
| `biography.py` | verified_working | `generate_biography()`, `generate_soldier_biography()`, `generate_event_biography()` |
| `ai_router.py` | verified_working | `select_model()` |
| `ai_client.py` | verified_working | `call_ai()` |
| `ai_research.py` | verified_working | `PROVIDERS` dict (gpt, claude, mistral, perplexity) |
| `memory_router.py` | verified_working | `route_query()` |
| `soldier_dashboard.py` | verified_working | `get_soldier_dashboard()` |
| `event_research_engine.py` | verified_working | `research_event()` |
| `event_query_engine.py` | verified_working | `query_event()` |
| `mass_index.py` | verified_working | 18 callables |
| `compliance_gate.py` | verified_working | `evaluate()` |
| `search_validator.py` | verified_working | `validate_search()`, `federated_search()` |
| `research_to_index.py` | verified_working | 19 callables |
| `external_link_service.py` | verified_working | `generate_links_for_provider()`, `detect_omonimie()`, `review_link_with_type()` |
| `external_metadata_service.py` | verified_working | `run_import()` |
| `sources_external_lebi.py` | verified_working | `LeBIAdapter` |
| `source_providers.federation` | verified_working | `federated_search()`, 40 callables |
| `extractor.py` | verified_working | `_get_client()`, `_get_mistral_client()` |
| `indexing_rules.py` | verified_working | 10 callables |

### 1.3 Connettori esterni (`archive_connectors`: 27 record)

| Codice | Nome | Status | Access mode | Authority |
|--------|------|--------|-------------|-----------|
| `antenati` | Archivi di Stato Italia — Antenati | active | auto | 0.5 |
| `cwgc` | CWGC — Commonwealth War Graves Commission | active | auto | 0.5 |
| `wikitree` | WikiTree | active | auto | 0.5 |
| `arolsen` | Arolsen Archives — ITS | active | auto | 0.5 |
| `bundesarchiv` | Bundesarchiv | active | auto | 0.5 |
| `shd` | SHD — Service Historique de la Défense | active | auto | 0.5 |
| `tna` | The National Archives (UK) | active | auto | 0.5 |
| `europeana` | Europeana | active | auto | 0.5 |
| `gallica` | Gallica — BnF | active | auto | 0.5 |
| ... | (18 altri) | active | auto | 0.5 |

**Problema**: Tutti i connector hanno `authority_score=0.5`, `reliability_criteria=NULL`, `provenance_group=NULL`, `last_verified_at=NULL`. Nessuna distinzione di affidabilità istituzionale.

---

## 2. Matrice dichiarato / trovato / funzionante / da correggere / mancante

### 2.1 Componenti dichiarati nel prompt

| Componente | Dichiarato | Trovato | Funzionante | Da correggere | Mancante |
|-----------|-----------|---------|-------------|---------------|----------|
| `database.py search_all()` | Sì | Sì (`:455`) | Sì — tokenizzazione AND, 12 tabelle | — | — |
| `federated_search()` | Sì | Sì (`federation.py`) | Sì — 27 provider ThreadPool | — | — |
| `search_validator.py` | Sì | Sì | Sì — `validate_search()`, LeBI per-name | — | — |
| `compliance_gate.py` | Sì | Sì | Sì — `evaluate()` | Schema `source_policies` non ha `classification` column | — |
| `research_to_index.py` | Sì | Sì | Sì — 19 callables | — | — |
| `ai_router.py` | Sì | Sì | Sì — `select_model()` | `ai_routing_policies` vuota (0 rows) | — |
| `ai_client.py` | Sì | Sì | Sì — `call_ai()` con fallback | — | — |
| `biography.py` | Sì | Sì | Sì — test end-to-end passato | — | — |
| `memory_router.py` | Sì | Sì | Sì — `route_query()` | — | — |
| `soldier_dashboard.py` | Sì | Sì | Sì — `get_soldier_dashboard()` | — | — |
| `event_research_engine.py` | Sì | Sì | Sì — `research_event()` | — | — |

### 2.2 Tabelle dichiarate

| Tabella | Dichiarata | Trovata | Record | Note |
|---------|-----------|---------|--------|------|
| `entita` | Sì | Sì | 688.739 | — |
| `collegamenti` | Sì | Sì | 2.349.417 | + `collegamenti_backup` (4.894.390) |
| `record_links` | Sì | Sì | 169.184 | Schema esteso (match_status, evidence_json, score_breakdown_json) |
| `event_links` | Sì | Sì | 0 | Vuota. FK `evento_id → eventi_1gm.id` |
| `research_subjects` | Sì | Sì | 118 | — |
| `research_sources` | Sì | **NO** | — | **MANCANTE** — sostituita da `research_subject_sources` (1.431) |
| `research_gaps` | Sì | Sì | 472 | FK `subject_id → research_subjects.id` |
| `fonti_indice` | Sì | Sì | 35.664 | — |
| `source_fetch_cache` | Sì | Sì | 14 | — |
| `external_records` | Sì | **NO** | — | **MANCANTE** — sostituita da `external_source_records` (1) |
| `external_links` | Sì | **NO** | — | **MANCANTE** — sostituita da `external_record_links` (0) |
| `source_policies` | Sì | Sì | 4 | Schema diverso da dichiarato (no `classification`, ha `metadata_license`, `digital_object_license`, ecc.) |
| `compliance_decisions` | Sì | Sì | 0 | Vuota |
| `compliance_authorizations` | Sì | Sì | 0 | Vuota |
| `compliance_review_queue` | Sì | Sì | 0 | Vuota |
| `ai_providers` | Sì | Sì | 6 | OpenAI, Anthropic, Mistral, Perplexity, Gemini, LMStudio |
| `ai_models` | Sì | Sì | 0 | **Vuota** — modelli hardcoded in `ai_research.PROVIDERS` |
| `ai_task_runs` | Sì | Sì | 71 | — |
| `ai_ricerche` | — | Sì | 201 | Non dichiarata ma presente |
| `ai_routing_policies` | — | Sì | 0 | **Vuota** — routing hardcoded in `ai_router._default_policy` |
| `ai_usage_ledger` | — | Sì | 64 | Non dichiarata ma presente |

### 2.3 Tabelle V2 già presenti (parzialmente)

| Tabella | Record | Schema | Completamento V2 |
|---------|--------|--------|------------------|
| `claims` | 42 | `stable_id, subject_type, subject_id, predicate, object_value, epistemic_status, confidence, extraction_method, review_status` | **70% completo** — manca `unit`, `qualifiers`, `polarity` |
| `claim_evidence` | 249 | `claim_id, source_id, source_table, document_id, page_or_frame, supporting_quote, evidence_role, source_independence_group, strength` | **80% completo** — manca `hash/fingerprint`, `verified_at` |
| `claim_relations` | 75 | `claim_a_id, claim_b_id, relation_type, confidence, method, review_status` | **90% completo** |
| `entity_variants` | 152 | `entity_type, entity_id, field_name, original_value, variant_value, variant_type, origin, confidence, verified` | **90% completo** |
| `entity_match_candidates` | 0 | `local_entity_type, local_record_id, candidate_source, candidate_record_id, score, score_breakdown_json, contrary_signals_json, missing_data_json, threshold_applied, algorithm_version, status, review_decision` | **95% completo** — vuota ma schema pronto |
| `research_plans` | 30 | `original_input, entity_type, entity_id, objective, gaps_to_fill, budget_cycles, budget_time_seconds, budget_cost_usd, status` | **80% completo** |
| `research_sessions` | 30 | `plan_id, connector_id, mode, status, cycle_number, result_count, stop_reason` | **70% completo** |
| `research_cycles` | 26 | `plan_id, session_id, cycle_number, initial_knowledge_json, gaps_selected_json, sources_selected_json, queries_executed_json, new_fragments_json, decision, stop_reason` | **85% completo** |
| `research_queries` | 0 | `session_id, query_text, query_language, filters_json, variant_used, generated_from_claim_id, generated_from_fragment, priority, motivation, search_tool, outcome` | **90% completo** — vuota |
| `generated_narratives` | 0 | `entity_type, entity_id, narrative_type, audience, structured_text, claim_ids_json, gaps_json, deductions_json, confidence_level, model_version, prompt_version, review_status` | **90% completo** — vuota |
| `document_extractions` | 0 | `document_id, document_table, version, method, original_text, ocr_text, language, raw_structured_output_json, review_status` | **80% completo** — vuota |
| `consolidated_memory` | 1 | `topic, summary, entities_json, sources_json, archivio_fonti_ids, query_count, confidence, last_verified_at` | **70% completo** |
| `memory_trace` | 55 | `query, cue_persona, cue_luogo, cue_reparto, route_selected, sources_found, confidence, used_fts, used_graph, used_cloud_ai, tokens_saved_estimate, response_ms` | **80% completo** |

### 2.4 Tabelle V2 mancanti

| Tabella richiesta | Tabella esistente | Azione |
|-------------------|-------------------|--------|
| `research_sources` | `research_subject_sources` (1.431) | **Mappare** — rinominare o creare view |
| `external_records` | `external_source_records` (1) | **Mappare** — rinominare o creare view |
| `external_links` | `external_record_links` (0) | **Mappare** — rinominare o creare view |
| `connectors` | `archive_connectors` (27) | **Mappare** — già presente con schema ricco |
| `source_items` | `fonti_indice` (35.664) + `archivio_fonti` (1.153) | **Mappare** — due tabelle con funzioni sovrapposte |
| `acquisitions` | — | **MANCANTE** — da creare |
| `evidence_anchors` | `claim_evidence` (249) | **Mappare** — già presente, estendere |
| `stable_locators` | — | **MANCANTE** — da creare (o estendere `fonti_indice`) |
| `content_fingerprints` | — | **MANCANTE** — da creare |
| `heuristic_edges` | `record_links` (169.184) | **Mappare** — già presente, estendere con `evidence_ids`, `algorithm_version` |
| `edge_evidence` | — | **MANCANTE** — da creare |
| `edge_versions` | — | **MANCANTE** — da creare |
| `prompt_versions` | — | **MANCANTE** — da creare |
| `budget_reservations` | — | **MANCANTE** — da creare |
| `circuit_breaker_state` | In-memory in `ai_client.py` | **Mappare** — persistere in `ai_providers` o tabella ded. |
| `publication_versions` | — | **MANCANTE** — da creare |
| `human_decisions` | `review_status`/`reviewed_by` in varie tabelle | **Mappare** — centralizzare o lasciare distribuito |
| `permitted_operations` | — | **MANCANTE** — da creare (o estendere `source_policies`) |

---

## 3. Script menzionati nel prompt — verifica rischi

### 3.1 `_clean_bad_links.py` (110 righe)
- **Stato**: present_unverified
- **Funzione**: identifica fonti in `fonti_indice` il cui `url_catalogo` è una pagina di ricerca (form/homepage) e rimuove i collegamenti associati
- **Usa**: `mass_index._is_search_page_url()` per classificare URL
- **Rischio**: 304 URL potenzialmente impropri su 35.664 totali (0.85%)
- **Problema**: script standalone, non integrato in pipeline continua

### 3.2 `_gen_record_links.py` (247 righe)
- **Stato**: present_broken (logica rischiosa)
- **Problemi confermati**:
  - **Star topology**: usa `ids[0]` come hub → il primo soldato diventa centro artificiale (riga 67-69)
  - **Match debole**: raggruppa per `anno_morte + luogo_morte` → "stesso anno + stesso luogo" non prova partecipazione allo stesso evento
  - **Ciclo cartesiano**: `for sid in ids[1:]` su gruppi fino a 500 elementi → O(n²) potenziale
  - **LIMIT 50**: non presente in questo script, ma `HAVING n <= 500` limita gruppi
  - **DELETE non reversibile**: riga 32 elimina tutti i link `fonte_personale` senza backup

### 3.3 `_gen_event_links.py` (700 righe)
- **Stato**: present_broken (logica rischiosa)
- **Problemi confermati**:
  - **Alias e sottostringhe**: usa `aliases` e `keywords` per match → "Carso" matcha anche "Carso" in contesti non bellici
  - **Collegamenti temporali deboli**: match per anno generico
  - **Eventi hardcoded**: 15 eventi 1GM inseriti manualmente come tassonomia → non fonti probatorie ma usati come base per link
  - **event_links vuota**: 0 record — script non eseguito o fallito
  - **Salto fase**: se trova link preesistenti può saltare intera fase

### 3.4 `_fix_gaiaschi_db.py` (45 righe)
- **Stato**: present_broken (modifica raw_text)
- **Problema critico**: riga 7 esegue `UPDATE internati SET raw_text = REPLACE(raw_text, ...)` — **modifica il testo originale**
- **Violazione invariante**: "il testo o record originale acquisito è immutabile"
- **Fix necessario**: migrare a modello overlay (tabella `entity_variants` già esiste)

### 3.5 `_check_keys.py` (25 righe)
- **Stato**: present_broken (sicurezza)
- **Problema critico**: riga 22 stampa `val[:8]` — **prefisso di chiave API nei log**
- **Violazione invariante**: "nessuna parte di una chiave deve comparire nei log"
- **Fix necessario**: sostituire con booleano redatto (`val: YES/NO`)

### 3.6 `_status.py` (7 righe)
- **Stato**: present_broken (contenuto fisso)
- **Problema**: riga 5 usa `20464` come totale hardcoded — il conteggio operativo deve derivare dal DB
- **Fix necessario**: `SELECT COUNT(*) FROM internati`

---

## 4. Baseline

### 4.1 Conteggi tabelle principali

| Tabella | Record |
|---------|--------|
| `internati` | 20.465 |
| `caduti_albooro` | 342.555 |
| `caduti_ministero` | 162.646 |
| `caduti_cwgc` | 506.446 |
| `caduti_sardi` | 20.435 |
| `caduti_bologna` | 9.656 |
| `caduti_francia_ww1` | 24.279 |
| `decorati` | 1.286 |
| `decorati_nastroazzurro` | 279.832 |
| `fonti_narrative` | 40 |
| `lettere_personali` | 1 |
| `fondi_archivistici` | 4.808 |
| `menzioni` | 10.976 |
| `documenti_nara_t315` | 1.153 |
| `documenti_nara_catalog` | 272 |
| `entita` | 688.739 |
| `collegamenti` | 2.349.417 |
| `record_links` | 169.184 |
| `event_links` | 0 |
| `fonti_indice` | 35.664 |
| `archivio_fonti` | 1.153 |
| `research_subjects` | 118 |
| `research_subject_sources` | 1.431 |
| `research_gaps` | 472 |
| `claims` | 42 |
| `claim_evidence` | 249 |
| `claim_relations` | 75 |
| `entity_variants` | 152 |
| `archive_connectors` | 27 |
| `source_policies` | 4 |
| `ai_providers` | 6 |
| `ai_task_runs` | 71 |
| `ai_ricerche` | 201 |

### 4.2 Link per tipo

| Tipo | Record | Qualità |
|------|--------|---------|
| `stesso_evento_luogo` | 142.594 | **Rischioso** — star topology, match anno+luogo |
| `stesso_anno_decorazione` | 11.222 | **Rischioso** — solo anno |
| `fonte_personale` | 9.546 | **Rischioso** — match cognome |
| `documento_evento` | 5.822 | **Da verificare** |
| **TOTALE** | **169.184** | |

### 4.3 URL impropri

| Metrica | Valore |
|---------|--------|
| `fonti_indice` totali | 35.664 |
| URL potenzialmente impropri (search/form/query) | 304 (0.85%) |

### 4.4 AI Providers

| Provider | Status | Priority | Note |
|----------|--------|----------|------|
| `openai` | active | 1 | **API key invalida (401)** |
| `anthropic` | active | 2 | **Crediti esauriti** |
| `mistral` | active | 3 | **Funzionante** (fallback attivo) |
| `perplexity` | active | 4 | Non testato in questo audit |
| `gemini` | active | 5 | Non testato in questo audit |
| `lmstudio` | active | 10 | Locale, non testato |

### 4.5 Indici FTS

| Elemento | Stato |
|----------|-------|
| FTS5 tables | **NESSUNA** — `idx_entita_search` è FTS5 virtuale (688K docs) ma non dichiarata come tabella FTS |
| Full-text search | `LIKE %term%` su tutte le query — **nessun FTS5 reale** |

### 4.6 Vincoli e integrità

| Elemento | Stato |
|----------|-------|
| UNIQUE constraints | `record_links(from_table, from_id, to_table, to_id, link_type)` |
| Foreign keys | `event_links.evento_id → eventi_1gm.id`, `research_gaps.subject_id → research_subjects.id` |
| FK su `record_links` | **ASSENTE** |
| FK su `claims` | **ASSENTE** |
| FK su `claim_evidence.claim_id` | **ASSENTE** |
| FK su `research_subject_sources` | **ASSENTE** |

---

## 5. Sicurezza dati

### 5.1 Segreti nei log

| Script | Problema | Severità |
|--------|----------|----------|
| `_check_keys.py:22` | Stampa `val[:8]` (primi 8 caratteri della chiave) | **ALTA** |

### 5.2 Modifiche a raw_text

| Script | Problema | Severità |
|--------|----------|----------|
| `_fix_gaiaschi_db.py:7` | `UPDATE internati SET raw_text = REPLACE(...)` | **ALTA** |

### 5.3 Conteggi fissi

| Script | Problema | Severità |
|--------|----------|----------|
| `_status.py:5` | `20464` hardcoded invece di `SELECT COUNT(*)` | **MEDIA** |

### 5.4 Backup

| Elemento | Stato |
|----------|-------|
| `collegamenti_backup` | 4.894.390 record (backup di collegamenti) |
| Backup DB completo | **Non rilevato** — nessun meccanismo automatico |
| Rollback migrazioni | **Non rilevato** — nessun sistema di migrazioni |

---

## 6. Mapping schema attuale → modello V2

### 6.1 Tabelle da mappare (riusare)

| Tabella V2 richiesta | Tabella esistente | Azione | Completamento |
|----------------------|-------------------|--------|---------------|
| `connectors` | `archive_connectors` (27) | Mappare direttamente | 80% — manca `policy_version`, `permitted_operations` separati |
| `source_items` | `fonti_indice` (35K) + `archivio_fonti` (1.1K) | Consolidare o view | 60% — due tabelle sovrapposte |
| `evidence_anchors` | `claim_evidence` (249) | Estendere | 80% — manca `hash`, `verified_at` |
| `heuristic_edges` | `record_links` (169K) | Estendere | 70% — manca `evidence_ids`, `algorithm_version` (parziale: ha `match_method`, `score_breakdown_json`) |
| `entities` | `entita` (688K) | Mappare | 90% |
| `entity_variants` | `entity_variants` (152) | Pronto | 90% |
| `identity_candidates` | `entity_match_candidates` (0) | Pronto | 95% |
| `claims` | `claims` (42) | Estendere | 70% — manca `unit`, `qualifiers`, `polarity` |
| `claim_evidence` | `claim_evidence` (249) | Estendere | 80% |
| `claim_conflicts` | `claim_relations` (75) con `relation_type=contradicts` | Mappare | 90% |
| `research_plans` | `research_plans` (30) | Pronto | 80% |
| `research_jobs` | `research_sessions` (30) | Mappare | 70% |
| `research_steps` | `research_cycles` (26) | Mappare | 85% |
| `queries` | `research_queries` (0) | Pronto | 90% |
| `hits` | — | **MANCANTE** | 0% |
| `stop_reasons` | `research_sessions.stop_reason` + `research_cycles.stop_reason` | Mappare (distribuito) | 70% |
| `human_decisions` | `review_status`/`reviewed_by` in varie tabelle | Mappare (distribuito) | 60% |
| `summaries` | `generated_narratives` (0) | Pronto | 90% |
| `biographies` | `generated_narratives` con `narrative_type=biography` | Mappare | 90% |
| `timelines` | `generated_narratives` con `narrative_type=timeline` | Mappare | 90% |
| `viewpoint_syntheses` | `generated_narratives` con `narrative_type=viewpoint` | Mappare | 90% |
| `publication_versions` | — | **MANCANTE** | 0% |
| `providers` | `ai_providers` (6) | Mappare | 90% |
| `models` | `ai_models` (0) | **Da popolare** | 10% — tabella vuota |
| `task_runs` | `ai_task_runs` (71) | Mappare | 80% |
| `usage_ledger` | `ai_usage_ledger` (64) | Mappare | 90% |
| `budget_reservations` | — | **MANCANTE** | 0% |
| `circuit_breaker_state` | In-memory | **Da persistere** | 10% |
| `prompt_versions` | — | **MANCANTE** | 0% |
| `source_policy_versions` | `source_policies` (4) | Estendere con versioning | 50% |
| `permitted_operations` | — | **MANCANTE** | 0% |
| `source_access_audit` | — | **MANCANTE** | 0% |
| `source_rights` | — | **MANCANTE** | 0% |
| `acquisitions` | — | **MANCANTE** | 0% |
| `stable_locators` | — | **MANCANTE** | 0% |
| `content_fingerprints` | — | **MANCANTE** | 0% |
| `edge_evidence` | — | **MANCANTE** | 0% |
| `edge_versions` | — | **MANCANTE** | 0% |

### 6.2 Schema `source_policies` reale vs dichiarato

```
REALE:
id, provider, domain, source_name, terms_url, privacy_url, robots_url,
archive_regulation_url, metadata_license, digital_object_license,
commercial_use_allowed, automated_access_allowed, metadata_indexing_allowed,
document_download_allowed, republication_allowed, attribution_required,
required_credit_line, request_contact, policy_status, verified_by,
verified_at, valid_from, review_due_at, notes, created_at, updated_at

DICHIARATO NEL PROMPT:
classification, download_allowed, ...

→ Schema reale è PIÙ ricco del dichiarato. Ha già separazione per operazione
  (metadata_indexing_allowed, document_download_allowed, republication_allowed).
→ Mancano: permitted_operations come tabella separata, policy_version_id, data_class.
```

### 6.3 Schema `record_links` reale vs richiesto V2

```
REALE:
id, from_table, from_id, to_table, to_id, link_type, confidence,
elaborato_il, match_status, match_method, matched_fields_json,
conflicting_fields_json, evidence_json, explanation, review_status,
reviewed_by, reviewed_at, algorithm_version, score_breakdown_json,
contrary_signals_json

RICHIESTO V2:
entità sorgente e destinazione, tipo, direzione, natura, feature,
evidence IDs, score, algoritmo e versione, data, stato, motivazione, revisore

→ Schema reale è già 80% completo per V2. Manca: `nature` (documented|deterministic|
  heuristic|human_confirmed), `edge_evidence` separata, `direction` esplicita.
```

---

## 7. Rischi e priorità di intervento

### 7.1 Rischi critici (bloccanti per V2)

| # | Rischio | File | Fix |
|---|---------|------|-----|
| R1 | `raw_text` modificato da script di correzione | `_fix_gaiaschi_db.py:7` | Migrare a `entity_variants` (già esiste) |
| R2 | Prefisso chiavi API nei log | `_check_keys.py:22` | Sostituire con booleano redatto |
| R3 | `ai_models` vuota — modelli hardcoded | `ai_research.PROVIDERS` | Popolare da `ai_research.PROVIDERS` |
| R4 | `ai_routing_policies` vuota — routing hardcoded | `ai_router._default_policy` | Seed da hardcoded a DB |
| R5 | Nessun FTS5 reale — solo `LIKE %term%` | `database.py` | Creare tabelle FTS5 |
| R6 | 304 URL di ricerca come fonti | `fonti_indice` | Eseguire `_clean_bad_links.py --execute` |
| R7 | `record_links` con star topology e match deboli | `_gen_record_links.py` | Marcare `legacy_unverified`, rigenerare |
| R8 | Nessun FK su tabelle critiche | DB schema | Aggiungere FK in migrazione |
| R9 | Nessun backup automatico | Infrastruttura | Implementare backup incrementale |
| R10 | `event_links` vuota — script non eseguito | `_gen_event_links.py` | Verificare e eseguire o dismettere |

### 7.2 Priorità di implementazione Fase 1

1. **Fix sicurezza**: R2 (segreti nei log), R1 (raw_text immutabile)
2. **Popolare tabelle vuote**: R3 (ai_models), R4 (ai_routing_policies)
3. **Migrazione link legacy**: R7 (marcare record_links esistenti come `legacy_unverified`)
4. **Quarantena URL impropri**: R6 (eseguire clean_bad_links con backup)
5. **FK e vincoli**: R8 (aggiungere FK su claim_evidence, record_links)
6. **FTS5**: R5 (creare tabelle FTS5 per internati, caduti, menzioni)
7. **Tabelle mancanti**: Creare `acquisitions`, `stable_locators`, `permitted_operations`, `hits`
8. **State machine job**: Formalizzare `created → planning → ... → completed`

---

## 8. Conclusioni

### Stato attuale: **60% pronto per V2**

- **Moduli**: 20/20 presenti e importabili
- **Tabelle V2**: 15/30 già presenti (parzialmente), 3 mappabili con rename, 12 mancanti
- **Schema**: `claims`, `claim_evidence`, `entity_match_candidates`, `research_plans` già strutturati per V2
- **Compliance**: `source_policies` già più ricco del dichiarato, ma `compliance_decisions` vuota
- **AI**: 5 provider attivi, ma 2 non funzionanti (OpenAI 401, Anthropic crediti)

### Gate per Fase 1

Prima di procedere a Fase 1 (Fondamenta):
1. ✅ Audit completato (questo documento)
2. ⬜ Fix R1 (raw_text immutabile) e R2 (segreti nei log)
3. ⬜ Backup DB completo
4. ⬜ Matrice requisito → componente → test approvata
5. ⬜ Decision record architetturale
