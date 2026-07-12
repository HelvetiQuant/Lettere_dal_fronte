"""Import unificato di fonti personali/narrative nel DB principale.

Consolida `import_lettere_personali.py` (migrazione da `ocr_lettere.db`)
e `import_personal_sources.py` (import da cartelle Desktop) in un unico modulo.

Tabelle target:
- `lettere_personali`: lettere OCR dal database secondario
- `fonti_narrative`: biografie, memoriali, foto, corrispondenza dal Desktop

Entrambe le tabelle collegano persone a `entita`/`collegamenti` (star schema).
"""

import base64
import hashlib
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from database import get_conn


# ─── Config ───────────────────────────────────────────────────────────────────

OCR_DB = Path("import_ocr_lettere/ocr_lettere.db")
MAIN_DB = Path("imi_internati.db")
DESKTOP = Path.home() / "Desktop"

CATEGORY_MAP = {
    "ARCHIVIO STORIE": "biografia",
    "STORIE IMI": "biografia",
    "ARO": "corrispondenza",
    "1945 gaiaschi è libero!": "fotografia",
    "rebancadatiinternatimilitariitaliani": "riferimento_archivio",
    "racconti, storie, libro": "memoriale",
}

ARCHIVE_LABEL = {
    "ARCHIVIO STORIE": "Desktop — ARCHIVIO STORIE",
    "STORIE IMI": "Desktop — ARCHIVIO STORIE / STORIE IMI",
    "ARO": "Desktop — ARO",
    "1945 gaiaschi è libero!": "Desktop — 1945 gaiaschi è libero!",
    "rebancadatiinternatimilitariitaliani": "Desktop — rebancadatiinternatimilitariitaliani",
    "racconti, storie, libro": "Desktop — racconti, storie, libro",
}

_LETTERE_DDL = """
CREATE TABLE IF NOT EXISTS lettere_personali (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_path TEXT,
    mittente TEXT,
    destinatario TEXT,
    data_lettera TEXT,
    luogo TEXT,
    oggetto TEXT,
    corpo_testo TEXT,
    note TEXT,
    confidenza REAL,
    lingua TEXT,
    raw_response TEXT,
    sha256 TEXT UNIQUE,
    sorgente_db TEXT,
    sorgente_id INTEGER,
    elaborato_il TEXT
);

CREATE INDEX IF NOT EXISTS idx_lettere_mittente ON lettere_personali(mittente);
CREATE INDEX IF NOT EXISTS idx_lettere_destinatario ON lettere_personali(destinatario);
CREATE INDEX IF NOT EXISTS idx_lettere_luogo ON lettere_personali(luogo);
CREATE INDEX IF NOT EXISTS idx_lettere_data ON lettere_personali(data_lettera);
"""


# ─── Utility ──────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalizza_nome(valore: str) -> str:
    v = re.sub(r"\s+", " ", valore.lower().strip())
    v = re.sub(r"[^a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ\s'-]", "", v)
    return v


def _estrai_cognome_nome(valore: str):
    if not valore:
        return "", ""
    valore = valore.strip()
    if "," in valore:
        parti = [p.strip() for p in valore.split(",")]
        return parti[0], " ".join(parti[1:])
    parti = valore.split()
    if len(parti) >= 2:
        return parti[0], " ".join(parti[1:])
    return valore, ""


def _persone_da_testo(testo: str):
    if not testo:
        return []
    pattern = re.compile(r"(?<![.!?]\s)(?<![A-Z])([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+(?:\s+[A-Z][a-zàèéìòù]+)?)")
    cortesia = {"grazie", "caro", "cara", "saluti", "tuo", "tua", "tanti", "affettuosi", "cordiali"}
    trovati = set()
    for m in pattern.finditer(testo):
        nome = m.group(1).strip()
        parole = nome.lower().split()
        if len(nome) > 3 and not any(p in cortesia for p in parole):
            trovati.add(nome)
    return sorted(trovati)


# ─── Entity linking (shared) ──────────────────────────────────────────────────

