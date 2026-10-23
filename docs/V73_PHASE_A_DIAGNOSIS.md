# V7.3 Phase A — Diagnosi e Baseline

## Data: 2026-08-03
## Branch: fix/provenance-linking-v2
## Commit: ae07093

---

## 1. Stato del repository

- **Branch**: `fix/provenance-linking-v2`
- **Ultimo commit**: `ae07093` (feat: narration V2 pipeline + ai_client JSON schema nativo)
- **File non committati**: 96 (report, canary, script temporanei)
- **Backup creati**: `imi_internati_backup_v73_phase_a.db` (1.88 GB), `eventi_1gm_backup_v73_phase_a.db` (249 MB)

---

## 2. Schema database

### imi_internati.db — 141 tabelle, 284 indici

Tabelle principali:

| Tabella | Righe | Note |
|---------|-------|------|
| internati | 20,465 | Record principali IMI WWII |
| decorati | 1,286 | Decorati di guerra |
| decorati_nastroazzurro | 279,832 | Albo d'oro nastro azzurro |
| caduti_albooro | 342,555 | Caduti albo d'oro |
| caduti_cwgc | 506,446 | Caduti CWGC (Commonwealth) |
| caduti_ministero | 162,646 | Caduti ministero |
| caduti_bologna | 9,656 | Caduti Bologna |
| caduti_sardi | 20,435 | Caduti sardi |
| caduti_francia_ww1 | 24,279 | Caduti Francia WWI |
| fonti_indice | 35,664 | Fonti archivistiche |
| archivio_documenti | 979 | Documenti archivio |
| archivio_fonti | 1,153 | Fondi archivistici |
| entita | 688,739 | Entità (persone, luoghi, eventi) |
| collegamenti | 2,349,417 | Collegamenti legacy |
| collegamenti_backup | 4,894,390 | Backup collegamenti |
| record_links | 169,184 | Link record-to-record |
| event_links | 0 | (vuota in imi_internati.db) |
| eventi_1gm | 15 | Copia locale eventi (senza colonne V3) |
| claims | 51 | Claim storici |
| claim_evidence | 601 | Evidenze claim |
| claim_relations | 138 | Relazioni fra claim |
| source_authority_registry | 12 | Registro autorità fonti |
| sync_outbox | 11 | Outbox Supabase |

### eventi_1gm.db — 7 tabelle, 10 indici

| Tabella | Righe | Note |
|---------|-------|------|
| eventi_1gm | 49 | Registro eventi (con colonne V3) |
| event_aliases | 161 | Alias eventi |
| event_links | 1,539,685 | Link evento-target |
| source_authority_registry | 12 | Registro autorità |
| legacy_link_quarantine_audit | 0 | Audit quarantena (vuota) |
| map_features | 0 | Feature mappa (vuota) |

---

## 3. Inventario legacy

### Script legacy frozen (kill_switch attivo)

| Script | Dimensione | Stato |
|--------|-----------|-------|
| `_gen_event_links.py` | 31,816 bytes | FROZEN (kill_switch) |
| `_gen_record_links.py` | 12,926 bytes | FROZEN (kill_switch) |
| `_clean_bad_links.py` | 4,916 bytes | FROZEN (kill_switch) |
| `_fix_gaiaschi_db.py` | 4,262 bytes | FROZEN (kill_switch) |
| `_fix_db.py` | 7,698 bytes | Non frozen |
| `_find_best_candidates.py` | 2,212 bytes | Non frozen |
| `_gen_event_links_v3.py` | 14,112 bytes | V3 replacement |
| `_gen_record_links_v3.py` | 17,737 bytes | V3 replacement |

### Script di check (non test automatici)

`_check_*.py` (14 file), `_status*.py` (2 file) — stampano informazioni ma non hanno assertion o criteri di fallimento.

---

## 4. Contaminazione WWI/WWII

### event_links (eventi_1gm.db) — 1,539,685 righe

**Tutti i link sono `status=unverified`, `rule_version=''` (vuoto).**

#### WWI eventi collegati a WWII internati (12,759 link)

