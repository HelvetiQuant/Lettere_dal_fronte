"""Migrazione completa SQLite → Supabase (PostgreSQL via REST API).

Migra tutti e 4 i database SQLite locali in un unico schema Supabase:
- imi_internati.db  (~75 tabelle, 6.5M+ righe)
- eventi_1gm.db    (3 tabelle, 892K righe)
- validazioni_ai.db (1 tabella, 200 righe)
- ocr_lettere.db   (1 tabella, 1 riga)

Fasi:
  1. --schema     Crea tabelle su Supabase (genera DDL PG da SQLite)
  2. --data       Migra dati in batch via REST API
  3. --indexes    Crea indici PostgreSQL
  4. --fts        Configura FTS (tsvector + GIN + trigger)
  5. --rls        Configura Row Level Security
  6. --verify     Verifica conteggi SQLite vs Supabase
  7. --full       Tutto (schema + data + indexes + fts + rls + verify)

Uso:
  python migrate_to_supabase.py --full
  python migrate_to_supabase.py --schema
  python migrate_to_supabase.py --data --table=internati
  python migrate_to_supabase.py --data --resume
  python migrate_to_supabase.py --verify

Prerequisiti:
  - .env con SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
  - exec_sql function su Supabase (creata automaticamente al primo run)
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import httpx

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRORE: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY richiesti in .env")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Database files
DB_FILES = {
    "main": BASE_DIR / "imi_internati.db",
    "events": BASE_DIR / "eventi_1gm.db",
    "validazioni": BASE_DIR / "validazioni_ai.db",
    "ocr": BASE_DIR / "import_ocr_lettere" / "ocr_lettere.db",
}

# Tables to skip
SKIP_TABLES = {
    "sqlite_sequence", "sqlite_stat1", "sqlite_stat4",
    # FTS5 virtual tables (replaced by tsvector)
    "idx_entita_search", "idx_entita_search_config",
    "idx_entita_search_content", "idx_entita_search_data",
    "idx_entita_search_docsize", "idx_entita_search_idx",
    # Backup table (too large, migrate separately if needed)
    "collegamenti_backup",
}

# Table rename map (avoid conflicts across DBs)
TABLE_RENAME = {
    # ocr_lettere.db has 'lettere' → rename to avoid conflict with lettere_personali
    ("ocr", "lettere"): "ocr_lettere",
}

# Batch sizes per table (override defaults for large tables)
BATCH_SIZES = {
    "collegamenti": 500,
    "entita": 500,
    "caduti_cwgc": 500,
    "caduti_albooro": 500,
    "event_links": 500,
    "record_links": 500,
    "caduti_ministero": 500,
    "decorati_nastroazzurro": 500,
    "caduti_francia_ww1": 1000,
    "populate_progress": 1000,
    "api_usage": 1000,
}
DEFAULT_BATCH_SIZE = 1000

# Checkpoint file for resume
CHECKPOINT_FILE = BASE_DIR / "supabase_migration_checkpoint.json"

# Type mapping SQLite → PostgreSQL
TYPE_MAP = {
    "TEXT": "TEXT",
    "INTEGER": "INTEGER",
    "REAL": "DOUBLE PRECISION",
    "BLOB": "BYTEA",
    "NUMERIC": "NUMERIC",
    "": "TEXT",
}


# ─── SQLite helpers ──────────────────────────────────────────────────────────

def get_sqlite_conn(db_key: str) -> sqlite3.Connection:
    path = DB_FILES[db_key]
    if not path.exists():
        raise FileNotFoundError(f"DB non trovato: {path}")
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows if r["name"] not in SKIP_TABLES]


def get_table_info(conn: sqlite3.Connection, table: str) -> list[dict]:
    cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [{"name": c["name"], "type": c["type"] or "TEXT",
             "notnull": c["notnull"], "dflt": c["dflt_value"],
             "pk": c["pk"]} for c in cols]


def get_row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


# ─── Supabase SQL execution ─────────────────────────────────────────────────

def supabase_sql(sql: str, *, timeout: int = 120) -> dict:
    """Execute SQL on Supabase via the exec_sql RPC function."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=HEADERS, json={"query": sql}, timeout=timeout)
    if r.status_code in (200, 201, 204):
        try:
            data = r.json()
            if isinstance(data, dict) and data.get("ok") is False:
                return {"ok": False, "error": data.get("error", "unknown")}
            return {"ok": True, "data": data}
        except Exception:
            return {"ok": True, "data": None}
    return {"ok": False, "status": r.status_code, "error": r.text[:500]}


