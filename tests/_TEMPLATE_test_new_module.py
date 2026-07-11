"""TEMPLATE — copia questo file in tests/test_<nome_modulo>.py quando
aggiungi un nuovo modulo Python al progetto (uno_scraper.py, un nuovo
provider, un nuovo servizio, ecc.).

Passi per attivarlo:
1. Rinomina questo file in test_<nome_modulo>.py e cancella questo blocco
   di istruzioni.
2. Se il modulo crea proprie tabelle con una funzione
   `_init_table()`/`_init_tables()`, aggiungi la voce corrispondente a
   MODULES_WITH_SCHEMA_INIT in tests/_helpers.py, poi elenca il nome del
   modulo in `schema_modules = (...)` qui sotto.
3. Se il modulo definisce un proprio DB_PATH/STORAGE_DIR indipendente da
   database.py (capita ancora nel progetto, vedi TODO.md #1: e' un debito
   tecnico noto, non introdurne altro se eviti), patchalo esplicitamente in
   setUp()/tearDown() come fa tests/test_archivio_fonti.py con STORAGE_DIR.
4. Se il modulo chiama servizi esterni (HTTP, API AI, scraping) mocka SEMPRE
   la funzione di livello piu' alto che li invoca (vedi
   tests/test_soldier_dashboard.py per @patch("modulo.federated_search") o
   tests/test_biography.py per @patch("biography._call_with_fallback")):
   questa suite non deve MAI fare chiamate di rete reali.
5. Se il modulo ha una dipendenza pesante opzionale (es. fitz/pymupdf) che
   potrebbe mancare in alcuni ambienti, avvolgi l'import in try/except e usa
   @unittest.skipIf come in tests/test_biography.py, invece di lasciare
   fallire l'intero modulo di test con un ImportError poco leggibile.
6. Aggiungi qualche riga a factories.py se il modulo lavora su una tabella
   sorgente che non ha ancora un make_<tabella>() li'.
7. Esegui `python -m unittest tests.test_<nome_modulo> -v` (o
   `pytest tests/test_<nome_modulo>.py -v`) e verifica che passi PRIMA di
   aprire la PR.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
# from factories import make_internato, make_entita  # decommenta se serve

# import nome_modulo  # sostituisci con il modulo reale


class TestEsempioSchema(TempDBTestCase):
    """Esempio: verifica che il modulo esponga una tabella/funzione attesa."""

    schema_modules = ()  # es. ("nome_modulo",) se ha una propria _init_tables()

    def test_placeholder(self):
        self.skipTest("Sostituisci con un test reale per il tuo modulo.")


if __name__ == "__main__":
    import unittest
    unittest.main()
