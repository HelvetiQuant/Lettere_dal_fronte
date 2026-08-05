"""V7 Provider Adapters — bridge existing providers into ProviderObservation contract.

Each adapter wraps an existing provider (web_search, local_db, federation)
and produces normalized ProviderObservation records that the V7 orchestrator
can process uniformly.

Adapters:
  - WebSearchAdapter: wraps web_search_providers (Tavily, Brave, Serper, SerpApi)
  - LocalDbAdapter: wraps SQLite database queries
  - FederationAdapter: wraps source_providers.federation (27 archive providers)

All adapters implement the same interface:
  def search(plan: SemanticQueryPlan) -> List[ProviderObservation]
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import List, Optional, Dict, Any

from provider_observation import ProviderObservation, ProviderCapabilityRegistry
from semantic_query_plan import SemanticQueryPlan

log = logging.getLogger(__name__)


# ─── Base adapter interface ──────────────────────────────────────────────────

class BaseProviderAdapter:
    """Base class for V7 provider adapters."""

    provider_name: str = ""
    capability: str = ""

    def search(self, plan: SemanticQueryPlan) -> List[ProviderObservation]:
        """Execute search according to the plan and return observations."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this adapter's provider is available."""
        return False


# ─── Web Search Adapter ─────────────────────────────────────────────────────

class WebSearchAdapter(BaseProviderAdapter):
    """Adapter for web search providers (Tavily, Brave, Serper, SerpApi).

    Wraps web_search_providers.py and produces ProviderObservation records
    with classification=SEARCH_RESULT or MODEL_LEAD.
    """

    def __init__(self, provider_name: str = "tavily"):
        self.provider_name = provider_name
        self.capability = "DISCOVERY_WEB"

    def is_available(self) -> bool:
        from web_search_providers import available_providers
        return self.provider_name in available_providers()

    def search(self, plan: SemanticQueryPlan) -> List[ProviderObservation]:
        from web_search_providers import (
            search_tavily, search_brave, search_serper, search_serpapi,
        )

        query = self._build_query(plan)
        max_results = 20
        timeout = 30

        routes = plan.get_providers_for_capability("DISCOVERY_WEB")
        for r in routes:
            if r.provider_name == self.provider_name:
                max_results = r.max_results
                timeout = r.timeout_ms // 1000
                break

        search_fn = {
            "tavily": search_tavily,
            "brave": search_brave,
            "serper": search_serper,
            "serpapi": search_serpapi,
        }.get(self.provider_name)

        if not search_fn:
            log.warning(f"Unknown web search provider: {self.provider_name}")
            return []

        t0 = time.time()
        try:
            resp = search_fn(query, max_results=max_results, timeout=timeout)
        except Exception as e:
            log.error(f"Web search {self.provider_name} failed: {e}")
            return []

        if not resp.ok:
            log.debug(f"Web search {self.provider_name} returned no results: {resp.error}")
            return []

        observations = []
        for i, result in enumerate(resp.results):
            obs = ProviderObservation(
                provider=self.provider_name,
                capability=self.capability,
                provider_result_id=f"{self.provider_name}_{i}",
                provider_query_id=query[:100],
                title=result.title,
                url_raw=result.url,
                url_canonical=result.url,
                snippet=result.snippet,
                content_state="NOT_OPENED",
                classification="SEARCH_RESULT",
                provider_score=result.score,
                provider_metadata={
                    "elapsed_ms": resp.elapsed_ms,
                    "query": query,
                },
            )
            observations.append(obs)

        log.info(f"WebSearchAdapter[{self.provider_name}]: {len(observations)} observations in {time.time()-t0:.2f}s")
        return observations

    def _build_query(self, plan: SemanticQueryPlan) -> str:
        """Build a search query string from the plan target."""
        target = plan.target
        parts = []

        if target.display_name:
            parts.append(target.display_name)

        if plan.intent == "PERSON_LOOKUP":
            parsed = target.parsed_fields
            if parsed.get("cognome"):
                parts.append(parsed["cognome"])
            if parsed.get("nome"):
                parts.append(parsed["nome"])
            if parsed.get("anno_nascita"):
                parts.append(f"nato {parsed['anno_nascita']}")
            if parsed.get("luogo_nascita"):
                parts.append(parsed["luogo_nascita"])
            if target.conflict == "WWII" or target.conflict == "AXIS_ONLY":
                parts.append("internato militare")
            elif target.conflict == "WWI" or target.conflict == "ITALIAN_ONLY":
                parts.append("prima guerra mondiale")
        elif plan.intent == "EVENT_LOOKUP":
            parts.append("prima guerra mondiale")
            if target.parsed_fields.get("event_name"):
                parts.append(target.parsed_fields["event_name"])

        return " ".join(parts) if parts else target.display_name


