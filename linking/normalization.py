"""
Versioned normalizers for linking v2.

Each normalizer preserves the original value alongside the normalized form.
Normalizers are versioned (VERSION constant) for reproducibility.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date


VERSION = "2.0.0"


@dataclass
class NormalizedName:
    original: str
    normalized: str
    cognome_normalized: str = ""
    nome_normalized: str = ""
    version: str = field(default=VERSION, init=False)


@dataclass
class NormalizedDate:
    original: str
    normalized: str | None = None
    precision: str = "unknown"  # exact, month, year, range, circa, before, after, unknown
    start: str | None = None
    end: str | None = None
    qualifier: str = ""  # circa, before, after, "" (none)
    version: str = field(default=VERSION, init=False)


# Place type taxonomy
PLACE_TYPES = [
    "birth_place", "death_place", "internment_place",
    "capture_place", "burial_place", "residence",
    "municipality", "current_municipality", "event_location",
    "unknown",
]

# Map claim predicates to place types
PREDICATE_TO_PLACE_TYPE: dict[str, str] = {
    "birth_place": "birth_place",
    "birth_province": "birth_place",
    "death_place": "death_place",
    "death_country": "death_place",
    "internment_place": "internment_place",
    "capture_place": "capture_place",
    "burial_place": "burial_place",
    "burial_country": "burial_place",
    "residence": "residence",
    "municipality": "municipality",
    "current_municipality": "current_municipality",
    "event_location": "event_location",
}


@dataclass
class NormalizedPlace:
    original: str
    normalized: str
    country: str = ""
    region: str = ""
    place_type: str = "unknown"  # from PLACE_TYPES
    latitude: float | None = None
    longitude: float | None = None
    historical_aliases: list[str] = field(default_factory=list)
    valid_period_start: str | None = None
    valid_period_end: str | None = None
    version: str = field(default=VERSION, init=False)


def normalize_name(cognome: str, nome: str = "") -> NormalizedName:
    """
    Normalize a personal name preserving original forms.
    
    - Unicode NFKD decomposition + accent stripping for matching key
    - Lowercase for matching
    - Original values preserved in .original
    """
    def _norm(s: str) -> str:
        if not s:
            return ""
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        s = s.lower().strip()
        s = re.sub(r"[^a-z\s'\-]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s
    
    cog = _norm(cognome)
    nom = _norm(nome)
    full = f"{cog} {nom}".strip()
    
    return NormalizedName(
        original=f"{cognome} {nome}".strip(),
        normalized=full,
        cognome_normalized=cog,
        nome_normalized=nom,
    )


# Italian month name → number
_ITALIAN_MONTHS = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def normalize_date(raw: str) -> NormalizedDate:
    """
    Normalize a date string with precision tracking.
    
    Supports:
    - ISO dates: 1917-10-24
    - Italian dates: 24/10/1917, 24 ott 1917, 24 ottobre 1917
    - Year only: 1917
    - Year range: 1915-1918
    - Month + year: 10/1917, ott 1917
    - Circa dates: ca. 1917, circa 1917, ca 1917
    - Before/after: prima del 1917, dopo il 1917, before 1917, after 1917
    """
    if not raw or not raw.strip():
        return NormalizedDate(original=raw or "")
    
    s = raw.strip()
    qualifier = ""
    
    # Strip circa/before/after qualifiers
    circa_match = re.match(r"^(?:ca\.?|circa)\s+(.+)$", s, re.IGNORECASE)
    if circa_match:
        qualifier = "circa"
        s = circa_match.group(1).strip()
    
    before_match = re.match(r"^(?:prima\s+(?:del|dell'|dei|delle)?|before)\s+(.+)$", s, re.IGNORECASE)
    if before_match:
        qualifier = "before"
        s = before_match.group(1).strip()
    
    after_match = re.match(r"^(?:dopo\s+(?:il|l'|i|le)?|after)\s+(.+)$", s, re.IGNORECASE)
    if after_match:
        qualifier = "after"
        s = after_match.group(1).strip()
    
    # ISO format: 1917-10-24
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        precision = "circa" if qualifier == "circa" else "exact"
        return NormalizedDate(
            original=raw,
            normalized=s,
            precision=precision,
            start=s,
            end=s,
            qualifier=qualifier,
        )
    
    # Italian format: 24/10/1917
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        iso = f"{y}-{int(mo):02d}-{int(d):02d}"
        precision = "circa" if qualifier == "circa" else "exact"
        return NormalizedDate(
            original=raw,
            normalized=iso,
            precision=precision,
            start=iso,
            end=iso,
            qualifier=qualifier,
        )
    
    # Italian textual: 24 ott 1917, 24 ottobre 1917
    m = re.match(r"^(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})$", s)
    if m:
        d, month_name, y = m.groups()
        mo = _ITALIAN_MONTHS.get(month_name.lower())
        if mo:
            iso = f"{y}-{mo:02d}-{int(d):02d}"
            precision = "circa" if qualifier == "circa" else "exact"
            return NormalizedDate(
                original=raw,
                normalized=iso,
                precision=precision,
                start=iso,
                end=iso,
                qualifier=qualifier,
            )
    
    # Year range: 1915-1918
    m = re.match(r"^(\d{4})\s*[-\u2013]\s*(\d{4})$", s)
    if m:
        y1, y2 = m.groups()
        return NormalizedDate(
            original=raw,
            normalized=f"{y1}/{y2}",
            precision="range",
            start=y1,
            end=y2,
            qualifier=qualifier,
        )
    
    # Year only: 1917
    m = re.match(r"^(\d{4})$", s)
    if m:
        y = m.group(1)
        precision = "circa" if qualifier == "circa" else "year"
        if qualifier == "before":
            precision = "before"
        elif qualifier == "after":
            precision = "after"
        return NormalizedDate(
            original=raw,
            normalized=y,
            precision=precision,
            start=y,
            end=y,
            qualifier=qualifier,
        )
    
    # Month + year: 10/1917
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        mo, y = m.groups()
        iso_month = f"{y}-{int(mo):02d}"
        precision = "circa" if qualifier == "circa" else "month"
        return NormalizedDate(
            original=raw,
            normalized=iso_month,
            precision=precision,
            start=iso_month,
            end=iso_month,
            qualifier=qualifier,
        )
    
    # Italian month name + year: ott 1917, ottobre 1917
    m = re.match(r"^([a-zA-Z]+)\s+(\d{4})$", s)
    if m:
        month_name, y = m.groups()
        mo = _ITALIAN_MONTHS.get(month_name.lower())
        if mo:
            iso_month = f"{y}-{mo:02d}"
            precision = "circa" if qualifier == "circa" else "month"
            return NormalizedDate(
                original=raw,
                normalized=iso_month,
                precision=precision,
                start=iso_month,
                end=iso_month,
                qualifier=qualifier,
            )
    
    return NormalizedDate(original=raw, precision="unknown", qualifier=qualifier)


def normalize_place(raw: str, place_type: str = "unknown") -> NormalizedPlace:
    """
    Normalize a place name preserving historical context.
    
    place_type: semantic type from PLACE_TYPES (birth_place, death_place, etc.)
    """
    if not raw or not raw.strip():
        return NormalizedPlace(original=raw or "", normalized="", place_type=place_type)
    
    s = raw.strip()
    normalized = unicodedata.normalize("NFKD", s)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = normalized.strip()
    
    return NormalizedPlace(
        original=s,
        normalized=normalized,
        place_type=place_type,
    )


def date_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """
    Check if two date ranges overlap.
    Handles year-level and ISO-level dates.
    """
    def _to_year(d: str | None) -> int | None:
        if not d:
            return None
        try:
            return int(d[:4])
        except (ValueError, IndexError):
            return None
    
    a_s = _to_year(a_start)
    a_e = _to_year(a_end)
    b_s = _to_year(b_start)
    b_e = _to_year(b_end)
    
    if a_s is None or b_s is None:
        return False
    if a_e is None:
        a_e = a_s
    if b_e is None:
        b_e = b_s
    
    return a_s <= b_e and b_s <= a_e


# ─── Family relations parser ─────────────────────────────────────────────────

RELATION_TYPES = ["father", "mother", "spouse", "sibling", "unknown"]


@dataclass
class NormalizedRelation:
    """A parsed family relation from a text field (e.g. paternity)."""
    original: str
    relation_type: str = "unknown"  # from RELATION_TYPES
    related_name: str = ""
    related_cognome: str = ""
    related_nome: str = ""
    confidence: float = 0.0
    version: str = field(default=VERSION, init=False)


def parse_paternity(raw: str) -> NormalizedRelation:
    """
    Parse Italian paternity field to extract father's name.
    
    Common patterns in Italian military records:
    - "fu Giovanni" → father deceased, named Giovanni
    - "di Giovanni" → son of Giovanni
    - "f. Giovanni" → figlio di Giovanni
    - "figlio di Giovanni" → son of Giovanni
    - "fu di Giovanni" → son of deceased Giovanni
    - "Giovanni" → just the name (implicit father)
    - "fu Giovanni di Antonio" → father Giovanni, grandfather Antonio
    """
    if not raw or not raw.strip():
        return NormalizedRelation(original=raw or "")
    
    s = raw.strip()
    
    # Pattern: "fu <name>" or "fu di <name>"
    m = re.match(r"^fu\s+(?:di\s+)?(.+)$", s, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        cog, nom = _split_italian_name(name)
        return NormalizedRelation(
            original=raw,
            relation_type="father",
            related_name=name,
            related_cognome=cog,
            related_nome=nom,
            confidence=0.95,
        )
    
    # Pattern: "figlio di <name>"
    m = re.match(r"^figlio\s+di\s+(.+)$", s, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        cog, nom = _split_italian_name(name)
        return NormalizedRelation(
            original=raw,
            relation_type="father",
            related_name=name,
            related_cognome=cog,
            related_nome=nom,
            confidence=0.95,
        )
    
    # Pattern: "f. <name>" or "f.di <name>"
    m = re.match(r"^f\.?\s*(?:di\s+)?(.+)$", s, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        cog, nom = _split_italian_name(name)
        return NormalizedRelation(
            original=raw,
            relation_type="father",
            related_name=name,
            related_cognome=cog,
            related_nome=nom,
            confidence=0.85,
        )
    
    # Pattern: "di <name>" (son of)
    m = re.match(r"^di\s+(.+)$", s, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        cog, nom = _split_italian_name(name)
        return NormalizedRelation(
            original=raw,
            relation_type="father",
            related_name=name,
            related_cognome=cog,
            related_nome=nom,
            confidence=0.75,
        )
    
    # Fallback: treat entire string as father's name
    cog, nom = _split_italian_name(s)
    return NormalizedRelation(
        original=raw,
        relation_type="father",
        related_name=s,
        related_cognome=cog,
        related_nome=nom,
        confidence=0.50,
    )


def _split_italian_name(full: str) -> tuple[str, str]:
    """Split an Italian name into (cognome, nome).
    
    Italian names in paternity fields are typically just a given name,
    but may include surname. We assume last word(s) are given name
    if there are 2+ words, first word is cognome.
    """
    parts = full.split()
    if len(parts) == 0:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    # 2+ parts: first = cognome, rest = nome
    return (parts[0], " ".join(parts[1:]))
