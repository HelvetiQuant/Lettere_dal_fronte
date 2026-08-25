"""Regression tests for Viewpoints V2 — Comparative Historical Reconstruction.

12 mandatory tests covering:
1. Cross-faction agreement → common fact
2. Different casualty figures → divergence, no average
3. Same lineage → single corroboration
4. Silence → NOT_MENTIONED, not DENIED
5. Explicit denial → CONTRADICTED
6. Fact vs interpretation separation
7. Postwar vs contemporary temporal layer
8. German archive, Italian source → Italian alignment
9. Generic geographic page → context only
10. Cross-war claim → blocked
11. AI cannot turn divergence into common fact
12. Follow-up "who was right?" → evidence + limits, not arbitrary choice

EVENT ONLY.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import unittest
from viewpoint_models import (
    FactionAlignment,
    SourceRole,
    TemporalLayer,
    ClaimNature,
    CommonFactStatus,
    DivergenceType,
    DivergenceResolution,
    OmissionStatus,
    PropagandaStatus,
    SourceFactionClassification,
    FactionBundle,
    FactionClaim,
    EventPhase,
)
from source_faction_classifier import classify_source, classify_faction, classify_role, classify_temporal_layer
from faction_bundle_builder import build_faction_bundles
from common_fact_resolver import resolve_common_facts
from divergence_engine import detect_divergences
from omission_detector import detect_omissions
from comparative_narrator import (
    generate_common_ground_narrative,
    generate_divergence_narrative,
    generate_omission_narrative,
)
from viewpoints_service_v2 import compare_viewpoints_v2


class Test1CrossFactionAgreement(unittest.TestCase):
    """TEST 1: Two factions agree on date and location -> common fact."""

    def test_cross_faction_confirmed(self):
        sources = [
            {"source_id": "s1", "label": "Italian war diary", "metadata": {"unit": "regio esercito", "repository": "archivio di stato", "date": "1917-10-25"}},
            {"source_id": "s2", "label": "German war diary", "metadata": {"unit": "heeresgruppe", "repository": "bundesarchiv", "date": "1917-10-25"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "start_date", "value": "1917-10-24", "raw_text": "attack started 24 october", "confidence": 0.9},
            {"source_id": "s2", "predicate": "start_date", "value": "1917-10-24", "raw_text": "Offensive began 24 October", "confidence": 0.9},
            {"source_id": "s1", "predicate": "location", "value": "Isonzo", "raw_text": "sector Isonzo", "confidence": 0.8},
            {"source_id": "s2", "predicate": "location", "value": "Isonzo", "raw_text": "Isonzo front", "confidence": 0.8},
        ]
        event_ctx = {"id": "test1", "nome": "Test Battle", "data_inizio": "1917-10-24", "data_fine": "1917-11-12"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        facts = resolve_common_facts(bundles)

        confirmed = [f for f in facts if f.status == CommonFactStatus.CROSS_FACTION_CONFIRMED]
        self.assertGreater(len(confirmed), 0, "Should have at least one CROSS_FACTION_CONFIRMED fact")
        self.assertIn("start_date", [f.predicate for f in confirmed])


class Test2DifferentCasualtyFigures(unittest.TestCase):
    """TEST 2: Two factions give different casualty figures -> divergence, no average."""

    def test_casualty_divergence_no_average(self):
        sources = [
            {"source_id": "s1", "label": "Italian report", "metadata": {"unit": "regio esercito", "date": "1917-10-25"}},
            {"source_id": "s2", "label": "German report", "metadata": {"unit": "heeresgruppe", "date": "1917-10-25"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "casualties", "value": "10000", "raw_text": "10.000 perdite", "confidence": 0.8},
            {"source_id": "s2", "predicate": "casualties", "value": "18000", "raw_text": "18.000 Verluste", "confidence": 0.8},
        ]
        event_ctx = {"id": "test2", "nome": "Test Battle", "data_inizio": "1917-10-24", "data_fine": "1917-11-12"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        facts = resolve_common_facts(bundles)
        divergences = detect_divergences(bundles, facts)

        casualty_divs = [d for d in divergences if d.divergence_type == DivergenceType.CASUALTY_CONFLICT]
        self.assertGreater(len(casualty_divs), 0, "Should have a CASUALTY_CONFLICT divergence")

        div = casualty_divs[0]
        values = [p["value"] for p in div.faction_positions]
        self.assertIn("10000", values)
        self.assertIn("18000", values)
        self.assertNotIn("14000", values, "Should NOT average the values")

        narrative = generate_divergence_narrative(divergences)
        self.assertIn("10000", narrative)
        self.assertIn("18000", narrative)
        self.assertNotIn("14000", narrative)


class Test3SameLineageSingleCorroboration(unittest.TestCase):
    """TEST 3: Three sources from same lineage -> one independent corroboration."""

    def test_same_lineage_not_independent(self):
        sources = [
            {"source_id": "s1", "label": "Italian bulletin A", "metadata": {"unit": "regio esercito", "lineage_id": "L1"}},
            {"source_id": "s2", "label": "Italian bulletin B", "metadata": {"unit": "regio esercito", "lineage_id": "L1"}},
            {"source_id": "s3", "label": "Italian bulletin C", "metadata": {"unit": "regio esercito", "lineage_id": "L1"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "start_date", "value": "1917-10-24", "raw_text": "started 24 oct", "confidence": 0.9, "lineage_ids": ["L1"]},
            {"source_id": "s2", "predicate": "start_date", "value": "1917-10-24", "raw_text": "started 24 oct", "confidence": 0.9, "lineage_ids": ["L1"]},
            {"source_id": "s3", "predicate": "start_date", "value": "1917-10-24", "raw_text": "started 24 oct", "confidence": 0.9, "lineage_ids": ["L1"]},
        ]
        event_ctx = {"id": "test3", "nome": "Test", "data_inizio": "1917-10-24"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        facts = resolve_common_facts(bundles)

        confirmed = [f for f in facts if f.status == CommonFactStatus.CROSS_FACTION_CONFIRMED]
        self.assertEqual(len(confirmed), 0, "Should NOT be CROSS_FACTION_CONFIRMED - all same faction")


class Test4SilenceNotDenial(unittest.TestCase):
    """TEST 4: One faction silent -> NOT_MENTIONED, not DENIED."""

    def test_silence_is_not_denial(self):
        sources = [
            {"source_id": "s1", "label": "Italian report", "metadata": {"unit": "regio esercito"}},
            {"source_id": "s2", "label": "German report", "metadata": {"unit": "heeresgruppe"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "prisoners", "value": "300 captured", "raw_text": "300 captured", "confidence": 0.8},
        ]
        event_ctx = {"id": "test4", "nome": "Test Battle", "data_inizio": "1917-10-24"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        omissions = detect_omissions(bundles)

        self.assertGreater(len(omissions), 0, "Should detect omission about prisoners")
        om = omissions[0]
        self.assertEqual(om.status, OmissionStatus.NOT_MENTIONED,
                         "Silence should be NOT_MENTIONED, not DENIED")
        self.assertNotEqual(om.status, OmissionStatus.DENIED)

        narrative = generate_omission_narrative(omissions)
        self.assertIn("non menzionato", narrative.lower())


class Test5ExplicitDenial(unittest.TestCase):
    """TEST 5: One faction explicitly denies -> CONTRADICTED."""

    def test_explicit_denial_is_contradicted(self):
        sources = [
            {"source_id": "s1", "label": "Italian report", "metadata": {"unit": "regio esercito"}},
            {"source_id": "s2", "label": "German report", "metadata": {"unit": "heeresgruppe"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "massacre", "value": "500 civilians killed", "raw_text": "500 civilians killed", "confidence": 0.8},
            {"source_id": "s2", "predicate": "massacre", "value": "no civilians were killed, false report", "raw_text": "no civilians killed", "confidence": 0.7},
        ]
        event_ctx = {"id": "test5", "nome": "Test", "data_inizio": "1917-10-24"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        omissions = detect_omissions(bundles)

        # Should detect either DENIED or CONTRADICTED
        denied = [o for o in omissions if o.status == OmissionStatus.DENIED]
        contradicted = [o for o in omissions if o.status == OmissionStatus.CONTRADICTED]
        # At least one should be detected (not just NOT_MENTIONED)
        self.assertTrue(len(denied) > 0 or len(contradicted) > 0,
                        "Explicit denial should be DENIED or CONTRADICTED, not NOT_MENTIONED")


class Test6FactVsInterpretation(unittest.TestCase):
    """TEST 6: Fact vs interpretation -> not merged."""

    def test_fact_interpretation_separation(self):
        sources = [
            {"source_id": "s1", "label": "Italian report", "metadata": {"unit": "regio esercito"}},
            {"source_id": "s2", "label": "German report", "metadata": {"unit": "heeresgruppe"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "movements", "value": "unit retreated 5km", "raw_text": "reparto arretrato 5km", "confidence": 0.8},
            {"source_id": "s1", "predicate": "causes", "value": "retreated due to cowardice of commander", "raw_text": "arretrato per codardia", "confidence": 0.5},
            {"source_id": "s2", "predicate": "movements", "value": "unit retreated 5km", "raw_text": "abgerueckt 5km", "confidence": 0.8},
        ]
        event_ctx = {"id": "test6", "nome": "Test", "data_inizio": "1917-10-24"}
        bundles = build_faction_bundles(sources, observations, event_ctx)

        # Find the interpretation claim
        for bundle in bundles:
            for claim in bundle.claims:
                if "codardia" in claim.value.lower() or "cowardice" in claim.value.lower():
                    self.assertIn(claim.claim_nature, [ClaimNature.INTERPRETATION, ClaimNature.CAUSAL_INTERPRETATION],
                                  "Cowardice attribution should be INTERPRETATION or CAUSAL_INTERPRETATION")
                if "5km" in claim.value.lower() or "arretr" in claim.value.lower():
                    if "codardia" not in claim.value.lower() and "cowardice" not in claim.value.lower():
                        self.assertEqual(claim.claim_nature, ClaimNature.OBSERVABLE_FACT,
                                         "Retreat of 5km should be OBSERVABLE_FACT")

        # Common facts should only include observable facts
        facts = resolve_common_facts(bundles)
        for f in facts:
            if f.status == CommonFactStatus.CROSS_FACTION_CONFIRMED:
                self.assertEqual(f.claim_nature, ClaimNature.OBSERVABLE_FACT,
                                 "Common facts should only be OBSERVABLE_FACT")


class Test7TemporalLayerPreservation(unittest.TestCase):
    """TEST 7: Postwar source vs contemporary -> temporal role preserved."""

    def test_temporal_layer_preserved(self):
        contemporary = classify_temporal_layer(
            {"date": "1917-10-25", "description": "war diary"},
            ("1917-10-24", "1917-11-12"),
        )
        postwar = classify_temporal_layer(
            {"date": "1965-01-01", "description": "memoir"},
            ("1917-10-24", "1917-11-12"),
        )

        self.assertEqual(contemporary, TemporalLayer.CONTEMPORARY)
        self.assertEqual(postwar, TemporalLayer.POSTWAR_TESTIMONY)
        self.assertNotEqual(contemporary, postwar)


class Test8GermanArchiveItalianSource(unittest.TestCase):
    """TEST 8: Source preserved in German archive but produced by Italians -> Italian alignment."""

    def test_faction_not_archive_country(self):
        cls = classify_source(
            source_id="s1",
            source_label="Italian operational order",
            source_metadata={
                "unit": "regio esercito italiano",
                "repository": "bundesarchiv freiburg",
                "description": "Ordine operativo del comando italiano",
                "source_creator_alignment": "ITALIAN",
            },
            event_context={"nome": "Test", "data_inizio": "1917-10-24"},
        )

        self.assertEqual(cls.faction_alignment, FactionAlignment.ITALIAN,
                         "Italian source in German archive should be ITALIAN, not GERMAN")
        self.assertEqual(cls.repository, "bundesarchiv freiburg")


class Test9GenericGeographicPage(unittest.TestCase):
    """TEST 9: Generic geographic page -> context only, cannot corroborate event."""

    def test_generic_geographic_not_corroborating(self):
        cls = classify_source(
            source_id="s1",
            source_label="Geographic encyclopedia: Isonzo river",
            source_metadata={
                "description": "The Isonzo is a river in Slovenia. General geographic information.",
                "repository": "wikipedia",
            },
            event_context={"nome": "Battle of Caporetto", "data_inizio": "1917-10-24"},
        )

        # Should be UNKNOWN or NEUTRAL — not a faction source
        self.assertIn(cls.faction_alignment, [FactionAlignment.UNKNOWN, FactionAlignment.NEUTRAL],
                      "Generic geographic page should not be assigned to a faction")


class Test10CrossWarClaimBlocked(unittest.TestCase):
    """TEST 10: Cross-war claim -> blocked."""

    def test_cross_war_blocked(self):
        # WWII internment link in WWI event
        result = compare_viewpoints_v2(
            event_id="999999",  # non-existent event
            custom_sources=[
                {"source_id": "s1", "label": "Italian WWI diary", "metadata": {"unit": "regio esercito", "war_period": "WWI"}},
                {"source_id": "s2", "label": "WWII internment record", "metadata": {"war_period": "WWII", "link_type": "internato_ww2"}},
            ],
            custom_observations=[
                {"source_id": "s1", "predicate": "start_date", "value": "1917-10-24", "raw_text": "started", "confidence": 0.9},
                {"source_id": "s2", "predicate": "start_date", "value": "1943-09-08", "raw_text": "8 september 1943", "confidence": 0.9},
            ],
        )

        # The WWII source should not produce a CROSS_FACTION_CONFIRMED with the WWI source
        # Different war periods = different events
        if result.get("ok"):
            facts = result.get("common_ground", {}).get("claims", [])
            confirmed = [f for f in facts if f.get("status") == "CROSS_FACTION_CONFIRMED"]
            # Should NOT confirm a 1943 date with a 1917 date
            for f in confirmed:
                if f.get("predicate") == "start_date":
                    self.assertNotEqual(f.get("normalized_value"), "1943-09-08",
                                        "WWII date should not be confirmed with WWI event")


class Test11AICannotTurnDivergenceIntoFact(unittest.TestCase):
    """TEST 11: AI cannot transform a divergence into a shared fact."""

    def test_divergence_preserved_in_narrative(self):
        sources = [
            {"source_id": "s1", "label": "Italian report", "metadata": {"unit": "regio esercito"}},
            {"source_id": "s2", "label": "German report", "metadata": {"unit": "heeresgruppe"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "casualties", "value": "10000", "raw_text": "10000", "confidence": 0.8},
            {"source_id": "s2", "predicate": "casualties", "value": "18000", "raw_text": "18000", "confidence": 0.8},
        ]
        event_ctx = {"id": "test11", "nome": "Test", "data_inizio": "1917-10-24"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        facts = resolve_common_facts(bundles)
        divergences = detect_divergences(bundles, facts)

        # Common ground narrative should NOT contain the conflicting values as confirmed
        common_narrative = generate_common_ground_narrative(facts)
        self.assertNotIn("10000", common_narrative,
                         "Conflicting value should not appear in common ground")
        self.assertNotIn("18000", common_narrative,
                         "Conflicting value should not appear in common ground")

        # Divergence narrative SHOULD contain both
        div_narrative = generate_divergence_narrative(divergences)
        self.assertIn("10000", div_narrative)
        self.assertIn("18000", div_narrative)


class Test12FollowupWhoWasRight(unittest.TestCase):
    """TEST 12: Follow-up 'who was right?' -> evidence and limits, not arbitrary choice."""

    def test_no_arbitrary_resolution(self):
        sources = [
            {"source_id": "s1", "label": "Italian report", "metadata": {"unit": "regio esercito", "date": "1917-10-25"}},
            {"source_id": "s2", "label": "German memoir", "metadata": {"unit": "heeresgruppe", "date": "1965-01-01"}},
        ]
        observations = [
            {"source_id": "s1", "predicate": "casualties", "value": "10000", "raw_text": "10000", "confidence": 0.8, "temporal_proximity": 0.9},
            {"source_id": "s2", "predicate": "casualties", "value": "18000", "raw_text": "18000", "confidence": 0.6, "temporal_proximity": 0.2},
        ]
        event_ctx = {"id": "test12", "nome": "Test", "data_inizio": "1917-10-24", "data_fine": "1917-11-12"}
        bundles = build_faction_bundles(sources, observations, event_ctx)
        facts = resolve_common_facts(bundles)
        divergences = detect_divergences(bundles, facts)

        # The divergence should NOT be automatically resolved as "Italian was right"
        for div in divergences:
            if div.divergence_type == DivergenceType.CASUALTY_CONFLICT:
                # Should be UNRESOLVED or RESOLVED_BY_STRONGER_EVIDENCE with explicit reason
                self.assertIn(div.resolution, [
                    DivergenceResolution.UNRESOLVED,
                    DivergenceResolution.RESOLVED_BY_STRONGER_EVIDENCE,
                ])
                # If resolved by stronger evidence, must have explicit reason
                if div.resolution == DivergenceResolution.RESOLVED_BY_STRONGER_EVIDENCE:
                    self.assertTrue(len(div.resolution_reason) > 10,
                                    "Resolution must have explicit probatory reason")
                    # Reason should mention temporal proximity or lineage, not AI intuition
                    self.assertTrue(
                        any(w in div.resolution_reason.lower() for w in ["temporal", "lineage", "contemporary", "postwar"]),
                        "Resolution reason must cite probatory criterion, not AI intuition"
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
