"""
Canonical linking v2 schema for SQLite.

This schema implements the provenance-aware, append-only, candidate-first
data model specified in the linking v2 requirements.

All tables use UUID primary keys (stored as TEXT in SQLite).
All relations use typed resource_registry UUIDs, not raw table+id pairs.
All algorithmic outputs start as 'candidate', never 'confirmed'.
OCR and source artifacts are immutable (append-only).
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent

SCHEMA_SQL = """
-- ════════════════════════════════════════════════════════════════════════════
-- LINKING V2 SCHEMA (SQLite)
-- ════════════════════════════════════════════════════════════════════════════

-- ─── resource_registry ──────────────────────────────────────────────────────
-- Typed registry of all resources. Eliminates namespace confusion.
CREATE TABLE IF NOT EXISTS resource_registry (
    id TEXT PRIMARY KEY,
    resource_kind TEXT NOT NULL CHECK (resource_kind IN (
        'person','event','place','unit','organization',
        'document','source','image','claim','other'
    )),
    source_namespace TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    canonical_entity_id TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (source_namespace, source_record_key)
);

CREATE INDEX IF NOT EXISTS idx_rr_kind ON resource_registry(resource_kind);
CREATE INDEX IF NOT EXISTS idx_rr_namespace ON resource_registry(source_namespace);
CREATE INDEX IF NOT EXISTS idx_rr_canonical ON resource_registry(canonical_entity_id);

