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
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin

from database import get_conn, DB_PATH
import source_locator

_EDB = Path(__file__).parent / "eventi_1gm.db"

_ALBO_BASE = "https://www.cadutigrandeguerra.it"

def normalize_albo_url(url: Optional[str]) -> str:
    """Converte detail_url relativo dell'Albo d'Oro in URL assoluto."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(_ALBO_BASE, url)


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


def search_events(term: str, limit: int = 20) -> List[Dict]:
    """Cerca eventi curati per nome, descrizione o keyword.
    Restituisce eventi con id, nome, descrizione."""
    if not term:
        return []
    term_lower = term.lower()
    results = []
    for e in EVENTI_CURATI:
        text = f"{e.get('nome', '')} {e.get('descrizione', '')}".lower()
        keywords = [k.lower() for k in e.get('keywords', [])]
        if term_lower in text or any(term_lower in k for k in keywords):
            results.append({
                "id": e["id"],
                "nome": e["nome"],
                "descrizione": e.get("descrizione", ""),
                "keywords": e.get("keywords", []),
            })
        if len(results) >= limit:
            break
    return results


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


def get_internati_per_evento(evento_nome: str, limit: int = 50, offset: int = 0, search: str = "") -> Dict:
    """Recupera gli internati probabilmente collegati a un evento curato.
    Se search è specificato, filtra per cognome, nome, grado, luogo_nascita, residenza, luogo_internamento."""
    evento_nome = evento_nome.replace("+", " ")
    evento = _NOME_A_EVENTO.get(evento_nome)
    if not evento:
        normalized = evento_nome.replace("_", " ").strip()
        # case-insensitive dict lookup
        evento = _NOME_A_EVENTO.get(normalized) or _NOME_A_EVENTO.get(normalized.title()) or _NOME_A_EVENTO.get(normalized.lower()) or _NOME_A_EVENTO.get(normalized.upper())
    if not evento:
        # fallback: nome abbreviato o completo parziale
        nome_lower = evento_nome.lower().replace("_", " ")
        for e in EVENTI_CURATI:
            en_lower = e["nome"].lower()
            if nome_lower in en_lower or en_lower in nome_lower:
                evento = e
                break
    if not evento:
        return {"evento": evento_nome, "internati": [], "total": 0}

    keywords = evento["keywords"]
    campi = evento["campi"]
    conditions = []
    params = []
    for campo in campi:
        for kw in keywords:
            conditions.append(f"LOWER({campo}) LIKE ?")
            params.append(f"%{kw.lower()}%")

    where_clause = ' OR '.join(conditions)

    # Add search filter on top of event match
    search_clause = ""
    search_params = []
    if search:
        search_clause = (" AND (cognome LIKE ? OR nome LIKE ? OR grado LIKE ? "
                         "OR luogo_nascita LIKE ? OR residenza LIKE ? OR luogo_internamento LIKE ? "
                         "OR luogo_cattura LIKE ? OR sorte LIKE ?) ")
        sp = f"%{search}%"
        search_params = [sp] * 8

    sql_total = f"SELECT COUNT(1) FROM internati WHERE ({where_clause}){search_clause}"
    sql = (
        f"SELECT id, cognome, nome, data_nascita, luogo_nascita, residenza, grado, "
        f"luogo_cattura, data_cattura, luogo_internamento, arbeitskommando, mansione, "
        f"sorte, data, matricola "
        f"FROM internati WHERE ({where_clause}){search_clause} "
        f"ORDER BY id LIMIT ? OFFSET ?"
    )
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    total = cur.execute(sql_total, params + search_params).fetchone()[0]
    rows = cur.execute(sql, params + search_params + [limit, offset]).fetchall()
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


# ─── Eventi 1GM dal DB event-centric ─────────────────────────────────────────

def get_eventi_1gm() -> List[Dict]:
    """Restituisce tutti gli eventi canonici 1GM+WW2 da eventi_1gm.db con stats."""
    if not _EDB.exists():
        return []
    conn = sqlite3.connect(str(_EDB), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        eventi = []
        for r in conn.execute(
            "SELECT e.id, e.nome, e.data_inizio, e.data_fine, e.luogo, "
            "e.aliases, e.keywords, e.descrizione, "
            "COUNT(el.id) as total_links, "
            "SUM(CASE WHEN el.link_type='soldato_caduto' THEN 1 ELSE 0 END) as caduti, "
            "SUM(CASE WHEN el.link_type='soldato_decorato' THEN 1 ELSE 0 END) as decorati, "
            "SUM(CASE WHEN el.link_type='documento' THEN 1 ELSE 0 END) as documenti, "
            "SUM(CASE WHEN el.link_type='fonte_archivistica' THEN 1 ELSE 0 END) as fonti, "
            "SUM(CASE WHEN el.link_type='internato_ww2' THEN 1 ELSE 0 END) as internati, "
            "SUM(CASE WHEN el.link_type='soldato_caduto_cwgc' THEN 1 ELSE 0 END) as cwgc "
            "FROM eventi_1gm e LEFT JOIN event_links el ON e.id=el.evento_id "
            "GROUP BY e.id ORDER BY total_links DESC"
        ).fetchall():
            d = dict(r)
            d["aliases"] = json.loads(d["aliases"]) if d["aliases"] else []
            d["keywords"] = json.loads(d["keywords"]) if d["keywords"] else []
            eventi.append(d)
        return eventi
    finally:
        conn.close()


def get_evento_1gm_dossier(query: str) -> Dict:
    """Query completa per un evento 1GM usando event_query_engine."""
    try:
        from event_query_engine import query_event
        return query_event(query, verbose=False)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_eventi_1gm_caduti(event_name: str, limit: int = 50, offset: int = 0, search: str = "", letter: str = "") -> Dict:
    """Caduti paginati per un evento 1GM con flag decorato e fonti collegate.
    Se search è specificato, filtra per nominativo/grado/reparto/luogo_morte.
    Se letter è specificato, filtra per iniziale del nominativo."""
    if not _EDB.exists():
        return {"event": event_name, "caduti": [], "total": 0}
    conn_ev = sqlite3.connect(str(_EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_ro = sqlite3.connect(str(DB_PATH), timeout=30)
    conn_ro.row_factory = sqlite3.Row
    try:
        # Find event by name/alias (also try normalized name with underscores→spaces)
        ev = conn_ev.execute(
            "SELECT id FROM eventi_1gm WHERE nome = ? OR ? IN (SELECT value FROM json_each(aliases))",
            (event_name, event_name)
        ).fetchone()
        if not ev:
            # Fallback: prova con underscore convertiti in spazi (case-insensitive)
            normalized = event_name.replace("_", " ").strip()
            norm_up = normalized.upper()
            ev = conn_ev.execute(
                "SELECT id FROM eventi_1gm WHERE UPPER(nome) = ? OR ? IN (SELECT UPPER(value) FROM json_each(aliases))",
                (norm_up, norm_up)
            ).fetchone()
        if not ev:
            return {"event": event_name, "caduti": [], "total": 0}

        # Get caduti IDs
        ids = [r["target_id"] for r in conn_ev.execute(
            "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='soldato_caduto'",
            (ev["id"],)
        ).fetchall()]
        if not ids:
            return {"event": event_name, "caduti": [], "total": 0}

        # Use temp table for large ID sets
        conn_ro.execute("CREATE TEMP TABLE _tmp_ids(ids INTEGER)")
        conn_ro.executemany("INSERT INTO _tmp_ids VALUES(?)", [(i,) for i in ids])
        filter_clause = ""
        filter_params = []
        if search:
            filter_clause = (" AND (c.nominativo LIKE ? OR c.grado LIKE ? OR c.reparto LIKE ? "
                             "OR c.luogo_morte LIKE ? OR c.anno_morte LIKE ?) ")
            sp = f"%{search}%"
            filter_params = [sp, sp, sp, sp, sp]
        if letter:
            letter = letter.strip().upper()[:1]
            filter_clause += " AND UPPER(c.nominativo) LIKE ? "
            filter_params.append(f"{letter}%")
        total = conn_ro.execute(
            f"SELECT COUNT(*) FROM caduti_albooro c JOIN _tmp_ids t ON c.id = t.ids{filter_clause}",
            filter_params
        ).fetchone()[0]
        rows = conn_ro.execute(
            f"SELECT c.id, c.nominativo, c.grado, c.reparto, c.luogo_morte, c.anno_morte, "
            f"c.causa_morte, c.paternita, c.comune_attuale, c.detail_url "
            f"FROM caduti_albooro c JOIN _tmp_ids t ON c.id = t.ids{filter_clause} "
            f"LIMIT ? OFFSET ?",
            filter_params + [limit, offset]
        ).fetchall()

        # Build set of decorated soldati by nominativo match
        nominativi = [r["nominativo"] for r in rows]
        decorati_map = {}
        if nominativi:
            placeholders = ",".join("?" * len(nominativi))
            dec_rows = conn_ro.execute(
                f"SELECT cognome, nome, decorazione FROM decorati "
                f"WHERE (cognome || ' ' || nome) IN ({placeholders})",
                nominativi
            ).fetchall()
            for dr in dec_rows:
                key = f"{dr['cognome']} {dr['nome']}".upper()
                decorati_map[key] = dr["decorazione"]

        # Check fonti collegate via record_links (fonte_personale)
        fonti_ids = set()
        if ids:
            id_list = rows and [r["id"] for r in rows]
            if id_list:
                placeholders_f = ",".join("?" * len(id_list))
                fl_rows = conn_ro.execute(
                    f"SELECT DISTINCT from_id FROM record_links "
                    f"WHERE link_type='fonte_personale' AND from_table='caduti_albooro' "
                    f"AND from_id IN ({placeholders_f})",
                    id_list
                ).fetchall()
                fonti_ids = {r["from_id"] for r in fl_rows}

        conn_ro.execute("DROP TABLE _tmp_ids")

        caduti_list = []
        for r in rows:
            d = dict(r)
            d["detail_url"] = normalize_albo_url(d.get("detail_url"))
            nom_upper = (d.get("nominativo") or "").upper()
            d["is_decorato"] = nom_upper in decorati_map
            d["decorazione"] = decorati_map.get(nom_upper, "")
            d["has_fonti"] = d["id"] in fonti_ids
            caduti_list.append(d)

        return {
            "event": event_name,
            "caduti": caduti_list,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn_ev.close()
        conn_ro.close()


def get_eventi_1gm_decorati(event_name: str, limit: int = 50, offset: int = 0, search: str = "") -> Dict:
    """Decorati paginati per un evento 1GM con flag caduto e fonti collegate.
    Se search è specificato, filtra per cognome/nome/arma/decorazione/anno."""
    if not _EDB.exists():
        return {"event": event_name, "decorati": [], "total": 0}
    conn_ev = sqlite3.connect(str(_EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_ro = sqlite3.connect(str(DB_PATH), timeout=30)
    conn_ro.row_factory = sqlite3.Row
    try:
        ev = conn_ev.execute(
            "SELECT id FROM eventi_1gm WHERE nome = ? OR ? IN (SELECT value FROM json_each(aliases))",
            (event_name, event_name)
        ).fetchone()
        if not ev:
            normalized = event_name.replace("_", " ").strip()
            norm_up = normalized.upper()
            ev = conn_ev.execute(
                "SELECT id FROM eventi_1gm WHERE UPPER(nome) = ? OR ? IN (SELECT UPPER(value) FROM json_each(aliases))",
                (norm_up, norm_up)
            ).fetchone()
        if not ev:
            return {"event": event_name, "decorati": [], "total": 0}

        ids = [r["target_id"] for r in conn_ev.execute(
            "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='soldato_decorato'",
            (ev["id"],)
        ).fetchall()]
        if not ids:
            return {"event": event_name, "decorati": [], "total": 0}

        conn_ro.execute("CREATE TEMP TABLE _tmp_ids(ids INTEGER)")
        conn_ro.executemany("INSERT INTO _tmp_ids VALUES(?)", [(i,) for i in ids])
        search_clause = ""
        search_params = []
        if search:
            search_clause = (" AND (d.cognome LIKE ? OR d.nome LIKE ? OR d.arma LIKE ? "
                             "OR d.tipo_decorazione LIKE ? OR d.anno_decorazione LIKE ?) ")
            sp = f"%{search}%"
            search_params = [sp, sp, sp, sp, sp]
        total = conn_ro.execute(
            f"SELECT COUNT(*) FROM decorati_nastroazzurro d JOIN _tmp_ids t ON d.id = t.ids{search_clause}",
            search_params
        ).fetchone()[0]
        rows = conn_ro.execute(
            f"SELECT d.id, d.cognome, d.nome, d.arma, d.anno_decorazione, d.tipo_decorazione "
            f"FROM decorati_nastroazzurro d JOIN _tmp_ids t ON d.id = t.ids{search_clause} "
            f"LIMIT ? OFFSET ?",
            search_params + [limit, offset]
        ).fetchall()

        # Build set of caduti by nominativo for cross-reference
        nominativi = [f"{r['cognome']} {r['nome']}".upper() for r in rows]
        caduti_set = set()
        if nominativi:
            placeholders = ",".join("?" * len(nominativi))
            cad_rows = conn_ro.execute(
                f"SELECT nominativo FROM caduti_albooro WHERE nominativo IN ({placeholders})",
                nominativi
            ).fetchall()
            caduti_set = {r["nominativo"].upper() for r in cad_rows}

        # Check fonti collegate via record_links
        fonti_ids = set()
        id_list = [r["id"] for r in rows]
        if id_list:
            placeholders_f = ",".join("?" * len(id_list))
            fl_rows = conn_ro.execute(
                f"SELECT DISTINCT from_id FROM record_links "
                f"WHERE link_type='fonte_personale' AND from_table='decorati_nastroazzurro' "
                f"AND from_id IN ({placeholders_f})",
                id_list
            ).fetchall()
            fonti_ids = {r["from_id"] for r in fl_rows}

        conn_ro.execute("DROP TABLE _tmp_ids")

        decorati_list = []
        for r in rows:
            d = dict(r)
            nom_upper = f"{d.get('cognome','')} {d.get('nome','')}".upper()
            d["nominativo"] = f"{d.get('cognome','')} {d.get('nome','')}".strip()
            d["is_caduto"] = nom_upper in caduti_set
            d["has_fonti"] = d["id"] in fonti_ids
            decorati_list.append(d)

        return {
            "event": event_name,
            "decorati": decorati_list,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn_ev.close()
        conn_ro.close()


# ─── Graph aggregation endpoints ─────────────────────────────────────────────

def get_graph_luoghi(limit: int = 50) -> Dict:
    """Aggregazione caduti per luogo_morte con link a eventi."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn_ev = sqlite3.connect(str(_EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT luogo_morte, COUNT(*) as n, "
            "SUM(CASE WHEN anno_morte='1915' THEN 1 ELSE 0 END) as a1915, "
            "SUM(CASE WHEN anno_morte='1916' THEN 1 ELSE 0 END) as a1916, "
            "SUM(CASE WHEN anno_morte='1917' THEN 1 ELSE 0 END) as a1917, "
            "SUM(CASE WHEN anno_morte='1918' THEN 1 ELSE 0 END) as a1918 "
            "FROM caduti_albooro "
            "WHERE luogo_morte IS NOT NULL AND luogo_morte != '' AND luogo_morte != '-' "
            "GROUP BY luogo_morte ORDER BY n DESC LIMIT ?",
            (limit,)
        ).fetchall()

        eventi_map = {}
        for ev in conn_ev.execute(
            "SELECT e.nome, el.match_value, el.link_type, COUNT(*) as n "
            "FROM event_links el JOIN eventi_1gm e ON el.evento_id=e.id "
            "WHERE el.link_type='soldato_caduto' AND el.match_field='luogo_morte' "
            "GROUP BY e.nome, el.match_value"
        ).fetchall():
            key = (ev["match_value"] or "").strip().upper()
            if key not in eventi_map:
                eventi_map[key] = []
            eventi_map[key].append({"evento": ev["nome"], "count": ev["n"]})

        nodes = []
        for r in rows:
            lm = r["luogo_morte"]
            ev_links = eventi_map.get(lm.upper(), [])
            nodes.append({
                "luogo": lm,
                "count": r["n"],
                "anni": {"1915": r["a1915"], "1916": r["a1916"], "1917": r["a1917"], "1918": r["a1918"]},
                "eventi": ev_links,
            })
        return {"nodes": nodes, "total": len(nodes)}
    finally:
        conn.close()
        conn_ev.close()


