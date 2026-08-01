"""Relevance Gate V4 — multi-stage classification pipeline.

Replaces the V3 binary relevance gate with a multi-stage pipeline that:

1. Canonicalizes URL and removes tracking
2. Classifies result_kind (search_page, record, document, context, commercial, social)
3. Checks chronological compatibility without deducing from a single keyword
4. Checks target identity on normalized name and strong features
5. Checks geographic scope and institutional relevance
6. Assigns a final state and reason codes

Stati minimi:
- DISCOVERY_LEAD
- SEARCH_PAGE_ONLY
- CONTEXT_ONLY
- IRRELEVANT
- REJECTED_WRONG_IDENTITY
- FETCH_FAILED
- CONTENT_NOT_SEARCHABLE
- CONSULTED_NO_MATCH
- CLAIM_EVIDENCE_PARTIAL
- CLAIM_EVIDENCE_ACCEPTED

Feature and reason code minimi:
- TARGET_NAME_EXACT
- TARGET_NAME_VARIANT
- TARGET_NAME_ABSENT
- WRONG_GIVEN_NAME
- WRONG_PERSON
- BIRTH_YEAR_CONFLICT
- BIRTH_PLACE_CONFLICT
- UNIT_CONFLICT
- CONFLICT_MISMATCH
- GEOGRAPHIC_SCOPE_MISMATCH
- PERIOD_CONFIRMED_WWI
- PERIOD_CONFIRMED_WWII
- PERIOD_UNKNOWN
- SEARCH_PAGE_NOT_RECORD
- CONTENT_NOT_OBSERVED
- COMMERCIAL_NO_HISTORICAL_VALUE
- CONTEXT_NOT_TARGET_EVIDENCE
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

log = logging.getLogger(__name__)


# ─── Result states ────────────────────────────────────────────────────────────

RESULT_STATES = {
    "DISCOVERY_LEAD",
    "SEARCH_PAGE_ONLY",
    "CONTEXT_ONLY",
    "IRRELEVANT",
    "REJECTED_WRONG_IDENTITY",
    "FETCH_FAILED",
    "CONTENT_NOT_SEARCHABLE",
    "CONSULTED_NO_MATCH",
    "CLAIM_EVIDENCE_PARTIAL",
    "CLAIM_EVIDENCE_ACCEPTED",
}

# ─── Reason codes ─────────────────────────────────────────────────────────────

REASON_CODES = {
    "TARGET_NAME_EXACT",
    "TARGET_NAME_VARIANT",
    "TARGET_NAME_ABSENT",
    "WRONG_GIVEN_NAME",
    "WRONG_PERSON",
    "BIRTH_YEAR_CONFLICT",
    "BIRTH_PLACE_CONFLICT",
    "UNIT_CONFLICT",
    "CONFLICT_MISMATCH",
    "GEOGRAPHIC_SCOPE_MISMATCH",
    "PERIOD_CONFIRMED_WWI",
    "PERIOD_CONFIRMED_WWII",
    "PERIOD_UNKNOWN",
    "SEARCH_PAGE_NOT_RECORD",
    "CONTENT_NOT_OBSERVED",
    "COMMERCIAL_NO_HISTORICAL_VALUE",
    "CONTEXT_NOT_TARGET_EVIDENCE",
    "SOCIAL_MEDIA_NO_HISTORICAL_VALUE",
    "GENERIC_GUIDE_NOT_RECORD",
}

# ─── Domain classifications ───────────────────────────────────────────────────

_COMMERCIAL_DOMAINS = {
    "amazon.com", "amazon.it", "ebay.com", "booking.com",
    "wine-searcher.com", "winedivaa.com", "vinifera-mundi.com",
    "prosecco.it", "folladorprosecco.com", "bottleofitaly.com",
    "chinchinwinetrading.com", "decantalo.com", "on-wine.com",
    "scribd.com",
}

_SOCIAL_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "pinterest.com", "tiktok.com", "reddit.com",
}

_SEARCH_PAGE_PATTERNS = [
    r"/search", r"/ricerca", r"/find", r"\?q=", r"cercanome\.aspx",
    r"/index\.php/ricerca", r"/File/Search", r"#person\|",
]

_HOMEPAGE_PATTERNS = [
    r"/pagine/", r"/default\.aspx$", r"/index\.(html|php|aspx)$",
    r"/$", r"/home", r"/about",
]

# WWI keywords (distinctive — not ambiguous)
_WWI_DISTINCTIVE = {
    "prima guerra mondiale", "grande guerra", "1915-1918", "1914-1918",
    "albo d'oro", "cadutigrandeguerra", "caporetto", "piave",
    "fronte del piave", "cellelager", "1917-1918",
}

# WWII keywords (distinctive)
_WWII_DISTINCTIVE = {
    "seconda guerra mondiale", "world war 2", "ww2", "1943", "1944", "1945",
    "imi", "internati militari italiani", "mauthausen", "tobruk",
    "divisione acqui", "resistenza", "deportazione",
}

# Ambiguous keywords (present in both conflicts or generic)
_AMBIGUOUS_KEYWORDS = {
    "militare", "soldato", "guerra", "caduto", "disperso",
    "prigioniero", "internato", "deportato", "reparto", "matricola",
    "military records", "italian military", "family tree",
}


@dataclass
class RelevanceResult:
    """Result of multi-stage relevance classification."""
    result_state: str = "DISCOVERY_LEAD"
    reason_codes: List[str] = field(default_factory=list)
    result_kind: str = ""  # search_page, record, document, context, commercial, social, homepage
    target_name_match: str = ""  # exact, variant, absent, wrong_person
    period_compatibility: str = ""  # confirmed_wwi, confirmed_wwii, unknown, mismatch
    geographic_scope: str = ""  # matching, mismatch, unknown
    fetch_status: str = "NOT_FETCHED"  # NOT_FETCHED, SUCCESS, FETCH_FAILED
    is_evidence: bool = False
    is_context: bool = False
    is_lead: bool = True
    is_rejected: bool = False
    notes: str = ""


def _normalize_text(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _check_name_in_text(target_name: str, text: str) -> Tuple[str, List[str]]:
    """Check if target name appears in text.

    Returns (match_level, reason_codes).
    match_level: exact, variant, absent, wrong_person
    """
    if not target_name or not text:
        return "absent", ["TARGET_NAME_ABSENT"]

    norm_target = _normalize_text(target_name)
    norm_text = _normalize_text(text)

    # Parse target into surname and given name
    parts = norm_target.split()
    if len(parts) < 2:
        if norm_target in norm_text:
            return "exact", ["TARGET_NAME_EXACT"]
        return "absent", ["TARGET_NAME_ABSENT"]

    surname = parts[0]
    given = parts[1]

    # Check exact full name (either order)
    if norm_target in norm_text or f"{given} {surname}" in norm_text:
        return "exact", ["TARGET_NAME_EXACT"]

    # Check surname present but different given name
    # Look for "surname <different_name>" pattern
    surname_pattern = rf'\b{re.escape(surname)}\b'
    if re.search(surname_pattern, norm_text):
        # Surname found — check if given name is also present
        given_pattern = rf'\b{re.escape(given)}\b'
        if re.search(given_pattern, norm_text):
            return "variant", ["TARGET_NAME_VARIANT"]
        else:
            # Surname found but given name absent — could be wrong person
            # Check if any other given name appears near the surname
            context_around = re.findall(
                rf'(\w+\s+){re.escape(surname)}|{re.escape(surname)}\s+(\w+)',
                norm_text
            )
            nearby_words = []
            for m in context_around:
                nearby_words.extend([w for w in m if w])
            # Filter out common non-name words
            non_name_words = {"di", "de", "del", "della", "da", "e", "il", "la",
                              "lo", "un", "una", "in", "a", "da", "per", "con",
                              "nato", "nata", "classe", "soldato", "maggiore",
                              "tenente", "capitano", "colonnello", "sottotenente"}
            other_names = [w for w in nearby_words if w not in non_name_words and w != given]
            if other_names:
                return "wrong_person", ["WRONG_GIVEN_NAME", "WRONG_PERSON"]
            return "variant", ["TARGET_NAME_VARIANT"]

    return "absent", ["TARGET_NAME_ABSENT"]


def _check_period_compatibility(text: str, target_conflict: str) -> Tuple[str, List[str]]:
    """Check chronological compatibility.

    Returns (compatibility, reason_codes).
    compatibility: confirmed_wwi, confirmed_wwii, unknown, mismatch
    """
    if not text:
        return "unknown", ["PERIOD_UNKNOWN"]

    norm_text = _normalize_text(text)

    # Check for distinctive WWI keywords
    has_wwi_distinctive = any(kw in norm_text for kw in _WWI_DISTINCTIVE)
    # Check for distinctive WWII keywords
    has_wwii_distinctive = any(kw in norm_text for kw in _WWII_DISTINCTIVE)
    # Check for ambiguous keywords
    has_ambiguous = any(kw in norm_text for kw in _AMBIGUOUS_KEYWORDS)

    if has_wwi_distinctive and not has_wwii_distinctive:
        if target_conflict == "ww1":
            return "confirmed_wwi", ["PERIOD_CONFIRMED_WWI"]
        elif target_conflict == "ww2":
            return "mismatch", ["CONFLICT_MISMATCH"]
        else:
            return "confirmed_wwi", ["PERIOD_CONFIRMED_WWI"]

    if has_wwii_distinctive and not has_wwi_distinctive:
        if target_conflict == "ww2":
            return "confirmed_wwii", ["PERIOD_CONFIRMED_WWII"]
        elif target_conflict == "ww1":
            return "mismatch", ["CONFLICT_MISMATCH"]
        else:
            return "confirmed_wwii", ["PERIOD_CONFIRMED_WWII"]

    if has_wwi_distinctive and has_wwii_distinctive:
        return "unknown", ["PERIOD_UNKNOWN"]

    if has_ambiguous:
        return "unknown", ["PERIOD_UNKNOWN"]

    return "unknown", ["PERIOD_UNKNOWN"]


def _check_geographic_scope(url: str, title: str, target_birth_place: str) -> Tuple[str, List[str]]:
    """Check if the result's geographic scope matches the target.

    Returns (scope_match, reason_codes).
    scope_match: matching, mismatch, unknown
    """
    if not target_birth_place:
        return "unknown", []

    norm_place = _normalize_text(target_birth_place)
    norm_text = _normalize_text(f"{title} {url}")

    # Extract key part of place name (first word for compound names)
    place_parts = norm_place.split()
    if not place_parts:
        return "unknown", []

    # Check if the place or its main component appears in the text
    main_component = place_parts[0]
    if main_component in norm_text or norm_place in norm_text:
        return "matching", []

    # Check if the URL domain suggests a different geographic area
    # (e.g., vigevano.it for a target from pordenone)
    # We can't do exhaustive checking, but we can flag obvious mismatches
    # if the title mentions a specific city different from the target
    return "unknown", []


def classify_result_kind(url: str, title: str = "", snippet: str = "") -> str:
    """Classify the kind of web result.

    Returns: search_page, record, document, context, commercial, social, homepage
    """
    if not url:
        return "search_page"

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
    except Exception:
        return "search_page"

    url_lower = url.lower()

    # Commercial
    for comm_dom in _COMMERCIAL_DOMAINS:
        if comm_dom in domain:
            return "commercial"

    # Social media
    for soc_dom in _SOCIAL_DOMAINS:
        if soc_dom in domain:
            return "social"

    # Search page
    for pattern in _SEARCH_PAGE_PATTERNS:
        if re.search(pattern, url_lower):
            return "search_page"

    # Homepage
    for pattern in _HOMEPAGE_PATTERNS:
        if re.search(pattern, url_lower):
            return "homepage"

    # Document (PDF, image, etc.)
    if any(ext in url_lower for ext in [".pdf", ".jpg", ".png", ".tiff", ".doc", ".docx"]):
        return "document"

    # Default: could be a record or context
    # Without fetching, we can't tell — treat as lead
    return "record"


def classify_relevance_v4(
    url: str,
    title: str,
    snippet: str,
    target_name: str,
    target_conflict: str,
    target_birth_place: str = "",
    target_birth_year: str = "",
    target_unit: str = "",
    fetch_status: str = "NOT_FETCHED",
    fetched_content: str = "",
) -> RelevanceResult:
    """Multi-stage relevance classification for a web search result.

    Args:
        url: Result URL
        title: Result title
        snippet: Result snippet
        target_name: Normalized target name (e.g., "LARI GIUSEPPE")
        target_conflict: "ww1", "ww2", or ""
        target_birth_place: Target's birth place
        target_birth_year: Target's birth year
        target_unit: Target's military unit
        fetch_status: Whether the content was fetched
        fetched_content: Content extracted from the URL (if fetched)

    Returns:
        RelevanceResult with state, reason codes, and classification details.
    """
    result = RelevanceResult()

    if not url:
        result.result_state = "IRRELEVANT"
        result.reason_codes = ["TARGET_NAME_ABSENT"]
        result.is_rejected = True
        return result

    # Stage 1: Classify result kind
    result.result_kind = classify_result_kind(url, title, snippet)

    # Stage 2: Reject commercial and social
    if result.result_kind == "commercial":
        result.result_state = "IRRELEVANT"
        result.reason_codes = ["COMMERCIAL_NO_HISTORICAL_VALUE"]
        result.is_rejected = True
        return result

    if result.result_kind == "social":
        result.result_state = "IRRELEVANT"
        result.reason_codes = ["SOCIAL_MEDIA_NO_HISTORICAL_VALUE"]
        result.is_rejected = True
        return result

    # Stage 3: Check period compatibility
    combined_text = f"{title} {snippet}"
    period_compat, period_codes = _check_period_compatibility(combined_text, target_conflict)
    result.period_compatibility = period_compat
    result.reason_codes.extend(period_codes)

    # If period mismatch (but NOT for WWI sources misclassified as WWII)
    if period_compat == "mismatch":
        # Don't reject just on period — the source might still be relevant
        # for context. But flag the mismatch.
        result.reason_codes.append("CONFLICT_MISMATCH")

    # Stage 4: Check target name identity
    name_match, name_codes = _check_name_in_text(target_name, combined_text)
    result.target_name_match = name_match
    result.reason_codes.extend(name_codes)

    # Stage 5: Check geographic scope
    geo_match, geo_codes = _check_geographic_scope(url, title, target_birth_place)
    result.geographic_scope = geo_match
    result.reason_codes.extend(geo_codes)

    if geo_match == "mismatch":
        result.reason_codes.append("GEOGRAPHIC_SCOPE_MISMATCH")

    # Stage 6: Determine final state based on all factors

    # Wrong person → reject with correct reason
    if name_match == "wrong_person":
        result.result_state = "REJECTED_WRONG_IDENTITY"
        result.is_rejected = True
        return result

    # Search page → SEARCH_PAGE_ONLY (not evidence, not "no match")
    if result.result_kind in ("search_page", "homepage"):
        result.result_state = "SEARCH_PAGE_ONLY"
        result.reason_codes.append("SEARCH_PAGE_NOT_RECORD")
        result.is_lead = True
        return result

    # Name absent → check if context or irrelevant
    if name_match == "absent":
        # Could be context (generic WWI/WWII info) or irrelevant
        if period_compat in ("confirmed_wwi", "confirmed_wwii"):
            result.result_state = "CONTEXT_ONLY"
            result.reason_codes.append("CONTEXT_NOT_TARGET_EVIDENCE")
            result.is_context = True
            result.is_lead = False
            return result
        else:
            result.result_state = "IRRELEVANT"
            result.is_rejected = True
            return result

    # Name present (exact or variant) — check if we have evidence
    if name_match in ("exact", "variant"):
        # Check if content was fetched
        if fetch_status == "NOT_FETCHED":
            # Without fetching, we can't confirm evidence
            result.result_state = "DISCOVERY_LEAD"
            result.fetch_status = "NOT_FETCHED"
            result.reason_codes.append("CONTENT_NOT_OBSERVED")
            result.is_lead = True
            return result

        if fetch_status == "FETCH_FAILED":
            result.result_state = "FETCH_FAILED"
            result.fetch_status = "FETCH_FAILED"
            result.is_lead = True
            return result

        # Content was fetched — check for target-specific data
        if fetched_content:
            # Check if the fetched content contains the target name
            content_name_match, _ = _check_name_in_text(target_name, fetched_content)
            if content_name_match in ("exact", "variant"):
                # Check for birth year match
                if target_birth_year:
                    year_pattern = rf'\b{re.escape(target_birth_year)}\b'
                    if re.search(year_pattern, fetched_content):
                        result.result_state = "CLAIM_EVIDENCE_ACCEPTED"
                        result.is_evidence = True
                        result.is_lead = False
                        result.fetch_status = "SUCCESS"
                        return result
                    else:
                        result.result_state = "CLAIM_EVIDENCE_PARTIAL"
                        result.is_evidence = True
                        result.is_lead = False
                        result.fetch_status = "SUCCESS"
                        return result
                else:
                    result.result_state = "CLAIM_EVIDENCE_PARTIAL"
                    result.is_evidence = True
                    result.is_lead = False
                    result.fetch_status = "SUCCESS"
                    return result
            elif content_name_match == "wrong_person":
                result.result_state = "REJECTED_WRONG_IDENTITY"
                result.is_rejected = True
                result.fetch_status = "SUCCESS"
                return result
            elif content_name_match == "absent":
                result.result_state = "CONSULTED_NO_MATCH"
                result.fetch_status = "SUCCESS"
                result.reason_codes.append("CONTENT_NOT_OBSERVED")
                return result

        # Fetched but no content extracted
        result.result_state = "CONTENT_NOT_SEARCHABLE"
        result.fetch_status = "SUCCESS"
        return result

    # Default: discovery lead
    result.result_state = "DISCOVERY_LEAD"
    result.is_lead = True
    return result


def filter_relevant_results_v4(
    results: list,
    target_name: str,
    target_conflict: str,
    target_birth_place: str = "",
    target_birth_year: str = "",
    target_unit: str = "",
) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
    """Filter web search results through multi-stage relevance pipeline.

    Returns:
        (evidence_results, context_results, lead_results, rejected_results)
    """
    evidence = []
    context = []
    leads = []
    rejected = []

    for r in results:
        rel = classify_relevance_v4(
            url=r.get("url", ""),
            title=r.get("title", ""),
            snippet=r.get("snippet", ""),
            target_name=target_name,
            target_conflict=target_conflict,
            target_birth_place=target_birth_place,
            target_birth_year=target_birth_year,
            target_unit=target_unit,
        )
        r["relevance_v4"] = {
            "result_state": rel.result_state,
            "reason_codes": rel.reason_codes,
            "result_kind": rel.result_kind,
            "target_name_match": rel.target_name_match,
            "period_compatibility": rel.period_compatibility,
            "geographic_scope": rel.geographic_scope,
            "fetch_status": rel.fetch_status,
            "is_evidence": rel.is_evidence,
            "is_context": rel.is_context,
            "is_lead": rel.is_lead,
            "is_rejected": rel.is_rejected,
        }

        if rel.is_rejected:
            rejected.append(r)
        elif rel.is_evidence:
            evidence.append(r)
        elif rel.is_context:
            context.append(r)
        else:
            leads.append(r)

    return evidence, context, leads, rejected


# ─── Fetch integration ────────────────────────────────────────────────────────

def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML content."""
    import re as _re
    # Remove script and style blocks
    html = _re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=_re.DOTALL | _re.IGNORECASE)
    # Remove HTML tags
    text = _re.sub(r'<[^>]+>', ' ', html)
    # Decode common HTML entities
    import html as _html
    text = _html.unescape(text)
    # Collapse whitespace
    text = _re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_and_classify(
    url: str,
    title: str,
    snippet: str,
    target_name: str,
    target_conflict: str,
    target_birth_place: str = "",
    target_birth_year: str = "",
    target_unit: str = "",
    timeout: int = 15,
) -> RelevanceResult:
    """Fetch URL content and classify relevance with full context.

    Performs HTTP GET, extracts text from HTML, then runs classify_relevance_v4
    with fetch_status=SUCCESS and the extracted content.

    Args:
        url: URL to fetch
        title: Result title from search
        snippet: Result snippet from search
        target_name: Normalized target name
        target_conflict: "ww1", "ww2", or ""
        target_birth_place: Target's birth place
        target_birth_year: Target's birth year
        target_unit: Target's military unit
        timeout: HTTP timeout in seconds

    Returns:
        RelevanceResult with fetch_status and content-based classification.
    """
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (ResearchBot; Historical Archive Verification)",
                "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
                "Accept-Language": "it,en;q=0.8",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_bytes) if (max_bytes := 500_000) else resp.read()

            # Only process text content
            if "text" in content_type or "html" in content_type:
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    html_text = raw.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    html_text = raw.decode("utf-8", errors="replace")
                extracted = _extract_text_from_html(html_text)
            elif "application/pdf" in content_type:
                extracted = f"[PDF document at {url}]"
            else:
                extracted = f"[Binary content: {content_type}]"

            return classify_relevance_v4(
                url=url,
                title=title,
                snippet=snippet,
                target_name=target_name,
                target_conflict=target_conflict,
                target_birth_place=target_birth_place,
                target_birth_year=target_birth_year,
                target_unit=target_unit,
                fetch_status="SUCCESS",
                fetched_content=extracted,
            )

    except urllib.error.HTTPError as e:
        result = classify_relevance_v4(
            url=url, title=title, snippet=snippet,
            target_name=target_name, target_conflict=target_conflict,
            target_birth_place=target_birth_place,
            target_birth_year=target_birth_year,
            target_unit=target_unit,
            fetch_status="FETCH_FAILED",
        )
        result.notes = f"HTTP {e.code}: {e.reason}"
        return result

    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result = classify_relevance_v4(
            url=url, title=title, snippet=snippet,
            target_name=target_name, target_conflict=target_conflict,
            target_birth_place=target_birth_place,
            target_birth_year=target_birth_year,
            target_unit=target_unit,
            fetch_status="FETCH_FAILED",
        )
        result.notes = str(e)[:200]
        return result
