"""Scraper per CWGC - Commonwealth War Graves Commission.
Usa l'endpoint di ricerca con download CSV per paese.
URL: https://www.cwgc.org/find/find-war-dead/results?country=XX
1.7M caduti Commonwealth WW1 e WW2."""
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from database import get_conn
import csv
import io

BASE = "https://www.cwgc.org"
SEARCH_URL = f"{BASE}/find-records/find-war-dead/search-results/"
REQUEST_DELAY = 1.2

stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": "",
             "total_saved": 0}


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def get_progress() -> dict:
    return dict(_progress)


def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caduti_cwgc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cwgc_id TEXT UNIQUE,
            nome TEXT,
            cognome TEXT,
            initials TEXT,
            rank TEXT,
            service_number TEXT,
            service TEXT,
            regiment TEXT,
            nationality TEXT,
            data_morte TEXT,
            eta TEXT,
            cimitero TEXT,
            paese_cimitero TEXT,
            guerra TEXT,
            data_nascita TEXT,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cwgc_cognome ON caduti_cwgc(cognome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cwgc_nome ON caduti_cwgc(nome)")
    conn.commit()
    conn.close()


def _save_record(rec: dict):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO caduti_cwgc
               (cwgc_id, nome, cognome, initials, rank, service_number, service,
                regiment, nationality, data_morte, eta, cimitero, paese_cimitero,
                guerra, data_nascita, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec["cwgc_id"], rec["nome"], rec["cognome"], rec["initials"],
             rec["rank"], rec["service_number"], rec["service"], rec["regiment"],
             rec["nationality"], rec["data_morte"], rec["eta"], rec["cimitero"],
             rec["paese_cimitero"], rec["guerra"], rec["data_nascita"],
             rec["elaborato_il"]),
        )
        conn.commit()
    except Exception as e:
        print(f"Errore save cwgc: {e}")
    finally:
        conn.close()


def _count_saved() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as c FROM caduti_cwgc").fetchone()
        conn.close()
        return row["c"]
    except Exception:
        conn.close()
        return 0


def _parse_html_row(cells: list) -> dict:
    """Mappa celle HTML CWGC al nostro schema.
    Struttura tabella (5 colonne flat, no header):
      0: Nome Cognome + Rank + Service Number
      1: Reggimento + Servizio + Nazionalita
      2: Data morte + Eta
      3: Cimitero + Paese
      4: More details (ignorato)
    """
    texts = [c.get_text(" ", strip=True) for c in cells]
    while len(texts) < 5:
        texts.append("")

    link = cells[0].find("a") if cells else None
    cwgc_id = ""
    href = link.get("href", "") if link else ""
    m = re.search(r'/casualty-details/(\d+)/', href)
    if m:
        cwgc_id = m.group(1)

    # Col 0: "MARIO ROSSI Private Service Number: 12345"
    col0 = texts[0]
    sn_m = re.search(r'Service Number:\s*([\w\/]+)', col0, re.I)
    service_number = sn_m.group(1) if sn_m else ""
    name_rank = re.sub(r'Service Number:.*', '', col0, flags=re.I).strip()
    parts = name_rank.split()
    # Tenta di separare Cognome (maiuscolo) da rank (mixed case)
    cognome_parts, rank_parts = [], []
    switched = False
    for p in parts:
        if not switched and (p.isupper() or p.replace("'", "").replace("-", "").isupper()):
            cognome_parts.append(p)
        else:
            switched = True
            rank_parts.append(p)
    cognome = " ".join(cognome_parts)
    nome = ""
    rank = " ".join(rank_parts)

    # Col 1: "2nd Bn. Hampshire Regiment United Kingdom"
    col1 = texts[1]
    nationality_m = re.search(r'(Italian|United Kingdom|Australian|Canadian|New Zealand|South African|Indian|German|Austrian|Polish|Greek|Norwegian|Dutch|Belgian|American|French|Russian|Romanian|Bulgarian|Hungarian|Czechoslovakian|Brazilian|Portuguese|Finnish)\s*$', col1, re.I)
    nationality = nationality_m.group(1) if nationality_m else ""
    regiment = col1.replace(nationality, "").strip() if nationality else col1

    # Col 2: "Died 14 August 1943" o "Died 14 August 1943 32 years old"
    col2 = texts[2]
    date_m = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', col2)
    data_morte = date_m.group(1) if date_m else re.sub(r'Died\s*', '', col2).strip()
    age_m = re.search(r'(\d+)\s+years', col2, re.I)
    eta = age_m.group(1) if age_m else ""

    # Col 3: "ASSISI WAR CEMETERY II.G.7. Italy"
    col3 = texts[3]
    paese_m = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$', col3)
    paese_cimitero = paese_m.group(1) if paese_m else ""
    cimitero = col3.replace(paese_cimitero, "").strip() if paese_cimitero else col3

    return {
        "cwgc_id": cwgc_id,
        "nome": nome,
        "cognome": cognome,
        "initials": "",
        "rank": rank,
        "service_number": service_number,
        "service": "",
        "regiment": regiment,
        "nationality": nationality,
        "data_morte": data_morte,
        "eta": eta,
        "cimitero": cimitero,
        "paese_cimitero": paese_cimitero,
        "guerra": "World War 2",
        "data_nascita": "",
        "elaborato_il": datetime.now().isoformat(),
    }


