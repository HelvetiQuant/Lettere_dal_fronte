"""Import massivo LeBI — fetch diretto per ID con thread pool.

Strategia:
1. Enumera ID 2345-330027 con GET parallelo (20 thread)
2. Per ogni ID valido (200), parse HTML e estrai dati biografici
3. Per ogni ID non valido (404), skip
4. Checkpoint ogni 500 record
5. Resume da ultimo checkpoint

Tabella: lebi_records
"""
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
log = logging.getLogger("lebi_import")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imi_internati.db")
BASE_URL = "https://www.lessicobiograficoimi.it"
DETAIL_URL = f"{BASE_URL}/frontend_prodimi.php/caduti/show"
HEADERS = {"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research; bulk-import-v2)"}
CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lebi_import_checkpoint.json")

MIN_ID = 2345
MAX_ID = 330027
BATCH_SIZE = 500
MAX_WORKERS = 20
REQUEST_TIMEOUT = 15


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lebi_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lebi_cognome ON lebi_records(cognome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lebi_nome ON lebi_records(nome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lebi_id ON lebi_records(lebi_id)")
    conn.commit()


def load_checkpoint() -> Dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_id": MIN_ID - 1, "total_valid": 0, "total_404": 0, "total_errors": 0}


def save_checkpoint(cp: Dict):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2)


def parse_record_html(html: str, lebi_id: str) -> Optional[Dict]:
    """Parse a LeBI record detail page and extract all biographical fields."""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    name_from_title = title_text.replace("LeBI - ", "").strip() if "LeBI - " in title_text else ""

    sections = {}
    active_section = "ANAGRAFICA"

    for span in soup.find_all("span", class_="fallen-box-title"):
        sn = span.get_text(strip=True)
        sections[sn] = {"fields": {}, "notes": []}

    for element in soup.find_all(["span", "div"], class_=True):
        classes = element.get("class", [])
        text = element.get_text(strip=True)

        if "fallen-box-title" in classes:
            if text:
                active_section = text
                sections.setdefault(active_section, {"fields": {}, "notes": []})
            continue

        if "fallen-label" in classes:
            label = text
            if not label:
                continue
            value_div = element.find_next_sibling("div", class_="fallen-field-margins")
            if value_div and "fallen-label" not in value_div.get("class", []):
                value = value_div.get_text(strip=True)
                if value:
                    sections.setdefault(active_section, {"fields": {}, "notes": []})
                    sections[active_section]["fields"][label] = value
            continue

    intern_camps = []
    in_internment = False
    for element in soup.find_all(["span", "div"], class_=True):
        classes = element.get("class", [])
        text = element.get_text(strip=True)
        if "fallen-box-title" in classes:
            in_internment = (text == "INTERNAMENTO")
            continue
        if in_internment and "fallen-field-margins" in classes and "fallen-label" not in classes:
            if text and text not in ("Luogo internamento", "Impiego"):
                intern_camps.append(text)

    anag = sections.get("ANAGRAFICA", {}).get("fields", {})
    militare = sections.get("POSIZIONE MILITARE", {}).get("fields", {})
    cattura = sections.get("CATTURA", {}).get("fields", {})
    decesso = sections.get("DECESSO", {}).get("fields", {})
    rientro = sections.get("RIENTRO", {}).get("fields", {})

    matricola = ""
    for note in sections.get("CATTURA", {}).get("notes", []):
        m = re.search(r"Matricola:\s*(\S+)", note)
        if m:
            matricola = m.group(1)
            break

    cognome = anag.get("COGNOME", "")
    nome = anag.get("NOME", "")
    if not cognome and name_from_title:
        parts = name_from_title.split()
        if len(parts) >= 2:
            cognome = parts[0]
            nome = " ".join(parts[1:])
        elif len(parts) == 1:
            cognome = parts[0]

    sorte = ""
    if decesso:
        sorte = "deceduto"
    elif rientro:
        sorte = "sopravvissuto"

    camps_str = json.dumps(intern_camps, ensure_ascii=False) if intern_camps else ""
    fonti_text = " | ".join(sections.get("FONTI", {}).get("notes", []))

    return {
        "lebi_id": str(lebi_id),
        "cognome": cognome.upper().strip() if cognome else "",
        "nome": nome.upper().strip() if nome else "",
        "data_nascita": anag.get("Data di nascita", ""),
        "luogo_nascita": anag.get("Comune di nascita", ""),
        "provincia_nascita": anag.get("Provincia", ""),
        "regione_nascita": anag.get("Regione", ""),
        "grado": militare.get("Grado", ""),
        "reparto": militare.get("Reparto", ""),
        "arma": militare.get("Arma", ""),
        "fronte_cattura": cattura.get("Fronte", ""),
        "luogo_cattura": cattura.get("Luogo di cattura", ""),
        "data_cattura": cattura.get("Data cattura", ""),
        "matricola": matricola,
        "campi_internamento": camps_str,
        "sorte": sorte,
        "data_decesso": decesso.get("Data decesso", ""),
        "luogo_decesso": decesso.get("Luogo/Fronte", ""),
        "causa_morte": decesso.get("Causa morte", ""),
        "luogo_sepoltura": decesso.get("Luogo di sepoltura", ""),
        "data_rientro": rientro.get("Data rientro", ""),
        "luogo_rientro": rientro.get("Luogo di rientro", ""),
        "fonti": fonti_text,
        "pdf_url": f"{BASE_URL}/frontend_prodimi.php/caduti/showpdf/{lebi_id}",
        "detail_url": f"{DETAIL_URL}/{lebi_id}",
    }


def fetch_and_parse(lebi_id: int, session: requests.Session) -> Optional[Dict]:
    """Fetch a LeBI record by ID and parse it. Returns None if 404."""
    url = f"{DETAIL_URL}/{lebi_id}"
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return parse_record_html(resp.text, str(lebi_id))
    except requests.RequestException:
        return None


def insert_record(conn: sqlite3.Connection, record: Dict) -> bool:
    now = datetime.now().isoformat()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO lebi_records
            (lebi_id, cognome, nome, data_nascita, luogo_nascita, provincia_nascita,
             regione_nascita, grado, reparto, arma, fronte_cattura, luogo_cattura,
             data_cattura, matricola, campi_internamento, sorte, data_decesso,
             luogo_decesso, causa_morte, luogo_sepoltura, data_rientro, luogo_rientro,
             fonti, pdf_url, detail_url, imported_at, enriched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            record["lebi_id"], record["cognome"], record["nome"], record["data_nascita"],
            record["luogo_nascita"], record["provincia_nascita"], record["regione_nascita"],
            record["grado"], record["reparto"], record["arma"],
            record["fronte_cattura"], record["luogo_cattura"], record["data_cattura"],
            record["matricola"], record["campi_internamento"], record["sorte"],
            record["data_decesso"], record["luogo_decesso"], record["causa_morte"],
            record["luogo_sepoltura"], record["data_rientro"], record["luogo_rientro"],
            record["fonti"], record["pdf_url"], record["detail_url"], now, now
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_existing_ids(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT lebi_id FROM lebi_records").fetchall()
    return {r["lebi_id"] for r in rows}


def run_import():
    conn = get_conn()
    ensure_table(conn)

    cp = load_checkpoint()
    existing = get_existing_ids(conn)
    log.info(f"LeBI bulk import v2 starting")
    log.info(f"Existing records in DB: {len(existing)}")
    log.info(f"Checkpoint: last_id={cp['last_id']}, valid={cp['total_valid']}, 404={cp['total_404']}")

    start_id = cp["last_id"] + 1
    if start_id < MIN_ID:
        start_id = MIN_ID

    session = requests.Session()
    session.headers.update(HEADERS)
    from requests.adapters import HTTPAdapter
    session.mount("https://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS))

    total_valid = cp["total_valid"]
    total_404 = cp["total_404"]
    total_errors = cp["total_errors"]
    batch_start = start_id

    log.info(f"Starting from ID {start_id} to {MAX_ID}")

    while batch_start <= MAX_ID:
        batch_end = min(batch_start + BATCH_SIZE - 1, MAX_ID)
        batch_ids = list(range(batch_start, batch_end + 1))

        to_fetch = [i for i in batch_ids if str(i) not in existing]
        if not to_fetch:
            batch_start = batch_end + 1
            continue

        t0 = time.time()
        batch_results = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_and_parse, i, session): i for i in to_fetch}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        batch_results.append(result)
                        total_valid += 1
                    else:
                        total_404 += 1
                except Exception:
                    total_errors += 1

        inserted = 0
        for record in batch_results:
            if insert_record(conn, record):
                inserted += 1
            existing.add(record["lebi_id"])

        elapsed = time.time() - t0
        progress = (batch_end - MIN_ID + 1) / (MAX_ID - MIN_ID + 1) * 100

        log.info(
            f"IDs {batch_start}-{batch_end} ({progress:.1f}%): "
            f"{len(batch_results)} valid, inserted={inserted}, "
            f"404={len(to_fetch)-len(batch_results)}, "
            f"time={elapsed:.1f}s, "
            f"total_valid={total_valid}, total_404={total_404}"
        )

        cp["last_id"] = batch_end
        cp["total_valid"] = total_valid
        cp["total_404"] = total_404
        cp["total_errors"] = total_errors
        save_checkpoint(cp)

        batch_start = batch_end + 1

    final_count = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]
    log.info(f"\n=== IMPORT COMPLETE ===")
    log.info(f"Total records in DB: {final_count}")
    log.info(f"Total valid (200): {total_valid}")
    log.info(f"Total 404: {total_404}")
    log.info(f"Total errors: {total_errors}")
    conn.close()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "import"

    if mode == "import":
        run_import()
    elif mode == "status":
        conn = get_conn()
        ensure_table(conn)
        total = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]
        with_data = conn.execute("SELECT COUNT(*) FROM lebi_records WHERE cognome != '' AND cognome IS NOT NULL").fetchone()[0]
        deceduti = conn.execute("SELECT COUNT(*) FROM lebi_records WHERE sorte = 'deceduto'").fetchone()[0]
        sopravvissuti = conn.execute("SELECT COUNT(*) FROM lebi_records WHERE sorte = 'sopravvissuto'").fetchone()[0]
        print(f"Total LeBI records: {total}")
        print(f"With surname: {with_data}")
        print(f"Deceduti: {deceduti}")
        print(f"Sopravvissuti: {sopravvissuti}")
        rows = conn.execute("SELECT lebi_id, cognome, nome, grado, sorte FROM lebi_records LIMIT 5").fetchall()
        for r in rows:
            print(f"  {r['lebi_id']}: {r['cognome']} {r['nome']} — {r['grado']} — {r['sorte']}")
        conn.close()
    elif mode == "test":
        conn = get_conn()
        ensure_table(conn)
        session = requests.Session()
        session.headers.update(HEADERS)
        test_ids = [2345, 2346, 2347, 2348, 2349, 2350, 50000, 100000, 200000, 300000]
        for tid in test_ids:
            record = fetch_and_parse(tid, session)
            if record:
                print(f"  ID {tid}: {record['cognome']} {record['nome']} — {record['grado']} — {record['sorte']}")
                insert_record(conn, record)
            else:
                print(f"  ID {tid}: 404")
        count = conn.execute("SELECT COUNT(*) FROM lebi_records").fetchone()[0]
        print(f"\nTotal in DB: {count}")
        conn.close()
