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

import json, logging, re, sqlite3, os, threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Score candidate against input per protocol section 12."""
    strong_matches = 0
    medium_matches = 0
    contradictions = []

    # Strong identifiers
    if si.data_nascita and candidate.data_nascita and si.data_nascita in candidate.data_nascita:
        strong_matches += 1
    elif si.data_nascita and candidate.data_nascita and si.data_nascita not in candidate.data_nascita:
        contradictions.append(f"data_nascita: input={si.data_nascita} vs candidate={candidate.data_nascita}")

    if si.luogo_nascita and candidate.luogo_nascita and si.luogo_nascita.lower() in candidate.luogo_nascita.lower():
        strong_matches += 1
    elif si.luogo_nascita and candidate.luogo_nascita and si.luogo_nascita.lower() not in candidate.luogo_nascita.lower():
        contradictions.append(f"luogo_nascita: input={si.luogo_nascita} vs candidate={candidate.luogo_nascita}")

    if si.paternita and candidate.paternita and si.paternita.lower() in candidate.paternita.lower():
        strong_matches += 1
    elif si.paternita and candidate.paternita and si.paternita.lower() not in candidate.paternita.lower():
        contradictions.append(f"paternita: input={si.paternita} vs candidate={candidate.paternita}")

    if si.numero_matricola and candidate.matricola and si.numero_matricola == candidate.matricola:
        strong_matches += 1

    # Medium identifiers
    for field_name in MEDIUM_IDENTIFIERS:
        input_val = getattr(si, field_name, "")
        cand_val = getattr(candidate, field_name.replace("numero_matricola", "matricola"), "")
        if not cand_val:
            # Try alternative field names
            alt_map = {"anno_nascita": "data_nascita", "distretto_militare": "distretto", "reparto": "reparto", "grado": "grado"}
            cand_val = getattr(candidate, alt_map.get(field_name, field_name), "")
        if input_val and cand_val and input_val.lower() in str(cand_val).lower():
            medium_matches += 1

    candidate.compatibilita = [f"strong_matches={strong_matches}", f"medium_matches={medium_matches}"]
    candidate.contraddizioni = contradictions

    # Decision per protocol section 12
    if strong_matches >= 1 and not contradictions:
        candidate.stato = "CONFIRMED"
    elif strong_matches >= 1 and contradictions:
        candidate.stato = "PROBABLE"
    elif medium_matches >= 3 and not contradictions:
        candidate.stato = "PROBABLE"
    elif medium_matches >= 1:
        candidate.stato = "POSSIBLE"
    elif contradictions and not strong_matches:
        candidate.stato = "EXCLUDED"
    else:
        # If user provided no strong identifiers, but candidate has data,
        # mark as POSSIBLE instead of INSUFFICIENT_DATA
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


def _ai_build_dossier(dossier: Dossier) -> Dossier:
    """Use Qwen AI to synthesize the final dossier from collected data."""
    try:
        from ai_runtime import get_adapter
        adapter = get_adapter()
        health = adapter.health()
        if not health.healthy:
            log.info("AI not healthy, skipping AI dossier synthesis")
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
Rispondi in JSON con: {
  "stato_identificazione": "confermata|probabile|possibile|non_identificata|dati_insufficienti",
  "profilo": {"dati_accertati": {}, "note": ""},
  "piste": [{"priorita": 1, "azione": "", "fonte": "", "motivazione": ""}],
  "richieste_archivistiche": [{"ente": "", "fondo": "", "documento_richiesto": "", "dati_conosciuti": "", "motivazione": ""}]
}"""
        user = json.dumps({
            "input": dossier.profilo.get("input", {}),
            "candidati": candidates_summary,
            "fonti_count": len(dossier.fonti),
            "contraddizioni": dossier.contraddizioni[:5],
            "ricerche_negative": len(dossier.ricerche_negative),
        }, ensure_ascii=False)

        result = adapter.generate_structured(system, user, max_tokens=2048, temperature=0.2, task_type="dossier_synthesis", timeout=60)
        if result.ok and result.text:
            data = json.loads(result.text)
            if data.get("stato_identificazione"):
                dossier.stato_identificazione = data["stato_identificazione"]
            if data.get("profilo"):
                dossier.profilo.update(data["profilo"])
            if data.get("piste"):
                dossier.piste = data["piste"]
            if data.get("richieste_archivistiche"):
                dossier.richieste = data["richieste_archivistiche"]
            dossier.ai_used = True
            dossier.ai_model = health.model
            log.info("AI dossier synthesized (model=%s)", health.model)
    except Exception as e:
        log.debug("AI dossier synthesis skipped: %s", e)
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
    """Persist dossier to Supabase for future reference."""
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
        entity_sql = f"""
        INSERT INTO core.entities (stable_id, entity_type, canonical_name, verification_status, confidence, source_system, source_table)
        SELECT '{stable_id}', 'person', '{si.full_name.replace("'", "''")}', 'candidate', 0.3, 'research_protocol', 'auto_search'
        WHERE NOT EXISTS (SELECT 1 FROM core.entities WHERE stable_id = '{stable_id}')
        RETURNING id;
        """
        r = httpx.post(rpc, headers=h, json={"query": entity_sql}, timeout=30)
        if r.status_code in (200, 201):
            data = r.json()
            if isinstance(data, list) and data and isinstance(data[0], dict):
                entity_id = data[0].get("id")
                if entity_id:
                    # Save claims for each candidate
                    for c in dossier.candidati[:20]:
                        if c.stato in ("CONFIRMED", "PROBABLE", "POSSIBLE"):
                            claim_sql = f"""
                            INSERT INTO evidence.claims (subject_entity_id, predicate, object_value, claim_status, source_system)
                            VALUES ({entity_id}, 'identified_as', '{c.nome_originale.replace("'", "''")}', 'discovered', 'research_protocol')
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

    dossier = Dossier(created_at=t_start.isoformat())
    dossier.profilo["input"] = input_data

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

    # Determine overall status
    confirmed = [c for c in dossier.candidati if c.stato == "CONFIRMED"]
    probable = [c for c in dossier.candidati if c.stato == "PROBABLE"]
    possible = [c for c in dossier.candidati if c.stato == "POSSIBLE"]
    if confirmed:
        dossier.stato_identificazione = "confermata"
        dossier.profilo["dati_accertati"] = confirmed[0].raw_data
    elif probable:
        dossier.stato_identificazione = "probabile"
    elif possible:
        dossier.stato_identificazione = "possibile"
    elif dossier.candidati:
        dossier.stato_identificazione = "dati_insufficienti"
    else:
        dossier.stato_identificazione = "non_identificata"

    # Collect all sources
    for c in dossier.candidati + dossier.omonimi_esclusi:
        dossier.fonti.extend(c.fonti)

    # Collect contradictions
    for c in dossier.candidati:
        for contra in c.contraddizioni:
            dossier.contraddizioni.append({"candidato": c.nome_originale, "contraddizione": contra})

    # Web search: always run to confirm and expand results with online sources
    dossier = _web_search_enrich(si, dossier)

    # AI dossier synthesis
    if use_ai:
        dossier = _ai_build_dossier(dossier)

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


def _web_search_enrich(si: SearchInput, dossier: Dossier) -> Dossier:
    """Web search con OpenAI: conferma candidati locali e amplia con fonti online certe."""
    try:
        import os
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            log.info("Web search: OPENAI_API_KEY non configurata, skip")
            return dossier

        client = OpenAI(api_key=api_key)

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

        # Include local candidates as context for confirmation
        local_context = ""
        if dossier.candidati:
            confirmed_candidates = []
            for c in dossier.candidati:
                if c.stato == "INSUFFICIENT_DATA":
                    continue
                parts = [c.nome_originale]
                if c.paternita:
                    parts.append(f"padre: {c.paternita}")
                if c.data_nascita:
                    parts.append(f"nascita: {c.data_nascita}")
                if c.luogo_nascita:
                    parts.append(f"luogo: {c.luogo_nascita}")
                if c.reparto:
                    parts.append(f"reparto: {c.reparto}")
                if c.grado:
                    parts.append(f"grado: {c.grado}")
                if c.morte:
                    parts.append(f"sorte: {c.morte}")
                parts.append(f"stato: {c.stato}")
                confirmed_candidates.append(" | ".join(parts))

            if confirmed_candidates:
                local_context = "\n\nCANDIDATI TROVATI NEL DB LOCALE (da confermare):\n" + "\n".join(
                    f"- {c}" for c in confirmed_candidates[:10]
                )
                query += local_context
                query += "\n\nVerifica se questi candidati corrispondono a record online reali (Albo d'Oro, ICRC, archivi statali). Cerca anche ULTERIORI fonti certe non presenti nel DB locale."

        query += "\n\nVerifica in: cadutigrandeguerra.it (Albo d'Oro), antenati.cultura.gov.it (ruoli matricolari), Archivi di Stato, ICRC, LeBI, Ministero Difesa, o altri archivi storici italiani online."

        instructions = (
            "Sei un ricercatore storico-archivistico specializzato in storia militare "
            "italiana del 1900 (Prima e Seconda Guerra Mondiale, IMI, internati, caduti, "
            "decorati). Cerca informazioni reali online negli archivi italiani. "
            "NON inventare dati. Rispondi in italiano con formato strutturato:\n"
            "1. CONFERMA CANDIDATI: per ogni candidato locale, indica se confermato online o meno\n"
            "2. NUOVI DATI TROVATI: informazioni aggiuntive non presenti nel DB locale\n"
            "3. FONTI CONSULTATE: elenco con URL\n"
            "4. AFFIDABILITA: livello (alta/media/bassa) con motivazione\n"
            "5. SUGGERIMENTI: fonti archivistiche da consultare"
        )

        log.info("Web search: querying OpenAI for '%s'", query[:80])

        resp = client.responses.create(
            model="gpt-5.5",
            tools=[{
                "type": "web_search",
                "search_context_size": "high",
                "user_location": {
                    "type": "approximate",
                    "country": "IT",
                },
            }],
            instructions=instructions,
            input=query,
        )

        sources = []
        search_actions = []
        if hasattr(resp, "output"):
            for item in resp.output:
                if item.type == "web_search_call":
                    action_type = ""
                    if hasattr(item, "action") and hasattr(item.action, "type"):
                        action_type = item.action.type
                    search_actions.append(action_type)
                    if hasattr(item, "results") and item.results:
                        for r in item.results:
                            url = getattr(r, "url", None) or ""
                            title = getattr(r, "title", None) or url
                            if url:
                                sources.append({"url": url, "title": title})

        usage = {}
        if hasattr(resp, "usage"):
            u = resp.usage
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0),
                "output_tokens": getattr(u, "output_tokens", 0),
                "total_tokens": getattr(u, "total_tokens", 0),
            }

        dossier.web_search_used = True
        dossier.web_search_results = {
            "query": query,
            "text": resp.output_text,
            "sources": sources,
            "search_actions": search_actions,
            "usage": usage,
        }

        log.info("Web search: completed — %d sources, %d tokens",
                 len(sources), usage.get("total_tokens", 0))

        # ── Discovery persistence pipeline ──
        try:
            from discovery_persistence import process_web_search_results
            dp_result = process_web_search_results(
                web_search_results=dossier.web_search_results,
                subject_name=si.full_name,
                subject_type="soldier",
                subject_id=si.cognome,  # best-effort ID
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
        log.warning("Web search failed: %s", e)

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
