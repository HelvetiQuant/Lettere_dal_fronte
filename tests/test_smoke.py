"""Smoke test per i percorsi più fragili di IMI Extractor.

Richiede il database `imi_internati.db` nella root del progetto.
Non dipende da API key esterne.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database import search_all, get_all_records_for_ai
from search_service import search_entities
from memory_router import route_query, extract_cues


class SmokeTest(unittest.TestCase):
    def test_search_all_returns_lettere_personali(self):
        res = search_all("Gaiaschi", limit=20)
        self.assertIn("lettere_personali", res)
        self.assertIn("fonti_narrative", res)
        self.assertIn("internati", res)
        self.assertEqual(res["term"], "Gaiaschi")

    def test_get_all_records_for_ai_returns_lettere_personali(self):
        res = get_all_records_for_ai("Gaiaschi", limit_per_table=10)
        self.assertIn("lettere_personali", res)
        self.assertIsInstance(res["lettere_personali"], list)

    def test_search_entities_basic(self):
        res = search_entities("Rossi", limit=5)
        self.assertIsInstance(res, list)
        if res:
            self.assertIn("entita_id", res[0])
            self.assertIn("valore", res[0])

    def test_memory_router_extract_cues(self):
        cues = extract_cues("Rossi Mario 45 divisione fanteria")
        self.assertEqual(cues["persona"], "Rossi Mario")
        self.assertIn("45", cues.get("reparto", ""))

    def test_memory_router_route_query_structure(self):
        # use_cloud_fallback=False evita chiamate Perplexity
        res = route_query("Rossi Mario", use_cloud_fallback=False)
        self.assertIn("cues", res)
        self.assertIn("route", res)
        self.assertIn("verified_sources", res)
        self.assertIn("confidence", res)

    def test_fastapi_app_imports(self):
        # Verifica che l'app FastAPI si importi senza errori
        import app
        self.assertTrue(hasattr(app, "app"))


if __name__ == "__main__":
    unittest.main()