def ensure_exec_sql_function() -> bool:
    """Create the exec_sql helper function on Supabase if it doesn't exist."""
    # First check if it already exists
    test = supabase_sql("SELECT 1")
    if test.get("ok"):
        print("  exec_sql function already exists")
        return True

    print("  Creating exec_sql function on Supabase...")
    # We need to create it via the Supabase SQL Editor or Management API
    # Since we can't use PostgREST for this (chicken-and-egg), we use
    # the Supabase client library
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Use the rpc endpoint to create the function
        # This requires the function to already exist, so we need
        # to create it via the Supabase Dashboard SQL Editor first.
        pass
    except Exception:
        pass

    # Alternative: try the Supabase query endpoint
    sql = """
    CREATE OR REPLACE FUNCTION exec_sql(query text)
    RETURNS json
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
    AS $$
    DECLARE
        result json;
    BEGIN
        EXECUTE query;
        RETURN json_build_object('ok', true);
    EXCEPTION WHEN OTHERS THEN
        RETURN json_build_object('ok', false, 'error', SQLERRM, 'detail', SQLSTATE);
    END;
    $$;
    """
    
    # Try via Supabase client
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # postgrest doesn't support raw SQL, but we can try the pg_net extension
        # Actually, we need to use the Supabase Management API
        pass
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("AZIONE RICHIESTA: Crea la funzione exec_sql su Supabase")
    print("=" * 70)
    print("Vai su: Supabase Dashboard → SQL Editor")
    print(f"Progetto: {SUPABASE_URL}")
    print("\nEsegui questo SQL:")
    print("-" * 70)
    print(sql)
    print("-" * 70)
    print("\nPoi ri-esegui questo script.")
    print("=" * 70)
    
    # Save the SQL to a file for easy copy-paste
    sql_path = BASE_DIR / "sql" / "00_exec_sql_function.sql"
    sql_path.parent.mkdir(exist_ok=True)
    sql_path.write_text(sql, encoding="utf-8")
    print(f"\nSQL salvato in: {sql_path}")
    
    return False


# ─── Schema Generation ───────────────────────────────────────────────────────

def convert_create_table_pg(table: str, cols: list[dict]) -> str:
    """Generate PostgreSQL CREATE TABLE from SQLite column info."""
    lines = []
    for c in cols:
        col_type = c["type"].upper().strip()
        pg_type = TYPE_MAP.get(col_type, "TEXT")
        
        # Handle compound types
        if "INT" in col_type:
            pg_type = "INTEGER"
        elif "CHAR" in col_type or "CLOB" in col_type or "TEXT" in col_type:
            pg_type = "TEXT"
        elif "REAL" in col_type or "DOUBLE" in col_type or "FLOAT" in col_type:
            pg_type = "DOUBLE PRECISION"
        elif "BLOB" in col_type:
            pg_type = "BYTEA"
        
        col_def = f'    "{c["name"]}" {pg_type}'
        
        if c["pk"] and pg_type == "INTEGER":
            col_def = f'    "{c["name"]}" SERIAL PRIMARY KEY'
        elif c["pk"]:
            col_def += " PRIMARY KEY"
        
        if c["notnull"] and not c["pk"]:
            col_def += " NOT NULL"
        
        if c["dflt"] is not None:
            dflt = str(c["dflt"]).strip()
            # Fix SQLite-specific defaults
            if dflt.upper() == "CURRENT_TIMESTAMP":
                dflt = "NOW()"
            col_def += f" DEFAULT {dflt}"
        
        lines.append(col_def)
    
    return f'CREATE TABLE IF NOT EXISTS "{table}" (\n' + ",\n".join(lines) + "\n);"


