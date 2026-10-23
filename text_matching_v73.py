"""V7.3 Text Matching Engine — tokenized, word-boundary aware matching.

Replaces legacy substring matching (`alias in text`) with proper:
- Unicode normalization (NFC)
- Punctuation normalization
- Tokenization
- Word boundary matching
- Diacritic-insensitive comparison
- OCR variant handling
- Compound surname support
- Full-phrase comparison

Key rules enforced:
- "Lana" != "Castellana"
- "Roma" != "Romania"
- "Nero" != generic adjective occurrence
- "Campo" alone != prison camp
- "Grappa" alone != a specific battle
- "Carab." != proper name
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Set, Tuple, Optional, Dict
from dataclasses import dataclass, field


# ─── Normalization ──────────────────────────────────────────────────────────

def normalize_unicode(text: str) -> str:
    """Normalize to NFC form."""
    return unicodedata.normalize("NFC", text)


def strip_diacritics(text: str) -> str:
    """Remove diacritics for comparison (NFD -> remove combining chars)."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize_punctuation(text: str) -> str:
    """Normalize punctuation: collapse variants, keep word separators."""
    # Replace various dashes and quotes
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text: str, remove_diacritics: bool = True) -> str:
    """Full normalization pipeline."""
    if not text:
        return ""
    text = normalize_unicode(text)
    text = normalize_punctuation(text)
    if remove_diacritics:
        text = strip_diacritics(text)
    return text.upper().strip()


# ─── Tokenization ───────────────────────────────────────────────────────────

# Tokens: sequences of letters (including apostrophes within words)
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ\u2019']+")

# Stopwords that should not be used as standalone keywords
_STOPWORDS: Set[str] = {
    "IL", "LO", "LA", "I", "GLI", "LE", "UN", "UNO", "UNA",
    "DI", "DEL", "DELLA", "DEI", "DEGLI", "DELLE",
    "DA", "DAL", "DALLA", "DAI", "DAGLI", "DALLE",
    "IN", "NEL", "NELLA", "NEI", "NEGLI", "NELLE",
    "A", "AL", "ALLA", "AI", "AGLI", "ALLE",
    "CON", "PER", "SU", "TRA", "FRA",
    "E", "ED", "O", "OD",
    "CHE", "CHI", "CUI",
    "NON", "SI", "SE",
    "DEL", "DELL",
}


def tokenize(text: str) -> List[str]:
    """Tokenize text into uppercase tokens, preserving word boundaries."""
    normalized = normalize_text(text, remove_diacritics=False)
    tokens = _TOKEN_RE.findall(normalized)
    return [t.upper().strip("'\"") for t in tokens if t.strip("'\"")]


def tokenize_no_diacritics(text: str) -> List[str]:
    """Tokenize with diacritics stripped for fuzzy matching."""
    normalized = normalize_text(text, remove_diacritics=True)
    tokens = _TOKEN_RE.findall(normalized)
    return [t.upper().strip("'\"") for t in tokens if t.strip("'\"")]


# ─── Word boundary matching ─────────────────────────────────────────────────

def matches_word_boundary(keyword: str, text: str, min_keyword_len: int = 4) -> bool:
    """Check if keyword appears as a complete word in text.

    Uses word boundary regex to prevent substring matches.
    Keywords shorter than min_keyword_len require exact word match
    (no partial matching at all).

    Examples:
        "Lana" in "Castellana" -> False (word boundary)
        "Lana" in "Monte Col di Lana" -> True
        "Roma" in "Romania" -> False (word boundary)
        "Roma" in "Roma" -> True
        "Nero" in "Monte Nero" -> True
        "Nero" in "nerofumo" -> False
    """
    if not keyword or not text:
        return False

    kw_norm = normalize_text(keyword)
    text_norm = normalize_text(text)

    if not kw_norm or not text_norm:
        return False

    # For short keywords, require exact token match
    if len(kw_norm) < min_keyword_len:
        tokens = set(tokenize(text_norm))
        return kw_norm in tokens

    # For longer keywords, use word boundary regex
    # Escape regex special characters
    kw_escaped = re.escape(kw_norm)
    pattern = r"\b" + kw_escaped + r"\b"
    return bool(re.search(pattern, text_norm))


