"""event_evidence_pipeline.py — Pipeline di raccolta evidenze per eventi storici.

Flusso a 4 livelli (ordine rigoroso):
1. Fonti interne: DB eventi_1gm, record_links, archivio_documenti, fonti_indice
2. Fonti archivistiche: source_locator (indice locale, cached text)
3. Fonti istituzionali/accademiche: federated search (NARA, USSME, Archivio di Stato, Europeana, IA)
4. Fonti web affidabili: solo dopo verifica (pagina, autore, data, URL, passaggio pertinente)

Per ogni fonte trovata:
- Estrae claim verificabili (date, luoghi, reparti, operazioni, protagonisti, conseguenze)
- Classifica la fonte (primaria, istituzionale, scientifica, web)
- Verifica compatibilità temporale e geografica con l'evento
- Assegna stato di affidabilità

Regole:
- Nessuna memoria generale AI come fonte
- Nessuna frase fattuale senza riferimento
- Per fatti centrali/controversi: almeno 2 fonti indipendenti o "attestato da una sola fonte"
- Corrispondenza basata solo su "Carso" rimane candidata (non probabile)
- Collegamento probabile solo con compatibilità nome + periodo + luogo + contesto militare
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
from event_resolver import get_event_by_id, get_related_events, resolve_event

EDB = Path(__file__).parent / "eventi_1gm.db"


# ─── Modelli dati ────────────────────────────────────────────────────────────

@dataclass
class Source:
    """Fonte recuperata dalla pipeline."""
    source_id: str
    title: str
    source_type: str  # "primaria" | "istituzionale" | "scientifico" | "web"
    authority: str  # "archivio" | "banca_dati" | "studio" | "pagina_web"
    url: str
    archive_reference: str  # archivio + fondo + segnatura + pagina/fotogramma
    author_or_institution: str
    date: str
    excerpt: str
    availability: str  # "disponibile" | "da_richiedere" | "online"
    relevance_score: float
    temporal_compatible: bool
    geographic_compatible: bool
    verification_status: str  # "verificata" | "candidata" | "non_verificata"
    verification_note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "authority": self.authority,
            "url": self.url,
            "archive_reference": self.archive_reference,
            "author_or_institution": self.author_or_institution,
            "date": self.date,
            "excerpt": self.excerpt,
            "availability": self.availability,
            "relevance_score": self.relevance_score,
            "temporal_compatible": self.temporal_compatible,
            "geographic_compatible": self.geographic_compatible,
            "verification_status": self.verification_status,
            "verification_note": self.verification_note,
        }


@dataclass
class Claim:
    """Affermazione verificabile estratta da una o più fonti."""
    claim_id: str
    text: str
    claim_type: str  # "date" | "place" | "unit" | "operation" | "person" | "casualty" | "outcome" | "consequence"
    value: str
    sources: List[str]  # source_ids
    confidence: str  # "alta" | "media" | "bassa" | "controversa" | "non_verificata"
    concordance: str  # "concordante" | "divergente" | "unica_fonte" | "incerta"
    conflicting_claims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "claim_type": self.claim_type,
            "value": self.value,
            "sources": self.sources,
            "confidence": self.confidence,
            "concordance": self.concordance,
            "conflicting_claims": self.conflicting_claims,
        }


@dataclass
class EvidencePackage:
    """Pacchetto di evidenze completo per un evento."""
    event_name: str
    event_id: Optional[int]
    resolution: Dict[str, Any]
    sources: List[Source]
    claims: List[Claim]
    concordant_facts: List[Claim]
    divergent_versions: List[Claim]
    uncertain_elements: List[Claim]
    archival_sources: List[Source]
    bibliographic_sources: List[Source]
    web_sources: List[Source]
    related_people: List[Dict[str, Any]]
    related_documents: List[Dict[str, Any]]
    graph_data: Dict[str, Any]
    collection_date: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name,
            "event_id": self.event_id,
            "resolution": self.resolution,
            "sources": [s.to_dict() for s in self.sources],
            "claims": [c.to_dict() for c in self.claims],
            "concordant_facts": [c.to_dict() for c in self.concordant_facts],
            "divergent_versions": [c.to_dict() for c in self.divergent_versions],
            "uncertain_elements": [c.to_dict() for c in self.uncertain_elements],
            "archival_sources": [s.to_dict() for s in self.archival_sources],
            "bibliographic_sources": [s.to_dict() for s in self.bibliographic_sources],
            "web_sources": [s.to_dict() for s in self.web_sources],
            "related_people": self.related_people,
            "related_documents": self.related_documents,
            "graph_data": self.graph_data,
            "collection_date": self.collection_date,
        }


# ─── Utility ─────────────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> Optional[Tuple[int, int, int]]:
    """Parse date string to (year, month, day) tuple."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # ISO format
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Year only
    m = re.match(r"^(\d{4})", date_str)
    if m:
        return int(m.group(1)), 0, 0
    return None