def _scrape_italian_page(session: requests.Session, page: int, war: str) -> tuple:
    """Scarica una pagina di caduti italiani (ServedWith=Italian, nessun cognome).
    Restituisce (records, total_pages). war: '1'=WW1, '2'=WW2, ''=tutte.
    Questo e' l'approccio definitivo: il CWGC ha ~621 italiani WW2 / ~639 totali."""
    params = {
        "ServedWith": "Italian",
        "AgeOfDeath": "0",
        "Page": str(page),
    }
    if war:
        params["WarSelect"] = war
    return _fetch_and_parse(session, params, page)


def _scrape_surname_page(session: requests.Session, surname_prefix: str, page: int, served_with: str = "") -> tuple:
    """Scarica una pagina risultati per prefisso cognome (wildcard '*' per prefix match).
    Restituisce (records, total_pages). CWGC usa il parametro 'Page' (maiuscolo)."""
    params = {
        "Surname": surname_prefix,
        "SurnameExact": "false",
        "Forename": "",
        "WarSelect": "2",
        "AgeOfDeath": "0",
        "Page": str(page),
    }
    if served_with:
        params["ServedWith"] = served_with
    return _fetch_and_parse(session, params, page)


def _fetch_and_parse(session: requests.Session, params: dict, page: int) -> tuple:
    """Esegue la GET e fa il parsing di record + total_pages."""
    try:
        r = session.get(SEARCH_URL, params=params, timeout=30)
    except Exception as e:
        print(f"  Errore GET Page={page}: {e}")
        return [], 1

    if r.status_code != 200:
        return [], 1

    soup = BeautifulSoup(r.text, "html.parser")

    records = []
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")[1:]
        for row in rows:
            cells = row.find_all(["td", "th"])
            if cells and len(cells) >= 3:
                rec = _parse_html_row(cells)
                if rec["cognome"] or rec["nome"]:
                    records.append(rec)
    else:
        items = soup.find_all("li", class_=lambda c: c and "result" in str(c).lower())
        for item in items:
            cells_text = item.find_all(["span", "div", "p"])
            if cells_text:
                rec = _parse_html_row(cells_text)
                if rec["cognome"] or rec["nome"]:
                    records.append(rec)

    # Determina numero totale di pagine.
    # 1) Dal div paginazione "N pages"
    total_pages = 1
    pag_div = soup.find(class_=lambda c: c and "pagination" in str(c).lower())
    if pag_div:
        m = re.search(r'(\d+)\s+pages?', pag_div.get_text(" ", strip=True), re.I)
        if m:
            total_pages = int(m.group(1))
    # 2) Fallback: da "of N war dead" (10 risultati per pagina)
    if total_pages == 1:
        m2 = re.search(r'of\s+([\d,]+)\s+war\s+dead', r.text, re.I)
        if m2:
            total = int(m2.group(1).replace(",", ""))
            per_page = len(records) if records else 10
            total_pages = (total + per_page - 1) // per_page if per_page else 1
    # 3) Fallback: massimo Page=N nei link (case-insensitive)
    if total_pages == 1:
        page_nums = re.findall(r'[?&]Page=(\d+)', " ".join([a.get("href", "") for a in soup.find_all("a")]), re.I)
        if page_nums:
            total_pages = max(int(p) for p in page_nums)

    return records, total_pages


SURNAME_PREFIXES = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

EXPORT_URL = f"{BASE}/ExportCasualtySearch"
EXPORT_CAP = 1000          # limite record per export CSV senza login
PAGE_CAP = 1000            # limite pagine accessibili nella ricerca HTML
PAGE_SIZE = 100            # record per pagina con size=100

