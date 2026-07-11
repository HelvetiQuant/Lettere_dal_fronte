# TODO — VOCI DAL FRONTE / IMI Extractor

Aggiornato: 11 luglio 2026, dopo analisi diretta del repo GitHub `helvetiquant/lettere_dal_fronte` (zip caricato, 228 file). Questa versione **corregge** la precedente, basata su una copia sincronizzata non aggiornata di alcuni file (in particolare `app.py`, che nella copia sincronizzata era un prototipo di 133 righe — nel repo reale è il sistema completo da 1.388 righe / 85 endpoint).

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
| 3 | Bug ricerca multi-parola (`search_all()` restituiva 0 risultati per query come "Rossi Mario") | ✅ **Risolto**: `database.py` ora tokenizza la query (`_tokenize`) e costruisce `WHERE` con OR incrociato su token×colonne (`_where_like_clause`), includendo anche `fonti_narrative` tra i risultati. | ⚠️ Il matching resta OR puro tra token — può restare troppo permissivo (falsi positivi su cognomi comuni). Da affinare se il rumore nei risultati diventa un problema reale in uso. |
| 4 | Script scratch mescolati ai moduli di produzione | Ancora presente: 61 file su 104 (59%) con prefisso `_test_/_check_/_run_/_status_/_fix_`. | 🟢 Bassa priorità — cleanup rimandabile. |
| 5 | Nessun test automatizzato | Aggiunto `tests/test_smoke.py` con 6 smoke test unittest su `search_all()`, `get_all_records_for_ai()`, `search_service.search_entities()`, `memory_router.route_query()` e import `app`. **Tutti passati**. | ✅ Risolto. Gli script `test_50_queries.py`/`test_research_to_index.py`/`test_wikitree.py` rimangono utili come reference ma non sono la test suite principale. |

---

## 2. DATI — stato reale e azioni

| # | Elemento | Stato | Azione |
|---|---|---|---|
| 1 | **Integrità `imi_internati.db` (1,4 GB)** | Il file `TODO_2026-07-10.md` del team segnala: dal mount del sandbox Cowork risultava "database disk image is malformed" — probabile artefatto di sincronizzazione durante scrittura concorrente (linker in esecuzione). | 🔴 **Da verificare sulla macchina reale**: `python -c "import sqlite3; print(sqlite3.connect('imi_internati.db').execute('PRAGMA quick_check').fetchone())"`. Se il risultato è `ok`, è solo un artefatto del mount, non un problema reale. |
| 2 | **Import lettere personali → star schema** | ✅ **Eseguito sul DB live**: `import_personal_sources.py` ha creato **40 record** in `fonti_narrative` con **69 collegamenti** in `entita`/`collegamenti`; `import_lettere_personali.py` ha migrato **1 record** in `lettere_personali` dallo snapshot `ocr_lettere.db`. | Verificare in UI con il caso Gaiaschi. |
| 3 | **Caso di test "Luigi Gaiaschi"** | Segnalato come IMI reale con documenti primari sul Desktop (Stalag, foglio caratteristico, liberazione 1945), assente da tutte le tabelle nel backup del 7/7. | Dopo l'import di `fonti_narrative`, cercarlo in UI per validare l'intero flusso "fonte pesante sul Desktop → collegata al soldato → biografia AI". Buon caso reale da usare anche come screenshot per il bando MiC. |
| 4 | **Dossier verificato (biography.py)** | Implementato con fallback gpt→claude→mistral→perplexity, ma mai testato end-to-end con chiavi API reali (non testabile dal sandbox Cowork). | Test da fare sulla macchina locale con le chiavi reali. |
| 5 | **Linker cross-dataset** | Nella copia sincronizzata risultava ancora in esecuzione l'11/7 mattina. Stato attuale non verificabile da qui (serve accesso diretto alla macchina). | Controllare se è terminato; se sì, aggiornare i conteggi in `ARCHITETTURA_DB.md`. |
| 6 | **CWGC** | Risultava completato nei log (tutte le nazionalità WW1+WW2, incluso UK WW2 a ~401k). | Solo da confermare nei documenti, non richiede altro lavoro tecnico. |
| 7 | **Provider federation** | ✅ **Parzialmente risolto**: TNA, Europeana, DDB, Mémoire des Hommes, Internet Archive, Google Books, Gallica/BNF e HathiTrust hanno query reali. Stati Uniti: Arolsen, Bundesarchiv, LAC, AWM, ABMC rimangono stub o accesso a catalogo. Italia/USSME cerca in `fondi_archivistici` locali. | 🟡 **Non più bloccante per il bando MiC**. Rifinire quando si arricchiranno fonti Asse/Alleati specifiche per singoli soldati/eventi (ottobre 2026). |

---

## 3. Non prioritario oggi

- Consolidare `import_lettere_personali.py` + `import_personal_sources.py` in un unico modulo (oggi coesistono due percorsi paralleli per contenuti concettualmente simili).
- Conformità Europeana Data Model (EDM), OpenAPI/Swagger, mappa geospaziale, responsive mobile, multilingua — coerenti con le scadenze Creative Europe (set 2026) e Horizon Europe (23 set 2026), non con quella di oggi.

---

## Nota metodologica

Molte voci sopra (integrità DB, esecuzione migrazioni, stato linker, test con chiavi API reali) **non sono verificabili dal sandbox Cowork**: non ho accesso al file `imi_internati.db` (troppo grande/escluso da .gitignore) né alle chiavi API del progetto. Vanno confermate direttamente sulla macchina dove gira il progetto.
