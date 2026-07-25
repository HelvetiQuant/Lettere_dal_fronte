"""ia_pipeline.py — Pipeline completa di integrazione Internet Archive.

Orchestra:
1. Discovery: ricerca item IA via advancedsearch.php con filtri evento
2. Metadata: recupero metadati dettagliati via metadata/{identifier}
3. Evaluation: valutazione storica candidati (ia_evaluation)
4. Asset selection: selezione miglior file (ia_locator)
5. Locator: estrazione pagina/passaggio (ia_locator)
6. Ingestion preview: precompila form con metadati reali
7. Confirm: archivia in fonti_indice + archivio_documenti + event_links
8. Reconstruct: genera claim/evidence per evento

Usa componenti esistenti:
- source_providers.providers.ProviderInternetArchive (search/metadata)
- event_resolver.resolve_event, get_event_by_id
- ia_evaluation.evaluate_candidates
- ia_locator.locate_passage, select_best_asset
- archivio_documenti.upsert_documenti
- claim_service.create_claim, add_evidence
- database.get_conn (fonti_indice, event_links)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from database import DB_PATH
from event_resolver import resolve_event, get_event_by_id
from ia_evaluation import evaluate_candidates, CandidateEvaluation
from ia_locator import locate_passage, select_best_asset, PageLocator, AssetSelection
from archivio_documenti import upsert_documenti, create_schema as create_doc_schema

logger = logging.getLogger("ia_pipeline")

EDB = Path(__file__).parent / "eventi_1gm.db"
IA_BASE = "https://archive.org"
FETCH_TIMEOUT = 30
USER_AGENT = "IMI-Extractor/1.0 (research; contact: imi-extractor@example.org)"


# ─── Data models ─────────────────────────────────────────────────────────────

@dataclass
class DiscoveryResult:
    """Risultato della fase di discovery IA."""
    event_name: str
    event_id: Optional[int]
    query_used: str
    items: List[Dict[str, Any]]
    evaluations: List[CandidateEvaluation]
    total_found: int
    accepted: int = 0
    candidate: int = 0
    rejected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name,
            "event_id": self.event_id,
            "query_used": self.query_used,
            "total_found": self.total_found,
            "accepted": self.accepted,
            "candidate": self.candidate,
            "rejected": self.rejected,
            "items": self.items,
            "evaluations": [e.to_dict() for e in self.evaluations],
        }


@dataclass
class ItemAnalysis:
    """Analisi dettagliata di un item IA."""
    identifier: str
    title: str
    metadata: Dict[str, Any]
    asset: AssetSelection
    locator: PageLocator
    evaluation: CandidateEvaluation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "metadata": _compact_metadata(self.metadata),
            "asset": self.asset.to_dict(),
            "locator": self.locator.to_dict(),
            "evaluation": self.evaluation.to_dict(),
        }


@dataclass
class IngestionPreview:
    """Form precompilato per conferma ingestion."""
    identifier: str
    title: str
    description: str
    creator: str
    date_text: str
    year_start: Optional[int]
    year_end: Optional[int]
    place: str
    language: str
    rights: str
    source_url: str
    catalog_url: str
    thumbnail_url: str
    page_start: Optional[int]
    page_end: Optional[int]
    snippet: str
    locator_source: str
    locator_confidence: float
    detected_conflict: str
    overall_score: float
    evaluation_status: str
    event_id: Optional[int]
    event_name: str
    suggested_link_type: str = "fonte_archivistica"
    suggested_war: str = "WWI"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "description": self.description,
            "creator": self.creator,
            "date_text": self.date_text,
            "year_start": self.year_start,
            "year_end": self.year_end,
            "place": self.place,
            "language": self.language,
            "rights": self.rights,
            "source_url": self.source_url,
            "catalog_url": self.catalog_url,
            "thumbnail_url": self.thumbnail_url,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "snippet": self.snippet,
            "locator_source": self.locator_source,
            "locator_confidence": self.locator_confidence,
            "detected_conflict": self.detected_conflict,
            "overall_score": self.overall_score,
            "evaluation_status": self.evaluation_status,
            "event_id": self.event_id,
            "event_name": self.event_name,
            "suggested_link_type": self.suggested_link_type,
            "suggested_war": self.suggested_war,
        }


@dataclass
class ConfirmResult:
    """Risultato della conferma di ingestion."""
    identifier: str
    fonte_id: Optional[int]
    documento_id: Optional[int]
    event_link_id: Optional[int]
    claim_ids: List[str] = field(default_factory=list)
    success: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "fonte_id": self.fonte_id,
            "documento_id": self.documento_id,
            "event_link_id": self.event_link_id,
            "claim_ids": self.claim_ids,
            "success": self.success,
            "message": self.message,
        }


# ─── Phase 1: Discovery ──────────────────────────────────────────────────────

def discover(
    event_query: str,
    max_results: int = 20,
    war_filter: str = None,
) -> DiscoveryResult:
    """Scopre item IA pertinenti a un evento.

    Args:
        event_query: nome evento (es. "Battaglia di Caporetto")
        max_results: numero massimo di risultati
        war_filter: "WWI" o "WW2" per filtrare per conflitto

    Returns:
        DiscoveryResult con items, valutazioni e statistiche
    """
    # Risolvi evento
    resolution = resolve_event(event_query)
    event_id = resolution.canonical_id if resolution.is_event else None
    event_name = resolution.canonical or event_query

    event_data = get_event_by_id(event_id) if event_id else {}
    if not event_data:
        event_data = {"nome": event_name, "conflict": war_filter or "WWI"}

    if war_filter:
        event_data["conflict"] = war_filter
    elif "conflict" not in event_data:
        # Infer from dates
        start = event_data.get("data_inizio", "")
        if "191" in str(start):
            event_data["conflict"] = "WWI"
        elif "194" in str(start) or "193" in str(start):
            event_data["conflict"] = "WW2"
        else:
            event_data["conflict"] = "WWI"

    # Build query for IA advanced search
    conflict = event_data.get("conflict", "WWI")
    conflict_range = CONFLICT_RANGES.get(conflict, (1914, 1918))

    # Build search query
    search_terms = [event_name]
    for kw in event_data.get("keywords", [])[:5]:
        search_terms.append(kw)
    for alias in event_data.get("aliases", [])[:3]:
        search_terms.append(alias)

    query_str = " OR ".join(f'"{t}"' for t in search_terms if t)
    ia_query = f'({query_str}) AND mediatype:(texts) AND date:[{conflict_range[0]} TO {conflict_range[1]}]'

    # Execute search
    items = _ia_advanced_search(ia_query, rows=max_results)

    # Also try with broader query if not enough results
    if len(items) < 5:
        broader = f'({event_name}) AND mediatype:(texts)'
        more = _ia_advanced_search(broader, rows=max_results - len(items))
        seen_ids = {i.get("identifier") for i in items}
        for m in more:
            if m.get("identifier") not in seen_ids:
                items.append(m)

    # Evaluate candidates
    evaluations = evaluate_candidates(items, event_data)

    accepted = sum(1 for e in evaluations if e.status == "accepted")
    candidate = sum(1 for e in evaluations if e.status == "candidate")
    rejected = sum(1 for e in evaluations if e.status == "rejected")

    return DiscoveryResult(
        event_name=event_name,
        event_id=event_id,
        query_used=ia_query,
        items=items,
        evaluations=evaluations,
        total_found=len(items),
        accepted=accepted,
        candidate=candidate,
        rejected=rejected,
    )


# ─── Phase 2: Item analysis ──────────────────────────────────────────────────

def analyze_item(
    identifier: str,
    event_query: str = "",
) -> ItemAnalysis:
    """Analizza un item IA: metadati, asset, locator, valutazione.

    Args:
        identifier: IA identifier
        event_query: nome evento per valutazione e locator

    Returns:
        ItemAnalysis con tutti i dettagli
    """
    # Fetch metadata
    metadata = _ia_get_metadata(identifier)

    # Resolve event for evaluation
    event_data = {}
    if event_query:
        resolution = resolve_event(event_query)
        if resolution.is_event and resolution.canonical_id:
            event_data = get_event_by_id(resolution.canonical_id) or {}
            event_data.setdefault("nome", resolution.canonical)
        else:
            event_data = {"nome": event_query}
    else:
        event_data = {"nome": ""}

    # Evaluate
    item_meta = _extract_search_fields(metadata)
    evaluation = evaluate_candidate(item_meta, event_data, metadata.get("server", {}).get("files", []))

    # Asset selection
    files = metadata.get("server", {}).get("files", [])
    asset = select_best_asset(identifier, files)

    # Locator
    search_terms = []
    search_terms.extend(event_data.get("keywords", []))
    search_terms.extend(event_data.get("aliases", []))
    if event_data.get("nome"):
        search_terms.append(event_data["nome"])
    if event_data.get("luogo"):
        search_terms.append(event_data["luogo"])
    search_terms = [t for t in search_terms if t and len(t) >= 4]

    locator = locate_passage(identifier, search_terms, metadata)

    title = metadata.get("metadata", {}).get("title", "") or item_meta.get("title", "")

    return ItemAnalysis(
        identifier=identifier,
        title=title,
        metadata=metadata,
        asset=asset,
        locator=locator,
        evaluation=evaluation,
    )


# ─── Phase 3: Ingestion preview ──────────────────────────────────────────────

def build_ingestion_preview(
    identifier: str,
    event_query: str,
) -> IngestionPreview:
    """Precompila il form di ingestion con metadati reali.

    Args:
        identifier: IA identifier
        event_query: nome evento

    Returns:
        IngestionPreview con tutti i campi precompilati
    """
    analysis = analyze_item(identifier, event_query)
    meta = analysis.metadata.get("metadata", {})

    # Parse years
    date_str = meta.get("date", "") or meta.get("year", "")
    years = []
    import re
    for m in re.finditer(r"\d{4}", str(date_str)):
        years.append(int(m.group()))
    year_start = years[0] if years else None
    year_end = years[-1] if len(years) > 1 else year_start

    # Determine war
    war = analysis.evaluation.detected_conflict
    if war == "unknown":
        if year_start and 1914 <= year_start <= 1918:
            war = "WWI"
        elif year_start and 1939 <= year_start <= 1946:
            war = "WW2"
        else:
            war = "WWI"

    # Resolve event
    resolution = resolve_event(event_query)
    event_id = resolution.canonical_id if resolution.is_event else None
    event_name = resolution.canonical or event_query

    # Build URLs
    catalog_url = f"{IA_BASE}/details/{identifier}"
    source_url = analysis.asset.best_url or catalog_url
    thumbnail = ""
    if meta.get("image"):
        thumbnail = f"{IA_BASE}/services/img/{identifier}"

    # Description (truncate)
    desc = meta.get("description", "")
    if isinstance(desc, list):
        desc = " ".join(str(d) for d in desc)
    desc = str(desc)[:500]

    # Creator
    creator = meta.get("creator", "")
    if isinstance(creator, list):
        creator = ", ".join(str(c) for c in creator)

    # Language
    lang = meta.get("language", "")
    if isinstance(lang, list):
        lang = ", ".join(str(l) for l in lang)

    # Rights
    rights = meta.get("rights", "") or meta.get("licenseurl", "")
    if isinstance(rights, list):
        rights = ", ".join(str(r) for r in rights)

    # Place
    place = meta.get("coverage", "") or meta.get("spatial", "")
    if isinstance(place, list):
        place = ", ".join(str(p) for p in place)

    # Link type suggestion
    link_type = "fonte_archivistica"
    if analysis.asset.has_ocr:
        link_type = "fonte_archivistica"
    elif analysis.asset.best_format == "pdf":
        link_type = "documento"

    return IngestionPreview(
        identifier=identifier,
        title=analysis.title or meta.get("title", ""),
        description=desc,
        creator=creator,
        date_text=str(date_str),
        year_start=year_start,
        year_end=year_end,
        place=place,
        language=lang,
        rights=rights,
        source_url=source_url,
        catalog_url=catalog_url,
        thumbnail_url=thumbnail,
        page_start=analysis.locator.page_start,
        page_end=analysis.locator.page_end,
        snippet=analysis.locator.snippet,
        locator_source=analysis.locator.source,
        locator_confidence=analysis.locator.confidence,
        detected_conflict=analysis.evaluation.detected_conflict,
        overall_score=analysis.evaluation.overall_score,
        evaluation_status=analysis.evaluation.status,
        event_id=event_id,
        event_name=event_name,
        suggested_link_type=link_type,
        suggested_war=war,
    )


# ─── Phase 4: Confirm ingestion ──────────────────────────────────────────────

def confirm_ingestion(
    identifier: str,
    event_id: int,
    preview_data: Dict[str, Any],
    create_claim: bool = True,
) -> ConfirmResult:
    """Conferma l'ingestion: archivia in DB e collega all'evento.

    1. Upsert in fonti_indice (metadati fonte)
    2. Upsert in archivio_documenti (metadati documento)
    3. Crea event_link (evento → fonte/documento)
    4. Crea claim se richiesto

    Args:
        identifier: IA identifier
        event_id: ID evento in eventi_1gm
        preview_data: dati dal form IngestionPreview (eventualmente modificati)
        create_claim: se True, crea claim atomico

    Returns:
        ConfirmResult con IDs creati
    """
    result = ConfirmResult(identifier=identifier)
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            # 1. Upsert in fonti_indice
            fonte_id = _upsert_fonti_indice(conn, identifier, preview_data, now)
            result.fonte_id = fonte_id

            # 2. Upsert in archivio_documenti
            doc_id = _upsert_archivio_doc(conn, identifier, preview_data, now)
            result.documento_id = doc_id

            # 3. Create event_link
            link_id = _create_event_link(
                conn, event_id, fonte_id, doc_id, preview_data, now
            )
            result.event_link_id = link_id

            conn.commit()
        finally:
            conn.close()

        # 4. Create claim if requested
        if create_claim and fonte_id:
            claim_ids = _create_ia_claim(identifier, event_id, preview_data, fonte_id)
            result.claim_ids = claim_ids

        result.success = True
        result.message = f"Ingestion completata: fonte_id={fonte_id}, doc_id={doc_id}, link_id={link_id}"
    except Exception as e:
        result.success = False
        result.message = f"Errore ingestion: {e}"
        logger.error("Confirm ingestion failed for %s: %s", identifier, e)

    return result


# ─── Phase 5: Reconstruct ────────────────────────────────────────────────────

def reconstruct_from_ia(
    event_query: str,
    max_sources: int = 10,
) -> Dict[str, Any]:
    """Genera ricostruzione evento basata su fonti IA accettate.

    1. Discovery + evaluation
    2. Per ogni item accepted/candidate: analysis + locator
    3. Estrai claim dalle fonti IA
    4. Ritorna pacchetto strutturato

    Args:
        event_query: nome evento
        max_sources: numero massimo fonti da analizzare

    Returns:
        Dict con sources, claims, locators, evaluations
    """
    discovery = discover(event_query, max_results=max_sources)

    sources = []
    claims = []
    locators = []

    for item in discovery.items[:max_sources]:
        identifier = item.get("identifier", "")
        if not identifier:
            continue

        # Find evaluation for this item
        ev = next((e for e in discovery.evaluations if e.identifier == identifier), None)
        if not ev or ev.status == "rejected":
            continue

        try:
            analysis = analyze_item(identifier, event_query)
            sources.append({
                "identifier": identifier,
                "title": analysis.title,
                "url": f"{IA_BASE}/details/{identifier}",
                "evaluation": ev.to_dict(),
                "asset": analysis.asset.to_dict(),
                "locator": analysis.locator.to_dict(),
            })

            if analysis.locator.snippet:
                locators.append(analysis.locator.to_dict())

            # Extract simple claims from snippet
            if analysis.locator.snippet:
                import re
                snippet = analysis.locator.snippet
                dates = re.findall(r"\b(\d{1,2}[\s\-]*(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4})\b", snippet, re.IGNORECASE)
                dates += re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", snippet)
                for d in set(dates):
                    claims.append({
                        "claim_type": "date",
                        "value": d,
                        "source": f"IA-{identifier}",
                        "confidence": "media" if ev.status == "accepted" else "bassa",
                    })

        except Exception as e:
            logger.warning("Analysis failed for %s: %s", identifier, e)
            continue

    return {
        "event_name": discovery.event_name,
        "event_id": discovery.event_id,
        "total_sources": len(sources),
        "sources": sources,
        "claims": claims,
        "locators": locators,
        "discovery_stats": {
            "total_found": discovery.total_found,
            "accepted": discovery.accepted,
            "candidate": discovery.candidate,
            "rejected": discovery.rejected,
        },
    }


# ─── IA API helpers ──────────────────────────────────────────────────────────

CONFLICT_RANGES = {
    "WWI": (1914, 1918),
    "WW2": (1939, 1946),
    "interwar": (1919, 1938),
}


def _ia_advanced_search(query: str, rows: int = 20) -> List[Dict[str, Any]]:
    """Esegue advancedsearch.php e ritorna items."""
    try:
        resp = requests.get(
            f"{IA_BASE}/advancedsearch.php",
            params={
                "q": query,
                "fl[]": ["identifier", "title", "description", "date", "mediatype",
                         "collection", "language", "downloads", "subject"],
                "rows": rows,
                "output": "json",
                "sort": "downloads desc",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=FETCH_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("response", {}).get("docs", [])
            return docs
    except Exception as e:
        logger.warning("IA advanced search failed: %s", e)
    return []


def _ia_get_metadata(identifier: str) -> Dict[str, Any]:
    """Recupera metadati completi via metadata API."""
    try:
        resp = requests.get(
            f"{IA_BASE}/metadata/{identifier}",
            headers={"User-Agent": USER_AGENT},
            timeout=FETCH_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning("IA metadata fetch failed for %s: %s", identifier, e)
    return {"metadata": {}, "server": {"files": []}}


def _extract_search_fields(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae campi compatibili con evaluate_candidate dai metadati IA."""
    meta = metadata.get("metadata", {})
    files = metadata.get("server", {}).get("files", [])

    def _first(val):
        if isinstance(val, list):
            return val[0] if val else ""
        return val or ""

    return {
        "identifier": metadata.get("id", meta.get("identifier", "")),
        "title": _first(meta.get("title")),
        "description": _first(meta.get("description")),
        "date": _first(meta.get("date")),
        "mediatype": _first(meta.get("mediatype")),
        "collection": _first(meta.get("collection")),
        "language": _first(meta.get("language")),
        "downloads": meta.get("downloads", 0),
        "subject": meta.get("subject", ""),
        "creator": _first(meta.get("creator")),
    }


