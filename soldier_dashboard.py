"""Soldier Dashboard — aggregazione dati soldato + fonti federate.

Combina:
1. Dati certi locali (internati, decorati, caduti, menzioni)
2. Fatti base verificati
3. Timeline eventi
4. Fonti locali (archivio_fonti, fondi_archivistici)
5. Fonti esterne (source federation layer)
6. Stato fonte (locale/online/da_richiedere/non_accessibile)
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from database import get_conn
from search_service import search_entities, get_entity_network
from source_providers.federation import federated_search, get_registry
from source_providers.base import score_source, _dict_factory


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}


def _extract_cues_from_soldier(soldier: dict) -> dict:
    """Estrae cue strutturati dai dati del soldato."""
    cues = {}
    if soldier.get("cognome") or soldier.get("nome"):
        cues["persona"] = f"{soldier.get('nome', '')} {soldier.get('cognome', '')}".strip()
    if soldier.get("luogo_nascita"):
        cues["luogo"] = soldier["luogo_nascita"]
    if soldier.get("data_nascita"):
        cues["data"] = soldier["data_nascita"]
    if soldier.get("grado"):
        cues["grado"] = soldier["grado"]
    if soldier.get("luogo_internamento") or soldier.get("luogo_cattura"):
        cues["luogo_internamento"] = soldier.get("luogo_internamento") or soldier.get("luogo_cattura")
    if soldier.get("data_cattura"):
        cues["data_cattura"] = soldier["data_cattura"]
    if soldier.get("reparto") or soldier.get("unita"):
        cues["reparto"] = soldier.get("reparto") or soldier.get("unita")
    return cues


def _build_timeline(soldier: dict, events: list) -> list:
    """Costruisce una timeline cronologica di eventi."""
    timeline = []

    if soldier.get("data_nascita"):
        timeline.append({
            "date": soldier["data_nascita"],
            "event": "Nascita",
            "place": soldier.get("luogo_nascita", ""),
            "source": "locale",
        })
    if soldier.get("data_cattura"):
        timeline.append({
            "date": soldier["data_cattura"],
            "event": "Cattura",
            "place": soldier.get("luogo_cattura", ""),
            "source": "locale",
        })
    if soldier.get("data"):
        timeline.append({
            "date": soldier["data"],
            "event": soldier.get("sorte", "Evento"),
            "place": soldier.get("luogo_internamento", ""),
            "source": "locale",
        })
    if soldier.get("data_morte"):
        timeline.append({
            "date": soldier["data_morte"],
            "event": "Morte",
            "place": soldier.get("luogo_morte", ""),
            "source": "locale",
        })

    # aggiungi eventi dal grafo entità
    for ev in events:
        if ev.get("data") and ev.get("tipo") == "evento":
            timeline.append({
                "date": ev.get("data"),
                "event": ev.get("valore", ""),
                "place": ev.get("luogo", ""),
                "source": "entity_graph",
            })

    # sort per data (se parsable)
    def _sort_key(item):
        d = item.get("date", "")
        m = re.search(r"(\d{4})", str(d))
        return int(m.group(1)) if m else 9999
    timeline.sort(key=_sort_key)
    return timeline


def _get_local_sources(soldier_id: int, soldier: dict) -> list:
    """Recupera fonti locali già disponibili."""
    sources = []
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    # 1. archivio_fonti — cerca per reparto/unità
    reparto = soldier.get("reparto") or soldier.get("unita_principale") or ""
    if reparto:
        cur.execute("""
            SELECT id, sha256, nome_file, formato, archivio, fondo,
                   unita_principale, teatro, data_documento, tipo_documento,
                   ocr_status, path_locale
            FROM archivio_fonti
            WHERE LOWER(unita_principale) LIKE ?
               OR LOWER(testo_ocr) LIKE ?
            LIMIT 10
        """, (f"%{reparto.lower()}%", f"%{reparto.lower()}%"))
        for r in cur.fetchall():
            sources.append({
                "source": "local",
                "table": "archivio_fonti",
                "id": r["id"],
                "archivio": r.get("archivio", ""),
                "fondo": r.get("fondo", ""),
                "titolo": f"{r.get('tipo_documento', '')} — {r.get('unita_principale', '')}",
                "date": r.get("data_documento", ""),
                "format": r.get("formato", ""),
                "ocr_status": r.get("ocr_status", ""),
                "path_locale": r.get("path_locale", ""),
                "access_type": "locale",
                "downloadable": True,
                "confidence": 0.85,
            })

    # 2. fondi_archivistici — cerca menzioni collegate
    cognome = soldier.get("cognome", "")
    if cognome:
        cur.execute("""
            SELECT m.id, m.tipo, m.cognome, m.nome, m.grado, m.reparto,
                   m.luogo, m.data, m.contesto, f.titolo as fondo_titolo,
                   f.id as fondo_id, f.file_pdf, f.url, f.pagina
            FROM menzioni m
            LEFT JOIN fondi_archivistici f ON m.fondo_id = f.id
            WHERE LOWER(m.cognome) LIKE ?
            LIMIT 10
        """, (f"%{cognome.lower()}%",))
        for r in cur.fetchall():
            sources.append({
                "source": "local",
                "table": "menzioni",
                "id": r["id"],
                "archivio": "USSME",
                "fondo": r.get("fondo_titolo", ""),
                "titolo": f"Menzione: {r.get('cognome', '')} {r.get('nome', '')}",
                "date": r.get("data", ""),
                "context": r.get("contesto", "")[:200],
                "fondo_id": r.get("fondo_id"),
                "file_pdf": r.get("file_pdf", ""),
                "page": r.get("pagina"),
                "url": r.get("url", ""),
                "access_type": "locale",
                "downloadable": bool(r.get("file_pdf")),
                "confidence": 0.75,
            })

    # 3. documenti_nara_t315 — OCR frame
    if reparto:
        cur.execute("""
            SELECT id, roll, frame, testo_ocr, data_documento, tipo_documento,
                   unita_principale, teatro, affidabilita_ocr
            FROM documenti_nara_t315
            WHERE LOWER(unita_principale) LIKE ?
               OR LOWER(testo_ocr) LIKE ?
            LIMIT 10
        """, (f"%{reparto.lower()}%", f"%{cognome.lower()}%" if cognome else "%%%"))
        for r in cur.fetchall():
            sources.append({
                "source": "local",
                "table": "documenti_nara_t315",
                "id": r["id"],
                "archivio": "NARA",
                "fondo": "T315",
                "titolo": f"Frame {r.get('roll', '')}/{r.get('frame', '')} — {r.get('tipo_documento', '')}",
                "date": r.get("data_documento", ""),
                "ocr_excerpt": (r.get("testo_ocr") or "")[:200],
                "ocr_reliability": r.get("affidabilita_ocr", ""),
                "access_type": "locale",
                "downloadable": False,
                "confidence": 0.7,
            })

    conn.close()
    return sources


def _get_external_sources(soldier: dict, cues: dict) -> list:
    """Cerca fonti esterne via federation layer."""
    query = cues.get("persona", "")
    if not query:
        return []

    # filtri per Antenati (comune + anno nascita)
    filters = {}
    if soldier.get("luogo_nascita"):
        filters["comune"] = soldier["luogo_nascita"]
    if soldier.get("data_nascita"):
        m = re.search(r"(\d{4})", str(soldier.get("data_nascita", "")))
        if m:
            filters["anno_nascita"] = m.group(1)
    if soldier.get("data") or soldier.get("data_morte"):
        for key in ("data", "data_morte"):
            m = re.search(r"(\d{4})", str(soldier.get(key, "")))
            if m:
                filters["anno_morte"] = m.group(1)
                break

    # provider prioritari per soldati italiani WW2
    priority_providers = [
        "nara", "antenati", "cwgc", "ussme", "archivio_stato",
        "arolsen", "bundesarchiv", "europeana", "googlebooks",
        "internetarchive", "tna",
    ]

    results = federated_search(query, cues=cues, providers=priority_providers,
                               filters=filters)

    # arricchisci con stato fonte
    for r in results:
        if "error" in r:
            r["access_type"] = "errore"
            continue
        # classifica disponibilità
        at = r.get("access_type", "online")
        if at == "locale":
            r["availability"] = "locale"
        elif at == "online" and r.get("downloadable"):
            r["availability"] = "online"
        elif at == "online":
            r["availability"] = "online_no_download"
        elif at == "login":
            r["availability"] = "da_richiedere"
        elif at == "catalog_only":
            r["availability"] = "da_richiedere"
        else:
            r["availability"] = "non_accessibile"

    return results


def get_soldier_dashboard(soldier_id: int) -> dict:
    """Endpoint principale: GET /api/soldiers/{id}/dashboard

    Ritorna:
    - dati certi locali
    - fatti base verificati
    - timeline
    - fonti locali
    - fonti esterne federate
    - entità collegate
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    # 1. Dati soldato
    cur.execute("SELECT * FROM internati WHERE id=?", (soldier_id,))
    soldier = cur.fetchone()
    if not soldier:
        conn.close()
        return {"ok": False, "error": f"soldato id={soldier_id} non trovato"}

    soldier = dict(soldier)
    cues = _extract_cues_from_soldier(soldier)

    # 2. Entità collegate (grafo)
    entities = []
    cognome = soldier.get("cognome", "")
    nome = soldier.get("nome", "")
    if cognome:
        try:
            ent_results = search_entities(f"{cognome} {nome}", limit=5, tipo="persona")
            for e in ent_results:
                e["source"] = "entity_graph"
                entities.append(e)
        except Exception:
            pass

    # 3. Fatti base verificati
    facts = []
    if soldier.get("cognome"):
        facts.append({"fact": "Identità", "value": f"{soldier.get('nome', '')} {soldier['cognome']}", "verified": True})
    if soldier.get("data_nascita"):
        facts.append({"fact": "Data nascita", "value": soldier["data_nascita"], "verified": True})
    if soldier.get("luogo_nascita"):
        facts.append({"fact": "Luogo nascita", "value": soldier["luogo_nascita"], "verified": bool(soldier.get("luogo_validato"))})
    if soldier.get("grado"):
        facts.append({"fact": "Grado", "value": soldier["grado"], "verified": True})
    if soldier.get("luogo_cattura"):
        facts.append({"fact": "Luogo cattura", "value": soldier["luogo_cattura"], "verified": True})
    if soldier.get("data_cattura"):
        facts.append({"fact": "Data cattura", "value": soldier["data_cattura"], "verified": True})
    if soldier.get("luogo_internamento"):
        facts.append({"fact": "Luogo internamento", "value": soldier["luogo_internamento"], "verified": True})
    if soldier.get("sorte"):
        facts.append({"fact": "Sorte", "value": soldier["sorte"], "verified": True})
    if soldier.get("matricola"):
        facts.append({"fact": "Matricola", "value": soldier["matricola"], "verified": True})
    if soldier.get("arbeitskommando"):
        facts.append({"fact": "Arbeitskommando", "value": soldier["arbeitskommando"], "verified": True})

    # 4. Timeline
    timeline = _build_timeline(soldier, entities)

    # 5. Fonti locali
    local_sources = _get_local_sources(soldier_id, soldier)

    conn.close()

    # 6. Fonti esterne (federation)
    external_sources = _get_external_sources(soldier, cues)

    return {
        "ok": True,
        "soldier_id": soldier_id,
        "soldier": soldier,
        "cues": cues,
        "facts": facts,
        "timeline": timeline,
        "entities": entities,
        "local_sources": local_sources,
        "external_sources": external_sources,
        "summary": {
            "local_count": len(local_sources),
            "external_count": len(external_sources),
            "entities_count": len(entities),
            "facts_count": len(facts),
            "timeline_count": len(timeline),
        },
    }


