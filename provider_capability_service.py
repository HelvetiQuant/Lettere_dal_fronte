"""Provider Capability Service — startup probe and runtime health check.

Checks provider availability once at backend startup:
- Loads config without printing keys or prefixes
- Checks OpenAI, Mistral/LMStudio, and web search (Tavily) separately
- Uses quota/health endpoint when available
- If provider doesn't expose balance, makes a minimal request to verify auth+model
- Maps errors to distinct states
- Saves capability snapshot with backend_boot_id, timestamp, TTL
- Does not block backend startup if providers are unavailable

States:
- AVAILABLE
- NOT_CONFIGURED
- AUTH_FAILED
- CREDIT_BALANCE_EXHAUSTED
- ORGANIZATION_SPEND_LIMIT
- PROJECT_SPEND_LIMIT
- USAGE_LIMIT
- RATE_LIMITED
- MODEL_UNAVAILABLE
- NETWORK_ERROR
- UNKNOWN_QUOTA
- DISABLED
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class ProviderStatus:
    """Status of a single provider."""
    configured: bool = False
    status: str = "NOT_CONFIGURED"
    usable: bool = False
    credits_remaining: Optional[float] = None  # None = not exposed, NOT zero
    last_error_code: str = ""
    last_checked: str = ""
    model: str = ""


@dataclass
class CapabilitySnapshot:
    """Immutable snapshot of provider capabilities at a point in time."""
    backend_boot_id: str = ""
    checked_at: str = ""
    research_mode: str = "LOCAL_ONLY"
    providers: Dict[str, ProviderStatus] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    notice_required: bool = False
    notice_version: str = ""

    def to_dict(self) -> dict:
        return {
            "backend_boot_id": self.backend_boot_id,
            "checked_at": self.checked_at,
            "research_mode": self.research_mode,
            "providers": {k: asdict(v) for k, v in self.providers.items()},
            "limitations": self.limitations,
            "notice_required": self.notice_required,
            "notice_version": self.notice_version,
        }

    def compute_notice_version(self) -> str:
        raw = f"{self.research_mode}|{self.research_mode}|"
        for k in sorted(self.providers.keys()):
            p = self.providers[k]
            raw += f"{k}:{p.status}:{p.usable}|"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


class ProviderCapabilityService:
    """Service that checks provider capabilities at startup and runtime.

    Singleton — created once in lifespan, reused by all requests.
    """

    _instance: Optional["ProviderCapabilityService"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._snapshot: Optional[CapabilitySnapshot] = None
        self._boot_id = hashlib.sha256(
            f"{datetime.now().isoformat()}|{os.getpid()}".encode()
        ).hexdigest()[:12]
        self._recheck_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ProviderCapabilityService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def probe_all(self) -> CapabilitySnapshot:
        """Run probes for all providers. Called once at startup."""
        snapshot = CapabilitySnapshot(
            backend_boot_id=self._boot_id,
            checked_at=datetime.now().isoformat(),
        )

        # ── Probe OpenAI ──
        openai_status = self._probe_openai()
        snapshot.providers["openai"] = openai_status

        # ── Probe Mistral ──
        mistral_status = self._probe_mistral()
        snapshot.providers["mistral"] = mistral_status

        # ── Probe web search (Tavily) ──
        web_status = self._probe_web_search()
        snapshot.providers["web_search"] = web_status

        # ── Determine research mode ──
        openai_ok = openai_status.usable
        mistral_ok = mistral_status.usable
        web_ok = web_status.usable

        if web_ok and openai_ok:
            snapshot.research_mode = "FULL_EXTERNAL"
        elif web_ok and mistral_ok:
            snapshot.research_mode = "WEB_WITH_MISTRAL"
        elif web_ok and not openai_ok and not mistral_ok:
            snapshot.research_mode = "WEB_DETERMINISTIC_REPORT"
        elif not web_ok and (openai_ok or mistral_ok):
            snapshot.research_mode = "LOCAL_WITH_MODEL"
        else:
            snapshot.research_mode = "LOCAL_ONLY"

        # ── Compute limitations ──
        if not web_ok:
            snapshot.limitations.append("NO_LIVE_WEB_SEARCH")
            snapshot.limitations.append("NO_EXTERNAL_CORROBORATION")
        if not openai_ok and not mistral_ok:
            snapshot.limitations.append("NO_AI_GENERATION")
            snapshot.limitations.append("DETERMINISTIC_REPORT_ONLY")
        if not openai_ok and mistral_ok:
            snapshot.limitations.append("OPENAI_UNAVAILABLE")
        if not mistral_ok and openai_ok:
            snapshot.limitations.append("MISTRAL_UNAVAILABLE")

        # ── Notice required? ──
        snapshot.notice_required = bool(snapshot.limitations)
        snapshot.notice_version = snapshot.compute_notice_version()

        self._snapshot = snapshot
        log.info("Provider capability probe complete: mode=%s, notice=%s",
                 snapshot.research_mode, snapshot.notice_required)
        return snapshot

    def recheck(self) -> CapabilitySnapshot:
        """Re-run probes with lock. Called via POST /api/system/capabilities/recheck."""
        with self._recheck_lock:
            return self.probe_all()

    def get_snapshot(self) -> Optional[CapabilitySnapshot]:
        """Get the current capability snapshot."""
        return self._snapshot

    def get_or_probe(self) -> CapabilitySnapshot:
        """Get snapshot, probing if not yet done."""
        if self._snapshot is None:
            return self.probe_all()
        return self._snapshot

    def _probe_openai(self) -> ProviderStatus:
        """Probe OpenAI availability."""
        status = ProviderStatus(last_checked=datetime.now().isoformat())

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key or len(api_key) < 10:
            status.status = "NOT_CONFIGURED"
            return status

        status.configured = True

        try:
            import httpx
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=10,
            )

            if resp.status_code == 200:
                status.status = "AVAILABLE"
                status.usable = True
                status.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            elif resp.status_code == 401:
                status.status = "AUTH_FAILED"
                status.last_error_code = "auth_failed"
            elif resp.status_code == 429:
                body = resp.json().get("error", {})
                code = body.get("code", "")
                if code == "credit_balance_exhausted":
                    status.status = "CREDIT_BALANCE_EXHAUSTED"
                elif code == "organization_spend_limit":
                    status.status = "ORGANIZATION_SPEND_LIMIT"
                elif code == "project_spend_limit":
                    status.status = "PROJECT_SPEND_LIMIT"
                elif code == "usage_limit":
                    status.status = "USAGE_LIMIT"
                else:
                    status.status = "RATE_LIMITED"
                status.last_error_code = code or "rate_limited"
            elif resp.status_code == 404:
                status.status = "MODEL_UNAVAILABLE"
                status.last_error_code = "model_not_found"
            else:
                status.status = "UNKNOWN_QUOTA"
                status.last_error_code = f"http_{resp.status_code}"

        except Exception as e:
            exc_str = str(e).lower()
            if "timeout" in exc_str or "timed out" in exc_str:
                status.status = "RATE_LIMITED"
                status.last_error_code = "timeout"
            elif "connection" in exc_str or "network" in exc_str:
                status.status = "NETWORK_ERROR"
                status.last_error_code = "network"
            else:
                status.status = "UNKNOWN_QUOTA"
                status.last_error_code = "unknown"
            log.warning("OpenAI probe failed: %s", str(e)[:100])

        return status

    def _probe_mistral(self) -> ProviderStatus:
        """Probe Mistral/LMStudio availability."""
        status = ProviderStatus(last_checked=datetime.now().isoformat())

        mistral_key = os.environ.get("MISTRAL_API_KEY", "")
        lmstudio_url = os.environ.get("LM_STUDIO_API_URL", "")

        if not mistral_key and not lmstudio_url:
            status.status = "NOT_CONFIGURED"
            return status

        status.configured = True

        # Try LMStudio first if configured
        if lmstudio_url:
            try:
                import httpx
                resp = httpx.get(f"{lmstudio_url}/v1/models", timeout=5)
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    if models:
                        status.status = "AVAILABLE"
                        status.usable = True
                        status.model = models[0].get("id", "lmstudio-local")
                        return status
            except Exception as e:
                log.warning("LMStudio probe failed: %s", str(e)[:100])

        # Try Mistral API
        if mistral_key:
            try:
                import httpx
                resp = httpx.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {mistral_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    timeout=10,
                )

                if resp.status_code == 200:
                    status.status = "AVAILABLE"
                    status.usable = True
                    status.model = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
                elif resp.status_code == 401:
                    status.status = "AUTH_FAILED"
                    status.last_error_code = "auth_failed"
                elif resp.status_code == 429:
                    status.status = "RATE_LIMITED"
                    status.last_error_code = "rate_limited"
                else:
                    status.status = "UNKNOWN_QUOTA"
                    status.last_error_code = f"http_{resp.status_code}"

            except Exception as e:
                exc_str = str(e).lower()
                if "timeout" in exc_str:
                    status.status = "RATE_LIMITED"
                    status.last_error_code = "timeout"
                elif "connection" in exc_str or "network" in exc_str:
                    status.status = "NETWORK_ERROR"
                    status.last_error_code = "network"
                else:
                    status.status = "UNKNOWN_QUOTA"
                    status.last_error_code = "unknown"
                log.warning("Mistral probe failed: %s", str(e)[:100])

        return status

    def _probe_web_search(self) -> ProviderStatus:
        """Probe web search (Tavily) availability."""
        status = ProviderStatus(last_checked=datetime.now().isoformat())

        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if not tavily_key or len(tavily_key) < 10:
            status.status = "NOT_CONFIGURED"
            return status

        status.configured = True

        try:
            import httpx
            resp = httpx.post(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                json={
                    "api_key": tavily_key,
                    "query": "test",
                    "max_results": 1,
                },
                timeout=10,
            )

            if resp.status_code == 200:
                status.status = "AVAILABLE"
                status.usable = True
            elif resp.status_code == 401:
                status.status = "AUTH_FAILED"
                status.last_error_code = "auth_failed"
            elif resp.status_code == 429:
                status.status = "RATE_LIMITED"
                status.last_error_code = "rate_limited"
            else:
                status.status = "UNKNOWN_QUOTA"
                status.last_error_code = f"http_{resp.status_code}"

        except Exception as e:
            exc_str = str(e).lower()
            if "timeout" in exc_str:
                status.status = "RATE_LIMITED"
                status.last_error_code = "timeout"
            elif "connection" in exc_str or "network" in exc_str:
                status.status = "NETWORK_ERROR"
                status.last_error_code = "network"
            else:
                status.status = "UNKNOWN_QUOTA"
                status.last_error_code = "unknown"
            log.warning("Web search probe failed: %s", str(e)[:100])

        return status
