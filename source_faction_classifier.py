"""Source Faction Classifier — Classifies sources by faction alignment and role.

Key principles:
- Faction ≠ Archive country (Italian doc in Bundesarchiv = Italian source)
- Classification based on: author/producer, military unit, administration, command,
  language (as hint only), original archival provenance, content, metadata
- Separates repository from source_creator_alignment

EVENT ONLY.
"""
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Any, Optional

from viewpoint_models import (
    FactionAlignment,
    SourceRole,
    TemporalLayer,
    PropagandaStatus,
    SourceFactionClassification,
)


# --- Faction alignment heuristics ---

_ITALIAN_INDICATORS = [
    "italia", "italian", "regio esercito", "stato maggiore", "comando supremo",
    "divisione", "reggimento", "brigata", "armir", "csir", "corpo d'armata",
    "ministero della guerra", "uomini arruolati", "alpini", "bersaglieri",
    "fanteria", "artiglieria", "genio", "cavalleria", "divisione acqui",
    "internati militari italiani", "imi", "anrp", "cicr",
]

_AUSTRO_HUNGARIAN_INDICATORS = [
    "austria", "austro-ungarico", "k.u.k", "kuk", "kaiserlich", "österreich",
    "ungarisch", "honvéd", "kaiser", "franz josef", "tiroler kaiserjäger",
    "edelweiss", "irredentismo",
]

_GERMAN_INDICATORS = [
    "germania", "deutschland", "german", "deutsche", "wehrmacht", "okw",
    "okh", "heeresgruppe", "armeeoberkommando", "generalkommando", "division",
    "regiment", "bataillon", "bundesarchiv", "reich", "luftwaffe", "ss",
    "waffen-ss", "kriegstagebuch", "wehrmachtsauskunft",
]

_ALLIED_INDICATORS = [
    "alleati", "allied", "allies", "coalizione", "cobelligerante",
]

_BRITISH_INDICATORS = [
    "britannico", "british", "uk", "united kingdom", "war office",
    "national archives uk", "kew", "commonwealth", "imperial war museum",
]

_FRENCH_INDICATORS = [
    "francia", "french", "france", "armée française", "service historique",
    "vincennes", "grand quartier général",
]

_US_INDICATORS = [
    "stati uniti", "united states", "american", "usa", "us army",
    "nara", "national archives washington", "pentagon",
]

_SOVIET_INDICATORS = [
    "soviet", "sovietico", "urss", "cccp", "red army", "krasnaya armiya",
    "rossiyskaya", "stalin", "moscow",
]

_YUGOSLAV_INDICATORS = [
    "jugoslavia", "yugoslav", "partigiani jugoslavi", "tito", "avnoj",
]

_GREEK_INDICATORS = [
    "grecia", "greek", "ellás", "hellenic", "athens",
]

_RESISTANCE_INDICATORS = [
    "resistenza", "partigiani", "partisan", "maquis", "underground",
    "résistance", "widerstand",
]

_CIVILIAN_INDICATORS = [
    "civile", "civilian", "popolazione", "population", "profughi",
    "rifugiati", "refugees",
]

_POSTWAR_HISTORIOGRAPHY_INDICATORS = [
    "storiografia", "historiography", "postwar study", "studio postbellico",
    "revisione storica", "historical analysis",
]

_FACTION_MAP = {
    FactionAlignment.ITALIAN: _ITALIAN_INDICATORS,
    FactionAlignment.AUSTRO_HUNGARIAN: _AUSTRO_HUNGARIAN_INDICATORS,
    FactionAlignment.GERMAN: _GERMAN_INDICATORS,
    FactionAlignment.ALLIED: _ALLIED_INDICATORS,
    FactionAlignment.BRITISH: _BRITISH_INDICATORS,
    FactionAlignment.FRENCH: _FRENCH_INDICATORS,
    FactionAlignment.US: _US_INDICATORS,
    FactionAlignment.SOVIET: _SOVIET_INDICATORS,
    FactionAlignment.YUGOSLAV: _YUGOSLAV_INDICATORS,
    FactionAlignment.GREEK: _GREEK_INDICATORS,
    FactionAlignment.RESISTANCE: _RESISTANCE_INDICATORS,
    FactionAlignment.CIVILIAN: _CIVILIAN_INDICATORS,
    FactionAlignment.POSTWAR_HISTORIOGRAPHY: _POSTWAR_HISTORIOGRAPHY_INDICATORS,
}

