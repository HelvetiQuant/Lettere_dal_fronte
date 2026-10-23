"""
Temporal filter and conflict detection for WWI/WWII source-event linking.

Centralizes the decision logic that prevents temporal cross-contamination
between WWI and WWII sources/events.

Usage (batch and query-time):
    from linking.temporal_filter import (
        temporal_relation,
        detect_conflict_markers,
        classify_keyword,
        KeywordClass,
        filter_sources_for_event,
    )
"""
import re
from typing import Optional

from linking.normalization import normalize_date, date_overlap


# ─── Keyword classes ────────────────────────────────────────────────────────

WWII_MARKERS = {
    "seconda guerra mondiale", "wwii", "1939-1945", "1943-1945",
    "8 settembre 1943", "operazione achse", "imi",
    "internati militari italiani", "tobruk 1941",
    "holocaust", "shoah", "kz", "mauthausen-gusen", "gusen",
    "deportazione nazista", "terzo reich", "lager nazista",
    "dachau", "auschwitz", "birkenau", " Ravensbruck",
    "resistenza", "partigiano", "rsi", "repubblica sociale italiana",
    "badoglio", "armistizio", "43", "44", "45",
    "cefalonia", "salerno", "cassino", "montecassino",
    "anzio", "gothic line", "linea gotica", "struttura Todt",
    "deportazione", "raid", "rastrellamento",
}

WWI_MARKERS = {
    "prima guerra mondiale", "grande guerra", "wwi", "1914-1918",
    "1915-1918", "sigmundsherberg", "rastatt", "k.u.k",
    "feldkorrespondenz", "caporetto", "piave", "isonzo",
    "carso", "ortigara", "15", "16", "17", "18",
}

AMBIGUOUS_MARKERS = {
    "mauthausen", "campo", "campi", "prigionia", "prigioniero",
    "internamento", "lager", "austria", "ungheria", "germania",
    "cattura", "captured", "fronte", "guerra", "morto",
    "caduto", "ferito", "prisoner", "pow", "camp",
    "kriegsgefangene", "gefangenenlager",
}


class KeywordClass:
    DISTINCTIVE = "distinctive"
    AMBIGUOUS = "ambiguous"
    OPPOSITE_CONFLICT = "opposite_conflict"
    NONE = "none"


def classify_keyword(keyword: str, event_conflict_code: str) -> str:
    """
    Classify a keyword relative to the event's conflict code.

    Returns:
        KeywordClass.DISTINCTIVE — keyword specific to the event's era
        KeywordClass.AMBIGUOUS — keyword could apply to either era
        KeywordClass.OPPOSITE_CONFLICT — keyword specific to the opposite era
        KeywordClass.NONE — keyword not recognized
    """
    kw_lower = keyword.lower().strip()

    if kw_lower in AMBIGUOUS_MARKERS:
        return KeywordClass.AMBIGUOUS

    if event_conflict_code == "WWI":
        if kw_lower in WWII_MARKERS:
            return KeywordClass.OPPOSITE_CONFLICT
        if kw_lower in WWI_MARKERS:
            return KeywordClass.DISTINCTIVE
    elif event_conflict_code == "WWII":
        if kw_lower in WWI_MARKERS:
            return KeywordClass.OPPOSITE_CONFLICT
        if kw_lower in WWII_MARKERS:
            return KeywordClass.DISTINCTIVE

    return KeywordClass.NONE


# ─── Temporal relation ──────────────────────────────────────────────────────

def temporal_relation(
    source_start: Optional[str],
    source_end: Optional[str],
    event_start: Optional[str],
    event_end: Optional[str],
) -> str:
    """
    Determine temporal relationship between source coverage and event period.

    Returns:
        "overlap" — intervals overlap (at least partially)
        "conflict" — intervals are certain and disjoint
        "unknown" — source period is absent or too uncertain
    """
    if not source_start or not source_start.strip():
        return "unknown"

    if not event_start or not event_start.strip():
        return "unknown"

    s_start = source_start.strip()
    s_end = (source_end or s_start).strip()
    e_start = event_start.strip()
    e_end = (event_end or e_start).strip()

    if date_overlap(s_start, s_end, e_start, e_end):
        return "overlap"

    def _to_year(d: str) -> int | None:
        if not d:
            return None
        try:
            return int(d[:4])
        except (ValueError, IndexError):
            return None

    s_y = _to_year(s_start)
    s_ye = _to_year(s_end)
    e_y = _to_year(e_start)
    e_ye = _to_year(e_end)

    if s_y is not None and e_y is not None:
        s_ye = s_ye or s_y
        e_ye = e_ye or e_y
        if s_y > e_ye or e_y > s_ye:
            return "conflict"

    return "unknown"


