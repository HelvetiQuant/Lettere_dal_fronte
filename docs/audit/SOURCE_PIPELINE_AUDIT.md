# Audit: Producer/Consumer, Schema, Writer Legacy

Data: 2026-07-28
Auditor: Senior Data Engineer / Platform Engineer

## 1. Database Canonico

### Stato attuale

| Database | Ruolo | Tabelle | Righe (stimate) |
|----------|-------|---------|-----------------|
| `imi_internati.db` (SQLite) | Legacy + linking v2 | 75 tabelle | 9.5M righe |
| `eventi_1gm.db` (SQLite) | Legacy eventi WW1 | ~10 tabelle | 891K event_links |
| Supabase (PostgreSQL) | Canonico v2 (parziale) | 24 tabelle in 7 schemi | 22 eventi, 84 alias |

### Decisione

**Supabase/PostgreSQL è il database canonico v2.**
SQLite è sorgente legacy, read-only durante la transizione.

Autorità per tipo dato durante la transizione:

| Tipo dato | Autorità | Note |
|-----------|----------|------|
| Eventi canonici | `core.events` (Supabase) | 22 eventi migrati, 84 alias |
| Entità canoniche | `core.entities` (Supabase) | Solo eventi per ora |
| Fonti esterne | `archive.external_items` (Supabase) | Vuoto, da alimentare |
| Rappresentazioni | `archive.representations` (Supabase) | Vuoto |
| Claim | `evidence.claims` (Supabase) | **MANCA — da creare** |
| Evidenze | `evidence.evidence` (Supabase) | **MANCA — da creare** |
| Decisioni editoriali | `evidence.editorial_decisions` (Supabase) | **MANCA — da creare** |
| Provider registry | `archive.providers` (Supabase) | **MANCA — da creare** |
| Job queue | `ops.job_queue` (Supabase) | Esiste ma incompleta |
| Relazioni v2 | `relations` (SQLite linking v2) | Da migrare a Supabase |
| Relazioni legacy | `event_links`, `record_links`, `collegamenti` (SQLite) | Frozen, da classificare |

## 2. Writer Legacy Identificati

### 2.1 Già frozen (kill_switch.py)

| Script | Kill switch | Stato |
|--------|-------------|-------|
| `_gen_event_links.py` | `LegacyJob.EVENT_LINKS` | Frozen, `assert_frozen()` all'import |
| `_gen_record_links.py` | `LegacyJob.RECORD_LINKS` | Frozen, `assert_frozen()` all'import |

### 2.2 NON frozen — da bloccare

| Script | Tabelle scritte | Problema | Azione |
|--------|-----------------|----------|--------|
| `mass_index.py` | `fonti_indice`, `collegamenti` | Scraping massivo, match per cognome/nome, confidence arbitraria | Aggiungere a kill_switch |
| `mass_index_parallel.py` | `fonti_indice`, `collegamenti` | 7 AI in parallelo, raccolta quantitativa | Aggiungere a kill_switch |
| `import_personal_sources.py` | `entita`, `collegamenti` | Crea entità+collegamenti per nome, confidenza 0.8 fissa | Wrapper v2 o freeze |
| `import_fonti_personali.py` | `fonti_indice` | Import fonti personali | Wrapper v2 |
| `import_lettere_personali.py` | `lettere_personali` | Import lettere | Wrapper v2 |
| `external_link_service.py` | `record_links` | Crea `record_links` con match_score, cri_match, lebi_match | Wrapper v2 |
| `research_to_index.py` | `fonti_indice`, `collegamenti` | Indicizzazione ricerca → fonti | Wrapper v2 |
| `ia_pipeline.py` | `fonti_indice`, `collegamenti` | Internet Archive pipeline | Wrapper v2 |
| `search_ww1_documents.py` | `fonti_indice` | Ricerca documenti WW1 | Wrapper v2 |
| `source_locator.py` | `fonti_indice` | Locator fonti | Wrapper v2 |
| `database.py` | `collegamenti` (via `insert_*`) | Funzioni utility usate da molti moduli | Audit chiamanti |
| `sync_ww1_to_supabase.py` | Supabase `event_links` | Sync SQLite→Supabase | Valutare |

### 2.3 Writer v2 (autorizzati)

| Modulo | Tabelle | Stato |
|--------|---------|-------|
| `linking/persistence.py` | `relations`, `pipeline_runs`, `resource_registry` | Idempotente, provenance-aware |
| `backfill_canonical.py` | Supabase `archive.*`, `evidence.*` | Backfill idempotente |

