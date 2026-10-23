"""Circuit breaker for Web Search and external providers.

Prevents cascading failures when a provider enters systemic error state.
After a configurable threshold of consecutive failures, the circuit opens
and subsequent calls are short-circuited with CIRCUIT_OPEN error code.

States:
- CLOSED: normal operation, calls go through
- OPEN: circuit broken, calls short-circuited
- HALF_OPEN: limited retry to test recovery

Error codes:
- RATE_LIMITED: HTTP 429 or provider-specific rate limit
- TIMEOUT: request exceeded timeout
- BUDGET_EXHAUSTED: API budget/quota exhausted
- AUTH_ERROR: authentication failure (401/403)
- CIRCUIT_OPEN: circuit breaker is open
- PROVIDER_ERROR: generic provider error
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class WebSearchErrorCode(str, Enum):
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AUTH_ERROR = "AUTH_ERROR"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    SUCCESS = "SUCCESS"


@dataclass
class CircuitBreaker:
    """Circuit breaker for a single provider (e.g., OpenAI Web Search).

    Configurable thresholds:
    - failure_threshold: consecutive failures before opening
    - recovery_timeout: seconds before transitioning to HALF_OPEN
    - half_open_max_calls: limited calls in HALF_OPEN state
    """
    provider_name: str = "openai_web_search"
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 1

    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_successes: int = 0
    total_failures: int = 0
    last_failure_time: float = 0.0
    last_error_code: str = ""
    half_open_calls: int = 0

    def can_call(self) -> bool:
        """Check if a call is allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                log.info("CircuitBreaker[%s]: OPEN -> HALF_OPEN", self.provider_name)
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False
        return False

    def record_success(self):
        """Record a successful call."""
        self.total_successes += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            log.info("CircuitBreaker[%s]: HALF_OPEN -> CLOSED (recovered)",
                     self.provider_name)
        elif self.state == CircuitState.OPEN:
            self.state = CircuitState.CLOSED

    def record_failure(self, error_code: str = ""):
        """Record a failed call."""
        self.total_failures += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = time.time()
        self.last_error_code = error_code

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            log.warning("CircuitBreaker[%s]: HALF_OPEN -> OPEN (recovery failed: %s)",
                        self.provider_name, error_code)
        elif self.consecutive_failures >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                log.warning("CircuitBreaker[%s]: CLOSED -> OPEN (%d consecutive failures, last=%s)",
                            self.provider_name, self.consecutive_failures, error_code)

    def health_dict(self) -> dict:
        """Return health status for run-level reporting."""
        return {
            "state": self.state.value,
            "successes": self.total_successes,
            "failures": self.total_failures,
            "consecutive_failures": self.consecutive_failures,
            "last_error_code": self.last_error_code,
        }

    def reset(self):
        """Reset circuit breaker to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.half_open_calls = 0
        self.last_error_code = ""


def classify_http_error(status_code: int) -> WebSearchErrorCode:
    """Classify HTTP status code into WebSearchErrorCode."""
    if status_code == 429:
        return WebSearchErrorCode.RATE_LIMITED
    elif status_code in (401, 403):
        return WebSearchErrorCode.AUTH_ERROR
    elif status_code == 408 or status_code >= 500:
        return WebSearchErrorCode.PROVIDER_ERROR
    return WebSearchErrorCode.PROVIDER_ERROR


def classify_exception(exc: Exception) -> WebSearchErrorCode:
    """Classify exception into WebSearchErrorCode."""
    exc_name = type(exc).__name__.lower()
    if "timeout" in exc_name or "timedout" in exc_name:
        return WebSearchErrorCode.TIMEOUT
    if "rate" in exc_name or "429" in str(exc):
        return WebSearchErrorCode.RATE_LIMITED
    if "auth" in exc_name or "401" in str(exc) or "403" in str(exc):
        return WebSearchErrorCode.AUTH_ERROR
    if "budget" in exc_name or "quota" in exc_name or "insufficient_quota" in str(exc):
        return WebSearchErrorCode.BUDGET_EXHAUSTED
    return WebSearchErrorCode.PROVIDER_ERROR
