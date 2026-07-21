# Analisi connessione DB ↔ frontend — IMI Extractor

Aggiornato: 21 luglio 2026
Template unico: `templates/index.html` (1GM + 2GM)

---

## 1. Panoramica

Dopo la rimozione del frontend dedicato `/1gm`, l'unico punto di accesso utente è `/` (`templates/index.html`). Questo template richiama un solo modulo dati: `voci-data.js`, che a sua volta esegue tutte le chiamate al backend FastAPI.

I dati arrivano da **due database principali**:
- `imi_internati.db` (o equivalente live): entità, internati, caduti, decorati, fonti, collegamenti.
- `eventi_1gm.db`: eventi curati Prima Guerra Mondiale con i relativi link a caduti/decorati/documenti/fonti.

Le chiamate AI (biografia, report, immagini, chat) non leggono direttamente il DB ma usano i dati già estratti dalle funzioni di backend.

---

## 2. Endpoint API consumati da `index.html`

| # | Sezione UI | Endpoint | Metodo | Backend (app.py) | Modulo/FUNZIONE | DB coinvolto | Note |
|---|------------|----------|--------|------------------|-----------------|--------------|------|
| 1 | Home — statistiche e grafici | `/api/stats/ww1` | GET | `api_stats_ww1()` | `events.py::stats_ww1` | `imi_internati.db` + altri | Dati aggregati WW1 |
| 2 | Home — ricerca live | `/api/search` | GET | `api_search()` | `search.py` vari | `imi_internati.db` | Cerca soggetti, eventi, fonti |
| 3 | Home — ricerca con validazione | `/api/search-validated` | GET | `api_search_validated()` | validazione + `search.py` | `imi_internati.db`, provider esterni | Discrepanze e fonti esterne |
| 4 | Ricerca — conferma correzione | `/api/search/confirm` | POST | `api_search_confirm()` | `database.py` (update) | `imi_internati.db` | Scrive correzioni utente |
| 5 | Home / esplora — eventi 1GM | `/api/events/1gm` | GET | `api_events_1gm_list()` | `events.py::get_eventi_1gm` | `eventi_1gm.db` | Lista eventi con stats |
| 6 | Dossier evento 1GM | `/api/events/1gm/{event_name}` | GET | `api_event_1gm_dossier()` | `events.py` + `event_query_engine.py::query_event` | `eventi_1gm.db` + `imi_internati.db` | Dossier completo |
| 7 | Tab Caduti evento 1GM | `/api/events/1gm/{event_name}/caduti` | GET | `api_event_1gm_caduti()` | `events.py::get_eventi_1gm_caduti` | `eventi_1gm.db` + `imi_internati.db` | Paginato 50, search |
| 8 | Tab Decorati evento 1GM | `/api/events/1gm/{event_name}/decorati` | GET | `api_event_1gm_decorati()` | `events.py::get_eventi_1gm_decorati` | `eventi_1gm.db` + `imi_internati.db` | Paginato 50, search |
| 9 | Tab Internati evento | `/api/events/{event_name}/internati` | GET | `api_event_internati()` | `events.py::get_internati_per_evento` | `imi_internati.db` | Paginato 50, search |
| 10 | Dossier soggetto — fonti | `/api/fonti-risorse` | GET | `api_list_fonti_risorse()` | `database.py::get_fonti_risorse` | `imi_internati.db` (`fonti_risorse`, `fonti_indice`) | Filtra per `fonte_id` |
| 11 | Dossier soldato — AI | `/api/biography` | POST | `api_generate_biography()` | `biography.py` | `imi_internati.db` (via `database.py`) | Generazione narrativa AI |
| 12 | Dossier soldato — immagini AI | `/api/soldier/images` | POST | `api_generate_soldier_images()` | `biography.py` | `imi_internati.db` + cache PNG | Genera immagini DALL-E |
| 13 | Dossier evento — report AI | `/api/event/report` | POST | `api_generate_event_report()` | `biography.py` | `eventi_1gm.db` + `fonti_indice` | Report convergenze |
| 14 | Dossier evento — report cronologico | `/api/event/report/chronological` | POST | `api_generate_chronological_report()` | `biography.py` | `eventi_1gm.db` + `fonti_indice` | Timeline narrativa |
| 15 | Dossier evento — chat AI | `/api/event/chat` | POST | `api_event_chat()` | `biography.py` | cache in `ai_ricerche` | Follow-up domande |
| 16 | Dossier fonte — analisi AI | `/api/fonte/analyze` | POST | `api_analyze_source()` | `biography.py` | `fonti_indice` | Riassunto fonte |
| 17 | Dossier fonte — immagini AI | `/api/fonte/generate-images` | POST | `api_generate_source_images()` | `biography.py` | `fonti_indice` | Immagini per fonte |
| 18 | Dettaglio internato | `/api/internati/{rid}` | GET | `api_get_internato()` | `events.py::get_internato_by_id` | `imi_internati.db` (`internati`) | Scheda anagrafica |
| 19 | Dettaglio caduto | `/api/caduti/{id}` | GET | (route presente in app.py) | `soldier_dashboard.py` / `database.py` | `imi_internati.db` (caduti_*) | Scheda caduto |
| 20 | Dettaglio decorato | `/api/decorati/{id}` | GET | (route presente in app.py) | `soldier_dashboard.py` / `database.py` | `imi_internati.db` (`decorati*`) | Scheda decorato |
| 21 | Esplora — grafi luoghi | `/api/graph/luoghi` | GET | route graph | `database.py` / `search.py` | `imi_internati.db` | Aggregazione geospaziale |
| 22 | Esplora — grafi mesi | `/api/graph/mesi` | GET | route graph | `database.py` / `search.py` | `imi_internati.db` | Aggregazione temporale |
| 23 | Esplora — grafi paesi | `/api/graph/paesi` | GET | route graph | `database.py` / `search.py` | `imi_internati.db` | Aggregazione per nazione |
| 24 | Esplora — architettura soldati | `/api/graph/soldati/architecture` | GET | route graph | `database.py` | `imi_internati.db` | Analisi cluster architetturale |
| 25 | Esplora — cluster soldati | `/api/graph/soldati/clusters` | GET | route graph | `database.py` | `imi_internati.db` | Clustering soldati |

