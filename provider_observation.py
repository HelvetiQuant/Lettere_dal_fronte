"""ProviderObservation — normalized result contract from every provider.

Every provider (OpenAI, Tavily, Mistral, local_db, archive_provider) must
produce ProviderObservation records. Free text from a provider is never
used as proof. The raw payload is preserved via hash/audit, but only the
validated DTO passes to subsequent pipeline stages.

Content state lifecycle:
  NOT_OPENED → OPENED → METADATA_ONLY | OCR_EXTRACTED | FAILED

Classification:
  MODEL_LEAD | SEARCH_RESULT | SOURCE_CANDIDATE | CONTEXT | REJECTED
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class CitationAnnotation:
    url: str
    title: str = ""
    citation_index: int = 0
    start_pos: int = 0
    end_pos: int = 0


@dataclass
class SearchAction:
    action_type: str = ""  # web_search_call, archive_query, etc.
    query_used: str = ""
    provider_action_id: str = ""


@dataclass
class ProviderObservation:
    observation_id: str = ""
    run_id: str = ""
    manifest_hash: str = ""
    provider: str = ""  # openai|tavily|perplexity|gemini|claude|local_db|archive_provider|mistral|lm_studio
    provider_result_id: str = ""
    provider_query_id: str = ""
    capability: str = ""  # DISCOVERY_WEB|ARCHIVE_SEARCH|CONTENT_FETCH|OCR_EXTRACTION|CLAIM_EXTRACTION|REPORT_GENERATION|CONVERSATION
    observed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    title: str = ""
    url_raw: str = ""
    url_canonical: str = ""
    snippet: str = ""
    citation_annotations: List[CitationAnnotation] = field(default_factory=list)
    search_actions: List[SearchAction] = field(default_factory=list)
    content_state: str = "NOT_OPENED"  # NOT_OPENED|OPENED|METADATA_ONLY|OCR_EXTRACTED|FAILED
    source_record_id: Optional[str] = None
    locator: Optional[str] = None
    excerpt: Optional[str] = None
    raw_response_hash: str = ""
    classification: str = "MODEL_LEAD"  # MODEL_LEAD|SEARCH_RESULT|SOURCE_CANDIDATE|CONTEXT|REJECTED
    reason_codes: List[str] = field(default_factory=list)
    provider_score: float = 0.0
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.observation_id:
            raw = f"{self.provider}_{self.provider_result_id}_{self.url_canonical}_{self.observed_at}"
            self.observation_id = f"obs_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"
        if not self.raw_response_hash and (self.title or self.snippet or self.url_raw):
            raw = f"{self.title}|{self.snippet}|{self.url_raw}"
            self.raw_response_hash = hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderObservation":
        citations = d.pop("citation_annotations", [])
        actions = d.pop("search_actions", [])
        return cls(
            citation_annotations=[CitationAnnotation(**c) if isinstance(c, dict) else c for c in citations],
            search_actions=[SearchAction(**a) if isinstance(a, dict) else a for a in actions],
            **d,
        )

    def verify_manifest_hash(self, expected_hash: str) -> bool:
        return self.manifest_hash == expected_hash


# ─── Capability Registry V6 ──────────────────────────────────────────────────

@dataclass
class ProviderCapability:
    provider_name: str
    capabilities: List[str]  # subset of CAPABILITY_TYPES
    contract_version: str = "6.0"
    available: bool = False
    max_results: int = 20
    timeout_ms: int = 30000
    supports_structured_output: bool = False
    supports_web_search: bool = False
    supports_citations: bool = False
    cost_per_1k_tokens: float = 0.0
    rate_limit_rpm: int = 0


CAPABILITY_TYPES = [
    "DISCOVERY_WEB",
    "ARCHIVE_SEARCH",
    "CONTENT_FETCH",
    "OCR_EXTRACTION",
    "CLAIM_EXTRACTION",
    "REPORT_GENERATION",
    "CONVERSATION",
]


class ProviderCapabilityRegistry:
    """Versioned registry of provider capabilities.

    Each adapter declares only what it can really do.
    The registry is queried at startup to determine which providers
    participate in discovery vs. report generation.
    """

    def __init__(self):
        self._providers: Dict[str, ProviderCapability] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(ProviderCapability(
            provider_name="openai",
            capabilities=["DISCOVERY_WEB", "REPORT_GENERATION", "CONVERSATION", "CLAIM_EXTRACTION"],
            available=False,  # probed at startup
            supports_structured_output=True,
            supports_web_search=True,
            supports_citations=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="tavily",
            capabilities=["DISCOVERY_WEB", "ARCHIVE_SEARCH"],
            available=False,
            supports_web_search=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="mistral",
            capabilities=["REPORT_GENERATION", "CONVERSATION", "CLAIM_EXTRACTION"],
            available=False,
            supports_structured_output=False,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="lm_studio",
            capabilities=["REPORT_GENERATION", "CONVERSATION"],
            available=False,
            supports_structured_output=False,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="local_db",
            capabilities=["ARCHIVE_SEARCH", "CONTENT_FETCH"],
            available=True,  # always available
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="perplexity",
            capabilities=["DISCOVERY_WEB", "REPORT_GENERATION"],
            available=False,
            supports_web_search=True,
            supports_citations=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="gemini",
            capabilities=["DISCOVERY_WEB", "REPORT_GENERATION", "CONVERSATION"],
            available=False,
            supports_web_search=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="claude",
            capabilities=["DISCOVERY_WEB", "REPORT_GENERATION", "CONVERSATION", "CLAIM_EXTRACTION"],
            available=False,
            supports_web_search=True,
            supports_citations=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="federation",
            capabilities=["ARCHIVE_SEARCH", "CONTENT_FETCH"],
            available=False,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="brave",
            capabilities=["DISCOVERY_WEB"],
            available=False,
            supports_web_search=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="serper",
            capabilities=["DISCOVERY_WEB"],
            available=False,
            supports_web_search=True,
            contract_version="6.0",
        ))
        self.register(ProviderCapability(
            provider_name="serpapi",
            capabilities=["DISCOVERY_WEB"],
            available=False,
            supports_web_search=True,
            contract_version="6.0",
        ))

    def register(self, cap: ProviderCapability):
        self._providers[cap.provider_name] = cap

    def get(self, name: str) -> Optional[ProviderCapability]:
        return self._providers.get(name)

    def get_available_for_capability(self, capability: str) -> List[ProviderCapability]:
        return [
            cap for cap in self._providers.values()
            if cap.available and capability in cap.capabilities
        ]

    def get_discovery_providers(self) -> List[ProviderCapability]:
        return self.get_available_for_capability("DISCOVERY_WEB")

    def get_report_providers(self) -> List[ProviderCapability]:
        return self.get_available_for_capability("REPORT_GENERATION")

    def get_conversation_providers(self) -> List[ProviderCapability]:
        return self.get_available_for_capability("CONVERSATION")

    def set_available(self, name: str, available: bool):
        if name in self._providers:
            self._providers[name].available = available

    def all_providers(self) -> Dict[str, ProviderCapability]:
        return dict(self._providers)
