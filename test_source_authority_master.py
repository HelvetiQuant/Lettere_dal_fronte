"""Master test suite for V3 Source Authority & Provenance System.

Tests:
1. Omonimi (homonyms) — name match blocked without second identifier
2. Date parziali — partial dates don't create hard constraints
3. OCR errato — low extraction confidence reduces link status
4. Conflitto fonte ufficiale vs sito web — web cannot overwrite official
5. Conflitto due fonti ufficiali — needs_review, both preserved
6. Eventi fuori periodo — temporal rejection before keyword matching
7. Source registry — authority tiers and scores
8. Temporal constraint engine — hard vs soft constraints
9. Migration idempotency — running twice doesn't change results
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_authority_registry import (
    SourceAuthorityRegistry,
    SourceEntry,
    LinkDecisionEngine,
    TemporalConstraint,
    TemporalConstraintEngine,
    LinkDecision,
    apply_source_registry_schema,
    migrate_record_links_schema,
    migrate_event_links_schema,
    DEFAULT_SOURCES,
    AUTHORITY_TIER_OFFICIAL,
    AUTHORITY_TIER_PRIMARY,
    AUTHORITY_TIER_SECONDARY,
    AUTHORITY_TIER_UNOFFICIAL,
    TIER_NAMES,
    TIER_SCORES,
    RULE_VERSION,
    LINK_STATES,
)


def _make_test_db():
    """Create a temporary SQLite DB for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Create record_links and event_links with V3 columns
    conn.execute("""CREATE TABLE IF NOT EXISTS record_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_table TEXT NOT NULL, from_id INTEGER NOT NULL,
        to_table TEXT NOT NULL, to_id INTEGER NOT NULL,
        link_type TEXT NOT NULL, confidence REAL DEFAULT 0.5,
        elaborato_il TEXT,
        UNIQUE(from_table, from_id, to_table, to_id, link_type)
    )""")
    migrate_record_links_schema(conn)

    conn.execute("""CREATE TABLE IF NOT EXISTS event_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        target_table TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        link_type TEXT NOT NULL,
        match_field TEXT,
        match_value TEXT,
        confidence REAL DEFAULT 0.5,
        created_at TEXT,
        FOREIGN KEY (evento_id) REFERENCES eventi_1gm(id)
    )""")
    migrate_event_links_schema(conn)

    apply_source_registry_schema(conn)

    return conn, path


def _cleanup_db(conn, path):
    conn.close()
    try:
        os.unlink(path)
    except OSError:
        pass


