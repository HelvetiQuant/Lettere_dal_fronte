# Architettura Completa — Lettere dal Fronte (post-migrazione canonical archive)

**Data:** 2026-07-27  
**Scope:** Sistema integrato di ricerca storica su WWI/WWII dopo l'adozione dello strato canonico su Supabase/PostgreSQL.

---

## 1. Panoramica

Il sistema "Lettere dal Fronte" è una piattaforma di ricerca storica specializzata sui conflitti del '900 (principalmente Prima e Seconda Guerra Mondiale) che integra:

- **Archivi locali SQLite** (legacy): dati principali estratti da lettere, fonti archivistiche, caduti, decorati, eventi.
- **Archivio canonico Supabase/PostgreSQL**: nuovo strato normalizzato, multi-schema, con RLS, hash di contenuto, provenance e indici.
- **Provider esterni federati**: 27+ fonti archivistiche nazionali e internazionali.
- **AI locale**: Qwen 2.5-0.5B-Instruct fine-tunato via LoRA su CPU, esposto tramite LM Studio / endpoint OpenAI-compatible.
- **Frontend React/TS**: interfaccia di ricerca, visualizzazione grafi, mappa eventi, admin di revisione.

Obiettivo dell'architettura: mantenere la compatibilità con il legacy, aggiungere un modello canonico stabile e citabile, e permettere l'integrazione controllata di fonti esterne e di modelli AI locali.

---

## 2. Livello Dati

### 2.1 Database SQLite legacy

| Database | File | Tabelle principali | Righe appross. | Ruolo |
|---|---|---|---|---|
| `main` | `imi_internati.db` | `internati`, `fondi_archivistici`, `menzioni`, `decorati`, `entita`, `collegamenti`, `fonti_indice`, `archivio_documenti`, caduti vari | ~9.5M | Dati primari estratti da PDF, fonti interne, anagrafiche militari |
| `events` | `eventi_1gm.db` | `eventi_1gm`, `event_aliases`, `event_links`, `map_features` | ~892K | Eventi storici canonici, gerarchie, alias e link a fonti |
| `validazioni` | `validazioni_ai.db` | — | piccolo | Validazioni offline del modello AI |

I database SQLite restano la **sorgente primaria** per le ricerche in tempo reale e per le API legacy. Non vengono rinominati né cancellati.

### 2.2 Supabase / PostgreSQL — strato canonico

**Project URL:** `https://wyqesimzxieykmyhfvqs.supabase.co`

#### Schemi

| Schema | Scopo |
|---|---|
| `public` | Tabelle esistenti esposte a PostgREST (127+ tabelle) |
| `archive` | Entità archivistiche canoniche (repository, collection, item, rappresentazione, unità, testo, passaggio, chunk) |
| `evidence` | Collegamenti sospetti (`link_quarantine`) e valutazioni diritti (`rights_assessments`) |
| `ops` | Query di discovery, candidati, job queue, fetch cache |
| `ai` | Dataset ML, versioni, item, sorgenti, evaluation runs |
| `api_public` | View read-only sicure per il frontend pubblico |
| `legacy` | View di compatibilità sulle tabelle legacy SQLite migrate |

#### Tabelle principali (`archive`)

| Tabella | Scopo | Chiave stabile |
|---|---|---|
| `archive.repositories` | Istituti archivistici (ANRP, NARA, CWGC, Europeana, ...) | `stable_id` |
| `archive.collections` | Fondi / collezioni all'interno di un repository | `stable_id` |
| `archive.external_items` | Item descritti da provider esterni (documenti, record, schede) | `stable_id` + `UNIQUE(provider_code, external_id)` |
| `archive.external_item_revisions` | Versioni storiche dei metadati grezzi | — |
| `archive.representations` | Asset digitali (PDF, immagini, audio) con diritti e checksum | — |
| `archive.document_units` | Pagine / unità fisiche o digitali con locator IIIF | `unit_number` per representation |
| `archive.text_versions` | Versioni testuali (OCR provider, OCR locale, trascrizione, normalizzazione, traduzione) | — |
| `archive.passages` | Passaggi citabili all'interno di un testo | `stable_id` + `content_hash` |
| `archive.chunks` | Chunk per RAG/embedding | `chunk_index` per text_version |

