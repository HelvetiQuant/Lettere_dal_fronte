# AI Historical Integration — Baseline Audit

**Data:** 2026-07-25  
**Branch:** `devin/ai-storica-eventi-mappe`  
**Commit base SHA:** `a7e6231f9c3cdea64b24da43bda06b1d8e9c3778`

---

## 1. Struttura del repository

### 1.1 Backend

- **Framework:** FastAPI 0.104.1 + Uvicorn 0.24.0
- **Linguaggio:** Python 3.12+
- **Entry point:** `app.py` (107KB, ~2800 righe, 162 endpoint)
- **Router moduli:** `rc_api.py`, `rc_api_ext.py`, `external_sources_api.py`, `research_engine_api.py`, `viewpoints_api.py`
- **Avvio:** `python -m uvicorn app:app --host 0.0.0.0 --port 8001`
- **Porta backend:** 8001

### 1.2 Frontend

- **Framework:** React 19 + TypeScript + Vite
- **Routing:** React Router (15 route)
- **Porta dev server:** 5173
- **Proxy:** `/api` → `http://127.0.0.1:8001`
- **Path alias:** `@` → `./src`

### 1.3 Route frontend

| Path | Componente | Descrizione |
|---|---|---|
| `/` | `HomePage` | Home page |
| `/esplora` | `ExplorePage` | Esplora dataset |
| `/eventi` | `EventsPage` | Lista eventi |
| `/eventi/:eventName` | `EventDossierPage` | Dossier evento (legacy) |
| `/ricerca-evento/:eventName` | `EventResearchPage` | Dossier evento (nuova pipeline) |
| `/ricerca` | `ResearchPage` | Ricerca AI |
| `/ricerca/piani` | `ResearchPlansPage` | Piani di ricerca |
| `/ricerca/soggetti` | `ResearchSubjectsPage` | Soggetti di ricerca |
| `/ricerca/lacune` | `ResearchGapsPage` | Lacune di ricerca |
| `/punti-di-vista` | `ViewpointsPage` | Punti di vista |
| `/collegamenti` | `HeuristicLinksPage` | Collegamenti euristici |
| `/riconoscimenti` | `RecognitionsPage` | Riconoscimenti |
| `/admin` | `AdminPage` | Amministrazione |
| `/soldato/:type/:id` | `SoldierDossierPage` | Dossier persona |
| `*` | `NotFoundPage` | 404 |

---

## 2. Database

### 2.1 Database file

| File | Size | Descrizione |
|---|---|---|
| `imi_internati.db` | 1789.64 MB | DB principale |
| `eventi_1gm.db` | 137.57 MB | DB eventi |
| `validazioni_ai.db` | 0.09 MB | DB validazioni (200 FK issues) |
| `imi_extractor.db` | 0 MB | DB vuoto/legacy |

### 2.2 Tabelle principali — `imi_internati.db`

**Integrity check:** `ok`  
**FK issues:** 25 (tabella `research_subject_sources` → `fonti_indice` con fkid=0)  
**Tabelle:** 68 (incluse FTS)  
**Indici:** 6

| Tabella | Rows | Note |
|---|---|---|
| `internati` | 20,465 | Archivio di Stato di Bolzano |
| `decorati` | 1,286 | Albi della Memoria ISTORECO |
| `decorati_nastroazzurro` | 9,832 | Nastro Azzurro |
| `entita` | 68,739 | Entità estratte cross-dataset |
| `record_links` | 169,184 | Collegamenti legacy (tutti candidate, tutti legacy_unverified) |
| `fonti_indice` | 35,664 | Fonti indicizzate |
| `fonti_narrative` | 40 | Fonti narrative personali |
| `fondi_archivistici` | 4,808 | Fondi Ufficio Storico SME |
| `lettere_personali` | 1 | Lettere dal fronte OCR |
| `menzioni` | 10,976 | Menzioni in fondi |
| `documenti_nara_t315` | 1,153 | Documenti NARA T315 |
| `documenti_nara_catalog` | 272 | Catalogo NARA |
| `claims` | 40 | Affermazioni atomiche (fact_extractor) |
| `claim_evidence` | 505 | Evidenze per claim |
| `external_source_records` | 1 | Record fonti esterne |
| `external_person_mentions` | 0 | Menzioni persona esterne |
| `external_record_links` | 0 | Collegamenti record esterni |
| `edge_evidence` | 0 | Evidenze archi grafo (vuoto) |
| `edge_versions` | 0 | Versioni archi grafo (vuoto) |
| `event_links` | 0 | Event links in main DB (vuoto) |
| `eventi_1gm` | 15 | Eventi in main DB (duplicati eventi_1gm.db?) |
| `rc_candidates` | 83 | Candidati riconoscimento |
| `rc_sources` | 80 | Fonti riconoscimento |
| `rc_recognition_assessments` | 50 | Valutazioni riconoscimento |
| `research_subjects` | 118 | Soggetti di ricerca |
| `research_plans` | 45 | Piani di ricerca |
| `research_gaps` | 472 | Lacune di ricerca |
| `research_subject_sources` | 1,431 | Fonti per soggetto (25 FK issues) |

