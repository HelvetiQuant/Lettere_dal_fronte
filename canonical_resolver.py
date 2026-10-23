"""Canonical entity resolver — mappa ID locali a core.entities.id (Supabase).

Principi:
- Un ID locale non è automaticamente un UUID canonico remoto
- Riutilizza mapping esistente prima di creare nuove entità
- Le nuove entità sono sempre 'candidate' a meno che non ci sia verifica
- L'AI non può assegnare 'verified', 'confirmed' o 'accepted'
- Il fingerprint è deterministico e stabile tra processi
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

log = logging.getLogger("canonical_resolver")


# ─── Subject type normalization ──────────────────────────────────────────────

_SUBJECT_TYPE_MAP = {
    "soldier": "person",
    "person": "person",
    "event": "event",
    "fact": "fact",
    "place": "place",
    "military_unit": "military_unit",
    "unit": "military_unit",
    "document": "document",
    "archive_record": "archive_record",
}

VALID_SUBJECT_TYPES = set(_SUBJECT_TYPE_MAP.values())


def normalize_subject_type(raw: str) -> str:
    """Normalizza il tipo del soggetto in un valore canonico."""
    return _SUBJECT_TYPE_MAP.get(raw.lower().strip(), raw.lower().strip())


# ─── Stable ID generation ────────────────────────────────────────────────────

def generate_stable_id(
    entity_type: str,
    canonical_name: str,
    source_system: str = "",
    source_id: str = "",
) -> str:
    """Genera uno stable_id deterministico per core.entities.

    Usa SHA-256 di una serializzazione canonica. Stabile tra processi,
    retry e macchine diverse. Non usa hash() di Python.
    """
    raw = json.dumps({
        "entity_type": entity_type.lower().strip(),
        "canonical_name": canonical_name.strip(),
        "source_system": source_system.strip(),
        "source_id": str(source_id).strip(),
    }, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ─── Claim fingerprint ───────────────────────────────────────────────────────

def claim_fingerprint(
    subject_entity_stable_id: str,
    predicate: str,
    normalized_value: str,
    value_type: str = "",
) -> str:
    """Fingerprint deterministico per deduplicazione claim.

    La fonte non deve rendere diverso lo stesso claim.
    Più fonti indipendenti devono collegarsi allo stesso claim.
    """
    raw = json.dumps({
        "subject": subject_entity_stable_id.strip(),
        "predicate": predicate.strip().lower(),
        "value": normalized_value.strip().lower(),
        "value_type": value_type.strip().lower(),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ─── Canonical entity resolver ───────────────────────────────────────────────

@dataclass
class CanonicalEntity:
    stable_id: str
    entity_type: str
    canonical_name: str
    verification_status: str = "candidate"
    source_system: str = ""
    source_table: str = ""
    source_id: str = ""
    remote_id: Optional[int] = None


class CanonicalResolver:
    """Risolve entità locali a entità canoniche Supabase (core.entities).

    Usa core.entity_mapping per persistere i mapping locale→remoto.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._cache: Dict[str, CanonicalEntity] = {}

    def resolve_canonical_entity(
        self,
        subject_type: str,
        local_subject_id: str,
        source_system: str = "sqlite",
        local_table: str = "",
        canonical_name: str = "",
    ) -> Optional[CanonicalEntity]:
        """Risolve un soggetto locale in un'entità canonica.

        Steps:
        1. Normalizza il tipo del soggetto
        2. Cerca mapping locale-remoto già persistito (SQLite cache)
        3. Se trovato, riutilizza il canonical_id
        4. Se non trovato, crea una nuova entità candidate
        5. Conserva il mapping per retry successivi

        Returns:
            CanonicalEntity se risolta, None se impossibile.
        """
        norm_type = normalize_subject_type(subject_type)
        if norm_type not in VALID_SUBJECT_TYPES:
            log.warning("Unknown subject type: %s -> %s", subject_type, norm_type)
            return None

        if not local_subject_id and not canonical_name:
            return None

        # Nome canonico: usa canonical_name se fornito, altrimenti local_subject_id
        name = canonical_name or str(local_subject_id).strip()
        if not name or len(name) < 2:
            return None

        # Genera stable_id deterministico
        stable_id = generate_stable_id(
            entity_type=norm_type,
            canonical_name=name,
            source_system=source_system,
            source_id=str(local_subject_id),
        )

        # Cache in-memory
        cache_key = f"{source_system}:{local_table}:{local_subject_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Cerca mapping locale nella tabella SQLite discovered_entities
        # (che funge da cache locale prima del sync Supabase)
        existing = self._lookup_local_entity(stable_id)
        if existing:
            entity = CanonicalEntity(
                stable_id=stable_id,
                entity_type=norm_type,
                canonical_name=name,
                verification_status=existing.get("status", "candidate"),
                source_system=source_system,
                source_table=local_table,
                source_id=str(local_subject_id),
                remote_id=existing.get("remote_id"),
            )
            self._cache[cache_key] = entity
            return entity

        # Cerca nelle tabelle legacy per match
        legacy_match = self._lookup_legacy(norm_type, name, local_table)
        if legacy_match:
            entity = CanonicalEntity(
                stable_id=stable_id,
                entity_type=norm_type,
                canonical_name=name,
                verification_status="candidate",
                source_system=source_system,
                source_table=legacy_match["table"],
                source_id=str(legacy_match["id"]),
            )
            self._cache[cache_key] = entity
            return entity

        # Nuova entità candidata
        entity = CanonicalEntity(
            stable_id=stable_id,
            entity_type=norm_type,
            canonical_name=name,
            verification_status="candidate",
            source_system=source_system,
            source_table=local_table,
            source_id=str(local_subject_id),
        )
        self._cache[cache_key] = entity
        return entity

    def _lookup_local_entity(self, stable_id: str) -> Optional[Dict]:
        """Cerca in discovered_entities per stable_id."""
        try:
            row = self.conn.execute(
                "SELECT canonical_id, status FROM discovered_entities "
                "WHERE canonical_id = ?",
                (stable_id,)
            ).fetchone()
            if row:
                return {"status": row["status"], "remote_id": None}
        except sqlite3.OperationalError:
            pass
        return None

    def _lookup_legacy(
        self, entity_type: str, name: str, local_table: str
    ) -> Optional[Dict]:
        """Cerca nelle tabelle legacy per match di nome."""
        if entity_type != "person":
            return None

        clean = re.sub(r"\s+", " ", name.strip())
        for table in ["caduti_albooro", "internati", "decorati"]:
            try:
                if table == "caduti_albooro":
                    row = self.conn.execute(
                        f"SELECT id FROM {table} WHERE nominativo = ? LIMIT 1",
                        (clean,)
                    ).fetchone()
                else:
                    parts = clean.split(" ", 1)
                    cog = parts[0]
                    nom = parts[1] if len(parts) > 1 else ""
                    row = self.conn.execute(
                        f"SELECT id FROM {table} "
                        f"WHERE cognome = ? AND nome = ? LIMIT 1",
                        (cog, nom)
                    ).fetchone()
                if row:
                    return {"table": table, "id": row["id"]}
            except sqlite3.OperationalError:
                continue
        return None


