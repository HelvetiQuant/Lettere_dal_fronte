"""V7.2 Query Family Builder — constructs multiple query variants from a single target.

Inspired by the GPT manual pipeline's step 4: instead of a single query,
the system builds families of queries to maximize discovery coverage:

  - Nominative: "Luigi Sonavetti", "SONAVETTI Luigi"
  - With context: "Luigi Sonavetti" Kassel, "Angelo Franchini" Trieste
  - Event-based: eccidio Kassel Wilhelmshöhe 78 italiani
  - OCR variants: Cassel/Kassel, Bonnis/Bannia, Falchemberg/Falkenberg
  - Geographic inverse: decompose "Stencle-Bai-Figan-Licvsia" → place candidates

Each query variant is tagged with its family and purpose, so the DISCOVER
stage can execute them in parallel and the EXTRACT stage can classify
results by query type.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class QueryVariant:
    """A single query variant in a query family."""
    query_text: str
    family: str  # NOMINATIVE|NOMINATIVE_WITH_CONTEXT|EVENT_BASED|OCR_VARIANT|GEOGRAPHIC_INVERSE
    purpose: str  # description of what this query tries to find
    priority: int = 10  # lower = higher priority
    source_field: str = ""  # which record field inspired this variant


@dataclass
class QueryFamily:
    """A family of related queries for a single research target."""
    target_name: str
    variants: List[QueryVariant] = field(default_factory=list)

    def get_by_family(self, family: str) -> List[QueryVariant]:
        return [v for v in self.variants if v.family == family]

    def sorted_variants(self) -> List[QueryVariant]:
        return sorted(self.variants, key=lambda v: v.priority)


# ─── OCR substitution patterns ───────────────────────────────────────────────

_OCR_SUBSTITUTIONS = {
    # German/Italian place name variants
    "cassel": "kassel",
    "kassel": "cassel",
    "falchemberg": "falkenberg",
    "fualchemberg": "falkenberg",
    "bonnis": "bannia",
    "bannia": "bonnis",
    "licvsia": "leipzig",
    "lipsia": "leipzig",
    "pigan": "pegau",
    "bai": "bei",
    # Common OCR consonant confusions
    "nn": "rn",
    "rn": "nn",
    "ii": "u",
    "cl": "d",
    "vs": "ws",
}


def build_query_family(
    target_name: str,
    record: Optional[Dict[str, Any]] = None,
    intent: str = "PERSON_LOOKUP",
) -> QueryFamily:
    """Build a family of query variants from a target name and optional DB record.

    Args:
        target_name: The primary search target (person name or event name)
        record: Optional DB record dict for context extraction
        intent: PERSON_LOOKUP or EVENT_LOOKUP

    Returns:
        QueryFamily with all variants sorted by priority
    """
    family = QueryFamily(target_name=target_name)

    # ── NOMINATIVE: direct name queries ──
    family.variants.append(QueryVariant(
        query_text=target_name,
        family="NOMINATIVE",
        purpose="Direct name search",
        priority=1,
    ))

    # Reversed name order (COGNOME NOME vs NOME COGNOME)
    parts = target_name.split(None, 1)
    if len(parts) == 2:
        reversed_name = f"{parts[1]} {parts[0]}"
        family.variants.append(QueryVariant(
            query_text=reversed_name,
            family="NOMINATIVE",
            purpose="Reversed name order search",
            priority=2,
        ))

    if record and intent == "PERSON_LOOKUP":
        cognome = str(record.get("cognome", "")).strip()
        nome = str(record.get("nome", "")).strip()

        # ── NOMINATIVE_WITH_CONTEXT: name + place/date context ──
        context_fields = [
            ("luogo_nascita", "birth place"),
            ("residenza", "residence"),
            ("luogo_internamento", "internment place"),
            ("luogo_cattura", "capture place"),
            ("luogo_morte", "death place"),
        ]
        for field_name, label in context_fields:
            val = str(record.get(field_name, "")).strip()
            if val and val != "-" and len(val) > 2:
                # Skip if the place itself looks OCR-deformed (will be handled separately)
                family.variants.append(QueryVariant(
                    query_text=f'"{target_name}" {val}',
                    family="NOMINATIVE_WITH_CONTEXT",
                    purpose=f"Name + {label}",
                    priority=5,
                    source_field=field_name,
                ))

        # ── EVENT_BASED: search for events related to the person's fate ──
        sorte = str(record.get("sorte", "")).strip().lower()
        if sorte:
            event_queries = _build_event_queries(sorte, record)
            for eq in event_queries:
                family.variants.append(QueryVariant(
                    query_text=eq,
                    family="EVENT_BASED",
                    purpose="Event-based search to explain person's fate",
                    priority=8,
                    source_field="sorte",
                ))

        # ── OCR_VARIANT: try OCR substitutions on place names ──
        for field_name, _ in context_fields:
            val = str(record.get(field_name, "")).strip()
            if val and val != "-":
                ocr_variants = _generate_ocr_variants(val)
                for ocr_v in ocr_variants:
                    family.variants.append(QueryVariant(
                        query_text=f'"{target_name}" {ocr_v}',
                        family="OCR_VARIANT",
                        purpose=f"OCR variant of {field_name}: {val} → {ocr_v}",
                        priority=10,
                        source_field=field_name,
                    ))

        # ── GEOGRAPHIC_INVERSE: decompose hyphenated place strings ──
        for field_name in ["luogo_internamento", "luogo_morte", "luogo_cattura"]:
            val = str(record.get(field_name, "")).strip()
            if val and "-" in val and val.count("-") >= 2:
                geo_candidates = _decompose_geographic_string(val)
                for candidate in geo_candidates:
                    family.variants.append(QueryVariant(
                        query_text=candidate,
                        family="GEOGRAPHIC_INVERSE",
                        purpose=f"Geographic decomposition of {field_name}: {val} → {candidate}",
                        priority=12,
                        source_field=field_name,
                    ))

    elif intent == "EVENT_LOOKUP":
        # For events, add context-based queries
        if record:
            luogo = str(record.get("luogo", "")).strip()
            data_inizio = str(record.get("data_inizio", "")).strip()
            if luogo:
                family.variants.append(QueryVariant(
                    query_text=f"{target_name} {luogo}",
                    family="NOMINATIVE_WITH_CONTEXT",
                    purpose="Event + location",
                    priority=3,
                    source_field="luogo",
                ))
            if data_inizio:
                year = re.match(r"^(\d{4})", data_inizio)
                if year:
                    family.variants.append(QueryVariant(
                        query_text=f"{target_name} {year.group(1)}",
                        family="NOMINATIVE_WITH_CONTEXT",
                        purpose="Event + year",
                        priority=4,
                        source_field="data_inizio",
                    ))

            # V7.2: Extract keywords and aliases from event record (JSON arrays)
            import json as _json
            keywords_raw = record.get("keywords", "")
            aliases_raw = record.get("aliases", "")
            try:
                keywords = _json.loads(keywords_raw) if isinstance(keywords_raw, str) else (keywords_raw or [])
            except Exception:
                keywords = []
            try:
                aliases = _json.loads(aliases_raw) if isinstance(aliases_raw, str) else (aliases_raw or [])
            except Exception:
                aliases = []

            # Add keywords as EVENT_BASED query variants
            for kw in keywords:
                if kw and len(kw) >= 4 and kw.lower() not in target_name.lower():
                    family.variants.append(QueryVariant(
                        query_text=kw,
                        family="EVENT_BASED",
                        purpose=f"Event keyword: {kw}",
                        priority=7,
                        source_field="keywords",
                    ))

            # Add aliases as OCR_VARIANT query variants
            for alias in aliases:
                if alias and len(alias) >= 4 and alias.lower() not in target_name.lower():
                    family.variants.append(QueryVariant(
                        query_text=alias,
                        family="OCR_VARIANT",
                        purpose=f"Event alias: {alias}",
                        priority=8,
                        source_field="aliases",
                    ))

        # Event variant: without "battaglia di" prefix
        lower = target_name.lower()
        for prefix in ["battaglia di ", "battaglia dell'", "battaglia del ", "battaglia della "]:
            if lower.startswith(prefix):
                stripped = target_name[len(prefix):]
                family.variants.append(QueryVariant(
                    query_text=stripped,
                    family="OCR_VARIANT",
                    purpose="Event name without prefix",
                    priority=6,
                ))
                break

    return family


def _build_event_queries(sorte: str, record: Dict[str, Any]) -> List[str]:
    """Build event-based queries from a person's fate field."""
    queries = []
    sorte_lower = sorte.lower()

    # Death-related fates
    death_keywords = {
        "ucciso": "ucciso",
        "fucilato": "fucilato",
        "deceduto": "deceduto",
        "morto": "morto",
        "caduto": "caduto",
    }

    for kw, search_term in death_keywords.items():
        if kw in sorte_lower:
            # Try to extract place from sorte or other fields
            place = ""
            for pfield in ["luogo_morte", "luogo_internamento", "luogo_cattura"]:
                pval = str(record.get(pfield, "")).strip()
                if pval and pval != "-":
                    place = pval
                    break
            if place:
                queries.append(f"{search_term} {place} italiani")
            else:
                queries.append(f"{search_term} prigionieri italiani")
            break

    # Internment-related
    if "internato" in sorte_lower or "prigionia" in sorte_lower:
        place = str(record.get("luogo_internamento", "")).strip()
        if place and place != "-":
            queries.append(f"prigionieri italiani {place}")

    return queries