def _upsert_persona(conn, valore: str, now: str, fonte_tabella: str, record_id: int):
    if not valore:
        return None
    cognome, nome = _estrai_cognome_nome(valore)
    if not cognome and not nome:
        return None
    display = f"{cognome} {nome}".strip()
    norm = _normalizza_nome(display)
    if not norm:
        return None

    row = conn.execute(
        "SELECT id FROM entita WHERE tipo='persona' AND valore_normalizzato=?",
        (norm,),
    ).fetchone()
    if row:
        entita_id = row[0]
    else:
        cur = conn.execute(
            """INSERT INTO entita (tipo, valore, valore_normalizzato, cognome, nome,
                                   fonte_tabella, fonte_id, elaborato_il)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("persona", display, norm, cognome, nome, fonte_tabella, record_id, now),
        )
        entita_id = cur.lastrowid

    conn.execute(
        "INSERT OR IGNORE INTO collegamenti (entita_id, tabella_origine, record_id, tipo_collegamento, confidenza, elaborato_il) VALUES (?, ?, ?, ?, ?, ?)",
        (entita_id, fonte_tabella, record_id, "menzionato", 0.8, now),
    )
    return entita_id


def _upsert_entita_batch(conn, people: List[dict], fonte_tabella: str, fonte_id: int):
    for p in people:
        cognome = (p.get("cognome") or "").strip()
        nome = (p.get("nome") or "").strip()
        if not cognome:
            continue
        valore = f"{cognome} {nome}".strip()
        _upsert_persona(conn, valore, datetime.now().isoformat(), fonte_tabella, fonte_id)


# ─── Lettere personali (from ocr_lettere.db) ──────────────────────────────────

def migrate_lettere(dry_run: bool = False) -> dict:
    """Migra lettere OCR da ocr_lettere.db → lettere_personali."""
    if not OCR_DB.exists():
        return {"status": "skip", "reason": f"DB OCR non trovato: {OCR_DB}", "inserted": 0, "skipped": 0}

    main = sqlite3.connect(MAIN_DB)
    main.executescript(_LETTERE_DDL)

    ocr = sqlite3.connect(OCR_DB)
    ocr.row_factory = sqlite3.Row
    rows = ocr.execute("SELECT * FROM lettere").fetchall()
    now = datetime.now().isoformat()

    inserted = 0
    skipped = 0
    for r in rows:
        sha = _sha256(Path(r["file_path"])) if r["file_path"] else ""
        if sha:
            existing = main.execute("SELECT id FROM lettere_personali WHERE sha256=?", (sha,)).fetchone()
            if existing:
                skipped += 1
                continue

        if dry_run:
            inserted += 1
            continue

        cur = main.execute(
            """INSERT INTO lettere_personali
                 (filename, file_path, mittente, destinatario, data_lettera, luogo, oggetto,
                  corpo_testo, note, confidenza, lingua, raw_response, sha256,
                  sorgente_db, sorgente_id, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r["filename"], r["file_path"], r["mittente"], r["destinatario"],
             r["data_lettera"], r["luogo"], r["oggetto"], r["corpo_testo"],
             r["note"], r["confidenza"], r["lingua"], r["raw_response"], sha,
             "ocr_lettere", r["id"], now),
        )
        lettera_id = cur.lastrowid
        inserted += 1

        _upsert_persona(main, r["mittente"] or "", now, "lettere_personali", lettera_id)
        _upsert_persona(main, r["destinatario"] or "", now, "lettere_personali", lettera_id)
        for persona in _persone_da_testo(r["corpo_testo"] or ""):
            _upsert_persona(main, persona, now, "lettere_personali", lettera_id)

    if not dry_run:
        main.commit()
    print(f"[lettere_personali] {inserted} inserite, {skipped} saltate.")
    ocr.close()
    main.close()
    return {"status": "ok", "inserted": inserted, "skipped": skipped}


# ─── Fonti narrative (from Desktop) ───────────────────────────────────────────

def _extract_odt_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("content.xml")
        root = ET.fromstring(xml)
        texts = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                texts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                texts.append(elem.tail.strip())
        return "\n".join(texts)
    except Exception as e:
        return f"[ERRORE estrazione ODT: {e}]"


def _extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        texts = []
        for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
            if t.text:
                texts.append(t.text)
        return "\n".join(texts)
    except Exception as e:
        return f"[ERRORE estrazione DOCX: {e}]"


def _mistral_ocr_image(path: Path) -> str:
    from extractor import _get_mistral_client
    client = _get_mistral_client()
    b64 = base64.b64encode(path.read_bytes()).decode()
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    result = client.ocr.process(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": f"data:{mime};base64,{b64}"},
    )
    if result.pages:
        return result.pages[0].markdown or ""
    return ""


def _mistral_ocr_pdf_page(path: Path, page_num: int) -> str:
    import fitz
    from extractor import _get_mistral_client
    client = _get_mistral_client()
    doc = fitz.open(str(path))
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    b64 = base64.b64encode(pix.tobytes("png")).decode()
    doc.close()
    result = client.ocr.process(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
    )
    if result.pages:
        return result.pages[0].markdown or ""
    return ""


def _extract_pdf_text(path: Path) -> str:
    import fitz
    doc = fitz.open(str(path))
    parts = []
    for i in range(doc.page_count):
        try:
            parts.append(_mistral_ocr_pdf_page(path, i))
        except Exception as e:
            parts.append(f"[ERRORE OCR pagina {i+1}: {e}]")
    doc.close()
    return "\n\n".join(parts)


