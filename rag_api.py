"""API per RAG pipeline."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from rag_pipeline import run_rag, validate_ai_output

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/retrieve")
def rag_retrieve(
    q: str = Query(..., min_length=2, max_length=300),
    entity_type: str = Query("generic"),
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    place: Optional[str] = None,
    max_chunks: int = Query(20, ge=1, le=100),
    max_tokens: int = Query(6000, ge=500, le=32000),
):
    """Run RAG pipeline: retrieve -> rerank -> build context."""
    ctx = run_rag(
        q,
        entity_type=entity_type,
        date_start=date_start,
        date_end=date_end,
        place=place,
        max_chunks=max_chunks,
        max_tokens=max_tokens,
    )
    return ctx.to_dict()


@router.post("/validate")
def rag_validate(body: Dict[str, Any]):
    """Validate AI output for uncited claims."""
    text = body.get("text", "")
    citations = body.get("citations", [])
    is_valid, issues = validate_ai_output(text, citations)
    return {"valid": is_valid, "issues": issues}
