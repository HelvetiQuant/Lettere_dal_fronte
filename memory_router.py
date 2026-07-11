"""Hippocampal Memory Router — IMI Extractor.

Pipeline ispirata al richiamo umano:
  cue extraction → SQL esatto → FTS5/BM25 → grafo entità →
  archivio_fonti → (optional) LLM → (optional) cloud AI

Principio fondamentale: non recuperare più testo del necessario.
Ogni ricerca lascia una traccia in memory_trace.
Le query frequenti convergono verso consolidated_memory.

Non tocca nessuna tabella esistente.
Dipende da: database.py, search_service.py
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

from database import get_conn
from search_service import search_entities, get_entity_network

# Import lazy per evitare dipendenza circolare (ai_research importa database)
_ai_research = None

def _get_ai_research():
    global _ai_research
    if _ai_research is None:
        import ai_research as _m
        _ai_research = _m
    return _ai_research

# ─── Config ────────────────────────────────────────────────────────────────────

RETRIEVAL_BUDGET = {
    "max_sources": 8,
    "max_image_only": 3,
    "max_graph_depth": 2,
    "max_fts_results": 20,
    "max_sql_results": 50,
}

# Pattern per estrazione cue — nomi divisioni/reparti italiani/tedeschi/altri
_DIV_PATTERNS = [
    r"\b(\d+[°\.\s]*(?:divisione|div\.?|division))\b",
    r"\b(\d+[°\.\s]*(?:reggimento|rgt\.?|regiment|fanteria|alpini|bersaglieri|artiglieria))\b",
    r"\b(\d+[°\.\s]*(?:battaglione|btg\.?|battalion))\b",
    r"\b(\d+[°\.\s]*(?:compagnia|cp\.?|company))\b",
    r"\b(\d+[°\.\s]*(?:corpo d[''`]armata|corps?))\b",
    r"\b(\d+[°\.\s]*(?:armata|army))\b",
    r"\b(jäger.?division|jaeger.?division|jager.?division|infanterie.?division|panzer.?division|gebirgs.?division)\b",
    r"\b(\d+\.?\s*(?:jäger|jager|jaeger|infanterie|panzer|gebirgs)[\s\-]?division)\b",
    r"\b(\d+\.?\s*(?:jäger|jager|jaeger|infanterie|panzer|gebirgs)[\s\-]?div\.?)\b",
]

_DATE_PATTERNS = [
    r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b",
    r"\b(\d{4})\b",
    r"\b(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
    r"settembre|ottobre|novembre|dicembre)\b",
    r"\b(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b",
    r"\b(\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
    r"settembre|ottobre|novembre|dicembre)\s+\d{4})\b",
]

_WAR_KEYWORDS = {
    "ww1": ["prima guerra", "grande guerra", "1914", "1915", "1916", "1917", "1918",
            "world war 1", "wwi", "ww1"],
    "ww2": ["seconda guerra", "1939", "1940", "1941", "1942", "1943", "1944", "1945",
            "world war 2", "wwii", "ww2"],
}

_ARCHIVE_KEYWORDS = ["nara", "aussme", "bundesarchiv", "tna", "shd", "t315", "wo95",
                     "rg407", "fondo", "segnatura", "busta", "fascicolo"]

_DOC_REQUEST_KEYWORDS = ["documento", "pdf", "immagine", "jpeg", "originale",
                          "scansione", "diario", "aar", "war diary", "ktb",
                          "kriegstagebuch", "journal de marche", "jmo"]


# ─── Tabelle ───────────────────────────────────────────────────────────────────

def _init_tables():
    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_trace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            cue_persona TEXT,
            cue_luogo TEXT,
            cue_reparto TEXT,
            cue_data TEXT,
            cue_guerra TEXT,
            cue_archivio TEXT,
            route_selected TEXT,
            sources_found INTEGER DEFAULT 0,
            image_only_found INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            used_fts INTEGER DEFAULT 0,
            used_graph INTEGER DEFAULT 0,
            used_cloud_ai INTEGER DEFAULT 0,
            tokens_saved_estimate INTEGER DEFAULT 0,
            response_ms INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS consolidated_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            summary TEXT,
            entities_json TEXT,
            sources_json TEXT,
            archivio_fonti_ids TEXT,
            query_count INTEGER DEFAULT 1,
            confidence REAL DEFAULT 0.0,
            last_verified_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(topic)
        )
    """)

    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_mt_created ON memory_trace(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_mt_cue_persona ON memory_trace(cue_persona)",
        "CREATE INDEX IF NOT EXISTS idx_mt_cue_reparto ON memory_trace(cue_reparto)",
        "CREATE INDEX IF NOT EXISTS idx_cm_topic ON consolidated_memory(topic)",
        "CREATE INDEX IF NOT EXISTS idx_cm_qcount ON consolidated_memory(query_count DESC)",
    ]:
        conn.execute(idx)

    conn.commit()
    conn.close()


