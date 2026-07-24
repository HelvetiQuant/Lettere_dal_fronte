# TODO — VOCI DAL FRONTE / IMI Extractor

Aggiornato: 24 luglio 2026 — AI Provider Consolidation + LeBI Fase 4 + Docs.

---

## Giornata 2026-07-24 — AI Consolidation + LeBI Fase 4 + Docs

### Completato
- [x] **AI Provider Consolidation**: OpenAI primario per tutti i task type in `ai_router.py`, `ai_client.py`, `event_research_engine.py`, `ai_research.py`, `biography.py`. Fallback chain: OpenAI → Anthropic → Mistral → Perplexity → Gemini.
- [x] **Modelli AI aggiornati**: Anthropic `claude-sonnet-4-5-20250929`, Gemini `gemini-2.0-flash` (sostituisce deprecato `gemini-1.5-flash`).
- [x] **LeBI Fase 4 — API**: 3 nuovi endpoint (`/api/lebi/search`, `/api/lebi/record/{id}`, `/api/lebi/compare/{soldier_id}`).
- [x] **LeBI Fase 4 — Frontend**: Tab "LeBI" nel dossier soldato (solo IMI), vista comparison con match/diff fields, detail espandibili, PDF links.
- [x] **LeBI Fase 4 — Parser fix**: `_parse_record_html` in `lebi.py` e `_parse_sections` in `sources_external_lebi.py` corretti per usare `fallen-label` class. Supporto sezione RIENTRO.
- [x] **Verifica reale**: ricerca "Rossi Mario" → 10 risultati, record #78247 parsato correttamente (cognome, nome, data nascita, grado, 7 campi internamento).
- [x] **Pipeline doc**: `docs/architecture/PIPELINE.md` creato con 11 sezioni (ricerca, AI, research-to-index, LeBI, compliance, OCR, biografia, event research, import, endpoint map, schema DB).
- [x] **Architettura aggiornata**: `ARCHITECTURE.md` versione 2026-07-24, stack AI con 5 provider, endpoint count 312.
- [x] **README aggiornato**: diagramma (27 provider, 5 AI), tabella federation (27), API LeBI, moduli LeBI.
- [x] **CHANGELOG aggiornato**: sezione 2026-07-24 dettagliata.
- [x] **TODO aggiornato**: questa sezione.

### Da completare (priorità)
- [ ] **LeBI Fase 5**: Report, FTS, Memory Router, Source Locator, citations.
- [ ] **LeBI Fase 7**: Test e documentazione — test su provider LeBI, adapter, API endpoint, frontend comparison.
- [ ] **Test conformità automatici**: 20 test Compliance Gate come da specifica.
- [ ] **Test migrazione PostgreSQL su Supabase**: creare progetto, eseguire `migrate_to_pg.py --full`, verificare conteggi.
- [ ] **Bulk import Scopri**: selezionare multipli risultati e importarli tutti insieme.
- [ ] **Auto-scan Scopri**: funzione che scansiona automaticamente tutti gli IMI deceduti e crea candidati in massa.
- [ ] **Frontend: visualizzare cross-check results** nel tab AI del dettaglio candidato.
- [ ] **Frontend: mappa geospaziale movimentazioni** (Leaflet + dati luogo_internamento).
- [ ] **Provider CRI Trieste**: ~34K schede Ufficio Prigionieri. Da implementare quando accessibile.
- [ ] **Integrazione Compliance Gate in endpoint esistenti**: export, dossier, pubblicazione.
- [ ] **Conformità Europeana Data Model (EDM)** — scadenza Creative Europe set 2026.

---

## Giornata 2026-07-23 (sera) — Frontend + Docs