-- ─── historical_events ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS historical_events (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL UNIQUE REFERENCES resource_registry(id),
    canonical_name TEXT NOT NULL,
    conflict_code TEXT NOT NULL CHECK (conflict_code IN ('ww1','ww2','other')),
    event_type TEXT NOT NULL,
    parent_event_id TEXT REFERENCES historical_events(id),
    start_date TEXT,
    end_date TEXT,
    temporal_precision TEXT NOT NULL DEFAULT 'unknown',
    canonical_place_id TEXT REFERENCES resource_registry(id),
    geometry TEXT,
    description_claim_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft','reviewed','published','deprecated'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_he_conflict ON historical_events(conflict_code);
CREATE INDEX IF NOT EXISTS idx_he_parent ON historical_events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_he_status ON historical_events(status);
CREATE INDEX IF NOT EXISTS idx_he_dates ON historical_events(start_date, end_date);

-- ─── event_aliases ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_aliases_v2 (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES historical_events(id),
    alias TEXT NOT NULL,
    language TEXT DEFAULT 'it',
    alias_type TEXT NOT NULL DEFAULT 'historical',
    specificity TEXT NOT NULL DEFAULT 'strong',
    is_ambiguous INTEGER NOT NULL DEFAULT 0,
    valid_place TEXT,
    valid_period_start TEXT,
    valid_period_end TEXT,
    source TEXT,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    UNIQUE (event_id, alias, language)
);

CREATE INDEX IF NOT EXISTS idx_ea_alias ON event_aliases_v2(alias);
CREATE INDEX IF NOT EXISTS idx_ea_event ON event_aliases_v2(event_id);
CREATE INDEX IF NOT EXISTS idx_ea_ambiguous ON event_aliases_v2(is_ambiguous);

-- ─── source_artifacts (immutable, append-only) ──────────────────────────────
CREATE TABLE IF NOT EXISTS source_artifacts (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    external_id TEXT,
    source_url TEXT,
    acquired_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    storage_locator TEXT NOT NULL,
    metadata_original TEXT NOT NULL,
    immutable INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sa_provider ON source_artifacts(provider);
CREATE INDEX IF NOT EXISTS idx_sa_sha ON source_artifacts(content_sha256);
CREATE INDEX IF NOT EXISTS idx_sa_external ON source_artifacts(external_id);

-- ─── ocr_observations (immutable, append-only) ──────────────────────────────
CREATE TABLE IF NOT EXISTS ocr_observations (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES source_artifacts(id),
    engine TEXT NOT NULL,
    engine_version TEXT,
    raw_text TEXT NOT NULL,
    raw_payload TEXT,
    language TEXT,
    supersedes_id TEXT REFERENCES ocr_observations(id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oo_artifact ON ocr_observations(artifact_id);
CREATE INDEX IF NOT EXISTS idx_oo_engine ON ocr_observations(engine);
CREATE INDEX IF NOT EXISTS idx_oo_supersedes ON ocr_observations(supersedes_id);

-- ─── claims_v2 (renamed to avoid conflict with existing claims table) ───────
CREATE TABLE IF NOT EXISTS claims_v2 (
    id TEXT PRIMARY KEY,
    subject_resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    predicate TEXT NOT NULL,
    object_value TEXT NOT NULL,
    normalized_value TEXT,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
        'proposed','confirmed','rejected','superseded','disputed'
    )),
    extraction_method TEXT NOT NULL,
    algorithm_version TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT,
    supersedes_claim_id TEXT REFERENCES claims_v2(id)
);

CREATE INDEX IF NOT EXISTS idx_cl2_subject ON claims_v2(subject_resource_id);
CREATE INDEX IF NOT EXISTS idx_cl2_status ON claims_v2(status);
CREATE INDEX IF NOT EXISTS idx_cl2_predicate ON claims_v2(predicate);

-- ─── evidence_fragments ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence_fragments (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES source_artifacts(id),
    ocr_observation_id TEXT REFERENCES ocr_observations(id),
    page_number INTEGER,
    image_region TEXT,
    char_start INTEGER,
    char_end INTEGER,
    quoted_fragment TEXT,
    locator_uri TEXT,
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ef_artifact ON evidence_fragments(artifact_id);
CREATE INDEX IF NOT EXISTS idx_ef_sha ON evidence_fragments(content_sha256);

-- ─── claim_evidence ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS claim_evidence_v2 (
    claim_id TEXT NOT NULL REFERENCES claims_v2(id),
    evidence_id TEXT NOT NULL REFERENCES evidence_fragments(id),
    support_type TEXT NOT NULL CHECK (support_type IN (
        'supports','contradicts','mentions','context'
    )),
    PRIMARY KEY (claim_id, evidence_id)
);

-- ─── review_decisions (append-only) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_decisions (
    id TEXT PRIMARY KEY,
    object_kind TEXT NOT NULL,
    object_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN (
        'confirm','reject','dispute','supersede','request_evidence'
    )),
    reason TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    previous_decision_id TEXT REFERENCES review_decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_rd_object ON review_decisions(object_kind, object_id);
CREATE INDEX IF NOT EXISTS idx_rd_decision ON review_decisions(decision);

-- ─── source_families ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_families (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    family_type TEXT NOT NULL,
    root_source_id TEXT REFERENCES resource_registry(id),
    derivation_notes TEXT,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sf_type ON source_families(family_type);

-- ─── source_family_members ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_family_members (
    source_resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    family_id TEXT NOT NULL REFERENCES source_families(id),
    relation_to_root TEXT NOT NULL,
    evidence_id TEXT REFERENCES evidence_fragments(id),
    PRIMARY KEY (source_resource_id, family_id)
);

-- ─── relations (candidate + confirmed) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    source_resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    target_resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    relation_type TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'directed',
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN (
        'candidate','confirmed','rejected','superseded','disputed','legacy_candidate',
        'accepted','needs_review','to_review'
    )),
    algorithm_name TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    feature_schema_version TEXT NOT NULL,
    features TEXT NOT NULL,
    raw_score REAL,
    confidence_calibrated REAL,
    calibration_model_version TEXT,
    evidence_strength TEXT NOT NULL DEFAULT 'weak' CHECK (evidence_strength IN (
        'weak','moderate','strong'
    )),
    conflict_flags TEXT NOT NULL DEFAULT '[]',
    pipeline_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT,
    supersedes_relation_id TEXT REFERENCES relations(id),
    CHECK (source_resource_id <> target_resource_id),
    CHECK (confidence_calibrated IS NULL OR (confidence_calibrated >= 0 AND confidence_calibrated <= 1))
);

CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_resource_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_resource_id);
CREATE INDEX IF NOT EXISTS idx_rel_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_rel_status ON relations(status);
CREATE INDEX IF NOT EXISTS idx_rel_run ON relations(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_rel_strength ON relations(evidence_strength);

-- Semantic uniqueness: same source+target+type+algorithm+version = upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_semantic
    ON relations(source_resource_id, target_resource_id, relation_type, algorithm_name, algorithm_version);

-- ─── relation_evidence ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS relation_evidence (
    relation_id TEXT NOT NULL REFERENCES relations(id),
    evidence_id TEXT NOT NULL REFERENCES evidence_fragments(id),
    support_type TEXT NOT NULL CHECK (support_type IN (
        'supports','contradicts','mentions','context'
    )),
    PRIMARY KEY (relation_id, evidence_id)
);

-- ─── pipeline_runs ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    code_commit_sha TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    input_count INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    confirmed_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    quarantined_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    checkpoint TEXT,
    error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_pr_name ON pipeline_runs(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_pr_status ON pipeline_runs(status);

-- ─── legacy_relation_quarantine ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS legacy_relation_quarantine (
    id TEXT PRIMARY KEY,
    legacy_table TEXT NOT NULL,
    legacy_pk TEXT NOT NULL,
    legacy_payload TEXT NOT NULL,
    legacy_payload_sha256 TEXT NOT NULL,
    inferred_source_ref TEXT,
    inferred_target_ref TEXT,
    quarantine_reason TEXT NOT NULL,
    legacy_algorithm_name TEXT NOT NULL,
    legacy_algorithm_version TEXT NOT NULL,
    migration_run_id TEXT NOT NULL,
    quarantined_at TEXT NOT NULL,
    restored_at TEXT,
    restored_by TEXT,
    UNIQUE (legacy_table, legacy_pk, migration_run_id)
);

CREATE INDEX IF NOT EXISTS idx_lq_table ON legacy_relation_quarantine(legacy_table);
CREATE INDEX IF NOT EXISTS idx_lq_run ON legacy_relation_quarantine(migration_run_id);
CREATE INDEX IF NOT EXISTS idx_lq_status ON legacy_relation_quarantine(restored_at);

-- ─── golden_dataset ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS golden_dataset_labels (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE,
    source_resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    target_resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    relation_type TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('positive','negative','uncertain')),
    evidence_ids TEXT,
    reviewer_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    review_notes TEXT,
    source_family_ids TEXT,
    dataset_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gdl_case ON golden_dataset_labels(case_id);
CREATE INDEX IF NOT EXISTS idx_gdl_label ON golden_dataset_labels(label);
CREATE INDEX IF NOT EXISTS idx_gdl_version ON golden_dataset_labels(dataset_version);

-- ════════════════════════════════════════════════════════════════════════════
-- EVIDENCE CONTRACT EXTENSIONS (v2.1 — 2026-08-17)
-- ════════════════════════════════════════════════════════════════════════════

-- ─── observations ──────────────────────────────────────────────────────────
-- An observation is a datum actually observed inside a source.
-- It sits between source_artifacts/ocr_observations and evidence_fragments.
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    source_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id),
    ocr_observation_id TEXT REFERENCES ocr_observations(id),
    source_type TEXT NOT NULL,          -- archive|document|web|ocr|ai_extracted|user_submitted
    source_record_id TEXT,              -- original record key in source system
    observation_type TEXT NOT NULL,     -- field_extraction|entity_mention|date|place|unit|matricola|event_ref
    field_name TEXT,                    -- which field was observed (e.g. 'cognome', 'data_nascita')
    raw_value TEXT NOT NULL,            -- exactly what was observed
    normalized_value TEXT,              -- normalized form
    page INTEGER,                       -- page number if applicable
    frame TEXT,                         -- image region / bounding box
    excerpt TEXT,                       -- surrounding context text
    extraction_method TEXT NOT NULL,    -- ocr|regex|ai|manual|federated
    extractor_version TEXT NOT NULL,    -- algorithm version
    pipeline_run_id TEXT REFERENCES pipeline_runs(id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_obs_artifact ON observations(source_artifact_id);
CREATE INDEX IF NOT EXISTS idx_obs_type ON observations(observation_type);
CREATE INDEX IF NOT EXISTS idx_obs_field ON observations(field_name);
CREATE INDEX IF NOT EXISTS idx_obs_run ON observations(pipeline_run_id);

-- ─── source_lineages ────────────────────────────────────────────────────────
-- Tracks which sources share a common origin (derivation chain).
-- Replaces/extends source_families with explicit lineage type.
CREATE TABLE IF NOT EXISTS source_lineages (
    id TEXT PRIMARY KEY,
    canonical_origin TEXT NOT NULL,     -- e.g. 'Ministero della Difesa — Albo d'Oro'
    origin_type TEXT NOT NULL CHECK (origin_type IN (
        'independent','derived','republication','mirror','unknown'
    )),
    parent_lineage_id TEXT REFERENCES source_lineages(id),
    description TEXT,
    authority_level REAL NOT NULL DEFAULT 0.5 CHECK (authority_level BETWEEN 0 AND 1),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sl_origin ON source_lineages(canonical_origin);
CREATE INDEX IF NOT EXISTS idx_sl_type ON source_lineages(origin_type);
CREATE INDEX IF NOT EXISTS idx_sl_parent ON source_lineages(parent_lineage_id);

-- ─── source_lineage_members ─────────────────────────────────────────────────
-- Links resource_registry entries to their source_lineage.
CREATE TABLE IF NOT EXISTS source_lineage_members (
    resource_id TEXT NOT NULL REFERENCES resource_registry(id),
    lineage_id TEXT NOT NULL REFERENCES source_lineages(id),
    relation_to_root TEXT NOT NULL,     -- root|derived|republication|mirror|unknown
    evidence_observation_id TEXT REFERENCES observations(id),
    PRIMARY KEY (resource_id, lineage_id)
);

CREATE INDEX IF NOT EXISTS idx_slm_lineage ON source_lineage_members(lineage_id);

-- ─── evidence_snapshots ─────────────────────────────────────────────────────
-- Immutable snapshot of a complete evidence pipeline run.
-- Every significant historical answer must be reproducible via its snapshot.
CREATE TABLE IF NOT EXISTS evidence_snapshots (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    intent TEXT NOT NULL,               -- PERSON_LOOKUP|EVENT_LOOKUP|AGGREGATE_QUERY|FOLLOWUP
    created_at TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    algorithm_versions TEXT NOT NULL,   -- JSON: {"linking":"2.0.0","narrator":"7.2",...}
    source_ids TEXT NOT NULL,           -- JSON array of source resource IDs
    observation_ids TEXT NOT NULL,      -- JSON array of observation IDs
    evidence_ids TEXT NOT NULL,         -- JSON array of evidence_fragments IDs
    claim_ids TEXT NOT NULL,            -- JSON array of claim IDs
    relation_ids TEXT NOT NULL,         -- JSON array of relation IDs
    rejected_candidates TEXT NOT NULL DEFAULT '[]',  -- JSON
    conflicts TEXT NOT NULL DEFAULT '[]',            -- JSON
    context_hash TEXT NOT NULL,         -- SHA-256 of all input context
    answer_hash TEXT NOT NULL,          -- SHA-256 of final answer
    snapshot_json TEXT NOT NULL         -- Full EvidenceSnapshotV7 serialized
);

CREATE INDEX IF NOT EXISTS idx_es_created ON evidence_snapshots(created_at);
CREATE INDEX IF NOT EXISTS idx_es_intent ON evidence_snapshots(intent);
CREATE INDEX IF NOT EXISTS idx_es_context ON evidence_snapshots(context_hash);

-- ─── explainable_scoring ────────────────────────────────────────────────────
-- Stores detailed feature breakdown for each relation score.
CREATE TABLE IF NOT EXISTS explainable_scores (
    relation_id TEXT NOT NULL REFERENCES relations(id),
    feature_name TEXT NOT NULL,         -- e.g. 'surname_exact', 'birth_year_exact'
    feature_value REAL NOT NULL,        -- contribution to score (can be negative)
    feature_raw TEXT,                   -- raw value that was compared
    is_penalty INTEGER NOT NULL DEFAULT 0,
    algorithm_name TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (relation_id, feature_name, algorithm_version)
);

CREATE INDEX IF NOT EXISTS idx_es_relation ON explainable_scores(relation_id);
CREATE INDEX IF NOT EXISTS idx_es_run ON explainable_scores(pipeline_run_id);

-- ─── place_authority ────────────────────────────────────────────────────────
-- Geographic authority layer: canonical places with historical names.
CREATE TABLE IF NOT EXISTS place_authority (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    historical_name TEXT,
    modern_name TEXT,
    country TEXT,
    historical_country TEXT,
    lat REAL,
    lon REAL,
    valid_from TEXT,
    valid_to TEXT,
    aliases TEXT,                       -- JSON array of alias strings
    parent_place_id TEXT REFERENCES place_authority(id),
    created_at TEXT NOT NULL,
    UNIQUE(canonical_name)
);

CREATE INDEX IF NOT EXISTS idx_pa_canonical ON place_authority(canonical_name);
CREATE INDEX IF NOT EXISTS idx_pa_parent ON place_authority(parent_place_id);
CREATE INDEX IF NOT EXISTS idx_pa_country ON place_authority(country);
"""

# ─── Migration SQL for existing tables (additive, idempotent) ────────────────

MIGRATION_CLAIMS_V2_SQL = """
-- Add evidence contract columns to claims_v2 (additive, idempotent)
ALTER TABLE claims_v2 ADD COLUMN temporal_context TEXT;
ALTER TABLE claims_v2 ADD COLUMN geographic_context TEXT;
ALTER TABLE claims_v2 ADD COLUMN support_score REAL DEFAULT 0.0;
ALTER TABLE claims_v2 ADD COLUMN conflict_status TEXT DEFAULT 'none' CHECK (conflict_status IN (
    'none','temporal','geographic','identity','source','factual'
));
ALTER TABLE claims_v2 ADD COLUMN verification_status TEXT DEFAULT 'candidate' CHECK (verification_status IN (
    'unsupported','candidate','supported','probable','verified','contradicted','disputed','rejected'
));
ALTER TABLE claims_v2 ADD COLUMN evidence_scope TEXT DEFAULT 'person_evidence' CHECK (evidence_scope IN (
    'person_evidence','context_evidence'
));
ALTER TABLE claims_v2 ADD COLUMN identity_cluster_id TEXT;
ALTER TABLE claims_v2 ADD COLUMN source_lineage_id TEXT REFERENCES source_lineages(id);
ALTER TABLE claims_v2 ADD COLUMN pipeline_run_id TEXT REFERENCES pipeline_runs(id);
ALTER TABLE claims_v2 ADD COLUMN reviewed_at TEXT;
ALTER TABLE claims_v2 ADD COLUMN reviewed_by TEXT;
"""

MIGRATION_EVIDENCE_FRAGMENTS_SQL = """
-- Add observation link and classification to evidence_fragments (additive)
ALTER TABLE evidence_fragments ADD COLUMN observation_id TEXT REFERENCES observations(id);
ALTER TABLE evidence_fragments ADD COLUMN evidence_type TEXT DEFAULT 'direct' CHECK (evidence_type IN (
    'direct','indirect','contextual','metadata'
));
ALTER TABLE evidence_fragments ADD COLUMN verification_status TEXT DEFAULT 'unverified' CHECK (verification_status IN (
    'unverified','verified','contradicted','superseded'
));
ALTER TABLE evidence_fragments ADD COLUMN source_lineage_id TEXT REFERENCES source_lineages(id);
ALTER TABLE evidence_fragments ADD COLUMN is_independent INTEGER DEFAULT 0;
"""

MIGRATION_RELATIONS_SQL = """
-- Add evidence contract columns to relations (additive)
ALTER TABLE relations ADD COLUMN temporal_gate TEXT DEFAULT 'unknown' CHECK (temporal_gate IN (
    'direct_contemporary','retrospective','temporally_compatible','temporally_ambiguous','temporally_incompatible','unknown'
));
ALTER TABLE relations ADD COLUMN geographic_gate TEXT DEFAULT 'unknown' CHECK (geographic_gate IN (
    'exact','compatible','ambiguous','incompatible','unknown'
));
ALTER TABLE relations ADD COLUMN identity_gate TEXT DEFAULT 'unverified' CHECK (identity_gate IN (
    'verified','probable','candidate','unverified','rejected','unknown'
));
ALTER TABLE relations ADD COLUMN origin TEXT DEFAULT 'v2' CHECK (origin IN (
    'v2','legacy','legacy_revalidated','manual','imported'
));
ALTER TABLE relations ADD COLUMN snapshot_id TEXT REFERENCES evidence_snapshots(id);
"""


def _safe_alter(conn: sqlite3.Connection, sql: str):
    """Execute ALTER TABLE statements, ignoring 'duplicate column' errors."""
    for stmt in sql.strip().split(';'):
        # Remove comment lines
        lines = [l for l in stmt.strip().split('\n') if not l.strip().startswith('--')]
        stmt = '\n'.join(lines).strip()
        if not stmt:
            continue
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise


def apply_schema(conn: sqlite3.Connection):
    """Apply the v2 schema to a SQLite database.

    Runs CREATE TABLE IF NOT EXISTS for all v2 tables, then applies
    additive ALTER TABLE migrations for evidence contract extensions.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    # Apply additive migrations (idempotent)
    _safe_alter(conn, MIGRATION_CLAIMS_V2_SQL)
    _safe_alter(conn, MIGRATION_EVIDENCE_FRAGMENTS_SQL)
    _safe_alter(conn, MIGRATION_RELATIONS_SQL)
    conn.commit()


def main():
    import sys
    db_path = ROOT / "imi_internati.db"
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    
    print(f"Applying linking v2 schema to: {db_path}")
    conn = sqlite3.connect(str(db_path), timeout=30)
    apply_schema(conn)
    
    # Count new tables
    new_tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ("
        "'resource_registry','historical_events','event_aliases_v2','source_artifacts',"
        "'ocr_observations','claims_v2','evidence_fragments','claim_evidence_v2',"
        "'review_decisions','source_families','source_family_members','relations',"
        "'relation_evidence','pipeline_runs','legacy_relation_quarantine','golden_dataset_labels',"
        "'observations','source_lineages','source_lineage_members','evidence_snapshots',"
        "'explainable_scores','place_authority'"
        ") ORDER BY name"
    ).fetchall()]
    
    conn.close()
    print(f"Created/verified {len(new_tables)} v2 tables: {', '.join(new_tables)}")


if __name__ == "__main__":
    main()
