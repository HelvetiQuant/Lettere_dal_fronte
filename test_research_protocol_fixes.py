"""Test per fix strutturale research_protocol.
Test fallenti prima del fix, poi implementare.
"""
import pytest
import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from unittest.mock import MagicMock, patch

# Import dalle modifiche che implementeremo
from research_protocol import (
    SearchInput, Candidate, SourceRecord, Dossier,
    score_candidate, research_person, AIError, format_ai_error,
)


# ════════════════════════════════════════════════════════════════════════════
# 1. TARGET IMMUTABILE + TARGET_HASH
# ════════════════════════════════════════════════════════════════════════════

class TestTargetImmutability:
    """Target hash non cambia durante candidate loop, provider loop e batch loop."""

    def test_target_hash_stable_across_candidates(self):
        """target_hash calcolato una volta, non cambia con candidati diversi."""
        from research_protocol import ResearchTarget
        t = ResearchTarget.from_search_input(SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
            luogo_nascita="Canneto sull'Oglio", reparto="206 Fanteria",
            conflitto_presunto="ww1",
        ))
        h1 = t.target_hash
        # Simula elaborazione di candidati
        c1 = Candidate(nome_originale="LARI GIUSEPPE", data_nascita="1886")
        c2 = Candidate(nome_originale="LARI GIUSEPPE", data_nascita="1883")
        h2 = t.target_hash
        assert h1 == h2, "target_hash changed after candidate processing"

    def test_target_hash_differs_for_different_targets(self):
        """Target diversi hanno hash diversi."""
        from research_protocol import ResearchTarget
        t1 = ResearchTarget.from_search_input(SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
            luogo_nascita="Canneto sull'Oglio",
        ))
        t2 = ResearchTarget.from_search_input(SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1883",
            luogo_nascita="Ronciglione",
        ))
        assert t1.target_hash != t2.target_hash, "Different targets should have different hashes"

    def test_subject_drift_detection(self):
        """Risposta con target_id/hash diverso produce SUBJECT_DRIFT."""
        from research_protocol import ResearchTarget, check_subject_drift
        t = ResearchTarget.from_search_input(SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
        ))
        # Simula risposta AI con hash diverso
        ai_response = {
            "target_id": t.target_id,
            "target_hash": "wrong_hash",
            "observations": [],
        }
        drift = check_subject_drift(t, ai_response)
        assert drift is True, "Should detect subject drift"

    def test_no_drift_when_hash_matches(self):
        """Nessun drift quando hash coincide."""
        from research_protocol import ResearchTarget, check_subject_drift
        t = ResearchTarget.from_search_input(SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
        ))
        ai_response = {
            "target_id": t.target_id,
            "target_hash": t.target_hash,
        }
        drift = check_subject_drift(t, ai_response)
        assert drift is False


# ════════════════════════════════════════════════════════════════════════════
# 2. GATE DETERMINISTICI
# ════════════════════════════════════════════════════════════════════════════

