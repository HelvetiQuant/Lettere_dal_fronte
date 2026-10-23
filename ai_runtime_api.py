"""API per AI runtime health, benchmark e configurazione."""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter

from ai_runtime import get_adapter, reset_adapter, HealthResult, GenerateResult

router = APIRouter(prefix="/api/ai-runtime", tags=["ai-runtime"])


@router.get("/health")
def ai_health():
    """Check AI runtime health — which adapter, model, local/remote."""
    adapter = get_adapter()
    result = adapter.health()
    return {
        "healthy": result.healthy,
        "provider": result.provider,
        "model": result.model,
        "detail": result.detail,
        "local": result.local,
    }


@router.get("/config")
def ai_config():
    """Return current AI runtime configuration (no secrets)."""
    import os
    from pathlib import Path

    env_path = Path(__file__).parent / ".env"
    has_lm_studio = bool(os.environ.get("LM_STUDIO_API_URL", ""))
    local_only = os.environ.get("AI_LOCAL_ONLY", "false").lower() in ("true", "1", "yes")

    # Read YAML config if exists
    config = {}
    yaml_path = Path(__file__).parent / "config" / "ai_runtime.yaml"
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    return {
        "provider": config.get("provider", "unknown"),
        "local_only": local_only,
        "lm_studio_configured": has_lm_studio,
        "generation": config.get("generation", {}),
        "embedding": config.get("embedding", {}),
        "remote_fallback_order": config.get("remote", {}).get("fallback_order", []),
    }


@router.post("/benchmark")
def ai_benchmark():
    """Run a quick benchmark: generate a short response and measure latency."""
    adapter = get_adapter()
    t0 = time.time()
    result = adapter.generate(
        system="You are a test assistant. Reply with exactly: BENCHMARK_OK",
        user="Reply with BENCHMARK_OK",
        max_tokens=20,
        temperature=0.0,
        timeout=30,
    )
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "ok": result.ok,
        "provider": result.provider,
        "model": result.model,
        "latency_ms": latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "text_preview": result.text[:100] if result.ok else "",
        "error": result.error if not result.ok else "",
    }


@router.post("/reset")
def ai_reset():
    """Reset adapter singleton (force re-initialization on next call)."""
    reset_adapter()
    return {"ok": True, "message": "AI runtime adapter reset. Next call will re-initialize."}
