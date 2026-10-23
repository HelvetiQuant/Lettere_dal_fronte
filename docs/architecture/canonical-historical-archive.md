# Audit del Repository — Archivio Documentale Canonico Supabase

**Data:** 2026-07-26  
**Branch:** `devin/ai-storica-eventi-mappe`  
**Commit:** `060bb8d`

---

## 4.1 Mappa dei Componenti

| Capacità | Implementazione corrente | Tabella/Modello corrente | Decisione |
|---|---|---|---|
| **Eventi canonici** | `event_resolver.py`, `event_schema.py`, `event_canonical_api.py` | `eventi_1gm` (22 righe, 21 colonne incluse 12 additive), `event_aliases` (90 righe) | **EXTEND** — aggiungere colonne mancanti (languages, historical_place_names) |
| **Fonti esterne** | `source_providers/federation.py` (27 provider), `external_sources_api.py` | `external_source_records` (0 righe), `archive_connectors` (27 righe) | **EXTEND** — aggiungere tabelle `ops.discovery_queries`, `ops.discovery_candidates` |
| **Metadati item** | `ia_pipeline.py`, `ia_locator.py`, `archivio_documenti.py` | `archivio_documenti` (433 righe), `archivio_fonti` (1,153 righe), `fonti_indice` (35,664 righe) | **EXTEND** — creare `archive.external_items` + `archive.external_item_revisions` |
| **Asset/file** | `external_digital_objects` table, `archivio_storage/` | `external_digital_objects` (0 righe), `source_fetch_cache` (14 righe) | **EXTEND** — creare `archive.representations` con ruoli e checksum |
| **Pagina/locator** | `ia_locator.py` (`PageLocator` dataclass) | `stable_locators` (0 righe) | **EXTEND** — creare `archive.document_units` con locator strutturato |
| **OCR/trascrizioni** | `ia_locator.py` (hOCR, DjVu), `document_extractions` | `document_extractions` (0 righe) | **EXTEND** — creare `archive.text_versions` con ruoli (original, ocr_provider, ocr_local, transcription, normalized, translation) |
| **Passaggi** | Non implementato come entità separata | — | **CREATE** — `archive.passages` (nuovo oggetto citabile) |
| **Claims/evidenze** | `claim_service.py`, `canonical_models.py` | `claims` (43 righe), `claim_evidence` (550 righe), `claim_relations` (102 righe) | **EXTEND** — aggiungere `passage_id` a `claim_evidence`, `semantic_hash` a `claims` |
| **RAG/embedding** | `rag_pipeline.py`, `rag_api.py` | `RetrievedChunk` dataclass, FTS5 su `fonti_indice` | **EXTEND** — collegare a `archive.passages` + `archive.chunks` |
| **Dataset ML** | `convert_training_datasets.py`, `data_mdh/` | `ml_training_datasets` (non esiste come tabella), `data_mdh/mdh_base.csv` (8.5MB), `data_mdh/mdh_annotations.csv` (8.6MB) | **CREATE** — `ai.datasets`, `ai.dataset_versions`, `ai.dataset_items`, `ai.dataset_item_sources` |
| **Worker/job** | `external_metadata_service.py` (import jobs), `pipeline_watchdog.py` | `external_import_jobs` (2 righe), `populate_progress` (8,516 righe) | **EXTEND** — creare `ops.job_queue` con claim atomico (FOR UPDATE SKIP LOCKED) |
| **Storage** | `archivio_storage/` (vuoto), `source_cache/` (vuoto) | Nessun bucket Supabase configurato | **CREATE** — bucket privati + pubblici con policy |
| **RLS/API pubblica** | `sql/04_rls_policies.sql` (189 righe) | 20+ tabelle con RLS (public read, service write) | **EXTEND** — aggiungere schemi canonici, `api_public` views, `ALTER DEFAULT PRIVILEGES` |

---

## 4.2 Inventario Tecnico

### Database SQLite (sorgente)

