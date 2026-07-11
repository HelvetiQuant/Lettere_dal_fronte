"""Base condivisa per tutti i test del progetto VOCI DAL FRONTE / IMI Extractor.

FILOSOFIA
---------
Ogni test gira su un database SQLite temporaneo e isolato, MAI su
`imi_internati.db` reale (>1 GB, in scrittura continua da scraper/linker,
mai incluso nel repo). Questo e' un cambio deliberato rispetto a
`test_search.py` (che gira sul DB reale con record prefissati `ZZZ_TEST_`
puliti in `tearDown`): la nuova suite deve poter girare ovunque (CI, laptop
di un nuovo contributore, sandbox) senza il DB di produzione, senza le
chiavi API reali e senza rischiare di scrivere nei dati veri.

COME ESTENDERE QUESTA SUITE QUANDO SI AGGIUNGE UN MODULO
---------------------------------------------------------
1. Se il nuovo modulo definisce tabelle proprie con una funzione
   `_init_table()` / `_init_tables()` (come memory_router, source_locator,
   research_to_index, archivio_fonti oggi), AGGIUNGILA alla lista
   MODULES_WITH_SCHEMA_INIT qui sotto: la userai automaticamente in ogni
   TempDBTestCase che dichiara quel modulo in `schema_modules`.
2. Se il nuovo modulo ridefinisce un proprio `DB_PATH` invece di usare
   `database.get_conn()` (debito tecnico noto: succede oggi in `credits.py`,
   vedi TODO.md #1 "Fix tecnici"), AGGIUNGILO a MODULES_WITH_OWN_DB_PATH,
   altrimenti i suoi test toccherebbero per errore il DB reale.
3. Copia `tests/_TEMPLATE_test_new_module.py` in `tests/test_<modulo>.py`
   e segui la struttura li' descritta.

Nessuno di questi due elenchi e' "magico": sono liste esplicite da
aggiornare a mano apposta, cosi' che dimenticarsi di un modulo nuovo dia un
errore visibile nei test (tabella mancante / DB sbagliato) invece di un
comportamento silenzioso.
"""
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import database  # noqa: E402  (import dopo aver sistemato sys.path)

# ─── Registro moduli con schema proprio ────────────────────────────────────
# Aggiornare quando si aggiunge un modulo con una propria _init_table(s)().
MODULES_WITH_SCHEMA_INIT = {
    "memory_router": "_init_tables",
    "source_locator": "_init_tables",
    "research_to_index": "_init_tables",
    "archivio_fonti": "_init_table",
}

# ─── Registro moduli con DB_PATH proprio (non da database.py) ─────────────
# Debito tecnico tracciato in TODO.md #1. Aggiornare se se ne trovano altri.
MODULES_WITH_OWN_DB_PATH = [
    "credits",
]

# DDL minime per tabelle "proposte ma non ancora automatizzate" nello schema
# principale (vedi schema_proposal_fonti_narrative.sql e
# import_lettere_personali.py). Tenerle qui, vicino ai test che le usano,
# evita di dipendere da script di migrazione con effetti collaterali (letture
# dal Desktop reale, chiamate OCR) durante i test.
EXTRA_SCHEMA_DDL = {
    "fonti_narrative": """
        CREATE TABLE IF NOT EXISTS fonti_narrative (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256 TEXT UNIQUE NOT NULL,
            nome_file TEXT NOT NULL,
            path_locale TEXT NOT NULL,
            formato TEXT NOT NULL,
            tipo_fonte TEXT NOT NULL,
            archivio TEXT,
            fondo TEXT,
            unita_principale TEXT,
            teatro TEXT,
            data_documento TEXT,
            data_inizio TEXT,
            data_fine TEXT,
            autore TEXT,
            soggetti_json TEXT,
            persone_possibili TEXT,
            titolo TEXT,
            descrizione TEXT,
            testo_ocr TEXT,
            ocr_status TEXT DEFAULT 'pending',
            access_type TEXT DEFAULT 'locale',
            fetch_status TEXT DEFAULT 'scaricato',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "lettere_personali": """
        CREATE TABLE IF NOT EXISTS lettere_personali (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            file_path TEXT,
            mittente TEXT,
            destinatario TEXT,
            data_lettera TEXT,
            luogo TEXT,
            oggetto TEXT,
            corpo_testo TEXT,
            note TEXT,
            confidenza REAL,
            lingua TEXT,
            raw_response TEXT,
            sha256 TEXT UNIQUE,
            sorgente_db TEXT,
            sorgente_id INTEGER,
            elaborato_il TEXT
        )
    """,
}


class TempDBTestCase(unittest.TestCase):
    """Classe base: crea un DB temporaneo vuoto per ogni test e reindirizza
    tutti i moduli noti verso di esso.

    Sottoclassi:
      schema_modules = ("memory_router", "source_locator", ...)
          quali moduli con _init_table(s)() richiamare oltre a database.init_db()
      extra_tables = ("fonti_narrative", "lettere_personali")
          quali DDL extra applicare (vedi EXTRA_SCHEMA_DDL)
    """

    schema_modules: tuple = ()
    extra_tables: tuple = ()

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test_imi.db"

        self._patched_modules = []
        self._set_db_path(database, self.db_path)
        database.init_db()

        for modname in MODULES_WITH_OWN_DB_PATH:
            mod = importlib.import_module(modname)
            self._set_db_path(mod, self.db_path)

        for modname in self.schema_modules:
            if modname not in MODULES_WITH_SCHEMA_INIT:
                raise AssertionError(
                    f"Modulo '{modname}' non registrato in MODULES_WITH_SCHEMA_INIT "
                    "(tests/_helpers.py). Aggiungilo li' con il nome della sua "
                    "funzione _init_table()/_init_tables()."
                )
            mod = importlib.import_module(modname)
            getattr(mod, MODULES_WITH_SCHEMA_INIT[modname])()

        if self.extra_tables:
            conn = database.get_conn()
            for table in self.extra_tables:
                conn.executescript(EXTRA_SCHEMA_DDL[table])
            conn.commit()
            conn.close()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _set_db_path(self, module, path):
        module.DB_PATH = path
        self._patched_modules.append(module)

    def conn(self):
        """Nuova connessione al DB di test (chiamare .close() a fine uso,
        oppure usare come context manager tramite `with self.conn() as c:`
        se lo stile del modulo lo consente)."""
        return database.get_conn()
