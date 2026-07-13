# TODO — VOCI DAL FRONTE / IMI Extractor

Aggiornato: 13 luglio 2026 — Pipeline multi-AI parallela, report engine, banner frontend, fix BackgroundTasks, watchdog pipeline.

---

## 0. URGENTISSIMO — Bando MiC Grande Guerra (scad. 15/7 ore 12:00 — 4 giorni)

Il pacchetto di candidatura è **già scritto** in `bando_mic_2026/` (progetto "VOCI DAL FRONTE", budget €37.000, 12 mesi Ott 2026–Set 2027, tipologie A+B+E). Buona notizia rispetto alla valutazione precedente: **non serve un ente ex L.78/2001** — la dichiarazione sostitutiva è già impostata anche per persona fisica. Quello che manca è solo la parte burocratica di invio, non la scrittura:

- [ ] Registrarsi su grandeguerra.cultura.gov.it/presenta-la-tua-domanda/ e ottenere il codice d'accesso
- [ ] Scaricare bando ufficiale + vademecum + Allegato A (PDF) + Allegato B (Excel)
- [ ] Trascrivere `DESCRIZIONE_PROGETTO.md` nel form online
- [ ] Compilare, firmare, scansionare l'Allegato A usando `DICHIARAZIONE_SOSTITUTIVA.md` come guida
- [ ] Compilare l'Allegato B Excel usando `CRONOPROGRAMMA.md`
- [ ] Preparare screenshot/foto della piattaforma come allegati fotografici
- [ ] Allegare copia documento d'identità
- [ ] Inviare entro il 15/7 ore 12:00

Questo è puro lavoro amministrativo/di trascrizione: non richiede altro intervento tecnico sul codice.

---

## 1. FIX TECNICI — stato reale (molti già risolti)

| # | Problema | Stato reale nel repo | Azione residua |
|---|---|---|---|
| 1 | Due database scollegati (`ocr_lettere.db` vs `imi_internati.db`) | ✅ **Risolto in codice**: `app.py` è il sistema completo, `database.py` punta a `imi_internati.db`. Esistono **due script di migrazione** che portano le lettere/fonti personali nello star schema: `import_lettere_personali.py` (da `ocr_lettere.db` → tabella `lettere_personali`) e `import_personal_sources.py` (da cartelle Desktop → tabella `fonti_narrative`, più ampia: include anche biografie, foto, memoriali). | ⚠️ Le due tabelle si sovrappongono concettualmente (entrambe collegano persone a `entita`/`collegamenti`). Decidere se unificarle o tenerle distinte per tipo di fonte. **Verificare se le migrazioni sono state effettivamente eseguite** sul DB live (non verificabile da qui, il file `.db` non è nel repo per dimensione/gitignore). |
| 2 | `requirements.txt` incompleto | ✅ **Risolto**: ora include `beautifulsoup4`, `mistralai`, `pymupdf`, `pdfplumber`, `schedule`, `httpx`, `pydantic`, ecc. — coerente con gli import reali. | Nessuna azione. |
| 3 | Bug ricerca multi-parola (`search_all()` restituiva 0 risultati per query come "Rossi Mario") | ✅ **Risolto e affinato (12/7)**: `_where_like_clause()` ora usa **AND tra token, OR tra colonne**. Prima: "Gaiaschi Giuseppe" → 14 internati falsi positivi (0 contenevano "gaiaschi"). Dopo: 0 falsi positivi, solo risultati pertinenti. 130 test passati. | ✅ Risolto. |
| 4 | Script scratch mescolati ai moduli di produzione | Ancora presente: 61 file su 104 (59%) con prefisso `_test_/_check_/_run_/_status_/_fix_`. | 🟢 Bassa priorità — cleanup rimandabile. |
| 5 | Nessun test automatizzato | Aggiunto `tests/test_smoke.py` con 6 smoke test unittest su `search_all()`, `get_all_records_for_ai()`, `search_service.search_entities()`, `memory_router.route_query()` e import `app`. **Tutti passati**. | ✅ Risolto. Gli script `test_50_queries.py`/`test_research_to_index.py`/`test_wikitree.py` rimangono utili come reference ma non sono la test suite principale. |

