"""Migrazione SQLite → PostgreSQL (Supabase).

Esegue:
1. Estrazione schema da SQLite (69 tabelle)
2. Conversione tipi SQLite → PostgreSQL
3. Creazione schema su PostgreSQL
4. Migrazione dati in batch (7M+ record)
5. Creazione indici e FTS (tsvector invece di FTS5)
6. Verifica conteggi

Uso:
  python migrate_to_pg.py --dry-run          # solo schema, no dati
  python migrate_to_pg.py --schema-only      # solo creazione tabelle
  python migrate_to_pg.py --data-only        # solo dati (schema già esistente)
  python migrate_to_pg.py --full             # schema + dati + indici
  python migrate_to_pg.py --table=internati  # singola tabella

Prerequisiti:
  - DATABASE_URL impostato in .env (es: postgresql://postgres.xxx@aws-0.eu.supabase.com:5432/postgres)
  - psycopg2-binary installato
"""
import os
import sys
import time
import argparse
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv()

import sqlite3
import psycopg2
import psycopg2.extras

DB_PATH = Path(__file__).parent / "imi_internati.db"

# Type mapping SQLite → PostgreSQL
TYPE_MAP = {
    "TEXT": "TEXT",
    "INTEGER": "INTEGER",
    "REAL": "DOUBLE PRECISION",
    "BLOB": "BYTEA",
    "NUMERIC": "NUMERIC",
}

# Tables to skip (SQLite internal)
SKIP_TABLES = {
    "sqlite_sequence",
    "sqlite_stat1",
    "sqlite_stat4",
}

# FTS5 virtual tables → will be replaced with tsvector
FTS_TABLES = {
    "idx_entita_search",
    "idx_entita_search_config",
    "idx_entita_search_content",
    "idx_entita_search_data",
    "idx_entita_search_docsize",
    "idx_entita_search_idx",
}


def get_sqlite_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERRORE: DATABASE_URL non impostato in .env")
        sys.exit(1)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def get_all_tables(sqlite_conn):
    rows = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows if r["name"] not in SKIP_TABLES]


def get_table_schema(sqlite_conn, table):
    """Estrae colonne e tipi di una tabella SQLite."""
    cols = sqlite_conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return [{"name": c["name"], "type": c["type"], "notnull": c["notnull"],
             "dflt": c["dflt_value"], "pk": c["pk"]} for c in cols]


def get_create_sql(sqlite_conn, table):
    """Estrae il CREATE TABLE originale."""
    row = sqlite_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    return row["sql"] if row else ""


def convert_create_table(sqlite_conn, table):
    """Converte CREATE TABLE SQLite → PostgreSQL."""
    cols = get_table_schema(sqlite_conn, table)
    if not cols:
        return None

    lines = []
    for c in cols:
        pg_type = TYPE_MAP.get(c["type"].upper(), "TEXT")
        col_def = f'    "{c["name"]}" {pg_type}'
        if c["pk"] and c["type"].upper() == "INTEGER":
            col_def = f'    "{c["name"]}" SERIAL PRIMARY KEY'
        elif c["pk"]:
            col_def += " PRIMARY KEY"
        if c["notnull"] and not c["pk"]:
            col_def += " NOT NULL"
        if c["dflt"] is not None:
            col_def += f" DEFAULT {c['dflt']}"
        lines.append(col_def)

    return f'CREATE TABLE IF NOT EXISTS "{table}" (\n' + ",\n".join(lines) + "\n);"


def get_row_count(sqlite_conn, table):
    return sqlite_conn.execute(f"SELECT COUNT(*) as c FROM '{table}'").fetchone()["c"]


def migrate_schema(sqlite_conn, pg_conn, tables=None):
    """Crea tutte le tabelle su PostgreSQL."""
    all_tables = tables or get_all_tables(sqlite_conn)
    cur = pg_conn.cursor()

    created = 0
    skipped = 0
    for table in all_tables:
        if table in FTS_TABLES:
            print(f"  [SKIP FTS] {table} — sarà ricreato con tsvector")
            skipped += 1
            continue

        create_sql = convert_create_table(sqlite_conn, table)
        if not create_sql:
            print(f"  [SKIP] {table} — impossibile determinare schema")
            skipped += 1
            continue

        try:
            cur.execute(create_sql)
            created += 1
            count = get_row_count(sqlite_conn, table)
            print(f"  [OK] {table} ({count:,} righe)")
        except Exception as e:
            print(f"  [ERR] {table}: {e}")
            pg_conn.rollback()
            skipped += 1

    pg_conn.commit()
    cur.close()
    print(f"\nSchema: {created} tabelle create, {skipped} saltate")
    return created


