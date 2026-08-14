# IMI Extractor — Architettura Tecnica Completa
## Sistema di Ricerca Storica su Eventi della Prima e Seconda Guerra Mondiale

**Versione documento**: 4.1  
**Data**: 2026-08-13  
**Scopo**: Documento di architettura per AI Architect — analisi completa di tutti i layer, dati, pipeline, API e infrastruttura.

**Changelog versione 4.1**:
- V7.8: Fix contaminazione cross-war (case sensitivity, name parsing, legacy fallback, war_period schema)
- V7.7: Frontend integration completa (ResearchPage, SoldierDossierPage, AdminPage)
- V7.6: Cross-Linking Sicuro con Reversibilità (audit table, 4.438 internati arricchiti)
- V7.5: OpenAI primary per report generation (gpt-4o + Mistral fallback)
- Aggiunta pipeline V7 (UnifiedResearchOrchestratorV7 — 9 stage)
- Aggiunta V7.3 Structural Correction (quarantine, identity, barriers, narration planner)
- Aggiunta V7.3-PERSON-FIX (schema registry, identity resolver, evidence-locked narrator)
- Aggiunta LeBI integration (166K record, 5 tabelle persona)
- Aggiunta Cross-Linking militare (caduti_ministero ← caduti_albooro, internati ← lebi_records)
- Aggiunta pipeline di ragionamento end-to-end (sezione 15)
- Aggiornamento file inventory con moduli V7/V7.3

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
| `internati` | Record IMI estratti da PDF OCR | 20.465 |
| `lebi_records` | Lessico Biografico IMI (ANRP) | 166.112 |
| `decorati_nastroazzurro` | Decorati Nastro Azzurro | 279.832 |
| `caduti_albooro` | Caduti Albo d'Oro | 342.555 |
| `caduti_cwgc` | Caduti Commonwealth War Graves Commission | 506.446 |
| `caduti_ministero` | Caduti Ministero Difesa (+cross-link militare) | 162.646 |
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

### 5.1b Cross-Linking Sicuro con Reversibilità (`cross_link_safe.py`)

Arricchimento dei record `internati` con dati militari e biografici da tabelle indipendenti, con tracciamento completo delle modifiche nella tabella `cross_link_audit`.

```
internati (20K, copertura campi molto bassa)
  ← cross-link con lebi_records (166K, dati completi al 65-99%)
  → Match SICURO: nome esatto + candidato unico + anno WWII plausibile (1895-1928)
  → 4.438 record arricchiti (21%)
  → 40.587 aggiornamenti campi (data_nascita, grado, reparto, campi, decesso, ...)

internati ← caduti_ministero (162K)
  → Match: nome esatto + anno di nascita coincidente
  → 13 record arricchiti

internati ← decorati_nastroazzurro (280K)
  → Match: nome esatto + anno decorazione 1940-1947
  → 353 record arricchiti (decorazione, arma)
```

**Audit table** (`cross_link_audit`): ogni modifica tracciata con `old_value`, `new_value`, `source_table`, `source_record_id`, `match_method`, `match_score`, `reverted`.

**Reversibilità**:
```bash
python cross_link_safe.py --audit    # Registra baseline pre-cross-link
python cross_link_safe.py --run      # Esegue cross-linking sicuro
python cross_link_safe.py --revert   # Reverte tutte le modifiche
python cross_link_safe.py --status   # Mostra stato audit
```

**Revert selettivo** (per tabella fonte o metodo match) via SQL diretto su `cross_link_audit`.

**Regole anti-mixing**:
- Solo nome esatto (cognome+nome), niente fuzzy
- Validazione anno WWII (1895-1928) filtra omonimi di altre epoche
- Solo campi vuoti popolati, nessuna sovrascrittura
- Candidato unico o singolo plausibile, niente ambiguità

**Schema aggiornato** (`person_source_schemas.py`):
- `internati`: 11 nuovi claim_fields (death_date, death_cause, death_place, burial_place, internment_camps, capture_front, return_date, decoration, decoration_year, death_year)

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

## 10. Flusso End-to-End: Ricerca Evento (Legacy V3)

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

