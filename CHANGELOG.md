# CHANGELOG - IMI Extractor

## 2026-07-20 — Rimozione frontend 1GM dedicato

### Frontend
- **Rimosso il sito web dedicato alla Prima Guerra Mondiale** (`/1gm`):
  - eliminato `templates/PRIMA_Guerra/` (index.html, voci-data-1gm.js);
  - eliminato `templates/voci-data-1gm.js` e `templates/index-1gm.html`;
  - rimosse le route FastAPI `/1gm` e `/voci-data-1gm.js` da `app.py`;
  - rimosso `tests/test_frontend_1gm.py`.
- **Unificazione frontend comune**: `templates/index.html` rimane l'unico punto di accesso per Prima e Seconda Guerra Mondiale.
- **Dati 1GM intatti**: nessun database `.db` eliminato; record, tabelle e API `/api/events/1gm` restano invariati.

## 2026-07-20 — Fix tab evento Caduti/Decorati e AI buttons su risultati ricerca

### Backend (`events.py`, `event_query_engine.py`)
- **Normalizzazione nome evento**: fix per ID URL-friendly con underscore (`battaglia_del_carso` → `Battaglia del Carso`) nei lookup di `find_event`, `get_eventi_1gm_caduti`, `get_eventi_1gm_decorati` e `get_internati_per_evento`.
- **Case-insensitive fallback**: i fallback dopo sostituzione underscore usano `UPPER(nome)` e `UPPER(value)` nelle query SQLite, risolvendo il mismatch tra `battaglia del carso` e `Battaglia del Carso`.
- **Endpoint verificati**: `/api/events/1gm/battaglia_del_carso`, `/.../caduti`, `/.../decorati` restituiscono ora i dati corretti (caduti: 45869, decorati: 36339 per Battaglia del Carso).

### Frontend (`templates/index.html`)
- **Stili pre-calcolati**: spostate tutte le espressioni dinamiche da inline `style` a proprietà JS pre-computate (`confBarStyle`, `dotStyle`, `labelStyle`, `cardStyle`, `linkStyle`, `bubbleStyle`, `rowStyle`), riducendo i falsi positivi del linter CSS.
- **AI buttons su risultati ricerca**: aggiunti bottoni `Dossier AI` e `Immagini AI` sulle card persona nella home search, con handler che aprono il dossier e lanciano la generazione.
- **`generateSoldierBio` / `generateSoldierImages`**: estese per accettare un `id` opzionale, permettendo la generazione direttamente dalla lista risultati.

### Server
- Riavvio del backend FastAPI/uvicorn su `http://127.0.0.1:8123` con `--reload`.

## 2026-07-20 — Ricerca universale e tab Internati WW2

### Backend (`events.py`, `app.py`)
- **`search_events`**: nuova funzione per cercare eventi curati WW2 per nome, descrizione o keyword.
- **`/api/search`**: include ora anche la sezione `events` con gli eventi curati trovati.
- **`get_internati_per_evento`**: aggiunto fallback di lookup per nome abbreviato o completo parziale, così l'endpoint funziona sia con "Operazione Achse" che con il nome esteso.

### Frontend (`templates/index.html`, `templates/PRIMA_Guerra/index.html`, `templates/voci-data.js`)
- **Tab Internati evento**: `hasInternati` ora è `true` anche quando il conteggio statico dell'evento indica internati (`src._stats.internati`), quindi il tab compare immediatamente per eventi WW2 con internati collegati.
- **`searchLive`**: popola `events` dai risultati `/api/search`; cerca "Operazione Achse" in home restituisce l'evento curato.
- **`loadEvents1gm`**: nuova funzione in `voci-data.js` per caricare eventi canonici 1GM+WW2 anche nel template PRIMA_Guerra.
- **Scheda internato in PRIMA_Guerra**: `openDossier` per subject `imi_*` carica `loadSoldierDossier` come già avveniva nel template generico.

### Test (`tests/test_api.py`)
- Aggiunti test reali (fixture DB temporaneo) per:
  - ricerca universale che include eventi curati;
  - ricerca "Gaiaschi Luigi" che trova internati;
  - endpoint `/api/events/.../internati` che restituisce internati per l'evento Operazione Achse.

## 2026-07-20 — Fix tab Fonti e anteprima file nel lightbox

### Backend: fix encoding nome evento per internati (`events.py`)
- **`get_internati_per_evento`**: decodifica `+` come spazio prima del lookup dell'evento, per allinearsi al frontend che usa `encodeURIComponent(name.replace(/\s+/g, '+'))`. Senza questo fix l'endpoint restituiva sempre 0 internati per eventi con spazi nel nome.

### Frontend: tab Fonti e lightbox (`templates/PRIMA_Guerra/index.html`, `templates/index.html`)
- **Fix `loadExternalSources`**: ora filtra per `fonte_id` quando disponibile e popola correttamente `access` (`locale`/`online`/`richiesta`) e `url` (`url_documento` o `url_pagina`). Prima il mapping mancava di questi campi, quindi i pulsanti "Apri file" / "Apri originale" non venivano mai attivati.
- **Fix pulsanti evento Fonti**: aggiunti flag booleani `hasCatalogoUrl` e `hasFileUrl` con validazione `http(s)://` per evitare link vuoti/non validi nel tab "Fonti archivistiche collegate all'evento".
- **Lightbox file preview**: il lightbox mostrava solo un placeholder; ora:
  - visualizza **immagini** (`<img>`) per URL che terminano in `.jpg/.png/.webp/...` o `data:image`;
  - visualizza **PDF** in `<iframe>` per URL `.pdf` o `data:application/pdf`;
  - mantiene il placeholder solo quando non c'è anteprima;
  - il pulsante "Apri sul sito dell'archivio" usa l'URL completo (anche se relativo).
  - **Nota tecnica**: gli elementi `<img>` e `<iframe>` vengono iniettati tramite `sc-html` per evitare che il browser tenti di caricare i placeholder `{{ ... }}` come URL reali (404).
- **Immagini AI**: stesso fix `sc-html` per evitare 404 su `{{ aim.image_base64 }}`.

### Backend: CORS (`app.py`)
- Aggiunto `CORSMiddleware` per permettere al browser preview/proxy di caricare asset JS/CSS dal server locale senza blocchi cross-origin.

## 2026-07-20 — Tab Internati WW2, Ricerca server-side, Scheda internato, Record Luigi Gaiaschi

### Backend: endpoint internati (`app.py`, `events.py`)
- **`GET /api/events/{event}/internati`**: parametro `search` aggiunto; filtro SQL LIKE su cognome, nome, grado, luogo_nascita, residenza, luogo_cattura, luogo_internamento, sorte.
- **`GET /api/internati/{rid}/detail`**: scheda dettagliata internato con fonti collegate via `record_links` e fallback per soggetti/persone in `fonti_indice`.
- **Fix** `api_internato_detail`: corretta query `record_links` (`to_id` invece di `from_id`) per recuperare fonti collegate; evitati match generici solo per nome.
- **Indici SQLite** su `imi_internati.db`: creati indici per `cognome`, `nome`, `luogo_internamento`, `luogo_cattura`, `sorte`, `luogo_nascita` per ottimizzare ricerche su grandi dataset.

### Frontend: tab Internati e modale (`templates/PRIMA_Guerra/index.html`, `templates/index.html`)
- **Tab "Internati"** visibile negli eventi che hanno internati; tab con tabella, campo ricerca server-side debounce 350ms, paginazione "Carica altri 50".
- **Modale internato**: campi specifici WW2 (luogo nascita, residenza, luogo cattura, data cattura, luogo internamento, arbeitskommando, mansione, sorte, data, matricola).
- **JS**: `_internatiFilter`, `setInternatiFilter`, `_searchInternatiServer`, `loadMoreInternati`, `openSoldatoModal` esteso a tipo `internato` con endpoint `/api/internati/{id}/detail`.
- **Moduli `voci-data.js` e `voci-data-1gm.js`**: `loadEventDossier` ora carica direttamente `/api/events/{event}/internati` con totale.

### Dati: inserimento record Luigi Gaiaschi (`imi_internati.db`)
- Inserito internato **Luigi Gaiaschi** (id `22808`):
  - Nato a **Nibbiaño (Bergamo)**, **9 gennaio 1912**.
  - Catturato in **Grecia** il **12 settembre 1943** dopo l'armistizio dell'8 settembre.
  - Evento: **Operazione Achse e internamento militare italiano (1943-1945)**.
  - **Divergenza fonti** documentata: fonti italiane indicano Belgrado; fonti dell'Asse indicano Grecia (confermata).
- Inserite 2 fonti in `fonti_indice` e collegate tramite `record_links`:
  - Fonti italiane: cattura a Belgrado (divergenza, confidence 0.5).
  - Fonti dell'Asse: cattura in Grecia (confermata, confidence 0.9).
- Inserita entità corrispondente in `entita` per ricerca globale.

### Testing
- **`/api/events/Operazione+Achse.../internati?search=Gaiaschi`**: ✅ total=1, record id 22808.
- **`/api/internati/22808/detail`**: ✅ has_fonti=true, 2 fonti corrette, luogo cattura Grecia.

## 2026-07-19/20 — Scheda soldato, Ricerca server-side, Fix bug

### Backend: endpoint scheda soldato (`app.py`, `events.py`)
- **`GET /api/caduti/{id}`**: scheda dettagliata caduto con paternità, classe, comune, causa morte, decorazioni collegate, documenti, fonti archivistiche, eventi collegati.
- **`GET /api/decorati/{id}`**: scheda dettagliata decorato con info caduto, eventi collegati.
- **Parametro `search`** in `GET /api/events/1gm/{event}/caduti` e `/decorati`: filtro SQL LIKE su nominativo, grado, reparto, luogo, anno (caduti) / cognome, nome, arma, decorazione, anno (decorati). Permette ricerca su tutti i 45.869 caduti del Carso, non solo sui primi 50 caricati.

### Frontend: modale scheda soldato + ricerca (`templates/PRIMA_Guerra/index.html`, `templates/index.html`)
- **Modale scheda**: cliccando nome caduto/decorato si apre dialog con tutti i dati anagrafici, decorazioni, eventi, documenti, fonti.
- **Campo di ricerca** sopra lista Caduti e Decorati con debounce 350ms → chiama API con `&search=` per filtrare lato server.
- **Nom cliccabili**: evidenziati in colore accento con `cursor:pointer`.
- **Stato JS**: `_soldatoModal`, `_cadutiFilter`, `_decoratiFilter` + metodi `openSoldatoModal`, `closeSoldatoModal`, `setCadutiFilter`, `setDecoratiFilter`, `_searchCadutiServer`, `_searchDecoratiServer`.

### Fix bug
- **Duplicate export `loadEventDossier`** in `voci-data-1gm.js`: rimosso dalla re-export list (era già `export async function`).
- **404 `image_base64`**: immagini AI senza data URI valido → aggiunto check `hasImage`/`noImage` con fallback "Nessuna immagine" in entrambi i template.
- **File temp `_check_schema2.py`** rimosso.

### Testing
- **`/api/caduti/109`** (ALBANI BIAGIO): ✅ 200 OK, nominativo corretto.
- **`/api/decorati/28`** (ABATE ANDREA): ✅ 200 OK, 13 eventi collegati.
- **Ricerca Carso + Gaiaschi**: ✅ Total 1, GAIASCHI GIUSEPPE (id 102126, luogo_morte: Carso).
- **Server**: avviato su `127.0.0.1:8001` con uvicorn `--reload`.

## 2026-07-18 — Report cronologico AI, Analisi fonti AI, Generazione immagini AI

### Backend: nuovi prompt e funzioni (`biography.py`)
- **`CHRONOLOGICAL_REPORT_PROMPT`**: prompt per report cronologico narrativo discorsivo che ricostruisce l'evento in ordine temporale.
- **`SOURCE_ANALYSIS_PROMPT`**: prompt per analisi dettagliata di una singola fonte (metadati + contenuto + contesto evento).
- **`IMAGE_PROMPT_GENERATOR`**: prompt che fa generare all'AI 3-5 prompt in inglese per `gpt-image-1`, con regole di accuratezza storica.
- **`generate_chronological_report()`**: raccoglie fonti verificate e genera report cronologico con fallback provider.
- **`analyze_single_source()`**: analisi singola fonte con metadati DB, contenuto in cache, e contesto evento.
- **`generate_source_images()`**: pipeline completa — genera prompt AI → `gpt-image-1` → fallback Stability AI → caching in `source_fetch_cache`.
- **`_generate_image_dalle()`**: generazione immagini via REST API diretta (bypass SDK OpenAI v1.3.7 incompatibile con httpx). Usa `gpt-image-1` (DALL-E 3 non disponibile con la key corrente).
- **`_generate_image_stability()`**: fallback Stability AI SD3.
- **`_save_generated_image()`** / **`_check_cached_images()`** / **`get_cached_images()`**: caching immagini in `source_fetch_cache` (tabella DB), evita rigenerazione.
- **Fix**: `generate_event_report` ora usa `preferred=None` invece di `"mistral"` per fallback naturale dei provider.
- **Fix**: escape parentesi graffe `{{` `}}` in `IMAGE_PROMPT_GENERATOR` per compatibilità con `.format()`.

### Backend: nuovi endpoint API (`app.py`)
- **`POST /api/event/report/chronological`**: genera report cronologico AI per evento.
- **`POST /api/fonte/analyze`**: analisi AI di singola fonte (richiede `source_id`, `event_name`).
- **`POST /api/fonte/generate-images`**: generazione 3-5 immagini AI per fonte con caching.
- **`GET /api/fonte/{source_id}/images`**: recupera immagini cached per fonte.