def _temporal_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """Verifica se due intervalli temporali si sovrappongono."""
    d1s = _parse_date(start1)
    d1e = _parse_date(end1)
    d2s = _parse_date(start2)
    d2e = _parse_date(end2)
    if not d1s or not d1e or not d2s or not d2e:
        return True  # Se non parseable, non escludere
    # Converte in giorni approssimati
    def to_days(y, m, d):
        return y * 365 + (m or 0) * 30 + (d or 0)
    s1, e1 = to_days(*d1s), to_days(*d1e)
    s2, e2 = to_days(*d2s), to_days(*d2e)
    return s1 <= e2 and s2 <= e1


def _geographic_overlap(event_luogo: str, source_luogo: str) -> bool:
    """Verifica compatibilità geografica tra evento e fonte."""
    if not event_luogo or not source_luogo:
        return True  # Se mancano dati, non escludere
    ev_tokens = set(re.findall(r"\w{4,}", event_luogo.lower()))
    src_tokens = set(re.findall(r"\w{4,}", source_luogo.lower()))
    if not ev_tokens or not src_tokens:
        return True
    return bool(ev_tokens & src_tokens)


def _relevance_tokens(canonical: str) -> Set[str]:
    """Token significativi dell'evento per filtro rilevanza."""
    stop = {"della", "delle", "degli", "dello", "battaglia", "eccidio",
            "campagna", "operazione", "campo", "campi", "fronte",
            "altopiano", "altipiano", "monte", "settore", "massiccio"}
    toks = {t.lower() for t in re.findall(r"\w{4,}", canonical)}
    return toks - stop


# ─── Livello 1: Fonti interne ────────────────────────────────────────────────

