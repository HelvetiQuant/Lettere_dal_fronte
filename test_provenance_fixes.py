"""
Master test suite for provenance-aware linking and canonical mapping fixes.

Tests cover:
1. Canonical resolver — entity resolution, stable_id, claim fingerprint
2. Source classification — historical vs non-historical domains
3. Person name validation — multi-level filtering of false positives
4. Outbox idempotency — no duplicates after retry
5. Outbox backoff — exponential with jitter
6. Error classification — retryable vs permanent
7. Claim mapping — SQLite → Supabase evidence.claims
8. Source mapping — SQLite → Supabase archive.external_items
9. Entity mapping — SQLite → Supabase core.entities
10. AI status capping — AI cannot assign verified/confirmed
11. Graph service — to_review filtering with include_to_review
12. Schema migration — 004_expose_core_schema.sql syntax
13. Regression — existing linking v2 tests still pass

Run: python test_provenance_fixes.py
     python -m pytest test_provenance_fixes.py -v
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


# ═══ 1. Canonical Resolver ═══════════════════════════════════════════════════

def test_generate_stable_id_deterministic():
    """Stable IDs must be deterministic across calls."""
    from canonical_resolver import generate_stable_id
    a = generate_stable_id("person", "Rossi Mario", "sqlite", "123")
    b = generate_stable_id("person", "Rossi Mario", "sqlite", "123")
    assert a == b, f"Non-deterministic: {a} != {b}"
    assert a.startswith("sha256:"), f"Expected sha256 prefix: {a}"


def test_generate_stable_id_different_inputs():
    """Different inputs produce different stable IDs."""
    from canonical_resolver import generate_stable_id
    a = generate_stable_id("person", "Rossi Mario", "sqlite", "123")
    b = generate_stable_id("person", "Bianchi Luigi", "sqlite", "456")
    assert a != b, "Different inputs should produce different stable IDs"


def test_normalize_subject_type():
    """Subject type normalization maps legacy types to canonical."""
    from canonical_resolver import normalize_subject_type
    assert normalize_subject_type("soldier") == "person"
    assert normalize_subject_type("SOLDIER") == "person"
    assert normalize_subject_type("unit") == "military_unit"
    assert normalize_subject_type("event") == "event"
    assert normalize_subject_type("place") == "place"


def test_claim_fingerprint_deterministic():
    """Claim fingerprints must be deterministic and source-independent."""
    from canonical_resolver import claim_fingerprint
    a = claim_fingerprint("sha256:abc", "birth_date", "1890-05-15", "date")
    b = claim_fingerprint("sha256:abc", "birth_date", "1890-05-15", "date")
    assert a == b, "Same claim should produce same fingerprint"
    c = claim_fingerprint("sha256:xyz", "birth_date", "1890-05-15", "date")
    assert a != c, "Different subjects should produce different fingerprints"


def test_claim_fingerprint_source_independent():
    """Same claim from different sources should produce same fingerprint."""
    from canonical_resolver import claim_fingerprint
    a = claim_fingerprint("sha256:ent1", "death_date", "1917-10-24", "date")
    b = claim_fingerprint("sha256:ent1", "death_date", "1917-10-24", "date")
    assert a == b, "Fingerprint should not depend on source"


def test_canonical_resolver_lookup_existing():
    """CanonicalResolver finds existing entities in discovered_entities."""
    from canonical_resolver import CanonicalResolver
    from canonical_resolver import generate_stable_id

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE discovered_entities (
                canonical_id TEXT PRIMARY KEY,
                entity_type TEXT,
                canonical_label TEXT,
                status TEXT DEFAULT 'candidate',
                discovery_parent_type TEXT,
                discovery_parent_id TEXT,
                created_at TEXT
            )
        """)
        stable_id = generate_stable_id("person", "Rossi Mario", "sqlite", "1")
        conn.execute(
            "INSERT INTO discovered_entities (canonical_id, entity_type, canonical_label, status) VALUES (?,?,?,?)",
            (stable_id, "person", "Rossi Mario", "candidate")
        )
        conn.commit()

        resolver = CanonicalResolver(conn)
        entity = resolver.resolve_canonical_entity("person", "1", "sqlite", "", "Rossi Mario")
        assert entity is not None
        assert entity.stable_id == stable_id
        assert entity.verification_status == "candidate"
        conn.close()
    finally:
        os.unlink(db_path)


