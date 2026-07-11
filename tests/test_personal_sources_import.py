"""Test per le due pipeline di import di fonti personali/narrative:

  - import_lettere_personali.py  (da import_ocr_lettere/ocr_lettere.db
    verso la tabella lettere_personali, gia' collegata allo star schema)
  - import_personal_sources.py   (da cartelle Desktop verso fonti_narrative,
    piu' ampia: biografie, corrispondenza, foto, memoriali)

Vedi TODO.md #1: le due tabelle/pipeline coesistono ma si sovrappongono
concettualmente (entrambe collegano persone a entita/collegamenti per fonti
"personali"). Nessuna delle due tocca il Desktop reale o chiama OCR/API
esterne in questi test: usiamo file temporanei e skip_ocr/dry_run dove serve.

import_personal_sources.py importa (a livello di modulo, non solo dove serve)
extractor._get_mistral_client, che a sua volta richiede `fitz` (pymupdf).
Se non installato, la classe relativa viene saltata con uno skip esplicito
— esattamente come in test_biography.py.
"""
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase

import database
import import_lettere_personali as ilp

try:
    import import_personal_sources as ips
    _IMPORT_ERROR = None
except ImportError as e:  # richiede pymupdf/fitz, vedi docstring sopra
    ips = None
    _IMPORT_ERROR = str(e)


# ─── import_lettere_personali.py ───────────────────────────────────────────

class TestEstraiCognomeNome(unittest.TestCase):
    def test_cognome_nome_spazio(self):
        self.assertEqual(ilp._estrai_cognome_nome("Rossi Mario"), ("Rossi", "Mario"))

    def test_cognome_nome_virgola(self):
        self.assertEqual(ilp._estrai_cognome_nome("Rossi, Mario"), ("Rossi", "Mario"))

    def test_stringa_vuota(self):
        self.assertEqual(ilp._estrai_cognome_nome(""), ("", ""))


class TestPersoneDaTesto(unittest.TestCase):
    def test_trova_nomi_propri_nel_corpo(self):
        persone = ilp._persone_da_testo(
            "Caro amico, ti scrivo per dirti che Giuseppe Verdi e Anna Bianchi sono arrivati."
        )
        self.assertIn("Giuseppe Verdi", persone)
        self.assertIn("Anna Bianchi", persone)

    def test_filtro_cortesia_esclude_parole_false_positive(self):
        """Dopo il fix, il filtro controlla ogni parola del match contro
        l'insieme di cortesia, non solo la stringa intera: "Caro Amico",
        "Tua Anna" ecc. non devono finire nel grafo entita'."""
        persone = ilp._persone_da_testo("Caro Amico, grazie di tutto. Tua Anna.")
        self.assertNotIn("Caro Amico", persone)
        self.assertNotIn("Tua Anna", persone)
        # "Grazie" da solo non matcha perche' il pattern richiede 2+ parole maiuscole


class TestMigratePipeline(TempDBTestCase):
    """Integrazione completa: ocr_lettere.db di prova -> lettere_personali
    + entita/collegamenti nel DB principale."""

    def _crea_ocr_db_di_prova(self, tmp_path: Path) -> Path:
        ocr_db = tmp_path / "ocr_lettere_test.db"
        conn = sqlite3.connect(str(ocr_db))
        conn.execute("""
            CREATE TABLE lettere (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT, file_path TEXT, mittente TEXT, destinatario TEXT,
                data_lettera TEXT, luogo TEXT, oggetto TEXT, corpo_testo TEXT,
                note TEXT, confidenza REAL, lingua TEXT, raw_response TEXT,
                elaborato_il TEXT
            )
        """)
        conn.execute(
            "INSERT INTO lettere (filename, file_path, mittente, destinatario, "
            "data_lettera, luogo, corpo_testo, elaborato_il) VALUES (?,?,?,?,?,?,?,?)",
            ("lettera1.jpg", str(tmp_path / "lettera1.jpg"), "Gaiaschi Luigi",
             "Gaiaschi Maria", "1944-03-01", "Fronte greco-albanese",
             "Cara mamma, sto bene. Saluta anche Pietro Bianchi.", "2026-01-01"),
        )
        conn.commit()
        conn.close()
        return ocr_db

    def test_migrazione_crea_lettera_e_collega_entita(self):
        tmp_path = Path(self._tmpdir.name)
        ocr_db = self._crea_ocr_db_di_prova(tmp_path)

        original_ocr_db, original_main_db = ilp.OCR_DB, ilp.MAIN_DB
        ilp.OCR_DB = ocr_db
        ilp.MAIN_DB = self.db_path
        try:
            ilp.migrate()
        finally:
            ilp.OCR_DB, ilp.MAIN_DB = original_ocr_db, original_main_db

        conn = self.conn()
        lettere = conn.execute("SELECT * FROM lettere_personali").fetchall()
        self.assertEqual(len(lettere), 1)
        self.assertEqual(lettere[0]["mittente"], "Gaiaschi Luigi")

        entita = conn.execute(
            "SELECT * FROM entita WHERE fonte_tabella='lettere_personali'"
        ).fetchall()
        conn.close()
        # Mittente + destinatario + almeno una persona citata nel corpo testo
        self.assertGreaterEqual(len(entita), 2)

    def test_migrazione_e_idempotente_su_stesso_file(self):
        """Dedup via sha256 del file_path: ri-eseguire migrate() sullo stesso
        file non deve duplicare la riga in lettere_personali."""
        tmp_path = Path(self._tmpdir.name)
        # Serve un file fisico reale perche' migrate() calcola sha256 da file_path.
        lettera_file = tmp_path / "lettera1.jpg"
        lettera_file.write_bytes(b"contenuto finto lettera")

        ocr_db = tmp_path / "ocr_lettere_test.db"
        conn = sqlite3.connect(str(ocr_db))
        conn.execute("""
            CREATE TABLE lettere (
                id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, file_path TEXT,
                mittente TEXT, destinatario TEXT, data_lettera TEXT, luogo TEXT,
                oggetto TEXT, corpo_testo TEXT, note TEXT, confidenza REAL,
                lingua TEXT, raw_response TEXT, elaborato_il TEXT
            )
        """)
        conn.execute(
            "INSERT INTO lettere (filename, file_path, mittente, elaborato_il) VALUES (?,?,?,?)",
            ("lettera1.jpg", str(lettera_file), "Rossi Mario", "2026-01-01"),
        )
        conn.commit()
        conn.close()

        original_ocr_db, original_main_db = ilp.OCR_DB, ilp.MAIN_DB
        ilp.OCR_DB, ilp.MAIN_DB = ocr_db, self.db_path
        try:
            ilp.migrate()
            ilp.migrate()
        finally:
            ilp.OCR_DB, ilp.MAIN_DB = original_ocr_db, original_main_db

        conn = self.conn()
        n = conn.execute("SELECT COUNT(*) FROM lettere_personali").fetchone()[0]
        conn.close()
        self.assertEqual(n, 1, "La seconda migrate() sullo stesso file deve essere no-op (dedup su sha256).")