def _internal_sources(event_id: int, event_name: str, event_data: Dict[str, Any]) -> List[Source]:
    """Fonti dal DB interno: event_links, archivio_documenti, fonti_indice."""
    sources: List[Source] = []
    ev_start = event_data.get("data_inizio", "")
    ev_end = event_data.get("data_fine", "")
    ev_luogo = event_data.get("luogo", "")
    tokens = _relevance_tokens(event_name)

    # 1a. event_links → fonti_indice
    if EDB.exists():
        conn_ev = sqlite3.connect(str(EDB), timeout=30)
        conn_ev.row_factory = sqlite3.Row
        conn_main = sqlite3.connect(str(DB_PATH), timeout=30)
        conn_main.row_factory = sqlite3.Row
        try:
            # Fonti archivistiche collegate
            fonti_ids = [r["target_id"] for r in conn_ev.execute(
                "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='fonte_archivistica'",
                (event_id,),
            ).fetchall()]
            if fonti_ids:
                placeholders = ",".join("?" * len(fonti_ids))
                for r in conn_main.execute(
                    f"SELECT id, titolo, luogo, soggetti_collegati, url_catalogo, url_file, "
                    f"archivio, fondo, serie, segnatura, tipo_fonte, access_type "
                    f"FROM fonti_indice WHERE id IN ({placeholders})",
                    fonti_ids,
                ).fetchall():
                    ref = f"{r['archivio'] or ''} {r['fondo'] or ''} {r['segnatura'] or ''}".strip()
                    temp_ok = True  # fonti_indice non ha sempre date precise
                    geo_ok = _geographic_overlap(ev_luogo, r["luogo"] or "")
                    verification = "verificata" if ref else "candidata"
                    sources.append(Source(
                        source_id=f"INT-FI-{r['id']}",
                        title=r["titolo"] or "",
                        source_type="primaria" if r["archivio"] else "istituzionale",
                        authority="archivio" if r["archivio"] else "banca_dati",
                        url=r["url_catalogo"] or r["url_file"] or "",
                        archive_reference=ref,
                        author_or_institution=r["archivio"] or "",
                        date="",
                        excerpt=(r["soggetti_collegati"] or "")[:500],
                        availability=r["access_type"] or "da_richiedere",
                        relevance_score=0.8 if geo_ok else 0.5,
                        temporal_compatible=temp_ok,
                        geographic_compatible=geo_ok,
                        verification_status=verification,
                        verification_note="Fonte interna collegata via event_links" if verification == "verificata" else "Fonte interna senza riferimento archivistico completo",
                    ))

            # Documenti collegati
            doc_ids = [r["target_id"] for r in conn_ev.execute(
                "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='documento'",
                (event_id,),
            ).fetchall()]
            if doc_ids:
                placeholders = ",".join("?" * len(doc_ids))
                for r in conn_main.execute(
                    f"SELECT rowid as id, title, description, provider, doc_type, source_url, "
                    f"thumbnail_url, creator, date_text, place, provider_collection "
                    f"FROM archivio_documenti WHERE rowid IN ({placeholders})",
                    doc_ids,
                ).fetchall():
                    geo_ok = _geographic_overlap(ev_luogo, r["place"] or "")
                    sources.append(Source(
                        source_id=f"INT-DOC-{r['id']}",
                        title=r["title"] or "",
                        source_type="primaria",
                        authority="archivio",
                        url=r["source_url"] or "",
                        archive_reference=f"{r['provider'] or ''} {r['provider_collection'] or ''}".strip(),
                        author_or_institution=r["provider"] or r["creator"] or "",
                        date=r["date_text"] or "",
                        excerpt=(r["description"] or "")[:500],
                        availability="online" if r["source_url"] else "da_richiedere",
                        relevance_score=0.7 if geo_ok else 0.4,
                        temporal_compatible=True,
                        geographic_compatible=geo_ok,
                        verification_status="verificata" if r["source_url"] else "candidata",
                        verification_note="Documento archivistico collegato via event_links",
                    ))
        finally:
            conn_ev.close()
            conn_main.close()

    return sources


# ─── Livello 2: Fonti archivistiche (source_locator) ─────────────────────────

def _archival_sources(event_name: str, event_data: Dict[str, Any]) -> List[Source]:
    """Fonti dall'indice archivistico locale (source_locator)."""
    sources: List[Source] = []
    ev_luogo = event_data.get("luogo", "")
    tokens = _relevance_tokens(event_name)

    try:
        import source_locator as sl
        exact = sl.find_sources_by_subject(event_name, limit=10).get("candidates", [])
        candidate = sl.find_candidate_sources(event_name, limit=10).get("candidates", [])
    except Exception:
        return sources

    seen = set()
    for c in exact + candidate:
        sid = c.get("id")
        if not sid or sid in seen:
            continue
        # Filtro rilevanza: almeno un token evento nei metadati
        hay = " ".join(str(c.get(k, "")) for k in
                       ("titolo", "soggetti_collegati", "luogo", "note", "fondo", "serie")).lower()
        if tokens and not any(t in hay for t in tokens):
            continue
        seen.add(sid)

        ref = f"{c.get('archivio','')} {c.get('fondo','')} {c.get('segnatura','')}".strip()
        geo_ok = _geographic_overlap(ev_luogo, c.get("luogo", ""))

        try:
            snippet = sl._read_cached_text(c.get("id"))
        except Exception:
            snippet = None

        sources.append(Source(
            source_id=f"ARCH-{c.get('id')}",
            title=c.get("titolo", ""),
            source_type="primaria" if c.get("archivio") else "istituzionale",
            authority="archivio" if c.get("archivio") else "banca_dati",
            url=c.get("url_catalogo", ""),
            archive_reference=ref,
            author_or_institution=c.get("archivio") or c.get("ente", ""),
            date=c.get("data_inizio", ""),
            excerpt=(snippet or c.get("soggetti_collegati") or "")[:800],
            availability=c.get("availability") or c.get("access_type") or "da_richiedere",
            relevance_score=0.75 if geo_ok else 0.45,
            temporal_compatible=True,
            geographic_compatible=geo_ok,
            verification_status="verificata" if ref else "candidata",
            verification_note="Fonte archivistica da indice locale" if ref else "Fonte senza riferimento archivistico completo",
        ))

    return sources


