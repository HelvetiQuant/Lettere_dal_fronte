# IMI Extractor — Architettura Tecnica Completa

> Documento di riferimento per sviluppatori frontend e backend.
> Versione: 2026-07-24 · AI Provider Consolidation + LeBI Fase 4 — Frontend, API, Parser Fix

---

## 1. Visione generale del progetto

**IMI Extractor** ("Voci dal Fronte" / "Lettere dal Fronte") è una piattaforma di ricerca storica federata dedicata ai soldati, dispersi, caduti e reduci italiani delle due guerre mondiali (1900-1945). Il sistema combina:

- **Database locali** con ~1.5M+ record storici estratti da fonti primarie
- **Federazione di 27 archivi internazionali** (Arolsen, Bundesarchiv, TNA, NARA, CWGC, Europeana, LeBI/ANRP, ecc.)
- **Intelligenza artificiale multi-provider** (OpenAI GPT-4o, Anthropic Claude, Mistral, Perplexity) per ricerca, analisi, biografie, report, OCR e generazione immagini
- **Modulo Percorso Riconoscimenti** per l'identificazione e gestione di candidati a onorificenze
- **Modulo Fonti Esterne Federate CRI** per l'integrazione di metadati archivistici della Croce Rossa Italiana
- **Modulo LeBI/ANRP** per l'integrazione del Lessico Biografico degli Internati Militari Italiani (305K+ nominativi)

### 1.1 Obiettivo storico-archivistico

