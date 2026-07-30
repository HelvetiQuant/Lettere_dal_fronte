# IMI Extractor — Architettura Tecnica Completa
## Sistema di Ricerca Storica su Eventi della Prima e Seconda Guerra Mondiale

**Versione documento**: 3.0  
**Data**: 2026-07-28  
**Scopo**: Documento di architettura per AI Architect — analisi completa di tutti i layer, dati, pipeline, API e infrastruttura.

---

## 1. Visione d'Insieme

IMI Extractor (aka "Voci dal Fronte" / "Lettere dal Fronte") è un sistema monolitico modulare in Python che:

1. **Estrae** dati da PDF OCR di elenchi di Internati Militari Italiani (IMI)
2. **Scrapa** fonti esterne (albi caduti, decorati, archivi nazionali)
3. **Collega** entità (persone, luoghi, eventi) tramite graph provenance
4. **Ricerca** eventi storici WW1/WW2 con pipeline di evidenza a 4 livelli
5. **Genera** narrazioni storiche con citazioni esplicite e validazione fonti
6. **Sincronizza** tutto su Supabase (PostgreSQL) come backend canonico

### Stack tecnologico

| Layer | Tecnologia |
|-------|-----------|
| Backend | Python 3.11, FastAPI 0.104, Uvicorn |
| Database locale | SQLite 3 (WAL mode, 3 DB separati) |
| Database remoto | Supabase (PostgreSQL 15, multi-schema) |
| Frontend | React 19, TypeScript 6, Vite 8, Leaflet |
| AI | Multi-provider: OpenAI, Mistral, Anthropic, Google Gemini, LM Studio (local) |
| HTTP client | httpx (async), requests (sync) |
| OCR | pdfplumber, PyMuPDF, Mistral Vision API |
| Auth | bcrypt, session-based, RBAC |

---

## 2. Topologia dei Database

### 2.1 SQLite Locale (3 database)

```
imi_internati.db     ← 1.8 GB — DB principale (persone, fonti, entità, collegamenti)
eventi_1gm.db        ← 248 MB — DB eventi Prima Guerra Mondiale + event_links
validazioni_ai.db    ← 94 KB  — DB validazioni AI
```

#### imi_internati.db — Tabelle principali

| Tabella | Scopo | Righe (approx) |
|---------|-------|----------------|
| `internati` | Record IMI estratti da PDF OCR | ~100K |
| `decorati` | Decorati (Albi della Memoria ISTORECO) | ~50K |
| `caduti_albooro` | Caduti Albo d'Oro | ~600K |
| `caduti_cwgc` | Caduti Commonwealth War Graves Commission | ~1.7M |
| `caduti_ministero` | Caduti Ministero Difesa | ~400K |
| `caduti_bologna` | Caduti bolognesi | ~12K |
| `caduti_sardi` | Caduti sardi | ~30K |
| `caduti_francia_ww1` | Caduti francesi WW1 | ~1.4M |
| `decorati_nastroazzurro` | Decorati Nastro Azzurro | ~20K |
| `fondi_archivistici` | Fondi USSME | ~5K |
| `menzioni` | Menzioni estratte dai fondi | ~50K |
| `entita` | Entità normalizzate (persone, luoghi, eventi) | ~200K |
| `collegamenti` | Link entità ↔ record | ~500K |
| `archivio_documenti` | Metadati documenti WW1 (foto, diari) | 979 |
| `fonti_risorse` | Catalogo metadati fonti esterne | ~10K |
| `fonti_narrative` | Fonti narrative importate | ~500 |
| `lettere_personali` | Lettere dal fronte | ~2K |
| `source_policies` | Policy compliance per dominio | ~30 |
| `ai_ricerche` | Log ricerche AI | ~1K |
| `graph_nodes` | Grafo canonico: nodi | ~300K |
| `graph_edges` | Grafo canonico: archi | ~1.5M |
| `graph_edge_reviews` | Review archi grafo | ~5K |
| `archival_metadata` | Metadata archivistico estensione | ~10K |

#### eventi_1gm.db — Schema

| Tabella | Scopo | Righe |
|---------|-------|-------|
| `eventi_1gm` | 49 eventi WW1 (Caporetto, Isonzo, Piave, ecc.) | 49 |
| `event_aliases` | Alias canonici eventi | ~150 |
| `event_links` | Link evento ↔ caduti/decorati/documenti/fonti | 1,539,685 |
| `map_features` | Feature geografiche eventi (GeoJSON) | ~200 |

### 2.2 Supabase (PostgreSQL) — Schema Canonico

Il progetto usa un **multi-schema PostgreSQL** su Supabase con 6 schemi:

```
public     ← Tabelle legacy migrate da SQLite (compatibilità)
archive    ← Archivio documentale canonico (repositories, collections, items, representations)
evidence   ← Quarantine link, rights assessments
ops        ← Discovery queries, job queue, fetch cache
ai         ← Datasets, versions, items, evaluation runs
api_public ← Viste pubbliche esposte via API
```