### Moduli V7/V7.3 (pipeline corrente)

| File | Scopo |
|------|-------|
| `unified_orchestrator_v7.py` | 9-stage pipeline: PLAN→DISCOVER→FETCH→EXTRACT→RESOLVE→FUSE→VALIDATE→NARRATE→PERSIST |
| `semantic_query_plan.py` | SemanticQueryPlan, TargetSpec, ProviderRoute |
| `evidence_snapshot_v7.py` | EvidenceSnapshotV7 con source_lineage, independence_groups, provenance_chain |
| `v7_provider_adapters.py` | V7AdapterRegistry: LocalDbAdapter (5 tabelle), WebSearchAdapter, FederationAdapter |
| `v7_identity_model.py` | IdentityResolver: cluster-based, strong/weak identifiers, homonym rejection |
| `v7_fusion_engine.py` | FusionEngine: PRESERVE_CONTRADICTIONS, independence groups, source lineage |
| `v7_narrator.py` | NarratorV7: AI/deterministic, evidence-locked, hallucination check, dedup |
| `v7_event_aggregate.py` | EventOntology, AggregateDefinitionRegistry (7 definizioni) |
| `v7_security_audit.py` | LegacySecurityAuditor, ImportSafetyAuditor, KillSwitchVerifier |
| `v7_quarantine.py` | QuarantineManager: 1.7M link legacy quarantined |
| `person_source_schemas.py` | Schema registry: 5 tabelle persona, claim_fields, identity_fields, conflict_fields |
| `narration_planner_v73.py` | ClaimSelector, CoveragePlanner, NarrationPlanner, SemanticValidator |
| `domain_model_v73.py` | Canonical domain model: SourceArtifact, Entity, IdentityCandidate, Evidence, Claim |
| `text_matching_v73.py` | Word-boundary matching, specificity, OCR variants, alias matching |
| `barriers_v73.py` | Temporal barriers (WWI/WWII veto), geographic barriers (semantic roles) |
| `cross_link_military_data_v3.py` | Cross-linking: caduti_ministero←albooro (89K), internati←lebi (5.8K) |
| `v7_api.py` | 5 endpoint: /api/v7/health, capabilities, research, research/{id}, narrate |
| `adapters_v73.py` | Legacy endpoint adapters con feature flags (V73_CANONICAL_*) |

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
│  │  Conversational Follow-Up → OpenAI Chat Completions multi-turn        │  │
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

## 14. Pipeline V7 — UnifiedResearchOrchestratorV7

### 14.1 9-Stage Pipeline (V7.1+)

```
PLAN → DISCOVER → FETCH → EXTRACT → RESOLVE → FUSE → VALIDATE → NARRATE → PERSIST
```

**File**: `unified_orchestrator_v7.py`

| Stage | Scopo | Modulo |
|-------|-------|--------|
| PLAN | Costruisce SemanticQueryPlan con TargetSpec + ProviderRoute | `semantic_query_plan.py` |
| DISCOVER | Interroga LocalDbAdapter (5 tabelle persona) + WebSearchAdapter | `v7_provider_adapters.py` |
| FETCH | Recupera record completi da SQLite | `v7_provider_adapters.py` |
| EXTRACT | Estrae claim+provenance via `extract_claims_from_record()` | `person_source_schemas.py` |
| RESOLVE | IdentityResolver: cluster-based, strong/weak identifiers, homonym rejection | `v7_identity_model.py` |
| FUSE | FusionEngine: PRESERVE_CONTRADICTIONS, independence groups, source lineage | `v7_fusion_engine.py` |
| VALIDATE | OutputValidatorV7: hallucination check, evidence hash, payload validation | `v7_narrator.py` |
| NARRATE | NarratorV7: AI (GPT-4o) o deterministic fallback con provenance completa | `v7_narrator.py` |
| PERSIST | Salva EvidenceSnapshotV7 con provenance chain | `evidence_snapshot_v7.py` |

### 14.2 V7.3 Structural Correction

**Quarantine**: Tutti i 1.708.869 link legacy marcati `CANDIDATE` con `usable_as_evidence=0`. Solo link V7.3 approvati sono usabili.