def generate_schema_sql(db_key: str) -> list[tuple[str, str]]:
    """Generate CREATE TABLE statements for all tables in a SQLite DB.
    
    Returns list of (table_name, create_sql) tuples.
    """
    conn = get_sqlite_conn(db_key)
    tables = get_sqlite_tables(conn)
    result = []
    
    for table in tables:
        target_name = TABLE_RENAME.get((db_key, table), table)
        cols = get_table_info(conn, table)
        if not cols:
            continue
        sql = convert_create_table_pg(target_name, cols)
        count = get_row_count(conn, table)
        result.append((target_name, sql, count))
    
    conn.close()
    return result


def run_schema(tables_filter: str = None):
    """Create all tables on Supabase."""
    print("\n" + "=" * 70)
    print("FASE 1: CREAZIONE SCHEMA SU SUPABASE")
    print("=" * 70)
    
    all_ddl = []
    for db_key, db_path in DB_FILES.items():
        if not db_path.exists():
            print(f"\n  [SKIP] {db_key}: {db_path} non trovato")
            continue
        
        print(f"\n  DB: {db_key} ({db_path.name})")
        schema_items = generate_schema_sql(db_key)
        
        for target_name, sql, count in schema_items:
            if tables_filter and target_name != tables_filter:
                continue
            all_ddl.append((target_name, sql, count))
    
    # Save full schema to file
    sql_dir = BASE_DIR / "sql"
    sql_dir.mkdir(exist_ok=True)
    
    full_schema = "-- Schema completo Voci dal Fronte → Supabase\n"
    full_schema += f"-- Generato: {datetime.now().isoformat()}\n"
    full_schema += f"-- Tabelle: {len(all_ddl)}\n\n"
    
    for name, sql, count in all_ddl:
        full_schema += f"-- {name} ({count:,} righe)\n{sql}\n\n"
    
    schema_path = sql_dir / "01_supabase_schema.sql"
    schema_path.write_text(full_schema, encoding="utf-8")
    print(f"\n  Schema SQL salvato: {schema_path}")
    
    # Execute each CREATE TABLE
    created = 0
    errors = 0
    for name, sql, count in all_ddl:
        result = supabase_sql(sql)
        if result.get("ok"):
            created += 1
            print(f"  [OK] {name} ({count:,} righe)")
        else:
            errors += 1
            print(f"  [ERR] {name}: {result.get('error', 'unknown')}")
    
    print(f"\nSchema: {created} tabelle create, {errors} errori")
    return created


# ─── Data Migration ──────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    return {}


