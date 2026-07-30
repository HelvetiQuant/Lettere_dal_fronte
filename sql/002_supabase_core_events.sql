-- ============================================================
-- 002_supabase_core_events.sql
-- Schema canonico "core" — entità ed eventi storici
-- ============================================================
-- Versione: 1.0.0
-- Data: 2026-07-27
--
-- PRINCIPI:
-- - Additivo e idempotente (CREATE IF NOT EXISTS)
-- - Non cancella né rinomina tabelle legacy (eventi_1gm resta la fonte SQLite)
-- - Riusa archive.set_updated_at() già definita in 001_supabase_historical_archive_core.sql
-- - RLS su ogni tabella, stesso pattern di 001
-- ============================================================

-- ─── STEP 0: Schema ────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS core;

-- ─── STEP 1: core.entities ─────────────────────────────────────────────────
-- Entità generiche (per ora solo entity_type='event', estendibile a
-- person/place/unit/organization in migrazioni additive future)

CREATE TABLE IF NOT EXISTS core.entities (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'event',
    canonical_name TEXT NOT NULL,
    created_by_kind TEXT NOT NULL DEFAULT 'migration',
    verification_status TEXT NOT NULL DEFAULT 'candidate',
    confidence REAL DEFAULT 0.5,
    source_system TEXT,
    source_table TEXT,
    source_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_core_entities_type ON core.entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_core_entities_source ON core.entities(source_system, source_id);

-- ─── STEP 2: core.events ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS core.events (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES core.entities(id) ON DELETE CASCADE,
    stable_id TEXT UNIQUE NOT NULL,
    preferred_name TEXT NOT NULL,
    conflict_code TEXT,
    event_type TEXT NOT NULL DEFAULT 'battaglia',
    parent_event_id BIGINT REFERENCES core.events(id) ON DELETE SET NULL,
    date_start DATE,
    date_end DATE,
    temporal_precision TEXT DEFAULT 'day',
    general_location TEXT,
    localities JSONB DEFAULT '[]',
    subjects JSONB DEFAULT '[]',
    units JSONB DEFAULT '[]',
    description TEXT,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    narrative_version TEXT,
    narrative_updated_at TIMESTAMPTZ,
    source_system TEXT NOT NULL DEFAULT 'sqlite:eventi_1gm',
    source_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_system, source_id)
);

CREATE INDEX IF NOT EXISTS idx_core_events_conflict ON core.events(conflict_code);
CREATE INDEX IF NOT EXISTS idx_core_events_parent ON core.events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_core_events_review ON core.events(review_status);

-- ─── STEP 3: core.entity_names ─────────────────────────────────────────────
-- Alias, traduzioni, varianti — separati dal nome canonico.

CREATE TABLE IF NOT EXISTS core.entity_names (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES core.entities(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    name_type TEXT NOT NULL DEFAULT 'alias',
    language_code TEXT,
    provenance TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_id, name)
);

CREATE INDEX IF NOT EXISTS idx_core_entity_names_entity ON core.entity_names(entity_id);
CREATE INDEX IF NOT EXISTS idx_core_entity_names_name ON core.entity_names(name);

-- ─── STEP 4: trigger updated_at (riusa archive.set_updated_at) ─────────────

DROP TRIGGER IF EXISTS trg_updated_core_entities ON core.entities;
CREATE TRIGGER trg_updated_core_entities BEFORE UPDATE ON core.entities
    FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at();

DROP TRIGGER IF EXISTS trg_updated_core_events ON core.events;
CREATE TRIGGER trg_updated_core_events BEFORE UPDATE ON core.events
    FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at();

-- ─── STEP 5: RLS (stesso pattern di 001) ───────────────────────────────────

ALTER TABLE core.entities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_read_entities" ON core.entities;
CREATE POLICY "public_read_entities" ON core.entities FOR SELECT USING (true);
DROP POLICY IF EXISTS "service_write_entities" ON core.entities;
CREATE POLICY "service_write_entities" ON core.entities FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
DROP POLICY IF EXISTS "service_update_entities" ON core.entities;
CREATE POLICY "service_update_entities" ON core.entities FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE core.events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_read_events" ON core.events;
CREATE POLICY "public_read_events" ON core.events FOR SELECT USING (review_status IN ('confirmed', 'probable') OR current_setting('request.jwt.claim.role', true) = 'service_role');
DROP POLICY IF EXISTS "service_write_events" ON core.events;
CREATE POLICY "service_write_events" ON core.events FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
DROP POLICY IF EXISTS "service_update_events" ON core.events;
CREATE POLICY "service_update_events" ON core.events FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE core.entity_names ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_read_entity_names" ON core.entity_names;
CREATE POLICY "public_read_entity_names" ON core.entity_names FOR SELECT USING (true);
DROP POLICY IF EXISTS "service_write_entity_names" ON core.entity_names;
CREATE POLICY "service_write_entity_names" ON core.entity_names FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

-- ─── STEP 6: Grants ─────────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA core TO anon, authenticated, service_role;
GRANT SELECT ON core.entities, core.events, core.entity_names TO anon, authenticated;
GRANT ALL ON core.entities, core.events, core.entity_names TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT ALL ON TABLES TO service_role;

-- ─── STEP 7: RPC di lettura (necessaria perché exec_sql non ritorna righe) ──
-- Nota operativa: PostgREST serve solo gli schemi elencati in
-- Supabase Dashboard > Settings > API > Exposed Schemas. "core" NON è
-- ancora in quella lista (verificato: schemi esposti = public,
-- graphql_public, api_public, archive, evidence, ops, legacy, ai).
-- Questa funzione, vivendo in "public" (già esposto), permette letture
-- verificabili su core.* anche prima che l'esposizione dashboard sia fatta.
-- Va aggiunta comunque "core" alle Exposed Schemas per usare select_schema()
-- / insert_batch_schema() di supabase_client.py in futuro.

CREATE OR REPLACE FUNCTION exec_sql_query(query text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    result json;
BEGIN
    EXECUTE format('SELECT COALESCE(json_agg(t), ''[]''::json) FROM (%s) t', query) INTO result;
    RETURN result;
EXCEPTION WHEN OTHERS THEN
    RETURN json_build_object('__error__', true, 'error', SQLERRM, 'detail', SQLSTATE);
END;
$$;

-- ─── STEP 8: RPC per query con CTE data-modifying (INSERT/UPDATE...RETURNING) ──
-- Postgres richiede che un WITH contenente una data-modifying statement sia
-- al livello top della query eseguita: exec_sql_query non va bene perché la
-- avvolge in "SELECT ... FROM (query) t". Questa RPC esegue la query così
-- com'è: il chiamante deve terminarla con un SELECT json_agg(row_to_json(x))
-- FROM x per ottenere righe indietro.

CREATE OR REPLACE FUNCTION exec_sql_returning(query text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    result json;
BEGIN
    EXECUTE query INTO result;
    RETURN result;
EXCEPTION WHEN OTHERS THEN
    RETURN json_build_object('__error__', true, 'error', SQLERRM, 'detail', SQLSTATE);
END;
$$;
