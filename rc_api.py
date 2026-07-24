"""API router per il modulo Percorso Riconoscimenti.

Tutti gli endpoint sono prefissati con /api/rc/.
Autenticazione session-based tramite auth.py.
"""
import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Body, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse

from database import get_conn
from auth import (
    get_current_user, require_auth, require_role, require_permission,
    has_permission, login as auth_login, logout as auth_logout,
    create_user, list_users, update_user, delete_user, ensure_default_admin,
    RC_COOKIE_NAME, RC_SESSION_TTL_HOURS, ROLES,
)
from rc_state_machine import (
    STATES, VALID_TRANSITIONS, get_valid_transitions, is_valid_transition,
    is_terminal, transition, get_transition_history,
)
from rc_ai_analysis import generate_ai_analysis, get_ai_analyses

router = APIRouter(prefix="/api/rc", tags=["percorso-riconoscimenti"])

RC_UPLOAD_DIR = Path(__file__).parent / "uploads" / "rc"
RC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RC_DOSSIER_DIR = Path(__file__).parent / "outputs" / "dossiers"
RC_DOSSIER_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helper ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now().isoformat()


def _audit(user: dict, azione: str, entita: str, entita_id: int,
           prev=None, next_val=None, motivazione=None):
    conn = get_conn()
    conn.execute(
        """INSERT INTO rc_audit_log
           (user_id, username, azione, entita, entita_id,
            valore_precedente, valore_successivo, motivazione, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user.get("id"), user.get("username", ""), azione, entita, entita_id,
         json.dumps(prev) if isinstance(prev, (dict, list)) else str(prev) if prev else None,
         json.dumps(next_val) if isinstance(next_val, (dict, list)) else str(next_val) if next_val else None,
         motivazione, _now()),
    )
    conn.commit()
    conn.close()


def _file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/auth/login")
def rc_login(request: Request, data: dict = Body(...)):
    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        raise HTTPException(400, "Username e password richiesti")
    result = auth_login(
        username, password,
        ip=request.client.host if request.client else None,
        ua=request.headers.get("user-agent", ""),
    )
    if not result:
        raise HTTPException(401, "Credenziali non valide")
    resp = JSONResponse({"user": result["user"]})
    resp.set_cookie(
        RC_COOKIE_NAME, result["token"],
        max_age=RC_SESSION_TTL_HOURS * 3600,
        httponly=True, samesite="lax",
    )
    return resp


@router.post("/auth/logout")
def rc_logout(request: Request):
    token = request.cookies.get(RC_COOKIE_NAME)
    if token:
        auth_logout(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(RC_COOKIE_NAME)
    return resp


@router.get("/auth/me")
def rc_me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Non autenticato")
    return user


@router.get("/auth/users")
def rc_list_users(request: Request):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    return {"users": list_users()}


@router.post("/auth/users")
def rc_create_user(request: Request, data: dict = Body(...)):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    try:
        new_user = create_user(
            username=data["username"],
            password=data["password"],
            role=data.get("role", "ricercatore"),
            email=data.get("email"),
            full_name=data.get("full_name"),
        )
        _audit(user, "create_user", "user", new_user["id"],
               next_val={"username": new_user["username"], "role": new_user["role"]})
        return {"user": {k: v for k, v in new_user.items() if k != "password_hash"}}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/auth/users/{uid}")
def rc_update_user(request: Request, uid: int, data: dict = Body(...)):
    user = require_auth(request)
    if user["role"] != "admin" and user["id"] != uid:
        raise HTTPException(403, "Solo admin o l'utente stesso")
    update_user(uid, **data)
    _audit(user, "update_user", "user", uid, next_val=data)
    return {"ok": True}


@router.delete("/auth/users/{uid}")
def rc_delete_user(request: Request, uid: int):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    delete_user(uid)
    _audit(user, "delete_user", "user", uid)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# CANDIDATI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates")
def list_candidates(request: Request,
                    q: str = "", stato: str = "", conflitto: str = "",
                    luogo: str = "", anno: str = "", reparto: str = "",
                    riconoscimento: str = "", has_discendenti: str = "",
                    pratica_trasmessa: str = "", esito: str = "",
                    limit: int = 50, offset: int = 0):
    user = require_auth(request)
    conn = get_conn()
    where = []
    params = []
    if q:
        where.append("(c.cognome LIKE ? OR c.nome LIKE ? OR c.varianti_nominativi LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if stato:
        where.append("c.stato = ?")
        params.append(stato)
    if conflitto:
        where.append("c.conflitto = ?")
        params.append(conflitto)
    if luogo:
        where.append("(c.luogo_nascita LIKE ? OR c.luogo_morte LIKE ? OR c.comune_residenza LIKE ?)")
        params.extend([f"%{luogo}%", f"%{luogo}%", f"%{luogo}%"])
    if anno:
        where.append("(c.data_nascita LIKE ? OR c.data_morte LIKE ?)")
        params.extend([f"%{anno}%", f"%{anno}%"])
    if reparto:
        where.append("c.reparto LIKE ?")
        params.append(f"%{reparto}%")
    where_clause = " AND ".join(where) if where else "1=1"
    total = conn.execute(
        f"SELECT COUNT(*) as c FROM rc_candidates c WHERE {where_clause}", params
    ).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT c.* FROM rc_candidates c
            WHERE {where_clause}
            ORDER BY c.updated_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {"candidates": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/candidates/{cid}")
def get_candidate(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    cand = conn.execute("SELECT * FROM rc_candidates WHERE id = ?", (cid,)).fetchone()
    if not cand:
        conn.close()
        raise HTTPException(404, "Candidato non trovato")
    result = dict(cand)
    result["valid_transitions"] = get_valid_transitions(cand["stato"])
    result["is_terminal"] = is_terminal(cand["stato"])
    conn.close()
    return result


@router.post("/candidates")
def create_candidate(request: Request, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:candidate:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_candidates
           (nome, cognome, varianti_nominativi, paternita, maternita,
            data_nascita, luogo_nascita, data_morte, luogo_morte,
            comune_residenza, grado, reparto, forza_armata, matricola,
            conflitto, stato, livello_certezza, note_interne,
            created_at, updated_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BOZZA', ?, ?, ?, ?, ?)""",
        (data.get("nome", ""), data.get("cognome", ""),
         data.get("varianti_nominativi"), data.get("paternita"),
         data.get("maternita"), data.get("data_nascita"),
         data.get("luogo_nascita"), data.get("data_morte"),
         data.get("luogo_morte"), data.get("comune_residenza"),
         data.get("grado"), data.get("reparto"), data.get("forza_armata"),
         data.get("matricola"), data.get("conflitto"),
         data.get("livello_certezza", "da_verificare"),
         data.get("note_interne"), now, now, user.get("id")),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "candidate", cid, next_val={"nome": data.get("nome"), "cognome": data.get("cognome")})
    return {"id": cid, "stato": "BOZZA"}