# ─── Cue Extraction ────────────────────────────────────────────────────────────

def extract_cues(query: str) -> dict:
    """Estrae dal testo libero tutti i cue strutturati rilevanti."""
    q = query.lower().strip()

    # Parole militari/geografiche da NON interpretare come persona
    _NON_PERSONA = {
        "Divisione", "Division", "Reggimento", "Regiment", "Battaglione",
        "Battalion", "Compagnia", "Company", "Armata", "Army", "Corpo",
        "Corps", "Jager", "Jaeger", "Jäger", "Panzer", "Infanterie",
        "Gebirgs", "Lagebericht", "Befehl", "Tatigkeitsbericht",
        "Fernspruch", "Kriegstagebuch", "Monte", "Valle", "Colle",
        "Nord", "Sud", "Est", "Ovest", "Grecia", "Italia", "Francia",
        "Balcani", "Africa", "Nara", "World", "War",
    }

    # Persona: cerca pattern Cognome Nome o viceversa (esclude termini militari)
    persona = None
    for m in re.finditer(r"\b([A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+)\s+([A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+)\b", query):
        w1, w2 = m.group(1), m.group(2)
        if w1 not in _NON_PERSONA and w2 not in _NON_PERSONA:
            persona = m.group(0)
            break

    # Reparto / divisione
    reparto_list = []
    for pat in _DIV_PATTERNS:
        for m in re.finditer(pat, q, re.IGNORECASE):
            reparto_list.append(m.group(1).strip())
    reparto = reparto_list[0] if reparto_list else None

    # Date
    date_list = []
    for pat in _DATE_PATTERNS:
        for m in re.finditer(pat, q, re.IGNORECASE):
            date_list.append(m.group(1))
    data = date_list[0] if date_list else None
    anni = [d for d in date_list if re.match(r"^\d{4}$", d)]

    # Guerra
    guerra = None
    for war, keywords in _WAR_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            guerra = war
            break
    if not guerra and anni:
        y = int(anni[0])
        if 1914 <= y <= 1918:
            guerra = "ww1"
        elif 1939 <= y <= 1945:
            guerra = "ww2"

    # Tipo documento tedesco → attiva ricerca archivio_fonti
    _TIPO_DOC_KEYWORDS = [
        "lagebericht", "tatigkeitsbericht", "tätigkeitsbericht",
        "befehl", "fernspruch", "fernschreiben", "tagesmeldung",
        "kriegstagebuch", "ktb", "war diary", "aar", "after action",
        "journal de marche", "jmo", "diario storico",
    ]
    tipo_documento_cue = next((kw for kw in _TIPO_DOC_KEYWORDS if kw in q), None)

    # Archivio / fondo
    archivio = None
    for kw in _ARCHIVE_KEYWORDS:
        if kw in q:
            archivio = kw
            break
    if not archivio and tipo_documento_cue:
        archivio = tipo_documento_cue  # forza layer archivio_fonti

    # Luogo: capitalizzate non già identificate come persona/reparto
    luogo = None
    luoghi_candidati = re.findall(r"\b([A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]{2,})\b", query)
    luoghi_stop = {"Battaglione", "Reggimento", "Divisione", "Compagnia", "Armata"}
    luogo_hits = [l for l in luoghi_candidati
                  if l not in luoghi_stop and (not persona or l not in persona)]
    if luogo_hits:
        # preferisci parole che assomigliano a toponimi (dopo "a", "in", "di", "presso")
        m_luogo = re.search(
            r"\b(?:a|in|presso|da|verso|nei pressi di)\s+([A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+)", query
        )
        luogo = m_luogo.group(1) if m_luogo else luogo_hits[0]

    # Richiesta documento originale
    richiede_doc = any(kw in q for kw in _DOC_REQUEST_KEYWORDS)

    # Query vaga: nessun cue strutturato preciso
    is_vague = not persona and not reparto and not archivio

    return {
        "persona": persona,
        "luogo": luogo,
        "reparto": reparto,
        "data": data,
        "anni": anni,
        "guerra": guerra,
        "archivio": archivio,
        "richiede_documento": richiede_doc,
        "is_vague": is_vague,
        "raw": query,
    }