#### Tabelle `evidence`

| Tabella | Scopo |
|---|---|
| `evidence.link_quarantine` | Collegamenti generati automaticamente che richiedono revisione umana |
| `evidence.rights_assessments` | Valutazioni diritti su item e rappresentazioni (accesso ai metadati, download, uso commerciale, training) |

#### Tabelle `ops`

| Tabella | Scopo |
|---|---|
| `ops.discovery_queries` | Cache delle query di ricerca federata |
| `ops.discovery_candidates` | Candidati trovati sui provider con score e decisione |
| `ops.job_queue` | Coda lavori con claim atomico (`FOR UPDATE SKIP LOCKED`) |
| `ops.fetch_cache` | Cache risposte HTTP con TTL |

#### Tabelle `ai`

| Tabella | Scopo |
|---|---|
| `ai.datasets` | Dataset ML canonici con licenza e provenance |
| `ai.dataset_versions` | Versioni immutabili con freeze hash |
| `ai.dataset_items` | Esempi di training/validation/test |
| `ai.dataset_item_sources` | Traccia della provenance di ogni esempio |
| `ai.evaluation_runs` | Run di valutazione sui modelli |

### 2.3 Collegamento tra i due mondi

```
┌─────────────────────┐         ┌──────────────────────────────────────┐
│  SQLite legacy      │         │  Supabase PostgreSQL canonical       │
│  imi_internati.db   │         │  schemas: archive, evidence, ops, ai │
│  eventi_1gm.db      │         │                                      │
└─────────┬───────────┘         └──────────────┬───────────────────────┘
          │                                      │
          │  database.py                         │  repository_layer.py
          │  get_conn() → SQLite o PostgreSQL    │  SupabaseBackend CRUD
          │  db_adapter.py (compat layer)        │  supabase_client.py
          │                                      │
          └──────────────┬───────────────────────┘
                         │
              ┌──────────┴──────────┐
              │  Pipelines Python   │
              │  ia_pipeline.py     │
              │  external_metadata  │
              │  rag_pipeline.py    │
              │  graph_service.py   │
              │  ai_runtime.py      │
              └─────────┬───────────┘
                        │
              ┌─────────┴──────────┐
              │  FastAPI app.py    │
              │  + frontend React  │
              └────────────────────┘
```

**Flusso dati tipico:**

1. La ricerca inizia su SQLite legacy (`database.py`, `rag_pipeline.py`) per massima velocità offline.
2. Quando si scopre una fonte esterna, il provider federato registra metadati in `archive.external_items` su Supabase.
3. La provenance, i diritti e i passaggi citabili vengono normalizzati nelle tabelle canoniche.
4. I link tra entità passano per `evidence.link_quarantine` fino a revisione umana.
5. I dataset per l'AI vengono congelati in `ai.dataset_versions` con hash anti-contaminazione.

---

## 3. Moduli e Responsabilità

### 3.1 `database.py` + `db_adapter.py`

- **Responsabilità:** connessione unificata a SQLite o PostgreSQL.
- **Logica:**
  - Se `DATABASE_URL` inizia con `postgresql://`, usa `psycopg2` tramite `PostgresConnection`.
  - Altrimenti usa `sqlite3` con WAL, cache, row factory.
  - `db_adapter.py` converte placeholder `?` in `%s`, AUTOINCREMENT → SERIAL, gestisce PRAGMA come no-op.
- **Uso:** tutti i moduli legacy e le pipeline usano `get_conn()`.

### 3.2 `supabase_client.py`

- **Responsabilità:** client HTTP REST/Storage per Supabase.
- **Funzioni estese (post-migrazione):**
  - `execute_sql(sql)` — esecuzione raw SQL via RPC `exec_sql`.
  - `insert_batch_schema(schema, table, rows, on_conflict)` — inserimento batch su schema qualificato.
  - `select_schema(...)` — SELECT con filtri PostgREST su schema qualificato.
  - `table_count_schema(...)`, `table_exists_schema(...)`.
  - `create_storage_bucket(...)`, `upload_file(...)`, `create_signed_url(...)`, `get_public_url(...)`.