---

## 2. DATI — stato reale e azioni

| # | Elemento | Stato | Azione |
|---|---|---|---|
| 1 | **Integrità `imi_internati.db` (1,4 GB)** | ✅ **Verificato (12/7)**: `PRAGMA quick_check` e `integrity_check` → **ok**. Il "malformed" era artefatto di mount. | ✅ Risolto. |
| 2 | **Import lettere personali → star schema** | ✅ **Verificato su DB live (12/7)**: `fonti_narrative` = 40 record, 69 collegamenti; `lettere_personali` = 1 record. 11 record `fonti_narrative` contengono "Gaiaschi" (foto, memoriali, documenti ARO). | ✅ Risolto. |
| 3 | **Caso di test "Luigi Gaiaschi"** | ✅ **Presente in `fonti_narrative` (12/7)**: 11 record con "Gaiaschi" (foto 1945, memoriali, ARO, archivio federale). `search_all("Gaiaschi")` trova 11 fonti_narrative + 4 caduti. Non presente in `internati` (IMI WW2 non nel DB principale — caso reale per Research-to-Index). | Usare come screenshot per bando MiC. |
| 4 | **Dossier verificato (biography.py)** | ✅ **Testato end-to-end (12/7)**: soldato (id=2451) → GPT-4o-mini, biografia narrativa con 3 fatti verificati, 19 fonti non verificate elencate, costo $0.0005. Evento ("Operazione Achse") → biografia 2.365 char. Fallback non necessario. Chiavi: OPENAI, ANTHROPIC, MISTRAL, PERPLEXITY tutte disponibili. | ✅ Risolto. |
| 5 | **Linker cross-dataset** | ✅ **Completato (12/7)**: 688.738 entità (560.133 persone, 102.319 luoghi, 14.952 eventi, 10.348 unità), 4.832.063 collegamenti. Distribuzione: caduti_ministero 1.5M, caduti_albooro 1.36M, caduti_cwgc 1.07M, internati 574k, caduti_sardi 127k, fondi_archivistici 68k, menzioni 55k, decorati 42k, caduti_bologna 33k, fonti_narrative 69. | ✅ Risolto. |
| 6 | **CWGC** | ✅ **Confermato (12/7)**: 506.446 record totali (WW2: 452.395, WW1: 35.400, non classificati: 18.651). | ✅ Risolto. |
| 7 | **Provider federation** | ✅ **Parzialmente risolto**: TNA, Europeana, DDB, Mémoire des Hommes, Internet Archive, Google Books, Gallica/BNF e HathiTrust hanno query reali. Stati Uniti: Arolsen, Bundesarchiv, LAC, AWM, ABMC rimangono stub o accesso a catalogo. Italia/USSME cerca in `fondi_archivistici` locali. | 🟡 **Non più bloccante per il bando MiC**. Rifinire quando si arricchiranno fonti Asse/Alleati specifiche per singoli soldati/eventi (ottobre 2026). |

---

## 3. Non prioritario oggi

- Consolidare `import_lettere_personali.py` + `import_personal_sources.py` in un unico modulo (oggi coesistono due percorsi paralleli per contenuti concettualmente simili).
- Conformità Europeana Data Model (EDM), OpenAPI/Swagger, mappa geospaziale, responsive mobile, multilingua — coerenti con le scadenze Creative Europe (set 2026) e Horizon Europe (23 set 2026), non con quella di oggi.

---

## Nota metodologica

Le verifiche del 12/7 sono state eseguite direttamente sulla macchina locale con DB live e chiavi API reali. Tutte le voci sopra sono ora confermate.

## Task completati il 12/7