# ─── Route Selection ───────────────────────────────────────────────────────────

def _select_route(cues: dict) -> list:
    """Decide quali livelli attivare, nell'ordine più efficiente."""
    route = []

    if cues["archivio"] or cues["richiede_documento"] or cues["reparto"] or cues["guerra"]:
        route.append("archivio_fonti")

    if cues["persona"] or cues["reparto"]:
        route.append("sql_exact")
        route.append("fts")
        route.append("graph")
    elif cues["luogo"] or cues["data"]:
        route.append("fts")
        route.append("graph")
    elif cues["is_vague"]:
        route.append("fts")
        route.append("vector_optional")

    if not route:
        route = ["fts", "graph"]

    return route


# ─── Retrieval layers ──────────────────────────────────────────────────────────

def _search_sql_exact(cues: dict) -> list:
    """Ricerca SQL esatta su tabelle strutturate."""
    conn = get_conn()
    results = []

    tables_cols = [
        ("internati", "cognome", "nome", "grado", "luogo_cattura"),
        ("caduti_cwgc", "cognome", "nome", "rank", "regiment"),
        ("decorati_nastroazzurro", "cognome", "nome", "arma", None),
        ("caduti_ministero", "cognome", "nome", "grado", "reparto"),
        ("caduti_sardi", "cognome", "nome", "grado", "reparto"),
        ("caduti_bologna", "nome", None, "grado", "reparto"),
    ]

    persona = cues.get("persona", "")
    parts = persona.split() if persona else []
    cognome = parts[0] if parts else None
    nome = parts[1] if len(parts) > 1 else None

    for (tbl, col_cog, col_nome, col_grado, col_reparto) in tables_cols:
        if not cognome:
            break
        try:
            conditions = [f"{col_cog} = ?"]
            params = [cognome]
            if nome and col_nome:
                conditions.append(f"{col_nome} = ?")
                params.append(nome)
            params.append(RETRIEVAL_BUDGET["max_sql_results"] // len(tables_cols))
            rows = conn.execute(
                f"SELECT * FROM {tbl} WHERE {' AND '.join(conditions)} LIMIT ?",
                params
            ).fetchall()
            for r in rows:
                results.append({
                    "source": "sql_exact",
                    "table": tbl,
                    "data": {k: r[k] for k in r.keys()},
                    "score": 1.0,
                })
        except Exception:
            pass

    conn.close()
    return results


def _search_fts(cues: dict) -> list:
    """FTS5/BM25 su entità."""
    parts = []
    if cues.get("persona"):
        parts.append(cues["persona"])
    if cues.get("reparto"):
        parts.append(cues["reparto"])
    if cues.get("luogo"):
        parts.append(cues["luogo"])
    if not parts:
        parts.append(cues["raw"])

    query_str = " ".join(parts)
    hits = search_entities(query_str, limit=RETRIEVAL_BUDGET["max_fts_results"])

    results = []
    for h in hits:
        results.append({
            "source": "fts",
            "table": h.get("fonte_tabella", "entita"),
            "entita_id": h.get("entita_id"),
            "data": h,
            "score": max(0.0, min(1.0, 1.0 + (h.get("rank") or 0) / 10.0)),
        })
    return results


def _search_graph(entity_ids: list, depth: int = None) -> list:
    """Graph traversal partendo dagli entita_id trovati."""
    if not entity_ids:
        return []
    depth = depth or RETRIEVAL_BUDGET["max_graph_depth"]
    results = []
    seen = set()
    for eid in entity_ids[:5]:  # limita entry points
        if eid in seen:
            continue
        seen.add(eid)
        try:
            net = get_entity_network(eid, depth=depth)
            for node in (net if isinstance(net, list) else []):
                nid = node.get("entita_id") or node.get("id")
                if nid and nid not in seen:
                    seen.add(nid)
                    results.append({
                        "source": "graph",
                        "table": node.get("tabella_origine", "entita"),
                        "entita_id": nid,
                        "data": node,
                        "score": max(0.1, 0.8 - 0.2 * node.get("depth", 1)),
                    })
        except Exception:
            pass
    return results


def _search_archivio_fonti(cues: dict) -> list:
    """Ricerca diretta in archivio_fonti con metadati militari."""
    conn = get_conn()
    conditions = []
    params = []

    if cues.get("reparto"):
        conditions.append(
            "(unita_principale LIKE ? OR unita_citate LIKE ? OR unita_superiore LIKE ?)"
        )
        u = f"%{cues['reparto']}%"
        params.extend([u, u, u])

    if cues.get("luogo"):
        conditions.append("(teatro_operazioni LIKE ? OR luoghi_citati LIKE ?)")
        l = f"%{cues['luogo']}%"
        params.extend([l, l])

    if cues.get("archivio"):
        conditions.append("archivio LIKE ?")
        params.append(f"%{cues['archivio']}%")

    if cues.get("anni"):
        year = cues["anni"][0]
        conditions.append("(data_inizio LIKE ? OR data_fine LIKE ?)")
        params.extend([f"{year}%", f"{year}%"])

    if cues.get("guerra"):
        war_map = {"ww1": "World War 1", "ww2": "World War 2"}
        conditions.append("conflitto = ?")
        params.append(war_map.get(cues["guerra"], ""))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(RETRIEVAL_BUDGET["max_sources"])

    try:
        rows = conn.execute(
            f"""SELECT id, hash_sha256, archivio, fondo, segnatura, titolo_documento,
                       unita_principale, teatro_operazioni, data_inizio, data_fine,
                       tipo_documento, ocr_status, readable, qualita_immagine,
                       attendibilita_fonte, testo_ocr, formato
                FROM archivio_fonti {where}
                ORDER BY attendibilita_fonte DESC, readable DESC
                LIMIT ?""",
            params
        ).fetchall()
    except Exception:
        rows = []
    conn.close()

    results = []
    for r in rows:
        score = ((r["attendibilita_fonte"] or 3) / 5.0) * 0.6
        if r["readable"]:
            score += 0.3
        if r["qualita_immagine"]:
            score += r["qualita_immagine"] * 0.1
        results.append({
            "source": "archivio_fonti",
            "table": "archivio_fonti",
            "data": {k: r[k] for k in r.keys()},
            "score": round(score, 3),
            "file_url": f"/api/archivio/file/{r['hash_sha256']}",
            "readable": bool(r["readable"]),
            "ocr_status": r["ocr_status"],
        })
    return results


# ─── Scoring e merge ───────────────────────────────────────────────────────────

def _score_and_merge(all_results: list, cues: dict) -> list:
    """
    Deduplica e assegna score finale:
      score = esattezza_metadati(0.4) + bm25(0.3) + attendibilita_fonte(0.2) + graph_proximity(0.1)
    """
    seen_keys = set()
    merged = []

    for r in all_results:
        key = (r.get("table"), str(r.get("data", {}).get("id") or r.get("entita_id", "")))
        if key in seen_keys:
            continue
        seen_keys.add(key)

        base = r.get("score", 0.5)

        # Bonus metadati: la fonte coincide con l'archivio cercato
        if cues.get("archivio") and r.get("source") == "archivio_fonti":
            arch = (r["data"].get("archivio") or "").lower()
            if cues["archivio"] in arch:
                base = min(1.0, base + 0.15)

        # Penalità immagini non leggibili (ma non escluderle)
        if r.get("source") == "archivio_fonti" and not r.get("readable"):
            base = max(0.1, base - 0.1)

        r["score_final"] = round(base, 3)
        merged.append(r)

    merged.sort(key=lambda x: x["score_final"], reverse=True)
    return merged[:RETRIEVAL_BUDGET["max_sources"]]


# ─── Memory Trace ──────────────────────────────────────────────────────────────

def _save_trace(
    query: str, cues: dict, route: list, results: list,
    confidence: float, response_ms: int
):
    conn = get_conn()
    image_only = sum(
        1 for r in results
        if r.get("source") == "archivio_fonti" and not r.get("readable")
    )
    # Stima token risparmiati: ogni documento non inviato all'AI = ~800 token
    total_docs = len(results)
    budget_used = min(total_docs, RETRIEVAL_BUDGET["max_sources"])
    tokens_saved = max(0, (total_docs - budget_used)) * 800

    try:
        conn.execute("""
            INSERT INTO memory_trace (
                query, cue_persona, cue_luogo, cue_reparto, cue_data,
                cue_guerra, cue_archivio, route_selected, sources_found,
                image_only_found, confidence, used_fts, used_graph,
                used_cloud_ai, tokens_saved_estimate, response_ms, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            query,
            cues.get("persona"), cues.get("luogo"), cues.get("reparto"),
            cues.get("data"), cues.get("guerra"), cues.get("archivio"),
            json.dumps(route),
            len(results), image_only, confidence,
            1 if "fts" in route else 0,
            1 if "graph" in route else 0,
            0,  # cloud_ai: aggiornato dopo se usato
            tokens_saved, response_ms,
            datetime.now().isoformat()
        ))
        conn.commit()
    except Exception as e:
        print(f"  memory_trace write error: {e}")
    finally:
        conn.close()


def _check_consolidation(query: str, cues: dict, results: list):
    """
    Se la stessa combinazione (reparto+teatro+anno) ricorre ≥3 volte,
    propone o aggiorna una consolidated_memory.
    """
    if not (cues.get("reparto") or cues.get("persona")):
        return

    topic_parts = [
        cues.get("reparto") or "",
        cues.get("luogo") or "",
        cues.get("anni")[0] if cues.get("anni") else "",
    ]
    topic = " / ".join(p for p in topic_parts if p).strip()
    if not topic:
        return

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id, query_count FROM consolidated_memory WHERE topic = ?", (topic,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE consolidated_memory SET query_count = query_count + 1, last_verified_at = ? WHERE id = ?",
                (datetime.now().isoformat(), existing["id"])
            )
        else:
            # Conta quante trace simili esistono già
            count_row = conn.execute(
                "SELECT COUNT(*) FROM memory_trace WHERE cue_reparto LIKE ?",
                (f"%{cues.get('reparto', '')}%",)
            ).fetchone()
            n_prev = count_row[0] if count_row else 0

            if n_prev >= 2:
                entity_ids = [r.get("entita_id") for r in results if r.get("entita_id")]
                af_ids = [r["data"]["id"] for r in results if r.get("source") == "archivio_fonti"]
                conn.execute("""
                    INSERT OR IGNORE INTO consolidated_memory
                    (topic, entities_json, sources_json, archivio_fonti_ids,
                     query_count, confidence, created_at, last_verified_at)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    topic,
                    json.dumps(entity_ids[:20]),
                    json.dumps(list({r["table"] for r in results})),
                    json.dumps(af_ids[:10]),
                    n_prev + 1,
                    round(sum(r.get("score_final", 0) for r in results) / max(len(results), 1), 3),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ))
        conn.commit()
    except Exception as e:
        print(f"  consolidation error: {e}")
    finally:
        conn.close()


