"""Scraper per Eroi e Caduti Sardi - Unione Sarda.
Fonte: https://eroiecadutisardi.unionesarda.it/Search?query=LETTER&war=1
20.531 caduti sardi della Grande Guerra.
Il sito ha certificato SSL scaduto - uso verify=False.
Struttura HTML: div.itemDefunto > a.city (comune) + a.name (cognome nome) + div.war + div.date"""
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from database import get_conn
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://eroiecadutisardi.unionesarda.it"
SEARCH_URL = f"{BASE}/Search"
REQUEST_DELAY = 1.5

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
        CREATE TABLE IF NOT EXISTS caduti_sardi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            cognome TEXT,
            nome TEXT,
            paternita TEXT,
            luogo_nascita TEXT,
            data_nascita TEXT,
            comune_residenza TEXT,
            guerra TEXT,
            grado TEXT,
            reparto TEXT,
            data_morte TEXT,
            luogo_morte TEXT,
            causa_morte TEXT,
            decorazioni TEXT,
            scheda_url TEXT,
            elaborato_il TEXT NOT NULL,
            UNIQUE(source_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sardi_cognome ON caduti_sardi(cognome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sardi_comune ON caduti_sardi(comune_residenza)")
    conn.commit()
    conn.close()


def _save_record(rec: dict):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO caduti_sardi
               (source_id, cognome, nome, paternita, luogo_nascita, data_nascita,
                comune_residenza, guerra, grado, reparto, data_morte, luogo_morte,
                causa_morte, decorazioni, scheda_url, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec["source_id"], rec["cognome"], rec["nome"], rec["paternita"],
             rec["luogo_nascita"], rec["data_nascita"],
             rec["comune_residenza"], rec["guerra"], rec["grado"], rec["reparto"],
             rec["data_morte"], rec["luogo_morte"], rec["causa_morte"],
             rec["decorazioni"], rec["scheda_url"], rec["elaborato_il"]),
        )
        conn.commit()
    except Exception as e:
        print(f"Errore save sardi: {e}")
    finally:
        conn.close()


def _count_saved() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as c FROM caduti_sardi").fetchone()
        conn.close()
        return row["c"]
    except Exception:
        conn.close()
        return 0


def _letter_has_records(letter: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM caduti_sardi WHERE cognome LIKE ?",
            (letter + "%",)
        ).fetchone()
        conn.close()
        return row["c"]
    except Exception:
        conn.close()
        return 0


def _parse_name(full_name: str) -> tuple:
    """Separa cognome e nome da una stringa come 'Abau Anacleto'.
    Il cognome e' la prima parola, il nome e' il resto."""
    if not full_name:
        return "", ""
    parts = full_name.strip().split(None, 1)
    cognome = parts[0] if parts else ""
    nome = parts[1] if len(parts) > 1 else ""
    return cognome, nome


def _parse_date_field(date_text: str) -> tuple:
    """Parsea il campo date: '15 Maggio 1893 - 03 Giugno 1916 sul monte Cengio'
    Ritorna (data_nascita, data_morte, luogo_morte)."""
    data_nascita = ""
    data_morte = ""
    luogo_morte = ""

    if not date_text:
        return data_nascita, data_morte, luogo_morte

    # Pattern: date in formato italiano 'DD Mese YYYY'
    date_pattern = r'(\d{1,2}\s+\w+\s+\d{4})'
    dates = re.findall(date_pattern, date_text)

    if len(dates) >= 2:
        data_nascita = dates[0]
        data_morte = dates[1]
    elif len(dates) == 1:
        data_morte = dates[0]

    # Estrai luogo morte: testo dopo l'ultima data
    if dates:
        after_last = date_text.split(dates[-1])
        if len(after_last) > 1:
            luogo_morte = after_last[-1].strip()
            # Rimuovi preposizioni iniziali
            luogo_morte = re.sub(r'^(sul|sulla|nel|nella|in|a|presso|dopo)\s+', '', luogo_morte, flags=re.I).strip()
            luogo_morte = luogo_morte.rstrip('.,;')

    return data_nascita, data_morte, luogo_morte


def _parse_item(item) -> dict:
    """Parsea un div.itemDefunto in un record."""
    rec = {
        "source_id": "", "cognome": "", "nome": "", "paternita": "",
        "luogo_nascita": "", "data_nascita": "", "comune_residenza": "",
        "guerra": "", "grado": "", "reparto": "",
        "data_morte": "", "luogo_morte": "", "causa_morte": "",
        "decorazioni": "", "scheda_url": "",
        "elaborato_il": datetime.now().isoformat(),
    }

    # a.city -> comune residenza
    city_link = item.find("a", class_="city")
    if city_link:
        rec["comune_residenza"] = city_link.get_text(strip=True)

    # a.name -> cognome + nome, href contiene ID
    name_link = item.find("a", class_="name")
    if name_link:
        full_name = name_link.get_text(strip=True)
        rec["cognome"], rec["nome"] = _parse_name(full_name)
        href = name_link.get("href", "")
        if href:
            if not href.startswith("http"):
                href = BASE + href if href.startswith("/") else BASE + "/" + href
            rec["scheda_url"] = href
            # Estrai source_id dall'href: /Cagliari/ABAU ANACLETO-1 -> 1
            m = re.search(r'-(\d+)$', href)
            if m:
                rec["source_id"] = m.group(1)

    # div.war -> guerra
    war_div = item.find("div", class_="war")
    if war_div:
        rec["guerra"] = war_div.get_text(strip=True)

    # div.date -> date e luogo
    date_div = item.find("div", class_="date")
    if date_div:
        date_text = date_div.get_text(strip=True)
        rec["data_nascita"], rec["data_morte"], rec["luogo_morte"] = _parse_date_field(date_text)

    return rec


def _search_letter(session: requests.Session, letter: str) -> int:
    """Cerca tutti i caduti con query=letter, paginando con page param."""
    saved = 0
    page = 0
    total_count = 0

    while True:
        if stop_event.is_set():
            break

        params = {"query": letter, "war": "1", "page": page}
        try:
            r = session.get(SEARCH_URL, params=params, timeout=20, verify=False)
        except Exception as e:
            print(f"  Errore letter={letter} page={page}: {e}")
            time.sleep(REQUEST_DELAY * 3)
            page += 1
            continue

        if r.status_code != 200:
            print(f"  Errore HTTP {r.status_code} letter={letter} page={page}")
            break

        soup = BeautifulSoup(r.text, "html.parser")

        # Estrai totale dalla prima pagina
        if page == 0:
            h1 = soup.find("h1")
            if h1:
                m = re.search(r'(\d+)\s+risultati', h1.get_text())
                if m:
                    total_count = int(m.group(1))
                    print(f"    Lettera {letter}: {total_count} risultati")

        # Parse items
        items = soup.find_all("div", class_="itemDefunto")
        if not items:
            break

        page_saved = 0
        for item in items:
            if stop_event.is_set():
                break
            rec = _parse_item(item)
            if rec["cognome"] and rec["source_id"]:
                _save_record(rec)
                page_saved += 1
                saved += 1
                _progress["processed"] += 1
                _progress["current"] = f"{rec['cognome']} {rec['nome']}"[:30]

        total_saved = _count_saved()
        _progress["total_saved"] = total_saved

        if page % 10 == 0:
            print(f"    {letter} pag {page}: {page_saved} record | DB: {total_saved}")

        # Cerca link "Avanti" per paginazione
        next_link = soup.find("a", string=re.compile(r"avanti", re.I))
        if not next_link:
            break

        # Estrai page number dal href: /Search?query=a&page=1
        href = next_link.get("href", "")
        m = re.search(r'page=(\d+)', href)
        if m:
            page = int(m.group(1))
        else:
            page += 1

        time.sleep(REQUEST_DELAY)

    return saved


def scrape_all(resume: bool = True):
    """Scrape di tutti i caduti sardi per lettera A-Z."""
    stop_event.clear()
    _init_table()
    already = _count_saved() if resume else 0

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,*/*",
    })

    _progress.update({
        "status": "processing", "processed": already, "total": 20531,
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
        print(f"  Caduti Sardi - lettera {letter}...")

        saved = _search_letter(s, letter)
        total_saved = _count_saved()
        _progress["total_saved"] = total_saved
        print(f"    Lettera {letter}: {saved} record | Totale DB: {total_saved}")

        time.sleep(REQUEST_DELAY)

    _progress["status"] = "done"
    _progress["current"] = ""
    print(f"\n=== Caduti Sardi completato. Totale: {_count_saved()} ===")


def count_caduti_sardi() -> int:
    try:
        return _count_saved()
    except Exception:
        return 0
