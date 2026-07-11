import time
import re
import requests
from typing import Optional

_cache: dict[str, bool] = {}
_last_request = 0.0
_MIN_INTERVAL = 1.1  # Nominatim rate limit: 1 req/sec

# Known German exonyms for Italian/other places that appear in IMI documents
# These are valid historical names, not OCR errors
KNOWN_EXONYMS = {
    "brandenburg", "brandemburg", "brandemburg havel", "neuw altstdatlicher",
    "friedorf", "nirenof", "kiel", "flossenburg", "stamm",
    "berlino", "berlin", "monaco", "munchen", "münchen",
    "amburgo", "hamburg", "norimberga", "nurnberg", "nürnberg",
    "dresda", "dresden", "leipzig", "francoforte", "frankfurt",
    "stoccarda", "stuttgart", "colonia", "koln", "köln",
    "brema", "bremen", "hanover", "hannover", "essen",
    "dortmund", "duisburg", "bochum", "wuppertal",
    "wien", "vienna", "praga", "prag", "varsavia", "warschau",
    "krakow", "cracovia", "danzica", "gdansk",
    "stalingrado", "volgograd", "mosca", "moskva",
    "brandemburg flavel", "brandenburg havel",
}

# Common false-positive patterns that shouldn't be flagged
_SKIP_PATTERNS = re.compile(r"^(F\.?\s*\d|Foglio|Pagina|N\.?\s*\d)", re.IGNORECASE)


def _rate_limit():
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request = time.time()


def _clean_place(name: str) -> str:
    """Clean a place name for validation."""
    if not name:
        return ""
    name = name.strip().strip(".,;:-+†*")
    # Remove trailing F.numbers
    name = re.sub(r"\s*F\.?\s*\d+.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*-F\.?\s*\d+.*$", "", name, flags=re.IGNORECASE)
    # If composite address like "Agrigento, Via Calcatore", take first part (city)
    if "," in name:
        parts = [p.strip() for p in name.split(",") if p.strip()]
        if parts:
            name = parts[0]
    return name.strip()


def validate_place(name: str) -> dict:
    """Validate a place name using Nominatim OSM API.
    Returns {"valid": bool, "original": str, "cleaned": str, "matched_name": str or None, "error": str or None}
    """
    result = {"valid": False, "original": name, "cleaned": "", "matched_name": None, "error": None}
    if not name or not name.strip():
        result["valid"] = True  # empty = skip validation
        return result

    cleaned = _clean_place(name)
    result["cleaned"] = cleaned
    if not cleaned:
        result["valid"] = True
        return result

    if _SKIP_PATTERNS.match(cleaned):
        result["valid"] = True
        return result

    key = cleaned.lower()
    if key in _cache:
        result["valid"] = _cache[key]
        if result["valid"]:
            result["matched_name"] = cleaned
        return result

    # Check known exonyms first (no API call)
    if key in KNOWN_EXONYMS or any(key.startswith(ex) for ex in KNOWN_EXONYMS):
        _cache[key] = True
        result["valid"] = True
        result["matched_name"] = cleaned
        return result

    # Query Nominatim
    try:
        _rate_limit()
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": cleaned,
                "format": "json",
                "limit": 1,
                "addressdetails": 0,
            },
            headers={"User-Agent": "IMI-Extractor/1.0 (historical research)"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                _cache[key] = True
                result["valid"] = True
                result["matched_name"] = data[0].get("display_name", cleaned).split(",")[0]
                return result
            else:
                _cache[key] = False
                result["valid"] = False
                result["error"] = "Localita non trovata"
                return result
        else:
            result["error"] = f"HTTP {resp.status_code}"
            # On API error, don't flag as invalid
            result["valid"] = True
            return result
    except Exception as e:
        result["error"] = str(e)
        # On network error, don't flag as invalid
        result["valid"] = True
        return result


def validate_record_locations(record: dict) -> dict:
    """Validate luogo_nascita, luogo_internamento, and residenza in a record.
    Returns updated record with needs_review/review_reason if locations are invalid.
    """
    reasons = []
    fields_to_check = [
        ("luogo_nascita", "luogo di nascita"),
        ("luogo_internamento", "luogo di internamento"),
        ("residenza", "residenza"),
    ]

    for field, label in fields_to_check:
        val = record.get(field)
        if val and val.strip():
            result = validate_place(val)
            if not result["valid"] and result["error"] == "Localita non trovata":
                reasons.append(f"{label} '{val}' non verificata")

    if reasons:
        existing_reason = record.get("review_reason", "")
        new_reason = "; ".join(reasons)
        if existing_reason:
            record["review_reason"] = existing_reason + "; " + new_reason
        else:
            record["review_reason"] = new_reason
        record["needs_review"] = True

    record["luogo_validato"] = True
    return record