# ─── Main entry point ──────────────────────────────────────────────────────────

def _build_local_context_summary(scored: list, cues: dict) -> str:
    """Costruisce un riassunto compatto dei risultati locali da passare a Perplexity."""
    lines = []
    lines.append(f"Query: {cues['raw']}")
    if cues.get('persona'):
        lines.append(f"Persona cercata: {cues['persona']}")
    if cues.get('reparto'):
        lines.append(f"Reparto: {cues['reparto']}")
    if cues.get('luogo'):
        lines.append(f"Luogo: {cues['luogo']}")
    if cues.get('anni'):
        lines.append(f"Anno/i: {', '.join(cues['anni'])}")
    if cues.get('guerra'):
        lines.append(f"Conflitto: {cues['guerra'].upper()}")

    if scored:
        lines.append(f"\nNel database locale sono stati trovati {len(scored)} risultati parziali:")
        for r in scored[:5]:
            d = r.get('data', {})
            label = (d.get('valore') or d.get('cognome') or
                     d.get('titolo_documento') or d.get('nominativo') or r.get('table'))
            lines.append(f"  - [{r['source']}:{r['table']}] {str(label)[:80]}")
    else:
        lines.append("\nNessun risultato trovato nel database locale.")

    lines.append(
        "\nIntegra con fonti esterne attendibili (NARA, TNA, Bundesarchiv, AUSSME, "
        "Commonwealth War Graves, MDH Francia, Ancestry, Fold3) cercando informazioni "
        "storiche verificate. NON inventare dati. Cita le fonti."
    )
    return "\n".join(lines)


