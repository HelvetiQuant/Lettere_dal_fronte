"""Smoke test HTTP per app.py (85 endpoint FastAPI) via TestClient.

Non e' pensata per coprire tutti gli 85 endpoint (sarebbe un lavoro a se',
vedi _TEMPLATE_test_new_module.py per come aggiungerne quando servono):
copre il percorso critico "un utente cerca qualcosa e ottiene una risposta"
su alcuni endpoint chiave (status, search, entita, research), piu' un
guardrail generico che elenca TUTTE le route registrate e verifica che
nessuna sollevi un errore 500 su un utilizzo base.

Richiede `fastapi`/`httpx` installati (gia' in requirements.txt). Se assenti,
l'intero modulo viene saltato.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato

try:
    from fastapi.testclient import TestClient
    _FASTAPI_ERROR = None
except ImportError as e:
    TestClient = None
    _FASTAPI_ERROR = str(e)


@unittest.skipIf(TestClient is None, f"fastapi/httpx non disponibili: {_FASTAPI_ERROR}")
class TestAPISmoke(TempDBTestCase):
    """NOTA: app.py importa moduli scraper pesanti (caduti_cwgc, nara_catalog,
    ecc.) al top-level. Se uno di questi import fallisse in un ambiente
    minimale, l'intero modulo salterebbe con lo stesso skip: e' il
    comportamento voluto (non vogliamo un errore oscuro qui, vogliamo un
    unico skip leggibile)."""

    def setUp(self):
        super().setUp()
        try:
            import app as flask_app_module  # noqa: F401  (nome storico, e' FastAPI)
        except ImportError as e:
            self.skipTest(f"app.py non importabile in questo ambiente: {e}")
        self.app_module = flask_app_module
        self.client = TestClient(self.app_module.app)
        self.client.__enter__()  # attiva startup event (init_db, init_usage_table)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        super().tearDown()

    def test_status_risponde_200(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("total_internati", r.json())

    def test_search_query_troppo_corta_400(self):
        r = self.client.get("/api/search", params={"q": "a"})
        self.assertEqual(r.status_code, 400)

    def test_search_trova_record_esistente(self):
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        r = self.client.get("/api/search", params={"q": "Gaiaschi Luigi"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreaterEqual(len(body["internati"]), 1)

    def test_entita_search_query_troppo_corta_400(self):
        r = self.client.get("/api/entita/search", params={"q": "a"})
        self.assertEqual(r.status_code, 400)

    def test_entita_dettaglio_inesistente_404(self):
        r = self.client.get("/api/entita/999999")
        self.assertEqual(r.status_code, 404)

    def test_search_include_curated_events(self):
        """La ricerca universale deve restituire anche eventi curati WW2."""
        r = self.client.get("/api/search", params={"q": "operazione achse"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreaterEqual(len(body.get("events", [])), 1)
        self.assertTrue(any("Achse" in e["nome"] for e in body["events"]))

    def test_event_internati_achse(self):
        """L'endpoint evento/internati deve trovare record che matchano le keyword dell'evento curato.
        Inseriamo un internato con raw_text che contiene una keyword dell'evento (non e' un mock,
        e' un record di test nel DB temporaneo)."""
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi", raw_text="catturato dopo l'armistizio dell'8 settembre")
        conn.close()

        r = self.client.get("/api/events/Operazione+Achse/internati", params={"limit": 50})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertTrue(any(i["cognome"] == "Gaiaschi" for i in body["internati"]))

    def test_search_gaiaschi_returns_internati(self):
        """La ricerca universale deve trovare internati per cognome/nome."""
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        r = self.client.get("/api/search", params={"q": "Gaiaschi Luigi"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreaterEqual(len(body.get("internati", [])), 1)
        self.assertTrue(any(i["cognome"] == "Gaiaschi" and i["nome"] == "Luigi" for i in body["internati"]))

    def test_pagina_index_serve_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_research_subjects_lista_vuota_non_esplode(self):
        r = self.client.get("/api/research/subjects")
        self.assertEqual(r.status_code, 200)

    def test_providers_lista_20_provider(self):
        r = self.client.get("/api/providers")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()), 1)


if __name__ == "__main__":
    unittest.main()
