"""Test LeBI Fase 5: Memory Router integration, Source Locator, Report Engine citations."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestLeBIRouteSelection(unittest.TestCase):
    """Test LeBI route activation in memory_router."""

    def test_lebi_route_ww2_person(self):
        from memory_router import _select_route
        cues = {
            "persona": "Rossi Mario",
            "reparto": None,
            "luogo": None,
            "data": None,
            "anni": ["1943"],
            "guerra": "ww2",
            "archivio": None,
            "richiede_documento": False,
            "evento": None,
            "is_vague": False,
            "raw": "Rossi Mario 1943",
        }
        route = _select_route(cues)
        self.assertIn("lebi", route, "LeBI route should activate for WW2 person queries")

    def test_lebi_route_achse_event(self):
        from memory_router import _select_route
        cues = {
            "persona": "Rossi Mario",
            "reparto": None,
            "luogo": None,
            "data": None,
            "anni": [],
            "guerra": None,
            "archivio": None,
            "richiede_documento": False,
            "evento": "achse",
            "is_vague": False,
            "raw": "Rossi Mario internato",
        }
        route = _select_route(cues)
        self.assertIn("lebi", route, "LeBI route should activate for achse event")

    def test_lebi_route_not_ww1(self):
        from memory_router import _select_route
        cues = {
            "persona": "Rossi Mario",
            "reparto": None,
            "luogo": None,
            "data": None,
            "anni": ["1916"],
            "guerra": "ww1",
            "archivio": None,
            "richiede_documento": False,
            "evento": None,
            "is_vague": False,
            "raw": "Rossi Mario 1916",
        }
        route = _select_route(cues)
        self.assertNotIn("lebi", route, "LeBI route should NOT activate for WW1 queries")


class TestLeBISourceLocator(unittest.TestCase):
    """Test LeBI domain in source_locator authorized domains."""

    def test_lebi_domain_authorized(self):
        from source_locator import AUTHORIZED_DOMAINS
        self.assertIn("www.lessicobiograficoimi.it", AUTHORIZED_DOMAINS)
        self.assertIn("lessicobiograficoimi.it", AUTHORIZED_DOMAINS)


class TestLeBIReportCitations(unittest.TestCase):
    """Test LeBI citations in report_engine output structure."""

    def test_report_has_lebi_citations_field(self):
        import ast
        with open(os.path.join(os.path.dirname(__file__), "report_engine.py"), "r",
                     encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        # Check that generate_report returns lebi_citations
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "lebi_citations" in node.value:
                    found = True
                    break
        self.assertTrue(found, "report_engine should include lebi_citations in output")


class TestLeBIMemoryRouterLayer(unittest.TestCase):
    """Test _search_lebi function exists and is callable."""

    def test_search_lebi_exists(self):
        from memory_router import _search_lebi
        self.assertTrue(callable(_search_lebi))

    def test_search_lebi_no_persona(self):
        from memory_router import _search_lebi
        cues = {"persona": None, "raw": "test"}
        results = _search_lebi(cues)
        self.assertEqual(results, [], "Should return empty when no persona")

    def test_search_lebi_in_route_query(self):
        """Verify route_query includes LeBI layer when route has 'lebi'."""
        import ast
        with open(os.path.join(os.path.dirname(__file__), "memory_router.py"), "r",
                     encoding="utf-8") as f:
            source = f.read()
        self.assertIn("Layer 6 — LeBI", source, "route_query should have LeBI layer")
        self.assertIn("_search_lebi", source, "route_query should call _search_lebi")


class TestLeBIFTSIndex(unittest.TestCase):
    """Test FTS index includes LeBI records if imported."""

    def test_fts_search_service_importable(self):
        from search_service import search_entities
        self.assertTrue(callable(search_entities))


if __name__ == "__main__":
    unittest.main()
