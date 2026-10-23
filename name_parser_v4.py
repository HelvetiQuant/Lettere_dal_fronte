"""Name Parser V4 — correct parsing of COGNOME NOME DI PADRE pattern.

Fixes the V3 bug where "PAPINI PUBLIO DI GIOVANNI" was parsed as:
  - surname: PAPINI
  - given: PUBLIO
  - paternity: PAPINI PUBLIO DI GIOVANNI (full name in paternity field)

The parser now correctly splits:
  - surname: PAPINI
  - given: PUBLIO
  - paternity: GIOVANNI

Also preserves raw_value, normalized_value, parser_version, field_provenance.
An uncertain parse creates needs_field_review, not a new homonym.
"""
from __future__ import annotations

import re
import unicodedata
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

PARSER_VERSION = "v4.1"


@dataclass
class ParsedName:
    """Result of parsing a display name into components."""
    surname: str = ""
    given_names: str = ""
    father_name: str = ""
    raw_value: str = ""
    normalized_value: str = ""
    parser_version: str = PARSER_VERSION
    field_provenance: str = ""  # where the raw value came from
    needs_field_review: bool = False
    parse_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "surname": self.surname,
            "given_names": self.given_names,
            "father_name": self.father_name,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "parser_version": self.parser_version,
            "field_provenance": self.field_provenance,
            "needs_field_review": self.needs_field_review,
            "parse_notes": self.parse_notes,
        }