def test_canonical_resolver_creates_new():
    """CanonicalResolver creates new candidate for unknown entities."""
    from canonical_resolver import CanonicalResolver

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE discovered_entities (
                canonical_id TEXT PRIMARY KEY,
                entity_type TEXT,
                canonical_label TEXT,
                status TEXT DEFAULT 'candidate',
                discovery_parent_type TEXT,
                discovery_parent_id TEXT,
                created_at TEXT
            )
        """)
        conn.commit()

        resolver = CanonicalResolver(conn)
        entity = resolver.resolve_canonical_entity("person", "999", "sqlite", "", "Verdi Giovanni")
        assert entity is not None
        assert entity.verification_status == "candidate"
        assert entity.canonical_name == "Verdi Giovanni"
        conn.close()
    finally:
        os.unlink(db_path)


# ═══ 2. Source Classification ════════════════════════════════════════════════

def test_classify_source_out_of_scope():
    """Non-historical domains are classified as out_of_scope."""
    from canonical_resolver import classify_source
    assert classify_source("https://www.booking.com/hotel/roma") == "out_of_scope"
    assert classify_source("https://www.tripadvisor.it/attractions") == "out_of_scope"
    assert classify_source("https://www.facebook.com/page") == "out_of_scope"


def test_classify_source_search_page():
    """Search page URLs are classified as discovery_only."""
    from canonical_resolver import classify_source
    assert classify_source("https://www.archivio.it/search?q=rossi") == "discovery_only"
    assert classify_source("https://www.archivio.it/ricerca?nome=mario") == "discovery_only"


def test_classify_source_geographic():
    """Pure geographic pages without military keywords are geographic_context."""
    from canonical_resolver import classify_source
    assert classify_source("https://www.comune.roma.it/storia") == "geographic_context"
    assert classify_source("https://www.turismo.valcamonica.it") == "geographic_context"


def test_classify_source_historical_context():
    """Encyclopedia domains are historical_context."""
    from canonical_resolver import classify_source
    assert classify_source("https://www.treccani.it/enciclopedia/guerra") == "historical_context"


def test_classify_source_default_discovery():
    """Unknown URLs default to discovery_only (conservative)."""
    from canonical_resolver import classify_source
    assert classify_source("https://www.example.com/page") == "discovery_only"


# ═══ 3. Person Name Validation ═══════════════════════════════════════════════

def test_valid_person_name_accepted():
    """Valid person names pass validation."""
    from discovery_persistence import _is_valid_person_name
    assert _is_valid_person_name("Rossi Mario")
    assert _is_valid_person_name("Bianchi Luigi Giovanni")
    assert _is_valid_person_name("Negre Francois")


def test_invalid_person_name_rejected():
    """Invalid names are rejected."""
    from discovery_persistence import _is_valid_person_name
    assert not _is_valid_person_name("CONFERMA CANDIDATI")
    assert not _is_valid_person_name("DATI TROVATI")
    assert not _is_valid_person_name("FONTI CONSULTATE")
    assert not _is_valid_person_name("WWI WWII")
    assert not _is_valid_person_name("IL LO")
    assert not _is_valid_person_name("DI DA")
    assert not _is_valid_person_name("Rossi123")


def test_short_names_rejected():
    """Names shorter than 5 chars are rejected."""
    from discovery_persistence import _is_valid_person_name
    assert not _is_valid_person_name("Ro Ma")
    assert not _is_valid_person_name("A B")


def test_single_token_rejected():
    """Single-token strings are not valid person names."""
    from discovery_persistence import _is_valid_person_name
    assert not _is_valid_person_name("Rossi")
    assert not _is_valid_person_name("Mario")


def test_extract_person_names_filters_false_positives():
    """_extract_person_names filters out section headers and common words."""
    from discovery_persistence import _extract_person_names
    text = """
    CONFERMA CANDIDATI: Rossi Mario trovato.
    DATI TROVATI: nato il 15/05/1890.
    FONTI CONSULTATE: Archivio di Stato.
    Testimone: Bianchi Luigi ha confermato.
    WWI e WWII sono conflitti diversi.
    Il tenente Verdi Giovanni era presente.
    """
    names = _extract_person_names(text, "Rossi Mario")
    # Should find Bianchi Luigi and Verdi Giovanni
    # Should NOT find CONFERMA CANDIDATI, DATI TROVATI, FONTI CONSULTATE, WWI WWII
    assert "Bianchi Luigi" in names, f"Expected Bianchi Luigi in {names}"
    assert "Verdi Giovanni" in names, f"Expected Verdi Giovanni in {names}"
    assert "CONFERMA CANDIDATI" not in names
    assert "DATI TROVATI" not in names
    assert "FONTI CONSULTATE" not in names
    assert "WWI WWII" not in names
    assert "Rossi Mario" not in names  # subject excluded


def test_extract_person_names_excludes_subject():
    """Subject name is excluded from results."""
    from discovery_persistence import _extract_person_names
    text = "Rossi Mario era presente. Bianchi Luigi anche."
    names = _extract_person_names(text, "Rossi Mario")
    assert "Rossi Mario" not in names
    assert "Bianchi Luigi" in names


# ═══ 4. Outbox Idempotency ═══════════════════════════════════════════════════

def test_enqueue_sync_idempotent():
    """_enqueue_sync does not create duplicates for same canonical_id:table."""
    from discovery_persistence import _enqueue_sync, _ensure_schema, SCHEMA_SQL
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        conn.commit()

        _enqueue_sync(conn, "ent1", "source_registry", {"url": "http://example.com"})
        _enqueue_sync(conn, "ent1", "source_registry", {"url": "http://example.com/v2"})
        rows = conn.execute("SELECT * FROM sync_outbox").fetchall()
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        # Payload should be updated
        payload = json.loads(rows[0]["payload"])
        assert payload["url"] == "http://example.com/v2"
        conn.close()
    finally:
        os.unlink(db_path)


def test_enqueue_sync_different_tables():
    """Same canonical_id with different table_name creates separate entries."""
    from discovery_persistence import _enqueue_sync
    from discovery_persistence import SCHEMA_SQL
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        conn.commit()

        _enqueue_sync(conn, "ent1", "source_registry", {"a": 1})
        _enqueue_sync(conn, "ent1", "historical_claims", {"b": 2})
        rows = conn.execute("SELECT * FROM sync_outbox").fetchall()
        assert len(rows) == 2
        conn.close()
    finally:
        os.unlink(db_path)


# ═══ 5. Outbox Backoff ═══════════════════════════════════════════════════════

def test_compute_backoff_increases():
    """Backoff increases with retry count."""
    from discovery_persistence import _compute_backoff
    b0 = _compute_backoff(0)
    b1 = _compute_backoff(1)
    b3 = _compute_backoff(3)
    assert b0 < b1 < b3, f"Backoff should increase: {b0} < {b1} < {b3}"


def test_compute_backoff_capped():
    """Backoff is capped at 300 seconds."""
    from discovery_persistence import _compute_backoff
    b = _compute_backoff(20)
    assert b <= 330, f"Backoff should be capped: {b}"  # cap + 10% jitter


# ═══ 6. Error Classification ═════════════════════════════════════════════════

def test_classify_error_permanent():
    """Schema/column errors are permanent."""
    from discovery_persistence import _classify_error
    assert _classify_error("column 'foo' does not exist") == "permanent_error"
    assert _classify_error("invalid input syntax for type bigint") == "permanent_error"
    assert _classify_error("violates foreign key constraint") == "permanent_error"
    assert _classify_error("duplicate key value violates unique constraint") == "permanent_error"


def test_classify_error_retryable():
    """Network/timeout errors are retryable."""
    from discovery_persistence import _classify_error
    assert _classify_error("Connection refused") == "retryable_error"
    assert _classify_error("timeout") == "retryable_error"
    assert _classify_error("503 Service Unavailable") == "retryable_error"


# ═══ 7. Claim Mapping ════════════════════════════════════════════════════════

def test_map_claim_status_capped():
    """AI cannot assign verified/confirmed/accepted statuses."""
    from canonical_resolver import cap_ai_status
    assert cap_ai_status("verified") == "discovered"
    assert cap_ai_status("confirmed") == "discovered"
    assert cap_ai_status("accepted") == "discovered"
    assert cap_ai_status("unverified") == "discovered"
    assert cap_ai_status("corroborated") == "supported"
    assert cap_ai_status("conflicting") == "conflicting"


def test_normalize_predicate():
    """Predicates are normalized to lowercase with underscores."""
    from canonical_resolver import normalize_predicate
    assert normalize_predicate("Birth Date") == "birth_date"
    assert normalize_predicate("MILITARY_UNIT") == "military_unit"
    assert normalize_predicate("  Rank  ") == "rank"


def test_claim_mapping_filters_columns():
    """Claim mapping only includes columns in CLAIMS_ALLOWED_COLUMNS."""
    from canonical_resolver import map_local_claim_to_remote, CanonicalResolver
    from canonical_resolver import CLAIMS_ALLOWED_COLUMNS

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE discovered_entities (
                canonical_id TEXT PRIMARY KEY,
                entity_type TEXT,
                canonical_label TEXT,
                status TEXT DEFAULT 'candidate',
                discovery_parent_type TEXT,
                discovery_parent_id TEXT,
                created_at TEXT
            )
        """)
        conn.commit()

        class FakeClaim:
            canonical_id = "sha256:test1"
            subject_type = "soldier"
            subject_id = "123"
            predicate = "birth_date"
            normalized_value = "1890-05-15"
            original_value = "15/05/1890"
            value_type = "date"
            status = "unverified"
            extraction_method = "ai_extraction"
            source_id = "src1"
            source_locator = ""
            conflict_code = ""

        resolver = CanonicalResolver(conn)
        payload, evidence = map_local_claim_to_remote(FakeClaim(), resolver)
        for key in payload:
            assert key in CLAIMS_ALLOWED_COLUMNS, f"Column {key} not in allowed list"
        assert payload["predicate"] == "birth_date"
        assert payload["claim_status"] == "discovered"  # capped from unverified
        conn.close()
    finally:
        os.unlink(db_path)


