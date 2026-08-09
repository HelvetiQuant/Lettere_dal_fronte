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

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("military_ontology")


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
    "unit_generic": ["reparto", "unita", "unit"],
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
        "mitraglieri": ["mitraglieri", "mitragliere", "machine gun"],
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


# ─── Unit context descriptions for narrator enrichment ──────────────────────

RANK_ROLE_DESCRIPTIONS: Dict[str, str] = {
    # ── Truppa ──
    "soldato": (
        "Il soldato era il grado base della truppa, il combattente di prima linea. "
        "Esecutore degli ordini, occupava e difendeva le trincee, avanzava negli assalti "
        "e svolgeva i lavori di fortificazione. Sostenne il maggior peso di perdite del conflitto."
    ),
    "fante": (
        "Il fante era il soldato di fanteria, protagonista della guerra di trincea. "
        "Armato di fucile e baionetta, occupava le prime linee, partecipava agli assalti "
        "e ai turni di guardia nelle trincee sotto il fuoco dell'artiglieria nemica."
    ),
    "caporale": (
        "Il caporale era il primo grado di comando nella truppa: comandava una squadra "
        "di 8-12 uomini. Responsabile della disciplina e dell'addestramento dei soldati, "
        "trasmetteva gli ordini dei superiori e guidava la squadra in combattimento."
    ),
    "caporale maggiore": (
        "Il caporale maggiore era un caporale con maggiore anzianita e responsabilita. "
        "Poteva comandare una squadra o svolgere funzioni di vice-comandante di plotone, "
        "con esperienza pregressa sul campo."
    ),
    "bersagliere": (
        "Il bersagliere era un soldato del corpo dei bersaglieri, truppa leggera addestrata "
        "alla rapidita e al tiro di precisione. Correva invece di marciare, operava come "
        "avanguardia e in missioni di esplorazione."
    ),
    "alpino": (
        "L'alpino era un soldato del corpo degli alpini, specializzato nella guerra di montagna. "
        "Operava ad alta quota, combatteva su ghiacciai e creste, trasportava rifornimenti "
        "con muli e slitte in condizioni estreme."
    ),
    "artigliere": (
        "L'artigliere era un soldato specializzato nel servizio dei cannoni: puntava, caricava "
        "e faceva fuoco, gestendo la manutenzione dei pezzi e il trasporto delle munizioni."
    ),
    "granatiere": (
        "Il granatiere era un soldato scelto di fanteria pesante, addestrato per il lancio "
        "di granate e per azioni di sfondamento. Tradizionalmente impiegato in missioni "
        "di assalto a posizioni fortificate."
    ),
    "fuciliere": (
        "Il fuciliere era un soldato di fanteria armato di fucile, impiegato in prima linea "
        "per il combattimento di trincea, la pattuglia e l'assalto."
    ),
    "marinaio": (
        "Il marinaio era un soldato della Regia Marina, addetto alle operazioni di bordo "
        "sulle navi da guerra: manovra, artiglieria navale, segnalazione e manutenzione."
    ),
    "aviere": (
        "L'aviere era un soldato del Corpo Aeronautico, addetto ai servizi di terra "
        "negli aeroporti militari: manutenzione degli aeroplani, rifornimento, assistenza "
        "ai piloti e gestione delle piste."
    ),
    # ── Sottufficiali ──
    "sergente": (
        "Il sergente era il sottufficiale piu basso in grado, comandava un plotone "
        "di 30-40 uomini in assenza di un ufficiale o ne era il vice. Responsabile "
        "dell'addestramento, della disciplina e del coordinamento tattico sul campo. "
        "In combattimento guidava personalmente il plotone negli assalti."
    ),
    "sergente maggiore": (
        "Il sergente maggiore era un sottufficiale con maggiore anzianita del sergente. "
        "Poteva comandare un plotone o svolgere funzioni amministrative e di collegamento "
        "tra la truppa e gli ufficiali. Spesso era il sottufficiale piu esperto della compagnia."
    ),
    "sergente capo": (
        "Il sergente capo era un sottufficiale con funzioni di comando intermedio: "
        "poteva essere vice-comandante di compagnia o responsabile di servizi specializzati "
        "all'interno del battaglione."
    ),
    "maresciallo": (
        "Il maresciallo era un sottufficiale di alto grado, con funzioni di comando "
        "e amministrative. Poteva comandare una compagnia in assenza di ufficiali, "
        "gestire la logistica del battaglione o svolgere ruoli di collegamento "
        "tra il comando e la linea del fronte. Era spesso il pilastro dell'unita."
    ),
    "maresciallo maggiore": (
        "Il maresciallo maggiore era il sottufficiale di grado piu alto, con lunga "
        "esperienza. Responsabile dell'organizzazione amministrativa e disciplinare "
        "del reparto, poteva sostituire ufficiali inferiori nel comando di compagnia."
    ),
    # ── Ufficiali inferiori ──
    "sottotenente": (
        "Il sottotenente era il primo grado da ufficiale, tipicamente assegnato a giovani "
        "di leva o di complemento. Comandava un plotone di 30-40 uomini, era responsabile "
        "della sua disciplina, addestramento e impiego tattico. In prima linea guidava "
        "personalmente il plotone negli assalti."
    ),
    "tenente": (
        "Il tenente era un ufficiale subalterno che comandava un plotone o, con maggiore "
        "anzianita, poteva essere vice-comandante di compagnia. Responsabile dell'impiego "
        "tattico del suo plotone, della disciplina e dell'addestramento. In combattimento "
        "era al fronte con i suoi uomini."
    ),
    "primo tenente": (
        "Il primo tenente era un tenente con maggiore anzianita, spesso vice-comandante "
        "di compagnia o comandante di plotone con responsabilita aggiuntive."
    ),
    "capitano": (
        "Il capitano era l'ufficiale comandante di compagnia (100-150 uomini). "
        "Responsabile dell'addestramento, disciplina e impiego operativo della sua unita, "
        "riceveva gli ordini dal battaglione e li traduceva in azioni tattiche sul terreno. "
        "In combattimento coordinava i plotoni dal posto di comando avanzato."
    ),
    # ── Ufficiali superiori ──
    "maggiore": (
        "Il maggiore era un ufficiale superiore, tipicamente vice-comandante di battaglione "
        "o comandante di battaglione. Responsabile della pianificazione operativa, "
        "del coordinamento tra le compagnie e dell'esecuzione degli ordini del reggimento."
    ),
    "tenente colonnello": (
        "Il tenente colonnello era un ufficiale superiore, comandante di battaglione "
        "o vice-comandante di reggimento. Pianificava e dirigeva le operazioni del battaglione "
        "(500-800 uomini), coordinando le compagnie sul terreno secondo gli ordini del reggimento."
    ),
    "colonnello": (
        "Il colonnello era l'ufficiale comandante di reggimento (2000-3000 uomini). "
        "Responsabile della pianificazione e direzione delle operazioni del reggimento, "
        "riceveva gli ordini dalla brigata o divisione e li traduceva in direttive "
        "per i battaglioni. Al fronte operava dal comando di reggimento."
    ),
    # ── Ufficiali generali ──
    "generale di brigata": (
        "Il generale di brigata comandava una brigata, grande unita composta da 2-3 reggimenti. "
        "Responsabile della pianificazione strategica a livello tattico, dirigeva le operazioni "
        "dalla retrovia del fronte."
    ),
    "generale di divisione": (
        "Il generale di divisione comandava una divisione, grande unita di 8000-12000 uomini "
        "composta da piu brigate. Definiva gli obiettivi operativi e coordinava l'impiego "
        "di fanteria, artiglieria e servizi."
    ),
    "generale di corpo d'armata": (
        "Il generale di corpo d'armata comandava un corpo d'armata, grande unita che "
        "raggruppava piu divisioni. Operava a livello strategico, definendo la condotta "
        "generale delle operazioni su un settore del fronte."
    ),
}