| Evento WWI | target_table | link_type | Righe |
|------------|-------------|-----------|-------|
| Prigionia (id=25, 1915-1918) | internati | internato_ww2 | 4,348 |
| Monte Pasubio (id=23, 1916-1918) | internati | internato_ww2 | 1,461 |
| Battaglia del Piave (id=19, 1918) | internati | internato_ww2 | 740 |
| Monte Col di Lana (id=28) | internati | internato_ww2 | 543 |
| Monte Nero (id=29) | internati | internato_ww2 | 302 |
| Battaglie dell'Isonzo (id=17) | internati | internato_ww2 | 282 |
| Battaglia di Vittorio Veneto (id=20) | internati | internato_ww2 | 175 |
| Fronte Albanese (id=27) | internati | internato_ww2 | 155 |
| Battaglia di Caporetto (id=16) | internati | internato_ww2 | 49 |
| Altopiano di Asiago (id=21) | internati | internato_ww2 | 27 |
| Fronte Macedone (id=26) | internati | internato_ww2 | 15 |

#### WWII eventi collegati a tabelle WWI

| Evento WWII | target_table | link_type | Righe |
|-------------|-------------|-----------|-------|
| Campagna di Russia (ARMIR) | decorati_nastroazzurro | soldato_decorato | 26,814 |
| Battaglia di Tobruk | decorati_nastroazzurro | soldato_decorato | 22,984 |
| Operazione Achse | decorati_nastroazzurro | soldato_decorato | 7,981 |
| Mauthausen e Gusen | decorati_nastroazzurro | soldato_decorato | 7,981 |
| Lavoro forzato nel Reich | decorati_nastroazzurro | soldato_decorato | 7,981 |
| Eccidio di Cefalonia | decorati_nastroazzurro | soldato_decorato | 3,830 |
| Battaglia di Tobruk | caduti_albooro | soldato_caduto | 340 |
| Eccidio di Cefalonia | caduti_albooro | soldato_caduto | 176 |
| Battaglia di Cassino | decorati_nastroazzurro | soldato_decorato | 131 |
| Campagna di Russia (ARMIR) | caduti_albooro | soldato_caduto | 53 |
| Battaglia di Cassino | caduti_albooro | soldato_caduto | 14 |
| Mauthausen e Gusen | caduti_albooro | soldato_caduto | 8 |
| Operazione Achse | caduti_albooro | soldato_caduto | 2 |

#### Keyword generiche

- `match_value='Campo'`: 10,270 link (campo da solo ≠ campo di prigionia)
- `match_value='Lager'`: link a "Prigionia" (WWI) per WWII internati
- `match_value='Acqui'`: link a "Eccidio di Cefalonia" per WWII internati

### record_links (imi_internati.db) — 169,184 righe

**Tutti i link sono `status=unverified`, `legacy_unverified=1`, `rule_version=''` (vuoto).**

| link_type | Righe | Problema |
|-----------|-------|----------|
| stesso_evento_luogo | 142,594 | Luogo di morte come prova di partecipazione |
| stesso_anno_decorazione | 11,222 | Anno decorazione come relazione fra persone |
| fonte_personale | 9,546 | Fonte personale non verificata |
| documento_evento | 5,822 | Documento collegato per anno |

### collegamenti (imi_internati.db) — 2,349,417 righe

Tabella legacy senza stati, provenienza, o regole.

---

## 5. Registro eventi — problemi strutturali

### "Battaglie dell'Isonzo" (evt_0017)