### 2.3 Tabelle — `eventi_1gm.db`

**Integrity check:** `ok`  
**FK issues:** 0

| Tabella | Rows | Note |
|---|---|---|
| `eventi_1gm` | 22 | Eventi (16 WWI + 6 WWII mescolati) |
| `event_links` | 891,874 | Collegamenti evento-soldato/fonte |

### 2.4 FTS tables

- `idx_entita_search` (FTS5 su entita, 68,739 docs)

### 2.5 Graph schema tables

**NON presenti** nel DB principale:
- `graph_nodes` — NOT FOUND
- `graph_edges` — NOT FOUND
- `graph_edge_reviews` — NOT FOUND
- `graph_pipeline_runs` — NOT FOUND
- `graph_integrity_issues` — NOT FOUND
- `archival_metadata` — NOT FOUND

Queste tabelle esistono solo nel refactor (`Lettere_dal_fronte-refactor-completo/.../graph_schema.py`).

---

## 3. Endpoint backend (162 totali)

### 3.1 Endpoint principali in `app.py`

**Search:**
- `GET /api/search` — ricerca cross-dataset
- `GET /api/search/ww1` — ricerca WW1
- `GET /api/search-validated` — ricerca con validazione
- `GET /api/conv-search` — alias search
- `POST /api/search/confirm` — conferma correzione

**Events:**
- `GET /api/events/1gm` — lista eventi
- `GET /api/events/1gm/{eventName}` — dossier evento
- `GET /api/events/1gm/{eventName}/caduti` — caduti evento
- `GET /api/events/1gm/{eventName}/decorati` — decorati evento
- `GET /api/events/{eventName}/internati` — internati evento
- `POST /api/event/report/{tab}` — report AI per tab

**Event Research Pipeline (nuova):**
- `GET /api/event-research/resolve` — risoluzione evento
- `GET /api/event-research/evidence` — evidenze
- `GET /api/event-research/narrative` — narrazione
- `GET /api/event-research/map` — mappa storica
- `GET /api/event-research/map/svg` — SVG mappa
- `GET /api/event-research/audit` — audit collegamenti
- `GET /api/event-research/audit/{eventId}` — audit per evento

**AI Research:**
- `POST /api/ai-research` — ricerca AI (gpt/mistral/perplexity/claude/all)
- `GET /api/ai-research/history` — storico ricerche

**Viewpoints:**
- `POST /api/viewpoints/create` — confronto fonti (nuovo)

**Entità/Collegamenti:**
- `GET /api/entita` — stats
- `GET /api/entita/search` — ricerca entità
- `GET /api/entita/{id}` — dettaglio entità
- `POST /api/entita/build` — build entità
- `POST /api/entita/stop` — stop build

**Internati:**
- `GET /api/internati/{id}/detail` — dettaglio
- `GET /api/internati/{id}/fonti` — fonti
- `GET /api/internati/{id}/links` — collegamenti
- `GET /api/internati/{id}/opengraph` — open graph

**Fonti:**
- `GET /api/fondi` — lista fondi
- `GET /api/fonti-risorse` — risorse esterne
- `GET /api/source/stats` — statistiche fonti

**External Sources:**
- `GET /api/icrc/search` — ICRC WW1
- `GET /api/icrc/filters` — filtri ICRC
- `POST /api/lebi/search` — LeBI
- `GET /api/lebi/record/{id}` — record LeBI
- `GET /api/lebi/compare/{soldierId}` — confronto LeBI
- `GET /api/nara` — NARA
- `POST /api/nara/enrich` — NARA enrich

**Research Orchestrator V2:**
- `POST /api/research/v2/create` — crea piano
- `GET /api/research/v2/plan/{id}` — piano
- `GET /api/research/v2/plans` — lista piani
- `POST /api/research/v2/locator/validate` — valida locator
- `POST /api/research/v2/preflight` — preflight

**Graph:**
- `GET /api/graph/luoghi` — grafo luoghi
- `GET /api/graph/mesi` — grafo mesi
- `GET /api/graph/paesi` — grafo paesi
- `GET /api/graph/soldati/architecture` — architettura
- `GET /api/graph/soldati/clusters` — cluster soldati

**Routers:**
- `rc_router` (49 endpoint) — riconoscimenti
- `rc_ext_router` (54 endpoint) — riconoscimenti estesi
- `external_sources_router` (14 endpoint) — fonti esterne
- `research_engine_router` (35 endpoint) — research engine
- `viewpoints_router` (1 endpoint) — punti di vista

---

## 4. Audit legacy issues

### 4.1 `record_links` — 169,184 righe

| Issue | Valore |
|---|---|
| `evidence_json` NULL | 169,184/169,184 (100%) |
| `match_status` | tutti `candidate` |
| `algorithm_version` | tutti `legacy` |
| `legacy_unverified` | tutti `1` |
| `review_status` | tutti `pending` |

**Link types:**
- `stesso_evento_luogo`: 142,594 (84.3%)
- `stesso_anno_decorazione`: 11,222 (6.6%)
- `fonte_personale`: 9,546 (5.6%)
- `documento_evento`: 5,822 (3.4%)

**Tutti i link sono legacy, senza evidenze, senza algoritmo versionato.**

### 4.2 `event_links` (eventi_1gm.db) — 891,874 righe

| Link type | Count |
|---|---|
| `soldato_decorato` | 688,607 |
| `soldato_caduto` | 188,791 |
| `internato_ww2` | 12,759 |
| `fonte_archivistica` | 1,703 |
| `documento` | 13 |
| `soldato_caduto_cwgc` | 1 |

**Nessuna colonna `evidence` nella tabella event_links.**

### 4.3 `eventi_1gm` — 22 eventi (WWI + WWII mescolati)

**Eventi WWI (16):**
- Battaglia di Caporetto, Battaglie dell'Isonzo, Battaglia del Carso, Battaglia del Piave, Battaglia di Vittorio Veneto, Altopiano di Asiago, Monte Grappa, Monte Pasubio, Monte San Michele, Prigionia, Fronte Macedone, Fronte Albanese, Monte Col di Lana, Monte Nero, Settore di Tolmino

**Eventi WWII (6) — NON dovrebbero essere in `eventi_1gm`:**
- Operazione Achse (1943-1945)
- Eccidio di Cefalonia (1943)
- Campagna di Russia ARMIR (1941-1943)
- Battaglia di Tobruk (1941-1942)
- Mauthausen e Gusen (1943-1945)
- Lavoro forzato nel Reich (1943-1945)
- Battaglia di Cassino (1944)

### 4.4 `validazioni_ai.db` — 200 FK issues

La tabella `record_link_validations` ha 200 righe con FK issues verso tabelle non specificate.

### 4.5 Graph schema

Le tabelle del grafo canonico (`graph_nodes`, `graph_edges`, `graph_edge_reviews`, ecc.) **non esistono** nel DB principale. Esistono solo nello script `graph_schema.py` nel refactor. L'integrazione deve creare queste tabelle.

### 4.6 Claims/claim_evidence

- `claims`: 40 righe (tutte per internato 22808 Gaiaschi Luigi, create da `fact_extractor`)
- `claim_evidence`: 505 righe (evidenze estratte da campi DB)
- `extraction_method`: `db_field_mapping`
- `review_status`: `proposed`

---

## 5. Provider AI e configurazione

### 5.1 Variabili d'ambiente

| Variabile | Stato |
|---|---|
| `OPENAI_API_KEY` | SET (invalida — 401) |
| `MISTRAL_API_KEY` | SET (funzionante) |
| `ANTHROPIC_API_KEY` | SET (credito insufficiente — 400) |
| `GOOGLE_API_KEY` | NOT_SET |
| `PERPLEXITY_API_KEY` | SET (invalida — 401) |
| `DATABASE_URL` | SET (Supabase configurato) |
| `LM_STUDIO_API_URL` | SET |
| `EUROPEANA_API_KEY` | SET |
| `SUPABASE_URL` | SET |
| `SUPABASE_ANON_KEY` | SET |
| `SUPABASE_SERVICE_KEY` | NOT_SET |

### 5.2 Provider AI attivi

| Provider | Status | Note |
|---|---|---|
| Mistral | ✅ Funzionante | `mistral-small-latest` |
| OpenAI | ❌ 401 | Chiave invalida |
| Anthropic | ❌ 400 | Credito insufficiente |
| Perplexity | ❌ 401 | Chiave invalida |
| Google | ❌ Not configured | API key non impostata |
| LM Studio | ⚠️ Configurato | URL impostato, da verificare |

### 5.3 AI routing

- `ai_client.py` — interfaccia unificata con fallback chain
- `ai_router.py` — routing con task types, circuit breaker, budget
- Fallback order: OpenAI → Anthropic → Mistral → Perplexity → Gemini
- Task types: 15 registrati incluso `generate_viewpoints`

---

## 6. Hardware e risorse

| Risorsa | Valore |
|---|---|
| CPU | Intel i5-1135G7 @ 2.40GHz, 4 core |
| RAM | 16 GB |
| GPU | Nessuna NVIDIA (integrazione Intel Iris Xe) |
| Disco | 474 GB total, 180 GB used, **293 GB free** |
| OS | Windows |

**Implicazioni modello locale:**
- Nessuna GPU NVIDIA → no CUDA
- LM Studio con quantizzazione CPU (GGUF/Q4)
- Modelli compatibili: 7B-8B parametri con Q4_K_M (~4-5GB RAM)
- Safetensors non pratico senza GPU

---

## 7. Dipendenze Python

Principali (da `requirements.txt`):
- fastapi==0.104.1, uvicorn==0.24.0
- pydantic>=2.5.0
- openai==1.3.7, mistralai>=2.0.0, anthropic>=0.21.0
- google-generativeai>=0.8.0
- playwright>=1.40.0
- psycopg2-binary>=2.9.0
- supabase==2.3.4
- beautifulsoup4>=4.12.0
- pymupdf>=1.23.0, pdfplumber>=0.9.0

Non presenti:
- `transformers`, `torch` (per safetensors locale)
- `sentence-transformers` (per embedding locale)
- `faiss` o `chromadb` (per vector store locale)
- `leaflet` (nel frontend: verificare)

---

## 8. Frontend dependencies

Da verificare in `frontend/package.json`:
- React 19, Vite, React Router
- Leaflet (per HistoricalMap)
- Lucide React (icone)

---

## 9. Script legacy da refactoring

| Script | Problema | Azione richiesta |
|---|---|---|
| `_gen_event_links.py` | Esecuzione mutativa, no dry-run | Refactoring con --dry-run default |
| `_gen_record_links.py` | Scritture all'import, cancellazione automatica | Pipeline versionata reversibile |
| `_clean_bad_links.py` | Cancellazione senza opzione separata | Marcatura + revisione |
| `_fix_gaiaschi_db.py` | Modifica diretta record reali | Proposal + audit trail |
| `_check_keys.py` | Mostra prefissi chiavi | Output solo SET/NOT_SET |
| `_audit_baseline.py` | Script audit (nuovo, OK) | Mantenere |
| `_audit_graph.py` | Script audit (nuovo, OK) | Mantenere |
| `_audit_links.py` | Script audit (nuovo, OK) | Mantenere |

---

## 10. Test esistenti

