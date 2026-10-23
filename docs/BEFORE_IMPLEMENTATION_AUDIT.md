# BEFORE_IMPLEMENTATION_AUDIT.md

## Audit completo pre-implementazione — 2026-08-06

---

## 1. Schema e flusso attuale

### 1.1 Database SQLite (`imi_internati.db`)

**Tabelle persona (5):**

| Tabella | Record | Guerra | Campi chiave |
|---------|--------|--------|--------------|
| `internati` | 20.465 | WWII | cognome, nome, data_nascita, luogo_nascita, residenza, grado, luogo_cattura, data_cattura, luogo_internamento, matricola, arbeitskommando, mansione, sorte, data, raw_text |
| `caduti_albooro` | 342.555 | WWI | nominativo, paternita, classe, comune_attuale, grado, reparto, anno_morte, luogo_morte, causa_morte |
| `decorati_nastroazzurro` | 279.832 | WWI | cognome, nome, anno_decorazione, forza_armata, decorazione, grado, reparto |
| `caduti_cwgc` | 506.446 | BOTH | nome, cognome, data_morte, cimitero, paese_cimitero, guerra, service_number, rank, regiment |
| `caduti_ministero` | 162.646 | WWII | nominativo, data_nascita, data_decesso, luogo_sepoltura, nazione_decesso, grado, reparto |

**Tabelle ausiliarie:**
- `fonti_indice`: 35.664 record (fonti archivistiche)
- `archivio_documenti`: 979 record (documenti federati)
- `entita`: entità normalizzate
- `collegamenti`: relazioni legacy
- `data_corrections`: 0 record (tabella overlay esiste ma vuota)
- `entity_variants`: 334 record (varianti/correzioni)

**Database eventi (`eventi_1gm.db`):**
- `eventi_1gm`: 21 eventi canonici (16 WWI + 5 WWII)
- `event_links`: 1.539.685 record — **TUTTI quarantined** (usable_as_evidence=0)

### 1.2 Linking v2 schema (`linking/schema_v2.py`)

Schema completo già definito:
- `resource_registry`: 16 record (solo person, da esecuzione parziale)
- `relations`: **0 record** — pipeline mai eseguita con `--execute`
- `claims_v2`: 0 record
- `evidence_fragments`: 0 record
- `pipeline_runs`: 0 record
- `legacy_relation_quarantine`: 0 record (migrazione formale mai eseguita)

### 1.3 Pipeline attiva

**Orchestratore:** `UnifiedResearchOrchestratorV7` (`unified_orchestrator_v7.py`)
- 9 stage: PLAN → DISCOVER → FETCH → EXTRACT → RESOLVE → FUSE → VALIDATE → NARRATE → PERSIST
- API: `POST /api/v7/research` (`v7_api.py`)
- Singleton orchestrator con cache

**Narratore:** `NarratorV7_v2` (`v7_narrator.py`)
- AI draft (OpenAI GPT-4o) con fallback deterministico
- OutputValidatorV7: controlla URL hallucinated, source_id non in snapshot, archivi non verificati
- NarrationValidator (`narration_validator.py`): valida claim_ids in allowlist, certainty matching, no URL in text, request_type matching
- **Non fa entailment semantico** (non rileva impiccato→internato, figlio→padre, ecc.)

**Identity model:** `IdentityResolver` (`v7_identity_model.py`)
- 5 stati: ANCHORED_RECORD, RESOLVED_IDENTITY, AMBIGUOUS_IDENTITY, PARTIAL_IDENTITY, UNRESOLVED_IDENTITY
- Discriminanti: birth_year, birth_place, paternita, unit+period, death_year/place, matricola, grado
- Missing discriminant is NOT agreement
- War period classification per table

**Fusion engine:** `FusionEngine` (`v7_fusion_engine.py`)
- SourceFamilyGraph + IndependenceAssessor
- Blocca fusion per AMBIGUOUS_IDENTITY
- Tagga claim con identity_cluster_id e evidence_scope

### 1.4 API e frontend

**API (FastAPI, `app.py`):**
- `POST /api/v7/research` — esegue pipeline completa
- `GET /api/v7/research/{run_id}` — stato run
- `POST /api/v7/narrate` — re-narra snapshot
- `GET /api/v7/system/capabilities` — capacità sistema
- `GET /api/v7/health` — health check
- Router legacy: `linking_v2_api`, `report_conversation_api`, `capability_api`, ecc.

**Frontend (React SPA):**
- `AdminPage.tsx` con corrections dashboard e narrator status
- Pagine: search, dbView, soldier dashboard, graph, map, admin

---

## 2. Script legacy analizzati

