"""Mock DB for testing without touching the real database."""

import sqlite3
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock


_test_db_path = None


def create_test_db() -> sqlite3.Connection:
    """Create a temp-file SQLite DB with fonti_risorse table for testing.
    Uses a temp file (not :memory:) so multiple get_conn() calls share the same DB."""
    global _test_db_path
    fd, _test_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(_test_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fonti_risorse (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fonte_id          INTEGER,
            url_pagina        TEXT NOT NULL UNIQUE,
            url_documento     TEXT,
            tipo_risorsa      TEXT,
            titolo            TEXT,
            descrizione       TEXT,
            autore            TEXT,
            ente_titolare     TEXT,
            data_pubblicazione TEXT,
            lingua            TEXT,
            licenza           TEXT,
            note_copyright    TEXT,
            hash_contenuto    TEXT,
            first_seen_at     TEXT,
            last_checked_at   TEXT,
            stato             TEXT DEFAULT 'non_verificato'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fonti_risorse_fonte_id ON fonti_risorse(fonte_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fonti_risorse_url ON fonti_risorse(url_pagina)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fonti_risorse_stato ON fonti_risorse(stato)")

    # Also create entita and collegamenti for search_service tests
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entita (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            valore TEXT NOT NULL,
            valore_normalizzato TEXT,
            cognome TEXT,
            nome TEXT,
            data TEXT,
            luogo TEXT,
            contesto TEXT,
            fonte_tabella TEXT,
            fonte_id INTEGER,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collegamenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entita_id INTEGER NOT NULL,
            tabella_origine TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            tipo_collegamento TEXT,
            confidenza REAL DEFAULT 1.0,
            elaborato_il TEXT NOT NULL,
            FOREIGN KEY (entita_id) REFERENCES entita(id)
        )
    """)
    # Create a mock source table with URL
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caduti_albooro (
            id INTEGER PRIMARY KEY,
            nominativo TEXT,
            scheda_url TEXT,
            elaborato_il TEXT
        )
    """)
    conn.commit()
    return conn


def get_test_conn() -> sqlite3.Connection:
    """Return a new connection to the current test DB file."""
    conn = sqlite3.connect(_test_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cleanup_test_db():
    """Release reference to temp DB file. On Windows, file is not deleted (OS cleans temp)."""
    global _test_db_path
    _test_db_path = None


def insert_test_risorsa(conn, **kwargs):
    """Insert a test risorsa with defaults."""
    now = datetime.now().isoformat()
    defaults = {
        "fonte_id": 1,
        "url_pagina": "https://test.example.com/page",
        "url_documento": None,
        "tipo_risorsa": "pagina",
        "titolo": "Test Page",
        "descrizione": "Test description",
        "autore": None,
        "ente_titolare": "Test Ente",
        "data_pubblicazione": None,
        "lingua": "it",
        "licenza": "tutti i diritti riservati",
        "note_copyright": None,
        "hash_contenuto": None,
        "first_seen_at": now,
        "last_checked_at": now,
        "stato": "valido",
    }
    defaults.update(kwargs)
    conn.execute(
        """INSERT INTO fonti_risorse
           (fonte_id, url_pagina, url_documento, tipo_risorsa, titolo, descrizione,
            autore, ente_titolare, data_pubblicazione, lingua, licenza, note_copyright,
            hash_contenuto, first_seen_at, last_checked_at, stato)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        tuple(defaults[k] for k in [
            "fonte_id", "url_pagina", "url_documento", "tipo_risorsa", "titolo",
            "descrizione", "autore", "ente_titolare", "data_pubblicazione",
            "lingua", "licenza", "note_copyright", "hash_contenuto",
            "first_seen_at", "last_checked_at", "stato"
        ])
    )
    conn.commit()
    return conn.execute("SELECT id FROM fonti_risorse WHERE url_pagina = ?",
                        (defaults["url_pagina"],)).fetchone()[0]


def insert_test_entity(conn, tipo="persona", valore="Test Entity", fonte_tabella="caduti_albooro", fonte_id=1):
    """Insert a test entity with a collegamento."""
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO entita (tipo, valore, valore_normalizzato, fonte_tabella, fonte_id, elaborato_il)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tipo, valore, valore.lower().strip(), fonte_tabella, fonte_id, now)
    )
    entita_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO collegamenti (entita_id, tabella_origine, record_id, elaborato_il)
           VALUES (?, ?, ?, ?)""",
        (entita_id, fonte_tabella, fonte_id, now)
    )
    conn.commit()
    return entita_id
