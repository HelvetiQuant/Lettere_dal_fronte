"""RAG Pipeline — Retrieval-Augmented Generation per Lettere dal Fronte.

Pipeline:
1. Retrieval ibrido: FTS5 (BM25) + metadata filters (date, luogo, tipo)
2. Reranking: source quality, temporal/geographic compatibility, independence
3. Context builder: contesto strutturato con citazioni esplicite
4. Output validato: Pydantic schema, reject uncited claims

Il modulo non genera testo AI direttamente. Prepara il contesto e valida
l'output. La generazione avviene tramite ai_runtime.get_adapter().
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database import get_conn, DB_PATH
from database_registry import (
    EVENTS_DB_PATH,
    TABLE_SPECS,
    connect_database,
    table_exists,
)

try:
    from source_pipeline.consumer_adapter import retrieve_from_supabase as _supabase_retrieve
    _SUPABASE_AVAILABLE = True
except Exception:
    _SUPABASE_AVAILABLE = False

log = logging.getLogger("rag_pipeline")


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    chunk_id: str
    source_table: str
    source_id: int
    title: str
    text: str
    score: float
    retrieval_method: str  # "fts" | "metadata" | "semantic"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_table": self.source_table,
            "source_id": self.source_id,
            "title": self.title,
            "text": self.text,
            "score": self.score,
            "retrieval_method": self.retrieval_method,
            "metadata": self.metadata,
        }


@dataclass
class RerankedChunk:
    chunk: RetrievedChunk
    reranked_score: float
    rerank_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.chunk.to_dict(),
            "reranked_score": self.reranked_score,
            "rerank_reasons": self.rerank_reasons,
        }


@dataclass
class RAGContext:
    system_prompt: str
    user_context: str
    chunks: List[RerankedChunk]
    citations: List[Dict[str, Any]]
    token_estimate: int
    truncated: bool
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "user_context": self.user_context,
            "chunks": [c.to_dict() for c in self.chunks],
            "citations": self.citations,
            "token_estimate": self.token_estimate,
            "truncated": self.truncated,
            "warnings": self.warnings,
        }


# ─── 1. Retrieval ────────────────────────────────────────────────────────────

def _fts_search(conn: sqlite3.Connection, table: str, query: str, limit: int = 20) -> List[RetrievedChunk]:
    """FTS5 search on a table if FTS index exists."""
    fts_table = f"idx_{table}_fts"
    if not table_exists(conn, fts_table):
        return []

    # Normalize query for FTS5
    tokens = re.findall(r"\w{2,}", query)
    fts_query = " ".join(t + "*" for t in tokens)
    if not fts_query:
        return []

    try:
        rows = conn.execute(
            f"SELECT * FROM {fts_table} WHERE {fts_table} MATCH ? ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    chunks = []
    for row in rows:
        d = dict(row)
        chunk = RetrievedChunk(
            chunk_id=f"{table}:{d.get('rowid', d.get('id', '?'))}",
            source_table=table,
            source_id=d.get("rowid", d.get("id", 0)),
            title=d.get("title", d.get("titolo", d.get("valore", ""))),
            text=d.get("content", d.get("text", d.get("descrizione", ""))),
            score=1.0,  # FTS5 rank is negative; we normalize later
            retrieval_method="fts",
            metadata=d,
        )
        chunks.append(chunk)
    return chunks


def _metadata_search(
    conn: sqlite3.Connection,
    table: str,
    *,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    place: Optional[str] = None,
    limit: int = 20,
) -> List[RetrievedChunk]:
    """Metadata-filtered search on a table."""
    if not table_exists(conn, table):
        return []

    spec = TABLE_SPECS.get(table)
    if not spec:
        return []

    conditions = []
    params = []

    if date_start and spec.date_fields:
        date_field = spec.date_fields[0]
        conditions.append(f'("{date_field}" IS NOT NULL AND "{date_field}" >= ?)')
        params.append(date_start)

    if date_end and spec.date_fields:
        date_field = spec.date_fields[-1]
        conditions.append(f'("{date_field}" IS NOT NULL AND "{date_field}" <= ?)')
        params.append(date_end)

    if place and spec.place_fields:
        place_conditions = " OR ".join(f'"{f}" LIKE ?' for f in spec.place_fields)
        conditions.append(f"({place_conditions})")
        params.extend(f"%{place}%" for _ in spec.place_fields)

    if not conditions:
        return []

    where_clause = " AND ".join(conditions)
    sql = f'SELECT * FROM "{table}" WHERE {where_clause} LIMIT ?'
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        log.warning("metadata_search error on %s: %s", table, e)
        return []

    chunks = []
    for row in rows:
        d = dict(row)
        label_parts = [str(d.get(f, "")) for f in spec.label_fields if d.get(f)]
        title = " ".join(label_parts).strip() or f"{table}#{d.get('id', '?')}"
        desc_parts = [str(d.get(f, "")) for f in spec.description_fields if d.get(f)]
        text = "; ".join(desc_parts)
        chunks.append(RetrievedChunk(
            chunk_id=f"{table}:{d.get('id', '?')}",
            source_table=table,
            source_id=d.get("id", 0),
            title=title,
            text=text,
            score=0.5,
            retrieval_method="metadata",
            metadata=d,
        ))
    return chunks


def retrieve(
    query: str,
    *,
    entity_type: str = "generic",
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    place: Optional[str] = None,
    limit: int = 30,
) -> List[RetrievedChunk]:
    """Hybrid retrieval: FTS5 + metadata filters across multiple tables."""
    chunks: List[RetrievedChunk] = []

    # Determine which tables to search based on entity_type
    if entity_type == "person":
        tables = ["internati", "caduti_albooro", "decorati", "menzioni"]
    elif entity_type == "event":
        tables = ["eventi_1gm"]
    elif entity_type == "source":
        tables = ["fonti_indice", "archivio_documenti", "fondi_archivistici"]
    else:
        tables = ["internati", "fonti_indice", "archivio_documenti", "menzioni", "fondi_archivistici"]

    # FTS search on main DB
    conn = connect_database("main", read_only=True)
    try:
        for table in tables:
            if table == "eventi_1gm":
                continue
            chunks.extend(_fts_search(conn, table, query, limit=limit // len(tables) + 1))
            chunks.extend(_metadata_search(conn, table, date_start=date_start, date_end=date_end, place=place, limit=limit // len(tables) + 1))
    finally:
        conn.close()

    # Search events DB
    if EVENTS_DB_PATH.exists():
        conn_ev = connect_database("events", read_only=True)
        try:
            if table_exists(conn_ev, "eventi_1gm"):
                # Simple LIKE search on events
                rows = conn_ev.execute(
                    "SELECT * FROM eventi_1gm WHERE nome LIKE ? OR descrizione LIKE ? OR aliases LIKE ? OR keywords LIKE ? LIMIT ?",
                    (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit),
                ).fetchall()
                for row in rows:
                    d = dict(row)
                    chunks.append(RetrievedChunk(
                        chunk_id=f"eventi_1gm:{d['id']}",
                        source_table="eventi_1gm",
                        source_id=d["id"],
                        title=d["nome"],
                        text=d.get("descrizione", ""),
                        score=0.7,
                        retrieval_method="fts",
                        metadata=d,
                    ))
        finally:
            conn_ev.close()

    # Deduplicate by chunk_id
    seen = set()
    unique = []
    for c in chunks:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            unique.append(c)

    # Supabase canonical schema retrieval (additional source)
    if _SUPABASE_AVAILABLE:
        try:
            sb_chunks = _supabase_retrieve(query, limit=limit // 3)
            for sc in sb_chunks:
                cid = sc.get("chunk_id", "")
                if cid and cid not in seen:
                    seen.add(cid)
                    unique.append(RetrievedChunk(
                        chunk_id=cid,
                        source_table=sc.get("source_table", "supabase"),
                        source_id=sc.get("source_id", 0),
                        title=sc.get("title", ""),
                        text=sc.get("text", ""),
                        score=sc.get("score", 0.6),
                        retrieval_method=sc.get("retrieval_method", "supabase"),
                        metadata=sc.get("metadata", {}),
                    ))
        except Exception as e:
            log.warning("Supabase retrieval failed: %s", e)

    # Semantic retrieval via embeddings (optional, falls back gracefully)
    try:
        from embeddings_pipeline import semantic_search as _semantic_search
        sem_results = _semantic_search(query, limit=limit // 3, threshold=0.25)
        for sr in sem_results:
            cid = f"{sr['source_table']}:{sr['source_id']}"
            if cid not in seen:
                seen.add(cid)
                unique.append(RetrievedChunk(
                    chunk_id=cid,
                    source_table=sr["source_table"],
                    source_id=sr["source_id"],
                    title=sr["chunk_text"][:80],
                    text=sr["chunk_text"],
                    score=sr["score"],
                    retrieval_method="semantic",
                    metadata={},
                ))
    except Exception as e:
        log.debug("Semantic retrieval skipped: %s", e)

    return unique[:limit]


# ─── 2. Reranking ────────────────────────────────────────────────────────────

def rerank(chunks: List[RetrievedChunk], *, query: str, event_context: Optional[Dict] = None) -> List[RerankedChunk]:
    """Rerank chunks by source quality, temporal/geographic compatibility, independence."""
    reranked = []
    query_lower = query.lower()

    for chunk in chunks:
        score = chunk.score
        reasons = []

        # Boost: title match
        if query_lower in chunk.title.lower():
            score += 0.2
            reasons.append("title_match")

        # Boost: text match
        if query_lower in chunk.text.lower():
            score += 0.1
            reasons.append("text_match")

        # Boost: source quality (archival > database > web)
        source_table = chunk.source_table
        if source_table in ("fonti_indice", "archivio_fonti", "fondi_archivistici"):
            score += 0.15
            reasons.append("archival_source")
        elif source_table in ("archivio_documenti", "lettere_personali"):
            score += 0.2
            reasons.append("primary_document")
        elif source_table in ("menzioni",):
            score += 0.1
            reasons.append("mention_record")

        # Temporal compatibility
        if event_context and event_context.get("date_start"):
            event_start = event_context["date_start"][:4] if event_context.get("date_start") else ""
            chunk_dates = []
            for k, v in chunk.metadata.items():
                if "data" in k.lower() or "date" in k.lower() or "anno" in k.lower():
                    if v and str(v)[:4].isdigit():
                        chunk_dates.append(str(v)[:4])
            if chunk_dates:
                if any(event_start == d for d in chunk_dates):
                    score += 0.15
                    reasons.append("temporal_match")
                elif any(abs(int(event_start) - int(d)) <= 1 for d in chunk_dates if d.isdigit()):
                    score += 0.08
                    reasons.append("temporal_close")

        # Geographic compatibility
        if event_context and event_context.get("luogo"):
            event_place = event_context["luogo"].lower()
            chunk_places = []
            for k, v in chunk.metadata.items():
                if "luogo" in k.lower() or "place" in k.lower() or "location" in k.lower():
                    if v:
                        chunk_places.append(str(v).lower())
            if any(event_place in p or p in event_place for p in chunk_places):
                score += 0.12
                reasons.append("geographic_match")

        # Cap at 1.0
        score = min(score, 1.0)
        reranked.append(RerankedChunk(chunk=chunk, reranked_score=score, rerank_reasons=reasons))

    # Sort by reranked score descending
    reranked.sort(key=lambda x: x.reranked_score, reverse=True)
    return reranked


# ─── 3. Context builder ──────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """Sei un assistente storico specializzato in conflitti del XX secolo (WWI e WWII).
Rispondi ESCLUSIVAMENTE in base alle fonti fornite nel contesto.
Non usare conoscenza generale non esplicitamente attestata nelle fonti.

