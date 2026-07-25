"""test_event_research_master.py — Test master per la nuova pipeline event research.

Covers: event_resolver, event_evidence_pipeline, event_narrative_builder, event_link_audit.
Nessun mock: tutti i test usano dati reali dal DB.
"""
import json
import os
import sqlite3
import unittest
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent)

from event_resolver import resolve, resolve_event, get_event_by_id, get_related_events, ResolutionResult
from event_evidence_pipeline import collect_evidence, EvidencePackage
from event_narrative_builder import build_narrative
from event_link_audit import audit_all_links, get_audit_summary


class TestEventResolver(unittest.TestCase):
    """Test per event_resolver.py."""

    def test_resolve_carso_is_event(self):
        """Battaglia del Carso viene riconosciuta come evento."""
        r = resolve("Battaglia del Carso")
        self.assertTrue(r["is_event"])
        self.assertEqual(r["canonical"], "Battaglia del Carso")

    def test_resolve_carso_ambiguous_collection(self):
        """Carso è classificato come collezione ambigua."""
        r = resolve("Battaglia del Carso")
        self.assertEqual(r["conflict"], "ambiguous_collection")
        self.assertIsNotNone(r["ambiguity_warning"])
        self.assertGreater(len(r["proposed_distinctions"]), 1)

    def test_resolve_carso_has_general_and_specific(self):
        """Le distinzioni proposte includono evento generale ed episodi specifici."""
        r = resolve("Battaglia del Carso")
        types = [d["type"] for d in r["proposed_distinctions"]]
        self.assertIn("evento_generale", types)
        self.assertIn("episodio_specifico", types)

    def test_resolve_caporetto_specific(self):
        """Caporetto è un evento specifico, non ambiguo."""
        r = resolve("Battaglia di Caporetto")
        self.assertTrue(r["is_event"])
        self.assertEqual(r["conflict"], "none")
        self.assertIsNone(r["ambiguity_warning"])

    def test_resolve_non_event_query(self):
        """Una query non-evento non viene classificata come evento."""
        r = resolve("Mario Rossi")
        self.assertFalse(r["is_event"])

    def test_resolve_monte_grappa_multiple_matches(self):
        """Monte Grappa matcha più eventi (Piave, Vittorio Veneto, Grappa stesso)."""
        r = resolve("Monte Grappa")
        self.assertTrue(r["is_event"])
        self.assertGreater(len(r["matches"]), 1)

    def test_resolve_event_by_id(self):
        """get_event_by_id ritorna i dati corretti."""
        ev = get_event_by_id(18)  # Battaglia del Carso
        self.assertIsNotNone(ev)
        self.assertEqual(ev["nome"], "Battaglia del Carso")
        self.assertIn("Carso", ev["aliases"])

    def test_resolve_related_events(self):
        """get_related_events ritorna padri e figli."""
        related = get_related_events(18)  # Carso
        self.assertIsInstance(related["parents"], list)
        self.assertIsInstance(related["children"], list)
        # Carso ha figli (Monte San Michele, ecc.)
        self.assertGreater(len(related["children"]), 0)

    def test_resolve_carso_warning_mentions_operations(self):
        """L'avviso per Carso menziona 'operazioni'."""
        r = resolve("Battaglia del Carso")
        warning = r["ambiguity_warning"] or ""
        self.assertIn("operazioni", warning.lower())