# Nazionalita (valore del select ServedWith sul form CWGC)
CWGC_NATIONALITIES = [
    "American", "Arab World", "Australian", "Austrian", "Belgian",
    "Brazilian", "Bulgarian", "Canadian", "Czechoslovakian", "Dutch",
    "Finnish", "German", "Greek", "Hungarian", "Indian", "Italian",
    "New Zealand", "Norwegian", "Polish", "Portuguese", "Romanian",
    "Russian", "South African", "United Kingdom",
]

# Intervallo anni coperti dal CWGC per guerra
WAR_YEARS = {
    "1": list(range(1914, 1922)),   # WW1: 1914-1921
    "2": list(range(1939, 1948)),   # WW2: 1939-1947
}

_STATE_FILE = Path(__file__).parent / "cwgc_progress.json"


def _load_completed() -> set:
    if _STATE_FILE.exists():
        try:
            import json as _json
            return set(_json.loads(_STATE_FILE.read_text()).get("completed", []))
        except Exception:
            return set()
    return set()


def _mark_done(key: str, completed: set):
    completed.add(key)
    try:
        import json as _json
        _STATE_FILE.write_text(_json.dumps({"completed": sorted(completed)}))
    except Exception:
        pass


def _parse_csv_row(row: dict) -> dict:
    """Mappa una riga del CSV Export CWGC al nostro schema (19 colonne)."""
    return {
        "cwgc_id": (row.get("Id") or "").strip(),
        "nome": (row.get("Forename") or "").strip(),
        "cognome": (row.get("Surname") or "").strip(),
        "initials": (row.get("Initials") or "").strip(),
        "rank": (row.get("Rank") or "").strip(),
        "service_number": (row.get("ServiceNumber") or "").strip().strip("'"),
        "service": (row.get("Unit") or "").strip(),
        "regiment": (row.get("Regiment") or "").strip(),
        "nationality": (row.get("CountryOfService") or "").strip(),
        "data_morte": (row.get("DateOfDeath") or "").strip(),
        "eta": (row.get("AgeAtDeath") or "").strip(),
        "cimitero": (row.get("Cemetery") or "").strip(),
        "paese_cimitero": (row.get("Burial") or "").strip(),
        "guerra": "",
        "data_nascita": "",
        "elaborato_il": datetime.now().isoformat(),
    }


def _date_params(year: int, month: int = None) -> dict:
    """Costruisce i parametri di range data per un anno o un mese specifico.
    Il filtro CWGC richiede giorno+mese+anno completi per From e To."""
    import calendar
    if month is None:
        return {
            "DateDeathFromYear": str(year), "DateDeathFromMonth": "1", "DateDeathFromDay": "1",
            "DateDeathToYear": str(year), "DateDeathToMonth": "12", "DateDeathToDay": "31",
        }
    last_day = calendar.monthrange(year, month)[1]
    return {
        "DateDeathFromYear": str(year), "DateDeathFromMonth": str(month), "DateDeathFromDay": "1",
        "DateDeathToYear": str(year), "DateDeathToMonth": str(month), "DateDeathToDay": str(last_day),
    }


def _search_total(session: requests.Session, params: dict) -> int:
    """Numero totale di risultati per una query (dal testo 'of N war dead')."""
    try:
        r = session.get(SEARCH_URL, params={**params, "Page": "1"}, timeout=30)
    except Exception:
        return -1
    m = re.search(r'of\s+([\d,]+)\s+war\s+dead', r.text, re.I)
    return int(m.group(1).replace(",", "")) if m else 0


def _export_csv(session: requests.Session, params: dict) -> int:
    """Scarica ed importa via Export CSV (max 1000 record). Ritorna record salvati."""
    import csv as _csv
    import io as _io
    try:
        r = session.get(EXPORT_URL, params=params, timeout=90)
    except Exception as e:
        print(f"  Errore export CSV: {e}")
        return 0
    if "csv" not in r.headers.get("Content-Type", "").lower():
        return 0
    saved = 0
    for row in _csv.DictReader(_io.StringIO(r.text)):
        rec = _parse_csv_row(row)
        if rec["cognome"] or rec["nome"]:
            _save_record(rec)
            saved += 1
    return saved