# ─── Claim mapper (SQLite → Supabase evidence.claims) ────────────────────────

# Colonne ammesse in evidence.claims (dal schema 003)
CLAIMS_ALLOWED_COLUMNS = {
    "stable_id",
    "subject_entity_id",
    "predicate",
    "object_entity_id",
    "object_value",
    "claim_status",
    "conflict_code",
    "valid_from",
    "valid_to",
    "date_precision",
    "extraction_method",
    "pipeline_run_id",
    "algorithm_version",
}

# Mapping stati locali → stati remoti ammessi
CLAIM_STATUS_MAP = {
    "unverified": "discovered",
    "corroborated": "supported",
    "conflicting": "conflicting",
    "verified": "verified",
    "rejected": "rejected",
}

# L'AI non può assegnare questi stati
AI_FORBIDDEN_STATUSES = {"verified", "confirmed", "accepted"}


def cap_ai_status(status: str) -> str:
    """L'Ai può solo proporre, non verificare."""
    if status in AI_FORBIDDEN_STATUSES:
        return "discovered"
    return CLAIM_STATUS_MAP.get(status, "discovered")


def normalize_predicate(predicate: str) -> str:
    """Normalizza il predicato del claim."""
    return predicate.strip().lower().replace(" ", "_")


def normalize_claim_value(value: str, value_type: str) -> str:
    """Normalizza il valore del claim."""
    v = value.strip()
    if value_type == "date":
        v = re.sub(r"[^\d\-/]", "", v)
    elif value_type in ("place", "person"):
        v = re.sub(r"\s+", " ", v).strip()
    return v