# Repository → default faction (overridable by content analysis)
_REPOSITORY_DEFAULTS = {
    "bundesarchiv": FactionAlignment.GERMAN,
    "national archives uk": FactionAlignment.BRITISH,
    "nara": FactionAlignment.US,
    "archivio centrale dello stato": FactionAlignment.ITALIAN,
    "archivio di stato": FactionAlignment.ITALIAN,
    "anrp": FactionAlignment.ITALIAN,
    "uussme": FactionAlignment.ITALIAN,
    "imperial war museum": FactionAlignment.BRITISH,
    "service historique": FactionAlignment.FRENCH,
    "kriegsarchiv": FactionAlignment.AUSTRO_HUNGARIAN,
    "anno": FactionAlignment.AUSTRO_HUNGARIAN,
    "onb": FactionAlignment.AUSTRO_HUNGARIAN,
    "oenb": FactionAlignment.AUSTRO_HUNGARIAN,
    "bayerisches": FactionAlignment.GERMAN,
    "bhk": FactionAlignment.GERMAN,
    "volksbund": FactionAlignment.GERMAN,
    "schwarzes kreuz": FactionAlignment.AUSTRO_HUNGARIAN,
    "deutsche digitale bibliothek": FactionAlignment.GERMAN,
    "ddb": FactionAlignment.GERMAN,
    "berlin state library": FactionAlignment.GERMAN,
    "baden-württemberg": FactionAlignment.GERMAN,
    "state library tyrol": FactionAlignment.AUSTRO_HUNGARIAN,
}

# --- Source role heuristics ---

_ROLE_INDICATORS = {
    SourceRole.OPERATIONAL_ORDER: ["ordine operativo", "operationsbefehl", "operational order", "directive"],
    SourceRole.WAR_DIARY: ["kriegstagebuch", "war diary", "diario di guerra", "giornale di guerra"],
    SourceRole.SITUATION_REPORT: ["situation report", "lagenbericht", "rapporto situazione"],
    SourceRole.AFTER_ACTION_REPORT: ["after action", "nachträglich", "relazione post-operazione"],
    SourceRole.CASUALTY_REPORT: ["perdite", "casualties", "verluste", "caduti", "feriti"],
    SourceRole.INTELLIGENCE_REPORT: ["intelligence", "nachrichten", "informazioni"],
    SourceRole.PRISONER_REPORT: ["prisoner", "kriegsgefangene", "prigioniero"],
    SourceRole.PERSONAL_DIARY: ["diario personale", "personal diary", "tagebuch"],
    SourceRole.LETTER: ["lettera", "brief", "correspondence", "corrispondenza"],
    SourceRole.PROPAGANDA: ["propaganda", "propaganda ministry", "ministero propaganda"],
    SourceRole.PRESS: ["press", "giornale", "zeitung", "newspaper", "corriere"],
    SourceRole.MEMOIR: ["memorie", "memoir", "erinnerungen", "ricordi"],
    SourceRole.ORAL_HISTORY: ["oral history", "testimonianza orale", "intervista"],
    SourceRole.POSTWAR_STUDY: ["postwar study", "studio postbellico", "historical analysis"],
    SourceRole.ARCHIVAL_CATALOG_METADATA: ["catalog", "inventario", "findbuch", "scheda archivistica"],
}


def _score_faction(text: str, indicators: list[str]) -> int:
    """Score how strongly text matches a faction's indicators."""
    text_lower = text.lower()
    score = 0
    for ind in indicators:
        if ind in text_lower:
            score += 1
    return score


