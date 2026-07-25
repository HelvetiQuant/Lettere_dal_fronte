"""event_resolver.py — Riconoscimento, disambiguazione e classificazione eventi.

Pipeline:
1. Riconosce che la ricerca riguarda un evento (vs persona/luogo).
2. Risolve nome, varianti e ambiguità contro eventi_1gm.
3. Distingue evento generale da singoli episodi (es. Carso vs Monte San Michele).
4. Per "Battaglia del Carso" avverte che può indicare un insieme di operazioni
   e propone distinzione fra evento generale, battaglie Isonzo, settori, singoli combattimenti.
5. Classifica ogni match con score, tipo (generale/specifico/ambiguo) e relazioni gerarchiche.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from database import DB_PATH

EDB = Path(__file__).parent / "eventi_1gm.db"

# ─── Classificazione eventi ──────────────────────────────────────────────────

# Eventi "generali" che contengono o sovrappongono altri eventi più specifici.
# Mappa: nome_evento_generale -> [nomi eventi specifici contenuti]
HIERARCHY: Dict[str, List[str]] = {
    "Battaglia del Carso": [
        "Monte San Michele",
        "Battaglie dell'Isonzo",
        "Settore di Tolmino",
    ],
    "Battaglie dell'Isonzo": [
        "Battaglia del Carso",
        "Monte San Michele",
        "Monte Nero",
        "Settore di Tolmino",
        "Battaglia di Caporetto",
    ],
    "Battaglia del Piave": [
        "Monte Grappa",
    ],
    "Battaglia di Vittorio Veneto": [
        "Monte Grappa",
        "Monte Pasubio",
    ],
    "Altopiano di Asiago": [],
    "Monte Grappa": [],
    "Monte Pasubio": [],
    "Monte San Michele": [],
    "Monte Col di Lana": [],
    "Monte Nero": [],
    "Settore di Tolmino": [],
    "Battaglia di Caporetto": [
        "Settore di Tolmino",
    ],
}

# Eventi che sono "collezioni" di operazioni — richiedono avviso di disambiguazione
AMBIGUOUS_COLLECTIONS: Set[str] = {
    "Battaglia del Carso",
    "Battaglie dell'Isonzo",
}

# Stopwords per normalizzazione nomi eventi
STOPWORDS: Set[str] = {
    "battaglia", "battaglie", "della", "delle", "degli", "dello", "di", "del",
    "eccidio", "campagna", "operazione", "campo", "campi", "fronte",
    "altopiano", "altipiano", "monte", "settore", "massiccio",
}


@dataclass
class EventMatch:
    """Singolo match di un evento dal DB."""
    id: int
    nome: str
    aliases: List[str]
    keywords: List[str]
    data_inizio: str
    data_fine: str
    luogo: str
    descrizione: str
    score: float
    match_source: str  # "exact" | "alias" | "keyword" | "partial"
    event_type: str  # "generale" | "specifico" | "ambiguo"
    parent_events: List[str] = field(default_factory=list)
    child_events: List[str] = field(default_factory=list)
    is_collection: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "aliases": self.aliases,
            "keywords": self.keywords,
            "data_inizio": self.data_inizio,
            "data_fine": self.data_fine,
            "luogo": self.luogo,
            "descrizione": self.descrizione,
            "score": self.score,
            "match_source": self.match_source,
            "event_type": self.event_type,
            "parent_events": self.parent_events,
            "child_events": self.child_events,
            "is_collection": self.is_collection,
        }


@dataclass
class ResolutionResult:
    """Risultato completo della risoluzione evento."""
    query: str
    is_event: bool
    canonical: Optional[str]
    canonical_id: Optional[int]
    matches: List[EventMatch]
    ambiguity_warning: Optional[str]
    proposed_distinctions: List[Dict[str, Any]]
    conflict: str  # "none" | "ambiguous_collection" | "multiple_matches" | "no_match"
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "is_event": self.is_event,
            "canonical": self.canonical,
            "canonical_id": self.canonical_id,
            "matches": [m.to_dict() for m in self.matches],
            "ambiguity_warning": self.ambiguity_warning,
            "proposed_distinctions": self.proposed_distinctions,
            "conflict": self.conflict,
            "confidence": self.confidence,
        }


# ─── Normalizzazione ─────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"[\s_]+", " ", s.strip().lower())


def _normalize_keep_case(s: str) -> str:
    return re.sub(r"[\s_]+", " ", s.strip())


def _tokens(s: str) -> Set[str]:
    return {t.lower() for t in re.findall(r"\w{3,}", s) if t.lower() not in STOPWORDS}


def _match_score(query: str, candidate: str) -> Tuple[float, str]:
    """Score di match: (score, source)."""
    q = _normalize(query)
    c = _normalize(candidate)
    if q == c:
        return 1.0, "exact"
    if q in c or c in q:
        return 0.85, "partial"
    q_tokens = _tokens(query)
    c_tokens = _tokens(candidate)
    if not q_tokens or not c_tokens:
        return 0.0, "none"
    inter = q_tokens & c_tokens
    if not inter:
        return 0.0, "none"
    score = len(inter) / max(len(q_tokens), len(c_tokens))
    return score, "keyword" if score >= 0.4 else "none"


# ─── Classificazione tipo evento ─────────────────────────────────────────────

def _classify_event(nome: str) -> str:
    """Classifica un evento come generale, specifico o ambiguo."""
    if nome in AMBIGUOUS_COLLECTIONS:
        return "ambiguo"
    if nome in HIERARCHY:
        children = HIERARCHY[nome]
        if children:
            return "generale"
    return "specifico"


def _get_children(nome: str) -> List[str]:
    return HIERARCHY.get(nome, [])


def _get_parents(nome: str) -> List[str]:
    parents = []
    for parent, children in HIERARCHY.items():
        if nome in children:
            parents.append(parent)
    return parents


# ─── Riconoscimento tipo query ───────────────────────────────────────────────

def _is_event_query(query: str) -> bool:
    """Heuristica: la query sembra riferirsi a un evento而非 persona o luogo."""
    q_lower = query.lower().strip()
    event_indicators = [
        "battaglia", "battaglie", "offensiva", "ritirata", "ripiegamento",
        "campagna", "operazione", "fronte", "settore", "eccidio",
        "prigionia", "internamento", "lavoro forzato", "campo",
        "caporetto", "isonzo", "carso", "piave", "grappa", "pasubio",
        "asiago", "ortigara", "cefalonia", "tobruk", "cassino",
        "mauthausen", "russia", "armir", "achse", "armistizio",
    ]
    for indicator in event_indicators:
        if indicator in q_lower:
            return True
    # Se contiene "monte" + nome geografico, probabile evento
    if re.match(r"^monte\s+\w", q_lower):
        return True
    return False


# ─── Risoluzione principale ──────────────────────────────────────────────────

def resolve_event(query: str) -> ResolutionResult:
    """Risolve una query in un evento canonico con disambiguazione completa.

    Passi:
    1. Verifica se la query è un evento.
    2. Cerca match nel DB eventi_1gm (exact, alias, keyword, partial).
    3. Classifica ogni match (generale/specifico/ambiguo).
    4. Se match ambiguo (es. Carso), genera avviso e proposte di distinzione.
    5. Ritorna risultato strutturato.
    """
    if not _is_event_query(query):
        return ResolutionResult(
            query=query,
            is_event=False,
            canonical=None,
            canonical_id=None,
            matches=[],
            ambiguity_warning=None,
            proposed_distinctions=[],
            conflict="none",
            confidence=0.0,
        )

    if not EDB.exists():
        return ResolutionResult(
            query=query,
            is_event=True,
            canonical=None,
            canonical_id=None,
            matches=[],
            ambiguity_warning="Database eventi_1gm non trovato.",
            proposed_distinctions=[],
            conflict="no_match",
            confidence=0.0,
        )

    conn = sqlite3.connect(str(EDB), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, nome, aliases, keywords, data_inizio, data_fine, luogo, descrizione "
            "FROM eventi_1gm ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    matches: List[EventMatch] = []
    for r in rows:
        alias_list = json.loads(r["aliases"]) if r["aliases"] else []
        kw_list = json.loads(r["keywords"]) if r["keywords"] else []
        all_names = [r["nome"]] + alias_list

        best_score = 0.0
        best_source = "none"
        for name in all_names:
            score, source = _match_score(query, name)
            if score > best_score:
                best_score = score
                best_source = source

        # Se nessun match diretto, prova keyword
        if best_score < 0.4:
            for kw in kw_list:
                score, source = _match_score(query, kw)
                if score > best_score:
                    best_score = score
                    best_source = "keyword"

        if best_score >= 0.4:
            nome = r["nome"]
            event_type = _classify_event(nome)
            children = _get_children(nome)
            parents = _get_parents(nome)
            is_collection = nome in AMBIGUOUS_COLLECTIONS

            matches.append(EventMatch(
                id=r["id"],
                nome=nome,
                aliases=alias_list,
                keywords=kw_list,
                data_inizio=r["data_inizio"],
                data_fine=r["data_fine"],
                luogo=r["luogo"],
                descrizione=r["descrizione"],
                score=round(best_score, 3),
                match_source=best_source,
                event_type=event_type,
                parent_events=parents,
                child_events=children,
                is_collection=is_collection,
            ))

    matches.sort(key=lambda m: m.score, reverse=True)

    if not matches:
        return ResolutionResult(
            query=query,
            is_event=True,
            canonical=None,
            canonical_id=None,
            matches=[],
            ambiguity_warning=None,
            proposed_distinctions=[],
            conflict="no_match",
            confidence=0.0,
        )

    top = matches[0]

    # Caso collezione ambigua (es. "Battaglia del Carso")
    if top.is_collection:
        warning = (
            f'"{top.nome}" può indicare un insieme di operazioni distinte. '
            f'Il termine copre un periodo ampio ({top.data_inizio} → {top.data_fine}) '
            f'e include settori geografici e singoli combattimenti diversi. '
            f'Vengono proposte le seguenti distinzioni:'
        )
        distinctions = []
        # Evento generale
        distinctions.append({
            "type": "evento_generale",
            "nome": top.nome,
            "periodo": f"{top.data_inizio} → {top.data_fine}",
            "luogo": top.luogo,
            "descrizione": top.descrizione,
        })
        # Eventi specifici figli
        for child_name in top.child_events:
            child_match = next((m for m in matches if m.nome == child_name), None)
            if child_match:
                distinctions.append({
                    "type": "episodio_specifico",
                    "nome": child_match.nome,
                    "periodo": f"{child_match.data_inizio} → {child_match.data_fine}",
                    "luogo": child_match.luogo,
                    "descrizione": child_match.descrizione,
                })
            else:
                # Cerca nel DB anche se non matchato
                distinctions.append({
                    "type": "episodio_specifico",
                    "nome": child_name,
                    "periodo": "vedere database",
                    "luogo": "",
                    "descrizione": "",
                })
        # Settori geografici (da keywords)
        for kw in top.keywords:
            if kw.lower() not in top.nome.lower() and kw not in [d["nome"] for d in distinctions]:
                distinctions.append({
                    "type": "settore_geografico",
                    "nome": kw,
                    "periodo": "",
                    "luogo": kw,
                    "descrizione": "",
                })

        return ResolutionResult(
            query=query,
            is_event=True,
            canonical=top.nome,
            canonical_id=top.id,
            matches=matches,
            ambiguity_warning=warning,
            proposed_distinctions=distinctions,
            conflict="ambiguous_collection",
            confidence=top.score,
        )

    # Multipli match con score simile
    if len(matches) > 1 and matches[1].score >= top.score - 0.1:
        warning = (
            f'La query "{query}" corrisponde a più eventi con score simile. '
            f'Risultati: {", ".join(m.nome for m in matches[:3])}. '
            f'È stato selezionato "{top.nome}" come migliore corrispondenza.'
        )
        return ResolutionResult(
            query=query,
            is_event=True,
            canonical=top.nome,
            canonical_id=top.id,
            matches=matches,
            ambiguity_warning=warning,
            proposed_distinctions=[],
            conflict="multiple_matches",
            confidence=top.score,
        )

    # Match singolo chiaro
    return ResolutionResult(
        query=query,
        is_event=True,
        canonical=top.nome,
        canonical_id=top.id,
        matches=matches,
        ambiguity_warning=None,
        proposed_distinctions=[],
        conflict="none",
        confidence=top.score,
    )


# ─── API di convenienza ──────────────────────────────────────────────────────

def resolve(query: str) -> Dict[str, Any]:
    """API semplice: ritorna dict con la risoluzione."""
    return resolve_event(query).to_dict()


def get_event_by_id(event_id: int) -> Optional[Dict[str, Any]]:
    """Recupera un evento per ID dal DB."""
    if not EDB.exists():
        return None
    conn = sqlite3.connect(str(EDB), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT id, nome, aliases, keywords, data_inizio, data_fine, luogo, descrizione "
            "FROM eventi_1gm WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not r:
            return None
        return {
            "id": r["id"],
            "nome": r["nome"],
            "aliases": json.loads(r["aliases"]) if r["aliases"] else [],
            "keywords": json.loads(r["keywords"]) if r["keywords"] else [],
            "data_inizio": r["data_inizio"],
            "data_fine": r["data_fine"],
            "luogo": r["luogo"],
            "descrizione": r["descrizione"],
        }
    finally:
        conn.close()


def get_related_events(event_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Recupera eventi correlati (padri e figli nella gerarchia)."""
    event = get_event_by_id(event_id)
    if not event:
        return {"parents": [], "children": []}

    nome = event["nome"]
    parent_names = _get_parents(nome)
    child_names = _get_children(nome)

    parents = []
    children = []

    if not EDB.exists():
        return {"parents": [], "children": []}

    conn = sqlite3.connect(str(EDB), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        for pname in parent_names:
            r = conn.execute("SELECT id, nome, data_inizio, data_fine, luogo FROM eventi_1gm WHERE nome = ?", (pname,)).fetchone()
            if r:
                parents.append(dict(r))
        for cname in child_names:
            r = conn.execute("SELECT id, nome, data_inizio, data_fine, luogo FROM eventi_1gm WHERE nome = ?", (cname,)).fetchone()
            if r:
                children.append(dict(r))
    finally:
        conn.close()

    return {"parents": parents, "children": children}
