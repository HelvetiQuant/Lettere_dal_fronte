# Report Tecnico: Schema DB, Collegamenti e Backend

**Progetto:** Voci dal Fronte — IMI Extractor  
**Data:** 2026-07-26  
**Backend Target:** Supabase PostgreSQL 17.6 (progetto `wyqesimzxieykmyhfvqs`)  
**Database originali:** SQLite → migrati su Supabase  
**Framework backend:** FastAPI (Python 3.11)

---

## 1. Architettura Database

### 1.1 Database Originali (SQLite)

| Database | Tabelle | Righe Totali | Descrizione |
|----------|---------|-------------|-------------|
| `imi_internati.db` | ~110 | ~4.6M | DB principale: IMI, caduti, decorati, fonti, grafo, AI |
| `eventi_1gm.db` | 3 | ~892K | Eventi storici 1GM + alias + feature cartografiche |
| `validazioni_ai.db` | 1 | 200 | Validazioni AI dei record links |
| `ocr_lettere.db` | 1 | 1 | Lettere OCR digitalizzate |

### 1.2 Schema Supabase (Post-Migrazione)

**125 tabelle** su schema `public` (114 migrate + 11 pre-esistenti).

---

## 2. Mappa delle Tabelle per Dominio

### 2.1 🎖️ DATI STORICI PRIMARI (16 tabelle)

#### Internati Militari Italiani (IMI)
| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `internati` | 20,465 | `id SERIAL` | Elenco IMI estratti da PDF (Elenchi A-D) |
| `progress` | 63 | `lettera TEXT` | Stato estrazione per lettera/PDF |

**Colonne chiave `internati`:** cognome, nome, data_nascita, luogo_nascita, residenza, grado, luogo_internamento, sorte, matricola, lettera, pagina, file_pdf, raw_text, needs_review, luogo_validato

#### Caduti delle Guerre Mondiali
| Tabella | Righe | PK | Fonte |
|---------|-------|-----|-------|
| `caduti_albooro` | 342,339 | `id SERIAL` | Albi d'Oro — ISTORECO |
| `caduti_bologna` | 9,656 | `id SERIAL` | Comune di Bologna |
| `caduti_cwgc` | 506,126 | `id SERIAL` | Commonwealth War Graves Commission |
| `caduti_francia_ww1` | 24,279 | `id SERIAL` | Mémoire des Hommes (Francia) |
| `caduti_ministero` | 162,646 | `id SERIAL` | Ministero della Difesa |
| `caduti_sardi` | 20,435 | `id SERIAL` | Sardegna Memoria 1GM |

#### Decorati
| Tabella | Righe | PK | Fonte |
|---------|-------|-----|-------|
| `decorati` | 1,286 | `id SERIAL` | ISTORECO — Albi della Memoria |
| `decorati_nastroazzurro` | 279,832 | `id SERIAL` | Nastro Azzurro |

#### Fondi Archivistici
| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `fondi_archivistici` | 4,808 | `id SERIAL` | Fondi SME (Stato Maggiore Esercito) |
| `menzioni` | 10,976 | `id SERIAL` | Menzioni persona/luogo estratte dai fondi |
| `fonti_indice` | 35,664 | `id SERIAL` | Indice fonti esterne indicizzate |
| `fonti_narrative` | 40 | `id SERIAL` | Fonti narrative personali (lettere, diari) |
| `archivio_documenti` | 433 | `(provider, external_id)` | Catalogo documenti archivistici |
| `archivio_fonti` | 1,153 | `id SERIAL` | Registro fonti con hash |

#### Documenti NARA
| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `documenti_nara_t315` | 1,153 | `id SERIAL` | NARA T315 microfilm (campo internamento) |
| `documenti_nara_catalog` | 272 | `id SERIAL` | NARA Catalog ricerche |

---

### 2.2 🔗 ENTITÀ E COLLEGAMENTI (7 tabelle)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `entita` | 689,058 | `id SERIAL` | Entità estratte (persone, luoghi, eventi) |
| `collegamenti` | 2,381,103 | `id SERIAL` | Links entità ↔ record tabella |
| `entity_variants` | 299 | `id SERIAL` | Varianti nome (alias, errori OCR) |
| `record_links` | 169,184 | `id SERIAL` | Links cross-tabella (es. internato ↔ caduto) |
| `event_links` | 892,073 | `id SERIAL` | Links evento ↔ record |
| `record_link_validations` | 200 | `id SERIAL` | Validazioni AI dei record links |
| `external_record_links` | 0 | `id SERIAL` | Links verso fonti esterne |