## 3. Schema Gaps (Supabase)

### 3.1 Tabelle mancanti vs specifica

| Tabella richiesta | Schema Supabase | Stato |
|-------------------|-----------------|-------|
| `archive.providers` | Non esiste | **DA CREARE** — provider_code, authority_class, independence_group, rights_status, terms_url, license_uri, ecc. |
| `evidence.claims` | Non esiste | **DA CREARE** — subject_entity_id, predicate, object, claim_status, conflict_code, extraction_method, pipeline_run_id |
| `evidence.evidence` | Non esiste | **DA CREARE** — claim_id, source_item_id, representation_id, page_or_canvas, line_or_region, text_span, evidence_type, ocr_confidence, human_verified, review_status, independence_group |
| `evidence.editorial_decisions` | Non esiste | **DA CREARE** — claim_id, decision, reviewer_id, reason, decided_at, supersedes_decision_id |
| `api_public.published_claims` | Non esiste | **DA CREARE** — vista su claims con status verified/supported |
| `api_public.published_relations` | Non esiste | **DA CREARE** — vista su relations con status confirmed |

### 3.2 Tabelle esistenti ma incomplete

| Tabella | Gap | Fix richiesto |
|---------|-----|---------------|
| `ops.job_queue` | Mancano: `provider_id`, `query_payload`, `idempotency_key`, `checkpoint`, `cursor`, `pipeline_run_id`, `next_attempt_at`, `last_error_code`, `last_error_message` | ALTER TABLE ADD COLUMN |
| `archive.external_items` | Mancano: `holding_institution`, `collection_or_fonds`, `archival_signature`, `persistent_identifier`, `rights_uri`, `source_version`, `content_checksum`, `raw_metadata` | ALTER TABLE ADD COLUMN |
| `archive.representations` | Mancano: `iiif_manifest`, `canvas_id`, `page_number`, `storage_policy`, `ocr_available` (parziale) | ALTER TABLE ADD COLUMN |

### 3.3 Tabelle esistenti e adeguate

| Tabella | Note |
|---------|------|
| `archive.repositories` | Adeguata |
| `archive.collections` | Adeguata |
| `archive.external_item_revisions` | Adeguata |
| `archive.document_units` | Adeguata |
| `archive.text_versions` | Adeguata |
| `archive.passages` | Adeguata |
| `archive.chunks` | Adeguata (VECTOR skippato, serve extension) |
| `evidence.link_quarantine` | Adeguata |
| `evidence.rights_assessments` | Adeguata |
| `ops.discovery_queries` | Adeguata |
| `ops.discovery_candidates` | Adeguata |
| `ops.fetch_cache` | Adeguata |
| `ai.datasets` | Adeguata |
| `ai.dataset_versions` | Adeguata |
| `ai.dataset_items` | Adeguata |
| `ai.dataset_item_sources` | Adeguata |
| `ai.evaluation_runs` | Adeguata |
| `core.entities` | Adeguata |
| `core.events` | Adeguata |
| `core.entity_names` | Adeguata |

## 4. Provider Registry

### 4.1 Stato attuale

- `config/archive_providers.yml`: 27 provider con capabilities, rights, authority_score
- **MANCA**: `authority_class` (PRIMARY_ARCHIVAL, OFFICIAL_DERIVED, ecc.), `independence_group`, `terms_url`, `license_uri`, `holding_institution`, `personal_data_policy`, `allowed_actions`, `rate_limit_policy`, `last_policy_check_at`, `provider_version`, `enabled`

### 4.2 Provider esistenti nel registry YAML

27 provider: ussme, archiviodistato, antenati, icrc_ww1, cri_milano, europeana, tna, ddb, bundesarchiv, arolsen, memoire_des_hommes, gallica, anno, iccu, quirinale, gazzetta_ufficiale, nara, lebi, cri_trieste, archives_portal_europe, internet_archive, cimeetrincee, cwgc, familysearch, hathitrust, google_books, archivportal_d.

### 4.3 Provider da implementare (priorità specifica)

