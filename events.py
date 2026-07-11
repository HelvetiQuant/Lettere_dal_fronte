"""Event layer — collega internati ed entità a eventi storici curati.

Fornisce:
- mappatura euristica internato → eventi (da luogo_cattura, luogo_internamento,
  arbeitskommando, ecc.)
- lista eventi curati in fonti_indice
- recupero fonti multilaterali per evento
"""

import json
import re
import sqlite3
from typing import List, Dict, Optional

from database import get_conn, DB_PATH
import source_locator


# Eventi curati con keyword di matching sui campi degli internati.
# Per ogni evento si definiscono i campi da cercare e le keyword.
EVENTI_CURATI = [
    {
        "id": "cefalonia",
        "nome": "Eccidio di Cefalonia (settembre 1943)",
        "keywords": ["cefalonia", "acqui", "corfù", "corfu"],
        "campi": ["luogo_cattura", "luogo_internamento", "raw_text"],
        "descrizione": "Scontri e rappresaglia tedesca contro la Divisione Acqui.",
    },
    {
        "id": "mauthausen_gusen",
        "nome": "Campi di concentramento di Mauthausen e Gusen",
        "keywords": ["mauthausen", "gusen", "linz"],
        "campi": ["luogo_internamento", "arbeitskommando", "raw_text"],
        "descrizione": "Internamento, lavoro forzato e morte nei campi del sistema Mauthausen-Gusen.",
    },
    {
        "id": "tobruk",
        "nome": "Battaglia di Tobruk e prigionia (gennaio 1941)",
        "keywords": ["tobruk", "tobruch", "tripoli"],
        "campi": ["luogo_cattura", "luogo_internamento", "raw_text"],
        "descrizione": "Caduta di Tobruk e cattura di migliaia di soldati italiani.",
    },
    {
        "id": "armir_russia",
        "nome": "Campagna italiana in Russia (ARMIR, 1941-1943)",
        "keywords": [
            "russia", "armir", "stalingrado", "stalingrad", "don", "ukraina",
            "bessarabia", "romania", "odessa", "sevastopol", "taganrog", "renci",
        ],
        "campi": ["luogo_cattura", "luogo_internamento", "arbeitskommando", "raw_text"],
        "descrizione": "Operazioni dell'ARMIR sul fronte orientale e ritirata invernale 1942-43.",
    },
    {
        "id": "operazione_achse",
        "nome": "Operazione Achse e internamento militare italiano (1943-1945)",
        "keywords": [
            "achse", "internati militari", "imi", "armistizio", "8 settembre",
            "germania", "lavoro forzato",
        ],
        "campi": ["luogo_cattura", "luogo_internamento", "arbeitskommando", "raw_text", "sorte"],
        "descrizione": "Disarmo delle forze armate italiane e deportazione nel Terzo Reich.",
    },
    {
        "id": "lavoro_forzato",
        "nome": "Lavoro forzato italiano nel Terzo Reich (1943-1945)",
        "keywords": [
            "lavoro forzato", "arbeitskommando", "imi", "campo lavoro",
            "forzato", "berlino", "amburgo", "hannover", "essen", "dresda",
        ],
        "campi": ["luogo_internamento", "arbeitskommando", "mansione", "raw_text", "sorte"],
        "descrizione": "Impiego di Internati Militari Italiani come manodopera coatta in Germania.",
    },
]

# Indice nome -> evento per lookup rapido
_NOME_A_EVENTO = {e["nome"]: e for e in EVENTI_CURATI}


def get_eventi_curati() -> List[Dict]:
    """Restituisce la lista degli eventi curati con conteggio fonti."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    eventi = []
    for e in EVENTI_CURATI:
        count = cur.execute(
            "SELECT COUNT(1) FROM fonti_indice WHERE soggetti_collegati = ?",
            (e["nome"],),
        ).fetchone()[0]
        eventi.append({**e, "fonti_count": count})
    conn.close()
    return eventi


def match_eventi_per_internato(internato: Dict) -> List[Dict]:
    """Restituisce gli eventi curati potenzialmente collegati a un record internato."""
    matches = []
    text = " ".join(
        str(internato.get(c, "") or "") for c in
        ["luogo_cattura", "luogo_internamento", "arbeitskommando", "raw_text", "sorte", "mansione"]
    ).lower()
    for e in EVENTI_CURATI:
        for kw in e["keywords"]:
            if kw.lower() in text:
                matches.append({
                    "id": e["id"],
                    "nome": e["nome"],
                    "descrizione": e["descrizione"],
                    "matched_keyword": kw,
                })
                break
    return matches


def get_internati_per_evento(evento_nome: str, limit: int = 50, offset: int = 0) -> Dict:
    """Recupera gli internati probabilmente collegati a un evento curato."""
    evento = _NOME_A_EVENTO.get(evento_nome)
    if not evento:
        return {"evento": evento_nome, "internati": [], "total": 0}

    keywords = evento["keywords"]
    # costruisci OR di LIKE sui campi rilevanti
    campi = evento["campi"]
    conditions = []
    params = []
    for campo in campi:
        for kw in keywords:
            conditions.append(f"LOWER({campo}) LIKE ?")
            params.append(f"%{kw.lower()}%")

    sql_total = f"SELECT COUNT(1) FROM internati WHERE {' OR '.join(conditions)}"
    sql = (
        f"SELECT * FROM internati WHERE {' OR '.join(conditions)} "
        f"ORDER BY id LIMIT ? OFFSET ?"
    )
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    total = cur.execute(sql_total, params).fetchone()[0]
    rows = cur.execute(sql, (*params, limit, offset)).fetchall()
    conn.close()
    return {
        "evento": evento_nome,
        "internati": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_evento_fonti(evento_nome: str, limit: int = 100) -> Dict:
    """Restituisce le fonti multilaterali per un evento, raggruppate per fazione."""
    base = source_locator.find_sources_by_subject(evento_nome, limit=limit)
    # raggruppa per fazione (estrae da note_parsed.fazione)
    gruppi = {}
    for f in base["candidates"]:
        fazione = "Altro"
        np = f.get("note_parsed") or {}
        if isinstance(np, dict) and np.get("fazione"):
            fazione = np["fazione"]
        gruppi.setdefault(fazione, []).append(f)
    return {
        "evento": base["subject"],
        "total": base["total"],
        "fonti_per_fazione": gruppi,
    }


def get_internato_eventi(internato_id: int) -> Dict:
    """Restituisce eventi curati + fonti correlate per uno specifico internato."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM internati WHERE id=?", (internato_id,)).fetchone()
    conn.close()
    if not row:
        return {"ok": False, "error": "internato non trovato"}
    internato = dict(row)
    eventi = match_eventi_per_internato(internato)
    for ev in eventi:
        ev["fonti"] = source_locator.find_sources_by_subject(ev["nome"], limit=20)["candidates"]
    return {"ok": True, "internato": internato, "eventi": eventi}


def search_eventi_in_fonti_indice(query: str, limit: int = 20) -> List[str]:
    """Cerca eventi per nome o keyword."""
    query = query.strip().lower()
    if not query:
        return []
    eventi = []
    for e in EVENTI_CURATI:
        if query in e["nome"].lower() or any(query in kw for kw in e["keywords"]):
            eventi.append(e["nome"])
    return eventi[:limit]