### Frontend: nuovi bottoni e UI (`templates/index.html`, `templates/PRIMA_Guerra/index.html`)
- **Tab Cronologia**: bottone "Genera Report Cronologico AI" con display report e gestione errori.
- **Tab Punti Vista**: etichetta aggiornata da "Genera Report" a "Genera Report Convergenze Fonti AI".
- **Tab Fonti**: per ogni fonte, due nuovi bottoni:
  - "Analizza con AI" — genera riassunto strutturato della fonte.
  - "Genera Immagini AI" — genera 3-5 immagini fotorealistiche con barra progresso.
- **Barra progresso** durante generazione immagini (CSS animato).
- **Display immagini** in grid con titolo, prompt, e click per ingrandire.
- **Metodi JS**: `generateChronologicalReport()`, `analyzeSource()`, `generateSourceImages()` in entrambi i template.
- **`renderVals`** aggiornato con stati per-fonte (`_sourceAnalysis`, `_sourceImages`) e report cronologico.

### Testing (18 luglio 2026)
- **Server**: avviato su `127.0.0.1:8000`, 22 eventi caricati, tutti endpoint rispondono.
- **`/api/event/report/chronological`** (Caporetto): ✅ 200 OK, provider Mistral, report cronologico generato.
- **`/api/fonte/analyze`** (source_id=55487, Caporetto): ✅ 200 OK, provider Mistral, analisi generata.
- **`/api/fonte/generate-images`** (source_id=55487, Caporetto): ✅ 5 immagini generate con `gpt-image-1`.
- **Caching**: ✅ seconda chiamata restituisce `from_cache: true`, 5 immagini cached.
- **`/api/fonte/55487/images`**: ✅ 200 OK, 5 immagini recuperate da cache.
- **Fix API key**: aggiornata `OPENAI_API_KEY` nel `.env` con nuova key (`sk-proj-sE-PetMIS0L...`).
- **Fix modello immagini**: DALL-E 3 non disponibile → switch a `gpt-image-1` (disponibile con key corrente).
- **Fix SDK OpenAI**: `openai==1.3.7` incompatibile con `httpx` → REST API diretta con `requests`.

## 2026-07-18 — Fetcher documenti (Gallica/TNA/IWM), Tab Fonti frontend, Chat AI report

### Nuovi fetcher documenti 1GM (`archivio_documenti.py`)
- **`fetch_gallica_sru()`**: Gallica BnF SRU API — foto, manoscritti, periodici francesi WWI. Parsing XML SRU/OAI-DC, estrazione ARK identifier, link diretto al viewer Gallica. Nessuna chiave API richiesta.
- **`fetch_tna_discovery()`**: The National Archives Discovery API — war diaries WO 95. Endpoint pubblico REST JSON, estrazione reference, coveringDates, description. Link diretto a Discovery.
- **`fetch_iwm_collections()`**: Imperial War Museum Collections API — private papers, diari, foto WWI. Endpoint pubblico REST JSON, estrazione id, title, displayDate, thumbnail.
- **Pipeline `documenti_1gm`** aggiornata in `mass_index.py`: 8 step totali (seed + IA + LoC + Wikimedia + Europeana + Gallica + TNA + IWM), stats finali per tipo e provider.

### Frontend: tab Fonti event-centric (`templates/index.html`, `templates/PRIMA_Guerra/index.html`)
- **Nuovo tab "Fonti"** nel dossier evento: visibile solo per eventi (sc-if `dossier.isEvent`), mostra lista fonti archivistiche con titolo, archivio, tipo_fonte, link a catalogo e documento.
- **Tab Caduti e Decorati** aggiunti al template generico `index.html` (erano già presenti in `PRIMA_Guerra/index.html`).
- **Stato tab** (`tabFontiActive`, `tabFontiClass`, `onTabFonti`) aggiunto a `renderVals` in entrambi i template.
- API verificata: `/api/events/1gm/{name}` restituisce 30 fonti per evento (es. Prigionia: 689 fonti totali, 30 mostrate).

### Chat AI follow-up report (`app.py`, `templates/index.html`, `templates/PRIMA_Guerra/index.html`)
- **`POST /api/event/chat`**: endpoint per domande di follow-up dopo il report AI. Riceve `event_name`, `message`, `report` (contesto), `history` (storico chat), usa `_call_with_fallback` (Mistral → Perplexity → GPT).
- **UI chat** sotto il report: area messaggi scrollabile con bubble user/AI, textarea + pulsante Invia, indicatore "AI sta scrivendo…", Enter per inviare.
- **Stato chat** (`_eventChatMessages`, `_eventChatInput`, `_eventChatLoading`) e metodi (`sendEventChatMessage`, `setEventChatInput`, `eventChatKeyDown`) in entrambi i template.

## 2026-07-17 — Integrazione event-centric: API, biography, frontend

### Grafo event-centric esteso (`_gen_event_links.py`, `eventi_1gm.db`)
- **Eventi WW2 aggiunti** (7 nuovi): Operazione Achse, Eccidio di Cefalonia, Campagna di Russia (ARMIR), Battaglia di Tobruk, Mauthausen e Gusen, Lavoro forzato nel Reich, Battaglia di Cassino.
- **Totale eventi canonici**: 22 (15 WW1 + 7 WW2).
- **Documenti collegati**: 1→13 (match multi-evento, campi estesi: title, description, place, creator, date_text, provider_collection).
- **Internati WW2 collegati**: 12.759 link `internato_ww2` (match luogo_cattura/luogo_internamento ↔ eventi WW2).
- **Confidence decorati variabile**: 0.6 per eventi ≤1 anno, 0.4 per 2 anni, 0.3 per >2 anni.
- **CWGC WW1**: 1 match (cimiteri inglesi in Francia, match "Tobruk").
- **caduti_ministero**: 0 match (dati luogo_sepoltura/nazione_decesso tutti vuoti).
- **Totale event_links**: 911.832 (688.607 decorati, 188.791 caduti, 12.759 internati, 1.703 fonti, 13 documenti, 1 CWGC).

### API endpoints (`app.py`, `events.py`)
- **`GET /api/events/1gm`**: lista eventi canonici con stats aggregate (caduti, decorati, documenti, fonti, internati, CWGC).
- **`GET /api/events/1gm/{event_name}`**: dossier completo evento via `event_query_engine.query_event()`.
- **`GET /api/events/1gm/{event_name}/caduti`**: caduti paginati per evento (temp table per large ID sets).
- **`GET /api/events/1gm/{event_name}/decorati`**: decorati paginati per evento.
- **`GET /api/events`** aggiornato: include sia eventi curati WW2 che eventi 1GM.

### Biography integration (`biography.py`)
- **`_event_centric_context()`**: estrae dati strutturati da `event_query_engine` (caduti, decorati, documenti, fonti con URL) e li inserisce nel prompt AI per `generate_event_biography()`.
- Fonti event-centric con URL aggiunte a `verified_sources` e `online_sources` restituiti al frontend.

### Frontend (`templates/PRIMA_Guerra/`)
- **`loadEvents1gm()`**: carica eventi canonici da `/api/events/1gm`, merge con eventi statici (fallback).
- **`loadEventDossier()`**: carica dossier completo (caduti, decorati, documenti, fonti) da API.
- **Dossier evento**: tab "Caduti" e "Decorati" con tabelle paginate, stats summary su overview, descrizione evento.
- **Eventi dinamici**: 22 eventi reali sostituiscono i 3 eventi statici di fallback.

### Endpoint unificato + subject_type event_1gm (`app.py`)
- **`GET /api/events/{event_name}`**: endpoint unificato con dispatch automatico — prova prima `eventi_1gm.db` (event-centric), poi fallback su eventi curati WW2 (fonti multilaterali). Posizionato dopo le route specifiche `/api/events/1gm/*` per evitare conflitti.
- **`POST /api/biography`** con `subject_type="event_1gm"`: usa `generate_event_biography()` con tutti i dati event-centric (event_query_engine + memory_router + federated_search + web search).
- **Fase 1.6 (entita → eventi)**: verificato e scartato — la tabella `entita` con `tipo='evento'` contiene eventi individuali dei soldati ("deceduto - il 13-2-1945"), non eventi storici canonici. 0 match con 168 alias/keyword degli eventi.

## 2026-07-16 — Validazione AI record_links, Grafo event-centric, Report DB completo

### Validazione AI record_links (`_validate_links_ai.py`)
- **5 cicli di validazione** completati, 20 link casuali per ciclo, 200 validazioni totali.
- **AI provider funzionanti**: Mistral (`mistral-small-latest`) e Perplexity (`sonar`) via REST API diretta (`requests`, nessun SDK).
- **AI provider non disponibili**: OpenAI (key scaduta), Anthropic (modello `claude-3-5-haiku-20241022` deprecato/non accessibile), Gemini (quota esaurita).
- **Risultati**: 93% INVALID, 5% VALID, 2% UNCERTAIN. L'AI giudica i link `stesso_evento_luogo` come non validi: due soldati morti nello stesso luogo e anno non sono necessariamente nello stesso evento specifico (stessa battaglia/stesso giorno).
- **DB separato** `validazioni_ai.db` per evitare lock con pipeline in corso. Main DB `imi_internati.db` aperto in read-only (`PRAGMA query_only=ON`).
- **Helper `_parse_json()`**: parsing robusto di risposte AI con wrapper markdown, estrazione JSON da testo libero, fallback UNCERTAIN.
- **Script stato** `_val_status.py`: report rapido validazioni per provider e ciclo.

### Grafo event-centric (`_gen_event_links.py`, `eventi_1gm.db`)
- **Nuovo paradigma**: invece di collegare soldato-soldato (grafo `record_links`, 93% falsi positivi), sistema event-centric dove ogni evento canonico aggrega soldati, documenti, fonti, diari, immagini.
- **Tabella `eventi_1gm`** (15 eventi canonici): Caporetto, Isonzo, Carso, Piave, Vittorio Veneto, Asiago, Grappa, Pasubio, San Michele, Prigionia, Fronte Macedone, Fronte Albanese, Col di Lana, Monte Nero, Settore Tolmino.
  - Ogni evento: nome, date inizio/fine, luogo, aliases (varianti nome), keywords per ricerca text-match, descrizione.
- **Tabella `event_links`** (799.103 link):
  - 188.198 `soldato_caduto`: caduti Albo d'Oro collegati a eventi per match `luogo_morte` ↔ aliases evento.
  - 610.905 `soldato_decorato`: decorati Nastro Azzurro collegati a eventi per match `anno_decorazione` ↔ range date evento (confidence 0.3, da rifinire).
- **DB separato** `eventi_1gm.db` (123 MB) per evitare lock con pipeline in corso.
- **Top eventi per caduti**: Prigionia 84.315, Carso 45.869, Isonzo 13.859, Caporetto 13.244, Asiago 11.624.
- **TODO**: linking documenti (`archivio_documenti`) e fonti (`fonti_indice`) agli eventi non ancora completato (errore colonna `id` risolto con `rowid`, da rilanciare).

### Report DB completo (`_report_all_db.py`)
- **Script report** che analizza tutti i 3 DB: schema, record, colonne, dati distinti, link, grafo.
- **DB principale** `imi_internati.db`: 1.790 MB, 43 tabelle, 11.621.745 record totali.
- **DB eventi** `eventi_1gm.db`: 123 MB, 3 tabelle, 799.120 record.
- **DB validazioni** `validazioni_ai.db`: 0,1 MB, 200 record.
- **Tabelle principali**: caduti_albooro (342.555), caduti_cwgc (506.446), caduti_ministero (162.646), decorati_nastroazzurro (279.832), internati (20.464), entita (688.738), collegamenti (2.349.417), fonti_indice (35.660), archivio_documenti (218), archivio_fonti (1.153).
- **Encoding fix**: `sys.stdout` wrapper UTF-8 per output Windows cp1252.

### Ispezione schema (`_inspect_schema.py`)
- Verifica colonne reali di tutte le tabelle, sample record, ricerche text-match ("Caporetto", "Isonzo").
- Scoperto: `archivio_documenti` non ha colonna `id` (usa `rowid`), 29 soldati con luogo_morte "Caporetto", 13.859 con "Isonzo", 12 fonti_indice con "Caporetto" nel titolo.

---

## 2026-07-15 — Pipeline 1GM, Fix CWGC, Scoring, URL Ministero Difesa

