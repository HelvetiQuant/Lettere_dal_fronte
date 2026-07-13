"""Watchdog per populate_loop.py — controlla ogni 10 minuti e riavvia se crashato.

Logica:
- Ogni CHECK_INTERVAL secondi legge il contatore processed da populate_progress
- Se il contatore non è aumentato rispetto all'ultima lettura → il processo è bloccato
- Se il PID del processo figlio non esiste più → è crashato
- In entrambi i casi riavvia populate_massivo dal punto dove si era fermato
- Auto-termina quando tutti gli internati sono processati
"""
import subprocess
import sys
import time
import logging
from datetime import datetime
from database import get_conn

CHECK_INTERVAL = 300   # 5 minuti
STALL_CYCLES   = 3     # riavvia dopo 3 cicli senza progresso (~15 min)
WORKERS        = 2     # delay adattivo: 2 sessioni parallele

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watchdog")


def get_total():
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM internati WHERE cognome IS NOT NULL AND cognome != ''"
    ).fetchone()[0]
    conn.close()
    return total


def get_processed():
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM populate_progress WHERE status='done'"
        ).fetchone()[0]
    except Exception:
        n = 0
    conn.close()
    return n


def launch_populate(total):
    log.info("Avvio populate_massivo (total=%d, workers=%d)", total, WORKERS)
    proc = subprocess.Popen(
        [sys.executable, "populate_massivo.py", str(total), "0", str(WORKERS)],
        cwd=".",
    )
    return proc


def main():
    total = get_total()
    log.info("Internati totali: %d", total)

    proc = launch_populate(total)
    last_processed = get_processed()
    stall_count = 0

    while True:
        time.sleep(CHECK_INTERVAL)

        current_processed = get_processed()
        log.info("Processati: %d / %d", current_processed, total)

        # Completato
        if current_processed >= total:
            log.info("COMPLETATO — tutti gli internati processati.")
            if proc and proc.poll() is None:
                proc.terminate()
            break

        # Controlla se il processo è ancora vivo
        alive = proc is not None and proc.poll() is None

        # Controlla progresso
        if current_processed <= last_processed:
            stall_count += 1
            log.warning("Nessun progresso da %d cicli (stall_count=%d)", stall_count, stall_count)
        else:
            stall_count = 0

        last_processed = current_processed

        # Riavvia se crashato o stallo prolungato
        if not alive or stall_count >= STALL_CYCLES:
            if not alive:
                rc = proc.returncode if proc else "N/A"
                log.warning("Processo terminato (exit=%s) — riavvio", rc)
            else:
                log.warning("Stallo rilevato (%d cicli) — riavvio", stall_count)
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()

            stall_count = 0
            proc = launch_populate(total)

    log.info("Watchdog terminato.")


if __name__ == "__main__":
    main()
