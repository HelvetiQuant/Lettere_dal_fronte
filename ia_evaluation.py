"""ia_evaluation.py — Valutazione storica di candidati Internet Archive.

Valuta ogni item IA restituito dalla discovery per:
1. Compatibilità di conflitto (WWI vs WWII vs altro)
2. Compatibilità temporale (sovrapposizione date)
3. Compatibilità geografica (luogo evento vs metadati item)
4. Pertinenza storiografica (token evento in titolo/descrizione)
5. Qualità del documento (OCR disponibile, mediatype, downloads)

Assegna uno score 0.0–1.0 e uno stato: accepted | candidate | rejected.

Non inventa dati mancanti: se non può valutare, marca come candidate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ─── Conflitti e periodi ─────────────────────────────────────────────────────

CONFLICT_RANGES: Dict[str, Tuple[int, int]] = {
    "WWI": (1914, 1918),
    "WW2": (1939, 1946),
    "interwar": (1919, 1938),
    "pre_ww1": (1900, 1913),
    "post_ww2": (1947, 1960),
}

# Parole chiave per identificare il conflitto nei metadati IA
WWI_KEYWORDS = {
    "world war", "first world war", "great war", "1914", "1915", "1916",
    "1917", "1918", "wwi", "ww1", "kaiser", "habsburg", "isonzo",
    "caporetto", "piave", "carso", "grappa", "trench", "trincea",
    "prigionia 1915", "prigionia 1916", "prigionia 1917", "prigionia 1918",
    "soldati italiani", "regio esercito", "fronte italiano",
}

WW2_KEYWORDS = {
    "world war ii", "second world war", "wwii", "ww2", "1940", "1941",
    "1942", "1943", "1944", "1945", "nazi", "third reich", "hitler",
    "musolini", "armistizio", "8 settembre", "internati militari",
    "imi", "arbeitskommando", "mauthausen", "stalag", "oflag",
    "cefalonia", "acqui", "armir", "russia 1942", "don 1942",
    "cassino", "tobruk", "africa settentrionale",
}


@dataclass
class CandidateEvaluation:
    """Risultato della valutazione di un candidato IA."""
    identifier: str
    title: str
    detected_conflict: str  # "WWI" | "WW2" | "interwar" | "unknown"
    temporal_compatible: bool
    geographic_compatible: bool
    relevance_score: float
    quality_score: float
    overall_score: float
    status: str  # "accepted" | "candidate" | "rejected"
    reasons: List[str] = field(default_factory=list)
    war_mismatch: bool = False
    is_search_page: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "detected_conflict": self.detected_conflict,
            "temporal_compatible": self.temporal_compatible,
            "geographic_compatible": self.geographic_compatible,
            "relevance_score": round(self.relevance_score, 3),
            "quality_score": round(self.quality_score, 3),
            "overall_score": round(self.overall_score, 3),
            "status": self.status,
            "reasons": self.reasons,
            "war_mismatch": self.war_mismatch,
            "is_search_page": self.is_search_page,
        }


def _detect_conflict(metadata: Dict[str, Any]) -> str:
    """Rileva il conflitto dai metadati IA (titolo, descrizione, date, collection)."""
    text_parts = []
    for key in ("title", "description", "collection", "subject", "creator"):
        val = metadata.get(key, "")
        if isinstance(val, list):
            text_parts.extend(str(v) for v in val)
        elif val:
            text_parts.append(str(val))
    text = " ".join(text_parts).lower()

    # Date extraction
    date_str = str(metadata.get("date", "") or metadata.get("year", "") or "")
    years = re.findall(r"\b(19\d{2})\b", date_str)
    if not years:
        years = re.findall(r"\b(19\d{2})\b", text)

    wwi_score = sum(1 for kw in WWI_KEYWORDS if kw in text)
    ww2_score = sum(1 for kw in WW2_KEYWORDS if kw in ww2_keywords_lower(text))

    if ww2_score > wwi_score:
        return "WW2"
    if wwi_score > ww2_score:
        return "WWI"

    for y in years:
        yi = int(y)
        if 1914 <= yi <= 1918:
            return "WWI"
        if 1939 <= yi <= 1946:
            return "WW2"
        if 1919 <= yi <= 1938:
            return "interwar"

    return "unknown"


def ww2_keywords_lower(text: str) -> str:
    return text


def _temporal_compatibility(
    event_start: str, event_end: str, item_date: str
) -> Tuple[bool, str]:
    """Verifica sovrapposizione temporale tra evento e item IA."""
    if not event_start or not item_date:
        return True, "Dati temporali insufficienti — non escluso"

    ev_years = re.findall(r"\d{4}", event_start)
    item_years = re.findall(r"\d{4}", str(item_date))

    if not ev_years or not item_years:
        return True, "Date non parseable — non escluso"

    ev_start_y = int(ev_years[0])
    ev_end_y = int(ev_years[-1]) if event_end and re.findall(r"\d{4}", event_end) else ev_start_y
    item_y = int(item_years[0])

    if ev_start_y <= item_y <= ev_end_y:
        return True, f"Anno item ({item_y}) nel range evento ({ev_start_y}-{ev_end_y})"
    if abs(item_y - ev_start_y) <= 2:
        return True, f"Anno item ({item_y}) vicino all'evento (±2 anni)"
    return False, f"Anno item ({item_y}) fuori range evento ({ev_start_y}-{ev_end_y})"


def _geographic_compatibility(
    event_luogo: str, item_metadata: Dict[str, Any]
) -> Tuple[bool, str]:
    """Verifica compatibilità geografica."""
    if not event_luogo:
        return True, "Luogo evento mancante — non escluso"

    ev_tokens = set(
        t.lower() for t in re.findall(r"\w{4,}", event_luogo)
        if t.lower() not in {"della", "delle", "degli", "dello", "monte", "settore"}
    )
    if not ev_tokens:
        return True, "Token geografici evento insufficienti — non escluso"

    text_parts = []
    for key in ("title", "description", "subject", "coverage", "spatial"):
        val = item_metadata.get(key, "")
        if isinstance(val, list):
            text_parts.extend(str(v) for v in val)
        elif val:
            text_parts.append(str(val))
    item_text = " ".join(text_parts).lower()

    if not item_text.strip():
        return True, "Metadati geografici item vuoti — non escluso"

    matches = ev_tokens & set(re.findall(r"\w{4,}", item_text))
    if matches:
        return True, f"Token geografici condivisi: {', '.join(matches)}"
    return False, f"Nessun token geografico condiviso tra evento e item"


def _relevance_score(
    event_name: str, event_keywords: List[str], event_aliases: List[str],
    item_metadata: Dict[str, Any],
) -> Tuple[float, str]:
    """Score di pertinenza storiografica."""
    score = 0.0
    text_parts = []
    for key in ("title", "description", "subject"):
        val = item_metadata.get(key, "")
        if isinstance(val, list):
            text_parts.extend(str(v) for v in val)
        elif val:
            text_parts.append(str(val))
    text = " ".join(text_parts).lower()
    title = str(item_metadata.get("title", "")).lower()

    # Match su keywords evento
    for kw in event_keywords:
        kw_l = kw.lower()
        if kw_l in title:
            score += 0.15
        elif kw_l in text:
            score += 0.08

    # Match su aliases
    for alias in event_aliases:
        alias_l = alias.lower()
        if len(alias_l) >= 4 and alias_l in title:
            score += 0.12
        elif len(alias_l) >= 4 and alias_l in text:
            score += 0.06

    # Match su nome canonico
    ev_name_l = event_name.lower()
    ev_tokens = [t for t in re.findall(r"\w{4,}", ev_name_l) if t not in {"battaglia", "della", "delle", "monte", "settore"}]
    for tok in ev_tokens:
        if tok in title:
            score += 0.10
        elif tok in text:
            score += 0.05

    score = min(score, 0.6)
    reason = f"Pertinenza: {score:.2f} (title match pesa di più)"
    return score, reason


def _quality_score(item_metadata: Dict[str, Any], files: List[Dict[str, Any]]) -> Tuple[float, str]:
    """Score di qualità del documento IA."""
    score = 0.0
    reasons = []

    mediatype = str(item_metadata.get("mediatype", "")).lower()
    if mediatype == "texts":
        score += 0.15
        reasons.append("mediatype=texts")
    elif mediatype == "image":
        score += 0.05
        reasons.append("mediatype=image")

    has_ocr = any(
        f.get("format", "").lower() in ("hocr", "djvu", "djvtxt", "text pdf")
        for f in files
    )
    if has_ocr:
        score += 0.25
        reasons.append("OCR/DjVu disponibile")

    has_pdf = any(
        f.get("format", "").lower() == "pdf" or f.get("name", "").lower().endswith(".pdf")
        for f in files
    )
    if has_pdf:
        score += 0.10
        reasons.append("PDF disponibile")

    downloads = item_metadata.get("downloads", 0)
    try:
        dl_int = int(downloads)
        if dl_int > 100:
            score += 0.10
            reasons.append(f"downloads={dl_int}")
        elif dl_int > 10:
            score += 0.05
            reasons.append(f"downloads={dl_int}")
    except (ValueError, TypeError):
        pass

    language = str(item_metadata.get("language", "")).lower()
    if "ita" in language or "italian" in language:
        score += 0.10
        reasons.append("lingua italiana")
    if "eng" in language or "english" in language:
        score += 0.05
        reasons.append("lingua inglese")

    score = min(score, 0.6)
    return score, "; ".join(reasons) if reasons else "Qualità non valutabile"


def _is_search_page(url: str) -> bool:
    """Verifica se l'URL è una pagina di ricerca generica."""
    if not url:
        return False
    u = url.lower()
    patterns = [
        "/search?", "/advancedsearch", "query=", "/details/texts?query",
        "/results?", "sort=", "and+date:",
    ]
    return any(p in u for p in patterns)