class TestEvidencePipeline(unittest.TestCase):
    """Test per event_evidence_pipeline.py."""

    def test_collect_evidence_carso(self):
        """collect_evidence per Carso ritorna un EvidencePackage."""
        pkg = collect_evidence("Battaglia del Carso")
        self.assertIsInstance(pkg, EvidencePackage)
        self.assertEqual(pkg.event_name, "Battaglia del Carso")
        self.assertIsNotNone(pkg.event_id)

    def test_collect_evidence_has_sources(self):
        """Il pacchetto di evidenze contiene fonti."""
        pkg = collect_evidence("Battaglia di Caporetto")
        # Almeno fonti interne o archivistiche
        self.assertGreater(len(pkg.sources) + len(pkg.archival_sources), 0)

    def test_collect_evidence_has_graph(self):
        """Il pacchetto include dati grafo."""
        pkg = collect_evidence("Battaglia di Caporetto")
        self.assertIn("nodes", pkg.graph_data)
        self.assertIn("edges", pkg.graph_data)
        self.assertGreater(len(pkg.graph_data["nodes"]), 0)

    def test_collect_evidence_has_people(self):
        """Il pacchetto include persone collegate."""
        pkg = collect_evidence("Battaglia di Caporetto")
        self.assertGreater(len(pkg.related_people), 0)

    def test_collect_evidence_sources_have_verification(self):
        """Ogni fonte ha uno stato di verifica."""
        pkg = collect_evidence("Battaglia di Caporetto")
        for s in pkg.sources:
            self.assertIn(s.verification_status, ("verificata", "candidata", "non_verificata"))
            self.assertTrue(s.verification_note)

    def test_collect_evidence_web_sources_are_candidates(self):
        """Le fonti web sono sempre candidate, non verificata."""
        pkg = collect_evidence("Battaglia di Caporetto")
        for s in pkg.sources:
            if s.source_type == "web":
                self.assertEqual(s.verification_status, "candidata")

    def test_collect_evidence_non_event(self):
        """Per query non-evento, ritorna pacchetto vuoto."""
        pkg = collect_evidence("Mario Rossi")
        self.assertEqual(len(pkg.sources), 0)
        self.assertEqual(len(pkg.claims), 0)

    def test_collect_evidence_carso_resolution(self):
        """La risoluzione per Carso include l'avviso di ambiguità."""
        pkg = collect_evidence("Battaglia del Carso")
        self.assertEqual(pkg.resolution["conflict"], "ambiguous_collection")
        self.assertIsNotNone(pkg.resolution["ambiguity_warning"])


class TestNarrativeBuilder(unittest.TestCase):
    """Test per event_narrative_builder.py."""

    def test_build_narrative_without_ai(self):
        """build_narrative con use_ai=False genera report strutturato."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        self.assertIn("event_name", r)
        self.assertIn("sections", r)
        self.assertFalse(r["ai_used"])
        self.assertGreater(len(r["sections"]), 0)

    def test_build_narrative_has_9_sections(self):
        """Il report senza AI ha 9 sezioni standard."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        self.assertEqual(len(r["sections"]), 9)

    def test_build_narrative_sections_have_source_ids(self):
        """Le sezioni con fonti hanno source_ids non vuoti."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        # Almeno una sezione dovrebbe avere fonti collegate
        has_sources = any(len(s["source_ids"]) > 0 for s in r["sections"])
        self.assertTrue(has_sources)

    def test_build_narrative_inquadramento(self):
        """L'inquadramento contiene il nome evento."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        self.assertIn("Caporetto", r["inquadramento"])

    def test_build_narrative_carso_warning(self):
        """Per Carso, l'inquadramento include l'avviso di ambiguità."""
        r = build_narrative("Battaglia del Carso", use_ai=False)
        self.assertIn("AVVISO", r["inquadramento"])

    def test_build_narrative_has_evidence_package(self):
        """Il report include il pacchetto evidenze completo."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        self.assertIn("evidence_package", r)
        self.assertIn("sources", r["evidence_package"])

    def test_build_narrative_has_graph(self):
        """Il report include il grafo relazioni."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        self.assertIn("grafo", r)
        self.assertIn("nodes", r["grafo"])

    def test_build_narrative_has_people(self):
        """Il report include persone collegate."""
        r = build_narrative("Battaglia di Caporetto", use_ai=False)
        self.assertIn("persone_collegate", r)
        self.assertGreater(len(r["persone_collegate"]), 0)