# ─── import_personal_sources.py ────────────────────────────────────────────

@unittest.skipIf(ips is None, f"import_personal_sources.py non importabile: {_IMPORT_ERROR}")
class TestClassify(unittest.TestCase):
    def test_biografia_da_archivio_storie(self):
        tipo, archivio = ips._classify(Path("/home/x/Desktop/ARCHIVIO STORIE/STORIE IMI/bio.odt"))
        self.assertEqual(tipo, "biografia")

    def test_corrispondenza_da_aro(self):
        tipo, _ = ips._classify(Path("/home/x/Desktop/ARO/lettera.docx"))
        self.assertEqual(tipo, "corrispondenza")

    def test_cartella_sconosciuta_e_altro(self):
        tipo, archivio = ips._classify(Path("/home/x/Desktop/cartella_a_caso/file.pdf"))
        self.assertEqual(tipo, "altro")
        self.assertEqual(archivio, "Desktop")


@unittest.skipIf(ips is None, f"import_personal_sources.py non importabile: {_IMPORT_ERROR}")
class TestDetectPeople(unittest.TestCase):
    def test_trova_persona_nel_testo(self):
        persone = ips._detect_people(
            "Lettera scritta da GAIASCHI Luigi al fratello nel 1944.", "GAIASCHI Luigi.odt"
        )
        cognomi = {p["cognome"] for p in persone}
        self.assertIn("Gaiaschi", cognomi)

    def test_filename_puo_generare_persona_quasi_duplicata(self):
        """Comportamento noto (non bloccante, ma da tenere a mente per la
        qualita' del grafo entita'): il fallback dal filename confronta la
        stringa esatta, non normalizzata, quindi puo' aggiungere una "persona"
        quasi identica a quella gia' trovata nel testo (stessa persona,
        maiuscole/spazi diversi). Se in futuro _detect_people() normalizza
        anche il confronto col filename, questo test va aggiornato per
        aspettarsi una sola voce."""
        persone = ips._detect_people(
            "Lettera scritta da GAIASCHI Luigi al fratello nel 1944.", "GAIASCHI Luigi.odt"
        )
        self.assertGreaterEqual(len(persone), 2)


@unittest.skipIf(ips is None, f"import_personal_sources.py non importabile: {_IMPORT_ERROR}")
class TestExtractOdtText(unittest.TestCase):
    def _crea_odt_minimale(self, testo: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".odt", delete=False)
        tmp.close()
        content_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><office:text><text:p>{testo}</text:p></office:text></office:body>
</office:document-content>"""
        with zipfile.ZipFile(tmp.name, "w") as z:
            z.writestr("content.xml", content_xml)
        return Path(tmp.name)

    def test_estrae_testo_reale_da_odt(self):
        odt = self._crea_odt_minimale("Cara mamma, sto bene. GAIASCHI Luigi.")
        testo = ips._extract_odt_text(odt)
        self.assertIn("GAIASCHI Luigi", testo)


if __name__ == "__main__":
    unittest.main()