#### Relazioni chiave:

```
entita.id ──→ collegamenti.entita_id
                 ↓
             collegamenti.tabella_origine + record_id
                 ↓
             (internati | caduti_* | decorati | menzioni)

record_links.source_table + source_id ──→ tabella A
record_links.target_table + target_id ──→ tabella B

event_links.event_id ──→ eventi_1gm.id
event_links.record_table + record_id ──→ (internati | caduti_* | decorati)

record_link_validations.link_id ──→ record_links.id (FK)
```

---

### 2.3 📅 EVENTI (3 tabelle — DB `eventi_1gm`)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `eventi_1gm` | 22 | `id SERIAL` | Eventi canonici (battaglie, campagne) |
| `event_aliases` | 90 | `id SERIAL` | Alias nomi per eventi |
| `map_features` | 0 | `id TEXT` | Feature GeoJSON per mappe |

**Colonne `eventi_1gm`:** nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione, stable_id, conflict (WWI/WWII), event_type, parent_event_id, temporal_precision, general_location, localities_json, subjects_json, units_json, review_status, narrative_version, narrative_updated_at

```
eventi_1gm.id ──→ event_aliases.event_id
eventi_1gm.id ──→ map_features.event_id
eventi_1gm.id ──→ event_links.event_id
eventi_1gm.parent_event_id ──→ eventi_1gm.id (gerarchia)
```

---

### 2.4 🕸️ GRAFO DI PROVENIENZA (6 tabelle)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `graph_nodes` | 0 | `id SERIAL` | Nodi del grafo (entità, record) |
| `graph_edges` | 0 | `id SERIAL` | Archi del grafo (relazioni) |
| `graph_edge_reviews` | 0 | `id SERIAL` | Review umane degli archi |
| `graph_pipeline_runs` | 0 | `id SERIAL` | Esecuzioni pipeline grafo |
| `graph_integrity_issues` | 0 | `id SERIAL` | Problemi integrità grafo |
| `archival_metadata` | 0 | `id SERIAL` | Metadati archivistici |

```
graph_edges.source_id ──→ graph_nodes.id
graph_edges.target_id ──→ graph_nodes.id
graph_edge_reviews.edge_id ──→ graph_edges.id
```

---

### 2.5 🤖 AI / RICERCA (16 tabelle)

#### Sistema AI Multi-Provider
| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `ai_providers` | 6 | `id SERIAL` | Provider AI (OpenAI, Mistral, Anthropic, Google, LMStudio, Ollama) |
| `ai_models` | 7 | `id SERIAL` | Modelli AI registrati |
| `ai_routing_policies` | 21 | `id SERIAL` | Policy routing per task AI |
| `ai_task_runs` | 74 | `id SERIAL` | Log esecuzioni task AI |
| `ai_usage_ledger` | 64 | `id SERIAL` | Registro costi/token AI |
| `ai_ricerche` | 217 | `id SERIAL` | Log ricerche AI eseguite |
| `api_usage` | 10,624 | `id SERIAL` | Log API esterne chiamate |

```
ai_task_runs.provider_id ──→ ai_providers.id
ai_task_runs.model_id ──→ ai_models.id
ai_task_runs.policy_id ──→ ai_routing_policies.id
ai_usage_ledger.task_run_id ──→ ai_task_runs.id
```

#### Motore di Ricerca v2
| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `research_plans` | 46 | `id SERIAL` | Piani di ricerca |
| `research_sessions` | 46 | `id SERIAL` | Sessioni di ricerca |
| `research_queries` | 0 | `id SERIAL` | Query eseguite |
| `research_results` | 0 | `id SERIAL` | Risultati ricerca |
| `research_cycles` | 50 | `id SERIAL` | Cicli di ricerca (iterativi) |
| `research_gaps` | 472 | `id SERIAL` | Lacune identificate |
| `research_subjects` | 118 | `id SERIAL` | Soggetti di ricerca |
| `research_subject_sources` | 1,431 | `id SERIAL` | Fonti per soggetto |
| `prompt_versions` | 1 | `id SERIAL` | Versioni prompt AI |

```
research_sessions.plan_id ──→ research_plans.id
research_queries.session_id ──→ research_sessions.id
research_results.query_id ──→ research_queries.id
research_cycles.session_id ──→ research_sessions.id
research_subject_sources.subject_id ──→ research_subjects.id
```

---

### 2.6 📋 RICONOSCIMENTI (RC — 20 tabelle)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `rc_candidates` | 83 | `id SERIAL` | Candidati per riconoscimento |
| `rc_sessions` | 44 | `id TEXT` | Sessioni utente |
| `rc_sources` | 80 | `id SERIAL` | Fonti per candidato |
| `rc_historical_events` | 45 | `id SERIAL` | Eventi storici per candidato |
| `rc_ai_analyses` | 28 | `id SERIAL` | Analisi AI per candidato |
| `rc_practices` | 0 | `id SERIAL` | Pratiche di riconoscimento |
| `rc_practice_documents` | 1 | `id SERIAL` | Documenti allegati |
| `rc_document_versions` | 1 | `id SERIAL` | Versioni documenti |
| `rc_document_checklists` | 0 | `id SERIAL` | Checklist documenti |
| `rc_recognition_types` | 12 | `id SERIAL` | Tipi riconoscimento (MAVM, MOVM...) |
| `rc_recognition_assessments` | 50 | `id SERIAL` | Valutazioni |
| `rc_audit_log` | 164 | `id SERIAL` | Log audit RC |
| `rc_state_transitions` | 0 | `id SERIAL` | Transizioni stato pratiche |
| `rc_users` | 2 | `id SERIAL` | Utenti RC |
| `rc_kinship_links` | 0 | `id SERIAL` | Links parentela |
| `rc_family_persons` | 0 | `id SERIAL` | Persone famiglia |
| `rc_descendant_cases` | 0 | `id SERIAL` | Casi discendenti |
| `rc_descendant_contacts` | 0 | `id SERIAL` | Contatti discendenti |
| `rc_descendant_packages` | 0 | `id SERIAL` | Pacchetti discendenti |
| `rc_communications` | 0 | `id SERIAL` | Comunicazioni |

```
rc_sources.candidate_id ──→ rc_candidates.id
rc_historical_events.candidate_id ──→ rc_candidates.id
rc_ai_analyses.candidate_id ──→ rc_candidates.id
rc_recognition_assessments.candidate_id ──→ rc_candidates.id
rc_practices.candidate_id ──→ rc_candidates.id
rc_practice_documents.practice_id ──→ rc_practices.id
rc_document_versions.document_id ──→ rc_practice_documents.id
rc_state_transitions.candidate_id ──→ rc_candidates.id
rc_audit_log.candidate_id ──→ rc_candidates.id
```

---

### 2.7 📄 OCR / LETTERE (2 tabelle)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `lettere_personali` | 1 | `id SERIAL` | Lettere importate e OCR'd dal progetto |
| `ocr_lettere` | 1 | `id SERIAL` | Lettere OCR dal modulo import |

**Colonne `ocr_lettere`:** filename, file_path, mittente, destinatario, data_lettera, luogo, oggetto, corpo_testo, note, confidenza, lingua, raw_response, elaborato_il

---

### 2.8 🔒 COMPLIANCE / SICUREZZA (5 tabelle)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `source_policies` | 4 | `id SERIAL` | Policy accesso fonti esterne |
| `compliance_authorizations` | 0 | `id SERIAL` | Autorizzazioni scraping |
| `compliance_decisions` | 0 | `id SERIAL` | Decisioni compliance |
| `compliance_review_queue` | 0 | `id SERIAL` | Coda review compliance |
| `permitted_operations` | 68 | `id SERIAL` | Operazioni permesse per dominio |

---

