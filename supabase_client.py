"""Supabase REST API client for schema creation and data migration.

Uses the Supabase Management API and PostgREST for:
- SQL execution (schema DDL, indexes, RLS policies)
- Batch data insertion via PostgREST
- Table listing and row counting

Credentials from .env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

_TIMEOUT = 60


def _rest_headers(*, prefer: str = "") -> dict:
    h = dict(_HEADERS)
    if prefer:
        h["Prefer"] = prefer
    return h


def execute_sql(sql: str, *, timeout: int = 120) -> dict:
    """Execute raw SQL on Supabase via the pg_net/rpc endpoint.

    Uses the Supabase SQL API (POST /rest/v1/rpc) or falls back
    to the PostgREST rpc endpoint.
    """
    # Use Supabase's built-in SQL execution via the /rest/v1/rpc endpoint
    # We create a helper function first, then call it
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=_rest_headers(), json={"query": sql}, timeout=timeout)
    if r.status_code in (200, 201, 204):
        try:
            return {"ok": True, "data": r.json()}
        except Exception:
            return {"ok": True, "data": None}
    return {"ok": False, "status": r.status_code, "error": r.text[:500]}


def execute_sql_direct(sql: str, *, timeout: int = 120) -> dict:
    """Execute raw SQL via Supabase's pg REST SQL endpoint (requires service_role)."""
    # Supabase exposes /pg/query for direct SQL (undocumented but works with service_role)
    url = f"{SUPABASE_URL}/rest/v1/rpc"
    
    # Alternative: use the Supabase Management API or the pg endpoint
    # Try the standard approach: create a function via PostgREST
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    
    # Use Supabase's /pg endpoint for direct SQL execution
    pg_url = f"{SUPABASE_URL.replace('.supabase.co', '.supabase.co')}/pg"
    r = httpx.post(pg_url, headers=headers, json={"query": sql}, timeout=timeout)
    if r.status_code in (200, 201, 204):
        try:
            return {"ok": True, "data": r.json()}
        except Exception:
            return {"ok": True, "data": None}
    
    return {"ok": False, "status": r.status_code, "error": r.text[:500]}


def create_exec_sql_function() -> bool:
    """Create a helper SQL function on Supabase for executing arbitrary SQL.
    
    This creates a PostgreSQL function that can be called via PostgREST RPC.
    Requires service_role key.
    """
    # This SQL creates a function that executes arbitrary SQL
    # We need to use the Supabase SQL Editor API for this
    sql = """
    CREATE OR REPLACE FUNCTION exec_sql(query text)
    RETURNS json
    LANGUAGE plpgsql
    SECURITY DEFINER
    AS $$
    DECLARE
        result json;
    BEGIN
        EXECUTE query;
        RETURN json_build_object('ok', true);
    EXCEPTION WHEN OTHERS THEN
        RETURN json_build_object('ok', false, 'error', SQLERRM);
    END;
    $$;
    """
    # To bootstrap, we need to use the Supabase Dashboard SQL Editor
    # or the Management API. For now, try via the REST endpoint.
    return _try_sql_via_management_api(sql)


def _try_sql_via_management_api(sql: str) -> bool:
    """Try executing SQL via Supabase Management API (requires service_role)."""
    # The Supabase client library provides a way to execute SQL
    # Let's try using the supabase-py client
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # The supabase-py client doesn't expose direct SQL execution
        # We need to use PostgREST rpc or the Management API
        pass
    except ImportError:
        pass
    
    # Fallback: use the Supabase HTTP API for SQL
    # POST to /rest/v1/rpc with the SQL
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    
    # Try the query endpoint
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=headers, json={"query": sql}, timeout=120)
    if r.status_code in (200, 201, 204):
        return True
    
    print(f"  Management API fallback needed. Status: {r.status_code}")
    return False


