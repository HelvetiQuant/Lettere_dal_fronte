"""Sistema archivio fonti documentali primarie.

Pipeline:
  File (PDF/JPEG/TIFF) → Ingestione → Classificazione OCR → DB archivio_fonti
  Query semantica → Recupero documenti + originale

Il sistema archivia SEMPRE il documento con i metadati noti dalla fonte
(fondo, segnatura, unità, data, archivio) anche quando il testo è in
corsivo illeggibile o la qualità è insufficiente per OCR/HTR.
La risposta a una query include il file originale + scheda metadati.

Tabella: archivio_fonti
Non tocca nessuna tabella esistente.
"""

import hashlib
import io
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from database import get_conn

# ─── Config ────────────────────────────────────────────────────────────────────

STORAGE_DIR = Path(__file__).parent / "archivio_storage"
STORAGE_DIR.mkdir(exist_ok=True)

SUPPORTED_FORMATS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

# Archivi storici riconosciuti
ARCHIVI_NOTI = {
    "AUSSME": "Archivio Ufficio Storico Stato Maggiore Esercito - Roma",
    "BUNDESARCHIV": "Bundesarchiv-Militärarchiv - Freiburg",
    "TNA": "The National Archives - Kew",
    "NARA": "National Archives and Records Administration - Washington",
    "SHD": "Service Historique de la Défense - Vincennes",
    "USSME": "Ufficio Storico Stato Maggiore Esercito",
    "ASMi": "Archivio di Stato di Milano",
    "ASTo": "Archivio di Stato di Torino",
    "MAE": "Ministero degli Affari Esteri - Archivio storico",
    "ALTRO": "Altro archivio",
}

# Livelli unità
LIVELLI_UNITA = ["armata", "corpo d'armata", "divisione", "brigata",
                 "reggimento", "battaglione", "compagnia", "plotone", "altro"]

# Teatri operativi
TEATRI = ["Italia", "Grecia", "Balcani", "Francia", "Africa settentrionale",
          "Africa orientale", "Russia/URSS", "Germania", "Austria", "Altro"]

stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": "", "total_saved": 0}


# ─── DB ────────────────────────────────────────────────────────────────────────

