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
    precision: str = "unknown"  # exact, month, year, range, unknown
    start: str | None = None
    end: str | None = None
    version: str = field(default=VERSION, init=False)


@dataclass
class NormalizedPlace:
    original: str
    normalized: str
    country: str = ""
    region: str = ""
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


def normalize_date(raw: str) -> NormalizedDate:
    """
    Normalize a date string with precision tracking.
    
    Supports:
    - ISO dates: 1917-10-24
    - Italian dates: 24/10/1917, 24 ott 1917
    - Year only: 1917
    - Year range: 1915-1918
    """
    if not raw or not raw.strip():
        return NormalizedDate(original=raw or "")
    
    s = raw.strip()
    
    # ISO format: 1917-10-24
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return NormalizedDate(
            original=raw,
            normalized=s,
            precision="exact",
            start=s,
            end=s,
        )
    
    # Italian format: 24/10/1917
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        iso = f"{y}-{int(mo):02d}-{int(d):02d}"
        return NormalizedDate(
            original=raw,
            normalized=iso,
            precision="exact",
            start=iso,
            end=iso,
        )
    
    # Year range: 1915-1918
    m = re.match(r"^(\d{4})\s*[-–]\s*(\d{4})$", s)
    if m:
        y1, y2 = m.groups()
        return NormalizedDate(
            original=raw,
            normalized=f"{y1}/{y2}",
            precision="range",
            start=y1,
            end=y2,
        )
    
    # Year only: 1917
    m = re.match(r"^(\d{4})$", s)
    if m:
        y = m.group(1)
        return NormalizedDate(
            original=raw,
            normalized=y,
            precision="year",
            start=y,
            end=y,
        )
    
    # Month + year: ott 1917, 10/1917
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        mo, y = m.groups()
        return NormalizedDate(
            original=raw,
            normalized=f"{y}-{int(mo):02d}",
            precision="month",
            start=f"{y}-{int(mo):02d}",
            end=f"{y}-{int(mo):02d}",
        )
    
    return NormalizedDate(original=raw, precision="unknown")


def normalize_place(raw: str) -> NormalizedPlace:
    """
    Normalize a place name preserving historical context.
    """
    if not raw or not raw.strip():
        return NormalizedPlace(original=raw or "", normalized="")
    
    s = raw.strip()
    normalized = unicodedata.normalize("NFKD", s)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = normalized.strip()
    
    return NormalizedPlace(
        original=s,
        normalized=normalized,
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