# Category-level descriptions (fallback when specific rank not found)
RANK_CATEGORY_DESCRIPTIONS: Dict[str, str] = {
    "truppa": (
        "Apparteneva alla truppa, la base dell'esercito: combattenti di prima linea "
        "che eseguivano gli ordini, occupavano le trincee e avanzavano negli assalti."
    ),
    "sottufficiali": (
        "Apparteneva ai sottufficiali, anello di congiunzione tra ufficiali e truppa: "
        "comandava plotoni o squadre, garantiva disciplina e addestramento, "
        "ed era il pilastro operativo del reparto."
    ),
    "ufficiali_inferiori": (
        "Apparteneva agli ufficiali inferiori: comandava plotoni o compagnie, "
        "responsabile dell'impiego tattico dei suoi uomini sul campo di battaglia."
    ),
    "ufficiali_superiori": (
        "Apparteneva agli ufficiali superiori: comandava battaglioni o reggimenti, "
        "pianificava e dirigeva le operazioni a livello tattico-operativo."
    ),
    "ufficiali_generali": (
        "Apparteneva agli ufficiali generali: comandava grandi unita (brigate, divisioni, "
        "corpi d'armata), definendo la condotta strategica delle operazioni."
    ),
    "ausiliarie": (
        "Apparteneva al personale ausiliario: infermiere, crocerossine o volontarie "
        "addette al soccorso e all'assistenza nei reparti sanitari."
    ),
}


