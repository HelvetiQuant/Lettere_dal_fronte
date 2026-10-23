"""Endpoint del confronto strutturato delle fonti (Punti di vista).

V1: /api/viewpoints/create — legacy AI provider comparison
V2: /api/viewpoints/v2/create — comparative historical reconstruction (EVENT ONLY)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from viewpoints_service import compare_viewpoints
from viewpoints_service_v2 import compare_viewpoints_v2


router = APIRouter(prefix="/api/viewpoints", tags=["punti-di-vista"])


class ViewpointsRequest(BaseModel):
    query: str = Field(min_length=3, max_length=300)
    use_ai: bool = False


class ViewpointsV2Request(BaseModel):
    event_id: str = Field(min_length=1, max_length=100, description="Event ID from eventi_1gm")
    use_ai: bool = Field(default=False, description="Use AI for narrative generation")
    custom_sources: list[dict] | None = Field(default=None, description="Override source gathering")
    custom_observations: list[dict] | None = Field(default=None, description="Override observation extraction")


@router.post("/create")
def create_viewpoints(body: ViewpointsRequest):
    """V1: Legacy viewpoints — AI provider comparison."""
    try:
        return compare_viewpoints(body.query, use_ai=body.use_ai)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Errore analisi viewpoints: {exc}") from exc


@router.post("/v2/create")
def create_viewpoints_v2(body: ViewpointsV2Request):
    """V2: Comparative Historical Reconstruction — EVENT ONLY.

    Reconstructs an event through the perspectives of different factions.
    Builds independent faction bundles, finds common facts, detects divergences,
    and generates comparative narration.
    """
    try:
        result = compare_viewpoints_v2(
            event_id=body.event_id,
            use_ai=body.use_ai,
            custom_sources=body.custom_sources,
            custom_observations=body.custom_observations,
        )
        if not result.get("ok"):
            raise HTTPException(422, result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Errore viewpoints v2: {exc}") from exc


@router.get("/v2/{event_id}")
def get_viewpoints_v2(event_id: str, use_ai: bool = False):
    """V2: GET endpoint for viewpoint comparison by event ID."""
    try:
        result = compare_viewpoints_v2(event_id=event_id, use_ai=use_ai)
        if not result.get("ok"):
            raise HTTPException(404, result.get("error", "Not found"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Errore viewpoints v2: {exc}") from exc