# ═══ 8. Source Mapping ═══════════════════════════════════════════════════════

def test_map_source_filters_columns():
    """Source mapping only includes columns in EXTERNAL_ITEMS_ALLOWED_COLUMNS."""
    from canonical_resolver import map_local_source_to_remote, EXTERNAL_ITEMS_ALLOWED_COLUMNS

    class FakeSource:
        canonical_id = "sha256:src1"
        canonical_url = "https://example.com/doc"
        original_url = "https://example.com/doc"
        source_title = "Test Document"
        source_type = "web_source"
        content_sha256 = "abc123"
        http_status = 200
        last_verified_at = "2026-07-31T12:00:00"
        language = "it"
        archival_reference = "REF-001"
        publication_or_record_date = "1917"

    payload = map_local_source_to_remote(FakeSource())
    for key in payload:
        assert key in EXTERNAL_ITEMS_ALLOWED_COLUMNS, f"Column {key} not in allowed list"
    assert payload["stable_id"] == "sha256:src1"
    assert payload["canonical_url"] == "https://example.com/doc"
    assert payload["review_status"] == "candidate"


def test_map_source_no_url_raises():
    """Source without URL raises PermanentPayloadError."""
    from canonical_resolver import map_local_source_to_remote, PermanentPayloadError

    class FakeSource:
        canonical_id = "sha256:src2"
        canonical_url = ""
        original_url = ""
        source_title = "No URL"
        source_type = "web_source"
        content_sha256 = ""
        http_status = None
        last_verified_at = None
        language = ""
        archival_reference = ""
        publication_or_record_date = ""

    try:
        map_local_source_to_remote(FakeSource())
        assert False, "Should have raised PermanentPayloadError"
    except PermanentPayloadError:
        pass