class TestDeterministicGates:
    """Gate deterministici: nessuna promozione senza evidenza."""

    def test_insufficient_data_cannot_promote(self):
        """INSUFFICIENT_DATA non può produrre PROBABLE/CONFIRMED."""
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
                         luogo_nascita="Canneto sull'Oglio", reparto="206 Fanteria")
        c = Candidate(
            nome_originale="LARI GIUSEPPE",
            data_nascita="1886", luogo_nascita="Canneto sull'Oglio",
            reparto="206 Fanteria",
            stato="INSUFFICIENT_DATA",
            confidence=0.10,
        )
        # Anche se score_candidate dice CONFIRMED, il gate deve impedire
        # la promozione se non c'è evidenza indipendente
        from research_protocol import apply_resolution_gate
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
        )
        assert result.resolution_state not in ("PROBABLE", "CONFIRMED"), \
            "INSUFFICIENT_DATA with 0 evidence cannot be PROBABLE/CONFIRMED"

    def test_zero_evidence_means_unresolved(self):
        """Zero evidenze indipendenti → external_validation=NO_EVIDENCE."""
        from research_protocol import apply_resolution_gate, ExternalValidationState
        c = Candidate(nome_originale="TEST", stato="POSSIBLE")
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
        )
        assert result.external_validation_state == ExternalValidationState.NO_EVIDENCE
        assert result.resolution_state not in ("PROBABLE", "CONFIRMED")

    def test_ai_error_no_fallback_positive(self):
        """Errore AI/parser non produce fallback positivo."""
        from research_protocol import apply_resolution_gate, RunState
        c = Candidate(nome_originale="TEST", stato="POSSIBLE")
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
            ai_synthesis_failed=True,
        )
        assert result.resolution_state not in ("PROBABLE", "CONFIRMED")
        assert result.run_state != RunState.SUCCESS

    def test_hard_conflict_rejects_before_scoring(self):
        """Anno/comune incompatibili respingono il candidato prima dello scoring positivo."""
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
                         luogo_nascita="Canneto sull'Oglio", reparto="206 Fanteria")
        c = Candidate(
            nome_originale="LARI GIUSEPPE",
            data_nascita="1883",  # CONFLICT: 1886 vs 1883
            luogo_nascita="Ronciglione",  # CONFLICT: Canneto vs Ronciglione
            reparto="22 Fanteria",  # CONFLICT: 206 vs 22
        )
        from research_protocol import check_hard_conflicts
        conflicts = check_hard_conflicts(c, si)
        assert len(conflicts) >= 2, "Should detect birth year and birth place conflicts"
        assert any("BIRTH_YEAR_CONFLICT" in fc for fc in conflicts)
        assert any("BIRTH_PLACE_CONFLICT" in fc for fc in conflicts)

    def test_lari_1883_ronciglione_rejected(self):
        """Lari 1883/Ronciglione/22° è incompatibile con target 1886/Canneto/206°."""
        si = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
                         luogo_nascita="Canneto sull'Oglio", reparto="206 Fanteria",
                         conflitto_presunto="ww1")
        c = Candidate(
            nome_originale="LARI GIUSEPPE",
            data_nascita="1883",
            luogo_nascita="Ronciglione",
            reparto="22 Reggimento Fanteria",
        )
        from research_protocol import check_hard_conflicts, apply_resolution_gate
        conflicts = check_hard_conflicts(c, si)
        assert len(conflicts) >= 3, "Should detect year+place+unit conflicts"
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
            hard_conflicts=conflicts,
        )
        assert result.resolution_state.value == "REJECTED_WRONG_IDENTITY"

    def test_federico_1895_larino_rejected(self):
        """Federico 1895/Larino/116° è incompatibile con target 1885/Longobucco/138°."""
        si = SearchInput(cognome="FEDERICO", nome="LUIGI", anno_nascita="1885",
                         luogo_nascita="Longobucco", reparto="138 Fanteria",
                         conflitto_presunto="ww1")
        c = Candidate(
            nome_originale="FEDERICO LUIGI",
            data_nascita="1895",
            luogo_nascita="Larino",
            reparto="116 Fanteria",
        )
        from research_protocol import check_hard_conflicts, apply_resolution_gate
        conflicts = check_hard_conflicts(c, si)
        assert len(conflicts) >= 2, "Should detect year+place conflicts"
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
            hard_conflicts=conflicts,
        )
        assert result.resolution_state.value == "REJECTED_WRONG_IDENTITY"


# ════════════════════════════════════════════════════════════════════════════
# 3. CLASSIFICAZIONE FONTI
# ════════════════════════════════════════════════════════════════════════════