**Barriere temporali**: WWI/WWII hard veto — nessun link cross-guerra.

**Barriere geografiche**: burial != event, death != capture, detention != event.

**Identity resolution**:
- Strong identifiers: data_nascita + luogo_nascita + matricola
- Medium identifiers: grado + reparto + paternita
- Weak identifiers: nome only → NEEDS_REVIEW
- Strong conflict → REJECTED_HOMONYM (claim mai combinati tra cluster)

**Narration planner** (`narration_planner_v73.py`):
- ClaimSelector: seleziona claim per identity cluster, mai mescola candidati
- CoveragePlanner: PERSON (tutti campi biografici), EVENT (10 dimensioni stratificate)
- SemanticValidator: contraddizioni, homonym leakage, temporal, geographic
- GlobalValidator: evidence, certainty, hallucination detection

### 14.3 V7.3-PERSON-FIX

**Schema registry** (`person_source_schemas.py`): 5 tabelle persona con mapping claim_fields, identity_fields, conflict_fields, war_period, authority_tier.

| Tabella | War Period | Claim Fields | Authority |
|---------|-----------|-------------|----------|
| `lebi_records` | WWII | 18 | 1 |
| `internati` | WWII | 14 (con cross-link: grado, reparto, arma) | 1 |
| `caduti_albooro` | WWI | 9 | 1 |
| `caduti_ministero` | WWII | 13 (con cross-link: grado, reparto, death_*) | 1 |
| `decorati_nastroazzurro` | Variabile | 3 | 1 |

**Narrator evidence-locked**:
- Payload validato con `_validate_payload()` + `_compute_evidence_hash()`
- Post-gen hallucination check: `_post_gen_hallucination_check()`
- Circuit breaker: 3 fallimenti AI → deterministic fallback
- AI non decide identità — solo backend

### 14.4 Anti-Duplicazione Narrativa

**Prompt-level**: Istruzioni esplicite anti-duplicazione nel system prompt del narrator.

**Renderer-level**: Deduplication in `v7_narrator.py` con token overlap e shared n-grams:
- Sentenze duplicate rilevate via Jaccard similarity su token sets
- N-gram overlap (3-gram) per frasi semanticamente simili
- Rimozione automatica di frasi duplicate prima dell'output

**Ambiguous identity blocking**: Quando `AMBIGUOUS_IDENTITY` con cluster conflittuali → fallback deterministico (no AI narration) per evitare mixing di claim da cluster diversi.

---

## 15. Pipeline di Ragionamento End-to-End

### 15.1 PERSON_LOOKUP — Flusso completo

