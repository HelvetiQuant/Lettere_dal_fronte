"""API endpoints for ReportConversationProvider.

Endpoints:
- POST /research/reports/{report_id}/conversations — create conversation bound to snapshot
- POST /research/conversations/{conversation_id}/messages — send message
- GET  /research/conversations/{conversation_id} — retrieve conversation
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from report_conversation_provider import ReportConversationProvider

log = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research-conversation"])

# Singleton provider
_provider: Optional[ReportConversationProvider] = None


def _get_provider() -> ReportConversationProvider:
    global _provider
    if _provider is None:
        _provider = ReportConversationProvider()
    return _provider


# ── Request/Response models ──

class CreateConversationRequest(BaseModel):
    snapshot: Dict[str, Any] = Field(..., description="EvidenceSnapshotV4 dict")


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
    snapshot: Dict[str, Any] = Field(..., description="EvidenceSnapshotV4 dict (same version)")


class SendMessageResponse(BaseModel):
    role: str
    content: str
    validation_state: str
    cited_claim_ids: list = []
    cited_source_ids: list = []


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
            }
            for m in conv.messages
        ],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )
