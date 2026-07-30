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
"""


def apply_schema(conn: sqlite3.Connection):
    """Apply the v2 schema to a SQLite database."""
    conn.executescript(SCHEMA_SQL)
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
        "'relation_evidence','pipeline_runs','legacy_relation_quarantine','golden_dataset_labels'"
        ") ORDER BY name"
    ).fetchall()]
    
    conn.close()
    print(f"Created/verified {len(new_tables)} v2 tables: {', '.join(new_tables)}")


if __name__ == "__main__":
    main()
