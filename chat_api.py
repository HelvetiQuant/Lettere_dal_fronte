"""API chat integrata con AI runtime locale (LM Studio) o remoto."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_runtime import get_adapter

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    system_override: Optional[str] = None
    context: Optional[str] = None  # e.g. event report, dossier text
    context_label: Optional[str] = None  # e.g. "Evento: Caporetto"
    max_tokens: int = 2048
    temperature: float = 0.3


class ChatResponse(BaseModel):
    risposta: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    local: bool


SYSTEM_DEFAULT = (
    "Sei un ricercatore storico specializzato negli eventi bellici del Novecento, "
    "in particolare la Prima e Seconda Guerra Mondiale, con focus sul fronte italiano. "
    "Rispondi in italiano con accuratezza storica. "
    "Cita le fonti quando possibile. Se non sei sicuro, dichiara la tua incertezza. "
    "Sii conciso ma preciso. Non inventare dati."
)


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Chat AI generale con contesto opzionale. Usa il runtime locale (LM Studio) se disponibile."""
    adapter = get_adapter()

    system = req.system_override or SYSTEM_DEFAULT
    if req.context:
        label = req.context_label or "Contesto"
        system = f"{system}\n\n=== {label} ===\n{req.context}"

    # Build conversation
    user_parts: List[str] = []
    for h in req.history[-10:]:
        if h.role == "user":
            user_parts.append(f"Utente: {h.content}")
        elif h.role == "assistant":
            user_parts.append(f"Assistente: {h.content}")
    user_parts.append(f"Utente: {req.message}")
    user_text = "\n\n".join(user_parts)

    result = adapter.generate(
        system=system,
        user=user_text,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        task_type="chat",
        timeout=120,
    )

    if not result.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Errore AI ({result.provider}): {result.error}",
        )

    return ChatResponse(
        risposta=result.text,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        local=True,
    )


@router.get("/health")
def chat_health():
    """Check if chat AI is available."""
    adapter = get_adapter()
    h = adapter.health()
    return {
        "available": h.healthy,
        "provider": h.provider,
        "model": h.model,
        "local": h.local,
        "detail": h.detail,
    }