---

## 3. Tabelle DB principali toccate

### `imi_internati.db`
- `internati` — dati anagrafici e di prigionia WW2.
- `caduti_cwgc`, `caduti_albooro`, `caduti_ministero`, `caduti_sardi`, `caduti_bologna` — caduti da fonti diverse.
- `decorati`, `decorati_nastroazzurro` — decorati e albi.
- `entita` — entità normalizzate (persone, luoghi, eventi, unità).
- `collegamenti` — relazioni cross-dataset tra entità.
- `fonti_indice` — fonti archivistiche catalogate.
- `fonti_risorse` — risorse esterne scrape/federate.
- `fonti_narrative` / `lettere_personali` — fonti personali, foto, memoriali.
- `menzioni` — menzioni in documenti.
- `ai_ricerche` — cache/storico ricerche AI.

### `eventi_1gm.db`
- `eventi_1gm` — eventi curati Prima Guerra Mondiale (nome, date, luogo, aliases).
- `event_links` — collegamenti evento ↔ soldato_caduto / soldato_decorato / documento / fonte.

---

## 4. Duplicazioni e colli di bottiglia rilevati

| Problema | Livello | Dettaglio |
|----------|---------|-----------|
| **Frontend 1GM + WW2 fusi ma con logica condizionale** | Frontend | `index.html` contiene branch `isSoldier`, `isEvent`, `tabCadutiActive`, `tabInternatiActive` per decidere cosa mostrare. La manutenzione crescerà. |
| **Tre modelli di ricerca in parallelo** | Backend | `search.py`, `search_all()` in `database.py`, `api_search()`, `api_conv_search()`, `api_search_validated()` hanno sovrapposizioni. |
| **Caricamento eventi 1GM duplicato** | Backend | `/api/events` e `/api/events/1gm` restituiscono entrambi eventi 1GM. `/api/events` include `eventi_1gm` e `curati` (WW2). `/api/events/1gm` filtra solo 1GM. |
| **Caduti/Decorati evento 1GM: JOIN runtime** | Backend | `get_eventi_1gm_caduti` e `get_eventi_1gm_decorati` aprono due connessioni SQLite (`eventi_1gm.db` e `imi_internati.db`) e fanno lookup degli ID. Per eventi grandi (45.869 caduti Carso) è pesante se non paginato. |
| **Fonti esterne: federazione sincrona in ricerca** | Backend | `api_search_validated` chiama provider esterni in linea; timeout possibili. |
| **Cache immagini AI mista** | Backend/File | `source_cache/` contiene PNG generate; non è in `.gitignore` (ora presenti in repo). Crescerà di dimensione. |

---

## 5. Raccomandazioni

1. **Unificare endpoint eventi**: valutare se `GET /api/events` possa sostituire `GET /api/events/1gm` con un parametro `scope=1gm|ww2|all`.
2. **Indicizzare `event_links`**: verificare che esistano indici su `evento_id` e `link_type` in `eventi_1gm.db` per i tab Caduti/Decorati.
3. **Decouple fonti esterne**: spostare `search_validated` in background o cache per evitare blocchi UI.
4. **Rifattorizzare `search.py`/`database.py`**: consolidare le tre funzioni di ricerca in un'unica API con scope e filtri.
5. **Aggiungere `source_cache/` a `.gitignore`** se le immagini AI sono rigenerabili, per non gonfiare il repo.
6. **Documentare il modello dati**: creare uno schema `docs/DATA_MODEL.md` con le tabelle, i campi e i mapping frontend.

---

## 6. Mappa concettuale: dove finisce ogni click in `index.html`

```
Utente su /
├── Home search ──> /api/search ----------------> search.py + imi_internati.db
├── Ricerca 1GM ──> /api/search/ww1  ----------> events.py + imi_internati.db
├── Seleziona evento 1GM
│   ├── Dossier ──> /api/events/1gm/{name} ----> events.py + eventi_1gm.db
│   ├── Caduti  ──> /api/events/1gm/{name}/caduti -> events.py + eventi_1gm.db + imi_internati.db
│   ├── Decorati -> /api/events/1gm/{name}/decorati -> events.py + eventi_1gm.db + imi_internati.db
│   ├── Internati -> /api/events/{name}/internati -> events.py + imi_internati.db
│   ├── Report AI -> /api/event/report -----------> biography.py
│   ├── Chat AI  --> /api/event/chat ------------> biography.py
│   └── Fonti    --> /api/events/{name}/sources -> events.py + fonti_indice
├── Seleziona soggetto
│   ├── Dossier  --> /api/fonti-risorse ---------> database.py + fonti_risorse
│   ├── Biografia AI -> /api/biography ----------> biography.py
│   └── Immagini AI -> /api/soldier/images ------> biography.py
└── Esplora grafici -> /api/graph/* -------------> database.py + imi_internati.db
```