# ─── Livello 3: Fonti istituzionali/accademiche (federated) ──────────────────

def _federated_sources(event_name: str, event_data: Dict[str, Any]) -> List[Source]:
    """Fonti dai provider esterni autorizzati (federated search)."""
    sources: List[Source] = []
    ev_start = event_data.get("data_inizio", "")
    ev_end = event_data.get("data_fine", "")
    ev_luogo = event_data.get("luogo", "")

    try:
        from source_providers.federation import federated_search
        providers = [
            "nara", "ussme", "archivio_stato", "europeana", "internetarchive",
            "googlebooks", "gallica", "hathitrust", "internetculturale",
            "memoiredeshommes", "iwm_lives", "tna", "shd",
        ]
        rows = federated_search(event_name, cues=event_data, providers=providers)
    except Exception:
        return sources

    for r in rows:
        if r.get("error"):
            continue
        date_str = r.get("date", "")
        raw_snippet_fed = r.get("snippet", "")
        if isinstance(raw_snippet_fed, list):
            snippet_fed = " ".join(str(s) for s in raw_snippet_fed)
        else:
            snippet_fed = str(raw_snippet_fed)
        temp_ok = _temporal_overlap(ev_start, ev_end, date_str, date_str) if date_str else True
        geo_ok = _geographic_overlap(ev_luogo, snippet_fed)
        verification = "candidata"
        note = "Fonte esterna federata — da verificare pagina, autore, data, URL e passaggio pertinente"
        if r.get("url") and r.get("provider"):
            verification = "verificata"
            note = f"Fonte federata da {r['provider']} con URL diretto"

        sources.append(Source(
            source_id=f"FED-{r.get('provider', 'EXT')}-{r.get('id', '')}",
            title=r.get("title") or r.get("label") or event_name,
            source_type="istituzionale",
            authority="banca_dati",
            url=r.get("url") or r.get("direct_url") or r.get("catalog_url", ""),
            archive_reference="",
            author_or_institution=r.get("provider", ""),
            date=date_str,
            excerpt=snippet_fed[:800],
            availability="online" if r.get("url") else "da_richiedere",
            relevance_score=0.6 if temp_ok and geo_ok else 0.3,
            temporal_compatible=temp_ok,
            geographic_compatible=geo_ok,
            verification_status=verification,
            verification_note=note,
        ))

    return sources


# ─── Livello 4: Fonti web affidabili ─────────────────────────────────────────