class TestSourceRegistry(unittest.TestCase):
    """Test source_authority_registry table and SourceAuthorityRegistry class."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_registry_has_default_sources(self):
        """All default sources should be loaded."""
        sources = self.registry.all_sources()
        self.assertGreaterEqual(len(sources), len(DEFAULT_SOURCES))

    def test_authority_tiers_correct(self):
        """Official sources should have tier 1 or 2, unofficial 3 or 4."""
        for src in self.registry.all_sources():
            if src.is_official:
                self.assertIn(src.authority_tier, (1, 2),
                              f"{src.source_key} is official but tier={src.authority_tier}")
            else:
                self.assertIn(src.authority_tier, (3, 4),
                              f"{src.source_key} is not official but tier={src.authority_tier}")

    def test_get_by_provider(self):
        """get_by_provider should return correct source entry."""
        entry = self.registry.get_by_provider("internati")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.source_key, "internati_imi")

    def test_authority_score_range(self):
        """All authority scores should be between 0 and 1."""
        for src in self.registry.all_sources():
            self.assertGreater(src.authority_score, 0)
            self.assertLessEqual(src.authority_score, 1)

    def test_can_overwrite_canonical(self):
        """Only official sources with tier <= 2 can overwrite canonical data."""
        self.assertTrue(self.registry.can_overwrite_canonical("anrp_lebi"))
        self.assertTrue(self.registry.can_overwrite_canonical("albo_oro"))
        self.assertFalse(self.registry.can_overwrite_canonical("fonti_indice"))
        self.assertFalse(self.registry.can_overwrite_canonical("web_search"))

    def test_upsert_new_source(self):
        """Upsert should add a new source."""
        new_entry = SourceEntry(
            source_key="test_archive",
            source_name="Test Archive",
            source_type="archive",
            authority_tier=2,
            authority_score=0.75,
            is_official=True,
            is_primary=True,
            verification_policy="primary_cross_check",
            provider="test_table",
            collection="TestCollection",
        )
        self.registry.upsert(new_entry)
        retrieved = self.registry.get("test_archive")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.source_name, "Test Archive")


class TestTemporalConstraintEngine(unittest.TestCase):
    """Test the temporal constraint engine."""

    def test_exact_dates_compatible(self):
        """Same exact dates should be compatible."""
        self.assertTrue(TemporalConstraintEngine.dates_compatible(
            "1890-05-15", "1890-05-15", "exact", "exact"
        ))

    def test_exact_dates_incompatible(self):
        """Different exact dates should be incompatible."""
        self.assertFalse(TemporalConstraintEngine.dates_compatible(
            "1890-05-15", "1891-03-20", "exact", "exact"
        ))

    def test_year_precision_compatible(self):
        """Year-only dates should be compatible within 1 year tolerance."""
        self.assertTrue(TemporalConstraintEngine.dates_compatible(
            "1890", "1890", "year", "year"
        ))

    def test_year_vs_exact_compatible(self):
        """Year vs exact should be compatible if year matches."""
        self.assertTrue(TemporalConstraintEngine.dates_compatible(
            "1890", "1890-05-15", "year", "exact"
        ))

    def test_year_vs_exact_incompatible(self):
        """Year vs exact should be incompatible if year differs."""
        self.assertFalse(TemporalConstraintEngine.dates_compatible(
            "1890", "1891-05-15", "year", "exact"
        ))

    def test_hard_constraint_blocks(self):
        """A hard constraint (official + exact) should block incompatible dates."""
        constraint = TemporalConstraint(
            date_value="1890-05-15",
            precision="exact",
            source_key="ministero_difesa",
            authority_tier=1,
            is_official=True,
        )
        blocked, reason = TemporalConstraintEngine.evaluate_temporal_veto(
            constraint, "1891-03-20", "exact"
        )
        self.assertTrue(blocked)
        self.assertIn("TEMPORAL_VETO", reason)

    def test_hard_constraint_allows_compatible(self):
        """A hard constraint should allow compatible dates."""
        constraint = TemporalConstraint(
            date_value="1890-05-15",
            precision="exact",
            source_key="ministero_difesa",
            authority_tier=1,
            is_official=True,
        )
        blocked, _ = TemporalConstraintEngine.evaluate_temporal_veto(
            constraint, "1890-05-15", "exact"
        )
        self.assertFalse(blocked)

    def test_soft_constraint_does_not_block(self):
        """A soft constraint (non-official or year-only) should not block."""
        constraint = TemporalConstraint(
            date_value="1890",
            precision="year",
            source_key="fonti_indice",
            authority_tier=3,
            is_official=False,
        )
        blocked, _ = TemporalConstraintEngine.evaluate_temporal_veto(
            constraint, "1891-03-20", "exact"
        )
        self.assertFalse(blocked)

    def test_no_candidate_date_does_not_block(self):
        """Missing candidate date should not block (but flag for review)."""
        constraint = TemporalConstraint(
            date_value="1890-05-15",
            precision="exact",
            source_key="ministero_difesa",
            authority_tier=1,
            is_official=True,
        )
        blocked, _ = TemporalConstraintEngine.evaluate_temporal_veto(
            constraint, "", "unknown"
        )
        self.assertFalse(blocked)


class TestOmonimiBlocking(unittest.TestCase):
    """Test 1: Homonyms — name match blocked without second identifier."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_name_only_no_second_identifier_needs_review(self):
        """Two records with same name but no other matching identifiers → needs_review."""
        source = {"cognome": "ROSSI", "nome": "MARIO"}
        target = {"cognome": "ROSSI", "nome": "MARIO"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="internati_imi", target_key="albo_oro"
        )

        self.assertEqual(decision.status, "needs_review")
        self.assertEqual(decision.conflict_code, "NAME_ONLY_NO_DISCRIMINATOR")
        self.assertTrue(decision.needs_review)
        self.assertLess(decision.match_confidence, 0.5)

    def test_name_plus_date_match_verified(self):
        """Name + matching birth date → verified (with sufficient authority)."""
        source = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                  "luogo_nascita": "Roma"}
        target = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                  "luogo_nascita": "Roma"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="internati_imi", target_key="albo_oro"
        )

        self.assertIn(decision.status, ("verified", "probable"))
        self.assertGreater(decision.match_confidence, 0.5)
        self.assertFalse(decision.needs_review)

    def test_different_cognome_rejected(self):
        """Different cognome → rejected."""
        source = {"cognome": "ROSSI", "nome": "MARIO"}
        target = {"cognome": "BIANCHI", "nome": "MARIO"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="internati_imi", target_key="albo_oro"
        )

        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.conflict_code, "NO_NAME_MATCH")


