# Audit preflight — Bootstrap Internet Archive → Supabase

Data: 2026-07-27

## Sintesi

Il prompt originale presupponeva un modello canonico `core.events` /
`core.entities` già presente su Supabase. **Non esisteva.** Gli eventi
storici (22 totali: 15 WWI, 7 WWII) vivevano solo in SQLite
(`eventi_1gm.db`, tabella `eventi_1gm`). Il resto del modello canonico
richiesto dal prompt (`archive.*`, `evidence.*`, `ops.*`, `ai.*`) **esisteva
già**, applicato ma vuoto, senza alcun worker/consumer.

## Tabella di audit

| Area | Oggetto esistente | Stato reale (verificato) | Riuso | Gap | Modifica fatta in questa sessione |
|---|---|---|---|---|---|
| Eventi canonici | nessuno (`core.*`) | **Schema `core` non esisteva** su Supabase (verificato via PostgREST: `Invalid schema: core`) | — | Bootstrap del prompt presuppone `core.events` | **Creato** `sql/002_supabase_core_events.sql` (`core.entities`, `core.events`, `core.entity_names`) + migrati i 22 eventi reali da SQLite |
| Provider Internet Archive | `source_providers/providers.py:ProviderInternetArchive` | Attivo, ma opera su ricerca federata SQLite (`federated_search`), non su Supabase | Sì, riusabile per query plan | Non scrive in `archive.*` | Non toccato in questa sessione |
| Advanced Search | `ProviderInternetArchive.search()` | Implementato, usa `advancedsearch.php`, `fl[]`, `sort=downloads desc` | Sì | Non registra provenienza in `ops.discovery_queries` | Non toccato |
| Metadata Read | `ProviderInternetArchive.get_metadata()` | Implementato (`archive.org/metadata/{id}`) | Sì | Non popola `archive.external_item_revisions` | Non toccato |
| Query planner contestuale | `ia_evaluation.build_internet_archive_query_plan` | Esiste, gestisce WWI/WWII, niente filtro `date:[1940 TO 1946]` hardcoded, fallback IT_MILITARY già vincolato a person/unit WW2 | Sì | Non genera rami per `mediatype:image/audio/movies/data` | Non toccato |
| Pipeline item→file→OCR→passaggio | `ia_pipeline.py` (881 righe) | Completa ma scrive in SQLite (`archivio_documenti`, `event_links`, `claim_service`) | Parziale | Non scrive nel modello canonico Supabase | Non toccato |
| Valutazione pertinenza | `ia_evaluation.evaluate_candidates` | Completa (conflitto, date, geografia, qualità) | Sì | — | Non toccato |
| Job queue | `ops.job_queue` (SQL) | Tabella esiste, **vuota**, nessun worker | No | Nessun consumer applicativo | Non toccato |
| `archive.external_items`/`representations`/`text_versions`/`chunks` | tabelle SQL | Esistono, **vuote** | Sì | Nessun writer applicativo collegato | Non toccato |
| `ops.discovery_queries`/`discovery_candidates` | tabelle SQL | Esistono, **vuote** | Sì | Nessun writer | Non toccato |
| `evidence.link_quarantine`/`rights_assessments` | tabelle SQL | Esistono, **vuote** | Sì | Nessun writer | Non toccato |
| Registry provider | `config/archive_providers.yml` | `internetarchive` registrato (righe 171-191) | Sì | Manca sezione `profiles.test_exhaustive` richiesta dal prompt | Non toccato |
| Config `IA_*` (rate limit, quote, profili) | — | **Nessuna** presente in `.env`/`.env.example` | No | Da introdurre | Non toccato |
| Admin UI popolamento | — | **Non esiste** pagina admin ingestion IA nel frontend | No | Da costruire | Non toccato |
| Estrazione/dedup nuovi eventi WWI/WWII | — | **Non esiste** | No | Da costruire (`research.event_candidates`) | Non toccato |
| RPC lettura dati cross-schema | `exec_sql` (solo scrittura, non ritorna righe) | Esisteva, insufficiente per letture con `RETURNING` | — | — | **Creato** `exec_sql_query` (SELECT semplici) e `exec_sql_returning` (query con CTE `INSERT...RETURNING`) |

## Verifiche materiali eseguite

- Query dirette PostgREST su Supabase (non solo lettura di file `.sql`):
  - `archive.external_items` → HTTP 200, **0 righe**
  - `ops.job_queue` → HTTP 200, **0 righe**
  - `core.events` (prima della migrazione) → HTTP 406 `Invalid schema: core`
  - Schemi esposti PostgREST: `public, graphql_public, api_public, archive, evidence, ops, legacy, ai` (⚠️ **`core` non è ancora tra questi** — vedi "Azione manuale richiesta")
- Conteggio reale eventi in `eventi_1gm.db`: **22** (15 WWI, 7 WWII), colonne canoniche già presenti (`stable_id`, `conflict`, `event_type`, `parent_event_id`, `review_status`, tutte popolate — nessun evento privo di conflitto/date/luogo)
- Nessuna directory `workers/` o `jobs/` applicativa nel repository

## Lavoro completato in questa sessione

1. **`sql/002_supabase_core_events.sql`** — migrazione additiva: schema `core` con `entities`, `events`, `entity_names`; trigger `updated_at` (riusa `archive.set_updated_at()`); RLS pattern identico a `001_supabase_historical_archive_core.sql`; RPC `exec_sql_query` ed `exec_sql_returning`.
2. **`apply_migration_002.py`** — applicatore che riusa `split_sql_statements`/`is_meaningful_statement` da `apply_migration_v2.py` (nessun parser duplicato). Eseguito: **41/41 statement OK**.
3. **`migrate_events_to_core.py`** — migrazione dati idempotente (upsert su `stable_id`/`source_id`) da `eventi_1gm.db` a `core.*`. Eseguito due volte per verificare idempotenza: stesso risultato (**22 eventi, 84 alias, 7 link parent/child**) senza duplicati.

## Azione manuale richiesta (bloccante per letture REST dirette)

Lo schema `core` **non è esposto** in Supabase Dashboard → Settings → API →
**Exposed Schemas** (come già annotato in
`docs/architecture/complete-app-architecture-post-migration.md:150` per gli
altri schemi). Finché non viene aggiunto:

- le letture/scritture dirette via PostgREST su `core.*` (es.
  `repository_layer.py`, `supabase_client.select_schema/insert_batch_schema`)
  restituiranno `406 Invalid schema`;
- le letture di verifica in questa sessione hanno usato le RPC
  `exec_sql_query`/`exec_sql_returning` (vivono in `public`, già esposto),
  che restano un percorso valido anche dopo l'esposizione del dashboard.

**Comando per l'utente**: Supabase Dashboard → Settings → API → Exposed
schemas → aggiungere `core` alla lista esistente.

## Non ancora fatto (fuori scope di questa sessione)

Tutto il resto del prompt originale (job queue reale con 20 tipi di job,
worker, sincronizzazione incrementale, admin UI, estrazione/dedup nuovi
eventi WWI/WWII con AI, claim/evidence review) **non è stato implementato**:
è un lavoro dell'ordine di settimane, non collegabile in modo credibile e
verificabile in un'unica sessione. Il passo successivo naturale, ora che
`core.events` esiste con dati reali, è collegare `ia_pipeline.py`/
`ia_evaluation.py` per scrivere in `archive.external_items` +
`archive.representations` per un evento pilota (es. `evt_0018` — Battaglia
del Carso), come test end-to-end reale prima di generalizzare a tutti i 22
eventi.