# ─── Conflict marker detection ──────────────────────────────────────────────

def _word_boundary_match(keyword: str, text: str) -> bool:
    """
    Match keyword with word boundaries, not substring.
    Case-insensitive, Unicode-aware.
    """
    if not keyword or not text:
        return False
    pattern = r"(?<!\w)" + re.escape(keyword) + r"(?!\w)"
    return bool(re.search(pattern, text, re.IGNORECASE | re.UNICODE))


def detect_conflict_markers(
    text: str,
    event_conflict_code: str,
) -> list[str]:
    """
    Detect strong markers of the opposite conflict in the source text.

    Returns list of matched markers (empty if none found).
    """
    if not text or not event_conflict_code:
        return []

    if event_conflict_code == "WWI":
        markers = WWII_MARKERS
    elif event_conflict_code == "WWII":
        markers = WWI_MARKERS
    else:
        return []

    matched = []
    for marker in markers:
        if _word_boundary_match(marker, text):
            matched.append(marker)
    return matched


def detect_same_era_markers(
    text: str,
    event_conflict_code: str,
) -> list[str]:
    """
    Detect distinctive markers of the same conflict era in the source text.
    """
    if not text or not event_conflict_code:
        return []

    if event_conflict_code == "WWI":
        markers = WWI_MARKERS
    elif event_conflict_code == "WWII":
        markers = WWII_MARKERS
    else:
        return []

    matched = []
    for marker in markers:
        if _word_boundary_match(marker, text):
            matched.append(marker)
    return matched


def detect_ambiguous_markers(text: str) -> list[str]:
    """
    Detect ambiguous markers in the source text.
    """
    if not text:
        return []

    matched = []
    for marker in AMBIGUOUS_MARKERS:
        if _word_boundary_match(marker, text):
            matched.append(marker)
    return matched


# ─── Source classification ──────────────────────────────────────────────────

def classify_source_for_event(
    source_text: str,
    source_coverage_start: Optional[str],
    source_coverage_end: Optional[str],
    event_conflict_code: str,
    event_start: Optional[str],
    event_end: Optional[str],
) -> dict:
    """
    Classify a source relative to an event.

    Returns:
        {
            "decision": "accepted" | "needs_review" | "rejected",
            "reason": str,
            "temporal_relation": str,
            "conflict_markers": list[str],
            "same_era_markers": list[str],
            "ambiguous_markers": list[str],
        }
    """
    t_rel = temporal_relation(
        source_coverage_start, source_coverage_end,
        event_start, event_end,
    )

    conflict_markers = detect_conflict_markers(source_text, event_conflict_code)
    same_era_markers = detect_same_era_markers(source_text, event_conflict_code)
    ambiguous_markers = detect_ambiguous_markers(source_text)

    # Decision logic (order matters — first match wins)

    # 1. Temporal conflict (certain disjoint) → rejected
    if t_rel == "conflict":
        return {
            "decision": "rejected",
            "reason": "temporal_conflict",
            "temporal_relation": t_rel,
            "conflict_markers": conflict_markers,
            "same_era_markers": same_era_markers,
            "ambiguous_markers": ambiguous_markers,
        }

    # 2. Strong opposite conflict marker → rejected
    if conflict_markers:
        return {
            "decision": "rejected",
            "reason": "ww1_ww2_mismatch",
            "temporal_relation": t_rel,
            "conflict_markers": conflict_markers,
            "same_era_markers": same_era_markers,
            "ambiguous_markers": ambiguous_markers,
        }

    # 3. Mixed era (both same-era and ambiguous, but no opposite) → needs_review
    if same_era_markers and ambiguous_markers and not conflict_markers:
        if t_rel == "unknown":
            return {
                "decision": "needs_review",
                "reason": "mixed_era_source",
                "temporal_relation": t_rel,
                "conflict_markers": conflict_markers,
                "same_era_markers": same_era_markers,
                "ambiguous_markers": ambiguous_markers,
            }

    # 4. Only ambiguous keywords → needs_review
    if ambiguous_markers and not same_era_markers and not conflict_markers:
        return {
            "decision": "needs_review",
            "reason": "ambiguous_keywords_only",
            "temporal_relation": t_rel,
            "conflict_markers": conflict_markers,
            "same_era_markers": same_era_markers,
            "ambiguous_markers": ambiguous_markers,
        }

    # 5. Distinctive keyword + temporal overlap → accepted
    if same_era_markers and t_rel == "overlap":
        return {
            "decision": "accepted",
            "reason": "distinctive_keyword_with_temporal_overlap",
            "temporal_relation": t_rel,
            "conflict_markers": conflict_markers,
            "same_era_markers": same_era_markers,
            "ambiguous_markers": ambiguous_markers,
        }

    # 6. Distinctive keyword but unknown temporal → needs_review (not accepted)
    if same_era_markers and t_rel == "unknown":
        return {
            "decision": "needs_review",
            "reason": "distinctive_keyword_unknown_temporal",
            "temporal_relation": t_rel,
            "conflict_markers": conflict_markers,
            "same_era_markers": same_era_markers,
            "ambiguous_markers": ambiguous_markers,
        }

    # 7. No evidence
    return {
        "decision": "rejected",
        "reason": "insufficient_evidence",
        "temporal_relation": t_rel,
        "conflict_markers": conflict_markers,
        "same_era_markers": same_era_markers,
        "ambiguous_markers": ambiguous_markers,
    }


