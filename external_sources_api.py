"""API FastAPI per modulo Fonti Esterne Federate (CRI).

Endpoint:
- GET  /api/external-sources                      — lista provider
- GET  /api/external-sources/records              — lista record (paginata, filtri)
- GET  /api/external-sources/records/{id}         — dettaglio record
- GET  /api/external-sources/records/{id}/children — record figli
- GET  /api/external-sources/records/{id}/parents  — gerarchia genitori
- POST /api/external-sources/import               — avvia import
- POST /api/external-sources/records/{id}/refresh — aggiorna singolo record
- POST /api/external-sources/records/{id}/verify-url — verifica URL
- GET  /api/external-sources/records/{id}/matches  — collegamenti candidati
- POST /api/external-sources/records/{id}/generate-matches — genera candidati
- PUT  /api/external-links/{id}/review            — revisione umana
- GET  /api/records/{table}/{id}/external-links   — link esterni di un record interno
- POST /api/external-sources/documents/upload     — upload documento manuale
- GET  /api/external-sources/import/status        — stato job import
"""
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel

from database import get_conn
from auth import require_auth, has_permission
from external_metadata_service import (
    list_providers, get_adapter, run_import, refresh_single_record,
    verify_record_url, get_import_progress, upsert_record,
    save_person_mentions, save_facts, save_digital_objects,
)
from external_link_service import (
    generate_links_for_record, generate_links_for_mention, review_link,
    MATCHABLE_TABLES,
)
from external_sources_models import (
    ImportRequest, ExternalRecordLinkReview, ExternalAccessRequestBase,
)


router = APIRouter(prefix="/api/external-sources", tags=["external-sources"])

# Allowlist tabelle interrogabili
ALLOWED_TABLES = set(MATCHABLE_TABLES.keys()) | {"entita", "menzioni", "fonti_indice", "archivio_fonti", "archivio_documenti", "research_subjects"}


def _row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys()} if row else {}