### 2.1 `_gen_event_links.py` (FROZEN)
- **Stato:** Kill-switch attivo, richiede `LEGACY_JOB_LEGACY_EVENT_LINKS=true`
- **Fix V7.3 già applicati:** Word boundary matching, temporal barriers WWI/WWII, no skip-if-exists, multi-event matching
- **Problemi residui:**
  - Usa `raw_text`, `sorte`, `luogo_cattura`, `luogo_internamento`, `arbeitskommando` come testo aggregato indistinto
  - Collega decorati per anno decorazione (non prova evento premiato)
  - Usa cimitero ↔ alias (cimitero ≠ luogo morte)
  - Keyword generiche in blocchi di testo aggregato
  - Nessuna provenance, nessuna algorithm version, nessun evidence fragment
  - Confidence non calibrata

### 2.2 `_gen_record_links.py` (FROZEN)
- **Stato:** Kill-switch attivo
- **Fix V7.3 già applicati:** Quarantine invece di DELETE, pairwise links (no star topology), exact year match con ORDER BY
- **Problemi residui:**
  - Soldati uniti per anno_morte + luogo_morte (condivisione ≠ relazione storica)
  - Decorati uniti per anno_decorazione
  - Soldati ↔ documenti per anno o luogo
  - `fonte_personale` basato su cognome+nome in haystack (substring, non word boundary)
  - LIMIT 50 arbitrario nel pairwise
  - Nessuna provenance, nessun evidence fragment

### 2.3 `_clean_bad_links.py` (FROZEN)
- **Stato:** Kill-switch attivo
- **Fix V7.3 già applicati:** Quarantine invece di DELETE, confidence=0.0
- **Problemi residui:**
  - Confronta `fonti_indice.id` con `collegamenti.entita_id` senza provare namespace match
  - Nessun typed resource UUID
  - Nessun restore mechanism formale

### 2.4 `_fix_gaiaschi_db.py` (FROZEN)
- **Stato:** Kill-switch attivo
- **Fix V7.3 già applicati:** Usa `data_corrections` overlay table invece di UPDATE diretto
- **Problemi residui:**
  - "Confermata Grecia" senza evidence locator o documental reference
  - Nessun review_decision record
  - Usa `entity_variants` come workaround, non claim model strutturato
  - Non registra autore/revisore/ versione/stato approvazione in modo tracciabile

### 2.5 `_find_best_candidates.py`
- **Stato:** Read-only, import-safe
- **Problemi:** Query SQL con `LIKE '%cognome%'` nel fallback, usa `collegamenti` legacy

---

## 3. Difetti confermati

### 3.1 Difetti strutturali

| # | Difetto | Impatto | Causa radice |
|---|---------|---------|--------------|
| D1 | Nessuna separazione PERSON_EVIDENCE vs CONTEXT_EVIDENCE | Contesto promosso a fatto personale | Pipeline non distingue scope claim |
| D2 | Validatore senza entailment semantico | impiccato→internato, figlio→padre non rilevati | Validator solo syntactic (pattern matching) |
| D3 | 0 relazioni v2 generate | Linking v2 schema esiste ma inutilizzato | Pipeline mai eseguita con --execute |
| D4 | 1.708.869 link legacy quarantined ma non migrati formalmente | legacy_relation_quarantine vuoto | Migrazione formale mai eseguita |
| D5 | Nessuna tipizzazione luoghi | Campo→residenza→luogo morte ambigui | Modello campi come stringhe |
| D6 | Nessuna precisione date | 3-??/1945 → marzo 1945 | normalize_date non traccia partial OCR |
| D7 | No parser relazioni familiari | "di Michelangelo" → padre invece di figlio | Nessun parser formule archivistiche |
| D8 | No ontologia gradi/reparti | "sergente" → "comandava squadra" | Nessun modello storico versionato |
| D9 | No finestra temporale adattiva | Anno → battaglia specifica | Contesto non legato a precisione |
| D10 | No modulo contesto storico-geografico | Hildesheim senza contesto separato | Nessun generatore contesto luoghi |
| D11 | publication_status non separato | "8/8 processati, 0 errori" | Solo execution_status |
| D12 | No 11-sezioni risposta finale | Report piatto | Narratore non strutturato per sezioni |
| D13 | entity_variants come workaround | Correzioni non tracciate | data_corrections vuoto |
| D14 | caduti_albooro classificato WWI ma event_links ha war_period vuoto | Contaminazione possibile | Eventi non classificati in DB |

### 3.2 Falsi positivi confermati (campioni)

**Event links (1.539.685 totali, tutti quarantined):**
- 1.262.644 `soldato_decorato` — decorati collegati a eventi per anno
- 260.903 `soldato_caduto` — caduti collegati per luogo_morte con keyword match
- 12.759 `internato_ww2` — internati collegati usando raw_text aggregato

