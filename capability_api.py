"""API endpoints for provider capability service.

GET  /api/system/capabilities — current snapshot
POST /api/system/capabilities/recheck — re-run probes
"""
from __future__ import annotations

from fastapi import APIRouter

from provider_capability_service import ProviderCapabilityService

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/capabilities")
async def get_capabilities():
    """Get current provider capability snapshot."""
    svc = ProviderCapabilityService.get_instance()
    snapshot = svc.get_or_probe()
    return snapshot.to_dict()


@router.post("/capabilities/recheck")
async def recheck_capabilities():
    """Re-run provider probes with lock."""
    svc = ProviderCapabilityService.get_instance()
    snapshot = svc.recheck()
    return snapshot.to_dict()