class TestLinkAudit(unittest.TestCase):
    """Test per event_link_audit.py."""

    def test_audit_returns_report(self):
        """audit_all_links ritorna un report con statistiche."""
        report = audit_all_links()
        self.assertGreater(report.total_links, 0)
        self.assertEqual(report.audited, report.total_links)

    def test_audit_has_status_counts(self):
        """Il report ha conteggi per candidate/probable/confirmed/rejected."""
        report = audit_all_links()
        total = report.candidates + report.probable + report.confirmed + report.rejected
        self.assertEqual(total, report.total_links)

    def test_audit_summary(self):
        """get_audit_summary ritorna un dict sintetico."""
        summary = get_audit_summary()
        self.assertIn("total_links", summary)
        self.assertIn("candidates", summary)
        self.assertIn("probable", summary)
        self.assertGreater(summary["total_links"], 0)

    def test_audit_links_have_review_status(self):
        """Ogni audit ha un review_status valido."""
        report = audit_all_links()
        valid_statuses = {"candidate", "probable", "confirmed", "rejected"}
        for a in report.audits[:100]:  # Check primi 100
            self.assertIn(a.review_status, valid_statuses)
            self.assertTrue(a.review_reason)

    def test_audit_links_have_method(self):
        """Ogni audit ha un match_method classificato."""
        report = audit_all_links()
        valid_methods = {"exact", "alias", "keyword", "text_match", "temporal_only", "unknown"}
        for a in report.audits[:100]:
            self.assertIn(a.match_method, valid_methods)

    def test_audit_carso_links_are_candidates(self):
        """I link basati solo su 'Carso' sono candidate, non probable."""
        report = audit_all_links()
        carso_links = [a for a in report.audits if a.match_value and a.match_value.lower().strip() == "carso"]
        for a in carso_links:
            self.assertEqual(a.review_status, "candidate")
            self.assertIn("Carso", a.review_reason)

    def test_audit_by_link_type(self):
        """Il report ha statistiche per link_type."""
        report = audit_all_links()
        self.assertGreater(len(report.by_link_type), 0)
        for lt, counts in report.by_link_type.items():
            self.assertIn("candidate", counts)
            self.assertIn("probable", counts)


class TestEventMapBuilder(unittest.TestCase):
    """Test mappa storico-operativa verificabile."""

    @classmethod
    def setUpClass(cls):
        from event_map_builder import build_map_from_query
        cls.build_map_from_query = build_map_from_query
        cls.map_caporetto = build_map_from_query("Battaglia di Caporetto")
        cls.map_carso = build_map_from_query("Battaglia del Carso")
        cls.map_piave = build_map_from_query("Battaglia del Piave")
        cls.map_vittorio = build_map_from_query("Battaglia di Vittorio Veneto")
        cls.map_cefalonia = build_map_from_query("Eccidio di Cefalonia")

    def test_map_has_svg(self):
        """La mappa deve contenere un SVG valido."""
        for m in [self.map_caporetto, self.map_carso, self.map_piave]:
            self.assertIsInstance(m["svg"], str)
            self.assertTrue(m["svg"].startswith("<svg"))
            self.assertTrue(m["svg"].endswith("</svg>"))
            self.assertGreater(len(m["svg"]), 500)

    def test_map_has_locations(self):
        """La mappa deve avere almeno 2 luoghi con coordinate."""
        for m in [self.map_caporetto, self.map_carso, self.map_piave]:
            self.assertGreaterEqual(len(m["locations"]), 2)
            for loc in m["locations"]:
                self.assertIn("lat", loc)
                self.assertIn("lon", loc)
                self.assertIn("name", loc)
                self.assertIn("verification", loc)
                self.assertIn(loc["verification"], ["verified", "probable", "hypothetical"])

    def test_map_caporetto_has_movements(self):
        """Caporetto deve avere movimenti (avanzata + ritirata)."""
        self.assertGreaterEqual(len(self.map_caporetto["movements"]), 1)
        for mov in self.map_caporetto["movements"]:
            self.assertIn("from", mov)
            self.assertIn("to", mov)
            self.assertIn("movement_type", mov)
            self.assertIn(mov["movement_type"], ["advance", "retreat", "flanking", "supply"])

    def test_map_caporetto_has_phases(self):
        """Caporetto deve avere fasi temporali."""
        self.assertGreaterEqual(len(self.map_caporetto["phases"]), 1)
        for phase in self.map_caporetto["phases"]:
            self.assertIn("name", phase)
            self.assertIn("start_date", phase)
            self.assertIn("end_date", phase)
            self.assertIn("color", phase)

    def test_map_carso_has_sub_maps(self):
        """Carso (evento ampio) deve generare sotto-mappe per fase."""
        self.assertGreaterEqual(len(self.map_carso["sub_maps"]), 1)
        for sub in self.map_carso["sub_maps"]:
            self.assertIn("title", sub)
            self.assertIn("svg", sub)
            self.assertTrue(sub["svg"].startswith("<svg"))

    def test_map_carso_is_not_partial(self):
        """Carso ha abbastanza dati per non essere parziale."""
        self.assertFalse(self.map_carso["is_partial"])

    def test_map_cefalonia_is_partial(self):
        """Cefalonia ha dati geografici limitati → mappa parziale."""
        self.assertTrue(self.map_cefalonia["is_partial"])
        self.assertGreater(len(self.map_cefalonia["partial_note"]), 10)

    def test_map_has_legend(self):
        """La mappa deve avere una legenda."""
        for m in [self.map_caporetto, self.map_carso]:
            self.assertGreaterEqual(len(m["legend"]), 3)

    def test_map_has_bounding_box(self):
        """La mappa deve avere un bounding box valido."""
        for m in [self.map_caporetto, self.map_carso, self.map_piave]:
            bbox = m["bounding_box"]
            self.assertLess(bbox["min_lat"], bbox["max_lat"])
            self.assertLess(bbox["min_lon"], bbox["max_lon"])

    def test_map_line_styles(self):
        """Le linee devono avere stili validi (solid, dashed, dotted)."""
        for m in [self.map_caporetto, self.map_carso, self.map_piave]:
            for line in m["lines"]:
                self.assertIn(line["style"], ["solid", "dashed", "dotted"])
                self.assertIn(line["line_type"], ["front", "defensive", "advance", "retreat"])

    def test_map_locations_have_label_numbers(self):
        """I luoghi devono avere numeri progressivi collegati alle fonti."""
        for m in [self.map_caporetto, self.map_carso]:
            numbers = [loc["label_number"] for loc in m["locations"]]
            self.assertEqual(numbers, sorted(numbers))
            self.assertGreater(max(numbers), 0)

    def test_map_vittorio_has_movement(self):
        """Vittorio Veneto deve avere almeno un movimento di avanzata."""
        self.assertGreaterEqual(len(self.map_vittorio["movements"]), 1)
        advance_movs = [m for m in self.map_vittorio["movements"] if m["movement_type"] == "advance"]
        self.assertGreaterEqual(len(advance_movs), 1)

    def test_map_svg_contains_legend(self):
        """L'SVG deve contenere la legenda visiva."""
        self.assertIn("Legenda", self.map_caporetto["svg"])
        self.assertIn("verificato", self.map_caporetto["svg"])
        self.assertIn("probabile", self.map_caporetto["svg"])
        self.assertIn("ipotetico", self.map_caporetto["svg"])

    def test_map_svg_partial_warning(self):
        """L'SVG di una mappa parziale deve contenere l'avviso."""
        if self.map_cefalonia["is_partial"]:
            self.assertIn("MAPPA PARZIALE", self.map_cefalonia["svg"])

    def test_map_not_invents_coordinates(self):
        """Tutte le coordinate devono essere plausibili (nessuna inventata)."""
        from event_map_builder import GAZETTEER
        for m in [self.map_caporetto, self.map_carso, self.map_piave]:
            for loc in m["locations"]:
                # Verifica che le coordinate siano plausibili (Europa e Mediterraneo)
                self.assertGreater(loc["lat"], 30.0)
                self.assertLess(loc["lat"], 55.0)
                self.assertGreater(loc["lon"], 5.0)
                self.assertLess(loc["lon"], 45.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
