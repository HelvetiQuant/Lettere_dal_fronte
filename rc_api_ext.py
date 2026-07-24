"""API estese per il modulo Percorso Riconoscimenti.

Contiene:
- CRUD contatti discendenti estesi
- CRUD contatti istituzionali
- Documenti con versionamento e classificazione
- Checklist documenti per riconoscimento
- Comunicazioni con thread e scadenze
- Timeline pratica
- Ricerca globale con permessi
- Dashboard con indicatori reali
- Generazione pacchetto discendente
- Generazione fascicolo ufficiale con validazione
"""
import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse

from database import get_conn
from auth import require_auth, has_permission
from rc_api import _now, _audit, RC_UPLOAD_DIR

router = APIRouter(prefix="/api/rc", tags=["percorso-riconoscimenti-ext"])

RC_DOC_DIR = Path(__file__).parent / "uploads" / "rc_docs"
RC_DOC_DIR.mkdir(parents=True, exist_ok=True)

RC_PKG_DIR = Path(__file__).parent / "outputs" / "rc_packages"
RC_PKG_DIR.mkdir(parents=True, exist_ok=True)

DOCUMENT_CATEGORIES = [
    "IDENTITA_CANDIDATO", "STATO_CIVILE", "PARENTELA", "FOGLIO_MATRICOLARE",
    "STATO_DI_SERVIZIO", "DIARIO_STORICO", "PROPOSTA_DI_RICOMPENSA",
    "ENCOMIO", "DECRETO", "GAZZETTA_UFFICIALE", "DOMANDA", "MODULO",
    "DELEGA", "CONSENSO", "RELAZIONE_STORICA", "FONTE_ARCHIVISTICA",
    "CORRISPONDENZA", "PEC_INVIATA", "PEC_RICEVUTA", "PROTOCOLLO",
    "RICHIESTA_INTEGRAZIONE", "INTEGRAZIONE", "RISPOSTA_INTERMEDIA",
    "PROVVEDIMENTO_FINALE", "ATTESTATO", "FOTOGRAFIA", "ALTRO",
]

DESCENDANT_CONTACT_STATES = [
    "NON_VERIFICATO", "DA_VERIFICARE", "VERIFICATO", "POTENZIALE_DISCENDENTE",
    "DISCENDENTE_CONFERMATO", "CONTATTO_DA_APPROVARE", "PRIMO_CONTATTO_INVIATO",
    "IN_ATTESA_DI_RISPOSTA", "INTERESSATO", "NON_INTERESSATO", "IRREPERIBILE",
    "RECAPITO_ERRATO", "NON_CONTATTARE", "REFERENTE_FAMILIARE", "ARCHIVIATO",
]

CONTACT_SOURCES = [
    "comunicato_direttamente", "comunicato_familiare", "comune", "prefettura",
    "associazione", "archivio", "elenco_pubblico", "necrologio",
    "fonte_genealogica", "ricerca_online", "intermediario",
    "corrispondenza_precedente", "altra_fonte_documentata",
]


def _filter_recaps(data: dict, user: dict) -> dict:
    """Oscura recapiti di persone viventi per utenti non autorizzati."""
    if has_permission(user["role"], "rc:contact:view_recaps"):
        return data
    if data.get("visibilita_limitata", 1) == 1:
        for field in ["email", "pec", "telefono", "indirizzo_postale", "altro_canale",
                       "profilo_pubblico_url", "url_fonte"]:
            if data.get(field):
                data[field] = "[DATO RISERVATO]"
    return data


def _placeholders(n):
    return ",".join(["?"] * n)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTATTI DISCENDENTI ESTESI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/descendant-contacts")
def list_descendant_contacts(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rc_descendant_contacts WHERE candidate_id = ? ORDER BY created_at DESC",
        (cid,),
    ).fetchall()
    conn.close()
    return {"contacts": [_filter_recaps(dict(r), user) for r in rows]}


@router.post("/candidates/{cid}/descendant-contacts")
def create_descendant_contact(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    _cols = ["candidate_id","nome","cognome","nome_precedente",
        "rapporto_parentela_presunto","rapporto_parentela_verificato","ramo_familiare",
        "comune_residenza","indirizzo_postale","email","pec","telefono","altro_canale",
        "profilo_pubblico_url","preferenza_contatto","lingua","note",
        "stato_verifica","fonte_contatto","url_fonte","titolo_pagina_fonte",
        "data_consultazione_fonte","operatore_inserimento","data_reperimento",
        "data_ultima_verifica","livello_attendibilita",
        "consenso_acquisito","data_consenso","modalita_consenso",
        "opposizione_contatto","richiesta_non_contattare","cancellazione_limitazione",
        "visibilita_limitata","created_at","updated_at","created_by"]
    _vals = [cid, data.get("nome",""), data.get("cognome",""), data.get("nome_precedente"),
        data.get("rapporto_parentela_presunto"), data.get("rapporto_parentela_verificato"),
        data.get("ramo_familiare"),
        data.get("comune_residenza"), data.get("indirizzo_postale"),
        data.get("email"), data.get("pec"), data.get("telefono"), data.get("altro_canale"),
        data.get("profilo_pubblico_url"), data.get("preferenza_contatto"),
        data.get("lingua","it"), data.get("note"),
        data.get("stato_verifica","NON_VERIFICATO"),
        data.get("fonte_contatto"), data.get("url_fonte"), data.get("titolo_pagina_fonte"),
        data.get("data_consultazione_fonte"), user.get("username",""), data.get("data_reperimento",now[:10]),
        data.get("data_ultima_verifica"), data.get("livello_attendibilita","da_verificare"),
        data.get("consenso_acquisito",0), data.get("data_consenso"), data.get("modalita_consenso"),
        data.get("opposizione_contatto",0), data.get("richiesta_non_contattare",0),
        data.get("cancellazione_limitazione"),
        data.get("visibilita_limitata",1), now, now, user.get("id")]
    cur = conn.execute(
        f"INSERT INTO rc_descendant_contacts ({','.join(_cols)}) VALUES ({_placeholders(len(_cols))})",
        _vals,
    )
    did = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "descendant_contact", did, next_val={"candidate_id": cid})
    return {"id": did}


@router.put("/descendant-contacts/{did}")
def update_descendant_contact(request: Request, did: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_descendant_contacts WHERE id = ?", (did,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Contatto non trovato")
    now = _now()
    updatable = ["nome", "cognome", "nome_precedente", "rapporto_parentela_presunto",
                 "rapporto_parentela_verificato", "ramo_familiare", "comune_residenza",
                 "indirizzo_postale", "email", "pec", "telefono", "altro_canale",
                 "profilo_pubblico_url", "preferenza_contatto", "lingua", "note",
                 "stato_verifica", "fonte_contatto", "url_fonte", "titolo_pagina_fonte",
                 "data_consultazione_fonte", "data_ultima_verifica", "livello_attendibilita",
                 "consenso_acquisito", "data_consenso", "modalita_consenso",
                 "opposizione_contatto", "richiesta_non_contattare", "cancellazione_limitazione",
                 "visibilita_limitata"]
    sets = []
    vals = []
    for f in updatable:
        if f in data:
            sets.append(f"{f} = ?")
            vals.append(data[f])
    sets.append("updated_at = ?")
    vals.append(now)
    vals.append(did)
    conn.execute(f"UPDATE rc_descendant_contacts SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    _audit(user, "update", "descendant_contact", did, prev=dict(existing))
    return {"ok": True}


@router.delete("/descendant-contacts/{did}")
def delete_descendant_contact(request: Request, did: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_descendant_contacts WHERE id = ?", (did,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Contatto non trovato")
    conn.execute("DELETE FROM rc_descendant_contacts WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    _audit(user, "delete", "descendant_contact", did, prev=dict(existing))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# CONTATTI ISTITUZIONALI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/institutional-contacts")
def list_institutional_contacts(request: Request):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:institutional:read"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_institutional_contacts ORDER BY ente").fetchall()
    conn.close()
    return {"contacts": [dict(r) for r in rows]}


@router.post("/institutional-contacts")
def create_institutional_contact(request: Request, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:institutional:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    _cols = ["ente","ministero_amministrazione","dipartimento","direzione_generale",
        "ufficio","archivio","sede","indirizzo","email","pec","telefono",
        "sito_ufficiale","pagina_procedura","referente_nome","referente_cognome",
        "referente_qualifica","referente_telefono_interno","orari",
        "ambito_competenza","territori_competenza","tipi_riconoscimento_gestiti",
        "modalita_preferita_contatto","fonte_recapito","url_fonte_ufficiale",
        "data_ultima_verifica","stato","note","created_at","updated_at","created_by"]
    _vals = [data.get("ente",""), data.get("ministero_amministrazione"),
        data.get("dipartimento"), data.get("direzione_generale"),
        data.get("ufficio"), data.get("archivio"), data.get("sede"), data.get("indirizzo"),
        data.get("email"), data.get("pec"), data.get("telefono"),
        data.get("sito_ufficiale"), data.get("pagina_procedura"),
        data.get("referente_nome"), data.get("referente_cognome"),
        data.get("referente_qualifica"), data.get("referente_telefono_interno"),
        data.get("orari"), data.get("ambito_competenza"), data.get("territori_competenza"),
        data.get("tipi_riconoscimento_gestiti"), data.get("modalita_preferita_contatto"),
        data.get("fonte_recapito"), data.get("url_fonte_ufficiale"),
        data.get("data_ultima_verifica"), data.get("stato","non_verificato"),
        data.get("note"), now, now, user.get("id")]
    cur = conn.execute(
        f"INSERT INTO rc_institutional_contacts ({','.join(_cols)}) VALUES ({_placeholders(len(_cols))})",
        _vals,
    )
    iid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "institutional_contact", iid)
    return {"id": iid}