- **Data fine**: 1917-09-12 (fine dell'undicesima battaglia)
- **Figli**: 14 eventi (11 battaglie numerate + Carso + Monte Nero + Caporetto)
- **Problema**: La serie dichiara "12 offensive" ma termina alla fine dell'undicesima. Caporetto (12ª battaglia, 24 ott - 12 nov 1917) è presente come figlio ma la data fine della serie non la include.
- **Correzione necessaria**: Data fine serie → 1917-11-12 (inclusione Caporetto)

### Caporetto (evt_0016)

- Correttamente figlio di Battaglie dell'Isonzo (parent=evt_0017)
- Ma anche "Ripiegamento dal Carso al Piave" (evt_0052) e "Riorganizzazione" (evt_0053) sono figli di Caporetto
- Caporetto è austro-tedesca, non italiana — deve essere distinta dalle offensive italiane precedenti

### Monte Grappa (evt_0022)

- Data: 1917-11-13 → 1918-11-04
- Parent: evt_0020 (Battaglia di Vittorio Veneto)
- "Difesa del Grappa" (evt_0064) è figlia di Monte Grappa
- **Problema**: Comprime l'intero periodo in un intervallo indistinto senza fasi

### Monte Sabotino (evt_0063)

- Data: 1916-08-06 → 1916-08-08
- Parent: evt_0044 (Sesta battaglia dell'Isonzo)
- Corretto come gerarchia, ma la narrazione precedente ha negato l'esistenza dei claim utilizzati

### Copia locale (imi_internati.db) vs eventi_1gm.db

- imi_internati.db: 15 eventi, senza colonne V3 (stable_id, event_type, parent_event_id, etc.)
- eventi_1gm.db: 49 eventi, con colonne V3 complete
- **Problema**: La copia locale è stantia e priva della gerarchia

---

## 6. Call graph della pipeline attiva

### Endpoint attivi (app.py)

```
POST /api/v7/research          → UnifiedResearchOrchestratorV7.execute()
POST /api/v7/narrate           → UnifiedResearchOrchestratorV7._deterministic_fallback_report()
GET  /api/v7/research/{run_id} → RunContext.to_dict()
GET  /api/v7/health            → capability snapshot
GET  /api/v7/system/capabilities

POST /research/reports/{id}/conversations    → ReportConversationProviderV6
POST /research/conversations/{id}/messages   → ReportConversationProviderV6
GET  /research/conversations/{id}            → ReportConversationProviderV6

+ ~160 endpoint legacy in app.py (dossier, graph, map, search, etc.)
```

### Pipeline V7 (unified_orchestrator_v7.py)

```
execute(user_input, intent)
  → _stage_plan          (SemanticQueryPlan)
  → _stage_discover      (V7AdapterRegistry + query families)
  → _stage_fetch         (content extraction, search-page URL filter)
  → _stage_extract       (claim extraction + identity classification)
  → _stage_resolve       (IdentityResolver + homonym rejection)
  → _stage_fuse          (SourceFamilyGraph + IndependenceAssessor)
  → _stage_validate      (invariant check)
  → _stage_narrate       (NarratorV7_v2 → NarrationDraft → NarrationResult)
  → _stage_persist       (snapshot + report to DB)
```

### Endpoint legacy che NON passano per V7

- `/api/dossier/{id}` — legge direttamente da DB
- `/api/graph/*` — legge da graph_nodes/graph_edges (vuote)
- `/api/map/*` — legge da map_features (vuota)
- `/api/search` — search_all() diretto
- `/api/collegamenti/*` — legge da collegamenti (2.3M righe legacy)
- `/api/lebi/*` — ricerca diretta su LeBI

**Questi endpoint leggono dai dati legacy non quarantenati.**

---

## 7. Secret scanning

| Check | Risultato |
|-------|-----------|
| `.env` tracciato da git | NO (corretto) |
| File con path Desktop hardcoded | 5 file (`ai_client.py`, `credits.py`, `extractor.py`, `import_ocr_lettere/ocr_engine.py`, `_validate_links_ai.py`) |
| Pattern `sk-` in codice | 2 occorrenze in `test_linking_v2_master.py` (assertion di test, non chiavi reali) |
| Chiavi API in codice | Nessuna trovata |

**Azione richiesta**: Rimuovere path Desktop hardcoded, usare solo `.env` nella directory del progetto.

---

## 8. Baseline dei 9 test

### Eseguiti con V7.2 (commit ae07093)

| # | Query | Intent | Esecuzione | Risultato | Problema |
|---|-------|--------|------------|-----------|----------|
| 1 | TERUZZI Santo | PERSON | OK | Falso negativo | Non trova Archivio di Stato Bolzano (data nascita 11-03-1911) |
| 2 | VENTURI Gino | PERSON | OK | Omonimia | Non separa omonimi storici/moderni |
| 3 | CARRARO Vinicio | PERSON | OK | Omonimia | Confuso con ricercatore contemporaneo |
| 4 | CATELLANI Gaspare | PERSON | OK | Falso negativo | Non scopre decorazione/285ª SAP |
| 5 | FARINA Armando | PERSON | OK | Contaminazione | Identità composita (dati incompatibili fusi) |
| 6 | RINALDI Silvio | PERSON | OK | Contaminazione | Claim di candidato diverso nella narrazione |
| 7 | Monte Grappa | EVENT | OK | Copertura insufficiente | 3-4 righe invece di copertura stratificata |
| 8 | Monte Sabotino | EVENT | OK | Incoerenza | Nega l'esistenza dei claim utilizzati |
| 9 | Battaglie dell'Isonzo | EVENT | OK | Errore storico | 12 battaglie ma data fine all'11ª; 12ª (Caporetto) non distinta |

### Metriche baseline

| Metrica | Valore |
|---------|--------|
| execution_success | 9/9 |
| schema_validity | 9/9 |
| identity_precision | 4/9 (Teruzzi, Catellani falsi negativi; Farina, Rinaldi contaminati) |
| identity_recall | 7/9 |
| historical_fact_accuracy | 6/9 (Isonzo errato, Grappa insufficiente, Sabotino incoerente) |
| temporal_consistency | 7/9 |
| geographical_consistency | 6/9 |
| citation_validity | 8/9 |
| narrative_coverage | 5/9 (eventi troppo brevi) |
| legacy_leakage | 3/9 (collegamenti legacy in narrazione) |

---

## 9. Problemi sistemici identificati

### P1: Contaminazione WWI/WWII
- 12,759 link WWII internati → eventi WWI
- 77,265+ link WWII eventi → tabelle WWI
- Nessuna barriera temporale nel matching

### P2: Link legacy non quarantenati
- 1,539,685 event_links: tutti `status=unverified`, `rule_version=''`
- 169,184 record_links: tutti `legacy_unverified=1`, `rule_version=''`
- 2,349,417 collegamenti: senza stati o provenienza
- Endpoint legacy leggono direttamente da queste tabelle

### P3: Keyword matching senza word boundary
- `Campo` = 10,270 link (campo ≠ campo di prigionia)
- `Lager` → Prigionia WWI per WWII internati
- Sottostringhe senza tokenizzazione

### P4: Registro eventi non versionato
- Data fine "Battaglie dell'Isonzo" = 1917-09-12 (esclude Caporetto)
- Copia locale (imi_internati.db) stantia con 15 eventi vs 49
- Nessuna fonte/provenienza per le date

### P5: Identità non risolta
- Nome singolo come identificatore sufficiente per narrabilità
- Claim di candidati diversi combinati nella stessa narrazione
- Nessun IdentityCandidate esplicito

### P6: Narratore eventi insufficiente
- EVENT_LOOKUP produce 3-4 righe
- Nessuna copertura stratificata (fasi, forze, esito, conseguenze)
- Validator non controlla coerenza storica globale

### P7: Endpoint legacy bypassano la pipeline canonica
- Dossier, graph, map, search leggono direttamente da DB legacy
- Nessun adapter o feature flag

### P8: Path hardcoded e sicurezza
- 5 file con path Desktop personale
- .env non tracciato (corretto)

---

## 10. Piano di intervento

| Fase | Obiettivo | Commit |
|------|-----------|--------|
| B | Quarantena legacy + migrazioni additive | 1 |
| C | Matching, identità, registro eventi | 1 |
| D | Selezione claim, narratore eventi, validator | 1 |
| E | Adapter endpoint legacy | 1 |
| F | Test e confronto prima/dopo | 1 |

---

*Fine Phase A — Nessuna modifica dati effettuata.*
