"""Popola fonti_indice: lancia populate_massivo su tutti gli internati in un unico run.

La versione concorrente di populate_massivo gestisce internamente il resume.
"""
import subprocess
import sys
from database import get_conn

WORKERS = 6

def get_total_internati():
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM internati WHERE cognome IS NOT NULL AND cognome != ''"
    ).fetchone()[0]
    conn.close()
    return total

total = get_total_internati()
print(f"Total internati: {total}")
print(f"Lancio populate_massivo con {total} internati, {WORKERS} workers concorrenti...")
print()

ret = subprocess.run(
    [sys.executable, "populate_massivo.py", str(total), "0", str(WORKERS)],
    capture_output=False,
)
print(f"\nExit code: {ret.returncode}")
