# Real State Before — Audit 28 Luglio 2026

**Branch**: `fix/provenance-linking-v2`  
**Commit**: `56ac6183e8fa8e38565c992d3bf722c7122be254`  
**Generated**: `2026-07-28T17:39:21Z`  
**Artifact**: `artifacts/state_before.json`

---

## 1. Runtime

| Componente | Versione |
|------------|----------|
| Python | 3.11.9 |
| FastAPI | 0.104.1 |
| SQLite | 3.45.1 |
| Pydantic | 2.13.4 |
| Framework migrazioni | Nessuno (SQL script manuali) |
| Framework test | Nessuno (nessun pytest configurato) |

## 2. Database

### imi_internati.db
- **Dimensione**: 1.876.578.304 bytes (1.75 GB)
- **SHA-256**: `2662feb6eb0ac6f1...`
- **Journal mode**: WAL
- **Integrity check**: `ok`
- **Tabelle**: 75
- **Righe totali**: ~4.1M (esclusi indici FTS)

### eventi_1gm.db
- **Dimensione**: 248.549.376 bytes (237 MB)
- **SHA-256**: `f93591ba543d9cd1...`
- **Journal mode**: delete
- **Integrity check**: `ok`
- **Tabelle**: 4 (eventi_1gm, event_aliases, event_links, map_features, sqlite_sequence)

### validazioni_ai.db
- **Dimensione**: 94.208 bytes
- **SHA-256**: `cfe1efe0e308df15...`

## 3. Conteggi critici

### Tabelle principali (imi_internati.db)

| Tabella | Righe |
|---------|-------|
| `internati` | 20.465 |
| `caduti_albooro` | 342.555 |
| `caduti_cwgc` | 506.446 |
| `caduti_ministero` | 162.646 |
| `caduti_bologna` | 9.656 |
| `caduti_sardi` | 20.435 |
| `caduti_francia_ww1` | 24.279 |
| `decorati_nastroazzurro` | 279.832 |
| `decorati` | 1.286 |
| `entita` | 688.739 |
| `collegamenti` | 2.349.417 |
| `collegamenti_backup` | 4.894.390 |
| `fonti_indice` | 35.664 |
| `archivio_documenti` | 979 |
| `record_links` | 169.184 |
| `event_links` | 0 (in imi_internati.db) |
| `eventi_1gm` | 15 (in imi_internati.db) |
| `graph_nodes` | 0 |
| `graph_edges` | 0 |
| `claims` | 43 |
| `claim_evidence` | 550 |
| `entity_variants` | 299 |

### Tabelle eventi (eventi_1gm.db)

| Tabella | Righe |
|---------|-------|
| `eventi_1gm` | 49 |
| `event_aliases` | 161 |
| `event_links` | 1.539.685 |
| `map_features` | 0 |

### Relation counts by type

#### event_links (eventi_1gm.db)

| link_type | Count |
|-----------|-------|
| `soldato_decorato` | 1.262.644 |
| `soldato_caduto` | 260.903 |
| `internato_ww2` | 12.759 |
| `fonte_archivistica` | 2.310 |
| `documento` | 1.068 |
| `soldato_caduto_cwgc` | 1 |

#### record_links (imi_internati.db)

| link_type | Count |
|-----------|-------|
| `stesso_evento_luogo` | 142.594 |
| `stesso_anno_decorazione` | 11.222 |
| `fonte_personale` | 9.546 |
| `documento_evento` | 5.822 |

## 4. Discrepanze accertate

1. **eventi_1gm in imi_internati.db**: 15 righe (legacy, script `_gen_event_links.py`)
2. **eventi_1gm in eventi_1gm.db**: 49 righe (aggiornato da `add_wwi_events.py`)
3. **event_links in imi_internati.db**: 0 righe (mai popolato)
4. **event_links in eventi_1gm.db**: 1.539.685 righe (dallo script legacy)
5. **record_links**: 169.184 righe (dallo script legacy `_gen_record_links.py`)
6. **collegamenti**: 2.349.417 righe (sistema legacy originale)
7. **collegamenti_backup**: 4.894.390 righe (backup più grande della tabella attiva — possibile duplicato)

## 5. Script legacy — Diagnosi