- **Vincolo:** gli schemi `archive`, `evidence`, `ops`, `ai`, `api_public`, `legacy` devono essere aggiunti in **Supabase Dashboard > Settings > API > Exposed Schemas** affinché PostgREST li serva.

### 3.3 `repository_layer.py`

- **Responsabilità:** CRUD Python tipizzato per tutte le tabelle canoniche.
- **Entità:** `Repository`, `Collection`, `ExternalItem`, `Representation`, `DocumentUnit`, `TextVersion`, `Passage`, `Chunk`.
- **Backend:** `SupabaseBackend` che usa `supabase_client.insert_batch_schema`, `select_schema`, ecc.
- **Uso futuro:** sostituirà gli accessi diretti a `archivio_documenti` e `external_source_records` per i nuovi flussi.

### 3.4 `config/archive_providers.yml`

- Registro versionato di 27+ provider esterni.
- Campi: `capabilities`, `access_mode`, `rights`, `authority_score`, `contract_version`, `geographic_coverage`, `temporal_coverage`.
- Consumato da `source_providers/federation.py` e dall'audit iniziale.

---

## 4. Pipelines

### 4.1 Pipeline Internet Archive (`ia_pipeline.py`)

```
Discovery ──> Metadata ──> Evaluation ──> Asset Selection ──> Locator ──> Ingestion ──> Claim
```

| Fase | Modulo | Output |
|---|---|---|
| Discovery | `ia_pipeline.discover()` | `DiscoveryResult` con items IA filtrati per evento/conflitto |
| Metadata | `ProviderInternetArchive._get_metadata()` | JSON grezzo da archive.org |
| Evaluation | `ia_evaluation.evaluate_candidates()` | `CandidateEvaluation` (accepted/candidate/rejected) |
| Asset Selection | `ia_locator.select_best_asset()` | `AssetSelection` (PDF/DjVu/txt, URL, dimensioni) |
| Locator | `ia_locator.locate_passage()` | `PageLocator` con pagina, snippet, bounding box, confidenza |
| Ingestion | `archivio_documenti.upsert_documenti()` + repository layer | `archive.external_items`, `archive.representations`, `archive.text_versions`, `archive.passages` |
| Claim generation | `claim_service.create_claim()` + `add_evidence()` | `claims` + `claim_evidence` in SQLite, con riferimento a `passage_id` canonico |

**Collegamento canonical:** i metadati confermati vengono scritti nelle tabelle `archive` tramite `repository_layer.py`; i passaggi citabili ottengono `stable_id` e `content_hash`.

### 4.2 Pipeline Import Metadati Esterni (`external_metadata_service.py`)

- Adattatori: `ArchimistaAdapter`, `LeBIAdapter`.
- `run_import(provider, start_url, max_records, resume, batch_size)` esegue import incrementale con checkpoint.
- Idempotenza via `UNIQUE(provider, external_id)` e `metadata_hash`.
- Estrae menzioni di persone, fatti e oggetti digitali.

**Collegamento canonical:** in fase di integrazione, `upsert_record` e i metodi di parsing scriveranno in `archive.repositories`, `archive.collections`, `archive.external_items` anziché solo in `external_source_records`.

### 4.3 Pipeline RAG (`rag_pipeline.py`)

```
Query utente ──> FTS5 su SQLite ──> Metadata filters ──> Rerank ──> Context + Citations
```

- Retrieval ibrido su SQLite: tabelle `internati`, `caduti_*`, `menzioni`, `fonti_indice`, `archivio_documenti`, `eventi_1gm`.
- Reranking per qualità fonte, compatibilità temporale/geografica, indipendenza.
- Contesto strutturato con citazioni `[fonte: tabella#id]`.
- Non genera testo direttamente: chiama `ai_runtime.get_adapter().generate(...)`.

**Collegamento canonical:** i chunk prodotti da `archive.text_versions` / `archive.passages` alimenteranno una futura ricerca semantica ibrida (FTS + embedding). Gli embedding vengono memorizzati in `archive.chunks.embedding`.

### 4.4 Pipeline Grafi (`graph_service.py`)

