"""AI Runtime Interface — porta di inferenza comune.

Il codice applicativo non chiama direttamente OpenAI, Mistral, ecc.
Chiama questa interfaccia con generate(), generate_structured(), embed(), health().

Adapter intercambiabili:
- lm_studio (OpenAI-compatible endpoint, CPU quantized)
- remote (delega ad ai_client.py per provider remoti)
- deterministic_test (no real AI, for unit tests only)
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("ai_runtime")


@dataclass
class GenerateResult:
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    error: str = ""
    citations: List[Dict] = field(default_factory=list)
    fallback_used: bool = False


@dataclass
class EmbedResult:
    ok: bool
    vector: List[float] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    dimension: int = 0
    error: str = ""


@dataclass
class HealthResult:
    healthy: bool
    provider: str = ""
    model: str = ""
    detail: str = ""
    local: bool = True


class InferenceAdapter(ABC):
    """Interfaccia comune per tutti gli adapter AI."""

    @abstractmethod
    def generate(self, system: str, user: str, *,
                 max_tokens: int = 4096,
                 temperature: float = 0.3,
                 task_type: str = "generic",
                 timeout: int = 120) -> GenerateResult:
        ...

    @abstractmethod
    def generate_structured(self, system: str, user: str, *,
                            max_tokens: int = 4096,
                            temperature: float = 0.3,
                            task_type: str = "generic",
                            timeout: int = 120) -> GenerateResult:
        ...

    @abstractmethod
    def embed(self, text: str, *,
              timeout: int = 30) -> EmbedResult:
        ...

    @abstractmethod
    def health(self) -> HealthResult:
        ...


class LMStudioAdapter(InferenceAdapter):
    """Adapter per LM Studio (OpenAI-compatible endpoint, CPU quantized)."""

    def __init__(self, base_url: str, model_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self._timeout = 120

    def generate(self, system: str, user: str, *,
                 max_tokens: int = 4096, temperature: float = 0.3,
                 task_type: str = "generic", timeout: int = 120) -> GenerateResult:
        import requests
        t0 = time.time()
        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model_id or "local-model",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return GenerateResult(
                ok=True,
                text=text,
                provider="lm_studio",
                model=self.model_id or data.get("model", "unknown"),
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            return GenerateResult(
                ok=False,
                provider="lm_studio",
                model=self.model_id,
                latency_ms=int((time.time() - t0) * 1000),
                error=str(e),
            )

    def generate_structured(self, system: str, user: str, *,
                            max_tokens: int = 4096, temperature: float = 0.3,
                            task_type: str = "generic", timeout: int = 120) -> GenerateResult:
        result = self.generate(system, user, max_tokens=max_tokens,
                               temperature=temperature, task_type=task_type, timeout=timeout)
        if result.ok:
            try:
                import json
                parsed = json.loads(result.text)
                result.text = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                pass
        return result

    def embed(self, text: str, *, timeout: int = 30) -> EmbedResult:
        import requests
        try:
            resp = requests.post(
                f"{self.base_url}/v1/embeddings",
                json={"model": self.model_id, "input": text},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            vec = data.get("data", [{}])[0].get("embedding", [])
            return EmbedResult(
                ok=True,
                vector=vec,
                provider="lm_studio",
                model=self.model_id,
                dimension=len(vec),
            )
        except Exception as e:
            return EmbedResult(ok=False, provider="lm_studio", model=self.model_id, error=str(e))

    def health(self) -> HealthResult:
        import requests
        try:
            resp = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                model_id = models[0].get("id", "") if models else ""
                return HealthResult(healthy=True, provider="lm_studio", model=model_id, local=True)
            return HealthResult(healthy=False, provider="lm_studio", detail=f"HTTP {resp.status_code}", local=True)
        except Exception as e:
            return HealthResult(healthy=False, provider="lm_studio", detail=str(e), local=True)


class RemoteAIAdapter(InferenceAdapter):
    """Adapter che delega ad ai_client.py (provider remoti con fallback)."""

    def __init__(self, local_only: bool = False):
        self.local_only = local_only

    def generate(self, system: str, user: str, *,
                 max_tokens: int = 4096, temperature: float = 0.3,
                 task_type: str = "generic", timeout: int = 120) -> GenerateResult:
        if self.local_only:
            return GenerateResult(ok=False, provider="remote", error="local_only=True, remote providers blocked")
        from ai_client import call_ai
        t0 = time.time()
        result = call_ai(
            task_type=task_type, system=system, user=user,
            max_tokens=max_tokens, temperature=temperature,
        )
        return GenerateResult(
            ok=result.get("ok", False),
            text=result.get("text", ""),
            provider=result.get("provider", ""),
            model=result.get("model", ""),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            latency_ms=int((time.time() - t0) * 1000),
            error=result.get("error", ""),
            citations=result.get("citations", []),
            fallback_used=result.get("fallback_used", False),
        )

    def generate_structured(self, system: str, user: str, *,
                            max_tokens: int = 4096, temperature: float = 0.3,
                            task_type: str = "generic", timeout: int = 120) -> GenerateResult:
        if self.local_only:
            return GenerateResult(ok=False, provider="remote", error="local_only=True, remote providers blocked")
        from ai_client import call_ai_json
        t0 = time.time()
        result = call_ai_json(
            task_type=task_type, system=system, user=user,
            max_tokens=max_tokens, temperature=temperature,
        )
        return GenerateResult(
            ok=result.get("ok", False),
            text=result.get("text", ""),
            provider=result.get("provider", ""),
            model=result.get("model", ""),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            latency_ms=int((time.time() - t0) * 1000),
            error=result.get("error", ""),
        )

    def embed(self, text: str, *, timeout: int = 30) -> EmbedResult:
        return EmbedResult(ok=False, provider="remote", error="Remote embedding not implemented. Use local adapter.")

    def health(self) -> HealthResult:
        if self.local_only:
            return HealthResult(healthy=False, provider="remote", detail="local_only=True", local=False)
        try:
            from ai_client import call_ai
            result = call_ai(task_type="generic", system="Health check", user="Reply with OK", max_tokens=10)
            return HealthResult(
                healthy=result.get("ok", False),
                provider=result.get("provider", "remote"),
                model=result.get("model", ""),
                detail="" if result.get("ok") else result.get("error", ""),
                local=False,
            )
        except Exception as e:
            return HealthResult(healthy=False, provider="remote", detail=str(e), local=False)


class DeterministicTestAdapter(InferenceAdapter):
    """Adapter deterministico per test — non genera dati di produzione."""

    def __init__(self, *, echo: bool = False):
        self.echo = echo

    def generate(self, system: str, user: str, *,
                 max_tokens: int = 4096, temperature: float = 0.3,
                 task_type: str = "generic", timeout: int = 120) -> GenerateResult:
        text = user if self.echo else "DETERMINISTIC_TEST_RESPONSE"
        return GenerateResult(ok=True, text=text, provider="test", model="deterministic-test", local=True)

    def generate_structured(self, system: str, user: str, *,
                            max_tokens: int = 4096, temperature: float = 0.3,
                            task_type: str = "generic", timeout: int = 120) -> GenerateResult:
        import json
        return GenerateResult(
            ok=True, text=json.dumps({"status": "test", "echo": user[:200]}),
            provider="test", model="deterministic-test", local=True,
        )

    def embed(self, text: str, *, timeout: int = 30) -> EmbedResult:
        return EmbedResult(ok=True, vector=[0.0] * 384, provider="test", model="deterministic-test", dimension=384)

    def health(self) -> HealthResult:
        return HealthResult(healthy=True, provider="test", model="deterministic-test", local=True)


# ─── Factory ─────────────────────────────────────────────────────────────────

_adapter: Optional[InferenceAdapter] = None


def get_adapter() -> InferenceAdapter:
    """Ritorna l'adapter attivo (singleton). Inizializza da config/env."""
    global _adapter
    if _adapter is not None:
        return _adapter

    import os
    from extractor import _load_env
    env = _load_env()

    lm_studio_url = env.get("LM_STUDIO_API_URL", "")
    local_only = os.environ.get("AI_LOCAL_ONLY", "false").lower() in ("true", "1", "yes")

    if lm_studio_url:
        _adapter = LMStudioAdapter(base_url=lm_studio_url)
        log.info("AI runtime: LMStudioAdapter (%s)", lm_studio_url)
    elif local_only:
        _adapter = DeterministicTestAdapter()
        log.warning("AI runtime: DeterministicTestAdapter (local_only, no LM Studio URL)")
    else:
        _adapter = RemoteAIAdapter(local_only=False)
        log.info("AI runtime: RemoteAIAdapter (remote providers with fallback)")

    return _adapter


def set_adapter(adapter: InferenceAdapter) -> None:
    """Override adapter (per test)."""
    global _adapter
    _adapter = adapter


def reset_adapter() -> None:
    """Reset singleton (per test)."""
    global _adapter
    _adapter = None