| File | Scope |
|---|---|
| `tests/test_api.py` | Endpoint API |
| `tests/test_database.py` | Database |
| `tests/test_fonti_risorse_master.py` | Fonti risorse (master) |
| `tests/test_rc_master.py` | Riconoscimenti (master) |
| `tests/test_search_service.py` | Search service |
| `tests/test_source_providers.py` | Source providers |
| `tests/test_biography.py` | Biography |
| `tests/test_linker.py` | Linker |
| `tests/test_enrich_entities.py` | Enrich entities |
| `tests/test_enrich_events.py` | Enrich events |
| `tests/test_indexing_rules.py` | Indexing rules |
| `tests/test_memory_router.py` | Memory router |
| `tests/test_source_locator.py` | Source locator |
| `tests/test_soldier_dashboard.py` | Soldier dashboard |
| `tests/test_archivio_fonti.py` | Archivio fonti |
| `tests/test_audit_cross_db.py` | Audit cross DB |
| `tests/test_personal_sources_import.py` | Personal sources |
| `tests/test_project_health.py` | Project health |
| `tests/test_research_to_index.py` | Research to index |
| `test_event_research_master.py` | Event research (root) |
| `test_research_engine_master.py` | Research engine (root) |
| `test_search.py` | Search (root) |
| `test_50_queries.py` | 50 query test |
| `test_50_direct.py` | 50 direct test |

---

## 11. Rischi di compatibilità

1. **DB 1.8 GB** — operazioni di backup richiedono attenzione (WAL mode)
2. **169K record_links legacy** — tutti candidate, nessuna evidenza, non devono essere promossi a confirmed
3. **891K event_links** — senza evidenze, generati con keyword matching
4. **WWII eventi in eventi_1gm** — il nome della tabella implica solo WWI
5. **Graph schema non deployato** — le tabelle canoniche non esistono nel DB
6. **25 FK issues** in `research_subject_sources` → `fonti_indice`
7. **200 FK issues** in `validazioni_ai.db`
8. **API key invalide** — solo Mistral funzionante
9. **No GPU** — limita opzioni modello locale a CPU-only (LM Studio GGUF)
10. **Frontend usa `any`** in diverse risposte API — necessita tipizzazione

---

## 12. .gitignore status

**Adeguato:**
- `.env`, `*.env` ✅
- `*.db`, `*.db-wal`, `*.db-shm` ✅
- `__pycache__/` ✅
- `*.log` ✅
- `archivio_storage/` ✅
- `outputs/` ✅

**Da aggiungere:**
- `*.safetensors` — modelli locali
- `*.gguf` — modelli LM Studio
- `data/` — directory runtime corpus
- `source_cache/` — cache fonti
- `uploads/` — file caricati
- `*.zip` — archivi
- `Lettere_dal_fronte-refactor-completo-a7e6231/` — cartella refactor
- `codex_handoff/` — handoff
- `enrich_entities*.log` — log grandi
- `mass_index.log` — log grande (54MB)
- `albo_log.txt`, `cwgc_log.txt`, `cwgc_scrape.log`, `nara_scrape.log` — log scrape
- `linker*.log` — log linker
- `*.xlsx`, `*.csv`, `*.ods` — export dati
- `imi.csv`, `imi.ods`, `export_internati.*` — export

---

## 13. Comandi di avvio

```bash
# Backend
python -m uvicorn app:app --host 0.0.0.0 --port 8001

# Frontend
cd frontend && npm run dev

# Test
pytest tests/ -v
```

---

## 14. Stato sintesi

| Area | Status | Note |
|---|---|---|
| Backend | ✅ Attivo | 162 endpoint, porta 8001 |
| Frontend | ✅ Attivo | 15 route, porta 5173 |
| DB principale | ✅ Integrity OK | 1.8 GB, 68 tabelle |
| DB eventi | ✅ Integrity OK | 137 MB, 22 eventi (WWI+WWII) |
| Graph schema | ❌ Non deployato | Tabelle canoniche mancanti |
| Record links | ⚠️ Legacy | 169K tutti candidate, 0 evidenze |
| Event links | ⚠️ Legacy | 891K senza evidenze |
| Claims | ✅ Esistente | 40 claims, 505 evidenze (solo Gaiaschi) |
| AI provider | ⚠️ Parziale | Solo Mistral funzionante |
| LM Studio | ⚠️ Configurato | Da verificare |
| Frontend tipi | ⚠️ Parziale | `any` in diverse risposte |
| .gitignore | ⚠️ Da completare | Modelli, data, cache non coperti |
