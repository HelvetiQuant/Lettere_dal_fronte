"""Expanded test suite for research protocol structural fixes.

Covers:
- Manifest immutability, completeness, substitution detection
- Provider capability routing (WWI/WWII filter)
- Circuit breaker for Web Search
- EvidenceSnapshot versioning and citation validation
- 7 additional subject drift cases (Giunta, Veneziano, Fantuz, Fedele, Russo)
- Property-based test: any name with incompatible features is rejected
- No special-case code for sentinel names in production
- Run status: COMPLETE requires all expected targets
"""

import pytest
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from unittest.mock import MagicMock, patch


# ════════════════════════════════════════════════════════════════════════════
# 6. MANIFEST SYSTEM
# ════════════════════════════════════════════════════════════════════════════

class TestManifest:
    """Manifest is immutable, versioned, and validates completeness."""

    def test_manifest_hash_stable(self):
        from research_manifest import build_manifest
        targets = [
            {"ordinal": 1, "target_id": "WWI-001", "target_type": "person",
             "conflict": "ww1", "raw_input": {"cognome": "LARI", "nome": "GIUSEPPE"}},
            {"ordinal": 2, "target_id": "WWI-002", "target_type": "person",
             "conflict": "ww1", "raw_input": {"cognome": "PAPINI", "nome": "PUBLIO"}},
        ]
        m1 = build_manifest("run-1", "people-only", targets)
        m2 = build_manifest("run-1", "people-only", targets)
        assert m1.manifest_hash == m2.manifest_hash

    def test_manifest_hash_differs_for_different_targets(self):
        from research_manifest import build_manifest
        t1 = [{"ordinal": 1, "target_id": "A", "target_type": "person",
               "conflict": "ww1", "raw_input": {"cognome": "X"}}]
        t2 = [{"ordinal": 1, "target_id": "A", "target_type": "person",
               "conflict": "ww1", "raw_input": {"cognome": "Y"}}]
        m1 = build_manifest("run-1", "people-only", t1)
        m2 = build_manifest("run-1", "people-only", t2)
        assert m1.manifest_hash != m2.manifest_hash

    def test_manifest_rejects_duplicate_ordinals(self):
        from research_manifest import build_manifest
        targets = [
            {"ordinal": 1, "target_id": "A", "target_type": "person", "conflict": "ww1", "raw_input": {}},
            {"ordinal": 1, "target_id": "B", "target_type": "person", "conflict": "ww1", "raw_input": {}},
        ]
        with pytest.raises(ValueError, match="Duplicate ordinals"):
            build_manifest("run-1", "people-only", targets)

    def test_manifest_rejects_duplicate_target_ids(self):
        from research_manifest import build_manifest
        targets = [
            {"ordinal": 1, "target_id": "A", "target_type": "person", "conflict": "ww1", "raw_input": {}},
            {"ordinal": 2, "target_id": "A", "target_type": "person", "conflict": "ww1", "raw_input": {}},
        ]
        with pytest.raises(ValueError, match="Duplicate target_ids"):
            build_manifest("run-1", "people-only", targets)

    def test_manifest_expected_matches_actual(self):
        from research_manifest import build_manifest
        targets = [
            {"ordinal": i, "target_id": f"T{i}", "target_type": "person",
             "conflict": "ww1", "raw_input": {"n": i}}
            for i in range(1, 11)
        ]
        m = build_manifest("run-1", "people-only", targets)
        assert m.expected_targets == 10
        assert len(m.targets) == 10

    def test_run_status_complete_only_if_all_completed(self):
        from research_manifest import RunStatus, RunState, TargetPhase
        rs = RunStatus(run_id="r1", manifest_hash="h", expected=10, scope="people-only")
        for i in range(10):
            rs.update_target_phase(f"T{i+1}", TargetPhase.COMPLETED)
        assert rs.state == RunState.SUCCESS

    def test_run_status_partial_if_missing(self):
        from research_manifest import RunStatus, RunState, TargetPhase
        rs = RunStatus(run_id="r1", manifest_hash="h", expected=10, scope="people-only")
        for i in range(8):
            rs.update_target_phase(f"T{i+1}", TargetPhase.COMPLETED)
        rs.missing_target_ids = ["T9", "T10"]
        rs.finalize()
        assert rs.state == RunState.PARTIAL

    def test_run_status_failed_if_nothing_completed(self):
        from research_manifest import RunStatus, RunState
        rs = RunStatus(run_id="r1", manifest_hash="h", expected=10, scope="people-only")
        rs.missing_target_ids = [f"T{i}" for i in range(1, 11)]
        rs.finalize()
        assert rs.state == RunState.FAILED

    def test_validate_run_detects_substitutions(self):
        from research_manifest import build_manifest, RunStatus, validate_run_against_manifest
        targets = [
            {"ordinal": i, "target_id": f"WWI-{i:03d}", "target_type": "person",
             "conflict": "ww1", "raw_input": {"n": i}}
            for i in range(1, 6)
        ]
        m = build_manifest("r1", "people-only", targets)
        rs = RunStatus(run_id="r1", manifest_hash=m.manifest_hash, expected=5, scope="people-only")
        # Process: skip WWI-003, add unexpected EXTRA
        processed = ["WWI-001", "WWI-002", "WWI-004", "WWI-005", "EXTRA"]
        rs = validate_run_against_manifest(m, processed, rs)
        assert "WWI-003" in rs.missing_target_ids
        assert "EXTRA" in rs.unexpected_target_ids

    def test_manifest_120_targets_full_benchmark(self):
        from research_manifest import build_manifest
        targets = []
        for i in range(1, 101):
            targets.append({"ordinal": i, "target_id": f"WWI-{i:03d}" if i <= 50 else f"WWII-{i-50:03d}",
                           "target_type": "person", "conflict": "ww1" if i <= 50 else "ww2",
                           "raw_input": {"n": i}})
        for i in range(1, 21):
            targets.append({"ordinal": 100 + i, "target_id": f"EVENT-{i:03d}",
                           "target_type": "event", "conflict": "ww1",
                           "raw_input": {"e": i}})
        m = build_manifest("r1", "full-benchmark", targets)
        assert m.expected_targets == 120
        assert m.scope == "full-benchmark"