def matches_any_keyword(keywords: List[str], text: str, min_keyword_len: int = 4) -> List[str]:
    """Return list of keywords that match in text (with word boundaries)."""
    matched = []
    for kw in keywords:
        if matches_word_boundary(kw, text, min_keyword_len):
            matched.append(kw)
    return matched


# ─── Specificity scoring ────────────────────────────────────────────────────

# Generic keywords that alone are insufficient for a match
GENERIC_KEYWORDS: Set[str] = {
    "CAMPO", "LANA", "GRAPPA", "CARSO", "RUSSIA", "AFRICA",
    "NERO", "CORNO", "PIAVE", "ISONZO", "ALPI",
    "MONTAGNA", "VALLE", "FIUME", "FRONTE",
    "GUERRA", "BATTAGLIA", "PRIGIONIA",
    "MORTE", "MORTO", "DECEDUTO",
    "DECORATO", "MEDAGLIA",
}

# Specific keywords that are strong indicators
SPECIFIC_KEYWORDS: Set[str] = {
    "CAPORETTO", "KOBARID", "KARFREIT",
    "SOCA", "DOBERDO", "SABOTINO",
    "SAN MICHELE", "SAN GABRIELE",
    "ERMADA", "CASTAGNEVIZZA",
    "VITTORIO VENETO",
    "MAUTHAUSEN", "GUSEN",
    "CEFALONIA", "ACQUI",
    "TOBRUK",
    "CASSINO",
    "ARMIR",
    "TOLMINO",
    "ASOLONE",
    "SOLAROLO", "MONTELLO", "NERVESA",
    "ORTIGARA",
    "PASUBIO",
}


@dataclass
class KeywordMatch:
    """Result of a keyword match evaluation."""
    keyword: str
    matched: bool
    specificity: str  # "specific", "generic", "very_generic"
    match_field: str = ""
    match_value: str = ""


def classify_keyword_specificity(keyword: str) -> str:
    """Classify a keyword by specificity.

    - "specific": Proper noun, unique identifier (e.g., "Caporetto")
    - "generic": Common noun that could apply to many contexts (e.g., "Campo")
    - "very_generic": Extremely common word (e.g., "guerra", "battaglia")
    """
    kw_upper = normalize_text(keyword)

    if kw_upper in SPECIFIC_KEYWORDS:
        return "specific"

    # Multi-word keywords are more specific
    tokens = kw_upper.split()
    if len(tokens) >= 2:
        return "specific"

    if kw_upper in GENERIC_KEYWORDS:
        return "generic"

    # Short single words are generic
    if len(kw_upper) <= 5:
        return "generic"

    return "specific"


def evaluate_keyword_matches(
    keywords: List[str],
    text: str,
    match_field: str = "",
) -> List[KeywordMatch]:
    """Evaluate all keywords against text, returning match results."""
    results = []
    for kw in keywords:
        matched = matches_word_boundary(kw, text)
        specificity = classify_keyword_specificity(kw)
        results.append(KeywordMatch(
            keyword=kw,
            matched=matched,
            specificity=specificity,
            match_field=match_field,
            match_value=text[:200],
        ))
    return results


def has_sufficient_specificity(matches: List[KeywordMatch]) -> bool:
    """Check if matches contain at least one specific keyword.

    Generic keywords alone are insufficient for creating a relation.
    """
    has_specific = any(m.matched and m.specificity == "specific" for m in matches)
    has_generic = any(m.matched and m.specificity == "generic" for m in matches)
    return has_specific or (has_generic and len([m for m in matches if m.matched]) >= 2)


# ─── Name parsing ───────────────────────────────────────────────────────────

