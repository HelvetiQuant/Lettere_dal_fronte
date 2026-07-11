"""Scraper OCR per NARA Microcopy T-315, Roll 1299.
Fonte: National Archives USA - Records of German Field Commands - Divisions
Contenuto: 117. Jäger-Division (ex 717. I.D.) - 1943-1945 - Balcani/Grecia
1.156 immagini JPG, documenti in lingua tedesca.

Usa GPT-4o Vision per OCR con prompt specializzato per documenti militari tedeschi WWII.
API key da Desktop/.env (stessa usata da ocr_lettere).
Resume automatico: salta frame già processati.
"""
import base64
import io
import json
import os
import re
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image
from mistralai.client import Mistral

sys.path.insert(0, str(Path(__file__).parent))
from database import get_conn

# ─── Config ────────────────────────────────────────────────────────────────────

IMAGES_DIR = Path(r"C:\Users\eryma\Downloads\T315_R1299_extracted\T315 R1299")
ROLL = "T315-R1299"
DIVISIONE = "117. Jäger-Division / 717. Infanterie-Division"
REQUEST_DELAY = 3.0
MAX_DIM = 2048

stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": "", "total_saved": 0}

# Frame da saltare (copertine/separatori non informativi)
SKIP_FRAMES = {1, 2, 3}


# ─── API Key ───────────────────────────────────────────────────────────────────

MISTRAL_MODEL = "pixtral-12b-2409"


def _load_api_key() -> str:
    key = os.environ.get("MISTRAL_API_KEY", "")
    if key:
        return key
    candidates = [
        Path.home() / "Desktop" / "lettere dal fronte backup_2026-06-28" / ".env",
        Path(__file__).parent / ".env",
        Path.cwd() / ".env",
    ]
    for p in candidates:
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and "MISTRAL_API_KEY" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("MISTRAL_API_KEY non trovata")


# ─── DB Setup ──────────────────────────────────────────────────────────────────

def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documenti_nara_t315 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT NOT NULL,
            frame INTEGER NOT NULL UNIQUE,
            file_immagine TEXT,
            tipo_documento TEXT,
            data_documento TEXT,
            data_raw TEXT,
            numero_documento TEXT,
            mittente TEXT,
            destinatario TEXT,
            unita_citate TEXT,
            luoghi_citati TEXT,
            perdite TEXT,
            testo_ocr TEXT,
            lingua TEXT DEFAULT 'de',
            divisione TEXT,
            confidenza REAL,
            note TEXT,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_t315_frame ON documenti_nara_t315(frame)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_t315_data ON documenti_nara_t315(data_documento)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_t315_tipo ON documenti_nara_t315(tipo_documento)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_t315_mittente ON documenti_nara_t315(mittente)")
    conn.commit()
    conn.close()
    print("  Tabella documenti_nara_t315 pronta")


def _frame_exists(frame: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT id FROM documenti_nara_t315 WHERE frame = ?", (frame,)).fetchone()
    conn.close()
    return row is not None


def _to_str(val):
    if val is None:
        return None
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    return str(val)


def _save_record(rec: dict):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO documenti_nara_t315
            (roll, frame, file_immagine, tipo_documento, data_documento, data_raw,
             numero_documento, mittente, destinatario, unita_citate, luoghi_citati,
             perdite, testo_ocr, lingua, divisione, confidenza, note, elaborato_il)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rec["roll"], rec["frame"], rec["file_immagine"], _to_str(rec["tipo_documento"]),
            _to_str(rec["data_documento"]), _to_str(rec["data_raw"]), _to_str(rec["numero_documento"]),
            _to_str(rec["mittente"]), _to_str(rec["destinatario"]),
            json.dumps(rec["unita_citate"] if isinstance(rec["unita_citate"], list) else [rec["unita_citate"]] if rec["unita_citate"] else [], ensure_ascii=False) if rec["unita_citate"] else None,
            json.dumps(rec["luoghi_citati"] if isinstance(rec["luoghi_citati"], list) else [rec["luoghi_citati"]] if rec["luoghi_citati"] else [], ensure_ascii=False) if rec["luoghi_citati"] else None,
            _to_str(rec["perdite"]), _to_str(rec["testo_ocr"]), _to_str(rec["lingua"]), rec["divisione"],
            rec["confidenza"], _to_str(rec["note"]), rec["elaborato_il"]
        ))
        conn.commit()
    except Exception as e:
        print(f"  Errore save frame {rec['frame']}: {e}")
    finally:
        conn.close()


def _count_saved() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM documenti_nara_t315").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


# ─── OCR con GPT-4o Vision ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei un esperto di archivistica militare specializzato in documenti Wehrmacht WWII.
Analizza l'immagine di un documento militare tedesco (1941-1945) e restituisci SOLO un JSON valido con questi campi:

{
  "tipo_documento": "Tagesmeldung|Fernspruch|Fernschreiben|Befehl|Tätigkeitsbericht|Lagebericht|Karte|Separatore|Altro",
  "data_raw": "data esatta come appare nel documento (es '16.3.1943' o '16.3.43')",
  "data_documento": "data in formato YYYY-MM-DD se deducibile, altrimenti null",
  "numero_documento": "numero interno del documento (es 'Nr. 40', '0375', 'Ia 34737/1')",
  "mittente": "unità o persona mittente (es 'Nachr.Kp.717', '717.I.D.', 'Braxenthaler')",
  "destinatario": "unità o persona destinataria (es 'Gren.Rgt.749', '117.Jäg.Div.')",
  "unita_citate": ["lista delle unità militari citate nel testo"],
  "luoghi_citati": ["lista dei luoghi geografici citati"],
  "perdite": "perdite indicate (es '15 Tote, 7 Verwundete') o null",
  "testo_ocr": "trascrizione COMPLETA e fedele del testo, anche se parzialmente illeggibile",
  "lingua": "de|it|hr|sr|el|en",
  "confidenza": 0.0-1.0,
  "note": "osservazioni su qualità immagine, danni, illeggibilità parziale"
}