| Fase | Provider | authority_class | access_mode | Stato |
|------|----------|-----------------|-------------|-------|
| 1 | SAN LOD | PRIMARY_ARCHIVAL | OPEN_API | Non implementato |
| 1 | ASI/ICAR | PRIMARY_ARCHIVAL | OPEN_DOWNLOAD | Non implementato |
| 2 | Europeana 14-18 | AGGREGATOR | OPEN_API | Parziale (federation) |
| 2 | ICRC WW1 | PRIMARY_ARCHIVAL | METADATA_ONLY | Implementato |
| 2 | Gallica/ANNO | PRIMARY_ARCHIVAL | OPEN_DOWNLOAD | Parziale (federation) |
| 3 | Quirinale | OFFICIAL_DERIVED | OPEN_API | Non implementato |
| 3 | Gazzetta Ufficiale | OFFICIAL_DERIVED | OPEN_DOWNLOAD | Non implementato |
| 4 | NARA | PRIMARY_ARCHIVAL | OPEN_API | Parziale (federation) |
| 4 | Arolsen | PRIMARY_ARCHIVAL | TARGETED_SEARCH | Implementato (reverse-eng) |
| 4 | LeBI | OFFICIAL_DERIVED | METADATA_ONLY | Implementato |
| 4 | CRI Milano | PRIMARY_ARCHIVAL | REQUEST_REQUIRED | Implementato |
| 4 | CRI Trieste | PRIMARY_ARCHIVAL | METADATA_ONLY | Non implementato |
| 5 | Archives Portal Europe | AGGREGATOR | OPEN_API | Non implementato |
| 5 | Portale Antenati | PRIMARY_ARCHIVAL | OPEN_DOWNLOAD | Parziale (federation) |
| 5 | Internet Archive | DISCOVERY_ONLY | OPEN_DOWNLOAD | Parziale (ia_pipeline) |

## 5. Job Queue

### 5.1 Stato attuale

```sql
ops.job_queue:
  id, job_type, payload_json, priority, status,
  claimed_by, claimed_at, lease_expires_at,
  attempts, max_attempts, last_error, result_json,
  created_at, completed_at
```

### 5.2 Gap vs specifica

Mancano: `provider_id`, `query_payload` (separato da payload_json), `idempotency_key`, `checkpoint`, `cursor`, `pipeline_run_id`, `next_attempt_at`, `last_error_code`, `last_error_message`.

Stati attuali: `pending | claimed | running | completed | failed | dead_letter`
Stati richiesti: `queued | running | retry_wait | partial | succeeded | failed | cancelled`

**Nessun worker esiste.**

## 6. Sicurezza

### 6.1 `_check_keys.py`

Attualmente stampa `SET` o `NOT_SET` per ogni chiave. Non stampa valori, ma il controllo `val.startswith("sk-")` è superfluo e potenzialmente fuorviante. Da semplificare: solo `presente` / `assente` / `non valido`.

### 6.2 `.env` in `.gitignore`

Da verificare.

### 6.3 Supabase `core` exposure

`core` NON è negli Exposed Schemas di Supabase. La specifica richiede di valutare alternative più sicure prima di esporlo:
1. RPC tipizzate (già esiste `exec_sql_query`)
2. Viste in `api_public`
3. RLS con policy esplicite (già implementato)
4. Nessuna esposizione diretta delle tabelle canoniche modificabili

**Decisione: non esporre `core` direttamente. Usare viste `api_public` + RPC.**

## 7. Consumer che leggono legacy

| Consumer | Fonte legacy | Proiezione richiesta |
|----------|-------------|---------------------|
| `graph_service.py` | `event_links`, `record_links`, `collegamenti`, `external_record_links`, `menzioni` | `api_public.published_relations` |
| `rag_pipeline.py` | FTS5 su SQLite (internati, caduti, fonti_indice, ecc.) | `archive.passages` + `archive.chunks` |
| `biography.py` | SQLite diretto | `api_public.published_claims` |
| `event_research_engine.py` | SQLite diretto | `api_public.published_claims` + `archive.external_items` |
| `search_service.py` | FTS5 su SQLite | Da migrare a Supabase tsvector |
| Frontend (index.html) | API legacy | API v2 |

## 8. Riepilogo Azioni Immediate

1. **Creare `sql/003_source_pipeline_schema.sql`**: providers, claims, evidence, editorial_decisions, published_claims/relations views, job_queue ALTER
2. **Estendere `kill_switch.py`**: aggiungere `MASS_INDEX`, `MASS_INDEX_PARALLEL`, `IMPORT_PERSONAL_SOURCES`, `IA_PIPELINE`
3. **Fixare `_check_keys.py`**: solo presenza/assenza
4. **Creare `source_pipeline/provider_contract.py`**: interfaccia `SourceProvider` con capabilities, policy, search, fetch_metadata, fetch_representations, normalize, checkpoint
5. **Creare `source_pipeline/worker.py`**: worker riprendibile per `ops.job_queue`
6. **Aggiornare `config/archive_providers.yml`**: aggiungere authority_class, independence_group, terms_url, ecc.
