"""Information Retrieval Layer per IMI Extractor.

Tre funzioni core:
1. search_entities()  - Full-Text Search con BM25 ranking su FTS5
2. get_entity_network() - Graph traversal via recursive CTE su entita'/collegamenti
3. get_entity_full_context() - Deep-dive: risolve dinamicamente il record sorgente

Usa solo sqlite3 nativo. Nessun DB esterno.
"""
import sqlite3
from typing import List, Dict, Optional, Any
from database import get_conn, DB_PATH, get_fonti_risorse_by_fonte_id
from scraper_service import scrape_if_stale


# ─── Helper ───────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> Dict:
    return {k: row[k] for k in row.keys()}


def _normalize_query(query_string: str) -> str:
    """Normalizza la query per FTS5: aggiunge prefix matching (*) se manca.
    Gestisce query vuote o con soli spazi."""
    query_string = query_string.strip()
    if not query_string:
        return ""
    tokens = query_string.split()
    normalized = []
    for t in tokens:
        if not t.endswith("*") and not t.endswith('"'):
            normalized.append(t + "*")
        else:
            normalized.append(t)
    return " ".join(normalized)


# ─── 1. Full-Text Search con BM25 ─────────────────────────────────────

def search_entities(
    query_string: str,
    limit: int = 10,
    tipo: Optional[str] = None,
) -> List[Dict]:
    """Cerca entita' con FTS5 + BM25 ranking.

    Args:
        query_string: testo da cercare (es. "Rossi Mario", "Agrigento", "deceduto 1945")
        limit: numero massimo di risultati
        tipo: filtra per tipo entita' ('persona', 'luogo', 'evento', 'decorazione', 'periodo')

    Returns:
        Lista di dict con: entita_id, tipo, valore, cognome, nome, luogo, contesto, rank, fonte_tabella, fonte_id
    """
    normalized = _normalize_query(query_string)
    if not normalized:
        return []

    conn = get_conn()
    try:
        if tipo:
            sql = """
                SELECT e.id as entita_id, e.tipo, e.valore, e.cognome, e.nome,
                       e.luogo, e.contesto, e.fonte_tabella, e.fonte_id,
                       bm25(idx_entita_search) as rank
                FROM idx_entita_search
                JOIN entita e ON e.id = idx_entita_search.entita_id
                WHERE idx_entita_search MATCH ?
                  AND idx_entita_search.tipo = ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (normalized, tipo, limit)).fetchall()
        else:
            sql = """
                SELECT e.id as entita_id, e.tipo, e.valore, e.cognome, e.nome,
                       e.luogo, e.contesto, e.fonte_tabella, e.fonte_id,
                       bm25(idx_entita_search) as rank
                FROM idx_entita_search
                JOIN entita e ON e.id = idx_entita_search.entita_id
                WHERE idx_entita_search MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (normalized, limit)).fetchall()

        return [_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        print(f"Errore FTS5: {e}")
        return []
    finally:
        conn.close()


# ─── 2. Graph Traversal via Recursive CTE ─────────────────────────────

def get_entity_network(entity_id: int, max_depth: int = 2) -> Dict:
    """Costruisce il grafo di entita' collegate entro max_depth hop.

    Il grafo e' star-shaped: entita' A -> record X -> entita' B.
    Ogni hop attraversa: entita' -> collegamenti -> (stesso record) -> entita'.

    Per depth=2 usa JOIN dirette (piu' efficiente).
    Per depth>2 usa recursive CTE.

    Args:
        entity_id: ID dell'entita' di partenza
        max_depth: profondita' massima di traversal (default 2)

    Returns:
        Dict con 'nodes' (lista di entita') e 'edges' (lista di collegamenti {source, target, via_record})
    """
    conn = get_conn()
    try:
        if max_depth <= 2:
            return _network_depth2(conn, entity_id)
        else:
            return _network_recursive(conn, entity_id, max_depth)
    finally:
        conn.close()


def _network_depth2(conn: sqlite3.Connection, entity_id: int) -> Dict:
    """Graph traversal depth=2 con JOIN dirette.
    Trova tutte le entita' che condividono almeno un record sorgente con entity_id."""
    nodes_sql = """
        SELECT DISTINCT e.id, e.tipo, e.valore, e.cognome, e.nome,
               e.luogo, e.contesto, e.fonte_tabella, e.fonte_id
        FROM collegamenti c1
        JOIN collegamenti c2
          ON c1.tabella_origine = c2.tabella_origine
         AND c1.record_id = c2.record_id
        JOIN entita e ON e.id = c2.entita_id
        WHERE c1.entita_id = ?
          AND e.id != ?
    """
    rows = conn.execute(nodes_sql, (entity_id, entity_id)).fetchall()

    edges_sql = """
        SELECT DISTINCT c1.entita_id as source, c2.entita_id as target,
               c1.tabella_origine || ':' || c1.record_id as via_record,
               c2.tipo_collegamento
        FROM collegamenti c1
        JOIN collegamenti c2
          ON c1.tabella_origine = c2.tabella_origine
         AND c1.record_id = c2.record_id
        WHERE c1.entita_id = ?
          AND c2.entita_id != ?
    """
    edge_rows = conn.execute(edges_sql, (entity_id, entity_id)).fetchall()

    center = conn.execute(
        "SELECT id, tipo, valore, cognome, nome, luogo, contesto, fonte_tabella, fonte_id FROM entita WHERE id = ?",
        (entity_id,)
    ).fetchone()

    nodes = []
    if center:
        nodes.append(_row_to_dict(center))
    nodes.extend(_row_to_dict(r) for r in rows)

    edges = [_row_to_dict(r) for r in edge_rows]

    return {
        "center": entity_id,
        "max_depth": 2,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _network_recursive(conn: sqlite3.Connection, entity_id: int, max_depth: int) -> Dict:
    """Graph traversal con recursive CTE per depth > 2.
    Espande il grafo livello per livello evitando cicli.
    SQLite non permette multiple reference al CTE ricorsivo, quindi
    usiamo un approccio con visited set temporaneo."""
    cte_sql = """
        WITH RECURSIVE graph AS (
            SELECT c2.entita_id as node_id, 1 as depth
            FROM collegamenti c1
            JOIN collegamenti c2
              ON c1.tabella_origine = c2.tabella_origine
             AND c1.record_id = c2.record_id
            WHERE c1.entita_id = ?
              AND c2.entita_id != ?

            UNION

            SELECT c2.entita_id, g.depth + 1
            FROM graph g
            JOIN collegamenti c1 ON c1.entita_id = g.node_id
            JOIN collegamenti c2
              ON c1.tabella_origine = c2.tabella_origine
             AND c1.record_id = c2.record_id
            WHERE c2.entita_id != ?
              AND g.depth < ?
        )
        SELECT DISTINCT node_id, MIN(depth) as depth FROM graph GROUP BY node_id ORDER BY depth
    """
    rows = conn.execute(cte_sql, (entity_id, entity_id, entity_id, max_depth)).fetchall()

    if not rows:
        center = conn.execute("SELECT * FROM entita WHERE id = ?", (entity_id,)).fetchone()
        return {
            "center": entity_id,
            "max_depth": max_depth,
            "nodes": [_row_to_dict(center)] if center else [],
            "edges": [],
            "node_count": 1 if center else 0,
            "edge_count": 0,
        }

    node_ids = list(set(r["node_id"] for r in rows))
    node_ids.append(entity_id)

    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _graph_nodes (node_id INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM _graph_nodes")
    conn.executemany("INSERT INTO _graph_nodes VALUES (?)", [(nid,) for nid in node_ids])

    node_rows = conn.execute(
        """SELECT e.id, e.tipo, e.valore, e.cognome, e.nome, e.luogo, e.contesto,
                  e.fonte_tabella, e.fonte_id
           FROM entita e
           JOIN _graph_nodes g ON e.id = g.node_id"""
    ).fetchall()

    edge_rows = conn.execute(
        """SELECT DISTINCT c1.entita_id as source, c2.entita_id as target,
                  c1.tabella_origine || ':' || c1.record_id as via_record,
                  c2.tipo_collegamento
           FROM collegamenti c1
           JOIN collegamenti c2
             ON c1.tabella_origine = c2.tabella_origine
            AND c1.record_id = c2.record_id
           JOIN _graph_nodes g1 ON c1.entita_id = g1.node_id
           JOIN _graph_nodes g2 ON c2.entita_id = g2.node_id
           WHERE c1.entita_id != c2.entita_id"""
    ).fetchall()

    conn.execute("DELETE FROM _graph_nodes")
    conn.commit()

    nodes = [_row_to_dict(r) for r in node_rows]
    edges = [_row_to_dict(r) for r in edge_rows]

    return {
        "center": entity_id,
        "max_depth": max_depth,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ─── 3. Relational Deep-Dive ──────────────────────────────────────────

# Mappa tabella -> campi da recuperare per il full context
SOURCE_TABLE_FIELDS = {
    "internati": [
        "id", "lettera", "file_pdf", "pagina", "riga", "cognome", "nome",
        "paternita", "maternita", "data_nascita", "luogo_nascita",
        "residenza", "professione", "stato_civile", "grado", "reparto",
        "corpo", "luogo_internamento", "data_internamento",
        "data_decesso", "luogo_decesso", "causa_decesso",
        "decorazioni", "fonte", "note", "elaborato_il"
    ],
    "decorati": [
        "id", "cognome", "nome", "paternita", "data_nascita",
        "luogo_nascita", "grado", "reparto", "decorazione",
        "motivazione", "data_decorazione", "fonte", "elaborato_il"
    ],
    "menzioni": [
        "id", "cognome", "nome", "grado", "reparto",
        "fonte_archivio", "fondi_id", "pagina", "contesto", "elaborato_il"
    ],
    "fondi_archivistici": [
        "id", "fondo", "sottofondo", "serie", "anno", "descrizione",
        "archivio", "collocazione", "elaborato_il"
    ],
    "caduti_albooro": [
        "id", "volume", "nominativo", "paternita", "classe",
        "comune", "grado", "reparto", "anno_morte", "luogo_morte",
        "causa_morte", "dettaglio_url", "elaborato_il"
    ],
    "caduti_bologna": [
        "id", "nome", "paternita", "grado", "reparto",
        "luogo_nascita", "anno_nascita", "dimora",
        "causa_morte", "luogo_morte", "data_morte",
        "professione", "stato_civile", "decorazioni", "elaborato_il"
    ],
    "caduti_ministero": [
        "id", "source_id", "cognome", "nome", "nominativo_paternita",
        "paternita", "maternita", "data_nascita", "data_decesso",
        "provincia_nascita", "comune_nascita", "nazione_decesso",
        "luogo_sepoltura", "codice_volume", "pagina", "sub",
        "scheda_url", "elaborato_il"
    ],
    "caduti_sardi": [
        "id", "source_id", "cognome", "nome", "comune_residenza",
        "guerra", "data_nascita", "data_morte", "luogo_morte",
        "scheda_url", "elaborato_il"
    ],
    "caduti_cwgc": [
        "id", "source_id", "cognome", "nome", "data_nascita",
        "data_decesso", "cimitero", "paese_cimitero", "grado",
        "reparto", "scheda_url", "elaborato_il"
    ],
}


def get_entity_full_context(entity_id: int) -> Dict:
    """Recupera il contesto completo di un'entita': metadata + record sorgente risolto dinamicamente.

    Args:
        entity_id: ID dell'entita'

    Returns:
        Dict con:
        - 'entity': metadata completo dell'entita'
        - 'source_record': record completo dalla tabella sorgente (o None se non trovato)
        - 'source_table': nome della tabella sorgente
        - 'collegamenti': lista dei collegamenti dell'entita'
    """
    conn = get_conn()
    try:
        entity_row = conn.execute(
            "SELECT * FROM entita WHERE id = ?", (entity_id,)
        ).fetchone()

        if not entity_row:
            return {
                "entity": None,
                "source_record": None,
                "source_table": None,
                "collegamenti": [],
                "error": f"Entita' {entity_id} non trovata"
            }

        entity = _row_to_dict(entity_row)
        fonte_tabella = entity.get("fonte_tabella")
        fonte_id = entity.get("fonte_id")

        source_record = None
        source_table = None

        if fonte_tabella and fonte_id:
            source_table = fonte_tabella
            fields = SOURCE_TABLE_FIELDS.get(fonte_tabella)

            if fields:
                field_list = ", ".join(fields)
                try:
                    row = conn.execute(
                        f"SELECT {field_list} FROM {fonte_tabella} WHERE id = ?",
                        (fonte_id,)
                    ).fetchone()
                    if row:
                        source_record = _row_to_dict(row)
                except sqlite3.OperationalError as e:
                    source_record = {"error": f"Tabella {fonte_tabella} non accessibile: {e}"}
            else:
                source_record = {"error": f"Schema per tabella {fonte_tabella} non mappato"}

        coll_rows = conn.execute(
            """SELECT c.id, c.tabella_origine, c.record_id, c.tipo_collegamento,
                      c.confidenza, c.elaborato_il
               FROM collegamenti c
               WHERE c.entita_id = ?
               ORDER BY c.tabella_origine, c.record_id""",
            (entity_id,)
        ).fetchall()

        collegamenti = [_row_to_dict(r) for r in coll_rows]

        # ─── Recupera fonti_risorse collegate all'entità ───────────────────
        fonti_risorse = get_fonti_risorse_for_entity(entity_id, entity, collegamenti, conn)

        return {
            "entity": entity,
            "source_record": source_record,
            "source_table": source_table,
            "collegamenti": collegamenti,
            "fonti_risorse": fonti_risorse,
        }
    finally:
        conn.close()


# ─── 4. Fonti Risorse Esterne ─────────────────────────────────────────────────

# Mapping tabelle sorgente -> tabella fonti con URL
_TABLE_TO_FONTI_TABLE = {
    "fondi_archivistici": "fondi_archivistici",
    "fonti_narrative": "fonti_narrative",
    "fonti_indice": "fonti_indice",
    "caduti_albooro": "caduti_albooro",
    "caduti_ministero": "caduti_ministero",
    "caduti_sardi": "caduti_sardi",
    "caduti_bologna": "caduti_bologna",
    "caduti_cwgc": "caduti_cwgc",
    "caduti_francia_ww1": "caduti_francia_ww1",
    "decorati": "decorati",
    "decorati_nastroazzurro": "decorati_nastroazzurro",
    "menzioni": "menzioni",
}


def _get_fonte_record_with_url(conn, tabella_origine: str, record_id: int) -> Optional[dict]:
    """Recupera un record sorgente che contiene un URL utilizzabile per scraping."""
    if tabella_origine not in _TABLE_TO_FONTI_TABLE:
        return None

    # Campi URL comuni in varie tabelle
    url_fields = [
        "url", "url_catalogo", "url_file", "scheda_url", "detail_url",
        "url_scheda", "link_scheda", "file_pdf",
    ]

    # Prova a leggere le colonne della tabella
    try:
        cols = [d[1] for d in conn.execute(f"PRAGMA table_info({tabella_origine})").fetchall()]
        url_col = None
        for f in url_fields:
            if f in cols:
                url_col = f
                break
        if not url_col:
            return None

        row = conn.execute(
            f"SELECT id, {url_col} as url_base FROM {tabella_origine} WHERE id = ?",
            (record_id,)
        ).fetchone()
        if row and row["url_base"]:
            return {"id": row["id"], "url_base": row["url_base"], "tabella": tabella_origine}
    except sqlite3.OperationalError:
        pass
    return None


def get_fonti_risorse_for_entity(
    entity_id: int,
    entity: dict,
    collegamenti: list,
    conn: sqlite3.Connection
) -> list:
    """Recupera le risorse esterne (fonti_risorse) collegate a un'entità.

    Logica:
    1. Per ogni collegamento dell'entità, identifica la tabella sorgente e il record.
    2. Se la tabella sorgente ha un URL, verifica se esistono già fonti_risorse.
    3. Se non esistono o sono stale, triggera scraping in background.
    4. Filtra le risorse per rilevanza (titolo/descrizione contenente il valore dell'entità).

    Args:
        entity_id: ID dell'entità
        entity: dict dell'entità
        collegamenti: lista dei collegamenti dell'entità
        conn: connessione DB attiva

    Returns:
        Lista di dict con: id_risorsa, fonte_id, url_pagina, url_documento,
        tipo_risorsa, titolo, ente_titolare, licenza, lingua, note_copyright
    """
    risorse_trovate = []
    seen_ids = set()
    entity_valore = (entity.get("valore") or "").lower()
    entity_tipo = entity.get("tipo", "")

    for coll in collegamenti:
        tabella = coll.get("tabella_origine")
        record_id = coll.get("record_id")
        if not tabella or not record_id:
            continue

        # Recupera il record sorgente per ottenere l'URL
        fonte_record = _get_fonte_record_with_url(conn, tabella, record_id)
        if not fonte_record:
            continue

        fonte_id = fonte_record["id"]

        # Cerca risorse esistenti per questo fonte_id
        existing_risorse = get_fonti_risorse_by_fonte_id(fonte_id)

        if not existing_risorse:
            # Trigger scraping in background (non bloccante)
            # Usa il record sorgente come fonte_record
            try:
                scrape_if_stale(fonte_record)
                existing_risorse = get_fonti_risorse_by_fonte_id(fonte_id)
            except Exception as e:
                print(f"Scraper trigger error for fonte {fonte_id}: {e}")
                continue

        # Filtra per rilevanza: se l'entità è un luogo o evento,
        # filtra per titolo/descrizione contenente il valore
        for r in existing_risorse:
            if r["id"] in seen_ids:
                continue

            if entity_tipo in ("luogo", "evento"):
                titolo = (r.get("titolo") or "").lower()
                descrizione = (r.get("descrizione") or "").lower()
                if entity_valore and entity_valore not in titolo and entity_valore not in descrizione:
                    continue

            seen_ids.add(r["id"])
            risorse_trovate.append({
                "id_risorsa": r["id"],
                "fonte_id": r.get("fonte_id"),
                "url_pagina": r["url_pagina"],
                "url_documento": r.get("url_documento"),
                "tipo_risorsa": r.get("tipo_risorsa"),
                "titolo": r.get("titolo"),
                "ente_titolare": r.get("ente_titolare"),
                "licenza": r.get("licenza"),
                "lingua": r.get("lingua"),
                "note_copyright": r.get("note_copyright"),
            })

    return risorse_trovate


# ─── Utility: statistiche indice ──────────────────────────────────────

def get_fts_stats() -> Dict:
    """Ritorna statistiche sull'indice FTS5 e sulle entita'."""
    conn = get_conn()
    try:
        fts_count = conn.execute("SELECT COUNT(*) FROM idx_entita_search").fetchone()[0]
        entita_count = conn.execute("SELECT COUNT(*) FROM entita").fetchone()[0]
        coll_count = conn.execute("SELECT COUNT(*) FROM collegamenti").fetchone()[0]

        tipo_dist = conn.execute(
            "SELECT tipo, COUNT(*) as c FROM entita GROUP BY tipo ORDER BY c DESC"
        ).fetchall()

        fonte_dist = conn.execute(
            "SELECT fonte_tabella, COUNT(*) as c FROM entita GROUP BY fonte_tabella ORDER BY c DESC"
        ).fetchall()

        return {
            "fts5_indexed": fts_count,
            "entita_total": entita_count,
            "collegamenti_total": coll_count,
            "synced": fts_count == entita_count,
            "tipi": {r["tipo"]: r["c"] for r in tipo_dist},
            "fonti": {r["fonte_tabella"]: r["c"] for r in fonte_dist},
        }
    finally:
        conn.close()