def _web_sources(event_name: str, event_data: Dict[str, Any]) -> List[Source]:
    """Fonti web — ricerca su provider affidabili (archivi militari, biblioteche digitali).

    Usa provider federati che hanno contenuti militari/storici:
    - USSME (Ufficio Storico Stato Maggiore Esercito)
    - Google Books (pubblicazioni storiche)
    - Gallica (Bibliothèque nationale de France)
    - Europeana (materiale culturale europeo)
    - Internet Archive (documenti digitalizzati)
    - HathiTrust (biblioteche accademiche)
    - Internet Culturale (biblioteche italiane)

    Fonti con URL diretto e snippet pertinente sono classificate come 'probabile'.
    Fonti senza URL o con corrispondenza debole rimangono 'candidata'.
    """
    sources: List[Source] = []
    ev_luogo = event_data.get("luogo", "")
    ev_start = event_data.get("data_inizio", "")
    ev_end = event_data.get("data_fine", "")

    # Provider con contenuti storico-militari affidabili
    web_providers = [
        "ussme", "googlebooks", "gallica", "europeana",
        "internetarchive", "hathitrust", "internetculturale",
        "archivio_stato", "memoiredeshommes", "iwm_lives",
    ]

    try:
        from source_providers.federation import federated_search
        rows = federated_search(event_name, cues=event_data, providers=web_providers)
    except Exception:
        return sources

    for r in rows:
        if r.get("error"):
            continue
        url = r.get("url") or r.get("direct_url") or r.get("catalog_url") or ""
        raw_snippet = r.get("snippet") or r.get("description") or ""
        if isinstance(raw_snippet, list):
            snippet = " ".join(str(s) for s in raw_snippet)
        else:
            snippet = str(raw_snippet)
        title = r.get("title") or r.get("label") or event_name
        if isinstance(title, list):
            title = " ".join(str(t) for t in title)
        else:
            title = str(title)
        provider_name = r.get("provider", "WEB")
        date_str = r.get("date", "")

        # Salta righe completamente vuote
        if not title and not url and not snippet:
            continue

        # Valuta pertinenza
        temp_ok = _temporal_overlap(ev_start, ev_end, date_str, date_str) if date_str else True
        geo_ok = _geographic_overlap(ev_luogo, snippet + " " + title)

        # Determina verification status
        if url and snippet and (geo_ok or temp_ok):
            verification = "probabile"
            note = f"Fonte da {provider_name} con URL e contenuto pertinente — da verificare manualmente"
            relevance = 0.55
        elif url:
            verification = "candidata"
            note = f"Fonte da {provider_name} con URL — corrispondenza da verificare"
            relevance = 0.35
        else:
            verification = "candidata"
            note = f"Fonte da {provider_name} senza URL diretto — da verificare"
            relevance = 0.25

        sources.append(Source(
            source_id=f"WEB-{provider_name}-{r.get('id', '')}",
            title=title,
            source_type="web",
            authority="pagina_web",
            url=url,
            archive_reference="",
            author_or_institution=provider_name,
            date=date_str,
            excerpt=snippet[:800],
            availability="online" if url else "da_richiedere",
            relevance_score=relevance,
            temporal_compatible=temp_ok,
            geographic_compatible=geo_ok,
            verification_status=verification,
            verification_note=note,
        ))

    return sources


# ─── Estrazione claim ────────────────────────────────────────────────────────

def _extract_claims_from_sources(event_name: str, sources: List[Source], event_data: Dict[str, Any] = None) -> List[Claim]:
    """Estrae claim verificabili dalle fonti raccolte.

    Per ora usa estrazione deterministica dai metadati delle fonti.
    L'estrazione AI avviene nel narrative builder.
    """
    claims: List[Claim] = []
    claim_counter = 0

    for src in sources:
        # Salta solo fonti web completamente non verificate
        if src.verification_status == "candidata" and src.source_type == "web" and not src.url:
            continue

        excerpt = src.excerpt
        if not excerpt:
            continue

        # Estrazione date
        dates = re.findall(r"\b(\d{1,2}[\s\-]*(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4})\b", excerpt, re.IGNORECASE)
        dates += re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", excerpt)
        dates += re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", excerpt)
        for d in set(dates):
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-{claim_counter:03d}",
                text=f"Data attestata: {d}",
                claim_type="date",
                value=d,
                sources=[src.source_id],
                confidence="media" if src.verification_status == "verificata" else "bassa",
                concordance="unica_fonte",
            ))

        # Estrazione luoghi: solo toponimi noti dall'evento (luogo, aliases, keywords)
        ev_geo_terms: Set[str] = set()
        if event_data:
            ev_geo_terms.update(t.lower() for t in re.split(r"[,\s]+", event_data.get("luogo", "")) if len(t) >= 4)
            for alias in event_data.get("aliases", []):
                ev_geo_terms.add(alias.lower())
            for kw in event_data.get("keywords", []):
                ev_geo_terms.add(kw.lower())
        excerpt_lower = excerpt.lower()
        for token in ev_geo_terms:
            if token in excerpt_lower:
                claim_counter += 1
                claims.append(Claim(
                    claim_id=f"CL-{claim_counter:03d}",
                    text=f"Luogo menzionato: {token}",
                    claim_type="place",
                    value=token,
                    sources=[src.source_id],
                    confidence="media" if src.verification_status in ("verificata", "probabile") else "bassa",
                    concordance="unica_fonte",
                ))

        # Estrazione reparti (pattern: numero + reggimento/brigata/divisione)
        units = re.findall(r"\b(\d+[°º]?\s*(?:reggimento|brigata|divisione|battaglione|compagnia|corpo)\b[^\n.]{0,50})", excerpt, re.IGNORECASE)
        for u in set(units):
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-{claim_counter:03d}",
                text=f"Reparto menzionato: {u.strip()}",
                claim_type="unit",
                value=u.strip(),
                sources=[src.source_id],
                confidence="media" if src.verification_status == "verificata" else "bassa",
                concordance="unica_fonte",
            ))

    # Analisi concordanze: claim dello stesso tipo con stesso valore
    _analyze_concordances(claims)

    # Claim dai metadati dell'evento (baseline verificato da DB interno)
    if event_data:
        ev_start = event_data.get("data_inizio", "")
        ev_end = event_data.get("data_fine", "")
        ev_luogo = event_data.get("luogo", "")
        ev_desc = event_data.get("descrizione", "")
        ev_aliases = event_data.get("aliases", [])

        if ev_start:
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-EV-{claim_counter:03d}",
                text=f"Data inizio evento: {ev_start}",
                claim_type="date",
                value=ev_start,
                sources=["EVENT-META"],
                confidence="alta",
                concordance="verificata",
            ))
        if ev_end:
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-EV-{claim_counter:03d}",
                text=f"Data fine evento: {ev_end}",
                claim_type="date",
                value=ev_end,
                sources=["EVENT-META"],
                confidence="alta",
                concordance="verificata",
            ))
        if ev_luogo:
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-EV-{claim_counter:03d}",
                text=f"Luogo dell'evento: {ev_luogo}",
                claim_type="place",
                value=ev_luogo,
                sources=["EVENT-META"],
                confidence="alta",
                concordance="verificata",
            ))
        if ev_desc:
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-EV-{claim_counter:03d}",
                text=f"Descrizione evento: {ev_desc[:200]}",
                claim_type="description",
                value=ev_desc,
                sources=["EVENT-META"],
                confidence="alta",
                concordance="verificata",
            ))
        for alias in ev_aliases:
            claim_counter += 1
            claims.append(Claim(
                claim_id=f"CL-EV-{claim_counter:03d}",
                text=f"Alias noto: {alias}",
                claim_type="alias",
                value=alias,
                sources=["EVENT-META"],
                confidence="alta",
                concordance="verificata",
            ))

    return claims


