# Runbook: Esposizione schema `core` su Supabase PostgREST

## Problema

Lo schema `core` (entità ed eventi canonici) esiste in PostgreSQL ma **non è esposto** in PostgREST. Questo blocca tutte le operazioni REST su `core.entities` e `core.events` tramite il client ordinario.

## Sintomi

- `select_schema("core", "entities")` ritorna lista vuota (HTTP 200 ma nessun dato)
- `table_exists_schema("core", "entities")` ritorna `False`
- `insert_batch_schema("core", "entities", ...)` fallisce o non ha effetto
- Sync outbox per `discovered_entities` → `core.entities` non funziona

## Root cause

PostgREST serve solo gli schemi elencati in **Supabase Dashboard > Settings > API > Exposed Schemas**. Lo schema `core` non è in quella lista.

## Fix richiesti

### 1. Codice (già fatto)

- `supabase_client.py:247` — `"core"` aggiunto a `VALID_SCHEMAS`
- `sql/004_expose_core_schema.sql` — grants e RLS verificati, tabella `core.entity_mapping` creata

### 2. Dashboard Supabase (MANUALE — bloccante)

1. Accedere a https://supabase.com/dashboard/project/wyqesimzxieykmyhfvqs
2. **Settings** → **API**
3. Scorrere fino a **Exposed Schemas**
4. Aggiungere `core` alla lista (accanto a `public`, `archive`, `evidence`, `ops`, `ai`, `api_public`, `legacy`)
5. **Save**
6. Attendere qualche secondo per il reload della schema cache di PostgREST

### 3. Verifica

Eseguire dopo il passaggio Dashboard:

```python
from supabase_client import select_schema, table_exists_schema

# Verifica lettura
exists = table_exists_schema("core", "entities")
print(f"core.entities accessible: {exists}")

# Verifica SELECT
rows = select_schema("core", "entities", limit=1)
print(f"Rows: {len(rows)}")
```

Oppure via curl:

```bash
curl -s "https://wyqesimzxieykmyhfvqs.supabase.co/rest/v1/entities?select=count&limit=0" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Accept-Profile: core"
```

### 4. Sicurezza

- `anon` e `authenticated` hanno solo `SELECT` su `core.entities` ed `core.events`
- `service_role` ha accesso completo
- RLS è attiva su tutte le tabelle `core.*`
- Policy esistenti:
  - `core.entities`: public read, service write/update
  - `core.events`: public read solo `confirmed`/`probable`, service write/update
  - `core.entity_mapping`: public read, service all

## Stato

- [x] Codice aggiornato (`VALID_SCHEMAS`)
- [x] Migrazione SQL creata (`004_expose_core_schema.sql`)
- [ ] **Dashboard: aggiungere `core` agli Exposed Schemas** ← BLOCCANTE
- [ ] Verifica post-dashboard