#### Schema `archive` (7 tabelle gerarchiche)

```
archive.repositories
  └─ archive.collections
       └─ archive.external_items
            ├─ archive.external_item_revisions
            ├─ archive.representations
            │    └─ archive.document_units
            │         └─ archive.text_versions
            │              ├─ archive.passages
            │              └─ archive.chunks (RAG embeddings, VECTOR(1536))
            └─ (links to evidence.rights_assessments)
```

#### Schema `evidence` (2 tabelle)

| Tabella | Scopo |
|---------|-------|
| `link_quarantine` | Link sospetti messi in quarantena per review |
| `rights_assessments` | Valutazione diritti per ogni external_item |

#### Schema `ops` (3 tabelle)

| Tabella | Scopo |
|---------|-------|
| `discovery_queries` | Query di discovery con cache e piano |
| `discovery_candidates` | Risultati discovery con score e decision |
| `job_queue` | Coda job asincroni (discovery, fetch, OCR, embed) |
| `fetch_cache` | Cache HTTP con ETag/Last-Modified |

#### Schema `ai` (4 tabelle)

| Tabella | Scopo |
|---------|-------|
| `datasets` | Dataset di training/eval |
| `dataset_versions` | Versioni frozen dei dataset |
| `dataset_items` | Item singoli (train/val/test split) |
| `dataset_item_sources` | Provenienza di ogni item |
| `evaluation_runs` | Run di valutazione modelli |

#### Sincronizzazione SQLite → Supabase

Il file `sync_ww1_to_supabase.py` implementa la sincronizzazione:
1. Crea tabelle `archivio_documenti` e `event_links` su Supabase (DDL)
2. Upsert batch di 500 righe via PostgREST API
3. Rate limiting 0.5s tra batch
4. `on_conflict="merge"` per archivio_documenti (upsert)
5. `on_conflict="ignore"` per event_links (no duplicati)

**Stato sync attuale**:
- `archivio_documenti`: 979 righe sincronizzate ✅
- `event_links`: 1.5M righe in corso (~4% al momento)

---

## 3. Architettura Backend

### 3.1 Entry point

```
app.py  ← 2,875 righe, FastAPI monolite
  ├── 10 router moduli inclusi
  ├── 163+ endpoint API
  ├── Lifespan: init_db, auth, schema, compliance, federation
  └── Thread locks per operazioni async (scrape, extract, link)
```

### 3.2 Router API (10 moduli)

| Router | File | Endpoint principali |
|--------|------|-------------------|
| Recognition Core | `rc_api.py` | `/api/rc/*` — dossier, riconoscimenti |
| Recognition Extended | `rc_api_ext.py` | `/api/rc/ext/*` — discovery, import, review |
| External Sources | `external_sources_api.py` | `/api/external-sources/*` — federated search |
| Research Engine | `research_engine_api.py` | `/api/research/v2/*` — orchestrator |
| Viewpoints | `viewpoints_api.py` | `/api/viewpoints/*` — sintesi punti di vista |
| Graph | `graph_api.py` | `/api/graph/*` — entity graph, edge review |
| Canonical Events | `event_canonical_api.py` | `/api/canonical-events/*` |
| RAG | `rag_api.py` | `/api/rag/retrieve`, `/api/rag/validate` |
| Map Features | `map_features_api.py` | `/api/map-features/*` |
| AI Runtime | `ai_runtime_api.py` | `/api/ai-runtime/*` — health, benchmark |
| Chat | `chat_api.py` | `/api/chat` — conversazione AI |

### 3.3 Moduli core

#### Pipeline di Evidenza (`event_evidence_pipeline.py` — 1,157 righe)

Pipeline a 4 livelli per ricerca storica:

```
Livello 1: Fonti interne
  ├── eventi_1gm.db (eventi, event_links)
  ├── archivio_documenti (documenti locali)
  └── fonti_indice (fonti catalogate)

Livello 2: Fonti archivistiche
  └── source_locator (indice locale, cached text)

Livello 3: Fonti istituzionali/accademiche (federated search)
  ├── NARA, USSME, Archivio di Stato
  ├── Europeana, Internet Archive, Gallica
  ├── Google Books, HathiTrust
  └── Mémoire des Hommes, IWM, TNA, SHD

Livello 4: Fonti web affidabili
  └── Solo dopo verifica (pagina, autore, data, URL, passaggio)
```

**Classificazione fonti**:
- `source_type`: `primaria` | `istituzionale` | `scientifico` | `web`
- `authority`: `archivio` | `banca_dati` | `studio` | `pagina_web`
- `verification_status`: `verificata` | `candidata` | `non_verificata`