def evaluate_candidate(
    item: Dict[str, Any],
    event_data: Dict[str, Any],
    files: List[Dict[str, Any]] = None,
) -> CandidateEvaluation:
    """Valuta un singolo candidato IA.

    Args:
        item: metadati IA (da advancedsearch o metadata API)
        event_data: dati evento canonico (nome, data_inizio, data_fine, luogo, keywords, aliases)
        files: lista file dell'item (da metadata API, server.files)

    Returns:
        CandidateEvaluation con score, stato e motivazioni
    """
    files = files or []
    identifier = item.get("identifier", "")
    title = item.get("title", "")

    event_name = event_data.get("nome", "")
    event_start = event_data.get("data_inizio", "")
    event_end = event_data.get("data_fine", "")
    event_luogo = event_data.get("luogo", "")
    event_keywords = event_data.get("keywords", [])
    event_aliases = event_data.get("aliases", [])
    event_conflict = event_data.get("conflict", "")

    reasons: List[str] = []

    # 1. Rileva conflitto
    detected = _detect_conflict(item)
    war_mismatch = False
    if event_conflict and detected != "unknown" and detected != event_conflict:
        war_mismatch = True
        reasons.append(f"War mismatch: evento={event_conflict}, item={detected}")

    # 2. Compatibilità temporale
    item_date = item.get("date", "") or item.get("year", "")
    temp_ok, temp_reason = _temporal_compatibility(event_start, event_end, item_date)
    reasons.append(temp_reason)

    # 3. Compatibilità geografica
    geo_ok, geo_reason = _geographic_compatibility(event_luogo, item)
    reasons.append(geo_reason)

    # 4. Pertinenza
    rel_score, rel_reason = _relevance_score(event_name, event_keywords, event_aliases, item)
    reasons.append(rel_reason)

    # 5. Qualità
    qual_score, qual_reason = _quality_score(item, files)
    reasons.append(qual_reason)

    # 6. Search page check
    catalog_url = f"https://archive.org/details/{identifier}" if identifier else ""
    is_sp = _is_search_page(item.get("catalog_url", catalog_url))

    # Score finale
    overall = rel_score + qual_score
    if temp_ok:
        overall += 0.15
    if geo_ok:
        overall += 0.15
    if war_mismatch:
        overall -= 0.30
    if is_sp:
        overall = 0.0
        reasons.append("URL è una pagina di ricerca generica — rifiutato")

    overall = max(0.0, min(1.0, overall))

    # Stato
    if war_mismatch or is_sp or overall < 0.15:
        status = "rejected"
    elif overall >= 0.45 and temp_ok and geo_ok:
        status = "accepted"
    else:
        status = "candidate"

    return CandidateEvaluation(
        identifier=identifier,
        title=title,
        detected_conflict=detected,
        temporal_compatible=temp_ok,
        geographic_compatible=geo_ok,
        relevance_score=rel_score,
        quality_score=qual_score,
        overall_score=overall,
        status=status,
        reasons=reasons,
        war_mismatch=war_mismatch,
        is_search_page=is_sp,
    )


