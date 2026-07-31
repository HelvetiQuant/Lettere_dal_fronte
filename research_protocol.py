"""Research Protocol — motore di ricerca storico-archivistica digitale.

Implementa il protocollo completo di ricerca militare integrando:
- person_finder.py (DB locali + 27 provider federati)
- ai_runtime.py (Qwen/LMStudio per normalizzazione e dossier)
- linking/ (entity resolution, scoring, homonym matrix)
- Supabase (persistenza evidence.claims, core.entities)

Usage:
    from research_protocol import research_person
    dossier = research_person({"cognome": "Siracusa", "nome": "Francesco", "anno_nascita": "1886", "luogo_nascita": "Messina"})
"""
from __future__ import annotations

import json, logging, re, sqlite3, os, threading, hashlib, uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SearchInput:
    nome: str = ""
    cognome: str = ""
    secondi_nomi: List[str] = field(default_factory=list)
    varianti_nome: List[str] = field(default_factory=list)
    varianti_cognome: List[str] = field(default_factory=list)
    soprannome: str = ""
    data_nascita: str = ""
    anno_nascita: str = ""
    luogo_nascita: str = ""
    provincia_nascita: str = ""
    paese_nascita: str = ""
    paternita: str = ""
    maternita: str = ""
    coniuge: str = ""
    residenza: str = ""
    professione: str = ""
    grado: str = ""
    arma: str = ""
    reparto: str = ""
    battaglione: str = ""
    compagnia: str = ""
    distretto_militare: str = ""
    numero_matricola: str = ""
    numero_prigioniero: str = ""
    conflitto_presunto: str = ""
    periodo_presunto: str = ""
    luogo_evento: str = ""
    stato_presunto: str = ""
    informazioni_familiari: str = ""
    documenti_iniziali: List[str] = field(default_factory=list)
    note_utente: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "SearchInput":
        f = {k: d.get(k, "") for k in cls.__dataclass_fields__}
        return cls(**f)

    @property
    def full_name(self) -> str:
        return f"{self.cognome} {self.nome}".strip()

    @property
    def has_identifiers(self) -> bool:
        return bool(self.cognome or self.nome or self.numero_matricola)


@dataclass
class NameVariant:
    text: str
    variant_type: str  # original, reversed, initial, ocr, transliteration, historical
    source: str = "auto"


@dataclass
class SourceRecord:
    url: str = ""
    dominio: str = ""
    istituzione: str = ""
    data_accesso: str = ""
    connection_type: str = ""  # SEARCH_DISCOVERY, DIRECT_HTML_GET, OFFICIAL_API, etc.
    metodo_individuazione: str = ""  # SEARCH_QUERY, DOMAIN_QUERY, API_SEARCH, etc.
    query: str = ""
    parametri: dict = field(default_factory=dict)
    metodo_http: str = ""
    codice_http: int = 0
    formato: str = ""
    autenticazione: bool = False
    limitazioni: str = ""
    condizioni_uso: str = ""
    licenza: str = ""
    identificativo_archivistico: str = ""
    source_level: str = ""  # A, B, C, D
    esito: str = ""  # positive, negative, blocked, ambiguous
    note: str = ""


@dataclass
class Candidate:
    nome_originale: str = ""
    nome_normalizzato: str = ""
    data_nascita: str = ""
    luogo_nascita: str = ""
    paternita: str = ""
    maternita: str = ""
    residenza: str = ""
    professione: str = ""
    matricola: str = ""
    distretto: str = ""
    reparto: str = ""
    grado: str = ""
    periodo: str = ""
    prigionia: str = ""
    morte: str = ""
    sepoltura: str = ""
    fonti: List[SourceRecord] = field(default_factory=list)
    compatibilita: List[str] = field(default_factory=list)
    contraddizioni: List[str] = field(default_factory=list)
    stato: str = "INSUFFICIENT_DATA"  # CONFIRMED, PROBABLE, POSSIBLE, INSUFFICIENT_DATA, EXCLUDED
    raw_data: dict = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class HistoricalLink:
    source_entity_id: str = ""
    target_entity_id: str = ""
    relation_type: str = ""  # SAME_IDENTITY_CONFIRMED, HOMONYM_POSSIBLE, etc.
    start_date: str = ""
    end_date: str = ""
    source_id: str = ""
    evidence_text: str = ""
    confidence: str = "low"  # confirmed, high, medium, low
    reasoning: str = ""
    contrary_evidence: List[str] = field(default_factory=list)


@dataclass
class SearchLogEntry:
    query_id: str = ""
    timestamp: str = ""
    subject_id: str = ""
    query: str = ""
    motore_o_archivio: str = ""
    filtri: dict = field(default_factory=dict)
    connection_type: str = ""
    risultati_trovati: int = 0
    risultati_aperti: List[str] = field(default_factory=list)
    esito: str = ""  # positive, negative, blocked, ambiguous
    note: str = ""


@dataclass
class Dossier:
    # A. Stato identificazione
    stato_identificazione: str = "non_identificata"  # confermata, probabile, possibile, non_identificata, dati_insufficienti
    # B. Profilo sintetico
    profilo: dict = field(default_factory=dict)
    # C. Matrice candidati
    candidati: List[Candidate] = field(default_factory=list)
    # D. Cronologia documentata
    cronologia: List[dict] = field(default_factory=list)
    # E. Percorso militare
    percorso_militare: dict = field(default_factory=dict)
    # F. Fonti consultate
    fonti: List[SourceRecord] = field(default_factory=list)
    # G. Documenti individuati
    documenti: List[dict] = field(default_factory=list)
    # H. Contraddizioni
    contraddizioni: List[dict] = field(default_factory=list)
    # I. Omonimi esclusi
    omonimi_esclusi: List[Candidate] = field(default_factory=list)
    # L. Ricerche negative
    ricerche_negative: List[SearchLogEntry] = field(default_factory=list)
    # M. Piste successive
    piste: List[dict] = field(default_factory=list)
    # N. Richieste archivistiche
    richieste: List[dict] = field(default_factory=list)
    # Variants generated
    varianti: List[NameVariant] = field(default_factory=list)
    # Search log
    search_log: List[SearchLogEntry] = field(default_factory=list)
    # AI metadata
    ai_used: bool = False
    ai_model: str = ""
    # Web search fallback
    web_search_used: bool = False
    web_search_results: dict = field(default_factory=dict)
    # Discovery persistence
    discovery_persistence: dict = field(default_factory=dict)
    # Timestamps
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ════════════════════════════════════════════════════════════════════════════
# STRUCTURAL FIX: ResearchTarget, separated states, deterministic gates
# ════════════════════════════════════════════════════════════════════════════

class LocalMatchState(Enum):
    NOT_SEARCHED = "NOT_SEARCHED"
    NOT_FOUND = "NOT_FOUND"
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    CONFLICT = "CONFLICT"


class ExternalValidationState(Enum):
    NOT_RUN = "NOT_RUN"
    NO_EVIDENCE = "NO_EVIDENCE"
    CORROBORATED = "CORROBORATED"
    CONFIRMED = "CONFIRMED"
    CONFLICTING = "CONFLICTING"
    ERROR = "ERROR"


class ResolutionState(Enum):
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    PROBABLE = "PROBABLE"
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED_WRONG_IDENTITY = "REJECTED_WRONG_IDENTITY"


