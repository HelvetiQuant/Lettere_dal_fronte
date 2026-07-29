"""Consumer Adapter — ponte tra i consumer esistenti (RAG, grafi, biografie,
report, mappe) e il nuovo schema canonico Supabase (archive.external_items,
evidence.claims, evidence.evidence, api_public.published_claims).

Questo modulo NON sostituisce i consumer esistenti: fornisce funzioni di
lettura dal nuovo schema che i consumer possono usare come fonte aggiuntiva
o alternativa a SQLite, mantenendo backward compatibility.

Casi d'uso:
  - RAG: retrieve() può cercare in evidence.claims + archive.external_items
    oltre che in SQLite FTS5
  - Grafi: get_entity_graph() può leggere relazioni da evidence.claims
    oltre che da graph_edges SQLite
  - Biografie: get_biographical_claims() estrae claim atomiche per una persona
  - Report: get_published_claims() per report pubblicabili
  - Mappe: get_geo_claims() per claim con coordinate geografiche
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("consumer_adapter")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


# ─── Data classes ───────────────────────────────────────────────────────────

@dataclass
class ClaimSummary:
    """Rappresenta una claim atomica dallo schema evidence."""
    claim_id: int
    stable_id: str
    subject_entity_id: int
    subject_name: str
    predicate: str
    object_entity_id: Optional[int]
    object_name: str
    object_value: Optional[str]
    claim_status: str
    valid_from: Optional[str]
    valid_to: Optional[str]
    evidence_count: int
    latest_decision: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "stable_id": self.stable_id,
            "subject_entity_id": self.subject_entity_id,
            "subject_name": self.subject_name,
            "predicate": self.predicate,
            "object_entity_id": self.object_entity_id,
            "object_name": self.object_name,
            "object_value": self.object_value,
            "claim_status": self.claim_status,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "evidence_count": self.evidence_count,
            "latest_decision": self.latest_decision,
        }


@dataclass
class EvidenceSummary:
    """Rappresenta una evidence dallo schema evidence."""
    evidence_id: int
    claim_id: int
    evidence_type: str
    source_item_id: Optional[int]
    source_provider_code: str
    text_span: str
    independence_group: str
    review_status: str
    human_verified: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "claim_id": self.claim_id,
            "evidence_type": self.evidence_type,
            "source_item_id": self.source_item_id,
            "source_provider_code": self.source_provider_code,
            "text_span": self.text_span,
            "independence_group": self.independence_group,
            "review_status": self.review_status,
            "human_verified": self.human_verified,
        }


@dataclass
class ExternalItemSummary:
    """Rappresenta un external_item dallo schema archive."""
    item_id: int
    stable_id: str
    provider_code: str
    external_id: str
    item_type: str
    title: str
    description: str
    canonical_url: str
    holding_institution: str
    collection_or_fonds: str
    archival_signature: str
    access_status: str
    review_status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "stable_id": self.stable_id,
            "provider_code": self.provider_code,
            "external_id": self.external_id,
            "item_type": self.item_type,
            "title": self.title,
            "description": self.description,
            "canonical_url": self.canonical_url,
            "holding_institution": self.holding_institution,
            "collection_or_fonds": self.collection_or_fonds,
            "archival_signature": self.archival_signature,
            "access_status": self.access_status,
            "review_status": self.review_status,
        }


# ─── Supabase RPC helpers ──────────────────────────────────────────────────

def _exec_sql_returning(sql: str) -> list:
    """Execute SQL that returns rows via exec_sql_returning RPC."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql_returning"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=60)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return []
    log.error("exec_sql_returning failed: %s", r.text[:500])
    return []


# ─── RAG Consumer ───────────────────────────────────────────────────────────

def search_claims(
    query: str,
    *,
    predicate: Optional[str] = None,
    claim_status: Optional[str] = None,
    limit: int = 30,
) -> List[ClaimSummary]:
    """Cerca claim nel nuovo schema per RAG retrieval.

    Args:
        query: testo di ricerca (match su subject_name, object_name, object_value)
        predicate: filtro opzionale su predicato (es. 'was_prisoner_in')
        claim_status: filtro opzionale (discovered, candidate, supported, verified, ...)
        limit: numero massimo di risultati

    Returns:
        Lista di ClaimSummary
    """
    conditions = []
    q = query.replace("'", "''")
    conditions.append(
        f"(c.subject_name ILIKE '%{q}%' OR c.object_name ILIKE '%{q}%' OR c.object_value ILIKE '%{q}%')"
    )
    if predicate:
        conditions.append(f"c.predicate = '{predicate}'")
    if claim_status:
        conditions.append(f"c.claim_status = '{claim_status}'")

    where = " AND ".join(conditions)
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            c.id AS claim_id,
            c.stable_id,
            c.subject_entity_id,
            e_s.name AS subject_name,
            c.predicate,
            c.object_entity_id,
            e_o.name AS object_name,
            c.object_value,
            c.claim_status,
            c.valid_from::text,
            c.valid_to::text,
            COUNT(ev.id) AS evidence_count,
            (SELECT ed.decision FROM evidence.editorial_decisions ed
             WHERE ed.claim_id = c.id ORDER BY ed.decided_at DESC LIMIT 1) AS latest_decision
        FROM evidence.claims c
        LEFT JOIN core.entities e_s ON e_s.id = c.subject_entity_id
        LEFT JOIN core.entities e_o ON e_o.id = c.object_entity_id
        LEFT JOIN evidence.evidence ev ON ev.claim_id = c.id
        WHERE {where}
        GROUP BY c.id, e_s.name, e_o.name
        ORDER BY c.id
        LIMIT {limit}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return [_row_to_claim(r) for r in rows if r]