def evaluate_candidates(
    items: List[Dict[str, Any]],
    event_data: Dict[str, Any],
    files_map: Dict[str, List[Dict[str, Any]]] = None,
) -> List[CandidateEvaluation]:
    """Valuta una lista di candidati IA.

    Args:
        items: lista metadati IA
        event_data: dati evento canonico
        files_map: mappa identifier → lista file (opzionale, per quality scoring)

    Returns:
        Lista di CandidateEvaluation ordinata per score decrescente
    """
    files_map = files_map or {}
    evaluations = []
    for item in items:
        files = files_map.get(item.get("identifier", ""), [])
        ev = evaluate_candidate(item, event_data, files)
        evaluations.append(ev)
    evaluations.sort(key=lambda e: e.overall_score, reverse=True)
    return evaluations


# ─── Query Planner ────────────────────────────────────────────────────────────

IA_QUERY_PLAN_VERSION = "ia_query_plan_v2"
IA_RELEVANCE_VERSION = "ia_relevance_v2"

_CONTEMPORARY_MARGIN_YEARS = 3


@dataclass
class IAQueryPlanEntry:
    """Singola strategia di query per Internet Archive."""
    query: str
    strategy: str  # exact_event | alias | contemporary | place_subevent | contextual
    priority: int
    reason: str
    event_scope: str  # event | subevent | place | context
    publication_date_filter: Optional[str] = None  # Solr date filter, None = no filter

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "strategy": self.strategy,
            "priority": self.priority,
            "reason": self.reason,
            "event_scope": self.event_scope,
            "publication_date_filter": self.publication_date_filter,
        }