| Database | Tabelle | Righe totali | Dimensione |
|---|---|---|---|
| `imi_internati.db` | 75 | 9,547,277 | 1.76 GB |
| `eventi_1gm.db` | 4 | 891,986 | 138 MB |
| `validazioni_ai.db` | 1 | 200 | 92 KB |

### Tabelle principali per volume

| Tabella | Righe | DB |
|---|---|---|
| `caduti_cwgc` | 506,446 | main |
| `caduti_albooro` | 342,555 | main |
| `decorati_nastroazzurro` | 279,832 | main |
| `record_links` | 169,184 | main |
| `caduti_ministero` | 162,646 | main |
| `fonti_indice` | 35,664 | main |
| `caduti_francia_ww1` | 24,279 | main |
| `internati` | 20,465 | main |
| `caduti_sardi` | 20,435 | main |
| `menzioni` | 10,976 | main |
| `populate_progress` | 8,516 | main |
| `fondi_archivistici` | 4,808 | main |
| `archivio_fonti` | 1,153 | main |
| `archivio_documenti` | 433 | main |
| `research_subject_sources` | 1,431 | main |
| `research_subjects` | 118 | main |
| `claim_evidence` | 550 | main |
| `claims` | 43 | main |
| `event_links` | 891,874 | events |
| `eventi_1gm` | 22 | events |
| `event_aliases` | 90 | events |

### Supabase (destinazione)

- **URL:** `https://wyqesimzxieykmyhfvqs.supabase.co`
- **Stato:** Connesso (HTTP 200)
- **Tabelle dati migrate:** 0 (solo metadati OpenAPI visibili)
- **Migrazione checkpoint:** 65 tabelle parzialmente migrate (interrotta)
- **Schema SQL generato:** `sql/supabase_complete_schema.sql` (85KB, 114 tabelle, 236 indici)
- **RLS policies:** `sql/04_rls_policies.sql` (20+ tabelle con public read / service write)

### Provider registrati (27)

| Provider | Classe | Base URL | Search | Get Metadata |
|---|---|---|---|---|
| `nara` | ProviderNARA | catalog.archives.gov | ✓ | ✓ |
| `antenati` | ProviderAntenati |antenati.san.beniculturali.it | ✓ | ✗ |
| `cwgc` | ProviderCWGC | cwgc.org | ✓ | ✗ |
| `wikitree` | ProviderWikiTree | wikitree.com | ✓ | ✗ |
| `arolsen` | ProviderArolsen | arolsen-archives.org | ✓ | ✗ |
| `bundesarchiv` | ProviderBundesarchiv | bundesarchiv.de | ✓ | ✗ |
| `shd` | ProviderSHD | defense.gouv.fr | ✓ | ✗ |
| `tna_uk` | ProviderNationalArchivesUK | nationalarchives.gov.uk | ✓ | ✗ |
| `europeana` | ProviderEuropeana | api.europeana.eu | ✓ | ✗ |
| `gallica` | ProviderGallica | gallica.bnf.fr | ✓ | ✗ |
| `internetarchive` | ProviderInternetArchive | archive.org | ✓ | ✓ |
| `googlebooks` | ProviderGoogleBooks | googleapis.com | ✓ | ✗ |
| `abmc` | ProviderABMC | abmc.gov | ✓ | ✗ |
| `librarycanada` | ProviderLibraryCanada | bac-lac.gc.ca | ✓ | ✗ |
| `awm` | ProviderAustralianWarMemorial | awm.gov.au | ✓ | ✗ |
| `archivportalD` | ProviderArchivportalD | deutsche-digitale-bibliothek.de | ✓ | ✗ |
| `internetculturale` | ProviderInternetCulturale | internet culturale.it | ✓ | ✗ |
| `hathitrust` | ProviderHathiTrust | catalog.hathitrust.org | ✓ | ✗ |
| `ussme` | ProviderUSSME | ussme.it | ✓ | ✗ |
| `archiviodistato` | ProviderArchivioDiStato | archiviodistato.it | ✓ | ✗ |
| `memoire_des_hommes` | ProviderMemoireDesHommes | memoiredeshommes.sga.defense.gouv.fr | ✓ | ✗ |
| `ddb` | ProviderDDB | api.deutsche-digitale-bibliothek.de | ✗ | ✗ |
| `iwm_lives` | ProviderIWMLives | iwm.org.uk | ✗ | ✗ |
| `grand_memorial` | ProviderGrandMemorial | grandmemorial.gc.ca | ✗ | ✗ |
| `icrc_ww1` | ProviderICRCWW1 | grandeguerre.icrc.org | ✓ | ✗ |
| `cri_milano` | ProviderCRIMilano | cri.it | ✓ | ✗ |
| `lebi` | ProviderLeBI | lessicobiograficoimi.it | ✓ | ✓ |