# ════════════════════════════════════════════════════════════════════════════
# 7. PROVIDER CAPABILITY ROUTING
# ════════════════════════════════════════════════════════════════════════════

class TestProviderRouting:
    """WWI providers are skipped for WWII targets and vice versa."""

    def test_icrc_ww1_skipped_for_ww2_target(self):
        from source_providers.icrc_ww1 import ProviderICRCWW1
        p = ProviderICRCWW1()
        assert p.is_compatible(conflict="ww2", subject_type="person") is False

    def test_icrc_ww1_allowed_for_ww1_target(self):
        from source_providers.icrc_ww1 import ProviderICRCWW1
        p = ProviderICRCWW1()
        assert p.is_compatible(conflict="ww1", subject_type="person") is True

    def test_lebi_skipped_for_ww1_target(self):
        from source_providers.lebi import ProviderLeBI
        p = ProviderLeBI()
        assert p.is_compatible(conflict="ww1", subject_type="person") is False

    def test_lebi_allowed_for_ww2_target(self):
        from source_providers.lebi import ProviderLeBI
        p = ProviderLeBI()
        assert p.is_compatible(conflict="ww2", subject_type="person") is True

    def test_time_range_filter(self):
        from source_providers.icrc_ww1 import ProviderICRCWW1
        p = ProviderICRCWW1()
        # 1914 is within range
        assert p.is_compatible(conflict="ww1", subject_type="person", target_year=1914) is True
        # 1944 is outside range
        assert p.is_compatible(conflict="ww1", subject_type="person", target_year=1944) is False

    def test_capability_dict_has_fields(self):
        from source_providers.icrc_ww1 import ProviderICRCWW1
        p = ProviderICRCWW1()
        cap = p.capability_dict()
        assert cap["provider_id"] == "icrc_ww1"
        assert "ww1" in cap["conflicts"]
        assert cap["time_start"] == 1914
        assert cap["time_end"] == 1918

    def test_generic_provider_compatible_with_all(self):
        from source_providers.base import SourceProvider
        # A provider with no conflict declarations is compatible with all
        class GenericProvider(SourceProvider):
            name = "generic"
            def search(self, query, filters=None, *, context=None):
                return []
            def get_metadata(self, record_id):
                return {}
        p = GenericProvider()
        assert p.is_compatible(conflict="ww1") is True
        assert p.is_compatible(conflict="ww2") is True