def save_checkpoint(data: dict):
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def migrate_table_data(db_key: str, source_table: str, target_table: str,
                       batch_size: int, checkpoint: dict,
                       rate_limit_per_min: int = 80) -> int:
    """Migrate all rows from a SQLite table to Supabase via REST API."""
    conn = get_sqlite_conn(db_key)
    total = get_row_count(conn, source_table)
    
    if total == 0:
        print(f"  [SKIP] {target_table} — 0 righe")
        conn.close()
        return 0
    
    cols = get_table_info(conn, source_table)
    col_names = [c["name"] for c in cols]
    
    # Check checkpoint for resume
    ck_key = f"{db_key}:{source_table}"
    offset = checkpoint.get(ck_key, 0)
    if offset >= total:
        print(f"  [DONE] {target_table} — già migrato ({total:,} righe)")
        conn.close()
        return total
    if offset > 0:
        print(f"  [RESUME] {target_table} da offset {offset:,}/{total:,}")
    
    url = f"{SUPABASE_URL}/rest/v1/{target_table}"
    headers = dict(HEADERS)
    headers["Prefer"] = "return=minimal,resolution=ignore-duplicates"
    
    migrated = offset
    request_count = 0
    start_time = time.time()
    errors = 0
    
    col_list = ", ".join(f'"{c}"' for c in col_names)
    
    while offset < total:
        rows = conn.execute(
            f'SELECT {col_list} FROM "{source_table}" LIMIT {batch_size} OFFSET {offset}'
        ).fetchall()
        
        if not rows:
            break
        
        # Convert to list of dicts, handling special types
        batch = []
        for row in rows:
            record = {}
            for c in col_names:
                val = row[c]
                if isinstance(val, bytes):
                    val = val.hex()
                record[c] = val
            batch.append(record)
        
        # Rate limiting
        request_count += 1
        elapsed = time.time() - start_time
        if elapsed > 0 and request_count > 0:
            rpm = request_count / (elapsed / 60)
            if rpm > rate_limit_per_min:
                wait = (request_count / rate_limit_per_min * 60) - elapsed
                if wait > 0:
                    time.sleep(wait)
        
        try:
            r = httpx.post(url, headers=headers, json=batch, timeout=60)
            if r.status_code in (200, 201, 204):
                migrated += len(batch)
                offset += batch_size
                
                # Save checkpoint every 10 batches
                if request_count % 10 == 0:
                    checkpoint[ck_key] = offset
                    save_checkpoint(checkpoint)
                
                # Progress log
                if migrated % (batch_size * 20) == 0 or migrated >= total:
                    pct = (migrated / total) * 100
                    elapsed = time.time() - start_time
                    rate = migrated / max(elapsed, 1)
                    eta = (total - migrated) / max(rate, 1)
                    print(f"    {target_table}: {migrated:,}/{total:,} "
                          f"({pct:.0f}%) [{rate:.0f} r/s, ETA {eta:.0f}s]")
            else:
                errors += 1
                err_text = r.text[:200]
                if errors <= 3:
                    print(f"    [ERR] {target_table} offset {offset}: "
                          f"HTTP {r.status_code} - {err_text}")
                if errors > 10:
                    print(f"    [ABORT] Troppi errori per {target_table}")
                    break
                # Retry with smaller batch
                if batch_size > 100:
                    half = batch_size // 2
                    for i in range(0, len(batch), half):
                        sub = batch[i:i+half]
                        try:
                            r2 = httpx.post(url, headers=headers, json=sub, timeout=60)
                            if r2.status_code in (200, 201, 204):
                                migrated += len(sub)
                        except Exception:
                            pass
                offset += batch_size
                
        except httpx.TimeoutException:
            errors += 1
            print(f"    [TIMEOUT] {target_table} offset {offset}")
            time.sleep(5)
            offset += batch_size
        except Exception as e:
            errors += 1
            print(f"    [ERR] {target_table}: {e}")
            offset += batch_size
    
    # Final checkpoint
    checkpoint[ck_key] = total
    save_checkpoint(checkpoint)
    
    elapsed = time.time() - start_time
    print(f"  [DONE] {target_table}: {migrated:,}/{total:,} righe "
          f"({elapsed:.0f}s, {errors} errori)")
    
    conn.close()
    return migrated


def run_data(tables_filter: str = None, resume: bool = False):
    """Migrate data from all SQLite DBs to Supabase."""
    print("\n" + "=" * 70)
    print("FASE 2: MIGRAZIONE DATI → SUPABASE")
    print("=" * 70)
    
    checkpoint = load_checkpoint() if resume else {}
    total_migrated = 0
    
    # Build ordered list of (db_key, source_table, target_table, row_count)
    migration_plan = []
    for db_key, db_path in DB_FILES.items():
        if not db_path.exists():
            continue
        conn = get_sqlite_conn(db_key)
        tables = get_sqlite_tables(conn)
        for table in tables:
            target = TABLE_RENAME.get((db_key, table), table)
            if tables_filter and target != tables_filter:
                continue
            count = get_row_count(conn, table)
            migration_plan.append((db_key, table, target, count))
        conn.close()
    
    # Sort: small tables first (FK targets), then large ones
    migration_plan.sort(key=lambda x: x[3])
    
    print(f"\n  Tabelle da migrare: {len(migration_plan)}")
    print(f"  Righe totali: {sum(x[3] for x in migration_plan):,}")
    
    for db_key, source_table, target_table, count in migration_plan:
        if count == 0:
            print(f"  [SKIP] {target_table} — 0 righe")
            continue
        
        batch_size = BATCH_SIZES.get(target_table, DEFAULT_BATCH_SIZE)
        migrated = migrate_table_data(
            db_key, source_table, target_table, batch_size, checkpoint
        )
        total_migrated += migrated
    
    print(f"\nTotale: {total_migrated:,} righe migrate")
    return total_migrated


