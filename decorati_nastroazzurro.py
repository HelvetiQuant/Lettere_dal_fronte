"""Scraper per l'archivio dei Decorati al Valor Militare dell'Istituto del Nastro Azzurro.
Fonte: http://decoratialvalormilitare.istitutonastroazzurro.org/
Endpoint AJAX: POST ./XMLHttp/getDatas.php
~375.000 decorati dal 1833 ad oggi.

Risposta: <ul class="user_list"><li><a onClick="getDatas(ID)"><b>COGNOME</b> NOME <i>(ANNO DECORAZIONE)</i></a></li>...
"""
import re
import time
import threading
import requests
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from database import get_conn

BASE_URL = "http://decoratialvalormilitare.istitutonastroazzurro.org"
SEARCH_URL = f"{BASE_URL}/XMLHttp/getDatas.php"
REQUEST_DELAY = 2.0
TIMEOUT = 60

ARMI = {
    1: "Esercito",
    2: "Marina",
    3: "Aeronautica",
    4: "Carabinieri",
    5: "Finanza",
}

stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": "", "total_saved": 0}

LI_PATTERN = re.compile(
    r'getDatas\((\d+)\).*?<b>(.*?)</b>\s*(.*?)\s*<i>\((.*?)\)</i>',
    re.DOTALL
)


def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decorati_nastroazzurro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT UNIQUE,
            id_arma INTEGER,
            arma TEXT,
            cognome TEXT,
            nome TEXT,
            anno_decorazione TEXT,
            tipo_decorazione TEXT,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_na_cognome ON decorati_nastroazzurro(cognome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_na_arma ON decorati_nastroazzurro(id_arma)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_na_decorazione ON decorati_nastroazzurro(tipo_decorazione)")
    conn.commit()
    conn.close()
    print("  Tabella decorati_nastroazzurro pronta")


def _count_saved() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM decorati_nastroazzurro").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def _parse_results(html: str, id_arma: int, arma_name: str) -> list:
    records = []
    for m in LI_PATTERN.finditer(html):
        source_id = m.group(1)
        cognome = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        nome = re.sub(r'<[^>]+>', '', m.group(3)).strip()
        decorazione_info = m.group(4).strip()
        
        anno_dec = None
        tipo_dec = decorazione_info
        parts = decorazione_info.split(None, 1)
        if parts and parts[0].isdigit():
            anno_dec = parts[0]
            tipo_dec = parts[1] if len(parts) > 1 else decorazione_info
        
        if nome in ('nd', 'ND'):
            nome = None
        
        records.append({
            "source_id": source_id,
            "id_arma": id_arma,
            "arma": arma_name,
            "cognome": cognome,
            "nome": nome,
            "anno_decorazione": anno_dec,
            "tipo_decorazione": tipo_dec,
            "elaborato_il": datetime.now().isoformat(),
        })
    return records


def _save_records(records: list) -> int:
    if not records:
        return 0
    conn = get_conn()
    saved = 0
    try:
        for rec in records:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO decorati_nastroazzurro
                    (source_id, id_arma, arma, cognome, nome, anno_decorazione, tipo_decorazione, elaborato_il)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    rec["source_id"], rec["id_arma"], rec["arma"],
                    rec["cognome"], rec["nome"], rec["anno_decorazione"],
                    rec["tipo_decorazione"], rec["elaborato_il"]
                ))
                if conn.total_changes:
                    saved += 1
            except Exception:
                pass
        conn.commit()
    except Exception as e:
        print(f"  Errore save: {e}")
    finally:
        conn.close()
    return saved


def _search(id_arma: int, cognome: str) -> str:
    params = {
        "all_arma": "0",
        "id_arma": str(id_arma),
        "nome": "",
        "cognome": cognome,
        "anno_nascita": "",
        "anno_decorazione": "",
        "tipo_decorazione": "",
        "anno_volume": "",
    }
    try:
        resp = requests.post(SEARCH_URL, data=params, timeout=TIMEOUT,
                           headers={"Content-Type": "application/x-www-form-urlencoded",
                                   "User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"  Errore ricerca: {e}")
    return ""


def get_progress() -> dict:
    return dict(_progress)


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def scrape_all():
    stop_event.clear()
    _init_table()
    
    import string
    letters = list(string.ascii_uppercase) + ["%"]
    total_combos = len(letters) * len(ARMI)
    already = _count_saved()
    
    _progress.update({
        "status": "processing", "processed": 0,
        "total": total_combos, "current": "", "total_saved": already
    })
    
    print(f"Nastro Azzurro: {total_combos} combinazioni, {already} record gia' presenti")
    
    for id_arma, arma_name in ARMI.items():
        for letter in letters:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            
            label = f"{arma_name} - {letter}"
            _progress["current"] = label
            
            html = _search(id_arma, letter)
            records = _parse_results(html, id_arma, arma_name)
            saved = _save_records(records)
            
            total_now = _count_saved()
            _progress["processed"] += 1
            _progress["total_saved"] = total_now
            
            print(f"  {label}: {len(records)} trovati, {saved} salvati (DB: {total_now:,})")
            
            time.sleep(REQUEST_DELAY)
    
    _progress["status"] = "done"
    _progress["current"] = ""
    total = _count_saved()
    _progress["total_saved"] = total
    print(f"\n=== Nastro Azzurro completato. Totale: {total:,} record ===")


def count_decorati_na() -> int:
    return _count_saved()
