"""V7.3-Fase9: Historical-geographical context for places.

Provides context for places mentioned in historical records:
  - Historical name variants (Italian, German, local names)
  - Border changes (Austro-Hungarian → Italian, etc.)
  - Historical region mapping (Trentino, Südtirol, Istria, Dalmatia)
  - Place disambiguation (same name, different places)
  - Temporal validity of place names (when was a name in use)

Key invariants:
  1. Place context is CONTEXT_EVIDENCE (not PERSON_EVIDENCE)
  2. Historical names are variants, not corrections — original is preserved
  3. Border changes are annotated, not silently applied
  4. Ambiguous place names are flagged, not resolved automatically
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ─── Historical place variants ───────────────────────────────────────────────
# Maps Italian name → historical variants (German, local, Austro-Hungarian, etc.)
# Source: historical atlases, ISTAT, Austrian censuses (Volkszählung)

HISTORICAL_PLACE_VARIANTS: Dict[str, Dict[str, str]] = {
    # Trentino-Alto Adige / Südtirol
    "trento": {"italian": "Trento", "german": "Trient", "historical": "Tridentum"},
    "bolzano": {"italian": "Bolzano", "german": "Bozen", "historical": "Bauzanum"},
    "merano": {"italian": "Merano", "german": "Meran", "historical": "Mais"},
    "brunico": {"italian": "Brunico", "german": "Bruneck"},
    "bressanone": {"italian": "Bressanone", "german": "Brixen"},
    "chiusa": {"italian": "Chiusa", "german": "Klausen"},
    "vana": {"italian": "Vipiteno", "german": "Sterzing"},
    "vipiteno": {"italian": "Vipiteno", "german": "Sterzing"},
    # Friuli-Venezia Giulia
    "trieste": {"italian": "Trieste", "german": "Triest", "slovenian": "Trst"},
    "gorizia": {"italian": "Gorizia", "german": "Görz", "slovenian": "Gorica"},
    "udine": {"italian": "Udine", "german": "Udine", "friulian": "Udin"},
    "pola": {"italian": "Pola", "german": "Pola", "croatian": "Pula"},
    "fiume": {"italian": "Fiume", "german": "Sankt Veit am Pflaumb", "croatian": "Rijeka"},
    "capodistria": {"italian": "Capodistria", "slovenian": "Koper"},
    "isola": {"italian": "Isola d'Istria", "slovenian": "Izola"},
    # Veneto
    "verona": {"italian": "Verona", "german": "Verona", "historical": "Veronia"},
    "vicenza": {"italian": "Vicenza", "german": "Vicenza"},
    "padova": {"italian": "Padova", "german": "Padua", "latin": "Patavium"},
    # Austrian camps (WWI)
    "sigmundsherberg": {"italian": "Sigmundsherberg", "german": "Sigmundsherberg"},
    "rastatt": {"italian": "Rastatt", "german": "Rastatt"},
    "mauthausen": {"italian": "Mauthausen", "german": "Mauthausen"},
    "gusen": {"italian": "Gusen", "german": "Gusen"},
    # WWII camps
    "dachau": {"italian": "Dachau", "german": "Dachau"},
    "auschwitz": {"italian": "Auschwitz", "german": "Auschwitz", "polish": "Oświęcim"},
    "birkenau": {"italian": "Birkenau", "german": "Birkenau", "polish": "Brzezinka"},
    # Major cities
    "torino": {"italian": "Torino", "german": "Turin", "french": "Turin"},
    "milano": {"italian": "Milano", "german": "Mailand"},
    "roma": {"italian": "Roma", "german": "Rom", "latin": "Roma"},
    "napoli": {"italian": "Napoli", "german": "Neapel"},
    "firenze": {"italian": "Firenze", "german": "Florenz", "latin": "Florentia"},
    "genova": {"italian": "Genova", "german": "Genua"},
    "bologna": {"italian": "Bologna", "german": "Bologna", "latin": "Bononia"},
}

# Reverse lookup: variant name (lowercase) → canonical Italian name
_VARIANT_TO_CANONICAL: Dict[str, str] = {}
for canonical, variants in HISTORICAL_PLACE_VARIANTS.items():
    _VARIANT_TO_CANONICAL[canonical.lower()] = canonical
    for lang, name in variants.items():
        _VARIANT_TO_CANONICAL[name.lower()] = canonical


# ─── Historical regions ──────────────────────────────────────────────────────

HISTORICAL_REGIONS: Dict[str, Dict[str, str]] = {
    "trentino": {
        "italian": "Trentino",
        "historical": "Welschtirol (Austro-Hungarian Empire)",
        "period": "1861-1918 Austrian, 1919+ Italian",
        "current": "Trentino-Alto Adige",
    },
    "sudtirol": {
        "italian": "Südtirol / Alto Adige",
        "historical": "Kronland Tirol (Austro-Hungarian Empire)",
        "period": "1861-1918 Austrian, 1919+ Italian",
        "current": "Trentino-Alto Adige",
    },
    "istria": {
        "italian": "Istria",
        "historical": "Austrian Littoral (Küstenland)",
        "period": "1861-1918 Austrian, 1919-1947 Italian, 1947+ Yugoslav/Croatian",
        "current": "Croatia / Slovenia",
    },
    "dalmazia": {
        "italian": "Dalmazia",
        "historical": "Kingdom of Dalmatia (Austro-Hungarian)",
        "period": "1861-1918 Austrian, 1918-1947 Italian/Yugoslav, 1947+ Yugoslav",
        "current": "Croatia",
    },
    "friuli": {
        "italian": "Friuli",
        "historical": "Part of Veneto (Austrian 1814-1866, Italian 1866+)",
        "period": "1861+ Italian (mostly)",
        "current": "Friuli-Venezia Giulia",
    },
    "venezia_giulia": {
        "italian": "Venezia Giulia",
        "historical": "Austrian Littoral (Küstenland)",
        "period": "1861-1918 Austrian, 1919-1947 Italian, 1947+ Yugoslav/Italian",
        "current": "Friuli-Venezia Giulia / Slovenia / Croatia",
    },
}

# ─── Ambiguous place names (same name, multiple places) ─────────────────────

AMBIGUOUS_PLACES: Dict[str, List[str]] = {
    "san giovanni": [
        "San Giovanni in Persiceto (BO)",
        "San Giovanni Valdarno (AR)",
        "San Giovanni Rotondo (FG)",
        "San Giovanni Ilarione (VR)",
    ],
    "san pietro": [
        "San Pietro in Gu (PD)",
        "San Pietro Vernotico (BR)",
        "San Pietro a Maida (CZ)",
    ],
    "santa maria": [
        "Santa Maria di Sala (VE)",
        "Santa Maria Capua Vetere (CE)",
        "Santa Maria della Versa (PV)",
    ],
    "castelnuovo": [
        "Castelnuovo del Garda (VR)",
        "Castelnuovo Berardenga (SI)",
        "Castelnuovo Scrivia (AL)",
        "Castelnuovo Magra (SP)",
    ],
}


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class PlaceContext:
    """Historical-geographical context for a place."""
    original_name: str = ""
    canonical_italian: str = ""
    historical_variants: Dict[str, str] = field(default_factory=dict)
    historical_region: str = ""
    historical_period: str = ""
    current_region: str = ""
    is_ambiguous: bool = False
    ambiguous_matches: List[str] = field(default_factory=list)
    evidence_scope: str = "CONTEXT_EVIDENCE"
    confidence: float = 0.0
    context_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "original_name": self.original_name,
            "canonical_italian": self.canonical_italian,
            "historical_variants": self.historical_variants,
            "historical_region": self.historical_region,
            "historical_period": self.historical_period,
            "current_region": self.current_region,
            "is_ambiguous": self.is_ambiguous,
            "ambiguous_matches": self.ambiguous_matches,
            "evidence_scope": self.evidence_scope,
            "confidence": self.confidence,
            "context_notes": self.context_notes,
        }


# ─── Lookup functions ────────────────────────────────────────────────────────

def get_place_context(place_name: str) -> PlaceContext:
    """Get historical-geographical context for a place name.

    Args:
        place_name: raw place name from a record

    Returns:
        PlaceContext with variants, historical region, and ambiguity info
    """
    if not place_name or not place_name.strip():
        return PlaceContext()

    s = place_name.strip()
    s_lower = s.lower()

    ctx = PlaceContext(original_name=s, evidence_scope="CONTEXT_EVIDENCE")

    # Check historical variants
    canonical = _VARIANT_TO_CANONICAL.get(s_lower)
    if canonical:
        variants = HISTORICAL_PLACE_VARIANTS.get(canonical, {})
        ctx.canonical_italian = variants.get("italian", canonical)
        ctx.historical_variants = variants
        ctx.confidence = 0.90
        ctx.context_notes.append(f"matched_historical_variant:{canonical}")
    else:
        # Try partial match (first 6 chars)
        for variant_lower, canon in _VARIANT_TO_CANONICAL.items():
            if s_lower in variant_lower or variant_lower in s_lower:
                variants = HISTORICAL_PLACE_VARIANTS.get(canon, {})
                ctx.canonical_italian = variants.get("italian", canon)
                ctx.historical_variants = variants
                ctx.confidence = 0.65
                ctx.context_notes.append(f"partial_match:{canon}")
                break

    # Check historical regions
    for region_key, region_info in HISTORICAL_REGIONS.items():
        if region_key in s_lower or s_lower in region_key:
            ctx.historical_region = region_info.get("italian", "")
            ctx.historical_period = region_info.get("period", "")
            ctx.current_region = region_info.get("current", "")
            ctx.context_notes.append(f"historical_region:{region_key}")
            if ctx.confidence < 0.70:
                ctx.confidence = 0.70
            break

    # Check ambiguity
    if s_lower in AMBIGUOUS_PLACES:
        ctx.is_ambiguous = True
        ctx.ambiguous_matches = AMBIGUOUS_PLACES[s_lower]
        ctx.context_notes.append("ambiguous_place_name")
        ctx.confidence = min(ctx.confidence, 0.50)

    if not ctx.canonical_italian and not ctx.historical_region:
        ctx.confidence = 0.20
        ctx.context_notes.append("no_historical_context_found")

    return ctx


def normalize_place_with_context(place_name: str) -> Tuple[str, PlaceContext]:
    """Normalize a place name and return its historical context.

    Returns:
        (normalized_name, PlaceContext)
    """
    ctx = get_place_context(place_name)
    normalized = ctx.canonical_italian or place_name.strip()
    return normalized, ctx


def places_are_compatible(place1: str, place2: str) -> Tuple[bool, str]:
    """Check if two place names refer to the same location.

    Handles historical variants and partial matches.

    Returns:
        (compatible, reason)
    """
    if not place1 or not place2:
        return True, "missing_place_data"

    p1_lower = place1.lower().strip()
    p2_lower = place2.lower().strip()

    # Exact match
    if p1_lower == p2_lower:
        return True, "exact_match"

    # Check if both resolve to same canonical
    c1 = _VARIANT_TO_CANONICAL.get(p1_lower)
    c2 = _VARIANT_TO_CANONICAL.get(p2_lower)
    if c1 and c2 and c1 == c2:
        return True, f"same_canonical:{c1}"

    # Check if one is a variant of the other
    if c1 and c1.lower() == p2_lower:
        return True, f"variant_of_canonical:{c1}"
    if c2 and c2.lower() == p1_lower:
        return True, f"variant_of_canonical:{c2}"

    # Check partial containment (e.g., "San Giovanni" in "San Giovanni in Persiceto")
    if p1_lower in p2_lower or p2_lower in p1_lower:
        return True, "partial_containment"

    # Check historical variants dict
    for canonical, variants in HISTORICAL_PLACE_VARIANTS.items():
        all_names = {canonical.lower()} | {v.lower() for v in variants.values()}
        if p1_lower in all_names and p2_lower in all_names:
            return True, f"historical_variants:{canonical}"

    return False, "different_places"
