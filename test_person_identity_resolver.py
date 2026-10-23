"""Unit tests for PersonIdentityResolver.

Tests cover:
- ALTA Antonio (common word surname)
- ARTI Saverio (common word surname)
- ARMANNO Luigi A (initial match)
- OCR variant matching
- Homonym rejection
- Conflicting identifiers
- Name parsing variations
- Query building
"""
import pytest
from person_identity_resolver import (
    PersonIdentityResolver,
    PersonMatchResult,
    ParsedName,
    parse_name,
    normalize_name,
    word_boundary_match,
    build_person_queries,
    RESOLVER_VERSION,
)


class TestNormalization:
    def test_normalize_name_basic(self):
        assert normalize_name("Rossi") == "rossi"
        assert normalize_name("D'Amico") == "damico"

    def test_normalize_name_accents(self):
        assert normalize_name("Nestor") == "nestor"
        assert normalize_name("Bianchi") == "bianchi"

    def test_normalize_name_empty(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""

    def test_word_boundary_match(self):
        assert word_boundary_match("alta montagna", "alta") == True
        assert word_boundary_match("Castellana", "lana") == False
        assert word_boundary_match("Romania", "Roma") == False


class TestNameParsing:
    def test_parse_with_db_fields(self):
        p = parse_name("ALTA Antonio", cognome_hint="ALTA", nome_hint="Antonio")
        assert p.cognome == "ALTA"
        assert p.nome == "Antonio"
        assert p.parse_rule == "db_fields"
        assert p.parse_confidence == 1.0

    def test_parse_comma_format(self):
        p = parse_name("Rossi, Mario")
        assert p.cognome == "ROSSI"
        assert p.nome == "Mario"
        assert p.parse_rule == "comma_split"

    def test_parse_single_token(self):
        p = parse_name("ALTA")
        assert p.cognome == "ALTA"
        assert p.nome == ""
        assert p.parse_confidence == 0.3

    def test_parse_first_uppercase_cognome(self):
        p = parse_name("ALTA Antonio")
        assert p.cognome == "ALTA"
        assert p.nome == "Antonio"
        assert p.parse_rule == "first_uppercase_cognome"

    def test_parse_initial_in_nome(self):
        p = parse_name("ARMANNO Luigi A.", cognome_hint="ARMANNO", nome_hint="Luigi A.")
        assert p.cognome == "ARMANNO"
        assert p.nome == "Luigi A."
        assert "A." in p.initials


class TestResolverALTA:
    """ALTA is a common Italian word — must not match 'alta montagna' etc."""

    def setup_method(self):
        self.resolver = PersonIdentityResolver()
        self.target = {
            "id": 2344,
            "cognome": "ALTA",
            "nome": "Antonio",
            "data_nascita": "1890-05-15",
            "luogo_nascita": "Torino",
            "matricola": "12345",
            "grado": "soldato",
            "reparto": "77 fanteria",
        }
        self.resolver.set_target("ALTA", "Antonio", record=self.target, target_id="2344")

    def test_exact_self_match_confirmed(self):
        """Same record should match itself as confirmed."""
        result = self.resolver.evaluate_source(
            source=self.target,
            source_kind="local_db",
            source_table="internati",
            source_id="2344",
        )
        assert result.status == "confirmed"
        assert "full_name_exact" in result.matched_features
        assert "matricola" in result.matched_features

    def test_surname_only_rejected(self):
        """A source with only 'ALTA' as surname but different nome should be rejected."""
        source = {"cognome": "ALTA", "nome": "Giovanni", "nominativo": "ALTA Giovanni"}
        result = self.resolver.evaluate_source(
            source=source, source_kind="web", source_table="web", source_id="1"
        )
        assert result.status in ("rejected", "ambiguous")
        assert "SURNAME_ONLY_MATCH" in result.reason_codes

    def test_irrelevant_source_rejected(self):
        """A source with completely different name should be rejected."""
        source = {"cognome": "Rossi", "nome": "Mario", "nominativo": "Rossi Mario"}
        result = self.resolver.evaluate_source(
            source=source, source_kind="web", source_table="web", source_id="2"
        )
        assert result.status == "rejected"
        assert "NO_COGNOME_MATCH" in result.reason_codes

    def test_conflicting_matricola_rejected(self):
        """Same name but different matricola should be rejected."""
        source = {
            "cognome": "ALTA", "nome": "Antonio",
            "matricola": "99999",
            "data_nascita": "1890-05-15",
        }
        result = self.resolver.evaluate_source(
            source=source, source_kind="web", source_table="web", source_id="3"
        )
        assert result.status == "rejected"
        assert any("CONFLICT" in r for r in result.reason_codes)


class TestResolverARTI:
    """ARTI is also a common Italian word."""

    def setup_method(self):
        self.resolver = PersonIdentityResolver()
        self.target = {
            "id": 2350,
            "cognome": "ARTI",
            "nome": "Saverio",
            "data_nascita": "1888-03-20",
            "luogo_nascita": "Roma",
            "matricola": "67890",
        }
        self.resolver.set_target("ARTI", "Saverio", record=self.target, target_id="2350")

    def test_exact_match_confirmed(self):
        result = self.resolver.evaluate_source(
            source=self.target,
            source_kind="local_db",
            source_table="internati",
            source_id="2350",
        )
        assert result.status == "confirmed"

    def test_different_name_same_surname_rejected(self):
        source = {"cognome": "ARTI", "nome": "Francesco"}
        result = self.resolver.evaluate_source(
            source=source, source_kind="web", source_table="web", source_id="1"
        )
        assert result.status in ("rejected", "ambiguous")


class TestResolverARMANNO:
    """ARMANNO Luigi A — test initial matching."""

    def setup_method(self):
        self.resolver = PersonIdentityResolver()
        self.target = {
            "id": 2357,
            "cognome": "ARMANNO",
            "nome": "Luigi A",
            "data_nascita": "1892-01-10",
            "luogo_nascita": "Cuneo",
            "matricola": "11111",
        }
        self.resolver.set_target("ARMANNO", "Luigi A", record=self.target, target_id="2357")

    def test_initial_match_probable(self):
        """Source with 'Luigi Antonio' should match target 'Luigi A' as initial."""
        source = {
            "cognome": "ARMANNO", "nome": "Luigi Antonio",
            "data_nascita": "1892-01-10",
            "luogo_nascita": "Cuneo",
        }
        result = self.resolver.evaluate_source(
            source=source, source_kind="web", source_table="web", source_id="1"
        )
        assert result.status == "probable"
        assert "nome_initial_match" in result.matched_features

    def test_full_name_exact_confirmed(self):
        result = self.resolver.evaluate_source(
            source=self.target,
            source_kind="local_db",
            source_table="internati",
            source_id="2357",
        )
        assert result.status == "confirmed"


class TestResolverOCR:
    """Test OCR variant handling."""

    def setup_method(self):
        self.resolver = PersonIdentityResolver()
        self.target = {
            "id": 2360,
            "cognome": "ANFOSSO",
            "nome": "Carlo",
            "data_nascita": "1885-07-22",
            "luogo_nascita": "Genova",
            "matricola": "22222",
        }
        self.resolver.set_target("ANFOSSO", "Carlo", record=self.target, target_id="2360")

    def test_exact_match(self):
        result = self.resolver.evaluate_source(
            source=self.target,
            source_kind="local_db",
            source_table="internati",
            source_id="2360",
        )
        assert result.status == "confirmed"


class TestResolverAMAROTTI:
    def setup_method(self):
        self.resolver = PersonIdentityResolver()
        self.target = {
            "id": 2353,
            "cognome": "AMAROTTI",
            "nome": "Enrico",
            "data_nascita": "1893-11-05",
            "luogo_nascita": "Bologna",
            "matricola": "33333",
        }
        self.resolver.set_target("AMAROTTI", "Enrico", record=self.target, target_id="2353")

    def test_exact_match(self):
        result = self.resolver.evaluate_source(
            source=self.target,
            source_kind="local_db",
            source_table="internati",
            source_id="2353",
        )
        assert result.status == "confirmed"

    def test_no_cognome_match(self):
        source = {"cognome": "AMARANTO", "nome": "Enrico"}
        result = self.resolver.evaluate_source(
            source=source, source_kind="web", source_table="web", source_id="1"
        )
        assert result.status == "rejected"


class TestResolverANVISIO:
    def setup_method(self):
        self.resolver = PersonIdentityResolver()
        self.target = {
            "id": 2356,
            "cognome": "ANVISIO",
            "nome": "Remo",
            "data_nascita": "1891-09-14",
            "luogo_nascita": "Milano",
            "matricola": "44444",
        }
        self.resolver.set_target("ANVISIO", "Remo", record=self.target, target_id="2356")

    def test_exact_match(self):
        result = self.resolver.evaluate_source(
            source=self.target,
            source_kind="local_db",
            source_table="internati",
            source_id="2356",
        )
        assert result.status == "confirmed"


class TestQueryBuilding:
    def test_basic_queries(self):
        queries = build_person_queries("ALTA", "Antonio", {"luogo_nascita": "Torino", "matricola": "12345"})
        assert len(queries) >= 3  # At least nominative_exact, reversed, comma
        assert any(q["purpose"] == "nominative_exact" for q in queries)
        assert any(q["purpose"] == "nominative_reversed" for q in queries)

    def test_queries_with_birth_place(self):
        queries = build_person_queries("ALTA", "Antonio", {"luogo_nascita": "Torino"})
        assert any(q["purpose"] == "name_plus_birth_place" for q in queries)

    def test_queries_with_matricola(self):
        queries = build_person_queries("ALTA", "Antonio", {"matricola": "12345"})
        assert any(q["purpose"] == "name_plus_matricola" for q in queries)

    def test_queries_empty_record(self):
        queries = build_person_queries("Rossi", "Mario", {})
        assert len(queries) == 3  # Only nominative variants


class TestResolverCounts:
    def test_counts(self):
        resolver = PersonIdentityResolver()
        resolver.set_target("ALTA", "Antonio", record={"id": 1, "matricola": "123"}, target_id="1")

        # Evaluate multiple sources
        resolver.evaluate_source(
            source={"cognome": "ALTA", "nome": "Antonio", "matricola": "123"},
            source_kind="local_db", source_table="internati", source_id="1"
        )
        resolver.evaluate_source(
            source={"cognome": "ALTA", "nome": "Giovanni"},
            source_kind="web", source_table="web", source_id="2"
        )
        resolver.evaluate_source(
            source={"cognome": "Rossi", "nome": "Mario"},
            source_kind="web", source_table="web", source_id="3"
        )

        counts = resolver.get_counts()
        assert counts["web_candidates_seen"] == 3
        assert counts["person_sources_confirmed"] == 1
        assert counts["person_candidates_rejected"] >= 1


class TestResolverVersion:
    def test_version(self):
        assert RESOLVER_VERSION == "1.0.0"
        r = PersonMatchResult.__dataclass_fields__["resolver_version"].default
        assert r == RESOLVER_VERSION
