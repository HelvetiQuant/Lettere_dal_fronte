# CHANGELOG — Sessione 28 Luglio 2026

## Modifiche applicate

### 1. Ricerca documenti WW1 per eventi italiani
**File:** `search_ww1_documents.py` (nuovo, 274 righe)

- Script di ricerca federata per documenti archivistici su 49 eventi WW1 italiani
- 5 provider interrogati: Internet Archive, Europeana, Library of Congress, Wikimedia Commons, Gallica BnF
- Query mirate per evento (keyword + alias + luogo)
- 700+ documenti recuperati e inseriti in `archivio_documenti`
- 1000+ link documento-evento creati via keyword matching
- Coverage eventi: da 18 a 47 eventi con documenti collegati

### 2. Riclassificazione Internet Archive come fonte archivistica
**File:** `event_evidence_pipeline.py`, `source_providers/providers.py`

- Internet Archive: `source_type="primaria"`, `authority="archivio"` (non più web generica)
- Rimozione di Internet Culturale come provider (fonte non archivistica)
- Verificato con script `_verify_sources.py`

### 3. Script di verifica e diagnosi
**File:** `_doc_status.py`, `_check_keywords.py`, `_find_doc_matches.py`, `_verify_sources.py`

- `_doc_status.py`: conta documenti per evento, identifica eventi senza link
- `_check_keywords.py`: stampa keyword e alias per eventi senza documenti
- `_find_doc_matches.py`: trova nuovi match documento-evento via keyword search
- `_verify_sources.py`: verifica classificazione fonti (source_type, authority)

### 4. Nuovo progetto Supabase configurato
**File:** `.env`

- Vecchio progetto `vldhrjbkduquhzyyljbr` non più attivo (DNS: non-existent domain)
- Nuovo progetto: `wyqesimzxieykmyhfvqs` (region: eu-central-2, Zurich)
- Chiavi aggiornate: formato `sb_publishable` / `sb_secret`
- Connettività verificata: `health_check()` → `{'ok': True, 'status': 200}`

### 5. Schema canonico Supabase applicato
**File:** `_apply_canonical_schema.py` (nuovo), `sql/001_supabase_historical_archive_core.sql`

- Script che divide l'SQL in statement singoli (rispettando blocchi `$$`)
- Applicato al nuovo progetto Supabase:
  - 6 schemi creati: `archive`, `evidence`, `ops`, `ai`, `api_public`, `legacy`
  - 21 tabelle canoniche create (repositories, collections, external_items, representations, document_units, text_versions, passages, chunks, link_quarantine, rights_assessments, discovery_queries, discovery_candidates, job_queue, fetch_cache, datasets, dataset_versions, dataset_items, dataset_item_sources, evaluation_runs)
  - 40+ indici creati
  - RLS policies applicate su ogni tabella
  - Trigger `updated_at` automatico
  - Funzioni utility: `generate_stable_id()`, `content_hash()`
  - Estensione `pgcrypto` abilitata
  - `VECTOR(1536)` skippata (richiede estensione `vector` da abilitare nel dashboard)
- Risultato: 61 OK, 34 idempotenti (policy already exists), 1 skip

### 6. Sincronizzazione documenti su Supabase
**File:** `sync_ww1_to_supabase.py` (nuovo, 196 righe)

- Crea tabelle `archivio_documenti` ed `event_links` su Supabase (DDL)
- Upsert batch di 500 righe via PostgREST API
- Rate limiting 0.5s tra batch
- `on_conflict="merge"` per archivio_documenti (upsert idempotente)
- `on_conflict="ignore"` per event_links (no duplicati)
- **archivio_documenti**: 979 righe sincronizzate ✅
- **event_links**: 1,539,685 righe in corso (sync in background)

### 7. Sincronizzazione eventi su Supabase
**File:** `sync_events_to_supabase.py` (nuovo, 130 righe)

- Crea tabelle `eventi_1gm`, `event_aliases`, `map_features` su Supabase
- Sync da SQLite `eventi_1gm.db` a Supabase
- **eventi_1gm**: 49 righe sincronizzate ✅
- **event_aliases**: 161 righe sincronizzate ✅
- **map_features**: 0 righe (tabella vuota) ✅

### 8. Documento di architettura completa
**File:** `docs/ARCHITETTURA_COMPLETA.md` (nuovo, 860+ righe)

- Architettura tecnica completa per AI Architect
- 14 sezioni: visione, topologia DB, backend, frontend, pipeline dati, infrastruttura Supabase, sicurezza, mappe, configurazione, flusso end-to-end, inventory file, diagramma, stato sync, roadmap
- Stack: Python 3.11 + FastAPI + SQLite + Supabase PostgreSQL + React 19 + TypeScript 6
- 27 provider federati, 163+ endpoint API, 75 tabelle SQLite, 21 tabelle canoniche Supabase
- Diagramma architetturale ASCII con tutti i layer

## Stato Supabase — 28 Luglio 2026

| Componente | Stato |
|------------|-------|
| Progetto `wyqesimzxieykmyhfvqs` | ✅ Attivo |
| Schema canonico (6 schemi, 21 tabelle) | ✅ Applicato |
| RLS policies | ✅ Applicate |
| `pgcrypto` extension | ✅ Abilitata |
| `vector` extension | ⏳ Da abilitare nel dashboard |
| `archivio_documenti` sync | ✅ 979 righe |
| `eventi_1gm` sync | ✅ 49 righe |
| `event_aliases` sync | ✅ 161 righe |
| `event_links` sync | ⏳ In corso (1.5M righe, ~18%) |
| Backfill canonico | ❌ Da eseguire |

## File creati/modificati

| File | Azione | Righe |
|------|--------|-------|
| `search_ww1_documents.py` | Nuovo | 274 |
| `sync_ww1_to_supabase.py` | Nuovo | 196 |
| `sync_events_to_supabase.py` | Nuovo | 130 |
| `_apply_canonical_schema.py` | Nuovo | 95 |
| `_doc_status.py` | Nuovo | 72 |
| `_check_keywords.py` | Nuovo | 16 |
| `_find_doc_matches.py` | Nuovo | 46 |
| `docs/ARCHITETTURA_COMPLETA.md` | Nuovo | 860+ |
| `.env` | Modificato | URL + chiavi Supabase aggiornate |
