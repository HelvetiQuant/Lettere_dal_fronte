"""event_link_audit.py — Riclassificazione e audit degli event_links esistenti.

Gli event_links attuali non vengono cancellati, ma:
1. Riclassificati con metodo, evidenza, compatibilità temporale e geografica.
2. Sottoposti a audit con stato di revisione e motivazione leggibile.
3. I collegamenti basati solo su corrispondenza di parola (es. "Carso") rimangono "candidati".
4. Il collegamento diventa "probabile" solo con compatibilità di nome, periodo, luogo e contesto militare.

Schema audit:
- match_method: "exact" | "alias" | "keyword" | "text_match" | "temporal_only"
- temporal_compatible: bool
- geographic_compatible: bool
- military_context: bool
- review_status: "candidate" | "probable" | "confirmed" | "rejected"
- review_reason: str (motivazione leggibile)
- audit_date: str
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from database import DB_PATH

EDB = Path(__file__).parent / "eventi_1gm.db"


@dataclass
class LinkAudit:
    """Audit di un singolo event_link."""
    link_id: int
    evento_id: int
    evento_nome: str
    target_table: str
    target_id: int
    link_type: str
    match_field: str
    match_value: str
    original_confidence: float
    match_method: str
    temporal_compatible: bool
    geographic_compatible: bool
    military_context: bool
    review_status: str  # "candidate" | "probable" | "confirmed" | "rejected"
    review_reason: str
    audit_date: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "link_id": self.link_id,
            "evento_id": self.evento_id,
            "evento_nome": self.evento_nome,
            "target_table": self.target_table,
            "target_id": self.target_id,
            "link_type": self.link_type,
            "match_field": self.match_field,
            "match_value": self.match_value,
            "original_confidence": self.original_confidence,
            "match_method": self.match_method,
            "temporal_compatible": self.temporal_compatible,
            "geographic_compatible": self.geographic_compatible,
            "military_context": self.military_context,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "audit_date": self.audit_date,
        }


@dataclass
class AuditReport:
    """Report completo di audit."""
    total_links: int
    audited: int
    candidates: int
    probable: int
    confirmed: int
    rejected: int
    by_link_type: Dict[str, Dict[str, int]]
    by_event: Dict[str, Dict[str, int]]
    issues: List[str]
    audits: List[LinkAudit]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_links": self.total_links,
            "audited": self.audited,
            "candidates": self.candidates,
            "probable": self.probable,
            "confirmed": self.confirmed,
            "rejected": self.rejected,
            "by_link_type": self.by_link_type,
            "by_event": self.by_event,
            "issues": self.issues,
            "audits": [a.to_dict() for a in self.audits],
        }


# ─── Utility ─────────────────────────────────────────────────────────────────

MILITARY_KEYWORDS: Set[str] = {
    "reggimento", "brigata", "divisione", "battaglione", "compagnia",
    "corpo", "armata", "reparto", "fanteria", "artiglieria",
    "cavalleria", "genio", "alpini", "bersaglieri", "granatieri",
    "caporetto", "isonzo", "piave", "grappa", "carso", "pasubio",
    "asiago", "ortigara", "cefalonia", "tobruk", "cassino",
    "mauthausen", "russia", "armir", "achse", "armistizio",
    "prigionia", "internamento", "lager", "campo",
    "caduto", "caduti", "decorato", "decorati", "medaglia",
    "croce", "guerra", "fronte", "trincea", "offensiva",
    "ritirata", "ripiegamento", "offensiva",
}


def _has_military_context(text: str) -> bool:
    """Verifica se il testo ha contesto militare."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in MILITARY_KEYWORDS)


def _parse_date(date_str: str) -> Optional[Tuple[int, int, int]]:
    if not date_str:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", date_str.strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"^(\d{4})", date_str.strip())
    if m:
        return int(m.group(1)), 0, 0
    return None


def _temporal_overlap(start1: str, end1: str, year: Optional[int] = None) -> bool:
    """Verifica compatibilità temporale tra evento e record."""
    if not year:
        return True  # Senza anno, non escludere
    d1s = _parse_date(start1)
    d1e = _parse_date(end1)
    if not d1s or not d1e:
        return True
    return d1s[0] <= year <= d1e[0]


def _geographic_overlap(event_luogo: str, record_text: str) -> bool:
    """Verifica compatibilità geografica."""
    if not event_luogo or not record_text:
        return True
    ev_tokens = set(re.findall(r"\w{4,}", event_luogo.lower()))
    rec_tokens = set(re.findall(r"\w{4,}", record_text.lower()))
    if not ev_tokens:
        return True
    return bool(ev_tokens & rec_tokens)


