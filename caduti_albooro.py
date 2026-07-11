"""Scraper per cadutigrandeguerra.it (Cimeetrincee) - Albo d'Oro caduti italiani GG.
Estrae tutti i caduti per ogni volume dell'Albo d'Oro (28 volumi + appendici).
Salva in DB nella tabella caduti_albooro."""
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from database import get_conn

BASE = "https://www.cadutigrandeguerra.it"
REQUEST_DELAY = 2.0

stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": "",
             "volume": "", "volume_records": 0, "total_saved": 0}


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def is_stop_requested() -> bool:
    return stop_event.is_set()


def get_progress() -> dict:
    return dict(_progress)


# Volumi dell'Albo d'Oro (dal select tAlbo)
VOLUMI = {
    "1": "Abruzzo e Molise - (Vol II)",
    "2": "Basilicata - (Vol III)",
    "3": "Calabria - (Vol IV)",
    "4": "Campania I - (Vol V)",
    "5": "Campania II - (Vol VI)",
    "6": "Emilia I - (Vol VII)",
    "7": "Emilia II - (Vol VIII)",
    "8": "Lazio e Sabina - (Vol I)",
    "9": "Liguria - (Vol IX)",
    "10": "Lombardia I - (Vol X)",
    "11": "Lombardia II - (Vol XI)",
    "12": "Lombardia III - (Vol XII)",
    "13": "Marche - (Vol XIII)",
    "14": "Piemonte I - (Vol XIV)",
    "15": "Piemonte II - (Vol XV)",
    "16": "Piemonte III - (Vol XVI)",
    "17": "Puglie I - (Vol XVII)",
    "18": "Puglie II - (Vol XVIII)",
    "19": "Sardegna - (Vol XIX)",
    "20": "Sicilia I - (Vol XX)",
    "21": "Sicilia II - (Vol XXI)",
    "22": "Sicilia III - (Vol XXII)",
    "23": "Toscana I - (Vol XXIII)",
    "24": "Toscana II - (Vol XXIV)",
    "25": "Trentino - (Vol ---)",
    "26": "Umbria - (Vol XXV)",
    "27": "Veneto I - (Vol XXVI-01)",
    "28": "Veneto I - (Vol XXVI bis)",
    "29": "Veneto I - (Vol XXVI)",
    "30": "Veneto II - (Vol XXVII bis)",
    "31": "Veneto II - (Vol XXVII)",
    "32": "Veneto III - (Vol XXVIII bis)",
    "33": "Veneto III - (Vol XXVIII)",
    "90": "Caduti NON in Albo d'Oro",
    "35": "Caduti NON in Albo d'Oro-2",
}


def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caduti_albooro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            volume_id TEXT,
            volume_name TEXT,
            nominativo TEXT,
            paternita TEXT,
            classe TEXT,
            comune_attuale TEXT,
            grado TEXT,
            reparto TEXT,
            anno_morte TEXT,
            luogo_morte TEXT,
            causa_morte TEXT,
            detail_url TEXT,
            img_url TEXT,
            elaborato_il TEXT NOT NULL,
            UNIQUE(volume_id, nominativo, paternita)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_albooro_nominativo ON caduti_albooro(nominativo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_albooro_volume ON caduti_albooro(volume_id)")
    conn.commit()
    conn.close()


def _parse_row(row_html, volume_id: str, volume_name: str) -> dict:
    """Estrae un record da una riga <tr> della tabella risultati."""
    cells = row_html.find_all("td")
    if len(cells) < 8:
        return None

    nominativo_full = cells[0].text.strip()
    # Separa nominativo e paternita ("COGNOME NOME DI PADRE")
    m = re.match(r"^(.+?)\s+DI\s+(.+)$", nominativo_full)
    if m:
        nominativo = m.group(1).strip()
        paternita = m.group(2).strip()
    else:
        nominativo = nominativo_full
        paternita = ""

    detail_url = ""
    img_url = ""
    for c in cells:
        for a in c.find_all("a"):
            href = a.get("href", "")
            if "DettagliNominativi" in href:
                detail_url = href
            elif "ShowImg" in href:
                img_url = href

    return {
        "source_id": detail_url.split("id=")[-1].split("%")[0] if detail_url else "",
        "volume_id": volume_id,
        "volume_name": volume_name,
        "nominativo": nominativo,
        "paternita": paternita,
        "classe": cells[1].text.strip(),
        "comune_attuale": cells[2].text.strip(),
        "grado": cells[3].text.strip(),
        "reparto": cells[4].text.strip(),
        "anno_morte": cells[5].text.strip(),
        "luogo_morte": cells[6].text.strip(),
        "causa_morte": cells[7].text.strip(),
        "detail_url": detail_url,
        "img_url": img_url,
        "elaborato_il": datetime.now().isoformat(),
    }


def _save_record(rec: dict):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO caduti_albooro
               (source_id, volume_id, volume_name, nominativo, paternita, classe,
                comune_attuale, grado, reparto, anno_morte, luogo_morte, causa_morte,
                detail_url, img_url, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec["source_id"], rec["volume_id"], rec["volume_name"],
             rec["nominativo"], rec["paternita"], rec["classe"],
             rec["comune_attuale"], rec["grado"], rec["reparto"],
             rec["anno_morte"], rec["luogo_morte"], rec["causa_morte"],
             rec["detail_url"], rec["img_url"], rec["elaborato_il"]),
        )
        conn.commit()
    except Exception as e:
        print(f"Errore save: {e}")
    finally:
        conn.close()


