"""V7.3 Phase E — Legacy endpoint adapters with feature flags.

Provides adapter functions that legacy endpoints can call to route
through the V7.3 canonical pipeline instead of reading directly
from legacy tables (collegamenti, event_links, record_links).

Feature flags:
- V73_CANONICAL_DOSSIER: Use canonical pipeline for /api/dossier
- V73_CANONICAL_GRAPH: Use canonical relations for /api/graph
- V73_CANONICAL_MAP: Use canonical event registry for /api/map
- V73_CANONICAL_SEARCH: Use canonical entities for /api/search
- V73_CANONICAL_NARRATION: Use V7.3 narration planner

When a flag is OFF, the legacy behavior is preserved.
When a flag is ON, the canonical pipeline is used.
"""
from __future__ import annotations

import os
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"


# ─── Feature flags ──────────────────────────────────────────────────────────

def is_feature_enabled(flag: str) -> bool:
    """Check if a V7.3 feature flag is enabled.

    Flags are read from environment variables.
    Default: all flags OFF (legacy behavior preserved).
    """
    return os.environ.get(flag, "").lower().strip() in ("true", "1", "yes")


FEATURE_FLAGS = {
    "V73_CANONICAL_DOSSIER": "Use canonical pipeline for dossier",
    "V73_CANONICAL_GRAPH": "Use canonical relations for graph",
    "V73_CANONICAL_MAP": "Use canonical event registry for map",
    "V73_CANONICAL_SEARCH": "Use canonical entities for search",
    "V73_CANONICAL_NARRATION": "Use V7.3 narration planner",
    "V73_CANONICAL_LINKS": "Use canonical relations instead of legacy links",
}


def get_feature_status() -> Dict[str, bool]:
    """Get status of all feature flags."""
    return {flag: is_feature_enabled(flag) for flag in FEATURE_FLAGS}


# ─── Dossier adapter ────────────────────────────────────────────────────────