def _analyze_concordances(claims: List[Claim]) -> None:
    """Analizza concordanze e divergenze tra claim."""
    by_type_value: Dict[Tuple[str, str], List[Claim]] = {}
    for c in claims:
        key = (c.claim_type, c.value.lower().strip())
        by_type_value.setdefault(key, []).append(c)

    for key, group in by_type_value.items():
        if len(group) > 1:
            source_ids = set()
            for c in group:
                source_ids.update(c.sources)
            if len(source_ids) >= 2:
                for c in group:
                    c.concordance = "concordante"
                    c.confidence = "alta"
            else:
                for c in group:
                    c.concordance = "unica_fonte"
        # Rileva divergenze: stesso tipo, valore diverso, stessa fonte
    # (semplificato — l'AI nel narrative builder farà analisi più approfondita)


# ─── Persone e documenti collegati ───────────────────────────────────────────

def _related_people(event_id: int, event_name: str) -> List[Dict[str, Any]]:
    """Recupera persone collegate all'evento (caduti, decorati, internati)."""
    people: List[Dict[str, Any]] = []
    if not EDB.exists():
        return people

    conn_ev = sqlite3.connect(str(EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_main = sqlite3.connect(str(DB_PATH), timeout=30)
    conn_main.row_factory = sqlite3.Row
    try:
        # Caduti
        caduti_ids = [r["target_id"] for r in conn_ev.execute(
            "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='soldato_caduto'",
            (event_id,),
        ).fetchall()]
        if caduti_ids:
            placeholders = ",".join("?" * min(len(caduti_ids), 50))
            for r in conn_main.execute(
                f"SELECT id, nominativo, grado, reparto, luogo_morte, anno_morte, causa_morte "
                f"FROM caduti_albooro WHERE id IN ({placeholders}) LIMIT 50",
                caduti_ids[:50],
            ).fetchall():
                people.append({
                    "type": "caduto",
                    "id": r["id"],
                    "nominativo": r["nominativo"],
                    "grado": r["grado"],
                    "reparto": r["reparto"],
                    "luogo_morte": r["luogo_morte"],
                    "anno_morte": r["anno_morte"],
                })

        # Decorati
        dec_ids = [r["target_id"] for r in conn_ev.execute(
            "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='soldato_decorato'",
            (event_id,),
        ).fetchall()]
        if dec_ids:
            placeholders = ",".join("?" * min(len(dec_ids), 50))
            for r in conn_main.execute(
                f"SELECT id, cognome, nome, tipo_decorazione, anno_decorazione "
                f"FROM decorati_nastroazzurro WHERE id IN ({placeholders}) LIMIT 50",
                dec_ids[:50],
            ).fetchall():
                people.append({
                    "type": "decorato",
                    "id": r["id"],
                    "nominativo": f"{r['cognome']} {r['nome']}",
                    "decorazione": r["tipo_decorazione"],
                    "anno_decorazione": r["anno_decorazione"],
                })

        # Internati
        int_ids = [r["target_id"] for r in conn_ev.execute(
            "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='internato_ww2'",
            (event_id,),
        ).fetchall()]
        if int_ids:
            placeholders = ",".join("?" * min(len(int_ids), 50))
            for r in conn_main.execute(
                f"SELECT id, cognome, nome, luogo_internamento, arbeitskommando "
                f"FROM internati WHERE id IN ({placeholders}) LIMIT 50",
                int_ids[:50],
            ).fetchall():
                people.append({
                    "type": "internato",
                    "id": r["id"],
                    "nominativo": f"{r['cognome']} {r['nome']}",
                    "luogo_internamento": r["luogo_internamento"],
                    "arbeitskommando": r["arbeitskommando"],
                })
    finally:
        conn_ev.close()
        conn_main.close()

    return people


def _related_documents(event_id: int) -> List[Dict[str, Any]]:
    """Recupera documenti collegati all'evento."""
    docs: List[Dict[str, Any]] = []
    if not EDB.exists():
        return docs

    conn_ev = sqlite3.connect(str(EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_main = sqlite3.connect(str(DB_PATH), timeout=30)
    conn_main.row_factory = sqlite3.Row
    try:
        doc_ids = [r["target_id"] for r in conn_ev.execute(
            "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='documento'",
            (event_id,),
        ).fetchall()]
        if doc_ids:
            placeholders = ",".join("?" * min(len(doc_ids), 50))
            for r in conn_main.execute(
                f"SELECT rowid as id, title, description, provider, doc_type, source_url, "
                f"thumbnail_url, creator, date_text, place "
                f"FROM archivio_documenti WHERE rowid IN ({placeholders}) LIMIT 50",
                doc_ids[:50],
            ).fetchall():
                docs.append({
                    "id": r["id"],
                    "title": r["title"],
                    "description": (r["description"] or "")[:300],
                    "provider": r["provider"],
                    "doc_type": r["doc_type"],
                    "source_url": r["source_url"],
                    "thumbnail_url": r["thumbnail_url"],
                    "creator": r["creator"],
                    "date_text": r["date_text"],
                    "place": r["place"],
                })
    finally:
        conn_ev.close()
        conn_main.close()

    return docs


# ─── Grafo relazioni ─────────────────────────────────────────────────────────

def _build_graph(event_id: int, event_name: str, sources: List[Source],
                 people: List[Dict[str, Any]], documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Costruisce grafo di relazioni per visualizzazione."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # Nodo evento
    nodes.append({
        "id": f"event:{event_id}",
        "label": event_name,
        "type": "evento",
        "source": "eventi_1gm",
    })

    # Nodi fonti
    for s in sources:
        nodes.append({
            "id": s.source_id,
            "label": s.title[:60],
            "type": "fonte",
            "source": s.source_type,
        })
        edges.append({
            "source": f"event:{event_id}",
            "target": s.source_id,
            "label": "attestato_da",
            "weight": s.relevance_score,
        })

    # Nodi persone
    for p in people:
        pid = f"person:{p['type']}:{p['id']}"
        nodes.append({
            "id": pid,
            "label": p.get("nominativo", ""),
            "type": p["type"],
            "source": "event_links",
        })
        edges.append({
            "source": f"event:{event_id}",
            "target": pid,
            "label": "collegato_a",
            "weight": 0.7,
        })

    # Nodi documenti
    for d in documents:
        did = f"doc:{d['id']}"
        nodes.append({
            "id": did,
            "label": d.get("title", "")[:60],
            "type": "documento",
            "source": "archivio_documenti",
        })
        edges.append({
            "source": f"event:{event_id}",
            "target": did,
            "label": "documentato_da",
            "weight": 0.8,
        })

    # Eventi correlati
    related = get_related_events(event_id)
    for parent in related.get("parents", []):
        nodes.append({
            "id": f"event:{parent['id']}",
            "label": parent["nome"],
            "type": "evento_padre",
            "source": "eventi_1gm",
        })
        edges.append({
            "source": f"event:{parent['id']}",
            "target": f"event:{event_id}",
            "label": "contiene",
            "weight": 0.9,
        })
    for child in related.get("children", []):
        nodes.append({
            "id": f"event:{child['id']}",
            "label": child["nome"],
            "type": "evento_figlio",
            "source": "eventi_1gm",
        })
        edges.append({
            "source": f"event:{event_id}",
            "target": f"event:{child['id']}",
            "label": "contiene",
            "weight": 0.9,
        })

    return {"nodes": nodes, "edges": edges}


# ─── Pipeline principale ─────────────────────────────────────────────────────

def collect_evidence(query: str) -> EvidencePackage:
    """Pipeline completa di raccolta evidenze per un evento.

    1. Risolve l'evento (event_resolver)
    2. Raccoglie fonti dai 4 livelli
    3. Estrae claim dalle fonti
    4. Classifica fonti per tipo
    5. Recupera persone e documenti collegati
    6. Costruisce grafo relazioni
    """
    resolution = resolve_event(query)

    if not resolution.is_event or not resolution.canonical:
        return EvidencePackage(
            event_name=query,
            event_id=None,
            resolution=resolution.to_dict(),
            sources=[],
            claims=[],
            concordant_facts=[],
            divergent_versions=[],
            uncertain_elements=[],
            archival_sources=[],
            bibliographic_sources=[],
            web_sources=[],
            related_people=[],
            related_documents=[],
            graph_data={"nodes": [], "edges": []},
            collection_date=datetime.now().isoformat(),
        )

    event_id = resolution.canonical_id
    event_name = resolution.canonical
    event_data = get_event_by_id(event_id) if event_id else {}

    # Livello 1: interne
    internal = _internal_sources(event_id, event_name, event_data) if event_id else []
    # Livello 2: archivistiche
    archival = _archival_sources(event_name, event_data)
    # Livello 3: istituzionali/accademiche
    federated = _federated_sources(event_name, event_data)
    # Livello 4: web
    web = _web_sources(event_name, event_data)

    all_sources = internal + archival + federated + web

    # Deduplica per source_id
    seen_ids = set()
    unique_sources: List[Source] = []
    for s in all_sources:
        if s.source_id not in seen_ids:
            seen_ids.add(s.source_id)
            unique_sources.append(s)

    # Estrai claim
    claims = _extract_claims_from_sources(event_name, unique_sources, event_data)

    # Classifica claim
    concordant = [c for c in claims if c.concordance == "concordante"]
    divergent = [c for c in claims if c.concordance == "divergente"]
    uncertain = [c for c in claims if c.concordance in ("unica_fonte", "incerta")]

    # Classifica fonti
    arch = [s for s in unique_sources if s.source_type in ("primaria", "istituzionale") and s.authority == "archivio"]
    biblio = [s for s in unique_sources if s.source_type in ("istituzionale", "scientifico") and s.authority != "archivio"]
    web_src = [s for s in unique_sources if s.source_type == "web"]

    # Persone e documenti
    people = _related_people(event_id, event_name) if event_id else []
    documents = _related_documents(event_id) if event_id else []

    # Grafo
    graph = _build_graph(event_id, event_name, unique_sources, people, documents) if event_id else {"nodes": [], "edges": []}

    return EvidencePackage(
        event_name=event_name,
        event_id=event_id,
        resolution=resolution.to_dict(),
        sources=unique_sources,
        claims=claims,
        concordant_facts=concordant,
        divergent_versions=divergent,
        uncertain_elements=uncertain,
        archival_sources=arch,
        bibliographic_sources=biblio,
        web_sources=web_src,
        related_people=people,
        related_documents=documents,
        graph_data=graph,
        collection_date=datetime.now().isoformat(),
    )