### Endpoint API (163 totali in `app.py`)

Moduli API identificati:
- **Ricerca eventi:** 12 endpoint (`/api/event-research/*`, `/api/events/*`)
- **Ricerca persone:** 15 endpoint (`/api/internati/*`, `/api/soldiers/*`)
- **Fonti esterne:** 18 endpoint (`/api/sources/*`, `/api/source/*`, `/api/providers/*`)
- **IA/RAG:** 8 endpoint (`/api/ai-research`, `/api/ai-runtime/*`, `/api/rag/*`)
- **Graph:** 8 endpoint (`/api/graph/*`)
- **Mappe:** 3 endpoint (`/api/event-research/map*`, `/api/map-features/*`)
- **Claims:** 4 endpoint (`/api/event-research/evidence`, `/api/fonte/*`)
- **LeBI:** 3 endpoint (`/api/lebi/*`)
- **Scraping/acquisizione:** 30+ endpoint (`/api/*/scrape`, `/api/extract/*`, `/api/mass-index/*`)
- **Riconoscimenti (RC):** 20+ endpoint (`/api/rc_*`)
- **Export/import:** 6 endpoint (`/api/export/*`, `/api/upload/*`)

### Moduli Python principali (non test, non temp)

| File | Dimensione | Responsabilità |
|---|---|---|
| `app.py` | 110 KB | FastAPI backend, 163 endpoint |
| `database.py` | 60 KB | Connessione SQLite, schema init |
| `biography.py` | 68 KB | Biografie soldati |
| `rc_api_ext.py` | 100 KB | API riconoscimenti estesa |
| `rc_ai_analysis.py` | 59 KB | Analisi AI riconoscimenti |
| `research_orchestrator.py` | 57 KB | Orchestrazione ricerca agentica |
| `mass_index.py` | 45 KB | Indicizzazione massiva |
| `event_evidence_pipeline.py` | 44 KB | Pipeline evidenze eventi |
| `event_map_builder.py` | 40 KB | Costruttore mappe storiche |
| `providers.py` | 78 KB | 15+ provider implementation |
| `graph_service.py` | 33 KB | Servizio grafo provenance |
| `claim_service.py` | 16 KB | CRUD claims + evidence |
| `rag_pipeline.py` | 17 KB | RAG retrieval + reranking |
| `ia_pipeline.py` | 31 KB | Pipeline Internet Archive completa |
| `ia_evaluation.py` | 20 KB | Valutazione pertinenza storica IA |
| `ia_locator.py` | 16 KB | Locator pagina/passaggio IA |
| `external_sources_schema.py` | 13 KB | Schema fonti esterne federate |
| `research_engine_schema.py` | 23 KB | Schema research engine + AI |
| `canonical_models.py` | 10 KB | Modelli Pydantic canonici |
| `compliance_gate.py` | 24 KB | Gate conformità fonti |
| `archive_registry.py` | 10 KB | Registry fonti unificato |

### Dataset ML esistenti

