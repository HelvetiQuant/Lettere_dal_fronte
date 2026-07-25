"""Endpoint del confronto strutturato delle fonti (Punti di vista)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from viewpoints_service import compare_viewpoints


router = APIRouter(prefix="/api/viewpoints", tags=["punti-di-vista"])


class ViewpointsRequest(BaseModel):
    query: str = Field(min_length=3, max_length=300)
    use_ai: bool = False


@router.post("/create")
def create_viewpoints(body: ViewpointsRequest):
    try:
        return compare_viewpoints(body.query, use_ai=body.use_ai)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Errore analisi viewpoints: {exc}") from exc