UNIT_BRANCH_DESCRIPTIONS: Dict[str, str] = {
    "fanteria": (
        "La fanteria era l'arma principale del Regio Esercito, composta da reggimenti di fucilieri "
        "destinati al combattimento di prima linea. Durante la Prima Guerra Mondiale sostenne il "
        "maggior peso delle perdite nelle trincee del Carso e del Piave."
    ),
    "artiglieria": (
        "L'artiglieria forniva supporto di fuoco alle unita di fanteria, impiegando cannoni e obici "
        "per il bombardamento delle posizioni nemiche. Era organizzata in reggimenti di artiglieria "
        "da campagna, pesante campale e pesante."
    ),
    "bersaglieri": (
        "I bersaglieri erano truppe leggere addestrate per la rapidita e l'esplorazione, "
        "riconoscibili per la corsa invece della marcia e per il cappello piumato. "
        "Impiegati come avanguardia e in azioni di assalto."
    ),
    "alpini": (
        "Gli alpini erano il corpo specializzato nella guerra di montagna, impiegati sul fronte "
        "dolomitico e carnico. Addestrati per operazioni in alta quota, scalate e combattimento "
        "su ghiacciai."
    ),
    "granatieri": (
        "I granatieri erano truppe scelte di fanteria pesante, tradizionalmente impiegate in azioni "
        "di sfondamento e difesa di posizioni chiave."
    ),
    "cavalleria": (
        "La cavalleria svolgeva missioni di ricognizione, esplorazione e protezione dei fianchi. "
        "Con la guerra di trincea il suo ruolo diminui, ma resto impiegata in azioni di "
        "copertura e inseguimento."
    ),
    "genio": (
        "Il genio militare era responsabile di fortificazioni, ponti, gallerie, mine e opere "
        "difensive. Sul fronte dell'Isonzo costruì un'estesa rete di gallerie e caverne."
    ),
    "trasmissioni": (
        "Le truppe di trasmissioni garantivano le comunicazioni tra comandi e unita sul campo, "
        "impiegando telefoni da campo, segnalatori e piccioni viaggiatori."
    ),
    "sanita": (
        "Il servizio sanitario militare gestiva ospedali da campo, ospedaletti e ambulanze. "
        "I medici e gli infermieri operavano spesso sotto il fuoco per il soccorso dei feriti."
    ),
    "intendenza": (
        "L'intendenza assicurava il rifornimento di viveri, munizioni e uniformi alle truppe "
        "al fronte, gestendo la logistica dalle retrovie alle prime linee."
    ),
    "carabinieri": (
        "I carabinieri reali svolgevano funzioni di polizia militare, sicurezza delle retrovie "
        "e repressione del disfattismo. Alcuni reparti furono impiegati anche al fronte."
    ),
    "aviazione": (
        "L'aviazione militare, allora Corpo Aeronautico del Regio Esercito, svolgeva missioni "
        "di ricognizione, osservazione del tiro di artiglieria e bombardamento."
    ),
    "marina": (
        "La Regia Marina operava nell'Adriatico e nel Mediterraneo, con navi da battaglia, "
        "cacciatorpediniere e sommergibili. Contro la flotta austro-ungarica svolse un ruolo "
        "di blocco e controllo del mare."
    ),
    "fucilieri": (
        "I fucilieri erano truppe di fanteria leggera armate di fucile, impiegate in prima linea "
        "per il combattimento di trincea e l'assalto."
    ),
    "mitraglieri": (
        "I mitraglieri erano truppe specializzate nell'impiego delle mitragliatrici, "
        "armi automatiche fondamentali per la difesa di trincea e il fuoco di soppressione. "
        "Organizzati in reparti autonomi o aggregati a reggimenti di fanteria, "
        "gestivano postazioni fisse e mobili sul fronte."
    ),
    "lagunari": (
        "I lagunari erano truppe specializzate per operazioni nelle lagune e negli ambienti "
        "acquitrinosi, particolarmente nel territorio veneto e friulano."
    ),
    "paracadutisti": (
        "I paracadutisti costituivano truppe d'assalto aviotrasportate, addestrate per operazioni "
        "di conquista di obiettivi strategici dietro le linee nemiche."
    ),
}