**Estrazione claim**: Per ogni fonte, estrae claim verificabili (date, luoghi, reparti, operazioni, persone, conseguenze) con confidence e concordance.

#### Narrative Builder (`event_narrative_builder.py` — 610 righe)

Genera narrazione storica strutturata in 13 sezioni:
1. Inquadramento evento
2. Narrazione storica
3. Cronologia e fasi
4. Luoghi e spostamenti
5. Reparti e soggetti
6. Cause e conseguenze
7. Fatti concordanti (sintesi AI discorsiva)
8. Versioni divergenti
9. Elementi incerti
10. Fonti archivistiche
11. Fonti bibliografiche/web
12. Grafo relazioni
13. Persone collegate

**Regola fondamentale**: Nessuna frase fattuale senza riferimento a una fonte. La memoria generale AI non è mai usata come fonte.

#### RAG Pipeline (`rag_pipeline.py` — 476 righe)

```
1. Retrieval ibrido: FTS5 (BM25) + metadata filters
2. Reranking: source quality, temporal/geographic compatibility, independence
3. Context builder: contesto strutturato con citazioni [fonte: table#id]
4. Output validato: Pydantic schema, reject uncited claims
```

#### Research Orchestrator (`research_orchestrator.py` — 1,436 righe)

Ciclo agentico:
```
Plan → Retrieve → Extract → Resolve → Validate → Expand → Stop → Synthesize
```

Ogni passo è idempotente, osservabile, ripetibile, non distruttivo. L'AI non inventa risultati: ogni output proviene da una chiamata reale a uno strumento.

### 3.4 Source Federation Layer

#### Provider registry (`source_providers/federation.py`)

27 provider registrati, ognuno implementa `SourceProvider` (ABC):

| Provider | Classe | Fonte |
|----------|--------|-------|
| NARA | `ProviderNARA` | National Archives USA |
| Antenati | `ProviderAntenati` | Antenati.san.beniculturali.it |
| CWGC | `ProviderCWGC` | Commonwealth War Graves |
| WikiTree | `ProviderWikiTree` | WikiTree.com |
| Arolsen | `ProviderArolsen` | Arolsen Archives |
| Bundesarchiv | `ProviderBundesarchiv` | Archivio federale tedesco |
| SHD | `ProviderSHD` | Service Historique Défense FR |
| TNA-UK | `ProviderNationalArchivesUK` | National Archives UK |
| Europeana | `ProviderEuropeana` | Europeana.eu |
| Gallica | `ProviderGallica` | BnF Gallica |
| Internet Archive | `ProviderInternetArchive` | archive.org |
| Google Books | `ProviderGoogleBooks` | books.google.com |
| ABMC | `ProviderABMC` | American Battle Monuments |
| Library Canada | `ProviderLibraryCanada` | Library and Archives Canada |
| AWM | `ProviderAustralianWarMemorial` | Australian War Memorial |
| ArchivportalD | `ProviderArchivportalD` | Archivio federale tedesco |
| HathiTrust | `ProviderHathiTrust` | hathitrust.org |
| USSME | `ProviderUSSME` | Ufficio Storico SME |
| Archivio di Stato | `ProviderArchivioDiStato` | ACS |
| Mémoire des Hommes | `ProviderMemoireDesHommes` | Francia |
| DDB | `ProviderDDB` | Deutsche Digitale Bibliothek |
| IWM Lives | `ProviderIWMLives` | Imperial War Museum |
| Grand Memorial | `ProviderGrandMemorial` | Grand Memorial |
| ICRC WW1 | `ProviderICRCWW1` | CICR Croce Rossa |
| CRI Milano | `ProviderCRIMilano` | Croce Rossa Italiana Milano |
| LeBI | `ProviderLeBI` | Lessico Biografico IMI ANRP |

**Interfaccia `SourceProvider`** (ABC):
```python
search()           → cerca metadati nell'archivio remoto
get_metadata()     → metadati dettagliati per record
get_document()     → scarica documento (PDF/immagine)
get_iiif_manifest()→ manifest IIIF se disponibile
build_direct_link()→ URL diretto alla pagina/frame
```

**`FederatedSearchContext`** (dataclass tipizzata):
```python
subject_type: "event" | "person" | "unit" | "place" | "document" | ...
canonical_name: str
aliases: Tuple[str, ...]
conflict: "ww1" | "ww2" | "other" | "unknown"
start_date / end_date: Optional[date]
places, keywords, units, languages: Tuple[str, ...]
```

### 3.5 AI Layer

#### AI Runtime (`ai_runtime.py` — 322 righe)

Porta di inferenza comune con adapter intercambiabili:

```
InferenceAdapter (ABC)
  ├── LMStudioAdapter     ← OpenAI-compatible, CPU quantized (locale)
  ├── RemoteAdapter       ← delega ad ai_client.py (provider remoti)
  └── DeterministicTestAdapter ← no AI, per unit test
```

