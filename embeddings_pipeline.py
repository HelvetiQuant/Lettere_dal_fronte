"""Embeddings pipeline for RAG semantic search.

Generates and stores embeddings for historical text chunks using:
1. Local sentence-transformers model (all-MiniLM-L6-v2) for CPU inference
2. Optional Supabase pgvector for cloud storage and similarity search
3. Fallback to FTS-only when embeddings are unavailable

The embeddings enhance the existing RAG pipeline (rag_pipeline.py) by adding
a semantic retrieval layer alongside FTS5/BM25 and metadata filters.

Usage:
    # Generate embeddings for all archivio_documenti records
    python embeddings_pipeline.py --build

    # Generate for specific table
    python embeddings_pipeline.py --build --table internati

    # Search using embeddings (semantic)
    python embeddings_pipeline.py --search "prigionia Russia"

    # Stats
    python embeddings_pipeline.py --stats
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database import get_conn, DB_PATH
from database_registry import EVENTS_DB_PATH, connect_database, table_exists

log = logging.getLogger("embeddings_pipeline")

EMBED_DIM = 384  # all-MiniLM-L6-v2 dimension
TABLES_TO_EMBED = [
    ("archivio_documenti", ["titolo", "descrizione", "testo_ocr"]),
    ("internati", ["cognome", "nome", "grado", "luogo_cattura", "luogo_internamento"]),
    ("fonti_indice", ["titolo", "descrizione"]),
    ("eventi_1gm", ["nome", "descrizione", "keywords"]),
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS text_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    embedding BLOB,
    embedding_model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    embedding_dim INTEGER NOT NULL DEFAULT 384,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_table, source_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_table ON text_embeddings(source_table);
CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON text_embeddings(text_hash);
"""


@dataclass
class EmbeddingResult:
    source_table: str
    source_id: int
    chunk_text: str
    embedding: Optional[List[float]]
    text_hash: str
    error: Optional[str] = None


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_chunk_text(row: dict, text_cols: List[str]) -> str:
    parts = []
    for col in text_cols:
        val = row.get(col)
        if val and str(val).strip():
            parts.append(str(val).strip())
    return " ".join(parts)[:2000]  # cap at 2000 chars


def _get_model():
    """Load sentence-transformers model (lazy import)."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("Loaded embedding model: all-MiniLM-L6-v2")
        return model
    except ImportError:
        log.warning("sentence-transformers not installed. Install with: pip install sentence-transformers")
        return None
    except Exception as e:
        log.warning("Failed to load embedding model: %s", e)
        return None


def build_embeddings(
    table: Optional[str] = None,
    batch_size: int = 100,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """Generate and store embeddings for text records.

    Args:
        table: Specific table to embed (None = all configured tables)
        batch_size: Number of records per embedding batch
        limit: Max records per table (None = all)

    Returns:
        Dict with stats: {table: count_embedded}
    """
    model = _get_model()
    conn = get_conn()
    _init_schema(conn)

    tables = [(t, cols) for t, cols in TABLES_TO_EMBED if table is None or t == table]
    stats = {}

    for tbl, text_cols in tables:
        use_events_db = tbl == "eventi_1gm"
        if use_events_db:
            db_conn = connect_database("events", read_only=True)
        else:
            db_conn = conn

        try:
            cols_str = ", ".join(text_cols)
            sql = f"SELECT id, {cols_str} FROM {tbl}"
            if limit:
                sql += f" LIMIT {limit}"
            rows = db_conn.execute(sql).fetchall()
        except sqlite3.OperationalError as e:
            log.warning("Table %s not accessible: %s", tbl, e)
            stats[tbl] = 0
            if use_events_db:
                db_conn.close()
            continue

        count = 0
        for row in rows:
            d = dict(row)
            chunk_text = _build_chunk_text(d, text_cols)
            if not chunk_text:
                continue

            text_hash = _hash_text(chunk_text)
            rid = d["id"]

            # Check if already embedded with same hash
            existing = conn.execute(
                "SELECT text_hash FROM text_embeddings WHERE source_table=? AND source_id=?",
                (tbl, rid)
            ).fetchone()
            if existing and existing[0] == text_hash:
                continue  # skip unchanged

            embedding = None
            if model:
                try:
                    emb = model.encode(chunk_text, normalize_embeddings=True)
                    embedding = emb.tolist()
                except Exception as e:
                    log.warning("Embedding failed for %s#%d: %s", tbl, rid, e)

            now = datetime.now().isoformat()
            emb_blob = json.dumps(embedding) if embedding else None

            conn.execute("""
                INSERT OR REPLACE INTO text_embeddings
                (source_table, source_id, chunk_text, text_hash, embedding,
                 embedding_model, embedding_dim, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (tbl, rid, chunk_text, text_hash, emb_blob,
                  "all-MiniLM-L6-v2", EMBED_DIM, now, now))
            count += 1

            if count % batch_size == 0:
                conn.commit()
                log.info("  %s: %d records embedded", tbl, count)

        conn.commit()
        stats[tbl] = count
        if use_events_db:
            db_conn.close()
        log.info("Table %s: %d records embedded (total)", tbl, count)

    conn.close()
    return stats