# ─── Local DB Adapter ───────────────────────────────────────────────────────

class LocalDbAdapter(BaseProviderAdapter):
    """Adapter for local SQLite database queries.

    Queries internati, caduti_albooro, decorati_nastroazzurro, caduti_cwgc,
    caduti_ministero, fonti_indice, archivio_documenti based on plan intent.
    """

    def __init__(self):
        self.provider_name = "local_db"
        self.capability = "ARCHIVE_SEARCH"

    def is_available(self) -> bool:
        return True  # always available

    def search(self, plan: SemanticQueryPlan) -> List[ProviderObservation]:
        from database import get_conn

        observations = []
        query = plan.target.display_name
        parts = query.split()
        cognome = parts[0] if parts else query
        nome = " ".join(parts[1:]) if len(parts) > 1 else ""

        try:
            conn = get_conn()

            if plan.intent == "PERSON_LOOKUP":
                tables = [
                    ("internati", "cognome", "nome"),
                    ("caduti_albooro", "nominativo", ""),
                    ("decorati_nastroazzurro", "cognome", "nome"),
                    ("caduti_cwgc", "cognome", "nome"),
                    ("caduti_ministero", "cognome", "nome"),
                ]
                for table, name_col, nome_col in tables:
                    try:
                        if name_col == "nominativo":
                            # V7.2: exact full-name match for nominativo tables
                            sql_full = f"SELECT * FROM {table} WHERE nominativo = ? LIMIT 20"
                            rows_full = conn.execute(sql_full, (query,)).fetchall()
                            # Surname-only matches (different nome)
                            sql_surname = f"SELECT * FROM {table} WHERE nominativo LIKE ? AND nominativo != ? LIMIT 20"
                            rows_surname = conn.execute(sql_surname, (f"{cognome}%", query)).fetchall()
                        else:
                            # V7.2: exact cognome + exact nome match
                            if nome_col and nome:
                                sql_full = f"SELECT * FROM {table} WHERE {name_col} = ? AND {nome_col} = ? LIMIT 20"
                                rows_full = conn.execute(sql_full, (cognome, nome)).fetchall()
                                # Surname-only matches (cognome matches but nome differs)
                                sql_surname = f"SELECT * FROM {table} WHERE {name_col} = ? AND ({nome_col} != ? OR {nome_col} = '' OR {nome_col} IS NULL) LIMIT 20"
                                rows_surname = conn.execute(sql_surname, (cognome, nome)).fetchall()
                            else:
                                # No nome column or no nome provided — all surname matches
                                sql_full = f"SELECT * FROM {table} WHERE {name_col} = ? LIMIT 20"
                                rows_full = conn.execute(sql_full, (cognome,)).fetchall()
                                rows_surname = []

                        # Add full-name matches as SOURCE_CANDIDATE
                        for i, r in enumerate(rows_full):
                            r = dict(r)
                            label = r.get("nominativo") or f"{r.get('cognome','')} {r.get('nome','')}"
                            obs = ProviderObservation(
                                provider=self.provider_name,
                                capability=self.capability,
                                provider_result_id=f"{table}_{r.get('id', i)}",
                                provider_query_id=query[:100],
                                title=label,
                                url_canonical="",
                                snippet=str(r)[:500],
                                content_state="METADATA_ONLY",
                                classification="SOURCE_CANDIDATE",
                                provider_score=1.0,
                                provider_metadata={
                                    "table": table,
                                    "id": r.get("id"),
                                    "raw_record": r,
                                },
                            )
                            observations.append(obs)

                        # V7.2: Add surname-only matches as SURNAME_ONLY_NON_CANDIDATE
                        for i, r in enumerate(rows_surname):
                            r = dict(r)
                            label = r.get("nominativo") or f"{r.get('cognome','')} {r.get('nome','')}"
                            obs = ProviderObservation(
                                provider=self.provider_name,
                                capability=self.capability,
                                provider_result_id=f"{table}_surname_{r.get('id', i)}",
                                provider_query_id=query[:100],
                                title=label,
                                url_canonical="",
                                snippet=str(r)[:500],
                                content_state="METADATA_ONLY",
                                classification="SURNAME_ONLY_NON_CANDIDATE",
                                provider_score=0.3,
                                provider_metadata={
                                    "table": table,
                                    "id": r.get("id"),
                                    "raw_record": r,
                                },
                            )
                            observations.append(obs)

                    except Exception as e:
                        log.debug(f"LocalDbAdapter table {table} failed: {e}")
                        continue

            elif plan.intent == "EVENT_LOOKUP":
                try:
                    rows = conn.execute(
                        "SELECT id, nome, descrizione, data_inizio, data_fine, luogo "
                        "FROM eventi_1gm WHERE nome LIKE ? OR descrizione LIKE ? LIMIT 20",
                        (f"%{query}%", f"%{query}%"),
                    ).fetchall()
                    for i, r in enumerate(rows):
                        r = dict(r)
                        obs = ProviderObservation(
                            provider=self.provider_name,
                            capability=self.capability,
                            provider_result_id=f"eventi_1gm_{r.get('id', i)}",
                            provider_query_id=query[:100],
                            title=r.get("nome", ""),
                            url_canonical="",
                            snippet=r.get("descrizione", "")[:500],
                            content_state="METADATA_ONLY",
                            classification="SOURCE_CANDIDATE",
                            provider_score=0.8,
                            provider_metadata={
                                "table": "eventi_1gm",
                                "id": r.get("id"),
                                "raw_record": r,
                            },
                        )
                        observations.append(obs)
                except Exception:
                    pass

            elif plan.intent == "ARCHIVE_SEARCH" or plan.intent == "SOURCE_LOOKUP":
                try:
                    rows = conn.execute(
                        "SELECT rowid, title, description, provider, source_url, place, year_start "
                        "FROM archivio_documenti WHERE title LIKE ? OR description LIKE ? LIMIT 20",
                        (f"%{query}%", f"%{query}%"),
                    ).fetchall()
                    for i, r in enumerate(rows):
                        r = dict(r)
                        obs = ProviderObservation(
                            provider=self.provider_name,
                            capability=self.capability,
                            provider_result_id=f"archivio_doc_{r.get('rowid', i)}",
                            provider_query_id=query[:100],
                            title=r.get("title", ""),
                            url_canonical=r.get("source_url", ""),
                            snippet=r.get("description", "")[:500],
                            content_state="METADATA_ONLY",
                            classification="SEARCH_RESULT",
                            provider_score=0.6,
                            provider_metadata={
                                "table": "archivio_documenti",
                                "rowid": r.get("rowid"),
                                "provider": r.get("provider"),
                                "place": r.get("place"),
                                "year_start": r.get("year_start"),
                            },
                        )
                        observations.append(obs)
                except Exception:
                    pass

            conn.close()
        except Exception as e:
            log.error(f"LocalDbAdapter failed: {e}")

        log.info(f"LocalDbAdapter: {len(observations)} observations")
        return observations