| File | Dimensione | Contenuto |
|---|---|---|
| `data/training_chatml/train_merged.jsonl` | 52 MB | Dataset unito per training Qwen |
| `data/training_chatml/commandnet_chatml.jsonl` | 30 MB | CommandNet dataset |
| `data/training_chatml/muninn_ww1_chatml.jsonl` | 20 MB | Muninn WW1 dataset |
| `data/training_chatml/quandho_chatml.jsonl` | 1.7 MB | QuandHO dataset |
| `data/training_chatml/aya_ita_chatml.jsonl` | 45 KB | Aya Italian dataset |
| `data_mdh/mdh_base.csv` | 8.5 MB | MDH base annotations |
| `data_mdh/mdh_annotations.csv` | 8.6 MB | MDH annotations |

### Modelli AI configurati

| Provider | Modelli | Stato |
|---|---|---|
| OpenAI | GPT-4o, GPT-4o-mini | active |
| Anthropic | Claude 3.5 Sonnet | active |
| Mistral | Mistral Large | active |
| Perplexity | Sonar | active |
| Gemini | Gemini 1.5 Pro | active |
| LM Studio | Qwen2.5-0.5B-Instruct (locale) | active |

### Frontend

- **Framework:** React + TypeScript + Vite
- **Pagine:** EventsPage, GraphEntityPage, EventResearchPage
- **API client:** `frontend/src/api/canonical-types.ts` (15 metodi API)
- **Router:** `frontend/src/app/router.tsx`

---

## 4.3 Rapporto di Compatibilità

### REUSE (riuso diretto, nessuna modifica)

| Oggetto | Posizione | Motivo |
|---|---|---|
| `eventi_1gm` | `eventi_1gm.db` | Tabella eventi esistente, già estesa con 12 colonne canoniche |
| `event_aliases` | `eventi_1gm.db` | Tabella alias già creata e popolata (90 righe) |
| `claims` | `imi_internati.db` | Tabella claims con stable_id, epistemic_status, review_status |
| `claim_evidence` | `imi_internati.db` | Tabella evidenze con source_id, page_or_frame, supporting_quote |
| `claim_relations` | `imi_internati.db` | Relazioni tra claim |
| `archive_connectors` | `imi_internati.db` | Registry 27 provider con capabilities |
| `ai_providers` | `imi_internati.db` | 6 provider AI configurati |
| `ai_models` | `imi_internati.db` | 7 modelli AI |
| `ai_routing_policies` | `imi_internati.db` | 21 policy di routing |
| `ai_task_runs` | `imi_internati.db` | 74 esecuzioni tracciate |
| `ai_usage_ledger` | `imi_internati.db` | 64 voci ledger |
| `graph_nodes/edges/reviews` | `imi_internati.db` | Schema grafo già creato (0 righe, pronto) |
| `map_features` | `eventi_1gm.db` | Tabella features cartografiche già creata |
| `source_policies` | `imi_internati.db` | 4 policy di conformità |
| `compliance_gate.py` | modulo Python | Gate conformità funzionante |

### EXTEND (estensione con nuovi campi/tabelle)

| Oggetto | Posizione | Estensione richiesta |
|---|---|---|
| `eventi_1gm` | `eventi_1gm.db` | Aggiungere `languages_json`, `historical_place_names_json` |
| `claim_evidence` | `imi_internati.db` | Aggiungere `passage_id`, `text_version_id`, `content_sha256`, `locator_json` |
| `claims` | `imi_internati.db` | Aggiungere `semantic_hash`, `event_id`, `model_run_id` |
| `external_source_records` | `imi_internati.db` | Aggiungere `repository_id`, `collection_id`, `rights_assessment_json` |
| `external_digital_objects` | `imi_internati.db` | Aggiungere `representation_role`, `etag`, `last_modified`, `bucket_path` |
| `record_links` | `imi_internati.db` | Già esteso con match_status, review_status — aggiungere `legacy_quarantine` flag |
| `fonti_indice` | `imi_internati.db` | Aggiungere `external_item_id`, `passage_id` per collegamento canonico |
| `FederatedSearchContext` | `source_providers/base.py` | Estendere con `languages`, `historical_place_names`, `parent_events`, `subevents` |
| `rag_pipeline.py` | modulo Python | Collegare retrieval a `archive.passages` invece di solo `fonti_indice` |
| `ia_pipeline.py` | modulo Python | Integrare con `archive.external_items` e `archive.representations` |

