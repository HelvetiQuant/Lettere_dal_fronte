"""Discovery Persistence — acquisizione, classificazione e persistenza
di fonti, claim, entità e piste scoperte via web search.

Pipeline:
1. Classificazione archival policy (compliance_gate)
2. Deduplicazione fonti (URL, hash, ID)
3. Estrazione claims dal testo web search
4. Entity resolution + nuove entità candidate
5. Creazione piste di ricerca
6. Persistenza locale transazionale (SQLite)
7. Outbox + sync idempotente Supabase
8. Output discovery_persistence per dossier API
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

log = logging.getLogger("discovery_persistence")


# ═══ Dataclasses ═════════════════════════════════════════════════════════════

@dataclass
class ArchivalDecision:
    policy: str = "metadata_only"  # full_content|structured_data|metadata_only|link_only|manual_review
    rights_status: str = "unknown"  # public_domain|open_license|explicit_permission|restricted|unknown
    license_name: str = ""
    license_url: str = ""
    terms_url: str = ""
    archival_allowed: bool = False
    metadata_allowed: bool = True
    content_download_allowed: bool = False
    extraction_allowed: bool = False
    decision_reason: str = ""
    checked_at: str = ""


@dataclass
class SourceMetadata:
    canonical_id: str = ""
    canonical_url: str = ""
    original_url: str = ""
    source_title: str = ""
    institution: str = ""
    archive_name: str = ""
    author_or_creator: str = ""
    source_type: str = ""
    record_kind: str = ""
    archival_reference: str = ""
    source_identifier: str = ""
    publication_or_record_date: str = ""
    language: str = ""
    country: str = "IT"
    conflict: str = ""
    historical_period_start: Optional[str] = None
    historical_period_end: Optional[str] = None
    geographic_scope: List[str] = field(default_factory=list)
    access_date: str = ""
    last_verified_at: str = ""
    retrieval_method: str = "web_search"
    query_used: str = ""
    scope_relation: str = ""
    historical_relevance_score: float = 0.0
    archival_policy: str = "metadata_only"
    rights_status: str = "unknown"
    license_name: str = ""
    content_sha256: str = ""
    source_cluster_id: str = ""
    primary_origin: str = ""
    fetch_status: str = ""
    http_status: Optional[int] = None
    provenance_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceObjectLink:
    canonical_id: str = ""
    source_id: str = ""
    object_type: str = ""  # soldier|event|fact|source|document|place|military_unit|claim
    object_id: str = ""
    relation_type: str = ""  # direct_evidence|mentions|describes|context_for|corroborates|contradicts|derived_from|same_as|discovery_lead|expands_research
    linked_claim_ids: List[str] = field(default_factory=list)
    evidence_fields: List[str] = field(default_factory=list)
    temporal_match: bool = False
    conflict_match: bool = False
    geographic_match: bool = False
    linkage_method: str = "ai_suggested"  # deterministic|provider|ai_suggested|manual
    linkage_score: float = 0.0
    linkage_explanation: str = ""
    review_status: str = "pending"  # automatic|pending|approved|rejected


@dataclass
class HistoricalClaim:
    canonical_id: str = ""
    subject_type: str = ""  # soldier|event|fact|place|military_unit
    subject_id: str = ""
    predicate: str = ""
    original_value: str = ""
    normalized_value: str = ""
    value_type: str = ""  # date|place|person|identifier|text|unit|status
    source_id: str = ""
    source_locator: str = ""
    extraction_method: str = "ai_extraction"  # structured|ocr|ai_extraction|manual
    status: str = "unverified"  # unverified|corroborated|conflicting|verified|rejected
    first_observed_at: str = ""
    last_evaluated_at: str = ""
    manual_review_required: bool = False


@dataclass
class DiscoveredEntity:
    canonical_id: str = ""
    entity_type: str = ""  # person|event|unit|place|document|source
    canonical_label: str = ""
    aliases: List[str] = field(default_factory=list)
    identifiers: Dict[str, str] = field(default_factory=dict)
    conflict: str = ""
    date_range: Dict[str, str] = field(default_factory=dict)
    discovery_source_id: str = ""
    discovery_parent_type: str = ""
    discovery_parent_id: str = ""
    status: str = "candidate"  # candidate|probable|verified|excluded
    review_required: bool = True


@dataclass
class ResearchLead:
    canonical_id: str = ""
    subject_type: str = ""
    subject_id: str = ""
    discovered_from_source_id: str = ""
    lead_type: str = ""  # archive|person|event|document|identifier|place|unit|related_source
    title: str = ""
    description: str = ""
    target_institution: str = ""
    target_url: str = ""
    suggested_queries: List[str] = field(default_factory=list)
    expected_evidence: str = ""
    priority: str = "medium"  # low|medium|high
    status: str = "new"  # new|queued|in_progress|resolved|discarded
    resolution_source_ids: List[str] = field(default_factory=list)
    created_at: str = ""
    last_checked_at: str = ""


@dataclass
class SyncState:
    canonical_id: str = ""
    local_version: int = 1
    remote_version: Optional[int] = None
    local_updated_at: str = ""
    remote_updated_at: str = ""
    sync_status: str = "pending"  # pending|syncing|synced|retryable_error|permanent_error|conflict
    retry_count: int = 0
    last_error: str = ""
    last_attempt_at: str = ""


@dataclass
class DiscoveryPersistenceResult:
    sources_discovered: int = 0
    new_sources_created: int = 0
    existing_sources_updated: int = 0
    full_content_archived: int = 0
    metadata_only_saved: int = 0
    link_only_saved: int = 0
    new_claims_created: int = 0
    conflicting_claims_created: int = 0
    new_entities_discovered: int = 0
    research_leads_created: int = 0
    object_links_created: int = 0
    local_persistence: str = "completed"  # completed|partial|failed
    supabase_sync: str = "pending"  # synced|pending|partial|failed
    manual_review_required: bool = False
    sources: List[Dict[str, Any]] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    leads: List[Dict[str, Any]] = field(default_factory=list)


# ═══ Schema SQLite ═══════════════════════════════════════════════════════════

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS source_registry (
    canonical_id TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    original_url TEXT,
    source_title TEXT,
    institution TEXT,
    archive_name TEXT,
    author_or_creator TEXT,
    source_type TEXT,
    record_kind TEXT,
    archival_reference TEXT,
    source_identifier TEXT,
    publication_or_record_date TEXT,
    language TEXT,
    country TEXT DEFAULT 'IT',
    conflict TEXT,
    historical_period_start TEXT,
    historical_period_end TEXT,
    geographic_scope TEXT,
    access_date TEXT,
    last_verified_at TEXT,
    retrieval_method TEXT DEFAULT 'web_search',
    query_used TEXT,
    scope_relation TEXT,
    historical_relevance_score REAL DEFAULT 0,
    archival_policy TEXT DEFAULT 'metadata_only',
    rights_status TEXT DEFAULT 'unknown',
    license_name TEXT,
    license_url TEXT,
    terms_url TEXT,
    content_sha256 TEXT,
    source_cluster_id TEXT,
    primary_origin TEXT,
    fetch_status TEXT,
    http_status INTEGER,
    provenance_payload TEXT,
    local_version INTEGER DEFAULT 1,
    sync_status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_attempt_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_object_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT,
    canonical_object_id TEXT,
    relation_type TEXT NOT NULL,
    linked_claim_ids TEXT,
    evidence_fields TEXT,
    temporal_match INTEGER DEFAULT 0,
    conflict_match INTEGER DEFAULT 0,
    geographic_match INTEGER DEFAULT 0,
    linkage_method TEXT DEFAULT 'ai_suggested',
    linkage_score REAL DEFAULT 0,
    linkage_explanation TEXT,
    review_status TEXT DEFAULT 'pending',
    engine_version TEXT DEFAULT 'discovery_v1',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES source_registry(canonical_id),
    UNIQUE(source_id, object_type, object_id, relation_type)
);

CREATE TABLE IF NOT EXISTS historical_claims (
    canonical_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT,
    predicate TEXT NOT NULL,
    original_value TEXT,
    normalized_value TEXT,
    value_type TEXT,
    source_id TEXT,
    source_locator TEXT,
    extraction_method TEXT DEFAULT 'ai_extraction',
    status TEXT DEFAULT 'unverified',
    first_observed_at TEXT,
    last_evaluated_at TEXT,
    manual_review_required INTEGER DEFAULT 0,
    conflict_code TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES source_registry(canonical_id)
);

CREATE TABLE IF NOT EXISTS discovered_entities (
    canonical_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_label TEXT NOT NULL,
    aliases TEXT,
    identifiers TEXT,
    conflict TEXT,
    date_range TEXT,
    discovery_source_id TEXT,
    discovery_parent_type TEXT,
    discovery_parent_id TEXT,
    status TEXT DEFAULT 'candidate',
    review_required INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (discovery_source_id) REFERENCES source_registry(canonical_id)
);

CREATE TABLE IF NOT EXISTS research_leads (
    canonical_id TEXT PRIMARY KEY,
    subject_type TEXT,
    subject_id TEXT,
    discovered_from_source_id TEXT,
    lead_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    target_institution TEXT,
    target_url TEXT,
    suggested_queries TEXT,
    expected_evidence TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'new',
    resolution_source_ids TEXT,
    created_at TEXT NOT NULL,
    last_checked_at TEXT,
    FOREIGN KEY (discovered_from_source_id) REFERENCES source_registry(canonical_id)
);

CREATE TABLE IF NOT EXISTS sync_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT 'upsert',
    payload TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    sync_status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    last_error TEXT,
    last_attempt_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(idempotency_key)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    query TEXT,
    sources_found INTEGER DEFAULT 0,
    sources_created INTEGER DEFAULT 0,
    sources_updated INTEGER DEFAULT 0,
    claims_created INTEGER DEFAULT 0,
    entities_discovered INTEGER DEFAULT 0,
    leads_created INTEGER DEFAULT 0,
    local_persistence TEXT,
    supabase_sync TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_src_reg_url ON source_registry(canonical_url);
CREATE INDEX IF NOT EXISTS idx_src_reg_sha ON source_registry(content_sha256);
CREATE INDEX IF NOT EXISTS idx_src_reg_cluster ON source_registry(source_cluster_id);
CREATE INDEX IF NOT EXISTS idx_sol_source ON source_object_links(source_id);
CREATE INDEX IF NOT EXISTS idx_sol_object ON source_object_links(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_hc_subject ON historical_claims(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_hc_source ON historical_claims(source_id);
CREATE INDEX IF NOT EXISTS idx_hc_status ON historical_claims(status);
CREATE INDEX IF NOT EXISTS idx_de_type ON discovered_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_de_status ON discovered_entities(status);
CREATE INDEX IF NOT EXISTS idx_rl_subject ON research_leads(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_rl_status ON research_leads(status);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON sync_outbox(sync_status);
CREATE INDEX IF NOT EXISTS idx_outbox_canonical ON sync_outbox(canonical_id);
CREATE INDEX IF NOT EXISTS idx_outbox_idempotency ON sync_outbox(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_outbox_retry ON sync_outbox(sync_status, next_retry_at);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Crea le tabelle se non esistono."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _now() -> str:
    return datetime.now().isoformat()


def _now_with_offset(seconds: float) -> str:
    from datetime import timedelta
    return (datetime.now() + timedelta(seconds=seconds)).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonicalize_url(url: str) -> str:
    """Canonicalizza URL per deduplicazione."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Rimuovi fragment, normalizza host lowercase, rimuovi trailing slash
        path = parsed.path.rstrip("/") or "/"
        query = parsed.query
        # Rimuovi parametri di tracking comuni
        if query:
            params = [p for p in query.split("&")
                      if not p.startswith(("utm_", "ref=", "source="))]
            query = "&".join(params)
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(),
                          path, parsed.params, query, "")).rstrip("?")
    except Exception:
        return url.strip().lower()