def migrate_data(sqlite_conn, pg_conn, tables=None, batch_size=5000):
    """Migra i dati da SQLite a PostgreSQL in batch."""
    all_tables = tables or get_all_tables(sqlite_conn)
    cur = pg_conn.cursor()

    total_migrated = 0
    for table in all_tables:
        if table in FTS_TABLES or table in SKIP_TABLES:
            continue

        count = get_row_count(sqlite_conn, table)
        if count == 0:
            print(f"  [SKIP] {table} — 0 righe")
            continue

        cols = get_table_schema(sqlite_conn, table)
        col_names = [c["name"] for c in cols]
        col_list = ", ".join(f'"{c}"' for c in col_names)
        placeholders = ", ".join(["%s"] * len(col_names))

        # Use INSERT ... ON CONFLICT DO NOTHING for idempotency
        insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        offset = 0
        migrated = 0
        while offset < count:
            rows = sqlite_conn.execute(
                f'SELECT {col_list} FROM "{table}" LIMIT {batch_size} OFFSET {offset}'
            ).fetchall()

            if not rows:
                break

            batch = [tuple(r[c] for c in col_names) for r in rows]
            try:
                psycopg2.extras.execute_batch(cur, insert_sql, batch, page_size=1000)
                pg_conn.commit()
                migrated += len(batch)
                if migrated % (batch_size * 10) == 0 or migrated >= count:
                    pct = (migrated / count) * 100
                    print(f"  {table}: {migrated:,}/{count:,} ({pct:.0f}%)")
            except Exception as e:
                print(f"  [ERR] {table} offset {offset}: {e}")
                pg_conn.rollback()
                # Try row by row for this batch
                for row in batch:
                    try:
                        cur.execute(insert_sql, row)
                        pg_conn.commit()
                        migrated += 1
                    except Exception:
                        pg_conn.rollback()

            offset += batch_size

        total_migrated += migrated
        print(f"  [DONE] {table}: {migrated:,} righe migrate")

    cur.close()
    print(f"\nTotale: {total_migrated:,} righe migrate")
    return total_migrated


def create_fts_pg(pg_conn):
    """Crea indice full-text PostgreSQL con tsvector (sostituto di FTS5)."""
    cur = pg_conn.cursor()

    # Add tsvector column to entita
    try:
        cur.execute("ALTER TABLE entita ADD COLUMN IF NOT EXISTS search_vector tsvector")
    except Exception:
        pg_conn.rollback()

    # Create GIN index
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_entita_search_vector
            ON entita USING GIN(search_vector)
        """)
    except Exception:
        pg_conn.rollback()

    # Populate tsvector
    try:
        cur.execute("""
            UPDATE entita
            SET search_vector = to_tsvector('simple',
                coalesce(valore, '') || ' ' ||
                coalesce(cognome, '') || ' ' ||
                coalesce(nome, '') || ' ' ||
                coalesce(luogo, '') || ' ' ||
                coalesce(contesto, '')
            )
        """)
        print(f"  [OK] tsvector popolato su entita")
    except Exception as e:
        print(f"  [ERR] tsvector: {e}")
        pg_conn.rollback()

    # Create trigger to auto-update tsvector
    try:
        cur.execute("""
            CREATE OR REPLACE FUNCTION entita_search_vector_update() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector := to_tsvector('simple',
                    coalesce(NEW.valore, '') || ' ' ||
                    coalesce(NEW.cognome, '') || ' ' ||
                    coalesce(NEW.nome, '') || ' ' ||
                    coalesce(NEW.luogo, '') || ' ' ||
                    coalesce(NEW.contesto, '')
                );
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        cur.execute("""
            DROP TRIGGER IF EXISTS trg_entita_search_vector ON entita;
            CREATE TRIGGER trg_entita_search_vector
            BEFORE INSERT OR UPDATE ON entita
            FOR EACH ROW EXECUTE FUNCTION entita_search_vector_update()
        """)
        print(f"  [OK] trigger tsvector creato")
    except Exception as e:
        print(f"  [ERR] trigger: {e}")
        pg_conn.rollback()

    pg_conn.commit()
    cur.close()


