"""
Feature extraction and conflict detection for linking v2.

Extracts comparable features from candidate pairs and detects
hard conflicts (veto) that prevent confirmation.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any

from linking.normalization import (
    normalize_name, normalize_date, normalize_place,
    date_overlap, VERSION,
)


FEATURE_SCHEMA_VERSION = "2.0.0"


@dataclass
class Features:
    """Features extracted from a candidate pair."""
    name_match: bool = False
    name_cognome_exact: bool = False
    name_nome_exact: bool = False
    name_cognome_phonetic: bool = False
    birth_date_compatible: bool = False
    birth_place_compatible: bool = False
    same_matricola: bool = False
    same_unit: bool = False
    same_camp: bool = False
    temporal_overlap: bool = False
    geographic_compatible: bool = False
    document_citation: bool = False
    discriminators: list[str] = field(default_factory=list)
    matched_terms: dict = field(default_factory=dict)
    conflict_markers_matched: list[str] = field(default_factory=list)
    version: str = field(default=FEATURE_SCHEMA_VERSION, init=False)


@dataclass
class ConflictFlags:
    """Hard conflicts that veto confirmation."""
    ww1_ww2_mismatch: bool = False
    born_after_event: bool = False
    died_before_event: bool = False
    unit_not_active: bool = False
    geo_incompatible: bool = False
    matricola_mismatch: bool = False
    omonimia_no_discriminator: bool = False
    search_page_only: bool = False
    event_too_broad: bool = False
    temporal_conflict: bool = False
    mixed_era_source: bool = False
    ambiguous_keywords_only: bool = False
    flags: list[str] = field(default_factory=list)
    
    def to_list(self) -> list[str]:
        result = []
        if self.ww1_ww2_mismatch: result.append("ww1_ww2_mismatch")
        if self.born_after_event: result.append("born_after_event")
        if self.died_before_event: result.append("died_before_event")
        if self.unit_not_active: result.append("unit_not_active")
        if self.geo_incompatible: result.append("geo_incompatible")
        if self.matricola_mismatch: result.append("matricola_mismatch")
        if self.omonimia_no_discriminator: result.append("omonimia_no_discriminator")
        if self.search_page_only: result.append("search_page_only")
        if self.event_too_broad: result.append("event_too_broad")
        if self.temporal_conflict: result.append("temporal_conflict")
        if self.mixed_era_source: result.append("mixed_era_source")
        if self.ambiguous_keywords_only: result.append("ambiguous_keywords_only")
        return result
    
    @property
    def has_veto(self) -> bool:
        return any([
            self.ww1_ww2_mismatch, self.born_after_event, self.died_before_event,
            self.unit_not_active, self.geo_incompatible, self.matricola_mismatch,
            self.omonimia_no_discriminator, self.temporal_conflict,
        ])


# ─── Ambiguous keywords that must not generate strong matches ────────────────

AMBIGUOUS_KEYWORDS = {
    "campo", "russia", "africa", "nero", "corno", "lana",
    "prigionia", "prigioniero", "lager", "cattura", "captured",
    "fronte", "guerra", "morto", "caduto", "ferito",
    "armistizio", "offensiva", "trincea", "difesa", "ritirata",
    "alpini", "concentramento", "internamento", "montagna",
    "ghiacciai", "bombardamento", "deportazione", "ritirata",
    "ripiegamento", "riorganizzazione", "disarmo",
}


def is_ambiguous_keyword(kw: str) -> bool:
    """Check if a keyword is too generic for strong matching."""
    return kw.lower().strip() in AMBIGUOUS_KEYWORDS


def extract_features_person_source(
    source_row: dict,
    target_row: dict,
) -> Features:
    """
    Extract features for a person ↔ source candidate pair.
    
    Requires at least one independent discriminator beyond name match
    to elevate evidence strength above 'weak'.
    """
    f = Features()
    
    # Name matching
    s_norm = normalize_name(
        source_row.get("cognome", ""),
        source_row.get("nome", ""),
    )
    t_norm = normalize_name(
        target_row.get("cognome", target_row.get("nominativo_cognome", "")),
        target_row.get("nome", target_row.get("nominativo_nome", "")),
    )
    
    if s_norm.cognome_normalized and t_norm.cognome_normalized:
        if s_norm.cognome_normalized == t_norm.cognome_normalized:
            f.name_cognome_exact = True
            f.name_match = True
        elif _phonetic_match(s_norm.cognome_normalized, t_norm.cognome_normalized):
            f.name_cognome_phonetic = True
            f.name_match = True
    
    if s_norm.nome_normalized and t_norm.nome_normalized:
        if s_norm.nome_normalized == t_norm.nome_normalized:
            f.name_nome_exact = True
    
    # Birth date compatibility
    s_date = normalize_date(source_row.get("data_nascita", ""))
    t_date = normalize_date(target_row.get("data_nascita", ""))
    if s_date.precision != "unknown" and t_date.precision != "unknown":
        if date_overlap(s_date.start, s_date.end, t_date.start, t_date.end):
            f.birth_date_compatible = True
            f.discriminators.append("birth_date")
    
    # Birth place compatibility
    s_place = normalize_place(source_row.get("luogo_nascita", ""))
    t_place = normalize_place(target_row.get("luogo_nascita", ""))
    if s_place.normalized and t_place.normalized:
        if _place_match(s_place.normalized, t_place.normalized):
            f.birth_place_compatible = True
            f.discriminators.append("birth_place")
    
    # Matricola
    s_mat = (source_row.get("matricola") or "").strip()
    t_mat = (target_row.get("matricola") or "").strip()
    if s_mat and t_mat and s_mat == t_mat:
        f.same_matricola = True
        f.discriminators.append("matricola")
    
    # Unit
    s_unit = (source_row.get("unita") or source_row.get("reparto") or "").strip()
    t_unit = (target_row.get("unita") or target_row.get("reparto") or "").strip()
    if s_unit and t_unit and s_unit.lower() == t_unit.lower():
        f.same_unit = True
        f.discriminators.append("unit")
    
    return f


def extract_features_person_event(
    person_row: dict,
    event_row: dict,
) -> tuple[Features, ConflictFlags]:
    """
    Extract features for a person ↔ event candidate pair.
    Returns features and conflict flags.
    """
    f = Features()
    cf = ConflictFlags()
    
    # Temporal compatibility
    event_start = event_row.get("data_inizio") or event_row.get("start_date")
    event_end = event_row.get("data_fine") or event_row.get("end_date")
    event_conflict = event_row.get("conflict_code", "")
    
    # Check WW1/WW2 mismatch
    person_conflict = _infer_person_conflict(person_row)
    if person_conflict and event_conflict and person_conflict != event_conflict:
        cf.ww1_ww2_mismatch = True
    
    # Born after event
    birth = normalize_date(person_row.get("data_nascita", ""))
    if birth.precision != "unknown" and event_start:
        try:
            if int(birth.start[:4]) > int(event_start[:4]) + 1:
                cf.born_after_event = True
        except (ValueError, IndexError):
            pass
    
    # Died before event
    death = person_row.get("data_morte") or person_row.get("data_decesso")
    if death and event_start:
        death_norm = normalize_date(death)
        if death_norm.precision != "unknown":
            try:
                if int(death_norm.start[:4]) < int(event_start[:4]) - 1:
                    cf.died_before_event = True
            except (ValueError, IndexError):
                pass
    
    # Temporal overlap
    if event_start and event_end:
        # Person's active period (birth to death or capture)
        person_start = birth.start or ""
        person_end = death or person_row.get("data_cattura") or ""
        if person_start and person_end:
            if date_overlap(person_start, person_end, event_start, event_end):
                f.temporal_overlap = True
                f.discriminators.append("temporal_overlap")
    
    # Geographic compatibility
    person_place = person_row.get("luogo_morte") or person_row.get("luogo_cattura") or ""
    event_place = event_row.get("luogo") or ""
    if person_place and event_place:
        if _place_match(person_place, event_place):
            f.geographic_compatible = True
            f.discriminators.append("geo_place")
    
    # Unit in theater
    person_unit = person_row.get("unita") or person_row.get("reparto") or ""
    if person_unit and event_row.get("keywords"):
        try:
            keywords = json.loads(event_row["keywords"]) if isinstance(event_row["keywords"], str) else event_row["keywords"]
            for kw in keywords:
                if not is_ambiguous_keyword(kw) and kw.lower() in person_unit.lower():
                    f.same_unit = True
                    f.discriminators.append("unit_in_theater")
                    break
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Document citation (placeholder — requires evidence_fragments)
    # This would check if there's an evidence_fragment linking the person to the event
    
    # Check for ambiguous keyword-only matches
    if not f.discriminators:
        cf.omonimia_no_discriminator = True
    
    return f, cf


def extract_features_document_event(
    doc_row: dict,
    event_row: dict,
) -> tuple[Features, ConflictFlags]:
    """
    Extract features for a document ↔ event candidate pair.
    Uses lexical boundary matching, not substring.
    """
    f = Features()
    cf = ConflictFlags()
    
    event_conflict = event_row.get("conflict_code", "")
    event_start = event_row.get("data_inizio") or event_row.get("start_date")
    event_end = event_row.get("data_fine") or event_row.get("end_date")
    
    # Temporal compatibility of document
    doc_year = doc_row.get("year_start")
    if doc_year and event_start and event_end:
        try:
            if int(event_start[:4]) <= doc_year <= int(event_end[:4]):
                f.temporal_overlap = True
                f.discriminators.append("doc_year_in_event_range")
        except (ValueError, IndexError):
            pass
    
    # Lexical boundary matching (not substring)
    text = " ".join(filter(None, [
        doc_row.get("title", ""),
        doc_row.get("description", ""),
        doc_row.get("place", ""),
    ]))
    
    keywords = event_row.get("keywords", "[]")
    try:
        keywords = json.loads(keywords) if isinstance(keywords, str) else keywords
    except (json.JSONDecodeError, TypeError):
        keywords = []
    
    aliases = event_row.get("aliases", "[]")
    try:
        aliases = json.loads(aliases) if isinstance(aliases, str) else aliases
    except (json.JSONDecodeError, TypeError):
        aliases = []
    
    matched_kw = None
    matched_in_title = False
    
    for kw in keywords:
        if is_ambiguous_keyword(kw):
            continue
        if _word_boundary_match(kw, text):
            matched_kw = kw
            if _word_boundary_match(kw, doc_row.get("title", "")):
                matched_in_title = True
            break
    
    if not matched_kw:
        for alias in aliases:
            if is_ambiguous_keyword(alias):
                continue
            if len(alias) >= 4 and _word_boundary_match(alias, text):
                matched_kw = alias
                break
    
    if matched_kw:
        f.document_citation = True
        f.discriminators.append(f"keyword:{matched_kw}")
        if matched_in_title:
            f.discriminators.append("keyword_in_title")
    
    if not f.discriminators:
        cf.omonimia_no_discriminator = True
    
    return f, cf


def extract_features_source_event(
    source_row: dict,
    event_row: dict,
) -> tuple[Features, ConflictFlags]:
    """
    Extract features for a fonti_indice ↔ event candidate pair.
    
    Uses temporal_relation from temporal_filter for coverage overlap/conflict,
    keyword classification (distinctive/ambiguous/opposite_conflict),
    and word boundary matching.
    """
    from linking.temporal_filter import (
        temporal_relation as _temporal_relation,
        detect_conflict_markers,
        detect_same_era_markers,
        detect_ambiguous_markers,
        classify_keyword,
        KeywordClass,
    )
    
    f = Features()
    cf = ConflictFlags()
    
    event_conflict = event_row.get("conflict") or event_row.get("conflict_code") or ""
    event_start = event_row.get("data_inizio") or event_row.get("start_date")
    event_end = event_row.get("data_fine") or event_row.get("end_date")
    
    # ─── Temporal compatibility ──────────────────────────────────────────
    cov_start = (
        source_row.get("coverage_start")
        or source_row.get("data_inizio")
    )
    cov_end = (
        source_row.get("coverage_end")
        or source_row.get("data_fine")
    )
    
    t_rel = _temporal_relation(cov_start, cov_end, event_start, event_end)
    
    if t_rel == "overlap":
        f.temporal_overlap = True
        f.discriminators.append("temporal_overlap")
    elif t_rel == "conflict":
        cf.temporal_conflict = True
    
    # ─── Text for keyword matching ───────────────────────────────────────
    text = " ".join(filter(None, [
        source_row.get("titolo", ""),
        source_row.get("soggetti_collegati", ""),
        source_row.get("note", ""),
        source_row.get("luogo", ""),
    ]))
    
    # ─── Conflict marker detection ───────────────────────────────────────
    conflict_markers = detect_conflict_markers(text, event_conflict)
    same_era_markers = detect_same_era_markers(text, event_conflict)
    ambiguous_markers = detect_ambiguous_markers(text)
    
    if conflict_markers:
        cf.ww1_ww2_mismatch = True
        f.conflict_markers_matched = conflict_markers
    
    if same_era_markers:
        for m in same_era_markers:
            f.discriminators.append(f"same_era:{m}")
        f.document_citation = True
    
    # ─── Keyword matching with classification ────────────────────────────
    keywords = event_row.get("keywords", "[]")
    try:
        keywords = json.loads(keywords) if isinstance(keywords, str) else keywords
    except (json.JSONDecodeError, TypeError):
        keywords = []
    
    aliases = event_row.get("aliases", "[]")
    try:
        aliases = json.loads(aliases) if isinstance(aliases, str) else aliases
    except (json.JSONDecodeError, TypeError):
        aliases = []
    
    matched_distinctive = []
    matched_ambiguous = []
    matched_opposite = []
    
    for kw in keywords:
        kw_class = classify_keyword(kw, event_conflict)
        if kw_class == KeywordClass.OPPOSITE_CONFLICT:
            if _word_boundary_match(kw, text):
                matched_opposite.append(kw)
        elif kw_class == KeywordClass.DISTINCTIVE:
            if _word_boundary_match(kw, text):
                matched_distinctive.append(kw)
                f.discriminators.append(f"keyword:{kw}")
                if _word_boundary_match(kw, source_row.get("titolo", "")):
                    f.discriminators.append(f"keyword_in_title:{kw}")
        elif kw_class == KeywordClass.AMBIGUOUS:
            if _word_boundary_match(kw, text):
                matched_ambiguous.append(kw)
    
    # Also check aliases (skip ambiguous ones)
    for alias in aliases:
        if len(alias) < 4:
            continue
        alias_class = classify_keyword(alias, event_conflict)
        if alias_class == KeywordClass.DISTINCTIVE:
            if _word_boundary_match(alias, text):
                matched_distinctive.append(alias)
                f.discriminators.append(f"alias:{alias}")
        elif alias_class == KeywordClass.OPPOSITE_CONFLICT:
            if _word_boundary_match(alias, text):
                matched_opposite.append(alias)
    
    if matched_opposite:
        cf.ww1_ww2_mismatch = True
        f.conflict_markers_matched = matched_opposite
    
    # ─── Mixed era detection ─────────────────────────────────────────────
    if same_era_markers and ambiguous_markers and not conflict_markers:
        cf.mixed_era_source = True
    
    # ─── Ambiguous-only detection ────────────────────────────────────────
    if matched_ambiguous and not matched_distinctive and not conflict_markers:
        cf.ambiguous_keywords_only = True
    
    # ─── No discriminators at all ────────────────────────────────────────
    if not f.discriminators:
        cf.omonimia_no_discriminator = True
    
    # Store matched terms for provenance
    f.matched_terms = {
        "distinctive": matched_distinctive,
        "ambiguous": matched_ambiguous,
        "opposite": matched_opposite,
        "same_era_markers": same_era_markers,
        "conflict_markers": conflict_markers,
    }
    
    return f, cf


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _phonetic_match(a: str, b: str) -> bool:
    """Check if two names are phonetically similar (simple heuristic)."""
    if not a or not b:
        return False
    # Same first 3 chars after normalization
    return a[:3] == b[:3]


def _place_match(a: str, b: str) -> bool:
    """Check if two place names match (normalized, case-insensitive, word-boundary)."""
    if not a or not b:
        return False
    a_norm = a.lower().strip()
    b_norm = b.lower().strip()
    if a_norm == b_norm:
        return True
    # Word-boundary containment (at least 5 chars) — prevents "Milano" matching "Milano Marittima" as exact
    if len(a_norm) >= 5 and _word_boundary_match(a_norm, b_norm):
        return True
    if len(b_norm) >= 5 and _word_boundary_match(b_norm, a_norm):
        return True
    return False


def _word_boundary_match(keyword: str, text: str) -> bool:
    """
    Match keyword with word boundaries, not substring.
    Case-insensitive, Unicode-aware.
    """
    if not keyword or not text:
        return False
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE | re.UNICODE))


def _infer_person_conflict(person: dict) -> str:
    """Infer whether a person is WW1 or WW2 based on available dates."""
    birth = person.get("data_nascita", "")
    death = person.get("data_morte") or person.get("data_decesso") or ""
    capture = person.get("data_cattura", "")
    
    for date_str in [capture, death, birth]:
        if date_str:
            try:
                year = int(str(date_str)[:4])
                if 1914 <= year <= 1919:
                    return "ww1"
                if 1939 <= year <= 1945:
                    return "ww2"
            except (ValueError, IndexError):
                pass
    
    return ""
