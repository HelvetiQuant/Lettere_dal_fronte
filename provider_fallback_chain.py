"""Provider Fallback Chain — OpenAI → Mistral → deterministic.

Implements a provider-agnostic resolver for report generation and chat:
1. OpenAI, only if configured and available
2. Mistral/local, if OpenAI is absent, out of credits/quota, in error, or circuit-open
3. Deterministic report, if Mistral also fails or doesn't pass validation

Rules:
- Don't try OpenAI when key is missing or config disables it
- Distinguish AUTH_ERROR, INSUFFICIENT_QUOTA, RATE_LIMIT, TIMEOUT, NETWORK, MODEL_UNAVAILABLE, INVALID_OUTPUT
- For permanent errors or quota: open circuit breaker for the run/TTL
- For transient rate limit: apply retry budget then fallback
- Mistral does not decide identity, probatory state, or source acceptance
- Fallback cannot modify EvidenceSnapshot
- Always log: provider_requested, provider_attempted, provider_used, model_used, fallback_reason, circuit_state, validation_attempts
- UI must show the actually used provider
- Tests must not consume live API: use fake adapters for errors and a separate opt-in live canary
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class ProviderState(Enum):
    AVAILABLE = "AVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTH_FAILED = "AUTH_FAILED"
    CREDIT_BALANCE_EXHAUSTED = "CREDIT_BALANCE_EXHAUSTED"
    ORGANIZATION_SPEND_LIMIT = "ORGANIZATION_SPEND_LIMIT"
    PROJECT_SPEND_LIMIT = "PROJECT_SPEND_LIMIT"
    USAGE_LIMIT = "USAGE_LIMIT"
    RATE_LIMITED = "RATE_LIMITED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_QUOTA = "UNKNOWN_QUOTA"
    DISABLED = "DISABLED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class ErrorType(Enum):
    AUTH_ERROR = "AUTH_ERROR"
    INSUFFICIENT_QUOTA = "INSUFFICIENT_QUOTA"
    ORGANIZATION_SPEND_LIMIT = "ORGANIZATION_SPEND_LIMIT"
    PROJECT_SPEND_LIMIT = "PROJECT_SPEND_LIMIT"
    USAGE_LIMIT = "USAGE_LIMIT"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    UNKNOWN = "UNKNOWN"


PERMANENT_ERRORS = {
    ErrorType.AUTH_ERROR,
    ErrorType.INSUFFICIENT_QUOTA,
    ErrorType.ORGANIZATION_SPEND_LIMIT,
    ErrorType.PROJECT_SPEND_LIMIT,
    ErrorType.USAGE_LIMIT,
}


@dataclass
class CircuitBreaker:
    """Circuit breaker for a provider."""
    provider: str
    state: str = "closed"  # closed | open | half_open
    opened_at: float = 0
    ttl_seconds: float = 300  # 5 minutes default
    error_type: Optional[ErrorType] = None
    error_count: int = 0

    def is_open(self) -> bool:
        if self.state == "open":
            if time.time() - self.opened_at > self.ttl_seconds:
                self.state = "half_open"
                return False
            return True
        return False

    def open(self, error_type: ErrorType, ttl: Optional[float] = None):
        self.state = "open"
        self.opened_at = time.time()
        self.error_type = error_type
        if ttl is not None:
            self.ttl_seconds = ttl
        log.warning(
            "Circuit breaker OPEN for provider %s due to %s (TTL=%ss)",
            self.provider, error_type.value, self.ttl_seconds,
        )

    def close(self):
        self.state = "closed"
        self.error_type = None
        log.info("Circuit breaker CLOSED for provider %s", self.provider)

    def record_error(self, error_type: ErrorType):
        self.error_count += 1
        if error_type in PERMANENT_ERRORS:
            self.open(error_type, ttl=3600)  # 1 hour for permanent errors
        elif error_type == ErrorType.RATE_LIMIT:
            if self.error_count >= 3:
                self.open(error_type, ttl=60)  # 1 minute for rate limit
        elif error_type in (ErrorType.NETWORK, ErrorType.TIMEOUT):
            if self.error_count >= 5:
                self.open(error_type, ttl=30)


@dataclass
class ProviderResult:
    """Result of a provider attempt."""
    provider_requested: str
    provider_attempted: str
    provider_used: str
    model_used: str
    text: str = ""
    fallback_reason: str = ""
    circuit_state: str = "closed"
    validation_attempts: int = 0
    error_type: Optional[str] = None
    error_message: str = ""
    ok: bool = False


def classify_error(exc: Exception) -> ErrorType:
    """Classify an exception into an error type."""
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    if "401" in exc_str or "authentication" in exc_str or "unauthorized" in exc_str:
        return ErrorType.AUTH_ERROR
    if "429" in exc_str:
        if "credit" in exc_str or "quota" in exc_str or "balance" in exc_str:
            return ErrorType.INSUFFICIENT_QUOTA
        if "spend" in exc_str and "org" in exc_str:
            return ErrorType.ORGANIZATION_SPEND_LIMIT
        if "spend" in exc_str and "project" in exc_str:
            return ErrorType.PROJECT_SPEND_LIMIT
        if "usage" in exc_str and "limit" in exc_str:
            return ErrorType.USAGE_LIMIT
        return ErrorType.RATE_LIMIT
    if "timeout" in exc_str or "timed out" in exc_str:
        return ErrorType.TIMEOUT
    if "connection" in exc_str or "network" in exc_str or "dns" in exc_str:
        return ErrorType.NETWORK
    if "model" in exc_str and ("not found" in exc_str or "unavailable" in exc_str):
        return ErrorType.MODEL_UNAVAILABLE
    if "invalid" in exc_str and "output" in exc_str:
        return ErrorType.INVALID_OUTPUT
    return ErrorType.UNKNOWN


class ProviderFallbackChain:
    """Provider-agnostic fallback chain: OpenAI → Mistral → deterministic.

    Usage:
        chain = ProviderFallbackChain()
        result = chain.generate(
            system_prompt=...,
            user_payload=...,
            snapshot_dict=...,
            validator_fn=...,
            deterministic_fn=...,
        )
    """

    def __init__(
        self,
        openai_configured: bool = False,
        mistral_configured: bool = True,
        circuit_ttl: float = 300,
    ):
        self._openai_configured = openai_configured
        self._mistral_configured = mistral_configured
        self._openai_breaker = CircuitBreaker("openai", ttl_seconds=circuit_ttl)
        self._mistral_breaker = CircuitBreaker("mistral", ttl_seconds=circuit_ttl)

    def generate(
        self,
        system_prompt: str,
        user_payload: str,
        snapshot_dict: dict,
        validator_fn: Optional[Callable[[str, dict], Tuple[bool, List[str]]]] = None,
        deterministic_fn: Optional[Callable[[dict], str]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        timeout: int = 60,
    ) -> ProviderResult:
        """Generate text using the fallback chain.

        Args:
            system_prompt: System prompt for the AI
            user_payload: User payload (JSON string)
            snapshot_dict: EvidenceSnapshot dict for validation
            validator_fn: Function(text, snapshot) -> (is_valid, violations)
            deterministic_fn: Function(snapshot) -> str (fallback)
            max_tokens: Max tokens for AI generation
            temperature: Temperature for AI generation
            timeout: Timeout in seconds

        Returns:
            ProviderResult with the generated text and metadata
        """
        provider_requested = "openai" if self._openai_configured else "mistral"

        # ── Try OpenAI first if configured ──
        if self._openai_configured and not self._openai_breaker.is_open():
            result = self._try_openai(
                system_prompt, user_payload, snapshot_dict,
                validator_fn, max_tokens, temperature, timeout,
            )
            if result.ok:
                return result

        # ── Try Mistral ──
        if self._mistral_configured and not self._mistral_breaker.is_open():
            result = self._try_mistral(
                system_prompt, user_payload, snapshot_dict,
                validator_fn, max_tokens, temperature, timeout,
                provider_requested=provider_requested,
            )
            if result.ok:
                return result

        # ── Deterministic fallback ──
        if deterministic_fn:
            text = deterministic_fn(snapshot_dict)
            return ProviderResult(
                provider_requested=provider_requested,
                provider_attempted="mistral" if self._mistral_configured else "openai",
                provider_used="deterministic",
                model_used="none",
                text=text,
                fallback_reason="all_providers_failed_or_unavailable",
                circuit_state=self._circuit_state_summary(),
                validation_attempts=0,
                ok=True,
            )

        return ProviderResult(
            provider_requested=provider_requested,
            provider_attempted="none",
            provider_used="none",
            model_used="none",
            fallback_reason="no_provider_available",
            circuit_state=self._circuit_state_summary(),
            ok=False,
        )

    def _try_openai(
        self,
        system_prompt: str,
        user_payload: str,
        snapshot_dict: dict,
        validator_fn: Optional[Callable],
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> ProviderResult:
        """Try OpenAI generation."""
        try:
            from ai_runtime import get_adapter
            adapter = get_adapter()

            result = adapter.generate(
                system=system_prompt,
                user=user_payload,
                max_tokens=max_tokens,
                temperature=temperature,
                task_type="conversational_report",
                timeout=timeout,
            )

            if not result.ok or not result.text:
                self._openai_breaker.record_error(ErrorType.UNKNOWN)
                return ProviderResult(
                    provider_requested="openai",
                    provider_attempted="openai",
                    provider_used="",
                    model_used="",
                    fallback_reason="openai_generation_failed",
                    circuit_state=self._openai_breaker.state,
                    ok=False,
                )

            # Validate
            if validator_fn:
                is_valid, violations = validator_fn(result.text, snapshot_dict)
                if not is_valid:
                    self._openai_breaker.record_error(ErrorType.INVALID_OUTPUT)
                    return ProviderResult(
                        provider_requested="openai",
                        provider_attempted="openai",
                        provider_used="",
                        model_used=result.model if hasattr(result, "model") else "",
                        fallback_reason=f"validation_failed: {violations[:3]}",
                        circuit_state=self._openai_breaker.state,
                        validation_attempts=1,
                        ok=False,
                    )

            return ProviderResult(
                provider_requested="openai",
                provider_attempted="openai",
                provider_used="openai",
                model_used=result.model if hasattr(result, "model") else "openai",
                text=result.text,
                circuit_state=self._openai_breaker.state,
                ok=True,
            )

        except Exception as e:
            error_type = classify_error(e)
            self._openai_breaker.record_error(error_type)
            log.warning("OpenAI provider failed: %s (%s)", error_type.value, str(e)[:100])
            return ProviderResult(
                provider_requested="openai",
                provider_attempted="openai",
                provider_used="",
                model_used="",
                fallback_reason=f"openai_error: {error_type.value}",
                error_type=error_type.value,
                error_message=str(e)[:200],
                circuit_state=self._openai_breaker.state,
                ok=False,
            )

    def _try_mistral(
        self,
        system_prompt: str,
        user_payload: str,
        snapshot_dict: dict,
        validator_fn: Optional[Callable],
        max_tokens: int,
        temperature: float,
        timeout: int,
        provider_requested: str,
    ) -> ProviderResult:
        """Try Mistral/local generation."""
        try:
            from ai_runtime import get_adapter
            adapter = get_adapter()
            health = adapter.health()

            if not health.healthy:
                self._mistral_breaker.record_error(ErrorType.MODEL_UNAVAILABLE)
                return ProviderResult(
                    provider_requested=provider_requested,
                    provider_attempted="mistral",
                    provider_used="",
                    model_used="",
                    fallback_reason="mistral_unhealthy",
                    circuit_state=self._mistral_breaker.state,
                    ok=False,
                )

            result = adapter.generate(
                system=system_prompt,
                user=user_payload,
                max_tokens=max_tokens,
                temperature=temperature,
                task_type="conversational_report",
                timeout=timeout,
            )

            if not result.ok or not result.text:
                self._mistral_breaker.record_error(ErrorType.UNKNOWN)
                return ProviderResult(
                    provider_requested=provider_requested,
                    provider_attempted="mistral",
                    provider_used="",
                    model_used="",
                    fallback_reason="mistral_generation_failed",
                    circuit_state=self._mistral_breaker.state,
                    ok=False,
                )

            # Validate
            if validator_fn:
                is_valid, violations = validator_fn(result.text, snapshot_dict)
                if not is_valid:
                    self._mistral_breaker.record_error(ErrorType.INVALID_OUTPUT)
                    return ProviderResult(
                        provider_requested=provider_requested,
                        provider_attempted="mistral",
                        provider_used="",
                        model_used=health.model,
                        fallback_reason=f"validation_failed: {violations[:3]}",
                        circuit_state=self._mistral_breaker.state,
                        validation_attempts=1,
                        ok=False,
                    )

            return ProviderResult(
                provider_requested=provider_requested,
                provider_attempted="mistral",
                provider_used="mistral",
                model_used=health.model,
                text=result.text,
                circuit_state=self._mistral_breaker.state,
                ok=True,
            )

        except Exception as e:
            error_type = classify_error(e)
            self._mistral_breaker.record_error(error_type)
            log.warning("Mistral provider failed: %s (%s)", error_type.value, str(e)[:100])
            return ProviderResult(
                provider_requested=provider_requested,
                provider_attempted="mistral",
                provider_used="",
                model_used="",
                fallback_reason=f"mistral_error: {error_type.value}",
                error_type=error_type.value,
                error_message=str(e)[:200],
                circuit_state=self._mistral_breaker.state,
                ok=False,
            )

    def _circuit_state_summary(self) -> str:
        return f"openai={self._openai_breaker.state},mistral={self._mistral_breaker.state}"

    def get_state(self) -> dict:
        """Return current state for API/logging."""
        return {
            "openai": {
                "configured": self._openai_configured,
                "circuit_state": self._openai_breaker.state,
                "error_type": self._openai_breaker.error_type.value if self._openai_breaker.error_type else None,
                "error_count": self._openai_breaker.error_count,
            },
            "mistral": {
                "configured": self._mistral_configured,
                "circuit_state": self._mistral_breaker.state,
                "error_type": self._mistral_breaker.error_type.value if self._mistral_breaker.error_type else None,
                "error_count": self._mistral_breaker.error_count,
            },
        }
