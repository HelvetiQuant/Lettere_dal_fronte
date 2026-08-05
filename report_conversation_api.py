"""API endpoints for ReportConversationProvider V6.

Factory-versioned: uses create_provider_v6() to select the best available provider.
V4 provider is kept as legacy fallback but never used by default.

Endpoints:
- POST /research/reports/{report_id}/conversations — create conversation bound to snapshot
- POST /research/conversations/{conversation_id}/messages — send message
- GET  /research/conversations/{conversation_id} — retrieve conversation
- GET  /research/conversations/{conversation_id}/versions — get provider/schema versions
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from report_conversation_provider_v6 import ReportConversationProviderV6, create_provider_v6

log = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research-conversation"])

# Singleton provider (V6 via factory)
_provider: Optional[ReportConversationProviderV6] = None


def _get_provider() -> ReportConversationProviderV6:
    global _provider
    if _provider is None:
        _provider = create_provider_v6()
        log.info("ReportConversationProviderV6 created: provider=%s model=%s", _provider.provider_name, _provider.model)
    return _provider


# ── Request/Response models ──

class CreateConversationRequest(BaseModel):
    snapshot: Dict[str, Any] = Field(..., description="EvidenceSnapshotV6 dict")


class CreateConversationResponse(BaseModel):
    conversation_id: str
    report_id: str
    snapshot_id: str
    snapshot_hash: str
    provider: str
    model: str
    created_at: str


class SendMessageRequest(BaseModel):
    message: str
    snapshot: Dict[str, Any] = Field(..., description="EvidenceSnapshotV6 dict (same version)")


class SendMessageResponse(BaseModel):
    role: str
    content: str
    validation_state: str
    cited_claim_ids: list = []
    cited_source_ids: list = []
    provider_class: str = ""
    provider_contract_version: str = ""
    snapshot_schema_version: str = ""
    renderer_version: str = ""
    validator_version: str = ""
    requires_new_research: bool = False
    validation_details: Dict[str, Any] = {}


class ConversationResponse(BaseModel):
    conversation_id: str
    report_id: str
    snapshot_id: str
    snapshot_hash: str
    provider: str
    model: str
    messages: list = []
    created_at: str
    updated_at: str


# ── Endpoints ──

@router.post("/reports/{report_id}/conversations")
def create_conversation(report_id: str, req: CreateConversationRequest):
    """Create a new conversation bound to a snapshot version."""
    provider = _get_provider()
    conv = provider.create_conversation(report_id, req.snapshot)
    return CreateConversationResponse(
        conversation_id=conv.conversation_id,
        report_id=conv.report_id,
        snapshot_id=conv.snapshot_id,
        snapshot_hash=conv.snapshot_hash,
        provider=conv.provider,
        model=conv.model,
        created_at=conv.created_at,
    )


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, req: SendMessageRequest):
    """Send a message to an existing conversation."""
    provider = _get_provider()
    conv = provider.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = provider.send_message(conv, req.message, req.snapshot)
    return SendMessageResponse(
        role=msg.role,
        content=msg.content,
        validation_state=msg.validation_state,
        cited_claim_ids=msg.cited_claim_ids,
        cited_source_ids=msg.cited_source_ids,
        provider_class=msg.provider_class,
        provider_contract_version=msg.provider_contract_version,
        snapshot_schema_version=msg.snapshot_schema_version,
        renderer_version=msg.renderer_version,
        validator_version=msg.validator_version,
        requires_new_research=msg.requires_new_research,
        validation_details=msg.validation_details,
    )


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """Retrieve a full conversation with all messages."""
    provider = _get_provider()
    conv = provider.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        conversation_id=conv.conversation_id,
        report_id=conv.report_id,
        snapshot_id=conv.snapshot_id,
        snapshot_hash=conv.snapshot_hash,
        provider=conv.provider,
        model=conv.model,
        messages=[
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "validation_state": m.validation_state,
                "cited_claim_ids": m.cited_claim_ids,
                "cited_source_ids": m.cited_source_ids,
                "provider_class": m.provider_class,
                "provider_contract_version": m.provider_contract_version,
                "snapshot_schema_version": m.snapshot_schema_version,
                "renderer_version": m.renderer_version,
                "validator_version": m.validator_version,
                "requires_new_research": m.requires_new_research,
            }
            for m in conv.messages
        ],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations/{conversation_id}/versions")
def get_versions(conversation_id: str):
    """Get provider and schema versions for a conversation."""
    provider = _get_provider()
    conv = provider.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "provider_class": provider.PROVIDER_CLASS,
        "provider_contract_version": provider.CONTRACT_VERSION,
        "renderer_version": provider.RENDERER_VERSION,
        "validator_version": provider.VALIDATOR_VERSION,
        "snapshot_schema_version": "6",
        "conversation_provider": conv.provider,
        "conversation_model": conv.model,
    }