### 2.9 🔧 INFRASTRUTTURA (8 tabelle)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `populate_progress` | 8,516 | `id SERIAL` | Stato batch populate loop |
| `source_fetch_cache` | 14 | `id SERIAL` | Cache fetch fonti esterne |
| `memory_trace` | 55 | `id SERIAL` | Trace memoria conversazionale |
| `consolidated_memory` | 1 | `id SERIAL` | Memoria consolidata |
| `claims` | 43 | `id SERIAL` | Affermazioni verificabili |
| `claim_evidence` | 550 | `id SERIAL` | Evidenze per claim |
| `claim_relations` | 102 | `id SERIAL` | Relazioni tra claims |
| `nara_catalog_files` | 0 | `id SERIAL` | File catalogo NARA |

---

### 2.10 🧠 DATASET ML / TRAINING (4 tabelle — Supabase only)

| Tabella | Righe | PK | Descrizione |
|---------|-------|-----|-------------|
| `ml_mdh_base` | 12,093 | `id SERIAL` | Mémoire des Hommes — schede base (soldati francesi 1GM) |
| `ml_mdh_annotations` | 12,186 | `id SERIAL` | MDH — annotazioni arricchite |
| `ml_training_datasets` | 41,168 | `id SERIAL` | Dataset training raw (aya_ita, commandnet, muninn_ww1, quandho) |
| `ml_training_chatml` | 81,080 | `id SERIAL` | Dataset ChatML format (messaggi fine-tuning) |

**Colonne `ml_mdh_base` / `ml_mdh_annotations`:** images_href, nom, naissance, grade, unite, lieu_naissance, bureau_recrutement, classe, matricule_recrutement, date_deces, lieu_deces, lieu_deces_suite, departement_deces, pays_deces, lieu_transcription_deces, departement_transcription_deces, pays_transcription_deces

**Colonne `ml_training_datasets`:** dataset_name, record_data (JSONB), created_at

**Colonne `ml_training_chatml`:** dataset_name, messages (JSONB), created_at

**Indici:** `idx_ml_training_datasets_name`, `idx_ml_training_chatml_name`

#### Breakdown Dataset Training

| Dataset | Tipo | Righe | Descrizione |
|---------|------|-------|-------------|
| `aya_ita` | raw | 668 | Aya Italian NLU dataset |
| `commandnet` | raw | 10,000 | CommandNet conversational dataset |
| `muninn_ww1` | raw | 28,700 | Muninn WW1 document archive (Europeana) |
| `quandho` | raw | 1,800 | QuandHo Italian QA dataset |
| `aya_ita_chatml` | ChatML | 40 | Fine-tuning ChatML format |
| `commandnet_chatml` | ChatML | 10,000 | Fine-tuning ChatML format |
| `muninn_ww1_chatml` | ChatML | 28,700 | Fine-tuning ChatML format |
| `quandho_chatml` | ChatML | 1,800 | Fine-tuning ChatML format |
| `train_merged` | ChatML | 40,540 | Merged training set |

---

## 3. Backend: Flusso Dati e Moduli

### 3.1 Architettura Data-Layer