Il sistema non è un catalogo generale di storia militare, ma uno strumento specializzato per:
1. **Identificare persone** attraverso dataset multipli (IMI, Albo d'Oro, Nastro Azzurro, Caduti Ministero, CWGC, ecc.)
2. **Cross-linkare** record della stessa persona tra database diversi
3. **Generare dossier** narrativi e biografie con citazioni di fonti verificate
4. **Trovare fonti archivistiche** correlate (fondi, documenti NARA, lettere dal fronte)
5. **Supportare il percorso di riconoscimento** per decorati/caduti/non riconosciuti

### 1.2 Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Database | SQLite (default) / PostgreSQL (Supabase) via `db_adapter.py` |
| Frontend pubblico | SPA vanilla JS + `support.js` (Signals/Reactive) — `templates/index.html` |
| Frontend operatori | SPA vanilla JS — `templates/rc.html` |
| AI Providers | OpenAI GPT-4o/4o-mini (primario), Anthropic Claude Sonnet 4.5, Mistral Small, Perplexity Sonar, Google Gemini 2.0 Flash (fallback) |
| OCR | Mistral OCR (`mistral-ocr-latest`), GPT-4o Vision (fallback), pdfplumber (fallback) |
| Image generation | DALL-E 3 (primary), Stability AI (fallback) |
| Web scraping | requests + BeautifulSoup, Playwright (TNA WAF challenge) |
| Full-Text Search | SQLite FTS5 / PostgreSQL tsvector + GIN |
| Auth | Session-based con ruoli (admin, ricercatore, revisore, genealogista, operatore, discendente) |

---

## 2. Architettura di alto livello

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                              │
│                                                                     │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐  │
│  │  index.html (pubblico)│    │  rc.html (operatori/riconosc.)  │  │
│  │  SPA + support.js     │    │  SPA vanilla JS                 │  │
│  │  voci-data.js         │    │  9 views + modals               │  │
│  │  i18n: it/en/de/fr    │    │  Auth + RBAC                    │  │
│  └──────────┬───────────┘    └──────────────┬───────────────────┘  │
│             │                               │                      │
└─────────────┼───────────────────────────────┼──────────────────────┘
              │ HTTP/JSON                     │ HTTP/JSON
              │                               │
┌─────────────┼───────────────────────────────┼──────────────────────┐
│             ▼         BACKEND LAYER         ▼                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    app.py (FastAPI)                         │   │
│  │                    2600+ righe, 312 endpoint                │   │
│  │                                                             │   │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │   │
│  │  │ Routers │ │ Auth     │ │ Events   │ │ External Sources│  │   │
│  │  │ rc_api  │ │ auth.py  │ │ events.py│ │ _api.py         │  │   │
│  │  │ rc_ext  │ │          │ │          │ │                 │  │   │
│  │  └─────────┘ └──────────┘ └──────────┘ └────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────── SERVICE LAYER ────────────────────────┐  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ AI Research  │  │ Biography    │  │ Event Research   │  │  │
│  │  │ ai_research  │  │ biography.py │  │ Engine           │  │  │
│  │  │ 4 providers  │  │ Fallback     │  │ event_research   │  │  │
│  │  │ + research_all│ │ chain        │  │ _engine.py       │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ Report Engine│  │ Memory Router│  │ Soldier Dashboard│  │  │
│  │  │ report_engine│  │ memory_router│  │ soldier_dashboard│  │  │
│  │  │ .py          │  │ .py          │  │ .py              │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ Linker       │  │ Search       │  │ Compliance Gate  │  │  │
│  │  │ linker.py    │  │ Service      │  │ compliance_gate  │  │  │
│  │  │ Cross-DB     │  │ search_      │  │ .py              │  │  │
│  │  │ entity graph │  │ service.py   │  │ Policy engine    │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ Extractor    │  │ NARA T315    │  │ External Metadata│  │  │
│  │  │ extractor.py │  │ OCR          │  │ Service          │  │  │
│  │  │ OCR + AI     │  │ nara_t315_ocr│  │ ext_metadata_svc │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ External Link│  │ Scraper      │  │ Source Locator   │  │  │
│  │  │ Service      │  │ Service      │  │ source_locator   │  │  │
│  │  │ ext_link_svc │  │ scraper_svc  │  │ .py              │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────── FEDERATION LAYER ─────────────────────────┐  │
│  │  source_providers/                                           │  │
│  │  ├── base.py          (SourceProvider ABC)                   │  │
│  │  ├── federation.py    (registry + federated_search)          │  │
│  │  ├── providers.py     (Arolsen, Bundesarchiv, SHD, TNA,     │  │
│  │  │                     Europeana, Gallica, InternetArchive,  │  │
│  │  │                     GoogleBooks, ABMC, LAC, AWM, etc.)    │  │
│  │  ├── cwgc.py          (Commonwealth War Graves)              │  │
│  │  ├── nara.py          (NARA Catalog API + DB locale)         │  │
│  │  ├── antenati.py      (Archivi di Stato Italia)              │  │
│  │  ├── icrc_ww1.py      (ICRC WW1 prisoners)                   │  │
│  │  ├── cri_milano.py    (CRI Milano — Archimista)              │  │
│  │  ├── wikitree.py      (WikiTree genealogy)                   │  │
│  │  ├── memoire_des_hommes.py  (SHD France)                     │  │
│  │  ├── deutsche_digitale_bibliothek.py (DDB)                   │  │
│  │  ├── iwm_lives.py     (Imperial War Museum)                  │  │
│  │  ├── grand_memorial.py (Grand Memorial France)               │  │
│  │  ├── lebi.py         (LeBI/ANRP — 305K IMI)                 │  │
│  │  └── ... (27 provider totali)                                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────── DATA LAYER ───────────────────────────────┐  │
│  │  database.py    (SQLite/PG dual-mode, get_conn())           │  │
│  │  db_adapter.py  (PostgreSQL adapter, executescript compat)  │  │
│  │  db_init_fts.py (FTS5/tsvector initialization)              │  │
│  │  config.py      (column mappings, PDF paths)                │  │
│  │  credits.py     (API usage tracking + cost logging)         │  │
│  │                                                               │  │
│  │  ┌─── SQLite Tables ───────────────────────────────────┐    │  │
│  │  │ internati (20K)          decorati (ISTORECO)         │    │  │
│  │  │ caduti_albooro (342K)    decorati_nastroazzurro(280K)│    │  │
│  │  │ caduti_ministero (162K)  caduti_cwgc (506K)          │    │  │
│  │  │ caduti_sardi              caduti_bologna              │    │  │
│  │  │ caduti_francia_ww1        menzioni                    │    │  │
│  │  │ fondi_archivistici        entita                      │    │  │
│  │  │ collegamenti              record_links                │    │  │
│  │  │ fonti_indice              fonti_risorse               │    │  │
│  │  │ archivio_fonti            archivio_documenti          │    │  │
│  │  │ documenti_nara_t315       documenti_nara_catalog      │    │  │
│  │  │ ai_ricerche               api_usage                   │    │  │
│  │  │ source_fetch_cache        source_policies             │    │  │
│  │  │ events_1gm (separate DB)                              │    │  │
│  │  │                                                       │    │  │
│  │  │ ── Percorso Riconoscimenti ──                         │    │  │
│  │  │ rc_candidates            rc_candidate_sources         │    │  │
│  │  │ rc_candidate_events      rc_assessments               │    │  │
│  │  │ rc_family_persons        rc_contacts                  │    │  │
│  │  │ rc_admin_cases           rc_state_transitions         │    │  │
│  │  │ rc_practices             rc_practice_documents        │    │  │
│  │  │ rc_recognition_types     rc_descendant_contacts       │    │  │
│  │  │ rc_institutional_contacts rc_communications           │    │  │
│  │  │                                                       │    │  │
│  │  │ ── Fonti Esterne CRI (Fase 2) ──                      │    │  │
│  │  │ external_source_records   external_person_mentions    │    │  │
│  │  │ external_source_facts     external_record_links       │    │  │
│  │  │ external_digital_objects  external_access_requests    │    │  │
│  │  │ external_import_jobs                                  │    │  │
│  │  └───────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Frontend — Architettura dettagliata

### 3.1 Frontend pubblico (`templates/index.html`)

**Tecnologia**: SPA vanilla JavaScript che usa `support.js` (un framework reactive basato su Signals, simile a Vue/SolidJS ma minimale). Il file `index.html` è ~2628 righe che definiscono tutto il markup e la logica di rendering in un singolo componente `VociDalFronte`.

**File coinvolti**:
- `@/templates/index.html:1-2628` — SPA principale, markup + logica
- `@/templates/voci-data.js:1-857` — Dati statici, stringhe i18n, funzioni API
- `@/templates/support.js` — Framework reactive (Signals, sc-if, sc-for, binding)

**Views (state.view)**:
- **home** — Hero + search bar + KPI stats + eventi in evidenza
- **search** — Risultati ricerca (subjects + events), con conferme e validazioni
- **explore** — Esplorazione tabella per tabella (internati, caduti, decorati, ecc.) con paginazione
- **events** — Lista eventi storici curati (1GM + 2GM)
- **dossier** — Dossier dettagliato di un soggetto o evento con tab:
  - **overview** — Panoramica
  - **crossdb** — Collegamenti cross-database
  - **sources** — Fonti collegate (locali + federate)
  - **events** — Eventi correlati
  - **gaps** — Lacune (campi mancanti, provider suggeriti)
  - **perspectives** — Punti di vista a confronto (it/de/allied)
- **admin** — Pannello operatori (import, estrazioni, provider federation, crediti AI)

**i18n**: 4 lingue (it, en, de, fr) definite in `voci-data.js` STRINGS. I dati storici rimangono in italiano (lingua originale della fonte).

**Flusso di ricerca (goSearch)**:
```
1. User digita query → goSearch(query)
2. voci-data.js searchLive(query) → GET /api/search-validated?q=...
3. Backend: memory_router.route_query() → SQL exact → FTS5/BM25 → graph → archivio_fonti
4. Risposta: { subjects, events, confirmations, validations, externalSources }
5. Frontend: renderizza subjects + events + badge "verificato/parziale/non verificato"
6. Se subject è IMI → click → openDossier('subject', 'imi_123')
7. openDossier → loadSoldierDossier(soldierId) → 3 API parallele:
   - GET /api/internati/{id}/fonti (fonti DB locale)
   - GET /api/internati/{id}/links (ricerca federata reale su 27 provider)
   - GET /api/internati/{id}/opengraph (card anagrafica)
8. Dossier renderizza: timeline, sources (verificate + da verificare), perspectives, gaps
```

**Flusso biografia AI (generateSoldierBio)**:
```
1. User click "Genera dossier verificato" nel dossier
2. POST /api/biography { subject_type: 'soldier', soldier_id: 123 }
3. Backend: biography.generate_soldier_biography(123, provider=null)
   - Recupera soldier_dashboard (dati certi, timeline, fonti)
   - Recupera lettere OCR che menzionano il cognome (ocr_lettere.db)
   - Recupera fonti web verificate (scrape_if_stale su fonti_risorse)
   - Costruisce prompt con SOLO fonti verificate
   - _call_with_fallback: GPT → Claude → Mistral → Perplexity
4. Frontend: mostra risposta AI + fonti online usate
```

**Flusso immagini AI (generateSoldierImages)**:
```
1. User click "Genera immagini" nel dossier
2. POST /api/soldier/images { name, subtitle, id }
3. Backend: biography.generate_soldier_images()
   - AI genera 3-5 prompt fotorealistici (IMAGE_PROMPT_GENERATOR)
   - DALL-E 3 genera immagini (fallback Stability AI)
   - Salvate in cache
4. Frontend: mostra galleria immagini
```

**Flusso report evento (openDossier event)**:
```
1. User click evento → openDossier('event', 'caporetto')
2. voci-data.js loadEventDossier(eventName) → 4 API parallele:
   - GET /api/events/1gm/{name} (dossier evento)
   - GET /api/events/1gm/{name}/caduti (caduti paginati)
   - GET /api/events/1gm/{name}/decorati (decorati paginati)
   - GET /api/events/{name}/internati (internati collegati)
3. Frontend: renderizza dossier con stats, caduti, decorati, documenti, fonti
4. User click "Genera Report" → POST /api/event/report { event_name, mode: 'specialist' }
5. Backend: event_research_engine.research_event()
   - Disambigua evento nel DB
   - Raccoglie fonti locali + federate + indice archivistico
   - AI genera scheda + JSON strutturato + matrice evidenze
6. Frontend: mostra report con tab (panoramica, fonti, punti_di_vista, cronologia)
7. User può fare follow-up chat → POST /api/event/chat { event_name, message, report, history }
```

### 3.2 Frontend operatori (`templates/rc.html`)

**Tecnologia**: SPA vanilla JavaScript puro (nessun framework reactive), ~1678 righe. State management manuale con oggetto `state` globale e funzione `render()` che ricostruisce il DOM.

**File**: `@/templates/rc.html:1-1678`

**Auth**: Login session-based (POST `/api/rc/auth/login`). Ruoli: admin, ricercatore, revisore, genealogista, operatore, discendente. Default: admin/admin.

**Views (state.view)**:
| View | Descrizione | API calls |
|---|---|---|
| `login` | Form login | POST /api/rc/auth/login |
| `dashboard` | KPI operativi, stati candidato, recenti | GET /api/rc/dashboard + /dashboard-ext |
| `discover` | Scopri candidati cross-DB | GET /api/rc/discover-candidates?q=... |
| `red-cross` | Sezione Croce Rossa | (renderRedCross) |
| `external-sources` | Fonti Esterne CRI federate | GET /api/external-sources/records |
| `external-record-detail` | Dettaglio record esterno | GET /api/external-sources/records/{id} |
| `candidates` | Lista candidati con filtri | GET /api/rc/candidates?... |
| `candidate-detail` | Dettaglio candidato con 9 tab | 12 API parallele |
| `recognition-types` | Catalogo onorificenze | GET /api/rc/recognition-types |
| `compliance` | Conformità source policies | (renderCompliance) |
| `audit` | Log audit trail | GET /api/rc/audit |
| `users` | Gestione utenti (admin only) | (renderUsers) |

**Candidate Detail — 9 Tab**:
1. **dati** — Anagrafica, grado, reparto, conflitto
2. **fonti** — Fonti collegate al candidato (CRUD)
3. **eventi** — Eventi bellici collegati
4. **valutazione** — Valutazioni storiche e amministrative
5. **ai** — Analisi AI generate (POST /api/rc/candidates/{id}/ai-analysis)
6. **genealogia** — Famiglia, discendenti
7. **contatti** — Contatti discendenti e istituzionali
8. **pratiche** — Pratiche amministrative, documenti pratica
9. **cronologia** — Storico transizioni di stato

**Flusso candidate-detail (loadCandidate)**:
```
12 API parallele su /api/rc/candidates/{cid}:
├── GET / (dati candidato)
├── GET /sources (fonti)
├── GET /events (eventi)
├── GET /assessments (valutazioni)
├── GET /family (famiglia)
├── GET /contacts (contatti)
├── GET /admin-cases (pratiche legacy)
├── GET /history (cronologia)
├── GET /ai-analyses (analisi AI)
├── GET /descendant-contacts (contatti discendenti)
├── GET /practices (pratiche estese)
└── GET /practice-documents (documenti pratica)
```

**Azioni frontend chiave**:
- **doTransition(cid, newState)** — Transizione stato candidato con motivazione
- **generateDossier(cid)** — Genera PDF fascicolo (GET /api/rc/candidates/{id}/dossier)
- **runAiAnalysis(cid)** — Analisi AI onorificenze (POST /api/rc/candidates/{id}/ai-analysis)
- **createSource/createAssessment/createFamilyPerson** — Modali CRUD

**Frontend Fonti Esterne (renderExternalSources)**:
```
1. setView('external-sources') → loadExternalSources(1)
2. GET /api/external-sources/records?page=1&page_size=50
3. Renderizza tabella con: provider, livello, titolo, estremi cronologici
4. Click record → loadExternalRecord(id)
5. GET /api/external-sources/records/{id} (dettaglio con menzioni, fatti, oggetti digitali, link)
6. Renderizza: metadati, gerarchia archivistica, menzioni persone, fatti, oggetti digitali
7. Azioni: genera collegamenti (POST /generate-matches), verifica URL (POST /verify-url)
```

---

## 4. Backend — Architettura dettagliata

### 4.1 App principale (`app.py`)

**File**: `@/app.py:1-2501`

**Avvio (lifespan)**:
```python
init_db()                    # Schema principale
init_usage_table()           # Tabella costi API
rti._init_tables()           # RTI tables
auth.init_auth_tables()      # Auth + utenti
rc_schema.init_rc_schema()   # Percorso Riconoscimenti
rc_schema.seed_recognition_types()
auth.ensure_default_admin()
seed_source_policies()       # Compliance gate policies
init_external_sources_schema()  # Fonti Esterne CRI
```

**Router registrati**:
- `rc_router` (rc_api.py) — Endpoints /api/rc/*
- `rc_ext_router` (rc_api_ext.py) — Endpoints estesi /api/rc/*
- `external_sources_router` (external_sources_api.py) — /api/external-sources/*

**Endpoint API principali** (80+ totali):

| Categoria | Endpoint | Metodo | Descrizione |
|---|---|---|---|
| **Ricerca** | `/api/search-validated` | GET | Ricerca validata con memory router |
| **Ricerca** | `/api/search/ww1` | GET | Ricerca WW1 specifica |
| **Ricerca** | `/api/search/confirm` | POST | Conferma correzione search |
| **AI Research** | `/api/ai-research` | POST | Ricerca AI multi-provider |
| **Biografia** | `/api/biography` | POST | Genera biografia/dossier soldato o evento |
| **Report Evento** | `/api/event/report` | POST | Scheda storica documentata evento |
| **Report Evento (tab)** | `/api/event/report/{tab}` | POST | Scheda specifica (panoramica/fonti/punti_di_vista/cronologia) |
| **Report Cronologico** | `/api/event/report/chronological` | POST | Report cronologico narrativo |
| **Chat Evento** | `/api/event/chat` | POST | Follow-up chat dopo report |
| **Analisi Fonte** | `/api/fonte/analyze` | POST | Analisi AI singola fonte |
| **Immagini Fonte** | `/api/fonte/generate-images` | POST | Genera immagini AI per fonte |
| **Immagini Soldato** | `/api/soldier/images` | POST | Genera immagini AI per soldato |
| **Soldier Dashboard** | `/api/soldiers/{id}/dashboard` | GET | Dashboard investigativa soldato |
| **Fonti Soldato** | `/api/internati/{id}/fonti` | GET | Fonti DB locale per soldato |
| **Link Soldato** | `/api/internati/{id}/links` | GET | Ricerca federata reale per soldato |
| **Federation** | `/api/providers` | GET | Lista 27 provider |
| **Federation** | `/api/source/search` | POST | Ricerca federata cross-provider |
| **Federation** | `/api/source/fetch` | POST | Fetch on-demand documento |
| **Federation** | `/api/source/stats` | GET | Statistiche federation |
| **Eventi** | `/api/events` | GET | Lista eventi curati |
| **Eventi 1GM** | `/api/events/1gm` | GET | Eventi canonici 1GM+WW2 |
| **Eventi 1GM** | `/api/events/1gm/{name}` | GET | Dossier evento |
| **Eventi 1GM** | `/api/events/1gm/{name}/caduti` | GET | Caduti paginati evento |
| **Eventi 1GM** | `/api/events/1gm/{name}/decorati` | GET | Decorati paginati evento |
| **Fonti Esterne** | `/api/external-sources` | GET | Lista provider esterni |
| **Fonti Esterne** | `/api/external-sources/records` | GET | Lista record (paginato, filtri) |
| **Fonti Esterne** | `/api/external-sources/records/{id}` | GET | Dettaglio record |
| **Fonti Esterne** | `/api/external-sources/records/{id}/children` | GET | Record figli (gerarchia) |
| **Fonti Esterne** | `/api/external-sources/records/{id}/parents` | GET | Gerarchia genitori |
| **Fonti Esterne** | `/api/external-sources/import` | POST | Avvia import incrementale |
| **Fonti Esterne** | `/api/external-sources/records/{id}/generate-matches` | POST | Genera collegamenti candidati |
| **Fonti Esterne** | `/api/external-links/{id}/review` | PUT | Revisione umana collegamento |
| **Fonti Esterne** | `/api/external-sources/documents/upload` | POST | Upload documento manuale |
| **Crediti** | `/api/credits` | GET | Riepilogo costi AI |
| **Status** | `/api/status` | GET | Stato estrazioni |

### 4.2 Database layer

**File**: `@/database.py` (1066+ righe), `@/db_adapter.py`

**Dual-mode**: SQLite (default) o PostgreSQL (se `DATABASE_URL` env var settata). `db_adapter.py` converte automaticamente sintassi SQLite-specifica (`AUTOINCREMENT` → `SERIAL`, `?` → `%s`).

**Tabelle principali**:
- **internati** (~20K) — IMI da Archivio di Stato Bolzano
- **caduti_albooro** (~342K) — Albo d'Oro caduti 1GM
- **decorati_nastroazzurro** (~280K) — Decorati al Valor Militare
- **caduti_cwgc** (~506K) — Caduti Commonwealth
- **caduti_ministero** (~162K) — Caduti Ministero Difesa
- **caduti_sardi, caduti_bologna, caduti_francia_ww1** — Fonti regionali/internazionali
- **decorati** — Decorati ISTORECO
- **menzioni** — Persone/luoghi estratti da fondi archivistici
- **fondi_archivistici** — Inventari e carteggi militari
- **entita** — Entità estratte cross-dataset (persone, luoghi, eventi, unità)
- **collegamenti** — Archi del grafo tra entità
- **record_links** — Link record-to-record tra tabelle diverse
- **fonti_indice** — Metadati fonti esterne indicizzate
- **fonti_risorse** — Risorse esterne catalogate
- **archivio_fonti** — Fonti narrative personali (diari, foto, documenti famiglia)
- **documenti_nara_t315, documenti_nara_catalog** — Documenti NARA
- **ai_ricerche** — Log ricerche AI salvate
- **api_usage** — Tracking costi per provider/model
- **source_fetch_cache** — Cache download documenti
- **source_policies** — Policy compliance per dominio/provider

**Full-Text Search**:
- SQLite: tabella virtuale `idx_entita_search` (FTS5) con trigger di sync
- PostgreSQL: colonna `search_vector` (tsvector) + GIN index + trigger

### 4.3 AI Integration — dettaglio completo

#### 4.3.1 Multi-provider architecture

**File**: `@/ai_research.py:1-357`

Quattro provider AI configurati con fallback automatico:

| Provider | Modello | SDK | Costo (input/output per 1M token) |
|---|---|---|---|
| **gpt** | gpt-4o-mini | openai Python SDK | $0.15 / $0.60 |
| **claude** | claude-sonnet-4-5-20250929 | anthropic Python SDK | $3.00 / $15.00 |
| **mistral** | mistral-large-latest | mistralai SDK | ~$2.00 / ~$6.00 |
| **perplexity** | sonar | HTTP REST (requests) | ~$1.00 / ~$1.00 |

**Pattern di fallback** (`biography.py:326-344`):
```python
_FALLBACK_ORDER = ["gpt", "claude", "mistral", "perplexity"]

def _call_with_fallback(system, prompt, tag, preferred=None, fallback_order=None):
    order = ([preferred] if preferred in base_order else []) + \
            [p for p in base_order if p != preferred]
    for provider in order:
        try:
            risposta, model, cost = _dispatch(provider, system, prompt)
            return {"ok": True, "provider": provider, "risposta": risposta, ...}
        except Exception as e:
            attempted.append({"provider": provider, "error": str(e)})
            continue
    return {"ok": False, "error": "Tutti i provider AI configurati hanno fallito."}
```

**Cost tracking** (`credits.py:35-123`):
- Ogni chiamata AI loggata in `api_usage` con provider, model, token, costo USD
- `get_usage_summary()` ritorna budget totale, costo corrente, % utilizzo, breakdown per provider/model

#### 4.3.2 AI nella ricerca (`ai_research.py`)

**Flusso**:
1. User query → `_extract_search_terms(query)` estrae anni, nomi propri, luoghi
2. `_prepare_context(term, limit)` → `get_all_records_for_ai(term)` interrogazione cross-DB:
   - internati, decorati, menzioni, caduti (6 fonti), fondi_archivistici, entita, documenti NARA, fonti_narrative, lettere_personali OCR
3. Formatta contesto come testo strutturato con sezioni per dataset
4. Invia a provider AI con `RESEARCH_PROMPT` (istruzioni: non inventare, cita dataset)
5. Salva risposta in `ai_ricerche` con costo
6. `research_all()` interroga tutti i 4 provider in sequenza per confronto

**Endpoint**: `POST /api/ai-research { query, provider: "gpt"|"mistral"|"perplexity"|"claude"|"all" }`

#### 4.3.3 AI nelle biografie (`biography.py`)

**Principio "nessun dato inventato"**:
- Nel prompt entrano SOLO fonti verificate (dati locali certi, archivio_fonti readable, testo_ocr, lettere OCR, fonti web verificate)
- Fonti esterne trovate ma non recuperate vengono elencate come "da verificare" in sezione separata
- L'AI ha istruzioni esplicite di NON usarle per il testo narrativo

**generate_soldier_biography(soldier_id)**:
1. `get_soldier_dashboard(soldier_id)` → dati certi, timeline, fonti locali, fonti esterne federate
2. `_find_letters_mentioning(cognome)` → lettere OCR dal DB `ocr_lettere.db`
3. Recupera fonti web verificate (scrape_if_stale su fonti_risorse)
4. Costruisce prompt con `BIOGRAPHY_PROMPT` (struttura obbligatoria: SINTESI, RICOSTRUZIONE CRONOLOGICA, CONTESTO STORICO, FONTI CITATE, LACUNE, FONTI DA VERIFICARE)
5. `_call_with_fallback()` → primo provider disponibile genera la biografia
6. Salva in `ai_ricerche` con tag `[BIOGRAFIA]`

**generate_event_biography(query)**:
1. `memory_router.route_query(query)` → recupero contesto (SQL → FTS → graph → archivio_fonti)
2. Costruisce prompt con fonti verificate
3. AI genera biografia evento

#### 4.3.4 AI nei report eventi (`event_research_engine.py`)

**File**: `@/event_research_engine.py:1-604`

**research_event(query, options, provider, tab, mode)**:

1. **Disambigazione**: `disambiguate_event(query)` matcha contro DB `eventi_1gm`
2. **Context building**: `_build_context(canonical, query, options)` raccoglie:
   - Fonti locali: `_local_sources_context(canonical)` (archivio_fonti, documenti NARA, menzioni)
   - Fonti federate: `_federated_sources_context(canonical)` (federated_search su 27 provider)
3. **Prompt**: `_build_prompt(canonical, context, tab)` con `EVENT_RESEARCH_PROMPT`
4. **Modalità**:
   - **specialist** (default): usa provider specialista per tab (Perplexity per panoramica, Claude per fonti, GPT per punti_di_vista, Mistral per cronologia)
   - **parallel**: interroga tutti i 4 provider in parallelo (`ThreadPoolExecutor`) per confronto
5. **Output**: scheda leggibile + JSON strutturato + matrice evidenze + dati contestati + claim non verificati

**TAB_PROVIDER mapping**:
| Tab | Provider specialista | Motivazione |
|---|---|---|
| panoramica | perplexity | Ricerca web + sintesi |
| fonti | claude | Analisi critica fonti |
| punti_di_vista | gpt | Sintesi convergenze/divergenze |
| cronologia | mistral | Velocità generazione |

**generate_event_tab_report(event_name, tab)**:
- Genera solo un tab specifico (es. solo "fonti") con provider specialista

**generate_chronological_report(event_name)**:
- Report cronologico narrativo con line del tempo

#### 4.3.5 AI nella generazione immagini (`biography.py:209-246`)

**IMAGE_PROMPT_GENERATOR**: L'AI analizza il testo della fonte e:
1. **Chunking**: divide in sezioni tematiche
2. **Selezione episodi**: sceglie 3-5 episodi visivamente rappresentabili
3. **Generazione prompt**: per ogni episodio genera prompt in inglese (min 40 parole, "photorealistic, historical accuracy, detailed")
4. Restituisce JSON array `[{prompt, title, chunk, episode}]`

**Esecuzione**: DALL-E 3 (primary) → Stability AI (fallback). Immagini salvate in `source_cache/` con SHA256.

**Endpoint**:
- `POST /api/fonte/generate-images { source_id, event_name }` — per fonte archivistica
- `POST /api/soldier/images { name, subtitle, id }` — per soldato
- `GET /api/fonte/{source_id}/images` — recupera immagini cached

#### 4.3.6 AI nell'OCR (`extractor.py`)

**File**: `@/extractor.py:1-378`

**Pipeline OCR per elenchi IMI (Archivio di Stato Bolzano)**:
1. **Text extraction**:
   - `mistral` engine: Mistral OCR (`mistral-ocr-latest`) su immagine pagina → markdown
   - `pdfplumber` engine: estrazione testo nativo PDF
   - `dual` engine: alterna Mistral OCR (pagine pari) + pdfplumber (pagine dispari)
2. **AI parsing**: GPT-4o-mini parse testo → JSON strutturato
   - `PARSE_PROMPT`: istruzioni per estrarre cognome, nome, data_nascita, luogo, grado, sorte, ecc.
   - Correzione automatica errori OCR
   - Flag `needs_review` per voci incomplete/illeggibili
3. **Fallback vision**: GPT-4o Vision per pagine illeggibili (ultimo resort)
4. **Concorrenza**: `ThreadPoolExecutor` con 4 worker per pagine parallele
5. **Geocoding**: `validate_record_locations()` valida luoghi con OpenStreetMap Nominatim

**Pipeline OCR NARA T315** (`nara_t315_ocr.py`):
- Documenti tedeschi WWII (117. Jäger-Division)
- GPT-4o Vision per OCR militare tedesco
- 1156 immagini JPG, resume automatico

#### 4.3.7 AI nel Percorso Riconoscimenti

**runAiAnalysis(candidate_id)**:
- `POST /api/rc/candidates/{id}/ai-analysis`
- L'AI analizza le onorificenze del candidato valutando:
  - Dati anagrafici e militari
  - Fonti collegate
  - Eventi collegati
  - Coerenza storica
- Output: valutazione strutturata per ogni onorificenza

#### 4.3.8 AI chat di follow-up (`app.py:1658-1698`)

**POST /api/event/chat { event_name, message, report, history, provider }**:
- Mantiene contesto del report generato
- History ultimi 10 messaggi
- System prompt: "ricercatore storico specializzato in eventi bellici italiani del '900"
- Usa `_call_with_fallback` con provider preferito

### 4.4 Memory Router — Pipeline di recupero (`memory_router.py`)

**File**: `@/memory_router.py:1-859`

Pipeline ispirata al richiamo hippocampale umano:

```
Query utente
    │
    ▼
1. CUE EXTRACTION
   ├── Pattern divisioni/reggimenti (es. "3ª divisione", "117. Jäger-Division")
   ├── Pattern date (es. "12 settembre 1943", "1917")
   ├── Pattern guerre (ww1/ww2 keywords)
   ├── Pattern archivi (nara, bundesarchiv, tna, ecc.)
   └── Pattern richieste documento (pdf, immagine, war diary, ktb)
    │
    ▼
2. SQL EXACT MATCH
   ├── Query dirette su tabelle per campi strutturati
   └── Limit: max_sql_results (50)
    │
    ▼
3. FTS5 / BM25 (search_service.py)
   ├── Full-text search su entita con ranking BM25
   ├── Supporto SQLite FTS5 e PostgreSQL tsvector
   └── Limit: max_fts_results (20)
    │
    ▼
4. GRAPH TRAVERSAL (search_service.py)
   ├── Recursive CTE su entita + collegamenti
   ├── Depth: max_graph_depth (2)
   └── Espansione entità collegate
    │
    ▼
5. ARCHIVIO FONTI
   ├── Ricerca in archivio_fonti (fonti narrative personali)
   ├── Ricerca in fonti_indice (metadati esterni)
   └── Separazione: verified_sources vs image_only_sources
    │
    ▼
6. (OPTIONAL) LLM AUGMENT
   ├── Se use_cloud_fallback=True
   └── ai_research.research() per arricchimento
    │
    ▼
7. OUTPUT
   ├── results: record trovati
   ├── verified_sources: fonti con testo leggibile
   ├── image_only_sources: fonti solo immagine (non recuperate)
   ├── cues: cue estratti
   └── memory_trace: traccia di ricerca
```

**Budget di recupero** (`RETRIEVAL_BUDGET`):
- max_sources: 8
- max_image_only: 3
- max_graph_depth: 2
- max_fts_results: 20
- max_sql_results: 50

### 4.5 Cross-DB Linking (`linker.py`)

**File**: `@/linker.py:1-600`

**Funzione**: Estrae entità (persone, luoghi, eventi) da TUTTI i dataset e crea collegamenti cross-dataset nella tabella `entita` + `collegamenti`.

**Dataset processati**:
- internati, decorati, menzioni, fondi_archivistici
- caduti_ministero, caduti_sardi, caduti_bologna, caduti_albooro
- caduti_cwgc, decorati_nastroazzurro, caduti_francia_ww1
- documenti_nara_t315, documenti_nara_catalog

**Per ogni dataset**:
1. Estrae nomi → `_save_persona_with_variants()` → `save_entita()` con dedup
2. Estrae luoghi → `save_entita(tipo='luogo')`
3. Estrae eventi → `save_entita(tipo='evento')`
4. Crea `collegamenti` tra entità dello stesso record

**Record-to-record links** (`_gen_record_links.py`):
- Genera link nella tabella `record_links` basati su:
  - Stesso anno morte + stesso luogo
  - Stesso anno decorazione
  - Stesso fondo archivistico
  - Stesso evento collegato

### 4.6 Federation Layer — 27 provider

**File**: `@/source_providers/federation.py:1-234`

**Registry**: 27 provider registrati, ognuno implementa `SourceProvider` ABC:

| Provider | Classe | Country | Tipo API |
|---|---|---|---|
| NARA | ProviderNARA | USA | REST JSON + DB locale |
| Antenati | ProviderAntenati | IT | HTML scraping |
| CWGC | ProviderCWGC | UK | DB locale |
| WikiTree | ProviderWikiTree | Intl | REST JSON |
| Arolsen (ITS) | ProviderArolsen | DE | ASP.NET JSON (reverse-eng) |
| Bundesarchiv | ProviderBundesarchiv | DE | Invenio REST JSON |
| SHD | ProviderSHD | FR | HTML scraping |
| TNA | ProviderNationalArchivesUK | UK | REST JSON + WAF (Playwright) |
| Europeana | ProviderEuropeana | EU | REST JSON |
| Gallica/BNF | ProviderGallica | FR | REST JSON / IIIF |
| Internet Archive | ProviderInternetArchive | US | REST JSON |
| Google Books | ProviderGoogleBooks | US | REST JSON |
| ABMC | ProviderABMC | US | HTML scraping |
| Library Canada | ProviderLibraryCanada | CA | REST JSON |
| AWM | ProviderAustralianWarMemorial | AU | REST JSON |
| Archivportal-D | ProviderArchivportalD | DE | REST JSON |
| Internet Culturale | ProviderInternetCulturale | IT | REST JSON |
| HathiTrust | ProviderHathiTrust | US | REST JSON |
| USSME | ProviderUSSME | IT | DB locale / HTML |
| Archivio di Stato | ProviderArchivioDiStato | IT | HTML scraping |
| Mémoire des Hommes | ProviderMemoireDesHommes | FR | HTML scraping |
| DDB | ProviderDDB | DE | REST JSON |
| IWM Lives | ProviderIWMLives | UK | REST JSON |
| Grand Memorial | ProviderGrandMemorial | FR | REST JSON |
| ICRC WW1 | ProviderICRCWW1 | CH | REST JSON |
| CRI Milano | ProviderCRIMilano | IT | HTML scraping (Archimista) |
| LeBI/ANRP | ProviderLeBI | IT | HTML scraping (PHP/Symfony) |

**federated_search(query, cues, providers, filters)**:
1. Itera su tutti i provider (o subset se specificato)
2. Chiama `provider.search(query, filters)` → metadati + URL
3. Calcola score con `score_source(result, cues)` basato su match persona/luogo/data
4. Ordina per score descending
5. NON scarica documenti (solo metadati)

**fetch_source(source_id)**:
1. Lookup `fonti_indice` per source_id
2. Match archivio → provider (`_match_provider`)
3. `provider.fetch_with_cache(url, source_id)` → download con cache su filesystem
4. Solo domini autorizzati (`is_authorized`)

**TNA WAF Challenge** (`providers.py:461-583`):
- TNA usa AWS WAF Bot Control → HTTP 202 con JS challenge
- `_WafSession` usa Playwright headless Chromium per risolvere il challenge
- Cookie `aws-waf-token` trasferito in `requests.Session`
- TTL 25 minuti, refresh automatico

### 4.7 LeBI — Lessico Biografico degli IMI (ANRP)

**File**: `@/source_providers/lebi.py:1-220`, `@/sources_external_lebi.py:1-280`

**Portale**: `https://www.lessicobiograficoimi.it/`
**Volume**: 305.827 nominativi inseriti, 165.084 convalidati, 1.156.450 documenti consultati
**Periodo**: IMI deportati nei lager nazisti 1943-1945

**URL verificati**:
| Endpoint | URL | Metodo |
|---|---|---|
| Ricerca | `/frontend_prodimi.php/caduti/search?q=&n=&l=&y=&d=0` | GET |
| Scheda | `/frontend_prodimi.php/caduti/show/{ID}` | GET |
| PDF | `/frontend_prodimi.php/caduti/showpdf/{ID}` | GET (200 se esiste, 404 se no) |

**Parametri ricerca** (form HTML verificato):
| Param | Descrizione |
|---|---|
| `q` | Cognome (campo principale) |
| `n` | Nome |
| `l` | Luogo di nascita |
| `y` | Anno di nascita |
| `d` | Flag debug (sempre 0) |

**Struttura scheda HTML** (classi CSS verificate):
- Sezioni: `span.fallen-box-title` → ANAGRAFICA, POSIZIONE MILITARE, CATTURA, DECESSO, INTERNAMENTO, FONTI
- Label: `div.col-xs-5` (senza `fallen-field-margins`)
- Valori: `div.fallen-field-margins`
- Note: `div.col-xs-12` con testo libero (matricola, prima sepoltura, fonti)

**Campi estratti**:
- Anagrafica: cognome, nome, data nascita, comune, provincia, regione
- Militare: grado, reparto, arma
- Cattura: fronte, luogo, data, matricola (da note)
- Decesso: data, luogo/fronte, sepoltura, causa morte
- Internamento: lista campi (Stalag I B, IV B, IV F, ecc.)
- Fonti: testo libero

**Provider** (`ProviderLeBI`):
- `search()` → ricerca per cognome, ritorna lista record con URL
- `get_metadata()` → parsing HTML completo scheda
- `get_document()` → verifica disponibilità PDF
- `build_search_url()` → URL ricerca con parametri pre-compilati

**Adapter** (`LeBIAdapter`):
- `discover_resources()` → ricerca per cognome con paginazione
- `parse_record()` → parsing completo + hash metadati
- `extract_person_mentions()` → 1 menzione per scheda (persona principale)
- `extract_facts()` → fatti: birth, capture, internment, death, burial
- `detect_digital_objects()` → PDF scheda

**Compliance**: policy `lebi` / dominio `lessicobiograficoimi.it`
- `METADATA_ONLY` con download PDF pubblico
- Attribution required: "ANRP — LeBI, Lessico Biografico degli IMI"
- No uso commerciale

**Ricerca federata in `search_validator.py`**:
- LeBI interrogato per ogni nome archivio (max 5) alongside ICRC
- Risultati priorizzati: ICRC per-nome → LeBI per-nome → ICRC query → LeBI query → altri

### 4.7.1 Linking LeBI (`external_link_service.py`)

**Estensioni matching**:
- **Camp/Luogo internamento**: confronto `camp_raw` menzione vs `camp_col` record interno (peso 1.0)
- **Data decesso**: confronto `event_date_text` vs `death_date_col` (peso 1.5, conflitto grave se differenza >2 anni)
- **grave_conflicts**: inizializzato a lista vuota, merge da entrambe le fonti (date nascita + date decesso)

**Funzioni batch**:
- `generate_links_for_provider(provider, limit)` — genera collegamenti per tutte le menzioni di un provider
- `detect_omonimie(provider, min_score)` — rileva menzioni con 2+ candidati con score gap < 0.15
- `review_link_with_type(link_id, ..., link_type='lebi_match')` — revisione con link_type personalizzato per record_links bidirezionali

### 4.7.2 Import incrementale LeBI (`external_metadata_service.py`)

**Checkpoint/Resume**:
- `run_import(provider, ..., resume=True)` — riprende dall'ultimo job incompleto
- URL già processati recuperati da `external_source_records` e skippati
- Job record aggiornato su `external_import_jobs` con `processed_records`, `error_count`, `last_error`
- Update batch ogni `batch_size` record (default 50) per ridurre I/O

**Helper LeBI**:
- `import_single_lebi_record(lebi_id)` — import singola scheda per ID
- `import_lebi_by_surname(surname, max_records)` — import batch per cognome

**Statistiche ritornate**: `total`, `processed`, `inserted`, `updated`, `unchanged`, `skipped`, `errors`

### 4.8 Compliance Gate (`compliance_gate.py`)

**File**: `@/compliance_gate.py:1-461`

**Funzione**: Motore centralizzato di valutazione conformità. Nessun modulo deve scaricare/pubblicare/esportare/inviare dati senza passare di qui.

**Classificazioni risorsa**:
- `METADATA_ONLY` — Solo metadati, no download
- `PUBLIC_VIEW` — Visualizzazione pubblica
- `PUBLIC_DOWNLOAD` — Download pubblico
- `REQUEST_REQUIRED` — Richiesta necessaria
- `AUTHORIZATION_REQUIRED` — Autorizzazione necessaria
- `RESTRICTED` — Accesso riservato
- `RIGHTS_UNKNOWN` — Diritti sconosciuti

**Azioni controllate**:
- `INDEX_METADATA`, `GENERATE_LINKS`, `DOWNLOAD_FILE`, `RUN_OCR`
- `EXTRACT_PERSONAL_DATA`, `SHOW_TO_AUTHENTICATED_USER`, `SHOW_PUBLICLY`
- `INCLUDE_IN_DOSSIER`, `EXPORT`, `DELETE`, `REFRESH_SOURCE`

**Decisioni**: `ALLOW`, `ALLOW_WITH_LIMITATIONS`, `REQUIRE_REVIEW`, `REQUIRE_AUTHORIZATION`, `DENY`

**Policy**: Tabella `source_policies` con regole per dominio/provider. Seed iniziale all'avvio.

### 4.8 Fonti Esterne CRI — Modulo Fase 2

**File coinvolti**:
- `@/external_sources_schema.py` — Schema DB (6 tabelle + estensione record_links)
- `@/external_sources_models.py` — Modelli Pydantic
- `@/sources_external_base.py` — Adapter base (ABC)
- `@/sources_external_archimista.py` — Adapter Archimista (CRI Milano)
- `@/external_metadata_service.py` — Service import incrementale
- `@/external_link_service.py` — Service linking (matching, scoring, conflitti)
- `@/external_sources_api.py` — FastAPI router

**Architettura adapter**:
```
BaseAdapter (ABC)
├── discover_resources() → lista URL da crawlare
├── parse_record(url) → metadati + entità da pagina HTML
├── extract_person_mentions() → persone menzionate
├── extract_facts() → fatti storici
├── extract_digital_objects() → oggetti digitali
├── _normalize_url() → normalizzazione URL
├── _rate_limit() → rate limiting rispettoso
└── _metadata_hash() → hash per change detection

ArchimistaAdapter(BaseAdapter)
├── Base URL: https://cri-mi.archimista.com
├── Parsing HTML con BeautifulSoup
├── Gerarchia: fonds → series → units
├── Estrazione: titolo, data, descrizione, segnatura, luoghi, persone
└── User-Agent: IMI-Extractor/1.0 (research; +https://imi-extractor.org)
```

**Import incrementale** (`external_metadata_service.py`):
1. `run_import(provider, archive_url, max_records)`:
   - Crea job in `external_import_jobs`
   - `adapter.discover_resources()` → lista URL
   - Per ogni URL: `adapter.parse_record(url)` → metadati
   - `upsert_record()` — insert or update basato su hash metadati
   - Salva `external_person_mentions`, `external_source_facts`, `external_digital_objects`
   - Checkpoint progress
2. Resume: skip record con hash immutato
3. Thread-safe con lock

**Linking pipeline** (`external_link_service.py`):
1. `generate_links_for_record(record_id)`:
   - Estrae menzioni persone dal record esterno
   - Per ogni menzione: `generate_links_for_mention(mention_id)`
   - Candidate generation: cerca in tabelle interne (internati, decorati, caduti_*, menzioni, entita)
   - Matching:
     - **Deterministic**: match esatto cognome + nome + data nascita
     - **Probabilistic**: similarità nome + match luogo + match periodo
   - Scoring: 0.0-1.0 basato su pesi
   - Conflict detection: omonimi, match multipli
   - Salva candidati in `external_record_links` con status `candidate`
2. `review_link(link_id, decision, notes)`:
   - Human-in-the-loop: `approved` / `rejected` / `needs_more_info`
   - Track reviewer + timestamp

---

## 5. Flussi dati end-to-end

### 5.1 Ricerca federata completa

```
Frontend (index.html)
    │
    ├── goSearch("Rossi Mario")
    │
    ▼
voci-data.js searchLive("Rossi Mario")
    │
    ├── GET /api/search-validated?q=Rossi+Mario&limit=20
    │
    ▼
app.py → memory_router.route_query("Rossi Mario")
    │
    ├── 1. Cue extraction: persona="Rossi Mario", cognome="Rossi", nome="Mario"
    ├── 2. SQL exact: SELECT * FROM internati WHERE cognome='ROSSI' AND nome='MARIO'
    ├── 3. FTS5: SELECT * FROM idx_entita_search WHERE entita_search MATCH 'Rossi Mario'
    ├── 4. Graph: SELECT * FROM entita e JOIN collegamenti c ON ...
    ├── 5. Archivio fonti: SELECT * FROM archivio_fonti WHERE persone_possibili LIKE '%Rossi%'
    │
    ▼
Response: { subjects: {imi_123: {...}, cad_456: {...}}, 
            events: {},
            confirmations: [...],
            validations: [...],
            externalSources: [...],
            status: "local_only" | "federated" | "ai_enhanced" }
    │
    ▼
Frontend renderizza risultati con badge verified/partial/unverified
    │
    ├── User click "Rossi Mario" (imi_123)
    │
    ▼
openDossier('subject', 'imi_123')
    │
    ├── loadSoldierDossier(123) — 3 API parallele:
    │   ├── GET /api/internati/123/fonti → fonti DB locale
    │   ├── GET /api/internati/123/links → federated_search su 26 provider
    │   └── GET /api/internati/123/opengraph → card anagrafica
    │
    ▼
Frontend renderizza dossier:
    ├── Timeline (nascita, cattura, internamento, sorte)
    ├── Sources (verificate + da verificare)
    ├── Perspectives (it/de/allied — raggruppate per archivio)
    └── Gaps (campi mancanti, provider suggeriti)
    │
    ├── User click "Genera dossier verificato"
    │
    ▼
POST /api/biography { subject_type: 'soldier', soldier_id: 123 }
    │
    ▼
biography.generate_soldier_biography(123)
    ├── soldier_dashboard.get_soldier_dashboard(123) → dati certi + fonti
    ├── _find_letters_mentioning("Rossi") → lettere OCR
    ├── scrape_if_stale() → fonti web verificate
    ├── Costruisce prompt (SOLO fonti verificate)
    └── _call_with_fallback() → GPT → Claude → Mistral → Perplexity
    │
    ▼
Response: { risposta: "## SINTESI\n...", online_sources: [...], provider: "gpt" }
    │
    ▼
Frontend mostra biografia AI + fonti citate
```

### 5.2 Cross-fonti e cross-DB analysis

```
linker.py (batch job)
    │
    ├── Per ogni tabella (internati, decorati, caduti_*, menzioni, ...):
    │   ├── Estrae nomi → _save_persona_with_variants()
    │   │   └── save_entita(tipo='persona', valore='Rossi Mario', ...)
    │   ├── Estrae luoghi → save_entita(tipo='luogo', ...)
    │   └── Estrae eventi → save_entita(tipo='evento', ...)
    │
    ├── Crea collegamenti:
    │   └── INSERT INTO collegamenti (entita_id, fonte_tabella, fonte_id, ...)
    │
    ▼
_gen_record_links.py (batch job)
    │
    ├── Match same death year + place → record_links
    ├── Match same decoration year → record_links
    ├── Match same archival fondo → record_links
    └── Match same event → record_links
    │
    ▼
search_service.py search_entities("Rossi Mario")
    │
    ├── FTS5/BM25 su idx_entita_search
    ├── Graph traversal: entita → collegamenti → entita correlate
    └── Ritorna: entità + num_collegamenti + record sorgente
    │
    ▼
Frontend: tab "Collegamenti" nel dossier mostra cross-DB links
```

### 5.3 Fonti Esterne CRI — import e linking

```
Frontend (rc.html) → setView('external-sources')
    │
    ├── GET /api/external-sources/records?page=1
    │
    ▼
external_sources_api.py → list_records()
    │
    ├── SELECT * FROM external_source_records ORDER BY created_at DESC
    │
    ▼
Frontend renderizza tabella record esterni
    │
    ├── User click "Import" 
    │
    ▼
POST /api/external-sources/import { provider: 'archimista', archive_url: '...' }
    │
    ▼
external_metadata_service.run_import()
    ├── Crea job in external_import_jobs
    ├── ArchimistaAdapter.discover_resources() → lista URL fondi/units
    ├── Per ogni URL:
    │   ├── fetch_page(url) → HTML (con rate limiting)
    │   ├── parse_record(url) → metadati strutturati
    │   ├── _metadata_hash() → SHA256 metadati
    │   ├── upsert_record() — insert/update se hash cambiato
    │   ├── save_person_mentions() → external_person_mentions
    │   ├── save_facts() → external_source_facts
    │   └── save_digital_objects() → external_digital_objects
    └── Update job progress
    │
    ▼
Frontend: GET /api/external-sources/import/status → monitor progress
    │
    ├── User click record → loadExternalRecord(id)
    │
    ▼
GET /api/external-sources/records/{id}
    │
    ├── SELECT * FROM external_source_records WHERE id=?
    ├── SELECT * FROM external_person_mentions WHERE external_source_record_id=?
    ├── SELECT * FROM external_source_facts WHERE external_source_record_id=?
    ├── SELECT * FROM external_digital_objects WHERE external_source_record_id=?
    └── SELECT * FROM external_record_links WHERE external_source_record_id=?
    │
    ▼
Frontend renderizza dettaglio: metadati, gerarchia, menzioni, fatti, oggetti digitali
    │
    ├── User click "Genera collegamenti"
    │
    ▼
POST /api/external-sources/records/{id}/generate-matches
    │
    ▼
external_link_service.generate_links_for_record(record_id)
    ├── Estrae person_mentions
    ├── Per ogni menzione:
    │   ├── Candidate generation: SELECT da internati, decorati, caduti_*, menzioni, entita
    │   ├── Deterministic match: cognome+nome+data_nascita exact
    │   ├── Probabilistic match: similarity score
    │   ├── Conflict detection: omonimi
    │   └── INSERT INTO external_record_links (status='candidate', score=...)
    │
    ▼
Frontend: mostra candidati con score e badge conflitto
    │
    ├── User review: PUT /api/external-links/{id}/review
    │   ├── { decision: 'approved', notes: '...' }
    │   └── external_link_service.review_link() → status='approved'
    │
    ▼
Link approvato → visibile nel dossier del soldato (se interno)
```

---

## 6. Mappa endpoint → file di implementazione

| Endpoint | File | Funzione |
|---|---|---|
| `GET /` | app.py:128 | `index()` → serve index.html |
| `GET /riconoscimenti` | app.py:133 | `rc_index()` → serve rc.html |
| `GET /api/search-validated` | app.py | `search_all()` con memory_router |
| `POST /api/ai-research` | app.py:523 | `ai_research.research()` |
| `POST /api/biography` | app.py:1518 | `biography.generate_soldier_biography()` |
| `POST /api/event/report` | app.py:1553 | `biography.generate_event_report()` |
| `POST /api/event/report/{tab}` | app.py:1569 | `biography.generate_event_tab_report()` |
| `POST /api/event/chat` | app.py:1658 | `biography._call_with_fallback()` |
| `POST /api/fonte/analyze` | app.py:1601 | `biography.analyze_single_source()` |
| `POST /api/fonte/generate-images` | app.py:1615 | `biography.generate_source_images()` |
| `POST /api/soldier/images` | app.py:1638 | `biography.generate_soldier_images()` |
| `GET /api/soldiers/{id}/dashboard` | app.py:1358 | `soldier_dashboard.get_soldier_dashboard()` |
| `GET /api/internati/{id}/fonti` | app.py:1367 | `soldier_dashboard.get_soldier_fonti_indice()` |
| `GET /api/internati/{id}/links` | app.py:1376 | `federated_search()` per soldato |
| `GET /api/providers` | app.py:1268 | `federation.list_providers()` |
| `POST /api/source/search` | app.py:1291 | `federation.federated_search()` |
| `POST /api/source/fetch` | app.py:1304 | `federation.fetch_source()` |
| `GET /api/source/stats` | app.py:1327 | `federation.get_federation_stats()` |
| `GET /api/events` | app.py:1713 | `events.get_eventi_curati()` |
| `GET /api/events/1gm` | app.py:1749 | `events.get_eventi_1gm()` |
| `GET /api/events/1gm/{name}` | app.py:1755 | `events.get_evento_1gm_dossier()` |
| `GET /api/credits` | app.py | `credits.get_usage_summary()` |
| `GET /api/external-sources` | external_sources_api.py:87 | `list_sources()` |
| `GET /api/external-sources/records` | external_sources_api.py:93 | `list_records()` |
| `GET /api/external-sources/records/{id}` | external_sources_api.py | `get_record()` |
| `POST /api/external-sources/import` | external_sources_api.py | `start_import()` |
| `POST /api/external-sources/records/{id}/generate-matches` | external_sources_api.py | `generate_matches()` |
| `PUT /api/external-links/{id}/review` | external_sources_api.py | `review_link()` |
| `GET /api/rc/*` | rc_api.py, rc_api_ext.py | 40+ endpoints riconoscimenti |

---

## 7. Configurazione e deployment

### 7.1 Variabili d'ambiente (`.env`)

```env
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname  # opzionale (default: SQLite)

# AI Providers
OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
PERPLEXITY_API_KEY=pplx-...

# Optional: Stability AI per image generation fallback
STABILITY_API_KEY=sk-...

# Frontend
# Nessuna variabile richiesta (SPA statica)
```

### 7.2 Avvio

```bash
# Installazione dipendenze
pip install -r requirements.txt

# Avvio server (sviluppo)
python app.py  # o: uvicorn app:app --reload --port 8000

# Frontend pubblico: http://localhost:8000/
# Frontend operatori: http://localhost:8000/riconoscimenti
```

### 7.3 Dipendenze principali

```
fastapi, uvicorn
openai, anthropic, mistralai
requests, beautifulsoup4
pdfplumber, pymupdf (fitz), Pillow
playwright (per TNA WAF)
psycopg2-binary (per PostgreSQL)
```

---

## 8. Note per il frontend developer

1. **API base URL**: Tutte le API sono sotto `/api/`. Il frontend operatori usa `/api/rc/` come base.
2. **Autenticazione operatori**: Session cookie. Login via `POST /api/rc/auth/login { username, password }`. Check auth via `GET /api/rc/auth/me`.
3. **Error handling**: API ritornano `HTTPException` con `detail` in italiano. Il frontend usa `toast(err.message, 'error')`.
4. **i18n**: Solo frontend pubblico ha i18n (it/en/de/fr). Frontend operatori è solo italiano.
5. **State management**: Frontend pubblico usa `support.js` (Signals). Frontend operatori usa oggetto `state` globale + `render()`.
6. **AI responses**: Le risposte AI sono in markdown. Il frontend le mostra come testo pre-formattato (non c'è un parser markdown integrato).
7. **Fonti Esterne**: Il modulo CRI è accessibile dal nav "Fonti Esterne" in rc.html. Endpoint base: `/api/external-sources`.
8. **Rate limiting**: Il backend implementa rate limiting rispettoso negli adapter esterni (delay tra richieste). Il frontend non deve gestirlo.
9. **File upload**: `POST /api/external-sources/documents/upload` accetta multipart/form-data.
10. **WebSocket**: Non usato. Tutte le comunicazioni sono HTTP request/response. Le operazioni lunghe (import, estrazione) sono async con polling status.

---

*Documento generato il 2026-07-23. Aggiornare in caso di modifiche architetturali.*