def search_external_items(
    query: str,
    *,
    provider_code: Optional[str] = None,
    item_type: Optional[str] = None,
    limit: int = 30,
) -> List[ExternalItemSummary]:
    """Cerca external_items nel nuovo schema per RAG retrieval.

    Args:
        query: testo di ricerca (match su title, description)
        provider_code: filtro opzionale per provider
        item_type: filtro opzionale per tipo
        limit: numero massimo di risultati

    Returns:
        Lista di ExternalItemSummary
    """
    conditions = []
    q = query.replace("'", "''")
    conditions.append(f"(i.title ILIKE '%{q}%' OR i.description ILIKE '%{q}%')")
    if provider_code:
        conditions.append(f"i.provider_code = '{provider_code}'")
    if item_type:
        conditions.append(f"i.item_type = '{item_type}'")

    where = " AND ".join(conditions)
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            i.id AS item_id,
            i.stable_id,
            i.provider_code,
            i.external_id,
            i.item_type,
            i.title,
            COALESCE(i.description, '') AS description,
            COALESCE(i.canonical_url, '') AS canonical_url,
            COALESCE(i.holding_institution, '') AS holding_institution,
            COALESCE(i.collection_or_fonds, '') AS collection_or_fonds,
            COALESCE(i.archival_signature, '') AS archival_signature,
            COALESCE(i.access_status, '') AS access_status,
            COALESCE(i.review_status, '') AS review_status
        FROM archive.external_items i
        WHERE {where}
        ORDER BY i.id
        LIMIT {limit}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return [_row_to_external_item(r) for r in rows if r]


def get_evidence_for_claim(claim_id: int) -> List[EvidenceSummary]:
    """Recupera tutte le evidence per una claim."""
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            ev.id AS evidence_id,
            ev.claim_id,
            ev.evidence_type,
            ev.source_item_id,
            COALESCE(p.provider_code, '') AS source_provider_code,
            COALESCE(ev.text_span, '') AS text_span,
            COALESCE(ev.independence_group, '') AS independence_group,
            ev.review_status,
            ev.human_verified
        FROM evidence.evidence ev
        LEFT JOIN archive.external_items ei ON ei.id = ev.source_item_id
        LEFT JOIN archive.providers p ON p.id = ei.provider_id
        WHERE ev.claim_id = {claim_id}
        ORDER BY ev.id
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return [_row_to_evidence(r) for r in rows if r]


# ─── Graph Consumer ─────────────────────────────────────────────────────────