# ════════════════════════════════════════════════════════════════════════════
# 8. CIRCUIT BREAKER
# ════════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """Circuit breaker opens after threshold failures, prevents cascading."""

    def test_circuit_starts_closed(self):
        from circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_call() is True

    def test_circuit_opens_after_threshold(self):
        from circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("TIMEOUT")
        cb.record_failure("TIMEOUT")
        cb.record_failure("TIMEOUT")
        assert cb.state == CircuitState.OPEN
        assert cb.can_call() is False

    def test_circuit_open_returns_circuit_open_code(self):
        from circuit_breaker import CircuitBreaker, CircuitState, WebSearchErrorCode
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("RATE_LIMITED")
        cb.record_failure("RATE_LIMITED")
        assert cb.state == CircuitState.OPEN
        # Simulate what _web_search_enrich does
        if not cb.can_call():
            error_code = WebSearchErrorCode.CIRCUIT_OPEN
            assert error_code.value == "CIRCUIT_OPEN"

    def test_circuit_recovers_after_timeout(self):
        import time
        from circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure("TIMEOUT")
        cb.record_failure("TIMEOUT")
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.can_call() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_half_open_success_closes(self):
        import time
        from circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure("TIMEOUT")
        cb.record_failure("TIMEOUT")
        time.sleep(0.15)
        cb.can_call()  # transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_half_open_failure_reopens(self):
        import time
        from circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure("TIMEOUT")
        cb.record_failure("TIMEOUT")
        time.sleep(0.15)
        cb.can_call()  # transitions to HALF_OPEN
        cb.record_failure("AUTH_ERROR")
        assert cb.state == CircuitState.OPEN

    def test_classify_exception_timeout(self):
        from circuit_breaker import classify_exception, WebSearchErrorCode
        result = classify_exception(TimeoutError("Request timed out"))
        assert result == WebSearchErrorCode.TIMEOUT

    def test_classify_exception_rate_limited(self):
        from circuit_breaker import classify_exception, WebSearchErrorCode
        result = classify_exception(Exception("429 Too Many Requests"))
        assert result == WebSearchErrorCode.RATE_LIMITED

    def test_circuit_health_dict(self):
        from circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_success()
        cb.record_failure("TIMEOUT")
        health = cb.health_dict()
        assert health["successes"] == 1
        assert health["failures"] == 1
        assert health["state"] == "CLOSED"


# ════════════════════════════════════════════════════════════════════════════
# 9. EVIDENCE SNAPSHOT
# ════════════════════════════════════════════════════════════════════════════