### _gen_event_links.py (700 righe)
- **Eventi hardcoded**: 22 (non 49 del DB)
- **Mischia WW1/WW2**: Sì — "Prigionia" WW1 ha keyword "campo" che matcha internati WW2
- **Match per sottostringa**: Sì — `alias.upper() in lm_up` senza tokenizzazione
- **Break al primo evento**: Sì — `break` dopo primo match per caduti, fonti, internati
- **Skip se link esistenti**: Sì — `if existing_X == 0: ... else: skip`
- **Keyword generici**: `campo`, `Russia`, `Africa`, `Nero`, `Corno`, `Lana`
- **Confidence non calibrata**: 0.3-0.9 assegnati arbitrariamente
- **Nessuna provenienza**: No algoritmo, versione, feature, evidenza, conflitti, revisione
- **Decorati per anno**: Collega a tutti gli eventi dello stesso anno

### _gen_record_links.py (247 righe)
- **Esecuzione all'import**: Sì — codice top-level, no `main()`, no CLI
- **Cancella fonte_personale**: Sì — `DELETE FROM record_links WHERE link_type='fonte_personale'`
- **Hub arbitrario**: Sì — `hub = ids[0]` (primo soldato come centro stella)
- **LIMIT 50**: Sì — `LIMIT 50` senza ordinamento
- **Same-year come relazione**: Sì — `stesso_anno_decorazione`
- **O(N×M) scan**: Sì — `for s in soldati_names: for fid, haystack in fonti_all:`
- **Nessuna evidenza**: No feature, no algoritmo, no run, no candidate/confirmed

### _clean_bad_links.py (110 righe)
- **Namespace confusion**: Confronta `fonti_indice.id` con `collegamenti.entita_id` senza dimostrare che i namespace coincidano
- **DELETE distruttivo**: `DELETE FROM collegamenti WHERE entita_id IN (...)` e `DELETE FROM fonti_indice WHERE id IN (...)`
- **Ha dry-run**: Sì, ma `--execute --delete-links` è distruttivo senza quarantena

### _fix_gaiaschi_db.py (60 righe)
- **Modifica luogo_nascita**: `UPDATE internati SET luogo_nascita = ...`
- **Non modifica raw_text**: Il commento dice "raw_text IMMUTABLE" e non lo tocca
- **Nessun claim model**: Usa `entity_variants` ma non `claims`/`evidence_fragments`
- **Nessun evidence locator**: "Confermata Grecia" senza riferimento documentale strutturato
- **Nessuna review decision**: Imposta `review_reason` ma non crea una `review_decision` tipizzata

### _check_keys.py (32 righe)
- **Non stampa valori**: Stampa solo `SET` o `NOT_SET` — sicuro
- **Legge .env da CWD**: Sì, ma non da percorsi Desktop storici

### _find_best_candidates.py (29 righe)
- **Match solo cognome**: `LIKE '%' || LOWER(i.cognome) || '%'`
- **Nessun discriminatore**: No data nascita, luogo, matricola, reparto

## 6. Sicurezza

| Check | Risultato |
|-------|-----------|
| `.env` in git | **Non tracciato** (verificato: `git ls-files .env` → vuoto) |
| Porta 8000 hardcoded | **54 file** con riferimenti a porta 8000 |
| `exec_sql` RPC su Supabase | **Attivo** — expone SQL arbitrario via PostgREST |
| Service role key in frontend | Non verificato in questa sessione |
| Secret scan su history | Non eseguito — richiede `git log -p` su tutta la history |

## 7. Supabase

| Componente | Stato |
|------------|-------|
| Progetto | `wyqesimzxieykmyhfvqs` (eu-central-2) |
| Schema canonico | Applicato (6 schemi, 21 tabelle, RLS) |
| `archivio_documenti` | 979 righe sincronizzate |
| `eventi_1gm` | 49 righe sincronizzate |
| `event_aliases` | 161 righe sincronizzate |
| `event_links` | Sync in corso (~18%, 1.5M righe) |
| Staging | **Non esiste** — solo progetto di produzione |
| `exec_sql` RPC | Attivo e pericoloso |

## 8. Blockers

1. **No staging Supabase** — solo produzione disponibile
2. **No golden dataset** — nessun dataset etichettato per calibrazione
3. **event_links sync in corso** — 1.5M righe legacy su produzione
4. **exec_sql RPC** — espone SQL arbitrario
5. **No migration framework** — SQL script manuali, no Alembic
6. **No pytest** — nessun test suite per linking logic
7. **collegamenti_backup (4.9M)** — più grande della tabella attiva, possibile duplicato
8. **Discrepanza eventi** — 15 eventi in imi_internati.db vs 49 in eventi_1gm.db