def _normalize(s: str) -> str:
    """Normalize string: NFKD, remove combining chars, lowercase, strip."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip()


# Italian particles that indicate paternity
_PATERNITY_PARTICLES = {"DI", "DE", "DELLA", "DEL", "DELLO", "DELLA", "DA", "D"}

# Common Italian given names (for disambiguation)
_COMMON_GIVEN_NAMES = {
    "GIUSEPPE", "ANTONIO", "GIOVANNI", "FRANCESCO", "LUIGI", "PIETRO",
    "CARLO", "MARIO", "ANGELO", "BRUNO", "ENRICO", "FEDERICO",
    "PUBLIO", "NICOLA", "GAETANO", "SALVATORE", "GIUSEPPINA",
    "MARIA", "ANNA", "ROSA", "TERESA", "LUCIA",
}


def parse_display_name(raw_name: str, field_provenance: str = "") -> ParsedName:
    """Parse a display name in the format COGNOME NOME DI PADRE.

    Handles:
    - "LARI GIUSEPPE" → surname=LARI, given=GIUSEPPE
    - "LARI GIUSEPPE DI EMANUELE" → surname=LARI, given=GIUSEPPE, father=EMANUELE
    - "PAPINI PUBLIO DI GIOVANNI" → surname=PAPINI, given=PUBLIO, father=GIOVANNI
    - "FANTUZ ANTONIO" → surname=FANTUZ, given=ANTONIO
    - "RUSSO GAETANO" → surname=RUSSO, given=GAETANO

    Does NOT create a homonym when paternity is embedded in the display name.
    """
    result = ParsedName(
        raw_value=raw_name,
        normalized_value=_normalize(raw_name).upper(),
        field_provenance=field_provenance,
    )

    if not raw_name or not raw_name.strip():
        result.parse_notes.append("EMPTY_INPUT")
        return result

    # Work with normalized uppercase
    name = raw_name.strip().upper()
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name)

    # Check for paternity particle pattern: "COGNOME NOME DI PADRE"
    # The particle can be DI, DE, DEL, DELLA, etc.
    paternity_match = re.match(
        r'^(\S+)\s+(.+?)\s+(DI|DE|DELLA|DEL|DELLO|DA|D)\s+(.+)$',
        name
    )

    if paternity_match:
        # Pattern: SURNAME GIVEN_NAMES PARTICLE FATHER_NAME
        surname = paternity_match.group(1)
        given_names = paternity_match.group(2).strip()
        father_name = paternity_match.group(4).strip()

        # Validate: given_names should not contain the surname
        if surname in given_names:
            result.needs_field_review = True
            result.parse_notes.append(f"SURNAME_IN_GIVEN_NAMES: {surname} found in {given_names}")
            # Try to extract just the first given name
            given_parts = given_names.split()
            given_names = given_parts[0] if given_parts else given_names

        # Validate: father_name should not contain the full name
        if father_name == name or len(father_name) > len(surname) + len(given_names) + 5:
            result.needs_field_review = True
            result.parse_notes.append(f"FATHER_NAME_TOO_LONG: {father_name}")
            # Try to extract just the father's given name
            father_parts = father_name.split()
            if len(father_parts) == 1:
                father_name = father_parts[0]
            else:
                # Take the last word as father's name
                father_name = father_parts[-1]

        result.surname = surname
        result.given_names = given_names
        result.father_name = father_name
        result.parse_notes.append("PARSED_WITH_PATERNITY")
        return result

    # No paternity particle — just SURNAME GIVEN_NAMES
    parts = name.split()
    if len(parts) == 1:
        # Only one word — could be just surname or just given name
        result.surname = parts[0]
        result.parse_notes.append("SINGLE_WORD_NAME")
        result.needs_field_review = True
        return result

    if len(parts) == 2:
        # SURNAME GIVEN_NAME
        result.surname = parts[0]
        result.given_names = parts[1]
        result.parse_notes.append("PARSED_SURNAME_GIVEN")
        return result

    # More than 2 words without paternity particle
    # Could be: SURNAME GIVEN_NAME1 GIVEN_NAME2
    # Or: COMPOUND_SURNAME GIVEN_NAME
    # Heuristic: if first word is a common given name, it's probably GIVEN SURNAME
    if parts[0] in _COMMON_GIVEN_NAMES and parts[-1] not in _COMMON_GIVEN_NAMES:
        # Probably GIVEN_NAMES SURNAME (reversed order)
        result.given_names = parts[0]
        result.surname = " ".join(parts[1:])
        result.parse_notes.append("PARSED_GIVEN_SURNAME_REVERSED")
        result.needs_field_review = True
        return result

    # Default: first word = surname, rest = given names
    result.surname = parts[0]
    result.given_names = " ".join(parts[1:])
    result.parse_notes.append("PARSED_SURNAME_MULTI_GIVEN")
    return result


def parse_candidate_fields(
    display_name: str,
    raw_paternity: str = "",
    raw_birth_year: str = "",
    raw_birth_place: str = "",
    field_provenance: str = "",
) -> Dict:
    """Parse all candidate fields with provenance tracking.

    This replaces the V3 approach where paternity could contain the full
    display_name, creating a false homonym. The parser now:
    1. Parses display_name to extract embedded paternity
    2. Uses explicit paternity field if available and different
    3. Preserves raw values for audit
    4. Marks uncertain parses with needs_field_review
    """
    parsed = parse_display_name(display_name, field_provenance)

    # If paternity was extracted from display_name, use it
    father_name = parsed.father_name

    # If explicit paternity field is provided and different, prefer it
    if raw_paternity and raw_paternity.strip():
        explicit_father = _normalize(raw_paternity).upper()
        # Check if explicit paternity is not the full display name
        if explicit_father != parsed.normalized_value and explicit_father != display_name.upper():
            father_name = explicit_father
        else:
            # Explicit paternity contains full name — parser error
            parsed.needs_field_review = True
            parsed.parse_notes.append(
                f"EXPLICIT_PATERNITY_CONTAINS_FULL_NAME: {raw_paternity}"
            )

    return {
        "surname": parsed.surname,
        "given_names": parsed.given_names,
        "father_name": father_name,
        "raw_display_name": display_name,
        "raw_paternity": raw_paternity,
        "normalized_display_name": parsed.normalized_value,
        "parser_version": PARSER_VERSION,
        "field_provenance": field_provenance,
        "needs_field_review": parsed.needs_field_review,
        "parse_notes": parsed.parse_notes,
    }