Metodi: `generate()`, `generate_structured()`, `embed()`, `health()`

#### AI Router (`ai_router.py` — 460 righe)

Router multi-modello con:
- **Circuit breaker**: 3 fallimenti → cooldown 5 min
- **Task types**: 15 tipi (resolve_input, generate_plan, extract_claims, compare_claims, ...)
- **Budget tracking**: crediti residui, costo stimato pre-task
- **Fallback ordinato**: LM Studio → Mistral → OpenAI → Anthropic → Gemini
- **Idempotency key** per task
- **Ledger consumi**

#### AI Client (`ai_client.py` — 18,792 righe)

Integrazione diretta con:
- OpenAI API (GPT-4, GPT-3.5)
- Mistral AI (Mistral Large, Mistral Medium)
- Anthropic Claude (Claude 3.5 Sonnet)
- Google Gemini (Gemini 2.0 Flash)
- LM Studio (locale, OpenAI-compatible)

### 3.6 Compliance Gate (`compliance_gate.py` — 486 righe)

Motore centralizzato di valutazione conformità. Nessun modulo scarica/pubblica/esporta senza passare di qui.

**Classificazioni risorsa**:
```
METADATA_ONLY | PUBLIC_VIEW | PUBLIC_DOWNLOAD | REQUEST_REQUIRED |
AUTHORIZATION_REQUIRED | RESTRICTED | RIGHTS_UNKNOWN | UNREACHABLE
```

**Azioni controllate**:
```
INDEX_METADATA | GENERATE_LINKS | DOWNLOAD_FILE | RUN_OCR |
EXTRACT_PERSONAL_DATA | SHOW_TO_AUTHENTICATED_USER | SHOW_PUBLICLY |
INCLUDE_IN_DOSSIER | EXPORT | DELETE | REFRESH_SOURCE
```

**Decisioni**: `ALLOW | ALLOW_WITH_LIMITATIONS | REQUIRE_REVIEW | REQUIRE_AUTHORIZATION | DENY`

### 3.7 Graph Service (`graph_service.py` — 884 righe)

Adattatore read-through dei sistemi di collegamento esistenti. Presenta un solo contratto al frontend ma conserva, per ogni arco, il sistema e l'identificativo originali.

**Tabelle legacy lette** (5 sistemi):
1. `collegamenti` (entità ↔ record)
2. `event_links` (eventi ↔ tutto)
3. `record_links` (record ↔ fonti)
4. `external_links` (record ↔ fonti esterne)
5. `link_quarantine` (link sospetti)

**Grafo canonico**:
- `graph_nodes`: nodi con namespace, type, label, source_table, source_id
- `graph_edges`: archi con relation, status, confidence, evidence, review
- `graph_edge_reviews`: review umane con decision (confirmed/rejected/superseded)
- `graph_integrity_issues`: issue automatici (severity: info/warning/error)

### 3.8 Database Registry (`database_registry.py` — 254 righe)

Registro canonico dei database e tabelle. Evita che ogni servizio reinventi percorsi e query dinamiche.

```python
TABLE_SPECS: dict[str, TableSpec] = {
    "internati": TableSpec("main", "persona", ("cognome", "nome"), ...),
    "caduti_albooro": TableSpec("main", "persona", ("nominativo",), ...),
    "eventi_1gm": TableSpec("events", "evento", ("nome",), ...),
    "archivio_documenti": TableSpec("main", "documento", ("title",), ...),
    ...
}
```

Le tabelle sono esplicitamente autorizzate: un valore dal DB non viene mai interpolato in SQL senza essere prima risolto nel registro.

### 3.9 Repository Layer (`repository_layer.py` — 442 righe)

CRUD canonico per le tabelle Supabase/PostgreSQL:
- `archive.repositories` → `Repository` dataclass
- `archive.collections` → `Collection` dataclass
- `archive.external_items` → `ExternalItem` dataclass
- `archive.representations` → `Representation` dataclass
- `archive.document_units` → `DocumentUnit` dataclass
- `archive.text_versions` → `TextVersion` dataclass
- `archive.passages` → `Passage` dataclass
- `archive.chunks` → `Chunk` dataclass

Usa `supabase_client` per REST API o `psycopg2` per connessione diretta. Fallback su SQLite per sviluppo.

---

## 4. Architettura Frontend

### 4.1 Stack

```
React 19 + TypeScript 6 + Vite 8
React Router 7 (BrowserRouter)
Leaflet 1.9 (mappe storiche)
Lucide React (icone)
```

### 4.2 Pagine (16 route)