### RENAME_WITH_COMPATIBILITY_VIEW

| Oggetto | Posizione | Nuovo nome | Vista di compatibilità |
|---|---|---|---|
| `archivio_documenti` | `imi_internati.db` | `archive.external_items` | `legacy.archivio_documenti_view` |
| `archivio_fonti` | `imi_internati.db` | `archive.repositories` (parziale) | `legacy.archivio_fonti_view` |
| `fonti_indice` | `imi_internati.db` | `archive.catalog_entries` | `legacy.fonti_indice_view` |
| `fonti_narrative` | `imi_internati.db` | `research.narratives` | `legacy.fonti_narrative_view` |
| `event_links` | `eventi_1gm.db` | `evidence.event_links` (in quarantena) | `legacy.event_links_view` |
| `record_links` | `imi_internati.db` | `evidence.record_links` (in quarantena) | `legacy.record_links_view` |
| `generated_narratives` | `imi_internati.db` | `research.narratives` | `legacy.generated_narratives_view` |
| `document_extractions` | `imi_internati.db` | `archive.text_versions` | `legacy.document_extractions_view` |

### BACKFILL (dati da migrare con script idempotenti)

| Sorgente | Destinazione | Volume | Note |
|---|---|---|---|
| `eventi_1gm` → `core.events` | Eventi canonici | 22 righe | Mappare conflict, event_type, parent_event_id |
| `event_aliases` → `core.event_aliases` | Alias eventi | 90 righe | Copia diretta |
| `archivio_documenti` → `archive.external_items` | Item esterni | 433 righe | Deduplica per provider + external_id |
| `archivio_fonti` → `archive.repositories` | Repository | 1,153 righe | Separare aggregatore da conservatore |
| `fonti_indice` → `archive.catalog_entries` | Catalogo fonti | 35,664 righe | Mappare URL con url_role |
| `event_links` → `evidence.link_quarantine` | Link in quarantena | 891,874 righe | Non promuovere a confirmed |
| `record_links` → `evidence.link_quarantine` | Link in quarantena | 169,184 righe | Non promuovere a confirmed |
| `claims` → `evidence.claims` | Claims | 43 righe | Aggiungere semantic_hash |
| `claim_evidence` → `evidence.claim_evidence` | Evidenze | 550 righe | Aggiungere passage_id (NULL per ora) |
| `research_subjects` → `core.research_subjects` | Soggetti ricerca | 118 righe | Copia diretta |
| `research_subject_sources` → `core.subject_sources` | Fonti soggetti | 1,431 righe | Copia diretta |
| `data_mdh/*.csv` → `ai.datasets` | Dataset ML | 2 file | Importare con provenienza e licenza |

### QUARANTINE (dati legacy non promossi automaticamente)

| Tabella | Volume | Motivo |
|---|---|---|
| `event_links` (891,874) | Link euristici per keyword/anno/luogo | Non diventano fatti verificati |
| `record_links` (169,184) | Link polimorfici generici | Richiedono revisione |
| `menzioni` (10,976) | Menzioni estratte da fonti | Non diventano evidenze senza passaggio |
| `entity_variants` (299) | Varianti identità | Da rivedere con entity resolution |
| `populate_progress` (8,516) | Stato scraping | Dato operativo, non storico |

### DO_NOT_CREATE (già esistenti o non necessari)

| Oggetto | Motivo |
|---|---|
| `ai_providers` | Già esiste con 6 provider |
| `ai_models` | Già esiste con 7 modelli |
| `ai_routing_policies` | Già esiste con 21 policy |
| `ai_task_runs` | Già esiste con 74 run |
| `ai_usage_ledger` | Già esiste con 64 voci |
| `graph_nodes/edges/reviews` | Già creati (schema graph_schema.py) |
| `map_features` | Già creata (schema map_schema.py) |
| `archive_connectors` | Già creato con 27 provider seeded |
| `source_policies` | Già esiste con 4 policy |
| `compliance_decisions` | Già esiste (tabella compliance_gate.py) |

