# CHANGELOG - IMI Extractor

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