| Route | Pagina | Scopo |
|-------|--------|-------|
| `/` | `HomePage` | Dashboard principale |
| `/esplora` | `ExplorePage` | Ricerca esplorativa |
| `/eventi` | `EventsPage` | Lista eventi WW1 |
| `/eventi/:eventName` | `EventDossierPage` | Dossier evento |
| `/ricerca-evento/:eventName` | `EventResearchPage` | Pipeline ricerca evento |
| `/ricerca` | `ResearchPage` | Orchestrator ricerca |
| `/ricerca/piani` | `ResearchPlansPage` | Piani di ricerca |
| `/ricerca/soggetti` | `ResearchSubjectsPage` | Soggetti ricerca |
| `/ricerca/lacune` | `ResearchGapsPage` | Lacune di ricerca |
| `/punti-di-vista` | `ViewpointsPage` | Sintesi punti di vista |
| `/collegamenti` | `HeuristicLinksPage` | Link euristici |
| `/grafo/:sourceTable/:sourceId` | `GraphEntityPage` | Grafo entità |
| `/chat` | `ChatPage` | Chat AI |
| `/riconoscimenti` | `RecognitionsPage` | Riconoscimenti |
| `/admin` | `AdminPage` | Admin panel |
| `/soldato/:type/:id` | `SoldierDossierPage` | Dossier soldato |

### 4.3 API Client (`frontend/src/api/client.ts` — 203 righe)

Single object `api` con ~60 metodi tipizzati. Tutte le chiamate passano attraverso `http.ts` con timeout configurabile.

### 4.4 Tipi TypeScript (`frontend/src/api/types.ts` — 836 righe)

Tipizzazione completa di tutti i DTO scambiati con il backend:
- `SearchResult`, `InternatoRecord`, `CadutoRecord`, `DecoratoRecord`
- `EventResolution`, `EvidencePackage`, `NarrativeReport`
- `CanonicalEvent`, `GraphEntityResponse`, `RAGContextResponse`
- `HistoricalMap`, `MapFeatureRecord`
- `AIRuntimeHealth`, `ChatResponseDTO`

---

## 5. Pipeline di Dati

### 5.1 Estrazione IMI

```
PDF OCR (Archivio Bolzano) → pdfplumber/PyMuPDF → estrazione strutturata
  → tabella `internati` (cognome, nome, grado, luogo_internamento, ...)
  → arricchimento con fonti esterne (LeBI, ICRC, CWGC)
```

### 5.2 Scraping fonti esterne

| Scraper | File | Fonte | Righe |
|---------|------|-------|-------|
| Albo d'Oro | `caduti_albooro.py` | cadutigrandeguerra.it | ~600K |
| CWGC | `caduti_cwgc.py` | cwgc.org | ~1.7M |
| Ministero Difesa | `caduti_ministero.py` | difesa.it | ~400K |
| Caduti Bologna | `caduti_bologna.py` | cadutibologna.it | ~12K |
| Caduti Sardi | `caduti_sardi.py` | cadutisardi.it | ~30K |
| Caduti Francia | `caduti_francia_ww1.py` | memoiredeshommes | ~1.4M |
| Nastro Azzurro | `decorati_nastroazzurro.py` | nastroazzurro.org | ~20K |
| NARA | `nara_catalog.py`, `nara_t315_ocr.py` | archives.gov | ~50K |
| Cimeetrincee | `scraper_cimeetrincee.py` | cimeetrincee.it | ~5K |

### 5.3 Document Retrieval WW1 (`search_ww1_documents.py`)

```
Per ogni evento WW1 (49 eventi):
  Per ogni query mirata (keyword + alias):
    1. Internet Archive API → diari, memorie, testi
    2. Europeana API → foto, documenti (con API key)
    3. Library of Congress API → stampe, fotografie
    4. Wikimedia Commons API → foto pubblico dominio
    5. Gallica BnF SRU API → documenti francesi
  → upsert in archivio_documenti (979 documenti)
  → link a eventi via keyword matching (1,068 link)
```

### 5.4 Event Linking

```
Per ogni evento in eventi_1gm:
  keyword + aliases + luogo → termini di ricerca (min 4 char)
  Per ogni documento in archivio_documenti:
    text = title + description + place + creator + date_text
    if term in text:
      INSERT INTO event_links (evento_id, target_id, link_type='documento',
        match_field='text_match', match_value=term, confidence=0.7-0.9)
```

### 5.5 Entity Resolution & Linking

```
extractor.py → estrae entità da PDF
linker.py → collega entità a record (cognome, nome, luogo, data)
enrich_entities.py → arricchisce con fonti esterne
entity_resolution.py → risolve omonimie e varianti
graph_service.py → proietta in grafo canonico
```

---

## 6. Infrastruttura Supabase

### 6.1 Configurazione

```env
SUPABASE_URL=https://wyqesimzxieykmyhfvqs.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
```

### 6.2 Client (`supabase_client.py` — 488 righe)

