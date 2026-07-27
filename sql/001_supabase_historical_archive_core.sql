-- ============================================================
-- 001_supabase_historical_archive_core.sql
-- Archivio Documentale Canonico — Schema Supabase/PostgreSQL
-- ============================================================
-- Versione: 1.0.0
-- Data: 2026-07-26
-- 
-- PRINCIPI:
-- - Additivo e idempotente (CREATE IF NOT EXISTS, ALTER ADD COLUMN)
-- - Non cancella né rinomina tabelle legacy
-- - Schemi separati: archive, evidence, ops, ai, api_public
-- - RLS su ogni tabella
-- - ALTER DEFAULT PRIVILEGES per sicurezza
-- ============================================================

-- ─── STEP 0: Schemi ─────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS archive;
CREATE SCHEMA IF NOT EXISTS evidence;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS api_public;
CREATE SCHEMA IF NOT EXISTS legacy;

-- ─── STEP 1: Funzioni utility ───────────────────────────────────────────────

-- Funzione per generare stable_id deterministico
CREATE OR REPLACE FUNCTION archive.generate_stable_id(
    p_namespace TEXT,
    p_external_id TEXT,
    p_provider TEXT DEFAULT NULL
) RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    raw TEXT;
BEGIN
    raw := COALESCE(p_namespace, '') || ':' || COALESCE(p_external_id, '');
    IF p_provider IS NOT NULL THEN
        raw := raw || ':' || p_provider;
    END IF;
    RETURN 'sha256:' || encode(digest(raw::bytea, 'sha256'), 'hex');
END;
$$;

-- Funzione per hash contenuto testuale
CREATE OR REPLACE FUNCTION archive.content_hash(p_text TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN 'sha256:' || encode(digest(p_text::bytea, 'sha256'), 'hex');
END;
$$;

-- ─── STEP 2: archive.repositories ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.repositories (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    institution_type TEXT NOT NULL DEFAULT 'archive',
    country TEXT,
    city TEXT,
    website_url TEXT,
    authority_uri TEXT,
    authority_score REAL DEFAULT 0.5,
    languages TEXT[] DEFAULT '{}',
    access_policy_default TEXT DEFAULT 'METADATA_ONLY',
    terms_of_use_url TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    notes TEXT,
    version TEXT DEFAULT '1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 3: archive.collections ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.collections (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    repository_id BIGINT REFERENCES archive.repositories(id) ON DELETE CASCADE,
    parent_collection_id BIGINT REFERENCES archive.collections(id) ON DELETE SET NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    collection_type TEXT NOT NULL DEFAULT 'fondo',
    date_range_start TEXT,
    date_range_end TEXT,
    extent TEXT,
    language TEXT,
    historical_period TEXT,
    geographic_area TEXT,
    access_status TEXT DEFAULT 'active',
    provider_code TEXT,
    raw_metadata_json JSONB,
    metadata_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, external_id)
);

-- ─── STEP 4: archive.external_items ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.external_items (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    repository_id BIGINT REFERENCES archive.repositories(id) ON DELETE SET NULL,
    collection_id BIGINT REFERENCES archive.collections(id) ON DELETE SET NULL,
    provider_code TEXT NOT NULL,
    external_id TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'document',
    title TEXT,
    description TEXT,
    date_text TEXT,
    date_from DATE,
    date_to DATE,
    language TEXT,
    reference_code TEXT,
    canonical_url TEXT NOT NULL,
    parent_external_id TEXT,
    access_status TEXT DEFAULT 'active',
    review_status TEXT DEFAULT 'candidate',
    metadata_hash TEXT,
    http_status INTEGER,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider_code, external_id)
);