def classify_faction(
    source_id: str,
    source_label: str,
    source_metadata: dict[str, Any],
    event_context: dict[str, Any],
) -> FactionAlignment:
    """Classify a source's faction alignment.

    Priority:
    1. Explicit metadata (source_creator_alignment, unit, command)
    2. Content analysis (text, description, keywords)
    3. Repository default (overridable)
    4. UNKNOWN
    """
    # 1. Check explicit metadata
    explicit = source_metadata.get("source_creator_alignment") or source_metadata.get("faction")
    if explicit:
        try:
            return FactionAlignment(explicit.upper())
        except (ValueError, AttributeError):
            pass

    # Check unit/administration
    unit = (source_metadata.get("unit") or "").lower()
    administration = (source_metadata.get("administration") or "").lower()
    command = (source_metadata.get("command") or "").lower()

    combined_explicit = f"{unit} {administration} {command}"

    # 2. Content analysis
    text_parts = [
        source_label,
        source_metadata.get("description", ""),
        source_metadata.get("text", ""),
        source_metadata.get("content", ""),
        source_metadata.get("keywords", ""),
        combined_explicit,
    ]
    full_text = " ".join(str(p) for p in text_parts if p)

    scores = {}
    for faction, indicators in _FACTION_MAP.items():
        s = _score_faction(full_text, indicators)
        if s > 0:
            scores[faction] = s

    if scores:
        best = max(scores, key=scores.get)
        return best

    # 3. Target table default (for event_links sources)
    target_table = (source_metadata.get("target_table") or "").lower()
    link_type = (source_metadata.get("link_type") or "").lower()

    _TABLE_FACTION_DEFAULTS = {
        "caduti_albooro": FactionAlignment.ITALIAN,
        "caduti_onorcaduti": FactionAlignment.ITALIAN,
        "decorati_nastroazzurro": FactionAlignment.ITALIAN,
        "decorati_albooro": FactionAlignment.ITALIAN,
        "internati": FactionAlignment.ITALIAN,
        "fonti_indice": FactionAlignment.UNKNOWN,
        "archivio_documenti": FactionAlignment.UNKNOWN,
    }

    # Provider-based faction defaults (for archivio_documenti sources)
    _PROVIDER_FACTION_DEFAULTS = {
        "kriegsarchivwien": FactionAlignment.AUSTRO_HUNGARIAN,
        "oeb-anno": FactionAlignment.AUSTRO_HUNGARIAN,
        "bayerischeshauptstaatsarchiv": FactionAlignment.GERMAN,
        "volksbund": FactionAlignment.GERMAN,
        "oeskr": FactionAlignment.AUSTRO_HUNGARIAN,
        "ussme": FactionAlignment.ITALIAN,
        "ussme-smd": FactionAlignment.ITALIAN,
    }

    if target_table in _TABLE_FACTION_DEFAULTS:
        faction = _TABLE_FACTION_DEFAULTS[target_table]
        if faction != FactionAlignment.UNKNOWN:
            return faction

    # 3b. Provider default (for archivio_documenti sources)
    provider = (source_metadata.get("provider") or "").lower()
    for prov_key, default_faction in _PROVIDER_FACTION_DEFAULTS.items():
        if prov_key in provider:
            return default_faction

    # 4. Repository default
    repository = (source_metadata.get("repository") or "").lower()
    for repo_key, default_faction in _REPOSITORY_DEFAULTS.items():
        if repo_key in repository:
            return default_faction

    # 5. Unknown
    return FactionAlignment.UNKNOWN


def classify_role(source_metadata: dict[str, Any], source_label: str) -> SourceRole:
    """Classify the role of a source."""
    # Check explicit metadata
    explicit = source_metadata.get("source_role") or source_metadata.get("document_type")
    if explicit:
        try:
            return SourceRole(explicit.lower())
        except (ValueError, AttributeError):
            pass

    # Content analysis
    text = f"{source_label} {source_metadata.get('description', '')} {source_metadata.get('text', '')}".lower()

    scores = {}
    for role, indicators in _ROLE_INDICATORS.items():
        s = sum(1 for ind in indicators if ind in text)
        if s > 0:
            scores[role] = s

    if scores:
        return max(scores, key=scores.get)

    return SourceRole.UNKNOWN


