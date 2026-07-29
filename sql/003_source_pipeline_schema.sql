-- ============================================================
-- 003_source_pipeline_schema.sql
-- Schema per la pipeline di acquisizione fonti storiche v2
-- ============================================================
-- Versione: 1.0.0
-- Data: 2026-07-28
--
-- PRINCIPI:
-- - Additivo e idempotente (CREATE IF NOT EXISTS, ALTER ADD COLUMN)
-- - Non cancella né rinomina tabelle esistenti
-- - RLS su ogni nuova tabella
-- - Separazione: risorsa → documento → passaggio → claim → evidenza → decisione
-- - Assertioni ed evidenze sono immutabili (append-only)
-- ============================================================

-- ─── STEP 1: archive.providers — Registry dei provider ─────────────────────

CREATE TABLE IF NOT EXISTS archive.providers (
    id BIGSERIAL PRIMARY KEY,
    provider_code TEXT UNIQUE NOT NULL,
    provider_name TEXT NOT NULL,
    authority_class TEXT NOT NULL DEFAULT 'DISCOVERY_ONLY'
        CHECK (authority_class IN (
            'PRIMARY_ARCHIVAL',
            'OFFICIAL_DERIVED',
            'SCHOLARLY_CURATED',
            'AGGREGATOR',
            'DISCOVERY_ONLY',
            'USER_CONTRIBUTED'
        )),
    access_mode TEXT NOT NULL DEFAULT 'METADATA_ONLY'
        CHECK (access_mode IN (
            'OPEN_API',
            'OPEN_DOWNLOAD',
            'METADATA_ONLY',
            'TARGETED_SEARCH',
            'REQUEST_REQUIRED',
            'AUTHORIZATION_REQUIRED',
            'UNAVAILABLE'
        )),
    independence_group TEXT,
    rights_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    terms_url TEXT,
    license_uri TEXT,
    holding_institution TEXT,
    collection_scope TEXT,
    personal_data_policy TEXT DEFAULT 'UNKNOWN',
    allowed_actions TEXT[] DEFAULT '{}',
    rate_limit_policy JSONB,
    last_policy_check_at TIMESTAMPTZ,
    provider_version TEXT DEFAULT '1.0',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prov_code ON archive.providers(provider_code);
CREATE INDEX IF NOT EXISTS idx_prov_authority ON archive.providers(authority_class);
CREATE INDEX IF NOT EXISTS idx_prov_enabled ON archive.providers(enabled);

-- ─── STEP 2: ALTER archive.external_items — colonne mancanti ───────────────

ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS provider_id BIGINT REFERENCES archive.providers(id) ON DELETE SET NULL;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS holding_institution TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS collection_or_fonds TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS archival_signature TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS persistent_identifier TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS rights_uri TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS source_version TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS content_checksum TEXT;
ALTER TABLE archive.external_items
    ADD COLUMN IF NOT EXISTS raw_metadata JSONB;

CREATE INDEX IF NOT EXISTS idx_ei_provider_id ON archive.external_items(provider_id);
CREATE INDEX IF NOT EXISTS idx_ei_persistent ON archive.external_items(persistent_identifier);
CREATE INDEX IF NOT EXISTS idx_ei_holding ON archive.external_items(holding_institution);

-- ─── STEP 3: ALTER archive.representations — colonne mancanti ──────────────

ALTER TABLE archive.representations
    ADD COLUMN IF NOT EXISTS iiif_manifest TEXT;
ALTER TABLE archive.representations
    ADD COLUMN IF NOT EXISTS canvas_id TEXT;
ALTER TABLE archive.representations
    ADD COLUMN IF NOT EXISTS page_number INTEGER;
ALTER TABLE archive.representations
    ADD COLUMN IF NOT EXISTS storage_policy TEXT DEFAULT 'reference_only';
ALTER TABLE archive.representations
    ADD COLUMN IF NOT EXISTS ocr_available BOOLEAN DEFAULT FALSE;

-- ─── STEP 4: evidence.claims — Affermazioni estratte ───────────────────────

CREATE TABLE IF NOT EXISTS evidence.claims (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    subject_entity_id BIGINT REFERENCES core.entities(id) ON DELETE SET NULL,
    predicate TEXT NOT NULL,
    object_entity_id BIGINT REFERENCES core.entities(id) ON DELETE SET NULL,
    object_value TEXT,
    claim_status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (claim_status IN (
            'discovered',
            'ingested',
            'candidate',
            'supported',
            'verified',
            'conflicting',
            'rejected',
            'superseded',
            'legacy_unverified'
        )),
    conflict_code TEXT,
    valid_from DATE,
    valid_to DATE,
    date_precision TEXT DEFAULT 'day',
    extraction_method TEXT NOT NULL DEFAULT 'manual',
    pipeline_run_id TEXT,
    algorithm_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (object_entity_id IS NOT NULL OR object_value IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_claims_subject ON evidence.claims(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_claims_object ON evidence.claims(object_entity_id);
CREATE INDEX IF NOT EXISTS idx_claims_predicate ON evidence.claims(predicate);
CREATE INDEX IF NOT EXISTS idx_claims_status ON evidence.claims(claim_status);
CREATE INDEX IF NOT EXISTS idx_claims_conflict ON evidence.claims(conflict_code);
CREATE INDEX IF NOT EXISTS idx_claims_pipeline ON evidence.claims(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_claims_stable ON evidence.claims(stable_id);

-- ─── STEP 5: evidence.evidence — Evidenze che supportano i claim ───────────

CREATE TABLE IF NOT EXISTS evidence.evidence (
    id BIGSERIAL PRIMARY KEY,
    stable_id TEXT UNIQUE NOT NULL,
    claim_id BIGINT NOT NULL REFERENCES evidence.claims(id) ON DELETE CASCADE,
    source_item_id BIGINT REFERENCES archive.external_items(id) ON DELETE SET NULL,
    representation_id BIGINT REFERENCES archive.representations(id) ON DELETE SET NULL,
    passage_id BIGINT REFERENCES archive.passages(id) ON DELETE SET NULL,
    page_or_canvas TEXT,
    line_or_region TEXT,
    text_span TEXT,
    normalized_value TEXT,
    evidence_type TEXT NOT NULL DEFAULT 'documentary'
        CHECK (evidence_type IN (
            'documentary',
            'ocr_extracted',
            'manual_transcription',
            'official_record',
            'cross_reference',
            'ai_extracted'
        )),
    ocr_confidence REAL,
    human_verified BOOLEAN NOT NULL DEFAULT FALSE,
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN (
            'pending',
            'accepted',
            'rejected',
            'needs_review'
        )),
    independence_group TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ev_claim ON evidence.evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_ev_item ON evidence.evidence(source_item_id);
CREATE INDEX IF NOT EXISTS idx_ev_rep ON evidence.evidence(representation_id);
CREATE INDEX IF NOT EXISTS idx_ev_passage ON evidence.evidence(passage_id);
CREATE INDEX IF NOT EXISTS idx_ev_review ON evidence.evidence(review_status);
CREATE INDEX IF NOT EXISTS idx_ev_independence ON evidence.evidence(independence_group);
CREATE INDEX IF NOT EXISTS idx_ev_stable ON evidence.evidence(stable_id);

-- ─── STEP 6: evidence.editorial_decisions — Decisioni umane ────────────────

CREATE TABLE IF NOT EXISTS evidence.editorial_decisions (
    id BIGSERIAL PRIMARY KEY,
    claim_id BIGINT NOT NULL REFERENCES evidence.claims(id) ON DELETE CASCADE,
    decision TEXT NOT NULL
        CHECK (decision IN (
            'verified',
            'supported',
            'rejected',
            'needs_revision',
            'deferred'
        )),
    reviewer_id TEXT NOT NULL,
    reason TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes_decision_id BIGINT REFERENCES evidence.editorial_decisions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ed_claim ON evidence.editorial_decisions(claim_id);
CREATE INDEX IF NOT EXISTS idx_ed_decision ON evidence.editorial_decisions(decision);
CREATE INDEX IF NOT EXISTS idx_ed_reviewer ON evidence.editorial_decisions(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_ed_supersedes ON evidence.editorial_decisions(supersedes_decision_id);

-- ─── STEP 7: ALTER ops.job_queue — colonne mancanti ────────────────────────

ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS provider_id BIGINT REFERENCES archive.providers(id) ON DELETE SET NULL;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS query_payload JSONB;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS checkpoint JSONB;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS cursor TEXT;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS pipeline_run_id TEXT;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS last_error_code TEXT;
ALTER TABLE ops.job_queue
    ADD COLUMN IF NOT EXISTS last_error_message TEXT;

-- Update status constraint to include new states
-- Note: We can't alter existing CHECK constraint without dropping it.
-- The existing status column accepts any TEXT, so new values work.
-- For strict validation, applications should enforce the following:
-- queued | running | retry_wait | partial | succeeded | failed | cancelled

CREATE INDEX IF NOT EXISTS idx_jq_provider ON ops.job_queue(provider_id);
CREATE INDEX IF NOT EXISTS idx_jq_idempotency ON ops.job_queue(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_jq_next_attempt ON ops.job_queue(next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_jq_pipeline ON ops.job_queue(pipeline_run_id);

-- ─── STEP 8: api_public.published_claims — Vista pubblicabile ──────────────

CREATE OR REPLACE VIEW api_public.published_claims AS
SELECT
    c.id,
    c.stable_id,
    c.subject_entity_id,
    c.predicate,
    c.object_entity_id,
    c.object_value,
    c.claim_status,
    c.conflict_code,
    c.valid_from,
    c.valid_to,
    c.date_precision,
    c.extraction_method,
    c.pipeline_run_id,
    c.created_at,
    e.id AS evidence_id,
    e.source_item_id,
    e.representation_id,
    e.passage_id,
    e.page_or_canvas,
    e.line_or_region,
    e.text_span,
    e.evidence_type,
    e.independence_group,
    ei.title AS source_title,
    ei.provider_code,
    ei.canonical_url AS source_url,
    ei.holding_institution,
    ei.archival_signature,
    ei.persistent_identifier,
    ei.rights_uri
FROM evidence.claims c
LEFT JOIN evidence.evidence e ON e.claim_id = c.id
LEFT JOIN archive.external_items ei ON e.source_item_id = ei.id
WHERE c.claim_status IN ('verified', 'supported')
ORDER BY c.created_at DESC;

-- ─── STEP 9: api_public.published_relations — Vista relazioni pubblicate ───

CREATE OR REPLACE VIEW api_public.published_relations AS
SELECT
    c.id AS claim_id,
    c.stable_id,
    c.subject_entity_id,
    c.predicate AS relation_type,
    c.object_entity_id,
    c.object_value,
    c.claim_status,
    c.valid_from,
    c.valid_to,
    c.date_precision,
    c.conflict_code,
    se.canonical_name AS subject_name,
    oe.canonical_name AS object_name,
    COUNT(e.id) AS evidence_count,
    COUNT(DISTINCT e.independence_group) AS independent_sources,
    c.created_at
FROM evidence.claims c
LEFT JOIN core.entities se ON c.subject_entity_id = se.id
LEFT JOIN core.entities oe ON c.object_entity_id = oe.id
LEFT JOIN evidence.evidence e ON e.claim_id = c.id
WHERE c.claim_status IN ('verified', 'supported')
GROUP BY c.id, se.canonical_name, oe.canonical_name
ORDER BY c.created_at DESC;

-- ─── STEP 10: api_public.provider_status — Vista stato provider ────────────

CREATE OR REPLACE VIEW api_public.provider_status AS
SELECT
    p.provider_code,
    p.provider_name,
    p.authority_class,
    p.access_mode,
    p.enabled,
    p.rights_status,
    p.terms_url,
    p.last_policy_check_at,
    p.provider_version,
    COUNT(DISTINCT ei.id) AS items_acquired,
    COUNT(DISTINCT c.id) AS claims_generated,
    COUNT(DISTINCT c.id) FILTER (WHERE c.claim_status = 'verified') AS claims_verified,
    COUNT(DISTINCT c.id) FILTER (WHERE c.claim_status = 'supported') AS claims_supported,
    COUNT(DISTINCT c.id) FILTER (WHERE c.claim_status = 'conflicting') AS claims_conflicting
FROM archive.providers p
LEFT JOIN archive.external_items ei ON ei.provider_id = p.id
LEFT JOIN evidence.evidence e ON e.source_item_id = ei.id
LEFT JOIN evidence.claims c ON e.claim_id = c.id
GROUP BY p.id, p.provider_code, p.provider_name, p.authority_class, p.access_mode,
         p.enabled, p.rights_status, p.terms_url, p.last_policy_check_at, p.provider_version;

-- ─── STEP 11: RLS su nuove tabelle ─────────────────────────────────────────

ALTER TABLE archive.providers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_providers" ON archive.providers FOR SELECT USING (true);
CREATE POLICY "service_write_providers" ON archive.providers FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_providers" ON archive.providers FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE evidence.claims ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_claims" ON evidence.claims FOR SELECT USING (claim_status IN ('verified', 'supported') OR current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_write_claims" ON evidence.claims FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_claims" ON evidence.claims FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE evidence.evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_evidence" ON evidence.evidence FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM evidence.claims c
        WHERE c.id = evidence.evidence.claim_id
        AND c.claim_status IN ('verified', 'supported')
    ) OR current_setting('request.jwt.claim.role', true) = 'service_role'
);
CREATE POLICY "service_write_evidence" ON evidence.evidence FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_evidence" ON evidence.evidence FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE evidence.editorial_decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all_editorial" ON evidence.editorial_decisions FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

-- ─── STEP 12: Trigger updated_at su nuove tabelle ──────────────────────────

CREATE TRIGGER IF NOT EXISTS trg_updated_providers
    BEFORE UPDATE ON archive.providers
    FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at();

CREATE TRIGGER IF NOT EXISTS trg_updated_claims
    BEFORE UPDATE ON evidence.claims
    FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at();

CREATE TRIGGER IF NOT EXISTS trg_updated_evidence
    BEFORE UPDATE ON evidence.evidence
    FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at();

-- ─── STEP 13: Grants ───────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA evidence TO anon, authenticated, service_role;
GRANT SELECT ON evidence.claims TO anon, authenticated;
GRANT SELECT ON evidence.evidence TO anon, authenticated;
GRANT ALL ON evidence.claims, evidence.evidence, evidence.editorial_decisions TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA evidence TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA evidence GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA evidence GRANT ALL ON TABLES TO service_role;

GRANT SELECT ON archive.providers TO anon, authenticated;
GRANT ALL ON archive.providers TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA archive TO service_role;

-- ─── STEP 14: Funzione stable_id per claims ────────────────────────────────

CREATE OR REPLACE FUNCTION evidence.generate_claim_stable_id(
    p_subject_entity_id BIGINT,
    p_predicate TEXT,
    p_object_entity_id BIGINT,
    p_object_value TEXT,
    p_pipeline_run_id TEXT
) RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    raw TEXT;
BEGIN
    raw := COALESCE(p_subject_entity_id::TEXT, '') || ':'
        || COALESCE(p_predicate, '') || ':'
        || COALESCE(p_object_entity_id::TEXT, '') || ':'
        || COALESCE(p_object_value, '') || ':'
        || COALESCE(p_pipeline_run_id, '');
    RETURN 'sha256:' || encode(digest(raw::bytea, 'sha256'), 'hex');
END;
$$;

CREATE OR REPLACE FUNCTION evidence.generate_evidence_stable_id(
    p_claim_id BIGINT,
    p_source_item_id BIGINT,
    p_page_or_canvas TEXT,
    p_line_or_region TEXT
) RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    raw TEXT;
BEGIN
    raw := COALESCE(p_claim_id::TEXT, '') || ':'
        || COALESCE(p_source_item_id::TEXT, '') || ':'
        || COALESCE(p_page_or_canvas, '') || ':'
        || COALESCE(p_line_or_region, '');
    RETURN 'sha256:' || encode(digest(raw::bytea, 'sha256'), 'hex');
END;
$$;