```
┌──────────────────────────────────────────────────────────┐
│                     FastAPI (app.py)                      │
│                   163 API Endpoints                       │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │database.py│  │db_adapter.py │  │database_registry.py│  │
│  │get_conn() │  │PostgresConn  │  │TableSpec registry  │  │
│  │init_db()  │  │SQL converter │  │get_record_detail() │  │
│  └─────┬─────┘  └──────┬───────┘  └─────────┬──────────┘  │
│        │               │                     │             │
│        └───────────────┼─────────────────────┘             │
│                        │                                   │
│         ┌──────────────┴──────────────┐                    │
│         │   Supabase PostgreSQL 17.6  │                    │
│         │   (via REST API o psycopg2) │                    │
│         └─────────────────────────────┘                    │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Moduli Backend → Tabelle

| Modulo | File | Tabelle Principali | Operazioni |
|--------|------|--------------------|-----------|
| **Estrazione PDF** | `extractor.py` | internati, progress | INSERT, UPDATE |
| **Fondi SME** | `fondi.py` | fondi_archivistici, menzioni, progress | INSERT |
| **Caduti Albo d'Oro** | `caduti_albooro.py` | caduti_albooro, progress | INSERT |
| **Caduti Bologna** | `caduti_bologna.py` | caduti_bologna, progress | INSERT |
| **Caduti CWGC** | `caduti_cwgc.py` | caduti_cwgc, progress | INSERT |
| **Caduti Francia WW1** | `caduti_francia_ww1.py` | caduti_francia_ww1, progress | INSERT |
| **Caduti Ministero** | `caduti_ministero.py` | caduti_ministero, progress | INSERT |
| **Caduti Sardi** | `caduti_sardi.py` | caduti_sardi, progress | INSERT |
| **Decorati ISTORECO** | `decorati.py` | decorati, progress | INSERT |
| **Decorati Nastro Azzurro** | `decorati_nastroazzurro.py` | decorati_nastroazzurro, progress | INSERT |
| **Entità/NER** | `enrich_entities.py` | entita, collegamenti | INSERT |
| **Linker** | `linker.py` | record_links, entita | SELECT, INSERT |
| **Ricerca Incrociata** | `database.py` | TUTTE le tabelle storiche | SELECT (LIKE) |
| **Eventi** | `events.py`, `enrich_events.py` | eventi_1gm, event_links | SELECT, INSERT |
| **Grafo** | `graph_service.py`, `graph_schema.py` | graph_* (6 tabelle) | CRUD |
| **AI Router** | `ai_router.py`, `ai_client.py` | ai_providers, ai_models, ai_routing_policies, ai_task_runs, ai_usage_ledger | CRUD |
| **Ricerca v2** | `research_orchestrator.py` | research_* (8 tabelle) | CRUD |
| **RC (Riconoscimenti)** | `rc_api.py`, `rc_api_ext.py` | rc_* (20 tabelle) | CRUD |
| **Compliance** | `compliance_gate.py` | source_policies, compliance_* | CRUD |
| **Fonti Esterne** | `external_metadata_service.py` | external_*, fonti_indice | CRUD |
| **Import Lettere** | `import_lettere_personali.py` | lettere_personali | INSERT |
| **Validazione AI** | `_validate_links_ai.py` | record_link_validations | INSERT, SELECT |
| **Biografia** | `biography.py` | source_fetch_cache, internati | SELECT, INSERT |
| **Dossier Soldato** | `soldier_dashboard.py` | internati, record_links, fonti_indice, caduti_* | SELECT |
| **Mappe** | `map_features_api.py`, `map_schema.py` | map_features | CRUD |
| **Memoria** | `memory_router.py` | memory_trace, consolidated_memory | CRUD |
| **Report** | `report_engine.py` | internati, fonti_indice, record_links, claims | SELECT |

### 3.3 API Endpoints per Dominio (163 totali)

| Dominio | Endpoints | Metodo HTTP | Esempio |
|---------|-----------|-------------|---------|
| **Ricerca** | 6 | GET/POST | `/api/search`, `/api/conv-search`, `/api/search/ww1` |
| **Internati** | 8 | GET/PUT/DELETE | `/api/internati`, `/api/internati/{rid}`, `/api/validate-locations/{rid}` |
| **Estrazione PDF** | 6 | POST/GET | `/api/extract/{letter}`, `/api/extract/status` |
| **Fondi** | 5 | GET/POST/DELETE | `/api/fondi`, `/api/fondi/extract-all` |
| **Caduti** | 12 | GET/POST | `/api/albooro`, `/api/cwgc/scrape`, `/api/caduti/{id}` |
| **Decorati** | 4 | GET/POST | `/api/decorati`, `/api/decorati/scrape` |
| **Entità** | 5 | GET/POST | `/api/entita`, `/api/entita/search`, `/api/entita/build` |
| **AI** | 3 | POST/GET | `/api/ai-research`, `/api/ai-research/history` |
| **Fonti Esterne** | 10 | GET/POST | `/api/providers`, `/api/source/search`, `/api/source/fetch` |
| **Eventi** | 13 | GET | `/api/events/1gm`, `/api/events/{name}/sources` |
| **Event Research** | 8 | GET | `/api/event-research/resolve`, `/api/event-research/map` |
| **Ricerca v2** | 10 | GET/POST/PATCH | `/api/research/v2/create`, `/api/research/subjects` |
| **Soldato Dashboard** | 4 | GET | `/api/soldiers/{id}/dashboard`, `/api/internati/{id}/links` |
| **LeBI (ANRP)** | 3 | GET | `/api/lebi/search`, `/api/lebi/record/{id}` |
| **ACS** | 2 | GET/POST | `/api/acs/registri`, `/api/acs/ingest` |
| **Archivio** | 4 | GET/POST | `/api/archivio`, `/api/archivio/ingest` |
| **Biografia** | 1 | POST | `/api/biography` |
| **Memoria** | 4 | POST/GET | `/api/memory/query`, `/api/memory/traces` |
| **Report** | 3 | POST/GET | `/api/event/report`, `/api/report` |
| **Immagini AI** | 3 | POST/GET | `/api/fonte/generate-images`, `/api/soldier/images` |
| **Export** | 2 | GET | `/api/export/excel`, `/api/export/csv` |
| **CWGC** | 3 | GET/POST | `/api/cwgc`, `/api/cwgc/scrape` |
| **Mass Index** | 3 | POST/GET | `/api/mass-index/start`, `/api/mass-index/status` |
| **Upload** | 3 | POST | `/api/upload`, `/api/upload/preview`, `/api/upload/import` |
| **Fonti Risorse** | 4 | GET/POST | `/api/fonti-risorse`, `/api/fonti-risorse/scrape` |
| **Cime e Trincee** | 3 | GET/POST | `/api/cimeetrincee/storie`, `/api/cimeetrincee/scrape` |

---

## 4. Diagramma Relazioni Principali

```
┌─────────────────────────────────────────────────────────────────┐
│                    LIVELLO DATI STORICI                          │
│                                                                  │
│  ┌──────────┐    ┌────────────────┐    ┌─────────────────────┐  │
│  │ internati│    │  caduti_*      │    │    decorati_*        │  │
│  │ (20.4K)  │    │ (1.1M totali)  │    │   (281K totali)     │  │
│  └────┬─────┘    └───────┬────────┘    └──────────┬──────────┘  │
│       │                  │                         │             │
│       ├──────────────────┼─────────────────────────┤             │
│       │                  │                         │             │
│       ▼                  ▼                         ▼             │
│  ┌──────────────────────────────────────────────────────┐       │
│  │               record_links (169K)                     │       │
│  │  source_table + source_id ↔ target_table + target_id  │       │
│  └─────────────────────┬────────────────────────────────┘       │
│                        │                                         │
│                        ▼                                         │
│  ┌──────────────────────────────────────────────────────┐       │
│  │          record_link_validations (200)                │       │
│  │         (AI validation: verdict, score, reason)       │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌─────────────┐        ┌──────────────────────────────┐        │
│  │ entita (689K)│───────→│ collegamenti (2.4M)          │        │
│  │ NER entities │        │ entita_id → tabella + record │        │
│  └──────┬──────┘         └──────────────────────────────┘        │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────┐                                             │
│  │entity_variants   │                                             │
│  │(299 alias/OCR)   │                                             │
│  └─────────────────┘                                             │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     LIVELLO EVENTI                                │
│                                                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐    │
│  │ eventi_1gm  │←──→│ event_aliases │    │   map_features    │    │
│  │ (22 eventi) │    │ (90 alias)   │    │   (0 GeoJSON)     │    │
│  └──────┬──────┘    └──────────────┘    └───────────────────┘    │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────────────────────────────────────────────┐        │
│  │              event_links (892K)                       │        │
│  │    event_id → record_table + record_id                │        │
│  │    (collega eventi a caduti/internati/decorati)        │        │
│  └──────────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    LIVELLO AI / RICERCA                            │
│                                                                   │
│  ai_providers → ai_models → ai_routing_policies                   │
│       ↓                                                           │
│  ai_task_runs → ai_usage_ledger                                   │
│                                                                   │
│  research_plans → research_sessions → research_queries             │
│                          ↓                                        │
│                   research_results, research_cycles                │
│                          ↓                                        │
│                   research_gaps                                    │
│                                                                   │
│  research_subjects → research_subject_sources                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                   LIVELLO RICONOSCIMENTI (RC)                     │
│                                                                   │
│  rc_users ──→ rc_sessions                                         │
│  rc_candidates ──→ rc_sources                                     │
│       │        ──→ rc_historical_events                           │
│       │        ──→ rc_ai_analyses                                 │
│       │        ──→ rc_recognition_assessments                     │
│       ↓                                                           │
│  rc_practices ──→ rc_practice_documents ──→ rc_document_versions  │
│       │        ──→ rc_state_transitions                           │
│       │        ──→ rc_audit_log                                   │
│       ↓                                                           │
│  rc_recognition_types (MAVM, MOVM, Croce al Merito...)            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Full-Text Search (FTS)