class RetryableDependencyError(Exception):
    """Errore retryable: dipendenza non ancora risolta."""
    pass


class PermanentPayloadError(Exception):
    """Errore permanente: payload non valido o schema mismatch."""
    pass


def map_local_claim_to_remote(
    local_claim,
    resolver: CanonicalResolver,
    source_system: str = "sqlite",
) -> Tuple[Dict[str, Any], list]:
    """Mappa un HistoricalClaim locale in payload per evidence.claims.

    Returns:
        (claim_payload, evidence_links)

    Raises:
        RetryableDependencyError: subject entity non ancora risolta
        PermanentPayloadError: payload non valido
    """
    entity = resolver.resolve_canonical_entity(
        subject_type=local_claim.subject_type,
        local_subject_id=local_claim.subject_id,
        source_system=source_system,
    )

    if entity is None:
        raise RetryableDependencyError(
            f"Canonical subject entity unresolved for "
            f"{local_claim.subject_type}/{local_claim.subject_id}"
        )

    predicate = normalize_predicate(local_claim.predicate)
    norm_value = normalize_claim_value(
        local_claim.normalized_value or local_claim.original_value,
        local_claim.value_type,
    )

    # Validazione
    if not predicate:
        raise PermanentPayloadError("Empty predicate after normalization")
    if not norm_value:
        raise PermanentPayloadError("Empty value after normalization")

    claim_payload = {
        "stable_id": local_claim.canonical_id,
        "subject_entity_id": entity.remote_id,  # BIGINT FK
        "predicate": predicate,
        "object_value": norm_value,
        "claim_status": cap_ai_status(local_claim.status),
        "extraction_method": local_claim.extraction_method,
        "algorithm_version": "discovery_v1",
    }

    # Aggiungi conflict_code se presente
    if getattr(local_claim, "conflict_code", ""):
        claim_payload["conflict_code"] = local_claim.conflict_code

    # Rimuovi colonne non nel schema remoto
    clean_payload = {
        k: v for k, v in claim_payload.items()
        if k in CLAIMS_ALLOWED_COLUMNS and v is not None
    }

    # Evidence links (collegamento claim → fonte)
    evidence_links = []
    if local_claim.source_id:
        evidence_links.append({
            "stable_id": hashlib.sha256(
                f"{local_claim.canonical_id}:{local_claim.source_id}".encode()
            ).hexdigest()[:32],
            "claim_stable_id": local_claim.canonical_id,
            "source_item_stable_id": local_claim.source_id,
            "evidence_type": "ai_extracted",
            "text_span": local_claim.source_locator or "",
        })

    return clean_payload, evidence_links


# ─── Source mapper (SQLite → Supabase archive.external_items) ────────────────

EXTERNAL_ITEMS_ALLOWED_COLUMNS = {
    "stable_id",
    "provider_code",
    "external_id",
    "item_type",
    "title",
    "description",
    "canonical_url",
    "date_text",
    "date_from",
    "date_to",
    "language",
    "reference_code",
    "review_status",
    "metadata_hash",
    "http_status",
    "last_verified_at",
}


def map_local_source_to_remote(source_meta) -> Dict[str, Any]:
    """Mappa un SourceMetadata locale in payload per archive.external_items.

    Raises:
        PermanentPayloadError: payload non valido
    """
    if not source_meta.canonical_url and not source_meta.original_url:
        raise PermanentPayloadError("Source without URL")

    url = source_meta.canonical_url or source_meta.original_url

    payload = {
        "stable_id": source_meta.canonical_id,
        "provider_code": "web_search",
        "external_id": source_meta.canonical_id,
        "item_type": source_meta.source_type or "web_source",
        "title": source_meta.source_title or "",
        "canonical_url": url,
        "review_status": "candidate",
        "metadata_hash": source_meta.content_sha256 or "",
        "http_status": source_meta.http_status,
        "last_verified_at": source_meta.last_verified_at or None,
    }

    # Aggiungi campi opzionali solo se valorizzati
    if source_meta.language:
        payload["language"] = source_meta.language
    if source_meta.archival_reference:
        payload["reference_code"] = source_meta.archival_reference
    if source_meta.publication_or_record_date:
        payload["date_text"] = source_meta.publication_or_record_date

    # Filtra solo colonne ammesse
    clean = {
        k: v for k, v in payload.items()
        if k in EXTERNAL_ITEMS_ALLOWED_COLUMNS and v is not None
    }

    return clean


