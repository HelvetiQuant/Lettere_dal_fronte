-- ============================================================
-- 004_expose_core_schema.sql
-- Esposizione controllata dello schema core per PostgREST
-- ============================================================
-- Versione: 1.0.0
-- Data: 2026-07-31
--
-- PRINCIPI:
-- - Idempotente (GRANT IF EXISTS equivalenti)
-- - Non amplia l'accesso anonimo alle tabelle protette
-- - Mantiene RLS esistente
-- - Service role ha accesso completo, anon/authenticated solo SELECT
--
-- IMPORTANTE: Questo SQL garantisce che i grants siano corretti.
-- L'esposizione effettiva di PostgREST richiede anche l'aggiunta
-- di "core" alla lista "Exposed Schemas" in:
--   Supabase Dashboard > Settings > API > Exposed Schemas
-- Vedi runbook: docs/runbook/RUNBOOK_SUPABASE_CORE_SCHEMA.md
-- ============================================================

-- ─── STEP 1: Grants sul schema ──────────────────────────────────────────────

GRANT USAGE ON SCHEMA core TO anon, authenticated, service_role;

-- ─── STEP 2: Grants sulle tabelle esistenti ─────────────────────────────────
-- (Idempotente: se le tabelle non esistono ancora, il GRANT fallisce
--  silenziosamente. Eseguire dopo 002_supabase_core_events.sql)

DO $$
BEGIN
    -- core.entities
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='entities') THEN
        GRANT SELECT ON core.entities TO anon, authenticated;
        GRANT ALL ON core.entities TO service_role;
    END IF;

    -- core.events
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='events') THEN
        GRANT SELECT ON core.events TO anon, authenticated;
        GRANT ALL ON core.events TO service_role;
    END IF;

    -- core.entity_names
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='entity_names') THEN
        GRANT SELECT ON core.entity_names TO anon, authenticated;
        GRANT ALL ON core.entity_names TO service_role;
    END IF;

    -- core.entity_mapping (tabella di mapping locale-remoto, se esiste)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='entity_mapping') THEN
        GRANT SELECT ON core.entity_mapping TO anon, authenticated;
        GRANT ALL ON core.entity_mapping TO service_role;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Grant step: %', SQLERRM;
END
$$;

-- ─── STEP 3: Sequences ──────────────────────────────────────────────────────

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO service_role;

-- ─── STEP 4: Default privileges per future tabelle ──────────────────────────

ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT ALL ON TABLES TO service_role;

-- ─── STEP 5: Verifica RLS attiva ────────────────────────────────────────────
-- (Non altera le policy esistenti, solo verifica)

DO $$
DECLARE
    rls_entities TEXT;
    rls_events TEXT;
BEGIN
    SELECT relrowsecurity::TEXT INTO rls_entities
    FROM pg_class WHERE relname='entities' AND relnamespace='core'::regschema;
    IF rls_entities = 'false' THEN
        RAISE WARNING 'RLS non attiva su core.entities — abilitare manualmente';
    END IF;

    SELECT relrowsecurity::TEXT INTO rls_events
    FROM pg_class WHERE relname='events' AND relnamespace='core'::regschema;
    IF rls_events = 'false' THEN
        RAISE WARNING 'RLS non attiva su core.events — abilitare manualmente';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'RLS check: %', SQLERRM;
END
$$;

-- ─── STEP 6: Tabella mapping locale → canonico ──────────────────────────────
-- Permette di mappare ID locali (SQLite) a ID canonici (Supabase core.entities)
-- senza duplicare entità.

CREATE TABLE IF NOT EXISTS core.entity_mapping (
    id BIGSERIAL PRIMARY KEY,
    local_source_system TEXT NOT NULL,
    local_table TEXT NOT NULL,
    local_id TEXT NOT NULL,
    canonical_entity_id BIGINT NOT NULL REFERENCES core.entities(id) ON DELETE CASCADE,
    mapping_confidence REAL DEFAULT 1.0,
    mapping_method TEXT DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(local_source_system, local_table, local_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_mapping_local
    ON core.entity_mapping(local_source_system, local_table, local_id);
CREATE INDEX IF NOT EXISTS idx_entity_mapping_canonical
    ON core.entity_mapping(canonical_entity_id);

ALTER TABLE core.entity_mapping ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_all_entity_mapping" ON core.entity_mapping;
CREATE POLICY "service_all_entity_mapping" ON core.entity_mapping
    FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');
DROP POLICY IF EXISTS "public_read_entity_mapping" ON core.entity_mapping;
CREATE POLICY "public_read_entity_mapping" ON core.entity_mapping
    FOR SELECT USING (true);

GRANT SELECT ON core.entity_mapping TO anon, authenticated;
GRANT ALL ON core.entity_mapping TO service_role;
GRANT USAGE, SELECT ON SEQUENCE core.entity_mapping_id_seq TO service_role;