---

## Tabelle canoniche da creare (nuove)

### Schema `archive`

| Tabella | Responsabilità |
|---|---|
| `archive.repositories` | Istituzioni conservatrici (nome, tipo, paese, authority URI) |
| `archive.collections` | Fondi/serie/collezioni |
| `archive.external_items` | Item esterni (provider_id + external_id, stable identity) |
| `archive.external_item_revisions` | Revisioni metadati immutabili (SHA-256, ETag, raw metadata) |
| `archive.representations` | Rappresentazioni file (original, pdf, ocr, hocr, alto, thumbnail, etc.) |
| `archive.document_units` | Unità documentali (page, leaf, canvas, frame, segment) |
| `archive.text_versions` | Versioni testuali (ocr_provider, ocr_local, transcription, normalized, translation) |
| `archive.passages` | Passaggi citabili (char_start, char_end, text, locator, SHA-256) |
| `archive.chunks` | Chunk RAG (collegati a text_versions) |

### Schema `ops`

| Tabella | Responsabilità |
|---|---|
| `ops.discovery_queries` | Query di discovery con EventContext, query plan, cache key |
| `ops.discovery_candidates` | Candidati con discovery_score, relevance_score, decision |
| `ops.job_queue` | Coda job con claim atomico (FOR UPDATE SKIP LOCKED) |
| `ops.fetch_cache` | Cache fetch con ETag, Last-Modified, TTL |

### Schema `ai` (estensione)

| Tabella | Responsabilità |
|---|---|
| `ai.datasets` | Dataset ML versionati |
| `ai.dataset_versions` | Versioni immutabili con hash, freeze, split policy |
| `ai.dataset_items` | Esempi ML con provenienza multipla |
| `ai.dataset_item_sources` | Fonti di ogni esempio (passage, claim, entity) |
| `ai.evaluation_runs` | Valutazioni modello con metriche |

### Schema `evidence` (estensione)

| Tabella | Responsabilità |
|---|---|
| `evidence.link_quarantine` | Link legacy in quarantena (raw, reason, status) |
| `evidence.rights_assessments` | Valutazione diritti versionata per item/representation |

### Schema `api_public`

| Oggetto | Tipo | Espone |
|---|---|---|
| `api_public.events` | VIEW | Eventi approvati (review_status = confirmed/probable) |
| `api_public.narratives` | VIEW | Narrazioni pubblicate |
| `api_public.citations` | VIEW | Citazioni approvate con passage |
| `api_public.sources_metadata` | VIEW | Metadati fonti pubblicabili |

---

## Principali gap identificati

1. **Passaggi citabili (`archive.passages`):** Non esistono. `claim_evidence` ha `page_or_frame` e `supporting_quote` ma non c'è entità passage separata con hash e locator.
2. **Discovery provenance (`ops.discovery_queries/candidates`):** Non esistono. La provenienza della discovery è dispersa nei log.
3. **Revisioni metadati immutabili:** `external_source_records` ha `metadata_hash` ma non conserva revisioni storiche.
4. **Diritti versionati:** `source_rights` (0 righe) e `source_policies` (4 righe) non hanno valutazione per-item con 8 dimensioni (metadata_access, content_access, download, etc.).
5. **Job queue atomica:** `external_import_jobs` non ha claim atomico con FOR UPDATE SKIP LOCKED.
6. **Dataset ML tracciati:** Non esistono tabelle `ai.datasets` / `ai.dataset_versions`. I file CSV/JSONL sono su filesystem senza provenienza.
7. **Bucket Storage:** Nessun bucket Supabase configurato.
8. **Schemi PostgreSQL separati:** Tutto in `public` senza separazione `archive`, `evidence`, `ops`, `ai`, `api_public`.
9. **`ALTER DEFAULT PRIVILEGES`:** Non configurato — nuove tabelle sarebbero accessibili.
10. **Frontend admin:** Manca interfaccia per revisione link/claim/evidence e stato ingestion.