UNIT_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "army": "Una grande unita operativa, comprendente piu corpi d'armata.",
    "corps": "Un corpo d'armata, grande unita che raggruppa piu divisioni.",
    "division": "Una divisione, grande unita autonoma composta da piu reggimenti.",
    "brigade": "Una brigata, unita tattica composta da piu reggimenti o battaglioni.",
    "regiment": "Un reggimento, unita fondamentale dell'esercito composta da piu battaglioni.",
    "battalion": "Un battaglione, unita tattica composta da piu compagnie.",
    "company": "Una compagnia, unita elementare composta da piu plotoni.",
    "battery": "Una batteria, unita di artiglieria equivalente alla compagnia di fanteria.",
    "squadron": "Uno squadrone, unita di cavalleria equivalente alla compagnia.",
    "platoon": "Un plotone, piccolo reparto operativo.",
    "squad": "Una squadra, la piu piccola unita di combattimento.",
    "group": "Un gruppo, unita tattica di dimensione variabile.",
    "command": "Un comando di unita, responsabile della direzione operativa.",
    "work_command": (
        "Un Arbeitskommando, comando di lavoro costituito dai tedeschi per gli IMI "
        "costretti al lavoro coatto in Germania e nei territori occupati."
    ),
    "unit_generic": "Un reparto militare, unita operativa di dimensione e composizione variabile.",
}


def _infer_war_period(claims: List[Dict[str, Any]]) -> str:
    """Infer war period from claim dates.

    Returns 'WWI', 'WWII', or 'unknown'.
    """
    wwi_keywords = {"prima guerra mondiale", "grande guerra", "1915", "1916", "1917", "1918",
                    "caporetto", "isonzo", "piave", "carso"}
    wwii_keywords = {"seconda guerra mondiale", "1940", "1941", "1942", "1943", "1944", "1945",
                     "imi", "internato militare", "armistizio", "8 settembre",
                     "stalag", "oflag", "campo prigionia", "lager", "prisoner of war",
                     "pow", "arbeitskommando", "campo concentramento"}

    for claim in claims:
        predicate = (claim.get("predicate", "") or "").lower().strip()
        value = (claim.get("value_normalized", "") or claim.get("value_raw", "") or "").lower()
        combined = f"{predicate} {value}"

        for kw in wwi_keywords:
            if kw in combined:
                return "WWI"
        for kw in wwii_keywords:
            if kw in combined:
                return "WWII"

    return "unknown"