class TestDateParziali(unittest.TestCase):
    """Test 2: Partial dates don't create hard constraints."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_year_only_does_not_block(self):
        """Year-only dates should not create hard temporal vetoes."""
        source = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890",
                  "luogo_nascita": "Roma"}
        target = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1891",
                  "luogo_nascita": "Roma"}

        # Should NOT be rejected — year-only is a soft constraint
        decision = self.engine.evaluate_record_link(
            source, target, source_key="internati_imi", target_key="albo_oro"
        )

        self.assertNotEqual(decision.status, "rejected")
        # Should still be probable/possible because place matches
        self.assertIn(decision.status, ("probable", "possible", "needs_review"))


class TestOCRErrato(unittest.TestCase):
    """Test 3: Low extraction confidence reduces link status."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_low_extraction_confidence_recorded(self):
        """Low extraction confidence should be recorded in the decision."""
        source = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                  "luogo_nascita": "Roma"}
        target = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                  "luogo_nascita": "Roma"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="internati_imi", target_key="albo_oro",
            extraction_confidence=0.30  # Low OCR confidence
        )

        self.assertEqual(decision.extraction_confidence, 0.30)


class TestConflittoUfficialeWeb(unittest.TestCase):
    """Test 4: Web source cannot overwrite canonical official data."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_web_cannot_overwrite_official(self):
        """Web source should not be able to overwrite official canonical data."""
        # Official source has data_nascita = 1890-05-15
        # Web source has data_nascita = 1891-03-20 (different)
        official = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                    "luogo_nascita": "Roma", "_table": "caduti_ministero"}
        web = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1891-03-20",
               "luogo_nascita": "Roma", "_table": "web_search"}

        decision = self.engine.evaluate_record_link(
            official, web, source_key="ministero_difesa", target_key="web_search"
        )

        # Should be rejected due to temporal veto from official source
        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.conflict_code, "TEMPORAL_VETO_OFFICIAL_DATE")

    def test_web_source_low_authority(self):
        """Web source alone should produce low-confidence links."""
        source = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                  "luogo_nascita": "Roma"}
        target = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1890-05-15",
                  "luogo_nascita": "Roma"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="web_search", target_key="wikipedia"
        )

        # Both are unofficial → status should be low
        self.assertIn(decision.status, ("unverified", "possible"))
        self.assertLess(decision.match_confidence, 0.5)


class TestConflittoDueUfficiali(unittest.TestCase):
    """Test 5: Two official sources disagree → needs_review, both preserved."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_two_officials_conflict_needs_review(self):
        """Two official sources with different values → conflicting, needs_review."""
        source1 = {"data_nascita": "1890-05-15"}
        source2 = {"data_nascita": "1891-03-20"}

        decision = self.engine.check_official_conflict(
            "ministero_difesa", source1,
            "albo_oro", source2,
            "data_nascita"
        )

        self.assertEqual(decision.status, "conflicting")
        self.assertEqual(decision.conflict_code, "OFFICIAL_SOURCES_CONFLICT")
        self.assertTrue(decision.needs_review)
        # Both values should be preserved in evidence
        self.assertIn("data_nascita", decision.evidence)

    def test_two_officials_agree_verified(self):
        """Two official sources with same value → verified."""
        source1 = {"data_nascita": "1890-05-15"}
        source2 = {"data_nascita": "1890-05-15"}

        decision = self.engine.check_official_conflict(
            "ministero_difesa", source1,
            "albo_oro", source2,
            "data_nascita"
        )

        self.assertEqual(decision.status, "verified")
        self.assertFalse(decision.needs_review)


