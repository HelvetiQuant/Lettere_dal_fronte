"""Test per enrich_entities.py — arricchimento entità con fonti esterne.

Focus:
- resume robusto dopo interruzione a metà batch
- tracking granulare degli ID completati
"""
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato

import enrich_entities as ee


class _MockFederation:
    """Finta federated_search che matcha per cognome (TestN) nella query.

    Puo' simulare un fallimento per specifici cognomi, utile per testare il resume.
    """

    def __init__(self, fail_cognomi=None, delay: float = 0.0):
        self.fail_cognomi = set(fail_cognomi or [])
        self.delay = delay
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, query, cues=None, providers=None):
        with self.lock:
            self.calls.append(query)
        time.sleep(self.delay)
        # Match per cognome TestN nella query
        for cognome in self.fail_cognomi:
            if cognome in (query or ""):
                raise RuntimeError(f"fallimento simulato per {cognome}")
        return [
            {
                "provider": "tna",
                "archivio": "TNA",
                "titolo": f"Scheda per {query[:40]}",
                "catalog_url": "https://discovery.nationalarchives.gov.uk/details/r/mock",
                "direct_url": "https://discovery.nationalarchives.gov.uk/details/r/mock",
                "source_type": "documento",
                "score": 0.7,
            }
        ]


class TestEnrichEntitiesResume(TempDBTestCase):
    schema_modules = ("source_locator",)

    def setUp(self):
        super().setUp()
        # enrich_entities importa DB_PATH da database a livello modulo;
        # il patch di database.DB_PATH non si propaga, quindi patchiamo anche ee.
        ee.DB_PATH = self.db_path

    def _patch_state(self, tmp_state_path: Path):
        ee.STATE_PATH = tmp_state_path

    def _insert_internati(self, count: int):
        ids = []
        cognomi = []
        for i in range(count):
            cognome = f"Test{i}"
            rid = make_internato(
                self.conn(),
                cognome=cognome,
                nome="Mario",
                luogo_cattura="Cefalonia" if i % 2 == 0 else "Tobruk",
            )
            ids.append(rid)
            cognomi.append(cognome)
        return ids, cognomi

    def test_resume_riprende_dopo_interruzione_a_meta_batch(self):
        """Simula: 10 internati, falliscono i cognomi Test3..Test9, poi resume.

        Lo stato salvato deve riprendere dall'ID piu' alto completato con
        successo (Test2), non dall'ultimo ID del batch.
        """
        ids, cognomi = self._insert_internati(10)
        tmp_state = Path(self._tmpdir.name) / "state.json"
        self._patch_state(tmp_state)

        # Primo run: falliscono i cognomi Test3..Test9
        fail_cognomi = set(cognomi[3:])
        mock = _MockFederation(fail_cognomi=fail_cognomi, delay=0.01)
        with patch.object(ee, "federated_search", mock):
            stats = ee.enrich(
                limit=10,
                offset=0,
                max_results_per_entity=1,
                delay=0.05,
                workers=2,
            )

        # Hanno successo solo i primi 3 (Test0, Test1, Test2)
        self.assertEqual(stats["completed"], 3)
        self.assertEqual(stats["last_processed_id"], ids[2])
        state = ee._load_state()
        self.assertEqual(state["last_processed_id"], ids[2])

        # Secondo run: i rimanenti 7 vanno a buon fine
        mock2 = _MockFederation(delay=0.01)
        with patch.object(ee, "federated_search", mock2):
            stats2 = ee.enrich(
                limit=10,
                offset=state["last_processed_id"],
                max_results_per_entity=1,
                delay=0.05,
                workers=2,
            )

        self.assertEqual(stats2["completed"], 7)
        self.assertEqual(stats2["last_processed_id"], ids[-1])

        # Verifica totale fonti create
        conn = self.conn()
        count = conn.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
        conn.close()
        self.assertEqual(count, 10)

    def test_fetch_internati_usa_after_id(self):
        """fetch_internati deve rispettare after_id, non offset."""
        ids, _ = self._insert_internati(5)
        # after_id = ids[1] deve restituire gli ID da ids[2] in poi
        rows = ee.fetch_internati(limit=10, after_id=ids[1])
        fetched_ids = [r["id"] for r in rows]
        self.assertNotIn(ids[0], fetched_ids)
        self.assertNotIn(ids[1], fetched_ids)
        self.assertIn(ids[2], fetched_ids)
        self.assertIn(ids[-1], fetched_ids)