# ═══ 9. Entity Mapping ═══════════════════════════════════════════════════════

def test_map_entity_caps_status():
    """Entity mapping caps AI-forbidden statuses to candidate."""
    from canonical_resolver import map_local_entity_to_remote, ENTITIES_ALLOWED_COLUMNS

    class FakeEntity:
        canonical_id = "sha256:ent1"
        entity_type = "person"
        canonical_label = "Rossi Mario"
        status = "verified"  # AI-forbidden
        discovery_parent_type = "soldier"
        discovery_parent_id = "123"

    payload = map_local_entity_to_remote(FakeEntity())
    for key in payload:
        assert key in ENTITIES_ALLOWED_COLUMNS, f"Column {key} not in allowed list"
    assert payload["verification_status"] == "candidate"  # capped


# ═══ 10. Graph Service include_to_review ═════════════════════════════════════

def test_graph_service_include_to_review_param():
    """GraphBuilder accepts include_to_review parameter."""
    from graph_service import GraphBuilder
    builder = GraphBuilder(include_to_review=False)
    assert builder.include_to_review is False
    builder.close()


def test_graph_service_default_include_to_review():
    """GraphBuilder defaults include_to_review to True."""
    from graph_service import GraphBuilder
    builder = GraphBuilder()
    assert builder.include_to_review is True
    builder.close()


# ═══ 11. Schema Migration 004 ════════════════════════════════════════════════

def test_migration_004_exists():
    """Migration file 004_expose_core_schema.sql exists."""
    sql_path = ROOT / "sql" / "004_expose_core_schema.sql"
    assert sql_path.exists(), f"Migration file not found: {sql_path}"


def test_migration_004_has_grants():
    """Migration 004 includes GRANT statements for core schema."""
    sql_path = ROOT / "sql" / "004_expose_core_schema.sql"
    content = sql_path.read_text(encoding="utf-8")
    assert "GRANT USAGE ON SCHEMA core" in content
    assert "GRANT SELECT ON core.entities" in content or "GRANT SELECT" in content
    assert "ENABLE ROW LEVEL SECURITY" in content