# ─── Entity mapper (SQLite → Supabase core.entities) ─────────────────────────

ENTITIES_ALLOWED_COLUMNS = {
    "stable_id",
    "entity_type",
    "canonical_name",
    "verification_status",
    "confidence",
    "source_system",
    "source_table",
    "source_id",
}


def map_local_entity_to_remote(entity) -> Dict[str, Any]:
    """Mappa un DiscoveredEntity locale in payload per core.entities.

    L'AI non può assegnare 'verified' o 'confirmed'.
    """
    status = entity.status
    if status in AI_FORBIDDEN_STATUSES:
        status = "candidate"

    payload = {
        "stable_id": entity.canonical_id,
        "entity_type": entity.entity_type,
        "canonical_name": entity.canonical_label,
        "verification_status": status,
        "source_system": "discovery_persistence",
        "source_table": entity.discovery_parent_type or "",
        "source_id": entity.discovery_parent_id or "",
    }

    clean = {
        k: v for k, v in payload.items()
        if k in ENTITIES_ALLOWED_COLUMNS and v is not None
    }

    return clean


# ─── Source classification ───────────────────────────────────────────────────

SOURCE_CLASSIFICATIONS = {
    "direct_historical_evidence",
    "historical_context",
    "geographic_context",
    "discovery_only",
    "out_of_scope",
}

# Domini che sono chiaramente non storici
_NON_HISTORICAL_DOMAINS = {
    "booking.com", "tripadvisor.it", "tripadvisor.com",
    "google.com", "google.it", "facebook.com",
    "youtube.com", "instagram.com", "twitter.com",
    "amazon.it", "amazon.com", "ebay.it",
    "meteo.it", "ilmeteo.net", "3bmeteo.com",
    "trenitalia.com", "trenitalia.it",
}

# Domini che sono pagine di ricerca, non fonti
_SEARCH_PAGE_INDICATORS = {
    "/search", "/ricerca", "/results", "?q=", "&q=",
    "/find", "/cerca",
}


def classify_source(url: str, title: str = "") -> str:
    """Classifica una fonte web per tipo di evidenza storica.

    Returns:
        Una di: direct_historical_evidence, historical_context,
        geographic_context, discovery_only, out_of_scope
    """
    if not url:
        return "discovery_only"

    domain = urlparse(url).netloc.lower().replace("www.", "")
    path = urlparse(url).path.lower()
    query = urlparse(url).query.lower()

    # Out of scope: domini chiaramente non storici
    if domain in _NON_HISTORICAL_DOMAINS:
        return "out_of_scope"

    # Discovery only: pagine di ricerca
    if any(ind in path or ind in query for ind in _SEARCH_PAGE_INDICATORS):
        return "discovery_only"

    # Geographic context: pagine puramente geografiche/comunali
    _GEO_INDICATORS = ["comune.", "provincia.", "regione.", "turismo.", "visit"]
    if any(ind in domain for ind in _GEO_INDICATORS):
        if not any(kw in (title or "").lower() for kw in
                    ["guerra", "fronte", "battaglia", "militare", "soldato",
                     "caduto", "prigioniero", "internato", "monumento",
                     "memoriale", "sacrario"]):
            return "geographic_context"

    # Historical context: enciclopedie generiche
    _ENCYCLOPEDIA_DOMAINS = {"wikipedia.org", "treccani.it", "britannica.com"}
    if domain in _ENCYCLOPEDIA_DOMAINS:
        return "historical_context"

    # Default: discovery_only (conservativo)
    return "discovery_only"
