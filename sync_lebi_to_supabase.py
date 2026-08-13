"""Sync lebi_records da SQLite a Supabase (PostgreSQL via REST API).

Crea la tabella su Supabase se non esiste, poi sincronizza in batch
con checkpoint/resume.

Uso:
  python sync_lebi_to_supabase.py --schema     # crea tabella
  python sync_lebi_to_supabase.py --data       # sync dati
  python sync_lebi_to_supabase.py --full       # schema + data
  python sync_lebi_to_supabase.py --verify     # verifica conteggi
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import httpx

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "imi_internati.db"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
CHECKPOINT_FILE = BASE_DIR / "sync_lebi_supabase_checkpoint.json"
BATCH_SIZE = 500

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRORE: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY richiesti in .env")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lebi_records (
    id SERIAL PRIMARY KEY,
    lebi_id TEXT UNIQUE NOT NULL,
    cognome TEXT,
    nome TEXT,
    data_nascita TEXT,
    luogo_nascita TEXT,
    provincia_nascita TEXT,
    regione_nascita TEXT,
    grado TEXT,
    reparto TEXT,
    arma TEXT,
    fronte_cattura TEXT,
    luogo_cattura TEXT,
    data_cattura TEXT,
    matricola TEXT,
    campi_internamento TEXT,
    sorte TEXT,
    data_decesso TEXT,
    luogo_decesso TEXT,
    causa_morte TEXT,
    luogo_sepoltura TEXT,
    data_rientro TEXT,
    luogo_rientro TEXT,
    fonti TEXT,
    pdf_url TEXT,
    detail_url TEXT,
    imported_at TEXT,
    enriched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_lebi_cognome ON lebi_records(cognome);
CREATE INDEX IF NOT EXISTS idx_lebi_nome ON lebi_records(nome);
CREATE INDEX IF NOT EXISTS idx_lebi_id ON lebi_records(lebi_id);
CREATE INDEX IF NOT EXISTS idx_lebi_sorte ON lebi_records(sorte);
CREATE INDEX IF NOT EXISTS idx_lebi_grado ON lebi_records(grado);
"""

COLS = [
    "lebi_id", "cognome", "nome", "data_nascita", "luogo_nascita",
    "provincia_nascita", "regione_nascita", "grado", "reparto", "arma",
    "fronte_cattura", "luogo_cattura", "data_cattura", "matricola",
    "campi_internamento", "sorte", "data_decesso", "luogo_decesso",
    "causa_morte", "luogo_sepoltura", "data_rientro", "luogo_rientro",
    "fonti", "pdf_url", "detail_url", "imported_at", "enriched_at",
]


def supabase_sql(sql: str, timeout: int = 120) -> dict:
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


def run_schema():
    print("\n=== CREAZIONE SCHEMA lebi_records SU SUPABASE ===")
    result = supabase_sql(CREATE_TABLE_SQL)
    if result.get("ok"):
        print("  [OK] Tabella lebi_records creata (o gia esistente)")
    else:
        print(f"  [ERR] {result.get('error', 'unknown')}")
        return False
    return True


def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    return {}


def save_checkpoint(data: dict):
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_data():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]
    if total == 0:
        print("  [SKIP] Nessun record lebi_records in SQLite")
        conn.close()
        return

    cp = load_checkpoint()
    offset = cp.get("offset", 0)
    if offset >= total:
        print(f"  [DONE] Gia sincronizzato ({total:,} righe)")
        conn.close()
        return
    if offset > 0:
        print(f"  [RESUME] Da offset {offset:,}/{total:,}")

    url = f"{SUPABASE_URL}/rest/v1/lebi_records?on_conflict=lebi_id"
    headers = dict(HEADERS)
    headers["Prefer"] = "return=minimal,resolution=merge-duplicates"

    col_list = ", ".join(f'"{c}"' for c in COLS)
    migrated = offset
    errors = 0
    start_time = time.time()
    batch_num = 0

    while offset < total:
        rows = conn.execute(
            f'SELECT {col_list} FROM lebi_records ORDER BY id LIMIT {BATCH_SIZE} OFFSET {offset}'
        ).fetchall()

        if not rows:
            break

        batch = []
        for row in rows:
            record = {}
            for c in COLS:
                val = row[c]
                if isinstance(val, bytes):
                    val = val.hex()
                record[c] = val
            batch.append(record)

        batch_num += 1
        try:
            r = httpx.post(url, headers=headers, json=batch, timeout=60)
            if r.status_code in (200, 201, 204):
                migrated += len(batch)
                offset += BATCH_SIZE

                if batch_num % 10 == 0:
                    cp["offset"] = offset
                    save_checkpoint(cp)

                if migrated % (BATCH_SIZE * 20) == 0 or migrated >= total:
                    pct = (migrated / total) * 100
                    elapsed = time.time() - start_time
                    rate = migrated / max(elapsed, 1)
                    eta = (total - migrated) / max(rate, 1)
                    print(f"    lebi_records: {migrated:,}/{total:,} "
                          f"({pct:.0f}%) [{rate:.0f} r/s, ETA {eta:.0f}s]")
            else:
                errors += 1
                err_text = r.text[:300]
                if errors <= 3:
                    print(f"    [ERR] offset {offset}: HTTP {r.status_code} - {err_text}")
                if errors > 10:
                    print(f"    [ABORT] Troppi errori")
                    break
                offset += BATCH_SIZE
        except httpx.TimeoutException:
            errors += 1
            print(f"    [TIMEOUT] offset {offset}")
            time.sleep(5)
            offset += BATCH_SIZE
        except Exception as e:
            errors += 1
            print(f"    [ERR] {e}")
            offset += BATCH_SIZE

    cp["offset"] = total
    save_checkpoint(cp)

    elapsed = time.time() - start_time
    print(f"\n  [DONE] lebi_records: {migrated:,}/{total:,} righe "
          f"({elapsed:.0f}s, {errors} errori)")
    conn.close()


def run_verify():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    sqlite_count = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]
    conn.close()

    url = f"{SUPABASE_URL}/rest/v1/lebi_records?select=*&limit=1"
    headers = dict(HEADERS)
    headers["Prefer"] = "count=exact"
    headers["Range"] = "0-0"

    try:
        r = httpx.get(url, headers=headers, timeout=30)
        content_range = r.headers.get("content-range", "")
        if content_range:
            supa_count = int(content_range.split("/")[1])
        else:
            supa_count = 0
    except Exception:
        supa_count = -1

    print(f"\n=== VERIFIA ===")
    print(f"  SQLite:  {sqlite_count:,} record")
    print(f"  Supabase: {supa_count:,} record")
    if sqlite_count == supa_count:
        print(f"  [OK] Conteaggi coincidono")
    else:
        diff = supa_count - sqlite_count
        print(f"  [DIFF] Differenza: {diff:+,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync lebi_records → Supabase")
    parser.add_argument("--schema", action="store_true", help="Crea tabella su Supabase")
    parser.add_argument("--data", action="store_true", help="Sincronizza dati")
    parser.add_argument("--full", action="store_true", help="Schema + data")
    parser.add_argument("--verify", action="store_true", help="Verifica conteggi")
    args = parser.parse_args()

    if args.full:
        run_schema()
        run_data()
        run_verify()
    elif args.schema:
        run_schema()
    elif args.data:
        run_data()
    elif args.verify:
        run_verify()
    else:
        parser.print_help()