# ─── Federation Adapter ─────────────────────────────────────────────────────

class FederationAdapter(BaseProviderAdapter):
    """Adapter for source_providers.federation (27 archive providers).

    Wraps federated_search and produces ProviderObservation records.
    """

    def __init__(self):
        self.provider_name = "federation"
        self.capability = "ARCHIVE_SEARCH"

    def is_available(self) -> bool:
        try:
            from source_providers.federation import list_providers
            return len(list_providers()) > 0
        except Exception:
            return False

    def search(self, plan: SemanticQueryPlan) -> List[ProviderObservation]:
        from source_providers.federation import federated_search

        query = plan.target.display_name
        observations = []

        try:
            results = federated_search(query)
            if not results:
                return []

            for i, r in enumerate(results):
                obs = ProviderObservation(
                    provider=r.get("provider", "federation"),
                    capability=self.capability,
                    provider_result_id=f"federation_{i}",
                    provider_query_id=query[:100],
                    title=r.get("title", ""),
                    url_canonical=r.get("url", ""),
                    snippet=r.get("snippet", "")[:500],
                    content_state="NOT_OPENED",
                    classification="SEARCH_RESULT",
                    provider_score=float(r.get("score", 0.5)),
                    provider_metadata=r,
                )
                observations.append(obs)
        except Exception as e:
            log.error(f"FederationAdapter failed: {e}")

        log.info(f"FederationAdapter: {len(observations)} observations")
        return observations