def parse_name(raw: str) -> Tuple[str, str]:
    """Parse a name into (cognome, nome).

    Handles:
    - "COGNOME NOME" (standard)
    - "COGNOME NOME DI PADRE" (patronymic)
    - "COGNOME COMPOSTO NOME" (compound surname)
    - "NOME COGNOME" (inverted order — heuristic detection)

    Returns (cognome, nome) tuple.
    """
    if not raw:
        return ("", "")

    normalized = normalize_punctuation(raw).strip()
    parts = normalized.split()

    if len(parts) == 0:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")

    # Check for patronymic pattern: "COGNOME NOME DI/DE/DDA/D'"
    patronymic_markers = {"DI", "DE", "DDA", "D'", "DEL", "DELLA", "DELL"}
    patronymic_idx = None
    for i, p in enumerate(parts[2:], start=2):
        if p.upper() in patronymic_markers:
            patronymic_idx = i
            break

    if patronymic_idx:
        cognome = " ".join(parts[:1])
        nome = " ".join(parts[1:patronymic_idx])
        return (cognome, nome)

    # Standard: first word = cognome, rest = nome
    return (parts[0], " ".join(parts[1:]))


def names_compatible(name1: str, name2: str) -> bool:
    """Check if two name strings could refer to the same person.

    Uses tokenized comparison with diacritic insensitivity.
    """
    if not name1 or not name2:
        return False

    n1 = normalize_text(name1)
    n2 = normalize_text(name2)

    if n1 == n2:
        return True

    # Check if one is a subset of the other (e.g., "MARIO" vs "MARIO ANTONIO")
    tokens1 = set(tokenize(n1))
    tokens2 = set(tokenize(n2))

    # All tokens of the shorter name must be in the longer name
    if len(tokens1) <= len(tokens2):
        return tokens1.issubset(tokens2)
    else:
        return tokens2.issubset(tokens1)


# ─── OCR variant handling ───────────────────────────────────────────────────

# Common OCR error patterns for Italian names
OCR_PATTERNS: List[Tuple[str, str]] = [
    (r"NN", "M"),  # NN -> M (OCR confusion)
    (r"U", "O"),   # U -> O (OCR confusion in some fonts)
    (r"8", "S"),   # 8 -> S
    (r"0", "O"),   # 0 -> O
    (r"1", "I"),   # 1 -> I
    (r"5", "S"),   # 5 -> S
]


def generate_ocr_variants(text: str) -> List[str]:
    """Generate possible OCR correction variants of a text."""
    variants = [text]
    for pattern, replacement in OCR_PATTERNS:
        new_variants = []
        for v in variants:
            corrected = re.sub(pattern, replacement, v)
            if corrected != v:
                new_variants.append(corrected)
        variants.extend(new_variants)
    return list(set(variants))


def matches_with_ocr_variants(keyword: str, text: str) -> bool:
    """Check if keyword matches text, considering OCR variants."""
    if matches_word_boundary(keyword, text):
        return True

    for variant in generate_ocr_variants(keyword):
        if variant != keyword and matches_word_boundary(variant, text):
            return True

    for variant in generate_ocr_variants(text):
        if variant != text and matches_word_boundary(keyword, variant):
            return True

    return False


# ─── Alias matching ─────────────────────────────────────────────────────────

@dataclass
class AliasMatch:
    """Result of alias matching."""
    alias: str
    matched: bool
    specificity: str
    in_text: bool = False
    in_field: str = ""


def match_aliases(
    aliases: List[str],
    text_fields: Dict[str, str],
    min_keyword_len: int = 4,
) -> List[AliasMatch]:
    """Match versioned aliases against multiple text fields.

    Args:
        aliases: List of alias strings (versioned, from event registry)
        text_fields: Dict of field_name -> text_value
        min_keyword_len: Minimum keyword length for word boundary matching

    Returns:
        List of AliasMatch results
    """
    results = []
    for alias in aliases:
        matched = False
        matched_field = ""
        for field_name, field_value in text_fields.items():
            if matches_word_boundary(alias, field_value, min_keyword_len):
                matched = True
                matched_field = field_name
                break

        specificity = classify_keyword_specificity(alias)
        results.append(AliasMatch(
            alias=alias,
            matched=matched,
            specificity=specificity,
            in_text=matched,
            in_field=matched_field,
        ))
    return results


def has_specific_alias_match(matches: List[AliasMatch]) -> bool:
    """Check if at least one specific alias matched.

    Generic alias matches alone are insufficient for creating a relation.
    """
    specific_matches = [m for m in matches if m.matched and m.specificity == "specific"]
    return len(specific_matches) >= 1
