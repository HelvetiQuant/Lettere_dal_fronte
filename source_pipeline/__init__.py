"""
Source provider contract — interfaccia unificata per tutti i provider di fonti.

Ogni adapter deve implementare SourceProvider con:
  capabilities()          → dichiara cosa può fare
  policy()                → termini d'uso, diritti, rate limit
  search(query, cursor)   → ricerca metadati, paginata
  fetch_metadata(id)      → metadati dettagliati
  fetch_representations(id) → rappresentazioni (PDF, immagini, OCR)
  normalize(payload)      → normalizza payload provider → schema canonico
  checkpoint()            → stato per resume
"""
from __future__ import annotations

import abc
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ProviderCapabilities:
    search: bool = False
    fetch_metadata: bool = False
    download: bool = False
    ocr: bool = False
    caching: bool = True
    publishing: bool = False
    local_storage: bool = False
    commercial_reuse: bool = False
    personal_data: bool = False


@dataclass(frozen=True)
class ProviderPolicy:
    provider_code: str
    authority_class: str
    access_mode: str
    rights_status: str
    terms_url: str
    license_uri: str
    holding_institution: str
    collection_scope: str
    personal_data_policy: str
    allowed_actions: Tuple[str, ...] = ()
    rate_limit_delay_seconds: float = 1.0
    rate_limit_max_per_minute: int = 60
    independence_group: str = ""
    provider_version: str = "1.0"
    enabled: bool = True


@dataclass
class SearchResult:
    external_id: str
    title: str
    description: str = ""
    canonical_url: str = ""
    item_type: str = "document"
    date_text: str = ""
    language: str = ""
    provider_code: str = ""
    holding_institution: str = ""
    collection_or_fonds: str = ""
    archival_signature: str = ""
    persistent_identifier: str = ""
    rights_uri: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    iiif_manifest: str = ""


@dataclass
class SearchPage:
    results: List[SearchResult]
    next_cursor: Optional[str] = None
    total_count: Optional[int] = None
    has_more: bool = False


@dataclass
class Representation:
    representation_type: str = "original"
    mime_type: str = ""
    file_url: str = ""
    page_count: int = 0
    iiif_manifest: str = ""
    canvas_id: str = ""
    page_number: int = 0
    ocr_available: bool = False
    checksum: str = ""
    rights_statement: str = ""


@dataclass
class NormalizedItem:
    provider_code: str
    provider_item_id: str
    holding_institution: str = ""
    collection_or_fonds: str = ""
    archival_signature: str = ""
    title: str = ""
    document_type: str = "document"
    date_start: str = ""
    date_end: str = ""
    date_precision: str = "day"
    language: str = ""
    original_url: str = ""
    persistent_identifier: str = ""
    rights_uri: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    representations: List[Representation] = field(default_factory=list)


class SourceProvider(abc.ABC):
    """Contratto unico per tutti i provider di fonti storiche."""

    @property
    @abc.abstractmethod
    def provider_code(self) -> str:
        """Unique identifier for this provider."""
        ...

    @abc.abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Declare what actions are permitted for this provider."""
        ...

    @abc.abstractmethod
    def policy(self) -> ProviderPolicy:
        """Return terms of use, rights, rate limits."""
        ...

    @abc.abstractmethod
    def search(self, query: str, cursor: Optional[str] = None) -> SearchPage:
        """Search the provider's catalog. Returns a page of results + cursor."""
        ...

    @abc.abstractmethod
    def fetch_metadata(self, external_id: str) -> Optional[NormalizedItem]:
        """Fetch detailed metadata for a single item."""
        ...

    @abc.abstractmethod
    def fetch_representations(self, external_id: str) -> List[Representation]:
        """Fetch available representations (PDF, images, OCR, transcriptions)."""
        ...

    @abc.abstractmethod
    def normalize(self, payload: Dict[str, Any]) -> NormalizedItem:
        """Normalize provider-specific payload into canonical schema."""
        ...

    def checkpoint(self) -> Dict[str, Any]:
        """Return serializable state for resume. Override if needed."""
        return {}

    def restore_checkpoint(self, state: Dict[str, Any]) -> None:
        """Restore state from a checkpoint. Override if needed."""
        pass


def compute_stable_id(namespace: str, external_id: str, provider: str = "") -> str:
    """Compute a deterministic stable ID for an external item."""
    raw = f"{namespace}:{external_id}"
    if provider:
        raw += f":{provider}"
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of text content."""
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()