def get_soldier_sources(soldier_id: int) -> dict:
    """Endpoint: GET /api/soldiers/{id}/sources

    Ritorna solo fonti (locali + esterne) senza dati completi.
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute("SELECT * FROM internati WHERE id=?", (soldier_id,))
    soldier = cur.fetchone()
    conn.close()
    if not soldier:
        return {"ok": False, "error": f"soldato id={soldier_id} non trovato"}

    soldier = dict(soldier)
    cues = _extract_cues_from_soldier(soldier)
    local = _get_local_sources(soldier_id, soldier)
    external = _get_external_sources(soldier, cues)

    return {
        "ok": True,
        "soldier_id": soldier_id,
        "local_sources": local,
        "external_sources": external,
        "total": len(local) + len(external),
    }


def get_soldier_fonti_indice(soldier_id: int, limit: int = 50) -> dict:
    """Endpoint: GET /api/internati/{id}/fonti

    Restituisce tutte le fonti archivistiche da fonti_indice
    matchate per cognome del soldato, raggruppate per archivio.
    Include metadati OpenGraph per ogni fonte.
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    soldier = conn.execute("SELECT * FROM internati WHERE id=?", (soldier_id,)).fetchone()
    if not soldier:
        conn.close()
        return {"ok": False, "error": f"soldato id={soldier_id} non trovato"}

    soldier = dict(soldier)
    cognome = (soldier.get("cognome") or "").strip()
    nome = (soldier.get("nome") or "").strip()

    luogo_nascita = (soldier.get("luogo_nascita") or "").strip()

    rows = []
    if cognome:
        rows = conn.execute(
            """SELECT id, archivio, fondo, serie, titolo, segnatura,
                      url_catalogo, access_type, confidence, tipo_fonte,
                      data_inizio, soggetti_collegati, persone_possibili
               FROM fonti_indice
               WHERE LOWER(titolo) LIKE ?
                  OR LOWER(segnatura) LIKE ?
                  OR LOWER(persone_possibili) LIKE ?
               ORDER BY confidence DESC, archivio
               LIMIT ?""",
            (f"%{cognome.lower()}%", f"%{cognome.lower()}%",
             f"%{cognome.lower()}%", limit),
        ).fetchall()

    # Aggiungi sempre il registro ONORCADUTI della provincia di nascita (se esiste)
    acs_row = None
    if luogo_nascita:
        acs_row = conn.execute(
            """SELECT id, archivio, fondo, serie, titolo, segnatura,
                      url_catalogo, access_type, confidence, tipo_fonte,
                      data_inizio, soggetti_collegati, persone_possibili
               FROM fonti_indice
               WHERE archivio LIKE '%ONORCADUTI%'
                 AND LOWER(titolo) LIKE ?
               LIMIT 1""",
            (f"%{luogo_nascita.lower()[:10]}%",),
        ).fetchone()

    conn.close()

    # Aggiungi il registro ACS della provincia se non già incluso
    if acs_row and not any(r["id"] == acs_row["id"] for r in rows):
        rows = list(rows) + [acs_row]

    by_archive: Dict[str, list] = {}
    for r in rows:
        arch = r.get("archivio") or "Altro"
        by_archive.setdefault(arch, []).append({
            "id": r["id"],
            "titolo": r.get("titolo", ""),
            "segnatura": r.get("segnatura", ""),
            "fondo": r.get("fondo", ""),
            "serie": r.get("serie", ""),
            "url": r.get("url_catalogo") or "",
            "access_type": r.get("access_type", "online"),
            "confidence": r.get("confidence", 0.5),
            "source_type": r.get("tipo_fonte", ""),
            "date_start": r.get("data_inizio", ""),
        })

    return {
        "ok": True,
        "soldier_id": soldier_id,
        "cognome": cognome,
        "nome": nome,
        "total": len(rows),
        "by_archive": by_archive,
        "archives": sorted(by_archive.keys()),
    }