- **Pattern:** read-through adapter.
- Legge 5 tabelle legacy di link (`record_links`, `event_links`, `collegamenti`, ecc.) e le presenta come `GraphNode` + `GraphEdge` con unico contratto al frontend.
- Nuove tabelle `graph_nodes`, `graph_edges`, `graph_edge_reviews` in `imi_internati.db` (fase precedente).
- Mantiene il sistema e l'id originale per ogni arco; non promuove automaticamente un candidato a fatto.

**Collegamento canonical:** i nodi/edge futuri potranno puntare a `archive.external_items` e `archive.passages` come fonti evidence.

### 4.5 AI Runtime (`ai_runtime.py` + `ai_runtime_api.py`)

- Interfaccia unificata `InferenceAdapter` con metodi:
  - `generate(system, user, ...)`
  - `generate_structured(system, user, ...)`
  - `embed(text, ...)`
  - `health()`
- Adapter disponibili:
  - `LMStudioAdapter` → endpoint OpenAI-compatible locale (Qwen/LM Studio).
  - `RemoteAdapter` → provider remoti.
  - `TestAdapter` → deterministici, per unit test.
- Configurazione in `config/ai_runtime.yaml`.
- API `/api/ai-runtime/health`, `/config`, `/benchmark`, `/reset`.

**Collegamenti dati:**
- Input: contesto `RAGContext` da `rag_pipeline.py`.
- Output: risposte strutturate validabili; token usage tracciato.
- Training: `ai.datasets` / `ai.dataset_versions` congelano i dati di training per Qwen LoRA, evitando leakage tra train e test.

### 4.6 Backfill Legacy → Canonical (`backfill_canonical.py`)

- 6 funzioni di backfill: eventi, item, repositories, claims, links, dataset.
- `--dry-run` verificato: 1,061,564 righe da migrare, 1,152 duplicate repository skipped.
- Idempotenza via `stable_id` / `content_hash`.
- Usa `supabase_client.insert_batch_schema(..., on_conflict="ignore")` oppure `execute_sql` per batch.

---

## 5. API principali (FastAPI in `app.py`)

| Gruppo | Endpoint chiave | Scopo |
|---|---|---|
| Fonti federate | `/api/source/stats`, `/api/source/reindex`, `/api/internati/{rid}/links` | Ricerca su provider esterni e salvataggio |
| Eventi canonici | `/api/canonical-events` | CRUD eventi con alias e gerarchia |
| Grafi | `/api/graph/entity/{table}/{id}`, `/api/graph/edges/{edge_id}/review` | Esplorazione relazioni e revisione |
| RAG | `/api/rag/retrieve`, `/api/rag/validate` | Recupero contesto e validazione output |
| Mappe | `/api/map-features` | Feature geografiche con provenance |
| AI runtime | `/api/ai-runtime/*` | Health, config, benchmark, reset |
| Admin canonical | *(da implementare)* | Revisione `link_quarantine`, claims, evidence |

---

## 6. Sicurezza

### 6.1 Row Level Security (RLS)

Tutte le tabelle canoniche hanno RLS attiva:

- `public_read_*`: accesso in lettura anonimo per record con `review_status IN ('confirmed', 'probable')` e `access_status = 'active'`.
- `service_write_*`, `service_update_*`, `service_all_*`: accesso completo solo al ruolo `service_role`.
- `evidence.link_quarantine`: accesso riservato a `service_role` e admin.

### 6.2 Diritti e licenze

- `evidence.rights_assessments` traccia per ogni item/rappresentazione:
  - `metadata_access`, `content_access`, `download_allowed`, `training_allowed`, `redistribution_allowed`, `commercial_use_allowed`, `attribution_required`.
- Il valore di default è `UNKNOWN`; le valutazioni vengono fatte dal compliance gate (`compliance_gate.py`) e possono essere sovrascritte da revisione umana.

### 6.3 Storage

- Bucket previsti:
  - `canonical-documents` — asset privati (PDF, immagini ad alta risoluzione), accesso tramite signed URL.
  - `canonical-public-thumbnails` — thumbnail pubblici.
- Ogni file ha `bucket_path` in `archive.representations`.
- Politiche: nessun bucket pubblico per documenti sensibili; solo thumbnail pubblici se i diritti lo permettono.

---