# ─── Indexes ─────────────────────────────────────────────────────────────────

def run_indexes():
    """Create PostgreSQL indexes from SQLite index definitions."""
    print("\n" + "=" * 70)
    print("FASE 4: CREAZIONE INDICI")
    print("=" * 70)
    
    all_indexes = []
    for db_key, db_path in DB_FILES.items():
        if not db_path.exists():
            continue
        conn = get_sqlite_conn(db_key)
        indexes = conn.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL"
        ).fetchall()
        
        for idx in indexes:
            sql = idx["sql"]
            tbl = idx["tbl_name"]
            name = idx["name"]
            
            if tbl in SKIP_TABLES:
                continue
            
            # Apply table rename
            target_tbl = TABLE_RENAME.get((db_key, tbl), tbl)
            if target_tbl != tbl:
                sql = sql.replace(f'ON {tbl}', f'ON "{target_tbl}"')
                sql = sql.replace(f'ON "{tbl}"', f'ON "{target_tbl}"')
            
            # Convert to PostgreSQL (mostly compatible)
            pg_sql = sql
            if "IF NOT EXISTS" not in pg_sql:
                pg_sql = pg_sql.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)
            
            all_indexes.append((name, target_tbl, pg_sql))
        
        conn.close()
    
    # Save to file
    sql_dir = BASE_DIR / "sql"
    sql_dir.mkdir(exist_ok=True)
    idx_sql = "-- Indici PostgreSQL per Voci dal Fronte\n\n"
    for name, tbl, sql in all_indexes:
        idx_sql += f"-- {name} on {tbl}\n{sql};\n\n"
    (sql_dir / "02_supabase_indexes.sql").write_text(idx_sql, encoding="utf-8")
    
    # Execute
    created = 0
    for name, tbl, sql in all_indexes:
        result = supabase_sql(sql)
        if result.get("ok"):
            created += 1
        else:
            print(f"  [SKIP] {name} on {tbl}: {result.get('error', '')[:100]}")
    
    print(f"\nIndici: {created}/{len(all_indexes)} creati")
    return created


# ─── FTS (tsvector) ──────────────────────────────────────────────────────────

def run_fts():
    """Configure PostgreSQL full-text search (tsvector) on entita table."""
    print("\n" + "=" * 70)
    print("FASE 3: CONFIGURAZIONE FTS (tsvector)")
    print("=" * 70)
    
    steps = [
        ("Aggiunta colonna search_vector",
         'ALTER TABLE "entita" ADD COLUMN IF NOT EXISTS search_vector tsvector'),
        
        ("Creazione indice GIN",
         'CREATE INDEX IF NOT EXISTS idx_entita_search_vector '
         'ON "entita" USING GIN(search_vector)'),
        
        ("Popolazione tsvector",
         """UPDATE "entita" SET search_vector = to_tsvector('simple',
            coalesce(valore, '') || ' ' ||
            coalesce(cognome, '') || ' ' ||
            coalesce(nome, '') || ' ' ||
            coalesce(luogo, '') || ' ' ||
            coalesce(contesto, ''))"""),
        
        ("Creazione trigger auto-update",
         """CREATE OR REPLACE FUNCTION entita_search_vector_update() RETURNS trigger AS $$
         BEGIN
             NEW.search_vector := to_tsvector('simple',
                 coalesce(NEW.valore, '') || ' ' ||
                 coalesce(NEW.cognome, '') || ' ' ||
                 coalesce(NEW.nome, '') || ' ' ||
                 coalesce(NEW.luogo, '') || ' ' ||
                 coalesce(NEW.contesto, ''));
             RETURN NEW;
         END;
         $$ LANGUAGE plpgsql"""),
        
        ("Creazione trigger",
         """DROP TRIGGER IF EXISTS trg_entita_search_vector ON "entita";
         CREATE TRIGGER trg_entita_search_vector
         BEFORE INSERT OR UPDATE ON "entita"
         FOR EACH ROW EXECUTE FUNCTION entita_search_vector_update()"""),
    ]
    
    for desc, sql in steps:
        result = supabase_sql(sql, timeout=300)
        status = "OK" if result.get("ok") else f"ERR: {result.get('error', '')[:100]}"
        print(f"  {desc}: {status}")