def classify_temporal_layer(source_metadata: dict[str, Any], event_dates: tuple[Optional[str], Optional[str]] = (None, None)) -> TemporalLayer:
    """Classify the temporal layer of a source relative to the event."""
    explicit = source_metadata.get("temporal_layer")
    if explicit:
        try:
            return TemporalLayer(explicit.upper())
        except (ValueError, AttributeError):
            pass

    source_date = source_metadata.get("date") or source_metadata.get("created_at") or ""
    source_year = None
    if source_date:
        try:
            source_year = int(str(source_date)[:4])
        except (ValueError, TypeError):
            pass

    event_start_year = None
    event_end_year = None
    if event_dates[0]:
        try:
            event_start_year = int(str(event_dates[0])[:4])
        except (ValueError, TypeError):
            pass
    if event_dates[1]:
        try:
            event_end_year = int(str(event_dates[1])[:4])
        except (ValueError, TypeError):
            pass

    # Check for text indicators first (memoir, historiography)
    text = f"{source_metadata.get('description', '')} {source_metadata.get('text', '')}".lower()
    if any(w in text for w in ["memorie", "memoir", "ricordi", "erinnerungen"]):
        return TemporalLayer.POSTWAR_TESTIMONY
    if any(w in text for w in ["storiografia", "historiography", "historical analysis"]):
        return TemporalLayer.HISTORIOGRAPHICAL

    # Year-based classification
    if source_year and event_start_year:
        event_end = event_end_year or event_start_year
        diff = source_year - event_end
        if diff <= 1:
            return TemporalLayer.CONTEMPORARY
        elif diff <= 5:
            return TemporalLayer.NEAR_CONTEMPORARY
        elif diff <= 30:
            return TemporalLayer.POSTWAR_TESTIMONY
        else:
            return TemporalLayer.HISTORIOGRAPHICAL

    return TemporalLayer.CONTEMPORARY


def assess_propaganda(source_metadata: dict[str, Any], source_role: SourceRole) -> tuple[PropagandaStatus, float]:
    """Assess propaganda status and rhetorical intensity.

    Returns (propaganda_status, rhetorical_intensity 0.0-1.0).
    Only DOCUMENTED when there's explicit evidence of propaganda nature.
    """
    if source_role == SourceRole.PROPAGANDA:
        return PropagandaStatus.DOCUMENTED, 0.8

    text = f"{source_metadata.get('description', '')} {source_metadata.get('text', '')}".lower()

    # Rhetorical markers
    rhetorical_markers = [
        "eroico", "heroic", "vile", "criminale", "barbaro", "barbaric",
        "tradimento", "betrayal", "sacro dovere", "sacred duty",
        "invasore", "invader", "liberatore", "liberator",
        "martiri", "martyrs", "sacrificio supremo",
    ]
    rhetorical_count = sum(1 for m in rhetorical_markers if m in text)
    intensity = min(rhetorical_count / 5.0, 1.0)

    if intensity >= 0.6:
        return PropagandaStatus.POSSIBLE, intensity
    elif intensity >= 0.3:
        return PropagandaStatus.POSSIBLE, intensity

    return PropagandaStatus.NOT_ASSESSED, intensity


def classify_source(
    source_id: str,
    source_label: str,
    source_metadata: dict[str, Any],
    event_context: dict[str, Any],
) -> SourceFactionClassification:
    """Full classification of a source for viewpoint analysis."""
    faction = classify_faction(source_id, source_label, source_metadata, event_context)
    role = classify_role(source_metadata, source_label)

    event_dates = (
        event_context.get("data_inizio"),
        event_context.get("data_fine"),
    )
    temporal = classify_temporal_layer(source_metadata, event_dates)

    propaganda, rhetoric = assess_propaganda(source_metadata, role)

    # Build classification reason
    reasons = []
    if source_metadata.get("source_creator_alignment"):
        reasons.append("explicit creator alignment")
    if source_metadata.get("unit"):
        reasons.append(f"unit: {source_metadata['unit']}")
    if source_metadata.get("repository"):
        reasons.append(f"repository: {source_metadata['repository']}")
    if not reasons:
        reasons.append("content-based heuristic")

    confidence = 0.5
    if source_metadata.get("source_creator_alignment"):
        confidence = 0.95
    elif source_metadata.get("unit") or source_metadata.get("command"):
        confidence = 0.8
    elif faction != FactionAlignment.UNKNOWN:
        confidence = 0.6

    return SourceFactionClassification(
        source_id=source_id,
        source_label=source_label,
        faction_alignment=faction,
        source_role=role,
        temporal_layer=temporal,
        repository=source_metadata.get("repository", ""),
        source_creator_alignment=source_metadata.get("source_creator_alignment", ""),
        classification_reason="; ".join(reasons),
        classification_confidence=confidence,
        propaganda_status=propaganda,
        rhetorical_intensity=rhetoric,
        metadata=source_metadata,
    )