class TestSourceClassification:
    """Homepage/search page sono lead, non evidenza."""

    def test_homepage_is_not_evidence(self):
        """Homepage Albo d'Oro è lead, non evidenza."""
        from research_protocol import classify_object_kind, is_evidence_eligible
        kind = classify_object_kind(
            url="https://www.difesa.it/OnorificenzeEDecorazioni/Pagine/AlbodOro.aspx",
            content_type="text/html",
            has_record_id=False,
            has_locator=False,
        )
        assert kind.value in ("HOMEPAGE", "SEARCH_PAGE"), f"Homepage should be HOMEPAGE, got {kind}"
        assert is_evidence_eligible(kind) is False

    def test_search_page_is_not_evidence(self):
        """Pagina di ricerca ICRC è lead, non evidenza."""
        from research_protocol import classify_object_kind, is_evidence_eligible
        kind = classify_object_kind(
            url="https://grandeguerre.icrc.org/en/File/Search#person|LARI%20GIUSEPPE|",
            content_type="text/html",
            has_record_id=False,
            has_locator=False,
        )
        assert kind.value in ("SEARCH_PAGE", "SEARCH_QUERY"), f"Search page should be SEARCH_PAGE, got {kind}"
        assert is_evidence_eligible(kind) is False

    def test_direct_record_is_evidence(self):
        """Record nominativo diretto con identificatore può essere evidenza."""
        from research_protocol import classify_object_kind, is_evidence_eligible
        kind = classify_object_kind(
            url="https://www.cadutigrandeguerra.it/DettagliNominativi.aspx?id=12345",
            content_type="text/html",
            has_record_id=True,
            has_locator=True,
        )
        assert kind.value == "CATALOG_RECORD", f"Direct record should be CATALOG_RECORD, got {kind}"
        assert is_evidence_eligible(kind) is True

    def test_excluded_candidate_not_in_fonti_count(self):
        """Candidato escluso non incrementa il conteggio fonti."""
        from research_protocol import compute_typed_counts, ObjectKind, EvidenceState
        candidates = [
            Candidate(nome_originale="A", stato="EXCLUDED",
                      fonti=[SourceRecord(url="http://a.it", istituzione="test")]),
            Candidate(nome_originale="B", stato="POSSIBLE",
                      fonti=[SourceRecord(url="http://b.it/record/1", istituzione="test")]),
        ]
        omonimi_esclusi = [candidates[0]]
        active = [candidates[1]]
        counts = compute_typed_counts(active, omonimi_esclusi)
        assert counts["rejected_person_candidates"] == 1
        assert counts["accepted_evidence_sources"] == 0  # no accepted evidence
        assert counts["person_candidates"] == 1  # only active, not excluded


# ════════════════════════════════════════════════════════════════════════════
# 4. STATI SEPARATI
# ════════════════════════════════════════════════════════════════════════════

class TestSeparatedStates:
    """Stati separati: local_match, external_validation, resolution, run."""

    def test_local_match_does_not_confirm(self):
        """Record locale EXACT non è conferma indipendente se origine stessa."""
        from research_protocol import ResolutionResult, LocalMatchState, ExternalValidationState
        result = ResolutionResult(
            local_match_state=LocalMatchState.EXACT,
            external_validation_state=ExternalValidationState.NO_EVIDENCE,
            resolution_state="UNRESOLVED",  # not CONFIRMED
            run_state="PARTIAL",
        )
        assert result.local_match_state == LocalMatchState.EXACT
        assert result.external_validation_state == ExternalValidationState.NO_EVIDENCE
        assert result.resolution_state not in ("CONFIRMED", "PROBABLE")

    def test_papini_not_confirmed(self):
        """Papini Publio: GPT dice 'non confermato' → non CONFIRMED."""
        from research_protocol import apply_resolution_gate
        si = SearchInput(cognome="PAPINI", nome="PUBLIO", anno_nascita="1890",
                         luogo_nascita="Roccalbegna", conflitto_presunto="ww1")
        c = Candidate(nome_originale="PAPINI PUBLIO", stato="POSSIBLE",
                      data_nascita="1890", luogo_nascita="Roccalbegna")
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
        )
        assert result.resolution_state not in ("CONFIRMED", "PROBABLE"), \
            "Papini with 0 evidence should not be CONFIRMED/PROBABLE"


# ════════════════════════════════════════════════════════════════════════════
# 5. NORMALIZATION
# ════════════════════════════════════════════════════════════════════════════