class RunState(Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ObjectKind(Enum):
    PROVIDER_ATTEMPT = "PROVIDER_ATTEMPT"
    SEARCH_QUERY = "SEARCH_QUERY"
    SEARCH_RESULT_LEAD = "SEARCH_RESULT_LEAD"
    HOMEPAGE = "HOMEPAGE"
    SEARCH_PAGE = "SEARCH_PAGE"
    CATALOG_RECORD = "CATALOG_RECORD"
    DIGITIZED_DOCUMENT = "DIGITIZED_DOCUMENT"
    TRANSCRIPTION = "TRANSCRIPTION"
    SECONDARY_SOURCE = "SECONDARY_SOURCE"


class EvidenceState(Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNFETCHED_LEAD = "UNFETCHED_LEAD"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class ResearchTarget:
    """Immutable research target. Created once per search, never modified."""
    target_id: str
    target_type: str
    raw_input: dict
    normalized_name: str
    birth_date_or_year: str
    birth_place: str
    parents: str
    military_unit: str
    rank: str
    death_date_or_year: str
    death_place: str
    conflict: str
    origin_dataset: str
    origin_record_id: str
    origin_source_lineage_id: str
    validation_mode: str
    target_hash: str

    @classmethod
    def from_search_input(cls, si: SearchInput, origin_dataset: str = "",
                          origin_record_id: str = "") -> "ResearchTarget":
        import unicodedata
        def _norm(s: str) -> str:
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s.lower().strip()

        normalized = f"{_norm(si.cognome)} {_norm(si.nome)}".strip()
        canonical_parts = [
            normalized,
            _norm(si.anno_nascita or si.data_nascita),
            _norm(si.luogo_nascita),
            _norm(si.paternita),
            _norm(si.reparto),
            _norm(si.grado),
            _norm(si.conflitto_presunto),
        ]
        canonical = "|".join(canonical_parts)
        target_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        target_id = f"target_{target_hash}"

        return cls(
            target_id=target_id,
            target_type="person",
            raw_input=asdict(si) if hasattr(si, '__dataclass_fields__') else {},
            normalized_name=normalized,
            birth_date_or_year=si.anno_nascita or si.data_nascita,
            birth_place=si.luogo_nascita,
            parents=si.paternita,
            military_unit=si.reparto,
            rank=si.grado,
            death_date_or_year="",
            death_place="",
            conflict=si.conflitto_presunto,
            origin_dataset=origin_dataset,
            origin_record_id=origin_record_id,
            origin_source_lineage_id=f"{origin_dataset}:{origin_record_id}" if origin_dataset else "",
            validation_mode="blind_external_validation",
            target_hash=target_hash,
        )


def check_subject_drift(target: ResearchTarget, ai_response: dict) -> bool:
    """Check if AI response has a different target_hash (subject drift)."""
    resp_hash = ai_response.get("target_hash", "")
    if resp_hash and resp_hash != target.target_hash:
        log.warning("SUBJECT_DRIFT: target_hash=%s but AI response hash=%s",
                    target.target_hash, resp_hash)
        return True
    return False


@dataclass
class ResolutionResult:
    """Result of identity resolution with separated states."""
    local_match_state: LocalMatchState = LocalMatchState.NOT_SEARCHED
    external_validation_state: ExternalValidationState = ExternalValidationState.NOT_RUN
    resolution_state: ResolutionState = ResolutionState.UNRESOLVED
    run_state: RunState = RunState.PARTIAL
    reason_codes: List[str] = field(default_factory=list)
    matched_features: List[str] = field(default_factory=list)
    conflicting_features: List[str] = field(default_factory=list)
    missing_features: List[str] = field(default_factory=list)


@dataclass
class AIError:
    """Observable AI error with code, stage, and context."""
    stage: str = ""
    error_code: str = ""
    exception_type: str = ""
    safe_message: str = ""
    provider: str = ""
    model: str = ""
    request_id: str = ""
    attempt: int = 1
    retryable: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def format_ai_error(err: AIError) -> str:
    """Format AI error for display — never empty parentheses."""
    return f"❌ ({err.error_code}: {err.stage})"


# ─── Hard conflict detection ─────────────────────────────────────────────────

def _norm_val(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _extract_year(s: str) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", str(s))
    return m.group(1) if m else None


def _norm_place(s: str) -> str:
    s = _norm_val(s)
    s = re.sub(r"\bcomune\s+di\s+", "", s)
    s = re.sub(r"\bprovincia\s+di\s+", "", s)
    s = re.sub(r"\bsull['\s]\w+", "", s)  # "sull'Oglio" etc.
    return s.strip()


def _norm_unit(s: str) -> str:
    s = _norm_val(s)
    s = re.sub(r"\breggimento\b", "rgt", s)
    s = re.sub(r"\bfanteria\b", "fan", s)
    s = re.sub(r"\bbatteria\b", "bat", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def check_hard_conflicts(candidate: Candidate, si: SearchInput) -> List[str]:
    """Detect hard conflicts that reject a candidate before positive scoring."""
    conflicts = []

    # Birth year conflict
    si_year = _extract_year(si.anno_nascita or si.data_nascita)
    cand_year = _extract_year(candidate.data_nascita)
    if si_year and cand_year and si_year != cand_year:
        conflicts.append(f"BIRTH_YEAR_CONFLICT: input={si_year} vs candidate={cand_year}")

    # Birth place conflict (normalized, not substring)
    si_place = _norm_place(si.luogo_nascita)
    cand_place = _norm_place(candidate.luogo_nascita)
    if si_place and cand_place and si_place != cand_place:
        if si_place not in cand_place and cand_place not in si_place:
            conflicts.append(f"BIRTH_PLACE_CONFLICT: input={si.luogo_nascita} vs candidate={candidate.luogo_nascita}")

    # Military unit conflict (only if both explicit and clearly different)
    si_unit = _norm_unit(si.reparto)
    cand_unit = _norm_unit(candidate.reparto)
    if si_unit and cand_unit:
        si_nums = set(re.findall(r"\d+", si_unit))
        cand_nums = set(re.findall(r"\d+", cand_unit))
        if si_nums and cand_nums and si_nums != cand_nums:
            conflicts.append(f"UNIT_CONFLICT: input={si.reparto} vs candidate={candidate.reparto}")

    return conflicts


# ─── Deterministic resolution gate ───────────────────────────────────────────

def apply_resolution_gate(
    candidate: Candidate,
    accepted_evidence_count: int = 0,
    independent_lineages: int = 0,
    hard_conflicts: List[str] = None,
    ai_synthesis_failed: bool = False,
) -> ResolutionResult:
    """Apply deterministic gates to determine resolution state.

    The number of candidates and retrieval score cannot confirm identity.
    Only accepted independent evidence can.
    """
    hard_conflicts = hard_conflicts or []
    result = ResolutionResult()

    # Hard conflicts → REJECTED_WRONG_IDENTITY
    if hard_conflicts:
        result.resolution_state = ResolutionState.REJECTED_WRONG_IDENTITY
        result.conflicting_features = hard_conflicts
        result.reason_codes = [fc.split(":")[0] for fc in hard_conflicts]
        result.run_state = RunState.PARTIAL
        return result

    # INSUFFICIENT_DATA cannot promote
    if candidate.stato == "INSUFFICIENT_DATA":
        result.resolution_state = ResolutionState.UNRESOLVED
        result.reason_codes = ["INSUFFICIENT_DATA_NO_PROMOTION"]
        result.external_validation_state = ExternalValidationState.NO_EVIDENCE
        return result

    # Zero accepted evidence → NO_EVIDENCE, not CONFIRMED/PROBABLE
    if accepted_evidence_count == 0:
        result.external_validation_state = ExternalValidationState.NO_EVIDENCE
        result.resolution_state = ResolutionState.UNRESOLVED
        result.reason_codes = ["NO_ACCEPTED_INDEPENDENT_EVIDENCE"]
        if ai_synthesis_failed:
            result.run_state = RunState.PARTIAL
            result.reason_codes.append("AI_SYNTHESIS_FAILED_NO_FALLBACK")
        return result

    # AI synthesis failure does not produce fallback positive
    if ai_synthesis_failed:
        result.run_state = RunState.PARTIAL
        result.reason_codes.append("AI_SYNTHESIS_FAILED")
        # Keep deterministic state from evidence, don't promote from AI
        if accepted_evidence_count == 0:
            result.resolution_state = ResolutionState.UNRESOLVED
            return result

    # Evidence-based promotion
    if independent_lineages >= 2 and accepted_evidence_count >= 2:
        result.external_validation_state = ExternalValidationState.CONFIRMED
        result.resolution_state = ResolutionState.CONFIRMED
        result.reason_codes = ["TWO_INDEPENDENT_SOURCES"]
    elif accepted_evidence_count >= 1 and independent_lineages >= 1:
        result.external_validation_state = ExternalValidationState.CORROBORATED
        result.resolution_state = ResolutionState.PROBABLE
        result.reason_codes = ["ONE_ACCEPTED_EVIDENCE"]
    else:
        result.external_validation_state = ExternalValidationState.NO_EVIDENCE
        result.resolution_state = ResolutionState.UNRESOLVED
        result.reason_codes = ["INSUFFICIENT_EVIDENCE"]

    return result


# ─── Source classification ────────────────────────────────────────────────────

def classify_object_kind(url: str, content_type: str = "",
                          has_record_id: bool = False,
                          has_locator: bool = False) -> ObjectKind:
    """Classify a URL/result into object_kind."""
    if not url:
        return ObjectKind.SEARCH_QUERY

    url_lower = url.lower()

    # Homepage detection
    homepage_patterns = [
        r"/pagine/", r"/default\.aspx$", r"/index\.(html|php|aspx)$",
        r"/$", r"/home", r"/about",
    ]
    if any(re.search(p, url_lower) for p in homepage_patterns):
        if not has_record_id:
            return ObjectKind.HOMEPAGE

    # Search page detection
    search_patterns = [
        r"/search", r"/File/Search", r"\?q=", r"#person\|",
        r"search\.aspx", r"/ricerca", r"/find",
    ]
    if any(re.search(p, url_lower) for p in search_patterns):
        if not has_record_id:
            return ObjectKind.SEARCH_PAGE

    # Direct record with ID and locator
    if has_record_id and has_locator:
        return ObjectKind.CATALOG_RECORD

    # Has record ID but no locator
    if has_record_id:
        return ObjectKind.SEARCH_RESULT_LEAD

    # Digitized document
    if any(ext in url_lower for ext in [".pdf", ".jpg", ".png", ".tiff", "/document/", "/image/"]):
        return ObjectKind.DIGITIZED_DOCUMENT

    # Default: search result lead
    return ObjectKind.SEARCH_RESULT_LEAD


def is_evidence_eligible(kind: ObjectKind) -> bool:
    """Check if an object kind is eligible as probative evidence."""
    eligible = {ObjectKind.CATALOG_RECORD, ObjectKind.DIGITIZED_DOCUMENT,
                ObjectKind.TRANSCRIPTION}
    return kind in eligible


# ─── Typed counts ────────────────────────────────────────────────────────────

def compute_typed_counts(
    active_candidates: List[Candidate],
    excluded_candidates: List[Candidate],
) -> Dict[str, int]:
    """Compute typed counts replacing the ambiguous 'fonti_totali'."""
    counts = {
        "provider_attempts": 0,
        "retrieved_items": 0,
        "person_candidates": len(active_candidates),
        "rejected_person_candidates": len(excluded_candidates),
        "search_leads": 0,
        "source_records": 0,
        "accepted_evidence_sources": 0,
        "independent_evidence_lineages": 0,
        "supported_claims": 0,
    }

    for c in active_candidates + excluded_candidates:
        for src in c.fonti:
            counts["retrieved_items"] += 1
            kind = classify_object_kind(src.url, has_record_id=bool(src.identificativo_archivistico))
            if kind in (ObjectKind.HOMEPAGE, ObjectKind.SEARCH_PAGE, ObjectKind.SEARCH_QUERY):
                counts["search_leads"] += 1
            elif is_evidence_eligible(kind):
                counts["source_records"] += 1
                counts["accepted_evidence_sources"] += 1

    return counts


# ─── Name matching (no substring) ────────────────────────────────────────────

def normalize_name_preserve_particles(name: str) -> str:
    """Normalize name preserving particles (DI, DE, etc.)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def names_match(name1: str, name2: str) -> bool:
    """Check if two names match using word boundary, not substring."""
    n1 = normalize_name_preserve_particles(name1)
    n2 = normalize_name_preserve_particles(name2)
    if n1 == n2:
        return True
    # Word boundary check: all words in shorter must be in longer
    w1 = set(n1.split())
    w2 = set(n2.split())
    if not w1 or not w2:
        return False
    # "lana" should not match "castellana" — shorter set must be subset
    shorter = w1 if len(w1) <= len(w2) else w2
    longer = w2 if len(w1) <= len(w2) else w1
    return shorter.issubset(longer) and shorter != longer


# ─── Phase 4: Name normalization ─────────────────────────────────────────────

def generate_variants(si: SearchInput) -> List[NameVariant]:
    """Generate all reasonable name variants per protocol section 4."""
    variants: List[NameVariant] = []
    nome = si.nome.strip()
    cognome = si.cognome.strip()
    if not nome and not cognome:
        return variants

    # Original
    variants.append(NameVariant(f"{nome} {cognome}".strip(), "original"))
    # Reversed
    variants.append(NameVariant(f"{cognome} {nome}".strip(), "reversed"))

    # Initials
    if nome:
        initial = nome[0] + "."
        variants.append(NameVariant(f"{initial} {cognome}", "initial"))
        variants.append(NameVariant(f"{cognome} {initial}", "initial"))
    if cognome:
        initial_c = cognome[0] + "."
        variants.append(NameVariant(f"{nome} {initial_c}", "initial"))

    # Second names
    for sn in si.secondi_nomi:
        variants.append(NameVariant(f"{nome} {sn} {cognome}", "second_name"))
        variants.append(NameVariant(f"{sn} {cognome}", "second_name"))

    # User-provided variants
    for v in si.varianti_nome:
        variants.append(NameVariant(f"{v} {cognome}", "user_variant"))
    for v in si.varianti_cognome:
        variants.append(NameVariant(f"{nome} {v}", "user_variant"))

    # OCR plausible errors (common Italian OCR mistakes)
    ocr_map = {"i": "l", "l": "i", "u": "n", "n": "u", "e": "c", "c": "e", "o": "0", "s": "f"}
    for bad, good in ocr_map.items():
        if bad in cognome and cognome.replace(bad, good) != cognome:
            variants.append(NameVariant(f"{nome} {cognome.replace(bad, good)}", "ocr"))
        if bad in nome and nome.replace(bad, good) != nome:
            variants.append(NameVariant(f"{nome.replace(bad, good)} {cognome}", "ocr"))

    # Accents removed
    import unicodedata
    nome_noacc = "".join(c for c in unicodedata.normalize("NFD", nome) if unicodedata.category(c) != "Mn")
    cognome_noacc = "".join(c for c in unicodedata.normalize("NFD", cognome) if unicodedata.category(c) != "Mn")
    if nome_noacc != nome:
        variants.append(NameVariant(f"{nome_noacc} {cognome}", "no_accent"))
    if cognome_noacc != cognome:
        variants.append(NameVariant(f"{nome} {cognome_noacc}", "no_accent"))

    # Soprannome
    if si.soprannome:
        variants.append(NameVariant(f"{si.soprannome} {cognome}", "soprannome"))

    # Deduplicate
    seen = set()
    unique = []
    for v in variants:
        key = v.text.lower().strip()
        if key not in seen and key:
            seen.add(key)
            unique.append(v)
    return unique


# ─── Phase 5: Progressive search strategy ─────────────────────────────────────

def _build_query_matrix(si: SearchInput, variants: List[NameVariant]) -> List[dict]:
    """Build progressive query matrix: Level 1 (exact) → 2 (identifiers) → 3 (variants) → 4 (domain)."""
    queries = []
    base_names = [v.text for v in variants[:6]]  # limit

    # Level 1: exact match
    keywords = ["militare", "soldato", "guerra", "caduto", "disperso", "prigioniero", "internato", "deportato", "reparto", "matricola"]
    for name in base_names[:3]:
        queries.append({"level": 1, "query": name, "type": "exact"})
        for kw in keywords:
            queries.append({"level": 1, "query": f"{name} {kw}", "type": "keyword"})

    # Level 2: identifiers
    identifiers = []
    if si.luogo_nascita:
        identifiers.append(("luogo", si.luogo_nascita))
    if si.anno_nascita:
        identifiers.append(("anno", si.anno_nascita))
    if si.paternita:
        identifiers.append(("paternita", f"di {si.paternita}"))
    if si.residenza:
        identifiers.append(("residenza", si.residenza))
    if si.reparto:
        identifiers.append(("reparto", si.reparto))
    if si.grado:
        identifiers.append(("grado", si.grado))
    if si.distretto_militare:
        identifiers.append(("distretto", si.distretto_militare))

    for name in base_names[:3]:
        for label, val in identifiers:
            queries.append({"level": 2, "query": f'{name} "{val}"', "type": f"with_{label}"})

    # Level 3: variants
    for v in variants[3:]:
        queries.append({"level": 3, "query": v.text, "type": v.variant_type})
        for label, val in identifiers[:3]:
            queries.append({"level": 3, "query": f'{v.text} "{val}"', "type": f"variant_{label}"})

    # Level 4: domain-specific
    domains = [
        "difesa.it", "esercito.difesa.it", "marina.difesa.it", "aeronautica.difesa.it",
        "cultura.gov.it", "antenati.cultura.gov.it",
        "collections.arolsen-archives.org", "grandeguerre.icrc.org",
        "bundesarchiv.de", "archives.gov", "discovery.nationalarchives.gov.uk",
        "commonwealthwargraves.org", "onoreaicaduti.it", "pietredellamemoria.it",
        "lessicobiograficoimi.it", "familysearch.org",
    ]
    primary_name = base_names[0] if base_names else ""
    for dom in domains:
        queries.append({"level": 4, "query": f'site:{dom} "{primary_name}"', "type": "domain"})

    return queries


# ─── Source classification ────────────────────────────────────────────────────

SOURCE_LEVEL_MAP = {
    # Level A — primary
    "fogli_matricolari": "A", "ruoli_matricolari": "A", "liste_leva": "A",
    "diari_storici": "A", "registri_reparto": "A", "schede_personali": "A",
    "registri_prigionia": "A", "atti_nascita": "A", "atti_morte": "A",
    "registri_cimiteriali": "A", "fascicoli_personali": "A",
    # Level B — institutional
    "ministero_difesa": "B", "archivio_stato": "B", "archivio_militare": "B",
    "icrc": "B", "arolsen": "B", "bundesarchiv": "B", "nara": "B",
    "national_archives": "B", "cwgc": "B", "lebi_anrp": "B",
    # Level C — scientific
    "albo_oro_trascrizione": "C", "banche_dati_commemorative": "C",
    "pubblicazioni_accademiche": "C", "musei": "C",
    # Level D — indicative
    "genealogici": "D", "forum": "D", "social": "D", "blog": "D",
}

def classify_source(provider_name: str, url: str = "") -> str:
    """Classify source level A/B/C/D."""
    key = provider_name.lower()
    for k, level in SOURCE_LEVEL_MAP.items():
        if k in key:
            return level
    if url:
        for k, level in SOURCE_LEVEL_MAP.items():
            if k in url.lower():
                return level
    return "D"


def classify_connection(provider_name: str, has_api: bool = False, url: str = "") -> str:
    """Classify connection type per protocol section 8."""
    if has_api or provider_name in ("icrc_ww1", "lebi", "europeana", "nara", "wikitree"):
        return "OFFICIAL_API"
    if url and url.endswith(".pdf"):
        return "DIRECT_PDF_GET"
    if url:
        return "DIRECT_HTML_GET"
    return "SEARCH_DISCOVERY"


# ─── Identifier strength scoring ──────────────────────────────────────────────

STRONG_IDENTIFIERS = ["data_nascita", "luogo_nascita", "paternita", "maternita", "numero_matricola", "numero_prigioniero"]
MEDIUM_IDENTIFIERS = ["anno_nascita", "distretto_militare", "reparto", "grado", "professione", "coniuge", "residenza"]
WEAK_IDENTIFIERS = ["nome", "cognome", "provincia_nascita"]

def score_candidate(candidate: Candidate, si: SearchInput) -> str:
    """Score candidate against input per protocol section 12.

    FIX: Hard conflicts are checked BEFORE any positive scoring.
    A candidate with incompatible birth year/place/unit is rejected
    before it can be promoted to CONFIRMED/PROBABLE.
    """
    # ── Hard conflict gate (before any positive scoring) ──
    hard_conflicts = check_hard_conflicts(candidate, si)
    if hard_conflicts:
        candidate.stato = "EXCLUDED"
        candidate.contraddizioni = hard_conflicts
        candidate.compatibilita = []
        return candidate.stato

    strong_matches = 0
    medium_matches = 0
    contradictions = []

    # Strong identifiers — use normalized comparison, not substring
    si_year = _extract_year(si.anno_nascita or si.data_nascita)
    cand_year = _extract_year(candidate.data_nascita)
    if si_year and cand_year:
        if si_year == cand_year:
            strong_matches += 1
        else:
            contradictions.append(f"BIRTH_YEAR_CONFLICT: input={si_year} vs candidate={cand_year}")

    si_place = _norm_place(si.luogo_nascita)
    cand_place = _norm_place(candidate.luogo_nascita)
    if si_place and cand_place:
        if si_place == cand_place or si_place in cand_place or cand_place in si_place:
            strong_matches += 1
        else:
            contradictions.append(f"BIRTH_PLACE_CONFLICT: input={si.luogo_nascita} vs candidate={candidate.luogo_nascita}")

    if si.paternita and candidate.paternita and _norm_val(si.paternita) == _norm_val(candidate.paternita):
        strong_matches += 1
    elif si.paternita and candidate.paternita and _norm_val(si.paternita) != _norm_val(candidate.paternita):
        contradictions.append(f"PATERNITA_CONFLICT: input={si.paternita} vs candidate={candidate.paternita}")

    if si.numero_matricola and candidate.matricola and si.numero_matricola == candidate.matricola:
        strong_matches += 1

    # Medium identifiers
    for field_name in MEDIUM_IDENTIFIERS:
        input_val = getattr(si, field_name, "")
        cand_val = getattr(candidate, field_name.replace("numero_matricola", "matricola"), "")
        if not cand_val:
            alt_map = {"anno_nascita": "data_nascita", "distretto_militare": "distretto", "reparto": "reparto", "grado": "grado"}
            cand_val = getattr(candidate, alt_map.get(field_name, field_name), "")
        if input_val and cand_val and _norm_val(str(input_val)) in _norm_val(str(cand_val)):
            medium_matches += 1

    candidate.compatibilita = [f"strong_matches={strong_matches}", f"medium_matches={medium_matches}"]
    candidate.contraddizioni = contradictions

    # Decision: hard conflicts already handled above.
    # Without accepted independent evidence, candidate stays at retrieval-level state.
    # CONFIRMED/PROBABLE require evidence, not just field matching.
    if contradictions and not strong_matches:
        candidate.stato = "EXCLUDED"
    elif strong_matches >= 1 and not contradictions:
        candidate.stato = "POSSIBLE"  # Downgraded from CONFIRMED — needs evidence gate
    elif strong_matches >= 1 and contradictions:
        candidate.stato = "POSSIBLE"  # Downgraded from PROBABLE — needs evidence gate
    elif medium_matches >= 3 and not contradictions:
        candidate.stato = "POSSIBLE"  # Downgraded from PROBABLE — needs evidence gate
    elif medium_matches >= 1:
        candidate.stato = "POSSIBLE"
    else:
        has_si_identifiers = any([si.data_nascita, si.luogo_nascita, si.paternita, si.numero_matricola])
        has_candidate_data = any([candidate.data_nascita, candidate.luogo_nascita,
                                  candidate.paternita, candidate.reparto, candidate.grado,
                                  candidate.matricola, candidate.distretto])
        if not has_si_identifiers and has_candidate_data:
            candidate.stato = "POSSIBLE"
        else:
            candidate.stato = "INSUFFICIENT_DATA"

    return candidate.stato


# ─── AI integration (Qwen) ────────────────────────────────────────────────────

def _ai_normalize_variants(si: SearchInput, variants: List[NameVariant]) -> List[NameVariant]:
    """Use Qwen AI to generate additional name variants (historical spellings, transliterations)."""
    try:
        from ai_runtime import get_adapter
        adapter = get_adapter()
        health = adapter.health()
        if not health.healthy:
            log.info("AI not healthy, skipping AI variant generation")
            return variants

        system = """Sei un esperto di onomastica storica italiana. Genera varianti plausibili di un nome/cognome.
Rispondi SOLO in JSON: {"varianti": [{"text": "...", "variant_type": "historical|transliteration|german|french|slavic|latin"}]}
Non inventare varianti fonetiche eccessivamente lontane. Basati su grafie storiche documentate."""
        user = json.dumps({"nome": si.nome, "cognome": si.cognome, "luogo": si.luogo_nascita, "periodo": si.periodo_presunto or si.conflitto_presunto})

        result = adapter.generate_structured(system, user, max_tokens=512, temperature=0.2, task_type="name_normalization", timeout=30)
        if result.ok and result.text:
            data = json.loads(result.text)
            for v in data.get("varianti", []):
                variants.append(NameVariant(text=v.get("text", ""), variant_type=v.get("variant_type", "ai"), source="qwen"))
            log.info("AI generated %d additional variants", len(data.get("varianti", [])))
    except Exception as e:
        log.debug("AI variant generation skipped: %s", e)
    return variants


def _ai_build_dossier(dossier: Dossier, target: ResearchTarget = None) -> Dossier:
    """Use Qwen AI to synthesize the final dossier from collected data.

    FIX: AI cannot override stato_identificazione. AI can only suggest
    piste and richieste_archivistiche. Errors are stored as structured AIError.
    """
    try:
        from ai_runtime import get_adapter
        adapter = get_adapter()
        health = adapter.health()
        if not health.healthy:
            log.info("AI not healthy, skipping AI dossier synthesis")
            dossier.profilo["ai_error"] = asdict(AIError(
                stage="dossier_synthesis", error_code="ADAPTER_UNHEALTHY",
                exception_type="HealthCheckFailed", safe_message="Adapter not healthy",
                provider="lmstudio", model=getattr(health, 'model', 'unknown'),
            ))
            return dossier

        # Prepare summary for AI
        candidates_summary = []
        for c in dossier.candidati[:10]:
            candidates_summary.append({
                "nome": c.nome_originale, "nascita": c.data_nascita, "luogo": c.luogo_nascita,
                "paternita": c.paternita, "reparto": c.reparto, "grado": c.grado,
                "stato": c.stato, "compatibilita": c.compatibilita, "contraddizioni": c.contraddizioni,
            })

        system = """Sei un ricercatore storico-archivistico. Sintetizza un dossier strutturato dai dati di ricerca.
NON inventare dati. NON fondere record omonimi. Distingui fatti da ipotesi.
Lo stato di identificazione è già determinato deterministicamente: NON sovrascriverlo.
Rispondi in JSON con: {
  "piste": [{"priorita": 1, "azione": "", "fonte": "", "motivazione": ""}],
  "richieste_archivistiche": [{"ente": "", "fondo": "", "documento_richiesto": "", "dati_conosciuti": "", "motivazione": ""}]
}"""
        user = json.dumps({
            "target_id": target.target_id if target else "",
            "target_hash": target.target_hash if target else "",
            "input": dossier.profilo.get("input", {}),
            "stato_identificazione": dossier.stato_identificazione,
            "candidati": candidates_summary,
            "typed_counts": dossier.profilo.get("typed_counts", {}),
            "contraddizioni": dossier.contraddizioni[:5],
            "ricerche_negative": len(dossier.ricerche_negative),
        }, ensure_ascii=False)

        result = adapter.generate_structured(system, user, max_tokens=2048, temperature=0.2, task_type="dossier_synthesis", timeout=60)
        if result.ok and result.text:
            data = json.loads(result.text)
            # ── FIX: AI cannot set stato_identificazione ──
            # Only accept piste and richieste from AI
            if data.get("piste"):
                dossier.piste = data["piste"]
            if data.get("richieste_archivistiche"):
                dossier.richieste = data["richieste_archivistiche"]
            dossier.ai_used = True
            dossier.ai_model = health.model
            log.info("AI dossier synthesized (model=%s) — stato NOT overridden", health.model)
        else:
            # ── FIX: Store structured error, never empty parentheses ──
            err = AIError(
                stage="dossier_synthesis",
                error_code="GENERATION_FAILED",
                exception_type=type(result.error).__name__ if hasattr(result, 'error') and result.error else "Unknown",
                safe_message=str(getattr(result, 'error', 'Generation failed'))[:200],
                provider="lmstudio",
                model=getattr(health, 'model', 'unknown'),
                retryable=False,
            )
            dossier.profilo["ai_error"] = asdict(err)
            log.warning("AI dossier synthesis failed: %s", err.error_code)
    except Exception as e:
        # ── FIX: Store structured error ──
        err = AIError(
            stage="dossier_synthesis",
            error_code="EXCEPTION",
            exception_type=type(e).__name__,
            safe_message=str(e)[:200],
            provider="lmstudio",
            model="",
            retryable=False,
        )
        dossier.profilo["ai_error"] = asdict(err)
        log.warning("AI dossier synthesis error: %s: %s", err.error_code, err.safe_message)
    return dossier


# ─── Search execution ─────────────────────────────────────────────────────────

_dossier_lock = threading.Lock()

def _search_local(si: SearchInput, variants: List[NameVariant], dossier: Dossier):
    """Search local SQLite databases."""
    from person_finder import _search_local_sqlite, PersonQuery
    pq = PersonQuery(raw=si.full_name, cognome=si.cognome, nome=si.nome,
                     birth_year=int(si.anno_nascita) if si.anno_nascita.isdigit() else None,
                     birth_place=si.luogo_nascita, conflict=si.conflitto_presunto)
    matches = _search_local_sqlite(pq)
    with _dossier_lock:
        for m in matches:
            rd = m.raw_data or {}
            c = Candidate(
                nome_originale=m.name, nome_normalizzato=m.name,
                data_nascita=str(m.birth_year or rd.get("classe") or rd.get("anno_nascita") or rd.get("data_nascita") or ""),
                luogo_nascita=m.birth_place or rd.get("luogo_nascita") or rd.get("comune_nascita") or rd.get("comune_attuale") or "",
                paternita=rd.get("paternita") or rd.get("nominativo_paternita") or "",
                maternita=rd.get("maternita") or "",
                residenza=rd.get("residenza") or rd.get("comune_residenza") or rd.get("luogo_dimora") or "",
                professione=rd.get("professione") or "",
                matricola=rd.get("matricola") or rd.get("numero_matricola") or "",
                distretto=rd.get("distretto") or rd.get("distretto_militare") or "",
                reparto=m.military_unit or rd.get("reparto") or "",
                grado=m.rank or rd.get("grado") or "",
                morte=m.fate or rd.get("causa_morte") or "",
                prigionia=rd.get("luogo_internamento") or rd.get("luogo_cattura") or "",
                sepoltura=rd.get("cimitero") or rd.get("luogo_sepoltura") or rd.get("paese_cimitero") or "",
                stato="POSSIBLE", raw_data=rd, confidence=m.confidence,
            )
            c.fonti.append(SourceRecord(
                url=m.url, istituzione=f"SQLite:{m.source_detail}",
                connection_type="DIRECT_HTML_GET", metodo_individuazione="FORM_SEARCH",
                source_level=classify_source(m.source_detail), esito="positive",
                data_accesso=datetime.now().isoformat(),
            ))
            score_candidate(c, si)
            dossier.candidati.append(c)
        dossier.search_log.append(SearchLogEntry(
            query_id=f"local_{datetime.now().strftime('%H%M%S')}", timestamp=datetime.now().isoformat(),
            query=si.full_name, motore_o_archivio="SQLite_local", connection_type="DIRECT_HTML_GET",
            risultati_trovati=len(matches), esito="positive" if matches else "negative",
        ))
        if not matches:
            dossier.ricerche_negative.append(dossier.search_log[-1])


def _search_supabase(si: SearchInput, dossier: Dossier):
    """Search Supabase tables."""
    from person_finder import _search_supabase, PersonQuery
    pq = PersonQuery(raw=si.full_name, cognome=si.cognome, nome=si.nome,
                     birth_year=int(si.anno_nascita) if si.anno_nascita.isdigit() else None,
                     birth_place=si.luogo_nascita)
    matches = _search_supabase(pq)
    with _dossier_lock:
        for m in matches:
            rd = m.raw_data or {}
            c = Candidate(
                nome_originale=m.name, nome_normalizzato=m.name,
                data_nascita=str(m.birth_year or rd.get("classe") or rd.get("anno_nascita") or rd.get("data_nascita") or ""),
                luogo_nascita=m.birth_place or rd.get("luogo_nascita") or rd.get("comune_nascita") or rd.get("comune_attuale") or "",
                paternita=rd.get("paternita") or rd.get("nominativo_paternita") or "",
                maternita=rd.get("maternita") or "",
                residenza=rd.get("residenza") or rd.get("comune_residenza") or "",
                matricola=rd.get("matricola") or rd.get("numero_matricola") or "",
                distretto=rd.get("distretto") or rd.get("distretto_militare") or "",
                reparto=m.military_unit or rd.get("reparto") or "",
                grado=m.rank or rd.get("grado") or "",
                morte=m.fate or rd.get("causa_morte") or "",
                prigionia=rd.get("luogo_internamento") or rd.get("luogo_cattura") or "",
                stato="POSSIBLE", raw_data=rd, confidence=m.confidence,
            )
            c.fonti.append(SourceRecord(
                url=m.url, istituzione=f"Supabase:{m.source_detail}",
                connection_type="PUBLIC_JSON_LOOKUP", metodo_individuazione="API_SEARCH",
                source_level="B", esito="positive",
                data_accesso=datetime.now().isoformat(),
            ))
            score_candidate(c, si)
            dossier.candidati.append(c)
        dossier.search_log.append(SearchLogEntry(
            query_id=f"supa_{datetime.now().strftime('%H%M%S')}", timestamp=datetime.now().isoformat(),
            query=si.full_name, motore_o_archivio="Supabase", connection_type="PUBLIC_JSON_LOOKUP",
            risultati_trovati=len(matches), esito="positive" if matches else "negative",
        ))
        if not matches:
            dossier.ricerche_negative.append(dossier.search_log[-1])


def _search_federated(si: SearchInput, variants: List[NameVariant], dossier: Dossier):
    """Search all 27 federated providers."""
    from person_finder import _search_federated, PersonQuery
    pq = PersonQuery(raw=si.full_name, cognome=si.cognome, nome=si.nome,
                     birth_year=int(si.anno_nascita) if si.anno_nascita.isdigit() else None,
                     birth_place=si.luogo_nascita, conflict=si.conflitto_presunto)
    matches = _search_federated(pq)
    with _dossier_lock:
        for m in matches:
            rd = m.raw_data or {}
            c = Candidate(
                nome_originale=m.name, nome_normalizzato=m.name,
                data_nascita=str(m.birth_year or rd.get("classe") or rd.get("anno_nascita") or rd.get("data_nascita") or ""),
                luogo_nascita=m.birth_place or rd.get("luogo_nascita") or rd.get("comune_nascita") or rd.get("comune_attuale") or "",
                paternita=rd.get("paternita") or rd.get("nominativo_paternita") or rd.get("father_name") or "",
                maternita=rd.get("maternita") or rd.get("mother_name") or "",
                residenza=rd.get("residenza") or rd.get("comune_residenza") or "",
                matricola=rd.get("matricola") or rd.get("numero_matricola") or rd.get("prisoner_number") or "",
                distretto=rd.get("distretto") or rd.get("distretto_militare") or "",
                reparto=m.military_unit or rd.get("reparto") or rd.get("regiment") or rd.get("unit") or "",
                grado=m.rank or rd.get("grado") or rd.get("rank") or rd.get("grade") or "",
                morte=m.fate or rd.get("causa_morte") or rd.get("fate") or "",
                prigionia=rd.get("luogo_internamento") or rd.get("luogo_cattura") or rd.get("camp") or "",
                stato="POSSIBLE", raw_data=rd, confidence=m.confidence,
            )
            provider = m.source_detail
            c.fonti.append(SourceRecord(
                url=m.url, istituzione=provider,
                connection_type=classify_connection(provider, has_api=True, url=m.url),
                metodo_individuazione="API_SEARCH", source_level=classify_source(provider, m.url),
                esito="positive", data_accesso=datetime.now().isoformat(),
            ))
            score_candidate(c, si)
            dossier.candidati.append(c)
        dossier.search_log.append(SearchLogEntry(
            query_id=f"fed_{datetime.now().strftime('%H%M%S')}", timestamp=datetime.now().isoformat(),
            query=si.full_name, motore_o_archivio="federated_27_providers", connection_type="OFFICIAL_API",
            risultati_trovati=len(matches), esito="positive" if matches else "negative",
        ))
        if not matches:
            dossier.ricerche_negative.append(dossier.search_log[-1])


def _search_web(si: SearchInput, dossier: Dossier):
    """Generate web search URLs for archives not covered by API providers."""
    from person_finder import _search_web, PersonQuery
    pq = PersonQuery(raw=si.full_name, cognome=si.cognome, nome=si.nome,
                     birth_year=int(si.anno_nascita) if si.anno_nascita.isdigit() else None,
                     birth_place=si.luogo_nascita)
    matches = _search_web(pq)
    with _dossier_lock:
        for m in matches:
            c = Candidate(
                nome_originale=m.name, stato="INSUFFICIENT_DATA",
                confidence=m.confidence, raw_data=m.raw_data,
            )
            c.fonti.append(SourceRecord(
                url=m.url, istituzione=m.source_detail,
                connection_type="SEARCH_DISCOVERY", metodo_individuazione="SEARCH_QUERY",
                source_level=classify_source(m.source_detail, m.url),
                esito="ambiguous", note=m.raw_data.get("search_hint", ""),
                data_accesso=datetime.now().isoformat(),
            ))
            dossier.candidati.append(c)
        dossier.search_log.append(SearchLogEntry(
            query_id=f"web_{datetime.now().strftime('%H%M%S')}", timestamp=datetime.now().isoformat(),
            query=si.full_name, motore_o_archivio="web_archives", connection_type="SEARCH_DISCOVERY",
            risultati_trovati=len(matches), esito="ambiguous",
        ))


# ─── Persistence ──────────────────────────────────────────────────────────────

def _persist_dossier(dossier: Dossier, si: SearchInput):
    """Persist dossier to Supabase for future reference.

    FIX: Only persist candidates with accepted evidence.
    Candidates without evidence are marked 'unverified', not 'discovered'.
    Rejected candidates (EXCLUDED/REJECTED_WRONG_IDENTITY) are NOT persisted.
    """
    try:
        import httpx
        from dotenv import load_dotenv
        load_dotenv()
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            return
        rpc = f"{url}/rest/v1/rpc/exec_sql_returning"
        h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        stable_id = f"research:{si.cognome.lower()}:{si.nome.lower()}:{si.anno_nascita or 'unk'}"
        # Use resolution_state to set verification_status
        resolution = dossier.profilo.get("resolution_state", "UNRESOLVED")
        typed_counts = dossier.profilo.get("typed_counts", {})
        accepted_evidence = typed_counts.get("accepted_evidence_sources", 0)

        if resolution == "CONFIRMED":
            ver_status = "verified"
            conf = 0.9
        elif resolution == "PROBABLE":
            ver_status = "probable"
            conf = 0.6
        elif accepted_evidence > 0:
            ver_status = "candidate"
            conf = 0.4
        else:
            ver_status = "unverified"
            conf = 0.1

        entity_sql = f"""
        INSERT INTO core.entities (stable_id, entity_type, canonical_name, verification_status, confidence, source_system, source_table)
        SELECT '{stable_id}', 'person', '{si.full_name.replace("'", "''")}', '{ver_status}', {conf}, 'research_protocol', 'auto_search'
        WHERE NOT EXISTS (SELECT 1 FROM core.entities WHERE stable_id = '{stable_id}')
        RETURNING id;
        """
        r = httpx.post(rpc, headers=h, json={"query": entity_sql}, timeout=30)
        if r.status_code in (200, 201):
            data = r.json()
            if isinstance(data, list) and data and isinstance(data[0], dict):
                entity_id = data[0].get("id")
                if entity_id:
                    # ── FIX: Only persist candidates with evidence, not just POSSIBLE ──
                    for c in dossier.candidati[:20]:
                        if c.stato in ("CONFIRMED", "PROBABLE"):
                            claim_status = "verified" if accepted_evidence > 0 else "discovered"
                        elif c.stato == "POSSIBLE":
                            claim_status = "unverified"  # Not 'discovered' without evidence
                        else:
                            continue  # Don't persist INSUFFICIENT_DATA or EXCLUDED
                        claim_sql = f"""
                        INSERT INTO evidence.claims (subject_entity_id, predicate, object_value, claim_status, source_system)
                        VALUES ({entity_id}, 'identified_as', '{c.nome_originale.replace("'", "''")}', '{claim_status}', 'research_protocol')
                        ON CONFLICT DO NOTHING;
                        """
                        try:
                            httpx.post(rpc, headers=h, json={"query": claim_sql}, timeout=15)
                        except Exception:
                            pass
    except Exception as e:
        log.debug("Persist error: %s", e)


# ─── Main orchestrator ────────────────────────────────────────────────────────

def research_person(input_data: dict, *, use_ai: bool = True, persist: bool = True) -> Dossier:
    """Execute full research protocol per specification.

    Args:
        input_data: dict matching the protocol input schema (section 1)
        use_ai: use Qwen/LMStudio for variant generation and dossier synthesis
        persist: save results to Supabase

    Returns:
        Dossier with all sections A-N per protocol section 17
    """
    t_start = datetime.now()
    si = SearchInput.from_dict(input_data)
    log.info("ResearchProtocol: start for '%s'", si.full_name)

    # ── FIX: Create immutable ResearchTarget ──
    target = ResearchTarget.from_search_input(si)
    log.info("ResearchProtocol: target_id=%s hash=%s", target.target_id, target.target_hash)

    dossier = Dossier(created_at=t_start.isoformat())
    dossier.profilo["input"] = input_data
    dossier.profilo["target_id"] = target.target_id
    dossier.profilo["target_hash"] = target.target_hash

    # Phase 4: base variants (fast, no AI)
    variants = generate_variants(si)

    # ── Parallel execution: AI variants + all 4 search levels concurrently ──
    import concurrent.futures
    import threading

    candidates_lock = threading.Lock()
    search_log_lock = threading.Lock()

    def _safe_search(func, *args):
        """Run a search function, catching errors. Appends to shared dossier."""
        try:
            func(*args)
        except Exception as e:
            log.warning("Search %s error: %s", func.__name__, e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        # AI variant enrichment — runs concurrently with searches
        future_ai = None
        if use_ai:
            future_ai = pool.submit(_ai_normalize_variants, si, variants)

        # All 4 search levels in parallel
        future_local = pool.submit(_safe_search, _search_local, si, variants, dossier)
        future_supabase = pool.submit(_safe_search, _search_supabase, si, dossier)
        future_federated = pool.submit(_safe_search, _search_federated, si, variants, dossier)
        future_web = pool.submit(_safe_search, _search_web, si, dossier)

        # Wait for AI variants (should finish in ~5s, searches take longer)
        if future_ai is not None:
            try:
                variants = future_ai.result(timeout=30)
            except Exception as e:
                log.warning("AI variant enrichment failed: %s", e)
        dossier.varianti = variants

        # Wait for all searches (federated is the bottleneck, now parallelized internally)
        for fut in [future_local, future_supabase, future_federated, future_web]:
            try:
                fut.result(timeout=120)
            except concurrent.futures.TimeoutError:
                log.warning("Search timed out: %s", fut)
            except Exception as e:
                log.warning("Search error: %s", e)

    log.info("Search complete: %d candidates in %.1fs", len(dossier.candidati), (datetime.now() - t_start).total_seconds())

    # Separate excluded homonyms
    dossier.omonimi_esclusi = [c for c in dossier.candidati if c.stato == "EXCLUDED"]
    dossier.candidati = [c for c in dossier.candidati if c.stato != "EXCLUDED"]

    # ── FIX: Determine overall status via deterministic gate ──
    # score_candidate now returns POSSIBLE (not CONFIRMED) for field matches.
    # The resolution gate checks for accepted independent evidence.
    # Without evidence, status is UNRESOLVED/dati_insufficienti, not confermata.
    best_resolution = ResolutionResult()
    for c in dossier.candidati:
        gate_result = apply_resolution_gate(
            candidate=c,
            accepted_evidence_count=0,  # No evidence collection yet — web search may add
            independent_lineages=0,
            hard_conflicts=c.contraddizioni if c.contraddizioni else [],
        )
        if gate_result.resolution_state == ResolutionState.REJECTED_WRONG_IDENTITY:
            c.stato = "EXCLUDED"
            dossier.omonimi_esclusi.append(c)
        elif gate_result.resolution_state.value not in ("UNRESOLVED",):
            best_resolution = gate_result

    # Re-filter after gate
    dossier.candidati = [c for c in dossier.candidati if c.stato != "EXCLUDED"]

    # Map resolution state to dossier status
    state_map = {
        ResolutionState.CONFIRMED: "confermata",
        ResolutionState.PROBABLE: "probabile",
        ResolutionState.AMBIGUOUS: "possibile",
        ResolutionState.NEEDS_REVIEW: "dati_insufficienti",
        ResolutionState.UNRESOLVED: "dati_insufficienti" if dossier.candidati else "non_identificata",
        ResolutionState.REJECTED_WRONG_IDENTITY: "non_identificata",
    }
    dossier.stato_identificazione = state_map.get(best_resolution.resolution_state, "dati_insufficienti" if dossier.candidati else "non_identificata")
    dossier.profilo["resolution_state"] = best_resolution.resolution_state.value
    dossier.profilo["reason_codes"] = best_resolution.reason_codes

    # ── FIX: Collect sources only from active candidates, not excluded ──
    for c in dossier.candidati:
        dossier.fonti.extend(c.fonti)

    # ── FIX: Compute typed counts ──
    typed_counts = compute_typed_counts(dossier.candidati, dossier.omonimi_esclusi)
    dossier.profilo["typed_counts"] = typed_counts

    # Collect contradictions
    for c in dossier.candidati:
        for contra in c.contraddizioni:
            dossier.contraddizioni.append({"candidato": c.nome_originale, "contraddizione": contra})

    # Web search: always run to confirm and expand results with online sources
    dossier = _web_search_enrich(si, dossier, target)

    # AI dossier synthesis — FIX: AI cannot override stato_identificazione
    if use_ai:
        dossier = _ai_build_dossier(dossier, target)

    # Generate archival requests if not confirmed
    if dossier.stato_identificazione != "confermata":
        dossier.richieste = _generate_archival_requests(si, dossier)

    # Persist
    if persist:
        _persist_dossier(dossier, si)

    dossier.completed_at = datetime.now().isoformat()
    log.info("ResearchProtocol: completed in %.1fs — status=%s candidates=%d",
             (datetime.now() - t_start).total_seconds(), dossier.stato_identificazione, len(dossier.candidati))
    return dossier


def _web_search_enrich(si: SearchInput, dossier: Dossier, target: ResearchTarget = None) -> Dossier:
    """Web search enrichment: Tavily (real search API) + Mistral AI per elaborazione.

    Pipeline:
    1. Costruisce query anchored al ResearchTarget (no candidati locali → no subject drift)
    2. Chiama Tavily API per risultati di ricerca web reali
    3. Passa i risultati a Mistral per elaborazione strutturata
    4. Classifica le fonti per object_kind ed evidence_eligibility
    5. Circuit breaker per cascading failure prevention
    """
    from circuit_breaker import CircuitBreaker, WebSearchErrorCode, classify_exception

    global _web_search_circuit
    if '_web_search_circuit' not in globals():
        _web_search_circuit = CircuitBreaker(
            provider_name="tavily_mistral",
            failure_threshold=5,
            recovery_timeout=60.0,
        )

    if not _web_search_circuit.can_call():
        log.warning("Web search: CIRCUIT_OPEN — skipping (failures=%d, last_error=%s)",
                    _web_search_circuit.consecutive_failures,
                    _web_search_circuit.last_error_code)
        dossier.web_search_used = False
        dossier.web_search_results = {
            "target_id": target.target_id if target else "",
            "target_hash": target.target_hash if target else "",
            "error": {
                "stage": "web_search",
                "error_code": WebSearchErrorCode.CIRCUIT_OPEN.value,
                "safe_message": "Circuit breaker open — too many consecutive failures",
                "provider": "tavily_mistral",
            },
        }
        return dossier

    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()

        # ── Step 1: Build search query from immutable target ──
        query_parts = [si.full_name]
        if si.anno_nascita:
            query_parts.append(f"nato nel {si.anno_nascita}")
        if si.luogo_nascita:
            query_parts.append(f"a {si.luogo_nascita}")
        if si.paternita:
            query_parts.append(f"figlio di {si.paternita}")
        if si.grado:
            query_parts.append(f"grado {si.grado}")
        if si.reparto:
            query_parts.append(f"reparto {si.reparto}")
        if si.conflitto_presunto:
            query_parts.append(si.conflitto_presunto)
        else:
            query_parts.append("militare italiano Prima/Seconda Guerra Mondiale")

        query = ", ".join(query_parts)
        search_query = f"{si.full_name} {si.anno_nascita} {si.luogo_nascita} caduto militare italiano Grande Guerra"

        log.info("Web search: Tavily query '%s'", search_query[:80])

        # ── Step 2: Call Tavily API for real web search results ──
        from web_search_providers import search_tavily
        search_resp = search_tavily(search_query, max_results=10, timeout=30)

        if not search_resp.ok or not search_resp.results:
            error_msg = search_resp.error or "No results returned"
            log.warning("Web search: Tavily failed — %s", error_msg)
            _web_search_circuit.record_failure(WebSearchErrorCode.RATE_LIMITED.value)
            dossier.web_search_used = False
            dossier.web_search_results = {
                "target_id": target.target_id if target else "",
                "target_hash": target.target_hash if target else "",
                "error": {
                    "stage": "web_search",
                    "error_code": "SEARCH_FAILED",
                    "safe_message": error_msg[:200],
                    "provider": "tavily",
                    "retryable": True,
                },
            }
            return dossier

        log.info("Web search: Tavily returned %d results in %dms",
                 len(search_resp.results), search_resp.elapsed_ms)

        # ── Step 3: Mistral AI elaboration of real search results ──
        sources_for_ai = [
            {"url": r.url, "title": r.title, "snippet": r.snippet}
            for r in search_resp.results[:10]
        ]

        ai_instructions = (
            "Sei un ricercatore storico-archivistico specializzato in storia militare "
            "italiana del 1900 (Prima e Seconda Guerra Mondiale, IMI, internati, caduti, "
            "decorati). Analizza i risultati di ricerca web reali per il soggetto indicato. "
            "NON inventare dati. NON sostituire il soggetto con un omonimo. "
            "Rispondi in italiano con formato strutturato:\n"
            "1. CONFERMA: indica se sono stati trovati record nominativi diretti (non pagine di ricerca)\n"
            "2. NUOVI DATI TROVATI: informazioni aggiuntive con fonte specifica\n"
            "3. FONTI CONSULTATE: elenco con URL diretto al record\n"
            "4. AFFIDABILITA: livello (alta/media/bassa) con motivazione\n"
            "5. SUGGERIMENTI: fonti archivistiche da consultare"
        )

        ai_user = json.dumps({
            "soggetto": query,
            "risultati_ricerca": sources_for_ai,
        }, ensure_ascii=False)

        from ai_runtime import get_adapter
        adapter = get_adapter()
        ai_result = adapter.generate(
            system=ai_instructions,
            user=ai_user,
            max_tokens=2048,
            temperature=0.2,
            task_type="web_search",
            timeout=60,
        )

        ai_text = ai_result.text if ai_result.ok else ""
        if not ai_result.ok:
            log.warning("Web search: Mistral elaboration failed — %s", ai_result.error)

        # ── Step 4: Build structured results ──
        sources = [{"url": r.url, "title": r.title} for r in search_resp.results]
        if ai_text:
            import re as _re
            extra_urls = _re.findall(r'https?://[^\s<>"\']+', ai_text)
            existing = {s["url"] for s in sources}
            for u in extra_urls:
                if u not in existing:
                    sources.append({"url": u, "title": u.split("/")[2] if "/" in u else u})
                    existing.add(u)

        dossier.web_search_used = True
        dossier.web_search_results = {
            "target_id": target.target_id if target else "",
            "target_hash": target.target_hash if target else "",
            "query": query,
            "search_query": search_query,
            "search_provider": "tavily",
            "text": ai_text or "Elaborazione AI non disponibile. Risultati di ricerca grezzi nei sources.",
            "sources": sources,
            "source_classifications": [
                {"url": s["url"], "title": s["title"],
                 "object_kind": classify_object_kind(s["url"]).value,
                 "evidence_eligible": is_evidence_eligible(classify_object_kind(s["url"]))}
                for s in sources
            ],
            "search_actions": ["tavily_search", "mistral_elaboration"],
            "usage": {
                "input_tokens": ai_result.input_tokens if ai_result.ok else 0,
                "output_tokens": ai_result.output_tokens if ai_result.ok else 0,
                "total_tokens": (ai_result.input_tokens + ai_result.output_tokens) if ai_result.ok else 0,
            },
            "raw_results_count": len(search_resp.results),
            "search_elapsed_ms": search_resp.elapsed_ms,
        }

        log.info("Web search: completed — %d sources, AI: %s, %d tokens",
                 len(sources), "OK" if ai_result.ok else "FAILED",
                 (ai_result.input_tokens + ai_result.output_tokens) if ai_result.ok else 0)

        _web_search_circuit.record_success()

        # ── Discovery persistence pipeline ──
        try:
            from discovery_persistence import process_web_search_results
            dp_result = process_web_search_results(
                web_search_results=dossier.web_search_results,
                subject_name=si.full_name,
                subject_type="soldier",
                subject_id=si.cognome,
                query_used=query,
            )
            dossier.discovery_persistence = {
                "sources_discovered": dp_result.sources_discovered,
                "new_sources_created": dp_result.new_sources_created,
                "existing_sources_updated": dp_result.existing_sources_updated,
                "full_content_archived": dp_result.full_content_archived,
                "metadata_only_saved": dp_result.metadata_only_saved,
                "link_only_saved": dp_result.link_only_saved,
                "new_claims_created": dp_result.new_claims_created,
                "conflicting_claims_created": dp_result.conflicting_claims_created,
                "new_entities_discovered": dp_result.new_entities_discovered,
                "research_leads_created": dp_result.research_leads_created,
                "object_links_created": dp_result.object_links_created,
                "local_persistence": dp_result.local_persistence,
                "supabase_sync": dp_result.supabase_sync,
                "manual_review_required": dp_result.manual_review_required,
                "sources": dp_result.sources,
                "claims": dp_result.claims,
                "entities": dp_result.entities,
                "leads": dp_result.leads,
            }
            log.info("DiscoveryPersistence: sources=%d claims=%d entities=%d leads=%d sync=%s",
                     dp_result.new_sources_created, dp_result.new_claims_created,
                     dp_result.new_entities_discovered, dp_result.research_leads_created,
                     dp_result.supabase_sync)
        except Exception as dp_err:
            log.warning("Discovery persistence failed: %s", dp_err)
            dossier.discovery_persistence = {
                "local_persistence": "failed",
                "supabase_sync": "failed",
                "error": str(dp_err),
            }

    except Exception as e:
        error_code = classify_exception(e)
        _web_search_circuit.record_failure(error_code.value)
        log.warning("Web search failed: %s — %s (circuit failures=%d)",
                    error_code.value, str(e)[:200],
                    _web_search_circuit.consecutive_failures)
        dossier.web_search_used = False
        dossier.web_search_results = {
            "target_id": target.target_id if target else "",
            "target_hash": target.target_hash if target else "",
            "error": {
                "stage": "web_search",
                "error_code": error_code.value,
                "exception_type": type(e).__name__,
                "safe_message": str(e)[:200],
                "provider": "tavily_mistral",
                "retryable": error_code in (WebSearchErrorCode.RATE_LIMITED, WebSearchErrorCode.TIMEOUT),
            },
        }

    return dossier


def _generate_archival_requests(si: SearchInput, dossier: Dossier) -> List[dict]:
    """Generate archival request templates per protocol section 17.N."""
    requests = []
    base_data = f"Nome: {si.nome} {si.cognome}"
    if si.anno_nascita:
        base_data += f", classe {si.anno_nascita}"
    if si.luogo_nascita:
        base_data += f", nato a {si.luogo_nascita}"
    if si.paternita:
        base_data += f", di {si.paternita}"

    # Archivio di Stato (foglio matricolare)
    if si.luogo_nascita or si.distretto_militare:
        requests.append({
            "ente": f"Archivio di Stato di {si.provincia_nascita or si.luogo_nascita or '—'}",
            "fondo": "Rubriche Fogli Matricolari",
            "documento_richiesto": "Foglio matricolare",
            "dati_conosciuti": base_data,
            "motivazione": "Ricostruzione percorso militare",
            "intervallo_cronologico": si.periodo_presunto or "1915-1945",
        })

    # Archivio Centrale dello Stato (ruoli matricolari)
    requests.append({
        "ente": "Archivio Centrale dello Stato — Roma",
        "fondo": "Ministero della Guerra — Ruoli Matricolari",
        "documento_richiesto": "Ruolo matricolare",
        "dati_conosciuti": base_data + (f", distretto {si.distretto_militare}" if si.distretto_militare else ""),
        "motivazione": "Verifica matricola e reparto di assegnazione",
        "intervallo_cronologico": si.periodo_presunto or "1915-1945",
    })

    # ICRC (prigionieri)
    if si.conflitto_presunto in ("ww1", "") or si.numero_prigioniero:
        requests.append({
            "ente": "ICRC — International Committee of the Red Cross",
            "fondo": "Prisoners of the First World War" if si.conflitto_presunto == "ww1" else "WW2 Prisoners",
            "documento_richiesto": "Scheda prigioniero",
            "dati_conosciuti": base_data + (f", n. prigioniero {si.numero_prigioniero}" if si.numero_prigioniero else ""),
            "motivazione": "Verifica cattura, campo di prigionia, trasferimenti",
            "intervallo_cronologico": si.periodo_presunto or "1915-1918",
        })

    # LeBI/ANRP (internati italiani)
    requests.append({
        "ente": "ANRP — Lessico Biografico degli IMI",
        "fondo": "Schede biografiche internati militari italiani",
        "documento_richiesto": "Scheda biografica",
        "dati_conosciuti": base_data,
        "motivazione": "Verifica internamento, campi attraversati, rimpatrio",
        "intervallo_cronologico": "1943-1947",
    })

    return requests


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print('Usage: python research_protocol.py \'{"cognome":"Siracusa","nome":"Francesco","anno_nascita":"1886","luogo_nascita":"Messina"}\'')
        sys.exit(1)
    input_data = json.loads(sys.argv[1])
    dossier = research_person(input_data)
    print(json.dumps(dossier.to_dict(), indent=2, ensure_ascii=False, default=str))