### Pipeline indicizzazione 1GM (`mass_index.py`)
- **3 nuove pipeline 1GM**: `pipeline_soldati_1gm()`, `pipeline_eventi_1gm()`, `pipeline_luoghi_1gm()`.
- CLI: `python mass_index.py soldati_1gm|eventi_1gm|luoghi_1gm|all_1gm [--limit N]`.
- **Eventi 1GM**: 525 query (25 eventi fissi + 500 dal DB), 111 fonti salvate. Completata in 7504s.
- **Luoghi 1GM**: 320 query (20 luoghi fissi + 300 dal DB), 7 fonti salvate. Interrotta al 50%.
- **Soldati 1GM**: 1000 soldati (500 Albo d'Oro + 500 Nastro Azzurro), 65 fonti salvate. Interrotta al 10%.
- **Totale fonti 1GM nuove**: 194 (109 OPAC SBN, 76 WikiTree, 7 Internet Archive, 2 CWGC).
- **Collegamenti 1GM nuovi**: 139 (127 caduti_albooro, 12 entita).
- Provider interrogati: europeana, internetarchive, gallica, hathitrust, googlebooks, cwgc, memoiredeshommes, iwm_lives, wikitree, internetculturale, ussme, antenati.

### Fix scoring `source_providers/base.py`
- `score_source()`: aggiunto scoring per cue `evento` (match token in titolo/descrizione/URL, +0.10 per token).
- `score_source()`: aggiunto scoring per cue `periodo` (match anni 1914-1918 in testo, +0.08 per anno).
- `MIN_SCORE` abbassato da 0.45 a 0.25 in `mass_index.py` (eventi/luoghi hanno meno token match rispetto a persone).

### Fix nomi provider in `mass_index.py`
- `internet_archive` → `internetarchive`, `memoire_des_hommes` → `memoiredeshommes`, `google_books` → `googlebooks`.
- Aggiunto `internetculturale` alle pipeline eventi_1gm e luoghi_1gm.

### Fix CWGC in `database.py`
- `stats_ww1()`: CWGC filtrato per `guerra='World War 1'` → 35.400 record (prima 506.446, includeva WW2).
- `search_ww1()`: stessa filtro applicato alla ricerca su `caduti_cwgc`.
- Caduti 1GM totali corretti: 594.971 (prima 1.066.017).

### Fix URL Ministero Difesa
- `config.py`: `onorcaduti.difesa.it` (dominio morto) → `www.difesa.it` in `SCRAPER_ALLOWED_DOMAINS`.
- `templates/voci-data.js`: URL `nascaduti.difesa.it/Ricerca` → `www.difesa.it/Il_Ministero/CadutiInGuerra/Pages/RicercaCaduti.aspx`.

### DB stats finali
- fonti_indice totali: 35.624 (era 35.430, +194 fonti 1GM).
- collegamenti totali: 2.349.397 (dopo dedup).
- 0 duplicati, 0 orfani.

### Generazione collegamenti OpenGraph 1GM
- **5 passaggi di generazione**:
  1. `caduti_albooro` → luogo (123k nuovi), unita (217k nuovi)
  2. `decorati_nastroazzurro` → evento (58.769 nuovi, match anno decorazione 1915-1918)
  3. `caduti_cwgc` WW1 → luogo (35k), unita (34k)
  4. `caduti_francia_ww1` → SKIP (colonne luogo/anno non compatibili)
  5. `caduti_ministero` → SKIP (colonne luogo/data non compatibili)
- **Approccio batch in-memory**: entita pre-caricate in dict Python + indice inverso per token (O(1) lookup).
- **5 verifiche**:
  1. Conteggio per tabella/tipo — 33 combinazioni attive.
  2. Duplicati — 0 (rimossi 1.108.627 duplicati preesistenti).
  3. Orfani — 0 (rimossi 2 collegamenti con entita_id inesistente).
  4. Congruenza eventi 1GM — 314k caduti_albooro, 58k decorati, 23k sardi, 54 bologna.
  5. Sample validazione — match corretti (es. "deceduto - 1917" per decorati, luoghi reali per caduti).
- **Collegamenti totali dopo cleanup**: 2.349.397 (era 3.458.024 prima di dedup).

### Archivio documenti 1GM (`archivio_documenti.py`)
- **Nuovo modulo**: archiviazione metadati + deep link di foto/diari WWI (modello Voci dal Fronte).
- **Schema `archivio_documenti`**: 19 campi (provider, external_id, doc_type, title, source_url, thumbnail_url, iiif_manifest, raw_json, ecc.).
- **18 collezioni curate** seedate: Europeana 1914-1918, LoC WWI Prints, IA diari, Gallica BnF, IWM, TNA WO 95, Archivio Diaristico Nazionale (Pieve Santo Stefano), 14-18.it ICCU, Wikimedia Commons, Fondazione Ansaldo, Mémoire des Hommes, AWM, Museo Guerra Rovereto, ACS, Oxford WW1 Poetry.
- **4 fetcher API**: Internet Archive (advancedsearch), Library of Congress (loc.gov JSON), Wikimedia Commons (MediaWiki API), Europeana (Search API con key).
- **Fetcher aggiuntivo**: `fetch_wikimedia_commons()` per foto WWI da Wikimedia.
- **Pipeline `documenti_1gm`** in `mass_index.py`: `python mass_index.py documenti_1gm`.
- **Nessun file binario scaricato**: solo metadati + link diretto alla fonte (deep link).
- **Integrato in `imi_internati.db`** via `database.get_conn()`.

### Grafo record-to-record (`record_links`)
- **Nuova tabella `record_links`**: link diretti tra record (soldati, documenti, fonti) con tipo e confidence.
- **156.694 link** generati:
  - 142.594 `stesso_evento_luogo` (caduti_albooro: soldati morti stesso anno+luogo, star topology)
  - 11.222 `stesso_anno_decorazione` (decorati_nastroazzurro: decorati stesso anno)
  - 2.878 `documento_evento` (caduti_albooro ↔ archivio_documenti: match anno+luogo)
- **Anti-omonimia**: match nomi su cognome+nome completo, non solo cognome.
- **Passo 4-5 (fonte_personale)**: 0 match — le 35.660 fonti sono prevalentemente tedesche/internazionali (Bundesarchiv, Arolsen), non contengono nomi italiani.
- **Script**: `_gen_record_links.py` (6 passi + verifiche).

## 2026-07-14 — Frontend 1GM, Test Harness, Link navigazione, Email MiC

### Frontend Prima Guerra Mondiale (`templates/PRIMA_Guerra/index.html`, `templates/voci-data-1gm.js`)
- Banner immagine 1GM aggiunto e successivamente rimosso su richiesta utente.
- Titolo pagina aggiornato: "Voci dal Fronte — Tutte le Voci, un'Unica Storia" (override `heroTitle2` in `voci-data-1gm.js` per IT/EN/DE/FR).
- Sezione `externalSources` (fonti esterne collegate) verificata: campi titolo, ente_titolare, licenza, tipo_risorsa, url_pagina, url_documento, hasDocument, note_copyright.
- Funzione `loadExternalSources()` chiama `/api/fonti-risorse` e popola `_externalSources` nel dossier.

### Link navigazione (`templates/index.html`)
- Aggiunto link "Prima Guerra Mondiale" nella nav bar del frontend generale, punta a `/1gm`, stile accento grassetto.

### Test Harness — Master file (`tests/test_fonti_risorse_master.py`)
- **83/83 test PASS** - zero failure, zero errori.
- Consolidamento di tutti i test fonti_risorse in un unico file master.
- Fix: DB temp file (Windows file locking), robots_cache clearing tra test, mock HTTP encoding string, copyright regex.
- Copertura: config, DB CRUD/constraints, scraper HTML/metadata/pipeline, robots.txt, domain allowlist, search service, API, security, E2E.

### Test Frontend 1GM (`tests/test_frontend_1gm.py`)
- **50/50 test PASS** - server reale, nessun mock.
- 6 classi: HTML (17), JS (13), Isolation (4), API Integration (8), Data Consistency (4), Assets (5).
- Verifica isolamento: nessun riferimento IMI/WW2/NARA/prigionia nel frontend 1GM.

### Mock utils (`tests/utils/`)
- `mock_db.py`: temp file SQLite DB con `get_test_conn()` e `cleanup_test_db()`.
- `mock_http_client.py`: `MockResponse` con encoding string, `patch_requests_get()`.
- `fake_html_sources.py`: 11 pagine HTML fittizie per test scraper.
- `fake_robots_txt.py`: 6 varianti robots.txt.
- `fake_domain_allowlist.py`: domini autorizzati/bloccati.

### Email MiC
- Template email preparato per Comitato Grande Guerra (Roma) e Soprintendenza ABAP Liguria.
- Richiesta parere favorevole/autorizzazione ex art. 3 punto 3.1 Bando Grande Guerra 2026/2027.
- Contatti: `comitatograndeguerra@cultura.gov.it` / PEC `mbac-comitatograndeguerra@mailcert.beniculturali.it`.
- Contatti Liguria: `sabap-liguria@cultura.gov.it` / PEC `sabap-liguria@pec.cultura.gov.it`.

### Regole memorizzate
- Regola: non usare mock nei test se non strettamente necessario (notificare e spiegare motivo).
- Regola: non creare file di test separati per la stessa feature - un solo master test.

---

## 2026-07-13 — Pipeline multi-AI parallela, Report Engine, Banner, Watchdog

### Fix server (`app.py`)
- `BackgroundTasks` aggiunto all'import FastAPI → server non avviava (`NameError`).
- Endpoint `/api/internati/{rid}/links` ora funzionante.

### Banner frontend (`templates/index.html`, `templates/header_banner.png`)
- Banner sostituisce SVG logo+titolo: immagine full-width sopra navbar sticky.
- CSS: `width:100%; aspect-ratio:5/1; object-fit:cover; max-height:240px` — responsive da mobile a 4K.
- Nuovo banner italiano generato (ratio 5:1, 2480×480px target): soldato in trincea, aereo, carro armato, lettera "cara mamma", titolo "Voci dal Fronte" + sottotitolo archivio.
- Banner cliccabile → torna alla home.

### Pipeline indicizzazione massiva (`mass_index.py`)
- 4 pipeline indipendenti: `soldati`, `reparti`, `eventi`, `luoghi`.
- `soldati`: query cognome+nome su 13 provider (Arolsen, Bundesarchiv, NARA, CWGC, Europeana, IA, HathiTrust, Gallica, TNA, AWM, Antenati, WikiTree, IWM).
- `reparti`: 10.348 unità militari da DB entita — query + varianti DE/EN su NARA/Bundesarchiv/TNA/USSME/IA.
- `eventi`: 16 eventi fissi ad alto valore + fino a 500 dal DB — query IT+EN, include giornali d'epoca (Europeana Press, IA Newspapers, Gallica/BnF, HathiTrust, Google Books).
- `luoghi`: 14 lager fissi (Stalag XVII-B, Mauthausen, Gusen, ecc.) + fino a 300 dal DB.
- ThreadPoolExecutor 4 worker, upsert idempotente su `fonti_indice`, `collegamenti` con colonne reali (`tabella_origine`, `record_id`).
- Endpoint `POST /api/mass-index/start` + `GET /api/mass-index/status`.

### Pipeline multi-AI parallela (`mass_index_parallel.py`)
- 7 agenti in parallelo su task distinti:
  - **OpenAI GPT-4o-mini** → soldati A–F: arricchisce query con varianti nome (grafia tedesca, errori trascrizione).
  - **Anthropic Claude Haiku** → soldati G–L: estrazione varianti + entity linking.
  - **Gemini 1.5 Flash** → soldati M–R: varianti nome per archivi internazionali.
  - **Mistral Small** → soldati S–Z: varianti EN per archivi angloamericani.
  - **Perplexity (web access)** → eventi/battaglie: trova URL diretti a fonti primarie via ricerca web live.
  - **LM Studio Qwen2.5-3B** → reparti: varianti nome unità — completamente opzionale, fallback silenzioso se offline.
  - **Scraper puro** → luoghi/lager: federated_search senza AI.
- Detection automatica LM Studio: `_lmstudio_available` flag, timeout 8s, skip immediato se offline.
- Endpoint `POST /api/mass-index/start-parallel`.

### Report Engine (`report_engine.py`)
- Query libera (evento/unità/luogo/persona) → report narrativo strutturato.
- Flusso: entità DB → soldati collegati → fonti archivistiche → contesto AI → narrative.
- Fallback chain AI: OpenAI → Anthropic → Mistral.
- Auto-detection tipo da keyword (battaglia/operazione → evento, divisione/reggimento → unità, lager/stalag → luogo).
- Arricchimento per soldati: fonti dirette per ciascuno dalla `fonti_indice`.
- Endpoint `GET /api/report?q=...&tipo=auto`.

### Watchdog pipeline (`pipeline_watchdog.py`)
- Monitor ogni 5 minuti: verifica server HTTP, pipeline status, log errori.
- Auto-fix: riavvio uvicorn se server down, riavvio pipeline se bloccata/in errore.
- Log su `pipeline_watchdog.log`.

### Fix DB schema
- Corretti nomi colonne `collegamenti`: `soggetto_tabella` → `tabella_origine`, `soggetto_id` → `record_id`, `tipo` → `tipo_collegamento`.

---

## 2026-07-12 (sera) — Test live Arolsen, refinement TNA/IA, popolamento DB

### Arolsen test live validato
- Flusso ASP.NET confermato: `BuildQueryGlobalForAngular` → session cookie → `GetCount` (7 persone) → `GetPersonList` (7 record GAIASCHI Arturo, nato 13/02/1902) → `GetArchiveList` (1 unità archivistica).
- 40 nuovi record inseriti in `fonti_indice` (query: Gaiaschi, Rossi, Bianchi, Ferrari, Italian internee).

### TNA refinement
- Scoperto: l'API REST Discovery (`/API/search/v1/records`) ignora il parametro `q` (restituisce sempre 42M record non filtrati). Il portale web è dietro AWS WAF (202 challenge).
- Implementato: filtro client-side per periodo WW2 (`numStartDate`/`numEndDate` 1939-1946 + fallback `coveringDates`), filtro pertinenza militare (keyword matching), fetch per reference WO specifiche (WO 392, WO 304, WO 208, WO 309, FO 916).
- 4 record fallback registrati in `fonti_indice`.

### Internet Archive refinement
- Aggiunti filtri temporali Solr: `date:[1940 TO 1946]`, `mediatype:(texts)`, `sort:downloads desc`.
- Strategy 2: broad search con termini italiani (`internati militari italiani`, `prigionieri di guerra italiani`, `campo prigionieri italia`) se query principale < 5 risultati.
- 19 nuovi record inseriti (Nazi Concentration Camps, Tactical And Technical Trends, newsreels, newspapers 1940-41).

### Popolamento DB
- **63 nuovi record** totali in `fonti_indice` da provider live.
- `fonti_indice` totale: 21.062 record (Arolsen 158, TNA 20.025, Internet Archive 66).

---

## 2026-07-12 (pomeriggio) — Consolidamento import, provider reali, README, cleanup

### Consolidamento script import (`import_fonti_personali.py`)
- Unificati `import_lettere_personali.py` + `import_personal_sources.py` in `import_fonti_personali.py`.
- Funzione `import_all(dry_run)` esegue entrambe le migrazioni (lettere OCR + fonti narrative Desktop).
- Entity linking condiviso (`_upsert_persona` con parametro `fonte_tabella` dinamico).
- Modulo verificato: import corretto, nessun errore.

### Provider federation — 6 provider da stub a reali (`source_providers/providers.py`)
- **Arolsen Archives (ITS)**: implementato endpoint reverse-engineered `ITS-WS.asmx` (`collections-server.arolsen-archives.org`). Flusso: `BuildQueryGlobalForAngular` → `GetCount` → `GetPersonList`/`GetArchiveList` con gestione sessioni ASP.NET (cookie-keyed). Estrae LastName, FirstName, PrisonerNumber, PlaceBirth, Dob, Signature.
- **Bundesarchiv**: implementato Invenio REST API (`/api/records` con `q`, `size`, `sort=bestmatch`). Parsing hits con metadata, files.entries per digital objects. Fallback a link catalogo + open data.
- **SHD/Mémoire des Hommes**: parsing HTML strutturato del portale (`/fr/search.php`). Estrazione link `/fr/article.php` con titoli da anchor text. Fallback a basi dati specifiche (WW1/WW2 morts).
- **Archivportal-D (DDB)**: implementato DDB REST API ufficiale (OpenAPI 3.0). Endpoint `/search` con OAuth API key (`DDB_API_KEY` da env). Parametri: query, rows, offset, sort, time_fct. `get_metadata()` via `/items/{id}`.
- **LAC (Library and Archives Canada)**: implementato Canadiana API (`search.canadiana.ca/search?fmt=json`) come endpoint primario + LAC Collection Search come fallback. Parsing docs con id, title, pubmin.
- **Internet Culturale (OPAC SBN)**: migliorato con endpoint OPAC SBN JSON (`/opacmobilegw/search.json`), parsing briefRecords con BID, titolo, autore, pubblicazione, anno. Fallback con regex BID dal HTML. `get_metadata()` via `/opacmobilegw/bid/{id}.json`.

### Documentazione (`README.md`)
- README completamente riscritto: architettura con diagramma ASCII, flusso Research-to-Index, tabella moduli, schema DB completo, tabella provider federation (16 provider con API e autenticazione), API principali, configurazione env.

### Cleanup script scratch
- Rimossi **59 file** con prefisso `_` (`_test_`, `_check_`, `_run_`, `_status_`, `_fix_`, `_bench_`, `_db_`, `_inspect_`, `_search_`, `_start_`, `_verify_`).
- File .py totali: da 107 a 48 (−55%).
- Verificato: nessun modulo di produzione importava gli script rimossi. Tutti i moduli si importano correttamente dopo il cleanup.

---

## 2026-07-12 — Verifica DB live, fix ricerca multi-parola, Tab Gaps, test biography

### Verifica DB live (`imi_internati.db`, 1.4 GB)
- `PRAGMA quick_check` e `PRAGMA integrity_check`: **ok** — DB integro, il "malformed" segnalato era artefatto di mount.
- `lettere_personali`: 1 record (migrazione da `ocr_lettere.db` confermata).
- `fonti_narrative`: 40 record, 69 collegamenti (migrazione Desktop confermata).
- Linker completato: **688.738 entità** (560.133 persone, 102.319 luoghi, 14.952 eventi, 10.348 unità), **4.832.063 collegamenti**.
- `fonti_indice`: 20.999 fonti (TNA 20.021, Internet Culturale 145, Arolsen 118, Bundesarchiv 118, Archivportal-D 116, LAC 116, SHD 116, Internet Archive 47).
- `caduti_cwgc`: 506.446 record (WW2: 452.395, WW1: 35.400, non classificati: 18.651).
- `research_subjects`: 118, `research_subject_sources`: 1.431, `research_gaps`: 472.

### Fix ricerca multi-parola (`database.py`)
- `_where_like_clause()`: cambiato da **OR puro tra token** a **AND tra token, OR tra colonne**.
- Prima: "Gaiaschi Giuseppe" → 14 internati, **0 contenevano "gaiaschi"** (tutti falsi positivi da "Giuseppe").
- Dopo: "Gaiaschi Giuseppe" → **0 falsi positivi** negli internati, 2 caduti pertinenti, 12 fonti_narrative pertinenti.
- "Luigi Gaiaschi" → 0 falsi positivi (prima 14), 6 fonti_narrative pertinenti.
- Test: 130 passed, 1 failed (non correlato: `test_source_locator` unable to open DB temporaneo).

### Tab Gaps in UI (`templates/index.html`)
- Aggiunto tab "Gaps" nella barra investigativa (5° tab dopo Eventi).
- Funzione `renderGapsTab()`: chiama `GET /api/research/gaps`, renderizza card con:
  - Nome soggetto e tipo (soldier/event/unit/place)
  - Campo mancante con label localizzata italiana
  - Badge priorità colorato (high=danger, medium=warning, low=muted)
  - Provider suggerito per colmare il gap
- Integrato in `convSearch()` come step 3b (dopo renderSourcesTab, prima di renderAIResponses).
- Endpoint `/api/research/gaps` verificato: 472 gap aperti, 5 restituiti correttamente.

### Test biography end-to-end (`POST /api/biography`)
- **Soldato** (id=2451, ABALIATI): GPT-4o-mini, 0 falsi positivi, biografia narrativa con 3 fatti verificati, 19 fonti non verificate elencate, fallback non necessario, costo $0.0005.
- **Evento** ("Operazione Achse 8 settembre 1943"): GPT-4o-mini, biografia 2.365 caratteri, contesto storico corretto.
- Chiavi API confermate disponibili: OPENAI, ANTHROPIC, MISTRAL, PERPLEXITY, EUROPEANA, GEMINI.

---

## 2026-07-11 (sera) — Fix pipeline arricchimento fonti + copertura test

### Catalogazione fonti (`c741bea`)
- Catalogate **25 fonti** da `fonti_scrapabili_metadata.xlsx` in `fonti_indice` tramite `import_fonti_catalogo.py`.
- Ogni fonte include archivio, dominio, access_type, confidence, note legali/tecniche.

### Arricchimento entità (`4481266`, `093e24c`)
- `enrich_entities.py`: pipeline di arricchimento con federated_search concorrente e resume.
- Risultato reale: **20.190 internati processati**, **19.868 nuove schede** in `fonti_indice`, **0 errori**.

### Arricchimento eventi (`d326552`)
- `enrich_events.py`: 6 eventi storici curati con fonti multilaterali (Italia / Asse / Alleati).
- Registrate **28 fonti** multilaterali in `fonti_indice` (Cefalonia, Mauthausen/Gusen, Tobruk, ARMIR Russia, Operazione Achse, lavoro forzato).

### Fix di questa sessione
- `enrich_entities.py`: resume granulare per ID completato; `fetch_internati` usa `WHERE id > ?` anziché OFFSET.
- `source_providers/providers.py`: rimosso `verify=False` da TNA Discovery, Europeana, Deutsche Digitale Bibliothek (Archivportal-D) e Mémoire des Hommes.
- `import_fonti_catalogo.py`: rimossa `_extract_domain()` non utilizzata (codice morto con `NameError` latente).
- `source_locator.py`: `last_checked_at` aggiunto alla whitelist di `register_source_metadata()` e popolato in insert/update.
- `enrich_events.py`: luogo geografico reale per evento, rimosso `time.sleep(0.2)`, rimosso `import json` duplicato.
- Test: `tests/test_enrich_entities.py`, `tests/test_enrich_events.py`, `tests/test_source_providers.py::TestTLSVerification`.

---

## 2026-07-11 (pomeriggio) — Integrazione lettere personali + upload GitHub

### Unificazione DB lettere personali (TODO fix tecnico #1)
- Creata tabella `lettere_personali` in `imi_internati.db` come nuova tabella sorgente.
- Scritto e eseguito `import_lettere_personali.py` per migrare i record da `import_ocr_lettere/ocr_lettere.db`.
- Migrato **1 record**; inserimento nello star schema via `entita`/`collegamenti` (quando `mittente`/`destinatario`/`luogo` sono popolati).
- Integrata `lettere_personali` in `database.py::search_all()` e `get_all_records_for_ai()`.
- Aggiornato frontend `templates/index.html`: card in `renderCrossDBLinks()` e tabella in `renderSourcesTab()`.

### Requirements.txt (TODO fix tecnico #2)
- Aggiornato con `uvicorn[standard]`, `pydantic`, `urllib3`, `schedule` e altri pacchetti mancanti.

### Upload GitHub
- Repository: `https://github.com/helvetiquant/lettere_dal_fronte`
- Inizializzato repo locale, creato `.gitignore` per escludere `.env`, DB SQLite e file grandi.
- Commit e push del codice (DB e secret esclusi).
- Token GitHub salvato in `.env` come `GITHUB_TOKEN`.

### Architettura e dati
- `ARCHITETTURA_DB.md` aggiornato con `lettere_personali`, conteggi `entita`/`collegamenti` aggiornati, CWGC segnato come completato.
- `caduti_cwgc`: stato aggiornato a **completato** (~1.07M record, UK WW2 chiuso a 401k).

---

## 2026-07-11 — Chiusura todo + aggiornamento architettura

### Aggiornamento documentazione architettura (`ARCHITETTURA_DB.md`)
- Statistiche DB aggiornate: ~1.4 GB, 25+ tabelle, ~4.8M record totali.
- Aggiunta tabella `fonti_narrative` al Livello Sorgenti con schema, indici e pipeline di import (`import_personal_sources.py`).
- Aggiornati conteggi `entita` (~688.738 record) e `collegamenti` (~4.832.063 archi), inclusi 69 collegamenti da `fonti_narrative`.
- Aggiornata pipeline Memory Router: `fonti_narrative` e' ora uno step esplicito tra `archivio_fonti` e fallback cloud.

### Frontend
- Colore pulsante **📖 Dossier verificato** cambiato da viola (`var(--accent)`) a grigio scuro (`#374151`) con hover `#1f2937`.

### Todo list
- Tutte le voci aperte chiuse: frontend verificato via API, provider Bundesarchiv implementato, dump XML open data valutato.

---

## 2026-07-10 (sera) — Schema fonti narrative + import fonti Desktop

### Verifica DB
- `PRAGMA quick_check` su `imi_internati.db` → `('ok',)`. Proceduto con creazione schema e import.

### Fix ricerca multi-parola (continuazione)
- `database.py::search_all()` e `get_all_records_for_ai()` ora tokenizzano la query e cercano su `internati`, `menzioni`, `decorati`, tabelle `caduti_*`, `decorati_nastroazzurro`, `documenti_nara_*`.
- Verificato caso reale "Gaiaschi Giuseppe fu Luigi": ora trova record in `caduti_albooro`.

### Nuova tabella `fonti_narrative`
- Creata tabella dedicata a fonti personali/narrative dal Desktop.
- Campi: `sha256`, `nome_file`, `path_locale`, `formato`, `tipo_fonte`, `archivio`, `fondo`, `autore`, `soggetti_json`, `persone_possibili`, `titolo`, `descrizione`, `testo_ocr`, `ocr_status`.
- Indici su `tipo_fonte`, `persone_possibili`, `archivio`, `data_documento`, `ocr_status`.
- Collegamento allo star schema esistente: inserimento nodi in `entita` e archi in `collegamenti` con `tabella_origine='fonti_narrative'`.
- Script: `import_personal_sources.py` (hashing, estrazione testo .odt/.docx, OCR Mistral per PDF/JPG, import, linking).

### Fonti Desktop importate (completato)
- Directory considerate:
  - `Desktop\ARCHIVIO STORIE\STORIE IMI\`
  - `Desktop\ARO\`
  - `Desktop\1945 gaiaschi è libero!\`
  - `Desktop\rebancadatiinternatimilitariitaliani\`
  - `Desktop\racconti, storie, libro\`
- Escluse: `Desktop\DOMANDE RENZI\`, `Desktop\vaticano\`.
- Totale file rilevati: 42 (13 `.odt`, 4 `.docx`, 5 `.pdf`, 15 `.jpg`, 5 `.jpeg`).
- Import effettivo: **40 record** in `fonti_narrative` (2 duplicati saltati via sha256), **69 collegamenti** in `entita/collegamenti`.
- OCR Mistral eseguito su PDF scansionati e fotografie.

### Frontend
- Aggiornati `renderCrossDBLinks()` e `renderSourcesTab()` in `templates/index.html` per mostrare anche i risultati della tabella `fonti_narrative` (card collegamenti e tabella fonti).

### Provider Bundesarchiv
- Confermato che il catalogo Invenio è un'applicazione JSF: endpoint `/invenio/api/records` e varianti restituiscono 404; login/main.xhtml risulta non raggiungibile in modo automatico (timeout/redirect a login).
- Implementato provider realistico in `source_providers/providers.py::ProviderBundesarchiv`:
  - Prova più endpoint JSON noti (`/invenio/api/records`, `/api/records`, `/api/records/`).
  - Fallback strutturato con 3 link: Invenio online (login), Open Data DDB-Bestand (dump XML pubblico), pagina "Recherchesysteme" del Bundesarchiv.
  - Supporto opzionale a `filters['fondo_xml']` per link diretto a un file XML open data.
- Identificato dump open data `https://open-data.bundesarchiv.de/ddb-bestand/` con migliaia di file XML per fondo, potenzialmente scaricabili per ricerca offline.
- Valutazione campione `DE-1958_AR_1-VII.xml`: formato EAD (`urn:isbn:1-931666-22-9`), testo in tedesco, struttura fondo/unita'/scopecontent. Ricerca offline e' fattibile ma richiede download massivo (centinaia di file, potenzialmente diversi GB) e parsing EAD mirato ai soli fondi militari (R, RH, RM, ecc.). Per uso IMI si consiglia di partire dai fondi specifici anziche' dall'intero dump.

### File modificati/ creati
| File | Modifica |
|---|---|
| `schema_proposal_fonti_narrative.sql` | proposta + DDL tabella |
| `database.py` | `search_all()` e `get_all_records_for_ai()` includono `fonti_narrative` |
| `import_personal_sources.py` | nuovo modulo import/OCR/linking |
| `templates/index.html` | render `fonti_narrative` in collegamenti e tab fonti |
| `source_providers/providers.py` | provider Bundesarchiv: tentativi API + fallback catalogo/open data |

---

## 2026-07-10 (sera) - Dossier Verificato (biografie AI) + fix frontend + import lettere + bug ricerca multi-parola

### Dossier Verificato / Biografie AI (`biography.py`, nuovo modulo)
- Nuovo modulo `biography.py`: genera una biografia/dossier narrativo per un soldato o un evento, riusando la pipeline esistente invece di duplicarla:
  - Soldato → `soldier_dashboard.get_soldier_dashboard()`
  - Evento/query libera → `memory_router.route_query(use_cloud_fallback=False)`
- Separazione netta fonti verificate/da verificare: nel prompt entrano solo fatti locali certi, fonti locali leggibili (`archivio_fonti`/menzioni/NARA), fonti esterne gia' scaricate (`fonti_indice.fetch_status='scaricato'` + `source_fetch_cache`), e le lettere in `import_ocr_lettere/ocr_lettere.db`. Le fonti solo candidate (federated_search, `image_only_sources`) vengono elencate a parte con istruzione esplicita all'AI di non usarle nel testo.
- Fallback automatico multi-provider: gpt → claude → mistral → perplexity (stessi provider di `ai_research.PROVIDERS`), un solo tentativo riuscito per biografia invece di 4 chiamate come `research_all()`.
- Logging: `save_ai_ricerca()` con tag `[BIOGRAFIA] ...`, stesso meccanismo gia' usato da `ai_research.py` — nessuna tabella nuova, nessuna alterazione di schema.
- Endpoint: `POST /api/biography` — `{subject_type: "soldier"|"event", soldier_id?, query?, provider?}`.
- Frontend: bottone "📖 Dossier verificato" nella barra di ricerca; card dedicata (`.ai-response.dossier`) mostra provider usato, eventuale fallback e conteggio fonti non utilizzate.

### Fix frontend (`templates/index.html`)
- Bug CSS: le regole `.invest-facts`/`.fact-card`/`.source-badge` del DB View Modal sovrascrivevano silenziosamente quelle condivise (fatti verificati senza bordo verde/warning, badge fonti con dimensione sbagliata). Ora scoped sotto `#dbViewContent`.
- Aggiunte media query responsive, assenti nonostante il meta viewport: header, barra ricerca, analytics bar, modali e form ora si adattano sotto 860px/480px.
- `currentSoldierId` ora valorizzato in `convSearch()` (era dichiarato ma mai assegnato dopo il redesign a 3 tab Risposta AI/Collegamenti/Fonti).

### Import dati (sola copia, nessuna modifica ai DB esistenti)
- Copiato `C:\Users\eryma\CascadeProjects\ocr_lettere` → `imi_extractor\import_ocr_lettere\` (codice + `ocr_lettere.db` + PDF/upload). Integrita' verificata via checksum. DB tenuto separato, NON fuso in `imi_internati.db` su richiesta esplicita — interrogato in sola lettura da `biography.py` per trovare lettere che citano il cognome del soldato.

### Bug trovato (non ancora corretto)
- `database.py::search_all()` (usata da `GET /api/search`) fa `LIKE '%intera query%'` su tutta la stringa multi-parola invece di tokenizzarla: cercare "Luigi Gaiaschi" o "Giuseppe Gaiaschi" ritorna sempre 0 risultati anche quando il dato esiste. Verificato sul backup `Desktop\i backup\imi_extractor_20260707_2100\imi_internati.db`: "Gaiaschi Giuseppe fu Luigi" (caduto 1916, Carso, 1° Rgt Granatieri) e' presente in `caduti_albooro` ma introvabile con la ricerca attuale. "Luigi Gaiaschi" (IMI WW2, documenti primari sul Desktop) non risulta invece in nessuna tabella di quel backup.

### File modificati
| File | Modifica |
|---|---|
| `biography.py` | nuovo modulo |
| `app.py` | +`import biography`, +endpoint `POST /api/biography` |
| `templates/index.html` | fix scoping CSS, +media query responsive, bottone Dossier verificato, +`generateBiography()`, fix `currentSoldierId` |
| `import_ocr_lettere/` | nuova cartella (copia sola lettura di ocr_lettere) |

---

## 2026-07-10 - Research-to-Index API + Frontend Integration + Architettura Update

### Endpoint API Research-to-Index (`app.py`)
- **8 nuovi endpoint API** per Research-to-Index:
  - `POST /api/research/query` — auto-index: cerca locale → se non trova, crea soggetto + arricchisce con fonti esterne federate
  - `POST /api/research/auto-index` — forza creazione soggetto (anche se esiste in DB)
  - `GET /api/research/subjects` — lista soggetti con filtri (type, status, min_confidence, pagination)
  - `GET /api/research/subjects/{id}` — dettaglio soggetto con fonti collegate e gaps
  - `GET /api/research/subjects/{id}/dashboard` — dashboard completa con arricchimento + stats
  - `PATCH /api/research/subjects/{id}` — aggiorna status/confidence/campi (whitelist campi)
  - `GET /api/research/gaps` — lista gaps aperti con suggerimenti provider
  - `GET /api/research/stats` — statistiche Research-to-Index
- Aggiunti import `sqlite3`, `datetime`, `research_to_index as rti` in `app.py`

### Frontend Integration (`templates/index.html`)
- **`convSearch()` aggiornata**: quando search_all non trova risultati locali, chiama `/api/research/query` (auto-index) invece di `/api/source/search` diretto
- **Nuova funzione `renderResearchSubject(rtiRes, query)`**: renderizza soggetti auto-indexed con:
  - Badge stato (Non verificato / Parzialmente verificato / Verificato)
  - Fonti esterne indicizzate con score, provider, access_type
  - Subject ID e tipo soggetto
  - Messaggio esplicativo "soggetto creato automaticamente"

### Documentazione (`ARCHITETTURA_DB.md`)
- Aggiunta sezione **Research-to-Index** in Livello 6 con:
  - 3 tabelle documentate: `research_subjects`, `research_subject_sources`, `research_gaps`
  - Schema colonne, indici, record count
  - Tabella endpoint API (8 endpoint)
  - Diagramma flusso Research-to-Index
- Aggiornate **Relazioni** con research_subjects → fonti_indice, research_gaps
- Aggiornati **Indici principali** con idx_rs_*, idx_rss_*, idx_rg_*

### File modificati
| File | Modifica |
|---|---|
| `app.py` | +8 endpoint API, +import sqlite3/datetime/rti |
| `templates/index.html` | convSearch → auto-index, +renderResearchSubject() |
| `ARCHITETTURA_DB.md` | +sezione Research-to-Index, +relazioni, +indici |

---

## 2026-07-09 (notte) - Research-to-Index + WikiTree Provider + Filtro Rilevanza + Bando MiC

### Research-to-Index (`research_to_index.py`)
- **Modulo completo implementato**: auto-indexing di ricerche non trovate nel DB locale.
  - 3 nuove tabelle: `research_subjects`, `research_subject_sources`, `research_gaps`
  - Funzioni: `create_minimal_subject_from_query`, `upsert_source_locator`, `link_subject_to_source`, `update_subject_confidence`, `identify_research_gaps`, `enrich_subject_from_sources`, `auto_index_if_not_found`, `index_external_sources_for_soldier`, `get_research_stats`
  - Helper `_safe_str` per conversione sicura di valori (liste, None, int) in stringhe SQLite
  - `index_external_sources_for_soldier(soldier_id)`: prende un soldato dal DB, estrae cue, esegue ricerca federata, indicizza fonti trovate in `fonti_indice`, collega a `research_subjects`
- **Filtro rilevanza risultati**: classificazione in 3 categorie:
  - **Relevant** (name_match o score >= 0.25 con record_id): indicizzate con `confirms`/`mentions`, confidence >= 0.3
  - **Catalog ref** (stub provider, score <= 0.15): salvate come `possibly_related`, confidence 0.15
  - **Skipped** (API results non pertinenti, es. TNA ritorna record casuali): non indicizzate
  - Match cognome nel titolo/descrizione rilevato automaticamente
- **Test su 50 soldati casuali** (`test_research_to_index.py`):
  - 437 fonti indicizzate in `fonti_indice` (dedup via segnatura UNIQUE)
  - 50 research_subjects creati (12 verified, 38 partially_verified)
  - 1.174 link subject-source
  - 200 research_gaps identificati (date_start, place, unit, date_end)
  - Provider con API reali: Internet Archive (122 fonti), TNA (15), NARA (1)
  - Provider stub: 6 provider × 50 soldati = 300 riferimenti catalogo

### WikiTree Provider (`source_providers/wikitree.py`)
- **Nuovo provider genealogico** integrato nella federation layer (20° provider)
- API: `https://api.wikitree.com/api.php?action=searchPerson`
- Ricerca per nome, cognome, date, luoghi — gratuita, no auth per profili pubblici
- ~40M+ profili globali, inclusi militari WW1/WW2
- Metodi: `search()`, `get_metadata()`, `get_person_bio()`
- Confidence: 0.60-0.90 basata su match nome + date
- Test: "Rossi Mario" → 5 risultati reali con date/luoghi italiani; "Mussolini Benito" → 2 profili storici

### Modifiche a file esistenti
- **`source_providers/federation.py`**: aggiunto import e registrazione `ProviderWikiTree` (20° provider)
- **`research_to_index.py`**: refactor `index_external_sources_for_soldier` con classificazione rilevanza, catalog_refs, name_match
- **`test_research_to_index.py`**: aggiornato report con relevant/catalog/skipped/name_matches

### File creati
| File | Descrizione |
|---|---|
| `research_to_index.py` | Modulo Research-to-Index: tabelle, funzioni auto-indexing, arricchimento |
| `test_research_to_index.py` | Test su 50 soldati casuali con report dettagliato |
| `source_providers/wikitree.py` | Provider WikiTree (API genealogiche) |
| `test_wikitree.py` | Test rapido provider WikiTree |
| `analyze_rti.py` | Analisi risultati Research-to-Index nel DB |
| `CONCORSI_EUROPEI.md` | Analisi architetturale + strategia funding EU/IT |

### Bando MiC Grande Guerra 2026/2027
- Identificato bando Ministero della Cultura per patrimonio storico Prima Guerra Mondiale
- Scadenza: **15 Luglio 2026 ore 12:00** (6 giorni)
- Budget stimato: ~€400-500k per biennio (bando 2024/2025: €494.647,90 / 17 progetti finanziati su 121)
- Tipologie ammissibili per IMI Extractor: A (censimento), B (catalogazione), E (valorizzazione)
- Soggetti ammissibili: qualsiasi soggetto privato o pubblico, singolarmente o in partenariato
- Documentazione: https://grandeguerra.cultura.gov.it/documentazione/
- Contatti: comitatograndeguerra@cultura.gov.it | mbac-comitatograndeguerra@mailcert.beniculturali.it

---

## 2026-07-09 (sera) - Source Federation Layer + Dashboard Investigativa + UI riprogettata

### Nuovi sistemi implementati

- **`source_providers/` — Source Federation Layer**: sistema di federazione archivistica che integra 19 provider esterni (NARA, Antenati, CWGC, Arolsen, Bundesarchiv, SHD, TNA, Europeana, Gallica, Internet Archive, Google Books, ABMC, LAC, AWM, Archivportal-D, Internet Culturale, HathiTrust, USSME, Archivio di Stato).
  - `base.py`: interfaccia astratta `SourceProvider` con metodi `search`, `get_metadata`, `get_document`, `get_iiif_manifest`, `build_direct_link`, `register_in_db`, `fetch_with_cache`. Helper `score_source` per ranking risultati.
  - `nara.py`: provider NARA (query locale + API catalog.archives.gov).
  - `antenati.py`: provider Antenati (parsing HTML `/search-registry`, estrazione ARK, gestione WAF).
  - `cwgc.py`: provider CWGC (query locale `caduti_cwgc`).
  - `providers.py`: 16 stub provider con fallback a URL catalogo.
  - `federation.py`: registry provider, ricerca federata multi-provider, fetch on-demand con cache, statistiche.

- **`soldier_dashboard.py` — Dashboard Investigativa**: aggregazione dati soldato + fonti federate.
  - `get_soldier_dashboard(id)`: ritorna dati certi, fatti verificati, timeline, fonti locali (archivio_fonti, menzioni, NARA T315), fonti esterne (federation), entità collegate.
  - `get_soldier_sources(id)`: solo fonti (locali + esterne).
  - `analyze_sources(source_ids)`: prepara contesto minimo per AI (metadati + excerpt da cache, no download diretto AI).

- **Interfaccia UI riprogettata** (`templates/index.html`):
  - **Analytics bar** in alto: 8 celle con statistiche globali (internati, caduti, decorati, entità, archi grafo, doc archivio, provider federati, fonti indicizzate).
  - **Ricerca conversazionale** centrale: input semplice → ricerca locale (FTS5 + search_all) → se trovato, carica dashboard soldato completo → se non trovato, ricerca federata diretta.
  - **Risultati investigativi** con 5 tab: Dati Soldato (fatti verificati/non), Timeline, Fonti Locali, Fonti Esterne, Entità.
  - **Source cards**: badge disponibilità (locale/online/da_richiedere/non_accessibile), score, thumbnail, bottoni Apri/IIIF/Scarica/Analizza.
  - **Analisi AI**: selezione fonti → preparazione contesto minimo → invio ad AI.
  - Pannelli operativi esistenti collassati sotto i risultati investigativi.

### Endpoint API aggiunti
- `GET /api/providers` — lista tutti i provider federati
- `GET /api/providers/{name}` — dettaglio provider
- `POST /api/source/search` — ricerca federata multi-provider
- `POST /api/source/fetch` — fetch on-demand documento (solo domini autorizzati)
- `GET /api/source/cache` — lista file in cache
- `GET /api/source/stats` — statistiche federation layer
- `POST /api/source/reindex` — re-index metadati da provider → fonti_indice
- `GET /api/soldiers/{id}/dashboard` — dashboard investigativa completa
- `GET /api/soldiers/{id}/sources` — solo fonti per soldato
- `POST /api/sources/analyze` — prepara contesto minimo per AI

### File creati
| File | Descrizione |
|---|---|
| `source_providers/__init__.py` | Package init |
| `source_providers/base.py` | Interfaccia SourceProvider + helper |
| `source_providers/nara.py` | Provider NARA |
| `source_providers/antenati.py` | Provider Antenati |
| `source_providers/cwgc.py` | Provider CWGC |
| `source_providers/providers.py` | 16 stub provider |
| `source_providers/federation.py` | Registry + orchestrazione federata |
| `soldier_dashboard.py` | Aggregazione dashboard investigativa |

### Principi architetturali
- **Nessun documento pesante scaricato automaticamente**: il DB locale è un indice intelligente, non un repository.
- **Fetch on-demand**: solo quando l'utente richiede, solo da domini autorizzati, con cache e TTL.
- **AI non scarica direttamente**: il backend seleziona fonti, prepara contesto minimo (metadati + excerpt testuali).
- **Score-based ranking**: ogni fonte ha score 0-1 basato su match persona/luogo/data/reparto.

---

## 2026-07-09 - Archivio fonti + NARA Catalog + fix NARA parsing

### Nuovi sistemi implementati
- **`archivio_fonti.py`**: sistema archivio documenti primari (PDF/JPEG/TIFF).
  Pipeline completa: ingestione → classificazione OCR → DB metadati → query semantica → risposta con file originale.
  Tabella `archivio_fonti` con 30+ campi: hash SHA256, metadati archivistici/militari/cronologici, `ocr_status` (done/partial/skip_cursive/skip_quality), `readable`, `attendibilita_fonte`.
  Retrofit NARA T315: 1.153 frame importati con metadati completi.
- **`nara_catalog.py`**: scraper NARA Catalog API (catalog.archives.gov) per After Action Reports USA WW2 relativi all'Italia. 16 query tematiche, ~35k documenti AAR Italy. In esecuzione.
- **Fix NARA T315 parsing**: 93 frame con "Errore parsing JSON" corretti senza API. Tre strategie: rimozione commenti JS inline, chiusura JSON troncati, estrazione regex per campo. 0 errori rimanenti.

### Endpoint API aggiunti
- `GET /api/archivio` — statistiche
- `POST /api/archivio/query` — query semantica (unità, teatro, data, tipo, fondo, testo libero)
- `GET /api/archivio/file/{sha256}` — download file originale (PDF/JPEG)
- `POST /api/archivio/ingest` — upload documento con metadati JSON
- `POST /api/archivio/retrofit_nara_t315` — import NARA T315 → archivio_fonti
- `GET /api/nara_catalog`, `POST /api/nara_catalog/scrape`, `POST /api/nara_catalog/stop`

### Stato database (09/07/2026 ore 18:00)

| Tabella | Record | Note |
|---|---:|---|
| `archivio_fonti` | 1.153 | Nuovo — NARA T315 retrofit, 1.115 readable |
| `documenti_nara_catalog` | in corso | AAR USA WW2 Italy, ~35k target |

## 2026-07-09 - Status e avanzamento CWGC + probe ABMC

### Stato database (09/07/2026 ore 16:00)

| Tabella | Record | Target | % | Stato |
|---|---:|---:|---:|---|
| `caduti_cwgc` | 437.758+ | ~1.763.187 | ~24,8% | 🔄 in corso |
| `caduti_albooro` | 342.555 | ~342.555 | 100% | ✅ completo |
| `caduti_ministero` | 162.646 | ~162.646 | 100% | ✅ completo |
| `caduti_sardi` | 20.435 | ~20.435 | 100% | ✅ completo |
| `caduti_bologna` | 9.656 | ~9.656 | 100% | ✅ completo |
| `caduti_francia_ww1` | 24.279 | ~1.400.000 | 1,7% | ⏸ parziale (download manuale JS) |
| `decorati_nastroazzurro` | 279.832 | 279.832 | 100% | ✅ completo |
| `internati` | 20.464 | 20.464 | 100% | ✅ completo |
| `documenti_nara_t315` | 1.153 | 1.153 | 100% | ✅ completo |
| `decorati` | 1.286 | 1.286 | 100% | ✅ completo |
| `entita` | 327.056 | — | — | 🔄 linker in esecuzione |
| `collegamenti` | 1.325.166 | — | — | 🔄 linker in esecuzione |
| **TOTALE** | **~2.645.000** | | | |

### CWGC — fix e avanzamento
- **WW1**: completato (tutte 24 nazionalità, ~35.400 nuovi record)
- **WW2 in corso**: dopo il reset delle partizioni large (UK/Indian/Canadian/Australian), il CWGC risponde correttamente — Canadian WW2 in scraping (45.388 record, p150/4539)
- **Fix `_paginate_html`**: aggiunto retry 5× con backoff esponenziale (1.2→2.4→4.8→9.6→19.2s) e tolleranza 10 pagine vuote (era 3) per resistere a timeout transitori
- **Fix campo `guerra`**: ora passato esplicitamente da `scrape_all` a `_paginate_html` ("World War 1" / "World War 2")
- **Script `_status_cwgc.py`**: aggiornato con path assoluto e riepilogo di tutte le tabelle

### ABMC — bloccato (WAF)
- `api.abmc.gov` → 403 su tutte le richieste Python (IP restriction / WAF)
- `www.abmc.gov` → reindirizzamento a "Knowvation" CDN WAF, Angular bundle 403
- Richiede **Playwright con fingerprint browser reale** per bypassare la protezione
- Stato: ⛔ **bloccato**, richiede approccio browser headless

### Todo priorità (aggiornato)
| Task | Stato |
|---|---|
| CWGC WW2 Canadian (45k) | 🔄 in corso |
| CWGC WW2 Indian (~87k) | ⏳ in coda |
| CWGC WW2 UK (~572k) | ⏳ in coda (~24h) |
| ABMC USA (~35k) | ⛔ bloccato WAF (serve Playwright) |
| Volksbund Germania (~825k) | ⛔ bloccato (questionario personale) |
| MDH Francia (~1,4M) | ⏸ parziale (download manuale JS/Arkothèque) |

---

## 2026-07-07 (sera) - Riepilogo discorsivo della giornata

### Dati inseriti nei database oggi

La giornata di oggi ha portato all'inserimento complessivo di **oltre 900.000 nuovi record** nel database `imi_internati.db`, portando il totale da ~20.500 record (internati + decorati di partenza) a **più di 920.000 record distribuiti su 8 tabelle**, più **160.191 entità** e **659.050 collegamenti** cross-dataset.

**In dettaglio, per ogni dataset:**

**Albo d'Oro** (`caduti_albooro`): 342.555 record — completato. Si tratta del database dei caduti italiani della Grande Guerra pubblicato su cimeetrincee.it / cadutigrandeguerra.it. Lo scraper ha recuperato l'intero dataset paginando attraverso tutte le lettere dell'alfabeto e gestendo correttamente i casi di omonimia. Ogni record contiene cognome, nome, data e luogo di nascita, data e luogo di morte, grado, corpo/armata,Decorazioni.

**Caduti Ministero Difesa** (`caduti_ministero`): 162.646 record — completato. Fonte: portale "Caduti in Guerra" del Ministero della Difesa, che copre sia la 1a che la 2a Guerra Mondiale. Lo scraper ha gestito il flusso di richieste POST con paginazione interna e parametri di filtro per conflitto.

**Caduti Sardi** (`caduti_sardi`): 20.435 record — completato. Fonte: Unione Sarda / eroiecadutisardi.it. Dataset regionale con caduti sardi in tutti i conflitti.

**Caduti Bolognesi** (`caduti_bologna`): 9.656 record — completato. Fonte: Museo del Risorgimento di Bologna. Dataset locale con caduti della provincia di Bologna.

**CWGC - Commonwealth War Graves Commission** (`caduti_cwgc`): 322.486 record acquisiti su un target di ~1.763.187 (18,3%) — in corso. Lo scraper multi-nazionalità ha completato australiani, indiani, canadesi, neozelandesi, sudafricani, tedeschi, polacchi e olandesi, ed è ora sulla nazionalità più numerosa (United Kingdom, 141.650 record finora). La strategia ibrida (Export CSV per partizioni piccole, paginazione HTML per quelle grandi) ha dimostrato di scalare bene. Nazionalità acquisite: United Kingdom (141.650), Indian (71.474), Canadian (37.420), Australian (35.333), New Zealand (10.716), South African (9.608), German (6.122), Polish (4.402), Dutch (3.844), Italian (621), Greek (328), Belgian (311), Norwegian (304), Czechoslovakian (200), American (79), Russian (51), Arab World (20), Austrian (2), Finnish (1).

**NARA T315 Roll 1299** (`documenti_nara_t315`): 1.111/1.153 frame processati (96,4%) — quasi completato. OCR tramite API Mistral Pixtral-12B delle 1.156 immagini JPG del microfilm T-315 Roll 1299 (Kriegstagebücher della 117. Jäger-Division, 1943). Fix critico applicato: timeout sul client Mistral (senza il quale le chiamate API si bloccavano indefinitamente) e fix della serializzazione JSON per campi di tipo lista. Ultimo frame processato: #1156 alle 22:36.

**Internati Militari Italiani** (`internati`): 20.464 record — era già completo (fonte: Archivio di Stato di Bolzano).

**Decorati al Valor Militare** (`decorati`): 1.286 record — era già completo (fonte: ISTORECO Reggio Emilia).

### Linker cross-dataset

Il linker ha continuato a lavorare per tutta la giornata, portando il numero di **entità estratte** da 42.806 a **160.191** e i **collegamenti** da 75.771 a **659.050**. Il linker collega record delle varie tabelle (internati, caduti_ministero, decorati, menzioni, fondi_archivistici) alle entità estratte (persone, luoghi, unità militari), creando la rete di relazioni che permette di navigare trasversalmente i dataset.

Distribuzione collegamenti per tabella di origine:
- `caduti_ministero`: 355.966 collegamenti
- `internati`: 280.896 collegamenti
- `decorati`: 21.020 collegamenti
- `menzioni`: 776 collegamenti
- `fondi_archivistici`: 392 collegamenti

### Totale record nel database

| Tabella | Record | Stato |
|---|---:|---|
| `caduti_albooro` | 342.555 | ✅ completo |
| `caduti_ministero` | 162.646 | ✅ completo |
| `internati` | 20.464 | ✅ completo |
| `caduti_sardi` | 20.435 | ✅ completo |
| `caduti_cwgc` | 322.486 | 🔄 in corso (target 1.763.187, 18,3%) |
| `caduti_bologna` | 9.656 | ✅ completo |
| `documenti_nara_t315` | 1.111 | 🔄 quasi completo (target 1.153, 96,4%) |
| `decorati` | 1.286 | ✅ completo |
| `entita` | 160.191 | 🔄 linker in corso |
| `collegamenti` | 659.050 | 🔄 linker in corso |
| **Totale** | **~920.000** | |

### Infrastruttura e tool

- **Script di monitoraggio** (`status.ps1`): script PowerShell per visualizzare in tempo reale lo stato di tutti i processi di acquisizione, con percentuali, barre di progresso, PID e uptime dei processi Python attivi. Supporta modalità watch con auto-refresh.
- **File workspace** (`imi_extractor.code-workspace`): configurazione Windsurf/VS Code con task integrate per status, NARA OCR e CWGC scraper.
- **Backup DB**: `imi_internati.db` (298 MB) copiato in `C:\Users\eryma\Desktop\i backup\imi_extractor_20260707_2100\` insieme a tutti i sorgenti (47 file, 597 MB totali).
- **Fix pipeline NARA**: timeout sul client Mistral e serializzazione JSON robusta per campi lista.
- **Fix pipeline CWGC**: parametro `Page` case-sensitive, endpoint Export CSV scoperto e integrato, strategia di partizionamento per nazionalità × guerra × anno × mese, resume via `cwgc_progress.json`, dedup via `cwgc_id UNIQUE`.

---

## 2026-07-07 (sera) - Fix pipeline + CWGC completo multi-nazionalità

### Fix critici
- **`database.py`** — risolto `sqlite3.OperationalError: database is locked` con troppi processi concorrenti: aggiunti `timeout=30`, `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`.
- **`nara_t315_ocr.py`** — risolti due bug che bloccavano l'OCR:
  1. Chiamata Mistral senza timeout → blocco indefinito. Aggiunto `Mistral(timeout_ms=90_000)`.
  2. `Error binding parameter 9: type 'list' is not supported` → serializzazione robusta di `unita_citate`/`luoghi_citati` con controllo `isinstance(..., list)`.
- **Processi bloccati** — terminati processi Python duplicati/stallati; linker riavviato pulito.

### CWGC — riscrittura completa (`caduti_cwgc.py`)
Obiettivo: scaricare **tutti i caduti CWGC di ogni nazionalità** (WW1 + WW2, ~1.76M) senza API pubblica.

**Scoperte tecniche** (via probing del sito):
- Endpoint reale di ricerca: `GET /find-records/find-war-dead/search-results/` (parametro paginazione `Page` maiuscolo).
- **Endpoint Export CSV pubblico**: `GET /ExportCasualtySearch` → fino a **1000 record/richiesta** in CSV strutturato (19 colonne: Id, Surname, Forename, Rank, Regiment, Unit, CountryOfService, ServiceNumber, Cemetery, GraveRef, AdditionalInfo…), **senza login**.
- **`size=100`** aumenta i risultati da 10 a 100 per pagina (10x più veloce).
- Cap: Export = 1000 record/query; paginazione HTML = 1000 pagine (100k record/query).
- Ricerca cognome = fuzzy/soundex (i prefissi a lettera singola sono inutili); filtro data attivo solo con giorno+mese+anno completi.

**Strategia di partizionamento** (nazionalità × guerra × anno × [mese]):
- partizione ≤ 1000 → **Export CSV** (1 richiesta, dati puliti)
- partizione ≤ 100k → **paginazione `size=100`**
- partizione > 100k → **sub-partizione mensile**
- Resume via `cwgc_progress.json`; dedup automatico via `cwgc_id UNIQUE`; `REQUEST_DELAY` 2.5→1.2s.
- **Nuova tabella arricchita**: `caduti_cwgc` (cwgc_id, cognome, nome, rank, service_number, regiment, nationality, data_morte, eta, cimitero, paese_cimitero, guerra).

### Stato database (07/07/2026 ore 23:22)
| Dataset | Tabella | Record | Stato |
|---|---|---:|---|
| Documenti NARA T315 R1299 | `documenti_nara_t315` | 1.111 | 🔄 OCR quasi completo (96,4%) |
| Caduti Albo d'Oro | `caduti_albooro` | 342.555 | ✅ completo |
| Caduti Ministero Difesa | `caduti_ministero` | 162.646 | ✅ completo |
| Caduti Sardi | `caduti_sardi` | 20.435 | ✅ completo |
| Caduti Bolognesi | `caduti_bologna` | 9.656 | ✅ completo |
| Caduti CWGC (tutte naz.) | `caduti_cwgc` | 322.486 | 🔄 in corso (target ~1.76M, 18,3%) |
| Internati Militari Italiani | `internati` | 20.464 | ✅ completo |
| Decorati al Valor Militare | `decorati` | 1.286 | ✅ completo |
| Entità estratte | `entita` | 160.191 | 🔄 linker in esecuzione |
| Collegamenti | `collegamenti` | 659.050 | 🔄 linker in esecuzione |

Collegamenti per tabella: `caduti_ministero` 355.966 · `internati` 280.896 · `decorati` 21.020 · `menzioni` 776 · `fondi_archivistici` 392.

### Script di monitoraggio (`status.ps1`)
- Script PowerShell per status di tutti i processi di acquisizione con percentuali
- Uso: `.\status.ps1` (snapshot) o `.\status.ps1 -Watch` (auto-refresh 10s)
- Mostra: tabella dataset con record/target/%/stato, barre progresso NARA e CWGC, distribuzione CWGC per nazionalità, stato linker, processi Python attivi
- Rilevamento processi attivi via log file timestamps

---

## 2026-07-07 - Sessione di lavoro

### Nuovi moduli implementati

#### 1. OCR NARA T315 Roll 1299 (`nara_t315_ocr.py`)
- **Fonte**: National Archives USA, Microcopy T-315, Roll 1299
- **Contenuto**: 1.156 immagini JPG — Kriegstagebücher della 717. Infanterie-Division / 117. Jäger-Division (1943)
- **Motore OCR**: Mistral `pixtral-12b-2409` via `MISTRAL_API_KEY`
- **Nuova tabella**: `documenti_nara_t315` (frame, tipo\_documento, data, mittente, destinatario, unità, luoghi, perdite, testo\_ocr, lingua, confidenza)
- **Endpoint API**: `GET /api/nara`, `POST /api/nara/scrape`, `POST /api/nara/stop`
- **Stato**: in corso (~52/1.153 frame processati al 07/07/2026 17:18)
- **Fix applicati**: JSON strict=False per caratteri di controllo; normalizzazione lista per frame multi-scheda; parsing backtick corretto

#### 2. Analisi storica 117. Jäger-Division (`analisi_117div_marzo1943.md`)
- Traduzione italiana completa dei documenti OCR (da tedesco)
- Analisi cronologica operativa: **marzo 1943**, Sarajevo–Visegrad–Grecia
- Documenti chiave tradotti: ordini di schieramento, rapporti situazione, ordine trasferimento Grecia
- **Riferimenti a forze italiane**: presidi a Gorazde/Kalinovik, collaborazione intelligence, anticipo Operazione Achse (set.1943)
- **Nota IMI**: dopo l'armistizio italiano (8 set. 1943) la 117. Jäger-Division disarmò truppe italiane in Grecia → potenziale collegamento con internati

#### 3. Estensione `linker.py` per nuovi dataset
- Aggiunti blocchi di estrazione per: `caduti_ministero` (162k), `caduti_sardi` (20k), `caduti_bologna` (9.6k), `caduti_albooro` (296k)
- Resume intelligente via `MAX(record_id)` per ogni tabella
- In esecuzione al 07/07/2026 17:18 su 516.305 record totali

### Stato database (07/07/2026 ore 17:18)
| Dataset | Tabella | Record | Stato |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | ✅ completo |
| Decorati al Valor Militare | `decorati` | 1.286 | ✅ completo |
| Caduti Albo d'Oro | `caduti_albooro` | 299.510+ | 🔄 in corso (~56%) |
| Caduti Bolognesi | `caduti_bologna` | 9.656 | ✅ completo |
| Caduti Ministero Difesa | `caduti_ministero` | 162.646 | ✅ completo |
| Caduti Sardi | `caduti_sardi` | 20.435 | ✅ completo |
| Documenti NARA T315 R1299 | `documenti_nara_t315` | 52+ | 🔄 OCR in corso (4.5%) |
| Entità estratte | `entita` | 42.806 | 🔄 linker in esecuzione |
| Collegamenti | `collegamenti` | 82.391 | 🔄 linker in esecuzione |

---

## 2026-07-06 - Sessione di lavoro

### Nuovi moduli implementati

#### 1. Sistema Entità e Collegamenti Cross-Dataset (`linker.py`)
- **Tabella `entita`**: entità estratte da tutti i dataset (persone, luoghi, eventi)
- **Tabella `collegamenti`**: link tra entità e record in `internati`, `decorati`, `menzioni`, `fondi_archivistici`
- Estrazione automatica con stop/resume e tracking del progresso
- **Risultato**: 42.806 entità, 75.771 collegamenti estratti da 21.854 record
- Endpoint API: `/api/entita`, `/api/entita/build`, `/api/entita/stop`, `/api/entita/search`, `/api/entita/{id}`

#### 2. Ricerca AI Assisted (`ai_research.py`)
- Integrazione con 3 provider AI: **OpenAI GPT-4o-mini**, **Mistral Large**, **Perplexity Sonar**
- Ogni provider interroga il DB locale per recuperare contesto (internati, decorati, menzioni, fondi)
- Estrazione termini significativi da query in linguaggio naturale (anni, nomi, luoghi)
- Prompt strutturato per ruolo di ricercatore storico con output in sezioni (SINTESI, PERSONE, LUOGHI, EVENTI, FONTI, COLLEGAMENTI, APPROFONDIMENTI)
- **Tabella `ai_ricerche`**: log di tutte le ricerche AI con provider, modello, costo, risposta
- Cost tracking integrato con `credits.py` esistente
- Endpoint API: `/api/ai-research` (POST con provider selezionabile o "all"), `/api/ai-research/history`
- **Test completati**:
  - "trova soldati decorati deceduti nel 1943" → 18 decorati trovati e analizzati (costo $0.0018)
  - "soldati presenti in più fonti" → cross-referencing tra internati/decorati/menzioni, identificati cognomi comuni (Rossi, Ferrari, Barbieri, Ferretti, Montanari, Bertolini, Rinaldi) (costo $0.0039)

#### 3. Caduti Albo d'Oro - Cimeetrincee (`caduti_albooro.py`)
- Scraping da `cadutigrandeguerra.it` (Associazione Storica Cimeetrincee)
- 35 volumi dell'Albo d'Oro dei caduti italiani della Grande Guerra (~530k nomi)
- Reverse-engineering di ASP.NET WebForms (VIEWSTATE, EVENTVALIDATION)
- **Tabella `caduti_albooro`**: nominativo, paternità, classe, comune, grado, reparto, anno/luogo/causa morte, link dettaglio
- Stop/resume con skip dei volumi già scaricati
- **Risultato in corso**: 21.041 caduti salvati da 22 volumi (su 35 totali)
- Endpoint API: `/api/albooro`, `/api/albooro/scrape`, `/api/albooro/stop`

#### 4. Frontend aggiornato (`templates/index.html`)
- Pannello "Entità e Collegamenti Cross-Dataset" con stats, bottoni estrazione/stop, ricerca entità
- Pannello "Ricerca AI Assisted" con selettore provider (GPT/Mistral/Perplexity/Tutti), input query, loading indicator, risultati formattati, storico ricerche cliccabile
- Pannello "Caduti Albo d'Oro" con stats volumi, bottoni scraping/stop, info progresso
- Polling automatico per aggiornamento stato durante operazioni background

### Modifiche a file esistenti

- **`database.py`**: Aggiunte tabelle `entita`, `collegamenti`, `ai_ricerche` con indici; funzioni CRUD per entità/collegamenti/ricerche AI; funzione `search_all` estesa con supporto multi-term
- **`app.py`**: Aggiunti import e threading locks per `linker`, `ai_research`, `caduti_albooro`; 12 nuovi endpoint API
- **`templates/index.html`**: 3 nuovi pannelli UI + ~150 righe di JavaScript per entità, AI research, Albo d'Oro

### Dati attualmente nel database

| Dataset | Tabella | Record | Fonte |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | Archivio di Stato di Bolzano |
| Decorati al Valor Militare | `decorati` | 1.286 | ISTORECO Albi della Memoria (RE) |
| Menzioni da fondi archivistici | `menzioni` | ~2.000+ | Ufficio Storico SME |
| Caduti Albo d'Oro | `caduti_albooro` | 21.041 (in corso) | Cimeetrincee / cadutigrandeguerra.it |
| Entità estratte | `entita` | 42.806 | Estrazione automatica cross-dataset |
| Collegamenti | `collegamenti` | 75.771 | Link entità ↔ record |
| Ricerche AI | `ai_ricerche` | 3 | Log ricerche AI-assisted |

### TODO - Siti di interesse tematico (aggiornato 07/07 ore 23:22)

| # | Fonte | Record | Priorità | Stato |
|---|---|---:|---|---|
| s1 | Cimeetrincee (Albo d'Oro) | 342.555 | alta | ✅ **completo** |
| s2 | Ministero Difesa (Caduti 1a/2a GM) | 162.646 | alta | ✅ **completo** |
| s3 | Caduti Bolognesi (Museo Risorgimento BO) | 9.656 | alta | ✅ **completo** |
| s4 | Eroi e Caduti Sardi (Unione Sarda) | 20.435 | alta | ✅ **completo** |
| s14 | UK/Commonwealth - CWGC (tutte naz.) | 322.486 / ~1.76M | media | 🔄 **in corso** (18,3%) |
| s5 | Istituto Nastro Azzurro (decorati VM) | n.d. | media | pending |
| s6 | Eco Museo Grande Guerra Prealpi Vicentine | museale | bassa | pending |
| s7 | Riassunti storici brigate fanteria | testuale | bassa | pending |
| s8 | 14-18 Documenti e immagini GG | documentale | bassa | pending |
| s9 | Centro Ricerche Grande Guerra | documentale | bassa | pending |
| s10 | Sacrario Redipuglia | n.d. | bassa | pending |
| s11 | The World Remembers (28 nazioni) | ~5M | media | pending |
| s12 | Francia - Mémoire des Hommes | ~1.4M | media | pending |
| s13 | Germania - Volksbund | ~825k | media | pending |
| s15 | USA - ABMC/NARA | ~116k | media | pending |

**Completati oggi**: s1 (Albo d'Oro), s2 (Ministero), s3 (Bologna), s4 (Sardi). **In corso**: s14 (CWGC multi-nazionalità, 18,3%).
**Altri task in corso**: OCR NARA T315 R1299 (1.111/1.153, 96,4% — quasi completo); linker cross-dataset (659.050 collegamenti, 160.191 entità).
**Backup DB**: `imi_internati.db` → `imi_internati_backup_20260707.db` (298 MB) + backup completo in `C:\Users\eryma\Desktop\i backup\`.

### Fonte già importata (esclusa)
- **Albi della Memoria ISTORECO Reggio Emilia** → tabella `decorati` (1.286 record)

---

## 2026-07-06 - IR Layer: FTS5 + Graph CTE (20:00)

### Stato popolamento database (snapshot 19:49)

| Dataset | Tabella | Record attuali | Target | % completamento | Stato |
|---|---|---:|---:|---:|---|
| Internati Militari Italiani | `internati` | 20.464 | 20.464 | 100% | **completo** |
| Decorati al Valor Militare | `decorati` | 1.286 | 1.286 | 100% | **completo** |
| Caduti Albo d'Oro | `caduti_albooro` | 296.568 | ~530.000 | 56% | idle (lettera A-Z in corso) |
| Caduti Bolognesi | `caduti_bologna` | 9.656 | ~10.732 | 90% | idle |
| Caduti Ministero Difesa | `caduti_ministero` | 7.334 | ~508.670 | 1.4% | **in corso** (lettera B) |
| Caduti Sardi | `caduti_sardi` | 4.910 | ~20.531 | 24% | **in corso** (lettera D) |
| Caduti CWGC | `caduti_cwgc` | 0 | ~1.700.000 | 0% | richiede Selenium |
| Menzioni fondi archivistici | `menzioni` | 98 | ~200 | 49% | completo per fonti disponibili |
| Fondi archivistici | `fondi_archivistici` | 6 | 6 | 100% | **completo** |
| Entita' estratte | `entita` | 42.806 | - | - | da estendere ai nuovi dataset |
| Collegamenti | `collegamenti` | 75.771 | - | - | da estendere ai nuovi dataset |
| Ricerche AI | `ai_ricerche` | 3 | - | - | log storico |
| **TOTALE** | | **383.196** | **~2.791.000** | **13.7%** | |

### Information Retrieval Layer implementato

#### 1. `db_init_fts.py` - Migration FTS5
- Crea virtual table `idx_entita_search` con FTS5 (tokenizer `unicode61 remove_diacritics 2`)
- Campi indicizzati: `valore`, `cognome`, `nome`, `luogo`, `contesto`
- Campi UNINDEXED: `entita_id`, `tipo` (per filtro)
- Trigger `AFTER INSERT/UPDATE/DELETE` su `entita` per sincronizzazione automatica
- Popolamento iniziale da 42.806 record esistenti (0.7s)
- Idempotente: sicuro da rieseguire

#### 2. `search_service.py` - Service Layer
- **`search_entities(query, limit, tipo)`**: FTS5 + BM25 ranking con prefix matching automatico (`*`), filtro per tipo entita' (persona/luogo/evento/decorazione/periodo)
- **`get_entity_network(entity_id, max_depth)`**: graph traversal
  - depth=2: JOIN dirette su `collegamenti` (ottimizzato per star schema)
  - depth>2: recursive CTE con temp table per evitare limite SQL variables
  - Output: `{nodes, edges, center, node_count, edge_count}` per visualizzazione grafo
- **`get_entity_full_context(entity_id)`**: deep-dive relazionale
  - Risolve dinamicamente il record sorgente da 9 tabelle (`internati`, `decorati`, `menzioni`, `fondi_archivistici`, `caduti_albooro`, `caduti_bologna`, `caduti_ministero`, `caduti_sardi`, `caduti_cwgc`)
  - Mappa `SOURCE_TABLE_FIELDS` per ogni tabella sorgente
  - Fallback graceful per tabelle non accessibili o record mancanti
- **`get_fts_stats()`**: statistiche indice (count, sync status, distribuzione tipi/fonti)

#### 3. `test_search.py` - Test Suite (31 test, 100% pass)
- **TestFTS5Sync** (3 test): trigger INSERT/UPDATE/DELETE su entita' temporanee
- **TestBM25Search** (9 test): ricerca persona, luogo, evento, prefix, multi-word, empty, nonexistent, ranking order
- **TestGraphTraversal** (7 test): depth=2, struttura nodi/edge, no self-loop, recursive depth=3, entity inesistente, centro nei nodi
- **TestEntityFullContext** (5 test): entity esistente, source record risolto, collegamenti, nonexistent, tutte le tabelle sorgente
- **TestNormalizeQuery** (4 test): empty, prefix, wildcard, multi-word
- **TestFTSStats** (3 test): struttura, sync, tipi

### File creati
- `db_init_fts.py` - migration script FTS5 + trigger
- `search_service.py` - IR service layer (3 funzioni core + stats)
- `test_search.py` - test suite 31 test

### Performance
- Popolamento FTS5: 42.806 record in 0.7s
- Query BM25: <1ms
- Graph traversal depth=2: <10ms su 75.771 collegamenti
- Graph traversal depth=3: ~2s (recursive CTE)

---

## 2026-07-06 - Sessione serale (18:00-20:00)

### Fix scraper esistenti

#### Fix Caduti Bolognesi: paginazione e parsing
- **Problema**: scraper si fermava a 482 record (paginazione errata: usava record offset invece di page number)
- **Fix**: `PAGE_SIZE=10` (cap del sito), `start` come page number, parsing tabella `id="DG"`
- **Risultato**: 4.323+ record (in corso, target 10.732)

#### Fix Ministero Difesa: da form HTML a API JSON
- **Problema**: scraper vecchio tentava di fare submit di un form HTML, ma il sito usa JavaScript con reCAPTCHA
- **Reverse engineering**: analizzato file JS `/assets/js/onorcaduti/cadutiprimaguerra.js`, scoperto endpoint API `https://sicadapi.difesa.it/sicad/v1/getprimaguerracadutopaginated`
- **API**: POST JSON con `{campoSingolo, selectedPage, pageSize}`, nessun token/reCAPTCHA richiesto, SSL self-signed (verify=False)
- **508.670 record totali** disponibili via API
- **Schema DB aggiornato**: `source_id` (UNIQUE), `nominativo_paternita`, `paternita`, `maternita`, `data_nascita`, `data_decesso`, `provincia_nascita`, `comune_nascita`, `nazione_decesso`, `luogo_sepoltura`, `codice_volume`, `pagina`, `sub`, `scheda_url` (link a scansione Albo Oro)
- **Parsing cognome/nome**: split su primo spazio del campo `nominativoePaternita` (es. "ABACOT GIUSEPPE DI MICHELE" → cognome=ABACOT, nome=GIUSEPPE DI MICHELE)
- **Risultato**: 975+ record (in corso, lettera A, target 508.670)

#### Fix Caduti Sardi: da probing generico a parsing strutturato
- **Problema**: scraper vecchio cercava tabelle HTML o split per virgola, ma il sito usa `div.itemDefunto` con struttura specifica
- **Endpoint corretto**: `/Search?query=LETTER&war=1&page=N` (20.531 risultati totali)
- **Struttura HTML**: ogni record è `div.itemDefunto` contenente:
  - `a.city` → comune di residenza
  - `a.name` → cognome + nome concatenati (es. "Abau Anacleto"), href contiene ID (es. `/Cagliari/ABAU ANACLETO-1`)
  - `div.war` → guerra (Prima/Seconda Guerra Mondiale)
  - `div.date` → date e luogo (es. "15 Maggio 1893 - 03 Giugno 1916 sul monte Cengio")
- **Parsing cognome/nome**: split su primo spazio (es. "Abau Anacleto" → cognome=Abau, nome=Anacleto) - confermato da verifica multipla
- **Parsing date**: regex per date in formato italiano "DD Mese YYYY", estrazione luogo morte dopo ultima data
- **Schema DB aggiornato**: `source_id` (UNIQUE), `guerra`, `comune_residenza`, indici su cognome e comune
- **Risultato**: 180+ record (in corso, lettera A, target 20.531)

### Nuovi file
- `ARCHITETTURA_DB.md` - documento architettura database a 3 livelli + prompt per generazione immagine + diagramma Mermaid

### File modificati
- `caduti_ministero.py` - rewrite completo: API JSON invece di form HTML, nuovo schema DB, parsing nominativoePaternita
- `caduti_sardi.py` - rewrite completo: endpoint /Search con paginazione, parsing div.itemDefunto, separazione cognome/nome, parsing date italiano
- `caduti_bologna.py` - fix paginazione (PAGE_SIZE=10, page number invece di offset)

### Stato database (in corso)
| Dataset | Tabella | Record | Fonte |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | Archivio di Stato di Bolzano |
| Decorati al Valor Militare | `decorati` | 1.286 | ISTORECO Albi della Memoria (RE) |
| Caduti Albo d'Oro | `caduti_albooro` | 238.231+ (in corso) | Cimeetrincee / cadutigrandeguerra.it |
| Caduti Bolognesi | `caduti_bologna` | 4.323+ (in corso) | Museo Risorgimento BO |
| Caduti Ministero Difesa | `caduti_ministero` | 975+ (in corso) | sicadapi.difesa.it (API JSON) |
| Caduti Sardi | `caduti_sardi` | 180+ (in corso) | eroiecadutisardi.unionesarda.it |
| Caduti CWGC | `caduti_cwgc` | 0 (richiede Selenium) | cwgc.org |
| Entità estratte | `entita` | 42.806 | Estrazione automatica cross-dataset |
| Collegamenti | `collegamenti` | 75.771 | Link entità ↔ record |

---

## 2026-07-06 - Sessione pomeridiana (16:00-18:00)

### Fix e miglioramenti

#### Fix Albo d'Oro: paginazione per lettera alfabetica
- **Problema**: ogni volume restituiva max 1000 record (cap di GridView ASP.NET)
- **Soluzione**: paginazione per lettera A-Z all'interno di ogni volume (35 volumi × 26 lettere = 910 richieste)
- Resume per singola lettera già scaricata (skip se `nominativo LIKE 'X%'` esiste)
- **Risultato**: da 31.222 a 58.137+ record (in corso, ~530k attesi)

#### Nuovo modulo: Caduti Bolognesi (`caduti_bologna.py`)
- Fonte: `badigit.comune.bologna.it/csg/ricerca.aspx` (Museo Civico del Risorgimento BO)
- 10.732 record caduti provincia di Bologna 1915-1918
- Paginazione via query string (`num=50&start=X`)
- Parsing regex estrae: nome, paternità, grado, reparto, luogo nascita, anno, dimora, causa/luogo/data morte, professione, stato civile, decorazioni
- **Tabella `caduti_bologna`** con UNIQUE constraint su nome+paternità+data_morte
- **Risultato**: 482+ record (in corso, 10.732 attesi)
- Endpoint API: `/api/bologna`, `/api/bologna/scrape`, `/api/bologna/stop`

#### Nuovo modulo: CWGC Commonwealth (`caduti_cwgc.py`)
- Fonte: `cwgc.org` - 1.7M caduti Commonwealth WW1/WW2
- Approccio: download CSV per paese (87 paesi)
- **Problema**: il sito CWGC è stato ridisegnato, l'URL `/find/find-war-dead/results` ritorna 404. Richiede Selenium/Playwright per JavaScript rendering
- **Tabella `caduti_cwgc`** creata e pronta, ma scraping non attivo
- Endpoint API: `/api/cwgc`, `/api/cwgc/scrape`, `/api/cwgc/stop`

### File creati
- `caduti_bologna.py` - scraper Caduti Bolognesi
- `caduti_cwgc.py` - scraper CWGC (richiede Selenium per JS)

### File modificati
- `caduti_albooro.py` - fix paginazione per lettera alfabetica
- `app.py` - aggiunti import, lock e endpoint per Bologna e CWGC

### Stato database (in corso)
| Dataset | Tabella | Record | Fonte |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | Archivio di Stato di Bolzano |
| Decorati al Valor Militare | `decorati` | 1.286 | ISTORECO Albi della Memoria (RE) |
| Caduti Albo d'Oro | `caduti_albooro` | 58.137+ (in corso) | Cimeetrincee / cadutigrandeguerra.it |
| Caduti Bolognesi | `caduti_bologna` | 482+ (in corso) | Museo Risorgimento BO |
| Caduti CWGC | `caduti_cwgc` | 0 (richiede Selenium) | cwgc.org |
| Entità estratte | `entita` | 42.806 | Estrazione automatica cross-dataset |
| Collegamenti | `collegamenti` | 75.771 | Link entità ↔ record |