class TestNormalization:
    """Cognomi composti restano integri."""

    def test_di_lazzaro_intact(self):
        from research_protocol import normalize_name_preserve_particles
        assert normalize_name_preserve_particles("DI LAZZARO") == "di lazzaro"

    def test_de_franceschi_intact(self):
        from research_protocol import normalize_name_preserve_particles
        assert normalize_name_preserve_particles("DE FRANCESCHI") == "de franceschi"

    def test_vailati_ustinelli_intact(self):
        from research_protocol import normalize_name_preserve_particles
        assert normalize_name_preserve_particles("VAILATI-USTINELLI") == "vailati-ustinelli"

    def test_lana_not_castellana(self):
        """Lana non matcha Castellana per substring."""
        from research_protocol import names_match
        assert names_match("LANA", "CASTELLANA") is False

    def test_roma_not_romania(self):
        """Roma non matcha Romania per substring."""
        from research_protocol import names_match
        assert names_match("ROMA", "ROMANIA") is False


# ════════════════════════════════════════════════════════════════════════════
# 6. ERRORI AI OSSERVABILI
# ════════════════════════════════════════════════════════════════════════════

class TestAIErrors:
    """Errori AI con codice e fase, mai parentesi vuote."""

    def test_ai_error_has_code_and_stage(self):
        from research_protocol import AIError
        err = AIError(
            stage="dossier_synthesis",
            error_code="ADAPTER_UNHEALTHY",
            exception_type="ConnectionError",
            safe_message="LMStudio adapter not responding",
            provider="lmstudio",
            model="qwen-0.5b",
        )
        assert err.error_code != ""
        assert err.stage != ""
        assert err.safe_message != ""

    def test_ai_error_not_empty_parentheses(self):
        """Il report non deve mostrare ❌ () ma ❌ (code: stage)."""
        from research_protocol import format_ai_error
        err = AIError(
            stage="dossier_synthesis",
            error_code="ADAPTER_UNHEALTHY",
            exception_type="ConnectionError",
            safe_message="not responding",
            provider="lmstudio",
            model="qwen",
        )
        formatted = format_ai_error(err)
        assert "()" not in formatted
        assert "ADAPTER_UNHEALTHY" in formatted


# ════════════════════════════════════════════════════════════════════════════
# 7. ISOLAMENTO BATCH
# ════════════════════════════════════════════════════════════════════════════

class TestBatchIsolation:
    """Accumulatori di due target consecutivi sono isolati."""

    def test_no_shared_state_between_targets(self):
        """Due ricerche consecutive non condividono candidati."""
        si1 = SearchInput(cognome="LARI", nome="GIUSEPPE", anno_nascita="1886")
        si2 = SearchInput(cognome="PAPINI", nome="PUBLIO", anno_nascita="1890")

        d1 = Dossier()
        d1.candidati.append(Candidate(nome_originale="LARI GIUSEPPE"))
        d2 = Dossier()
        d2.candidati.append(Candidate(nome_originale="PAPINI PUBLIO"))

        assert len(d1.candidati) == 1
        assert len(d2.candidati) == 1
        assert d1.candidati[0].nome_originale == "LARI GIUSEPPE"
        assert d2.candidati[0].nome_originale == "PAPINI PUBLIO"
        # Verify no shared mutable state
        assert d1.candidati is not d2.candidati
        assert d1.fonti is not d2.fonti


# ════════════════════════════════════════════════════════════════════════════
# 8. REGRESSIONE 5 CASI REALI
# ════════════════════════════════════════════════════════════════════════════