Se il documento è una copertina/separatore/pagina vuota, imposta tipo_documento='Separatore' e testo_ocr con il titolo visibile.
Non aggiungere nulla fuori dal JSON."""


def _encode_image(path: Path) -> str:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > MAX_DIM:
        ratio = MAX_DIM / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _ocr_frame(client: Mistral, img_path: Path) -> dict:
    b64 = _encode_image(img_path)
    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": SYSTEM_PROMPT + "\n\nAnalizza questo documento militare tedesco WWII ed estrai i dati strutturati come JSON."},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                }},
            ]},
        ],
        max_tokens=4096,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    if raw.startswith("json"):
        raw = raw[4:].strip()

    try:
        parsed = json.loads(raw, strict=False)
        if isinstance(parsed, list):
            if not parsed:
                raise ValueError("Lista vuota")
            merged = parsed[0]
            for item in parsed[1:]:
                for k in ("unita_citate", "luoghi_citati"):
                    if isinstance(item.get(k), list):
                        existing = merged.get(k) or []
                        merged[k] = list(set(existing + item[k]))
                if item.get("testo_ocr") and merged.get("testo_ocr"):
                    merged["testo_ocr"] += "\n---\n" + item["testo_ocr"]
            merged["note"] = f"Frame con {len(parsed)} schede. " + (merged.get("note") or "")
            return merged
        return parsed
    except (json.JSONDecodeError, ValueError):
        return {
            "tipo_documento": "Altro",
            "data_raw": None, "data_documento": None,
            "numero_documento": None, "mittente": None,
            "destinatario": None, "unita_citate": [],
            "luoghi_citati": [], "perdite": None,
            "testo_ocr": raw,
            "lingua": "de", "confidenza": 0.0,
            "note": "Errore parsing JSON"
        }


# ─── Scrape principale ─────────────────────────────────────────────────────────

def get_progress() -> dict:
    return dict(_progress)


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def scrape_all(resume: bool = True):
    stop_event.clear()
    _init_table()

    images = sorted(IMAGES_DIR.glob("*.jpg"))
    if not images:
        print(f"Nessuna immagine trovata in {IMAGES_DIR}")
        return

    total = len(images)
    already = _count_saved() if resume else 0
    _progress.update({
        "status": "processing", "processed": already,
        "total": total, "current": "", "total_saved": already
    })

    print(f"T315 R1299: {total} frame totali, {already} già processati")

    api_key = _load_api_key()
    client = Mistral(api_key=api_key, timeout_ms=90_000)

    for img_path in images:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return

        frame_num = int(img_path.stem)

        if frame_num in SKIP_FRAMES:
            continue

        if resume and _frame_exists(frame_num):
            _progress["processed"] += 1
            continue

        _progress["current"] = img_path.name
        print(f"  Frame {frame_num:04d}/{total}: {img_path.name}")

        try:
            ocr_data = _ocr_frame(client, img_path)
        except Exception as e:
            print(f"    Errore OCR frame {frame_num}: {e}")
            time.sleep(REQUEST_DELAY * 3)
            continue

        rec = {
            "roll": ROLL,
            "frame": frame_num,
            "file_immagine": str(img_path),
            "tipo_documento": ocr_data.get("tipo_documento"),
            "data_documento": ocr_data.get("data_documento"),
            "data_raw": ocr_data.get("data_raw"),
            "numero_documento": ocr_data.get("numero_documento"),
            "mittente": ocr_data.get("mittente"),
            "destinatario": ocr_data.get("destinatario"),
            "unita_citate": ocr_data.get("unita_citate"),
            "luoghi_citati": ocr_data.get("luoghi_citati"),
            "perdite": ocr_data.get("perdite"),
            "testo_ocr": ocr_data.get("testo_ocr"),
            "lingua": ocr_data.get("lingua", "de"),
            "divisione": DIVISIONE,
            "confidenza": ocr_data.get("confidenza"),
            "note": ocr_data.get("note"),
            "elaborato_il": datetime.now().isoformat(),
        }

        _save_record(rec)
        saved_total = _count_saved()
        _progress["processed"] += 1
        _progress["total_saved"] = saved_total

        tipo = ocr_data.get("tipo_documento", "?")
        data = ocr_data.get("data_raw", "?")
        print(f"    -> {tipo} | {data} | conf={ocr_data.get('confidenza', 0):.1f}")

        if _progress["processed"] % 50 == 0:
            print(f"\n  === Progresso: {_progress['processed']}/{total} | DB: {saved_total} ===\n")

        time.sleep(REQUEST_DELAY)

    _progress["status"] = "done"
    _progress["current"] = ""
    total_saved = _count_saved()
    _progress["total_saved"] = total_saved
    print(f"\n=== T315 R1299 completato. Totale: {total_saved} frame processati ===")


def count_documenti_nara() -> int:
    return _count_saved()