def get_soldier_opengraph(soldier_id: int) -> dict:
    """Endpoint: GET /api/internati/{id}/opengraph

    Genera metadati OpenGraph-style per condivisione social/link.
    Include descrizione sintetica, fatti verificati e link alle fonti.
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    soldier = conn.execute("SELECT * FROM internati WHERE id=?", (soldier_id,)).fetchone()
    if not soldier:
        conn.close()
        return {"ok": False, "error": f"soldato id={soldier_id} non trovato"}

    soldier = dict(soldier)
    conn.close()

    cognome = soldier.get("cognome") or ""
    nome = soldier.get("nome") or ""
    full_name = f"{nome} {cognome}".strip()

    parts = [f"IMI – {full_name}"]
    if soldier.get("grado"):
        parts.append(soldier["grado"])
    if soldier.get("data_nascita"):
        parts.append(f"n. {soldier['data_nascita']}")
    if soldier.get("luogo_nascita"):
        parts.append(soldier["luogo_nascita"])
    if soldier.get("luogo_cattura") and soldier.get("data_cattura"):
        parts.append(f"catturato {soldier['data_cattura']} a {soldier['luogo_cattura']}")
    elif soldier.get("luogo_cattura"):
        parts.append(f"catturato a {soldier['luogo_cattura']}")
    if soldier.get("luogo_internamento"):
        parts.append(f"internato a {soldier['luogo_internamento']}")
    if soldier.get("sorte"):
        parts.append(f"sorte: {soldier['sorte']}")

    description = " | ".join(parts)

    fonti_res = get_soldier_fonti_indice(soldier_id, limit=5)
    source_preview = []
    for arch, items in (fonti_res.get("by_archive") or {}).items():
        if items:
            source_preview.append({
                "archivio": arch,
                "titolo": items[0].get("titolo", ""),
                "url": items[0].get("url", ""),
            })

    return {
        "ok": True,
        "soldier_id": soldier_id,
        "og": {
            "title": f"{full_name} — Internato Militare Italiano (WW2)",
            "description": description,
            "type": "article",
            "site_name": "VOCI DAL FRONTE — Ricerca Storica IMI",
            "article:tag": ["IMI", "internati militari", "seconda guerra mondiale", cognome],
        },
        "card": {
            "name": full_name,
            "matricola": soldier.get("matricola", ""),
            "grado": soldier.get("grado", ""),
            "nascita": f"{soldier.get('data_nascita','')} {soldier.get('luogo_nascita','')}".strip(),
            "cattura": f"{soldier.get('data_cattura','')} {soldier.get('luogo_cattura','')}".strip(),
            "internamento": soldier.get("luogo_internamento", ""),
            "arbeitskommando": soldier.get("arbeitskommando", ""),
            "sorte": soldier.get("sorte", ""),
            "fonti_count": fonti_res.get("total", 0),
            "fonti_preview": source_preview,
        },
    }


def analyze_sources(source_ids: List[int], query: str = "") -> dict:
    """Endpoint: POST /api/sources/analyze

    Prepara contesto minimo per AI analysis.
    Il backend decide quali fonti aprire, l'AI non scarica nulla.
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    context_parts = []
    for sid in source_ids[:5]:  # max 5 fonti
        cur.execute("SELECT * FROM fonti_indice WHERE id=?", (sid,))
        meta = cur.fetchone()
        if not meta:
            continue

        part = {
            "source_id": sid,
            "archivio": meta.get("archivio"),
            "titolo": meta.get("titolo"),
            "segnatura": meta.get("segnatura"),
            "url": meta.get("url_catalogo") or meta.get("url_file"),
            "access_type": meta.get("access_type"),
            "fetch_status": meta.get("fetch_status"),
        }

        # se c'è contenuto in cache, includi excerpt
        cur.execute("SELECT path_file, content_type FROM source_fetch_cache "
                    "WHERE source_id=? ORDER BY fetched_at DESC LIMIT 1", (sid,))
        cache = cur.fetchone()
        if cache and cache.get("path_file"):
            part["cached"] = True
            part["content_type"] = cache.get("content_type")
            # se testo, leggi prime righe
            if cache.get("content_type", "").startswith("text/"):
                try:
                    with open(cache["path_file"], "r", encoding="utf-8", errors="replace") as f:
                        part["excerpt"] = f.read()[:2000]
                except Exception:
                    pass
        else:
            part["cached"] = False

        context_parts.append(part)

    conn.close()

    return {
        "ok": True,
        "query": query,
        "sources": context_parts,
        "context_size": sum(len(str(p.get("excerpt", ""))) for p in context_parts),
        "note": "Il backend ha selezionato queste fonti. L'AI riceve solo "
                "metadati ed excerpt testuali. I documenti originali restano "
                "la fonte primaria.",
    }