class TestEvidenceSnapshot:
    """EvidenceSnapshot is immutable, versioned, and validates citations."""

    def test_snapshot_hash_stable(self):
        from evidence_snapshot import EvidenceSnapshot
        s = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc123",
            states={"resolution": "UNRESOLVED"},
        )
        h1 = s.snapshot_hash
        s2 = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc123",
            states={"resolution": "UNRESOLVED"},
        )
        assert h1 == s2.snapshot_hash

    def test_snapshot_hash_changes_with_evidence(self):
        from evidence_snapshot import EvidenceSnapshot
        s1 = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            states={"resolution": "UNRESOLVED"},
        )
        s2 = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            states={"resolution": "CONFIRMED"},
            accepted_claims=[{"claim_id": "cl_1", "predicate": "test"}],
        )
        assert s1.snapshot_hash != s2.snapshot_hash

    def test_snapshot_validates_claim_id(self):
        from evidence_snapshot import EvidenceSnapshot
        s = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            accepted_claims=[{"claim_id": "cl_1", "predicate": "born_in"}],
        )
        assert s.validate_claim_id("cl_1") is True
        assert s.validate_claim_id("cl_nonexistent") is False

    def test_snapshot_validates_evidence_source_id(self):
        from evidence_snapshot import EvidenceSnapshot
        s = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            accepted_evidence_sources=[{"source_id": "ev_1", "url": "http://test"}],
        )
        assert s.validate_evidence_source_id("ev_1") is True
        assert s.validate_evidence_source_id("ev_nonexistent") is False

    def test_snapshot_validates_citation_link(self):
        from evidence_snapshot import EvidenceSnapshot
        s = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            accepted_claims=[{
                "claim_id": "cl_1",
                "predicate": "born_in",
                "evidence_source_ids": ["ev_1"],
            }],
            accepted_evidence_sources=[{"source_id": "ev_1", "url": "http://test"}],
        )
        assert s.validate_citation("cl_1", "ev_1") is True
        assert s.validate_citation("cl_1", "ev_nonexistent") is False

    def test_snapshot_rejected_candidates_separate(self):
        from evidence_snapshot import EvidenceSnapshot
        s = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            rejected_candidates=[{
                "candidate_id": "rej_1",
                "name": "LARI GIUSEPPE 1883",
                "reason_codes": ["BIRTH_YEAR_CONFLICT"],
            }],
            accepted_claims=[],
        )
        # Rejected candidates don't appear in accepted claims
        assert len(s.accepted_claims) == 0
        assert len(s.rejected_candidates) == 1

    def test_snapshot_research_leads_separate_from_evidence(self):
        from evidence_snapshot import EvidenceSnapshot
        s = EvidenceSnapshot(
            target_id="T1",
            target_hash="abc",
            research_leads=[{
                "lead_id": "lead_1",
                "url": "https://difesa.it/AlbodOro.aspx",
                "object_kind": "HOMEPAGE",
            }],
            accepted_evidence_sources=[],
        )
        assert len(s.research_leads) == 1
        assert len(s.accepted_evidence_sources) == 0


# ════════════════════════════════════════════════════════════════════════════
# 10. ADDITIONAL SUBJECT DRIFT CASES
# ════════════════════════════════════════════════════════════════════════════

class TestAdditionalSubjectDrift:
    """7 additional observed drift cases: Giunta, Veneziano, Fantuz, Fedele, Russo."""

    def _make_candidate(self, name, birth_year, birth_place, unit):
        from research_protocol import Candidate
        return Candidate(
            nome_originale=name,
            data_nascita=birth_year,
            luogo_nascita=birth_place,
            reparto=unit,
        )

    def _make_input(self, name, birth_year, birth_place, unit, conflict="ww1"):
        from research_protocol import SearchInput
        return SearchInput(
            cognome=name.split()[0],
            nome=" ".join(name.split()[1:]),
            anno_nascita=birth_year,
            luogo_nascita=birth_place,
            reparto=unit,
            conflitto_presunto=conflict,
        )

    def test_giunta_1879_modica_rejected_vs_1883_san_lorenzo(self):
        from research_protocol import score_candidate, check_hard_conflicts
        si = self._make_input("GIUNTA GIUSEPPE", "1879", "Modica", "2 Granatieri")
        c = self._make_candidate("GIUNTA GIUSEPPE", "1883", "San Lorenzo", "245 Fanteria")
        result = score_candidate(c, si)
        assert result == "EXCLUDED"

    def test_veneziano_1898_lioni_rejected_vs_1879_casaluce(self):
        from research_protocol import score_candidate
        si = self._make_input("VENEZIANO NICOLA", "1898", "Lioni", "4 Fanteria")
        c = self._make_candidate("VENEZIANO NICOLA", "1879", "Casaluce", "224 Battaglione M.T.")
        result = score_candidate(c, si)
        assert result == "EXCLUDED"

    def test_fantuz_1896_pasiano_rejected_vs_1894_pasiano(self):
        from research_protocol import score_candidate
        si = self._make_input("FANTUZ ANTONIO", "1896", "Pasiano di Pordenone", "228 Fanteria")
        c = self._make_candidate("FANTUZ ANTONIO", "1894", "Pasiano di Pordenone", "6 Bersaglieri")
        result = score_candidate(c, si)
        assert result == "EXCLUDED"

    def test_fedele_1880_magnano_rejected_vs_1895_brienza(self):
        from research_protocol import score_candidate
        si = self._make_input("FEDELE AGOSTINO", "1880", "Magnano in Riviera", "128 Battaglione M.T.")
        c = self._make_candidate("FEDELE AGOSTINO", "1895", "Brienza", "8 Fanteria")
        result = score_candidate(c, si)
        assert result == "EXCLUDED"

    def test_russo_1888_misterbianco_rejected_vs_1876_lettere(self):
        from research_protocol import score_candidate
        si = self._make_input("RUSSO GAETANO", "1888", "Misterbianco", "48 Fanteria")
        c = self._make_candidate("RUSSO GAETANO", "1876", "Lettere", "224 Fanteria")
        result = score_candidate(c, si)
        assert result == "EXCLUDED"