def _classify_match_method(match_field: str, match_value: str, link_type: str) -> str:
    """Classifica il metodo di match usato per il link."""
    if match_field == "luogo_morte":
        return "exact" if match_value and len(match_value) > 3 else "text_match"
    if match_field == "anno_decorazione":
        return "temporal_only"
    if match_field == "text_match":
        return "text_match"
    if match_field == "titolo_luogo_soggetti":
        return "text_match"
    if match_field == "luogo_text":
        return "text_match"
    if match_field == "cimitero":
        return "exact"
    if match_field == "luogo_sepoltura":
        return "exact"
    return "unknown"


# ─── Audit principale ────────────────────────────────────────────────────────

def audit_all_links() -> AuditReport:
    """Esegue audit completo di tutti gli event_links esistenti.

    Non modifica i dati: legge e classifica.
    """
    if not EDB.exists():
        return AuditReport(
            total_links=0, audited=0, candidates=0, probable=0,
            confirmed=0, rejected=0, by_link_type={}, by_event={},
            issues=["Database eventi_1gm.db non trovato"], audits=[],
        )

    conn_ev = sqlite3.connect(str(EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_main = sqlite3.connect(str(DB_PATH), timeout=30)
    conn_main.row_factory = sqlite3.Row

    audits: List[LinkAudit] = []
    issues: List[str] = []
    now = datetime.now().isoformat()

    try:
        # Carica eventi
        events = {r["id"]: dict(r) for r in conn_ev.execute(
            "SELECT id, nome, aliases, keywords, data_inizio, data_fine, luogo FROM eventi_1gm"
        ).fetchall()}

        # Carica tutti i link
        links = conn_ev.execute(
            "SELECT id, evento_id, target_table, target_id, link_type, match_field, match_value, confidence "
            "FROM event_links ORDER BY id"
        ).fetchall()

        for link in links:
            ev = events.get(link["evento_id"])
            if not ev:
                issues.append(f"Link {link['id']}: evento_id {link['evento_id']} non trovato")
                continue

            ev_luogo = ev["luogo"] or ""
            ev_start = ev["data_inizio"] or ""
            ev_end = ev["data_fine"] or ""
            match_value = link["match_value"] or ""
            match_field = link["match_field"] or ""

            # Recupera dati del record target
            record_text = ""
            record_year = None
            target_table = link["target_table"]
            target_id = link["target_id"]

            try:
                if target_table == "caduti_albooro":
                    r = conn_main.execute(
                        "SELECT nominativo, luogo_morte, anno_morte, reparto FROM caduti_albooro WHERE id=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['nominativo']} {r['luogo_morte']} {r['reparto']}"
                        anno = r["anno_morte"]
                        if anno and re.match(r"^\d{4}$", anno):
                            record_year = int(anno)
                elif target_table == "decorati_nastroazzurro":
                    r = conn_main.execute(
                        "SELECT cognome, nome, anno_decorazione FROM decorati_nastroazzurro WHERE id=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['cognome']} {r['nome']}"
                        anno = r["anno_decorazione"]
                        if anno and re.match(r"^\d{4}$", anno):
                            record_year = int(anno)
                elif target_table == "archivio_documenti":
                    r = conn_main.execute(
                        "SELECT title, description, place, creator, date_text FROM archivio_documenti WHERE rowid=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['title']} {r['description']} {r['place']}"
                elif target_table == "fonti_indice":
                    r = conn_main.execute(
                        "SELECT titolo, luogo, soggetti_collegati FROM fonti_indice WHERE id=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['titolo']} {r['luogo']} {r['soggetti_collegati']}"
                elif target_table == "internati":
                    r = conn_main.execute(
                        "SELECT cognome, nome, luogo_cattura, luogo_internamento, arbeitskommando, raw_text FROM internati WHERE id=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['cognome']} {r['nome']} {r['luogo_cattura']} {r['luogo_internamento']} {r['arbeitskommando']} {r['raw_text']}"
                elif target_table == "caduti_cwgc":
                    r = conn_main.execute(
                        "SELECT nome, cimitero, paese_cimitero FROM caduti_cwgc WHERE id=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['nome']} {r['cimitero']} {r['paese_cimitero']}"
                elif target_table == "caduti_ministero":
                    r = conn_main.execute(
                        "SELECT nome, luogo_sepoltura, nazione_decesso FROM caduti_ministero WHERE id=?",
                        (target_id,),
                    ).fetchone()
                    if r:
                        record_text = f"{r['nome']} {r['luogo_sepoltura']} {r['nazione_decesso']}"
            except Exception:
                pass

            # Classificazione
            method = _classify_match_method(match_field, match_value, link["link_type"])
            temp_ok = _temporal_overlap(ev_start, ev_end, record_year)
            geo_ok = _geographic_overlap(ev_luogo, record_text)
            military = _has_military_context(record_text) or _has_military_context(match_value)

            # Review status
            if method == "exact" and temp_ok and geo_ok and military:
                status = "probable"
                reason = f"Match esatto su {match_field} con compatibilità temporale, geografica e contesto militare."
            elif method == "temporal_only":
                status = "candidate"
                reason = f"Match basato solo su anno ({match_value}). Senza compatibilità geografica o di reparto, rimane candidato."
            elif method == "text_match" and not geo_ok:
                status = "candidate"
                reason = f"Match testuale su '{match_value}' senza conferma geografica o temporale. Rimane candidato."
            elif method == "text_match" and geo_ok and temp_ok and military:
                status = "probable"
                reason = f"Match testuale con compatibilità geografica, temporale e contesto militare."
            elif method == "text_match" and (geo_ok or temp_ok):
                status = "candidate"
                reason = f"Match testuale con compatibilità parziale ({'geo' if geo_ok else 'temp'}). Rimane candidato."
            elif not military:
                status = "candidate"
                reason = "Senza contesto militare nel record, il collegamento rimane candidato."
            else:
                status = "candidate"
                reason = "Compatibilità insufficiente per promuovere a probabile."

            # Caso speciale: corrispondenza solo su "Carso"
            if match_value and match_value.lower().strip() == "carso":
                status = "candidate"
                reason = "Corrispondenza basata solo sulla parola 'Carso' — rimane candidato finché non verificato nome, periodo, luogo e contesto militare."

            audits.append(LinkAudit(
                link_id=link["id"],
                evento_id=link["evento_id"],
                evento_nome=ev["nome"],
                target_table=target_table,
                target_id=target_id,
                link_type=link["link_type"],
                match_field=match_field,
                match_value=match_value,
                original_confidence=link["confidence"],
                match_method=method,
                temporal_compatible=temp_ok,
                geographic_compatible=geo_ok,
                military_context=military,
                review_status=status,
                review_reason=reason,
                audit_date=now,
            ))

    finally:
        conn_ev.close()
        conn_main.close()

    # Statistiche
    by_type: Dict[str, Dict[str, int]] = {}
    by_event: Dict[str, Dict[str, int]] = {}
    candidates = probable = confirmed = rejected = 0

    for a in audits:
        lt = a.link_type
        by_type.setdefault(lt, {"candidate": 0, "probable": 0, "confirmed": 0, "rejected": 0})
        by_type[lt][a.review_status] = by_type[lt].get(a.review_status, 0) + 1

        en = a.evento_nome
        by_event.setdefault(en, {"candidate": 0, "probable": 0, "confirmed": 0, "rejected": 0})
        by_event[en][a.review_status] = by_event[en].get(a.review_status, 0) + 1

        if a.review_status == "candidate":
            candidates += 1
        elif a.review_status == "probable":
            probable += 1
        elif a.review_status == "confirmed":
            confirmed += 1
        elif a.review_status == "rejected":
            rejected += 1

    return AuditReport(
        total_links=len(audits),
        audited=len(audits),
        candidates=candidates,
        probable=probable,
        confirmed=confirmed,
        rejected=rejected,
        by_link_type=by_type,
        by_event=by_event,
        issues=issues,
        audits=audits,
    )


def audit_event(event_id: int) -> List[LinkAudit]:
    """Audit dei link di un singolo evento."""
    if not EDB.exists():
        return []

    conn_ev = sqlite3.connect(str(EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    try:
        links = conn_ev.execute(
            "SELECT id, evento_id, target_table, target_id, link_type, match_field, match_value, confidence "
            "FROM event_links WHERE evento_id=? ORDER BY id",
            (event_id,),
        ).fetchall()
    finally:
        conn_ev.close()

    # Ri Usa la logica di audit_all_links ma filtrata
    full_report = audit_all_links()
    return [a for a in full_report.audits if a.evento_id == event_id]


def get_audit_summary() -> Dict[str, Any]:
    """Riepilogo sintetico dell'audit."""
    report = audit_all_links()
    return {
        "total_links": report.total_links,
        "candidates": report.candidates,
        "probable": report.probable,
        "confirmed": report.confirmed,
        "rejected": report.rejected,
        "by_link_type": report.by_link_type,
        "by_event": report.by_event,
        "issues": report.issues,
    }