Funzioni principali:
- `execute_sql(sql)` → RPC `exec_sql` per DDL/DML arbitrario
- `insert_batch(table, rows, on_conflict)` → PostgREST bulk insert
- `insert_batch_schema(schema, table, rows)` → insert in schema non-public
- `table_exists_on_supabase(table)` → check esistenza tabella
- `select_schema(schema, table)` → SELECT con Accept-Profile
- `create_storage_bucket(name)` → Storage API
- `upload_file(bucket, path, file_path)` → upload file

### 6.3 Migrazione (`migrate_to_supabase.py` — 848 righe)

Pipeline completa:
```
--schema  → crea tabelle PostgreSQL da schema SQLite
--data    → migra righe (batch 500-1000, rate limit 80 req/min)
--indexes → crea indici PostgreSQL
--fts     → crea tsvector per full-text search
--rls     → configura Row Level Security
--verify  → verifica conteggi e integrità
--full    → tutto
```

Con checkpoint/resume, retry con batch ridotto, conversione tipi SQLite→PG.

### 6.4 Backfill Canonico (`backfill_canonical.py`)

6 funzioni di backfill idempotente:
1. `backfill_events` → eventi_1gm → archive.external_items
2. `backfill_items` → internati/caduti/decorati → archive.external_items
3. `backfill_repositories` → provider → archive.repositories
4. `backfill_claims` → claim_service → evidence schema
5. `backfill_links` → collegamenti → graph_edges
6. `backfill_datasets` → training data → ai.datasets

Dry-run verificato: 1,061,564 righe da migrare.

---

## 7. Sicurezza e Conformità

### 7.1 Auth (`auth.py` — 13,808 righe)

- Session-based con bcrypt password hashing
- RBAC: admin, operator, researcher, viewer
- `require_auth(request)` su ogni endpoint protetto
- `has_permission(role, permission)` per autorizzazioni granulari

### 7.2 RLS (Row Level Security)

SQL `04_rls_policies.sql` (16,874 bytes) configura RLS su ogni tabella canonica:
- `archive.*`: service_role full access, anon read solo su `review_status='confirmed'`
- `evidence.*`: service_role full, anon deny
- `ops.*`: service_role full, anon deny
- `ai.*`: service_role full, anon read su datasets pubblici

### 7.3 Compliance Gate

Ogni operazione su fonti esterne passa attraverso `compliance_gate.evaluate()`:
1. Recupera policy per dominio/provider
2. Valuta azione richiesta vs classificazione risorsa
3. Restituisce decision (ALLOW/DENY/REQUIRE_REVIEW)
4. Logga ogni decision in `compliance_decisions`

### 7.4 Rate Limiting

- Scraper: 10 req/min per dominio (`SCRAPER_MAX_REQUESTS_PER_MINUTE`)
- Supabase: 0.5s tra batch (sync script)
- Migration: 80 req/min con backoff automatico
- AI Router: circuit breaker 3 fail → 5 min cooldown

---

## 8. Mappe Storiche

### 8.1 Map Builder (`event_map_builder.py` — 40,427 righe)

Genera mappe SVG vettoriali per eventi:
- `MapLocation`: punti con lat/lon, ruolo, fase, fonti
- `MapLine`: linee (frontiere, trincee) con stile
- `MapMovement`: spostamenti (from→to) con data
- `MapPhase`: fasi temporali con colori
- `HistoricalMap`: composizione completa con bounding box, legend, sub-maps

### 8.2 Map Features (`map_schema.py`, `map_features_api.py`)

Tabella `map_features` con GeoJSON, provenienza e review:
- `feature_type`: location, line, movement, area
- `certainty`: confirmed, probable, approximate
- `review_status`: pending, confirmed, rejected
- `source_table` + `source_id`: provenienza

---

## 9. Configurazione

### 9.1 Environment (`.env`)

```env
DATABASE_URL=sqlite+aiosqlite:///lettere_fronte.db
SUPABASE_URL=https://wyqesimzxieykmyhfvqs.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...

OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
LM_STUDIO_API_URL=http://127.0.0.1:1234/v1/chat/completions

EUROPEANA_API_KEY=zaledenticie
HOST=127.0.0.1
PORT=8123
```

### 9.2 Server

```
Uvicorn su http://127.0.0.1:8123
Frontend dev: vite dev server (porta 5173)
```

---

## 10. Flusso End-to-End: Ricerca Evento

