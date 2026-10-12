"""Aggiorna i record LeBI con matricola vuota - estrae matricola dal campo Note."""

import json
import logging
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lebi_update_matricole")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imi_internati.db")
BASE_URL = "https://www.lessicobiograficoimi.it"
DETAIL_URL = f"{BASE_URL}/frontend_prodimi.php/caduti/show"
HEADERS = {"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research; update-matricole-v1)"}
CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lebi_update_checkpoint.json")

BATCH_SIZE = 100
MAX_WORKERS = 10
REQUEST_TIMEOUT = 15

# Label = Stalag/camp designation -> prisoner camp number; else -> military matricola
CAMP_LABEL_RE = re.compile(
    r"stalag|oflag|dulag|kz\b|lager|\bcampo\b|prigionier|prigionia|dachau|mauthausen|"
    r"buchenwald|auschwitz|fallingbostel|warendorf|duderstadt|katovice|katowice|"
    r"breslavia|witten|nevers|marlag|milag|stalino|lamsdorf",
    re.IGNORECASE,
)
ROMAN_CAMP_RE = re.compile(r"^\(?\s*[IVXLCDM]+\s*[A-Z]{0,2}\s*\)?$")


# Label = military organization -> military matricola
MIL_LABEL_RE = re.compile(
    r"milit|distret|marina|aeronaut|guardia|finanz|carabinier|legione|capitaneria|"
    r"compartimento|dipartimento|polizia|p\.s\.|c\.r\.i\.|\bcri\b|crem|z\.a\.t\.|"
    r"scuola|centro|corpo|comando|equipaggi|deposito|direzione|reclutamento",
    re.IGNORECASE,
)


def is_camp_matricola(label: str) -> bool:
    """True if the matricola label refers to a prisoner camp (Stalag code, KZ, camp name)."""
    if CAMP_LABEL_RE.search(label):
        return True
    return bool(ROMAN_CAMP_RE.match(label.strip()))


def is_cattura_matricola(label: str, section: str) -> bool:
    """True if a matricola note is a capture/prisoner matricola."""
    if is_camp_matricola(label):
        return True
    if MIL_LABEL_RE.search(label):
        return False
    # Bare/generic "Matricola" label inside CATTURA or INTERNAMENTO = capture matricola
    return section in ("CATTURA", "INTERNAMENTO")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def load_checkpoint() -> Dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_processed_id": 0, "total_updated": 0, "total_skipped": 0, "total_errors": 0}


def save_checkpoint(cp: Dict):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2)


def fetch_and_parse(lebi_id: int, session: requests.Session) -> Dict:
    """Fetch LeBI record and extract matricola. No DB writes (thread-safe)."""
    url = f"{DETAIL_URL}/{lebi_id}"
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return {"lebi_id": lebi_id, "status": "404", "matricola": None}

        soup = BeautifulSoup(resp.text, "html.parser")
        matricola = ""
        camp_numbers = []
        active_section = "ANAGRAFICA"
        for element in soup.find_all(["span", "div"], class_=True):
            classes = element.get("class", [])
            text = element.get_text(strip=True)
            if "fallen-box-title" in classes:
                if text:
                    active_section = text
                continue
            if "white-corner-show" not in classes:
                continue
            if not text or text == "Note":
                continue
            # Split merged notes like "Matricola III A: 113541.Matricola KZ: 0565."
            for part in re.split(r"\.\s*(?=Matricola)", text, flags=re.IGNORECASE):
                m = re.search(r"Matricola\s+([^:]+?)\s*:\s*(\S+)", part, re.IGNORECASE)
                if m:
                    label = m.group(1).strip()
                    value = m.group(2).strip().rstrip(".")
                    if is_cattura_matricola(label, active_section):
                        camp_numbers.append(f"Matricola {label}: {value}")
                    elif not matricola:
                        matricola = value
                else:
                    m2 = re.search(r"Matricola\s*:\s*(\S+)", part, re.IGNORECASE)
                    if m2:
                        value = m2.group(1).strip().rstrip(".")
                        if active_section in ("CATTURA", "INTERNAMENTO"):
                            camp_numbers.append(f"Matricola: {value}")
                        elif not matricola:
                            matricola = value

        numero_campo = "; ".join(camp_numbers) if camp_numbers else ""
        if matricola or numero_campo:
            return {
                "lebi_id": lebi_id,
                "status": "found",
                "matricola": matricola or None,
                "numero_campo": numero_campo or None,
            }
        return {"lebi_id": lebi_id, "status": "no_matricola", "matricola": None}

    except Exception as e:
        return {"lebi_id": lebi_id, "status": "error", "error": str(e)}