def _validate_unit_snippet(
    snippet: str,
    title: str,
    unit_info: "UnitInfo",
    war_period: str,
) -> Dict[str, str]:
    """Validate that a Tavily snippet actually refers to the same unit and war period.

    Returns the snippet dict with a match_confidence field:
      - 'high': unit number matches AND war period matches
      - 'medium': unit number matches but war period unclear
      - 'low': unit number not found in snippet (possible mismatch)
      - 'rejected': snippet refers to a different war period or different unit
    """
    text = f"{title} {snippet}".lower()

    # Check war period
    if war_period == "WWI":
        wwi_markers = ["prima guerra", "grande guerra", "1915", "1916", "1917", "1918",
                       "caporetto", "isonzo", "piave", "carso"]
        wwii_markers = ["seconda guerra", "1940", "1941", "1942", "1943", "1944", "1945",
                        "imi", "internato militare", "8 settembre", "armistizio"]
        has_wwi = any(m in text for m in wwi_markers)
        has_wwii = any(m in text for m in wwii_markers)
        if has_wwii and not has_wwi:
            return {"match_confidence": "rejected",
                    "reason": "snippet refers to WWII, not WWI"}
    elif war_period == "WWII":
        wwi_markers = ["prima guerra", "grande guerra", "1915", "1916", "1917", "1918"]
        wwii_markers = ["seconda guerra", "1940", "1941", "1942", "1943", "1944", "1945",
                        "imi", "internato militare", "8 settembre", "armistizio"]
        has_wwii = any(m in text for m in wwii_markers)
        has_wwi = any(m in text for m in wwi_markers)
        if has_wwi and not has_wwii:
            return {"match_confidence": "rejected",
                    "reason": "snippet refers to WWI, not WWII"}

    # Check unit number match
    if unit_info.unit_number:
        num = unit_info.unit_number
        # Match patterns: "64°", "64 reggimento", "64° reggimento", "63° e 64°"
        import re as _re
        # Look for the number followed by degree symbol or reggimento/battaglione
        patterns = [
            rf"\b{num}\s*°",
            rf"\b{num}\s*°?\s*reggimento",
            rf"\b{num}\s*°?\s*battaglione",
            rf"\b{num}\s*°?\s*brigata",
            rf"\b{num}\s*°?\s*divisione",
            rf"\b{num}\s*°?\s*compagnia",
        ]
        has_number = any(_re.search(p, text) for p in patterns)
        if not has_number:
            # Also check if the original unit name appears in the snippet
            if unit_info.original.lower() in text:
                has_number = True

        if not has_number:
            return {"match_confidence": "low",
                    "reason": f"unit number {num} not found in snippet"}

    # Check branch match
    branch_match = True
    if unit_info.unit_branch and unit_info.unit_branch != "unknown":
        branch_it = {
            "fanteria": ["fanteria", "fante"],
            "artiglieria": ["artiglieria", "artigliere"],
            "bersaglieri": ["bersaglieri", "bersagliere"],
            "alpini": ["alpini", "alpino"],
            "granatieri": ["granatieri", "granatiere"],
            "cavalleria": ["cavalleria", "cavaliere"],
            "genio": ["genio", "geniere", "pontieri", "zappatori"],
            "mitraglieri": ["mitraglieri", "mitragliere", "mitragliatrici"],
        }.get(unit_info.unit_branch, [unit_info.unit_branch])
        branch_match = any(b in text for b in branch_it)

    if war_period != "unknown":
        if branch_match:
            return {"match_confidence": "high", "reason": ""}
        else:
            return {"match_confidence": "medium", "reason": "war period ok, branch not confirmed"}
    else:
        if branch_match:
            return {"match_confidence": "medium", "reason": "war period unknown, branch matches"}
        else:
            return {"match_confidence": "low", "reason": "war period unknown, branch not confirmed"}


def _search_unit_history(
    unit_info: "UnitInfo",
    war_period: str = "unknown",
    max_results: int = 5,
) -> List[Dict[str, str]]:
    """Search the web for historical context about a military unit.

    Returns a list of dicts with title, url, snippet, match_confidence.
    Only results with match_confidence 'high' or 'medium' are included.
    Falls back gracefully if Tavily is unavailable.
    """
    if not unit_info or not unit_info.original:
        return []

    # Build search query from unit info, scoped to war period
    query_parts = []
    if unit_info.unit_number:
        query_parts.append(f"{unit_info.unit_number} reggimento")
    elif unit_info.original:
        query_parts.append(unit_info.original)
    if unit_info.unit_branch and unit_info.unit_branch != "unknown":
        branch_it = {
            "fanteria": "fanteria",
            "artiglieria": "artiglieria",
            "bersaglieri": "bersaglieri",
            "alpini": "alpini",
            "granatieri": "granatieri",
            "cavalleria": "cavalleria",
            "genio": "genio",
            "trasmissioni": "trasmissioni",
            "sanita": "sanita",
            "intendenza": "intendenza",
            "carabinieri": "carabinieri",
            "aviazione": "aviazione",
            "marina": "marina",
            "fucilieri": "fucilieri",
            "mitraglieri": "mitraglieri",
            "lagunari": "lagunari",
            "paracadutisti": "paracadutisti",
        }.get(unit_info.unit_branch, unit_info.unit_branch)
        if unit_info.unit_number:
            query_parts.append(branch_it)
    if war_period == "WWI":
        query_parts.append("prima guerra mondiale")
    elif war_period == "WWII":
        query_parts.append("seconda guerra mondiale")
    else:
        query_parts.append("prima guerra mondiale")
    query = " ".join(query_parts)

    try:
        from web_search_providers import search_tavily
        resp = search_tavily(query, max_results=max_results, timeout=15)
        if not resp.ok:
            log.debug(f"Unit history search failed for '{query}': {resp.error}")
            return []
        results = []
        for r in resp.results[:max_results]:
            validation = _validate_unit_snippet(
                r.snippet or "", r.title or "", unit_info, war_period
            )
            confidence = validation["match_confidence"]
            if confidence == "rejected":
                log.debug(f"Unit history snippet rejected: {validation['reason']} | title={r.title}")
                continue
            results.append({
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet[:300] if r.snippet else "",
                "match_confidence": confidence,
            })
        # Sort by confidence: high first, then medium, then low
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        results.sort(key=lambda x: confidence_order.get(x["match_confidence"], 3))
        # Return top 3 validated results
        results = results[:3]
        log.debug(f"Unit history search '{query}': {len(results)} validated results "
                  f"(from {len(resp.results)} raw)")
        return results
    except Exception as e:
        log.debug(f"Unit history search skipped: {e}")
        return []


