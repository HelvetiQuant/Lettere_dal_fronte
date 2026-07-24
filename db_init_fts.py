"""Migration script: crea FTS5 virtual table, trigger di sincronizzazione,
e popola l'indice dai 42.806 record esistenti in `entita`.

Idempotente: sicuro da eseguire piu' volte. Non cancella dati esistenti.
Usa tokenizer unicode61 con remove_diacritics=2 per gestire accenti italiani.

Su PostgreSQL (Supabase): crea colonna tsvector + GIN index + trigger.
"""
import os
import sqlite3
import time
from pathlib import Path
from database import get_conn, DB_PATH

_USE_POSTGRES = bool(os.environ.get("DATABASE_URL", "").startswith("postgresql"))


def check_fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
        conn.execute("DROP TABLE _fts5_check")
        return True
    except Exception:
        return False


def fts_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='idx_entita_search'"
    ).fetchone()
    return row is not None


def triggers_exist(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_entita_ai'"
    ).fetchone()
    return row is not None


def create_fts_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS idx_entita_search USING fts5(
            entita_id UNINDEXED,
            tipo UNINDEXED,
            valore,
            cognome,
            nome,
            luogo,
            contesto,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    conn.commit()
    print("  Tabella FTS5 idx_entita_search creata")


def create_triggers(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS trg_entita_ai
        AFTER INSERT ON entita
        BEGIN
            INSERT INTO idx_entita_search(entita_id, tipo, valore, cognome, nome, luogo, contesto)
            VALUES (new.id, new.tipo, new.valore, new.cognome, new.nome, new.luogo, new.contesto);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_entita_ad
        AFTER DELETE ON entita
        BEGIN
            DELETE FROM idx_entita_search WHERE entita_id = old.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_entita_au
        AFTER UPDATE ON entita
        BEGIN
            DELETE FROM idx_entita_search WHERE entita_id = old.id;
            INSERT INTO idx_entita_search(entita_id, tipo, valore, cognome, nome, luogo, contesto)
            VALUES (new.id, new.tipo, new.valore, new.cognome, new.nome, new.luogo, new.contesto);
        END;
    """)
    conn.commit()
    print("  Trigger di sincronizzazione creati (AFTER INSERT/UPDATE/DELETE)")


def populate_fts(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM idx_entita_search").fetchone()
    existing = row[0]

    if existing > 0:
        print(f"  FTS5 gia' popolato con {existing:,} record. Skip popolamento.")
        return existing

    row = conn.execute("SELECT COUNT(*) FROM entita").fetchone()
    total = row[0]

    if total == 0:
        print("  Tabella entita vuota. Niente da indicizzare.")
        return 0

    print(f"  Popolamento FTS5 da {total:,} record di entita'...")
    t0 = time.time()

    conn.execute("""
        INSERT INTO idx_entita_search(entita_id, tipo, valore, cognome, nome, luogo, contesto)
        SELECT id, tipo, valore, cognome, nome, luogo, contesto FROM entita
    """)
    conn.commit()

    elapsed = time.time() - t0
    row = conn.execute("SELECT COUNT(*) FROM idx_entita_search").fetchone()
    indexed = row[0]
    print(f"  Indicizzati {indexed:,} record in {elapsed:.1f}s")
    return indexed


def verify_sync(conn: sqlite3.Connection) -> bool:
    row_e = conn.execute("SELECT COUNT(*) FROM entita").fetchone()
    row_f = conn.execute("SELECT COUNT(*) FROM idx_entita_search").fetchone()
    count_e = row_e[0]
    count_f = row_f[0]

    if count_e != count_f:
        print(f"  ATTENZIONE: entita={count_e:,} vs fts5={count_f:,} (discordanza)")
        return False
    print(f"  Verifica OK: entita={count_e:,} = fts5={count_f:,}")
    return True


def run_migration():
    print("=" * 60)
    print("MIGRAZIONE FTS - IR Layer")
    print("=" * 60)

    if _USE_POSTGRES:
        print("Backend: PostgreSQL (tsvector + GIN)")
        conn = get_conn()
        cur = conn.cursor()

        # Add tsvector column
        try:
            cur.execute("ALTER TABLE entita ADD COLUMN IF NOT EXISTS search_vector tsvector")
            conn.commit()
            print("1. Colonna search_vector creata")
        except Exception as e:
            print(f"1. Colonna search_vector: {e}")
            conn.rollback()

        # Create GIN index
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entita_search_vector
                ON entita USING GIN(search_vector)
            """)
            conn.commit()
            print("2. Indice GIN creato")
        except Exception as e:
            print(f"2. Indice GIN: {e}")
            conn.rollback()

        # Create trigger function
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
            conn.commit()
            print("3. Trigger tsvector creato")
        except Exception as e:
            print(f"3. Trigger: {e}")
            conn.rollback()

        # Populate
        print("4. Popolamento tsvector...")
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
            conn.commit()
            count = cur.execute("SELECT COUNT(*) FROM entita WHERE search_vector IS NOT NULL").fetchone()[0]
            print(f"   Indicizzati {count:,} record")
        except Exception as e:
            print(f"   Errore: {e}")
            conn.rollback()

        conn.close()
        print("=" * 60)
        print("MIGRAZIONE COMPLETATA (PostgreSQL)")
        print("=" * 60)
        return True

    # SQLite path (original)
    print("Backend: SQLite (FTS5)")
    conn = get_conn()

    if not check_fts5_available(conn):
        print("ERRORE: FTS5 non disponibile in questo build di SQLite")
        conn.close()
        return False

    print("1. FTS5 disponibile: OK")

    if not fts_table_exists(conn):
        print("2. Creazione tabella FTS5...")
        create_fts_table(conn)
    else:
        print("2. Tabella FTS5 gia' esistente")

    if not triggers_exist(conn):
        print("3. Creazione trigger...")
        create_triggers(conn)
    else:
        print("3. Trigger gia' esistenti")

    print("4. Popolamento indice...")
    populate_fts(conn)

    print("5. Verifica sincronia...")
    verify_sync(conn)

    conn.close()
    print("=" * 60)
    print("MIGRAZIONE COMPLETATA")
    print("=" * 60)
    return True


if __name__ == "__main__":
    run_migration()