def run_update(only_ids=None):
    conn = get_conn()
    cp = load_checkpoint()

    if only_ids is not None:
        lebi_ids = sorted(only_ids)
    else:
        rows = conn.execute(
            "SELECT lebi_id FROM lebi_records WHERE matricola_militare IS NULL OR matricola_militare = '' ORDER BY lebi_id"
        ).fetchall()
        lebi_ids = [int(r["lebi_id"]) for r in rows]
    
    log.info(f"LeBI matricola update starting")
    log.info(f"Records without matricola: {len(lebi_ids)}")
    log.info(f"Checkpoint: last_id={cp['last_processed_id']}, updated={cp['total_updated']}")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    from requests.adapters import HTTPAdapter
    session.mount("https://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS))
    
    total_updated = cp["total_updated"]
    total_skipped = cp["total_skipped"]
    total_errors = cp["total_errors"]
    
    # Resume: skip IDs already processed (lebi_id <= last_processed_id)
    if cp["last_processed_id"] and only_ids is None:
        lebi_ids = [lid for lid in lebi_ids if lid > cp["last_processed_id"]]
        log.info(f"Resuming after lebi_id={cp['last_processed_id']}: {len(lebi_ids)} remaining")

    # Process in batches
    for i in range(0, len(lebi_ids), BATCH_SIZE):
        batch = lebi_ids[i:i+BATCH_SIZE]
        batch_start = batch[0]
        batch_end = batch[-1]

        t0 = time.time()
        batch_results = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_and_parse, lid, session): lid for lid in batch}
            for future in as_completed(futures):
                try:
                    batch_results.append(future.result())
                except Exception:
                    total_errors += 1

        # Write all updates in main thread (SQLite single-writer)
        updates = [
            (r["matricola"], r.get("numero_campo"), str(r["lebi_id"]))
            for r in batch_results if r["status"] == "found"
        ]
        if updates:
            conn.executemany(
                "UPDATE lebi_records SET matricola_militare = ?, matricola_cattura = ? WHERE lebi_id = ?",
                updates,
            )
            conn.commit()

        total_updated += len(updates)
        total_skipped += sum(1 for r in batch_results if r["status"] == "no_matricola")
        batch_errors = [r["lebi_id"] for r in batch_results if r["status"] in ("error", "404")]
        total_errors += len(batch_errors)

        cp.setdefault("error_ids", [])
        cp["error_ids"] = sorted(set(cp["error_ids"]) | set(batch_errors))

        elapsed = time.time() - t0
        progress = (i + len(batch)) / len(lebi_ids) * 100

        log.info(
            f"Batch {batch_start}-{batch_end} ({progress:.1f}%): "
            f"found={len(updates)}, "
            f"no_mat={sum(1 for r in batch_results if r['status']=='no_matricola')}, "
            f"errors={sum(1 for r in batch_results if r['status'] in ('error','404'))}, "
            f"time={elapsed:.1f}s, "
            f"total_updated={total_updated}"
        )

        cp["last_processed_id"] = batch_end
        cp["total_updated"] = total_updated
        cp["total_skipped"] = total_skipped
        cp["total_errors"] = total_errors
        save_checkpoint(cp)
    
    final_count = conn.execute("SELECT COUNT(*) FROM lebi_records WHERE matricola_militare IS NOT NULL AND matricola_militare != ''").fetchone()[0]
    log.info(f"\n=== UPDATE COMPLETE ===")
    log.info(f"Records with matricola: {final_count}")
    log.info(f"Total updated: {total_updated}")
    log.info(f"Total skipped: {total_skipped}")
    log.info(f"Total errors: {total_errors}")
    conn.close()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "update"
    
    if mode == "update":
        run_update()
    elif mode == "retry":
        cp = load_checkpoint()
        err_ids = cp.get("error_ids", [])
        if not err_ids:
            print("Nessun ID con errore nel checkpoint")
        else:
            print(f"Retry su {len(err_ids)} ID con errore")
            cp["error_ids"] = []
            run_update(only_ids=err_ids)
    elif mode == "status":
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]
        with_matricola = conn.execute("SELECT COUNT(*) FROM lebi_records WHERE matricola_militare IS NOT NULL AND matricola_militare != ''").fetchone()[0]
        without_matricola = total - with_matricola
        print(f"Total LeBI records: {total}")
        print(f"With matricola: {with_matricola}")
        print(f"Without matricola: {without_matricola}")
        print(f"Coverage: {with_matricola/total*100:.1f}%")
        conn.close()
    elif mode == "test":
        session = requests.Session()
        session.headers.update(HEADERS)
        test_ids = [300438, 81270, 264543, 50000, 2351, 2346]
        for tid in test_ids:
            result = fetch_and_parse(tid, session)
            print(f"ID {tid}: {result}")