- [x] Verifica integrità DB → ok
- [x] Verifica migrazioni lettere_personali (1 record) e fonti_narrative (40 record, 69 collegamenti)
- [x] Verifica linker completato (688.738 entità, 4.832.063 collegamenti)
- [x] Fix ricerca multi-parola: AND tra token invece di OR puro (0 falsi positivi)
- [x] Tab Gaps in UI: `renderGapsTab()` con badge priorità, label localizzate, provider suggeriti
- [x] Test biography end-to-end: soldato + evento, GPT-4o-mini, fallback non necessario
- [x] CWGC confermato: 506.446 record

## Task completati il 12/7 (pomeriggio)

- [x] Consolidato `import_fonti_personali.py` (unificato lettere + fonti narrative)
- [x] Provider Arolsen reale: ITS-WS.asmx reverse-engineered (BuildQuery → GetCount → GetPersonList/GetArchiveList)
- [x] Provider Bundesarchiv reale: Invenio REST API (/api/records)
- [x] Provider SHD/Mémoire des Hommes reale: parsing HTML strutturato
- [x] Provider Archivportal-D reale: DDB REST API con OAuth API key
- [x] Provider LAC reale: Canadiana API + Collection Search fallback
- [x] Provider Internet Culturale reale: OPAC SBN JSON + fallback HTML
- [x] README riscritto: architettura, diagramma flusso, 16 provider, schema DB, API
- [x] Cleanup 59 script scratch (107 → 48 file .py, −55%)

## Task completati il 13/7

- [x] Fix `BackgroundTasks` non importato → server non partiva
- [x] Banner full-width responsive (2480×480px ratio 5:1) sopra navbar sticky
- [x] Nuovo banner italiano "Voci dal Fronte" con soldato+lettera+aereo (sostituisce precedente)
- [x] `mass_index.py`: pipeline batch 4 dimensioni (soldati/reparti/eventi/luoghi) con ThreadPoolExecutor
- [x] `report_engine.py`: report narrativo AI (OpenAI→Anthropic→Mistral fallback chain) con grafo entità
- [x] Endpoint `GET /api/report?q=...&tipo=...` — report storico on-demand
- [x] Endpoint `POST /api/mass-index/start` — pipeline singola in background
- [x] Endpoint `POST /api/mass-index/start-parallel` — 7 AI in parallelo
- [x] Endpoint `GET /api/mass-index/status` — stato pipeline + stats fonti_indice
- [x] `mass_index_parallel.py`: OpenAI(A-F) + Anthropic(G-L) + Gemini(M-R) + Mistral(S-Z) + Perplexity(eventi) + LMStudio(reparti) + Scraper(luoghi)
- [x] LM Studio opzionale: detection automatica disponibilità, fallback silenzioso
- [x] Fix colonne DB: `soggetto_tabella`→`tabella_origine`, `soggetto_id`→`record_id`
- [x] `pipeline_watchdog.py`: monitor ogni 5 min, fix e riavvio automatico
- [x] Push GitHub: helvetiquant/lettere_dal_fronte aggiornato

## Task residui

- [ ] **Bando MiC (scad. 15/7 ore 12:00)** — URGENTE — solo amministrativo
- [ ] DDB API key: registrarsi su deutsche-digitale-bibliothek.de per ottenere key
- [ ] TNA: query per cognome causa HTTP 500 — usare query generiche o reference series
- [ ] Popolamento massivo completo: 20.464 soldati × tutti i provider (stimato 8-12h con 4 AI)
- [ ] Frontend: aggiungere tab Report nella UI (query libera → report narrativo)
- [ ] Frontend: mappa geospaziale movimentazioni (Leaflet + dati luogo_internamento)
- [ ] Conformità Europeana Data Model (EDM) — scadenza Creative Europe set 2026
- [ ] Gemini: verificare che google-generativeai sia installato (`pip install google-generativeai`)
