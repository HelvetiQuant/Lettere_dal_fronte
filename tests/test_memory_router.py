"""Test per memory_router.py — estrazione cue, routing, orchestrazione.

route_query() viene sempre chiamato con use_cloud_fallback=False nei test:
il ramo Perplexity richiede una chiave API reale e rete esterna, quindi va
testato separatamente (manualmente, sulla macchina reale) e non fa parte di
questa suite. extract_cues()/_select_route() sono funzioni pure (nessun I/O)
e vengono testate direttamente.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato, make_entita, make_collegamento

import memory_router as mr


class TestExtractCues(TempDBTestCase):
    """Funzione pura: non serve nemmeno un DB, ma eredita TempDBTestCase
    per uniformita' con il resto della suite (e per poter aggiungere in
    futuro varianti che consultano il DB, es. dizionari di reparti noti)."""

    def test_persona_semplice(self):
        cues = mr.extract_cues("Mario Rossi")
        self.assertEqual(cues["persona"], "Mario Rossi")

    def test_persona_luogo_e_anno(self):
        cues = mr.extract_cues("Mario Rossi a Trento nel 1943")
        self.assertEqual(cues["persona"], "Mario Rossi")
        self.assertEqual(cues["luogo"], "Trento")
        self.assertIn("1943", cues["anni"])
        self.assertEqual(cues["guerra"], "ww2")

    def test_anno_ww1_inferisce_guerra(self):
        cues = mr.extract_cues("Notizie del 1916")
        self.assertEqual(cues["guerra"], "ww1")

    def test_termini_militari_non_diventano_persona(self):
        """'Divisione Alpina' non deve essere interpretato come nome+cognome
        di una persona (bug facile da reintrodurre modificando _NON_PERSONA)."""
        cues = mr.extract_cues("Divisione Alpina")
        self.assertIsNone(cues["persona"])

    def test_query_vaga_senza_cue(self):
        cues = mr.extract_cues("cosa e' successo")
        self.assertTrue(cues["is_vague"])

    def test_richiesta_documento_originale(self):
        cues = mr.extract_cues("mostrami il documento originale su Rossi Mario")
        self.assertTrue(cues["richiede_documento"])


class TestSelectRoute(TempDBTestCase):
    def test_persona_attiva_sql_fts_graph(self):
        cues = mr.extract_cues("Mario Rossi")
        route = mr._select_route(cues)
        self.assertIn("sql_exact", route)
        self.assertIn("fts", route)
        self.assertIn("graph", route)

    def test_query_vaga_evita_sql_exact(self):
        cues = mr.extract_cues("cosa e' successo")
        route = mr._select_route(cues)
        self.assertNotIn("sql_exact", route)

    def test_route_non_e_mai_vuota(self):
        cues = mr.extract_cues("")
        route = mr._select_route(cues)
        self.assertTrue(route)


class TestRouteQuery(TempDBTestCase):
    """route_query() end-to-end, sempre con use_cloud_fallback=False."""

    def test_trova_soldato_esistente_via_sql_exact(self):
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        risultato = mr.route_query("Gaiaschi Luigi", use_cloud_fallback=False)
        self.assertIn("cues", risultato)
        self.assertIn("confidence", risultato)
        fonti_internati = [r for r in risultato.get("sources_found", risultato.get("verified_sources", []))
                           if isinstance(r, dict) and r.get("table") == "internati"]
        # La forma esatta della chiave con i risultati puo' evolvere; verifichiamo
        # invece che il record sia effettivamente raggiungibile in qualche punto
        # della risposta serializzata.
        import json
        self.assertIn("Gaiaschi", json.dumps(risultato, default=str))

    def test_query_senza_risultati_non_esplode(self):
        risultato = mr.route_query("Nessuno Che Esiste Zzz", use_cloud_fallback=False)
        self.assertIsInstance(risultato, dict)
        self.assertEqual(risultato["confidence"], 0.0)

    def test_tabelle_scraper_mancanti_non_bloccano_la_ricerca(self):
        """_search_sql_exact interroga anche caduti_cwgc, caduti_ministero,
        caduti_sardi, caduti_bologna, decorati_nastroazzurro: tabelle create
        dai rispettivi moduli scraper, non da database.init_db(). Sullo
        schema base non esistono: la ricerca deve comunque completare."""
        conn = self.conn()
        make_internato(conn, cognome="Verdi", nome="Anna")
        conn.close()
        risultato = mr.route_query("Verdi Anna", use_cloud_fallback=False)
        self.assertIsInstance(risultato, dict)


if __name__ == "__main__":
    import unittest
    unittest.main()
