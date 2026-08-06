"""V7.3-Fase6: Military Rank & Unit Ontology.

Distinguishes three semantic categories:
  - rank_fact: the person's actual held rank (PERSON_EVIDENCE)
  - rank_context: rank mentioned in event/unit context (CONTEXT_EVIDENCE)
  - personal_duty: the person's specific duty/assignment (PERSON_EVIDENCE)

Key invariants:
  1. A rank from a person record is rank_fact (PERSON_EVIDENCE)
  2. A rank from an event description is rank_context (CONTEXT_EVIDENCE)
  3. A unit from a person record is personal_duty (PERSON_EVIDENCE)
  4. A unit from an event description is unit_context (CONTEXT_EVIDENCE)
  5. rank_fact and rank_context can coexist without conflict
  6. Rank normalization preserves the original Italian form
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ─── Rank taxonomy ───────────────────────────────────────────────────────────

# Italian military ranks by category (WWI & WWII)
# Source: Regio Esercito rank structure, 1861-1946

RANK_CATEGORIES = {
    "ufficiali_generali": [
        "maresciallo d'italia", "generale d'armata", "generale di corpo d'armata",
        "generale di divisione", "generale di brigata", "ammiraglio",
        "vice ammiraglio", "contrammiraglio",
    ],
    "ufficiali_superiori": [
        "colonnello", "tenente colonnello", "maggiore",
        "capitano di vascello", "capitano di fregata", "capitano di corvetta",
    ],
    "ufficiali_inferiori": [
        "capitano", "tenente", "sottotenente", "guardiamarina",
        "primo tenente", "tenente di vascello",
    ],
    "sottufficiali": [
        "maresciallo", "sergente maggiore", "sergente",
        "capo di 3a classe", "capo di 2a classe", "capo di 1a classe",
        "secondo capo", "sergente capo",
    ],
    "truppa": [
        "caporale maggiore", "caporale", "soldato", "fante",
        "artigliere", "bersagliere", "alpino", "granatiere",
        "fuciliere", "marinaio", "aviere",
    ],
    "ausiliarie": [
        "ausiliaria", "infermiera volontaria", "crocerossina",
        "salesiana",
    ],
}

# Flatten for quick lookup
_ALL_RANKS: Dict[str, str] = {}
for category, ranks in RANK_CATEGORIES.items():
    for rank in ranks:
        _ALL_RANKS[rank.lower()] = category
        # Also without apostrophes
        _ALL_RANKS[rank.lower().replace("'", " ")] = category

# Abbreviation map
RANK_ABBREVIATIONS: Dict[str, str] = {
    "gen.": "generale",
    "col.": "colonnello",
    "ten. col.": "tenente colonnello",
    "magg.": "maggiore",
    "cap.": "capitano",
    "ten.": "tenente",
    "sottoten.": "sottotenente",
    "sott. ten.": "sottotenente",
    "maresc.": "maresciallo",
    "serg. magg.": "sergente maggiore",
    "serg.": "sergente",
    "cap. magg.": "caporale maggiore",
    "cap.": "caporale",
    "sold.": "soldato",
    "fante": "fante",
    "artigl.": "artigliere",
    "bers.": "bersagliere",
    "alp.": "alpino",
    "fucil.": "fuciliere",
    "mar.": "marinaio",
    "av.": "aviere",
    "amm.": "ammiraglio",
    "v. amm.": "vice ammiraglio",
    "c. amm.": "contrammiraglio",
}

# Reverse: canonical → abbreviations
_CANONICAL_TO_ABBR: Dict[str, List[str]] = {}
for abbr, canon in RANK_ABBREVIATIONS.items():
    if canon not in _CANONICAL_TO_ABBR:
        _CANONICAL_TO_ABBR[canon] = []
    _CANONICAL_TO_ABBR[canon].append(abbr)


# ─── Unit taxonomy ───────────────────────────────────────────────────────────

UNIT_TYPES = {
    "army": ["armata", "army"],
    "corps": ["corpo d'armata", "corpo d armata", "corps"],
    "division": ["divisione", "division"],
    "brigade": ["brigata", "brigade"],
    "regiment": ["reggimento", "regimento", "regiment", "regt", "rgt"],
    "battalion": ["battaglione", "battaglione ", "battalion", "batt", "btn", "bn"],
    "company": ["compagnia", "company", "coy", "cp"],
    "battery": ["batteria", "battery", "bty"],
    "squadron": ["squadrone", "squadron", "sqdn"],
    "platoon": ["plotone", "platoon", "plt"],
    "squad": ["squadra", "squad", "sq"],
    "group": ["gruppo", "group", "grp"],
    "command": ["comando", "command", "cmd"],
    "work_command": ["arbeitskommando", "arbeitskommando", "ak"],
}

# Reverse lookup: keyword → unit_type
_UNIT_KEYWORD_TO_TYPE: Dict[str, str] = {}
for unit_type, keywords in UNIT_TYPES.items():
    for kw in keywords:
        _UNIT_KEYWORD_TO_TYPE[kw.lower().strip()] = unit_type


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class RankInfo:
    """Parsed rank information."""
    original: str
    canonical: str = ""
    category: str = ""  # ufficiali_generali, ufficiali_superiori, etc.
    is_abbreviation: bool = False
    evidence_scope: str = "PERSON_EVIDENCE"  # rank_fact vs rank_context
    confidence: float = 0.0


@dataclass
class UnitInfo:
    """Parsed military unit information."""
    original: str
    unit_type: str = ""  # regiment, battalion, company, etc.
    unit_number: str = ""  # e.g., "5" from "5 Reggimento Artiglieria"
    unit_branch: str = ""  # Artiglieria, Fanteria, Alpini, etc.
    normalized: str = ""
    evidence_scope: str = "PERSON_EVIDENCE"  # personal_duty vs unit_context
    confidence: float = 0.0


# ─── Parsers ─────────────────────────────────────────────────────────────────

def parse_rank(raw: str, source_context: str = "person_record") -> RankInfo:
    """Parse a rank string into structured RankInfo.

    Args:
        raw: the raw rank string from a DB field or text
        source_context: "person_record" | "event_description" | "unknown"
            - person_record → rank_fact (PERSON_EVIDENCE)
            - event_description → rank_context (CONTEXT_EVIDENCE)

    Returns:
        RankInfo with canonical form, category, and evidence_scope
    """
    if not raw or not raw.strip():
        return RankInfo(original=raw or "")

    s = raw.strip()
    s_lower = s.lower()

    # Determine evidence scope based on source context
    if source_context == "event_description":
        evidence_scope = "CONTEXT_EVIDENCE"
    else:
        evidence_scope = "PERSON_EVIDENCE"

    # Try exact match
    if s_lower in _ALL_RANKS:
        return RankInfo(
            original=s,
            canonical=s_lower,
            category=_ALL_RANKS[s_lower],
            is_abbreviation=False,
            evidence_scope=evidence_scope,
            confidence=0.95,
        )

    # Try abbreviation expansion
    if s_lower in RANK_ABBREVIATIONS:
        canonical = RANK_ABBREVIATIONS[s_lower]
        category = _ALL_RANKS.get(canonical, "")
        return RankInfo(
            original=s,
            canonical=canonical,
            category=category,
            is_abbreviation=True,
            evidence_scope=evidence_scope,
            confidence=0.90,
        )

    # Try fuzzy: check if any known rank is contained in the string
    for rank, category in _ALL_RANKS.items():
        if rank in s_lower:
            return RankInfo(
                original=s,
                canonical=rank,
                category=category,
                is_abbreviation=False,
                evidence_scope=evidence_scope,
                confidence=0.75,
            )

    # Try abbreviation fuzzy
    for abbr, canonical in RANK_ABBREVIATIONS.items():
        if abbr in s_lower:
            category = _ALL_RANKS.get(canonical, "")
            return RankInfo(
                original=s,
                canonical=canonical,
                category=category,
                is_abbreviation=True,
                evidence_scope=evidence_scope,
                confidence=0.70,
            )

    # Unknown rank — return as-is
    return RankInfo(
        original=s,
        canonical=s_lower,
        category="unknown",
        evidence_scope=evidence_scope,
        confidence=0.30,
    )


def parse_unit(raw: str, source_context: str = "person_record") -> UnitInfo:
    """Parse a military unit string into structured UnitInfo.

    Args:
        raw: the raw unit string from a DB field or text
        source_context: "person_record" | "event_description" | "unknown"
            - person_record → personal_duty (PERSON_EVIDENCE)
            - event_description → unit_context (CONTEXT_EVIDENCE)

    Returns:
        UnitInfo with unit_type, unit_number, unit_branch, and evidence_scope
    """
    if not raw or not raw.strip():
        return UnitInfo(original=raw or "")

    s = raw.strip()
    s_lower = s.lower()

    # Determine evidence scope
    if source_context == "event_description":
        evidence_scope = "CONTEXT_EVIDENCE"
    else:
        evidence_scope = "PERSON_EVIDENCE"

    # Extract unit number (leading or embedded number)
    number_match = re.search(r"(\d+)", s)
    unit_number = number_match.group(1) if number_match else ""

    # Determine unit type
    unit_type = "unknown"
    for keyword, utype in _UNIT_KEYWORD_TO_TYPE.items():
        if keyword in s_lower:
            unit_type = utype
            break

    # Determine branch (common Italian military branches)
    branch_keywords = {
        "fanteria": ["fanteria", "fante", "infantry"],
        "artiglieria": ["artiglieria", "artigliere", "artillery"],
        "cavalleria": ["cavalleria", "cavaliere", "cavalry"],
        "alpini": ["alpini", "alpino"],
        "bersaglieri": ["bersaglieri", "bersagliere"],
        "granatieri": ["granatieri", "granatiere"],
        "genio": ["genio", "geniere", "engineer"],
        "trasmissioni": ["trasmissioni", "segnalatori", "signal"],
        "sanita": ["sanita", "sanitario", "medical"],
        "intendenza": ["intendenza", "logistics"],
        "carabinieri": ["carabinieri", "carabiniere"],
        "aviazione": ["aviazione", "aviere", "aeronautica", "air"],
        "marina": ["marina", "marinaio", "navy", "regia marina"],
        "fucilieri": ["fucilieri", "fuciliere"],
        "lagunari": ["lagunari"],
        "paracadutisti": ["paracadutisti", "paracadutista", "paratrooper"],
    }
    unit_branch = "unknown"
    for branch, keywords in branch_keywords.items():
        for kw in keywords:
            if kw in s_lower:
                unit_branch = branch
                break
        if unit_branch != "unknown":
            break

    # Build normalized form
    parts = []
    if unit_number:
        parts.append(unit_number)
    if unit_type != "unknown":
        parts.append(unit_type)
    if unit_branch != "unknown":
        parts.append(unit_branch)
    normalized = " ".join(parts) if parts else s_lower

    confidence = 0.90
    if unit_type == "unknown":
        confidence = 0.50
    if unit_branch == "unknown":
        confidence -= 0.10

    return UnitInfo(
        original=s,
        unit_type=unit_type,
        unit_number=unit_number,
        unit_branch=unit_branch,
        normalized=normalized,
        evidence_scope=evidence_scope,
        confidence=confidence,
    )


def classify_rank_predicate(predicate: str, source_context: str = "person_record") -> str:
    """Classify a rank-related claim predicate into the ontology.

    Returns one of:
      - "rank_fact" — person's actual rank (PERSON_EVIDENCE)
      - "rank_context" — rank mentioned in event context (CONTEXT_EVIDENCE)
      - "personal_duty" — person's specific duty/assignment (PERSON_EVIDENCE)
      - "unit_context" — unit mentioned in event context (CONTEXT_EVIDENCE)
    """
    if predicate in ("rank", "grado"):
        if source_context == "event_description":
            return "rank_context"
        return "rank_fact"

    if predicate in ("military_unit", "reparto", "regiment", "assignment"):
        if source_context == "event_description":
            return "unit_context"
        return "personal_duty"

    if predicate in ("military_branch", "arma"):
        if source_context == "event_description":
            return "unit_context"
        return "personal_duty"

    if predicate in ("work_command", "arbeitskommando"):
        return "personal_duty"

    return "rank_fact"  # default


# ─── Integration helpers ─────────────────────────────────────────────────────

def enrich_claim_with_ontology(
    predicate: str,
    raw_value: str,
    source_context: str = "person_record",
) -> Dict[str, str]:
    """Enrich a claim dict with ontology classification.

    Returns a dict with additional fields:
      - ontology_class: rank_fact | rank_context | personal_duty | unit_context
      - rank_canonical: canonical rank form (if applicable)
      - rank_category: rank category (if applicable)
      - unit_type: regiment, battalion, etc. (if applicable)
      - unit_number: extracted number (if applicable)
      - unit_branch: artiglieria, fanteria, etc. (if applicable)
    """
    result: Dict[str, str] = {}

    ontology_class = classify_rank_predicate(predicate, source_context)
    result["ontology_class"] = ontology_class

    if predicate in ("rank", "grado"):
        rank_info = parse_rank(raw_value, source_context)
        result["rank_canonical"] = rank_info.canonical
        result["rank_category"] = rank_info.category
        result["evidence_scope"] = rank_info.evidence_scope

    if predicate in ("military_unit", "reparto", "regiment", "assignment",
                      "military_branch", "arma", "work_command", "arbeitskommando"):
        unit_info = parse_unit(raw_value, source_context)
        result["unit_type"] = unit_info.unit_type
        result["unit_number"] = unit_info.unit_number
        result["unit_branch"] = unit_info.unit_branch
        result["unit_normalized"] = unit_info.normalized
        result["evidence_scope"] = unit_info.evidence_scope

    return result