def test_migration_004_has_entity_mapping():
    """Migration 004 creates core.entity_mapping table."""
    sql_path = ROOT / "sql" / "004_expose_core_schema.sql"
    content = sql_path.read_text(encoding="utf-8")
    assert "core.entity_mapping" in content
    assert "UNIQUE(local_source_system, local_table, local_id)" in content


# ═══ 12. Supabase Client VALID_SCHEMAS ═══════════════════════════════════════

def test_supabase_valid_schemas_includes_core():
    """VALID_SCHEMAS in supabase_client includes 'core'."""
    from supabase_client import VALID_SCHEMAS
    assert "core" in VALID_SCHEMAS, f"core not in VALID_SCHEMAS: {VALID_SCHEMAS}"


# ═══ 13. Regression — Linking v2 ═════════════════════════════════════════════

def test_regression_kill_switch_frozen():
    """Legacy jobs remain frozen."""
    from linking.kill_switch import LegacyJob, is_legacy_job_enabled
    for job in LegacyJob:
        assert not is_legacy_job_enabled(job), f"{job.value} should be frozen"


def test_regression_scoring_accepted():
    """Scoring still accepts strong evidence pairs."""
    from linking.scoring import score_candidate, decide
    from linking.feature_extraction import Features, ConflictFlags
    f = Features(
        name_match=True,
        name_cognome_exact=True,
        birth_date_compatible=True,
        same_matricola=True,
        temporal_overlap=True,
        discriminators=["name_cognome_exact", "birth_date_compatible", "same_matricola"],
    )
    cf = ConflictFlags()
    result = score_candidate(f, cf)
    assert result.raw_score > 0
    decision = decide(f, cf)
    assert decision.status == "accepted"


def test_regression_scoring_veto_temporal():
    """Temporal conflict still triggers veto."""
    from linking.scoring import score_candidate, decide
    from linking.feature_extraction import Features, ConflictFlags
    f = Features(discriminators=["name_cognome_exact"])
    cf = ConflictFlags(temporal_conflict=True)
    result = score_candidate(f, cf)
    decision = decide(f, cf)
    assert decision.status == "rejected"


# ═══ 14. Runbook ═════════════════════════════════════════════════════════════

def test_runbook_core_schema_exists():
    """Runbook for core schema exposure exists."""
    runbook = ROOT / "docs" / "runbook" / "RUNBOOK_SUPABASE_CORE_SCHEMA.md"
    assert runbook.exists(), f"Runbook not found: {runbook}"


# ═══ Runner ══════════════════════════════════════════════════════════════════

def run_all():
    tests = [
        # Canonical resolver
        test_generate_stable_id_deterministic,
        test_generate_stable_id_different_inputs,
        test_normalize_subject_type,
        test_claim_fingerprint_deterministic,
        test_claim_fingerprint_source_independent,
        test_canonical_resolver_lookup_existing,
        test_canonical_resolver_creates_new,
        # Source classification
        test_classify_source_out_of_scope,
        test_classify_source_search_page,
        test_classify_source_geographic,
        test_classify_source_historical_context,
        test_classify_source_default_discovery,
        # Person name validation
        test_valid_person_name_accepted,
        test_invalid_person_name_rejected,
        test_short_names_rejected,
        test_single_token_rejected,
        test_extract_person_names_filters_false_positives,
        test_extract_person_names_excludes_subject,
        # Outbox idempotency
        test_enqueue_sync_idempotent,
        test_enqueue_sync_different_tables,
        # Outbox backoff
        test_compute_backoff_increases,
        test_compute_backoff_capped,
        # Error classification
        test_classify_error_permanent,
        test_classify_error_retryable,
        # Claim mapping
        test_map_claim_status_capped,
        test_normalize_predicate,
        test_claim_mapping_filters_columns,
        # Source mapping
        test_map_source_filters_columns,
        test_map_source_no_url_raises,
        # Entity mapping
        test_map_entity_caps_status,
        # Graph service
        test_graph_service_include_to_review_param,
        test_graph_service_default_include_to_review,
        # Schema migration
        test_migration_004_exists,
        test_migration_004_has_grants,
        test_migration_004_has_entity_mapping,
        # Supabase client
        test_supabase_valid_schemas_includes_core,
        # Regression
        test_regression_kill_switch_frozen,
        test_regression_scoring_accepted,
        test_regression_scoring_veto_temporal,
        # Runbook
        test_runbook_core_schema_exists,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        print(f"\nFailures:")
        for test in tests:
            try:
                test()
            except Exception as e:
                print(f"  {test.__name__}: {e}")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
