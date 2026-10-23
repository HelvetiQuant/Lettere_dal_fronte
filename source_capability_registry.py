"""Source Capability Registry — single registry for provider routing.

Used by:
- retrieval (federated search)
- query generation
- archival suggestions
- report rendering
- UI

Each source declares:
- conflicts (ww1, ww2, both)
- time_range
- subject_types
- research_goals
- geographic_scope
- result_kind
- access_mode
- official_name
- official_url
- custody_notes
- last_verified_at

This ensures that if LeBI/ANRP is skipped for a WWI target,
it cannot reappear in archival suggestions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import logging

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceCapability:
    """Capability declaration for a single source/provider."""
    provider_key: str
    official_name: str
    conflicts: str  # "ww1", "ww2", "both"
    time_range: str  # e.g., "1914-1918", "1943-1945", "1914-1945"
    subject_types: str  # "soldiers", "prisoners", "internati", "caduti", "general"
    research_goals: str  # "prisoners", "casualties", "biographical", "operational"
    geographic_scope: str  # "italy", "europe", "global", "regional"
    result_kind: str  # "record", "index", "search_page", "document"
    access_mode: str  # "api", "html", "pdf", "mixed"
    official_url: str = ""
    custody_notes: str = ""
    last_verified_at: str = "2026-07-31"
    suggest_for_prisoners: bool = False
    suggest_for_casualties: bool = False
    suggest_for_biographical: bool = False


# ─── Registry ─────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, SourceCapability] = {
    # WWI-only providers
    "icrc_ww1": SourceCapability(
        provider_key="icrc_ww1",
        official_name="ICRC — Prisoners of the First World War",
        conflicts="ww1",
        time_range="1914-1918",
        subject_types="prisoners",
        research_goals="prisoners",
        geographic_scope="europe",
        result_kind="record",
        access_mode="api",
        official_url="https://grandeguerre.icrc.org/",
        custody_notes="International Committee of the Red Cross archival index",
        suggest_for_prisoners=True,
    ),
    "grandeguerre_icrc": SourceCapability(
        provider_key="grandeguerre_icrc",
        official_name="ICRC — Grande Guerre",
        conflicts="ww1",
        time_range="1914-1918",
        subject_types="prisoners",
        research_goals="prisoners",
        geographic_scope="europe",
        result_kind="record",
        access_mode="html",
        official_url="https://grandeguerre.icrc.org/",
        suggest_for_prisoners=True,
    ),
    "albo_oro": SourceCapability(
        provider_key="albo_oro",
        official_name="Albo d'Oro dei Caduti della Grande Guerra",
        conflicts="ww1",
        time_range="1915-1918",
        subject_types="caduti",
        research_goals="casualties",
        geographic_scope="italy",
        result_kind="record",
        access_mode="html",
        official_url="https://www.difesa.it/OnorificenzeEDecorazioni/Pagine/AlbodOro.aspx",
        custody_notes="Ministero della Difesa — official roll of honour",
        suggest_for_casualties=True,
    ),
    "onoreaicaduti": SourceCapability(
        provider_key="onoreaicaduti",
        official_name="Onore ai Caduti",
        conflicts="ww1",
        time_range="1915-1918",
        subject_types="caduti",
        research_goals="casualties",
        geographic_scope="italy",
        result_kind="index",
        access_mode="html",
        suggest_for_casualties=True,
    ),
    "pietredellamemoria": SourceCapability(
        provider_key="pietredellamemoria",
        official_name="Pietre della Memoria",
        conflicts="ww1",
        time_range="1915-1918",
        subject_types="caduti",
        research_goals="casualties",
        geographic_scope="italy",
        result_kind="record",
        access_mode="html",
        official_url="https://www.pietredellamemoria.it/",
        suggest_for_casualties=True,
    ),
    "1914-1918-online": SourceCapability(
        provider_key="1914-1918-online",
        official_name="1914-1918-Online International Encyclopedia of the First World War",
        conflicts="ww1",
        time_range="1914-1918",
        subject_types="general",
        research_goals="context",
        geographic_scope="global",
        result_kind="document",
        access_mode="html",
    ),
    "europeana_1914-1918": SourceCapability(
        provider_key="europeana_1914-1918",
        official_name="Europeana 1914-1918",
        conflicts="ww1",
        time_range="1914-1918",
        subject_types="general",
        research_goals="context",
        geographic_scope="europe",
        result_kind="document",
        access_mode="api",
    ),
    "cadutigrandeguerra": SourceCapability(
        provider_key="cadutigrandeguerra",
        official_name="Caduti della Grande Guerra",
        conflicts="ww1",
        time_range="1915-1918",
        subject_types="caduti",
        research_goals="casualties",
        geographic_scope="italy",
        result_kind="index",
        access_mode="html",
        suggest_for_casualties=True,
    ),

    # WWII-only providers
    "arolsen": SourceCapability(
        provider_key="arolsen",
        official_name="Arolsen Archives International Center on Nazi Persecution",
        conflicts="ww2",
        time_range="1939-1945",
        subject_types="prisoners",
        research_goals="prisoners",
        geographic_scope="europe",
        result_kind="record",
        access_mode="api",
        official_url="https://collections.arolsen-archives.org/",
        suggest_for_prisoners=True,
    ),
    "yadvashem": SourceCapability(
        provider_key="yadvashem",
        official_name="Yad Vashem — World Holocaust Remembrance Center",
        conflicts="ww2",
        time_range="1933-1945",
        subject_types="victims",
        research_goals="biographical",
        geographic_scope="global",
        result_kind="record",
        access_mode="api",
    ),
    "ushmm": SourceCapability(
        provider_key="ushmm",
        official_name="United States Holocaust Memorial Museum",
        conflicts="ww2",
        time_range="1933-1945",
        subject_types="victims",
        research_goals="biographical",
        geographic_scope="global",
        result_kind="record",
        access_mode="api",
    ),
    "mauthausen_memorial": SourceCapability(
        provider_key="mauthausen_memorial",
        official_name="Mauthausen Memorial",
        conflicts="ww2",
        time_range="1938-1945",
        subject_types="prisoners",
        research_goals="prisoners",
        geographic_scope="europe",
        result_kind="record",
        access_mode="html",
    ),
    "lebi": SourceCapability(
        provider_key="lebi",
        official_name="ANRP — Lessico Biografico degli IMI",
        conflicts="ww2",
        time_range="1943-1945",
        subject_types="internati",
        research_goals="biographical",
        geographic_scope="italy",
        result_kind="record",
        access_mode="html",
        official_url="https://www.lessicobiograficoimi.it/",
        custody_notes="ANRP biographical dictionary of Italian Military Internees 1943-1945",
        suggest_for_biographical=True,
    ),
    "lessicobiograficoimi": SourceCapability(
        provider_key="lessicobiograficoimi",
        official_name="Lessico Biografico degli IMI",
        conflicts="ww2",
        time_range="1943-1945",
        subject_types="internati",
        research_goals="biographical",
        geographic_scope="italy",
        result_kind="record",
        access_mode="html",
        official_url="https://www.lessicobiograficoimi.it/",
        suggest_for_biographical=True,
    ),
    "anrp": SourceCapability(
        provider_key="anrp",
        official_name="ANRP — Associazione Nazionale Reduci dalla Prigionia",
        conflicts="ww2",
        time_range="1943-1945",
        subject_types="internati",
        research_goals="biographical",
        geographic_scope="italy",
        result_kind="record",
        access_mode="html",
        suggest_for_biographical=True,
    ),

    # Both conflicts
    "familysearch": SourceCapability(
        provider_key="familysearch",
        official_name="FamilySearch International",
        conflicts="both",
        time_range="1800-2000",
        subject_types="general",
        research_goals="biographical",
        geographic_scope="global",
        result_kind="index",
        access_mode="api",
        official_url="https://www.familysearch.org/",
    ),
    "ancestry": SourceCapability(
        provider_key="ancestry",
        official_name="Ancestry.com",
        conflicts="both",
        time_range="1800-2000",
        subject_types="general",
        research_goals="biographical",
        geographic_scope="global",
        result_kind="index",
        access_mode="api",
    ),
    "findagrave": SourceCapability(
        provider_key="findagrave",
        official_name="Find a Grave",
        conflicts="both",
        time_range="1800-2020",
        subject_types="general",
        research_goals="biographical",
        geographic_scope="global",
        result_kind="record",
        access_mode="html",
    ),
    "commonwealthwargraves": SourceCapability(
        provider_key="commonwealthwargraves",
        official_name="Commonwealth War Graves Commission",
        conflicts="both",
        time_range="1914-1945",
        subject_types="soldiers",
        research_goals="casualties",
        geographic_scope="global",
        result_kind="record",
        access_mode="api",
        official_url="https://www.cwgc.org/",
    ),
    "nara": SourceCapability(
        provider_key="nara",
        official_name="U.S. National Archives and Records Administration",
        conflicts="both",
        time_range="1914-1945",
        subject_types="general",
        research_goals="biographical",
        geographic_scope="global",
        result_kind="record",
        access_mode="api",
    ),
    "national_archives_uk": SourceCapability(
        provider_key="national_archives_uk",
        official_name="The National Archives (UK)",
        conflicts="both",
        time_range="1914-1945",
        subject_types="general",
        research_goals="biographical",
        geographic_scope="europe",
        result_kind="record",
        access_mode="api",
    ),
    "bundesarchiv": SourceCapability(
        provider_key="bundesarchiv",
        official_name="Bundesarchiv (German Federal Archives)",
        conflicts="both",
        time_range="1914-1945",
        subject_types="general",
        research_goals="biographical",
        geographic_scope="europe",
        result_kind="record",
        access_mode="api",
    ),
    "wikipedia": SourceCapability(
        provider_key="wikipedia",
        official_name="Wikipedia",
        conflicts="both",
        time_range="any",
        subject_types="general",
        research_goals="context",
        geographic_scope="global",
        result_kind="document",
        access_mode="api",
    ),
    "dbpedia": SourceCapability(
        provider_key="dbpedia",
        official_name="DBpedia",
        conflicts="both",
        time_range="any",
        subject_types="general",
        research_goals="context",
        geographic_scope="global",
        result_kind="document",
        access_mode="api",
    ),
    "wikidata": SourceCapability(
        provider_key="wikidata",
        official_name="Wikidata",
        conflicts="both",
        time_range="any",
        subject_types="general",
        research_goals="context",
        geographic_scope="global",
        result_kind="document",
        access_mode="api",
    ),
}


def get_capability(provider_key: str) -> Optional[SourceCapability]:
    """Get capability for a provider."""
    return _REGISTRY.get(provider_key)


def get_eligible_providers(conflict: str) -> Set[str]:
    """Get set of provider keys eligible for a given conflict."""
    eligible = set()
    for key, cap in _REGISTRY.items():
        if cap.conflicts == conflict or cap.conflicts == "both":
            eligible.add(key)
    return eligible


def get_skipped_providers(conflict: str) -> Set[str]:
    """Get set of provider keys skipped for a given conflict."""
    skipped = set()
    for key, cap in _REGISTRY.items():
        if cap.conflicts != conflict and cap.conflicts != "both":
            skipped.add(key)
    return skipped


def is_eligible_for_suggestion(provider_key: str, conflict: str,
                                 research_goal: str = "") -> bool:
    """Check if a provider is eligible for archival suggestions.

    This is the SAME routing used for retrieval — if a provider was
    skipped for a WWI target, it cannot appear in suggestions.
    """
    cap = _REGISTRY.get(provider_key)
    if not cap:
        return False
    if cap.conflicts != conflict and cap.conflicts != "both":
        return False
    # ICRC WWI Prisoners only for prisoner/dispersi goals
    if provider_key in ("icrc_ww1", "grandeguerre_icrc"):
        if research_goal and research_goal not in ("prisoners", "dispersi", ""):
            return False
    # LeBI/ANRP only for WWII biographical
    if provider_key in ("lebi", "lessicobiograficoimi", "anrp"):
        if conflict != "ww2":
            return False
    return True


def get_routing_matrix(conflict: str) -> dict:
    """Return routing matrix for a given conflict."""
    eligible = get_eligible_providers(conflict)
    skipped = get_skipped_providers(conflict)
    return {
        "eligible": sorted(eligible),
        "skipped": sorted(skipped),
        "eligible_count": len(eligible),
        "skipped_count": len(skipped),
        "reason": f"Conflict={conflict}: skipping {len(skipped)} incompatible providers",
    }