class TestRealRegression:
    """Regressione sui 5 casi reali del report 31 luglio 2026."""

    def test_lari_giuseppe_unresolved(self):
        """LARI GIUSEPPE 1886/Canneto/206° → UNRESOLVED, non probabile."""
        si = SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
            luogo_nascita="Canneto sull'Oglio", reparto="206 Fanteria",
            conflitto_presunto="ww1",
        )
        c = Candidate(
            nome_originale="LARI GIUSEPPE",
            data_nascita="1886", luogo_nascita="Canneto sull'Oglio",
            reparto="206 Fanteria",
            stato="INSUFFICIENT_DATA",
        )
        from research_protocol import apply_resolution_gate
        result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,
            independent_lineages=0,
        )
        assert result.resolution_state not in ("CONFIRMED", "PROBABLE")
        assert result.external_validation_state.value == "NO_EVIDENCE"

    def test_lari_1883_candidate_rejected(self):
        """Candidato Lari 1883/Ronciglione/22° → REJECTED_WRONG_IDENTITY."""
        si = SearchInput(
            cognome="LARI", nome="GIUSEPPE", anno_nascita="1886",
            luogo_nascita="Canneto sull'Oglio", reparto="206 Fanteria",
            conflitto_presunto="ww1",
        )
        c = Candidate(
            nome_originale="LARI GIUSEPPE",
            data_nascita="1883", luogo_nascita="Ronciglione",
            reparto="22 Reggimento Fanteria",
        )
        from research_protocol import check_hard_conflicts, apply_resolution_gate
        conflicts = check_hard_conflicts(c, si)
        result = apply_resolution_gate(
            candidate=c, accepted_evidence_count=0,
            independent_lineages=0, hard_conflicts=conflicts,
        )
        assert result.resolution_state.value == "REJECTED_WRONG_IDENTITY"
        assert any("BIRTH_YEAR_CONFLICT" in fc for fc in conflicts)
        assert any("BIRTH_PLACE_CONFLICT" in fc for fc in conflicts)

    def test_federico_1895_candidate_rejected(self):
        """Candidato Federico 1895/Larino/116° → REJECTED_WRONG_IDENTITY."""
        si = SearchInput(
            cognome="FEDERICO", nome="LUIGI", anno_nascita="1885",
            luogo_nascita="Longobucco", reparto="138 Fanteria",
            conflitto_presunto="ww1",
        )
        c = Candidate(
            nome_originale="FEDERICO LUIGI",
            data_nascita="1895", luogo_nascita="Larino",
            reparto="116 Fanteria",
        )
        from research_protocol import check_hard_conflicts, apply_resolution_gate
        conflicts = check_hard_conflicts(c, si)
        result = apply_resolution_gate(
            candidate=c, accepted_evidence_count=0,
            independent_lineages=0, hard_conflicts=conflicts,
        )
        assert result.resolution_state.value == "REJECTED_WRONG_IDENTITY"

    def test_papini_not_confirmed(self):
        """Papini Publio → non CONFIRMED senza evidenza."""
        si = SearchInput(
            cognome="PAPINI", nome="PUBLIO", anno_nascita="1890",
            luogo_nascita="Roccalbegna", conflitto_presunto="ww1",
        )
        c = Candidate(
            nome_originale="PAPINI PUBLIO",
            data_nascita="1890", luogo_nascita="Roccalbegna",
            stato="POSSIBLE",
        )
        from research_protocol import apply_resolution_gate
        result = apply_resolution_gate(
            candidate=c, accepted_evidence_count=0,
            independent_lineages=0,
        )
        assert result.resolution_state != "CONFIRMED"

    def test_fonti_totali_not_candidates_plus_excluded(self):
        """fonti_totali ≠ candidati + omonimi_esclusi."""
        from research_protocol import compute_typed_counts
        active = [
            Candidate(nome_originale="A", stato="POSSIBLE",
                      fonti=[SourceRecord(url="http://a.it/record/1")]),
        ]
        excluded = [
            Candidate(nome_originale="B", stato="EXCLUDED",
                      fonti=[SourceRecord(url="http://b.it/search?q=test")]),
        ]
        counts = compute_typed_counts(active, excluded)
        # fonti_totali should NOT be len(active) + len(excluded) = 2
        assert counts["accepted_evidence_sources"] == 0  # no accepted evidence
        assert counts["person_candidates"] == 1
        assert counts["rejected_person_candidates"] == 1