def build_internet_archive_query_plan(
    query: str,
    context: Any = None,
) -> List[IAQueryPlanEntry]:
    """Costruisce un piano di query Internet Archive sensibile al contesto.

    Genera strategie multiple:
    1. exact_event: nome canonico in title/description, senza filtro editoriale rigido
    2. alias: varianti e traduzioni del nome evento
    3. contemporary: fonti coeve con intervallo derivato dalle date evento
    4. place_subevent: luogo + keyword specifiche
    5. contextual: ricerca ampia con keyword evento

    Non usa MAI filtri hardcoded come date:[1940 TO 1946].
    Non attiva _IT_MILITARY per eventi.
    """
    entries: List[IAQueryPlanEntry] = []

    if context is None:
        # Fallback: solo query nuda, senza filtri
        entries.append(IAQueryPlanEntry(
            query=f'({query}) AND mediatype:(texts)',
            strategy="contextual",
            priority=10,
            reason="Nessun contesto disponibile — query generica senza filtro temporale",
            event_scope="context",
        ))
        return entries

    canonical = context.canonical_name or query
    aliases = context.aliases
    places = context.places
    keywords = context.keywords
    start_year = context.start_year
    end_year = context.end_year
    conflict = context.conflict

    # 1. exact_event — nome canonico, nessun filtro editoriale
    entries.append(IAQueryPlanEntry(
        query=f'title:("{canonical}") OR description:("{canonical}")',
        strategy="exact_event",
        priority=1,
        reason=f"Ricerca esatta nome evento '{canonical}' senza filtro editoriale",
        event_scope="event",
    ))

    # 2. alias — varianti e traduzioni
    for alias in aliases:
        if len(alias) < 4:
            continue
        entries.append(IAQueryPlanEntry(
            query=f'title:("{alias}") OR description:("{alias}")',
            strategy="alias",
            priority=2,
            reason=f"Ricerca alias/traduzione '{alias}'",
            event_scope="event",
        ))

    # 3. contemporary — fonti coeve con intervallo derivato
    if start_year and end_year:
        margin = _CONTEMPORARY_MARGIN_YEARS
        date_filter = f"date:[{start_year - margin} TO {end_year + margin}]"
        entries.append(IAQueryPlanEntry(
            query=f'("{canonical}") AND mediatype:(texts) AND {date_filter}',
            strategy="contemporary",
            priority=3,
            reason=f"Fonti coeve {start_year - margin}-{end_year + margin} (margine ±{margin} anni)",
            event_scope="event",
            publication_date_filter=date_filter,
        ))
    elif start_year:
        margin = _CONTEMPORARY_MARGIN_YEARS
        date_filter = f"date:[{start_year - margin} TO {start_year + margin}]"
        entries.append(IAQueryPlanEntry(
            query=f'("{canonical}") AND mediatype:(texts) AND {date_filter}',
            strategy="contemporary",
            priority=3,
            reason=f"Fonti coeve {start_year - margin}-{start_year + margin} (solo start_date, margine ±{margin})",
            event_scope="event",
            publication_date_filter=date_filter,
        ))

    # 4. place_subevent — luogo + keyword
    if places and keywords:
        place_str = " OR ".join(f'"{p}"' for p in places[:3])
        kw_str = " OR ".join(f'"{k}"' for k in keywords[:5])
        entries.append(IAQueryPlanEntry(
            query=f'({place_str}) AND ({kw_str}) AND mediatype:(texts)',
            strategy="place_subevent",
            priority=4,
            reason=f"Luogo ({place_str}) + keyword evento ({kw_str})",
            event_scope="place",
        ))
    elif places:
        place_str = " OR ".join(f'"{p}"' for p in places[:3])
        entries.append(IAQueryPlanEntry(
            query=f'({place_str}) AND ("{canonical}") AND mediatype:(texts)',
            strategy="place_subevent",
            priority=4,
            reason=f"Luogo ({place_str}) + nome evento",
            event_scope="place",
        ))

    # 5. contextual — keyword ampie senza filtro editoriale
    if keywords:
        kw_query = " AND ".join(f'"{k}"' for k in keywords[:5])
        entries.append(IAQueryPlanEntry(
            query=f'({kw_query}) AND mediatype:(texts)',
            strategy="contextual",
            priority=5,
            reason="Ricerca contestuale con keyword evento, senza filtro editoriale",
            event_scope="context",
        ))

    # Se contesto incompleto, aggiungi entry di avviso
    if conflict == "unknown" and not start_year:
        entries.append(IAQueryPlanEntry(
            query=f'("{canonical}") AND mediatype:(texts)',
            strategy="contextual",
            priority=99,
            reason="Contesto incompleto (conflict=unknown, no dates) — query generica",
            event_scope="context",
        ))

    return entries


def evaluate_candidates_from_context(
    items: List[Dict[str, Any]],
    context: Any,
    files_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[CandidateEvaluation]:
    """Valuta candidati IA usando FederatedSearchContext invece di event_data dict.

    Converte FederatedSearchContext nel formato event_data atteso da evaluate_candidate,
    mappando i campi normalizzati.
    """
    files_map = files_map or {}

    # Mappa FederatedSearchContext → event_data dict (compatibilità evaluate_candidate)
    event_data: Dict[str, Any] = {
        "nome": context.canonical_name,
        "data_inizio": context.start_date.isoformat() if context.start_date else "",
        "data_fine": context.end_date.isoformat() if context.end_date else "",
        "luogo": ", ".join(context.places) if context.places else "",
        "keywords": list(context.keywords),
        "aliases": list(context.aliases),
        "conflict": {"ww1": "WWI", "ww2": "WW2"}.get(context.conflict, ""),
    }

    return evaluate_candidates(items, event_data, files_map)
