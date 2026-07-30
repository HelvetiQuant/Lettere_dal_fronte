"""Repository Layer — accesso canonico agli oggetti dell'archivio storico.

Fornisce CRUD e query per le tabelle canoniche di Supabase/PostgreSQL:
- archive.repositories
- archive.collections
- archive.external_items (+ revisions)
- archive.representations
- archive.document_units
- archive.text_versions
- archive.passages
- archive.chunks

Ogni operazione è idempotente e traccia provenienza.

Utilizza supabase_client per REST API o psycopg2 per connessione diretta.
Fallback su SQLite locale per sviluppo/testing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("repository_layer")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class Repository:
    stable_id: str
    name: str
    institution_type: str = "archive"
    country: Optional[str] = None
    city: Optional[str] = None
    website_url: Optional[str] = None
    authority_uri: Optional[str] = None
    authority_score: float = 0.5
    languages: List[str] = field(default_factory=list)
    access_policy_default: str = "METADATA_ONLY"
    terms_of_use_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    id: Optional[int] = None


@dataclass
class Collection:
    stable_id: str
    repository_id: Optional[int]
    external_id: str
    title: str
    description: Optional[str] = None
    collection_type: str = "fondo"
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    extent: Optional[str] = None
    language: Optional[str] = None
    historical_period: Optional[str] = None
    geographic_area: Optional[str] = None
    access_status: str = "active"
    provider_code: Optional[str] = None
    raw_metadata_json: Optional[Dict] = None
    id: Optional[int] = None


@dataclass
class ExternalItem:
    stable_id: str
    provider_code: str
    external_id: str
    item_type: str = "document"
    title: Optional[str] = None
    description: Optional[str] = None
    date_text: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    language: Optional[str] = None
    reference_code: Optional[str] = None
    canonical_url: str = ""
    parent_external_id: Optional[str] = None
    access_status: str = "active"
    review_status: str = "candidate"
    metadata_hash: Optional[str] = None
    http_status: Optional[int] = None
    repository_id: Optional[int] = None
    collection_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class Representation:
    external_item_id: int
    representation_role: str = "original"
    format: str = "pdf"
    file_url: Optional[str] = None
    bucket_path: Optional[str] = None
    file_size: Optional[int] = None
    sha256: Optional[str] = None
    etag: Optional[str] = None
    page_count: Optional[int] = None
    has_ocr: bool = False
    publicly_viewable: bool = False
    public_download_allowed: bool = False
    authorization_required: bool = False
    rights_statement: Optional[str] = None
    credit_line: Optional[str] = None
    id: Optional[int] = None


@dataclass
class DocumentUnit:
    external_item_id: int
    unit_type: str = "page"
    unit_number: int = 1
    unit_label: Optional[str] = None
    iiif_canvas_uri: Optional[str] = None
    image_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    representation_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class TextVersion:
    external_item_id: int
    text_role: str = "ocr_provider"
    language: Optional[str] = None
    text_content: Optional[str] = None
    content_hash: Optional[str] = None
    ocr_confidence: Optional[float] = None
    model_version: Optional[str] = None
    representation_id: Optional[int] = None
    document_unit_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class Passage:
    stable_id: str
    text_version_id: int
    char_start: int
    char_end: int
    passage_text: str
    content_hash: str
    language: Optional[str] = None
    locator_json: Optional[Dict] = None
    document_unit_id: Optional[int] = None
    created_by: str = "system"
    review_status: str = "candidate"
    id: Optional[int] = None


# ─── Backend abstraction ─────────────────────────────────────────────────────

class RepositoryBackend:
    """Interfaccia astratta per backend (Supabase REST, psycopg2, SQLite)."""

    def upsert_repository(self, repo: Repository) -> Dict: ...
    def upsert_collection(self, coll: Collection) -> Dict: ...
    def upsert_external_item(self, item: ExternalItem) -> Dict: ...
    def add_item_revision(self, item_id: int, raw_metadata: Dict, metadata_hash: str) -> Dict: ...
    def upsert_representation(self, rep: Representation) -> Dict: ...
    def upsert_document_unit(self, unit: DocumentUnit) -> Dict: ...
    def upsert_text_version(self, tv: TextVersion) -> Dict: ...
    def upsert_passage(self, passage: Passage) -> Dict: ...
    def get_external_item(self, provider_code: str, external_id: str) -> Optional[Dict]: ...
    def get_representations(self, item_id: int) -> List[Dict]: ...
    def get_text_versions(self, item_id: int) -> List[Dict]: ...
    def get_passages(self, text_version_id: int) -> List[Dict]: ...
    def search_items(self, query: str, filters: Optional[Dict] = None) -> List[Dict]: ...


class SupabaseBackend(RepositoryBackend):
    """Backend Supabase via REST API (PostgREST).

    Uses PostgREST schema-switching headers (Accept-Profile / Content-Type-Profile)
    instead of schema-qualified URL paths, which are not exposed by default.
    """

    def __init__(self):
        from supabase_client import SUPABASE_URL, _rest_headers, _TIMEOUT
        self.url = SUPABASE_URL
        self.headers = _rest_headers()
        self.timeout = _TIMEOUT

    @staticmethod
    def _split_table(table: str) -> tuple[str, str]:
        if "." in table:
            schema, name = table.split(".", 1)
            return schema, name
        return "public", table

    def _schema_headers(self, schema: str, *, prefer: str = "") -> Dict:
        h = dict(self.headers)
        h["Accept-Profile"] = schema
        h["Content-Type-Profile"] = schema
        if prefer:
            h["Prefer"] = prefer
        return h

    def _post(self, table: str, data: Dict, prefer: str = "return=representation") -> Dict:
        """Insert or upsert a single row using exec_sql.

        PostgREST writes to non-public schemas often fail unless the schema is
        listed in Supabase Exposed Schemas. exec_sql (SECURITY DEFINER) is
        reliable and bypasses both RLS and schema exposure limits. It does not
        return the inserted row; callers should fetch explicitly if they need
        the generated id.
        """
        from supabase_client import insert_batch_schema
        schema, name = self._split_table(table)
        on_conflict = "merge" if "merge-duplicates" in prefer else "ignore"
        result = insert_batch_schema(schema, name, [data], on_conflict=on_conflict, batch_size=1)
        if result.get("ok"):
            return {"ok": True, "count": result.get("count", 0)}
        return {"error": result.get("error", "insert failed"), "status": 500}

    def _get(self, table: str, params: str) -> List[Dict]:
        import httpx
        schema, name = self._split_table(table)
        url = f"{self.url}/rest/v1/{name}?{params}"
        h = self._schema_headers(schema)
        r = httpx.get(url, headers=h, timeout=self.timeout)
        if r.status_code == 200:
            return r.json()
        return []

    def upsert_repository(self, repo: Repository) -> Dict:
        data = {
            "stable_id": repo.stable_id,
            "name": repo.name,
            "institution_type": repo.institution_type,
            "country": repo.country,
            "city": repo.city,
            "website_url": repo.website_url,
            "authority_uri": repo.authority_uri,
            "authority_score": repo.authority_score,
            "languages": repo.languages,
            "access_policy_default": repo.access_policy_default,
            "terms_of_use_url": repo.terms_of_use_url,
            "contact_email": repo.contact_email,
            "contact_phone": repo.contact_phone,
            "notes": repo.notes,
        }
        return self._post("archive.repositories", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def upsert_collection(self, coll: Collection) -> Dict:
        data = {
            "stable_id": coll.stable_id,
            "repository_id": coll.repository_id,
            "external_id": coll.external_id,
            "title": coll.title,
            "description": coll.description,
            "collection_type": coll.collection_type,
            "date_range_start": coll.date_range_start,
            "date_range_end": coll.date_range_end,
            "extent": coll.extent,
            "language": coll.language,
            "historical_period": coll.historical_period,
            "geographic_area": coll.geographic_area,
            "access_status": coll.access_status,
            "provider_code": coll.provider_code,
            "raw_metadata_json": json.dumps(coll.raw_metadata_json) if coll.raw_metadata_json else None,
        }
        return self._post("archive.collections", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def upsert_external_item(self, item: ExternalItem) -> Dict:
        data = {
            "stable_id": item.stable_id,
            "repository_id": item.repository_id,
            "collection_id": item.collection_id,
            "provider_code": item.provider_code,
            "external_id": item.external_id,
            "item_type": item.item_type,
            "title": item.title,
            "description": item.description,
            "date_text": item.date_text,
            "date_from": item.date_from,
            "date_to": item.date_to,
            "language": item.language,
            "reference_code": item.reference_code,
            "canonical_url": item.canonical_url,
            "parent_external_id": item.parent_external_id,
            "access_status": item.access_status,
            "review_status": item.review_status,
            "metadata_hash": item.metadata_hash,
            "http_status": item.http_status,
        }
        return self._post("archive.external_items", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def add_item_revision(self, item_id: int, raw_metadata: Dict, metadata_hash: str) -> Dict:
        existing = self._get("archive.external_item_revisions",
                             f"external_item_id=eq.{item_id}&order=revision_number.desc&limit=1")
        next_rev = (existing[0].get("revision_number", 0) + 1) if existing else 1
        data = {
            "external_item_id": item_id,
            "revision_number": next_rev,
            "raw_metadata_json": json.dumps(raw_metadata),
            "metadata_hash": metadata_hash,
        }
        return self._post("archive.external_item_revisions", data)

    def upsert_representation(self, rep: Representation) -> Dict:
        data = {
            "external_item_id": rep.external_item_id,
            "representation_role": rep.representation_role,
            "format": rep.format,
            "file_url": rep.file_url,
            "bucket_path": rep.bucket_path,
            "file_size": rep.file_size,
            "sha256": rep.sha256,
            "etag": rep.etag,
            "page_count": rep.page_count,
            "has_ocr": rep.has_ocr,
            "publicly_viewable": rep.publicly_viewable,
            "public_download_allowed": rep.public_download_allowed,
            "authorization_required": rep.authorization_required,
            "rights_statement": rep.rights_statement,
            "credit_line": rep.credit_line,
        }
        return self._post("archive.representations", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def upsert_document_unit(self, unit: DocumentUnit) -> Dict:
        data = {
            "external_item_id": unit.external_item_id,
            "representation_id": unit.representation_id,
            "unit_type": unit.unit_type,
            "unit_number": unit.unit_number,
            "unit_label": unit.unit_label,
            "iiif_canvas_uri": unit.iiif_canvas_uri,
            "image_url": unit.image_url,
            "width": unit.width,
            "height": unit.height,
        }
        return self._post("archive.document_units", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def upsert_text_version(self, tv: TextVersion) -> Dict:
        content_hash = tv.content_hash or _sha256(tv.text_content or "")
        data = {
            "external_item_id": tv.external_item_id,
            "representation_id": tv.representation_id,
            "document_unit_id": tv.document_unit_id,
            "text_role": tv.text_role,
            "language": tv.language,
            "text_content": tv.text_content,
            "content_hash": content_hash,
            "ocr_confidence": tv.ocr_confidence,
            "model_version": tv.model_version,
        }
        return self._post("archive.text_versions", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def upsert_passage(self, passage: Passage) -> Dict:
        data = {
            "stable_id": passage.stable_id,
            "text_version_id": passage.text_version_id,
            "document_unit_id": passage.document_unit_id,
            "char_start": passage.char_start,
            "char_end": passage.char_end,
            "passage_text": passage.passage_text,
            "content_hash": passage.content_hash,
            "language": passage.language,
            "locator_json": json.dumps(passage.locator_json) if passage.locator_json else None,
            "created_by": passage.created_by,
            "review_status": passage.review_status,
        }
        return self._post("archive.passages", data,
                          prefer="return=representation,resolution=merge-duplicates")

    def get_external_item(self, provider_code: str, external_id: str) -> Optional[Dict]:
        results = self._get("archive.external_items",
                            f"provider_code=eq.{provider_code}&external_id=eq.{external_id}&limit=1")
        return results[0] if results else None

    def get_representations(self, item_id: int) -> List[Dict]:
        return self._get("archive.representations", f"external_item_id=eq.{item_id}")

    def get_text_versions(self, item_id: int) -> List[Dict]:
        return self._get("archive.text_versions", f"external_item_id=eq.{item_id}")

    def get_passages(self, text_version_id: int) -> List[Dict]:
        return self._get("archive.passages", f"text_version_id=eq.{text_version_id}")

    def search_items(self, query: str, filters: Optional[Dict] = None) -> List[Dict]:
        params = f"title=ilike.*{query}*"
        if filters:
            if "provider_code" in filters:
                params += f"&provider_code=eq.{filters['provider_code']}"
            if "review_status" in filters:
                params += f"&review_status=eq.{filters['review_status']}"
        params += "&limit=50"
        return self._get("archive.external_items", params)


# ─── Factory ─────────────────────────────────────────────────────────────────

_backend: Optional[RepositoryBackend] = None


def get_backend() -> RepositoryBackend:
    global _backend
    if _backend is None:
        if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            _backend = SupabaseBackend()
        else:
            raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY richiesti per repository layer")
    return _backend


# ─── Helper functions ────────────────────────────────────────────────────────

def make_stable_id(namespace: str, external_id: str, provider: str = "") -> str:
    raw = f"{namespace}:{external_id}"
    if provider:
        raw += f":{provider}"
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def make_passage_stable_id(text_version_id: int, char_start: int, char_end: int) -> str:
    raw = f"passage:{text_version_id}:{char_start}:{char_end}"
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"