def get_graph_mesi() -> Dict:
    """Aggregazione caduti + decorati per anno (1914-1921)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        caduti = {}
        for r in conn.execute(
            "SELECT anno_morte, COUNT(*) as n FROM caduti_albooro "
            "WHERE anno_morte IS NOT NULL AND anno_morte != '' "
            "AND CAST(anno_morte AS INTEGER) BETWEEN 1914 AND 1921 "
            "GROUP BY anno_morte ORDER BY anno_morte"
        ).fetchall():
            caduti[r["anno_morte"]] = r["n"]

        decorati = {}
        for r in conn.execute(
            "SELECT anno_decorazione, COUNT(*) as n FROM decorati_nastroazzurro "
            "WHERE anno_decorazione IS NOT NULL AND anno_decorazione != '' "
            "AND CAST(anno_decorazione AS INTEGER) BETWEEN 1914 AND 1921 "
            "GROUP BY anno_decorazione ORDER BY anno_decorazione"
        ).fetchall():
            decorati[r["anno_decorazione"]] = r["n"]

        anni = sorted(set(list(caduti.keys()) + list(decorati.keys())))
        nodes = []
        for a in anni:
            nodes.append({
                "anno": a,
                "caduti": caduti.get(a, 0),
                "decorati": decorati.get(a, 0),
                "totale": caduti.get(a, 0) + decorati.get(a, 0),
            })
        return {"nodes": nodes}
    finally:
        conn.close()


def get_graph_paesi() -> Dict:
    """Aggregazione caduti per nazione/teatro (classificazione da luogo_morte)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        teatri_map = {
            "Italia": ["carso", "isonzo", "piave", "grappa", "tolmino", "asiago", "altipiano", "cadore", "trentino", "gorizia", "udine", "tagliamento", "monte san michele", "monte grappa", "settore"],
            "Austria-Ungheria": ["prigionia", "campo", "mate", "maut", "thalerhof", "sigmundsherberg", "mitterling"],
            "Francia": ["francia", "verdun", "somme", "marna", "chemin des dames", "ardenne"],
            "Balcani": ["serbia", "macedonia", "salonico", "balcani", "albania", "montenegro"],
            "Russia": ["russia", "ucraina", "galizia"],
            "Turchia": ["turchia", "anatolia", "mesopotamia", "dardanelli", "gallipoli"],
            "Mare": ["mare", "mediterraneo", "adriatico", "navale"],
        }

        rows = conn.execute(
            "SELECT luogo_morte, COUNT(*) as n FROM caduti_albooro "
            "WHERE luogo_morte IS NOT NULL AND luogo_morte != '' AND luogo_morte != '-' "
            "GROUP BY luogo_morte"
        ).fetchall()

        teatri = {k: {"count": 0, "luoghi": []} for k in teatri_map}
        teatri["Altro"] = {"count": 0, "luoghi": []}

        for r in rows:
            lm = r["luogo_morte"]
            lm_lower = lm.lower()
            assigned = False
            for teatro, keywords in teatri_map.items():
                if any(kw in lm_lower for kw in keywords):
                    teatri[teatro]["count"] += r["n"]
                    teatri[teatro]["luoghi"].append({"luogo": lm, "count": r["n"]})
                    assigned = True
                    break
            if not assigned:
                teatri["Altro"]["count"] += r["n"]
                teatri["Altro"]["luoghi"].append({"luogo": lm, "count": r["n"]})

        for t in teatri.values():
            t["luoghi"].sort(key=lambda x: x["count"], reverse=True)

        nodes = [{"teatro": k, "count": v["count"], "luoghi_count": len(v["luoghi"]),
                   "top_luoghi": v["luoghi"][:5]}
                 for k, v in sorted(teatri.items(), key=lambda x: x[1]["count"], reverse=True)
                 if v["count"] > 0]

        return {"nodes": nodes}
    finally:
        conn.close()