**Record links (169.184 totali, tutti quarantined):**
- 142.594 `stesso_evento_luogo` — soldati uniti per anno+luogo morte
- 11.222 `stesso_anno_decorazione` — decorati uniti per anno
- 9.546 `fonte_personale` — soldati↔fonti per cognome+nome in haystack
- 5.822 `documento_evento` — soldati↔documenti per anno

**Esempi concreti di falsi positivi:**
- `Lana` matcha `Castellana` (ora fixato con word boundary)
- `Roma` matcha `Romania` (ora fixato)
- `Campo` geocodificato come campo di prigionia (non fixato — ancora in keyword list)
- `Prigionia` come luogo di morte (non fixato — ancora in eventi canonici)
- `Estero` come comune_attuale (non fixato — nessuna categoria amministrativa)
- Decorati collegati a Operazione Achse per anno 1943 (WWI vs WWII non filtrato per decorati)

---

## 4. Quantità link generati dalle regole legacy

| Tabella | Tipo link | Quantità | Stato |
|---------|-----------|----------|-------|
| event_links | soldato_decorato | 1.262.644 | Quarantined |
| event_links | soldato_caduto | 260.903 | Quarantined |
| event_links | internato_ww2 | 12.759 | Quarantined |
| event_links | fonte_archivistica | 2.310 | Quarantined |
| event_links | documento | 1.068 | Quarantined |
| event_links | soldato_caduto_cwgc | 1 | Quarantined |
| record_links | stesso_evento_luogo | 142.594 | Quarantined |
| record_links | stesso_anno_decorazione | 11.222 | Quarantined |
| record_links | fonte_personale | 9.546 | Quarantined |
| record_links | documento_evento | 5.822 | Quarantined |
| **TOTALE** | | **1.708.869** | **Tutti quarantined** |

---

## 5. Piano di migrazione

### Fase 1: Audit (questo documento)
- Completato

### Fase 2: Fix legacy scripts
- Congelare definitivamente gli script legacy (già FROZEN)
- Rimuovere keyword ambigue da eventi canonici (`Campo`, `Prigionia`, `Lana`)
- Aggiungere `ADMINISTRATIVE_CATEGORY` per `Estero`

### Fase 3: PERSON_EVIDENCE vs CONTEXT_EVIDENCE
- Estendere `EvidenceSnapshotV7` con `person_claims` e `context_claims` separati
- Modificare `_stage_extract` per classificare ogni claim con scope
- Modificare `_stage_fuse` per non promuovere context a person

### Fase 4: Modello semantico campi
- Creare `semantic_fields.py` con tipi luogo, precisione date, parser paternità
- Integrare in `_stage_extract` e `_stage_resolve`

### Fase 5: Risoluzione identità (6 stati)
- Estendere `v7_identity_model.py` con PROBABLE_MATCH, POSSIBLE_DUPLICATE, CONFLICTING
- Aggiungere UNRESOLVED (già presente come UNRESOLVED_IDENTITY)

### Fase 6: Ontologia gradi/reparti
- Creare `military_ontology.py` con modello versionato
- Integrare in narratore per rank_context e unit_context

### Fase 7: Linking persona-reparto-evento
- Estendere `linking/feature_extraction.py` con nuovi relation types
- Eseguire pipeline v2 con --execute

### Fase 8: Finestra temporale adattiva
- Creare `temporal_window.py` con finestre configurabili

### Fase 9: Contesto storico-geografico
- Creare `place_context.py` con generatore contesto mirato

### Fase 10: Validatore semantico
- Creare `semantic_validator.py` con entailment claim-by-claim
- Integrare in `_stage_validate` e `_stage_narrate`

### Fase 11: Stati claim + publishability
- Estendere snapshot con 4 stati separati
- Modificare API response

### Fase 12: Struttura risposta finale (11 sezioni)
- Modificare `NarratorV7_v2` per generare 11 sezioni
- Modificare `ReportRenderer` per output strutturato

### Fase 13: API + frontend
- Estendere `v7_api.py` con nuovi campi response
- Aggiornare frontend per visualizzazione separata

### Fase 14: Migrazione link legacy
- Eseguire migrazione formale: event_links/record_links → legacy_relation_quarantine
- Ricalcolare candidati con v2

### Fase 15: Regression test
- 10 casi reali (A-J) + test automatici

---

## 6. Rischi di regressione

| Rischio | Mitigazione |
|---------|-------------|
| Breaking API esistente | Nuovi campi additive, vecchi campi mantenuti |
| Performance degradata | Blocking indexes già in linking v2 |
| Perdita dati legacy | Quarantine non DELETE, backup prima di migrazione |
| Frontend incompatibile | Nuovi campi opzionali, frontend aggiornato in parallelo |
| Pipeline timeout | Esecuzione batch con resume |
| AI provider non disponibile | Fallback deterministico già presente |