# ═══ 1. Archival Decision ════════════════════════════════════════════════════

# Domain policies: archivi noti con diritti noti
_DOMAIN_POLICIES = {
    "cadutigrandeguerra.it": {
        "rights_status": "unknown",
        "policy": "metadata_only",
        "reason": "Sito di digitalizzazione Albo d'Oro, diritti non dichiarati esplicitamente.",
    },
    "difesa.it": {
        "rights_status": "public_domain",
        "policy": "structured_data",
        "reason": "Sito istituzionale Ministero Difesa, contenuti di pubblico dominio.",
    },
    "antenati.cultura.gov.it": {
        "rights_status": "open_license",
        "policy": "structured_data",
        "reason": "Portale Antenati SAN, licenza aperta CC-BY per metadati.",
    },
    "icrc.org": {
        "rights_status": "restricted",
        "policy": "metadata_only",
        "reason": "CICR: metadati consultabili, contenuti soggetti a restrizioni.",
    },
    "grandeguerre.icrc.org": {
        "rights_status": "restricted",
        "policy": "metadata_only",
        "reason": "CICR WW1: metadati consultabili, contenuti soggetti a restrizioni.",
    },
    "lessicolebi.it": {
        "rights_status": "restricted",
        "policy": "metadata_only",
        "reason": "LeBI ANRP: metadati e link, contenuti riservati.",
    },
    "arolsen-archives.org": {
        "rights_status": "restricted",
        "policy": "metadata_only",
        "reason": "Arolsen Archives: metadati consultabili, contenuti soggetti a autorizzazione.",
    },
    "archiviodistato.gov.it": {
        "rights_status": "unknown",
        "policy": "metadata_only",
        "reason": "Archivio di Stato: diritti variabili per fondo, default metadata_only.",
    },
    "sias-archivi.cultura.gov.it": {
        "rights_status": "open_license",
        "policy": "structured_data",
        "reason": "SIAS: sistema archivistico, metadati in licenza aperta.",
    },
}


def classify_archival_policy(url: str, source_title: str = "",
                             source_type: str = "") -> ArchivalDecision:
    """Classifica la policy di archiviazione per una fonte web."""
    decision = ArchivalDecision(checked_at=_now())

    if not url:
        decision.policy = "manual_review"
        decision.decision_reason = "URL mancante, revisione manuale necessaria"
        return decision

    domain = urlparse(url).netloc.lower().replace("www.", "")

    # Cerca policy per dominio esatto o suffix
    policy_data = None
    for known_domain, pdata in _DOMAIN_POLICIES.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            policy_data = pdata
            break

    if policy_data:
        decision.rights_status = policy_data["rights_status"]
        decision.policy = policy_data["policy"]
        decision.decision_reason = policy_data["reason"]
    else:
        # Sconosciuto: default metadata_only
        decision.rights_status = "unknown"
        decision.policy = "metadata_only"
        decision.decision_reason = (
            "Dominio non in registry. Policy default: metadata_only. "
            "Accessibilità pubblica non implica archiviabilità."
        )

    # Imposta flag in base alla policy
    if decision.policy == "full_content":
        decision.archival_allowed = True
        decision.metadata_allowed = True
        decision.content_download_allowed = True
        decision.extraction_allowed = True
    elif decision.policy == "structured_data":
        decision.archival_allowed = False
        decision.metadata_allowed = True
        decision.content_download_allowed = False
        decision.extraction_allowed = True
    elif decision.policy == "metadata_only":
        decision.archival_allowed = False
        decision.metadata_allowed = True
        decision.content_download_allowed = False
        decision.extraction_allowed = False
    elif decision.policy == "link_only":
        decision.archival_allowed = False
        decision.metadata_allowed = False
        decision.content_download_allowed = False
        decision.extraction_allowed = False
    elif decision.policy == "manual_review":
        decision.archival_allowed = False
        decision.metadata_allowed = True
        decision.content_download_allowed = False
        decision.extraction_allowed = False

    return decision