def insert_batch(table: str, rows: list[dict], *, 
                 on_conflict: str = "ignore") -> dict:
    """Insert a batch of rows into a Supabase table via PostgREST.

    Args:
        table: table name
        rows: list of dicts (column: value)
        on_conflict: 'ignore' (skip duplicates) or 'merge' (upsert)
    
    Returns:
        dict with 'ok', 'count', 'error' keys
    """
    if not rows:
        return {"ok": True, "count": 0}

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    prefer = "return=minimal"
    if on_conflict == "ignore":
        prefer += ",resolution=ignore-duplicates"
    elif on_conflict == "merge":
        prefer += ",resolution=merge-duplicates"
    
    headers = _rest_headers(prefer=prefer)
    
    # Clean rows: convert non-JSON-serializable values
    clean_rows = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, bytes):
                clean[k] = v.hex()
            elif isinstance(v, (int, float, str, bool, type(None))):
                clean[k] = v
            else:
                clean[k] = str(v)
        clean_rows.append(clean)
    
    try:
        r = httpx.post(url, headers=headers, json=clean_rows, timeout=_TIMEOUT)
        if r.status_code in (200, 201, 204):
            return {"ok": True, "count": len(clean_rows)}
        return {"ok": False, "count": 0, "status": r.status_code, 
                "error": r.text[:500]}
    except httpx.TimeoutException:
        return {"ok": False, "count": 0, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "count": 0, "error": str(e)[:500]}


def list_tables() -> list[str]:
    """List all tables currently on Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/"
    r = httpx.get(url, headers=_rest_headers(), timeout=_TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, dict):
            return list(data.keys())
        elif isinstance(data, list):
            return [item.get("table_name", str(item)) for item in data if isinstance(item, dict)]
    return []


def table_count(table: str) -> int:
    """Get row count for a table on Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=count"
    headers = _rest_headers(prefer="count=exact")
    r = httpx.head(url, headers=headers, timeout=_TIMEOUT)
    if r.status_code == 200:
        content_range = r.headers.get("content-range", "")
        # Format: "0-N/total" or "*/total"
        if "/" in content_range:
            total = content_range.split("/")[-1]
            if total != "*":
                return int(total)
    return -1