def create_indexes(pg_conn, sqlite_conn):
    """Ricrea gli indici non-PK da SQLite su PostgreSQL."""
    cur = pg_conn.cursor()
    sqlite_cur = sqlite_conn.cursor()

    # Get all indexes from SQLite
    indexes = sqlite_cur.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    ).fetchall()

    created = 0
    for idx in indexes:
        idx_name = idx["name"]
        tbl = idx["tbl_name"]
        sql = idx["sql"]

        # Convert SQLite CREATE INDEX to PostgreSQL
        # Replace CREATE INDEX IF NOT EXISTS x ON table → same syntax works in PG
        # But need to handle column expressions
        try:
            # Simple conversion: SQLite syntax is mostly compatible
            pg_sql = sql.replace(" IF NOT EXISTS ", " IF NOT EXISTS ")
            cur.execute(pg_sql)
            created += 1
            print(f"  [OK] {idx_name} on {tbl}")
        except Exception as e:
            # Try manual creation
            print(f"  [SKIP] {idx_name} on {tbl}: {e}")
            pg_conn.rollback()

    pg_conn.commit()
    cur.close()
    sqlite_cur.close()
    print(f"\nIndici: {created} creati")


def verify_counts(sqlite_conn, pg_conn):
    """Verifica che i conteggi corrispondano."""
    tables = get_all_tables(sqlite_conn)
    cur = pg_conn.cursor()

    mismatches = 0
    for table in tables:
        if table in FTS_TABLES or table in SKIP_TABLES:
            continue

        sqlite_count = get_row_count(sqlite_conn, table)
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            pg_count = cur.fetchone()[0]
        except Exception:
            pg_count = -1

        status = "OK" if sqlite_count == pg_count else "MISMATCH"
        if status == "MISMATCH":
            mismatches += 1
        print(f"  {table}: SQLite={sqlite_count:,} PG={pg_count:,} [{status}]")

    cur.close()
    print(f"\nVerifica: {len(tables) - mismatches}/{len(tables)} tabelle corrette")
    return mismatches == 0


def main():
    parser = argparse.ArgumentParser(description="Migrazione SQLite → PostgreSQL Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Solo schema, no dati")
    parser.add_argument("--schema-only", action="store_true", help="Solo creazione tabelle")
    parser.add_argument("--data-only", action="store_true", help="Solo dati (schema esistente)")
    parser.add_argument("--full", action="store_true", help="Schema + dati + indici + FTS")
    parser.add_argument("--table", type=str, help="Singola tabella")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size per insert")
    args = parser.parse_args()

    if not any([args.dry_run, args.schema_only, args.data_only, args.full, args.table]):
        parser.print_help()
        return

    print("=" * 70)
    print("MIGRAZIONE SQLite → PostgreSQL (Supabase)")
    print("=" * 70)

    sqlite_conn = get_sqlite_conn()
    pg_conn = get_pg_conn()

    tables = [args.table] if args.table else None

    if args.dry_run or args.schema_only or args.full:
        print("\n1. CREAZIONE SCHEMA")
        migrate_schema(sqlite_conn, pg_conn, tables)

    if args.data_only or args.full or args.table:
        print("\n2. MIGRAZIONE DATI")
        migrate_data(sqlite_conn, pg_conn, tables, args.batch_size)

    if args.full:
        print("\n3. CREAZIONE INDICI")
        create_indexes(pg_conn, sqlite_conn)

        print("\n4. CREAZIONE FTS (tsvector)")
        create_fts_pg(pg_conn)

        print("\n5. VERIFICA CONTEGGI")
        verify_counts(sqlite_conn, pg_conn)

    sqlite_conn.close()
    pg_conn.close()
    print("\nMigrazione completata.")


if __name__ == "__main__":
    main()