@router.put("/institutional-contacts/{iid}")
def update_institutional_contact(request: Request, iid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:institutional:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_institutional_contacts WHERE id = ?", (iid,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Contatto non trovato")
    now = _now()
    updatable = [f for f in data.keys()
                 if f in {r["name"] for r in conn.execute("PRAGMA table_info(rc_institutional_contacts)").fetchall()}
                 and f not in ("id", "created_at", "created_by")]
    sets = []
    vals = []
    for f in updatable:
        sets.append(f"{f} = ?")
        vals.append(data[f])
    sets.append("updated_at = ?")
    vals.append(now)
    vals.append(iid)
    conn.execute(f"UPDATE rc_institutional_contacts SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    _audit(user, "update", "institutional_contact", iid, prev=dict(existing))
    return {"ok": True}


@router.delete("/institutional-contacts/{iid}")
def delete_institutional_contact(request: Request, iid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:institutional:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_institutional_contacts WHERE id = ?", (iid,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Contatto non trovato")
    conn.execute("DELETE FROM rc_institutional_contacts WHERE id = ?", (iid,))
    conn.commit()
    conn.close()
    _audit(user, "delete", "institutional_contact", iid, prev=dict(existing))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# PRATICHE ESTESE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/practices")
def list_practices(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.*, r.denominazione as recognition_name,
                  ic.ente as institutional_ente
           FROM rc_practices p
           LEFT JOIN rc_recognition_types r ON p.recognition_type_id = r.id
           LEFT JOIN rc_institutional_contacts ic ON p.institutional_contact_id = ic.id
           WHERE p.candidate_id = ? ORDER BY p.created_at DESC""",
        (cid,),
    ).fetchall()
    conn.close()
    return {"practices": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/practices")
def create_practice(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:case:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    _cols = ["candidate_id","recognition_type_id","descendant_contact_id",
        "institutional_contact_id","protocollo","data_invio",
        "modalita_trasmissione","ufficio_assegnatario",
        "responsabile_procedimento","data_apertura","termine_previsto",
        "stato","richieste_integrazione","esito","decreto_provvedimento",
        "data_esito","data_consegna_attestato","note_cerimonia",
        "pronto_invio","validato_da_revisore","motivazione_eccezione",
        "created_at","updated_at","created_by"]
    _vals = [cid, data.get("recognition_type_id"), data.get("descendant_contact_id"),
        data.get("institutional_contact_id"), data.get("protocollo"),
        data.get("data_invio"), data.get("modalita_trasmissione"),
        data.get("ufficio_assegnatario"), data.get("responsabile_procedimento"),
        data.get("data_apertura"), data.get("termine_previsto"),
        data.get("stato","in_preparazione"), data.get("richieste_integrazione"),
        data.get("esito"), data.get("decreto_provvedimento"),
        data.get("data_esito"), data.get("data_consegna_attestato"),
        data.get("note_cerimonia"), data.get("pronto_invio",0),
        data.get("validato_da_revisore",0), data.get("motivazione_eccezione"),
        now, now, user.get("id")]
    cur = conn.execute(
        f"INSERT INTO rc_practices ({','.join(_cols)}) VALUES ({_placeholders(len(_cols))})",
        _vals,
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "practice", pid, next_val={"candidate_id": cid})
    return {"id": pid}


@router.put("/practices/{pid}")
def update_practice(request: Request, pid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:case:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_practices WHERE id = ?", (pid,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Pratica non trovata")
    now = _now()
    all_cols = {r["name"] for r in conn.execute("PRAGMA table_info(rc_practices)").fetchall()}
    updatable = [f for f in data.keys() if f in all_cols and f not in ("id", "created_at", "created_by")]
    sets = []
    vals = []
    for f in updatable:
        sets.append(f"{f} = ?")
        vals.append(data[f])
    sets.append("updated_at = ?")
    vals.append(now)
    vals.append(pid)
    conn.execute(f"UPDATE rc_practices SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    _audit(user, "update", "practice", pid, prev=dict(existing))
    return {"ok": True}


@router.post("/practices/{pid}/declare-ready")
def declare_practice_ready(request: Request, pid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:practice:declare_ready"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    practice = conn.execute("SELECT * FROM rc_practices WHERE id = ?", (pid,)).fetchone()
    if not practice:
        conn.close()
        raise HTTPException(404, "Pratica non trovata")
    # Verifica che non ci siano documenti obbligatori mancanti
    missing = conn.execute(
        """SELECT * FROM rc_document_checklists
           WHERE practice_id = ? AND obbligatorietà = 'obbligatorio'
           AND stato_documento IN ('mancante', 'non_valido')""",
        (pid,),
    ).fetchall()
    if missing and not data.get("motivazione_eccezione"):
        conn.close()
        raise HTTPException(400, f"Documenti obbligatori mancanti: {len(missing)}. "
                                 "Fornire motivazione_eccezione per dichiarare pronto nonostante.")
    now = _now()
    conn.execute(
        "UPDATE rc_practices SET pronto_invio = 1, validato_da_revisore = 1, "
        "motivazione_eccezione = ?, updated_at = ? WHERE id = ?",
        (data.get("motivazione_eccezione", ""), now, pid),
    )
    conn.commit()
    conn.close()
    _audit(user, "declare_ready", "practice", pid, next_val={"motivazione": data.get("motivazione_eccezione", "")})
    return {"ok": True, "pronto_invio": True}


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENTI DI PRATICA
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/practice-documents")
def list_practice_documents(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rc_practice_documents
           WHERE candidate_id = ? AND archiviato = 0
           ORDER BY created_at DESC""",
        (cid,),
    ).fetchall()
    conn.close()
    docs = [dict(r) for r in rows]
    # Filtra documenti di identita' per utenti non autorizzati
    if not has_permission(user["role"], "rc:doc:view_identity"):
        for d in docs:
            if d.get("categoria_documentale") in ("IDENTITA_CANDIDATO", "STATO_CIVILE"):
                d["file_path"] = "[RISERVATO]"
    return {"documents": docs}


@router.get("/practices/{pid}/documents")
def list_practice_documents_by_practice(request: Request, pid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rc_practice_documents
           WHERE practice_id = ? AND archiviato = 0
           ORDER BY created_at DESC""",
        (pid,),
    ).fetchall()
    conn.close()
    return {"documents": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/practice-documents")
async def upload_practice_document(
    request: Request,
    cid: int,
    file: UploadFile = File(...),
    titolo: str = Form(""),
    descrizione: str = Form(""),
    categoria_documentale: str = Form("ALTRO"),
    data_documento: str = Form(""),
    mittente: str = Form(""),
    destinatario: str = Form(""),
    ente_produttore: str = Form(""),
    fonte: str = Form(""),
    segnatura: str = Form(""),
    protocollo: str = Form(""),
    livello_riservatezza: str = Form("operatore"),
    practice_id: str = Form(""),
    descendant_contact_id: str = Form(""),
    note: str = Form(""),
):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:upload"):
        raise HTTPException(403, "Permesso insufficiente")
    # Validate category
    if categoria_documentale not in DOCUMENT_CATEGORIES:
        raise HTTPException(400, f"Categoria non valida. Valori ammessi: {DOCUMENT_CATEGORIES}")
    # Save file
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = RC_DOC_DIR / safe_name
    file_path.write_bytes(content)
    now = _now()
    conn = get_conn()
    pid = int(practice_id) if practice_id else None
    dcid = int(descendant_contact_id) if descendant_contact_id else None
    _cols = ["practice_id","candidate_id","descendant_contact_id",
        "titolo","descrizione","categoria_documentale",
        "filename_originale","file_path","formato_mime","dimensione",
        "checksum","autore_caricamento","data_caricamento",
        "data_documento","mittente","destinatario","ente_produttore",
        "fonte","segnatura","protocollo","livello_riservatezza",
        "stato_verifica","versione","note","created_at","updated_at","created_by"]
    _vals = [pid, cid, dcid,
        titolo or file.filename, descrizione, categoria_documentale,
        file.filename, str(file_path), file.content_type, len(content),
        checksum, user.get("username",""), now,
        data_documento, mittente, destinatario, ente_produttore,
        fonte, segnatura, protocollo, livello_riservatezza,
        "non_verificata", 1, note, now, now, user.get("id")]
    cur = conn.execute(
        f"INSERT INTO rc_practice_documents ({','.join(_cols)}) VALUES ({_placeholders(len(_cols))})",
        _vals,
    )
    did = cur.lastrowid
    # Save initial version
    conn.execute(
        """INSERT INTO rc_document_versions
           (document_id, versione, file_path, checksum, dimensione,
            motivazione_sostituzione, created_at, created_by)
           VALUES (?, 1, ?, ?, ?, 'Caricamento iniziale', ?, ?)""",
        (did, str(file_path), checksum, len(content), now, user.get("id")),
    )
    conn.commit()
    conn.close()
    _audit(user, "upload", "practice_document", did, next_val={"candidate_id": cid, "filename": file.filename})
    return {"id": did, "checksum": checksum, "size": len(content)}


@router.post("/practice-documents/{did}/ocr")
def ocr_practice_document(request: Request, did: int):
    """Esegue OCR su un documento di pratica usando Mistral OCR.
    Supporta immagini (JPG, PNG, TIFF) e PDF multi-pagina.
    Passa dal Compliance Gate prima di elaborare."""
    import base64
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:verify"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    doc = conn.execute("SELECT * FROM rc_practice_documents WHERE id = ?", (did,)).fetchone()
    if not doc:
        conn.close()
        raise HTTPException(404, "Documento non trovato")
    d = dict(doc)

    # Compliance Gate check
    from compliance_gate import evaluate as compliance_eval, AUTHORIZATION_REQUIRED
    cat = (d.get("categoria_documentale") or "").upper()
    has_health = any(k in cat for k in ("CERTIFICATO_MORTE", "REFERTO", "CARTELLA", "OSPEDALE", "SANITA"))
    resource = {
        "record_id": str(did),
        "classification": "AUTHORIZATION_REQUIRED" if has_health else "PUBLIC_DOWNLOAD",
        "domain": "local",
        "provider": "local_upload",
        "has_health_data": has_health,
        "life_status": "deceased",
    }
    gate_result = compliance_eval(resource, "RUN_OCR", user.get("role", "operator"))
    if gate_result["decision"] in ("DENY", "REQUIRE_AUTHORIZATION", "REQUIRE_REVIEW"):
        conn.close()
        raise HTTPException(
            403 if gate_result["decision"] == "DENY" else 403,
            f"Compliance Gate: {gate_result['decision']} — {gate_result['reason']}"
        )

    file_path = Path(d["file_path"])
    if not file_path.exists():
        conn.close()
        raise HTTPException(404, "File non trovato sul disco")
    # Get Mistral client
    try:
        from extractor import _get_mistral_client
        client = _get_mistral_client()
    except Exception as e:
        conn.close()
        raise HTTPException(500, f"Errore init Mistral client: {e}")
    ext = file_path.suffix.lower()
    ocr_text = ""
    pages_count = 0
    try:
        if ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp"):
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext[1:]}"
            b64 = base64.b64encode(file_path.read_bytes()).decode()
            result = client.ocr.process(
                model="mistral-ocr-latest",
                document={"type": "image_url", "image_url": f"data:{mime};base64,{b64}"},
            )
            if result.pages:
                ocr_text = result.pages[0].markdown or ""
            pages_count = 1
        elif ext == ".pdf":
            import fitz
            pdf_doc = fitz.open(str(file_path))
            parts = []
            for i in range(pdf_doc.page_count):
                page = pdf_doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                b64 = base64.b64encode(pix.tobytes("png")).decode()
                result = client.ocr.process(
                    model="mistral-ocr-latest",
                    document={"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
                )
                if result.pages:
                    parts.append(result.pages[0].markdown or "")
            pdf_doc.close()
            ocr_text = "\n\n---\n\n".join(parts)
            pages_count = len(parts)
        else:
            conn.close()
            raise HTTPException(400, f"Formato non supportato per OCR: {ext}")
        # Log usage
        try:
            from credits import log_mistral_ocr
            log_mistral_ocr(pages_count)
        except Exception:
            pass
        # Save OCR text to DB
        now = _now()
        conn.execute(
            "UPDATE rc_practice_documents SET ocr_text = ?, ocr_status = 'done', ocr_pages = ?, updated_at = ? WHERE id = ?",
            (ocr_text, pages_count, now, did),
        )
        conn.commit()
        conn.close()
        _audit(user, "ocr", "practice_document", did, next_val={"pages": pages_count, "chars": len(ocr_text)})
        return {"ok": True, "ocr_text": ocr_text, "pages": pages_count, "chars": len(ocr_text)}
    except Exception as e:
        now = _now()
        conn.execute(
            "UPDATE rc_practice_documents SET ocr_status = 'error', updated_at = ? WHERE id = ?",
            (now, did),
        )
        conn.commit()
        conn.close()
        raise HTTPException(500, f"Errore OCR: {e}")


@router.get("/practice-documents/{did}/ocr")
def get_ocr_text(request: Request, did: int):
    """Recupera il testo OCR di un documento di pratica."""
    user = require_auth(request)
    conn = get_conn()
    doc = conn.execute("SELECT ocr_text, ocr_status, ocr_pages FROM rc_practice_documents WHERE id = ?", (did,)).fetchone()
    if not doc:
        conn.close()
        raise HTTPException(404, "Documento non trovato")
    conn.close()
    return {"ocr_text": doc["ocr_text"] or "", "ocr_status": doc["ocr_status"] or "pending", "ocr_pages": doc["ocr_pages"]}


@router.put("/practice-documents/{did}/verify")
def verify_practice_document(request: Request, did: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:verify"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_practice_documents WHERE id = ?", (did,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Documento non trovato")
    now = _now()
    conn.execute(
        "UPDATE rc_practice_documents SET stato_verifica = ?, updated_at = ? WHERE id = ?",
        (data.get("stato_verifica", "verificata"), now, did),
    )
    conn.commit()
    conn.close()
    _audit(user, "verify", "practice_document", did,
           prev=dict(existing), next_val={"stato": data.get("stato_verifica")})
    return {"ok": True}


@router.post("/practice-documents/{did}/replace")
async def replace_practice_document(
    request: Request,
    did: int,
    file: UploadFile = File(...),
    motivazione: str = Form(...),
):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:upload"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_practice_documents WHERE id = ?", (did,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Documento non trovato")
    d = dict(existing)
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_v{d['versione'] + 1}_{file.filename}"
    file_path = RC_DOC_DIR / safe_name
    file_path.write_bytes(content)
    now = _now()
    new_version = d["versione"] + 1
    # Save old version
    conn.execute(
        """INSERT INTO rc_document_versions
           (document_id, versione, file_path, checksum, dimensione,
            motivazione_sostituzione, sostituito_da, created_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (did, d["versione"], d["file_path"], d["checksum"], d["dimensione"],
         motivazione, str(file_path), now, user.get("id")),
    )
    # Update document
    conn.execute(
        """UPDATE rc_practice_documents SET
           filename_originale = ?, file_path = ?, formato_mime = ?,
           dimensione = ?, checksum = ?, versione = ?,
           stato_verifica = 'non_verificata', updated_at = ?
           WHERE id = ?""",
        (file.filename, str(file_path), file.content_type,
         len(content), checksum, new_version, now, did),
    )
    conn.commit()
    conn.close()
    _audit(user, "replace", "practice_document", did,
           prev={"versione": d["versione"]}, next_val={"versione": new_version, "motivazione": motivazione})
    return {"id": did, "versione": new_version, "checksum": checksum}


@router.get("/practice-documents/{did}/versions")
def list_document_versions(request: Request, did: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rc_document_versions WHERE document_id = ? ORDER BY versione DESC",
        (did,),
    ).fetchall()
    conn.close()
    return {"versions": [dict(r) for r in rows]}


@router.get("/practice-documents/{did}/download")
def download_practice_document(request: Request, did: int):
    user = require_auth(request)
    conn = get_conn()
    doc = conn.execute("SELECT * FROM rc_practice_documents WHERE id = ?", (did,)).fetchone()
    conn.close()
    if not doc:
        raise HTTPException(404, "Documento non trovato")
    d = dict(doc)
    if d.get("categoria_documentale") in ("IDENTITA_CANDIDATO", "STATO_CIVILE"):
        if not has_permission(user["role"], "rc:doc:view_identity"):
            raise HTTPException(403, "Non autorizzato a scaricare documenti di identita'")
    return FileResponse(d["file_path"], filename=d["filename_originale"])


@router.put("/practice-documents/{did}/archive")
def archive_practice_document(request: Request, did: int, data: dict = Body(default={})):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:verify"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    conn.execute(
        "UPDATE rc_practice_documents SET archiviato = 1, note = ?, updated_at = ? WHERE id = ?",
        (data.get("motivazione", ""), now, did),
    )
    conn.commit()
    conn.close()
    _audit(user, "archive", "practice_document", did, next_val={"motivazione": data.get("motivazione", "")})
    return {"ok": True}


@router.delete("/practice-documents/{did}")
def delete_practice_document(request: Request, did: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:doc:delete"):
        raise HTTPException(403, "Permesso insufficiente. Solo admin puo' cancellare definitivamente.")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_practice_documents WHERE id = ?", (did,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Documento non trovato")
    d = dict(existing)
    # Delete file
    try:
        Path(d["file_path"]).unlink(missing_ok=True)
    except:
        pass
    conn.execute("DELETE FROM rc_document_versions WHERE document_id = ?", (did,))
    conn.execute("DELETE FROM rc_practice_documents WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    _audit(user, "delete", "practice_document", did, prev=d)
    return {"ok": True}


@router.delete("/practices/{pid}")
def delete_practice(request: Request, pid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:practice:delete"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_practices WHERE id = ?", (pid,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Pratica non trovata")
    d = dict(existing)
    now = datetime.now().isoformat()
    # Cascade: delete documents, checklist, deadlines, communications
    docs = conn.execute("SELECT id, file_path FROM rc_practice_documents WHERE practice_id = ?", (pid,)).fetchall()
    for doc in docs:
        try:
            Path(doc["file_path"]).unlink(missing_ok=True)
        except:
            pass
        conn.execute("DELETE FROM rc_document_versions WHERE document_id = ?", (doc["id"],))
    conn.execute("DELETE FROM rc_practice_documents WHERE practice_id = ?", (pid,))
    conn.execute("DELETE FROM rc_document_checklists WHERE practice_id = ?", (pid,))
    conn.execute("DELETE FROM rc_practice_deadlines WHERE practice_id = ?", (pid,))
    conn.execute("DELETE FROM rc_communications WHERE practice_id = ?", (pid,))
    conn.execute("DELETE FROM rc_descendant_packages WHERE practice_id = ?", (pid,))
    conn.execute("DELETE FROM rc_practices WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    _audit(user, "delete", "practice", pid, prev=d)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# CHECKLIST DOCUMENTI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/practices/{pid}/checklist")
def get_checklist(request: Request, pid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:checklist:read"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rc_document_checklists WHERE practice_id = ? ORDER BY id",
        (pid,),
    ).fetchall()
    conn.close()
    return {"checklist": [dict(r) for r in rows]}


@router.post("/practices/{pid}/checklist")
def add_checklist_item(request: Request, pid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:checklist:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_document_checklists
           (recognition_type_id, practice_id, nome_documento, descrizione,
            obbligatorietà, soggetto_produttore, ente_reperizione,
            modello_disponibile, stato_documento, motivazione_invalidita,
            data_richiesta, scadenza, operatore_responsabile,
            documento_collegato_id, created_at, updated_at)
           VALUES (?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?)""",
        (data.get("recognition_type_id"), pid,
         data.get("nome_documento", ""), data.get("descrizizione", ""),
         data.get("obbligatorietà", "obbligatorio"),
         data.get("soggetto_produttore"), data.get("ente_reperizione"),
         data.get("modello_disponibile"),
         data.get("stato_documento", "mancante"),
         data.get("motivazione_invalidita"),
         data.get("data_richiesta"), data.get("scadenza"),
         data.get("operatore_responsabile"),
         data.get("documento_collegato_id"),
         now, now),
    )
    clid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "checklist_item", clid, next_val={"practice_id": pid})
    return {"id": clid}


@router.put("/checklist/{clid}")
def update_checklist_item(request: Request, clid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:checklist:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_document_checklists WHERE id = ?", (clid,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Item non trovato")
    now = _now()
    all_cols = {r["name"] for r in conn.execute("PRAGMA table_info(rc_document_checklists)").fetchall()}
    updatable = [f for f in data.keys() if f in all_cols and f not in ("id", "created_at")]
    sets = []
    vals = []
    for f in updatable:
        sets.append(f"{f} = ?")
        vals.append(data[f])
    sets.append("updated_at = ?")
    vals.append(now)
    vals.append(clid)
    conn.execute(f"UPDATE rc_document_checklists SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    _audit(user, "update", "checklist_item", clid, prev=dict(existing))
    return {"ok": True}


@router.delete("/checklist/{clid}")
def delete_checklist_item(request: Request, clid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:checklist:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    conn.execute("DELETE FROM rc_document_checklists WHERE id = ?", (clid,))
    conn.commit()
    conn.close()
    _audit(user, "delete", "checklist_item", clid)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# COMUNICAZIONI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/communications")
def list_communications(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rc_communications WHERE candidate_id = ?
           ORDER BY data_ora_effettiva DESC, created_at DESC""",
        (cid,),
    ).fetchall()
    conn.close()
    return {"communications": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/communications")
def create_communication(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    thread_id = data.get("thread_id") or secrets.token_hex(8)
    _cols = ["candidate_id","descendant_contact_id","practice_id",
        "institutional_contact_id","document_id","thread_id",
        "parent_communication_id","tipo","direzione","mittente",
        "destinatari","copia_conoscenza","oggetto","contenuto",
        "allegati","data_ora_effettiva","data_ora_registrazione",
        "operatore","stato","ricevuta_consegna","protocollo",
        "risposta_attesa","data_entro_rispondere","esito","note",
        "created_at","updated_at","created_by"]
    _vals = [cid, data.get("descendant_contact_id"), data.get("practice_id"),
        data.get("institutional_contact_id"), data.get("document_id"),
        thread_id, data.get("parent_communication_id"),
        data.get("tipo","nota_interna"), data.get("direzione","uscita"),
        data.get("mittente"), data.get("destinatari"), data.get("copia_conoscenza"),
        data.get("oggetto"), data.get("contenuto"), data.get("allegati"),
        data.get("data_ora_effettiva",now), now,
        user.get("username",""), data.get("stato","bozza"),
        data.get("ricevuta_consegna"), data.get("protocollo"),
        data.get("risposta_attesa",0), data.get("data_entro_rispondere"),
        data.get("esito"), data.get("note"),
        now, now, user.get("id")]
    cur = conn.execute(
        f"INSERT INTO rc_communications ({','.join(_cols)}) VALUES ({_placeholders(len(_cols))})",
        _vals,
    )
    comm_id = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "communication", comm_id, next_val={"candidate_id": cid, "thread_id": thread_id})
    return {"id": comm_id, "thread_id": thread_id}


@router.put("/communications/{comm_id}")
def update_communication(request: Request, comm_id: int, data: dict = Body(...)):
    user = require_auth(request)
    conn = get_conn()
    existing = conn.execute("SELECT * FROM rc_communications WHERE id = ?", (comm_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Comunicazione non trovata")
    # Approvazione richiede permesso specifico
    if data.get("stato") == "inviata" and not has_permission(user["role"], "rc:comm:approve"):
        conn.close()
        raise HTTPException(403, "Permesso insufficiente per approvare l'invio")
    now = _now()
    all_cols = {r["name"] for r in conn.execute("PRAGMA table_info(rc_communications)").fetchall()}
    updatable = [f for f in data.keys() if f in all_cols and f not in ("id", "created_at", "created_by")]
    sets = []
    vals = []
    for f in updatable:
        sets.append(f"{f} = ?")
        vals.append(data[f])
    sets.append("updated_at = ?")
    vals.append(now)
    vals.append(comm_id)
    conn.execute(f"UPDATE rc_communications SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    _audit(user, "update", "communication", comm_id, prev=dict(existing))
    return {"ok": True}


@router.get("/communications/thread/{thread_id}")
def list_thread_communications(request: Request, thread_id: str):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rc_communications WHERE thread_id = ? ORDER BY data_ora_effettiva",
        (thread_id,),
    ).fetchall()
    conn.close()
    return {"communications": [dict(r) for r in rows]}


# ═══════════════════════════════════════════════════════════════════════════════
# SCADENZE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/deadlines")
def list_deadlines(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rc_practice_deadlines WHERE candidate_id = ? AND risolta = 0 ORDER BY data_scadenza",
        (cid,),
    ).fetchall()
    conn.close()
    return {"deadlines": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/deadlines")
def create_deadline(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_practice_deadlines
           (practice_id, candidate_id, tipo_scadenza, data_scadenza,
            descrizione, created_at, created_by)
           VALUES (?,?,?,?, ?,?,?)""",
        (data.get("practice_id"), cid, data.get("tipo_scadenza", ""),
         data.get("data_scadenza"), data.get("descrizione", ""),
         now, user.get("id")),
    )
    did = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "deadline", did, next_val={"candidate_id": cid})
    return {"id": did}


@router.put("/deadlines/{did}/resolve")
def resolve_deadline(request: Request, did: int, data: dict = Body(...)):
    user = require_auth(request)
    conn = get_conn()
    now = _now()
    conn.execute(
        "UPDATE rc_practice_deadlines SET risolta = 1, data_risoluzione = ?, note = ? WHERE id = ?",
        (now, data.get("note", ""), did),
    )
    conn.commit()
    conn.close()
    _audit(user, "resolve", "deadline", did)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# TIMELINE PRATICA
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/timeline")
def get_timeline(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    events = []
    # Audit log
    for r in conn.execute(
        "SELECT * FROM rc_audit_log WHERE entita_id = ? OR (entita = 'candidate' AND entita_id = ?) ORDER BY created_at",
        (cid, cid),
    ).fetchall():
        events.append({"tipo": "audit", "data": dict(r)["created_at"], "descrizione": f"{dict(r)['azione']} {dict(r)['entita']}", "autore": dict(r).get("username", ""), "dettaglio": dict(r)})
    # State transitions
    for r in conn.execute(
        "SELECT * FROM rc_state_transitions WHERE candidate_id = ? ORDER BY data_ora",
        (cid,),
    ).fetchall():
        d = dict(r)
        events.append({"tipo": "transizione", "data": d.get("data_ora", ""), "descrizione": f"Stato: {d.get('stato_precedente', '')} -> {d.get('stato_successivo', '')}", "autore": d.get("autore", "")})
    # Sources
    for r in conn.execute(
        "SELECT * FROM rc_sources WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "fonte", "data": dict(r)["created_at"], "descrizione": f"Fonte aggiunta: {dict(r).get('titolo', '')}", "autore": ""})
    # Assessments
    for r in conn.execute(
        "SELECT * FROM rc_recognition_assessments WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "valutazione", "data": dict(r)["created_at"], "descrizione": f"Valutazione: {dict(r).get('riconoscimento_ipotizzato', '')}", "autore": dict(r).get("valutatore", "")})
    # Descendant contacts
    for r in conn.execute(
        "SELECT * FROM rc_descendant_contacts WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "discendente", "data": dict(r)["created_at"], "descrizione": f"Contatto discendente: {dict(r).get('cognome', '')} {dict(r).get('nome', '')} ({dict(r).get('stato_verifica', '')})", "autore": dict(r).get("operatore_inserimento", "")})
    # Communications
    for r in conn.execute(
        "SELECT * FROM rc_communications WHERE candidate_id = ? ORDER BY data_ora_effettiva",
        (cid,),
    ).fetchall():
        events.append({"tipo": "comunicazione", "data": dict(r).get("data_ora_effettiva", dict(r)["created_at"]), "descrizione": f"Comunicazione {dict(r).get('tipo', '')} ({dict(r).get('direzione', '')}): {dict(r).get('oggetto', '')}", "autore": dict(r).get("operatore", "")})
    # Documents
    for r in conn.execute(
        "SELECT * FROM rc_practice_documents WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "documento", "data": dict(r)["created_at"], "descrizione": f"Documento: {dict(r).get('titolo', '')} ({dict(r).get('categoria_documentale', '')})", "autore": dict(r).get("autore_caricamento", "")})
    # Practices
    for r in conn.execute(
        "SELECT * FROM rc_practices WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "pratica", "data": dict(r)["created_at"], "descrizione": f"Pratica creata: {dict(r).get('stato', '')}", "autore": ""})
    # AI analyses
    for r in conn.execute(
        "SELECT * FROM rc_ai_analyses WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "ai_analysis", "data": dict(r)["created_at"], "descrizione": "Analisi AI generata", "autore": dict(r).get("modello_ai", "")})
    # Packages
    for r in conn.execute(
        "SELECT * FROM rc_descendant_packages WHERE candidate_id = ? ORDER BY created_at",
        (cid,),
    ).fetchall():
        events.append({"tipo": "pacchetto", "data": dict(r)["created_at"], "descrizione": f"Pacchetto discendente v{dict(r).get('versione', 1)} generato", "autore": dict(r).get("approvatore", "")})
    conn.close()
    # Sort by date
    events.sort(key=lambda e: e.get("data", ""))
    return {"timeline": events}


# ═══════════════════════════════════════════════════════════════════════════════
# RICERCA GLOBALE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/search")
def global_search(request: Request, q: str = "", tipo: str = ""):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:search:global"):
        raise HTTPException(403, "Permesso insufficiente")
    if not q or len(q) < 2:
        return {"results": []}
    conn = get_conn()
    results = []
    like = f"%{q}%"
    can_view_recaps = has_permission(user["role"], "rc:contact:view_recaps")

    # Candidati
    if not tipo or tipo == "candidato":
        rows = conn.execute(
            "SELECT id, cognome, nome, grado, conflitto, stato FROM rc_candidates WHERE cognome LIKE ? OR nome LIKE ? OR note_interne LIKE ? LIMIT 20",
            (like, like, like),
        ).fetchall()
        for r in rows:
            results.append({"tipo": "candidato", "id": r["id"], "label": f"{r['cognome']} {r['nome']}", "stato": r["stato"], "url": f"/riconoscimenti?cand={r['id']}"})

    # Discendenti
    if not tipo or tipo == "discendente":
        rows = conn.execute(
            "SELECT id, candidate_id, nome, cognome, stato_verifica FROM rc_descendant_contacts WHERE cognome LIKE ? OR nome LIKE ? LIMIT 20",
            (like, like),
        ).fetchall()
        for r in rows:
            results.append({"tipo": "discendente", "id": r["id"], "label": f"{r['cognome']} {r['nome']} ({r['stato_verifica']})", "candidate_id": r["candidate_id"]})

    # Uffici istituzionali
    if not tipo or tipo == "ufficio":
        rows = conn.execute(
            "SELECT id, ente, ufficio, referente_nome, referente_cognome FROM rc_institutional_contacts WHERE ente LIKE ? OR ufficio LIKE ? OR referente_nome LIKE ? OR referente_cognome LIKE ? LIMIT 20",
            (like, like, like, like),
        ).fetchall()
        for r in rows:
            results.append({"tipo": "ufficio", "id": r["id"], "label": f"{r['ente']} - {r.get('ufficio', '')} {r.get('referente_cognome', '')}"})

    # Pratiche per protocollo
    if not tipo or tipo == "protocollo":
        rows = conn.execute(
            "SELECT id, candidate_id, protocollo, stato FROM rc_practices WHERE protocollo LIKE ? LIMIT 20",
            (like,),
        ).fetchall()
        for r in rows:
            results.append({"tipo": "protocollo", "id": r["id"], "label": f"Protocollo: {r['protocollo']} (pratica {r['id']})", "candidate_id": r["candidate_id"]})

    # Documenti per segnatura
    if not tipo or tipo == "documento":
        rows = conn.execute(
            "SELECT id, candidate_id, titolo, categoria_documentale, segnatura FROM rc_practice_documents WHERE titolo LIKE ? OR segnatura LIKE ? OR protocollo LIKE ? LIMIT 20",
            (like, like, like),
        ).fetchall()
        for r in rows:
            results.append({"tipo": "documento", "id": r["id"], "label": f"Doc: {r['titolo']} ({r['categoria_documentale']})", "candidate_id": r["candidate_id"]})

    conn.close()
    return {"results": results, "total": len(results)}


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD ESTESA
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard-ext")
def dashboard_ext(request: Request):
    user = require_auth(request)
    conn = get_conn()
    now = datetime.now()
    in_30_days = (now + timedelta(days=30)).isoformat()

    stats = {}
    # Candidati da verificare
    stats["candidati_da_verificare"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_candidates WHERE livello_certezza = 'da_verificare' AND stato != 'RICONOSCIMENTO_GIA_CONCESSO'"
    ).fetchone()["c"]
    # Valutazioni storiche pendenti
    stats["valutazioni_storiche_pendenti"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_recognition_assessments WHERE validazione_storica = 0"
    ).fetchone()["c"]
    # Valutazioni amministrative pendenti
    stats["valutazioni_ammin_pendenti"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_recognition_assessments WHERE validazione_amministrativa = 0"
    ).fetchone()["c"]
    # Discendenti da contattare
    stats["discendenti_da_contattare"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_descendant_contacts WHERE stato_verifica IN ('NON_VERIFICATO', 'DA_VERIFICARE', 'POTENZIALE_DISCENDENTE', 'CONTATTO_DA_APPROVARE')"
    ).fetchone()["c"]
    # Contatti in attesa di risposta
    stats["contatti_in_attesa_risposta"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_descendant_contacts WHERE stato_verifica = 'IN_ATTESA_DI_RISPOSTA'"
    ).fetchone()["c"]
    # Documenti mancanti
    stats["documenti_mancanti"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_document_checklists WHERE stato_documento = 'mancante'"
    ).fetchone()["c"]
    # Pratiche da completare
    stats["pratiche_da_completare"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practices WHERE stato = 'in_preparazione'"
    ).fetchone()["c"]
    # Pratiche pronte per revisione
    stats["pratiche_pronte_revisione"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practices WHERE pronto_invio = 1 AND validato_da_revisore = 0"
    ).fetchone()["c"]
    # Pratiche trasmesse
    stats["pratiche_trasmesse"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practices WHERE stato = 'trasmessa'"
    ).fetchone()["c"]
    # Richieste integrazione aperte
    stats["richieste_integrazione_aperte"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practices WHERE richieste_integrazione IS NOT NULL AND richieste_integrazione != '' AND stato = 'in_attesa_integrazione'"
    ).fetchone()["c"]
    # Scadenze imminenti (30 giorni)
    stats["scadenze_imminenti"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practice_deadlines WHERE risolta = 0 AND data_scadenza <= ?",
        (in_30_days,),
    ).fetchone()["c"]
    # Pratiche concluse
    stats["pratiche_concluse"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practices WHERE stato IN ('conclusa', 'archiviata')"
    ).fetchone()["c"]
    # Riconoscimenti concessi
    stats["riconoscimenti_concessi"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_candidates WHERE stato = 'RICONOSCIMENTO_GIA_CONCESSO'"
    ).fetchone()["c"]
    # Pratiche respinte
    stats["pratiche_respinte"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_practices WHERE stato = 'respinta'"
    ).fetchone()["c"]
    # Comunicazioni bozza
    stats["comunicazioni_bozza"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_communications WHERE stato = 'bozza'"
    ).fetchone()["c"]
    # Comunicazioni da approvare
    stats["comunicazioni_da_approvare"] = conn.execute(
        "SELECT COUNT(*) as c FROM rc_communications WHERE stato = 'da_approvare'"
    ).fetchone()["c"]

    conn.close()
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAZIONE PACCHETTO DISCENDENTE
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/candidates/{cid}/generate-descendant-package")
def generate_descendant_package(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:pkg:generate_descendant"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    cand = conn.execute("SELECT * FROM rc_candidates WHERE id = ?", (cid,)).fetchone()
    if not cand:
        conn.close()
        raise HTTPException(404, "Candidato non trovato")
    cand = dict(cand)
    # Get data
    sources = [dict(r) for r in conn.execute("SELECT * FROM rc_sources WHERE candidate_id = ?", (cid,)).fetchall()]
    events = [dict(r) for r in conn.execute("SELECT * FROM rc_historical_events WHERE candidate_id = ?", (cid,)).fetchall()]
    assessments = [dict(r) for r in conn.execute(
        "SELECT a.*, r.denominazione as recognition_name FROM rc_recognition_assessments a LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id WHERE a.candidate_id = ?", (cid,)
    ).fetchall()]
    docs = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_practice_documents WHERE candidate_id = ? AND archiviato = 0 AND livello_riservatezza IN ('operatore', 'discendente')", (cid,)
    ).fetchall()]
    checklists = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_document_checklists WHERE practice_id IN (SELECT id FROM rc_practices WHERE candidate_id = ?)", (cid,)
    ).fetchall()]
    # Get version
    existing_pkgs = conn.execute(
        "SELECT COUNT(*) as c FROM rc_descendant_packages WHERE candidate_id = ?", (cid,)
    ).fetchone()["c"]
    version = existing_pkgs + 1
    now = datetime.now()
    token = secrets.token_urlsafe(32)
    token_exp = (now + timedelta(days=30)).isoformat()
    # Generate PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    file_name = f"pacchetto_discendente_{cid}_v{version}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    file_path = RC_PKG_DIR / file_name
    doc = SimpleDocTemplate(str(file_path), pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    # Copertina
    story.append(Paragraph(f"PACCHETTO PRELIMINARE PER IL DISCENDENTE", styles["Title"]))
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(f"Versione: {version}", styles["Normal"]))
    story.append(Paragraph(f"Data generazione: {now.isoformat()}", styles["Normal"]))
    story.append(Paragraph(f"Codice pratica: RC-{cid}-{version}", styles["Normal"]))
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(f"Candidato: {cand['cognome']} {cand['nome']}", styles["Heading2"]))
    story.append(Spacer(1, 1*cm))
    # 1. Lettera di accompagnamento
    story.append(PageBreak())
    story.append(Paragraph("1. LETTERA DI ACCOMPAGNAMENTO", styles["Heading1"]))
    story.append(Paragraph(
        "Gentile Familiare, con la presente trasmettiamo la documentazione preliminare "
        "relativa al procedimento di potenziale riconoscimento del Suo congiunto. "
        "Si precisa che il presente pacchetto non costituisce garanzia di concessione "
        "di alcun riconoscimento. La procedura amministrativa e' potenzialmente "
        "praticabile e sara' necessaria la verifica da parte degli enti competenti.",
        styles["Normal"]))
    # 2. Sintesi del caso
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("2. SINTESI DEL CASO", styles["Heading1"]))
    story.append(Paragraph(f"Soggetto: {cand['cognome']} {cand.get('nome', '')}", styles["Normal"]))
    if cand.get("grado"): story.append(Paragraph(f"Grado: {cand['grado']}", styles["Normal"]))
    if cand.get("conflitto"): story.append(Paragraph(f"Conflitto: {cand['conflitto']}", styles["Normal"]))
    if cand.get("data_nascita"): story.append(Paragraph(f"Data nascita: {cand['data_nascita']}", styles["Normal"]))
    if cand.get("luogo_nascita"): story.append(Paragraph(f"Luogo nascita: {cand['luogo_nascita']}", styles["Normal"]))
    # 3-7. Identita', rapporto, riconoscimento, procedura, dichiarazione
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("3. IDENTITA' DEL CANDIDATO", styles["Heading1"]))
    story.append(Paragraph(f"Il soggetto e' identificato come: {cand['cognome']} {cand.get('nome', '')}", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("4. RAPPORTO FAMILIARE IPOTIZZATO", styles["Heading1"]))
    story.append(Paragraph("Il rapporto di parentela sara' verificato durante il procedimento.", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("5. RICONOSCIMENTO POTENZIALMENTE APPLICABILE", styles["Heading1"]))
    for a in assessments[:3]:
        story.append(Paragraph(f"- {a.get('recognition_name', a.get('riconoscimento_ipotizzato', ''))}", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("6. SPIEGAZIONE PRUDENTE DELLA PROCEDURA", styles["Heading1"]))
    story.append(Paragraph(
        "La procedura amministrativa varia in base al tipo di riconoscimento. "
        "Sara' necessario presentare domanda all'ente competente, corredata della "
        "documentazione di prova. I tempi variano da mesi ad anni.", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("7. DICHIARAZIONE DI ASSENZA DI GARANZIA", styles["Heading1"]))
    story.append(Paragraph(
        "Il presente pacchetto ha valore informativo preliminare. "
        "Nessun riconoscimento e' garantito. La concessione dipende "
        "dalla valutazione esclusiva dell'autorita' competente.", styles["Normal"]))
    # 8. Cronologia
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("8. CRONOLOGIA DOCUMENTATA", styles["Heading1"]))
    for e in events[:10]:
        story.append(Paragraph(f"- {e.get('tipo_evento', '')}: {e.get('descrizione_verificata', '')[:100]}", styles["Normal"]))
    # 9. Fonti
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("9. FONTI CONDIVISIBILI", styles["Heading1"]))
    for s in sources[:10]:
        story.append(Paragraph(f"- {s.get('titolo', '')} ({s.get('ente_conservatore', '')})", styles["Normal"]))
    # 10-11. Documenti
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("10. DOCUMENTI GIA' REPERITI", styles["Heading1"]))
    for d in docs:
        story.append(Paragraph(f"- {d.get('titolo', '')} ({d.get('categoria_documentale', '')})", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("11. DOCUMENTI ANCORA NECESSARI", styles["Heading1"]))
    missing = [c for c in checklists if c.get("stato_documento") == "mancante"]
    for c in missing:
        story.append(Paragraph(f"- {c.get('nome_documento', '')} ({c.get('obbligatorietà', '')})", styles["Normal"]))
    if not missing:
        story.append(Paragraph("Nessun documento specificato come mancante.", styles["Normal"]))
    # 12. Istruzioni parentela
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("12. ISTRUZIONI PER DIMOSTRARE LA PARENTELA", styles["Heading1"]))
    story.append(Paragraph(
        "Sara' necessario fornire: certificati di stato civile, albero genealogico, "
        "documenti d'identita', eventuali deleghe. Gli enti competenti forniranno "
        "i moduli specifici.", styles["Normal"]))
    # 13. Moduli
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("13. MODULI DA COMPILARE", styles["Heading1"]))
    story.append(Paragraph("I moduli ufficiali saranno forniti dall'ente competente.", styles["Normal"]))
    # 14. Privacy
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("14. INFORMATIVA PRIVACY", styles["Heading1"]))
    story.append(Paragraph(
        "I dati personali raccolti saranno trattati ai sensi del GDPR (Reg. UE 2016/679) "
        "e della normativa italiana applicabile. I dati di persone viventi sono protetti "
        "e non saranno diffusi senza consenso.", styles["Normal"]))
    # 15-17. Adesione, consenso, delega
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("15. MODULO DI ADESIONE", styles["Heading1"]))
    story.append(Paragraph("[Da compilare a cura del discendente]", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("16. CONSENSO AL TRATTAMENTO", styles["Heading1"]))
    story.append(Paragraph("[Da compilare a cura del discendente]", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("17. DELEGA (se applicabile)", styles["Heading1"]))
    story.append(Paragraph("[Da compilare se il richiedente delega un terzo]", styles["Normal"]))
    # 18. Contatti
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("18. CONTATTI DEL PROGETTO", styles["Heading1"]))
    story.append(Paragraph("Progetto: Lettere dal Fronte - Vocidalfronte", styles["Normal"]))
    story.append(Paragraph("Email: info@vocidalfronte.local", styles["Normal"]))
    # 19. Modalita' restituzione
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("19. MODALITA' DI RESTITUZIONE", styles["Heading1"]))
    story.append(Paragraph("I documenti possono essere restituiti via PEC o posta ordinaria.", styles["Normal"]))
    # 20. Codice
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("20. CODICE IDENTIFICATIVO PRATICA", styles["Heading1"]))
    story.append(Paragraph(f"RC-{cid}-{version}", styles["Normal"]))
    doc.build(story)
    file_size = file_path.stat().st_size
    checksum = hashlib.sha256(file_path.read_bytes()).hexdigest()
    # Save to DB
    cur = conn.execute(
        """INSERT INTO rc_descendant_packages
           (candidate_id, descendant_contact_id, practice_id, versione,
            file_path, checksum, dimensione, documenti_inclusi, documenti_esclusi,
            dati_personali_presenti, livello_riservatezza, approvatore,
            data_generazione, token_condivisione, token_scadenza,
            created_at, created_by)
           VALUES (?,?,?,?, ?,?,?, ?,?,?, ?,?,?, ?,?,?,?)""",
        (cid, data.get("descendant_contact_id"), data.get("practice_id"),
         version, str(file_path), checksum, file_size,
         json.dumps([d["titolo"] for d in docs], ensure_ascii=False),
         json.dumps([c["nome_documento"] for c in missing], ensure_ascii=False),
         "nome, cognome, data nascita, luogo nascita",
         "discendente", user.get("username", ""),
         now.isoformat(), token, token_exp,
         now.isoformat(), user.get("id")),
    )
    pkg_id = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "generate", "descendant_package", pkg_id,
           next_val={"candidate_id": cid, "versione": version})
    return {"id": pkg_id, "versione": version, "file": file_name, "token": token}


@router.get("/descendant-packages/{pkg_id}/download")
def download_descendant_package(request: Request, pkg_id: int, token: str = ""):
    user = require_auth(request)
    conn = get_conn()
    pkg = conn.execute("SELECT * FROM rc_descendant_packages WHERE id = ?", (pkg_id,)).fetchone()
    conn.close()
    if not pkg:
        raise HTTPException(404, "Pacchetto non trovato")
    d = dict(pkg)
    # Token validation for external access
    if token:
        if d.get("token_condivisione") != token:
            raise HTTPException(403, "Token non valido")
        if d.get("token_scadenza") and datetime.fromisoformat(d["token_scadenza"]) < datetime.now():
            raise HTTPException(403, "Token scaduto")
    else:
        if not has_permission(user["role"], "rc:pkg:generate_descendant"):
            raise HTTPException(403, "Permesso insufficiente")
    return FileResponse(d["file_path"], filename=f"pacchetto_discendente_v{d['versione']}.pdf",
                        media_type="application/pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAZIONE FASCICOLO UFFICIALE CON VALIDAZIONE
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/practices/{pid}/generate-official-dossier")
def generate_official_dossier(request: Request, pid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:pkg:generate_official"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    practice = conn.execute("SELECT * FROM rc_practices WHERE id = ?", (pid,)).fetchone()
    if not practice:
        conn.close()
        raise HTTPException(404, "Pratica non trovata")
    p = dict(practice)
    # Validazione: check documenti obbligatori
    missing = conn.execute(
        """SELECT * FROM rc_document_checklists
           WHERE practice_id = ? AND obbligatorietà = 'obbligatorio'
           AND stato_documento IN ('mancante', 'non_valido')""",
        (pid,),
    ).fetchall()
    if missing and not p.get("motivazione_eccezione"):
        conn.close()
        raise HTTPException(400, f"Impossibile generare: {len(missing)} documenti obbligatori mancanti o non validi. "
                                 "Dichiarare pronto con motivazione eccezione prima di generare.")
    # Check pronto_invio
    if not p.get("pronto_invio"):
        conn.close()
        raise HTTPException(400, "Pratica non dichiarata pronta per l'invio")
    # Get all data
    cand = dict(conn.execute("SELECT * FROM rc_candidates WHERE id = ?", (p["candidate_id"],)).fetchone())
    sources = [dict(r) for r in conn.execute("SELECT * FROM rc_sources WHERE candidate_id = ?", (p["candidate_id"],)).fetchall()]
    events = [dict(r) for r in conn.execute("SELECT * FROM rc_historical_events WHERE candidate_id = ?", (p["candidate_id"],)).fetchall()]
    assessments = [dict(r) for r in conn.execute(
        "SELECT a.*, r.denominazione as recognition_name FROM rc_recognition_assessments a LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id WHERE a.candidate_id = ?", (p["candidate_id"],)
    ).fetchall()]
    docs = [dict(r) for r in conn.execute("SELECT * FROM rc_practice_documents WHERE practice_id = ? AND archiviato = 0", (pid,)).fetchall()]
    checklists = [dict(r) for r in conn.execute("SELECT * FROM rc_document_checklists WHERE practice_id = ?", (pid,)).fetchall()]
    inst_contact = None
    if p.get("institutional_contact_id"):
        inst_row = conn.execute("SELECT * FROM rc_institutional_contacts WHERE id = ?", (p["institutional_contact_id"],)).fetchone()
        if inst_row:
            inst_contact = dict(inst_row)
    conn.close()
    # Generate PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    now = datetime.now()
    file_name = f"fascicolo_ufficiale_{pid}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    file_path = RC_PKG_DIR / file_name
    doc = SimpleDocTemplate(str(file_path), pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("FASCICOLO AMMINISTRATIVO", styles["Title"]))
    story.append(Paragraph(f"Pratica N. {pid}", styles["Heading2"]))
    story.append(Paragraph(f"Data: {now.isoformat()}", styles["Normal"]))
    story.append(Spacer(1, 1*cm))
    # 1. Istansa
    story.append(Paragraph("1. ISTANZA", styles["Heading1"]))
    story.append(Paragraph(f"Richiedente riconoscimento per: {cand['cognome']} {cand.get('nome', '')}", styles["Normal"]))
    # 2. Relazione storico-documentale
    story.append(PageBreak())
    story.append(Paragraph("2. RELAZIONE STORICO-DOCUMENTALE", styles["Heading1"]))
    for e in events:
        story.append(Paragraph(f"- {e.get('tipo_evento', '')}: {e.get('descrizione_verificata', '')}", styles["Normal"]))
    # 3. Scheda anagrafica
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("3. SCHEDA ANAGRAFICA", styles["Heading1"]))
    for field in ["cognome", "nome", "data_nascita", "luogo_nascita", "comune_residenza", "grado", "reparto", "conflitto"]:
        if cand.get(field):
            story.append(Paragraph(f"{field}: {cand[field]}", styles["Normal"]))
    # 4. Cronologia
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("4. CRONOLOGIA", styles["Heading1"]))
    # 5. Inquadramento riconoscimento
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("5. INQUADRAMENTO DEL RICONOSCIMENTO", styles["Heading1"]))
    for a in assessments:
        story.append(Paragraph(f"- {a.get('recognition_name', '')}: {a.get('riconoscimento_ipotizzato', '')}", styles["Normal"]))
        story.append(Paragraph(f"  Procedura: {a.get('procedura', '')}", styles["Normal"]))
    # 6. Tabella requisiti
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("6. TABELLA REQUISITI E PROVE", styles["Heading1"]))
    # 7. Fonti primarie
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("7. FONTI PRIMARIE", styles["Heading1"]))
    for s in sources:
        story.append(Paragraph(f"- {s.get('titolo', '')} - {s.get('ente_conservatore', '')} (attendibilita': {s.get('livello_attendibilita', '')})", styles["Normal"]))
    # 8-9. Documentazione
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("8. DOCUMENTAZIONE MILITARE E DI STATO CIVILE", styles["Heading1"]))
    for d in docs:
        story.append(Paragraph(f"- {d.get('titolo', '')} ({d.get('categoria_documentale', '')}) - verifica: {d.get('stato_verifica', '')}", styles["Normal"]))
    # 10. Prova parentela
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("10. PROVA DELLA PARENTELA", styles["Heading1"]))
    # 14. Elenco allegati
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("14. ELENCO ALLEGATI", styles["Heading1"]))
    for i, d in enumerate(docs, 1):
        story.append(Paragraph(f"All. {i}: {d.get('titolo', '')} - {d.get('filename_originale', '')}", styles["Normal"]))
    # 15. Indirizzo ufficio
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("15. UFFICIO DESTINATARIO", styles["Heading1"]))
    if inst_contact:
        story.append(Paragraph(f"Ente: {inst_contact.get('ente', '')}", styles["Normal"]))
        story.append(Paragraph(f"Ufficio: {inst_contact.get('ufficio', '')}", styles["Normal"]))
        story.append(Paragraph(f"Indirizzo: {inst_contact.get('indirizzo', '')}", styles["Normal"]))
        story.append(Paragraph(f"PEC: {inst_contact.get('pec', '')}", styles["Normal"]))
    # 16. Comunicazione di accompagnamento
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("16. COMUNICAZIONE DI ACCOMPAGNAMENTO", styles["Heading1"]))
    story.append(Paragraph(
        "Si trasmette il presente fascicolo per l'avvio del procedimento "
        "di riconoscimento. Si resta a disposizione per eventuali integrazioni.",
        styles["Normal"]))
    # Validazione warning
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("NOTE DI VALIDAZIONE", styles["Heading2"]))
    if missing:
        story.append(Paragraph(f"ATTENZIONE: {len(missing)} documenti obbligatori mancanti. Eccezione motivata.", styles["Normal"]))
    story.append(Paragraph(f"Pronto invio: SI (validato da revisore)", styles["Normal"]))
    if p.get("motivazione_eccezione"):
        story.append(Paragraph(f"Motivazione eccezione: {p['motivazione_eccezione']}", styles["Normal"]))
    doc.build(story)
    _audit(user, "generate", "official_dossier", pid, next_val={"file": file_name})
    return {"file": file_name, "path": str(file_path), "size": file_path.stat().st_size}


# ═══════════════════════════════════════════════════════════════════════════════
# SCOPRI CANDIDATI - ricerca in tutti i DB storici
# ═══════════════════════════════════════════════════════════════════════════════

_DISCOVER_SOURCES = {
    "internati": {
        "label": "IMI - Internati Militari Italiani",
        "table": "internati",
        "cols": "id, cognome, nome, grado, luogo_nascita, residenza, luogo_cattura, luogo_internamento, sorte, data, matricola, lettera, pagina",
        "search_cols": ["cognome", "nome", "luogo_nascita", "residenza", "luogo_internamento", "grado", "matricola"],
    },
    "caduti_albooro": {
        "label": "Albo d'Oro - Caduti 1GM",
        "table": "caduti_albooro",
        "cols": "id, nominativo, grado, reparto, luogo_morte, anno_morte, causa_morte, detail_url",
        "search_cols": ["nominativo", "grado", "reparto", "luogo_morte"],
    },
    "decorati_nastroazzurro": {
        "label": "Nastro Azzurro - Decorati",
        "table": "decorati_nastroazzurro",
        "cols": "id, nome, cognome, grado, decorazione, anno_decorazione, reparto",
        "search_cols": ["nome", "cognome", "grado", "decorazione", "reparto"],
    },
    "decorati": {
        "label": "Decorati ISTORECO",
        "table": "decorati",
        "cols": "id, cognome, nome, grado, decorazione, guerra, luogo_morte, luogo_internamento, causa_morte, comune_nascita",
        "search_cols": ["cognome", "nome", "grado", "decorazione", "guerra", "luogo_morte", "luogo_internamento"],
    },
    "caduti_ministero": {
        "label": "Caduti Ministero Difesa",
        "table": "caduti_ministero",
        "cols": "id, cognome, nome, grado, reparto, luogo_nascita, luogo_sepoltura, nazione_decesso, data_decesso",
        "search_cols": ["cognome", "nome", "grado", "reparto", "luogo_nascita"],
    },
    "caduti_cwgc": {
        "label": "CWGC - Caduti Commonwealth",
        "table": "caduti_cwgc",
        "cols": "id, name, rank, regiment, cemetery, country, age, date_of_death",
        "search_cols": ["name", "rank", "regiment", "cemetery"],
    },
    "fonti_indice": {
        "label": "Fonti d'archivio indicizzate",
        "table": "fonti_indice",
        "cols": "id, titolo, archivio, tipo_fonte, url_pagina, soggetto",
        "search_cols": ["titolo", "archivio", "soggetto"],
    },
    "fondi_archivistici": {
        "label": "Fondi archivistici esplorati",
        "table": "fondi_archivistici",
        "cols": "id, fondo, segnatura, descrizione, archivio",
        "search_cols": ["fondo", "segnatura", "descrizione", "archivio"],
    },
    "documenti_nara_t315": {
        "label": "NARA T315 - Prigionia",
        "table": "documenti_nara_t315",
        "cols": "id, roll, frame, subjects",
        "search_cols": ["subjects"],
    },
}


@router.get("/discover-candidates")
def discover_candidates(request: Request, q: str = "", limit: int = 50,
                        source: str = "", conflict: str = "", fate: str = ""):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:candidate:read"):
        raise HTTPException(403, "Permesso insufficiente")
    if len(q.strip()) < 2:
        return {"results": [], "total": 0, "query": q}
    conn = get_conn()
    tokens = [t.upper().strip() for t in q.split() if t.strip()]
    if not tokens:
        conn.close()
        return {"results": [], "total": 0, "query": q}
    results = []
    for source_key, source_info in _DISCOVER_SOURCES.items():
        if source and source_key != source:
            continue
        table = source_info["table"]
        cols = source_info["cols"]
        search_cols = source_info["search_cols"]
        label = source_info["label"]
        try:
            where_parts = []
            params = []
            for col in search_cols:
                for token in tokens:
                    where_parts.append(f"UPPER(CAST({col} AS TEXT)) LIKE ?")
                    params.append(f"%{token}%")
            where_clause = " OR ".join(where_parts)
            extra_where = []
            if conflict:
                conflict_map = {"ww1": ["1GM", "WW1", "prima", "1914", "1915", "1916", "1917", "1918"],
                                "ww2": ["2GM", "WW2", "seconda", "1939", "1940", "1941", "1942", "1943", "1944", "1945"]}
                keywords = conflict_map.get(conflict.lower(), [])
                if keywords:
                    kw_or = " OR ".join([f"UPPER(CAST(grado AS TEXT)) LIKE '%{kw.upper()}%'" for kw in keywords] +
                                         [f"UPPER(CAST(reparto AS TEXT)) LIKE '%{kw.upper()}%'" for kw in keywords] +
                                         [f"UPPER(CAST(guerra AS TEXT)) LIKE '%{kw.upper()}%'" for kw in keywords])
                    extra_where.append(f"({kw_or})")
            if fate:
                fate_field = "sorte" if "sorte" in cols else "sorte"
                extra_where.append(f"UPPER(CAST({fate_field} AS TEXT)) LIKE '%{fate.upper()}%'")
            if extra_where:
                where_clause = f"({where_clause}) AND {' AND '.join(extra_where)}"
            sql = f"SELECT {cols} FROM {table} WHERE ({where_clause}) LIMIT ?"
            rows = conn.execute(sql, params + [limit]).fetchall()
            for row in rows:
                d = dict(row)
                entry = {
                    "source": source_key,
                    "source_label": label,
                    "record_id": d.get("id"),
                    "data": d,
                }
                # Check if already imported as RC candidate
                cognome = (d.get("cognome") or d.get("nominativo") or d.get("name") or "").strip()
                nome = (d.get("nome") or "").strip()
                if cognome:
                    existing = conn.execute(
                        "SELECT id FROM rc_candidates WHERE UPPER(cognome) = ? AND UPPER(nome) = ? LIMIT 1",
                        (cognome.upper(), nome.upper()),
                    ).fetchone()
                    entry["already_imported"] = existing is not None
                    if existing:
                        entry["rc_candidate_id"] = existing["id"]
                else:
                    entry["already_imported"] = False
                results.append(entry)
        except Exception:
            pass
    conn.close()
    # Sort: non-imported first, then by source
    results.sort(key=lambda r: (r.get("already_imported", False), r["source_label"]))
    return {"results": results[:limit], "total": len(results), "query": q}


@router.post("/discover-candidates/{source}/{record_id}/import")
def import_discovered_candidate(request: Request, source: str, record_id: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:candidate:write"):
        raise HTTPException(403, "Permesso insufficiente")
    if source not in _DISCOVER_SOURCES:
        raise HTTPException(400, f"Fonte non valida: {source}")
    conn = get_conn()
    source_info = _DISCOVER_SOURCES[source]
    table = source_info["table"]
    cols = source_info["cols"]
    try:
        row = conn.execute(f"SELECT {cols} FROM {table} WHERE id = ?", (record_id,)).fetchone()
    except Exception:
        conn.close()
        raise HTTPException(404, "Record non trovato")
    if not row:
        conn.close()
        raise HTTPException(404, "Record non trovato")
    d = dict(row)
    now = _now()
    # Map fields based on source
    cognome = (d.get("cognome") or "").strip()
    nome = (d.get("nome") or "").strip()
    if not cognome and d.get("nominativo"):
        parts = d["nominativo"].split(" ", 1)
        cognome = parts[0]
        nome = parts[1] if len(parts) > 1 else ""
    if not cognome and d.get("name"):
        cognome = d["name"]
    if not cognome:
        conn.close()
        raise HTTPException(400, "Impossibile estrarre cognome dal record")
    # Check if already exists
    existing = conn.execute(
        "SELECT id FROM rc_candidates WHERE UPPER(cognome) = ? AND UPPER(nome) = ? LIMIT 1",
        (cognome.upper(), nome.upper()),
    ).fetchone()
    if existing:
        conn.close()
        return {"ok": True, "candidate_id": existing["id"], "already_exists": True}
    # Build candidate from source data
    grado = d.get("grado") or d.get("rank") or ""
    luogo_nascita = d.get("luogo_nascita") or d.get("comune_nascita") or ""
    residenza = d.get("residenza") or d.get("comune_residenza") or ""
    matricola = d.get("matricola") or ""
    reparto = d.get("reparto") or d.get("regiment") or ""
    sorte = d.get("sorte") or ""
    luogo_internamento = d.get("luogo_internamento") or ""
    luogo_morte = d.get("luogo_morte") or d.get("luogo_sepoltura") or d.get("cemetery") or ""
    conflitto = "Seconda Guerra Mondiale" if source == "internati" else "Prima Guerra Mondiale"
    note = f"Importato da {source_info['label']} (record id={record_id})"
    if sorte:
        note += f". Sorte: {sorte}"
    if d.get("decorazione"):
        note += f". Decorazione: {d['decorazione']}"
    if d.get("anno_decorazione"):
        note += f" ({d['anno_decorazione']})"
    if d.get("guerra"):
        conflitto = d["guerra"]
    if d.get("detail_url"):
        note += f". URL: {d['detail_url']}"
    conn.execute(
        """INSERT INTO rc_candidates
           (nome, cognome, grado, luogo_nascita, comune_residenza, reparto,
            matricola, luogo_morte, conflitto, stato, livello_certezza,
            note_interne, created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'BOZZA', 'da_verificare', ?, ?, ?, ?)""",
        (nome, cognome, grado, luogo_nascita, residenza, reparto,
         matricola, luogo_morte, conflitto, note, now, now, user.get("id")),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    # Create a source record linking to the original DB entry
    conn.execute(
        """INSERT INTO rc_sources
           (candidate_id, tipologia, titolo, ente_conservatore, url_documento,
            livello_attendibilita, created_at, updated_at)
           VALUES (?, 'database', ?, ?, ?, 'alta', ?, ?)""",
        (new_id, f"Record originale - {source_info['label']}",
         source_info["label"],
         d.get("detail_url") or d.get("url_pagina") or "",
         now, now),
    )
    conn.commit()
    conn.close()
    _audit(user, "import", "candidate", new_id, next_val={"source": source, "record_id": record_id})
    return {"ok": True, "candidate_id": new_id, "already_exists": False}


# ─── Compliance Gate endpoints ─────────────────────────────────────────────────

@router.get("/compliance/policies")
async def list_compliance_policies(request: Request):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM source_policies ORDER BY domain").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/compliance/policies/{policy_id}")
async def get_compliance_policy(request: Request, policy_id: int):
    user = require_auth(request)
    conn = get_conn()
    row = conn.execute("SELECT * FROM source_policies WHERE id = ?", (policy_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Policy non trovata")
    return dict(row)


@router.put("/compliance/policies/{policy_id}")
async def update_compliance_policy(request: Request, policy_id: int, body: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user, "rc:admin"):
        raise HTTPException(403, "Permesso richiesto: rc:admin")
    conn = get_conn()
    existing = conn.execute("SELECT * FROM source_policies WHERE id = ?", (policy_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, "Policy non trovata")
    now = _now()
    allowed_fields = [
        "terms_url", "privacy_url", "robots_url", "archive_regulation_url",
        "metadata_license", "digital_object_license",
        "commercial_use_allowed", "automated_access_allowed",
        "metadata_indexing_allowed", "document_download_allowed",
        "republication_allowed", "attribution_required",
        "required_credit_line", "request_contact",
        "policy_status", "verified_by", "verified_at",
        "valid_from", "review_due_at", "notes",
    ]
    updates = []
    values = []
    for f in allowed_fields:
        if f in body:
            val = body[f]
            if isinstance(val, bool):
                val = 1 if val else 0
            updates.append(f"{f} = ?")
            values.append(val)
    if updates:
        updates.append("updated_at = ?")
        values.append(now)
        values.append(policy_id)
        conn.execute(f"UPDATE source_policies SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    _audit(user, "update", "compliance_policy", policy_id, next_val=body)
    return {"ok": True}


@router.get("/compliance/decisions")
async def list_compliance_decisions(request: Request, limit: int = 100):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM compliance_decisions ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/compliance/review-queue")
async def get_compliance_review_queue(request: Request, status: str = "pending"):
    user = require_auth(request)
    from compliance_gate import get_review_queue
    return get_review_queue(status)


@router.post("/compliance/review-queue/{item_id}/resolve")
async def resolve_review_item(request: Request, item_id: int, body: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user, "rc:doc:verify"):
        raise HTTPException(403, "Permesso richiesto: rc:doc:verify")
    from compliance_gate import resolve_review
    decision = body.get("decision", "")
    motivation = body.get("motivation", "")
    if decision not in ("approve", "approve_with_limitations", "reject", "suspend", "request_consultation"):
        raise HTTPException(400, "Decisione non valida")
    resolve_review(item_id, decision, motivation, user["username"])
    _audit(user, "resolve", "compliance_review", item_id, next_val=body)
    return {"ok": True}


@router.post("/compliance/authorize")
async def create_authorization(request: Request, body: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user, "rc:admin"):
        raise HTTPException(403, "Permesso richiesto: rc:admin")
    conn = get_conn()
    now = _now()
    auth_id = conn.execute(
        """INSERT INTO compliance_authorizations
           (source_policy_id, record_id, scope, purpose, granted_by, granted_to,
            protocol, valid_from, valid_until, limitations, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (body.get("source_policy_id"), body.get("record_id", ""),
         body.get("scope", ""), body.get("purpose", ""),
         body.get("granted_by", ""), user["username"],
         body.get("protocol", ""), body.get("valid_from", now),
         body.get("valid_until", ""), body.get("limitations", ""), now),
    ).lastrowid
    conn.commit()
    conn.close()
    _audit(user, "authorize", "compliance_auth", auth_id, next_val=body)
    return {"ok": True, "authorization_id": auth_id}


@router.delete("/compliance/authorizations/{auth_id}")
async def revoke_authorization(request: Request, auth_id: int, body: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user, "rc:admin"):
        raise HTTPException(403, "Permesso richiesto: rc:admin")
    conn = get_conn()
    now = _now()
    conn.execute(
        "UPDATE compliance_authorizations SET revoked = 1, revoked_at = ?, revoked_by = ?, revoke_reason = ? WHERE id = ?",
        (now, user["username"], body.get("reason", ""), auth_id),
    )
    conn.commit()
    conn.close()
    _audit(user, "revoke", "compliance_auth", auth_id, next_val=body)
    return {"ok": True}


@router.post("/compliance/evaluate")
async def evaluate_action(request: Request, body: dict = Body(...)):
    user = require_auth(request)
    from compliance_gate import evaluate
    resource = body.get("resource", {})
    action = body.get("action", "")
    result = evaluate(resource, action, user.get("role", "operator"))
    return result


# ─── Croce Rossa search endpoints ─────────────────────────────────────────────

@router.get("/red-cross/search")
async def red_cross_search(request: Request, q: str, source: str = "all",
                           nationality: str = "", status: str = "", files: str = ""):
    """Cerca nelle fonti Croce Rossa (ICRC WW1, CRI Milano).
    
    Filtri ICRC auto-compilabili:
    - nationality: italy, france, germany, united_kingdom, austria_hungary, russia, romania, serbia, belgium, ottoman_empire, bulgaria, portugal, united_states
    - status: military, civilian
    - files: index_cards, family_requests, all
    """
    user = require_auth(request)
    from source_providers.federation import get_provider
    results = []

    providers_to_search = []
    if source in ("all", "icrc_ww1"):
        providers_to_search.append("icrc_ww1")
    if source in ("all", "cri_milano"):
        providers_to_search.append("cri_milano")

    icrc_filters = {}
    if nationality:
        icrc_filters["nationality"] = nationality
    if status:
        icrc_filters["status"] = status
    if files:
        icrc_filters["files"] = files

    for pname in providers_to_search:
        provider = get_provider(pname)
        if provider:
            try:
                hits = provider.search(q, icrc_filters if pname == "icrc_ww1" else {})
                for h in hits:
                    h["provider_display"] = provider.display_name
                results.extend(hits)
            except Exception as e:
                results.append({
                    "provider": pname,
                    "error": str(e),
                    "titolo": f"Errore {pname}: {e}",
                })

    return {"results": results, "count": len(results), "query": q, "filters": icrc_filters}


@router.get("/red-cross/{provider}/{record_id}")
async def red_cross_detail(request: Request, provider: str, record_id: str):
    """Recupera dettaglio da una fonte Croce Rossa. Solo metadati."""
    user = require_auth(request)
    from source_providers.federation import get_provider
    p = get_provider(provider)
    if not p:
        raise HTTPException(404, f"Provider '{provider}' non trovato")
    meta = p.get_metadata(record_id)
    return meta

