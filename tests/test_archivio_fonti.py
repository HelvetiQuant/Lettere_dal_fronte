"""Test per archivio_fonti.py — ingestione documenti originali, dedup via SHA256.

Nota architetturale: STORAGE_DIR e' un altro esempio (oltre a DB_PATH in
credits.py, vedi TODO.md #1) di path hardcoded a livello di modulo
(`Path(__file__).parent / "archivio_storage"`) invece che configurabile.
Qui lo ripuntiamo a una cartella temporanea in setUp/tearDown per non
scrivere file nella vera cartella del repo durante i test.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase

import archivio_fonti as af


class ArchivioFontiTestCase(TempDBTestCase):
    schema_modules = ("archivio_fonti",)

    def setUp(self):
        super().setUp()
        self._storage_tmp = tempfile.TemporaryDirectory()
        self._original_storage_dir = af.STORAGE_DIR
        af.STORAGE_DIR = Path(self._storage_tmp.name)

    def tearDown(self):
        af.STORAGE_DIR = self._original_storage_dir
        self._storage_tmp.cleanup()
        super().tearDown()

    def _make_temp_file(self, name="test.jpg", content=b"contenuto finto immagine di test"):
        tmp = tempfile.NamedTemporaryFile(suffix=Path(name).suffix, delete=False)
        tmp.write(content)
        tmp.close()
        return Path(tmp.name)


class TestIngestFile(ArchivioFontiTestCase):
    def test_ingest_file_inserisce_record(self):
        f = self._make_temp_file()
        risultato = af.ingest_file(f, archivio="TEST", tipo_documento="foto")
        self.assertNotIn("error", risultato)
        self.assertIn("id", risultato)

    def test_formato_non_supportato_ritorna_errore(self):
        f = self._make_temp_file(name="test.xyz")
        risultato = af.ingest_file(f)
        self.assertIn("error", risultato)

    def test_file_inesistente_ritorna_errore(self):
        risultato = af.ingest_file(Path("/percorso/che/non/esiste.pdf"))
        self.assertIn("error", risultato)

    def test_stesso_file_non_viene_duplicato(self):
        """Dedup via SHA256: ingerire due volte lo stesso contenuto deve
        aggiornare il record esistente, non crearne uno secondo."""
        f = self._make_temp_file(content=b"contenuto identico per dedup test")
        primo = af.ingest_file(f, archivio="TEST")
        secondo = af.ingest_file(f, archivio="TEST", note="seconda ingestione")
        self.assertEqual(primo["id"], secondo["id"])
        self.assertEqual(af._count_saved(), 1)

    def test_contenuti_diversi_creano_record_diversi(self):
        f1 = self._make_temp_file(content=b"contenuto A")
        f2 = self._make_temp_file(content=b"contenuto B")
        r1 = af.ingest_file(f1)
        r2 = af.ingest_file(f2)
        self.assertNotEqual(r1["id"], r2["id"])
        self.assertEqual(af._count_saved(), 2)


if __name__ == "__main__":
    import unittest
    unittest.main()