# ─── Batch filter for API mitigation ────────────────────────────────────────

def filter_sources_for_event(
    sources: list[dict],
    event: dict,
    include_candidates: bool = False,
) -> dict:
    """
    Filter a list of sources for an event, separating by decision.

    Args:
        sources: list of source dicts with at least: title, soggetti_collegati, note
        event: event dict with: conflict (or conflict_code), data_inizio, data_fine
        include_candidates: if True, include needs_review in candidate_sources

    Returns:
        {
            "sources": list[dict],          # accepted only
            "candidate_sources": list[dict], # needs_review (if include_candidates)
            "rejected_count": int,
            "needs_review_count": int,
            "linking_version": str,
        }
    """
    event_conflict = event.get("conflict") or event.get("conflict_code") or ""
    event_start = event.get("data_inizio") or event.get("start_date")
    event_end = event.get("data_fine") or event.get("end_date")

    accepted = []
    candidates = []
    rejected_count = 0
    needs_review_count = 0

    for src in sources:
        text = " ".join(filter(None, [
            src.get("titolo", ""),
            src.get("title", ""),
            src.get("soggetti_collegati", ""),
            src.get("note", ""),
            src.get("description", ""),
            src.get("luogo", ""),
        ]))

        cov_start = (
            src.get("coverage_start")
            or src.get("data_inizio")
            or src.get("year_start")
        )
        cov_end = (
            src.get("coverage_end")
            or src.get("data_fine")
            or src.get("year_end")
        )

        if cov_start is not None:
            cov_start = str(cov_start)
        if cov_end is not None:
            cov_end = str(cov_end)

        result = classify_source_for_event(
            text, cov_start, cov_end,
            event_conflict, event_start, event_end,
        )

        src_with_decision = dict(src)
        src_with_decision["_decision"] = result["decision"]
        src_with_decision["_reason"] = result["reason"]
        src_with_decision["_temporal_relation"] = result["temporal_relation"]
        src_with_decision["_conflict_markers"] = result["conflict_markers"]
        src_with_decision["_same_era_markers"] = result["same_era_markers"]
        src_with_decision["_ambiguous_markers"] = result["ambiguous_markers"]

        if result["decision"] == "accepted":
            accepted.append(src_with_decision)
        elif result["decision"] == "needs_review":
            needs_review_count += 1
            if include_candidates:
                candidates.append(src_with_decision)
        else:
            rejected_count += 1

    return {
        "sources": accepted,
        "candidate_sources": candidates,
        "rejected_count": rejected_count,
        "needs_review_count": needs_review_count,
        "linking_version": "2.0.0-filtered",
    }