def table_exists_on_supabase(table: str) -> bool:
    """Check if a table exists on Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=count&limit=0"
    headers = _rest_headers(prefer="count=exact")
    r = httpx.head(url, headers=headers, timeout=_TIMEOUT)
    return r.status_code == 200


def health_check() -> dict:
    """Check Supabase connectivity and return project info."""
    url = f"{SUPABASE_URL}/rest/v1/"
    try:
        r = httpx.get(url, headers=_rest_headers(), timeout=15)
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "url": SUPABASE_URL,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# Multi-schema support (archive, evidence, ops, ai, api_public, legacy)
# ════════════════════════════════════════════════════════════════════════════

VALID_SCHEMAS = {"public", "archive", "evidence", "ops", "ai", "api_public", "legacy"}


def _validate_schema(schema: str) -> str:
    if schema not in VALID_SCHEMAS:
        raise ValueError(f"Invalid schema '{schema}'. Valid: {VALID_SCHEMAS}")
    return schema


def _schema_headers(schema: str, *, prefer: str = "") -> dict:
    """Return headers for PostgREST schema switching.

    Uses Accept-Profile for reads and Content-Type-Profile for writes.
    Sending both keeps reads/writes/PATCH working transparently.
    """
    headers = _rest_headers(prefer=prefer)
    headers["Accept-Profile"] = schema
    headers["Content-Type-Profile"] = schema
    return headers


def insert_batch_schema(schema: str, table: str, rows: list[dict], *,
                        on_conflict: str = "ignore") -> dict:
    """Insert batch into a schema-qualified table via PostgREST schema switching.

    Uses the unqualified table path (/rest/v1/table) with the
    Content-Type-Profile header set to the target schema.
    """
    if not rows:
        return {"ok": True, "count": 0}

    _validate_schema(schema)
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    prefer = "return=minimal"
    if on_conflict == "ignore":
        prefer += ",resolution=ignore-duplicates"
    elif on_conflict == "merge":
        prefer += ",resolution=merge-duplicates"

    headers = _schema_headers(schema, prefer=prefer)

    clean_rows = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, bytes):
                clean[k] = v.hex()
            elif isinstance(v, (int, float, str, bool, type(None))):
                clean[k] = v
            elif isinstance(v, (list, dict)):
                clean[k] = json.dumps(v) if isinstance(v, dict) else v
            else:
                clean[k] = str(v)
        clean_rows.append(clean)

    # PostgREST max batch ~500 rows, chunk if needed
    BATCH_SIZE = 500
    total_ok = 0
    total_err = None
    for i in range(0, len(clean_rows), BATCH_SIZE):
        batch = clean_rows[i:i + BATCH_SIZE]
        try:
            r = httpx.post(url, headers=headers, json=batch, timeout=_TIMEOUT)
            if r.status_code in (200, 201, 204):
                total_ok += len(batch)
            else:
                total_err = f"status={r.status_code}: {r.text[:300]}"
                break
        except httpx.TimeoutException:
            total_err = "timeout"
            break
        except Exception as e:
            total_err = str(e)[:300]
            break

    if total_err:
        return {"ok": False, "count": total_ok, "error": total_err}
    return {"ok": True, "count": total_ok}


def table_count_schema(schema: str, table: str) -> int:
    """Get row count for a schema-qualified table."""
    _validate_schema(schema)
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=count"
    headers = _schema_headers(schema, prefer="count=exact")
    r = httpx.head(url, headers=headers, timeout=_TIMEOUT)
    if r.status_code == 200:
        content_range = r.headers.get("content-range", "")
        if "/" in content_range:
            total = content_range.split("/")[-1]
            if total != "*":
                return int(total)
    return -1


def table_exists_schema(schema: str, table: str) -> bool:
    """Check if a schema-qualified table exists and is accessible."""
    _validate_schema(schema)
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=count&limit=0"
    headers = _schema_headers(schema, prefer="count=exact")
    r = httpx.head(url, headers=headers, timeout=_TIMEOUT)
    return r.status_code == 200


def select_schema(schema: str, table: str, *,
                  columns: str = "*",
                  filters: str = "",
                  limit: int = 100,
                  order: str = "") -> list[dict]:
    """SELECT from a schema-qualified table via PostgREST schema switching.

    Args:
        schema: schema name (archive, evidence, ops, ai, etc.)
        table: table name
        columns: column list (comma-separated or *)
        filters: PostgREST filter string (e.g. "review_status=eq.confirmed")
        limit: max rows
        order: order by (e.g. "created_at.desc")
    """
    _validate_schema(schema)
    params = f"select={columns}"
    if filters:
        params += f"&{filters}"
    if order:
        params += f"&order={order}"
    params += f"&limit={limit}"

    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    headers = _schema_headers(schema)
    r = httpx.get(url, headers=headers, timeout=_TIMEOUT)
    if r.status_code == 200:
        return r.json()
    return []


def exec_sql_batch(sql_text: str, *, timeout: int = 120) -> dict:
    """Execute a full SQL file by sending it as a single call to exec_sql.

    Handles multi-statement SQL including $$ blocks.
    """
    result = execute_sql(sql_text, timeout=timeout)
    return result


# ════════════════════════════════════════════════════════════════════════════
# Supabase Storage API
# ════════════════════════════════════════════════════════════════════════════

def create_storage_bucket(name: str, *, public: bool = False,
                          file_size_limit: int = None,
                          allowed_mime_types: list = None) -> dict:
    """Create a Storage bucket via the Supabase Storage API."""
    url = f"{SUPABASE_URL}/storage/v1/bucket"
    body = {"name": name, "public": public}
    if file_size_limit:
        body["file_size_limit"] = file_size_limit
    if allowed_mime_types:
        body["allowed_mime_types"] = allowed_mime_types

    r = httpx.post(url, headers=_rest_headers(), json=body, timeout=_TIMEOUT)
    if r.status_code in (200, 201):
        return {"ok": True, "data": r.json() if r.text else {}}
    return {"ok": False, "status": r.status_code, "error": r.text[:500]}


def list_storage_buckets() -> list[dict]:
    """List all Storage buckets."""
    url = f"{SUPABASE_URL}/storage/v1/bucket"
    r = httpx.get(url, headers=_rest_headers(), timeout=_TIMEOUT)
    if r.status_code == 200:
        return r.json()
    return []


def upload_file(bucket: str, path: str, file_path: str,
                *, content_type: str = "application/octet-stream") -> dict:
    """Upload a file to a Storage bucket."""
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    headers = _rest_headers()
    headers["Content-Type"] = content_type

    with open(file_path, "rb") as f:
        r = httpx.post(url, headers=headers, content=f, timeout=300)
    if r.status_code in (200, 201):
        return {"ok": True, "path": f"{bucket}/{path}"}
    return {"ok": False, "status": r.status_code, "error": r.text[:500]}


def create_signed_url(bucket: str, path: str, *, expires_in: int = 3600) -> dict:
    """Create a signed URL for a private file."""
    url = f"{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{path}"
    r = httpx.post(url, headers=_rest_headers(),
                   json={"expiresIn": expires_in}, timeout=_TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        signed_url = f"{SUPABASE_URL}/storage/v1{data.get('signedURL', '')}"
        return {"ok": True, "url": signed_url}
    return {"ok": False, "status": r.status_code, "error": r.text[:500]}


def get_public_url(bucket: str, path: str) -> str:
    """Get the public URL for a file in a public bucket."""
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