def _generate_ocr_variants(text: str) -> List[str]:
    """Generate OCR substitution variants of a text string."""
    variants = set()
    text_lower = text.lower()

    for old, new in _OCR_SUBSTITUTIONS.items():
        if old in text_lower:
            variant = text_lower.replace(old, new)
            if variant != text_lower:
                variants.add(variant)

    # Also try with just the first part if hyphenated
    if "-" in text:
        parts = text.split("-")
        for part in parts:
            if len(part) > 3:
                for old, new in _OCR_SUBSTITUTIONS.items():
                    if old in part.lower():
                        variants.add(part.lower().replace(old, new))

    return list(variants)[:5]  # limit to 5 variants


def _decompose_geographic_string(raw: str) -> List[str]:
    """Decompose a hyphenated geographic string into candidate place names.

    Example: "Stencle-Bai-Figan-Licvsia" → ["Stöntzsch bei Pegau Leipzig", "Stencle Pegau Leipzig"]
    """
    candidates = []
    parts = [p.strip() for p in raw.split("-") if p.strip()]

    if len(parts) < 2:
        return []

    # Try combining parts with German geographic connectors
    connectors = ["bei", "bei der", "im", "am"]

    # Apply OCR substitutions to each part
    normalized_parts = []
    for p in parts:
        p_lower = p.lower()
        for old, new in _OCR_SUBSTITUTIONS.items():
            if old in p_lower:
                p_lower = p_lower.replace(old, new)
                break
        normalized_parts.append(p_lower)

    # Build candidate: "part1 bei part2 part3"
    if len(normalized_parts) >= 3:
        # Try: first part + bei + second part + last part
        candidate = f"{normalized_parts[0]} bei {normalized_parts[1]} {normalized_parts[-1]}"
        candidates.append(candidate)

    # Try: all parts joined with space
    candidates.append(" ".join(normalized_parts))

    # Try: first + last only
    if len(normalized_parts) >= 2:
        candidates.append(f"{normalized_parts[0]} {normalized_parts[-1]}")

    return candidates[:3]  # limit to 3 candidates