def route_query(query: str, depth: int = None, use_cloud_fallback: bool = True) -> dict:
    """
    Entry point principale del Memory Router.

    Args:
        query: testo libero dell'utente
        depth: profondità grafo (default da RETRIEVAL_BUDGET)

    Returns:
        dict con query, cues, route, sources_found, image_only_sources,
        verified_sources, suggested_next_steps, need_cloud_ai, confidence
    """
    t0 = time.perf_counter()
    _init_tables()

    cues = extract_cues(query)
    route = _select_route(cues)

    all_results = []
    used_fts = False
    used_graph = False

    # Layer 1 — SQL esatto (più economico)
    if "sql_exact" in route:
        all_results.extend(_search_sql_exact(cues))

    # Layer 2 — FTS5/BM25
    if "fts" in route:
        fts_hits = _search_fts(cues)
        all_results.extend(fts_hits)
        used_fts = bool(fts_hits)

    # Layer 3 — Graph expansion (usa entita_id trovati da FTS)
    if "graph" in route:
        entity_ids = [r["entita_id"] for r in all_results if r.get("entita_id")]
        if entity_ids:
            graph_hits = _search_graph(entity_ids, depth=depth)
            all_results.extend(graph_hits)
            used_graph = bool(graph_hits)

    # Layer 4 — Archivio fonti (documenti originali)
    if "archivio_fonti" in route or cues.get("reparto") or cues.get("archivio"):
        af_hits = _search_archivio_fonti(cues)
        all_results.extend(af_hits)

    # Scoring e merge
    scored = _score_and_merge(all_results, cues)

    # Separa documenti leggibili da image-only
    verified = [r for r in scored if r.get("readable") is True or r.get("source") != "archivio_fonti"]
    image_only = [r for r in scored
                  if r.get("source") == "archivio_fonti" and not r.get("readable")]
    image_only = image_only[:RETRIEVAL_BUDGET["max_image_only"]]

    # Confidence globale
    if scored:
        confidence = round(sum(r["score_final"] for r in scored) / len(scored), 3)
    else:
        confidence = 0.0

    # Decide se serve cloud AI
    need_cloud = (
        len(verified) == 0 and confidence < 0.25
    )

    # ── Fallback Perplexity (solo se need_cloud e non query vaga generica) ──
    cloud_result = None
    if need_cloud and use_cloud_fallback and not cues["is_vague"]:
        try:
            ai = _get_ai_research()
            local_ctx = _build_local_context_summary(scored, cues)
            cloud_result = ai.research_with_perplexity(query=query, limit=5)
            # Sovrascrive il contesto con quello arricchito locale+query
            route.append("perplexity")
        except Exception as e:
            cloud_result = {"error": str(e), "provider": "perplexity", "risposta": None}
            route.append("perplexity_error")

    # Suggested next steps
    suggestions = []
    if image_only:
        suggestions.append(
            f"{len(image_only)} documento/i in corsivo/illeggibile: "
            "recuperabile come file originale, considerare HTR manuale."
        )
    if need_cloud and cues["is_vague"]:
        suggestions.append(
            "Query vaga: aggiungi reparto, anno o archivio per risultati più precisi."
        )
    if need_cloud and not cues["is_vague"] and cloud_result and not cloud_result.get("error"):
        suggestions.append("Risultati integrati via Perplexity (fonti esterne).")
    elif need_cloud and not cues["is_vague"] and not cloud_result:
        suggestions.append("Nessun risultato locale — PERPLEXITY_API_KEY non configurata.")

    # Controlla consolidation
    _check_consolidation(query, cues, scored)

    # Aggiorna trace con cloud_ai=1 se usato
    response_ms = int((time.perf_counter() - t0) * 1000)
    _save_trace(query, cues, route, scored, confidence, response_ms)
    if cloud_result and not cloud_result.get("error"):
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE memory_trace SET used_cloud_ai=1 WHERE id=(SELECT MAX(id) FROM memory_trace)"
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    return {
        "query": query,
        "cues": cues,
        "route": route,
        "response_ms": response_ms,
        "sources_found": scored,
        "image_only_sources": image_only,
        "verified_sources": verified[:RETRIEVAL_BUDGET["max_sources"]],
        "cloud_result": cloud_result,
        "suggested_next_steps": suggestions,
        "need_cloud_ai": need_cloud,
        "confidence": confidence,
        "retrieval_budget": RETRIEVAL_BUDGET,
    }


# ─── Utility pubbliche ─────────────────────────────────────────────────────────

def count_traces() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM memory_trace").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def get_consolidated(limit: int = 20) -> list:
    """Ritorna le consolidated_memory ordinate per frequenza query."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, topic, summary, query_count, confidence, last_verified_at
               FROM consolidated_memory ORDER BY query_count DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_recent_traces(limit: int = 20) -> list:
    """Ultime N ricerche con metriche."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT query, cue_persona, cue_reparto, cue_luogo, route_selected,
                      sources_found, confidence, response_ms, tokens_saved_estimate, created_at
               FROM memory_trace ORDER BY created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()