def _count_saved() -> int:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as c FROM caduti_albooro").fetchone()
    conn.close()
    return row["c"]


def _volume_has_records(volume_id: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM caduti_albooro WHERE volume_id = ?", (volume_id,)
    ).fetchone()
    conn.close()
    return row["c"]


LETTERS = [chr(c) for c in range(ord('A'), ord('Z') + 1)]


def _volume_letter_has_records(volume_id: str, letter: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM caduti_albooro WHERE volume_id = ? AND nominativo LIKE ?",
        (volume_id, letter + "%")
    ).fetchone()
    conn.close()
    return row["c"]


def scrape_volume(volume_id: str, volume_name: str, resume: bool = True) -> int:
    """Scrape di un singolo volume dell'Albo d'Oro, paginando per lettera."""
    total_saved = 0

    for letter in LETTERS:
        if stop_event.is_set():
            break
        if resume and _volume_letter_has_records(volume_id, letter) > 0:
            print(f"  Volume {volume_id} lettera {letter}: gia' scaricata, skip")
            continue

        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        r = s.get(f"{BASE}/CercaNome.aspx", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        def gv(soup, name):
            el = soup.find("input", {"name": name})
            return el.get("value", "") if el else ""

        data = {
            "__VIEWSTATE": gv(soup, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": gv(soup, "__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": gv(soup, "__EVENTVALIDATION"),
            "tAlbo": volume_id,
            "tNome": letter,
            "btCerca": "CERCA",
        }

        try:
            r2 = s.post(f"{BASE}/CercaNome.aspx", data=data, timeout=30)
        except Exception as e:
            print(f"  Errore richiesta vol={volume_id} letter={letter}: {e}")
            time.sleep(REQUEST_DELAY)
            continue

        if r2.status_code != 200:
            print(f"  Errore HTTP {r2.status_code} per vol={volume_id} letter={letter}")
            time.sleep(REQUEST_DELAY)
            continue

        soup2 = BeautifulSoup(r2.text, "html.parser")
        table = soup2.find("table", {"id": "GridView2"})
        if not table:
            tables = soup2.find_all("table")
            table = tables[1] if len(tables) > 1 else None
        if not table:
            print(f"  Nessuna tabella per vol={volume_id} letter={letter}")
            time.sleep(REQUEST_DELAY)
            continue

        rows = table.find_all("tr")[1:]
        letter_saved = 0
        for row in rows:
            if stop_event.is_set():
                break
            rec = _parse_row(row, volume_id, volume_name)
            if rec:
                _save_record(rec)
                letter_saved += 1
                total_saved += 1
                _progress["processed"] += 1
                _progress["current"] = rec["nominativo"][:30]

        print(f"  Vol={volume_id} letter={letter}: {letter_saved} record")
        time.sleep(REQUEST_DELAY)

    return total_saved


def scrape_all(resume: bool = True):
    """Scrape di tutti i volumi dell'Albo d'Oro, paginando per lettera."""
    stop_event.clear()
    _init_table()
    total = len(VOLUMI) * len(LETTERS)
    _progress.update({
        "status": "processing", "processed": 0, "total": total,
        "current": "", "volume": "", "volume_records": 0,
        "total_saved": _count_saved()
    })

    for vid, vname in VOLUMI.items():
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return

        _progress["volume"] = vname
        _progress["volume_records"] = 0
        print(f"\n=== Volume {vid}: {vname} ===")

        saved = scrape_volume(vid, vname, resume=resume)
        _progress["volume_records"] = saved
        _progress["total_saved"] = _count_saved()
        print(f"  Salvati: {saved} | Totale DB: {_progress['total_saved']}")

    _progress["status"] = "done"
    _progress["current"] = ""
    print(f"\n=== Completato. Totale record: {_count_saved()} ===")


def count_caduti_albooro() -> int:
    try:
        return _count_saved()
    except Exception:
        return 0


def get_volumes_summary() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT volume_id, volume_name, COUNT(*) as n
               FROM caduti_albooro GROUP BY volume_id ORDER BY volume_id"""
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []
