"""
Persistence layer for linking v2.

Writes candidates, relations, and pipeline runs to the v2 schema tables.
All operations are idempotent via semantic unique keys.
"""
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from linking.scoring import ScoreResult
from linking.feature_extraction import Features
from linking.candidate_generation import CandidatePair


PERSISTENCE_VERSION = "2.0.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid4())


def create_pipeline_run(
    conn: sqlite3.Connection,
    pipeline_name: str,
    algorithm_version: str,
    code_commit_sha: str,
    configuration: dict,
) -> str:
    """Create a pipeline_runs entry and return its ID."""
    run_id = _uuid()
    config_hash = hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode()
    ).hexdigest()
    
    conn.execute(
        """INSERT INTO pipeline_runs
           (id, pipeline_name, algorithm_version, code_commit_sha,
            configuration_hash, started_at, status)
           VALUES (?, ?, ?, ?, ?, ?, 'running')""",
        (run_id, pipeline_name, algorithm_version, code_commit_sha, config_hash, _utc_now())
    )
    conn.commit()
    return run_id


def finish_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str = "completed",
    counts: dict | None = None,
    error_summary: str | None = None,
):
    """Update a pipeline run with final status and counts."""
    fields = ["finished_at = ?", "status = ?"]
    values = [_utc_now(), status]
    
    if counts:
        for k in ["input_count", "processed_count", "candidate_count",
                   "confirmed_count", "rejected_count", "quarantined_count",
                   "failed_count"]:
            if k in counts:
                fields.append(f"{k} = ?")
                values.append(counts[k])
    
    if error_summary:
        fields.append("error_summary = ?")
        values.append(json.dumps(error_summary))
    
    values.append(run_id)
    conn.execute(
        f"UPDATE pipeline_runs SET {', '.join(fields)} WHERE id = ?",
        values
    )
    conn.commit()


def register_resource(
    conn: sqlite3.Connection,
    resource_kind: str,
    source_namespace: str,
    source_record_key: str,
    canonical_entity_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """
    Register or get a resource in resource_registry.
    Idempotent: returns existing ID if (namespace, key) already exists.
    """
    existing = conn.execute(
        "SELECT id FROM resource_registry WHERE source_namespace = ? AND source_record_key = ?",
        (source_namespace, source_record_key)
    ).fetchone()
    
    if existing:
        return existing[0]
    
    rid = _uuid()
    conn.execute(
        """INSERT INTO resource_registry
           (id, resource_kind, source_namespace, source_record_key,
            canonical_entity_id, metadata_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (rid, resource_kind, source_namespace, source_record_key,
         canonical_entity_id, json.dumps(metadata) if metadata else None, _utc_now())
    )
    conn.commit()
    return rid


def upsert_relation(
    conn: sqlite3.Connection,
    source_resource_id: str,
    target_resource_id: str,
    relation_type: str,
    algorithm_name: str,
    algorithm_version: str,
    features: Features,
    score: ScoreResult,
    pipeline_run_id: str,
    direction: str = "directed",
    status: str = "candidate",
) -> str:
    """
    Insert or update a relation. Idempotent via semantic unique key.
    Returns the relation ID.
    
    For symmetric relations, normalizes orientation so A-B and B-A
    don't become duplicates.
    """
    # Normalize symmetric relations
    if direction == "symmetric":
        if source_resource_id > target_resource_id:
            source_resource_id, target_resource_id = target_resource_id, source_resource_id
    
    # Check for existing relation with same semantic key
    existing = conn.execute(
        """SELECT id FROM relations
           WHERE source_resource_id = ? AND target_resource_id = ?
             AND relation_type = ? AND algorithm_name = ? AND algorithm_version = ?""",
        (source_resource_id, target_resource_id, relation_type,
         algorithm_name, algorithm_version)
    ).fetchone()
    
    rel_id = existing[0] if existing else _uuid()
    features_json = json.dumps({
        "name_match": features.name_match,
        "name_cognome_exact": features.name_cognome_exact,
        "name_nome_exact": features.name_nome_exact,
        "birth_date_compatible": features.birth_date_compatible,
        "birth_place_compatible": features.birth_place_compatible,
        "same_matricola": features.same_matricola,
        "same_unit": features.same_unit,
        "temporal_overlap": features.temporal_overlap,
        "geographic_compatible": features.geographic_compatible,
        "document_citation": features.document_citation,
        "discriminators": features.discriminators,
    }, ensure_ascii=False)
    
    if existing:
        # Update existing
        conn.execute(
            """UPDATE relations SET
               features = ?, raw_score = ?, evidence_strength = ?,
               conflict_flags = ?, pipeline_run_id = ?
               WHERE id = ?""",
            (features_json, score.raw_score, score.evidence_strength,
             json.dumps(score.conflict_flags), pipeline_run_id, rel_id)
        )
    else:
        # Insert new
        conn.execute(
            """INSERT INTO relations
               (id, source_resource_id, target_resource_id, relation_type,
                direction, status, algorithm_name, algorithm_version,
                feature_schema_version, features, raw_score,
                confidence_calibrated, calibration_model_version,
                evidence_strength, conflict_flags, pipeline_run_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_id, source_resource_id, target_resource_id, relation_type,
             direction, status, algorithm_name, algorithm_version,
             features.version, features_json, score.raw_score,
             score.confidence_calibrated, score.calibration_model_version,
             score.evidence_strength, json.dumps(score.conflict_flags),
             pipeline_run_id, _utc_now())
        )
    
    conn.commit()
    return rel_id