def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS archivio_fonti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Identificazione file
            hash_sha256 TEXT UNIQUE NOT NULL,
            path_originale TEXT,
            path_storage TEXT,
            formato TEXT,
            dimensione_bytes INTEGER,
            pagine INTEGER,

            -- Classificazione OCR/leggibilità
            ocr_status TEXT DEFAULT 'pending',
            -- 'done'|'partial'|'skip_cursive'|'skip_quality'|'pending'|'error'
            readable INTEGER DEFAULT 0,
            htr_attempted INTEGER DEFAULT 0,
            qualita_immagine REAL,
            testo_ocr TEXT,
            lingua_documento TEXT,

            -- Metadati archivistici (compilabili senza leggere il testo)
            archivio TEXT,
            fondo TEXT,
            serie TEXT,
            busta TEXT,
            fascicolo TEXT,
            segnatura TEXT,
            titolo_documento TEXT,

            -- Metadati militari
            unita_principale TEXT,
            livello_unita TEXT,
            unita_superiore TEXT,
            teatro_operazioni TEXT,
            nazione_forza TEXT,

            -- Metadati cronologici
            data_inizio TEXT,
            data_fine TEXT,
            data_raw TEXT,

            -- Classificazione tipologica
            tipo_documento TEXT,
            -- diario_storico|ordine|rapporto|mappa|fotografia|lettera|corsivo_illeggibile|altro
            conflitto TEXT,
            -- "World War 1"|"World War 2"|"Guerra d'Etiopia"|altro

            -- Indice semantico (JSON arrays)
            unita_citate TEXT,
            luoghi_citati TEXT,
            parole_chiave TEXT,

            -- Attendibilità e note
            attendibilita_fonte INTEGER DEFAULT 3,
            -- 1=bassa 2=discreta 3=media 4=buona 5=eccellente
            note TEXT,
            fonte_acquisizione TEXT,
            -- NARA_T315|JMO_FRANCIA|TNA_WO95|UPLOAD_MANUALE|...

            elaborato_il TEXT NOT NULL,
            aggiornato_il TEXT
        )
    """)

    # Indici per query semantica
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_af_hash ON archivio_fonti(hash_sha256)",
        "CREATE INDEX IF NOT EXISTS idx_af_archivio ON archivio_fonti(archivio)",
        "CREATE INDEX IF NOT EXISTS idx_af_unita ON archivio_fonti(unita_principale)",
        "CREATE INDEX IF NOT EXISTS idx_af_teatro ON archivio_fonti(teatro_operazioni)",
        "CREATE INDEX IF NOT EXISTS idx_af_data ON archivio_fonti(data_inizio)",
        "CREATE INDEX IF NOT EXISTS idx_af_tipo ON archivio_fonti(tipo_documento)",
        "CREATE INDEX IF NOT EXISTS idx_af_ocr ON archivio_fonti(ocr_status)",
        "CREATE INDEX IF NOT EXISTS idx_af_fondo ON archivio_fonti(fondo)",
        "CREATE INDEX IF NOT EXISTS idx_af_conflitto ON archivio_fonti(conflitto)",
    ]:
        conn.execute(idx_sql)

    conn.commit()
    conn.close()
    print("  Tabella archivio_fonti pronta")


def _count_saved() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM archivio_fonti").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def _hash_exists(sha256: str) -> Optional[int]:
    conn = get_conn()
    try:
        r = conn.execute("SELECT id FROM archivio_fonti WHERE hash_sha256 = ?", (sha256,)).fetchone()
        return r[0] if r else None
    finally:
        conn.close()


def _compute_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _store_file(src: Path, sha256: str) -> Path:
    """Copia il file nello storage permanente organizzato per hash."""
    subdir = STORAGE_DIR / sha256[:2]
    subdir.mkdir(exist_ok=True)
    dest = subdir / f"{sha256}{src.suffix.lower()}"
    if not dest.exists():
        shutil.copy2(src, dest)
    return dest


def _count_pages(path: Path) -> int:
    """Conta le pagine (PDF) o ritorna 1 per immagini."""
    try:
        if path.suffix.lower() == ".pdf":
            import subprocess
            result = subprocess.run(
                ["python", "-c",
                 f"import fitz; doc=fitz.open(r'{path}'); print(doc.page_count)"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        return 1
    except Exception:
        return 1


def _estimate_quality(path: Path) -> float:
    """Stima qualità immagine 0-1 basata su dimensione e formato."""
    try:
        size = path.stat().st_size
        fmt = path.suffix.lower()
        if fmt == ".pdf":
            return 0.8
        if size < 50_000:
            return 0.3
        if size < 200_000:
            return 0.6
        return 0.85
    except Exception:
        return 0.5


# ─── Ingestione ────────────────────────────────────────────────────────────────

def ingest_file(
    path: Path,
    *,
    archivio: str = "",
    fondo: str = "",
    serie: str = "",
    busta: str = "",
    fascicolo: str = "",
    segnatura: str = "",
    titolo_documento: str = "",
    unita_principale: str = "",
    livello_unita: str = "",
    unita_superiore: str = "",
    teatro_operazioni: str = "",
    nazione_forza: str = "",
    data_inizio: str = "",
    data_fine: str = "",
    data_raw: str = "",
    tipo_documento: str = "",
    conflitto: str = "",
    unita_citate: list = None,
    luoghi_citati: list = None,
    parole_chiave: list = None,
    attendibilita_fonte: int = 3,
    note: str = "",
    fonte_acquisizione: str = "UPLOAD_MANUALE",
    ocr_status: str = "pending",
    testo_ocr: str = "",
    readable: bool = False,
    qualita_immagine: float = None,
    lingua_documento: str = "",
) -> dict:
    """
    Inserisce un documento nell'archivio.
    Ritorna dict con {id, hash, status, path_storage}.
    Se il file è già presente (stesso hash) aggiorna i metadati.
    """
    path = Path(path)
    if not path.exists():
        return {"error": f"File non trovato: {path}"}
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        return {"error": f"Formato non supportato: {path.suffix}"}

    sha256 = _compute_hash(path)
    existing_id = _hash_exists(sha256)

    path_storage = _store_file(path, sha256)
    pagine = _count_pages(path)
    if qualita_immagine is None:
        qualita_immagine = _estimate_quality(path)

    now = datetime.now().isoformat()

    conn = get_conn()
    try:
        if existing_id:
            conn.execute("""
                UPDATE archivio_fonti SET
                    archivio=COALESCE(NULLIF(?,''),(SELECT archivio FROM archivio_fonti WHERE id=?)),
                    fondo=COALESCE(NULLIF(?,''),(SELECT fondo FROM archivio_fonti WHERE id=?)),
                    serie=COALESCE(NULLIF(?,''),(SELECT serie FROM archivio_fonti WHERE id=?)),
                    busta=COALESCE(NULLIF(?,''),(SELECT busta FROM archivio_fonti WHERE id=?)),
                    fascicolo=COALESCE(NULLIF(?,''),(SELECT fascicolo FROM archivio_fonti WHERE id=?)),
                    segnatura=COALESCE(NULLIF(?,''),(SELECT segnatura FROM archivio_fonti WHERE id=?)),
                    titolo_documento=COALESCE(NULLIF(?,''),(SELECT titolo_documento FROM archivio_fonti WHERE id=?)),
                    unita_principale=COALESCE(NULLIF(?,''),(SELECT unita_principale FROM archivio_fonti WHERE id=?)),
                    livello_unita=COALESCE(NULLIF(?,''),(SELECT livello_unita FROM archivio_fonti WHERE id=?)),
                    teatro_operazioni=COALESCE(NULLIF(?,''),(SELECT teatro_operazioni FROM archivio_fonti WHERE id=?)),
                    nazione_forza=COALESCE(NULLIF(?,''),(SELECT nazione_forza FROM archivio_fonti WHERE id=?)),
                    data_inizio=COALESCE(NULLIF(?,''),(SELECT data_inizio FROM archivio_fonti WHERE id=?)),
                    data_fine=COALESCE(NULLIF(?,''),(SELECT data_fine FROM archivio_fonti WHERE id=?)),
                    tipo_documento=COALESCE(NULLIF(?,''),(SELECT tipo_documento FROM archivio_fonti WHERE id=?)),
                    conflitto=COALESCE(NULLIF(?,''),(SELECT conflitto FROM archivio_fonti WHERE id=?)),
                    aggiornato_il=?
                WHERE id=?
            """, (
                archivio, existing_id, fondo, existing_id, serie, existing_id,
                busta, existing_id, fascicolo, existing_id, segnatura, existing_id,
                titolo_documento, existing_id, unita_principale, existing_id,
                livello_unita, existing_id, teatro_operazioni, existing_id,
                nazione_forza, existing_id, data_inizio, existing_id,
                data_fine, existing_id, tipo_documento, existing_id,
                conflitto, existing_id, now, existing_id,
            ))
            conn.commit()
            return {"id": existing_id, "hash": sha256, "status": "updated", "path_storage": str(path_storage)}

        conn.execute("""
            INSERT INTO archivio_fonti (
                hash_sha256, path_originale, path_storage, formato,
                dimensione_bytes, pagine, ocr_status, readable,
                qualita_immagine, testo_ocr, lingua_documento,
                archivio, fondo, serie, busta, fascicolo, segnatura,
                titolo_documento, unita_principale, livello_unita,
                unita_superiore, teatro_operazioni, nazione_forza,
                data_inizio, data_fine, data_raw, tipo_documento, conflitto,
                unita_citate, luoghi_citati, parole_chiave,
                attendibilita_fonte, note, fonte_acquisizione, elaborato_il
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            sha256, str(path), str(path_storage), path.suffix.lower(),
            path.stat().st_size, pagine, ocr_status, 1 if readable else 0,
            qualita_immagine, testo_ocr or None, lingua_documento or None,
            archivio or None, fondo or None, serie or None, busta or None,
            fascicolo or None, segnatura or None, titolo_documento or None,
            unita_principale or None, livello_unita or None,
            unita_superiore or None, teatro_operazioni or None,
            nazione_forza or None, data_inizio or None, data_fine or None,
            data_raw or None, tipo_documento or None, conflitto or None,
            json.dumps(unita_citate or [], ensure_ascii=False),
            json.dumps(luoghi_citati or [], ensure_ascii=False),
            json.dumps(parole_chiave or [], ensure_ascii=False),
            attendibilita_fonte, note or None, fonte_acquisizione, now,
        ))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        return {"id": new_id, "hash": sha256, "status": "inserted", "path_storage": str(path_storage)}

    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def ingest_directory(
    directory: Path,
    *,
    archivio: str = "",
    fondo: str = "",
    teatro_operazioni: str = "",
    nazione_forza: str = "",
    conflitto: str = "",
    fonte_acquisizione: str = "UPLOAD_MANUALE",
    recursive: bool = True,
) -> dict:
    """Ingerisce tutti i file supportati in una directory."""
    directory = Path(directory)
    pattern = "**/*" if recursive else "*"
    files = [f for f in directory.glob(pattern)
             if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS]

    results = {"inserted": 0, "updated": 0, "errors": 0, "total": len(files)}
    for f in files:
        res = ingest_file(
            f,
            archivio=archivio, fondo=fondo,
            teatro_operazioni=teatro_operazioni,
            nazione_forza=nazione_forza,
            conflitto=conflitto,
            fonte_acquisizione=fonte_acquisizione,
        )
        if "error" in res:
            results["errors"] += 1
        elif res["status"] == "inserted":
            results["inserted"] += 1
        else:
            results["updated"] += 1

    return results