@router.put("/candidates/{cid}")
def update_candidate(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:candidate:write"):
        raise HTTPException(403, "Permesso insufficiente")
    allowed = {
        "nome", "cognome", "varianti_nominativi", "paternita", "maternita",
        "data_nascita", "luogo_nascita", "data_morte", "luogo_morte",
        "comune_residenza", "grado", "reparto", "forza_armata", "matricola",
        "conflitto", "livello_certezza", "note_interne", "priorita_json",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Nessun campo da aggiornare")
    conn = get_conn()
    old = conn.execute("SELECT * FROM rc_candidates WHERE id = ?", (cid,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(404, "Candidato non trovato")
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [cid]
    conn.execute(f"UPDATE rc_candidates SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    _audit(user, "update", "candidate", cid, prev=dict(old), next_val=updates)
    return {"ok": True}


@router.post("/candidates/{cid}/transition")
def candidate_transition(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    new_state = data.get("new_state", "")
    motivazione = data.get("motivazione", "")
    allegati = data.get("allegati")
    try:
        result = transition(cid, new_state, user, motivazione=motivazione, allegati=allegati)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/candidates/{cid}/history")
def candidate_history(request: Request, cid: int):
    user = require_auth(request)
    return {"transitions": get_transition_history(cid)}


@router.get("/states")
def list_states(request: Request):
    user = require_auth(request)
    return {
        "states": STATES,
        "transitions": {k: v for k, v in VALID_TRANSITIONS.items()},
        "terminal": list(is_terminal(s) for s in STATES if is_terminal(s)),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FONTI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/sources")
def list_sources(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_sources WHERE candidate_id = ? ORDER BY created_at DESC", (cid,)).fetchall()
    conn.close()
    return {"sources": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/sources")
def create_source(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:source:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_sources
           (titolo, tipologia, ente_conservatore, fondo, serie, busta,
            fascicolo, pagina_immagine, segnatura_completa, url_istituzionale,
            data_documento, trascrizione, estrazione_automatica,
            livello_attendibilita, stato_verifica, verificatore,
            candidate_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data.get("titolo", ""), data.get("tipologia"),
         data.get("ente_conservatore"), data.get("fondo"),
         data.get("serie"), data.get("busta"), data.get("fascicolo"),
         data.get("pagina_immagine"), data.get("segnatura_completa"),
         data.get("url_istituzionale"), data.get("data_documento"),
         data.get("trascrizione"), data.get("estrazione_automatica"),
         data.get("livello_attendibilita", "da_verificare"),
         data.get("stato_verifica", "non_verificata"),
         data.get("verificatore"), cid, now, now),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "source", sid, next_val={"titolo": data.get("titolo"), "candidate_id": cid})
    return {"id": sid}


@router.put("/sources/{sid}")
def update_source(request: Request, sid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:source:write"):
        raise HTTPException(403, "Permesso insufficiente")
    allowed = {
        "titolo", "tipologia", "ente_conservatore", "fondo", "serie", "busta",
        "fascicolo", "pagina_immagine", "segnatura_completa", "url_istituzionale",
        "data_documento", "trascrizione", "estrazione_automatica",
        "livello_attendibilita", "stato_verifica", "verificatore",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Nessun campo da aggiornare")
    updates["updated_at"] = _now()
    conn = get_conn()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [sid]
    conn.execute(f"UPDATE rc_sources SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    _audit(user, "update", "source", sid, next_val=updates)
    return {"ok": True}


@router.post("/sources/{sid}/upload")
async def upload_source_file(request: Request, sid: int, file: UploadFile = File(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:source:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    src = conn.execute("SELECT * FROM rc_sources WHERE id = ?", (sid,)).fetchone()
    if not src:
        conn.close()
        raise HTTPException(404, "Fonte non trovata")
    file_dir = RC_UPLOAD_DIR / str(sid)
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / file.filename
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    checksum = hashlib.sha256(content).hexdigest()
    conn.execute(
        "UPDATE rc_sources SET file_path = ?, file_checksum = ?, updated_at = ? WHERE id = ?",
        (str(file_path), checksum, _now(), sid),
    )
    conn.commit()
    conn.close()
    _audit(user, "upload", "source", sid, next_val={"file": file.filename, "checksum": checksum})
    return {"ok": True, "checksum": checksum}


# ═══════════════════════════════════════════════════════════════════════════════
# EVENTI STORICI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/events")
def list_historical_events(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_historical_events WHERE candidate_id = ? ORDER BY data_inizio", (cid,)).fetchall()
    conn.close()
    return {"events": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/events")
def create_historical_event(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:candidate:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_historical_events
           (candidate_id, tipo_evento, data_inizio, data_fine, luogo,
            descrizione_verificata, testo_originale_fonte, condotta_individuale,
            rischio_affrontato, conseguenze, testimoni, grado_attendibilita,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, data.get("tipo_evento"), data.get("data_inizio"),
         data.get("data_fine"), data.get("luogo"),
         data.get("descrizione_verificata"), data.get("testo_originale_fonte"),
         data.get("condotta_individuale"), data.get("rischio_affrontato"),
         data.get("conseguenze"), data.get("testimoni"),
         data.get("grado_attendibilita", "da_verificare"), now, now),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "historical_event", eid, next_val={"candidate_id": cid})
    return {"id": eid}


# ═══════════════════════════════════════════════════════════════════════════════
# VALUTAZIONI RICONOSCIMENTO
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/assessments")
def list_assessments(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT a.*, r.denominazione as recognition_name
           FROM rc_recognition_assessments a
           LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id
           WHERE a.candidate_id = ? ORDER BY a.created_at DESC""",
        (cid,),
    ).fetchall()
    conn.close()
    return {"assessments": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/assessments")
def create_assessment(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:assessment:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_recognition_assessments
           (candidate_id, recognition_type_id, riconoscimento_ipotizzato,
            requisiti_presenti, requisiti_mancanti, elementi_contrari,
            procedura, motivazione, valutatore, data_valutazione,
            validazione_storica, validazione_amministrativa,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, data.get("recognition_type_id"), data.get("riconoscimento_ipotizzato"),
         data.get("requisiti_presenti"), data.get("requisiti_mancanti"),
         data.get("elementi_contrari"), data.get("procedura", "da_verificare"),
         data.get("motivazione"), user.get("username", ""), now,
         data.get("validazione_storica", 0), data.get("validazione_amministrativa", 0),
         now, now),
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "assessment", aid, next_val={"candidate_id": cid})
    return {"id": aid}


# ─── Analisi AI ──────────────────────────────────────────────────────────────

@router.post("/candidates/{cid}/ai-analysis")
def run_ai_analysis(request: Request, cid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:assessment:write"):
        raise HTTPException(403, "Permesso insufficiente")
    try:
        result = generate_ai_analysis(cid)
        _audit(user, "ai_analysis", "candidate", cid,
               next_val={"honors": len(result.get("onorificenze_analizzate", []))})
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Errore analisi: {e}")


@router.get("/candidates/{cid}/ai-analyses")
def list_ai_analyses(request: Request, cid: int):
    user = require_auth(request)
    analyses = get_ai_analyses(cid)
    return {"analyses": analyses}


# ═══════════════════════════════════════════════════════════════════════════════
# CATALOGO RICONOSCIMENTI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/recognition-types")
def list_recognition_types(request: Request):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_recognition_types ORDER BY denominazione").fetchall()
    conn.close()
    return {"types": [dict(r) for r in rows]}


@router.post("/recognition-types")
def create_recognition_type(request: Request, data: dict = Body(...)):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_recognition_types
           (denominazione, categoria, autorita_concedente, ente_istruttore,
            base_normativa, requisiti, concessione_memoria, soggetti_legittimati,
            modalita_avvio, termini, documenti_richiesti, procedura_attiva,
            data_ultimo_aggiornamento, fonti_istituzionali, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data.get("denominazione", ""), data.get("categoria"),
         data.get("autorita_concedente"), data.get("ente_istruttore"),
         data.get("base_normativa"), data.get("requisiti"),
         data.get("concessione_memoria", 0), data.get("soggetti_legittimati"),
         data.get("modalita_avvio"), data.get("termini"),
         data.get("documenti_richiesti"), data.get("procedura_attiva", "da_verificare"),
         now, data.get("fonti_istituzionali"), now, now),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "recognition_type", rid)
    return {"id": rid}


@router.put("/recognition-types/{rid}")
def update_recognition_type(request: Request, rid: int, data: dict = Body(...)):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    allowed = {
        "denominazione", "categoria", "autorita_concedente", "ente_istruttore",
        "base_normativa", "requisiti", "concessione_memoria", "soggetti_legittimati",
        "modalita_avvio", "termini", "documenti_richiesti", "procedura_attiva",
        "fonti_istituzionali",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["data_ultimo_aggiornamento"] = _now()
    updates["updated_at"] = _now()
    conn = get_conn()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [rid]
    conn.execute(f"UPDATE rc_recognition_types SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    _audit(user, "update", "recognition_type", rid, next_val=updates)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# GENEALOGIA
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/family")
def list_family_persons(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_family_persons WHERE candidate_id = ? ORDER BY id", (cid,)).fetchall()
    persons = [dict(r) for r in rows]
    for p in persons:
        if p.get("stato_vita") == "vivente" or p.get("stato_vita") == "non_accertato":
            if p.get("visibilita_limitata"):
                p["data_nascita"] = None
                p["luogo_nascita"] = None
    conn.close()
    return {"persons": persons}


@router.post("/candidates/{cid}/family")
def create_family_person(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:genealogy:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_family_persons
           (candidate_id, nome, cognome, data_nascita, luogo_nascita,
            data_morte, rapporto_candidato, stato_vita, fonte_genealogica,
            livello_certezza, visibilita_limitata, stato_contatto,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, data.get("nome"), data.get("cognome"),
         data.get("data_nascita"), data.get("luogo_nascita"),
         data.get("data_morte"), data.get("rapporto_candidato"),
         data.get("stato_vita", "non_accertato"),
         data.get("fonte_genealogica"), data.get("livello_certezza", "basso"),
         1, data.get("stato_contatto", "nessuno"), now, now),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "family_person", fid, next_val={"candidate_id": cid})
    return {"id": fid}


@router.get("/candidates/{cid}/kinship")
def list_kinship(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT k.*, p1.nome as origine_nome, p1.cognome as origine_cognome,
                  p2.nome as dest_nome, p2.cognome as dest_cognome
           FROM rc_kinship_links k
           JOIN rc_family_persons p1 ON k.persona_origine_id = p1.id
           JOIN rc_family_persons p2 ON k.persona_destinazione_id = p2.id
           WHERE p1.candidate_id = ? OR p2.candidate_id = ?""",
        (cid, cid),
    ).fetchall()
    conn.close()
    return {"links": [dict(r) for r in rows]}


@router.post("/kinship")
def create_kinship(request: Request, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:genealogy:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_kinship_links
           (persona_origine_id, persona_destinazione_id, tipo_rapporto,
            fonte, grado_certezza, verificato_da, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data.get("persona_origine_id"), data.get("persona_destinazione_id"),
         data.get("tipo_rapporto"), data.get("fonte"),
         data.get("grado_certezza", "basso"), data.get("verificato_da"), now),
    )
    kid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "kinship_link", kid)
    return {"id": kid}


# ═══════════════════════════════════════════════════════════════════════════════
# CONTATTI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/contacts")
def list_contacts(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_contact_attempts WHERE candidate_id = ? ORDER BY created_at DESC", (cid,)).fetchall()
    conn.close()
    return {"contacts": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/contacts")
def create_contact(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_contact_attempts
           (candidate_id, destinatario_id, canale, intermediario,
            testo_approvato, data_invio, esito, operatore,
            divieto_ulteriori, prova_inoltro, approvato, approvato_da,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, data.get("destinatario_id"), data.get("canale"),
         data.get("intermediario"), data.get("testo_approvato"),
         data.get("data_invio"), data.get("esito", "in_attesa"),
         user.get("username", ""), data.get("divieto_ulteriori", 0),
         data.get("prova_inoltro"), 0, None, now, now),
    )
    coid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "contact_attempt", coid, next_val={"candidate_id": cid})
    return {"id": coid}


@router.post("/contacts/{coid}/approve")
def approve_contact(request: Request, coid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:approve"):
        raise HTTPException(403, "Permesso insufficiente per approvare contatti")
    conn = get_conn()
    conn.execute(
        "UPDATE rc_contact_attempts SET approvato = 1, approvato_da = ?, updated_at = ? WHERE id = ?",
        (user.get("username", ""), _now(), coid),
    )
    conn.commit()
    conn.close()
    _audit(user, "approve", "contact_attempt", coid)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# CASI DISCENDENTI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/descendant-cases")
def list_descendant_cases(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rc_descendant_cases WHERE candidate_id = ? ORDER BY created_at DESC", (cid,)).fetchall()
    conn.close()
    return {"cases": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/descendant-cases")
def create_descendant_case(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:case:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_descendant_cases
           (candidate_id, discendente_referente_id, parentela_dichiarata,
            parentela_verificata, documenti_prova, consenso, delega,
            data_adesione, altri_rami_familiari, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, data.get("discendente_referente_id"),
         data.get("parentela_dichiarata"), data.get("parentela_verificata", "non_verificata"),
         data.get("documenti_prova"), data.get("consenso", 0),
         data.get("delega"), data.get("data_adesione"),
         data.get("altri_rami_familiari"), now, now),
    )
    dcid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "descendant_case", dcid, next_val={"candidate_id": cid})
    return {"id": dcid}


@router.post("/descendant-cases/{dcid}/invitation")
def create_invitation(request: Request, dcid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:contact:approve"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    dc = conn.execute("SELECT * FROM rc_descendant_cases WHERE id = ?", (dcid,)).fetchone()
    if not dc:
        conn.close()
        raise HTTPException(404, "Caso discendente non trovato")
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(days=30)
    conn.execute(
        """INSERT INTO rc_invitations
           (token, descendant_case_id, email, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (token, dcid, data.get("email"), now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()
    _audit(user, "create", "invitation", dcid, next_val={"token": token[:8] + "..."})
    return {"token": token, "expires_at": expires.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════════
# PRATICHE AMMINISTRATIVE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/candidates/{cid}/admin-cases")
def list_admin_cases(request: Request, cid: int):
    user = require_auth(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT a.*, r.denominazione as recognition_name
           FROM rc_administrative_cases a
           LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id
           WHERE a.candidate_id = ? ORDER BY a.created_at DESC""",
        (cid,),
    ).fetchall()
    conn.close()
    return {"cases": [dict(r) for r in rows]}


@router.post("/candidates/{cid}/admin-cases")
def create_admin_case(request: Request, cid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:case:write"):
        raise HTTPException(403, "Permesso insufficiente")
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        """INSERT INTO rc_administrative_cases
           (candidate_id, recognition_type_id, ente_destinatario, ufficio,
            protocollo, data_invio, modalita_trasmissione, responsabile,
            scadenze, stato, richieste_integrazione, esito,
            decreto_provvedimento, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, data.get("recognition_type_id"), data.get("ente_destinatario"),
         data.get("ufficio"), data.get("protocollo"), data.get("data_invio"),
         data.get("modalita_trasmissione"), data.get("responsabile"),
         data.get("scadenze"), data.get("stato", "in_preparazione"),
         data.get("richieste_integrazione"), data.get("esito"),
         data.get("decreto_provvedimento"), now, now),
    )
    acid = cur.lastrowid
    conn.commit()
    conn.close()
    _audit(user, "create", "admin_case", acid, next_val={"candidate_id": cid})
    return {"id": acid}


@router.put("/admin-cases/{acid}")
def update_admin_case(request: Request, acid: int, data: dict = Body(...)):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:case:write"):
        raise HTTPException(403, "Permesso insufficiente")
    allowed = {
        "recognition_type_id", "ente_destinatario", "ufficio", "protocollo",
        "data_invio", "modalita_trasmissione", "responsabile", "scadenze",
        "stato", "richieste_integrazione", "esito", "decreto_provvedimento",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = _now()
    conn = get_conn()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [acid]
    conn.execute(f"UPDATE rc_administrative_cases SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    _audit(user, "update", "admin_case", acid, next_val=updates)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/audit")
def list_audit(request: Request, entita: str = "", entita_id: int = None,
               limit: int = 100, offset: int = 0):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    conn = get_conn()
    where = []
    params = []
    if entita:
        where.append("entita = ?")
        params.append(entita)
    if entita_id is not None:
        where.append("entita_id = ?")
        params.append(entita_id)
    where_clause = " AND ".join(where) if where else "1=1"
    total = conn.execute(f"SELECT COUNT(*) as c FROM rc_audit_log WHERE {where_clause}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM rc_audit_log WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {"entries": [dict(r) for r in rows], "total": total}


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
def dashboard(request: Request):
    user = require_auth(request)
    conn = get_conn()
    total_candidates = conn.execute("SELECT COUNT(*) as c FROM rc_candidates").fetchone()["c"]
    by_state = {}
    for row in conn.execute("SELECT stato, COUNT(*) as c FROM rc_candidates GROUP BY stato").fetchall():
        by_state[row["stato"]] = row["c"]
    total_sources = conn.execute("SELECT COUNT(*) as c FROM rc_sources").fetchone()["c"]
    total_recognition_types = conn.execute("SELECT COUNT(*) as c FROM rc_recognition_types").fetchone()["c"]
    total_admin_cases = conn.execute("SELECT COUNT(*) as c FROM rc_administrative_cases").fetchone()["c"]
    total_descendant_cases = conn.execute("SELECT COUNT(*) as c FROM rc_descendant_cases").fetchone()["c"]
    # New tables
    total_practices = 0
    total_practice_docs = 0
    total_descendant_contacts = 0
    total_institutional_contacts = 0
    total_communications = 0
    total_ai_analyses = 0
    try:
        total_practices = conn.execute("SELECT COUNT(*) as c FROM rc_practices").fetchone()["c"]
    except:
        pass
    try:
        total_practice_docs = conn.execute("SELECT COUNT(*) as c FROM rc_practice_documents").fetchone()["c"]
    except:
        pass
    try:
        total_descendant_contacts = conn.execute("SELECT COUNT(*) as c FROM rc_descendant_contacts").fetchone()["c"]
    except:
        pass
    try:
        total_institutional_contacts = conn.execute("SELECT COUNT(*) as c FROM rc_institutional_contacts").fetchone()["c"]
    except:
        pass
    try:
        total_communications = conn.execute("SELECT COUNT(*) as c FROM rc_communications").fetchone()["c"]
    except:
        pass
    try:
        total_ai_analyses = conn.execute("SELECT COUNT(*) as c FROM rc_ai_analyses").fetchone()["c"]
    except:
        pass
    recent_candidates = conn.execute(
        "SELECT id, nome, cognome, stato, updated_at FROM rc_candidates ORDER BY updated_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return {
        "total_candidates": total_candidates,
        "by_state": by_state,
        "total_sources": total_sources,
        "total_recognition_types": total_recognition_types,
        "total_admin_cases": total_admin_cases,
        "total_descendant_cases": total_descendant_cases,
        "total_practices": total_practices,
        "total_practice_docs": total_practice_docs,
        "total_descendant_contacts": total_descendant_contacts,
        "total_institutional_contacts": total_institutional_contacts,
        "total_communications": total_communications,
        "total_ai_analyses": total_ai_analyses,
        "recent_candidates": [dict(r) for r in recent_candidates],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PORTALE DISCENDENTE (accesso pubblico via token)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/public/invitation/{token}")
def public_invitation(token: str):
    conn = get_conn()
    inv = conn.execute("SELECT * FROM rc_invitations WHERE token = ?", (token,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(404, "Invito non trovato")
    if inv["revocato"]:
        conn.close()
        raise HTTPException(403, "Invito revocato")
    if inv["accettato"]:
        conn.close()
        raise HTTPException(409, "Invito già accettato")
    if inv["expires_at"] < _now():
        conn.close()
        raise HTTPException(410, "Invito scaduto")
    dc = conn.execute("SELECT * FROM rc_descendant_cases WHERE id = ?", (inv["descendant_case_id"],)).fetchone()
    if not dc:
        conn.close()
        raise HTTPException(404, "Caso non trovato")
    cand = conn.execute("SELECT id, nome, cognome, grado, reparto, conflitto FROM rc_candidates WHERE id = ?", (dc["candidate_id"],)).fetchone()
    conn.close()
    return {
        "candidate": dict(cand) if cand else None,
        "parentela_dichiarata": dc["parentela_dichiarata"],
        "invitation_id": inv["id"],
    }


@router.post("/public/invitation/{token}/accept")
def public_accept_invitation(token: str, data: dict = Body(...)):
    conn = get_conn()
    inv = conn.execute("SELECT * FROM rc_invitations WHERE token = ?", (token,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(404, "Invito non trovato")
    if inv["revocato"] or inv["accettato"] or inv["expires_at"] < _now():
        conn.close()
        raise HTTPException(403, "Invito non più valido")
    now = _now()
    conn.execute(
        "UPDATE rc_invitations SET accettato = 1, data_accettazione = ? WHERE id = ?",
        (now, inv["id"]),
    )
    if data.get("consenso"):
        conn.execute(
            "UPDATE rc_descendant_cases SET consenso = 1, data_adesione = ? WHERE id = ?",
            (now, inv["descendant_case_id"]),
        )
    if data.get("parentela_dichiarata"):
        conn.execute(
            "UPDATE rc_descendant_cases SET parentela_dichiarata = ? WHERE id = ?",
            (data["parentela_dichiarata"], inv["descendant_case_id"]),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "case_id": inv["descendant_case_id"]}


@router.get("/public/case/{dcid}")
def public_get_case(dcid: int):
    """Il discendente vede solo il proprio caso e le fonti autorizzate."""
    conn = get_conn()
    dc = conn.execute("SELECT * FROM rc_descendant_cases WHERE id = ?", (dcid,)).fetchone()
    if not dc:
        conn.close()
        raise HTTPException(404, "Caso non trovato")
    cand = conn.execute(
        "SELECT id, nome, cognome, grado, reparto, conflitto, data_nascita, luogo_nascita FROM rc_candidates WHERE id = ?",
        (dc["candidate_id"],),
    ).fetchone()
    sources = conn.execute(
        """SELECT id, titolo, tipologia, ente_conservatore, url_istituzionale,
                  data_documento, trascrizione
           FROM rc_sources WHERE candidate_id = ? AND stato_verifica = 'verificata'""",
        (dc["candidate_id"],),
    ).fetchall()
    admin_cases = conn.execute(
        """SELECT stato, ente_destinatario, ufficio, protocollo, esito
           FROM rc_administrative_cases WHERE candidate_id = ?""",
        (dc["candidate_id"],),
    ).fetchall()
    conn.close()
    return {
        "candidate": dict(cand) if cand else None,
        "parentela_dichiarata": dc["parentela_dichiarata"],
        "parentela_verificata": dc["parentela_verificata"],
        "consenso": dc["consenso"],
        "sources": [dict(r) for r in sources],
        "admin_cases": [dict(r) for r in admin_cases],
    }


@router.post("/public/case/{dcid}/upload")
async def public_upload_doc(dcid: int, file: UploadFile = File(...)):
    conn = get_conn()
    dc = conn.execute("SELECT * FROM rc_descendant_cases WHERE id = ?", (dcid,)).fetchone()
    if not dc:
        conn.close()
        raise HTTPException(404, "Caso non trovato")
    file_dir = RC_UPLOAD_DIR / f"descendant_{dcid}"
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / file.filename
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    checksum = hashlib.sha256(content).hexdigest()
    conn.execute(
        """INSERT INTO rc_documents
           (candidate_id, descendant_case_id, filename, file_path,
            file_checksum, file_size, mime_type, uploaded_by, visibilita, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'discendente', 'discendente', ?)""",
        (dc["candidate_id"], dcid, file.filename, str(file_path),
         checksum, len(content), file.content_type, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "checksum": checksum}


@router.post("/public/case/{dcid}/consent")
def public_set_consent(dcid: int, data: dict = Body(...)):
    conn = get_conn()
    dc = conn.execute("SELECT * FROM rc_descendant_cases WHERE id = ?", (dcid,)).fetchone()
    if not dc:
        conn.close()
        raise HTTPException(404, "Caso non trovato")
    conn.execute(
        "UPDATE rc_descendant_cases SET consenso = ?, delega = ?, updated_at = ? WHERE id = ?",
        (data.get("consenso", 0), data.get("delega"), _now(), dcid),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# MODULO PUBBLICO "Riconosci questo nominativo?"
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/public/recognize")
def public_recognize(data: dict = Body(...)):
    """Un familiare può manifestare interesse per un nominativo.
    NON espone dati del candidato. Crea un record di contatto pubblico."""
    conn = get_conn()
    now = _now()
    candidate_id = data.get("candidate_id")
    if candidate_id:
        cand = conn.execute("SELECT id FROM rc_candidates WHERE id = ?", (candidate_id,)).fetchone()
        if not cand:
            conn.close()
            raise HTTPException(404, "Candidato non trovato")
    cur = conn.execute(
        """INSERT INTO rc_contact_attempts
           (candidate_id, canale, intermediario, testo_approvato,
            esito, operatore, divieto_ulteriori, approvato,
            created_at, updated_at)
           VALUES (?, 'modulo_pubblico', NULL, ?, 'in_attesa', 'pubblico', 0, 0, ?, ?)""",
        (candidate_id, data.get("messaggio", ""), now, now),
    )
    coid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "contact_id": coid, "message": "Grazie per il suo interesse. Sarà ricontattato se il nominativo risulta pertinente."}


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAZIONE FASCICOLO PDF
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/candidates/{cid}/dossier")
def generate_dossier(request: Request, cid: int):
    user = require_auth(request)
    if not has_permission(user["role"], "rc:case:write"):
        raise HTTPException(403, "Permesso insufficiente")
    from rc_dossier import generate_pdf_dossier
    try:
        pdf_path = generate_pdf_dossier(cid)
        _audit(user, "generate_dossier", "candidate", cid, next_val={"file": str(pdf_path)})
        return FileResponse(str(pdf_path), media_type="application/pdf",
                            filename=f"fascicolo_{cid}.pdf")
    except Exception as e:
        raise HTTPException(500, f"Errore generazione fascicolo: {e}")
