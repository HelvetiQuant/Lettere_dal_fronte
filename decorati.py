"""Pipeline per gli Albi della Memoria di ISTORECO Reggio Emilia
(https://www.albimemoria-istoreco.re.it). Scarica i nominativi dei decorati/caduti
di un albo tramite la sua API JSON e li salva nel database per arricchire le
ricerche incrociate. Nessun dato simulato: tutti i dati provengono dall'API ufficiale."""
import json
import threading
import time

import requests
import urllib3

from database import save_decorato, decorato_exists, count_decorati

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ORIGIN = "https://www.albimemoria-istoreco.re.it"
API = ORIGIN + "/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
}
PAGE_SIZE = 100
REQUEST_DELAY = 0.25

# Albo predefinito richiesto: "Decorati di tutte le guerre"
DEFAULT_ALBO = "e84b6a5a-5f21-4216-a148-c1bbe6206adb"

stop_event = threading.Event()
_progress = {"status": "idle", "albo": None, "processed": 0, "total": 0}


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def is_stop_requested() -> bool:
    return stop_event.is_set()


def get_progress() -> dict:
    return dict(_progress)


def _get(path: str):
    r = requests.get(API + path, headers=HEADERS, timeout=60, verify=False)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict):
    r = requests.post(API + path, headers=HEADERS, data=json.dumps(body), timeout=60, verify=False)
    r.raise_for_status()
    return r.json()


def get_albo_info(albo_id: str) -> dict:
    return _get(f"/Site/Albo/{albo_id}")


def fetch_page(albo_id: str, page: int, page_size: int = PAGE_SIZE) -> dict:
    return _post(f"/Site/cercacaduti?PageNumber={page}&PageSize={page_size}", {"alboId": albo_id})


def fetch_detail(caduto_id: str) -> dict:
    return _get(f"/Site/Caduto/{caduto_id}")


def _year(v):
    if not v:
        return None
    try:
        return int(str(v)[:4])
    except (ValueError, TypeError):
        return None


def _map_detail(d: dict, albo_id: str) -> dict:
    sid = d.get("id")
    return {
        "source_id": sid,
        "albo_id": albo_id,
        "albo_nome": (d.get("albiNomeImmagineUrl") or {}).get("nomeAlbo"),
        "cognome": d.get("cognome"),
        "nome": d.get("nome"),
        "comune_nascita": d.get("comuneNascita"),
        "comune_residenza": d.get("comuneResidenza"),
        "data_nascita": d.get("dataNascita"),
        "data_morte": d.get("dataMorte"),
        "anno_nascita": d.get("annoNascita") or _year(d.get("dataNascita")),
        "anno_morte": d.get("annoMorte") or _year(d.get("dataMorte")),
        "guerra": d.get("guerra"),
        "grado": d.get("grado"),
        "corpo_militare": d.get("corpoMilitare"),
        "reparto": d.get("reparto"),
        "decorazione": d.get("decorazione"),
        "motivazione": d.get("motivazione"),
        "causa_morte": d.get("causaMorte"),
        "luogo_morte": d.get("luogoMorte"),
        "luogo_cattura": d.get("luogoCattura"),
        "luogo_internamento": d.get("luogoInternamento"),
        "matricola": d.get("matricola"),
        "professione": d.get("professione"),
        "note": d.get("note"),
        "url_scheda": f"{ORIGIN}/albidellamemoria/nominativo/{sid}",
        "foto_urls": ", ".join(d.get("fotoUrls") or []),
        "raw_json": json.dumps(d, ensure_ascii=False),
    }


def scrape_albo(albo_id: str = DEFAULT_ALBO, resume: bool = True,
                fetch_details: bool = True, delay: float = REQUEST_DELAY) -> dict:
    """Scarica tutti i nominativi di un albo e li salva nel DB."""
    info = get_albo_info(albo_id)
    albo_nome = info.get("nome")
    first = fetch_page(albo_id, 1)
    total = first.get("totalCount", 0)
    total_pages = first.get("totalPages", 0)
    _progress.update({"status": "processing", "albo": albo_nome, "processed": 0, "total": total})
    print(f"  [Decorati] Albo '{albo_nome}': {total} nominativi, {total_pages} pagine")

    saved = 0
    processed = 0
    for page in range(1, total_pages + 1):
        if stop_event.is_set():
            _progress["status"] = "stopped"
            print(f"  [Decorati] Interrotto a pagina {page}")
            break
        data = first if page == 1 else fetch_page(albo_id, page)
        for item in data.get("listCaduti", []):
            if stop_event.is_set():
                break
            sid = item.get("id")
            processed += 1
            _progress["processed"] = processed
            if resume and decorato_exists(sid):
                continue
            try:
                if fetch_details:
                    detail = fetch_detail(sid)
                    row = _map_detail(detail, albo_id)
                    if delay:
                        time.sleep(delay)
                else:
                    row = {
                        "source_id": sid, "albo_id": albo_id, "albo_nome": albo_nome,
                        "cognome": item.get("cognome"), "nome": item.get("nome"),
                        "comune_nascita": item.get("comuneNascita"),
                        "comune_residenza": item.get("comuneResidenza"),
                        "data_nascita": item.get("dataNascita"), "data_morte": item.get("dataMorte"),
                        "anno_nascita": item.get("annoNascita"), "anno_morte": item.get("annoMorte"),
                        "url_scheda": f"{ORIGIN}/albidellamemoria/nominativo/{sid}",
                        "raw_json": json.dumps(item, ensure_ascii=False),
                    }
                save_decorato(row)
                saved += 1
            except Exception as e:
                print(f"    [ERROR] decorato {sid}: {e}")
        print(f"    [Decorati] Pagina {page}/{total_pages} - salvati {saved} (tot DB: {count_decorati()})")

    if not stop_event.is_set():
        _progress["status"] = "done"
    return {"albo": albo_nome, "total": total, "saved": saved, "in_db": count_decorati()}