```
Utente: "Battaglia di Caporetto"
  │
  ▼
[Frontend] EventResearchPage.tsx
  │ GET /api/event-research/narrative?q=Battaglia di Caporetto&ai=true
  ▼
[Backend] app.py → event_research_engine.py
  │
  ├── event_resolver.py: resolve_event("Battaglia di Caporetto")
  │   → EventResolution { canonical: "Battaglia di Caporetto", id: 16, ... }
  │
  ├── event_evidence_pipeline.py: collect_evidence(event_id=16)
  │   │
  │   ├── _internal_sources() → eventi_1gm.db, archivio_documenti, event_links
  │   │   → 27 documenti collegati, 15 caduti, 8 decorati
  │   │
  │   ├── _archival_sources() → source_locator
  │   │   → fonti archivistiche locali
  │   │
  │   ├── _federated_sources() → federation.federated_search()
  │   │   → NARA, USSME, Europeana, Internet Archive, ...
  │   │   → 27 provider interrogati in parallelo
  │   │
  │   └── _web_sources() → provider web affidabili
  │       → Internet Archive (primaria, archivio)
  │       → Europeana, Gallica, LoC, Wikimedia
  │
  ├── _extract_claims() → Claim[] (date, luoghi, reparti, operazioni)
  ├── _analyze_concordances() → fatti concordanti, divergenti, incerti
  │
  ├── event_narrative_builder.py: build_narrative(evidence_package)
  │   ├── _build_concordant_synthesis() → AI sintesi discorsiva
  │   ├── 13 sezioni narrative con citazioni
  │   └── NarrativeReport completo
  │
  ├── graph_service.py: get_entity_network("eventi_1gm", 16)
  │   → nodi (caduti, decorati, documenti, fonti)
  │   → archi con evidence e review status
  │
  └── Response: NarrativeReport (JSON)
      │
      ▼
[Frontend] EventResearchPage.tsx
  ├── Tab: Narrazione (13 sezioni)
  ├── Tab: Fonti (archivistiche, bibliografiche, web)
  ├── Tab: Punti di vista (sintesi concordanti, divergenti)
  ├── Tab: Grafo (ForceGraph visualization)
  ├── Tab: Mappa (Leaflet + SVG)
  └── Tab: Persone collegate
```

---

## 11. File Inventory (moduli principali)

| File | Righe | Scopo |
|------|-------|-------|
| `app.py` | 2,875 | FastAPI entry point, 163+ endpoint |
| `database.py` | 1,443 | SQLite schema, CRUD, search |
| `event_evidence_pipeline.py` | 1,157 | Pipeline evidenza 4 livelli |
| `research_orchestrator.py` | 1,436 | Orchestrator agentico ricerca |
| `rc_api_ext.py` | 2,625 | API recognition extended |
| `event_map_builder.py` | 1,070 | Mappe storiche SVG |
| `graph_service.py` | 884 | Grafo provenance read-through |
| `migrate_to_supabase.py` | 848 | Migrazione SQLite→Supabase |
| `archivio_documenti.py` | 651 | Archivio documenti WW1 + fetcher |
| `event_narrative_builder.py` | 610 | Generazione narrazione storica |
| `rag_pipeline.py` | 476 | RAG retrieval+reranking+validation |
| `supabase_client.py` | 488 | Client Supabase REST API |
| `ai_router.py` | 460 | Router multi-modello AI |
| `repository_layer.py` | 442 | CRUD canonico Supabase |
| `compliance_gate.py` | 486 | Compliance gate centralizzato |
| `ai_runtime.py` | 322 | Interfaccia inference adapter |
| `database_registry.py` | 254 | Registro tabelle canoniche |
| `source_providers/base.py` | 498 | ABC SourceProvider + FederatedSearchContext |
| `source_providers/federation.py` | 245 | Registry 27 provider + search |
| `search_ww1_documents.py` | 294 | Ricerca documenti WW1 per evento |
| `sync_ww1_to_supabase.py` | 196 | Sync SQLite→Supabase |

---

## 12. Diagramma Architetturale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React 19)                                │
│  HomePage · ExplorePage · EventResearchPage · GraphEntityPage · ChatPage    │
│  SoldierDossierPage · AdminPage · ViewpointsPage · ResearchPage             │
│  API Client (60+ metodi tipizzati) · TypeScript types (836 righe)           │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTP (localhost:8123)
┌──────────────────────────────┴──────────────────────────────────────────────┐
│                        BACKEND (FastAPI + Uvicorn)                           │
│                                                                              │
│  ┌─── Router API (10 moduli) ────────────────────────────────────────────┐  │
│  │ rc_api · rc_api_ext · external_sources · research_engine · viewpoints │  │
│  │ graph_api · event_canonical · rag_api · map_features · ai_runtime     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─── Core Services ─────────────────────────────────────────────────────┐  │
│  │                                                                       │  │
│  │  Event Evidence Pipeline (4 livelli)                                  │  │
│  │    ├── Internal Sources (SQLite)                                      │  │
│  │    ├── Archival Sources (source_locator)                              │  │
│  │    ├── Federated Search (27 providers)                                │  │
│  │    └── Web Sources (verified)                                         │  │
│  │                                                                       │  │
│  │  Narrative Builder → 13 sezioni con citazioni                         │  │
│  │  RAG Pipeline → FTS5 + reranking + validation                         │  │
│  │  Research Orchestrator → Plan-Retrieve-Extract-Resolve-Validate       │  │
│  │  Graph Service → read-through 5 legacy link systems                   │  │
│  │  Compliance Gate → policy evaluation per ogni operazione              │  │
│  │  AI Router → multi-modello con circuit breaker e budget               │  │
│  │  AI Runtime → LM Studio / Remote / Test adapter                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─── Source Federation (27 providers) ──────────────────────────────────┐  │
│  │ NARA · CWGC · ICRC · LeBI · Europeana · IA · Gallica · LoC · USSME   │  │
│  │ Archivio Stato · TNA · SHD · Bundesarchiv · Arolsen · IWM · ABMC     │  │
│  │ WikiTree · Antenati · CRI Milano · Google Books · HathiTrust · ...   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  SQLite Locale   │ │   Supabase       │ │  AI Providers    │
│                  │ │  (PostgreSQL)    │ │                  │
│ imi_internati.db │ │  6 schemi:       │ │ OpenAI GPT-4     │
│  (1.8 GB)        │ │  archive         │ │ Mistral Large    │
│                  │ │  evidence        │ │ Claude 3.5       │
│ eventi_1gm.db    │ │  ops             │ │ Gemini 2.0       │
│  (248 MB)        │ │  ai              │ │ LM Studio (local)│
│                  │ │  api_public      │ │                  │
│ validazioni_ai   │ │  legacy          │ │                  │
│  (94 KB)         │ │                  │ │                  │
│                  │ │  RLS su ogni     │ │                  │
│ 75 tabelle       │ │  tabella         │ │                  │
│ 9.5M righe totali│ │  VECTOR(1536)    │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

---

## 13. Sync Supabase — Stato Attuale

### Completato

| Tabella | Righe locali | Righe sincronizzate | Status |
|---------|-------------|-------------------|--------|
| `archivio_documenti` | 979 | 979 | ✅ Completato |
| `eventi_1gm` | 49 | 49 | ✅ Completato |
| `event_aliases` | 161 | 161 | ✅ Completato |
| `map_features` | 0 | 0 | ✅ Vuota |

### In corso (background)

| Tabella | Righe locali | Righe sincronizzate | Status |
|---------|-------------|-------------------|--------|
| `event_links` | 1,539,685 | ~270K (18%) | ⏳ In corso |

### Schema canonico Supabase — APPLICATO ✅

Il file `sql/001_supabase_historical_archive_core.sql` (748 righe) è stato applicato al nuovo progetto Supabase `wyqesimzxieykmyhfvqs`:
- 6 schemi creati (archive, evidence, ops, ai, api_public, legacy) ✅
- 21 tabelle canoniche create ✅
- 40+ indici creati ✅
- RLS policies applicate (34 "already exists" = idempotenti) ✅
- Trigger `updated_at` creato ✅
- Funzioni utility (`generate_stable_id`, `content_hash`) create ✅
- Estensione `pgcrypto` abilitata ✅
- `VECTOR(1536)` skippata (richiede estensione `vector` da abilitare nel dashboard)

### Da sincronizzare

| Tabella | DB fonte | Righe | Priorità |
|---------|----------|-------|----------|
| `internati` | imi_internati.db | ~100K | Alta |
| `decorati` | imi_internati.db | ~50K | Alta |
| `caduti_albooro` | imi_internati.db | ~600K | Media |
| `caduti_cwgc` | imi_internati.db | ~1.7M | Media |
| `graph_nodes` | imi_internati.db | ~300K | Media |
| `graph_edges` | imi_internati.db | ~1.5M | Media |
| `entita` | imi_internati.db | ~200K | Bassa |
| `collegamenti` | imi_internati.db | ~500K | Bassa |

---

## 14. Roadmap Tecnica

### Immediato
1. ~~**Completare sync event_links** (1.5M righe, ~30 min ETA)~~ ⏳ In corso (18%)
2. ~~**Applicare schema canonico** `001_supabase_historical_archive_core.sql`~~ ✅ Completato
3. ~~**Sync tabelle eventi** (eventi_1gm, event_aliases, map_features)~~ ✅ Completato
4. **Eseguire backfill canonico** (`backfill_canonical.py`) per 1M+ righe
5. **Abilitare estensione `vector`** nel dashboard Supabase per RAG embeddings

### Breve termine
5. **Configurare RLS** sul nuovo progetto (`04_rls_policies.sql`)
6. **Creare Storage buckets** per thumbnail e rappresentazioni
7. **Estendere `supabase_client.py`** per multi-schema completo
8. **Integrare `repository_layer.py`** nelle pipeline esistenti

### Medio termine
9. **FTS tsvector** su PostgreSQL (`03_fts_tsvector.sql`)
10. **Vector embeddings** su `archive.chunks` per RAG semantico
11. **Job queue** attiva su `ops.job_queue` per task asincroni
12. **Frontend admin** per review link/claims/evidence

---

*Documento generato per AI Architect — 2026-07-28*
