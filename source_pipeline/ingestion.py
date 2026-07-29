"""
Ingestion — persist search results and extracted claims/evidence
into the canonical Supabase schema (archive.external_items,
evidence.claims, evidence.evidence).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from source_pipeline import (
    SearchResult,
    NormalizedItem,
    Representation,
    compute_stable_id,
    compute_content_hash,
)
from source_pipeline.adapters import get_all_adapters

load_dotenv()

logger = logging.getLogger("source_pipeline.ingestion")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def _execute_sql(sql: str) -> dict:
    """Execute SQL on Supabase via exec_sql RPC."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=120)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


def _exec_sql_returning(sql: str) -> list | dict:
    """Execute SQL that returns rows via exec_sql_returning RPC."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql_returning"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=120)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


def _get_provider_id(provider_code: str) -> Optional[int]:
    """Get provider_id from archive.providers."""
    sql = f"SELECT json_agg(row_to_json(x)) FROM (SELECT id FROM archive.providers WHERE provider_code = '{provider_code}' LIMIT 1) x;"
    result = _exec_sql_returning(sql)
    if isinstance(result, list) and result:
        return result[0].get("id")
    return None


def ingest_search_result(
    result: SearchResult,
    provider_id: Optional[int] = None,
) -> Optional[int]:
    """Insert a SearchResult into archive.external_items. Returns item ID or None."""
    stable_id = compute_stable_id("ext", result.external_id, result.provider_code)

    # Check if already exists
    check_sql = f"SELECT json_agg(row_to_json(x)) FROM (SELECT id FROM archive.external_items WHERE stable_id = '{stable_id}' LIMIT 1) x;"
    existing = _exec_sql_returning(check_sql)
    if isinstance(existing, list) and existing:
        item_id = existing[0].get("id")
        logger.info("Item already exists (id=%s): %s", item_id, result.title[:50])
        return item_id

    # Insert via SQL
    title_escaped = result.title.replace("'", "''")
    desc_escaped = result.description.replace("'", "''")[:500] if result.description else ""
    url_escaped = result.canonical_url.replace("'", "''")
    raw_json = json.dumps(result.raw_metadata, ensure_ascii=False, default=str).replace("'", "''")[:5000]

    sql = f"""
    WITH x AS (
        INSERT INTO archive.external_items
            (stable_id, provider_code, external_id, item_type, title, description,
             canonical_url, raw_metadata{", provider_id" if provider_id else ""})
        VALUES
            ('{stable_id}', '{result.provider_code}', '{result.external_id.replace("'", "''") or stable_id}',
             '{result.item_type}',
             '{title_escaped}', '{desc_escaped}',
             '{url_escaped}', '{raw_json}'::jsonb{f", {provider_id}" if provider_id else ""})
        ON CONFLICT (stable_id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            canonical_url = EXCLUDED.canonical_url,
            raw_metadata = EXCLUDED.raw_metadata,
            updated_at = now()
        RETURNING id
    )
    SELECT json_agg(row_to_json(x)) FROM x;
    """
    result_data = _exec_sql_returning(sql)
    if isinstance(result_data, list) and result_data:
        return result_data[0].get("id")
    if isinstance(result_data, dict) and result_data.get("__error__"):
        logger.error("Failed to insert external_item: %s", result_data.get("error", ""))
        return None

    # Fallback: query after insert
    existing = _exec_sql_returning(check_sql)
    if isinstance(existing, list) and existing:
        return existing[0].get("id")
    return None


def create_claim(
    subject_entity_id: int,
    predicate: str,
    object_entity_id: Optional[int] = None,
    object_value: Optional[str] = None,
    claim_status: str = "discovered",
    extraction_method: str = "manual",
    pipeline_run_id: str = "",
    valid_from: str = "",
    valid_to: str = "",
    conflict_code: str = "",
) -> Optional[int]:
    """Insert a claim into evidence.claims. Returns claim ID."""
    stable_id = compute_stable_id(
        "claim",
        f"{subject_entity_id}:{predicate}:{object_entity_id or object_value or ''}:{pipeline_run_id}",
    )

    obj_entity = str(object_entity_id) if object_entity_id else "NULL"
    obj_value_escaped = (object_value or "").replace("'", "''")
    valid_from_clause = f"'{valid_from}'" if valid_from else "NULL"
    valid_to_clause = f"'{valid_to}'" if valid_to else "NULL"
    conflict_clause = f"'{conflict_code}'" if conflict_code else "NULL"

    sql = f"""
    WITH x AS (
        INSERT INTO evidence.claims
            (stable_id, subject_entity_id, predicate, object_entity_id, object_value,
             claim_status, extraction_method, pipeline_run_id, valid_from, valid_to, conflict_code)
        VALUES
            ('{stable_id}', {subject_entity_id}, '{predicate}', {obj_entity}, '{obj_value_escaped}',
             '{claim_status}', '{extraction_method}', '{pipeline_run_id}',
             {valid_from_clause}, {valid_to_clause}, {conflict_clause})
        ON CONFLICT (stable_id) DO UPDATE SET
            claim_status = EXCLUDED.claim_status,
            updated_at = now()
        RETURNING id
    )
    SELECT json_agg(row_to_json(x)) FROM x;
    """
    result = _exec_sql_returning(sql)
    if isinstance(result, list) and result:
        return result[0].get("id")
    if isinstance(result, dict) and result.get("__error__"):
        logger.error("Failed to create claim: %s", result.get("error", ""))
        return None

    # Fallback: query after insert
    check_sql = f"SELECT json_agg(row_to_json(x)) FROM (SELECT id FROM evidence.claims WHERE stable_id = '{stable_id}' LIMIT 1) x;"
    existing = _exec_sql_returning(check_sql)
    if isinstance(existing, list) and existing:
        return existing[0].get("id")
    return None


def add_evidence(
    claim_id: int,
    source_item_id: Optional[int] = None,
    evidence_type: str = "documentary",
    text_span: str = "",
    page_or_canvas: str = "",
    independence_group: str = "",
    review_status: str = "pending",
) -> Optional[int]:
    """Add evidence linking a claim to a source item."""
    stable_id = compute_stable_id(
        "evidence",
        f"{claim_id}:{source_item_id or ''}:{page_or_canvas}:{text_span[:50]}",
    )

    source_clause = str(source_item_id) if source_item_id else "NULL"
    text_escaped = text_span.replace("'", "''")[:1000]
    page_escaped = page_or_canvas.replace("'", "''")
    ind_escaped = independence_group.replace("'", "''")

    sql = f"""
    WITH x AS (
        INSERT INTO evidence.evidence
            (stable_id, claim_id, source_item_id, evidence_type, text_span,
             page_or_canvas, independence_group, review_status)
        VALUES
            ('{stable_id}', {claim_id}, {source_clause}, '{evidence_type}',
             '{text_escaped}', '{page_escaped}', '{ind_escaped}', '{review_status}')
        ON CONFLICT (stable_id) DO UPDATE SET
            review_status = EXCLUDED.review_status,
            updated_at = now()
        RETURNING id
    )
    SELECT json_agg(row_to_json(x)) FROM x;
    """
    result = _exec_sql_returning(sql)
    if isinstance(result, list) and result:
        return result[0].get("id")
    if isinstance(result, dict) and result.get("__error__"):
        logger.error("Failed to add evidence: %s", result.get("error", ""))
        return None

    # Fallback: query after insert
    check_sql = f"SELECT json_agg(row_to_json(x)) FROM (SELECT id FROM evidence.evidence WHERE stable_id = '{stable_id}' LIMIT 1) x;"
    existing = _exec_sql_returning(check_sql)
    if isinstance(existing, list) and existing:
        return existing[0].get("id")
    return None


def run_discovery(
    provider_code: str,
    query: str,
    max_results: int = 20,
) -> List[SearchResult]:
    """Run a discovery search via a provider adapter and ingest results."""
    adapters = get_all_adapters()
    adapter = adapters.get(provider_code)
    if not adapter:
        logger.error("No adapter for provider '%s'", provider_code)
        return []

    provider_id = _get_provider_id(provider_code)
    logger.info("Discovery: provider=%s query='%s' provider_id=%s", provider_code, query, provider_id)

    all_results: List[SearchResult] = []
    cursor = None
    while len(all_results) < max_results:
        page = adapter.search(query, cursor=cursor)
        if not page.results:
            break
        for result in page.results:
            item_id = ingest_search_result(result, provider_id=provider_id)
            if item_id:
                logger.info("  Ingested: id=%s '%s'", item_id, result.title[:60])
            all_results.append(result)
            if len(all_results) >= max_results:
                break
        if not page.has_more or not page.next_cursor:
            break
        cursor = page.next_cursor
        time.sleep(1)

    logger.info("Discovery complete: %d results ingested", len(all_results))
    return all_results