# ════════════════════════════════════════════════════════════════════════════
# 11. PROPERTY-BASED: GENERIC REJECTION
# ════════════════════════════════════════════════════════════════════════════

class TestPropertyBasedRejection:
    """Any name with incompatible birth_year+place is rejected, regardless of name value."""

    @pytest.mark.parametrize("cognome,nome,year_in,place_in,year_cand,place_cand", [
        ("ROSSI", "MARIO", "1880", "Roma", "1885", "Milano"),
        ("BIANCHI", "LUIGI", "1890", "Napoli", "1895", "Torino"),
        ("ZURLINI", "CARLO", "1888", "Frosinone", "1882", "Bergamo"),
        ("MORANDINI", "PIETRO", "1875", "Verona", "1901", "Padova"),
        ("ESPOSITO", "GIOVANNI", "1892", "Salerno", "1888", "Caserta"),
    ])
    def test_incompatible_year_place_rejected(self, cognome, nome, year_in, place_in, year_cand, place_cand):
        from research_protocol import SearchInput, Candidate, score_candidate
        si = SearchInput(cognome=cognome, nome=nome, anno_nascita=year_in, luogo_nascita=place_in)
        c = Candidate(nome_originale=f"{cognome} {nome}", data_nascita=year_cand, luogo_nascita=place_cand)
        result = score_candidate(c, si)
        assert result == "EXCLUDED", f"Should be EXCLUDED for {cognome} {nome}: {year_in}/{place_in} vs {year_cand}/{place_cand}"

    @pytest.mark.parametrize("cognome,nome,year,place", [
        ("DI LAZZARO", "ATTILIO", "1890", "Velletri"),
        ("DE FRANCESCHI", "CARLO", "1885", "Trieste"),
        ("VAILATI-USTINELLI", "MARIO", "1888", "Brescia"),
        ("DELL'ANNO", "GIUSEPPE", "1891", "Foggia"),
        ("L'ABBATE", "NICOLA", "1887", "Bari"),
    ])
    def test_composed_names_preserve_identity(self, cognome, nome, year, place):
        from research_protocol import normalize_name_preserve_particles
        full = f"{cognome} {nome}"
        normalized = normalize_name_preserve_particles(full)
        # Particles and hyphens preserved
        parts = cognome.lower().replace("'", "'").split()
        for part in parts:
            if len(part) > 2:
                assert part in normalized


# ════════════════════════════════════════════════════════════════════════════
# 12. NO SPECIAL-CASE CODE IN PRODUCTION
# ════════════════════════════════════════════════════════════════════════════

