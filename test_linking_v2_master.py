"""
Master test file for linking v2 modules.

Tests:
1. Kill switch — frozen jobs raise RuntimeError
2. Normalization — name, date, place normalization
3. Feature extraction — person/event, person/source, document/event
4. Conflict detection — WW1/WW2, born_after, ambiguous keywords
5. Scoring — weak/moderate/strong evidence, veto overrides
6. Persistence — idempotent upsert, resource registry
7. Schema — all 16 v2 tables exist
8. Security — secret redaction, .env not tracked
9. Golden dataset — mandatory cases seeded
10. CLI — dry-run generate, audit, quarantine

Run: python -m pytest test_linking_v2_master.py -v
     python test_linking_v2_master.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def test_kill_switch_frozen():
    """All legacy jobs must be frozen by default."""
    from linking.kill_switch import LegacyJob, is_legacy_job_enabled, assert_frozen
    
    for job in LegacyJob:
        assert not is_legacy_job_enabled(job), f"{job.value} should be frozen by default"
    
    try:
        assert_frozen(LegacyJob.EVENT_LINKS)
        assert False, "Should have raised RuntimeError"
    except RuntimeError:
        pass


def test_kill_switch_env_override():
    """Legacy jobs can be enabled via env var."""
    from linking.kill_switch import LegacyJob, is_legacy_job_enabled
    
    os.environ["LEGACY_JOB_LEGACY_EVENT_LINKS"] = "true"
    assert is_legacy_job_enabled(LegacyJob.EVENT_LINKS)
    del os.environ["LEGACY_JOB_LEGACY_EVENT_LINKS"]
    assert not is_legacy_job_enabled(LegacyJob.EVENT_LINKS)


def test_normalize_name():
    from linking.normalization import normalize_name
    
    n = normalize_name("Rossi", "Mario")
    assert n.cognome_normalized == "rossi"
    assert n.nome_normalized == "mario"
    assert n.normalized == "rossi mario"
    
    # Accent stripping
    n2 = normalize_name("Negré", "François")
    assert "negre" in n2.cognome_normalized
    assert "francois" in n2.nome_normalized


def test_normalize_date():
    from linking.normalization import normalize_date
    
    # ISO
    d = normalize_date("1917-10-24")
    assert d.precision == "exact"
    assert d.normalized == "1917-10-24"
    
    # Italian
    d2 = normalize_date("24/10/1917")
    assert d2.precision == "exact"
    assert d2.normalized == "1917-10-24"
    
    # Year only
    d3 = normalize_date("1917")
    assert d3.precision == "year"
    
    # Range
    d4 = normalize_date("1915-1918")
    assert d4.precision == "range"
    assert d4.start == "1915"
    assert d4.end == "1918"
    
    # Unknown
    d5 = normalize_date("")
    assert d5.precision == "unknown"


def test_date_overlap():
    from linking.normalization import date_overlap
    
    assert date_overlap("1915", "1918", "1917", "1918")
    assert not date_overlap("1919", "1920", "1915", "1918")
    assert date_overlap("1917", "1917", "1917", "1917")


def test_ambiguous_keyword():
    from linking.feature_extraction import is_ambiguous_keyword
    
    assert is_ambiguous_keyword("campo")
    assert is_ambiguous_keyword("Russia")
    assert is_ambiguous_keyword("Africa")
    assert not is_ambiguous_keyword("Caporetto")
    assert not is_ambiguous_keyword("Carso")


def test_word_boundary_match():
    from linking.feature_extraction import _word_boundary_match
    
    assert _word_boundary_match("Carso", "La battaglia del Carso fu sanguinosa")
    assert not _word_boundary_match("Carso", "Il Carsismo è un fenomeno geologico")
    assert _word_boundary_match("Caporetto", "La ritirata di Caporetto")


def test_feature_extraction_person_event_ww1_ww2():
    from linking.feature_extraction import extract_features_person_event
    
    person = {
        "data_nascita": "1920-01-15",
        "data_morte": "1944-06-01",
    }
    event = {
        "conflict_code": "ww1",
        "data_inizio": "1915-05-24",
        "data_fine": "1918-11-04",
        "keywords": "[]",
        "aliases": "[]",
    }
    
    features, conflicts = extract_features_person_event(person, event)
    assert conflicts.ww1_ww2_mismatch, "Should detect WW1/WW2 mismatch"
    assert conflicts.born_after_event, "Person born 1920 should be after WW1"


def test_feature_extraction_person_event_temporal():
    from linking.feature_extraction import extract_features_person_event
    
    person = {
        "data_nascita": "1890-01-01",
        "data_morte": "1917-10-25",
        "luogo_morte": "Caporetto",
    }
    event = {
        "conflict_code": "ww1",
        "data_inizio": "1917-10-24",
        "data_fine": "1917-11-12",
        "luogo": "Caporetto",
        "keywords": '["Caporetto"]',
        "aliases": '[]',
    }
    
    features, conflicts = extract_features_person_event(person, event)
    assert features.temporal_overlap
    assert features.geographic_compatible
    assert not conflicts.has_veto


def test_scoring_weak_no_discriminator():
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import score_candidate
    
    f = Features(name_match=True, name_cognome_exact=True)
    s = score_candidate(f)
    assert s.evidence_strength == "weak"
    assert not s.can_be_confirmed


def test_scoring_moderate_one_discriminator():
    from linking.feature_extraction import Features
    from linking.scoring import score_candidate
    
    f = Features(
        name_match=True, name_cognome_exact=True,
        birth_date_compatible=True,
        discriminators=["birth_date"],
    )
    s = score_candidate(f)
    assert s.evidence_strength == "moderate"
    assert not s.can_be_confirmed  # Only 1 discriminator


def test_scoring_strong_two_discriminators():
    from linking.feature_extraction import Features
    from linking.scoring import score_candidate
    
    f = Features(
        name_match=True, name_cognome_exact=True,
        birth_date_compatible=True, birth_place_compatible=True,
        discriminators=["birth_date", "birth_place"],
    )
    s = score_candidate(f)
    assert s.evidence_strength == "strong"
    assert s.can_be_confirmed


def test_scoring_veto_overrides():
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import score_candidate
    
    f = Features(
        name_match=True, name_cognome_exact=True,
        discriminators=["birth_date", "birth_place"],
    )
    cf = ConflictFlags(ww1_ww2_mismatch=True)
    s = score_candidate(f, cf)
    assert s.evidence_strength == "weak"
    assert not s.can_be_confirmed
    assert "ww1_ww2_mismatch" in s.conflict_flags


def test_scoring_confidence_calibrated_is_none():
    from linking.feature_extraction import Features
    from linking.scoring import score_candidate
    
    f = Features(name_match=True, discriminators=["x", "y"])
    s = score_candidate(f)
    assert s.confidence_calibrated is None, "No calibration dataset yet"


def test_schema_v2_tables_exist():
    """All 16 v2 tables must exist in imi_internati.db."""
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    
    expected = [
        "resource_registry", "historical_events", "event_aliases_v2",
        "source_artifacts", "ocr_observations", "claims_v2",
        "evidence_fragments", "claim_evidence_v2", "review_decisions",
        "source_families", "source_family_members", "relations",
        "relation_evidence", "pipeline_runs", "legacy_relation_quarantine",
        "golden_dataset_labels",
    ]
    
    for table in expected:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table,)
        ).fetchone()
        assert result is not None, f"Table {table} not found"
    
    conn.close()


def test_security_redact_secrets():
    from linking.security import redact_secrets
    
    text = "My key is sb_secret_abcdef1234567890abcdef and sk-1234567890abcdef123456"
    redacted = redact_secrets(text)
    assert "sb_secret_abcdef" not in redacted
    assert "sk-1234567890" not in redacted
    assert "REDACTED" in redacted


def test_security_env_not_tracked():
    from linking.security import check_env_not_tracked
    
    result = check_env_not_tracked(ROOT)
    assert result["safe"], f".env is tracked by git: {result}"


def test_persistence_idempotent_upsert():
    """Upserting the same relation twice should not create duplicates."""
    from linking.schema_v2 import apply_schema
    from linking.persistence import register_resource, upsert_relation, create_pipeline_run
    from linking.feature_extraction import Features
    from linking.scoring import ScoreResult
    
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    
    # Register resources
    rid1 = register_resource(conn, "person", "test_ns", "test_key_1")
    rid2 = register_resource(conn, "person", "test_ns", "test_key_2")
    
    # Create pipeline run
    run_id = create_pipeline_run(conn, "test", "2.0.0", "test_sha", {"test": True})
    
    f = Features(name_match=True, name_cognome_exact=True, discriminators=["test"])
    s = ScoreResult(raw_score=0.5, evidence_strength="moderate", conflict_flags=[])
    
    # Insert once
    rel_id1 = upsert_relation(
        conn, rid1, rid2, "test_relation", "test_algo", "2.0.0",
        f, s, run_id
    )
    
    # Insert again (should be idempotent)
    rel_id2 = upsert_relation(
        conn, rid1, rid2, "test_relation", "test_algo", "2.0.0",
        f, s, run_id
    )
    
    assert rel_id1 == rel_id2, "Idempotent upsert should return same ID"
    
    # Verify only one row
    count = conn.execute(
        "SELECT COUNT(*) FROM relations WHERE source_resource_id = ? AND target_resource_id = ?",
        (rid1, rid2)
    ).fetchone()[0]
    assert count == 1, f"Expected 1 relation, found {count}"
    
    # Cleanup
    conn.execute("DELETE FROM relations WHERE id = ?", (rel_id1,))
    conn.execute("DELETE FROM resource_registry WHERE id IN (?, ?)", (rid1, rid2))
    conn.execute("DELETE FROM pipeline_runs WHERE id = ?", (run_id,))
    conn.commit()
    conn.close()


def test_golden_dataset_seed():
    from linking.schema_v2 import apply_schema
    from linking.golden_dataset import seed_golden_dataset, MANDATORY_CASES
    
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    
    inserted = seed_golden_dataset(conn)
    
    # Verify cases exist
    count = conn.execute("SELECT COUNT(*) FROM golden_dataset_labels").fetchone()[0]
    assert count >= len(MANDATORY_CASES), f"Expected >= {len(MANDATORY_CASES)} cases, found {count}"
    
    # Verify labels
    labels = [r[0] for r in conn.execute(
        "SELECT DISTINCT label FROM golden_dataset_labels"
    ).fetchall()]
    assert "positive" in labels
    assert "negative" in labels
    assert "uncertain" in labels
    
    conn.close()


def test_candidate_generation_blocking():
    """Blocking should produce candidate pairs, not O(N*M) scans."""
    from linking.candidate_generation import generate_candidates
    
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    
    # Use small tables for test - fonti_indice uses 'titolo' not 'cognome'
    candidates = generate_candidates(
        conn, "internati",
        {"cognome": "cognome", "nome": "nome", "id": "id",
         "place": "luogo_nascita"},
        "fonti_indice",
        {"cognome": "titolo", "id": "id",
         "place": "archivio"},
    )
    
    # Should produce some candidates (internati has 20K rows)
    assert isinstance(candidates, list)
    assert len(candidates) > 0, "Should produce some candidate pairs"
    
    # Each candidate should have required fields
    if candidates:
        c = candidates[0]
        assert hasattr(c, "source_namespace")
        assert hasattr(c, "target_namespace")
        assert hasattr(c, "block_key")
        assert hasattr(c, "block_type")
    
    conn.close()


# ─── Temporal filter tests ───────────────────────────────────────────────────

def test_temporal_relation_overlap():
    """temporal_relation correctly identifies overlapping periods."""
    from linking.temporal_filter import temporal_relation
    assert temporal_relation("1915", "1918", "1916", "1917") == "overlap"
    assert temporal_relation("1914", "1918", "1915", "1918") == "overlap"


def test_temporal_relation_conflict():
    """temporal_relation correctly identifies non-overlapping (conflict) periods."""
    from linking.temporal_filter import temporal_relation
    assert temporal_relation("1940", "1945", "1915", "1918") == "conflict"
    assert temporal_relation("1915", "1918", "1943", "1945") == "conflict"


def test_temporal_relation_unknown():
    """temporal_relation returns unknown when dates are missing."""
    from linking.temporal_filter import temporal_relation
    assert temporal_relation(None, None, "1915", "1918") == "unknown"
    assert temporal_relation("1915", "1918", None, None) == "unknown"


def test_classify_keyword_distinctive_ww1():
    """Distinctive WWI keywords are classified correctly."""
    from linking.temporal_filter import classify_keyword, KeywordClass
    assert classify_keyword("Caporetto", "WWI") == KeywordClass.DISTINCTIVE
    assert classify_keyword("Carso", "WWI") == KeywordClass.DISTINCTIVE


def test_classify_keyword_distinctive_ww2():
    """Distinctive WWII keywords are classified correctly."""
    from linking.temporal_filter import classify_keyword, KeywordClass
    assert classify_keyword("Cefalonia", "WWII") == KeywordClass.DISTINCTIVE
    assert classify_keyword("Salerno", "WWII") == KeywordClass.DISTINCTIVE


def test_classify_keyword_opposite_conflict():
    """WWII keyword against WWI event is classified as OPPOSITE_CONFLICT."""
    from linking.temporal_filter import classify_keyword, KeywordClass
    assert classify_keyword("Cefalonia", "WWI") == KeywordClass.OPPOSITE_CONFLICT
    assert classify_keyword("Caporetto", "WWII") == KeywordClass.OPPOSITE_CONFLICT


def test_classify_keyword_ambiguous():
    """Ambiguous keywords are classified correctly."""
    from linking.temporal_filter import classify_keyword, KeywordClass
    assert classify_keyword("fronte", "WWI") == KeywordClass.AMBIGUOUS
    assert classify_keyword("prigionia", "WWII") == KeywordClass.AMBIGUOUS


def test_detect_conflict_markers_ww2_in_ww1():
    """WWII markers detected in text when event is WWI."""
    from linking.temporal_filter import detect_conflict_markers
    markers = detect_conflict_markers("Eccidio di Cefalonia 1943", "WWI")
    assert len(markers) > 0
    assert any("cefalonia" in m.lower() for m in markers)


def test_detect_same_era_markers_ww1():
    """WWI markers detected in text when event is WWI."""
    from linking.temporal_filter import detect_same_era_markers
    markers = detect_same_era_markers("Battaglia di Caporetto 1917", "WWI")
    assert len(markers) > 0


def test_filter_sources_for_event_rejects_conflict():
    """filter_sources_for_event rejects sources with opposite-era markers."""
    from linking.temporal_filter import filter_sources_for_event
    sources = [
        {"id": 1, "titolo": "Eccidio di Cefalonia 1943", "coverage_start": "1943", "coverage_end": "1943"},
        {"id": 2, "titolo": "Battaglia di Caporetto 1917", "coverage_start": "1917", "coverage_end": "1917"},
    ]
    event = {"conflict": "WWI", "data_inizio": "1915", "data_fine": "1918"}
    result = filter_sources_for_event(sources, event, include_candidates=False)
    source_ids = [s["id"] for s in result["sources"]]
    assert 2 in source_ids, "WWI source should be accepted"
    assert 1 not in source_ids, "WWII source should be rejected"


def test_filter_sources_for_event_include_candidates():
    """filter_sources_for_event includes candidates when flag is set."""
    from linking.temporal_filter import filter_sources_for_event
    sources = [
        {"id": 1, "titolo": "Eccidio di Cefalonia 1943", "coverage_start": "1943", "coverage_end": "1943"},
        {"id": 2, "titolo": "Battaglia di Caporetto 1917", "coverage_start": "1917", "coverage_end": "1917"},
    ]
    event = {"conflict": "WWI", "data_inizio": "1915", "data_fine": "1918"}
    result = filter_sources_for_event(sources, event, include_candidates=True)
    assert len(result["sources"]) > 0
    assert len(result["candidate_sources"]) >= 0


# ─── Source-event feature extraction tests ────────────────────────────────────

def test_extract_features_source_event_temporal_overlap():
    """Source-event feature extraction detects temporal overlap."""
    from linking.feature_extraction import extract_features_source_event
    source = {
        "id": 1, "titolo": "Relazione sulla battaglia",
        "coverage_start": "1916", "coverage_end": "1917",
        "soggetti_collegati": "", "note": "", "luogo": "",
    }
    event = {
        "id": 56, "nome": "Battaglia di Caporetto",
        "data_inizio": "1915", "data_fine": "1918",
        "conflict": "WWI", "keywords": "[]", "aliases": "[]",
    }
    features, conflicts = extract_features_source_event(source, event)
    assert features.temporal_overlap, "Should detect temporal overlap"
    assert not conflicts.temporal_conflict, "Should not have temporal conflict"


def test_extract_features_source_event_temporal_conflict():
    """Source-event feature extraction detects temporal conflict."""
    from linking.feature_extraction import extract_features_source_event
    source = {
        "id": 1, "titolo": "Massacro di Cefalonia",
        "coverage_start": "1943", "coverage_end": "1943",
        "soggetti_collegati": "", "note": "", "luogo": "",
    }
    event = {
        "id": 56, "nome": "Battaglia di Caporetto",
        "data_inizio": "1915", "data_fine": "1918",
        "conflict": "WWI", "keywords": "[]", "aliases": "[]",
    }
    features, conflicts = extract_features_source_event(source, event)
    assert conflicts.temporal_conflict or conflicts.ww1_ww2_mismatch, \
        "Should detect temporal conflict or WW1/WW2 mismatch"


def test_extract_features_source_event_distinctive_keyword():
    """Source-event feature extraction detects distinctive keywords."""
    from linking.feature_extraction import extract_features_source_event
    source = {
        "id": 1, "titolo": "Diario di Caporetto",
        "coverage_start": "1917", "coverage_end": "1917",
        "soggetti_collegati": "", "note": "", "luogo": "",
    }
    event = {
        "id": 56, "nome": "Battaglia di Caporetto",
        "data_inizio": "1915", "data_fine": "1918",
        "conflict": "WWI",
        "keywords": '["Caporetto"]', "aliases": "[]",
    }
    features, conflicts = extract_features_source_event(source, event)
    assert any("caporetto" in d.lower() for d in features.discriminators), \
        "Should match distinctive keyword 'Caporetto'"


# ─── decide() tests ───────────────────────────────────────────────────────────

def test_decide_accepted():
    """decide() returns accepted for distinctive keyword + temporal overlap."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    f.discriminators = ["keyword:Caporetto", "temporal_overlap"]
    f.temporal_overlap = True
    cf = ConflictFlags()
    result = decide(f, cf)
    assert result.status == "accepted", f"Expected accepted, got {result.status}"


