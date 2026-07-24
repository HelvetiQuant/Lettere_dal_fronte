"""Database adapter layer — supporta SQLite e PostgreSQL (Supabase) trasparentemente.

Rileva automaticamente il backend da variabili d'ambiente:
- DATABASE_URL=postgresql://... → PostgreSQL (psycopg2)
- Assenza di DATABASE_URL → SQLite (default, retrocompatibile)

Mantiene la stessa interfaccia get_conn() ma restituisce una connessione
che funziona con entrambi i backend, con row factory compatibile.
"""
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional, Any

# Rileva backend
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))

# SQLite path (fallback)
DB_PATH = Path(__file__).parent / "imi_internati.db"


class PostgresRow(dict):
    """Dict-like row che simula sqlite3.Row (accesso per chiave e per indice)."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(super().values())[key]
        return super().__getitem__(key)


class PostgresConnection:
    """Wrapper psycopg2 che simula sqlite3.Connection con row_factory."""
    def __init__(self, pg_conn):
        self._conn = pg_conn
        self.row_factory = PostgresRow

    def execute(self, sql: str, params: tuple = ()):
        # Converti ? placeholder in %s per psycopg2
        pg_sql = _convert_sqlite_to_pg(sql)
        import psycopg2.extras
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_sql, params if isinstance(params, (tuple, list)) else (params,))
        return cur

    def executescript(self, sql: str):
        # PostgreSQL: esegui come batch
        cur = self._conn.cursor()
        # Converti AUTOINCREMENT → SERIAL per PostgreSQL
        pg_sql = re.sub(
            r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
            'SERIAL PRIMARY KEY',
            sql, flags=re.IGNORECASE
        )
        statements = _split_sql_statements(pg_sql)
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    @property
    def cursor(self):
        return self._conn.cursor()

    def last_insert_rowid(self):
        cur = self._conn.cursor()
        cur.execute("SELECT lastval()")
        return cur.fetchone()[0]


def _convert_sqlite_to_pg(sql: str) -> str:
    """Converte sintassi SQLite in PostgreSQL."""
    # ? → %s (psycopg2)
    # Ma non sostituire ? dentro stringhe
    result = []
    in_string = False
    quote_char = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            if ch == quote_char:
                in_string = False
            result.append(ch)
        elif ch in ("'", '"'):
            in_string = True
            quote_char = ch
            result.append(ch)
        elif ch == '?':
            result.append('%s')
        else:
            result.append(ch)
        i += 1
    pg_sql = ''.join(result)

    # AUTOINCREMENT → GENERATED (gestito a livello schema)
    # INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL
    pg_sql = re.sub(
        r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
        'SERIAL PRIMARY KEY',
        pg_sql, flags=re.IGNORECASE
    )

    # PRAGMA statements: skip in PostgreSQL
    if pg_sql.strip().upper().startswith('PRAGMA'):
        return "SELECT 1"  # no-op

    # LIKE è case-insensitive in SQLite, case-sensitive in PostgreSQL
    # Per compatibilità, usiamo ILIKE dove possibile (ma solo per query semplici)
    # Non convertiamo automaticamente: gestito nelle query specifiche

    return pg_sql


def _split_sql_statements(sql: str) -> list:
    """Split SQL su ; rispettando stringhe e blocchi BEGIN/END."""
    statements = []
    current = []
    in_string = False
    quote_char = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            if ch == quote_char:
                in_string = False
            current.append(ch)
        elif ch in ("'", '"'):
            in_string = True
            quote_char = ch
            current.append(ch)
        elif ch == ';':
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1
    last = ''.join(current).strip()
    if last:
        statements.append(last)
    return statements


def get_conn():
    """Factory che restituisce una connessione SQLite o PostgreSQL."""
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
        pg_conn = psycopg2.connect(DATABASE_URL)
        pg_conn.autocommit = False
        # Set row factory to RealDictCursor for dict-like access
        cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.close()
        return PostgresConnection(pg_conn)
    else:
        conn = sqlite3.connect(str(DB_PATH), timeout=60)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-65536")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")
        return conn


def get_backend() -> str:
    """Ritorna 'postgresql' o 'sqlite'."""
    return "postgresql" if USE_POSTGRES else "sqlite"


def is_postgres() -> bool:
    return USE_POSTGRES


def is_sqlite() -> bool:
    return not USE_POSTGRES