class TestNoSpecialCaseCode:
    """Production code must not contain special-case logic for sentinel names."""

    SENTINEL_NAMES = [
        "LARI", "PAPINI", "FOLLADOR", "SIFANNO", "FEDERICO",
        "GIUNTA", "VENEZIANO", "FANTUZ", "FEDELE", "RUSSO",
    ]

    def test_no_sentinel_names_in_score_candidate(self):
        import inspect
        from research_protocol import score_candidate
        source = inspect.getsource(score_candidate)
        for name in self.SENTINEL_NAMES:
            assert name not in source, f"Sentinel name '{name}' found in score_candidate source"

    def test_no_sentinel_names_in_check_hard_conflicts(self):
        import inspect
        from research_protocol import check_hard_conflicts
        source = inspect.getsource(check_hard_conflicts)
        for name in self.SENTINEL_NAMES:
            assert name not in source, f"Sentinel name '{name}' found in check_hard_conflicts source"

    def test_no_sentinel_names_in_apply_resolution_gate(self):
        import inspect
        from research_protocol import apply_resolution_gate
        source = inspect.getsource(apply_resolution_gate)
        for name in self.SENTINEL_NAMES:
            assert name not in source, f"Sentinel name '{name}' found in apply_resolution_gate source"

    def test_no_sentinel_names_in_classify_object_kind(self):
        import inspect
        from research_protocol import classify_object_kind
        source = inspect.getsource(classify_object_kind)
        for name in self.SENTINEL_NAMES:
            assert name not in source, f"Sentinel name '{name}' found in classify_object_kind source"

    def test_no_sentinel_names_in_web_search_enrich(self):
        import inspect
        from research_protocol import _web_search_enrich
        source = inspect.getsource(_web_search_enrich)
        for name in self.SENTINEL_NAMES:
            assert name not in source, f"Sentinel name '{name}' found in _web_search_enrich source"


# ════════════════════════════════════════════════════════════════════════════
# 13. BATCH ISOLATION (expanded)
# ════════════════════════════════════════════════════════════════════════════

class TestBatchIsolationExpanded:
    """Accumulators of consecutive targets are isolated — no contamination."""

    def test_two_consecutive_targets_no_fonti_contamination(self):
        from research_protocol import SearchInput, Candidate, Dossier, SourceRecord, compute_typed_counts
        # Target 1: has candidates with fonti
        si1 = SearchInput(cognome="AAA", nome="BBB", anno_nascita="1880")
        c1 = Candidate(nome_originale="AAA BBB", stato="POSSIBLE",
                       fonti=[SourceRecord(url="http://a.it/record/1", istituzione="test")])
        d1 = Dossier()
        d1.candidati = [c1]
        d1.omonimi_esclusi = []
        counts1 = compute_typed_counts(d1.candidati, d1.omonimi_esclusi)

        # Target 2: no candidates
        d2 = Dossier()
        d2.candidati = []
        d2.omonimi_esclusi = []
        counts2 = compute_typed_counts(d2.candidati, d2.omonimi_esclusi)

        assert counts1["person_candidates"] == 1
        assert counts2["person_candidates"] == 0
        assert counts2["accepted_evidence_sources"] == 0

    def test_permuted_order_same_results(self):
        """Permuting target order with seed doesn't change per-target results."""
        from research_protocol import SearchInput, Candidate, score_candidate
        import random

        targets = [
            (SearchInput(cognome="X", nome="A", anno_nascita="1880", luogo_nascita="Roma"),
             Candidate(nome_originale="X A", data_nascita="1880", luogo_nascita="Roma")),
            (SearchInput(cognome="Y", nome="B", anno_nascita="1890", luogo_nascita="Milano"),
             Candidate(nome_originale="Y B", data_nascita="1890", luogo_nascita="Milano")),
            (SearchInput(cognome="Z", nome="C", anno_nascita="1885", luogo_nascita="Napoli"),
             Candidate(nome_originale="Z C", data_nascita="1885", luogo_nascita="Napoli")),
        ]

        # Compute results in original order
        results_original = [score_candidate(c, si) for si, c in targets]

        # Permute with seed
        rng = random.Random(42)
        indices = list(range(len(targets)))
        rng.shuffle(indices)
        results_permuted = [score_candidate(targets[i][1], targets[i][0]) for i in indices]

        # Same results (just reordered)
        assert sorted(results_original) == sorted(results_permuted)