### PostgreSQL (Supabase)

| Tabella | Colonna | Config | Trigger |
|---------|---------|--------|---------|
| `entita` | `search_vector` (tsvector) | `'simple'` | `trg_entita_search_vector` (BEFORE INSERT/UPDATE) |

**Campi indicizzati nel tsvector:** valore, cognome, nome, luogo, contesto

**Indice GIN:** `idx_entita_search_vector`

### Query FTS Pattern
```sql
SELECT * FROM entita
WHERE search_vector @@ to_tsquery('simple', 'ROSSI & MARIO')
```

---

## 6. Row Level Security (RLS)

### Policy applicate:

| Categoria | Tabelle | SELECT | INSERT/UPDATE/DELETE |
|-----------|---------|--------|---------------------|
| **Pubblica (storica)** | caduti_*, decorati_*, fondi_archivistici, menzioni, entita, internati, fonti_*, eventi_1gm, event_*, archivio_*, collegamenti, record_links | ✅ `true` | 🔑 `service_role` only |
| **OCR/Lettere** | ocr_lettere, lettere_personali | ✅ `true` | 🔑 `service_role` only |
| **Admin/AI** | ai_*, api_usage, source_policies, compliance_*, graph_* | 🔑 `service_role` | 🔑 `service_role` |

---