def get_entity_graph(
    entity_id: int,
    *,
    max_depth: int = 2,
    limit: int = 50,
) -> Dict[str, Any]:
    """Costruisce un grafo di relazioni partendo da un'entità usando evidence.claims.

    Args:
        entity_id: ID dell'entità di partenza
        max_depth: profondità del grafo (1 = diretti, 2 = 2-hop)
        limit: numero massimo di nodi

    Returns:
        Dict con nodes e edges
    """
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        WITH RECURSIVE graph AS (
            -- Nodo di partenza
            SELECT c.id AS claim_id, c.subject_entity_id, c.object_entity_id,
                   c.predicate, c.claim_status, 1 AS depth
            FROM evidence.claims c
            WHERE c.subject_entity_id = {entity_id} OR c.object_entity_id = {entity_id}
            UNION
            -- Espansione 1 livello
            SELECT c.id, c.subject_entity_id, c.object_entity_id,
                   c.predicate, c.claim_status, g.depth + 1
            FROM evidence.claims c
            JOIN graph g ON (c.subject_entity_id = g.object_entity_id
                          OR c.object_entity_id = g.subject_entity_id)
            WHERE g.depth < {max_depth}
        )
        SELECT DISTINCT
            g.claim_id,
            g.subject_entity_id,
            e_s.name AS subject_name,
            e_s.entity_type AS subject_type,
            g.object_entity_id,
            e_o.name AS object_name,
            e_o.entity_type AS object_type,
            g.predicate,
            g.claim_status,
            g.depth
        FROM graph g
        LEFT JOIN core.entities e_s ON e_s.id = g.subject_entity_id
        LEFT JOIN core.entities e_o ON e_o.id = g.object_entity_id
        ORDER BY g.depth, g.claim_id
        LIMIT {limit}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    if not rows:
        return {"nodes": [], "edges": []}

    nodes = {}
    edges = []
    for r in rows:
        sid = r.get("subject_entity_id")
        oid = r.get("object_entity_id")
        if sid and sid not in nodes:
            nodes[sid] = {
                "id": sid,
                "name": r.get("subject_name", ""),
                "type": r.get("subject_type", ""),
            }
        if oid and oid not in nodes:
            nodes[oid] = {
                "id": oid,
                "name": r.get("object_name", ""),
                "type": r.get("object_type", ""),
            }
        edges.append({
            "source": sid,
            "target": oid,
            "predicate": r.get("predicate", ""),
            "claim_status": r.get("claim_status", ""),
            "claim_id": r.get("claim_id"),
        })

    return {"nodes": list(nodes.values()), "edges": edges}


# ─── Biography Consumer ─────────────────────────────────────────────────────

def get_biographical_claims(person_entity_id: int) -> List[ClaimSummary]:
    """Recupera tutte le claim biografiche per una persona.

    Ordinate per data (date_from) ascendente.
    """
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            c.id AS claim_id,
            c.stable_id,
            c.subject_entity_id,
            e_s.name AS subject_name,
            c.predicate,
            c.object_entity_id,
            e_o.name AS object_name,
            c.object_value,
            c.claim_status,
            c.valid_from::text,
            c.valid_to::text,
            COUNT(ev.id) AS evidence_count,
            (SELECT ed.decision FROM evidence.editorial_decisions ed
             WHERE ed.claim_id = c.id ORDER BY ed.decided_at DESC LIMIT 1) AS latest_decision
        FROM evidence.claims c
        LEFT JOIN core.entities e_s ON e_s.id = c.subject_entity_id
        LEFT JOIN core.entities e_o ON e_o.id = c.object_entity_id
        LEFT JOIN evidence.evidence ev ON ev.claim_id = c.id
        WHERE c.subject_entity_id = {person_entity_id}
        GROUP BY c.id, e_s.name, e_o.name
        ORDER BY c.valid_from NULLS LAST, c.id
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return [_row_to_claim(r) for r in rows if r]


# ─── Report Consumer ────────────────────────────────────────────────────────

def get_published_claims(
    *,
    predicate: Optional[str] = None,
    limit: int = 100,
) -> List[ClaimSummary]:
    """Recupera claim pubblicabili dalla vista api_public.published_claims."""
    conditions = []
    if predicate:
        conditions.append(f"predicate = '{predicate}'")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT * FROM api_public.published_claims
        WHERE {where}
        LIMIT {limit}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return [_row_to_claim(r) for r in rows if r]


# ─── Map Consumer ───────────────────────────────────────────────────────────

def get_geo_claims(
    *,
    limit: int = 100,
) -> List[ClaimSummary]:
    """Recupera claim per visualizzazione su mappa. (Placeholder: il schema attuale
    non ha colonna place su claims, ma si puo derivare da object_entity o valid_from/valid_to.)"""
    sql = f"""
    SELECT json_agg(row_to_json(x)) FROM (
        SELECT
            c.id AS claim_id,
            c.stable_id,
            c.subject_entity_id,
            e_s.name AS subject_name,
            c.predicate,
            c.object_entity_id,
            e_o.name AS object_name,
            c.object_value,
            c.claim_status,
            c.valid_from::text,
            c.valid_to::text,
            COUNT(ev.id) AS evidence_count,
            (SELECT ed.decision FROM evidence.editorial_decisions ed
             WHERE ed.claim_id = c.id ORDER BY ed.decided_at DESC LIMIT 1) AS latest_decision
        FROM evidence.claims c
        LEFT JOIN core.entities e_s ON e_s.id = c.subject_entity_id
        LEFT JOIN core.entities e_o ON e_o.id = c.object_entity_id
        LEFT JOIN evidence.evidence ev ON ev.claim_id = c.id
        WHERE c.claim_status IN ('supported', 'verified')
        GROUP BY c.id, e_s.name, e_o.name
        ORDER BY c.id
        LIMIT {limit}
    ) x;
    """
    rows = _exec_sql_returning(sql)
    return [_row_to_claim(r) for r in rows if r]


# ─── RAG Integration ────────────────────────────────────────────────────────

