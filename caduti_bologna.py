"""Scraper per Caduti Bolognesi - Museo del Risorgimento BO.
Fonte: http://badigit.comune.bologna.it/csg/ricerca.aspx
10.732 record caduti provincia di Bologna GG 1915-1918.
Paginazione via query string: num=50&start=X"""
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from database import get_conn

BASE = "http://badigit.comune.bologna.it/csg"
PAGE_SIZE = 10
REQUEST_DELAY = 1.5

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
        CREATE TABLE IF NOT EXISTS caduti_bologna (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            paternita TEXT,
            grado TEXT,
            reparto TEXT,
            luogo_nascita TEXT,
            anno_nascita TEXT,
            luogo_dimora TEXT,
            causa_morte TEXT,
            luogo_morte TEXT,
            data_morte TEXT,
            professione TEXT,
            stato_civile TEXT,
            decorazioni TEXT,
            scheda_completa TEXT,
            elaborato_il TEXT NOT NULL,
            UNIQUE(nome, paternita, data_morte)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bologna_nome ON caduti_bologna(nome)")
    conn.commit()
    conn.close()


def _parse_record(text: str) -> dict:
    """Parsea il testo di un record dalla tabella risultati."""
    text = text.strip()
    if not text:
        return None

    # Pattern: "COGNOME NOME, (decorazioni), di PADRE, grado nel reparto, nato a LUOGO nel ANNO, dimorante a LUOGO, morto per CAUSA il DATA. PROFESSIONE. STATO CIVILE."
    rec = {
        "nome": "", "paternita": "", "grado": "", "reparto": "",
        "luogo_nascita": "", "anno_nascita": "", "luogo_dimora": "",
        "causa_morte": "", "luogo_morte": "", "data_morte": "",
        "professione": "", "stato_civile": "", "decorazioni": "",
        "scheda_completa": text[:500],
        "elaborato_il": datetime.now().isoformat(),
    }

    # Estrai decorazioni (tra parentesi all'inizio)
    m = re.match(r"^([A-ZÀ-ÿ\s]+),\s*\(([^)]+)\),", text)
    if m:
        rec["nome"] = m.group(1).strip()
        rec["decorazioni"] = m.group(2).strip()
    else:
        # Senza decorazioni
        m = re.match(r"^([A-ZÀ-ÿ\s]+),\s*(?:di\s+|,)", text)
        if m:
            rec["nome"] = m.group(1).strip()
        else:
            # Fallback: prendi tutto fino alla prima virgola
            parts = text.split(",", 1)
            rec["nome"] = parts[0].strip()

    # Estrai paternità "di PADRE"
    m = re.search(r",\s*di\s+([^,]+),", text)
    if m:
        rec["paternita"] = m.group(1).strip()

    # Estrai grado e reparto "grado nel X reggimento Y"
    m = re.search(r",\s*([^,]+)\s+nel\s+([^,]+),", text)
    if m:
        rec["grado"] = m.group(1).strip()
        rec["reparto"] = m.group(2).strip()
    else:
        m = re.search(r",\s*([^,]+)\s+in\s+([^,]+),", text)
        if m:
            rec["grado"] = m.group(1).strip()
            rec["reparto"] = m.group(2).strip()

    # Estrai nascita "nato a LUOGO nel ANNO"
    m = re.search(r"nato\s+a\s+([^)]+?)\s+nel\s+(\d{4})", text)
    if m:
        rec["luogo_nascita"] = m.group(1).strip()
        rec["anno_nascita"] = m.group(2).strip()

    # Estrai dimora "dimorante a LUOGO"
    m = re.search(r"dimorante\s+a\s+([^,]+)", text)
    if m:
        rec["luogo_dimora"] = m.group(1).strip()

    # Estrai morte "morto per CAUSA ... il DATA"
    m = re.search(r"morto\s+(?:in\s+seguito\s+)?a\s+(?:ferite|malattia|gas|colera|annegamento|annegato|cause|infortunio)?\s*(?:[\w\s]+)?(?:il\s+)?(\d+\s+\w+\s+\d{4})", text)
    if m:
        rec["data_morte"] = m.group(1).strip()

    # Estrai causa morte
    m = re.search(r"morto\s+(?:in\s+seguito\s+)?(?:a|per)\s+([\w\s]+?)(?:\s+(?:il|nel|nell|,|\.))", text, re.I)
    if m:
        rec["causa_morte"] = m.group(1).strip()[:80]
    else:
        m = re.search(r"morto\s+per\s+([^,]+?)(?:\s+(?:il|nel|nell))", text)
        if m:
            rec["causa_morte"] = m.group(1).strip()[:80]

    # Estrai luogo morte
    m = re.search(r"morto\s+[\w\s]+(?:il\s+\d+\s+\w+\s+\d{4})?\s*(?:,|\.|$)", text)
    # Prova pattern alternativi per luogo morte
    m = re.search(r"(?:ospedaletto|ospedale|campo|cimitero|monte|fiume|Piave|Grappa|Sabotino|Podgora|Carso|Isonzo|Caporetto|Villa)\s+[\w\s]+", text)
    if m:
        rec["luogo_morte"] = m.group(0).strip()[:100]

    # Estrai professione (dopo il punto che segue la morte)
    m = re.search(r"\.\s*([^.]+?)\.\s*(?:Ammogliato|Celibe|Nubile|Sposato|$)", text)
    if m:
        rec["professione"] = m.group(1).strip()[:100]

    # Estrai stato civile
    m = re.search(r"(Ammogliato|Celibe|Nubile|Sposato)", text)
    if m:
        rec["stato_civile"] = m.group(1).strip()

    return rec


def _save_record(rec: dict):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO caduti_bologna
               (nome, paternita, grado, reparto, luogo_nascita, anno_nascita,
                luogo_dimora, causa_morte, luogo_morte, data_morte,
                professione, stato_civile, decorazioni, scheda_completa, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec["nome"], rec["paternita"], rec["grado"], rec["reparto"],
             rec["luogo_nascita"], rec["anno_nascita"], rec["luogo_dimora"],
             rec["causa_morte"], rec["luogo_morte"], rec["data_morte"],
             rec["professione"], rec["stato_civile"], rec["decorazioni"],
             rec["scheda_completa"], rec["elaborato_il"]),
        )
        conn.commit()
    except Exception as e:
        print(f"Errore save bologna: {e}")
    finally:
        conn.close()


