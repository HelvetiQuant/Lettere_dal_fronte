"""Push matricola_militare, matricola_cattura, impiego da SQLite a Supabase.

Upsert batch su lebi_records (on_conflict=lebi_id): aggiorna solo le 3 colonne
inviate, lasciando inalterate le altre.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "imi_internati.db"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
CHECKPOINT_FILE = BASE_DIR / "push_lebi_matricole_checkpoint.json"
BATCH_SIZE = 500

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRORE: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY richiesti in .env")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal,resolution=merge-duplicates",
}


def main():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]

    cp = {}
    if CHECKPOINT_FILE.exists():
        cp = json.loads(CHECKPOINT_FILE.read_text())
    offset = cp.get("offset", 0)

    url = f"{SUPABASE_URL}/rest/v1/lebi_records?on_conflict=lebi_id"
    migrated = offset
    errors = 0
    t0 = time.time()

    print(f"Push matricole/impiego: {total:,} record, resume da offset {offset:,}")

    while offset < total:
        rows = conn.execute(
            """SELECT lebi_id, matricola_militare, matricola_cattura, impiego
               FROM lebi_records ORDER BY id LIMIT ? OFFSET ?""",
            (BATCH_SIZE, offset),
        ).fetchall()
        if not rows:
            break

        batch = [
            {
                "lebi_id": r["lebi_id"],
                "matricola_militare": r["matricola_militare"],
                "matricola_cattura": r["matricola_cattura"],
                "impiego": r["impiego"],
            }
            for r in rows
        ]

        try:
            r = httpx.post(url, headers=HEADERS, json=batch, timeout=60)
            if r.status_code in (200, 201, 204):
                migrated += len(batch)
            else:
                errors += 1
                if errors <= 3:
                    print(f"  [ERR] offset {offset}: HTTP {r.status_code} - {r.text[:300]}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  [ERR] offset {offset}: {e}")
            time.sleep(2)
            continue

        offset += len(batch)
        if offset % 10000 == 0 or offset >= total:
            cp["offset"] = offset
            CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2))
            pct = offset / total * 100
            rate = offset / max(time.time() - t0, 1)
            print(f"  {offset:,}/{total:,} ({pct:.0f}%) [{rate:.0f} r/s]")

    elapsed = time.time() - t0
    print(f"\nCompletato: {migrated:,}/{total:,} in {elapsed:.0f}s, errori={errors}")
    conn.close()


if __name__ == "__main__":
    main()
