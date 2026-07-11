"""Backup automatico del database SQLite.
Esegue backup compresso in ~/Documents/DB_Backup/ ogni giorno alle 18:00.
Usa SQLite Online Backup API (safe con DB in uso) + compressione gzip.
"""
import sqlite3
import gzip
import shutil
import os
import time
import schedule
from datetime import datetime
from pathlib import Path
from database import DB_PATH

BACKUP_DIR = Path.home() / "Documents" / "DB_Backup"


def backup_db():
    """Esegue backup del DB usando SQLite Online Backup API (safe con connessioni attive)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"imi_internati_{timestamp}.db"
    gzip_path = BACKUP_DIR / f"imi_internati_{timestamp}.db.gz"

    print(f"[{datetime.now().isoformat()}] Inizio backup -> {backup_path}")

    try:
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(str(backup_path))
        src.backup(dst)
        dst.close()
        src.close()

        size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"  Backup creato: {backup_path.name} ({size_mb:.1f} MB)")

        with open(backup_path, "rb") as f_in:
            with gzip.open(gzip_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        gz_mb = gzip_path.stat().st_size / (1024 * 1024)
        print(f"  Compresso: {gzip_path.name} ({gz_mb:.1f} MB)")

        backup_path.unlink()

        _cleanup_old_backups()

        print(f"  Backup completato.")
        return True
    except Exception as e:
        print(f"  ERRORE backup: {e}")
        return False


def _cleanup_old_backups(max_days: int = 30):
    """Elimina backup piu' vecchi di max_days giorni."""
    cutoff = time.time() - (max_days * 86400)
    removed = 0
    for f in BACKUP_DIR.glob("imi_internati_*.db.gz"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    if removed:
        print(f"  Eliminati {removed} backup vecchi (> {max_days} giorni)")


def run_scheduler():
    """Avvia scheduler: backup ogni giorno alle 18:00."""
    print(f"Backup scheduler avviato. Directory: {BACKUP_DIR}")
    print(f"Prossimo backup: ogni giorno alle 18:00")

    schedule.every().day.at("18:00").do(backup_db)

    backup_db()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv or "/once" in sys.argv:
        backup_db()
    else:
        run_scheduler()