def get_graph_soldati_architecture() -> Dict:
    """Architettura per network graph soldati (342k+ nodi)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT COUNT(*) FROM caduti_albooro").fetchone()[0]
        with_luogo = conn.execute(
            "SELECT COUNT(*) FROM caduti_albooro WHERE luogo_morte IS NOT NULL AND luogo_morte != '' AND luogo_morte != '-'"
        ).fetchone()[0]
        with_reparto = conn.execute(
            "SELECT COUNT(*) FROM caduti_albooro WHERE reparto IS NOT NULL AND reparto != ''"
        ).fetchone()[0]
        with_anno = conn.execute(
            "SELECT COUNT(*) FROM caduti_albooro WHERE anno_morte IS NOT NULL AND anno_morte != ''"
        ).fetchone()[0]

        top_reparti = conn.execute(
            "SELECT reparto, COUNT(*) as n FROM caduti_albooro "
            "WHERE reparto IS NOT NULL AND reparto != '' "
            "GROUP BY reparto ORDER BY n DESC LIMIT 20"
        ).fetchall()

        top_luoghi = conn.execute(
            "SELECT luogo_morte, COUNT(*) as n FROM caduti_albooro "
            "WHERE luogo_morte IS NOT NULL AND luogo_morte != '' AND luogo_morte != '-' "
            "GROUP BY luogo_morte ORDER BY n DESC LIMIT 20"
        ).fetchall()

        return {
            "total_soldati": total,
            "with_luogo": with_luogo,
            "with_reparto": with_reparto,
            "with_anno": with_anno,
            "strategy": {
                "approach": "server-side aggregation + paginated rendering",
                "clustering_fields": ["luogo_morte", "reparto", "anno_morte"],
                "max_nodes_per_page": 500,
                "phases": [
                    "1. Cluster gerarchico: luogo -> reparto -> soldato",
                    "2. Paginazione per cluster (500 nodi per pagina)",
                    "3. Force-directed layout server-side (NetworkX)",
                    "4. Rendering progressivo client-side (SVG + viewport culling)",
                    "5. Drill-down: click cluster -> espande soldati singoli",
                ],
                "endpoints": [
                    "GET /api/graph/soldati/clusters?field=luogo_morte&limit=50",
                    "GET /api/graph/soldati/cluster/{cluster_id}?page=1&limit=500",
                    "GET /api/graph/soldati/search?q=...&limit=50",
                ],
            },
            "top_clusters": {
                "luoghi": [{"name": r["luogo_morte"], "count": r["n"]} for r in top_luoghi],
                "reparti": [{"name": r["reparto"], "count": r["n"]} for r in top_reparti],
            },
        }
    finally:
        conn.close()


def get_graph_soldati_clusters(field: str = "luogo_morte", limit: int = 50) -> Dict:
    """Cluster soldati per campo (luogo_morte, reparto, anno_morte)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if field not in ("luogo_morte", "reparto", "anno_morte"):
            field = "luogo_morte"

        rows = conn.execute(
            f"SELECT {field} as cluster, COUNT(*) as n FROM caduti_albooro "
            f"WHERE {field} IS NOT NULL AND {field} != '' AND {field} != '-' "
            f"GROUP BY {field} ORDER BY n DESC LIMIT ?",
            (limit,)
        ).fetchall()

        clusters = [{"id": i, "cluster": r["cluster"], "count": r["n"]}
                    for i, r in enumerate(rows)]
        return {"field": field, "clusters": clusters, "total": len(clusters)}
    finally:
        conn.close()


def get_graph_soldati_cluster(cluster_field: str, cluster_value: str,
                               page: int = 1, limit: int = 500) -> Dict:
    """Soldati singoli paginati per cluster."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if cluster_field not in ("luogo_morte", "reparto", "anno_morte"):
            cluster_field = "luogo_morte"

        offset = (page - 1) * limit
        total = conn.execute(
            f"SELECT COUNT(*) FROM caduti_albooro WHERE {cluster_field} = ?",
            (cluster_value,)
        ).fetchone()[0]

        rows = conn.execute(
            f"SELECT id, nominativo, grado, reparto, luogo_morte, anno_morte, causa_morte, detail_url "
            f"FROM caduti_albooro WHERE {cluster_field} = ? "
            f"ORDER BY nominativo LIMIT ? OFFSET ?",
            (cluster_value, limit, offset)
        ).fetchall()

        soldati = []
        for r in rows:
            d = dict(r)
            d["detail_url"] = normalize_albo_url(d.get("detail_url"))
            soldati.append(d)
        return {
            "cluster_field": cluster_field,
            "cluster_value": cluster_value,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
            "soldati": soldati,
        }
    finally:
        conn.close()
