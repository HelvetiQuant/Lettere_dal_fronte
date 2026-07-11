"""Test per biography.py — dossier narrativo AI con fallback multi-provider.

Richiede `pymupdf` (import fitz, usato da extractor.py) installato — e' gia'
in requirements.txt del progetto. Se manca (es. ambiente minimale), il modulo
viene saltato con uno skip esplicito invece di far fallire l'intera suite.

_call_with_fallback() (la funzione che chiama davvero i provider AI) e'
SEMPRE mockata: questa suite non deve mai consumare crediti API reali.
Un test end-to-end con chiavi vere va fatto separatamente sulla macchina
reale (vedi TODO.md #2 "Dossier verificato").
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato

try:
    import biography as bio
    _IMPORT_ERROR = None
except ImportError as e:  # es. manca pymupdf/fitz in un ambiente minimale
    bio = None
    _IMPORT_ERROR = str(e)


@unittest.skipIf(bio is None, f"biography.py non importabile: {_IMPORT_ERROR}")
class TestGenerateSoldierBiography(TempDBTestCase):

    @patch("biography._call_with_fallback")
    @patch("biography.get_soldier_dashboard")
    def test_soldato_esistente_produce_dossier(self, mock_dash, mock_fallback):
        mock_dash.return_value = {
            "ok": True,
            "soldier": {"id": 1, "cognome": "Gaiaschi", "nome": "Luigi"},
            "summary": "riepilogo finto",
            "facts": [], "timeline": [], "local_sources": [], "external_sources": [],
        }
        mock_fallback.return_value = {
            "ok": True, "provider": "gpt", "model": "gpt-4o", "risposta": "Testo biografia.",
            "cost_usd": 0.01, "fallback_used": False, "attempted_before_success": [],
        }

        risultato = bio.generate_soldier_biography(1)

        self.assertTrue(risultato["ok"])
        self.assertEqual(risultato["subject_type"], "soldier")
        mock_fallback.assert_called_once()

    @patch("biography.get_soldier_dashboard")
    def test_soldato_inesistente_propaga_errore_dashboard(self, mock_dash):
        mock_dash.return_value = {"ok": False, "error": "soldato id=999 non trovato"}
        risultato = bio.generate_soldier_biography(999)
        self.assertFalse(risultato["ok"])

    @patch("biography._call_with_fallback")
    @patch("biography.get_soldier_dashboard")
    def test_tutti_i_provider_falliscono_ritorna_ok_false(self, mock_dash, mock_fallback):
        mock_dash.return_value = {
            "ok": True, "soldier": {"id": 1, "cognome": "Rossi", "nome": "Mario"},
            "summary": "", "facts": [], "timeline": [], "local_sources": [], "external_sources": [],
        }
        mock_fallback.return_value = {
            "ok": False, "error": "Tutti i provider AI configurati hanno fallito.",
            "attempted": [{"provider": "gpt", "error": "no api key"}],
        }
        risultato = bio.generate_soldier_biography(1)
        self.assertFalse(risultato["ok"])


@unittest.skipIf(bio is None, f"biography.py non importabile: {_IMPORT_ERROR}")
class TestGenerateBiographyDispatcher(TempDBTestCase):

    @patch("biography.generate_soldier_biography")
    def test_dispatch_soldier(self, mock_gen):
        mock_gen.return_value = {"ok": True}
        bio.generate_biography("soldier", "42")
        mock_gen.assert_called_once_with(42, provider=None)

    @patch("biography.generate_event_biography")
    def test_dispatch_event(self, mock_gen):
        mock_gen.return_value = {"ok": True}
        bio.generate_biography("event", "battaglia di Caporetto")
        mock_gen.assert_called_once_with("battaglia di Caporetto", provider=None)

    def test_tipo_sconosciuto(self):
        risultato = bio.generate_biography("pianeta", "Marte")
        self.assertFalse(risultato["ok"])


if __name__ == "__main__":
    unittest.main()