## 7. Local Qwen AI

### 7.1 Modello

- **Base:** `Qwen2.5-0.5B-Instruct`.
- **Fine-tuning:** LoRA su CPU, 75 chunk, loss finale ~3.9.
- **Endpoint:** LM Studio o server OpenAI-compatible locale (`http://localhost:1234/v1`).
- **Adapter:** `LMStudioAdapter` in `ai_runtime.py`.

### 7.2 Flusso di integrazione

```
Utente fa domanda
        │
        ▼
rag_pipeline.retrieve(query) ──> SQLite FTS5 + filtri
        │
        ▼
rag_pipeline.rerank() ──> score qualità, luogo, data
        │
        ▼
RAGContext con citazioni [fonte: tabella#id]
        │
        ▼
ai_runtime.generate_structured(system, user_context)
        │
        ▼
Risposta validata + citations
```

### 7.3 Training data governance

- Gli esempi di training non devono contaminare il test set.
- `ai.dataset_versions` è immutabile (`immutable = true`) e ha `freeze_hash`.
- `ai.dataset_item_sources` traccia la fonte originale di ogni esempio (es. `archive.passages#123`).
- Valutazioni in `ai.evaluation_runs`.

---

## 8. Flusso end-to-end: dalla scoperta alla citazione

```
1. Ricerca federata
   /api/source/reindex?q=Battaglia+di+Caporetto
        │
        ▼
2. ProviderInternetArchive.search() -> item IA candidati
        │
        ▼
3. ia_pipeline.discover() -> valutazione storica
        │
        ▼
4. ia_locator.select_best_asset() + locate_passage()
        │
        ▼
5. Conferma umana (admin)
        │
        ▼
6. Scrittura canonical:
   archive.repositories -> archive.collections -> archive.external_items
   -> archive.representations -> archive.document_units
   -> archive.text_versions -> archive.passages
        │
        ▼
7. Generazione claim:
   claim_service.create_claim() + add_evidence(passage_id=archive.passages.id)
        │
        ▼
8. Revisione link/claim in evidence.link_quarantine (admin)
        │
        ▼
9. Pubblicazione: api_public.events / api_public.sources_metadata (RLS)
```

---

## 9. Stato post-migrazione

### Completato

- [x] Schema SQL canonico applicato su Supabase (6 schemi, 21 tabelle, 40+ indici, RLS, trigger `updated_at`).
- [x] Funzioni helper PostgreSQL: `archive.generate_stable_id`, `archive.content_hash`, `archive.set_updated_at`.
- [x] `supabase_client.py` esteso per schemi multipli e Storage.
- [x] `repository_layer.py` con CRUD SupabaseBackend.
- [x] `backfill_canonical.py` pronto con `--dry-run` (1,061,564 righe identificate).
- [x] Provider registry `config/archive_providers.yml`.
- [x] ADR `docs/adr/ADR-Canonical-Archive-Supabase.md`.

### Da completare

- [ ] Aggiungere schemi `archive,evidence,ops,ai,api_public,legacy` agli **Exposed Schemas** di Supabase.
- [ ] Eseguire backfill reale su Supabase.
- [ ] Configurare bucket Storage e policy.
- [ ] Integrare `repository_layer.py` nelle pipeline esistenti (sostituire scritture legacy dove appropriato).
- [ ] Frontend admin per revisione `link_quarantine`, claims, evidence.
- [ ] Test di unità, integrazione, sicurezza RLS, regressione.

---

## 10. File chiave

| File | Scopo |
|---|---|
| `sql/001_supabase_historical_archive_core.sql` | DDL canonico completo |
| `supabase_client.py` | Client Supabase REST + Storage |
| `repository_layer.py` | CRUD Python per tabelle canoniche |
| `backfill_canonical.py` | Migrazione dati legacy |
| `config/archive_providers.yml` | Registro provider |
| `docs/adr/ADR-Canonical-Archive-Supabase.md` | Decisioni architetturali |
| `docs/architecture/canonical-historical-archive.md` | Audit pre-migrazione |
| `docs/architecture/complete-app-architecture-post-migration.md` | Questo documento |
| `apply_migration_v2.py` | Runner migrazione statement-by-statement |