def _extract_text(path: Path, skip_ocr: bool = False) -> Tuple[str, str]:
    ext = path.suffix.lower()
    if ext == ".odt":
        return _extract_odt_text(path), "done"
    if ext == ".docx":
        return _extract_docx_text(path), "done"
    if ext in (".jpg", ".jpeg", ".png", ".tiff"):
        if skip_ocr:
            return "[OCR omesso in dry-run]", "pending"
        return _mistral_ocr_image(path), "done"
    if ext == ".pdf":
        if skip_ocr:
            return "[OCR omesso in dry-run]", "pending"
        return _extract_pdf_text(path), "done"
    return "", "skip_quality"


def _detect_people(text: str, filename: str) -> List[dict]:
    people = []
    for m in re.finditer(r"\b([A-Z][A-Z\s'-]{1,})([A-Z][a-z]+)\b", text):
        cognome = m.group(1).strip().title()
        nome = m.group(2).strip()
        people.append({"cognome": cognome, "nome": nome})
    base = Path(filename).stem
    if base:
        clean = re.sub(r"\b(LIBRETTO|EMAIL|generica|tutti|enti)\b", "", base, flags=re.I).strip()
        if clean and not any(p.get("cognome") == clean for p in people):
            people.append({"cognome": clean, "nome": ""})
    return people[:20]


def _classify(path: Path) -> Tuple[str, str]:
    parts = [p.name for p in path.parents]
    for key, cat in CATEGORY_MAP.items():
        if key in parts:
            return cat, ARCHIVE_LABEL.get(key, key)
    return "altro", "Desktop"


def _collect_files() -> List[Path]:
    sources = [
        DESKTOP / "ARCHIVIO STORIE" / "STORIE IMI",
        DESKTOP / "ARO",
        DESKTOP / "1945 gaiaschi è libero!",
        DESKTOP / "rebancadatiinternatimilitariitaliani",
        DESKTOP / "racconti, storie, libro",
    ]
    files = []
    for src in sources:
        if src.exists():
            for p in src.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".odt", ".docx", ".pdf", ".jpg", ".jpeg", ".png", ".tiff"):
                    files.append(p)
    return sorted(files)


def import_fonti_narrative(dry_run: bool = False) -> dict:
    """Importa fonti narrative dal Desktop → fonti_narrative."""
    files = _collect_files()
    print(f"[fonti_narrative] Trovati {len(files)} file da importare.")
    conn = get_conn()
    inserted = 0
    skipped = 0
    errors = 0

    for path in files:
        try:
            sha = _sha256(path)
            existing = conn.execute("SELECT id FROM fonti_narrative WHERE sha256 = ?", (sha,)).fetchone()
            if existing:
                skipped += 1
                continue

            tipo_fonte, archivio = _classify(path)
            text, ocr_status = _extract_text(path, skip_ocr=dry_run)
            people = _detect_people(text, path.name)
            persone_possibili = " ".join(
                f"{p.get('cognome','')} {p.get('nome','')}".strip() for p in people
            ).strip()

            if dry_run:
                inserted += 1
                continue

            data = {
                "sha256": sha,
                "nome_file": path.name,
                "path_locale": str(path),
                "formato": path.suffix.lower().lstrip("."),
                "tipo_fonte": tipo_fonte,
                "archivio": archivio,
                "fondo": path.parent.name,
                "persone_possibili": persone_possibili,
                "soggetti_json": json.dumps(people, ensure_ascii=False),
                "titolo": path.stem,
                "descrizione": "",
                "testo_ocr": text,
                "ocr_status": ocr_status,
                "created_at": datetime.now().isoformat(),
            }

            cur = conn.execute(
                """INSERT INTO fonti_narrative
                   (sha256, nome_file, path_locale, formato, tipo_fonte, archivio, fondo,
                    persone_possibili, soggetti_json, titolo, descrizione, testo_ocr, ocr_status, created_at)
                   VALUES (:sha256, :nome_file, :path_locale, :formato, :tipo_fonte, :archivio, :fondo,
                           :persone_possibili, :soggetti_json, :titolo, :descrizione, :testo_ocr, :ocr_status, :created_at)""",
                data,
            )
            fonte_id = cur.lastrowid
            _upsert_entita_batch(conn, people, "fonti_narrative", fonte_id)
            conn.commit()
            inserted += 1
        except Exception as e:
            print(f"  [ERRORE] {path.name}: {e}")
            errors += 1

    conn.close()
    print(f"[fonti_narrative] {inserted} inserite, {skipped} saltate, {errors} errori.")
    return {"status": "ok", "inserted": inserted, "skipped": skipped, "errors": errors}


# ─── Entry point ──────────────────────────────────────────────────────────────

def import_all(dry_run: bool = False) -> dict:
    """Esegue entrambe le importazioni (lettere + fonti narrative)."""
    print("=== Import fonti personali unificato ===\n")
    r1 = migrate_lettere(dry_run=dry_run)
    r2 = import_fonti_narrative(dry_run=dry_run)
    return {"lettere_personali": r1, "fonti_narrative": r2}


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    result = import_all(dry_run=dry)
    print(f"\n=== Risultato ===\n{json.dumps(result, indent=2, ensure_ascii=False)}")