```
Utente: "GUSTINELLI ANNIBALE"
  │
  ▼
[1] PLAN — semantic_query_plan.py
  │ TargetSpec(name="GUSTINELLI ANNIBALE", intent=PERSON_LOOKUP)
  │ ProviderRoute: LocalDbAdapter (5 tabelle) + WebSearchAdapter (fallback)
  │
  ▼
[2] DISCOVER — v7_provider_adapters.py: LocalDbAdapter
  │ Query 5 tabelle in parallelo:
  │   SELECT * FROM lebi_records WHERE cognome='GUSTINELLI' AND nome LIKE 'ANNIBALE%'
  │   SELECT * FROM internati WHERE cognome='GUSTINELLI' AND nome LIKE 'ANNIBALE%'
  │   SELECT * FROM caduti_ministero WHERE cognome='GUSTINELLI' AND nome LIKE 'ANNIBALE%'
  │   SELECT * FROM caduti_albooro WHERE nominativo LIKE '%GUSTINELLI ANNIBALE%'
  │   SELECT * FROM decorati_nastroazzurro WHERE cognome='GUSTINELLI' AND nome LIKE 'ANNIBALE%'
  │ → Observations: [{table, record_id, cognome, nome, ...}, ...]
  │
  ▼
[3] FETCH — Recupero record completi
  │ Per ogni observation: SELECT * FROM {table} WHERE id={record_id}
  │ → Record completi con tutti i campi (inclusi cross-link militari)
  │
  ▼
[4] EXTRACT — person_source_schemas.py: extract_claims_from_record()
  │ Per ogni record, per ogni claim_field nello schema:
  │   raw_value = record[col_name]
  │   normalized, status, note = validate_and_normalize_value(predicate, raw_value)
  │   if status != skipped:
  │     claim = {predicate, value_raw, value_normalized, source_id, table, record_id}
  │ → Claims: [{predicate: birth_date, value: 1912-04-12}, {predicate: rank, value: Soldato}, ...]
  │
  ▼
[5] RESOLVE — v7_identity_model.py: IdentityResolver
  │ 5a. Cluster creation:
  │   Per ogni observation, crea IdentityCandidate con:
  │   - strong_ids: data_nascita + luogo_nascita + matricola
  │   - medium_ids: grado + reparto + paternita
  │   - war_period: dallo schema della tabella
  │
  │ 5b. Cluster matching:
  │   Per ogni pair di candidates:
  │   - Se strong_ids match → stesso cluster
  │   - Se strong_ids conflict → REJECTED_HOMONYM
  │   - Se solo name match → NEEDS_REVIEW (no merge)
  │
  │ 5c. Status assignment:
  │   - 1 cluster, 0 homonyms → RESOLVED_IDENTITY
  │   - 1 cluster, N homonyms → RESOLVED_IDENTITY (homonyms rejected)
  │   - 2+ clusters, no conflict → AMBIGUOUS_IDENTITY (multiple candidates)
  │   - 2+ clusters with conflicting claims → AMBIGUOUS_IDENTITY_CONFLICTING
  │
  │ → IdentityResult: {status, clusters: [{id, claims, observations}], rejected_homonyms}
  │
  ▼
[6] FUSE — v7_fusion_engine.py: FusionEngine
  │ Per ogni cluster:
  │   6a. Dedup claims per (predicate, value_normalized)
  │   6b. Group by independence_group (same source = dependent)
  │   6c. Corroboration:
  │     - 2+ independent sources same value → VERIFIED (confidence 0.9+)
  │     - 1 source, authoritative → ASSERTED (confidence 0.85)
  │     - 1 source, non-authoritative → PROBABLE (confidence 0.7)
  │     - Conflicting values → CONFLICTING (preserved, not resolved)
  │   6d. Source lineage groups: track provenance chain
  │ → FusedClaims: [{predicate, value, status, confidence, evidence_ids, sources}]
  │
  ▼
[7] VALIDATE — v7_narrator.py: pre-narration checks
  │ 7a. Check identity status:
  │   - RESOLVED_IDENTITY → proceed to AI narration
  │   - AMBIGUOUS_IDENTITY_CONFLICTING → block AI, use deterministic
  │   - AMBIGUOUS_IDENTITY (no conflict) → proceed with caution
  │
  │ 7b. Build evidence payload:
  │   - Claims from resolved cluster only (never mix clusters)
  │   - Context claims (provenance, source URLs)
  │   - Evidence hash for post-gen validation
  │
  │ 7c. Circuit breaker check:
  │   - If 3 AI failures in window → skip AI, use deterministic
  │   - If AI provider unavailable → deterministic fallback
  │
  ▼
[8] NARRATE — v7_narrator.py: NarratorV7
  │ 8a. AI Narration path (GPT-4o):
  │   - System prompt: anti-duplication instructions, evidence-locked
  │   - User prompt: structured claims with values, provenance
  │   - Schema: OpenAI structured output (narration_models.py)
  │   - Post-gen checks:
  │     _post_gen_hallucination_check(): verify no invented facts
  │     _validate_payload(): verify all claims present in evidence
  │   - Deduplication: token overlap + n-gram similarity → remove duplicates
  │
  │ 8b. Deterministic fallback:
  │   - ReportRenderer: structured markdown with APPROVED/PROBABLE/CONFLICTING sections
  │   - All claims with provenance, no AI invention
  │   - Omonimi respinti listed with rejection reasons
  │   - Gap condizionali listed (missing fields)
  │
  │ → NarrationResult: {answer_markdown, used_claim_ids, omitted_claims, provider, model}
  │
  ▼
[9] PERSIST — evidence_snapshot_v7.py
  │ Save EvidenceSnapshotV7:
  │   - snapshot_id, timestamp, target_name, intent
  │   - person_claims, context_claims
  │   - identity_status, resolved_cluster_id
  │   - candidate_identities, rejected_homonyms
  │   - provider_ledger (observations per provider)
  │   - narration_result (answer, used/omitted claims)
  │   - schema_version, narrator_contract
  │ → Persisted to SQLite + optional Supabase sync
```