# ─── Adapter Registry ───────────────────────────────────────────────────────

class V7AdapterRegistry:
    """Registry of V7 provider adapters.

    The orchestrator queries this registry to find available adapters
    for each capability type.
    """

    def __init__(self, capability_registry: Optional[ProviderCapabilityRegistry] = None):
        self._adapters: Dict[str, BaseProviderAdapter] = {}
        self._capability_registry = capability_registry or ProviderCapabilityRegistry()
        self._register_defaults()

    def _register_defaults(self):
        # Local DB is always available
        self.register(LocalDbAdapter())
        self._capability_registry.set_available("local_db", True)

        # Web search providers
        for name in ("tavily", "brave", "serper", "serpapi"):
            adapter = WebSearchAdapter(name)
            if adapter.is_available():
                self.register(adapter)
                self._capability_registry.set_available(name, True)

        # Federation
        fed = FederationAdapter()
        if fed.is_available():
            self.register(fed)
            self._capability_registry.set_available("federation", True)

    def register(self, adapter: BaseProviderAdapter):
        self._adapters[adapter.provider_name] = adapter

    def get(self, name: str) -> Optional[BaseProviderAdapter]:
        return self._adapters.get(name)

    def get_for_capability(self, capability: str) -> List[BaseProviderAdapter]:
        return [
            a for a in self._adapters.values()
            if a.capability == capability and a.is_available()
        ]

    def get_discovery_adapters(self) -> List[BaseProviderAdapter]:
        return self.get_for_capability("DISCOVERY_WEB")

    def get_archive_adapters(self) -> List[BaseProviderAdapter]:
        return self.get_for_capability("ARCHIVE_SEARCH")

    def all_adapters(self) -> Dict[str, BaseProviderAdapter]:
        return dict(self._adapters)

    def search_all(self, plan: SemanticQueryPlan) -> List[ProviderObservation]:
        """Execute search across all available adapters for the plan's routes.

        This is the main entry point for the DISCOVER stage of the orchestrator.
        """
        all_observations = []

        # Get adapters for each capability in the plan
        discovery_caps = plan.get_providers_for_capability("DISCOVERY_WEB")
        archive_caps = plan.get_providers_for_capability("ARCHIVE_SEARCH")

        # Run archive searches first (local DB is fast and reliable)
        for route in archive_caps:
            adapter = self.get(route.provider_name)
            if adapter and adapter.is_available():
                try:
                    obs = adapter.search(plan)
                    all_observations.extend(obs)
                except Exception as e:
                    log.error(f"Adapter {route.provider_name} failed: {e}")

        # Run web discovery searches
        for route in discovery_caps:
            adapter = self.get(route.provider_name)
            if adapter and adapter.is_available():
                try:
                    obs = adapter.search(plan)
                    all_observations.extend(obs)
                except Exception as e:
                    log.error(f"Adapter {route.provider_name} failed: {e}")

        return all_observations