# ═══ 2. Deduplicazione ═══════════════════════════════════════════════════════

def _compute_source_fingerprint(url: str, title: str, institution: str = "") -> str:
    """Fingerprint per deduplicazione."""
    canon_url = _canonicalize_url(url)
    clean_title = re.sub(r"\s+", " ", (title or "").strip().lower())
    clean_inst = (institution or "").strip().lower()
    raw = f"{canon_url}|{clean_title}|{clean_inst}"
    return _sha256(raw)[:32]


def deduplicate_sources(
    sources: List[Dict[str, Any]],
    conn: sqlite3.Connection,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Deduplica fonti: ritorna (new_sources, existing_sources).

    Una fonte è duplicata se:
    - stesso URL canonicalizzato
    - stesso content_sha256
    - stessa fingerprint metadati
    - stesso source_identifier + institution
    """
    new_sources = []
    existing_sources = []

    for src in sources:
        url = src.get("url", "")
        canon_url = _canonicalize_url(url)
        title = src.get("title", "") or ""
        fingerprint = _compute_source_fingerprint(url, title, src.get("institution", ""))

        # Controlla DB locale
        existing = conn.execute(
            "SELECT canonical_id, canonical_url, source_title FROM source_registry "
            "WHERE canonical_url = ? OR content_sha256 = ? OR source_identifier = ?",
            (canon_url, fingerprint, src.get("source_identifier", ""))
        ).fetchone()

        if existing:
            src["existing_canonical_id"] = existing["canonical_id"]
            src["fingerprint"] = fingerprint
            existing_sources.append(src)
        else:
            src["fingerprint"] = fingerprint
            new_sources.append(src)

    return new_sources, existing_sources


# ═══ 3. Estrazione Claims ════════════════════════════════════════════════════

def extract_claims_from_text(
    text: str,
    subject_name: str,
    source_id: str,
) -> List[HistoricalClaim]:
    """Estrae claim strutturati dal testo narrativo della web search."""
    claims = []
    now = _now()

    # Pre-pulisci il testo da artefatti encoding comuni
    # UTF-8 mojibake: Â° = degree, Ã  = à, Ã¨ = è, etc.
    clean_text = text.replace("\u00c2\u00b0", "\u00b0")
    clean_text = clean_text.replace("\u00c3\u00a0", "\u00e0")
    clean_text = clean_text.replace("\u00c3\u00a8", "\u00e8")
    clean_text = clean_text.replace("\u00c3\u00a9", "\u00e9")
    clean_text = clean_text.replace("\u00c3\u00ac", "\u00ec")
    clean_text = clean_text.replace("\u00c3\u00b2", "\u00f2")
    clean_text = clean_text.replace("\u00c3\u00b9", "\u00f9")
    clean_text = clean_text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    clean_text = clean_text.replace("\u2013", "-").replace("\u2014", "-")
    # Rimuovi Â residuo (mojibake di byte UTF-8 interpretato come Latin-1)
    clean_text = clean_text.replace("\u00c2", "")

    # Pattern comuni nel testo di risposta
    patterns = [
        # "nato il 15 marzo 1899 a Cividate Camuno"
        (r"nato\s+(?:il\s+)?(\d{1,2}\s+\w+\s+\d{4})\s+a\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "birth_date", "date"),
        (r"nato\s+nel\s+(\d{4})\s+a\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "birth_year", "date"),
        # "morto il 16 maggio 1917"
        (r"morto\s+(?:il\s+)?(\d{1,2}\s+\w+\s+\d{4})(?:\s+a\s+([A-Z][\w\s]+?))?(?:[,\.\n]|$)",
         "death_date", "date"),
        # "reparto: 37° Reggimento Fanteria"
        (r"(?:reparto|unità|reggimento)[:\s]+([^\n,\.\(\)]+?)(?:[,\.\n]|$)",
         "military_unit", "unit"),
        # "grado: soldato/tenente/..."
        (r"grado[:\s]+([^\n,\.\(\)]+?)(?:[,\.\n]|$)",
         "rank", "text"),
        # "prigioniero a [luogo]"
        (r"prigion(?:ia|iero)\s+(?:a|nel|presso)\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "prison_location", "place"),
        # "internato a [luogo]"
        (r"internato\s+(?:a|nel|presso)\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "internment_location", "place"),
        # "figlio di [nome]"
        (r"figlio\s+di\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "father_name", "person"),
        # "matricola n. 12345"
        (r"matricola\s*(?:n\.?\s*)?(\d+)",
         "military_id", "identifier"),
        # "classe 1899"
        (r"classe\s+(\d{4})",
         "birth_class", "date"),
        # "ferito il [data]"
        (r"ferito\s+(?:il\s+)?(\d{1,2}\s+\w+\s+\d{4})",
         "wound_date", "date"),
        # "decorato con [medaglia]"
        (r"decorato\s+(?:con\s+)?([^\n,\.\(\)]+?)(?:[,\.\n]|$)",
         "decoration", "text"),
    ]

    _seen_claim_keys = set()
    for pattern, predicate, value_type in patterns:
        for match in re.finditer(pattern, clean_text, re.IGNORECASE):
            value = match.group(1).strip() if match.groups() else ""
            if not value or len(value) < 2:
                continue

            # Pulisci markdown e artefatti encoding
            value = value.replace("**", "").replace("*", "").replace("__", "")
            value = value.replace("\u00c2\u00b0", "\u00b0").replace("\u00c3 ", "\u00e0")
            value = value.replace("\u00c3\u00a8", "\u00e8").replace("\u00c3\u00a9", "\u00e9")
            value = value.replace("\u00c3\u00ac", "\u00ec").replace("\u00c3\u00b2", "\u00f2")
            value = value.replace("\u00c3\u00b9", "\u00f9").strip()
            # Salta se dopo pulizia è vuoto o troppo corto
            if len(value) < 2:
                continue

            # Filtra valori non informativi
            _GARBAGE_INDICATORS = ["|", "coincidono", "causa di morte", "e la causa", "e causa", "e vicende", "vicende militari"]
            if any(g in value.lower() for g in _GARBAGE_INDICATORS):
                continue
            # Salta se contiene piu di 2 parole per predicate che richiedono valori brevi
            if predicate in ("military_unit", "rank", "birth_class", "birth_year", "death_date", "wound_date") and len(value.split()) > 6:
                continue

            claim = HistoricalClaim(
                canonical_id=_uuid(),
                subject_type="soldier",
                subject_id=subject_name,
                predicate=predicate,
                original_value=value,
                normalized_value=value.strip().lower(),
                value_type=value_type,
                source_id=source_id,
                source_locator="web_search_text",
                extraction_method="ai_extraction",
                status="unverified",
                first_observed_at=now,
                last_evaluated_at=now,
                manual_review_required=False,
            )
            # Deduplica per predicate+value nello stesso batch
            dedup_key = (claim.predicate, claim.normalized_value)
            if dedup_key not in _seen_claim_keys:
                _seen_claim_keys.add(dedup_key)
                claims.append(claim)

    return claims


def detect_conflicting_claims(
    new_claims: List[HistoricalClaim],
    conn: sqlite3.Connection,
) -> List[HistoricalClaim]:
    """Marca claim come conflicting se esistono claim con stesso predicate e valore diverso."""
    for claim in new_claims:
        existing = conn.execute(
            "SELECT normalized_value, status FROM historical_claims "
            "WHERE subject_type = ? AND subject_id = ? AND predicate = ?",
            (claim.subject_type, claim.subject_id, claim.predicate)
        ).fetchall()

        for row in existing:
            if row["normalized_value"] != claim.normalized_value:
                claim.status = "conflicting"
                claim.manual_review_required = True
                claim.conflict_code = f"value_mismatch:{row['status']}"
                log.info("Conflict detected: %s/%s — '%s' vs '%s'",
                         claim.subject_id, claim.predicate,
                         claim.normalized_value, row["normalized_value"])
                break

    return new_claims


# ═══ 4. Entity Resolution ════════════════════════════════════════════════════

def resolve_or_create_entity(
    label: str,
    entity_type: str,
    source_id: str,
    conn: sqlite3.Connection,
    parent_type: str = "",
    parent_id: str = "",
    aliases: List[str] = None,
) -> Optional[DiscoveredEntity]:
    """Entity resolution: cerca entità esistente o crea candidato."""
    if not label or len(label) < 3:
        return None

    clean_label = re.sub(r"\s+", " ", label.strip())
    now = _now()

    # Cerca per label esatta o alias
    existing = conn.execute(
        "SELECT canonical_id, canonical_label, status FROM discovered_entities "
        "WHERE entity_type = ? AND (canonical_label = ? OR aliases LIKE ?)",
        (entity_type, clean_label, f"%{clean_label}%")
    ).fetchone()

    if existing:
        log.info("Entity resolution: '%s' → existing %s (status=%s)",
                 clean_label, existing["canonical_id"], existing["status"])
        return None  # Già esiste

    # Cerca nelle tabelle legacy (caduti_albooro, internati, etc.)
    if entity_type == "person":
        for table in ["caduti_albooro", "internati", "decorati"]:
            try:
                row = conn.execute(
                    f"SELECT id, nome, cognome FROM {table} "
                    f"WHERE (nome || ' ' || cognome) = ? OR (cognome || ' ' || nome) = ? LIMIT 1",
                    (clean_label, clean_label)
                ).fetchone()
                if row:
                    log.info("Entity resolution: '%s' → existing in %s (id=%s)",
                             clean_label, table, row["id"])
                    return None
            except sqlite3.OperationalError:
                continue

    # Crea nuova entità candidata
    entity = DiscoveredEntity(
        canonical_id=_uuid(),
        entity_type=entity_type,
        canonical_label=clean_label,
        aliases=aliases or [],
        discovery_source_id=source_id,
        discovery_parent_type=parent_type,
        discovery_parent_id=parent_id,
        status="candidate",
        review_required=True,
    )
    return entity


# ═══ 5. Research Leads ═══════════════════════════════════════════════════════

def extract_research_leads(
    text: str,
    subject_type: str,
    subject_id: str,
    source_id: str,
) -> List[ResearchLead]:
    """Estrae piste di ricerca dal testo web search."""
    leads = []
    now = _now()

    # Pattern per piste archivistiche
    archive_patterns = [
        (r"(?:Archivio di Stato di|AS di)\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "archive", "Archivio di Stato"),
        (r"(?:comune di|Comune di)\s+([A-Z][\w\s]+?)(?:[,\.\n]|$)",
         "archive", "Comune"),
        (r"(?:Ufficio Storico|USSME)\s*(?:di|del)?\s*([A-Z][\w\s]+?)?(?:[,\.\n]|$)",
         "archive", "Ufficio Storico SME"),
        (r"(?:ANRP|associazione)\s+([^\n,\.\(\)]+?)(?:[,\.\n]|$)",
         "archive", "ANRP"),
    ]

    seen_institutions = set()
    for pattern, lead_type, institution_prefix in archive_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group(1).strip() if match.groups() else ""
            if not value or len(value) < 3:
                continue

            institution_key = f"{institution_prefix}:{value.lower().strip()}"
            if institution_key in seen_institutions:
                continue
            seen_institutions.add(institution_key)

            lead = ResearchLead(
                canonical_id=_uuid(),
                subject_type=subject_type,
                subject_id=subject_id,
                discovered_from_source_id=source_id,
                lead_type=lead_type,
                title=f"Verifica presso {institution_prefix} di {value}",
                description=f"La fonte suggerisce di consultare {institution_prefix} di {value} per approfondire la ricerca su {subject_id}.",
                target_institution=f"{institution_prefix} di {value}",
                priority="medium",
                status="new",
                created_at=now,
            )
            leads.append(lead)

    # Pattern per URL diretti
    url_pattern = r'https?://[^\s\)\]"\']+'
    seen_urls = set()
    for match in re.finditer(url_pattern, text):
        url = match.group(0).rstrip(".,;)")
        domain = urlparse(url).netloc.replace("www.", "")
        if domain in ("openai.com", "github.com"):
            continue
        # Deduplica per dominio
        if domain in seen_urls:
            continue
        seen_urls.add(domain)

        lead = ResearchLead(
            canonical_id=_uuid(),
            subject_type=subject_type,
            subject_id=subject_id,
            discovered_from_source_id=source_id,
            lead_type="related_source",
            title=f"Fonte online: {domain}",
            description=f"URL scoperto durante la ricerca web: {url}",
            target_url=url,
            target_institution=domain,
            priority="low",
            status="new",
            created_at=now,
        )
        leads.append(lead)

    return leads


# ═══ 6. Persistenza Locale ════════════════════════════════════════════════════

def _persist_source(conn: sqlite3.Connection, source: SourceMetadata,
                    decision: ArchivalDecision) -> bool:
    """Persiste una fonte in source_registry."""
    now = _now()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO source_registry
            (canonical_id, canonical_url, original_url, source_title, institution,
             archive_name, author_or_creator, source_type, record_kind,
             archival_reference, source_identifier, publication_or_record_date,
             language, country, conflict, historical_period_start, historical_period_end,
             geographic_scope, access_date, last_verified_at, retrieval_method,
             query_used, scope_relation, historical_relevance_score,
             archival_policy, rights_status, license_name, license_url, terms_url,
             content_sha256, source_cluster_id, primary_origin, fetch_status,
             http_status, provenance_payload, local_version, sync_status,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (source.canonical_id, source.canonical_url, source.original_url,
             source.source_title, source.institution, source.archive_name,
             source.author_or_creator, source.source_type, source.record_kind,
             source.archival_reference, source.source_identifier,
             source.publication_or_record_date, source.language, source.country,
             source.conflict, source.historical_period_start, source.historical_period_end,
             json.dumps(source.geographic_scope, ensure_ascii=False),
             source.access_date, source.last_verified_at, source.retrieval_method,
             source.query_used, source.scope_relation, source.historical_relevance_score,
             decision.policy, decision.rights_status, decision.license_name,
             decision.license_url, decision.terms_url, source.content_sha256,
             source.source_cluster_id, source.primary_origin, source.fetch_status,
             source.http_status, json.dumps(source.provenance_payload, ensure_ascii=False),
             1, "pending", now, now)
        )
        return True
    except Exception as e:
        log.error("Failed to persist source %s: %s", source.canonical_id, e)
        return False


def _persist_claim(conn: sqlite3.Connection, claim: HistoricalClaim) -> bool:
    """Persiste un claim in historical_claims."""
    try:
        conn.execute(
            """INSERT OR REPLACE INTO historical_claims
            (canonical_id, subject_type, subject_id, predicate, original_value,
             normalized_value, value_type, source_id, source_locator,
             extraction_method, status, first_observed_at, last_evaluated_at,
             manual_review_required, conflict_code, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (claim.canonical_id, claim.subject_type, claim.subject_id,
             claim.predicate, claim.original_value, claim.normalized_value,
             claim.value_type, claim.source_id, claim.source_locator,
             claim.extraction_method, claim.status, claim.first_observed_at,
             claim.last_evaluated_at, int(claim.manual_review_required),
             getattr(claim, "conflict_code", ""), _now())
        )
        return True
    except Exception as e:
        log.error("Failed to persist claim %s: %s", claim.canonical_id, e)
        return False


def _persist_entity(conn: sqlite3.Connection, entity: DiscoveredEntity) -> bool:
    """Persiste un'entità scoperta in discovered_entities."""
    try:
        conn.execute(
            """INSERT OR REPLACE INTO discovered_entities
            (canonical_id, entity_type, canonical_label, aliases, identifiers,
             conflict, date_range, discovery_source_id, discovery_parent_type,
             discovery_parent_id, status, review_required, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entity.canonical_id, entity.entity_type, entity.canonical_label,
             json.dumps(entity.aliases, ensure_ascii=False),
             json.dumps(entity.identifiers, ensure_ascii=False),
             entity.conflict, json.dumps(entity.date_range, ensure_ascii=False),
             entity.discovery_source_id, entity.discovery_parent_type,
             entity.discovery_parent_id, entity.status,
             int(entity.review_required), _now())
        )
        return True
    except Exception as e:
        log.error("Failed to persist entity %s: %s", entity.canonical_id, e)
        return False


def _persist_lead(conn: sqlite3.Connection, lead: ResearchLead) -> bool:
    """Persiste una pista in research_leads."""
    try:
        conn.execute(
            """INSERT OR REPLACE INTO research_leads
            (canonical_id, subject_type, subject_id, discovered_from_source_id,
             lead_type, title, description, target_institution, target_url,
             suggested_queries, expected_evidence, priority, status,
             resolution_source_ids, created_at, last_checked_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (lead.canonical_id, lead.subject_type, lead.subject_id,
             lead.discovered_from_source_id, lead.lead_type, lead.title,
             lead.description, lead.target_institution, lead.target_url,
             json.dumps(lead.suggested_queries, ensure_ascii=False),
             lead.expected_evidence, lead.priority, lead.status,
             json.dumps(lead.resolution_source_ids, ensure_ascii=False),
             lead.created_at, lead.last_checked_at)
        )
        return True
    except Exception as e:
        log.error("Failed to persist lead %s: %s", lead.canonical_id, e)
        return False


def _persist_link(conn: sqlite3.Connection, link: SourceObjectLink) -> bool:
    """Persiste un collegamento fonte-oggetto (idempotente)."""
    try:
        conn.execute(
            """INSERT OR IGNORE INTO source_object_links
            (canonical_id, source_id, object_type, object_id, relation_type,
             linked_claim_ids, evidence_fields, temporal_match, conflict_match,
             geographic_match, linkage_method, linkage_score, linkage_explanation,
             review_status, engine_version, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (link.canonical_id, link.source_id, link.object_type, link.object_id,
             link.relation_type, json.dumps(link.linked_claim_ids, ensure_ascii=False),
             json.dumps(link.evidence_fields, ensure_ascii=False),
             int(link.temporal_match), int(link.conflict_match),
             int(link.geographic_match), link.linkage_method, link.linkage_score,
             link.linkage_explanation, link.review_status, "discovery_v1", _now())
        )
        return True
    except Exception as e:
        log.error("Failed to persist link %s: %s", link.canonical_id, e)
        return False


def _enqueue_sync(conn: sqlite3.Connection, canonical_id: str,
                  table_name: str, payload: dict) -> None:
    """Accoda un evento di sincronizzazione nell'outbox (idempotente).

    Usa idempotency_key = canonical_id:table_name per prevenire duplicati.
    Se esiste già un evento pending/retryable per la stessa chiave, aggiorna il payload.
    """
    idempotency_key = f"{canonical_id}:{table_name}"
    payload_json = json.dumps(payload, ensure_ascii=False)
    now = _now()

    existing = conn.execute(
        "SELECT id, sync_status FROM sync_outbox WHERE idempotency_key = ?",
        (idempotency_key,)
    ).fetchone()

    if existing:
        if existing["sync_status"] in ("pending", "retryable_error"):
            conn.execute(
                "UPDATE sync_outbox SET payload = ?, created_at = ? WHERE id = ?",
                (payload_json, now, existing["id"])
            )
        return

    conn.execute(
        """INSERT OR IGNORE INTO sync_outbox
           (canonical_id, table_name, operation, payload, idempotency_key,
            sync_status, created_at)
           VALUES (?,?, 'upsert', ?, ?, 'pending', ?)""",
        (canonical_id, table_name, payload_json, idempotency_key, now)
    )


# ═══ 7. Sync Supabase ════════════════════════════════════════════════════════

def _classify_error(err: str) -> str:
    """Classifica un errore come retryable o permanent.

    Retryable: rete, timeout, indisponibilita remota, dipendenza non risolta.
    Permanent: schema mismatch, colonna inesistente, payload invalido.
    """
    err_lower = (err or "").lower()
    permanent_indicators = [
        "column", "does not exist", "schema", "invalid input syntax",
        "foreign key", "violates", "check constraint", "duplicate key",
        "permanent", "payload",
    ]
    if any(ind in err_lower for ind in permanent_indicators):
        return "permanent_error"
    return "retryable_error"


def _compute_backoff(retry_count: int, base: float = 2.0, cap: float = 300.0) -> float:
    """Backoff esponenziale con jitter. Cap a 5 minuti."""
    import random
    delay = min(base ** retry_count, cap)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


def sync_outbox_to_supabase(conn: sqlite3.Connection, max_items: int = 50) -> Dict[str, int]:
    """Processa l'outbox: upsert idempotente su Supabase.

    Stati: pending -> syncing -> synced | retryable_error | permanent_error | conflict
    Un errore Supabase non annulla il commit SQLite ne genera HTTP 500.
    Retry con backoff e jitter. Nessun duplicato dopo ripristino.
    """
    stats = {"synced": 0, "errors": 0, "skipped": 0}

    try:
        import supabase_client as sb
    except Exception as e:
        log.warning("Supabase client non disponibile: %s", e)
        return stats

    from canonical_resolver import (
        CanonicalResolver,
        map_local_claim_to_remote,
        map_local_source_to_remote,
        map_local_entity_to_remote,
        RetryableDependencyError,
        PermanentPayloadError,
    )

    resolver = CanonicalResolver(conn)

    now = _now()
    pending = conn.execute(
        "SELECT id, canonical_id, table_name, payload, retry_count "
        "FROM sync_outbox "
        "WHERE sync_status IN ('pending', 'retryable_error') "
        "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
        "ORDER BY created_at LIMIT ?",
        (now, max_items)
    ).fetchall()

    for row in pending:
        outbox_id = row["id"]
        canonical_id = row["canonical_id"]
        table_name = row["table_name"]
        raw_payload = json.loads(row["payload"])
        retry_count = row["retry_count"]

        try:
            conn.execute(
                "UPDATE sync_outbox SET sync_status = 'syncing', last_attempt_at = ? WHERE id = ?",
                (_now(), outbox_id)
            )
            conn.commit()

            sb_mapping = {
                "source_registry": ("archive", "external_items"),
                "historical_claims": ("evidence", "claims"),
                "discovered_entities": ("core", "entities"),
            }.get(table_name)

            if not sb_mapping:
                conn.execute(
                    "UPDATE sync_outbox SET sync_status = 'permanent_error', "
                    "last_error = ? WHERE id = ?",
                    (f"No Supabase mapping for {table_name}", outbox_id)
                )
                stats["skipped"] += 1
                continue

            schema, sb_table = sb_mapping

            # ── Map payload using canonical mappers ──
            mapped_payload = None
            if table_name == "source_registry":
                from dataclasses import dataclass as _dc
                # Reconstruct minimal SourceMetadata-like object
                class _SrcMeta:
                    pass
                sm = _SrcMeta()
                sm.canonical_id = canonical_id
                sm.canonical_url = raw_payload.get("canonical_url", "")
                sm.original_url = raw_payload.get("original_url", "")
                sm.source_title = raw_payload.get("title", "")
                sm.source_type = raw_payload.get("item_type", "web_source")
                sm.content_sha256 = raw_payload.get("metadata_hash", "")
                sm.http_status = raw_payload.get("http_status")
                sm.last_verified_at = raw_payload.get("last_verified_at")
                sm.language = raw_payload.get("language", "")
                sm.archival_reference = raw_payload.get("reference_code", "")
                sm.publication_or_record_date = raw_payload.get("date_text", "")
                mapped_payload = map_local_source_to_remote(sm)

            elif table_name == "historical_claims":
                class _Claim:
                    pass
                c = _Claim()
                c.canonical_id = canonical_id
                c.subject_type = raw_payload.get("subject_type", "")
                c.subject_id = raw_payload.get("subject_id", "")
                c.predicate = raw_payload.get("predicate", "")
                c.normalized_value = raw_payload.get("normalized_value", raw_payload.get("object_value", ""))
                c.original_value = raw_payload.get("original_value", raw_payload.get("object_value", ""))
                c.value_type = raw_payload.get("value_type", "")
                c.status = raw_payload.get("claim_status", "unverified")
                c.extraction_method = raw_payload.get("extraction_method", "ai_extraction")
                c.source_id = raw_payload.get("source_id", "")
                c.source_locator = raw_payload.get("source_locator", "")
                c.conflict_code = raw_payload.get("conflict_code", "")
                try:
                    mapped_payload, _evidence = map_local_claim_to_remote(c, resolver)
                except RetryableDependencyError as e:
                    conn.execute(
                        "UPDATE sync_outbox SET sync_status = 'retryable_error', "
                        "last_error = ?, retry_count = retry_count + 1, "
                        "last_attempt_at = ?, next_retry_at = ? WHERE id = ?",
                        (str(e)[:200], _now(),
                         _now_with_offset(_compute_backoff(retry_count)),
                         outbox_id)
                    )
                    stats["errors"] += 1
                    continue
                except PermanentPayloadError as e:
                    conn.execute(
                        "UPDATE sync_outbox SET sync_status = 'permanent_error', "
                        "last_error = ? WHERE id = ?",
                        (str(e)[:200], outbox_id)
                    )
                    stats["skipped"] += 1
                    continue

            elif table_name == "discovered_entities":
                class _Entity:
                    pass
                e = _Entity()
                e.canonical_id = canonical_id
                e.entity_type = raw_payload.get("entity_type", "")
                e.canonical_label = raw_payload.get("canonical_name", "")
                e.status = raw_payload.get("verification_status", "candidate")
                e.discovery_parent_type = raw_payload.get("source_table", "")
                e.discovery_parent_id = raw_payload.get("source_id", "")
                mapped_payload = map_local_entity_to_remote(e)

            if mapped_payload is None:
                conn.execute(
                    "UPDATE sync_outbox SET sync_status = 'permanent_error', "
                    "last_error = ? WHERE id = ?",
                    ("Mapping returned None", outbox_id)
                )
                stats["skipped"] += 1
                continue

            result = sb.insert_batch_schema(schema, sb_table, [mapped_payload], on_conflict="ignore")

            if result.get("ok"):
                conn.execute(
                    "UPDATE sync_outbox SET sync_status = 'synced', last_attempt_at = ? WHERE id = ?",
                    (_now(), outbox_id)
                )
                if table_name == "source_registry":
                    conn.execute(
                        "UPDATE source_registry SET sync_status = 'synced' WHERE canonical_id = ?",
                        (canonical_id,)
                    )
                stats["synced"] += 1
            else:
                err = result.get("error", "unknown error")
                error_type = _classify_error(err)
                if error_type == "permanent_error":
                    conn.execute(
                        f"UPDATE sync_outbox SET sync_status = 'permanent_error', "
                        "last_error = ? WHERE id = ?",
                        (str(err)[:200], outbox_id)
                    )
                    stats["skipped"] += 1
                else:
                    backoff = _compute_backoff(retry_count)
                    conn.execute(
                        "UPDATE sync_outbox SET sync_status = 'retryable_error', "
                        "last_error = ?, retry_count = retry_count + 1, "
                        "last_attempt_at = ?, next_retry_at = ? WHERE id = ?",
                        (str(err)[:200], _now(),
                         _now_with_offset(backoff), outbox_id)
                    )
                    if table_name == "source_registry":
                        conn.execute(
                            "UPDATE source_registry SET sync_status = 'retryable_error', "
                            "last_error = ? WHERE canonical_id = ?",
                            (str(err)[:200], canonical_id)
                        )
                    stats["errors"] += 1

        except Exception as e:
            log.warning("Sync failed for %s: %s", canonical_id, e)
            err_str = str(e)[:200]
            error_type = _classify_error(err_str)
            backoff = _compute_backoff(retry_count) if error_type == "retryable_error" else 0
            conn.execute(
                f"UPDATE sync_outbox SET sync_status = '{error_type}', "
                "last_error = ?, retry_count = retry_count + 1, "
                "last_attempt_at = ?, next_retry_at = ? WHERE id = ?",
                (err_str, _now(),
                 _now_with_offset(backoff) if backoff else None,
                 outbox_id)
            )
            stats["errors"] += 1

    conn.commit()
    return stats


# ═══ 7b. Person Name Validation ═════════════════════════════════════════════

# Blocklist di parole che sono titoli di sezione, acronimi, o non-nomi
_NON_NAME_BLOCKLIST = {
    "CONFERMA CANDIDATI", "NUOVI DATI", "FONTI CONSULTATE",
    "AFFIDABILITA", "SUGGERIMENTI", "DATI TROVATI",
    "PISTA FAMILIARE", "ESITO SINTETICO", "RICERCA ARCHIVIA",
    "CONFRONTO DATI", "SCHEDA RIASSUNTIVA", "NOTE STORICHE",
    "FONTI ARCHIVISTICHE", "DOCUMENTAZIONE",
    "ANAGRAFE", "STATO CIVILE", "ARCHIVIO DI STATO",
    "REGISTRO", "MATRICOLA", "RUOLO",
    "WWI", "WWII", "WW1", "WW2", "IMI", "ANRP",
    "CROCE ROSSA", "COMITEE", "INTERNATIONAL",
    "ARCHIVIO CENTRALE", "STATO MAGGIORE",
    "MINISTERO DELLA DIFESA", "MINISTERO DELLA GUERRA",
    "REGIO ESERCITO", "REGIO MARINE",
    "DATA NASCITA", "DATA MORTE", "DATA CATTURA",
    "LUOGO NASCITA", "LUOGO MORTE",
    "NUMERO MATRICOLA", "GRADO MILITARE",
    "UNITA MILITARE", "CAMPO PRIGIONIA",
    "FONTE PRIMARIA", "FONTE SECONDARIA",
    "EVIDENZA DIRETTA", "EVIDENZA INDIRETTA",
}

# Parole singole che non sono nomi propri (anche se in maiuscolo)
_NON_NAME_WORDS = {
    "IL", "LO", "LA", "I", "GLI", "LE", "UN", "UNO", "UNA",
    "DI", "DA", "DEL", "DELLA", "DEI", "DELLE", "DALLE", "DALLA",
    "IN", "CON", "SU", "PER", "TRA", "FRA",
    "CHE", "CUI", "NON", "MA", "SE", "O", "ED",
    "SONO", "STATO", "STATA", "ERANO", "SARÀ",
    "NATO", "NATA", "MORTO", "MORTA",
    "CITTÀ", "COMUNE", "PROVINCIA", "REGIONE",
    "ITALIA", "FRANCIA", "GERMANIA", "AUSTRIA",
    "ESERCITO", "MARINA", "AVIAZIONE",
    "FANTE", "ALPINO", "BERSAGLIERE", "ARTIGLIERE",
    "CAPORALE", "SERGENTE", "TENENTE", "CAPITANO", "MAGGIORE",
    "COLONNELLO", "GENERALE", "MARESCIALLO",
    "FRONTE", "GUERRA", "BATTAGLIA", "MISSIONE",
    "PRIGIONIA", "INTERNAMENTO", "DEPORTAZIONE",
    "CAMPO", "OSPEDALE", "CIMITERO", "SACRARIO",
    "DOCUMENTO", "CERTIFICATO", "ELENCO", "REGISTRO",
    "FONTI", "DATI", "NOTE", "SCHEDA",
    "RICERCA", "ANALISI", "STUDIO",
    "CONFERMA", "VERIFICA", "CONTROLLO",
    "RISULTATO", "EVIDENZA", "PROVA",
}

# Pattern per nomi italiani validi: 2-4 token, iniziale maiuscola o tutto maiuscolo
_VALID_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{2,}|[A-Z]{3,})"
    r"(?:\s+([A-Z][a-z]{2,}|[A-Z]{3,}))"
    r"(?:\s+([A-Z][a-z]{2,}|[A-Z]{3,}))?"
    r"(?:\s+([A-Z][a-z]{2,}|[A-Z]{3,}))?"
    r"\b"
)


def _is_valid_person_name(name: str) -> bool:
    """Validazione multi-livello per nomi di persona.

    Livelli:
    1. Lunghezza: 5-60 caratteri
    2. Token: 2-4 parole
    3. Nessuna parola nella blocklist
    4. Almeno un token > 3 caratteri (non solo acronimi)
    5. Non contiene cifre, punteggiatura strana, o caratteri di encoding
    6. Non è un titolo di sezione o etichetta
    """
    if not name or len(name) < 5 or len(name) > 60:
        return False

    tokens = name.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return False

    # Blocklist check (full name)
    if name.upper() in _NON_NAME_BLOCKLIST:
        return False

    # Blocklist check (each token)
    for t in tokens:
        if t.upper() in _NON_NAME_WORDS:
            return False
        if t.upper() in _NON_NAME_BLOCKLIST:
            return False

    # Almeno un token > 3 caratteri (esclude acronimi puri)
    if not any(len(t) > 3 for t in tokens):
        return False

    # No digits, no weird chars
    if re.search(r"[\d\.\,\;\:\!\?\(\)\[\]\{\}\"\'\/\\\<\>\#\@\*\+\=\|\&]", name):
        return False

    # No encoding artifacts
    if any(c in name for c in "ÂÃ€âÃ"):
        return False

    # No all-uppercase single tokens > 8 chars (likely section headers or acronyms)
    if all(t.isupper() and len(t) > 8 for t in tokens):
        return False

    return True


def _extract_person_names(text: str, subject_name: str) -> list:
    """Estrai nomi di persona dal testo con validazione multi-livello.

    Evita falsi positivi come titoli di sezione, acronimi, parole comuni.
    Non estrae il subject_name stesso.
    """
    found = set()
    subject_upper = subject_name.upper().strip()

    for match in _VALID_NAME_PATTERN.finditer(text):
        # Ricostruisci il nome completo dai gruppi
        groups = [g for g in match.groups() if g]
        if len(groups) < 2:
            continue
        full_name = " ".join(groups)

        # Salta il subject stesso
        if full_name.upper() == subject_upper:
            continue

        # Valida
        if _is_valid_person_name(full_name):
            found.add(full_name)

    return sorted(found)

def process_web_search_results(
    web_search_results: Dict[str, Any],
    subject_name: str,
    subject_type: str = "soldier",
    subject_id: str = "",
    query_used: str = "",
) -> DiscoveryPersistenceResult:
    """Pipeline completa: classifica, deduplica, estrae, persiste, sincronizza.

    Args:
        web_search_results: dict from _web_search_enrich (text, sources, usage)
        subject_name: nome del soggetto della ricerca (es. "DAMIOLI GIOVANNI")
        subject_type: tipo oggetto (soldier, event, etc.)
        subject_id: ID dell'oggetto nel DB locale (se esiste)
        query_used: query originale usata per la web search

    Returns:
        DiscoveryPersistenceResult con statistiche e dettagli
    """
    from database import get_conn

    result = DiscoveryPersistenceResult()
    run_id = _uuid()
    now = _now()

    conn = get_conn()
    _ensure_schema(conn)

    text = web_search_results.get("text", "")
    # Pre-clean encoding artifacts for all downstream extraction
    clean_text = text.replace("\u00c2\u00b0", "\u00b0")
    clean_text = clean_text.replace("\u00c3\u00a0", "\u00e0")
    clean_text = clean_text.replace("\u00c3\u00a8", "\u00e8")
    clean_text = clean_text.replace("\u00c3\u00a9", "\u00e9")
    clean_text = clean_text.replace("\u00c3\u00ac", "\u00ec")
    clean_text = clean_text.replace("\u00c3\u00b2", "\u00f2")
    clean_text = clean_text.replace("\u00c3\u00b9", "\u00f9")
    clean_text = clean_text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    clean_text = clean_text.replace("\u2013", "-").replace("\u2014", "-")
    clean_text = clean_text.replace("\u00c2", "")
    raw_sources = web_search_results.get("sources", [])
    result.sources_discovered = len(raw_sources)

    log.info("DiscoveryPersistence: processing %d sources for '%s'",
             len(raw_sources), subject_name)

    # ── 1. Deduplicazione ──
    new_sources, existing_sources = deduplicate_sources(raw_sources, conn)
    result.existing_sources_updated = len(existing_sources)

    # ── 2. Per ogni nuova fonte: classifica, persisti, estrai ──
    all_claims: List[HistoricalClaim] = []
    all_entities: List[DiscoveredEntity] = []
    all_leads: List[ResearchLead] = []
    all_links: List[SourceObjectLink] = []

    for src in new_sources:
        url = src.get("url", "")
        title = src.get("title", "") or url

        # Classifica archival policy
        decision = classify_archival_policy(url, title)

        # Crea SourceMetadata
        source_meta = SourceMetadata(
            canonical_id=_uuid(),
            canonical_url=_canonicalize_url(url),
            original_url=url,
            source_title=title,
            institution=urlparse(url).netloc.replace("www.", ""),
            retrieval_method="web_search",
            query_used=query_used,
            access_date=now,
            last_verified_at=now,
            content_sha256=src.get("fingerprint", ""),
            archival_policy=decision.policy,
            rights_status=decision.rights_status,
            provenance_payload={
                "search_actions": web_search_results.get("search_actions", []),
                "usage": web_search_results.get("usage", {}),
            },
        )

        # Persisti fonte
        if _persist_source(conn, source_meta, decision):
            result.new_sources_created += 1
            if decision.policy == "full_content":
                result.full_content_archived += 1
            elif decision.policy == "metadata_only":
                result.metadata_only_saved += 1
            elif decision.policy == "link_only":
                result.link_only_saved += 1

            # Crea link fonte → oggetto
            link = SourceObjectLink(
                canonical_id=_uuid(),
                source_id=source_meta.canonical_id,
                object_type=subject_type,
                object_id=subject_id,
                relation_type="discovery_lead",
                linkage_method="ai_suggested",
                linkage_score=0.5,
                linkage_explanation=f"Fonte scoperta via web search per '{subject_name}'",
            )
            all_links.append(link)

            # Classifica la fonte per tipo di evidenza storica
            from canonical_resolver import classify_source
            source_class = classify_source(url, title)
            source_meta.scope_relation = source_class

            # Estrai claims dal testo (usando il testo completo, non per-fonte)
            # I claims vengono estratti una sola volta dal testo completo

            # Enqueue sync
            _enqueue_sync(conn, source_meta.canonical_id, "source_registry", {
                "canonical_url": source_meta.canonical_url,
                "title": source_meta.source_title,
                "provider_code": "web_search",
                "external_id": source_meta.canonical_id,
                "item_type": "web_source",
                "canonical_url": source_meta.canonical_url,
            })

        result.sources.append({
            "canonical_id": source_meta.canonical_id,
            "url": url,
            "title": title,
            "archival_policy": decision.policy,
            "rights_status": decision.rights_status,
            "decision_reason": decision.decision_reason,
            "local_persisted": True,
            "sync_status": "pending",
        })

    # ── 3. Estrai claims dal testo completo ──
    if text:
        # Usa il primo source_id creato, o crea un source "virtuale"
        virtual_source_id = new_sources[0].get("canonical_id") if new_sources else _uuid()
        if not new_sources:
            # Crea fonte virtuale per il testo web search
            virtual_source = SourceMetadata(
                canonical_id=virtual_source_id,
                canonical_url="",
                original_url="",
                source_title=f"Web search results for '{subject_name}'",
                retrieval_method="web_search",
                query_used=query_used,
                access_date=now,
                archival_policy="metadata_only",
                rights_status="unknown",
            )
            _persist_source(conn, virtual_source, ArchivalDecision(
                policy="metadata_only", rights_status="unknown",
                decision_reason="Fonte virtuale per testo web search",
                checked_at=now,
            ))
            result.new_sources_created += 1
            result.metadata_only_saved += 1

        claims = extract_claims_from_text(clean_text, subject_name, virtual_source_id)
        claims = detect_conflicting_claims(claims, conn)

        for claim in claims:
            if _persist_claim(conn, claim):
                result.new_claims_created += 1
                if claim.status == "conflicting":
                    result.conflicting_claims_created += 1
                    result.manual_review_required = True

                _enqueue_sync(conn, claim.canonical_id, "historical_claims", {
                    "subject_type": claim.subject_type,
                    "subject_id": claim.subject_id,
                    "predicate": claim.predicate,
                    "object_value": claim.original_value,
                    "normalized_value": claim.normalized_value or claim.original_value,
                    "value_type": claim.value_type,
                    "claim_status": claim.status,
                    "extraction_method": claim.extraction_method,
                    "source_id": claim.source_id,
                    "source_locator": getattr(claim, 'source_locator', ''),
                    "conflict_code": getattr(claim, 'conflict_code', ''),
                })

                result.claims.append({
                    "canonical_id": claim.canonical_id,
                    "predicate": claim.predicate,
                    "value": claim.original_value,
                    "value_type": claim.value_type,
                    "status": claim.status,
                    "manual_review_required": claim.manual_review_required,
                })

        all_claims.extend(claims)

    # ── 4. Estrai entità dal testo ──
    if clean_text:
        # Cerca nomi di persone con validazione multi-livello
        persons_found = _extract_person_names(clean_text, subject_name)
        for full_name in persons_found:
            entity = resolve_or_create_entity(
                full_name, "person", virtual_source_id, conn,
                parent_type=subject_type, parent_id=subject_id,
            )
            if entity:
                if _persist_entity(conn, entity):
                    result.new_entities_discovered += 1
                    result.entities.append({
                        "canonical_id": entity.canonical_id,
                        "label": entity.canonical_label,
                        "type": entity.entity_type,
                        "status": entity.status,
                    })
                    _enqueue_sync(conn, entity.canonical_id, "discovered_entities", {
                        "entity_type": entity.entity_type,
                        "canonical_name": entity.canonical_label,
                        "verification_status": entity.status,
                        "source_table": entity.discovery_parent_type or "",
                        "source_id": entity.discovery_parent_id or "",
                    })
                all_entities.append(entity)

        # Cerca unità militari (Pattern: N° Reggimento/Battaglione)
        unit_pattern = r"(\d+°?\s*(?:Reggimento|Battaglione|Brigata|Divisione)\s+\w+)"
        for match in re.finditer(unit_pattern, clean_text):
            unit_name = match.group(1).strip()
            entity = resolve_or_create_entity(
                unit_name, "unit", virtual_source_id, conn,
                parent_type=subject_type, parent_id=subject_id,
            )
            if entity:
                if _persist_entity(conn, entity):
                    result.new_entities_discovered += 1
                    result.entities.append({
                        "canonical_id": entity.canonical_id,
                        "label": entity.canonical_label,
                        "type": entity.entity_type,
                        "status": entity.status,
                    })
                all_entities.append(entity)

        # Cerca luoghi (Pattern: Cividate Camuno, etc.)
        place_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:Camuno|Valcamonica|al Piano)"
        for match in re.finditer(place_pattern, clean_text):
            place_name = match.group(0).strip()
            entity = resolve_or_create_entity(
                place_name, "place", virtual_source_id, conn,
                parent_type=subject_type, parent_id=subject_id,
            )
            if entity:
                if _persist_entity(conn, entity):
                    result.new_entities_discovered += 1
                    result.entities.append({
                        "canonical_id": entity.canonical_id,
                        "label": entity.canonical_label,
                        "type": entity.entity_type,
                        "status": entity.status,
                    })
                all_entities.append(entity)

    # ── 5. Estrai piste di ricerca ──
    if text:
        leads = extract_research_leads(clean_text, subject_type, subject_id, virtual_source_id)
        for lead in leads:
            if _persist_lead(conn, lead):
                result.research_leads_created += 1
                result.leads.append({
                    "canonical_id": lead.canonical_id,
                    "title": lead.title,
                    "lead_type": lead.lead_type,
                    "target_institution": lead.target_institution,
                    "target_url": lead.target_url,
                    "priority": lead.priority,
                })
        all_leads.extend(leads)

    # ── 6. Persisti link ──
    for link in all_links:
        if _persist_link(conn, link):
            result.object_links_created += 1

    # ── 7. Commit locale ──
    try:
        conn.commit()
        result.local_persistence = "completed"
    except Exception as e:
        log.error("Local persistence failed: %s", e)
        result.local_persistence = "failed"
        conn.rollback()

    # ── 8. Sync Supabase (best-effort, non bloccante) ──
    try:
        sync_stats = sync_outbox_to_supabase(conn)
        if sync_stats["errors"] > 0 and sync_stats["synced"] == 0:
            result.supabase_sync = "failed"
        elif sync_stats["errors"] > 0:
            result.supabase_sync = "partial"
        elif sync_stats["synced"] > 0:
            result.supabase_sync = "synced"
        else:
            result.supabase_sync = "pending"
    except Exception as e:
        log.warning("Supabase sync failed (non-blocking): %s", e)
        result.supabase_sync = "failed"

    # ── 9. Registra ingestion run ──
    try:
        conn.execute(
            """INSERT INTO ingestion_runs
            (run_id, query, sources_found, sources_created, sources_updated,
             claims_created, entities_discovered, leads_created,
             local_persistence, supabase_sync, started_at, completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, query_used, result.sources_discovered,
             result.new_sources_created, result.existing_sources_updated,
             result.new_claims_created, result.new_entities_discovered,
             result.research_leads_created, result.local_persistence,
             result.supabase_sync, now, _now())
        )
        conn.commit()
    except Exception:
        pass

    log.info("DiscoveryPersistence: completed — sources=%d claims=%d entities=%d leads=%d sync=%s",
             result.new_sources_created, result.new_claims_created,
             result.new_entities_discovered, result.research_leads_created,
             result.supabase_sync)

    return result