def get_dossier_legacy(internato_id: int) -> Dict[str, Any]:
    """Legacy dossier: reads directly from internati + collegamenti."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get internato record
    cur.execute("SELECT * FROM internati WHERE id = ?", (internato_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": "not_found", "id": internato_id}

    dossier = dict(row)

    # Get legacy collegamenti (NOT filtered by quarantine)
    cur.execute("""
        SELECT tipo_collegamento, entita_id, tabella_origine, record_id
        FROM collegamenti
        WHERE record_id = ? AND tabella_origine = 'internati'
        LIMIT 100
    """, (internato_id,))
    dossier["collegamenti"] = [dict(r) for r in cur.fetchall()]

    # Get legacy record_links (NOT filtered by quarantine)
    cur.execute("""
        SELECT * FROM record_links
        WHERE (from_table = 'internati' AND from_id = ?)
        OR (to_table = 'internati' AND to_id = ?)
        LIMIT 100
    """, (internato_id, internato_id))
    dossier["record_links"] = [dict(r) for r in cur.fetchall()]

    conn.close()
    dossier["source"] = "legacy"
    return dossier


def get_dossier_canonical(internato_id: int) -> Dict[str, Any]:
    """Canonical dossier: reads from canonical tables only.

    Legacy collegamenti and record_links are NOT read.
    Only canonical_entities, canonical_claims, canonical_relations
    with usable_as_evidence=1 are included.
    """
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get internato record (base data is always from source table)
    cur.execute("SELECT * FROM internati WHERE id = ?", (internato_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": "not_found", "id": internato_id}

    dossier = dict(row)

    # Get canonical entity for this internato
    cur.execute("""
        SELECT * FROM canonical_entities
        WHERE source_table = 'internati' AND source_id = ?
    """, (internato_id,))
    entity = cur.fetchone()
    if entity:
        entity_dict = dict(entity)
        dossier["canonical_entity"] = entity_dict

        # Get canonical claims (only usable_as_evidence=1)
        cur.execute("""
            SELECT * FROM canonical_claims
            WHERE subject_entity_id = ? AND usable_as_evidence = 1
        """, (entity_dict["entity_id"],))
        dossier["canonical_claims"] = [dict(r) for r in cur.fetchall()]

        # Get canonical relations (only status != REJECTED)
        cur.execute("""
            SELECT * FROM canonical_relations
            WHERE (subject_entity_id = ? OR object_entity_id = ?)
            AND status != 'REJECTED'
        """, (entity_dict["entity_id"], entity_dict["entity_id"]))
        dossier["canonical_relations"] = [dict(r) for r in cur.fetchall()]
    else:
        dossier["canonical_claims"] = []
        dossier["canonical_relations"] = []

    conn.close()
    dossier["source"] = "canonical_v73"
    return dossier


def get_dossier(internato_id: int) -> Dict[str, Any]:
    """Get dossier — routes through canonical or legacy based on feature flag."""
    if is_feature_enabled("V73_CANONICAL_DOSSIER"):
        return get_dossier_canonical(internato_id)
    return get_dossier_legacy(internato_id)


# ─── Graph adapter ──────────────────────────────────────────────────────────

def get_graph_legacy(entity_id: int) -> Dict[str, Any]:
    """Legacy graph: reads from collegamenti."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM collegamenti
        WHERE record_id = ?
        LIMIT 500
    """, (entity_id,))
    edges = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {"nodes": [], "edges": edges, "source": "legacy"}


def get_graph_canonical(entity_id: str) -> Dict[str, Any]:
    """Canonical graph: reads from canonical_relations only."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM canonical_relations
        WHERE (subject_entity_id = ? OR object_entity_id = ?)
        AND status != 'REJECTED'
    """, (entity_id, entity_id))
    edges = [dict(r) for r in cur.fetchall()]

    # Get connected entities
    entity_ids = set()
    for e in edges:
        entity_ids.add(e["subject_entity_id"])
        entity_ids.add(e["object_entity_id"])

    nodes = []
    if entity_ids:
        placeholders = ", ".join(["?"] * len(entity_ids))
        cur.execute(f"""
            SELECT * FROM canonical_entities
            WHERE entity_id IN ({placeholders})
        """, list(entity_ids))
        nodes = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {"nodes": nodes, "edges": edges, "source": "canonical_v73"}


def get_graph(entity_id: str) -> Dict[str, Any]:
    """Get graph — routes through canonical or legacy."""
    if is_feature_enabled("V73_CANONICAL_GRAPH"):
        return get_graph_canonical(entity_id)
    return get_graph_legacy(int(entity_id) if str(entity_id).isdigit() else 0)


# ─── Map adapter ────────────────────────────────────────────────────────────

def get_map_events_legacy() -> List[Dict[str, Any]]:
    """Legacy map events: reads from eventi_1gm (local copy in imi_internati.db)."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM eventi_1gm")
    events = [dict(r) for r in cur.fetchall()]

    conn.close()
    return events


def get_map_events_canonical() -> List[Dict[str, Any]]:
    """Canonical map events: reads from canonical_event_registry."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM canonical_event_registry
        WHERE review_status = 'active'
        ORDER BY data_inizio
    """)
    events = [dict(r) for r in cur.fetchall()]

    conn.close()
    return events


def get_map_events() -> List[Dict[str, Any]]:
    """Get map events — routes through canonical or legacy."""
    if is_feature_enabled("V73_CANONICAL_MAP"):
        return get_map_events_canonical()
    return get_map_events_legacy()


# ─── Search adapter ─────────────────────────────────────────────────────────

