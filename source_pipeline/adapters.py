"""
Bridge adapters — wraps existing source_providers/ implementations
to conform to the new source_pipeline.SourceProvider contract.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from source_pipeline import (
    SourceProvider,
    ProviderCapabilities,
    ProviderPolicy,
    SearchResult,
    SearchPage,
    Representation,
    NormalizedItem,
    compute_stable_id,
)
from source_pipeline.registry import load_providers, ProviderConfig
from pathlib import Path

logger = logging.getLogger("source_pipeline.adapters")


def _load_provider_configs() -> Dict[str, ProviderConfig]:
    yaml_path = Path(__file__).parent.parent / "config" / "archive_providers.yml"
    return load_providers(yaml_path)


_PROVIDER_CONFIGS: Optional[Dict[str, ProviderConfig]] = None


def _get_config(code: str) -> ProviderConfig:
    global _PROVIDER_CONFIGS
    if _PROVIDER_CONFIGS is None:
        _PROVIDER_CONFIGS = _load_provider_configs()
    return _PROVIDER_CONFIGS.get(code, ProviderConfig(code=code, display_name=code))


class LegacyBridgeAdapter(SourceProvider):
    """Wraps an existing source_providers/ provider to implement the new contract."""

    def __init__(self, legacy_provider, provider_code: str):
        self._legacy = legacy_provider
        self._code = provider_code
        self._config = _get_config(provider_code)

    @property
    def provider_code(self) -> str:
        return self._code

    def capabilities(self) -> ProviderCapabilities:
        return self._config.to_caps()

    def policy(self) -> ProviderPolicy:
        return self._config.to_policy()

    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        results = []
        try:
            legacy_results = self._legacy.search(query)
            for r in legacy_results:
                results.append(SearchResult(
                    external_id=r.get("provider_record_id", ""),
                    title=r.get("titolo", r.get("title", "")),
                    description=r.get("description", ""),
                    canonical_url=r.get("catalog_url", r.get("direct_url", "")),
                    item_type=r.get("source_type", "document"),
                    date_text=r.get("date_start", ""),
                    language=r.get("language", ""),
                    provider_code=self._code,
                    holding_institution=r.get("archivio", self._config.holding_institution),
                    raw_metadata=r,
                ))
        except Exception as exc:
            logger.error("Search failed for provider %s: %s", self._code, exc)

        return SearchPage(results=results, next_cursor=None, has_more=False)

    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        try:
            data = self._legacy.get_metadata(external_id)
            if not data:
                return None
            return self.normalize(data)
        except Exception as exc:
            logger.error("fetch_metadata failed for %s/%s: %s", self._code, external_id, exc)
            return None

    def fetch_representations(self, external_id: str) -> List[Representation]:
        reps = []
        try:
            data = self._legacy.get_metadata(external_id)
            if data:
                if data.get("direct_url") or data.get("pdf_url"):
                    reps.append(Representation(
                        representation_type="original",
                        mime_type="application/pdf" if data.get("pdf_url") else "text/html",
                        file_url=data.get("pdf_url") or data.get("direct_url", ""),
                        rights_statement=self._config.rights_status,
                    ))
                if data.get("iiif_manifest"):
                    reps.append(Representation(
                        representation_type="iiif",
                        mime_type="application/json",
                        file_url=data.get("iiif_manifest", ""),
                        iiif_manifest=data.get("iiif_manifest", ""),
                    ))
        except Exception as exc:
            logger.error("fetch_representations failed for %s/%s: %s", self._code, external_id, exc)
        return reps

    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        return NormalizedItem(
            provider_code=self._code,
            provider_item_id=payload.get("provider_record_id", payload.get("id", "")),
            holding_institution=payload.get("archivio", self._config.holding_institution),
            title=payload.get("titolo", payload.get("title", "")),
            document_type=payload.get("source_type", "document"),
            date_start=payload.get("date_start", ""),
            language=payload.get("language", ""),
            original_url=payload.get("catalog_url", payload.get("direct_url", "")),
            rights_uri=self._config.license_uri,
            raw_metadata=payload,
        )


class EuropeanaAdapter(SourceProvider):
    """Europeana adapter with real API key support."""

    def __init__(self):
        self._config = _get_config("europeana")
        self._api_key = os.environ.get("EUROPEANA_API_KEY", "api2demo")

    @property
    def provider_code(self) -> str:
        return "europeana"

    def capabilities(self) -> ProviderCapabilities:
        return self._config.to_caps()

    def policy(self) -> ProviderPolicy:
        return self._config.to_policy()

    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        import requests
        url = "https://api.europeana.eu/record/v2/search.json"
        params = {
            "wskey": self._api_key,
            "query": query,
            "rows": 20,
            "profile": "rich",
            "start": int(cursor) + 1 if cursor else 1,
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                logger.error("Europeana search HTTP %d: %s", resp.status_code, resp.text[:200])
                return SearchPage(results=[], has_more=False)

            data = resp.json()
            results = []
            for item in data.get("items", []):
                title = item.get("title", "")
                if isinstance(title, list):
                    title = title[0] if title else ""
                desc = item.get("dcDescription", "")
                if isinstance(desc, list):
                    desc = desc[0] if desc else ""
                preview = item.get("edmPreview", "")
                if isinstance(preview, list):
                    preview = preview[0] if preview else ""
                shown_at = item.get("edmIsShownAt", "")
                if isinstance(shown_at, list):
                    shown_at = shown_at[0] if shown_at else ""

                results.append(SearchResult(
                    external_id=item.get("id", ""),
                    title=title,
                    description=desc,
                    canonical_url=f"https://www.europeana.eu/item/{item.get('id', '')}",
                    item_type=item.get("type", "TEXT"),
                    date_text=str(item.get("year", "")),
                    language=",".join(item.get("language", [])) if isinstance(item.get("language"), list) else str(item.get("language", "")),
                    provider_code="europeana",
                    holding_institution="Europeana",
                    raw_metadata=item,
                ))

            total = int(data.get("totalResults", 0))
            current_start = int(params["start"])
            has_more = current_start + len(results) < total
            next_cursor = str(current_start + len(results) - 1) if has_more else None

            return SearchPage(results=results, next_cursor=next_cursor, total_count=total, has_more=has_more)
        except Exception as exc:
            logger.error("Europeana search error: %s", exc)
            return SearchPage(results=[], has_more=False)

    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        import requests
        url = f"https://api.europeana.eu/record/v2/{external_id}.json"
        params = {"wskey": self._api_key}
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                return None
            data = resp.json()
            obj = data.get("object", data)
            title = obj.get("title", "")
            if isinstance(title, list):
                title = title[0] if title else ""
            return self.normalize({
                "provider_record_id": external_id,
                "titolo": title,
                "catalog_url": f"https://www.europeana.eu/item/{external_id}",
                "source_type": "digitized_document",
                "raw": obj,
            })
        except Exception as exc:
            logger.error("Europeana fetch_metadata error: %s", exc)
            return None

    def fetch_representations(self, external_id: str) -> List[Representation]:
        return []

    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        return NormalizedItem(
            provider_code="europeana",
            provider_item_id=payload.get("provider_record_id", ""),
            holding_institution="Europeana",
            title=payload.get("titolo", ""),
            document_type=payload.get("source_type", "document"),
            original_url=payload.get("catalog_url", ""),
            rights_uri=self._config.license_uri,
            raw_metadata=payload.get("raw", payload),
        )


class ICRCWW1Adapter(SourceProvider):
    """ICRC WW1 Prisoners adapter."""

    def __init__(self):
        self._config = _get_config("icrc_ww1")

    @property
    def provider_code(self) -> str:
        return "icrc_ww1"

    def capabilities(self) -> ProviderCapabilities:
        caps = self._config.to_caps()
        return caps

    def policy(self) -> ProviderPolicy:
        return self._config.to_policy()

    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        from source_providers.icrc_ww1 import ProviderICRCWW1
        legacy = ProviderICRCWW1()
        try:
            legacy_results = legacy.search(query)
            results = []
            for r in legacy_results:
                results.append(SearchResult(
                    external_id=r.get("provider_record_id", ""),
                    title=r.get("titolo", ""),
                    description=r.get("description", ""),
                    canonical_url=r.get("catalog_url", ""),
                    item_type="person_record",
                    provider_code="icrc_ww1",
                    holding_institution="ICRC Archives",
                    raw_metadata=r,
                ))
            return SearchPage(results=results, has_more=False)
        except Exception as exc:
            logger.error("ICRC search error: %s", exc)
            return SearchPage(results=[], has_more=False)

    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        return None

    def fetch_representations(self, external_id: str) -> List[Representation]:
        return []

    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        return NormalizedItem(
            provider_code="icrc_ww1",
            provider_item_id=payload.get("provider_record_id", ""),
            holding_institution="ICRC Archives",
            title=payload.get("titolo", ""),
            document_type="person_record",
            original_url=payload.get("catalog_url", ""),
            raw_metadata=payload,
        )


class LeBIAdapter(SourceProvider):
    """LeBI (Lessico Biografico IMI) adapter."""

    def __init__(self):
        self._config = _get_config("lebi")

    @property
    def provider_code(self) -> str:
        return "lebi"

    def capabilities(self) -> ProviderCapabilities:
        return self._config.to_caps()

    def policy(self) -> ProviderPolicy:
        return self._config.to_policy()

    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        from source_providers.lebi import ProviderLeBI
        legacy = ProviderLeBI()
        try:
            legacy_results = legacy.search(query)
            results = []
            for r in legacy_results:
                results.append(SearchResult(
                    external_id=r.get("provider_record_id", ""),
                    title=r.get("titolo", ""),
                    description=r.get("description", ""),
                    canonical_url=r.get("catalog_url", ""),
                    item_type="person_record",
                    provider_code="lebi",
                    holding_institution="ANRP — Lessico Biografico IMI",
                    raw_metadata=r,
                ))
            return SearchPage(results=results, has_more=False)
        except Exception as exc:
            logger.error("LeBI search error: %s", exc)
            return SearchPage(results=[], has_more=False)

    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        from source_providers.lebi import ProviderLeBI
        legacy = ProviderLeBI()
        try:
            data = legacy.get_metadata(external_id)
            if not data:
                return None
            return self.normalize(data)
        except Exception as exc:
            logger.error("LeBI fetch_metadata error: %s", exc)
            return None

    def fetch_representations(self, external_id: str) -> List[Representation]:
        reps = []
        pdf_url = f"https://www.lessicobiograficoimi.it/showpdf/{external_id}"
        reps.append(Representation(
            representation_type="pdf",
            mime_type="application/pdf",
            file_url=pdf_url,
            rights_statement="METADATA_ONLY",
        ))
        return reps

    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        return NormalizedItem(
            provider_code="lebi",
            provider_item_id=payload.get("provider_record_id", payload.get("id", "")),
            holding_institution="ANRP — Lessico Biografico IMI",
            title=payload.get("titolo", payload.get("nome", "")),
            document_type="person_record",
            original_url=payload.get("catalog_url", ""),
            raw_metadata=payload,
        )


class NARAAdapter(SourceProvider):
    """NARA adapter wrapping existing ProviderNARA."""

    def __init__(self):
        self._config = _get_config("nara")

    @property
    def provider_code(self) -> str:
        return "nara"

    def capabilities(self) -> ProviderCapabilities:
        return self._config.to_caps()

    def policy(self) -> ProviderPolicy:
        return self._config.to_policy()

    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        from source_providers.nara import ProviderNARA
        legacy = ProviderNARA()
        try:
            legacy_results = legacy.search(query)
            results = []
            for r in legacy_results:
                results.append(SearchResult(
                    external_id=r.get("provider_record_id", ""),
                    title=r.get("titolo", ""),
                    description=r.get("description", ""),
                    canonical_url=r.get("catalog_url", ""),
                    item_type=r.get("source_type", "document"),
                    date_text=r.get("date_start", ""),
                    provider_code="nara",
                    holding_institution="NARA",
                    raw_metadata=r,
                ))
            return SearchPage(results=results, has_more=False)
        except Exception as exc:
            logger.error("NARA search error: %s", exc)
            return SearchPage(results=[], has_more=False)

    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        from source_providers.nara import ProviderNARA
        legacy = ProviderNARA()
        try:
            data = legacy.get_metadata(external_id)
            if not data:
                return None
            return self.normalize(data)
        except Exception:
            return None

    def fetch_representations(self, external_id: str) -> List[Representation]:
        return []

    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        return NormalizedItem(
            provider_code="nara",
            provider_item_id=payload.get("provider_record_id", ""),
            holding_institution="NARA",
            title=payload.get("titolo", ""),
            document_type=payload.get("source_type", "document"),
            date_start=payload.get("date_start", ""),
            original_url=payload.get("catalog_url", ""),
            raw_metadata=payload,
        )


class QuirinaleAdapter(SourceProvider):
    """Quirinale — Albo d'Oro e onorificenze.

    Fonti:
    - https://www.quirinale.it/albo-d-oro
    - https://www.quirinale.it/onorificenze
    - Gazzetta Ufficiale (archivio storico)
    """

    def __init__(self):
        self._config = _get_config("ussme")
        self._config = ProviderConfig(
            code="quirinale",
            display_name="Presidenza della Repubblica — Albo d'Oro e Onorificenze",
            authority_class="PRIMARY_ARCHIVAL",
            access_mode="METADATA_ONLY",
            independence_group="quirinale",
            rights_status="PUBLIC_VIEW",
            terms_url="https://www.quirinale.it/",
            holding_institution="Presidenza della Repubblica",
            collection_scope="Italy",
            personal_data_policy="UNKNOWN",
            allowed_actions=["search"],
            rate_limit_delay=3.0,
            provider_version="1.0",
            enabled=True,
            capabilities={"search": True, "fetch_metadata": False},
        )

    @property
    def provider_code(self) -> str:
        return "quirinale"

    def capabilities(self) -> ProviderCapabilities:
        return self._config.to_caps()

    def policy(self) -> ProviderPolicy:
        return self._config.to_policy()

    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        import requests
        results = []
        try:
            url = "https://www.quirinale.it/search-results"
            params = {"keyword": query, "sezione": "onorificenze"}
            resp = requests.get(url, params=params, timeout=30,
                                headers={"User-Agent": "ricerca-storica/1.0"})
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select(".card, .result-item, .search-result"):
                    title_el = card.select_one("h2, h3, .title, a")
                    title = title_el.get_text(strip=True) if title_el else ""
                    link = title_el.get("href", "") if title_el and title_el.name == "a" else ""
                    if not link:
                        link_el = card.select_one("a")
                        link = link_el.get("href", "") if link_el else ""
                    if title:
                        results.append(SearchResult(
                            external_id=link or title,
                            title=title,
                            canonical_url=link if link.startswith("http") else f"https://www.quirinale.it{link}" if link else "",
                            item_type="honor",
                            provider_code="quirinale",
                            holding_institution="Presidenza della Repubblica",
                            raw_metadata={"title": title, "url": link},
                        ))
        except Exception as exc:
            logger.error("Quirinale search error: %s", exc)

        return SearchPage(results=results, has_more=False)

    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        return None

    def fetch_representations(self, external_id: str) -> List[Representation]:
        return []

    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        return NormalizedItem(
            provider_code="quirinale",
            provider_item_id=payload.get("provider_record_id", ""),
            holding_institution="Presidenza della Repubblica",
            title=payload.get("titolo", ""),
            document_type="honor",
            original_url=payload.get("catalog_url", ""),
            raw_metadata=payload,
        )


def get_all_adapters() -> Dict[str, SourceProvider]:
    """Build and return all available provider adapters."""
    adapters: Dict[str, SourceProvider] = {}

    adapters["europeana"] = EuropeanaAdapter()
    adapters["icrc_ww1"] = ICRCWW1Adapter()
    adapters["lebi"] = LeBIAdapter()
    adapters["nara"] = NARAAdapter()
    adapters["quirinale"] = QuirinaleAdapter()

    # Bridge legacy providers
    try:
        from source_providers.federation import get_registry
        legacy_reg = get_registry()
        bridge_codes = [
            "internetarchive", "gallica", "antenati", "arolsen",
            "bundesarchiv", "cwgc", "memoire_des_hommes",
            "tna_uk", "abmc", "iwm_lives", "ddb",
            "wikitree", "grand_memorial", "librarycanada", "awm",
            "cri_milano", "ussme", "archiviodistato",
            "internetculturale", "googlebooks", "hathitrust",
            "shd",
        ]
        for code in bridge_codes:
            if code in legacy_reg and code not in adapters:
                adapters[code] = LegacyBridgeAdapter(legacy_reg[code], code)
    except Exception as exc:
        logger.warning("Failed to load legacy providers: %s", exc)

    return adapters
