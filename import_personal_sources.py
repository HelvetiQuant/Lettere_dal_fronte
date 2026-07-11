"""Importa fonti storiche personali/narrative dal Desktop in fonti_narrative.

Fonti:
- Desktop\ARCHIVIO STORIE\STORIE IMI\  -> biografie .odt
- Desktop\ARO\                          -> corrispondenza .odt/.docx/.pdf
- Desktop\1945 gaiaschi è libero!\      -> fotografie .jpg
- Desktop\rebancadatiinternatimilitariitaliani\  -> riferimento archivio .odt/.pdf
- Desktop\racconti, storie, libro\      -> memoriale .pdf

Non tocca DOMANDE RENZI né vaticano.
"""

import base64
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from database import get_conn
from extractor import _get_mistral_client


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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_odt_text(path: Path) -> str:
    """Estrae testo da .odt via content.xml (nessuna dipendenza esterna)."""
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
    """Estrae testo da .docx via word/document.xml."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts = []
        for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
            if t.text:
                texts.append(t.text)
        return "\n".join(texts)
    except Exception as e:
        return f"[ERRORE estrazione DOCX: {e}]"


def _mistral_ocr_image(path: Path) -> str:
    """OCR di un'immagine via Mistral OCR."""
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
    """OCR di una pagina PDF via Mistral OCR."""
    import fitz
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
    """Estrae testo da PDF scansionato via Mistral OCR (tutte le pagine)."""
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
    """Ritorna (testo, ocr_status). Se skip_ocr=True, non chiama API (utile per dry-run)."""
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
    """Euristica per estrarre persone menzionate (cognome/nome)."""
    people = []
    # Pattern: COGNOME in maiuscolo seguito da nome minuscolo
    for m in re.finditer(r"\b([A-Z][A-Z\s'-]{1,})([A-Z][a-z]+)\b", text):
        cognome = m.group(1).strip().title()
        nome = m.group(2).strip()
        people.append({"cognome": cognome, "nome": nome})
    # Dal filename: rimuovi estensione e usa come soggetto se contiene un nome
    base = Path(filename).stem
    # Esempi: "BERETTA GIUSEPPE", "D'OTTAVI", "DE ANGELIS"
    if base:
        # rimuovi parole generiche
        clean = re.sub(r"\b(LIBRETTO|EMAIL|generica|tutti|enti)\b", "", base, flags=re.I).strip()
        if clean and not any(p.get("cognome") == clean for p in people):
            people.append({"cognome": clean, "nome": ""})
    return people[:20]


def _classify(path: Path) -> Tuple[str, str]:
    """Ritorna (tipo_fonte, archivio) in base al percorso."""
    parts = [p.name for p in path.parents]
    for key, cat in CATEGORY_MAP.items():
        if key in parts:
            return cat, ARCHIVE_LABEL.get(key, key)
    return "altro", "Desktop"


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _upsert_entities(conn, people: List[dict], fonte_id: int):
    """Crea nodi entita e archi collegamenti per ogni persona."""
    for p in people:
        cognome = (p.get("cognome") or "").strip()
        nome = (p.get("nome") or "").strip()
        if not cognome:
            continue
        valore = f"{cognome} {nome}".strip()
        norm = _normalize_name(valore)
        now = datetime.now().isoformat()
        row = conn.execute(
            "SELECT id FROM entita WHERE valore_normalizzato = ? AND tipo = 'persona'",
            (norm,),
        ).fetchone()
        if row:
            entita_id = row["id"]
        else:
            cur = conn.execute(
                """INSERT INTO entita (tipo, valore, valore_normalizzato, cognome, nome,
                                        fonte_tabella, fonte_id, elaborato_il)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("persona", valore, norm, cognome, nome, "fonti_narrative", fonte_id, now),
            )
            entita_id = cur.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO collegamenti (entita_id, tabella_origine, record_id, tipo_collegamento, confidenza, elaborato_il) VALUES (?, ?, ?, ?, ?, ?)",
            (entita_id, "fonti_narrative", fonte_id, "menzionato", 0.8, now),
        )


def _insert(conn, path: Path, dry_run: bool = False) -> dict:
    sha = _sha256(path)
    existing = conn.execute("SELECT id FROM fonti_narrative WHERE sha256 = ?", (sha,)).fetchone()
    if existing:
        return {"path": str(path), "status": "già presente", "id": existing["id"]}

    tipo_fonte, archivio = _classify(path)
    text, ocr_status = _extract_text(path, skip_ocr=dry_run)
    people = _detect_people(text, path.name)
    persone_possibili = " ".join(
        f"{p.get('cognome','')} {p.get('nome','')}".strip() for p in people
    ).strip()

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

    if dry_run:
        return {"path": str(path), "status": "dry-run", "tipo": tipo_fonte, "persone": people}

    cur = conn.execute(
        """INSERT INTO fonti_narrative
           (sha256, nome_file, path_locale, formato, tipo_fonte, archivio, fondo,
            persone_possibili, soggetti_json, titolo, descrizione, testo_ocr, ocr_status, created_at)
           VALUES (:sha256, :nome_file, :path_locale, :formato, :tipo_fonte, :archivio, :fondo,
                   :persone_possibili, :soggetti_json, :titolo, :descrizione, :testo_ocr, :ocr_status, :created_at)""",
        data,
    )
    fonte_id = cur.lastrowid
    _upsert_entities(conn, people, fonte_id)
    conn.commit()
    return {"path": str(path), "status": "inserito", "id": fonte_id, "tipo": tipo_fonte}


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


def import_all(dry_run: bool = False):
    files = _collect_files()
    print(f"Trovati {len(files)} file da importare.")
    conn = get_conn()
    results = []
    for path in files:
        try:
            res = _insert(conn, path, dry_run=dry_run)
            print(f"  {res['status']:12} {path.name}")
            results.append(res)
        except Exception as e:
            print(f"  [ERRORE] {path.name}: {e}")
            results.append({"path": str(path), "status": "errore", "error": str(e)})
    conn.close()
    return results


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    import_all(dry_run=dry)