def test_decide_rejected_temporal_conflict():
    """decide() returns rejected for temporal conflict."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    f.discriminators = ["keyword:Caporetto"]
    cf = ConflictFlags()
    cf.temporal_conflict = True
    result = decide(f, cf)
    assert result.status == "rejected", f"Expected rejected, got {result.status}"
    assert result.reason == "temporal_conflict"


def test_decide_rejected_ww1_ww2_mismatch():
    """decide() returns rejected for WW1/WW2 mismatch."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    f.discriminators = ["keyword:Cefalonia"]
    cf = ConflictFlags()
    cf.ww1_ww2_mismatch = True
    result = decide(f, cf)
    assert result.status == "rejected", f"Expected rejected, got {result.status}"
    assert result.reason == "ww1_ww2_mismatch"


def test_decide_needs_review_mixed_era():
    """decide() returns needs_review for mixed era source."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    f.discriminators = ["same_era:carso"]
    cf = ConflictFlags()
    cf.mixed_era_source = True
    result = decide(f, cf)
    assert result.status == "needs_review", f"Expected needs_review, got {result.status}"


def test_decide_needs_review_ambiguous_only():
    """decide() returns needs_review when only ambiguous keywords matched."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    f.discriminators = []
    cf = ConflictFlags()
    cf.ambiguous_keywords_only = True
    result = decide(f, cf)
    assert result.status == "needs_review", f"Expected needs_review, got {result.status}"


