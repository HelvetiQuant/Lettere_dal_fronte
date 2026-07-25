"""API canonica per ricerca, grafo, revisioni e metadati."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from graph_models import (
    EdgeReviewRequest,
    GraphResponse,
)
from graph_service import get_graph, review_edge


router = APIRouter(prefix="/api/graph", tags=["grafo-canonico"])


@router.get("/entity/{source_table}/{source_id}", response_model=GraphResponse)
def graph_entity(
    source_table: str,
    source_id: int,
    max_nodes: int = Query(100, ge=1, le=500),
    max_edges: int = Query(200, ge=1, le=1000),
    include_candidates: bool = True,
    include_rejected: bool = False,
):
    try:
        return get_graph(
            source_table,
            source_id,
            max_nodes=max_nodes,
            max_edges=max_edges,
            include_candidates=include_candidates,
            include_rejected=include_rejected,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/edges/{edge_id:path}/review")
def graph_edge_review(
    edge_id: str,
    body: EdgeReviewRequest,
):
    try:
        return review_edge(edge_id, body, "system")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
