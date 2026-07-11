"""Importer per la base dei Morts pour la France (1ª Guerra Mondiale) - Mémoire des Hommes.
Fonte: data.gouv.fr - CSV open data (~1,4M record).
Due file: base validata + annotations (indexazione collaborativa).
Delimitatore: virgola. Encoding: UTF-8.
"""
import csv
import io
import os
import sys
import time
import threading
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from database import get_conn

URLS = {
    "base": "https://www.data.gouv.fr/api/1/datasets/r/7fb4e959-df14-4a28-b7fc-f7b6c9cae93b",
    "annotations": "https://www.data.gouv.fr/api/1/datasets/r/e9f5409a-589a-478c-99da-6aea9b12c70a",
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data_mdh")
CHUNK_SIZE = 1024 * 1024  # 1MB

stop_event = threading.Event()
_progress = {"status": "idle", "phase": "", "downloaded": 0, "imported": 0, "total_saved": 0}


def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caduti_francia_ww1 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            images_href TEXT,
            nom TEXT,
            naissance TEXT,
            grade TEXT,
            unite TEXT,
            lieu_naissance TEXT,
            bureau_recrutement TEXT,
            classe TEXT,
            matricule TEXT,
            date_deces TEXT,
            lieu_deces TEXT,
            lieu_deces_suite TEXT,
            departement_deces TEXT,
            pays_deces TEXT,
            lieu_transcription TEXT,
            departement_transcription TEXT,
            pays_transcription TEXT,
            source TEXT,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_nom ON caduti_francia_ww1(nom)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_unite ON caduti_francia_ww1(unite)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_deces ON caduti_francia_ww1(date_deces)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fr_lieu ON caduti_francia_ww1(lieu_deces)")
    conn.commit()
    conn.close()
    print("  Tabella caduti_francia_ww1 pronta")


def _count_saved() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM caduti_francia_ww1").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def count_caduti_francia_ww1() -> int:
    return _count_saved()


def _download_csv(url: str, filename: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        print(f"  {filename} gia' scaricato ({os.path.getsize(filepath):,} bytes)")
        return filepath

    print(f"  Download {filename}...")
    resp = requests.get(url, stream=True, timeout=120,
                       headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    
    downloaded = 0
    with open(filepath, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if stop_event.is_set():
                return filepath
            f.write(chunk)
            downloaded += len(chunk)
            _progress["downloaded"] = downloaded
            if downloaded % (10 * CHUNK_SIZE) == 0:
                print(f"    {downloaded / (1024*1024):.1f} MB scaricati")
    
    print(f"  {filename} completato: {downloaded / (1024*1024):.1f} MB")
    return filepath


def _import_csv(filepath: str, source_label: str):
    conn = get_conn()
    batch = []
    batch_size = 5000
    count = 0
    now = datetime.now().isoformat()
    
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if stop_event.is_set():
                break
            
            batch.append((
                row.get('images-href', ''),
                row.get('nom', ''),
                row.get('naissance', ''),
                row.get('Grade', ''),
                row.get('Unité', row.get('Unit\u00e9', '')),
                row.get('Lieu de naissance', ''),
                row.get('Bureau de recrutement', ''),
                row.get('Classe', ''),
                row.get('Matricule au recrutement', ''),
                row.get('Date de d\u00e9c\u00e8s', row.get('Date de décès', '')),
                row.get('Lieu de d\u00e9c\u00e8s', row.get('Lieu de décès', '')),
                row.get('Lieu de d\u00e9c\u00e8s (suite)', row.get('Lieu de décès (suite)', '')),
                row.get('D\u00e9partement de d\u00e9c\u00e8s', row.get('Département de décès', '')),
                row.get('Pays de d\u00e9c\u00e8s', row.get('Pays de décès', '')),
                row.get('Lieu de transcription du d\u00e9c\u00e8s', row.get('Lieu de transcription du décès', '')),
                row.get('D\u00e9partement de transcription du d\u00e9c\u00e8s', row.get('Département de transcription du décès', '')),
                row.get('Pays de transcription du d\u00e9c\u00e8s', row.get('Pays de transcription du décès', '')),
                source_label,
                now,
            ))
            
            if len(batch) >= batch_size:
                conn.executemany("""
                    INSERT INTO caduti_francia_ww1
                    (images_href, nom, naissance, grade, unite, lieu_naissance,
                     bureau_recrutement, classe, matricule, date_deces,
                     lieu_deces, lieu_deces_suite, departement_deces, pays_deces,
                     lieu_transcription, departement_transcription, pays_transcription,
                     source, elaborato_il)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, batch)
                conn.commit()
                count += len(batch)
                _progress["imported"] = count
                print(f"    {count:,} importati")
                batch = []
    
    if batch:
        conn.executemany("""
            INSERT INTO caduti_francia_ww1
            (images_href, nom, naissance, grade, unite, lieu_naissance,
             bureau_recrutement, classe, matricule, date_deces,
             lieu_deces, lieu_deces_suite, departement_deces, pays_deces,
             lieu_transcription, departement_transcription, pays_transcription,
             source, elaborato_il)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        conn.commit()
        count += len(batch)
    
    conn.close()
    _progress["imported"] = count
    print(f"  Importazione {source_label} completata: {count:,} record")
    return count


def get_progress() -> dict:
    return dict(_progress)


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def scrape_all():
    stop_event.clear()
    _init_table()
    
    already = _count_saved()
    if already > 0:
        print(f"  {already:,} record gia' presenti. Pulizia tabella per reimportazione...")
        conn = get_conn()
        conn.execute("DELETE FROM caduti_francia_ww1")
        conn.commit()
        conn.close()
    
    _progress.update({"status": "processing", "phase": "download", "downloaded": 0, "imported": 0})
    
    total_imported = 0
    for label, url in URLS.items():
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return
        
        filename = f"mdh_{label}.csv"
        _progress["phase"] = f"download_{label}"
        filepath = _download_csv(url, filename)
        
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return
        
        _progress["phase"] = f"import_{label}"
        count = _import_csv(filepath, label)
        total_imported += count
    
    _progress["status"] = "done"
    _progress["phase"] = ""
    total = _count_saved()
    _progress["total_saved"] = total
    print(f"\n=== Memoire des Hommes completato. Totale: {total:,} record ===")


def count_caduti_francia() -> int:
    return _count_saved()