def retrieve_from_supabase(
    query: str,
    *,
    entity_type: str = "generic",
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Retrieval ibrido dal nuovo schema Supabase per RAG.

    Cerca in:
    1. evidence.claims (claim atomiche con evidence)
    2. archive.external_items (fonti esterne)

    Returns:
        Lista di dict nel formato RetrievedChunk-compatible
    """
    chunks = []

    # 1. Cerca claim
    claims = search_claims(query, limit=limit // 2)
    for claim in claims:
        evidence = get_evidence_for_claim(claim.claim_id)
        text_parts = [f"{claim.subject_name} {claim.predicate} {claim.object_name}"]
        if claim.object_value:
            text_parts.append(claim.object_value)
        if claim.valid_from:
            text_parts.append(f"Data: {claim.valid_from}")
        text_parts.append(f"Stato: {claim.claim_status}")
        if evidence:
            providers = set(e.source_provider_code for e in evidence)
            text_parts.append(f"Fonti: {', '.join(providers)} ({len(evidence)} evidence)")

        chunks.append({
            "chunk_id": f"claim:{claim.claim_id}",
            "source_table": "evidence.claims",
            "source_id": claim.claim_id,
            "title": f"{claim.subject_name} {claim.predicate} {claim.object_name}",
            "text": ". ".join(text_parts),
            "score": 0.8 if claim.claim_status == "verified" else 0.6,
            "retrieval_method": "supabase_claims",
            "metadata": {
                "claim_status": claim.claim_status,
                "evidence_count": claim.evidence_count,
                "latest_decision": claim.latest_decision,
                "valid_from": claim.valid_from,
                "valid_to": claim.valid_to,
            },
        })

    # 2. Cerca external_items
    items = search_external_items(query, limit=limit // 2)
    for item in items:
        text_parts = [item.title]
        if item.description:
            text_parts.append(item.description)
        if item.holding_institution:
            text_parts.append(f"Istituto: {item.holding_institution}")
        if item.collection_or_fonds:
            text_parts.append(f"Fondo: {item.collection_or_fonds}")
        if item.archival_signature:
            text_parts.append(f"Segnatura: {item.archival_signature}")

        chunks.append({
            "chunk_id": f"ext_item:{item.item_id}",
            "source_table": "archive.external_items",
            "source_id": item.item_id,
            "title": item.title,
            "text": ". ".join(text_parts),
            "score": 0.6,
            "retrieval_method": "supabase_items",
            "metadata": {
                "provider_code": item.provider_code,
                "item_type": item.item_type,
                "canonical_url": item.canonical_url,
                "access_status": item.access_status,
                "review_status": item.review_status,
            },
        })

    return chunks[:limit]


# ─── Helpers ────────────────────────────────────────────────────────────────

def _row_to_claim(r: dict) -> ClaimSummary:
    return ClaimSummary(
        claim_id=r.get("claim_id", 0),
        stable_id=r.get("stable_id", ""),
        subject_entity_id=r.get("subject_entity_id", 0),
        subject_name=r.get("subject_name", ""),
        predicate=r.get("predicate", ""),
        object_entity_id=r.get("object_entity_id"),
        object_name=r.get("object_name", ""),
        object_value=r.get("object_value"),
        claim_status=r.get("claim_status", "discovered"),
        valid_from=r.get("valid_from"),
        valid_to=r.get("valid_to"),
        evidence_count=r.get("evidence_count", 0),
        latest_decision=r.get("latest_decision"),
    )


def _row_to_evidence(r: dict) -> EvidenceSummary:
    return EvidenceSummary(
        evidence_id=r.get("evidence_id", 0),
        claim_id=r.get("claim_id", 0),
        evidence_type=r.get("evidence_type", ""),
        source_item_id=r.get("source_item_id"),
        source_provider_code=r.get("source_provider_code", ""),
        text_span=r.get("text_span", ""),
        independence_group=r.get("independence_group", ""),
        review_status=r.get("review_status", "pending"),
        human_verified=r.get("human_verified", False),
    )


def _row_to_external_item(r: dict) -> ExternalItemSummary:
    return ExternalItemSummary(
        item_id=r.get("item_id", 0),
        stable_id=r.get("stable_id", ""),
        provider_code=r.get("provider_code", ""),
        external_id=r.get("external_id", ""),
        item_type=r.get("item_type", ""),
        title=r.get("title", ""),
        description=r.get("description", ""),
        canonical_url=r.get("canonical_url", ""),
        holding_institution=r.get("holding_institution", ""),
        collection_or_fonds=r.get("collection_or_fonds", ""),
        archival_signature=r.get("archival_signature", ""),
        access_status=r.get("access_status", ""),
        review_status=r.get("review_status", ""),
    )