---

## 7. Criteri di misurazione del miglioramento

| Metrica | Baseline | Target |
|---------|----------|--------|
| Relazioni v2 attive | 0 | ≥ 1.000 candidate |
| Link legacy invalidati | 0 (formale) | 1.708.869 |
| Falsi positivi linking | ~100% (quarantined) | < 5% |
| Claim con provenance puntuale | Sconosciuto | 100% person claims |
| Identità ambigue con biografia unificata | Presenti | 0 |
| Errori semantici non rilevati | Presenti | 0 |
| raw_text modificato | No (già immutabile) | 0 |
| Segreti in log | 0 (verificato) | 0 |
| Categorie geocodificate errate | Presenti | 0 |
| Contesto promosso a fatto personale | Presente | 0 |

---

## 8. Sicurezza e .env

- **Nessuno script legge direttamente `.env`** — verificato con grep su tutti i file `.py`
- Le chiavi API sono caricate tramite `os.environ` / `os.getenv` (variabili d'ambiente)
- Nessuna porzione di chiave compare nei log
- Controllo API: indicare solo `configured/not configured`

---

## 9. Baseline benchmark (su 8 target reali)

Eseguito il 2026-08-06 su 8 target (6 casuali + Gaiaschi Luigi + Gaiaschi Giuseppe):

| Target | Tabella | Identità | Claim | Oss. | Tempo | Hallucination flags |
|--------|---------|----------|-------|------|------|-------------------|
| Tarise Giuseppe | internati | RESOLVED | 7 | 63 | 18.5s | 3 (date, luogo) |
| Pompa Gianfranco | internati | RESOLVED | 6 | 72 | 17.4s | 3 (luogo, data) |
| Roberti Nicola | caduti_albooro | RESOLVED | 50 | 138 | 15.4s | 0 |
| Carbone Giuseppe | caduti_albooro | AMBIGUOUS | 210 | 195 | 12.2s | 0 |
| Basavecchia Corrado | decorati | RESOLVED | 3 | 57 | 25.5s | 2 (date) |
| Nerini Giuseppe | decorati | AMBIGUOUS | 20 | 96 | 16.6s | 0 |
| Gaiaschi Luigi | internati | RESOLVED | 8 | 39 | 15.2s | 0 (fallback) |
| Gaiaschi Giuseppe | caduti_albooro | AMBIGUOUS | 16 | 59 | 28.0s | 0 |

**Totale: 8/8 esecuzioni concluse, 0 errori tecnici, 8 hallucination flags rilevati**

**Problemi baseline confermati:**
- Tarise: "impiccato a Hildesheim" non preservato (diventato "internato")
- Tarise: "Mantova-Marmirolo" trasformato in residenza
- Pompa: "deceduto per bombardamento" causa omessa
- Pompa: "Littoria, Arena?" trasformato in residenza certa
- Roberti: "di Michelangelo" interpretato come "padre di" invece di "figlio di"
- Basavecchia: "per il suo contributo militare" (formula generica non in evidenza)
- Nerini: "classe 1888" → "chiamato alle armi nel 1888"
- Gaiaschi Luigi: report deterministico senza sezioni discorsive
- 3/8 identità ambigue ma tutte con biografia unificata assertiva
- Publication status non separato da execution status

---

## 10. File chiave da modificare

| File | Modifica | Priorità |
|------|----------|----------|
| `unified_orchestrator_v7.py` | Stage EXTRACT/FUSE/VALIDATE/NARRATE | Alta |
| `v7_identity_model.py` | 6 stati, nuovi discriminanti | Alta |
| `v7_narrator.py` | 11 sezioni, rank/unit context | Alta |
| `narration_validator.py` | Entailment semantico | Alta |
| `evidence_snapshot_v7.py` | person_claims/context_claims separation | Alta |
| `v7_api.py` | Nuovi campi response | Media |
| `linking/feature_extraction.py` | Nuovi relation types | Media |
| `linking/scoring.py` | Nuovi evidence_strength rules | Media |
| `_gen_event_links.py` | Rimozione keyword ambigue (frozen) | Bassa |
| `linking/schema_v2.py` | Estensione tabelle contesto | Media |

### Nuovi file da creare

| File | Scopo |
|------|-------|
| `semantic_fields.py` | Tipi luogo, precisione date, parser paternità |
| `military_ontology.py` | Ontologia gradi/reparti versionata |
| `temporal_window.py` | Finestra temporale adattiva |
| `place_context.py` | Contesto storico-geografico |
| `semantic_validator.py` | Validatore entailment claim-by-claim |
| `publication_status.py` | Stati pubblicabilità |
| `tests/test_regression_real.py` | 10 regression test reali (A-J) |
| `tests/test_semantic.py` | Test automatici generali |
