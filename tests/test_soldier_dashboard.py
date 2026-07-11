"""Test per soldier_dashboard.py — dashboard investigativa aggregata.

federated_search() e' sempre mockata: la dashboard interroga 11 provider
esterni in _get_external_sources(), e questa suite non deve mai fare
chiamate di rete reali.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato

import soldier_dashboard as sd


class TestGetSoldierDashboard(TempDBTestCase):
    def test_soldato_inesistente(self):
        risultato = sd.get_soldier_dashboard(999999)
        self.assertFalse(risultato["ok"])
        self.assertIn("error", risultato)

    @patch("soldier_dashboard.federated_search")
    def test_soldato_esistente_ha_fatti_verificati(self, mock_fed):
        mock_fed.return_value = []
        conn = self.conn()
        rid = make_internato(conn, cognome="Gaiaschi", nome="Luigi",
                              data_nascita="1920-05-01", luogo_nascita="Bologna",
                              grado="Soldato")
        conn.close()

        dash = sd.get_soldier_dashboard(rid)
        self.assertNotIn("error", dash)
        fatti = {f["fact"]: f for f in dash["facts"]}
        self.assertIn("Identità", fatti)
        self.assertTrue(fatti["Identità"]["verified"])
        self.assertIn("Data nascita", fatti)

    @patch("soldier_dashboard.federated_search")
    def test_luogo_non_validato_risulta_non_verificato(self, mock_fed):
        mock_fed.return_value = []
        conn = self.conn()
        rid = make_internato(conn, luogo_nascita="Bologna", luogo_validato=0)
        conn.close()

        dash = sd.get_soldier_dashboard(rid)
        fatti = {f["fact"]: f for f in dash["facts"]}
        self.assertFalse(fatti["Luogo nascita"]["verified"],
            "Un luogo non ancora validato geograficamente non deve risultare 'verified'.")

    @patch("soldier_dashboard.federated_search")
    def test_fonti_federate_vengono_passate_alla_dashboard(self, mock_fed):
        mock_fed.return_value = [
            {"archivio": "NARA", "titolo": "Foglio matricolare", "access_type": "online",
             "downloadable": True},
        ]
        conn = self.conn()
        rid = make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        dash = sd.get_soldier_dashboard(rid)
        self.assertTrue(mock_fed.called)
        esterne = dash.get("external_sources", [])
        self.assertGreaterEqual(len(esterne), 1)
        self.assertEqual(esterne[0]["availability"], "online")

    @patch("soldier_dashboard.federated_search")
    def test_fonte_federata_con_errore_non_esplode(self, mock_fed):
        mock_fed.return_value = [{"error": "timeout"}]
        conn = self.conn()
        rid = make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()
        dash = sd.get_soldier_dashboard(rid)
        self.assertNotIn("error", dash)  # non deve propagare l'errore del provider come errore globale


if __name__ == "__main__":
    import unittest
    unittest.main()
