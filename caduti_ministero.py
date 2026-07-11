"""Scraper per Ministero Difesa - Banca Dati Caduti e Dispersi 1a GM.
API: https://sicadapi.difesa.it/sicad/v1/getprimaguerracadutopaginated
POST JSON: {campoSingolo, selectedPage, pageSize}
508.670 record totali. Paginazione per lettera A-Z.
L'API ha certificato SSL self-signed - uso verify=False.
Non richiede token ne' reCAPTCHA."""
import re
import time
import threading
import requests
import urllib3
from datetime import datetime
from database import get_conn

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://sicadapi.difesa.it/sicad/v1/getprimaguerracadutopaginated"
PAGE_SIZE = 15
REQUEST_DELAY = 1.0

stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": "",
             "total_saved": 0}

LETTERS = [chr(c) for c in range(ord('A'), ord('Z') + 1)]


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def get_progress() -> dict:
    return dict(_progress)


def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caduti_ministero (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER UNIQUE,
            cognome TEXT,
            nome TEXT,
            nominativo_paternita TEXT,
            paternita TEXT,
            maternita TEXT,
            data_nascita TEXT,
            data_decesso TEXT,
            provincia_nascita TEXT,
            comune_nascita TEXT,
            nazione_decesso TEXT,
            luogo_sepoltura TEXT,
            codice_volume INTEGER,
            pagina INTEGER,
            sub INTEGER,
            scheda_url TEXT,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ministero_cognome ON caduti_ministero(cognome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ministero_nominativo ON caduti_ministero(nominativo_paternita)")
    conn.commit()
    conn.close()


def _parse_nominativo(text: str) -> tuple:
    """Estrae cognome e nome dal campo nominativoePaternita.
    Format: 'ABACOT GIUSEPPE DI MICHELE' -> cognome=ABACOT, nome=GIUSEPPE DI MICHELE
    Il cognome e' la prima parola, il nome e' il resto."""
    if not text:
        return "", ""
    parts = text.strip().split(None, 1)
    cognome = parts[0] if parts else ""
    nome = parts[1] if len(parts) > 1 else ""
    return cognome, nome


def _save_record(item: dict):
    conn = get_conn()
    try:
        nominativo = item.get("nominativoePaternita", "")
        cognome, nome = _parse_nominativo(nominativo)
        scheda_url = f"https://www.difesa.it/assets/albooro/{item.get('codiceVolume','')}/{item.get('pagina','')}.jpg"
        conn.execute(
            """INSERT OR IGNORE INTO caduti_ministero
               (source_id, cognome, nome, nominativo_paternita, paternita, maternita,
                data_nascita, data_decesso, provincia_nascita, comune_nascita,
                nazione_decesso, luogo_sepoltura, codice_volume, pagina, sub,
                scheda_url, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.get("id"), cognome, nome, nominativo,
             item.get("paternita", ""), item.get("maternita", ""),
             item.get("dataNascita", ""), item.get("dataDecesso", ""),
             item.get("provinciaNascita", ""), item.get("comuneNascita", ""),
             item.get("nazioneDecesso", ""), item.get("luogoSepoltura", ""),
             item.get("codiceVolume"), item.get("pagina"), item.get("sub"),
             scheda_url, datetime.now().isoformat()),
        )
        conn.commit()
    except Exception as e:
        print(f"Errore save ministero: {e}")
    finally:
        conn.close()


def _count_saved() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as c FROM caduti_ministero").fetchone()
        conn.close()
        return row["c"]
    except Exception:
        conn.close()
        return 0


def _letter_has_records(letter: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM caduti_ministero WHERE cognome LIKE ?",
            (letter + "%",)
        ).fetchone()
        conn.close()
        return row["c"]
    except Exception:
        conn.close()
        return 0


def _search_letter(session: requests.Session, letter: str) -> int:
    """Cerca tutti i caduti con cognome che inizia per una lettera via API."""
    saved = 0
    page = 1
    total_pages = 1

    while page <= total_pages:
        if stop_event.is_set():
            break

        payload = {"campoSingolo": letter, "selectedPage": page, "pageSize": PAGE_SIZE}
        try:
            r = session.post(API_URL, json=payload, timeout=30, verify=False)
        except Exception as e:
            print(f"  Errore API letter={letter} page={page}: {e}")
            time.sleep(REQUEST_DELAY * 3)
            page += 1
            continue

        if r.status_code != 200:
            print(f"  Errore HTTP {r.status_code} letter={letter} page={page}")
            time.sleep(REQUEST_DELAY * 3)
            page += 1
            continue

        try:
            data = r.json()
        except Exception as e:
            print(f"  Errore JSON letter={letter} page={page}: {e}")
            page += 1
            continue

        if data.get("isError"):
            print(f"  API error letter={letter}: {data.get('errorMessage')}")
            break

        content = data.get("content", [])
        total_rows = data.get("totalRowsCount", 0)
        total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

        for item in content:
            if stop_event.is_set():
                break
            _save_record(item)
            saved += 1
            _progress["processed"] += 1
            nom = item.get("nominativoePaternita", "")[:30]
            _progress["current"] = nom

        saved_db = _count_saved()
        _progress["total_saved"] = saved_db

        if page == 1:
            print(f"    Lettera {letter}: {total_rows} record in {total_pages} pagine")

        if page % 20 == 0:
            print(f"    {letter} pag {page}/{total_pages}: {saved} salvati | DB: {saved_db}")

        page += 1
        time.sleep(REQUEST_DELAY)

    return saved


def scrape_all(resume: bool = True):
    """Scrape di tutti i caduti del Ministero Difesa per lettera."""
    stop_event.clear()
    _init_table()

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Origin": "https://www.difesa.it",
        "Referer": "https://www.difesa.it/il-ministro/cadutiinguerra/primaguerra/primaguerra.html",
    })

    already = _count_saved() if resume else 0
    _progress.update({
        "status": "processing", "processed": already, "total": 508670,
        "current": "", "total_saved": already
    })

    for letter in LETTERS:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return

        if resume and _letter_has_records(letter) > 0:
            print(f"  Lettera {letter}: gia' scaricata, skip")
            continue

        _progress["current"] = f"Lettera {letter}"
        print(f"  Ministero Difesa - lettera {letter}...")

        saved = _search_letter(s, letter)
        total_saved = _count_saved()
        _progress["total_saved"] = total_saved
        print(f"    Lettera {letter}: {saved} record | Totale DB: {total_saved}")

        time.sleep(REQUEST_DELAY)

    _progress["status"] = "done"
    _progress["current"] = ""
    print(f"\n=== Ministero Difesa completato. Totale: {_count_saved()} ===")


def count_caduti_ministero() -> int:
    try:
        return _count_saved()
    except Exception:
        return 0
