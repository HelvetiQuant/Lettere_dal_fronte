"""Web Search Providers — adapter per motori di ricerca reali.

Provider supportati:
- Tavily (1000 free calls/month) — https://tavily.com
- Serper (2500 free calls) — https://serper.dev
- Brave Search (2000 free calls/month) — https://brave.com/search/api/

Ogni provider restituisce SearchResult con url, title, snippet.
L'elaborazione AI (Mistral) avviene separatamente in _web_search_enrich.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("web_search_providers")


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    score: float = 0.0


@dataclass
class WebSearchResponse:
    ok: bool
    provider: str = ""
    query: str = ""
    results: List[SearchResult] = field(default_factory=list)
    error: str = ""
    elapsed_ms: int = 0


def _get_key(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        from extractor import _load_env
        env = _load_env()
        val = env.get(name, "")
    return val


# ─── Tavily ──────────────────────────────────────────────────────────────────

def search_tavily(query: str, *, max_results: int = 10, timeout: int = 30) -> WebSearchResponse:
    """Tavily API — AI-optimized web search. 1000 free calls/month."""
    api_key = _get_key("TAVILY_API_KEY")
    if not api_key:
        return WebSearchResponse(ok=False, provider="tavily", query=query, error="TAVILY_API_KEY not set")

    t0 = time.time()
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", []):
            results.append(SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", "")[:500],
                score=float(r.get("score", 0.0)),
            ))
        return WebSearchResponse(
            ok=True, provider="tavily", query=query, results=results,
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    except Exception as e:
        return WebSearchResponse(ok=False, provider="tavily", query=query, error=str(e)[:200],
                                 elapsed_ms=int((time.time() - t0) * 1000))


# ─── Serper ──────────────────────────────────────────────────────────────────

def search_serper(query: str, *, max_results: int = 10, timeout: int = 30) -> WebSearchResponse:
    """Serper.dev — Google Search API. 2500 free calls."""
    api_key = _get_key("SERPER_API_KEY")
    if not api_key:
        return WebSearchResponse(ok=False, provider="serper", query=query, error="SERPER_API_KEY not set")

    t0 = time.time()
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("organic", []):
            results.append(SearchResult(
                url=r.get("link", ""),
                title=r.get("title", ""),
                snippet=r.get("snippet", "")[:500],
                score=1.0 - (len(results) * 0.1),
            ))
        # Also include knowledge graph if present
        kg = data.get("knowledgeGraph", {})
        if kg:
            results.insert(0, SearchResult(
                url=kg.get("website", "") or kg.get("descriptionLink", ""),
                title=kg.get("title", ""),
                snippet=kg.get("description", "")[:500],
                score=1.0,
            ))
        return WebSearchResponse(
            ok=True, provider="serper", query=query, results=results,
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    except Exception as e:
        return WebSearchResponse(ok=False, provider="serper", query=query, error=str(e)[:200],
                                 elapsed_ms=int((time.time() - t0) * 1000))


# ─── Brave Search ────────────────────────────────────────────────────────────

def search_brave(query: str, *, max_results: int = 10, timeout: int = 30) -> WebSearchResponse:
    """Brave Search API — 2000 free calls/month."""
    api_key = _get_key("BRAVE_API_KEY")
    if not api_key:
        return WebSearchResponse(ok=False, provider="brave", query=query, error="BRAVE_API_KEY not set")

    t0 = time.time()
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
            },
            params={"q": query, "count": max_results},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("description", "")[:500],
                score=float(r.get("score", 1.0 - len(results) * 0.1)),
            ))
        return WebSearchResponse(
            ok=True, provider="brave", query=query, results=results,
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    except Exception as e:
        return WebSearchResponse(ok=False, provider="brave", query=query, error=str(e)[:200],
                                 elapsed_ms=int((time.time() - t0) * 1000))


# ─── Orchestrator ────────────────────────────────────────────────────────────

# Tavily = primary (1000 free calls/month)
# Serper = validation only (limited monthly calls, Google results for cross-check)
# Brave = fallback if available

_PRIMARY_PROVIDERS = [
    ("tavily", search_tavily),
    ("brave", search_brave),
]

_VALIDATION_PROVIDERS = [
    ("serper", search_serper),
]


def web_search(query: str, *, max_results: int = 10, timeout: int = 30) -> WebSearchResponse:
    """Primary web search. Tries Tavily first, then Brave.

    Serper is NOT used here — it's reserved for validation only (few monthly calls).
    """
    last_error = ""
    for name, func in _PRIMARY_PROVIDERS:
        resp = func(query, max_results=max_results, timeout=timeout)
        if resp.ok and resp.results:
            log.info("Web search: %s returned %d results in %dms", name, len(resp.results), resp.elapsed_ms)
            return resp
        if resp.error and "not set" not in resp.error.lower():
            last_error = f"{name}: {resp.error}"
            log.warning("Web search %s failed: %s", name, resp.error)
        elif "not set" in resp.error.lower():
            log.debug("Web search %s skipped: %s", name, resp.error)

    return WebSearchResponse(
        ok=False, query=query,
        error=last_error or "No web search provider configured. Set TAVILY_API_KEY or BRAVE_API_KEY",
    )


def web_search_validation(query: str, *, max_results: int = 5, timeout: int = 30) -> WebSearchResponse:
    """Validation search using Serper (Google results). Use sparingly — limited monthly calls.

    Use this for cross-validation when primary search results need confirmation,
    or when Tavily results are ambiguous and need deeper verification.
    """
    for name, func in _VALIDATION_PROVIDERS:
        resp = func(query, max_results=max_results, timeout=timeout)
        if resp.ok and resp.results:
            log.info("Web search validation: %s returned %d results in %dms", name, len(resp.results), resp.elapsed_ms)
            return resp
        if resp.error and "not set" not in resp.error.lower():
            log.warning("Web search validation %s failed: %s", name, resp.error)

    return WebSearchResponse(
        ok=False, query=query,
        error="Validation provider (Serper) not available or not configured",
    )


def available_providers() -> List[str]:
    """Return list of all providers with API keys configured."""
    all_providers = _PRIMARY_PROVIDERS + _VALIDATION_PROVIDERS
    available = []
    for name, _ in all_providers:
        key_name = f"{name.upper()}_API_KEY"
        if _get_key(key_name):
            available.append(name)
    return available