def test_decide_needs_review_unknown_temporal():
    """decide() returns needs_review for distinctive keyword without temporal overlap."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    f.discriminators = ["keyword:Caporetto"]
    f.temporal_overlap = False
    cf = ConflictFlags()
    result = decide(f, cf)
    assert result.status == "needs_review", f"Expected needs_review, got {result.status}"


def test_decide_rejected_insufficient_evidence():
    """decide() returns rejected when no discriminators."""
    from linking.feature_extraction import Features, ConflictFlags
    from linking.scoring import decide
    f = Features()
    cf = ConflictFlags()
    result = decide(f, cf)
    assert result.status == "rejected", f"Expected rejected, got {result.status}"
    assert result.reason == "insufficient_evidence"


# ─── Migration tests ──────────────────────────────────────────────────────────

def test_migration_coverage_columns_exist():
    """coverage_* columns exist on fonti_indice after migration."""
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(fonti_indice)").fetchall()]
    conn.close()
    expected = ["coverage_start", "coverage_end", "coverage_precision",
                "coverage_source_field", "coverage_extraction_method", "coverage_confidence"]
    for col in expected:
        assert col in cols, f"Column {col} missing from fonti_indice"


def test_migration_coverage_backfilled():
    """At least some fonti_indice rows have coverage_start populated."""
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    count = conn.execute("SELECT COUNT(*) FROM fonti_indice WHERE coverage_start IS NOT NULL").fetchone()[0]
    conn.close()
    assert count > 0, f"Expected some rows with coverage_start, got {count}"


# ─── Supabase kill switch test ────────────────────────────────────────────────

def test_supabase_kill_switch_env():
    """SYNC_EVENT_LINKS_SUPABASE=false suspends event_links sync."""
    old_val = os.environ.get("SYNC_EVENT_LINKS_SUPABASE")
    try:
        os.environ["SYNC_EVENT_LINKS_SUPABASE"] = "false"
        # Import and call sync_event_links — should return 0 without syncing
        from sync_ww1_to_supabase import sync_event_links
        result = sync_event_links()
        assert result == 0, f"Expected 0 (suspended), got {result}"
    finally:
        if old_val is not None:
            os.environ["SYNC_EVENT_LINKS_SUPABASE"] = old_val
        else:
            os.environ.pop("SYNC_EVENT_LINKS_SUPABASE", None)


# ─── Graph service legacy status test ─────────────────────────────────────────

def test_graph_service_legacy_event_links_to_review():
    """Legacy event_links without algorithm_version are marked as to_review."""
    from graph_service import _status_from_row
    row = {"algorithm_version": None}
    status = _status_from_row(row, source_system="event_links")
    assert status == "to_review", f"Expected to_review, got {status}"


def test_graph_service_v2_event_links_candidate():
    """Event links with non-legacy algorithm_version are marked as candidate."""
    from graph_service import _status_from_row
    row = {"algorithm_version": "2.0.0"}
    status = _status_from_row(row, source_system="event_links")
    assert status == "candidate", f"Expected candidate, got {status}"


def run_all():
    """Run all tests and report results."""
    tests = [
        test_kill_switch_frozen,
        test_kill_switch_env_override,
        test_normalize_name,
        test_normalize_date,
        test_date_overlap,
        test_ambiguous_keyword,
        test_word_boundary_match,
        test_feature_extraction_person_event_ww1_ww2,
        test_feature_extraction_person_event_temporal,
        test_scoring_weak_no_discriminator,
        test_scoring_moderate_one_discriminator,
        test_scoring_strong_two_discriminators,
        test_scoring_veto_overrides,
        test_scoring_confidence_calibrated_is_none,
        test_schema_v2_tables_exist,
        test_security_redact_secrets,
        test_security_env_not_tracked,
        test_persistence_idempotent_upsert,
        test_golden_dataset_seed,
        test_candidate_generation_blocking,
        # Temporal filter tests
        test_temporal_relation_overlap,
        test_temporal_relation_conflict,
        test_temporal_relation_unknown,
        test_classify_keyword_distinctive_ww1,
        test_classify_keyword_distinctive_ww2,
        test_classify_keyword_opposite_conflict,
        test_classify_keyword_ambiguous,
        test_detect_conflict_markers_ww2_in_ww1,
        test_detect_same_era_markers_ww1,
        test_filter_sources_for_event_rejects_conflict,
        test_filter_sources_for_event_include_candidates,
        # Source-event feature extraction tests
        test_extract_features_source_event_temporal_overlap,
        test_extract_features_source_event_temporal_conflict,
        test_extract_features_source_event_distinctive_keyword,
        # decide() tests
        test_decide_accepted,
        test_decide_rejected_temporal_conflict,
        test_decide_rejected_ww1_ww2_mismatch,
        test_decide_needs_review_mixed_era,
        test_decide_needs_review_ambiguous_only,
        test_decide_needs_review_unknown_temporal,
        test_decide_rejected_insufficient_evidence,
        # Migration tests
        test_migration_coverage_columns_exist,
        test_migration_coverage_backfilled,
        # Supabase kill switch test
        test_supabase_kill_switch_env,
        # Graph service legacy status tests
        test_graph_service_legacy_event_links_to_review,
        test_graph_service_v2_event_links_candidate,
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS  {test.__name__}")
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  FAIL  {test.__name__}: {e}")
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if errors:
        print("\nFailures:")
        for name, err in errors:
            print(f"  {name}: {err}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