def build_military_context(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build military context from claims for narrator enrichment.

    Extracts rank and unit info from claims, and generates contextual
    descriptions of the military unit's role and branch.

    Args:
        claims: List of claim dicts (as built by _build_ai_input payload_claims)

    Returns:
        Dict with:
          - rank: {canonical, category, original}
          - unit: {original, type, number, branch, normalized, type_description, branch_description}
          - summary: human-readable context string for the AI
    """
    context: Dict[str, Any] = {}
    rank_info = None
    unit_info = None

    for claim in claims:
        predicate = (claim.get("predicate", "") or "").lower().strip()
        value = claim.get("value_normalized", "") or claim.get("value_raw", "") or ""

        if predicate in ("rank", "grado") and value and not rank_info:
            rank_info = parse_rank(value, "person_record")

        if predicate in ("military_unit", "reparto", "regiment", "assignment",
                         "military_branch", "arma", "work_command",
                         "arbeitskommando") and value and not unit_info:
            unit_info = parse_unit(value, "person_record")

    if rank_info:
        rank_role = RANK_ROLE_DESCRIPTIONS.get(rank_info.canonical, "")
        if not rank_role and rank_info.category in RANK_CATEGORY_DESCRIPTIONS:
            rank_role = RANK_CATEGORY_DESCRIPTIONS[rank_info.category]
        context["rank"] = {
            "canonical": rank_info.canonical,
            "category": rank_info.category,
            "original": rank_info.original,
            "role_description": rank_role,
        }

    if unit_info:
        branch_desc = UNIT_BRANCH_DESCRIPTIONS.get(unit_info.unit_branch, "")
        type_desc = UNIT_TYPE_DESCRIPTIONS.get(unit_info.unit_type, "")
        war_period = _infer_war_period(claims)
        web_ctx = _search_unit_history(unit_info, war_period=war_period)

        context["unit"] = {
            "original": unit_info.original,
            "type": unit_info.unit_type,
            "number": unit_info.unit_number,
            "branch": unit_info.unit_branch,
            "normalized": unit_info.normalized,
            "type_description": type_desc,
            "branch_description": branch_desc,
            "web_context": web_ctx,
        }

    # Build summary string
    parts = []
    if rank_info and rank_info.canonical:
        parts.append(f"Grado: {rank_info.canonical} (categoria: {rank_info.category})")
        rank_role = RANK_ROLE_DESCRIPTIONS.get(rank_info.canonical, "")
        if not rank_role and rank_info.category in RANK_CATEGORY_DESCRIPTIONS:
            rank_role = RANK_CATEGORY_DESCRIPTIONS[rank_info.category]
        if rank_role:
            parts.append(rank_role)
    if unit_info:
        if unit_info.unit_number:
            parts.append(f"Reparto: {unit_info.unit_number}° {unit_info.unit_type} {unit_info.unit_branch}")
        else:
            parts.append(f"Reparto: {unit_info.unit_type} {unit_info.unit_branch}")
        if unit_info.unit_branch and UNIT_BRANCH_DESCRIPTIONS.get(unit_info.unit_branch):
            parts.append(UNIT_BRANCH_DESCRIPTIONS[unit_info.unit_branch])
        if unit_info.unit_type and UNIT_TYPE_DESCRIPTIONS.get(unit_info.unit_type):
            parts.append(UNIT_TYPE_DESCRIPTIONS[unit_info.unit_type])

    if parts:
        context["summary"] = " ".join(parts)

    return context