def search_legacy(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Legacy search: uses search_all from database module."""
    try:
        from database import search_all
        return search_all(query, limit=limit)
    except Exception as e:
        logger.error(f"Legacy search failed: {e}")
        return []


def search_canonical(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Canonical search: uses canonical_entities with normalized names."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Normalize query
    from text_matching_v73 import normalize_text, tokenize
    normalized = normalize_text(query)
    tokens = tokenize(normalized)

    if not tokens:
        conn.close()
        return []

    # Search by cognome + nome
    cognome = tokens[0] if tokens else ""
    nome = " ".join(tokens[1:]) if len(tokens) > 1 else ""

    if nome:
        cur.execute("""
            SELECT * FROM canonical_entities
            WHERE entity_type = 'person'
            AND (normalized_name LIKE ? OR cognome = ?)
            LIMIT ?
        """, (f"%{normalized}%", cognome, limit))
    else:
        cur.execute("""
            SELECT * FROM canonical_entities
            WHERE entity_type = 'person'
            AND (normalized_name LIKE ? OR cognome = ?)
            LIMIT ?
        """, (f"%{normalized}%", cognome, limit))

    results = [dict(r) for r in cur.fetchall()]
    conn.close()
    return results


def search(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Search — routes through canonical or legacy."""
    if is_feature_enabled("V73_CANONICAL_SEARCH"):
        return search_canonical(query, limit)
    return search_legacy(query, limit)


# ─── Link quarantine filter ─────────────────────────────────────────────────

def filter_quarantined_links(links: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """Split links into usable and quarantined.

    Returns (usable, quarantined) tuple.
    Usable links have usable_as_evidence=1.
    """
    usable = [l for l in links if l.get("usable_as_evidence") == 1]
    quarantined = [l for l in links if l.get("usable_as_evidence") != 1]
    return usable, quarantined


def get_event_links_canonical(event_id: int) -> Dict[str, Any]:
    """Get event links with quarantine filtering.

    Returns both usable and quarantined links, clearly separated.
    """
    conn = sqlite3.connect(str(DB_EVENTS))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all links for this event
    cur.execute("SELECT * FROM event_links WHERE evento_id = ?", (event_id,))
    all_links = [dict(r) for r in cur.fetchall()]

    usable, quarantined = filter_quarantined_links(all_links)

    conn.close()
    return {
        "usable_links": usable,
        "quarantined_links": quarantined,
        "total": len(all_links),
        "usable_count": len(usable),
        "quarantined_count": len(quarantined),
    }


def get_record_links_canonical(record_id: int, table: str = "internati") -> Dict[str, Any]:
    """Get record links with quarantine filtering."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM record_links
        WHERE (from_table = ? AND from_id = ?)
        OR (to_table = ? AND to_id = ?)
    """, (table, record_id, table, record_id))
    all_links = [dict(r) for r in cur.fetchall()]

    usable, quarantined = filter_quarantined_links(all_links)

    conn.close()
    return {
        "usable_links": usable,
        "quarantined_links": quarantined,
        "total": len(all_links),
        "usable_count": len(usable),
        "quarantined_count": len(quarantined),
    }


# ─── API endpoint info ──────────────────────────────────────────────────────

def get_endpoint_info() -> Dict[str, Any]:
    """Get information about which endpoints use canonical vs legacy."""
    return {
        "feature_flags": get_feature_status(),
        "endpoints": {
            "/api/dossier/{id}": {
                "canonical_flag": "V73_CANONICAL_DOSSIER",
                "canonical": "get_dossier_canonical",
                "legacy": "get_dossier_legacy",
            },
            "/api/graph/{id}": {
                "canonical_flag": "V73_CANONICAL_GRAPH",
                "canonical": "get_graph_canonical",
                "legacy": "get_graph_legacy",
            },
            "/api/map/events": {
                "canonical_flag": "V73_CANONICAL_MAP",
                "canonical": "get_map_events_canonical",
                "legacy": "get_map_events_legacy",
            },
            "/api/search": {
                "canonical_flag": "V73_CANONICAL_SEARCH",
                "canonical": "search_canonical",
                "legacy": "search_legacy",
            },
        },
        "quarantine_status": {
            "event_links": {
                "total": "1,539,685",
                "quarantined": "1,539,685",
                "usable": 0,
            },
            "record_links": {
                "total": "169,184",
                "quarantined": "169,184",
                "usable": 0,
            },
        },
    }