-- ─── STEP 5: archive.external_item_revisions ────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.external_item_revisions (
    id BIGSERIAL PRIMARY KEY,
    external_item_id BIGINT NOT NULL REFERENCES archive.external_items(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    raw_metadata_json JSONB NOT NULL,
    metadata_hash TEXT NOT NULL,
    etag TEXT,
    last_modified TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fetched_by TEXT DEFAULT 'system',
    UNIQUE(external_item_id, revision_number)
);

-- ─── STEP 6: archive.representations ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.representations (
    id BIGSERIAL PRIMARY KEY,
    external_item_id BIGINT NOT NULL REFERENCES archive.external_items(id) ON DELETE CASCADE,
    representation_role TEXT NOT NULL DEFAULT 'original',
    -- original | derivative | thumbnail | ocr_provider | ocr_local | transcription | normalized | translation
    format TEXT NOT NULL,
    -- pdf | jpeg | tiff | hocr | alto | text | json | xml
    file_url TEXT,
    bucket_path TEXT,
    file_size BIGINT,
    sha256 TEXT,
    etag TEXT,
    last_modified TIMESTAMPTZ,
    page_count INTEGER,
    has_ocr BOOLEAN DEFAULT FALSE,
    publicly_viewable BOOLEAN DEFAULT FALSE,
    public_download_allowed BOOLEAN DEFAULT FALSE,
    authorization_required BOOLEAN DEFAULT FALSE,
    rights_statement TEXT,
    credit_line TEXT,
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 7: archive.document_units ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.document_units (
    id BIGSERIAL PRIMARY KEY,
    external_item_id BIGINT NOT NULL REFERENCES archive.external_items(id) ON DELETE CASCADE,
    representation_id BIGINT REFERENCES archive.representations(id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL DEFAULT 'page',
    -- page | leaf | canvas | frame | segment
    unit_number INTEGER NOT NULL,
    unit_label TEXT,
    iiif_canvas_uri TEXT,
    image_url TEXT,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(representation_id, unit_number)
);

-- ─── STEP 8: archive.text_versions ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.text_versions (
    id BIGSERIAL PRIMARY KEY,
    external_item_id BIGINT NOT NULL REFERENCES archive.external_items(id) ON DELETE CASCADE,
    representation_id BIGINT REFERENCES archive.representations(id) ON DELETE CASCADE,
    document_unit_id BIGINT REFERENCES archive.document_units(id) ON DELETE CASCADE,
    text_role TEXT NOT NULL DEFAULT 'ocr_provider',
    -- ocr_provider | ocr_local | transcription | normalized | translation
    language TEXT,
    text_content TEXT,
    content_hash TEXT,
    ocr_confidence REAL,
    model_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 9: archive.passages ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.passages (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    text_version_id BIGINT NOT NULL REFERENCES archive.text_versions(id) ON DELETE CASCADE,
    document_unit_id BIGINT REFERENCES archive.document_units(id) ON DELETE SET NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    passage_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    language TEXT,
    locator_json JSONB,
    -- {page, x0, y0, x1, y1, source: "hocr"|"djvu"|"manual"}
    created_by TEXT DEFAULT 'system',
    review_status TEXT DEFAULT 'candidate',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 10: archive.chunks (RAG) ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archive.chunks (
    id BIGSERIAL PRIMARY KEY,
    text_version_id BIGINT NOT NULL REFERENCES archive.text_versions(id) ON DELETE CASCADE,
    passage_id BIGINT REFERENCES archive.passages(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding VECTOR(1536),
    embedding_model TEXT,
    embedding_version TEXT,
    token_count INTEGER,
    chunk_strategy TEXT DEFAULT 'fixed_512',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(text_version_id, chunk_index)
);

-- ─── STEP 11: evidence.link_quarantine ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS evidence.link_quarantine (
    id BIGSERIAL PRIMARY KEY,
    source_table TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    target_table TEXT NOT NULL,
    target_id BIGINT NOT NULL,
    link_type TEXT NOT NULL,
    raw_data_json JSONB,
    algorithm TEXT,
    algorithm_version TEXT,
    quarantine_reason TEXT NOT NULL,
    quarantine_status TEXT DEFAULT 'pending',
    -- pending | reviewed_accepted | reviewed_rejected | superseded
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_table, source_id, target_table, target_id, link_type)
);

-- ─── STEP 12: evidence.rights_assessments ───────────────────────────────────

CREATE TABLE IF NOT EXISTS evidence.rights_assessments (
    id BIGSERIAL PRIMARY KEY,
    external_item_id BIGINT REFERENCES archive.external_items(id) ON DELETE CASCADE,
    representation_id BIGINT REFERENCES archive.representations(id) ON DELETE CASCADE,
    assessment_version INTEGER NOT NULL DEFAULT 1,
    metadata_access TEXT NOT NULL DEFAULT 'UNKNOWN',
    content_access TEXT NOT NULL DEFAULT 'UNKNOWN',
    download_allowed TEXT NOT NULL DEFAULT 'UNKNOWN',
    training_allowed TEXT NOT NULL DEFAULT 'UNKNOWN',
    redistribution_allowed TEXT NOT NULL DEFAULT 'UNKNOWN',
    commercial_use_allowed TEXT NOT NULL DEFAULT 'UNKNOWN',
    attribution_required TEXT NOT NULL DEFAULT 'UNKNOWN',
    license_url TEXT,
    rights_statement TEXT,
    assessment_method TEXT,
    assessed_by TEXT DEFAULT 'system',
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT,
    UNIQUE(external_item_id, assessment_version)
);

-- ─── STEP 13: ops.discovery_queries ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ops.discovery_queries (
    id BIGSERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    query_language TEXT DEFAULT 'it',
    event_context_json JSONB,
    -- {event_name, conflict, start_date, end_date, places, keywords, subject_type}
    query_plan_json JSONB,
    -- {strategies: [{name, query, filters}], plan_version}
    provider_code TEXT,
    cache_key TEXT UNIQUE,
    result_count INTEGER DEFAULT 0,
    execution_ms INTEGER,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 14: ops.discovery_candidates ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS ops.discovery_candidates (
    id BIGSERIAL PRIMARY KEY,
    discovery_query_id BIGINT REFERENCES ops.discovery_queries(id) ON DELETE CASCADE,
    external_item_id BIGINT REFERENCES archive.external_items(id) ON DELETE SET NULL,
    provider_code TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    snippet TEXT,
    canonical_url TEXT,
    discovery_score REAL DEFAULT 0.0,
    relevance_score REAL DEFAULT 0.0,
    discovery_strategy TEXT,
    -- keyword | temporal | geographic | contemporary | contextual | fallback
    decision TEXT DEFAULT 'pending',
    -- pending | accepted | rejected | needs_review
    decision_reason TEXT,
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(discovery_query_id, provider_code, external_id)
);

-- ─── STEP 15: ops.job_queue ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ops.job_queue (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    -- discovery | fetch | ocr | index | embed | backfill | export
    payload_json JSONB NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'pending',
    -- pending | claimed | running | completed | failed | dead_letter
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- ─── STEP 16: ops.fetch_cache ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ops.fetch_cache (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    method TEXT DEFAULT 'GET',
    etag TEXT,
    last_modified TIMESTAMPTZ,
    cache_key TEXT UNIQUE,
    response_status INTEGER,
    response_body BYTEA,
    response_headers_json JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    ttl_days INTEGER DEFAULT 120
);

-- ─── STEP 17: ai.datasets ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai.datasets (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    dataset_type TEXT NOT NULL DEFAULT 'instruction',
    -- instruction | conversational | extraction | classification
    source_providers TEXT[] DEFAULT '{}',
    license TEXT,
    license_url TEXT,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 18: ai.dataset_versions ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai.dataset_versions (
    id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NOT NULL REFERENCES ai.datasets(id) ON DELETE CASCADE,
    version_number TEXT NOT NULL,
    version_label TEXT,
    freeze_hash TEXT NOT NULL,
    freeze_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    item_count INTEGER NOT NULL DEFAULT 0,
    split_policy_json JSONB,
    -- {train: 0.8, val: 0.1, test: 0.1, method: "random"|"temporal"|"by_entity"}
    anti_leakage_notes TEXT,
    immutable BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(dataset_id, version_number)
);

-- ─── STEP 19: ai.dataset_items ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai.dataset_items (
    id BIGSERIAL PRIMARY KEY,
    dataset_version_id BIGINT NOT NULL REFERENCES ai.dataset_versions(id) ON DELETE CASCADE,
    item_index INTEGER NOT NULL,
    split_tag TEXT NOT NULL DEFAULT 'train',
    -- train | val | test
    content_json JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(dataset_version_id, item_index)
);

-- ─── STEP 20: ai.dataset_item_sources ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai.dataset_item_sources (
    id BIGSERIAL PRIMARY KEY,
    dataset_item_id BIGINT NOT NULL REFERENCES ai.dataset_items(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    -- passage | claim | entity | external_item | text_version
    source_id BIGINT,
    source_table TEXT,
    provenance_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── STEP 21: ai.evaluation_runs ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai.evaluation_runs (
    id BIGSERIAL PRIMARY KEY,
    dataset_version_id BIGINT REFERENCES ai.dataset_versions(id) ON DELETE SET NULL,
    model_identifier TEXT NOT NULL,
    model_version TEXT,
    eval_type TEXT NOT NULL DEFAULT 'auto',
    metrics_json JSONB,
    -- {loss, perplexity, bleu, rouge, exact_match, f1}
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ════════════════════════════════════════════════════════════════════════════
-- INDICI
-- ════════════════════════════════════════════════════════════════════════════

-- archive.repositories
CREATE INDEX IF NOT EXISTS idx_repo_country ON archive.repositories(country);
CREATE INDEX IF NOT EXISTS idx_repo_type ON archive.repositories(institution_type);

-- archive.collections
CREATE INDEX IF NOT EXISTS idx_coll_repo ON archive.collections(repository_id);
CREATE INDEX IF NOT EXISTS idx_coll_parent ON archive.collections(parent_collection_id);
CREATE INDEX IF NOT EXISTS idx_coll_provider ON archive.collections(provider_code);

-- archive.external_items
CREATE INDEX IF NOT EXISTS idx_ei_provider ON archive.external_items(provider_code);
CREATE INDEX IF NOT EXISTS idx_ei_collection ON archive.external_items(collection_id);
CREATE INDEX IF NOT EXISTS idx_ei_hash ON archive.external_items(metadata_hash);
CREATE INDEX IF NOT EXISTS idx_ei_url ON archive.external_items(canonical_url);
CREATE INDEX IF NOT EXISTS idx_ei_review ON archive.external_items(review_status);
CREATE INDEX IF NOT EXISTS idx_ei_date ON archive.external_items(date_from);

-- archive.external_item_revisions
CREATE INDEX IF NOT EXISTS idx_eir_item ON archive.external_item_revisions(external_item_id);

-- archive.representations
CREATE INDEX IF NOT EXISTS idx_rep_item ON archive.representations(external_item_id);
CREATE INDEX IF NOT EXISTS idx_rep_role ON archive.representations(representation_role);
CREATE INDEX IF NOT EXISTS idx_rep_sha ON archive.representations(sha256);

-- archive.document_units
CREATE INDEX IF NOT EXISTS idx_du_item ON archive.document_units(external_item_id);
CREATE INDEX IF NOT EXISTS idx_du_rep ON archive.document_units(representation_id);

-- archive.text_versions
CREATE INDEX IF NOT EXISTS idx_tv_item ON archive.text_versions(external_item_id);
CREATE INDEX IF NOT EXISTS idx_tv_rep ON archive.text_versions(representation_id);
CREATE INDEX IF NOT EXISTS idx_tv_role ON archive.text_versions(text_role);
CREATE INDEX IF NOT EXISTS idx_tv_hash ON archive.text_versions(content_hash);

-- archive.passages
CREATE INDEX IF NOT EXISTS idx_pas_tv ON archive.passages(text_version_id);
CREATE INDEX IF NOT EXISTS idx_pas_hash ON archive.passages(content_hash);
CREATE INDEX IF NOT EXISTS idx_pas_review ON archive.passages(review_status);

-- archive.chunks
CREATE INDEX IF NOT EXISTS idx_chunk_tv ON archive.chunks(text_version_id);
CREATE INDEX IF NOT EXISTS idx_chunk_hash ON archive.chunks(content_hash);
-- GIN index per embedding (cosine search)
-- CREATE INDEX IF NOT EXISTS idx_chunk_embedding ON archive.chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- evidence.link_quarantine
CREATE INDEX IF NOT EXISTS idx_lq_source ON evidence.link_quarantine(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_lq_target ON evidence.link_quarantine(target_table, target_id);
CREATE INDEX IF NOT EXISTS idx_lq_status ON evidence.link_quarantine(quarantine_status);

-- evidence.rights_assessments
CREATE INDEX IF NOT EXISTS idx_ra_item ON evidence.rights_assessments(external_item_id);
CREATE INDEX IF NOT EXISTS idx_ra_rep ON evidence.rights_assessments(representation_id);

-- ops.discovery_queries
CREATE INDEX IF NOT EXISTS idx_dq_cache ON ops.discovery_queries(cache_key);
CREATE INDEX IF NOT EXISTS idx_dq_provider ON ops.discovery_queries(provider_code);
CREATE INDEX IF NOT EXISTS idx_dq_executed ON ops.discovery_queries(executed_at);

-- ops.discovery_candidates
CREATE INDEX IF NOT EXISTS idx_dc_query ON ops.discovery_candidates(discovery_query_id);
CREATE INDEX IF NOT EXISTS idx_dc_item ON ops.discovery_candidates(external_item_id);
CREATE INDEX IF NOT EXISTS idx_dc_decision ON ops.discovery_candidates(decision);

-- ops.job_queue
CREATE INDEX IF NOT EXISTS idx_jq_status ON ops.job_queue(status);
CREATE INDEX IF NOT EXISTS idx_jq_priority ON ops.job_queue(priority);
CREATE INDEX IF NOT EXISTS idx_jq_lease ON ops.job_queue(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_jq_type ON ops.job_queue(job_type);

-- ops.fetch_cache
CREATE INDEX IF NOT EXISTS idx_fc_key ON ops.fetch_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_fc_expires ON ops.fetch_cache(expires_at);

-- ai.datasets
CREATE INDEX IF NOT EXISTS idx_ds_stable ON ai.datasets(stable_id);

-- ai.dataset_versions
CREATE INDEX IF NOT EXISTS idx_dsv_dataset ON ai.dataset_versions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_dsv_hash ON ai.dataset_versions(freeze_hash);

-- ai.dataset_items
CREATE INDEX IF NOT EXISTS idx_di_version ON ai.dataset_items(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_di_split ON ai.dataset_items(split_tag);
CREATE INDEX IF NOT EXISTS idx_di_hash ON ai.dataset_items(content_hash);

-- ai.dataset_item_sources
CREATE INDEX IF NOT EXISTS idx_dis_item ON ai.dataset_item_sources(dataset_item_id);
CREATE INDEX IF NOT EXISTS idx_dis_source ON ai.dataset_item_sources(source_type, source_id);

-- ai.evaluation_runs
CREATE INDEX IF NOT EXISTS idx_er_dataset ON ai.evaluation_runs(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_er_model ON ai.evaluation_runs(model_identifier);

-- ════════════════════════════════════════════════════════════════════════════
-- TRIGGER: updated_at automatico
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION archive.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- Applica trigger a tutte le tabelle con updated_at
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE table_schema IN ('archive', 'evidence', 'ops', 'ai')
          AND column_name = 'updated_at'
          AND table_name NOT IN ()
    LOOP
        EXECUTE format(
            'CREATE TRIGGER IF NOT EXISTS trg_updated_%s BEFORE UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;

-- ════════════════════════════════════════════════════════════════════════════
-- VISTE DI COMPATIBILITÀ (legacy)
-- ════════════════════════════════════════════════════════════════════════════

-- Vista legacy per archivio_documenti → archive.external_items
CREATE OR REPLACE VIEW legacy.archivio_documenti_view AS
SELECT
    ei.id,
    ei.provider_code AS archivio,
    ei.title AS titolo,
    ei.description,
    ei.canonical_url AS url,
    ei.date_text AS data,
    ei.external_id,
    ei.review_status,
    ei.created_at,
    ei.updated_at
FROM archive.external_items ei;

-- Vista legacy per fonti_indice → archive.external_items + passages
CREATE OR REPLACE VIEW legacy.fonti_indice_view AS
SELECT
    ei.id,
    ei.title AS titolo,
    ei.canonical_url AS url,
    ei.provider_code AS fonte,
    ei.description AS snippet,
    ei.date_text,
    ei.review_status,
    ei.created_at
FROM archive.external_items ei;

-- ════════════════════════════════════════════════════════════════════════════
-- VISTE PUBBLICHE (api_public)
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW api_public.events AS
SELECT
    e.id,
    e.stable_id,
    e.nome AS preferred_name,
    e.conflict,
    e.event_type,
    e.data_inizio AS date_start,
    e.data_fine AS date_end,
    e.luogo AS general_location,
    e.review_status
FROM public.eventi_1gm e
WHERE e.review_status IN ('confirmed', 'probable');

CREATE OR REPLACE VIEW api_public.sources_metadata AS
SELECT
    ei.id,
    ei.title,
    ei.provider_code,
    ei.canonical_url,
    ei.date_text,
    ei.item_type,
    ei.review_status
FROM archive.external_items ei
WHERE ei.review_status IN ('confirmed', 'probable')
  AND ei.access_status = 'active';

-- ════════════════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY
-- ════════════════════════════════════════════════════════════════════════════

-- archive schema: public read, service_role write
ALTER TABLE archive.repositories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_repositories" ON archive.repositories FOR SELECT USING (true);
CREATE POLICY "service_write_repositories" ON archive.repositories FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_repositories" ON archive.repositories FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.collections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_collections" ON archive.collections FOR SELECT USING (true);
CREATE POLICY "service_write_collections" ON archive.collections FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_collections" ON archive.collections FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.external_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_external_items" ON archive.external_items FOR SELECT USING (review_status IN ('confirmed', 'probable') OR current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_write_external_items" ON archive.external_items FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_external_items" ON archive.external_items FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.external_item_revisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_revisions" ON archive.external_item_revisions FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.representations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_representations" ON archive.representations FOR SELECT USING (publicly_viewable = true OR current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_write_representations" ON archive.representations FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_representations" ON archive.representations FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.document_units ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_doc_units" ON archive.document_units FOR SELECT USING (true);
CREATE POLICY "service_write_doc_units" ON archive.document_units FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.text_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_text_versions" ON archive.text_versions FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.passages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_passages" ON archive.passages FOR SELECT USING (review_status IN ('confirmed', 'probable') OR current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_write_passages" ON archive.passages FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_passages" ON archive.passages FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE archive.chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_chunks" ON archive.chunks FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

-- evidence schema: service_role only
ALTER TABLE evidence.link_quarantine ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_link_quarantine" ON evidence.link_quarantine FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE evidence.rights_assessments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_rights" ON evidence.rights_assessments FOR SELECT USING (true);
CREATE POLICY "service_write_rights" ON evidence.rights_assessments FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_rights" ON evidence.rights_assessments FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

-- ops schema: service_role only
ALTER TABLE ops.discovery_queries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_discovery_queries" ON ops.discovery_queries FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ops.discovery_candidates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_discovery_candidates" ON ops.discovery_candidates FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ops.job_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_job_queue" ON ops.job_queue FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ops.fetch_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_fetch_cache" ON ops.fetch_cache FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

-- ai schema: service_role only
ALTER TABLE ai.datasets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_datasets" ON ai.datasets FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ai.dataset_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_dataset_versions" ON ai.dataset_versions FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ai.dataset_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_dataset_items" ON ai.dataset_items FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ai.dataset_item_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_dataset_item_sources" ON ai.dataset_item_sources FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE ai.evaluation_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_evaluation_runs" ON ai.evaluation_runs FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

-- ════════════════════════════════════════════════════════════════════════════
-- ALTER DEFAULT PRIVILEGES
-- ════════════════════════════════════════════════════════════════════════════

-- Nuove tabelle create dal service_role non sono accessibili a anon
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA archive REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA evidence REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA ops REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA ai REVOKE ALL ON TABLES FROM anon;

-- ════════════════════════════════════════════════════════════════════════════
-- ESTENSIONI
-- ════════════════════════════════════════════════════════════════════════════

-- pgcrypto per digest SHA-256
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- vector per embedding (richiede installazione su Supabase)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- ════════════════════════════════════════════════════════════════════════════
-- FINE
-- ════════════════════════════════════════════════════════════════════════════
