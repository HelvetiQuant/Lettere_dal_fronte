"""Modulo per l'estrazione di entita (persone, luoghi, eventi) da tutti i dataset
e la creazione di collegamenti cross-dataset. Permette di partire da un nome,
luogo, data o evento e trovare tutti i record collegati nei vari fondi."""
import json
import re
import threading
from datetime import datetime
from typing import Optional

from database import (
    get_conn, save_entita, count_entita, count_collegamenti,
)


stop_event = threading.Event()
_progress = {"status": "idle", "processed": 0, "total": 0, "current": ""}


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def is_stop_requested() -> bool:
    return stop_event.is_set()


def get_progress() -> dict:
    return dict(_progress)


def _norm(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().lower())


ALL_TABLES = (
    "internati", "decorati", "menzioni", "fondi_archivistici",
    "caduti_ministero", "caduti_sardi", "caduti_bologna", "caduti_albooro",
)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _already_linked(table: str) -> int:
    """Max record_id già linkato per questa tabella (0 = nessuno)."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT MAX(record_id) FROM collegamenti WHERE tabella_origine=?",
            (table,)
        ).fetchone()
        return row[0] if (row and row[0] is not None) else 0
    finally:
        conn.close()


def build_links(resume: bool = True):
    """Estrae entita da tutte le tabelle e crea collegamenti cross-dataset."""
    stop_event.clear()
    conn = get_conn()

    # Conta record totali da processare
    counts = {}
    for tab in ALL_TABLES:
        if _table_exists(conn, tab):
            counts[tab] = conn.execute(f"SELECT COUNT(*) as c FROM {tab}").fetchone()["c"]
        else:
            counts[tab] = 0
    total = sum(counts.values())
    _progress.update({"status": "processing", "processed": 0, "total": total, "current": "internati"})
    conn.close()

    processed = 0

    # ─── Internati: estrai persone e luoghi ───
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, cognome, nome, luogo_nascita, residenza, luogo_internamento,
                  luogo_cattura, grado, data_nascita, sorte, data
           FROM internati"""
    ).fetchall()
    conn.close()
    for r in rows:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return
        processed += 1
        _progress["processed"] = processed
        _progress["current"] = f"internati:{r['id']}"
        # Persona
        if r["cognome"]:
            save_entita("persona", f"{r['cognome']} {r['nome'] or ''}".strip(),
                        "internati", r["id"],
                        cognome=r["cognome"], nome=r["nome"],
                        data=r["data_nascita"], luogo=r["luogo_nascita"])
        # Luoghi
        for campo, val in [("luogo_nascita", r["luogo_nascita"]),
                           ("residenza", r["residenza"]),
                           ("luogo_internamento", r["luogo_internamento"]),
                           ("luogo_cattura", r["luogo_cattura"])]:
            if val and val.strip():
                save_entita("luogo", val.strip(), "internati", r["id"],
                            luogo=val.strip(), contesto=campo)
        # Evento (sorte)
        if r["sorte"] and r["data"]:
            save_entita("evento", f"{r['sorte']} - {r['data']}", "internati", r["id"],
                        data=r["data"], contesto=r["sorte"])

    # ─── Decorati: estrai persone e luoghi ───
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, cognome, nome, comune_nascita, comune_residenza, grado,
                  luogo_morte, luogo_internamento, data_nascita, data_morte,
                  decorazione, guerra
           FROM decorati"""
    ).fetchall()
    conn.close()
    for r in rows:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return
        processed += 1
        _progress["processed"] = processed
        _progress["current"] = f"decorati:{r['id']}"
        if r["cognome"]:
            save_entita("persona", f"{r['cognome']} {r['nome'] or ''}".strip(),
                        "decorati", r["id"],
                        cognome=r["cognome"], nome=r["nome"],
                        data=r["data_nascita"], luogo=r["comune_nascita"])
        for campo, val in [("comune_nascita", r["comune_nascita"]),
                           ("comune_residenza", r["comune_residenza"]),
                           ("luogo_morte", r["luogo_morte"]),
                           ("luogo_internamento", r["luogo_internamento"])]:
            if val and val.strip():
                save_entita("luogo", val.strip(), "decorati", r["id"],
                            luogo=val.strip(), contesto=campo)
        if r["decorazione"]:
            save_entita("decorazione", r["decorazione"], "decorati", r["id"],
                        contesto=r["guerra"])

    # ─── Menzioni: estrai persone e luoghi ───
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, cognome, nome, grado, reparto, luogo, data, contesto
           FROM menzioni"""
    ).fetchall()
    conn.close()
    for r in rows:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return
        processed += 1
        _progress["processed"] = processed
        _progress["current"] = f"menzioni:{r['id']}"
        if r["cognome"]:
            save_entita("persona", f"{r['cognome']} {r['nome'] or ''}".strip(),
                        "menzioni", r["id"],
                        cognome=r["cognome"], nome=r["nome"],
                        data=r["data"], luogo=r["luogo"], contesto=r["contesto"])
        if r["luogo"] and r["luogo"].strip():
            save_entita("luogo", r["luogo"].strip(), "menzioni", r["id"],
                        luogo=r["luogo"].strip(), contesto=r["contesto"])

    # ─── Fondi archivistici: estrai luoghi e descrizioni ───
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, codice_fondo, titolo, descrizione, periodo, luoghi
           FROM fondi_archivistici"""
    ).fetchall()
    conn.close()
    for r in rows:
        if stop_event.is_set():
            _progress["status"] = "stopped"
            return
        processed += 1
        _progress["processed"] = processed
        _progress["current"] = f"fondi:{r['id']}"
        if r["luoghi"] and r["luoghi"].strip():
            for luogo in re.split(r"[,;]", r["luoghi"]):
                luogo = luogo.strip()
                if luogo:
                    save_entita("luogo", luogo, "fondi_archivistici", r["id"],
                                luogo=luogo, contesto=r["titolo"])
        if r["periodo"] and r["periodo"].strip():
            save_entita("periodo", r["periodo"].strip(), "fondi_archivistici", r["id"],
                        data=r["periodo"], contesto=r["titolo"])

    # ─── Caduti Ministero Difesa: persone e luoghi ───
    conn = get_conn()
    if _table_exists(conn, "caduti_ministero"):
        already = _already_linked("caduti_ministero") if resume else 0
        rows = conn.execute(
            "SELECT id, cognome, nome, comune_nascita, provincia_nascita, luogo_sepoltura, "
            "data_nascita, data_decesso, nazione_decesso FROM caduti_ministero"
        ).fetchall()
        conn.close()
        _progress["current"] = "caduti_ministero"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["cognome"]:
                save_entita("persona", f"{r['cognome']} {r['nome'] or ''}".strip(),
                            "caduti_ministero", r["id"],
                            cognome=r["cognome"], nome=r["nome"],
                            data=r["data_nascita"], luogo=r["comune_nascita"])
            for campo, val in [("comune_nascita", r["comune_nascita"]),
                               ("provincia_nascita", r["provincia_nascita"]),
                               ("luogo_sepoltura", r["luogo_sepoltura"]),
                               ("nazione_decesso", r["nazione_decesso"])]:
                if val and val.strip():
                    save_entita("luogo", val.strip(), "caduti_ministero", r["id"],
                                luogo=val.strip(), contesto=campo)
            if r["data_decesso"]:
                save_entita("evento", f"deceduto - {r['data_decesso']}", "caduti_ministero",
                            r["id"], data=r["data_decesso"], contesto="caduto in guerra")
    else:
        conn.close()

    # ─── Caduti Sardi: persone e luoghi ───
    conn = get_conn()
    if _table_exists(conn, "caduti_sardi"):
        already = _already_linked("caduti_sardi") if resume else 0
        rows = conn.execute(
            "SELECT id, cognome, nome, comune_residenza, luogo_morte, "
            "data_nascita, data_morte, guerra FROM caduti_sardi"
        ).fetchall()
        conn.close()
        _progress["current"] = "caduti_sardi"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["cognome"]:
                save_entita("persona", f"{r['cognome']} {r['nome'] or ''}".strip(),
                            "caduti_sardi", r["id"],
                            cognome=r["cognome"], nome=r["nome"],
                            data=r["data_nascita"], luogo=r["comune_residenza"])
            for campo, val in [("comune_residenza", r["comune_residenza"]),
                               ("luogo_morte", r["luogo_morte"])]:
                if val and val.strip():
                    save_entita("luogo", val.strip(), "caduti_sardi", r["id"],
                                luogo=val.strip(), contesto=campo)
            if r["data_morte"]:
                save_entita("evento", f"deceduto - {r['data_morte']}", "caduti_sardi",
                            r["id"], data=r["data_morte"], contesto=r["guerra"] or "caduto")
    else:
        conn.close()

    # ─── Caduti Bolognesi: persone e luoghi ───
    conn = get_conn()
    if _table_exists(conn, "caduti_bologna"):
        already = _already_linked("caduti_bologna") if resume else 0
        rows = conn.execute(
            "SELECT id, nome, luogo_nascita, luogo_dimora, luogo_morte, "
            "data_morte, anno_nascita FROM caduti_bologna"
        ).fetchall()
        conn.close()
        _progress["current"] = "caduti_bologna"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["nome"]:
                parts = r["nome"].strip().split(None, 1)
                cognome_b = parts[0] if parts else r["nome"]
                nome_b = parts[1] if len(parts) > 1 else ""
                save_entita("persona", r["nome"].strip(),
                            "caduti_bologna", r["id"],
                            cognome=cognome_b, nome=nome_b,
                            data=str(r["anno_nascita"]) if r["anno_nascita"] else None,
                            luogo=r["luogo_nascita"])
            for campo, val in [("luogo_nascita", r["luogo_nascita"]),
                               ("luogo_dimora", r["luogo_dimora"]),
                               ("luogo_morte", r["luogo_morte"])]:
                if val and val.strip():
                    save_entita("luogo", val.strip(), "caduti_bologna", r["id"],
                                luogo=val.strip(), contesto=campo)
            if r["data_morte"]:
                save_entita("evento", f"deceduto - {r['data_morte']}", "caduti_bologna",
                            r["id"], data=r["data_morte"], contesto="caduto in guerra")
    else:
        conn.close()

    # ─── Caduti Albo d'Oro: persone e luoghi ───
    conn = get_conn()
    if _table_exists(conn, "caduti_albooro"):
        already = _already_linked("caduti_albooro") if resume else 0
        rows = conn.execute(
            "SELECT id, nominativo, comune_attuale, luogo_morte, anno_morte "
            "FROM caduti_albooro"
        ).fetchall()
        conn.close()
        _progress["current"] = "caduti_albooro"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["nominativo"]:
                parts = r["nominativo"].strip().split(None, 1)
                cognome_a = parts[0] if parts else r["nominativo"]
                nome_a = parts[1] if len(parts) > 1 else ""
                save_entita("persona", r["nominativo"].strip(),
                            "caduti_albooro", r["id"],
                            cognome=cognome_a, nome=nome_a,
                            luogo=r["comune_attuale"])
            for campo, val in [("comune_attuale", r["comune_attuale"]),
                               ("luogo_morte", r["luogo_morte"])]:
                if val and val.strip():
                    save_entita("luogo", val.strip(), "caduti_albooro", r["id"],
                                luogo=val.strip(), contesto=campo)
            if r["anno_morte"]:
                save_entita("evento", f"deceduto - {r['anno_morte']}", "caduti_albooro",
                            r["id"], data=str(r["anno_morte"]), contesto="caduto in guerra")
    else:
        conn.close()

    # ─── Caduti CWGC: persone, luoghi, eventi ───
    conn = get_conn()
    if _table_exists(conn, "caduti_cwgc"):
        already = _already_linked("caduti_cwgc") if resume else 0
        rows = conn.execute(
            "SELECT id, cognome, nome, initials, rank, regiment, nationality, "
            "data_morte, data_nascita, cimitero, paese_cimitero, guerra "
            "FROM caduti_cwgc"
        ).fetchall()
        conn.close()
        _progress["current"] = "caduti_cwgc"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["cognome"]:
                full_name = f"{r['cognome']} {r['nome'] or r['initials'] or ''}".strip()
                save_entita("persona", full_name, "caduti_cwgc", r["id"],
                            cognome=r["cognome"], nome=r["nome"] or r["initials"],
                            data=r["data_nascita"], luogo=r["paese_cimitero"])
            for campo, val in [("cimitero", r["cimitero"]),
                               ("paese_cimitero", r["paese_cimitero"])]:
                if val and val.strip():
                    save_entita("luogo", val.strip(), "caduti_cwgc", r["id"],
                                luogo=val.strip(), contesto=campo)
            if r["regiment"]:
                save_entita("unita", r["regiment"], "caduti_cwgc", r["id"],
                            contesto="regiment")
            if r["data_morte"]:
                save_entita("evento", f"deceduto - {r['data_morte']}", "caduti_cwgc",
                            r["id"], data=r["data_morte"], contesto=r["guerra"] or "caduto")
    else:
        conn.close()

    # ─── Decorati Nastro Azzurro: persone ───
    conn = get_conn()
    if _table_exists(conn, "decorati_nastroazzurro"):
        already = _already_linked("decorati_nastroazzurro") if resume else 0
        rows = conn.execute(
            "SELECT id, cognome, nome, arma, tipo_decorazione, anno_decorazione "
            "FROM decorati_nastroazzurro"
        ).fetchall()
        conn.close()
        _progress["current"] = "decorati_nastroazzurro"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["cognome"]:
                full_name = f"{r['cognome']} {r['nome'] or ''}".strip()
                save_entita("persona", full_name, "decorati_nastroazzurro", r["id"],
                            cognome=r["cognome"], nome=r["nome"],
                            data=r["anno_decorazione"], contesto=r["tipo_decorazione"])
            if r["arma"]:
                save_entita("unita", r["arma"], "decorati_nastroazzurro", r["id"],
                            contesto="arma")
            if r["tipo_decorazione"]:
                save_entita("decorazione", r["tipo_decorazione"], "decorati_nastroazzurro",
                            r["id"], data=r["anno_decorazione"], contesto=r["arma"])
    else:
        conn.close()

    # ─── Caduti Francia WW1: persone, luoghi ───
    conn = get_conn()
    if _table_exists(conn, "caduti_francia_ww1"):
        already = _already_linked("caduti_francia_ww1") if resume else 0
        rows = conn.execute(
            "SELECT id, nom, grade, unite, lieu_naissance, bureau_recrutement, "
            "date_deces, lieu_deces, pays_deces, classe "
            "FROM caduti_francia_ww1"
        ).fetchall()
        conn.close()
        _progress["current"] = "caduti_francia_ww1"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["nom"]:
                parts = r["nom"].strip().split(None, 1)
                cognome_f = parts[0] if parts else r["nom"]
                nome_f = parts[1] if len(parts) > 1 else ""
                save_entita("persona", r["nom"].strip(), "caduti_francia_ww1", r["id"],
                            cognome=cognome_f, nome=nome_f,
                            luogo=r["lieu_naissance"])
            for campo, val in [("lieu_naissance", r["lieu_naissance"]),
                               ("bureau_recrutement", r["bureau_recrutement"]),
                               ("lieu_deces", r["lieu_deces"]),
                               ("pays_deces", r["pays_deces"])]:
                if val and val.strip():
                    save_entita("luogo", val.strip(), "caduti_francia_ww1", r["id"],
                                luogo=val.strip(), contesto=campo)
            if r["unite"]:
                save_entita("unita", r["unite"], "caduti_francia_ww1", r["id"],
                            contesto="unite")
            if r["date_deces"]:
                save_entita("evento", f"deceduto - {r['date_deces']}", "caduti_francia_ww1",
                            r["id"], data=r["date_deces"], contesto="caduto WW1")
    else:
        conn.close()

    # ─── Documenti NARA T315: luoghi, unita, eventi ───
    conn = get_conn()
    if _table_exists(conn, "documenti_nara_t315"):
        already = _already_linked("documenti_nara_t315") if resume else 0
        rows = conn.execute(
            "SELECT id, tipo_documento, data_documento, mittente, destinatario, "
            "unita_citate, luoghi_citati, perdite, divisione "
            "FROM documenti_nara_t315"
        ).fetchall()
        conn.close()
        _progress["current"] = "documenti_nara_t315"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["luoghi_citati"] and r["luoghi_citati"].strip():
                for luogo in re.split(r"[,;]", r["luoghi_citati"]):
                    luogo = luogo.strip()
                    if luogo:
                        save_entita("luogo", luogo, "documenti_nara_t315", r["id"],
                                    luogo=luogo, contesto=r["tipo_documento"])
            if r["unita_citate"] and r["unita_citate"].strip():
                for unita in re.split(r"[,;]", r["unita_citate"]):
                    unita = unita.strip()
                    if unita:
                        save_entita("unita", unita, "documenti_nara_t315", r["id"],
                                    contesto=r["divisione"] or "")
            if r["data_documento"]:
                save_entita("evento", f"documento - {r['data_documento']}", "documenti_nara_t315",
                            r["id"], data=r["data_documento"], contesto=r["tipo_documento"] or "")
    else:
        conn.close()

    # ─── Documenti NARA Catalog: luoghi, unita ───
    conn = get_conn()
    if _table_exists(conn, "documenti_nara_catalog"):
        already = _already_linked("documenti_nara_catalog") if resume else 0
        rows = conn.execute(
            "SELECT id, title, description, record_group, series, inclusive_dates, "
            "unit, location, document_type "
            "FROM documenti_nara_catalog"
        ).fetchall()
        conn.close()
        _progress["current"] = "documenti_nara_catalog"
        for r in rows:
            if stop_event.is_set():
                _progress["status"] = "stopped"
                return
            processed += 1
            _progress["processed"] = processed
            if resume and already > 0 and r["id"] <= already:
                continue
            if r["location"] and r["location"].strip():
                save_entita("luogo", r["location"].strip(), "documenti_nara_catalog", r["id"],
                            luogo=r["location"].strip(), contesto=r["title"])
            if r["unit"] and r["unit"].strip():
                save_entita("unita", r["unit"].strip(), "documenti_nara_catalog", r["id"],
                            contesto=r["record_group"] or "")
            if r["inclusive_dates"] and r["inclusive_dates"].strip():
                save_entita("periodo", r["inclusive_dates"].strip(), "documenti_nara_catalog",
                            r["id"], data=r["inclusive_dates"], contesto=r["title"])
    else:
        conn.close()

    _progress["status"] = "done"
    _progress["current"] = ""
    return {
        "entita": count_entita(),
        "collegamenti": count_collegamenti(),
    }


def find_cross_references(name: str) -> list[dict]:
    """Trova tutte le occorrenze di una persona/luogo nei vari dataset."""
    conn = get_conn()
    norm = _norm(name)
    results = []
    # Cerca per cognome+nome nei vari dataset
    parts = norm.split()
    cognome = parts[0] if parts else norm
    like = f"%{cognome}%"

    internati = conn.execute(
        """SELECT id, cognome, nome, luogo_nascita, residenza, grado,
                  luogo_internamento, sorte, lettera, pagina
           FROM internati WHERE cognome LIKE ? ORDER BY cognome LIMIT 50""",
        (like,),
    ).fetchall()
    for r in internati:
        results.append({"dataset": "internati", "record": dict(r)})

    decorati = conn.execute(
        """SELECT id, cognome, nome, comune_nascita, grado, decorazione,
                  guerra, luogo_morte, url_scheda
           FROM decorati WHERE cognome LIKE ? ORDER BY cognome LIMIT 50""",
        (like,),
    ).fetchall()
    for r in decorati:
        results.append({"dataset": "decorati", "record": dict(r)})

    menzioni = conn.execute(
        """SELECT m.id, m.cognome, m.nome, m.grado, m.luogo, m.contesto,
                  f.codice_fondo, f.titolo
           FROM menzioni m LEFT JOIN fondi_archivistici f ON m.fondo_id = f.id
           WHERE m.cognome LIKE ? LIMIT 50""",
        (like,),
    ).fetchall()
    for r in menzioni:
        results.append({"dataset": "menzioni", "record": dict(r)})

    conn.close()
    return results