# ─── Retrofit NARA T315 ────────────────────────────────────────────────────────

def retrofit_nara_t315():
    """
    Porta i 1.153 frame NARA T315 già processati nella tabella archivio_fonti.
    Non cancella né modifica documenti_nara_t315.
    """
    _init_table()
    conn = get_conn()
    rows = conn.execute("""
        SELECT frame, file_immagine, tipo_documento, data_documento, data_raw,
               mittente, destinatario, unita_citate, luoghi_citati,
               testo_ocr, lingua, confidenza, note, elaborato_il
        FROM documenti_nara_t315
        ORDER BY frame
    """).fetchall()
    conn.close()

    print(f"Retrofit NARA T315: {len(rows)} frame")
    inserted = 0
    skipped = 0

    for (frame, file_immagine, tipo_doc, data_doc, data_raw,
         mittente, destinatario, unita_raw, luoghi_raw,
         testo_ocr, lingua, confidenza, note, elaborato_il) in rows:

        path = Path(file_immagine) if file_immagine else None
        if not path or not path.exists():
            skipped += 1
            continue

        # Parsa liste JSON
        try:
            unita = json.loads(unita_raw) if unita_raw else []
        except Exception:
            unita = [unita_raw] if unita_raw else []
        try:
            luoghi = json.loads(luoghi_raw) if luoghi_raw else []
        except Exception:
            luoghi = [luoghi_raw] if luoghi_raw else []

        # Determina OCR status
        has_text = bool(testo_ocr and len(testo_ocr) > 20)
        ocr_status = "done" if has_text else "skip_quality"
        readable = has_text and (confidenza or 0) > 0.3

        res = ingest_file(
            path,
            archivio="NARA",
            fondo="Records of German Field Commands - Divisions",
            serie="Microcopy T-315, Roll 1299",
            segnatura=f"T315-R1299-F{frame:04d}",
            titolo_documento=f"Frame {frame:04d} - {tipo_doc or 'Documento'}",
            unita_principale="117. Jäger-Division / 717. Infanterie-Division",
            livello_unita="divisione",
            teatro_operazioni="Balcani",
            nazione_forza="Germania",
            data_inizio=data_doc or "",
            data_raw=data_raw or "",
            tipo_documento=tipo_doc or "altro",
            conflitto="World War 2",
            unita_citate=unita,
            luoghi_citati=luoghi,
            attendibilita_fonte=4,
            note=f"Mittente: {mittente or '-'} | Destinatario: {destinatario or '-'}. {note or ''}".strip(),
            fonte_acquisizione="NARA_T315",
            ocr_status=ocr_status,
            testo_ocr=testo_ocr or "",
            readable=readable,
            qualita_immagine=confidenza,
            lingua_documento=lingua or "de",
        )
        if "error" in res:
            print(f"  Errore frame {frame}: {res['error']}")
        else:
            inserted += 1

    print(f"Retrofit completato: {inserted} inseriti, {skipped} saltati (file non trovato)")
    return {"inserted": inserted, "skipped": skipped}


# ─── Query semantica ───────────────────────────────────────────────────────────

def query_archivio(
    unita: str = "",
    teatro: str = "",
    data_da: str = "",
    data_a: str = "",
    tipo_documento: str = "",
    archivio: str = "",
    fondo: str = "",
    conflitto: str = "",
    testo_libero: str = "",
    solo_leggibili: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Query semantica sull'archivio.
    Ritorna lista di documenti + path per download del file originale.
    """
    conn = get_conn()
    conditions = []
    params = []

    if unita:
        conditions.append(
            "(unita_principale LIKE ? OR unita_citate LIKE ? OR unita_superiore LIKE ?)"
        )
        u = f"%{unita}%"
        params.extend([u, u, u])

    if teatro:
        conditions.append("teatro_operazioni LIKE ?")
        params.append(f"%{teatro}%")

    if data_da:
        conditions.append("(data_inizio >= ? OR data_inizio IS NULL)")
        params.append(data_da)

    if data_a:
        conditions.append("(data_fine <= ? OR data_fine IS NULL)")
        params.append(data_a)

    if tipo_documento:
        conditions.append("tipo_documento LIKE ?")
        params.append(f"%{tipo_documento}%")

    if archivio:
        conditions.append("archivio LIKE ?")
        params.append(f"%{archivio}%")

    if fondo:
        conditions.append("fondo LIKE ?")
        params.append(f"%{fondo}%")

    if conflitto:
        conditions.append("conflitto LIKE ?")
        params.append(f"%{conflitto}%")

    if testo_libero:
        conditions.append(
            "(testo_ocr LIKE ? OR titolo_documento LIKE ? OR note LIKE ? OR parole_chiave LIKE ?)"
        )
        t = f"%{testo_libero}%"
        params.extend([t, t, t, t])

    if solo_leggibili:
        conditions.append("readable = 1 AND ocr_status = 'done'")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total_row = conn.execute(
        f"SELECT COUNT(*) FROM archivio_fonti {where}", params
    ).fetchone()
    total = total_row[0] if total_row else 0

    rows = conn.execute(
        f"""SELECT id, hash_sha256, path_storage, formato, pagine,
               archivio, fondo, segnatura, titolo_documento,
               unita_principale, livello_unita, teatro_operazioni, nazione_forza,
               data_inizio, data_fine, tipo_documento, conflitto,
               ocr_status, readable, qualita_immagine, attendibilita_fonte,
               testo_ocr, unita_citate, luoghi_citati, note
           FROM archivio_fonti {where}
           ORDER BY data_inizio ASC, attendibilita_fonte DESC
           LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()
    conn.close()

    risultati = []
    for row in rows:
        (rid, sha, path_storage, fmt, pagine,
         arch, fondo_, seg, titolo,
         unita_p, livello, teatro, nazione,
         d_inizio, d_fine, tipo, conf,
         ocr_st, readable_, qualita, attendib,
         testo, unita_c_raw, luoghi_c_raw, note_) = row

        try:
            unita_c = json.loads(unita_c_raw or "[]")
        except Exception:
            unita_c = []
        try:
            luoghi_c = json.loads(luoghi_c_raw or "[]")
        except Exception:
            luoghi_c = []

        risultati.append({
            "id": rid,
            "archivio": arch,
            "fondo": fondo_,
            "segnatura": seg,
            "titolo": titolo,
            "unita": unita_p,
            "livello_unita": livello,
            "teatro": teatro,
            "nazione": nazione,
            "data_inizio": d_inizio,
            "data_fine": d_fine,
            "tipo_documento": tipo,
            "conflitto": conf,
            "ocr_status": ocr_st,
            "readable": bool(readable_),
            "qualita_immagine": qualita,
            "attendibilita": attendib,
            "formato": fmt,
            "pagine": pagine,
            "unita_citate": unita_c,
            "luoghi_citati": luoghi_c,
            "note": note_,
            "testo_anteprima": (testo or "")[:300] if readable_ else None,
            "file_url": f"/api/archivio/file/{sha}",
            "path_storage": path_storage,
        })

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "risultati": risultati,
    }


def get_file_path(sha256: str) -> Optional[Path]:
    """Ritorna il path del file originale dato il suo hash SHA256."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT path_storage FROM archivio_fonti WHERE hash_sha256 = ?", (sha256,)
        ).fetchone()
        return Path(row[0]) if row else None
    finally:
        conn.close()


def update_ocr(doc_id: int, testo_ocr: str, lingua: str = "", confidenza: float = None):
    """Aggiorna il testo OCR di un documento già archiviato."""
    conn = get_conn()
    try:
        readable = bool(testo_ocr and len(testo_ocr.strip()) > 20)
        conn.execute("""
            UPDATE archivio_fonti SET
                testo_ocr=?, lingua_documento=?, qualita_immagine=?,
                ocr_status='done', readable=?, aggiornato_il=?
            WHERE id=?
        """, (testo_ocr, lingua or None, confidenza, 1 if readable else 0,
              datetime.now().isoformat(), doc_id))
        conn.commit()
    finally:
        conn.close()


def get_progress() -> dict:
    return dict(_progress)


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()