def semantic_search(
    query: str,
    limit: int = 20,
    threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """Search using embeddings (semantic similarity).

    Args:
        query: Search query text
        limit: Max results
        threshold: Minimum cosine similarity (0-1)

    Returns:
        List of results with source_table, source_id, score, chunk_text
    """
    model = _get_model()
    if not model:
        log.warning("No embedding model available — returning empty results")
        return []

    query_emb = model.encode(query, normalize_embeddings=True)

    conn = get_conn()
    _init_schema(conn)

    results = []
    try:
        rows = conn.execute(
            "SELECT source_table, source_id, chunk_text, embedding "
            "FROM text_embeddings WHERE embedding IS NOT NULL"
        ).fetchall()

        for row in rows:
            d = dict(row)
            try:
                stored_emb = json.loads(d["embedding"])
                # Cosine similarity (both vectors are normalized)
                dot = sum(a * b for a, b in zip(query_emb, stored_emb))
                if dot >= threshold:
                    results.append({
                        "source_table": d["source_table"],
                        "source_id": d["source_id"],
                        "score": round(float(dot), 4),
                        "chunk_text": d["chunk_text"][:200],
                        "retrieval_method": "semantic",
                    })
            except (json.JSONDecodeError, TypeError):
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
    finally:
        conn.close()

    return results[:limit]


def get_stats() -> Dict[str, Any]:
    """Return embedding statistics."""
    conn = get_conn()
    _init_schema(conn)
    try:
        total = conn.execute("SELECT COUNT(*) FROM text_embeddings").fetchone()[0]
        with_embedding = conn.execute(
            "SELECT COUNT(*) FROM text_embeddings WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        by_table = conn.execute(
            "SELECT source_table, COUNT(*) as cnt FROM text_embeddings GROUP BY source_table"
        ).fetchall()
        return {
            "total": total,
            "with_embedding": with_embedding,
            "without_embedding": total - with_embedding,
            "by_table": [{"table": r[0], "count": r[1]} for r in by_table],
            "model": "all-MiniLM-L6-v2",
            "dim": EMBED_DIM,
        }
    finally:
        conn.close()


def hybrid_search(
    query: str,
    limit: int = 20,
    semantic_weight: float = 0.4,
    fts_weight: float = 0.6,
) -> List[Dict[str, Any]]:
    """Hybrid search combining FTS and semantic results.

    Args:
        query: Search query
        limit: Max results
        semantic_weight: Weight for semantic scores (0-1)
        fts_weight: Weight for FTS scores (0-1)

    Returns:
        Merged and re-ranked results
    """
    # FTS results from rag_pipeline
    from rag_pipeline import retrieve
    fts_chunks = retrieve(query, limit=limit)

    # Semantic results
    sem_results = semantic_search(query, limit=limit)

    # Merge
    merged = {}
    for c in fts_chunks:
        key = (c.source_table, c.source_id)
        merged[key] = {
            "source_table": c.source_table,
            "source_id": c.source_id,
            "chunk_text": c.title + " " + c.text,
            "fts_score": c.score,
            "semantic_score": 0.0,
        }

    for s in sem_results:
        key = (s["source_table"], s["source_id"])
        if key in merged:
            merged[key]["semantic_score"] = s["score"]
        else:
            merged[key] = {
                "source_table": s["source_table"],
                "source_id": s["source_id"],
                "chunk_text": s["chunk_text"],
                "fts_score": 0.0,
                "semantic_score": s["score"],
            }

    # Compute hybrid score
    results = []
    for v in merged.values():
        hybrid_score = v["fts_score"] * fts_weight + v["semantic_score"] * semantic_weight
        results.append({
            "source_table": v["source_table"],
            "source_id": v["source_id"],
            "chunk_text": v["chunk_text"][:200],
            "fts_score": round(v["fts_score"], 4),
            "semantic_score": round(v["semantic_score"], 4),
            "hybrid_score": round(hybrid_score, 4),
        })

    results.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return results[:limit]


def main():
    parser = argparse.ArgumentParser(description="Embeddings pipeline for RAG semantic search")
    parser.add_argument("--build", action="store_true", help="Generate embeddings")
    parser.add_argument("--search", type=str, help="Semantic search query")
    parser.add_argument("--hybrid", type=str, help="Hybrid FTS+semantic search")
    parser.add_argument("--stats", action="store_true", help="Show embedding statistics")
    parser.add_argument("--table", type=str, help="Specific table to embed")
    parser.add_argument("--limit", type=int, help="Max records per table")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.stats:
        s = get_stats()
        print(json.dumps(s, indent=2))
    elif args.build:
        stats = build_embeddings(table=args.table, limit=args.limit)
        print(json.dumps(stats, indent=2))
    elif args.search:
        results = semantic_search(args.search, limit=args.limit or 20)
        for r in results:
            print(f"  [{r['score']:.3f}] {r['source_table']}#{r['source_id']}: {r['chunk_text'][:80]}")
    elif args.hybrid:
        results = hybrid_search(args.hybrid, limit=args.limit or 20)
        for r in results:
            print(f"  [hybrid={r['hybrid_score']:.3f} fts={r['fts_score']:.3f} sem={r['semantic_score']:.3f}] "
                  f"{r['source_table']}#{r['source_id']}: {r['chunk_text'][:80]}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