### 15.2 EVENT_LOOKUP — Flusso completo

```
Utente: "Battaglia di Caporetto"
  │
  ▼
[1] PLAN → TargetSpec(name="Caporetto", intent=EVENT_LOOKUP)
  │
  ▼
[2] DISCOVER → eventi_1gm.db (49 eventi) + event_aliases (161 alias)
  │ → EventResolution: {canonical: "Battaglia di Caporetto", id: 16}
  │
  ▼
[3-4] FETCH + EXTRACT → archivio_documenti + event_links + fonti_indice
  │ → Claims: date, luoghi, reparti, operazioni, conseguenze
  │
  ▼
[5] RESOLVE → Event identity è deterministica (49 eventi canonici)
  │ → Temporal filter: WWI events only accept WWI sources
  │ → Geographic filter: burial != event, death != capture
  │
  ▼
[6] FUSE → Claim corroboration con independence groups
  │ → 10 dimensioni stratificate: cronologia, geografia, reparti, perdite, cause, conseguenze
  │
  ▼
[7] VALIDATE → CoveragePlanner: critical/important/minor gaps
  │
  ▼
[8] NARRATE → 13 sezioni narrative con citazioni esplicite
  │ → AI sintesi discorsiva per fatti concordanti
  │ → Versioni divergenti preservate (no AI resolution)
  │
  ▼
[9] PERSIST → EvidenceSnapshotV7 + graph projection
```

### 15.3 AGGREGATE_QUERY — Flusso completo

```
Utente: "Quanti internati per campo?"
  │
  ▼
[1] PLAN → TargetSpec(intent=AGGREGATE_QUERY, definition_id="camp_count")
  │
  ▼
[2-4] DISCOVER+FETCH+EXTRACT → AggregateDefinitionRegistry (7 definizioni)
  │ → Esecuzione deterministica (AI non inventa definizioni)
  │
  ▼
[5-6] RESOLVE+FUSE → Group by campo, count internati, sort desc
  │ → 50 campi, top: Berlino (384), Amburgo (215), ...
  │
  ▼
[7-9] VALIDATE+NARRATE+PERSIST → Tabella + grafico + narrazione
```

---

## 16. Roadmap Tecnica

### Completato (V7/V7.3/V7.8)
- ✅ V7.1 Pipeline refactor (12 fasi, 26 test, 16/16 acceptance)
- ✅ V7.3 Structural Correction (6 fasi, 160 test, quarantine + barriers)
- ✅ V7.3-PERSON-FIX (14 task, 43 test, schema registry + identity resolver)
- ✅ V7.5 OpenAI primary per report generation (gpt-4o + Mistral fallback)
- ✅ V7.6 Cross-Linking Sicuro (4.438 internati arricchiti, audit table reversibile)
- ✅ V7.7 Frontend integration (ResearchPage, SoldierDossierPage, AdminPage)
- ✅ V7.8 Fix contaminazione cross-war (6 root cause, case sensitivity + name parsing + legacy fallback + war_period schema)
- ✅ LeBI integration (166K record, 5 tabelle persona)
- ✅ Cross-linking militare (89K caduti_ministero + 5.8K internati arricchiti)
- ✅ Anti-duplicazione narrativa (prompt + renderer + ambiguous blocking)
- ✅ Supabase parity check (6/8 tabelle OK)

### Immediato
1. **Eseguire backfill canonico** (`backfill_canonical.py`) per 1M+ righe
2. **Abilitare estensione `vector`** nel dashboard Supabase per RAG embeddings
3. **Sync cross-link militare** su Supabase (89K + 5.8K record aggiornati)
4. **Migliorare matching internati↔lebi** (14.6K ancora senza match)

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

*Documento generato per AI Architect — 2026-08-13 (v4.1)*