def _paginate_html(session: requests.Session, params: dict, label: str, start_page: int = 1, guerra: str = "") -> int:
    """Paginazione HTML diretta. Il CWGC supporta pagine illimitate (10 risultati/pagina).
    Ritorna record salvati. Retry robusto su errori di rete."""
    saved = 0
    page = start_page
    empty_streak = 0
    max_retries = 5
    while True:
        if stop_event.is_set():
            return saved
        success = False
        for attempt in range(max_retries):
            try:
                records, total_pages = _fetch_and_parse(session, {**params, "Page": str(page)}, page)
                success = True
                break
            except Exception as e:
                wait = REQUEST_DELAY * (2 ** attempt)
                print(f"    {label} p{page} retry {attempt+1}/{max_retries}: {e} (wait {wait:.0f}s)")
                time.sleep(wait)
        if not success:
            print(f"    {label} p{page}: SKIP dopo {max_retries} tentativi")
            page += 1
            empty_streak += 1
            if empty_streak >= 10:
                break
            continue
        if not records:
            empty_streak += 1
            if empty_streak >= 10:
                break
            time.sleep(REQUEST_DELAY)
            page += 1
            continue
        empty_streak = 0
        for rec in records:
            if guerra:
                rec["guerra"] = guerra
            _save_record(rec)
            saved += 1
        if page % 50 == 0:
            print(f"    {label} p{page}/{total_pages} +{saved} | DB={_count_saved():,}")
        if page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return saved


def _harvest_partition(session: requests.Session, params: dict, total: int, label: str) -> int:
    """Sceglie la strategia in base alla dimensione della partizione."""
    if total <= 0:
        return 0
    if total <= EXPORT_CAP:
        n = _export_csv(session, params)
        print(f"    {label}: export CSV +{n} (total={total})")
        return n
    if total <= PAGE_SIZE * PAGE_CAP:
        print(f"    {label}: paginazione size=100 (total={total:,})")
        return _paginate_html(session, params, label)
    # Troppo grande: sub-partizione mensile
    print(f"    {label}: SUB-PARTIZIONE mensile (total={total:,})")
    return -1  # segnale: richiede sub-partizione


def scrape_all(resume: bool = True, war: str = ""):
    """Scrape TUTTI i caduti CWGC di ogni nazionalita (WW1 + WW2, ~1.76M).
    Strategia:
      - partizione <= 1000  -> Export CSV (1 richiesta, veloce, dati puliti)
      - partizione > 1000   -> paginazione HTML diretta (illimitata, 10 rec/pag)
    Resume robusto: salta le partizioni gia completate (cwgc_progress.json).
    Dedup automatico via cwgc_id UNIQUE.

    war: '' = entrambe le guerre, '1' = solo WW1, '2' = solo WW2.
    """
    stop_event.clear()
    _init_table()

    completed = _load_completed() if resume else set()

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,*/*",
        "Referer": "https://www.cwgc.org/find/find-war-dead/",
    })

    war_codes = [war] if war else ["2", "1"]
    _progress.update({
        "status": "processing", "processed": 0,
        "total": len(CWGC_NATIONALITIES) * len(war_codes),
        "current": "", "total_saved": _count_saved()
    })

    for war_code in war_codes:
        war_label = "WW2" if war_code == "2" else "WW1"

        for nat in CWGC_NATIONALITIES:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return

            nat_key = f"{war_label}|{nat}"
            if nat_key in completed:
                print(f"{nat_key}: skip (completato)")
                continue

            base = {"ServedWith": nat, "WarSelect": war_code}
            nat_total = _search_total(s, base)
            _progress["current"] = nat_key
            _progress["processed"] += 1

            if nat_total <= 0:
                print(f"{nat_key}: 0 record")
                _mark_done(nat_key, completed)
                continue

            print(f"{nat_key}: {nat_total:,} record totali")

            # Se l'intera nazionalita/guerra sta sotto il cap export: 1 richiesta
            if nat_total <= EXPORT_CAP:
                n = _export_csv(s, base)
                print(f"  {nat_key}: export CSV +{n}")
                _mark_done(nat_key, completed)
                _progress["total_saved"] = _count_saved()
                time.sleep(REQUEST_DELAY)
                continue

            # Paginazione HTML diretta (illimitata)
            label = f"{nat} {war_label}"
            guerra_str = "World War 1" if war_code == "1" else "World War 2"
            print(f"  {nat_key}: paginazione diretta ({nat_total:,} record, ~{nat_total//10} pagine)")
            n = _paginate_html(s, base, label, guerra=guerra_str)
            print(f"  {nat_key}: +{n} salvati")
            _mark_done(nat_key, completed)
            _progress["total_saved"] = _count_saved()
            print(f"  {nat_key} COMPLETO | DB totale={_count_saved():,}")

    _progress["status"] = "done"
    _progress["current"] = ""
    print(f"\n=== CWGC completato. Totale record: {_count_saved():,} ===")


def count_caduti_cwgc() -> int:
    try:
        return _count_saved()
    except Exception:
        return 0
