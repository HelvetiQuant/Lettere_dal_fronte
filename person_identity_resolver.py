"""PersonIdentityResolver — deterministic identity resolution for PERSON pipeline.

Replaces surname-only matching with a versioned, traceable resolver that:
1. Normalizes names preserving originals (Unicode, accents, punctuation, word boundaries)
2. Uses multiple identifiers (birth date, place, matricola, reparto, etc.)
3. Produces deterministic, explainable status: confirmed | probable | ambiguous | rejected
4. Never uses fuzzy matching alone for confirmed status
5. Preserves initials and multi-part names (e.g. "Luigi A" stays "Luigi A")
6. Handles Cognome Nome, Nome Cognome, Cognome, Nome orderings

RESOLVER_VERSION = "1.0.0"
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple


RESOLVER_VERSION = "1.0.0"

# ═══════════════════════════════════════════════════════════════════════════════
# NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Italian common words that should never match as surnames
_COMMON_WORD_SURNAMES = {
    "ALTA", "ARTI", "BELLA", "BENE", "BUONO", "CAMPO", "CASA", "CITTA",
    "CORTE", "DONNA", "FELICE", "FORTE", "GENTE", "GRANDE", "GUERRA",
    "LUNGO", "MONTE", "MORTE", "NUOVO", "PONTE", "PORTA", "POVERO",
    "PRIMA", "RICO", "ROCCA", "SANTA", "SANTO", "SCUOLA", "SERVA",
    "STELLA", "TERRA", "VIA", "VITA", "VOCE",
}


def normalize_unicode(text: str) -> str:
    """NFKD normalization, preserve original value separately."""
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text)


def strip_accents(text: str) -> str:
    """Remove combining characters (accents) from normalized text."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(text: str) -> str:
    """Full name normalization: lowercase, no accents, no extra spaces, no apostrophes."""
    if not text:
        return ""
    text = strip_accents(text)
    text = text.lower().strip()
    text = re.sub(r"[\"'`'']", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[,;:]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_punctuation(text: str) -> str:
    """Remove controlled punctuation but keep hyphens in compound names."""
    if not text:
        return ""
    text = re.sub(r"[.,;:!?()]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    """Tokenize into words, preserving original tokens."""
    if not text:
        return []
    text = normalize_punctuation(text)
    return [t for t in text.split() if t]


def word_boundary_match(haystack: str, needle: str) -> bool:
    """True word-boundary match, not substring."""
    if not haystack or not needle:
        return False
    pattern = r"\b" + re.escape(needle) + r"\b"
    return bool(re.search(pattern, haystack, re.IGNORECASE))


# ═══════════════════════════════════════════════════════════════════════════════
# NAME PARSING
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParsedName:
    """Parsed name preserving original and all components."""
    raw_value: str
    cognome: str = ""
    nome: str = ""
    initials: List[str] = field(default_factory=list)
    parser_version: str = RESOLVER_VERSION
    parse_confidence: float = 1.0
    parse_rule: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def parse_name(raw: str, cognome_hint: str = "", nome_hint: str = "") -> ParsedName:
    """Parse a name string into components.

    Handles:
    - "COGNOME Nome" (most common in internati)
    - "Nome COGNOME"
    - "COGNOME, Nome"
    - "COGNOME N." / "COGNOME N.A."
    - Compound surnames
    - Multiple given names
    - Initials with and without dots

    If cognome_hint and nome_hint are provided (from DB fields), use them directly.
    """
    raw = (raw or "").strip()
    if not raw:
        return ParsedName(raw_value=raw, parse_confidence=0.0)

    # If we have separate DB fields, use them directly
    if cognome_hint and nome_hint:
        initials = re.findall(r"\b([A-Z])\.", nome_hint)
        return ParsedName(
            raw_value=raw,
            cognome=cognome_hint.strip().upper(),
            nome=nome_hint.strip(),
            initials=[i + "." for i in initials],
            parse_rule="db_fields",
            parse_confidence=1.0,
        )

    # Parse from raw string
    # Try "Cognome, Nome" format first
    if "," in raw:
        parts = raw.split(",", 1)
        cognome = parts[0].strip()
        nome = parts[1].strip()
        initials = re.findall(r"\b([A-Z])\.", nome)
        return ParsedName(
            raw_value=raw,
            cognome=cognome.upper(),
            nome=nome,
            initials=[i + "." for i in initials],
            parse_rule="comma_split",
            parse_confidence=0.9,
        )

    # "COGNOME Nome" or "Nome COGNOME" — heuristic
    tokens = tokenize(raw)
    if len(tokens) == 1:
        return ParsedName(
            raw_value=raw,
            cognome=tokens[0].upper(),
            parse_rule="single_token",
            parse_confidence=0.3,
        )

    # Check if first token is all uppercase (likely cognome)
    if tokens[0].isupper() and len(tokens[0]) >= 2:
        cognome = tokens[0]
        nome = " ".join(tokens[1:])
        parse_rule = "first_uppercase_cognome"
        conf = 0.85
    elif tokens[-1].isupper() and len(tokens[-1]) >= 2:
        # Last token might be cognome (Nome Cognome)
        cognome = tokens[-1]
        nome = " ".join(tokens[:-1])
        parse_rule = "last_uppercase_cognome"
        conf = 0.75
    else:
        # Default: first token is cognome
        cognome = tokens[0]
        nome = " ".join(tokens[1:])
        parse_rule = "default_first_token"
        conf = 0.6

    initials = re.findall(r"\b([A-Z])\.", nome)
    return ParsedName(
        raw_value=raw,
        cognome=cognome.upper(),
        nome=nome,
        initials=[i + "." for i in initials],
        parse_rule=parse_rule,
        parse_confidence=conf,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MATCH STATUS
# ═══════════════════════════════════════════════════════════════════════════════

MATCH_STATUS_VALUES = ["confirmed", "probable", "ambiguous", "rejected"]


@dataclass
class PersonMatchResult:
    """Result of evaluating a single source against a person record."""
    status: str  # confirmed | probable | ambiguous | rejected
    person_table: str = ""
    person_id: int = 0
    source_table: str = ""
    source_id: int = 0
    source_kind: str = ""  # local_db | web | archive | icrc | lebi
    normalized_name: str = ""
    matched_features: List[str] = field(default_factory=list)
    conflicting_features: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    confidence: float = 0.0
    resolver_version: str = RESOLVER_VERSION
    url: str = ""
    title: str = ""
    query_used: str = ""
    provider: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_person_source(self) -> bool:
        """True if this match can be used as a personal source (confirmed or probable)."""
        return self.status in ("confirmed", "probable")


# ═══════════════════════════════════════════════════════════════════════════════
# IDENTIFIER FIELDS
# ═══════════════════════════════════════════════════════════════════════════════

# Strong identifiers that alone can confirm identity
STRONG_IDENTIFIERS = [
    "matricola",
    "numero_prigioniero",
    "archival_id",
]

# Medium identifiers that need at least 2 to confirm
MEDIUM_IDENTIFIERS = [
    "data_nascita",
    "anno_nascita",
    "luogo_nascita",
    "paternita",
    "maternita",
    "data_morte",
    "anno_morte",
    "luogo_morte",
    "luogo_cattura",
    "data_cattura",
    "luogo_internamento",
    "arbeitskommando",
    "grado",
    "reparto",
    "stalag",
]

# Fields that indicate conflict if they disagree
CONFLICT_FIELDS = [
    "data_nascita",
    "anno_nascita",
    "luogo_nascita",
    "matricola",
    "paternita",
    "reparto",
]


# ═══════════════════════════════════════════════════════════════════════════════
# RESOLVER
# ═══════════════════════════════════════════════════════════════════════════════


class PersonIdentityResolver:
    """Deterministic identity resolver for PERSON pipeline.

    Usage:
        resolver = PersonIdentityResolver()
        resolver.set_target(cognome="ALTA", nome="Antonio", record=internato_record)
        result = resolver.evaluate_source(source_record, source_kind="local_db", ...)
        # result.status == "confirmed" | "probable" | "ambiguous" | "rejected"
    """

    def __init__(self):
        self._target_cognome: str = ""
        self._target_nome: str = ""
        self._target_normalized_cognome: str = ""
        self._target_normalized_nome: str = ""
        self._target_parsed: Optional[ParsedName] = None
        self._target_record: Dict[str, Any] = {}
        self._target_id: str = ""
        self._matches: List[PersonMatchResult] = []

    def set_target(
        self,
        cognome: str,
        nome: str,
        record: Dict[str, Any] = None,
        target_id: str = "",
    ):
        """Set the target person for this resolution session."""
        self._target_cognome = (cognome or "").strip().upper()
        self._target_nome = (nome or "").strip()
        self._target_normalized_cognome = normalize_name(cognome or "")
        self._target_normalized_nome = normalize_name(nome or "")
        self._target_record = record or {}
        self._target_id = target_id or str(record.get("id", "")) if record else ""
        self._target_parsed = parse_name(
            f"{cognome} {nome}".strip(),
            cognome_hint=cognome,
            nome_hint=nome,
        )
        self._matches = []

    def evaluate_source(
        self,
        source: Dict[str, Any],
        source_kind: str = "web",
        source_table: str = "",
        source_id: str = "",
        url: str = "",
        title: str = "",
        query_used: str = "",
        provider: str = "",
    ) -> PersonMatchResult:
        """Evaluate a source against the target person.

        Returns PersonMatchResult with deterministic status.
        """
        if not self._target_cognome:
            return PersonMatchResult(
                status="rejected",
                reason_codes=["NO_TARGET_SET"],
                resolver_version=RESOLVER_VERSION,
            )

        # Extract name fields from source
        src_cognome = (source.get("cognome") or "").strip()
        src_nome = (source.get("nome") or "").strip()
        src_nominativo = (source.get("nominativo") or source.get("name") or "").strip()

        # Parse source name
        if src_cognome and src_nome:
            src_parsed = parse_name(
                f"{src_cognome} {src_nome}",
                cognome_hint=src_cognome,
                nome_hint=src_nome,
            )
        elif src_nominativo:
            src_parsed = parse_name(src_nominativo)
        else:
            # No name in source — check if title contains the name
            src_parsed = parse_name(title or "")

        matched_features: List[str] = []
        conflicting_features: List[str] = []
        reason_codes: List[str] = []

        # ─── NAME COMPARISON ─────────────────────────────────────────────
        cognome_match = self._compare_cognome(src_parsed.cognome)
        nome_match = self._compare_nome(src_parsed.nome)

        # If no cognome match at all → rejected
        if not cognome_match.get("exact") and not cognome_match.get("word_boundary"):
            reason_codes.append("NO_COGNOME_MATCH")
            return self._make_result(
                "rejected", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.0,
            )

        # Surname-only check: reject common words that happen to match
        if self._target_cognome in _COMMON_WORD_SURNAMES:
            if not cognome_match.get("exact") and not cognome_match.get("word_boundary"):
                reason_codes.append("COMMON_WORD_SURNAME")
                return self._make_result(
                    "rejected", source, source_kind, source_table, source_id,
                    url, title, query_used, provider,
                    matched_features, conflicting_features, reason_codes, 0.0,
                )

        if cognome_match.get("exact"):
            matched_features.append("cognome_exact")
        elif cognome_match.get("word_boundary"):
            matched_features.append("cognome_word_boundary")

        # Full name match check
        full_name_match = cognome_match.get("exact", False) and nome_match.get("exact", False)
        if full_name_match:
            matched_features.append("full_name_exact")
        elif cognome_match.get("exact") and nome_match.get("initial"):
            matched_features.append("nome_initial_match")
        elif cognome_match.get("exact") and not nome_match.get("exact"):
            reason_codes.append("SURNAME_ONLY_MATCH")
            # Surname-only is at most ambiguous
            return self._evaluate_identifiers(
                source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes,
                max_status="ambiguous",
            )

        # ─── IDENTIFIER COMPARISON ───────────────────────────────────────
        return self._evaluate_identifiers(
            source, source_kind, source_table, source_id,
            url, title, query_used, provider,
            matched_features, conflicting_features, reason_codes,
            max_status="confirmed",
        )

    def _evaluate_identifiers(
        self,
        source: Dict[str, Any],
        source_kind: str,
        source_table: str,
        source_id: str,
        url: str,
        title: str,
        query_used: str,
        provider: str,
        matched_features: List[str],
        conflicting_features: List[str],
        reason_codes: List[str],
        max_status: str,
    ) -> PersonMatchResult:
        """Evaluate identifiers to determine match status."""

        # Check strong identifiers
        strong_matches = 0
        strong_conflicts = 0
        for field in STRONG_IDENTIFIERS:
            target_val = str(self._target_record.get(field, "")).strip()
            src_val = str(source.get(field, "")).strip()
            if target_val and src_val:
                if self._compare_values(target_val, src_val):
                    matched_features.append(field)
                    strong_matches += 1
                else:
                    conflicting_features.append(field)
                    reason_codes.append(f"CONFLICT_{field}")
                    strong_conflicts += 1

        # Strong conflict → rejected
        if strong_conflicts > 0:
            return self._make_result(
                "rejected", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.0,
            )

        # Strong identifier match → confirmed (if max_status allows)
        if strong_matches > 0 and max_status == "confirmed":
            reason_codes.append("STRONG_IDENTIFIER_MATCH")
            return self._make_result(
                "confirmed", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.95,
            )

        # Check medium identifiers
        medium_matches = 0
        medium_conflicts = 0
        for field in MEDIUM_IDENTIFIERS:
            target_val = str(self._target_record.get(field, "")).strip()
            src_val = str(source.get(field, "")).strip()
            if target_val and src_val:
                if self._compare_values(target_val, src_val):
                    if field not in matched_features:
                        matched_features.append(field)
                    medium_matches += 1
                elif field in CONFLICT_FIELDS:
                    conflicting_features.append(field)
                    reason_codes.append(f"CONFLICT_{field}")
                    medium_conflicts += 1

        # Medium conflict on critical fields → rejected
        if medium_conflicts > 0:
            return self._make_result(
                "rejected", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.0,
            )

        # Full name + 2+ medium identifiers → confirmed
        if "full_name_exact" in matched_features and medium_matches >= 2 and max_status == "confirmed":
            reason_codes.append("FULL_NAME_PLUS_TWO_IDENTIFIERS")
            return self._make_result(
                "confirmed", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.9,
            )

        # Full name + 1 medium identifier → probable
        if "full_name_exact" in matched_features and medium_matches >= 1:
            reason_codes.append("FULL_NAME_PLUS_ONE_IDENTIFIER")
            return self._make_result(
                "probable", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.7,
            )

        # Full name only, no identifiers → ambiguous
        if "full_name_exact" in matched_features:
            reason_codes.append("FULL_NAME_NO_IDENTIFIERS")
            return self._make_result(
                min("ambiguous", max_status) if max_status != "confirmed" else "ambiguous",
                source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.4,
            )

        # Nome initial match + identifiers
        if "nome_initial_match" in matched_features and medium_matches >= 2:
            reason_codes.append("INITIAL_PLUS_TWO_IDENTIFIERS")
            return self._make_result(
                "probable", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.65,
            )

        if "nome_initial_match" in matched_features and medium_matches >= 1:
            reason_codes.append("INITIAL_PLUS_ONE_IDENTIFIER")
            return self._make_result(
                "probable", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.55,
            )

        # Surname-only with no identifiers
        if "full_name_exact" not in matched_features:
            reason_codes.append("SURNAME_ONLY_NO_IDENTIFIERS")
            return self._make_result(
                "rejected", source, source_kind, source_table, source_id,
                url, title, query_used, provider,
                matched_features, conflicting_features, reason_codes, 0.0,
            )

        # Fallback
        reason_codes.append("INSUFFICIENT_EVIDENCE")
        return self._make_result(
            "ambiguous", source, source_kind, source_table, source_id,
            url, title, query_used, provider,
            matched_features, conflicting_features, reason_codes, 0.3,
        )

    def _compare_cognome(self, src_cognome: str) -> Dict[str, bool]:
        """Compare surname with word-boundary matching."""
        if not src_cognome:
            return {"exact": False, "word_boundary": False}

        target = self._target_normalized_cognome
        source = normalize_name(src_cognome)

        if not target or not source:
            return {"exact": False, "word_boundary": False}

        # Exact match (normalized)
        if target == source:
            return {"exact": True, "word_boundary": True}

        # Word-boundary match (handles compound surnames)
        if word_boundary_match(source, target) or word_boundary_match(target, source):
            return {"exact": False, "word_boundary": True}

        return {"exact": False, "word_boundary": False}

    def _compare_nome(self, src_nome: str) -> Dict[str, bool]:
        """Compare given name, handling initials and multi-part names."""
        if not src_nome:
            return {"exact": False, "initial": False}

        target = self._target_normalized_nome
        source = normalize_name(src_nome)

        if not target or not source:
            return {"exact": False, "initial": False}

        # Exact match
        if target == source:
            return {"exact": True, "initial": False}

        # Check if source is an initial of target or vice versa
        target_tokens = tokenize(target)
        source_tokens = tokenize(source)

        # "Luigi A" vs "Luigi Antonio" — initial match
        if len(target_tokens) == len(source_tokens):
            all_match = True
            has_initial = False
            for tt, st in zip(target_tokens, source_tokens):
                if tt == st:
                    continue
                elif len(st) == 1 and tt[0] == st[0]:
                    has_initial = True
                    continue
                elif len(tt) == 1 and st[0] == tt[0]:
                    has_initial = True
                    continue
                else:
                    all_match = False
                    break
            if all_match and has_initial:
                return {"exact": False, "initial": True}

        # Check if one is a single initial matching the first token
        if len(source_tokens) == 1 and len(source_tokens[0]) == 1:
            if target_tokens and target_tokens[0][0] == source_tokens[0][0]:
                return {"exact": False, "initial": True}

        # Word-boundary match for multi-part names
        if word_boundary_match(source, target) or word_boundary_match(target, source):
            return {"exact": False, "initial": False}

        return {"exact": False, "initial": False}

    def _compare_values(self, val1: str, val2: str) -> bool:
        """Compare two values with normalization."""
        n1 = normalize_name(val1)
        n2 = normalize_name(val2)
        if not n1 or not n2:
            return False
        # Exact match
        if n1 == n2:
            return True
        # Year match (extract 4-digit year)
        years1 = re.findall(r"\b(19\d{2})\b", val1)
        years2 = re.findall(r"\b(19\d{2})\b", val2)
        if years1 and years2 and years1[0] == years2[0]:
            return True
        # Partial date match (same year-month)
        if len(n1) >= 7 and len(n2) >= 7 and n1[:7] == n2[:7]:
            return True
        return False

    def _make_result(
        self,
        status: str,
        source: Dict[str, Any],
        source_kind: str,
        source_table: str,
        source_id: str,
        url: str,
        title: str,
        query_used: str,
        provider: str,
        matched_features: List[str],
        conflicting_features: List[str],
        reason_codes: List[str],
        confidence: float,
    ) -> PersonMatchResult:
        """Build a PersonMatchResult."""
        result = PersonMatchResult(
            status=status,
            person_table="internati",
            person_id=int(self._target_id) if self._target_id.isdigit() else 0,
            source_table=source_table,
            source_id=int(source_id) if str(source_id).isdigit() else 0,
            source_kind=source_kind,
            normalized_name=f"{self._target_cognome} {self._target_nome}".strip(),
            matched_features=matched_features,
            conflicting_features=conflicting_features,
            reason_codes=reason_codes,
            confidence=confidence,
            resolver_version=RESOLVER_VERSION,
            url=url,
            title=title,
            query_used=query_used,
            provider=provider,
        )
        self._matches.append(result)
        return result

    def get_all_matches(self) -> List[PersonMatchResult]:
        return list(self._matches)

    def get_confirmed(self) -> List[PersonMatchResult]:
        return [m for m in self._matches if m.status == "confirmed"]

    def get_probable(self) -> List[PersonMatchResult]:
        return [m for m in self._matches if m.status == "probable"]

    def get_ambiguous(self) -> List[PersonMatchResult]:
        return [m for m in self._matches if m.status == "ambiguous"]

    def get_rejected(self) -> List[PersonMatchResult]:
        return [m for m in self._matches if m.status == "rejected"]

    def get_counts(self) -> Dict[str, int]:
        return {
            "web_candidates_seen": len(self._matches),
            "person_sources_confirmed": len(self.get_confirmed()),
            "person_sources_probable": len(self.get_probable()),
            "person_sources_ambiguous": len(self.get_ambiguous()),
            "person_candidates_rejected": len(self.get_rejected()),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# QUERY BUILDER
# ═══════════════════════════════════════════════════════════════════════════════


def build_person_queries(cognome: str, nome: str, record: Dict[str, Any] = None) -> List[Dict[str, str]]:
    """Build progressive query variants for PERSON search.

    Returns list of {query, purpose, priority} dicts.
    """
    record = record or {}
    queries = []
    full_name = f"{cognome} {nome}".strip()
    reversed_name = f"{nome} {cognome}".strip()
    comma_name = f"{cognome}, {nome}".strip()

    # Priority 1: Full name exact
    queries.append({"query": full_name, "purpose": "nominative_exact", "priority": 1})
    queries.append({"query": reversed_name, "purpose": "nominative_reversed", "priority": 1})
    queries.append({"query": comma_name, "purpose": "nominative_comma", "priority": 1})

    # Priority 2: Name + birth year
    birth_year = ""
    for f in ["anno_nascita", "data_nascita"]:
        val = str(record.get(f, "")).strip()
        if val:
            years = re.findall(r"\b(19\d{2})\b", val)
            if years:
                birth_year = years[0]
                break
    if birth_year:
        queries.append({
            "query": f"{full_name} {birth_year}",
            "purpose": "name_plus_birth_year",
            "priority": 2,
        })

    # Priority 2: Name + birth place
    birth_place = str(record.get("luogo_nascita", "")).strip()
    if birth_place:
        queries.append({
            "query": f"{full_name} {birth_place}",
            "purpose": "name_plus_birth_place",
            "priority": 2,
        })

    # Priority 3: Name + matricola
    matricola = str(record.get("matricola", "")).strip()
    if matricola:
        queries.append({
            "query": f"{full_name} {matricola}",
            "purpose": "name_plus_matricola",
            "priority": 3,
        })

    # Priority 3: Name + reparto
    reparto = str(record.get("reparto", "")).strip()
    if reparto:
        queries.append({
            "query": f"{full_name} {reparto}",
            "purpose": "name_plus_reparto",
            "priority": 3,
        })

    # Priority 3: Name + luogo_internamento
    luogo_int = str(record.get("luogo_internamento", "")).strip()
    if luogo_int:
        queries.append({
            "query": f"{full_name} {luogo_int}",
            "purpose": "name_plus_camp",
            "priority": 3,
        })

    # Priority 4: Name + residenza
    residenza = str(record.get("residenza", "")).strip()
    if residenza:
        queries.append({
            "query": f"{full_name} {residenza}",
            "purpose": "name_plus_residence",
            "priority": 4,
        })

    return queries