def _count_saved() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as c FROM caduti_bologna").fetchone()
        conn.close()
        return row["c"]
    except Exception:
        conn.close()
        return 0


def scrape_all(resume: bool = True):
    """Scrape di tutti i caduti bolognesi paginando per pagina."""
    stop_event.clear()
    _init_table()
    already = _count_saved() if resume else 0

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    # Prima richiesta per ottenere il totale e numero pagine
    url = f"{BASE}/ricerca.aspx?Su=*&MD=&MA=&De=&Sp=&Fi=&num={PAGE_SIZE}&start=0"
    r = s.get(url, timeout=20)
    if r.status_code != 200:
        print(f"Errore HTTP {r.status_code}")
        _progress["status"] = "error"
        return

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text()

    # Estrai totale record "Record totali trovati: 10732"
    m = re.search(r"Record\s+totali\s+trovati:\s*(\d+)", text)
    total = int(m.group(1)) if m else 10732

    # Estrai totale pagine "di 1074"
    m2 = re.search(r"di\s*(\d+)", text)
    total_pages = int(m2.group(1)) if m2 else (total // PAGE_SIZE) + 1
    print(f"Totale record: {total} | Pagine: {total_pages}")

    _progress.update({
        "status": "processing", "processed": already, "total": total,
        "current": "", "total_saved": already
    })

    # start è il numero di pagina (0-indexed)
    start_page = (already // PAGE_SIZE) if resume else 0
    while start_page < total_pages:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return

        url = f"{BASE}/ricerca.aspx?Su=*&MD=&MA=&De=&Sp=&Fi=&num={PAGE_SIZE}&start={start_page}"
        try:
            r = s.get(url, timeout=20)
        except Exception as e:
            print(f"Errore richiesta page={start_page}: {e}")
            time.sleep(REQUEST_DELAY * 2)
            start_page += 1
            continue

        if r.status_code != 200:
            print(f"Errore HTTP {r.status_code} a page={start_page}")
            time.sleep(REQUEST_DELAY * 2)
            start_page += 1
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        # I record sono nella tabella con id="DG"
        table = soup.find("table", {"id": "DG"})
        page_records = 0
        if table:
            rows = table.find_all("tr")
            for row in rows:
                if stop_event.is_set():
                    break
                cells = row.find_all("td")
                if len(cells) >= 2:
                    rec_text = cells[0].get_text(strip=True)
                    if rec_text and len(rec_text) > 20 and "Record totali" not in rec_text:
                        try:
                            rec = _parse_record(rec_text)
                            if rec and rec["nome"]:
                                _save_record(rec)
                                page_records += 1
                                _progress["processed"] += 1
                                _progress["current"] = rec["nome"][:30]
                        except Exception as e:
                            print(f"  Errore parsing record: {e}")
        else:
            print(f"  Nessuna tabella DG a page={start_page}")

        saved = _count_saved()
        _progress["total_saved"] = saved
        if page_records > 0:
            print(f"  page={start_page}: {page_records} record | Totale DB: {saved}")

        start_page += 1
        time.sleep(REQUEST_DELAY)

    _progress["status"] = "done"
    _progress["current"] = ""
    print(f"\n=== Completato. Totale record: {_count_saved()} ===")


def count_caduti_bologna() -> int:
    try:
        return _count_saved()
    except Exception:
        return 0
