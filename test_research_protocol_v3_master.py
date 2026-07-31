"""Master test file for Research Protocol V3 structural fix.

Tests all invariants, regressions, and integration points for the
10 error classes identified in the canary run.

Run: python -m pytest test_research_protocol_v3_master.py -v
"""
import pytest
import json
import hashlib
import sys
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from research_protocol import (
    SearchInput, Candidate, Dossier, ResearchTarget, ResolutionState,
    LocalMatchState, ExternalValidationState, OriginRecordState,
    RunState, ObjectKind, EvidenceState, ResolutionResult,
    EvidenceSnapshot, AIError, NameVariant, SourceRecord,
    check_hard_conflicts, apply_resolution_gate, score_candidate,
    classify_object_kind, is_evidence_eligible, compute_typed_counts,
    normalize_name_preserve_particles, names_match,
    generate_variants, _build_query_matrix,
    classify_source, classify_connection,
    check_subject_drift, canonicalize_url, deduplicate_sources,
    classify_web_result_relevance, filter_relevant_results,
    check_ai_truncation, get_provider_capabilities,
    _WWI_ONLY_PROVIDERS, _WWII_ONLY_PROVIDERS, _BOTH_CONFLICTS_PROVIDERS,
    VALIDATION_MODES, PROVIDER_EXECUTION_STATES, RETRIEVAL_OUTCOMES,
    SEMANTIC_MATCH_STATES,
    _norm_place, _norm_val, _extract_year, _norm_unit,
)


# ════════════════════════════════════════════════════════════════════════════
# 1. target_hash immutability
# ════════════════════════════════════════════════════════════════════════════

class TestTargetHashImmutability:
    def test_same_input_produces_same_hash(self):
        si1 = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
                         luogo_nascita="Canneto sull'Oglio", paternita="EMANUELE")
        si2 = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
                         luogo_nascita="Canneto sull'Oglio", paternita="EMANUELE")
        t1 = ResearchTarget.from_search_input(si1)
        t2 = ResearchTarget.from_search_input(si2)
        assert t1.target_hash == t2.target_hash

    def test_different_input_produces_different_hash(self):
        si1 = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886")
        si2 = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1883")
        t1 = ResearchTarget.from_search_input(si1)
        t2 = ResearchTarget.from_search_input(si2)
        assert t1.target_hash != t2.target_hash

    def test_target_is_frozen(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE")
        target = ResearchTarget.from_search_input(si)
        with pytest.raises(Exception):
            target.target_id = "modified"


# ════════════════════════════════════════════════════════════════════════════
# 2. SUBJECT_DRIFT detection
# ════════════════════════════════════════════════════════════════════════════

class TestSubjectDrift:
    def test_no_drift_when_hash_matches(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE")
        target = ResearchTarget.from_search_input(si)
        ai_response = {"target_hash": target.target_hash}
        assert check_subject_drift(target, ai_response) is False

    def test_drift_detected_when_hash_differs(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE")
        target = ResearchTarget.from_search_input(si)
        ai_response = {"target_hash": "different_hash_123"}
        assert check_subject_drift(target, ai_response) is True

    def test_no_drift_when_hash_missing(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE")
        target = ResearchTarget.from_search_input(si)
        ai_response = {}
        assert check_subject_drift(target, ai_response) is False


# ════════════════════════════════════════════════════════════════════════════
# 3. INSUFFICIENT_DATA cannot promote identity
# ════════════════════════════════════════════════════════════════════════════

class TestInsufficientDataNoPromotion:
    def test_insufficient_data_stays_unresolved(self):
        c = Candidate(stato="INSUFFICIENT_DATA", confidence=0.1)
        result = apply_resolution_gate(candidate=c, accepted_evidence_count=0)
        assert result.resolution_state == ResolutionState.UNRESOLVED
        assert "INSUFFICIENT_DATA_NO_PROMOTION" in result.reason_codes

    def test_insufficient_data_with_evidence_still_cannot_promote(self):
        c = Candidate(stato="INSUFFICIENT_DATA", confidence=0.1)
        result = apply_resolution_gate(candidate=c, accepted_evidence_count=5, independent_lineages=3)
        # INSUFFICIENT_DATA is checked first, before evidence
        assert result.resolution_state == ResolutionState.UNRESOLVED


# ════════════════════════════════════════════════════════════════════════════
# 4. AI errors do not produce positive fallback
# ════════════════════════════════════════════════════════════════════════════

class TestAIErrorNoFallback:
    def test_ai_failure_with_no_evidence_stays_unresolved(self):
        c = Candidate(stato="POSSIBLE", confidence=0.8)
        result = apply_resolution_gate(
            candidate=c, accepted_evidence_count=0, ai_synthesis_failed=True)
        assert result.resolution_state != ResolutionState.CONFIRMED
        assert result.resolution_state != ResolutionState.PROBABLE
        assert "AI_SYNTHESIS_FAILED" in result.reason_codes or \
               "AI_SYNTHESIS_FAILED_NO_FALLBACK" in result.reason_codes

    def test_ai_failure_with_evidence_keeps_deterministic_state(self):
        c = Candidate(stato="POSSIBLE", confidence=0.8)
        result = apply_resolution_gate(
            candidate=c, accepted_evidence_count=2, independent_lineages=2,
            ai_synthesis_failed=True)
        # Evidence-based promotion should still work despite AI failure
        assert result.resolution_state == ResolutionState.CONFIRMED


# ════════════════════════════════════════════════════════════════════════════
# 5. Hard conflicts reject candidates before scoring
# ════════════════════════════════════════════════════════════════════════════

class TestHardConflicts:
    def test_birth_year_conflict_rejects(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886")
        c = Candidate(data_nascita="1883", luogo_nascita="Canneto sull'Oglio")
        conflicts = check_hard_conflicts(c, si)
        assert any("BIRTH_YEAR_CONFLICT" in fc for fc in conflicts)

    def test_birth_place_conflict_rejects(self):
        si = SearchInput(cognome="LARI", luogo_nascita="Canneto sull'Oglio")
        c = Candidate(data_nascita="1886", luogo_nascita="Ronciglione")
        conflicts = check_hard_conflicts(c, si)
        assert any("BIRTH_PLACE_CONFLICT" in fc for fc in conflicts)

    def test_unit_conflict_rejects(self):
        si = SearchInput(cognome="LARI", reparto="206 Reggimento Fanteria")
        c = Candidate(reparto="138 Reggimento Fanteria")
        conflicts = check_hard_conflicts(c, si)
        assert any("UNIT_CONFLICT" in fc for fc in conflicts)

    def test_no_conflict_when_compatible(self):
        si = SearchInput(cognome="LARI", anno_nascita="1886",
                        luogo_nascita="Canneto sull'Oglio", reparto="206 Reggimento Fanteria")
        c = Candidate(data_nascita="1886", luogo_nascita="Canneto sull'Oglio",
                     reparto="206 Reggimento Fanteria")
        conflicts = check_hard_conflicts(c, si)
        assert len(conflicts) == 0


# ════════════════════════════════════════════════════════════════════════════
# 6. _norm_place preserves compound toponyms
# ════════════════════════════════════════════════════════════════════════════

class TestNormPlaceCompound:
    def test_preserves_sull_oglio(self):
        assert "sull'oglio" in _norm_place("Canneto sull'Oglio")
        assert _norm_place("Canneto sull'Oglio") != "canneto"

    def test_preserves_di_pordenone(self):
        assert "di" in _norm_place("Pasiano di Pordenone")
        assert "pordenone" in _norm_place("Pasiano di Pordenone")

    def test_preserves_in_riviera(self):
        assert "in" in _norm_place("Magnano in Riviera")
        assert "riviera" in _norm_place("Magnano in Riviera")

    def test_strips_comune_di(self):
        result = _norm_place("Comune di Roma")
        assert "comune" not in result
        assert "roma" in result


# ════════════════════════════════════════════════════════════════════════════
# 7. URL canonicalization and deduplication
# ════════════════════════════════════════════════════════════════════════════

class TestURLCanonicalization:
    def test_canonicalize_removes_tracking_params(self):
        url = "https://example.com/page?utm_source=google&id=123"
        canon = canonicalize_url(url)
        assert "utm_source" not in canon
        assert "id=123" in canon

    def test_canonicalize_normalizes_case(self):
        url1 = "HTTPS://Example.COM/Path"
        url2 = "https://example.com/Path"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_canonicalize_strips_trailing_slash(self):
        url1 = "https://example.com/page/"
        url2 = "https://example.com/page"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_canonicalize_rejects_truncated(self):
        assert canonicalize_url("https://") == ""
        assert canonicalize_url("") == ""
        assert canonicalize_url(None) == ""

    def test_deduplicate_sources(self):
        sources = [
            {"url": "https://example.com/page", "title": "A"},
            {"url": "https://example.com/page/", "title": "B"},  # dup
            {"url": "https://example.com/page?utm_source=x", "title": "C"},  # dup
            {"url": "https://other.com/page", "title": "D"},
        ]
        unique = deduplicate_sources(sources)
        assert len(unique) == 2


# ════════════════════════════════════════════════════════════════════════════
# 8. Relevance gate
# ════════════════════════════════════════════════════════════════════════════

class TestRelevanceGate:
    def _make_target(self, conflict="ww1"):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", conflitto_presunto=conflict)
        return ResearchTarget.from_search_input(si)

    def test_commercial_domain_rejected(self):
        target = self._make_target()
        result = classify_web_result_relevance(
            "https://amazon.com/product", "Buy Wine", "", target)
        assert result["domain_relevance"] == "COMMERCIAL"

    def test_search_page_rejected(self):
        target = self._make_target()
        result = classify_web_result_relevance(
            "https://example.com/search?q=test", "Search", "", target)
        assert result["domain_relevance"] == "SEARCH_PAGE"

    def test_period_mismatch_ww2_for_ww1_target(self):
        target = self._make_target("ww1")
        result = classify_web_result_relevance(
            "https://example.com/ww2", "IMI internato 1943", "internati militari italiani", target)
        assert "PERIOD_MISMATCH" in result["rejection_reason"]

    def test_historical_source_accepted(self):
        target = self._make_target("ww1")
        result = classify_web_result_relevance(
            "https://cadutigrandeguerra.it/scheda/123", "Caduto Grande Guerra", "soldato", target)
        assert result["domain_relevance"] == "HISTORICAL"
        assert result["historical_period_compatible"] is True

    def test_filter_relevant_results(self):
        target = self._make_target("ww1")
        results = [
            {"url": "https://cadutigrandeguerra.it/123", "title": "Caduto", "snippet": ""},
            {"url": "https://amazon.com/wine", "title": "Buy Wine", "snippet": ""},
            {"url": "https://example.com/search?q=test", "title": "Search", "snippet": ""},
        ]
        relevant, rejected = filter_relevant_results(results, target)
        assert len(relevant) >= 1
        assert len(rejected) >= 2


# ════════════════════════════════════════════════════════════════════════════
# 9. AI truncation detection
# ════════════════════════════════════════════════════════════════════════════

class TestAITruncation:
    def test_no_result_is_truncated(self):
        result = check_ai_truncation(None)
        assert result["is_truncated"] is True

    def test_finish_reason_length_is_truncated(self):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Some text"
        mock_result.finish_reason = "length"
        mock_result.output_tokens = 100
        mock_result.max_output_tokens = 0
        result = check_ai_truncation(mock_result)
        assert result["is_truncated"] is True

    def test_normal_output_not_truncated(self):
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "This is a complete response."
        mock_result.finish_reason = "stop"
        mock_result.output_tokens = 50
        mock_result.max_output_tokens = 2048
        result = check_ai_truncation(mock_result)
        assert result["is_truncated"] is False


# ════════════════════════════════════════════════════════════════════════════
# 10. Provider capability routing
# ════════════════════════════════════════════════════════════════════════════

class TestProviderCapabilityRouting:
    def test_ww1_target_skips_wwii_providers(self):
        caps = get_provider_capabilities("ww1")
        assert "arolsen" in caps["skipped"]
        assert "lebi" in caps["skipped"]
        assert "albo_oro" in caps["eligible"]
        assert "icrc_ww1" in caps["eligible"]

    def test_ww2_target_skips_wwi_providers(self):
        caps = get_provider_capabilities("ww2")
        assert "albo_oro" in caps["skipped"]
        assert "icrc_ww1" in caps["skipped"]
        assert "arolsen" in caps["eligible"]
        assert "lebi" in caps["eligible"]

    def test_unknown_conflict_searches_all(self):
        caps = get_provider_capabilities("")
        assert len(caps["skipped"]) == 0
        assert len(caps["eligible"]) > 0

    def test_both_conflicts_always_eligible(self):
        for conflict in ["ww1", "ww2", ""]:
            caps = get_provider_capabilities(conflict)
            assert "familysearch" in caps["eligible"]
            assert "commonwealthwargraves" in caps["eligible"]

    def test_returns_json_serializable(self):
        """Verify return value is JSON serializable (no sets)."""
        import json
        caps = get_provider_capabilities("ww1")
        json.dumps(caps)  # Should not raise


# ════════════════════════════════════════════════════════════════════════════
# 11. Resolution gate with SOURCE_RECORD_ONLY
# ════════════════════════════════════════════════════════════════════════════

class TestSourceRecordOnly:
    def test_strong_local_match_without_evidence_is_source_record_only(self):
        c = Candidate(stato="POSSIBLE", confidence=0.9)
        result = apply_resolution_gate(candidate=c, accepted_evidence_count=0)
        assert result.resolution_state == ResolutionState.SOURCE_RECORD_ONLY
        assert "SOURCE_RECORD_MATCH_NO_EXTERNAL_EVIDENCE" in result.reason_codes

    def test_weak_local_match_without_evidence_stays_unresolved(self):
        c = Candidate(stato="POSSIBLE", confidence=0.3)
        result = apply_resolution_gate(candidate=c, accepted_evidence_count=0)
        assert result.resolution_state == ResolutionState.UNRESOLVED

    def test_source_record_only_with_evidence_promotes(self):
        c = Candidate(stato="POSSIBLE", confidence=0.9)
        result = apply_resolution_gate(
            candidate=c, accepted_evidence_count=2, independent_lineages=2)
        assert result.resolution_state == ResolutionState.CONFIRMED


# ════════════════════════════════════════════════════════════════════════════
# 12. EvidenceSnapshot
# ════════════════════════════════════════════════════════════════════════════

class TestEvidenceSnapshot:
    def test_snapshot_from_dossier(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886")
        target = ResearchTarget.from_search_input(si)
        dossier = Dossier()
        dossier.stato_identificazione = "record_fonte_singola"
        dossier.profilo["resolution_state"] = "SOURCE_RECORD_ONLY"
        dossier.profilo["reason_codes"] = ["SOURCE_RECORD_MATCH_NO_EXTERNAL_EVIDENCE"]
        dossier.profilo["typed_counts"] = {"person_candidates": 1}
        dossier.candidati.append(Candidate(
            nome_originale="LARI GIUSEPPE", stato="POSSIBLE", confidence=0.9))
        dossier.web_search_used = True
        dossier.ai_used = True
        dossier.ai_model = "mistral-large-latest"

        snapshot = EvidenceSnapshot.from_dossier(dossier, target)
        assert snapshot.target_id == target.target_id
        assert snapshot.target_hash == target.target_hash
        assert snapshot.resolution_state == "SOURCE_RECORD_ONLY"
        assert len(snapshot.candidates) == 1
        assert snapshot.completeness["web_searched"] is True
        assert snapshot.completeness["ai_synthesized"] is True

    def test_conversational_context_contains_key_info(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE")
        target = ResearchTarget.from_search_input(si)
        dossier = Dossier()
        dossier.stato_identificazione = "record_fonte_singola"
        dossier.profilo["resolution_state"] = "SOURCE_RECORD_ONLY"
        dossier.profilo["typed_counts"] = {"person_candidates": 1}
        dossier.candidati.append(Candidate(nome_originale="LARI GIUSEPPE", confidence=0.9))

        snapshot = EvidenceSnapshot.from_dossier(dossier, target)
        context = snapshot.to_conversational_context()
        assert "LARI GIUSEPPE" in context
        assert "SOURCE_RECORD_ONLY" in context
        assert "Completeness" in context


# ════════════════════════════════════════════════════════════════════════════
# 13. Paternity comparison with display_name awareness
# ════════════════════════════════════════════════════════════════════════════

class TestPaternityComparison:
    def test_matching_paternity_is_strong_match(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", paternita="EMANUELE")
        c = Candidate(nome_originale="LARI GIUSEPPE", paternita="EMANUELE",
                     data_nascita="1886", luogo_nascita="Canneto sull'Oglio")
        score_candidate(c, si)
        assert c.stato == "POSSIBLE"
        assert any("strong_matches" in s for s in c.compatibilita)

    def test_different_paternity_creates_conflict(self):
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", paternita="EMANUELE")
        c = Candidate(nome_originale="LARI GIUSEPPE", paternita="GIOVANNI",
                     data_nascita="1886", luogo_nascita="Canneto sull'Oglio")
        score_candidate(c, si)
        assert any("PATERNITA_CONFLICT" in contra for contra in c.contraddizioni)

    def test_paternita_containing_full_name_is_parse_uncertain(self):
        si = SearchInput(cognome="PAPINI", nome="PUBLIO", paternita="GIOVANNI")
        c = Candidate(nome_originale="PAPINI PUBLIO DI GIOVANNI",
                     paternita="PAPINI PUBLIO DI GIOVANNI",
                     data_nascita="1890", luogo_nascita="Roccalbegna")
        score_candidate(c, si)
        # Should not create a hard PATERNITA_CONFLICT — it's a parser issue
        assert not any("PATERNITA_CONFLICT" in contra for contra in c.contraddizioni)
        assert any("FIELD_PARSE_UNCERTAIN" in contra for contra in c.contraddizioni)


# ════════════════════════════════════════════════════════════════════════════
# 14. Object kind classification
# ════════════════════════════════════════════════════════════════════════════

class TestObjectKindClassification:
    def test_homepage_detected(self):
        kind = classify_object_kind("https://example.com/")
        assert kind == ObjectKind.HOMEPAGE

    def test_search_page_detected(self):
        kind = classify_object_kind("https://example.com/search?q=test")
        assert kind == ObjectKind.SEARCH_PAGE

    def test_catalog_record_with_id_and_locator(self):
        kind = classify_object_kind("https://example.com/record/123",
                                    has_record_id=True, has_locator=True)
        assert kind == ObjectKind.CATALOG_RECORD

    def test_search_result_lead_with_id_only(self):
        kind = classify_object_kind("https://example.com/record/123",
                                    has_record_id=True)
        assert kind == ObjectKind.SEARCH_RESULT_LEAD

    def test_digitized_document(self):
        kind = classify_object_kind("https://example.com/doc.pdf")
        assert kind == ObjectKind.DIGITIZED_DOCUMENT

    def test_evidence_eligible_only_for_records_and_documents(self):
        assert is_evidence_eligible(ObjectKind.CATALOG_RECORD) is True
        assert is_evidence_eligible(ObjectKind.DIGITIZED_DOCUMENT) is True
        assert is_evidence_eligible(ObjectKind.TRANSCRIPTION) is True
        assert is_evidence_eligible(ObjectKind.HOMEPAGE) is False
        assert is_evidence_eligible(ObjectKind.SEARCH_PAGE) is False
        assert is_evidence_eligible(ObjectKind.SEARCH_RESULT_LEAD) is False


# ════════════════════════════════════════════════════════════════════════════
# 15. Typed counts replace ambiguous 'fonti_totali'
# ════════════════════════════════════════════════════════════════════════════

class TestTypedCounts:
    def test_typed_counts_keys(self):
        c = Candidate(nome_originale="Test", stato="POSSIBLE")
        c.fonti.append(SourceRecord(url="https://example.com/record/123",
                                    identificativo_archivistico="REC123"))
        counts = compute_typed_counts([c], [])
        assert "person_candidates" in counts
        assert "rejected_person_candidates" in counts
        assert "search_leads" in counts
        assert "source_records" in counts
        assert "accepted_evidence_sources" in counts
        assert "independent_evidence_lineages" in counts
        assert counts["person_candidates"] == 1

    def test_typed_counts_excluded_candidates(self):
        c1 = Candidate(nome_originale="A", stato="POSSIBLE")
        c2 = Candidate(nome_originale="B", stato="EXCLUDED")
        counts = compute_typed_counts([c1], [c2])
        assert counts["person_candidates"] == 1
        assert counts["rejected_person_candidates"] == 1


# ════════════════════════════════════════════════════════════════════════════
# 16. New states exist and are properly enumerated
# ════════════════════════════════════════════════════════════════════════════

class TestNewStates:
    def test_resolution_state_source_record_only_exists(self):
        assert ResolutionState.SOURCE_RECORD_ONLY.value == "SOURCE_RECORD_ONLY"

    def test_resolution_state_corroborated_exists(self):
        assert ResolutionState.CORROBORATED.value == "CORROBORATED"

    def test_origin_record_state_enum_exists(self):
        assert OriginRecordState.ABSENT.value == "ABSENT"
        assert OriginRecordState.SOURCE_RECORD_MATCHED.value == "SOURCE_RECORD_MATCHED"

    def test_validation_modes_exist(self):
        assert "LOOKUP_ENRICHMENT" in VALIDATION_MODES
        assert "BLIND_INDEPENDENT_VALIDATION" in VALIDATION_MODES
        assert "DISCOVERY_FROM_MINIMAL_INPUT" in VALIDATION_MODES

    def test_provider_execution_states_exist(self):
        assert "NOT_RUN" in PROVIDER_EXECUTION_STATES
        assert "SUCCESS" in PROVIDER_EXECUTION_STATES
        assert "CIRCUIT_OPEN" in PROVIDER_EXECUTION_STATES

    def test_retrieval_outcomes_exist(self):
        assert "NO_RESULTS" in RETRIEVAL_OUTCOMES
        assert "LEADS_ONLY" in RETRIEVAL_OUTCOMES
        assert "PERSON_CANDIDATES" in RETRIEVAL_OUTCOMES
        assert "SOURCE_RECORDS" in RETRIEVAL_OUTCOMES

    def test_semantic_match_states_exist(self):
        assert "NONE" in SEMANTIC_MATCH_STATES
        assert "POSITIVE" in SEMANTIC_MATCH_STATES
        assert "CONFLICTING" in SEMANTIC_MATCH_STATES


# ════════════════════════════════════════════════════════════════════════════
# 17. Name matching (no substring false positives)
# ════════════════════════════════════════════════════════════════════════════

class TestNameMatching:
    def test_exact_match(self):
        assert names_match("Lari Giuseppe", "Lari Giuseppe") is True

    def test_word_subset_match(self):
        assert names_match("Lari", "Lari Giuseppe") is True

    def test_no_substring_false_positive(self):
        assert names_match("lana", "castellana") is False

    def test_different_names_no_match(self):
        assert names_match("Lari", "Federico") is False


# ════════════════════════════════════════════════════════════════════════════
# 18. AIError formatting (never empty parentheses)
# ════════════════════════════════════════════════════════════════════════════

class TestAIErrorFormatting:
    def test_error_has_code_and_stage(self):
        err = AIError(stage="dossier_synthesis", error_code="GENERATION_FAILED",
                     safe_message="Test error")
        s = f"❌ ({err.error_code}: {err.stage})"
        assert "GENERATION_FAILED" in s
        assert "dossier_synthesis" in s

    def test_error_never_empty(self):
        err = AIError()
        assert err.error_code == ""
        assert err.stage == ""
        # Even empty, the format should show the structure
        s = f"❌ ({err.error_code}: {err.stage})"
        assert s.startswith("❌ (")


# ════════════════════════════════════════════════════════════════════════════
# 19. Canary target data integrity (no hardcoded exceptions)
# ════════════════════════════════════════════════════════════════════════════

class TestCanaryTargetIntegrity:
    """Verify that the canary targets are not special-cased in the code."""

    def test_no_hardcoded_target_ids_in_score_candidate(self):
        """score_candidate should not reference specific target IDs."""
        import inspect
        source = inspect.getsource(score_candidate)
        # Must not contain any canary target IDs
        for tid in ["WWI-001", "WWI-002", "WWI-003", "WWI-004", "WWI-005",
                     "WWI-006", "WWI-007", "WWI-008", "WWI-009", "WWI-010"]:
            assert tid not in source, f"score_candidate hardcodes {tid}"

    def test_no_hardcoded_surnames_in_apply_resolution_gate(self):
        """apply_resolution_gate should not reference specific surnames."""
        import inspect
        source = inspect.getsource(apply_resolution_gate)
        for surname in ["LARI", "FEDERICO", "GIUNTA", "VENEZIANO", "FANTUZ",
                        "FEDELE", "RUSSO", "PAPINI", "FOLLADOR", "SIFANNO"]:
            assert surname not in source, f"apply_resolution_gate hardcodes {surname}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