## 7. Indici PostgreSQL (236 totali)

### Indici principali per performance:

| Tabella | Indice | Colonne |
|---------|--------|---------|
| `internati` | `idx_internati_cognome` | cognome |
| `menzioni` | `idx_menzioni_cognome` | cognome |
| `menzioni` | `idx_menzioni_luogo` | luogo |
| `decorati` | `idx_decorati_cognome` | cognome |
| `entita` | `idx_entita_valore` | valore_normalizzato |
| `entita` | `idx_entita_tipo` | tipo |
| `entita` | `idx_entita_search_vector` | search_vector (GIN) |
| `collegamenti` | `idx_collegamenti_entita` | entita_id |
| `collegamenti` | `idx_collegamenti_record` | (tabella_origine, record_id) |
| `record_links` | composite indexes | source_table, target_table, status |
| `event_links` | `idx_event_links_*` | event_id, record_table |
| `caduti_cwgc` | `idx_cwgc_cognome_nocase` | cognome |
| `caduti_ministero` | multiple | cognome, nome, comune_nascita |
| `fonti_indice` | `idx_fonti_indice_*` | provider, hash |
| `map_features` | `idx_map_features_event` | event_id |

---

## 8. Statistiche di Volume

| Metrica | Valore |
|---------|--------|
| **Tabelle totali** | 114 (migrate) + 11 (pre-esistenti) = 125 |
| **Righe totali** | ~5,545,074 |
| **Indici** | 236 |
| **FTS tsvector** | 1 (entita) |
| **Policy RLS** | ~60 |
| **API Endpoints** | 163 |
| **Moduli Python backend** | ~50 |
| **Provider AI integrati** | 6 (OpenAI, Mistral, Anthropic, Google, LMStudio, Ollama) |
| **Fonti dati esterne** | 27 (ICRC, LeBI, CWGC, NARA, Nastro Azzurro, etc.) |

---

## 9. Supabase: Configurazione

| Parametro | Valore |
|-----------|--------|
| **Project Ref** | `wyqesimzxieykmyhfvqs` |
| **Project Name** | Voci dal Fronte |
| **PostgreSQL** | 17.6 |
| **Region** | AWS (auto) |
| **Schema** | `public` |
| **Auth** | Service Role Key (backend-only) |
| **RLS** | Abilitato su tutte le tabelle storiche e admin |
| **FTS** | tsvector + GIN su `entita` |
| **Helper Function** | `exec_sql(query text) → json` |

---

*Report generato automaticamente — Voci dal Fronte, 2026-07-26*