### Completato
- [x] **Frontend `renderRedCross()`**: UI completa con ricerca, filtri fonte, tabella risultati, badge compliance, dettaglio record espandibile, link esterni.
- [x] **Frontend `renderCompliance()`**: UI completa con 3 tab (Policy, Coda revisione, Log decisioni), badge colorati, bottoni risoluzione review.
- [x] **Filtri avanzati Scopri**: 3 dropdown (fonte, conflitto, sorte) + backend `GET /discover-candidates` esteso con parametri `source`, `conflict`, `fate`.
- [x] **Architettura**: documento `ARCHITECTURE.md` generato (8 sezioni, 26 provider, flussi end-to-end, mappa endpoint).
- [x] **Riorganizzazione docs**: tutti i .md spostati in `docs/` con sottocartelle (architecture, manuals, changelog, todo, analysis).
- [x] **README.md**: aggiornato con architettura corrente.
- [x] **Manuale d'uso**: `docs/manuals/MANUALE_USO.md` creato.
- [x] **CHANGELOG**: aggiornato con sezione dettagliata.
- [x] **TODO**: aggiornato con task completati e nuovi pending.

### Da completare (priorità)
- [ ] **Bulk import Scopri**: selezionare multipli risultati e importarli tutti insieme.
- [ ] **Auto-scan Scopri**: funzione che scansiona automaticamente tutti gli IMI deceduti e crea candidati in massa.
- [ ] **Frontend: visualizzare cross-check results** nel tab AI del dettaglio candidato (match in Albo d'Oro, IMI, Nastro Azzurro, ecc.).
- [ ] **Frontend: visualizzare documenti di pratica nell'AI analysis** (sezione 3b/3c del processo logico).
- [ ] **Provider CRI Trieste**: ~34K schede Ufficio Prigionieri. Da implementare quando accessibile.
- [ ] **Test conformità automatici**: 20 test come da specifica.
- [ ] **Generatore pacchetto conformità**: funzione admin per documentazione tecnica bandi.
- [ ] **Integrazione Compliance Gate in endpoint esistenti**: export, dossier, pubblicazione — tutti devono passare dal gate.
- [ ] **Test migrazione PostgreSQL su Supabase**: creare progetto, eseguire `migrate_to_pg.py --full`, verificare conteggi.
- [ ] **Ottimizzazione batch migrazione**: tabelle grandi (collegamenti 2.3M) possono richiedere parallelismo.
- [ ] **Indici PostgreSQL**: ricreare indici non-PK da SQLite su PostgreSQL.
- [ ] **502 immagini AI (`/api/fonte/generate-images`)**: riprodurre con il `source_id` esatto che fallisce.
- [ ] **TNA: query per cognome causa HTTP 500** — usare query generiche o reference series.
- [ ] **Frontend: mappa geospaziale movimentazioni** (Leaflet + dati luogo_internamento).
- [ ] **Conformità Europeana Data Model (EDM)** — scadenza Creative Europe set 2026.

---

## Giornata 2026-07-23 — Compliance Gate + Fonti Croce Rossa + PostgreSQL

### Compliance Gate (completato)
- [x] **Schema DB**: `source_policies`, `compliance_decisions`, `compliance_authorizations`, `compliance_review_queue` + `life_status` su `rc_candidates`.
- [x] **`compliance_gate.py`**: motore `evaluate()` con 8 classificazioni, 11 azioni, 5 decisioni. Regole per UNREACHABLE, RESTRICTED, RIGHTS_UNKNOWN, dati sanitari, persona vivente, METADATA_ONLY, PUBLIC_VIEW, PUBLIC_DOWNLOAD, REQUEST_REQUIRED, AUTHORIZATION_REQUIRED.
- [x] **Pre-popolazione policy**: ICRC WW1 (METADATA_ONLY), CRI Milano (REQUEST_REQUIRED), CRI Trieste (METADATA_ONLY) con condizioni reali, contatti, credit line.
- [x] **Integrazione OCR**: endpoint OCR passa dal Compliance Gate. Documenti sanitari richiedono autorizzazione.
- [x] **API**: 10 endpoint `/compliance/*` (policies CRUD, decisions, review queue, authorize/revoke, evaluate).
- [x] **Frontend**: nav items "Croce Rossa" e "Conformità" + routing.

### Provider ICRC WW1 (completato)
- [x] **`source_providers/icrc_ww1.py`**: `ProviderICRCWW1` per `grandeguerre.icrc.org`. 5M+ schede prigionieri 1GM. Scraping HTML, metadati minimi, no download. Classificazione `METADATA_ONLY`.
- [x] **Registrazione in federation**: provider attivo nel registry.

### Provider CRI Milano (completato)
- [x] **`source_providers/cri_milano.py`**: `ProviderCRIMilano` per `cri-mi.archimista.com`. Catalogo archimista, dispersi 2GM. Documenti su richiesta. Classificazione `REQUEST_REQUIRED`.
- [x] **Registrazione in federation**: provider attivo nel registry.

### API Croce Rossa (completato)
- [x] **`GET /red-cross/search`**: ricerca simultanea ICRC + CRI Milano.
- [x] **`GET /red-cross/{provider}/{record_id}`**: dettaglio record (solo metadati).

### Migrazione SQLite → PostgreSQL (completato)
- [x] **`db_adapter.py`**: adapter layer trasparente. Conversione `?`→`%s`, `AUTOINCREMENT`→`SERIAL`, `PRAGMA`→no-op. `RealDictCursor` per compatibilità `sqlite3.Row`.
- [x] **`migrate_to_pg.py`**: script migrazione (schema, dati, indici, FTS, verifica). Batch insert con `ON CONFLICT DO NOTHING`. Supporto `--full`, `--schema-only`, `--data-only`, `--table=nome`.
- [x] **`database.py`**: `get_conn()` supporta SQLite e PostgreSQL.
- [x] **`search_service.py`**: `search_entities()` con FTS5 (SQLite) e tsvector (PostgreSQL). `get_fts_stats()` adattato.
- [x] **`db_init_fts.py`**: `run_migration()` con path PostgreSQL (tsvector + GIN + trigger).
- [x] **`.env.example`**: template con istruzioni Supabase.
- [x] **`requirements.txt`**: `psycopg2-binary>=2.9.0`.
- [x] **`app.py`**: `seed_source_policies()` al boot.

### Da completare
- [ ] **Provider CRI Trieste**: ~34K schede Ufficio Prigionieri. Parzialmente digitalizzato su `archiviodistatotrieste.it`. Da implementare quando accessibile.
- [ ] **Test conformità automatici**: 20 test come da specifica (link form rifiutato, RIGHTS_UNKNOWN blocca download, dati sanitari esclusi log, persona vivente richiede revisione, ecc.).
- [ ] **Generatore pacchetto conformità**: funzione admin che genera cartella documentazione tecnica per bandi (architettura, data flow, matrice permessi, DPIA, ecc.).
- [ ] **Integrazione Compliance Gate in endpoint esistenti**: export, dossier, pubblicazione — tutti devono passare dal gate.
- [ ] **Test migrazione PostgreSQL su Supabase**: creare progetto, eseguire `migrate_to_pg.py --full`, verificare conteggi.
- [ ] **Ottimizzazione batch migrazione**: tabelle grandi (collegamenti_backup 4.9M, collegamenti 2.3M) possono richiedere parallelismo.
- [ ] **Indici PostgreSQL**: ricreare indici non-PK da SQLite su PostgreSQL.

---

## Giornata 2026-07-22 (notte 2) — Scopri Candidati

- [x] **Backend: `GET /discover-candidates`** — ricerca simultanea in 9 fonti storiche (IMI, Albo d'Oro, Nastro Azzurro, decorati, caduti Ministero, CWGC, fonti_indice, fondi_archivistici, NARA T315) con multi-token search.
- [x] **Backend: `POST /discover-candidates/{source}/{id}/import`** — crea candidato RC da record storico con mappatura automatica campi + record in rc_sources + audit log.
- [x] **Backend: `DELETE /practices/{pid}`** — endpoint con cascade su documenti, versioni, checklist, scadenze, comunicazioni, pacchetti.
- [x] **Frontend: pagina Scopri** — campo ricerca, tabella risultati con tag colorati per fonte, bottoni Importa/Apri, loading state.
- [x] **Frontend: dashboard estesa** — 12 KPI reali nella sezione generale + 8 KPI operativi + 8 KPI pratiche.
- [x] **Frontend: link sito principale** — navbar con "Percorso Riconoscimenti →" al posto di "/1gm".
- [x] **Test: cleanup automatico** — sezione 14. Cleanup in `_test_ext.py` che elimina record di test. 28/28 pass.
- [x] **Verifica end-to-end**: ricerca "ALMONTI" → 4 risultati, import → candidato 102, AI analysis → 9 onorificenze.
- [ ] **Aggiungere filtri avanzati** nella pagina Scopri (per fonte, per conflitto, per sorte).
- [ ] **Bulk import** — selezionare multipli risultati e importarli tutti insieme.
- [ ] **Auto-scan** — funzione che scansiona automaticamente tutti gli IMI deceduti e crea candidati in massa.

---

## Giornata 2026-07-22 (notte) — Percorso Riconoscimenti: enhancement frontend + AI

- [x] **Frontend: tab Contatti** — form aggiunta manuale contatti discendenti con modal completo (nome, cognome, parentela, email, PEC, telefono, fonte, stato verifica, consenso) + CRUD (create/edit/delete).
- [x] **Frontend: tab Pratiche** — upload documenti con data caricamento + lista documenti con categoria, versione, stato verifica, data aggiornamento + bottoni verifica/archivia/elimina + form nuova pratica estesa.
- [x] **Frontend: dashboard estesa** — `loadDashboard` chiama `/dashboard` + `/dashboard-ext` in parallelo, render con 3 sezioni KPI (generale, operativi, pratiche) con border colorato per priorità.
- [x] **AI analysis: documenti pratiche** — `_get_candidate_full` recupera practice_documents, ext_practices, descendant_contacts. Processo logico con sezioni 3b/3c. % di concessione con boost/penalty per documenti verificati. Fattori e raccomandazioni estese.
- [x] **AI analysis: cross-check 9 fonti storiche** — `_cross_check_sources()` cerca cognome+nome in caduti_albooro (342K), internati (20K), decorati_nastroazzurro (280K), decorati (1.3K), caduti_ministero (162K), caduti_cwgc (506K), fonti_indice (35K), fondi_archivistici (4.8K), documenti_nara_t315. Boost % per match, fattori espliciti, raccomandazioni specifiche.
- [x] **Backend fix**: `archive_practice_document` accetta body vuoto.
- [x] **Test**: 27/27 passati. AI verificata su candidati reali (AGOSTI VASCO, BLUM GIULIO, BONDI DOMENICO).
- [x] **CHANGELOG**: aggiornato con sezione dettagliata.
- [ ] **Estendere test suite** per coprire cross-check fonti storiche e documenti pratiche nell'AI analysis.
- [ ] **Frontend: visualizzare cross-check results** nel tab AI del dettaglio candidato (mostrare match trovati in Albo d'Oro, IMI, Nastro Azzurro, ecc.).
- [ ] **Frontend: visualizzare documenti di pratica nell'AI analysis** (sezione 3b/3c del processo logico).

---

## Giornata 2026-07-22 (sera) — Nuovo modulo: Percorso Riconoscimenti

- [x] **Schema**: 14 tabelle DB con prefisso `rc_` + 9 nuove tabelle estese (institutional_contacts, rc_documents_v2, doc_versions, doc_checklists, communications, comm_threads, deadlines, rc_descendant_contacts, rc_practices).
- [x] **Permessi granulari**: 15+ nuovi permessi (rc:contact:write, rc:doc:upload, rc:doc:verify, rc:assessment:write, rc:pkg:generate_descendant, ecc.).
- [x] **API**: CRUD contatti discendenti estesi + istituzionali + documenti + checklist + comunicazioni + timeline + ricerca + dashboard estesa + pacchetti + fascicolo ufficiale.
- [x] **Frontend**: SPA con login, dashboard, elenco candidati con filtri + paginazione, dettaglio candidato con 9 tab, catalogo riconoscimenti, audit log.
- [x] **AI analysis**: modulo rule-based con processo logico, valutazione onorificenze, % di concessione, raccomandazioni.
- [x] **Test**: 27 test in `_test_ext.py` (auth, contatti, documenti, checklist, comunicazioni, scadenze, timeline, ricerca, pacchetti, fascicolo, privacy).

---

- [x] **Analisi manuale "Linee guida per l'indicizzazione"** (Antenati/DGA/FamilySearch, ed. 9 luglio 2024).
- [x] **Nuovo modulo `indexing_rules.py`** (single source of truth): `normalize_match_key`, `is_empty_value`, `strip_titles`, `expand_or_variants`/`fold_variants`, `titlecase_name`, `clean_toponym`, `normalize_age` — ognuna cita la sezione del manuale.
- [x] **Integrazione pipeline (no doppioni)**: `database._normalize_name`, `linker._norm`, `research_to_index._normalize_name` delegano al modulo condiviso; `search_service._normalize_query` rimuove titoli/placeholder.
- [x] **Test**: `tests/test_indexing_rules.py` (40 test). Suite 251 passed, 1 skipped.
- [x] **Applicare `clean_toponym`/`titlecase_name`/`normalize_age` in fase di import** dei dataset: integrati in caduti_ministero, caduti_cwgc, caduti_albooro, caduti_bologna, caduti_sardi, caduti_francia_ww1, decorati, decorati_nastroazzurro, import_fonti_personali, import_personal_sources. Valutare impatto su record già presenti (re-import necessario per normalizzare dati esistenti).
- [x] **Consolidare `audit_cross_db.normalize_text`** sul modulo condiviso: `normalize_text`/`normalize_name`/`is_empty` ora delegano a `indexing_rules`.
- [x] **Re-import dataset esistenti**: migrazione in-place completata. 6.381 record aggiornati su 1.347.135 totali (0 errori, 0 record cancellati). Normalizzati nomi (titlecase_name) e toponimi (clean_toponym) in caduti_ministero, caduti_cwgc, caduti_albooro, caduti_bologna, caduti_sardi, decorati, decorati_nastroazzurro.
- [x] **Indicizzare le varianti "O"** come voci ricercabili separate: `linker._save_persona_with_variants` espande nomi con "O" in entità separate collegate allo stesso record (sez. 1.4.5).

---

## Giornata 2026-07-21 (sera) — Fix errori console e AI multi-provider

- [x] **Fix crash React #231**: `onClick` stringa nel link "Albo ↗" → sostituito con handler funzione `onAlboClick`. Risolti a cascata tutti i `{{ }}` non risolti e l'errore sul `value` del number input caduti.
- [x] **Fix 400 report cronologico**: nome evento robusto da `_eventDossier.event.name` in `generateChronologicalReport`/`generateEventReport`/`sendEventChatMessage`.
- [x] **Provider AI specialista per-tab**: rimosso default `mistral` forzato negli endpoint report evento (Panoramica→Perplexity, Fonti→Anthropic, Punti di vista→OpenAI, Cronologia→Mistral).
- [x] **Modalità parallela multi-AI**: toggle Specialista/Parallelo nella UI + `mode="parallel"` nel backend con `ThreadPoolExecutor`.
- [x] **Filtro rilevanza fonti locali**: `_is_relevant()` scarta falsi positivi full-text (WWII su eventi WWI).
- [ ] **📧 GUARDARE EMAIL ERIKA**: controllare la posta in arrivo di Erika per eventuali richieste/comunicazioni in sospeso e rispondere/agire di conseguenza.
- [ ] **502 immagini AI (`/api/fonte/generate-images`)**: riprodurre con il `source_id` esatto che fallisce (gpt-image-1 conferma 200 OK; problema in metadata fonte o parsing JSON prompt).
- [x] **Bug latente grafi SVG**: sostituito `onClick="${() => ...}"` (stringificato nell'SVG) con `data-graph-idx` + event delegation tramite `onGraphSVGClick` sui container div. Fix applicato a tutti e 4 i grafi (eventi, luoghi, paesi, soldati).
- [x] **Verifica end-to-end nel browser preview**: server attivo su 8123, API verificate: eventi 1GM (22 eventi), graph luoghi (50 nodi), graph paesi (8 nodi), graph mesi (8 nodi), graph soldati clusters, search "gaiaschi" (1 internato, 4 caduti, 11 fonti_narrative), caduti evento "Battaglia del Carso" (200 OK). Browser preview avviato.

---

## Giornata 2026-07-21 — Verifiche e rifiniture

- [x] **Analisi approfondita connessione DB e frontend**: mappare quali tabelle/query alimentano ogni sezione della UI nel template comune `index.html` (1GM + 2GM). Documento `ANALISI_DB_FRONTEND.md` creato.
- [x] **Rimozione frontend 1GM dedicato**: eliminati `templates/PRIMA_Guerra/`, `templates/voci-data-1gm.js`, `templates/index-1gm.html`, le route `/1gm` e `/voci-data-1gm.js` in `app.py` e `tests/test_frontend_1gm.py`. **⚠️ Nessun dato eliminato dai database**: i file `.db` e i record restano intatti.
- [x] **Barra progresso percentuale per generazione report AI**: aggiunta in `templates/index.html` per report evento e report cronologico con `_eventReportProgress`/`_chronoReportProgress`.
- [x] **Fix URL Albo d'Oro per caduti**: normalizzazione `detail_url` relativo in URL assoluto `https://www.cadutigrandeguerra.it/...` in `events.py`, `app.py` e `caduti_albooro.py`. Verificato su `Battaglia del Carso` (id 1 → ABBONIZIO GIUSEPPE).
- [ ] **Verifica end-to-end AI buttons in home search**: cercare "gaiaschi", cliccare `Dossier AI` e `Immagini AI` su una card, confermare che il dossier si apre e la generazione parte.
- [ ] **Test tab evento popolati**: aprire "Battaglia del Carso" e verificare che i tab `Caduti` e `Decorati` mostrino dati nel browser preview.
- [x] **Falsi positivi linter CSS**: warning da templating `{{ }}` negli attributi `style` accettati come noti; `.vscode/settings.json` non creato perché la cartella `.vscode/` è in `.gitignore`.
- [x] **Test suite**: eseguito `python -m pytest tests/ -q` → **220 passed, 1 skipped**. Fixati 3 fallimenti: scansione `.venv` in `test_project_health.py`, conteggio `SCRAPER_ALLOWED_DOMAINS` in `test_fonti_risorse_master.py`, mock `federated_search` in `test_soldier_dashboard.py`.
- [x] **Pulizia workspace**: rimossi file `tmp_*`, DB vuoti, audit HTML/JSON residui e output HTML di debug.
- [x] **Documentazione**: aggiornato `README.md` con sezione "AI nel frontend".

---

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

## Stato attuale (14/7 h 15:50)

- ✅ **Server attivo su porta 8001** (evitati processi uvicorn zombie sulla 8000).
- ✅ **Pipeline multi-AI parallela in esecuzione** (`mode=parallel_multi_ai`, limit 1.000 soldati/AI, tot 4.000 + reparti + eventi + luoghi).
- ✅ **Watchdog attivo** controlla ogni 5 min server + pipeline, scrive `watchdog_snapshot.json`.
- ✅ **Fix `/api/mass-index/status`** — aggiunto import locale `get_conn`, niente più 500.
- ✅ **`fonti_indice` a 113.670+ record** (Arolsen 38.570, TNA 34.219, Bundesarchiv 27.788, Archivportal-D 10.778, WikiTree 1.312, CWGC 180, altri).
- ✅ **Repo GitHub aggiornato** a `046fb7c` → `820aa46`.

## Task residui

- [ ] **Bando MiC (scad. 15/7 ore 12:00)** — URGENTE — solo amministrativo
- [ ] DDB API key: registrarsi su deutsche-digitale-bibliothek.de per ottenere key
- [ ] TNA: query per cognome causa HTTP 500 — usare query generiche o reference series
- [ ] Popolamento massivo completo: 20.464 soldati × tutti i provider (stimato 8-12h con 4 AI)
- [ ] Frontend: aggiungere tab Report nella UI (query libera → report narrativo)
- [ ] Frontend: mappa geospaziale movimentazioni (Leaflet + dati luogo_internamento)
- [ ] Conformità Europeana Data Model (EDM) — scadenza Creative Europe set 2026
- [x] Gemini: verificare che google-generativeai sia installato (`pip install google-generativeai`)