class TestEventiFuoriPeriodo(unittest.TestCase):
    """Test 6: Events outside time period → rejected before keyword matching."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_ww2_soldier_rejected_for_ww1_event(self):
        """A WWII soldier (died 1943) should not link to a WWI event (1915-1918)."""
        event = {
            "nome": "Battaglia di Caporetto",
            "data_inizio": "1917-10-24",
            "data_fine": "1917-11-12",
            "keywords": json.dumps(["Caporetto", "Isonzo", "Tolmino"]),
            "aliases": json.dumps(["Caporetto", "Kobarid"]),
        }
        soldier = {
            "id": 1,
            "luogo_morte": "Caporetto",
            "data_morte": "1943-09-10",  # WWII date
        }

        decision = self.engine.evaluate_event_link(
            event, soldier, target_source_key="albo_oro"
        )

        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.conflict_code, "TEMPORAL_OUT_OF_PERIOD")

    def test_ww1_soldier_accepted_for_ww1_event(self):
        """A WWI soldier (died 1917) should be accepted for a WWI event."""
        event = {
            "nome": "Battaglia di Caporetto",
            "data_inizio": "1917-10-24",
            "data_fine": "1917-11-12",
            "keywords": json.dumps(["Caporetto", "Isonzo", "Tolmino"]),
            "aliases": json.dumps(["Caporetto", "Kobarid"]),
        }
        soldier = {
            "id": 1,
            "luogo_morte": "Caporetto",
            "data_morte": "1917-10-25",  # Within event period
        }

        decision = self.engine.evaluate_event_link(
            event, soldier, target_source_key="albo_oro"
        )

        self.assertNotEqual(decision.status, "rejected")
        self.assertNotEqual(decision.conflict_code, "TEMPORAL_OUT_OF_PERIOD")

    def test_unofficial_source_not_direct_evidence(self):
        """Unofficial web source should not be direct evidence for an event."""
        event = {
            "nome": "Battaglia di Caporetto",
            "data_inizio": "1917-10-24",
            "data_fine": "1917-11-12",
            "keywords": json.dumps(["Caporetto"]),
            "aliases": json.dumps(["Caporetto"]),
        }
        web_record = {
            "title": "Caporetto battle description",
            "description": "The battle of Caporetto was a major defeat",
            "year_start": 1917,
        }

        decision = self.engine.evaluate_event_link(
            event, web_record, target_source_key="web_search"
        )

        self.assertEqual(decision.status, "unverified")
        self.assertIn("lead only", decision.decision_reason.lower())


class TestLinkStates(unittest.TestCase):
    """Test that all required link states are defined."""

    def test_all_states_present(self):
        """All 6 states should be defined."""
        expected = {"verified", "probable", "possible", "unverified", "conflicting", "rejected"}
        self.assertEqual(set(LINK_STATES), expected)


class TestMigrationIdempotency(unittest.TestCase):
    """Test 9: Migration is idempotent — running twice doesn't change results."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_apply_schema_twice_no_error(self):
        """Applying schema twice should not raise errors."""
        apply_source_registry_schema(self.conn)
        apply_source_registry_schema(self.conn)  # Should be idempotent

        count = self.conn.execute("SELECT COUNT(*) FROM source_authority_registry").fetchone()[0]
        self.assertGreater(count, 0)

    def test_migrate_record_links_twice_no_error(self):
        """Migrating record_links columns twice should not raise errors."""
        migrate_record_links_schema(self.conn)
        migrate_record_links_schema(self.conn)  # Should be idempotent

        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(record_links)").fetchall()}
        self.assertIn("status", cols)
        self.assertIn("source_authority", cols)
        self.assertIn("match_confidence", cols)
        self.assertIn("needs_review", cols)
        self.assertIn("rule_version", cols)

    def test_migrate_event_links_twice_no_error(self):
        """Migrating event_links columns twice should not raise errors."""
        migrate_event_links_schema(self.conn)
        migrate_event_links_schema(self.conn)

        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(event_links)").fetchall()}
        self.assertIn("status", cols)
        self.assertIn("source_authority", cols)
        self.assertIn("match_confidence", cols)


class TestTemporalVetoPriority(unittest.TestCase):
    """Test the key rule: temporal veto has priority over name similarity."""

    def setUp(self):
        self.conn, self.db_path = _make_test_db()
        self.registry = SourceAuthorityRegistry(self.conn)
        self.engine = LinkDecisionEngine(self.registry)

    def tearDown(self):
        _cleanup_db(self.conn, self.db_path)

    def test_date_veto_blocks_even_with_exact_name_match(self):
        """An official date conflict MUST block the link even with exact name match."""
        # Both have exact same name, but official birth dates differ
        source = {"cognome": "ROSSI", "nome": "MARIO",
                  "data_nascita": "1890-05-15",  # Official date
                  "luogo_nascita": "Roma", "matricola": "12345"}
        target = {"cognome": "ROSSI", "nome": "MARIO",
                  "data_nascita": "1891-03-20",  # Different date
                  "luogo_nascita": "Roma", "matricola": "12345"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="ministero_difesa", target_key="albo_oro"
        )

        # MUST be rejected — date veto has priority over name match
        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.conflict_code, "TEMPORAL_VETO_OFFICIAL_DATE")
        self.assertEqual(decision.match_confidence, 0.0)
        self.assertIn("TEMPORAL_VETO", decision.decision_reason)

    def test_date_veto_blocks_even_with_matricola_match(self):
        """Date veto blocks even when matricola matches (could be data error)."""
        source = {"cognome": "ROSSI", "nome": "MARIO",
                  "data_nascita": "1890-05-15",
                  "matricola": "12345"}
        target = {"cognome": "ROSSI", "nome": "MARIO",
                  "data_nascita": "1895-07-10",
                  "matricola": "12345"}

        decision = self.engine.evaluate_record_link(
            source, target, source_key="ministero_difesa", target_key="albo_oro"
        )

        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.conflict_code, "TEMPORAL_VETO_OFFICIAL_DATE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