def _compact_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Compatta metadati per output API (rimuovi file list enorme)."""
    compact = dict(metadata)
    if "server" in compact and "files" in compact["server"]:
        compact["server"] = {
            "files_count": len(compact["server"]["files"]),
            "files_sample": compact["server"]["files"][:5],
        }
    return compact


# ─── DB helpers ──────────────────────────────────────────────────────────────

def _upsert_fonti_indice(
    conn: sqlite3.Connection,
    identifier: str,
    data: Dict[str, Any],
    now: str,
) -> Optional[int]:
    """Upsert in fonti_indice."""
    try:
        conn.execute(
            """
            INSERT INTO fonti_indice (
                archivio, titolo, description, url_catalogo, url_file,
                data_inizio, data_fine, luogo, tipo_fonte, language,
                ente_titolare, rights, fetch_status, last_checked_at,
                page_start, page_end, snippet, hash_se_disponibile
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_catalogo) DO UPDATE SET
                titolo=excluded.titolo, description=excluded.description,
                data_inizio=excluded.data_inizio, data_fine=excluded.data_fine,
                luogo=excluded.luogo, last_checked_at=excluded.last_checked_at,
                page_start=excluded.page_start, page_end=excluded.page_end,
                snippet=excluded.snippet
            """,
            (
                "Internet Archive",
                data.get("title", ""),
                data.get("description", ""),
                f"{IA_BASE}/details/{identifier}",
                data.get("source_url", ""),
                str(data.get("year_start") or ""),
                str(data.get("year_end") or ""),
                data.get("place", ""),
                "digitized_document",
                data.get("language", ""),
                "Internet Archive",
                data.get("rights", ""),
                "metadata_only",
                now,
                data.get("page_start"),
                data.get("page_end"),
                data.get("snippet", ""),
                None,
            ),
        )
        row = conn.execute(
            "SELECT id FROM fonti_indice WHERE url_catalogo=?",
            (f"{IA_BASE}/details/{identifier}",),
        ).fetchone()
        return row["id"] if row else None
    except Exception as e:
        # Table might not have url_catalogo conflict — try simpler insert
        logger.debug("fonti_indice upsert: %s", e)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO fonti_indice (
                    archivio, titolo, description, url_catalogo, url_file,
                    data_inizio, data_fine, luogo, tipo_fonte, language,
                    ente_titolare, rights, fetch_status, last_checked_at,
                    page_start, page_end, snippet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Internet Archive", data.get("title", ""), data.get("description", ""),
                    f"{IA_BASE}/details/{identifier}", data.get("source_url", ""),
                    str(data.get("year_start") or ""), str(data.get("year_end") or ""),
                    data.get("place", ""), "digitized_document", data.get("language", ""),
                    "Internet Archive", data.get("rights", ""), "metadata_only", now,
                    data.get("page_start"), data.get("page_end"), data.get("snippet", ""),
                ),
            )
            row = conn.execute(
                "SELECT id FROM fonti_indice WHERE url_catalogo=?",
                (f"{IA_BASE}/details/{identifier}",),
            ).fetchone()
            return row["id"] if row else None
        except Exception as e2:
            logger.error("fonti_indice insert failed: %s", e2)
            return None


def _upsert_archivio_doc(
    conn: sqlite3.Connection,
    identifier: str,
    data: Dict[str, Any],
    now: str,
) -> Optional[int]:
    """Upsert in archivio_documenti."""
    try:
        create_doc_schema(conn)
        rows = [{
            "provider": "InternetArchive",
            "external_id": identifier,
            "doc_type": "documento",
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "creator": data.get("creator", ""),
            "date_text": data.get("date_text", ""),
            "year_start": data.get("year_start"),
            "year_end": data.get("year_end"),
            "place": data.get("place", ""),
            "war": data.get("suggested_war", "WWI"),
            "language": data.get("language", ""),
            "rights": data.get("rights", ""),
            "source_url": data.get("source_url", f"{IA_BASE}/details/{identifier}"),
            "thumbnail_url": data.get("thumbnail_url", ""),
            "provider_collection": "Internet Archive",
            "raw_json": json.dumps(data, ensure_ascii=False),
        }]
        upsert_documenti(conn, rows)
        row = conn.execute(
            "SELECT rowid FROM archivio_documenti WHERE provider='InternetArchive' AND external_id=?",
            (identifier,),
        ).fetchone()
        return row["rowid"] if row else None
    except Exception as e:
        logger.error("archivio_documenti upsert failed: %s", e)
        return None


def _create_event_link(
    conn: sqlite3.Connection,
    event_id: int,
    fonte_id: Optional[int],
    doc_id: Optional[int],
    data: Dict[str, Any],
    now: str,
) -> Optional[int]:
    """Crea link tra evento e fonte/documento in event_links."""
    if not EDB.exists():
        return None

    link_type = data.get("suggested_link_type", "fonte_archivistica")
    target_id = doc_id if link_type == "documento" and doc_id else fonte_id
    if not target_id:
        return None

    try:
        ev_conn = sqlite3.connect(str(EDB), timeout=30)
        ev_conn.row_factory = sqlite3.Row
        try:
            # Check if link already exists
            existing = ev_conn.execute(
                "SELECT id FROM event_links WHERE evento_id=? AND link_type=? AND target_id=?",
                (event_id, link_type, target_id),
            ).fetchone()
            if existing:
                return existing["id"]

            ev_conn.execute(
                """
                INSERT INTO event_links (evento_id, link_type, target_id, match_value, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, link_type, target_id,
                    data.get("title", "")[:200],
                    data.get("overall_score", 0.5),
                    now,
                ),
            )
            ev_conn.commit()
            row = ev_conn.execute(
                "SELECT id FROM event_links WHERE evento_id=? AND link_type=? AND target_id=?",
                (event_id, link_type, target_id),
            ).fetchone()
            return row["id"] if row else None
        finally:
            ev_conn.close()
    except Exception as e:
        logger.error("event_link creation failed: %s", e)
        return None


def _create_ia_claim(
    identifier: str,
    event_id: int,
    data: Dict[str, Any],
    fonte_id: int,
) -> List[str]:
    """Crea claim atomico per la fonte IA."""
    claim_ids = []
    try:
        from claim_service import create_claim, add_evidence

        claim_text = f"Fonte Internet Archive confermata: {data.get('title', identifier)}"
        claim = create_claim(
            text=claim_text,
            claim_type="source_attestation",
            value=identifier,
            source_id=fonte_id,
            source_table="fonti_indice",
            event_id=event_id,
            confidence="media" if data.get("evaluation_status") == "accepted" else "bassa",
        )
        if claim:
            claim_ids.append(claim.claim_id)

            # Add evidence
            add_evidence(
                claim_id=claim.claim_id,
                source_url=data.get("source_url", f"{IA_BASE}/details/{identifier}"),
                excerpt=data.get("snippet", ""),
                page_start=data.get("page_start"),
                page_end=data.get("page_end"),
            )
    except Exception as e:
        logger.warning("Claim creation failed for %s: %s", identifier, e)

    return claim_ids