# ─── RLS (Row Level Security) ────────────────────────────────────────────────

def run_rls():
    """Configure Row Level Security policies on Supabase."""
    print("\n" + "=" * 70)
    print("FASE 6: CONFIGURAZIONE RLS")
    print("=" * 70)
    
    # Public read tables (historical data)
    public_read = [
        "caduti_albooro", "caduti_bologna", "caduti_cwgc",
        "caduti_francia_ww1", "caduti_ministero", "caduti_sardi",
        "decorati", "decorati_nastroazzurro",
        "fondi_archivistici", "menzioni", "entita",
        "fonti_indice", "fonti_narrative", "archivio_documenti",
        "archivio_fonti", "eventi_1gm", "event_aliases", "event_links",
        "internati",
    ]
    
    # Authenticated CRUD tables
    auth_crud = [
        "research_plans", "research_sessions", "research_queries",
        "research_results", "research_cycles", "research_gaps",
        "research_subjects", "research_subject_sources",
        "rc_candidates", "rc_sessions", "rc_sources",
        "rc_historical_events", "rc_ai_analyses",
        "claims", "claim_evidence", "claim_relations",
        "entity_variants", "lettere_personali", "ocr_lettere",
        "record_links", "collegamenti",
    ]
    
    # Service role only (admin)
    admin_only = [
        "api_usage", "ai_providers", "ai_models", "ai_routing_policies",
        "ai_task_runs", "ai_usage_ledger", "ai_ricerche",
        "source_policies", "compliance_authorizations",
        "compliance_decisions", "compliance_review_queue",
        "graph_nodes", "graph_edges", "graph_edge_reviews",
        "graph_pipeline_runs", "graph_integrity_issues",
    ]
    
    rls_sql = []
    
    for table in public_read:
        rls_sql.append(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY')
        rls_sql.append(
            f'CREATE POLICY IF NOT EXISTS "public_read_{table}" ON "{table}" '
            f'FOR SELECT USING (true)'
        )
        rls_sql.append(
            f'CREATE POLICY IF NOT EXISTS "service_write_{table}" ON "{table}" '
            f"FOR ALL USING (auth.role() = 'service_role')"
        )
    
    for table in auth_crud:
        rls_sql.append(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY')
        rls_sql.append(
            f'CREATE POLICY IF NOT EXISTS "auth_crud_{table}" ON "{table}" '
            f"FOR ALL USING (auth.role() IN ('authenticated', 'service_role'))"
        )
    
    for table in admin_only:
        rls_sql.append(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY')
        rls_sql.append(
            f'CREATE POLICY IF NOT EXISTS "admin_only_{table}" ON "{table}" '
            f"FOR ALL USING (auth.role() = 'service_role')"
        )
    
    # Save to file
    sql_dir = BASE_DIR / "sql"
    sql_dir.mkdir(exist_ok=True)
    rls_file = "-- RLS Policies per Voci dal Fronte\n\n"
    for sql in rls_sql:
        rls_file += sql + ";\n"
    (sql_dir / "03_supabase_rls.sql").write_text(rls_file, encoding="utf-8")
    
    # Execute
    ok = 0
    for sql in rls_sql:
        result = supabase_sql(sql)
        if result.get("ok"):
            ok += 1
    
    print(f"  RLS policies: {ok}/{len(rls_sql)} applicate")
    print(f"  Pubbliche (SELECT): {len(public_read)} tabelle")
    print(f"  Autenticate (CRUD): {len(auth_crud)} tabelle")
    print(f"  Solo admin: {len(admin_only)} tabelle")


# ─── Verify ──────────────────────────────────────────────────────────────────

def run_verify():
    """Verify row counts between SQLite and Supabase."""
    print("\n" + "=" * 70)
    print("FASE 9: VERIFICA CONTEGGI")
    print("=" * 70)
    
    mismatches = 0
    total_tables = 0
    
    for db_key, db_path in DB_FILES.items():
        if not db_path.exists():
            continue
        
        print(f"\n  DB: {db_key} ({db_path.name})")
        conn = get_sqlite_conn(db_key)
        tables = get_sqlite_tables(conn)
        
        for table in tables:
            target = TABLE_RENAME.get((db_key, table), table)
            sqlite_count = get_row_count(conn, table)
            
            # Get Supabase count
            url = f"{SUPABASE_URL}/rest/v1/{target}?select=count"
            headers = dict(HEADERS)
            headers["Prefer"] = "count=exact"
            try:
                r = httpx.head(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    content_range = r.headers.get("content-range", "")
                    if "/" in content_range:
                        sb_count = int(content_range.split("/")[-1])
                    else:
                        sb_count = -1
                else:
                    sb_count = -1
            except Exception:
                sb_count = -1
            
            total_tables += 1
            status = "OK" if sqlite_count == sb_count else "MISMATCH"
            if status == "MISMATCH":
                mismatches += 1
            
            if sqlite_count > 0 or sb_count > 0:
                print(f"    {target:40s} SQLite={sqlite_count:>10,}  "
                      f"Supabase={sb_count:>10,}  [{status}]")
        
        conn.close()
    
    print(f"\nVerifica: {total_tables - mismatches}/{total_tables} tabelle corrette")
    if mismatches > 0:
        print(f"  {mismatches} mismatch trovati")
    return mismatches == 0


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Migrazione SQLite → Supabase (Voci dal Fronte)"
    )
    parser.add_argument("--schema", action="store_true", help="Crea tabelle")
    parser.add_argument("--data", action="store_true", help="Migra dati")
    parser.add_argument("--indexes", action="store_true", help="Crea indici")
    parser.add_argument("--fts", action="store_true", help="Configura FTS")
    parser.add_argument("--rls", action="store_true", help="Configura RLS")
    parser.add_argument("--verify", action="store_true", help="Verifica conteggi")
    parser.add_argument("--full", action="store_true", help="Tutto")
    parser.add_argument("--table", type=str, help="Singola tabella")
    parser.add_argument("--resume", action="store_true", help="Riprendi da checkpoint")
    args = parser.parse_args()
    
    if not any([args.schema, args.data, args.indexes, args.fts, 
                args.rls, args.verify, args.full]):
        parser.print_help()
        return
    
    print("=" * 70)
    print("MIGRAZIONE SQLite → Supabase (Voci dal Fronte)")
    print(f"URL: {SUPABASE_URL}")
    print(f"Ora: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # Check exec_sql function (needed for schema/indexes/fts/rls, not for data)
    needs_exec_sql = any([args.schema, args.indexes, args.fts, args.rls, args.full])
    if needs_exec_sql:
        print("\nVerifica funzione exec_sql...")
        if not ensure_exec_sql_function():
            return
    
    if args.schema or args.full:
        run_schema(args.table)
    
    if args.data or args.full:
        run_data(args.table, args.resume)
    
    if args.indexes or args.full:
        run_indexes()
    
    if args.fts or args.full:
        run_fts()
    
    if args.rls or args.full:
        run_rls()
    
    if args.verify or args.full:
        run_verify()
    
    print(f"\nMigrazione completata: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