Regole:
1. Ogni affermazione fattuale deve avere una citazione nel formato [fonte: table#id]
2. Se le fonti sono insufficienti, dichiara "Evidenze insufficienti" e spiega cosa manca
3. Se le fonti sono contraddittorie, presenta entrambe le versioni senza scegliere
4. Non inventare date, luoghi, nomi o numeri
5. Distingui tra fatti confermati (più fonti indipendenti) e fatti attestati da una sola fonte
6. Le "claim" devono essere atomiche: un soggetto, un predicato, un oggetto
7. Lo stato epistemico deve essere: confirmed, probable, candidate, to_review, conflicting, unverifiable
"""


def build_context(
    chunks: List[RerankedChunk],
    *,
    query: str,
    max_tokens: int = 6000,
    entity_type: str = "generic",
) -> RAGContext:
    """Build structured context with explicit citations for AI generation."""
    citations = []
    context_parts = []
    token_estimate = 0
    truncated = False
    warnings = []

    # System prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE
    token_estimate += len(system_prompt) // 4

    for i, rc in enumerate(chunks):
        c = rc.chunk
        citation = {
            "index": i + 1,
            "source_table": c.source_table,
            "source_id": c.source_id,
            "title": c.title,
            "score": round(rc.reranked_score, 3),
            "reasons": rc.rerank_reasons,
        }
        citations.append(citation)

        # Format chunk text
        chunk_text = f"[fonte: {c.source_table}#{c.source_id}] {c.title}\n{c.text}\n"
        chunk_tokens = len(chunk_text) // 4

        if token_estimate + chunk_tokens > max_tokens:
            truncated = True
            warnings.append(f"Contesto troncato a {i} fonti per limite token ({max_tokens})")
            break

        context_parts.append(chunk_text)
        token_estimate += chunk_tokens

    user_context = "\n---\n".join(context_parts)
    if not user_context:
        user_context = "Nessuna fonte trovata per la query."
        warnings.append("Nessuna fonte recuperata — output sarà limitato")

    return RAGContext(
        system_prompt=system_prompt,
        user_context=user_context,
        chunks=chunks[:len(citations)],
        citations=citations,
        token_estimate=token_estimate,
        truncated=truncated,
        warnings=warnings,
    )


# ─── 4. Output validation ────────────────────────────────────────────────────

def validate_ai_output(text: str, citations: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate AI output for uncited claims.

    Returns (is_valid, issues).
    """
    issues = []

    # Check for citation references in text
    citation_pattern = re.compile(r"\[fonte:\s*\w+#\d+\]", re.IGNORECASE)
    found_citations = citation_pattern.findall(text)

    if not found_citations and len(text) > 100:
        issues.append("Output senza citazioni: nessun riferimento [fonte: table#id] trovato")

    # Check for hallucination indicators
    hallucination_patterns = [
        (r"secondo (la storiografia|gli storici)", "Frase generica non attribuita a fonte specifica"),
        (r"come è noto", "Frase generica non attribuita a fonte specifica"),
        (r"probabilmente.{0,30}(morto|catturato|ferito)", "Speculazione non supportata da citazione"),
    ]
    for pattern, message in hallucination_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(f"Potenziale allucinazione: {message}")

    # Check for "Evidenze insufficienti" declaration when no citations
    if not found_citations and "evidenze insufficienti" not in text.lower():
        if len(text) > 200:
            issues.append("Output lungo senza citazioni né dichiarazione di evidenze insufficienti")

    return len(issues) == 0, issues


# ─── Full pipeline ───────────────────────────────────────────────────────────

def run_rag(
    query: str,
    *,
    entity_type: str = "generic",
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    place: Optional[str] = None,
    event_context: Optional[Dict] = None,
    max_chunks: int = 20,
    max_tokens: int = 6000,
) -> RAGContext:
    """Full RAG pipeline: retrieve -> rerank -> build context."""
    chunks = retrieve(
        query,
        entity_type=entity_type,
        date_start=date_start,
        date_end=date_end,
        place=place,
        limit=max_chunks,
    )
    reranked = rerank(chunks, query=query, event_context=event_context)
    context = build_context(reranked, query=query, max_tokens=max_tokens, entity_type=entity_type)
    return context
