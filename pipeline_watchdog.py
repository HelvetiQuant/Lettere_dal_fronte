"""Watchdog per pipeline di indicizzazione massiva.

Controlla ogni 5 minuti:
  1. Server uvicorn attivo su :8000
  2. Pipeline in esecuzione (se era stata avviata)
  3. Log errori recenti

In caso di problemi:
  - Riavvia uvicorn se down
  - Riavvia pipeline se bloccata o in errore
  - Logga tutto su pipeline_watchdog.log

Avvio: python pipeline_watchdog.py
       python pipeline_watchdog.py --mode parallel --limit 500
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

LOG_FILE   = Path(__file__).parent / "pipeline_watchdog.log"
SERVER_URL = "http://127.0.0.1:8000"
CHECK_INTERVAL = 300   # secondi tra i check (5 minuti)
MAX_STUCK_SEC  = 600   # pipeline considerata bloccata se running ma saved non cresce dopo 10min
UVICORN_CMD    = [sys.executable, "-m", "uvicorn", "app:app",
                  "--host", "127.0.0.1", "--port", "8000", "--reload"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watchdog")

_uvicorn_proc = None        # processo uvicorn gestito dal watchdog
_pipeline_mode = "parallel" # modalità pipeline da (ri)avviare
_pipeline_limit = None      # limite soldati per AI
_last_saved = 0             # ultima lettura fonti salvate
_last_saved_at = 0.0        # timestamp ultima variazione


# ─── Utility ──────────────────────────────────────────────────────────────────

def _server_alive() -> bool:
    try:
        r = requests.get(f"{SERVER_URL}/api/status", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _pipeline_status() -> dict:
    try:
        r = requests.get(f"{SERVER_URL}/api/mass-index/status", timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def _start_server():
    global _uvicorn_proc
    log.info("Avvio uvicorn...")
    cwd = str(Path(__file__).parent)
    _uvicorn_proc = subprocess.Popen(
        UVICORN_CMD, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(6)
    if _server_alive():
        log.info("Server avviato OK (pid=%d)", _uvicorn_proc.pid)
        return True
    log.error("Server non risponde dopo avvio")
    return False


def _start_pipeline():
    """Avvia la pipeline appropriata via API REST."""
    global _last_saved, _last_saved_at
    time.sleep(3)
    if _pipeline_mode == "parallel":
        body = {"limit": _pipeline_limit} if _pipeline_limit else {}
        url  = f"{SERVER_URL}/api/mass-index/start-parallel"
    else:
        body = {"mode": _pipeline_mode}
        if _pipeline_limit:
            body["limit"] = _pipeline_limit
        url = f"{SERVER_URL}/api/mass-index/start"
    try:
        r = requests.post(url, json=body, timeout=10)
        data = r.json()
        if data.get("ok"):
            log.info("Pipeline '%s' avviata", _pipeline_mode)
            _last_saved    = 0
            _last_saved_at = time.time()
            return True
        log.warning("Pipeline non avviata: %s", data.get("error","?"))
    except Exception as e:
        log.error("Errore avvio pipeline: %s", e)
    return False


def _check_stuck() -> bool:
    """Ritorna True se pipeline è running ma saved non cresce da MAX_STUCK_SEC."""
    global _last_saved, _last_saved_at
    st = _pipeline_status()
    pipe = st.get("pipeline", {})
    if not pipe.get("running"):
        return False
    saved_now = st.get("fonti_indice", {}).get("total", 0)
    if saved_now > _last_saved:
        _last_saved    = saved_now
        _last_saved_at = time.time()
        return False
    elapsed = time.time() - _last_saved_at
    if elapsed > MAX_STUCK_SEC:
        log.warning("Pipeline bloccata: saved=%d invariato da %.0fs", saved_now, elapsed)
        return True
    return False


# ─── Loop principale ──────────────────────────────────────────────────────────

def run_watchdog(pipeline_mode: str, pipeline_limit: int = None,
                 start_pipeline_now: bool = True):
    global _pipeline_mode, _pipeline_limit, _last_saved_at

    _pipeline_mode  = pipeline_mode
    _pipeline_limit = pipeline_limit
    _last_saved_at  = time.time()

    log.info("=== WATCHDOG AVVIATO (check ogni %ds) ===", CHECK_INTERVAL)
    log.info("Pipeline mode: %s | limit: %s", pipeline_mode, pipeline_limit)

    # Avvio iniziale server se non attivo
    if not _server_alive():
        log.warning("Server non attivo — avvio uvicorn")
        if not _start_server():
            log.error("Impossibile avviare il server — uscita")
            sys.exit(1)

    # Avvio pipeline iniziale
    if start_pipeline_now:
        st = _pipeline_status()
        if st.get("pipeline", {}).get("running"):
            log.info("Pipeline già in esecuzione — non riavvio")
        else:
            _start_pipeline()

    check_n = 0
    while True:
        time.sleep(CHECK_INTERVAL)
        check_n += 1
        now = datetime.now().strftime("%H:%M:%S")
        log.info("--- CHECK #%d @ %s ---", check_n, now)

        # 1. Server alive?
        if not _server_alive():
            log.error("Server DOWN — riavvio uvicorn")
            if _uvicorn_proc:
                try:
                    _uvicorn_proc.terminate()
                except Exception:
                    pass
            if _start_server():
                time.sleep(5)
                _start_pipeline()
            continue

        # 2. Pipeline status
        st    = _pipeline_status()
        pipe  = st.get("pipeline", {})
        fi    = st.get("fonti_indice", {})
        total = fi.get("total", 0)
        url_ok= fi.get("con_url", 0)

        log.info("Server: OK | Pipeline running=%s | fonti_indice=%d (con_url=%d)",
                 pipe.get("running"), total, url_ok)

        # 3. Errore in pipeline?
        if pipe.get("error"):
            log.error("Pipeline in errore: %s — riavvio", pipe["error"])
            _start_pipeline()
            continue

        # 4. Pipeline bloccata?
        if _check_stuck():
            log.warning("Pipeline bloccata — riavvio forzato")
            _start_pipeline()
            continue

        # 5. Pipeline terminata senza essere in running → riavvia se vuole girare
        if not pipe.get("running") and pipe.get("mode"):
            log.info("Pipeline terminata (mode=%s saved=%d) — non riavvio automatico",
                     pipe.get("mode"), fi.get("total", 0))

        # 6. Scrivi snapshot su file
        snapshot = {
            "check": check_n,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "server": "ok",
            "pipeline": pipe,
            "fonti_indice": fi,
        }
        snap_path = Path(__file__).parent / "watchdog_snapshot.json"
        try:
            snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except Exception:
            pass


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watchdog pipeline indicizzazione")
    parser.add_argument("--mode", default="parallel",
                        choices=["parallel","soldati","reparti","eventi","luoghi","all"],
                        help="Modalità pipeline da avviare/monitorare")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limite soldati per AI (default: tutti)")
    parser.add_argument("--no-start", action="store_true",
                        help="Non avviare la pipeline subito (solo monitor)")
    args = parser.parse_args()

    run_watchdog(
        pipeline_mode=args.mode,
        pipeline_limit=args.limit,
        start_pipeline_now=not args.no_start,
    )