def _get_record_with_relations(conn, record_id: int) -> dict:
    """Recupera record con menzioni, fatti, oggetti digitali, collegamenti."""
    record = conn.execute("SELECT * FROM external_source_records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        return None
    r = _row_to_dict(record)

    mentions = conn.execute(
        "SELECT * FROM external_person_mentions WHERE external_source_record_id = ?", (record_id,)
    ).fetchall()
    r["person_mentions"] = [_row_to_dict(m) for m in mentions]

    facts = conn.execute(
        "SELECT * FROM external_source_facts WHERE external_source_record_id = ?", (record_id,)
    ).fetchall()
    r["facts"] = [_row_to_dict(f) for f in facts]

    digital_objects = conn.execute(
        "SELECT * FROM external_digital_objects WHERE external_source_record_id = ?", (record_id,)
    ).fetchall()
    r["digital_objects"] = [_row_to_dict(d) for d in digital_objects]

    links = conn.execute(
        "SELECT * FROM external_record_links WHERE external_source_record_id = ?", (record_id,)
    ).fetchall()
    r["record_links"] = [_row_to_dict(l) for l in links]

    return r


# ─── Provider list ──────────────────────────────────────────────────────
@router.get("")
def list_sources():
    """Lista provider disponibili."""
    return list_providers()


# ─── Records list ───────────────────────────────────────────────────────
@router.get("/records")
def list_records(
    request: Request,
    provider: Optional[str] = None,
    record_level: Optional[str] = None,
    fonds_external_id: Optional[str] = None,
    parent_external_id: Optional[str] = None,
    search: Optional[str] = None,
    has_digital_object: Optional[bool] = None,
    access_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "created_at",
    sort_dir: str = "desc",
):
    """Lista record esterni con filtri e paginazione."""
    user = require_auth(request)
    conn = get_conn()

    where = []
    params = []
    if provider:
        where.append("provider = ?")
        params.append(provider)
    if record_level:
        where.append("record_level = ?")
        params.append(record_level)
    if fonds_external_id:
        where.append("fonds_external_id = ?")
        params.append(fonds_external_id)
    if parent_external_id:
        where.append("parent_external_id = ?")
        params.append(parent_external_id)
    if access_status:
        where.append("access_status = ?")
        params.append(access_status)
    if has_digital_object is not None:
        where.append("digital_object_available = ?")
        params.append(1 if has_digital_object else 0)
    if search:
        where.append("(title LIKE ? OR description LIKE ? OR reference_code LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s])

    where_clause = " AND ".join(where) if where else "1=1"

    # Sort
    valid_sort = {"created_at", "updated_at", "title", "date_from", "last_verified_at", "record_level"}
    sort_col = sort if sort in valid_sort else "created_at"
    sort_direction = "DESC" if sort_dir.lower() == "desc" else "ASC"

    # Count
    total = conn.execute(
        f"SELECT COUNT(*) as c FROM external_source_records WHERE {where_clause}", params
    ).fetchone()["c"]

    # Page
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM external_source_records WHERE {where_clause} ORDER BY {sort_col} {sort_direction} LIMIT ? OFFSET ?",
        params + [page_size, offset]
    ).fetchall()

    conn.close()
    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


# ─── Record detail ──────────────────────────────────────────────────────
@router.get("/records/{record_id}")
def get_record(record_id: int, request: Request):
    """Dettaglio record con relazioni."""
    user = require_auth(request)
    conn = get_conn()
    record = _get_record_with_relations(conn, record_id)
    conn.close()
    if not record:
        raise HTTPException(404, "Record non trovato")
    return record


# ─── Children ───────────────────────────────────────────────────────────
@router.get("/records/{record_id}/children")
def get_children(record_id: int, request: Request):
    """Record figli nella gerarchia."""
    user = require_auth(request)
    conn = get_conn()
    record = conn.execute("SELECT provider, external_id FROM external_source_records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        conn.close()
        raise HTTPException(404, "Record non trovato")
    children = conn.execute(
        "SELECT * FROM external_source_records WHERE provider = ? AND parent_external_id = ? ORDER BY record_level, title",
        (record["provider"], record["external_id"])
    ).fetchall()
    conn.close()
    return [_row_to_dict(c) for c in children]


# ─── Parents ────────────────────────────────────────────────────────────
@router.get("/records/{record_id}/parents")
def get_parents(record_id: int, request: Request):
    """Gerarchia genitori."""
    user = require_auth(request)
    conn = get_conn()
    record = conn.execute("SELECT * FROM external_source_records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        conn.close()
        raise HTTPException(404, "Record non trovato")

    parents = []
    current = record
    while current and current["parent_external_id"]:
        parent = conn.execute(
            "SELECT * FROM external_source_records WHERE provider = ? AND external_id = ?",
            (current["provider"], current["parent_external_id"])
        ).fetchone()
        if parent:
            parents.append(_row_to_dict(parent))
            current = parent
        else:
            break
    conn.close()
    return parents


# ─── Import ─────────────────────────────────────────────────────────────
@router.post("/import")
def start_import(req: ImportRequest, request: Request):
    """Avvia import incrementale in background."""
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:upload"):
        raise HTTPException(403, "Permesso insufficiente")

    # Run in background thread
    def _run():
        run_import(req.provider, req.fonds_url, req.max_records or 0, req.force_refresh)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "started", "provider": req.provider}


@router.get("/import/status")
def import_status(provider: Optional[str] = None, request: Request = None):
    """Stato job import."""
    if provider:
        return get_import_progress(provider)
    # All providers
    result = {}
    for p in list_providers():
        pid = p["provider_id"]
        result[pid] = get_import_progress(pid)
    return result


# ─── Refresh single ─────────────────────────────────────────────────────
@router.post("/records/{record_id}/refresh")
def refresh_record(record_id: int, request: Request):
    """Aggiorna singolo record."""
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:upload"):
        raise HTTPException(403, "Permesso insufficiente")
    return refresh_single_record(record_id)


# ─── Verify URL ─────────────────────────────────────────────────────────
@router.post("/records/{record_id}/verify-url")
def verify_url(record_id: int, request: Request):
    """Verifica raggiungibilità URL canonico."""
    user = require_auth(request)
    return verify_record_url(record_id)


# ─── Matches ────────────────────────────────────────────────────────────
@router.get("/records/{record_id}/matches")
def get_matches(record_id: int, request: Request):
    """Collegamenti candidati del record."""
    user = require_auth(request)
    conn = get_conn()
    links = conn.execute(
        "SELECT * FROM external_record_links WHERE external_source_record_id = ? ORDER BY match_score DESC",
        (record_id,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(l) for l in links]


@router.post("/records/{record_id}/generate-matches")
def gen_matches(record_id: int, request: Request):
    """Genera collegamenti candidati per tutte le menzioni del record."""
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:verify"):
        raise HTTPException(403, "Permesso insufficiente")
    links = generate_links_for_record(record_id)
    return {"generated": len(links), "links": links}


# ─── Review link ────────────────────────────────────────────────────────
@router.put("/links/{link_id}/review")
def review_link_endpoint(link_id: int, review: ExternalRecordLinkReview, request: Request):
    """Revisione umana di un collegamento."""
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:verify"):
        raise HTTPException(403, "Permesso insufficiente")
    return review_link(link_id, review.review_status, review.match_status, user.get("username", "system"))


# ─── External links for internal record ─────────────────────────────────
@router.get("/records/{table}/{record_id}/external-links")
def get_external_links_for_record(table: str, record_id: int, request: Request):
    """Collegamenti esterni di un record interno."""
    user = require_auth(request)
    if table not in ALLOWED_TABLES:
        raise HTTPException(400, f"Tabella non consentita. Allowlist: {sorted(ALLOWED_TABLES)}")
    conn = get_conn()
    links = conn.execute(
        "SELECT * FROM external_record_links WHERE target_table = ? AND target_record_id = ? ORDER BY match_score DESC",
        (table, record_id)
    ).fetchall()
    conn.close()
    return [_row_to_dict(l) for l in links]


# ─── Upload document ────────────────────────────────────────────────────
@router.post("/documents/upload")
async def upload_document(
    request: Request,
    external_source_record_id: int = Form(...),
    file: UploadFile = File(...),
):
    """Upload manuale di documento associato a un record esterno."""
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:upload"):
        raise HTTPException(403, "Permesso insufficiente")

    # Validate file
    if not file.filename:
        raise HTTPException(400, "Nome file mancante")
    if file.size and file.size > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(400, "File troppo grande (max 50MB)")

    # Validate MIME
    allowed_types = {"image/jpeg", "image/png", "image/tiff", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"Tipo file non consentito: {file.content_type}")

    # Generate safe filename (not user-controlled)
    import hashlib
    ext = Path(file.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"):
        raise HTTPException(400, "Estensione non consentita")

    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()
    safe_filename = f"ext_{external_source_record_id}_{sha256[:12]}{ext}"

    # Save to storage
    storage_dir = Path("archivio_storage/external_documents")
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / safe_filename
    file_path.write_bytes(content)

    # Save to DB
    conn = get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO external_digital_objects
           (external_source_record_id, object_type, media_type, label, page_url,
            digital_object_available, publicly_viewable, public_download_allowed,
            authorization_required, local_file_path, sha256, file_size, ocr_status,
            rights_statement, retrieved_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 1, 0, 0, 1, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (external_source_record_id, "uploaded_document", file.content_type,
         file.filename, None, str(file_path), sha256, len(content),
         "Caricato manualmente da operatore", now, now, now)
    )
    conn.commit()
    conn.close()

    return {"status": "uploaded", "sha256": sha256, "file_size": len(content), "filename": safe_filename}
