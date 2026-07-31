"""Archive Jurisdiction Registry — verified mapping of comune → archival institute.

This replaces the V3 template-based approach of generating
"Archivio di Stato di {birth_place}" which invented non-existent institutes.

The registry maps:
  comune storico → provincia/circondario → distretto militare → istituto di conservazione

If a mapping is not verified, the system outputs a generic statement
rather than inventing an institute name, fondo, or URL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchiveJurisdiction:
    """Verified mapping of a comune to its archival jurisdiction."""
    comune: str
    provincia: str
    distretto_militare: str
    archivio_di_stato: str  # official name, verified
    archivio_di_stato_url: str  # official URL, verified
    fondo_matricolare: str  # verified fondo name
    note: str = ""


# ─── Registry ─────────────────────────────────────────────────────────────────
# Only verified mappings are included. Unmapped comuni get a generic statement.

_REGISTRY: Dict[str, ArchiveJurisdiction] = {
    "canneto sull'oglio": ArchiveJurisdiction(
        comune="Canneto sull'Oglio",
        provincia="Mantova",
        distretto_militare="Mantova",
        archivio_di_stato="Archivio di Stato di Mantova",
        archivio_di_stato_url="http://www.archiviodistatomantova.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Mantova, conservato presso l'Archivio di Stato di Mantova",
    ),
    "pasiano di pordenone": ArchiveJurisdiction(
        comune="Pasiano di Pordenone",
        provincia="Pordenone",
        distretto_militare="Pordenone",
        archivio_di_stato="Archivio di Stato di Pordenone",
        archivio_di_stato_url="http://www.archiviodistatopordenone.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Pordenone",
    ),
    "magnano in riviera": ArchiveJurisdiction(
        comune="Magnano in Riviera",
        provincia="Udine",
        distretto_militare="Udine",
        archivio_di_stato="Archivio di Stato di Udine",
        archivio_di_stato_url="https://archiviodistatoudine.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Udine",
    ),
    "ronciglione": ArchiveJurisdiction(
        comune="Ronciglione",
        provincia="Viterbo",
        distretto_militare="Viterbo",
        archivio_di_stato="Archivio di Stato di Viterbo",
        archivio_di_stato_url="https://archiviodistatoviterbo.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Viterbo",
    ),
    "larino": ArchiveJurisdiction(
        comune="Larino",
        provincia="Campobasso",
        distretto_militare="Campobasso",
        archivio_di_stato="Archivio di Stato di Campobasso",
        archivio_di_stato_url="https://archiviodistatocampobasso.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Campobasso",
    ),
    "longobucco": ArchiveJurisdiction(
        comune="Longobucco",
        provincia="Cosenza",
        distretto_militare="Cosenza",
        archivio_di_stato="Archivio di Stato di Cosenza",
        archivio_di_stato_url="https://archiviodistatocosenza.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Cosenza",
    ),
    "lioni": ArchiveJurisdiction(
        comune="Lioni",
        provincia="Avellino",
        distretto_militare="Avellino",
        archivio_di_stato="Archivio di Stato di Avellino",
        archivio_di_stato_url="https://archiviodistatoavellino.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Avellino",
    ),
    "misterbianco": ArchiveJurisdiction(
        comune="Misterbianco",
        provincia="Catania",
        distretto_militare="Catania",
        archivio_di_stato="Archivio di Stato di Catania",
        archivio_di_stato_url="https://archiviodistatocatania.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Catania",
    ),
    "roccalbegna": ArchiveJurisdiction(
        comune="Roccalbegna",
        provincia="Grosseto",
        distretto_militare="Grosseto",
        archivio_di_stato="Archivio di Stato di Grosseto",
        archivio_di_stato_url="https://archiviodistatogrosseto.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Grosseto",
    ),
    "falcade": ArchiveJurisdiction(
        comune="Falcade",
        provincia="Belluno",
        distretto_militare="Belluno",
        archivio_di_stato="Archivio di Stato di Belluno",
        archivio_di_stato_url="https://archiviodistatobelluno.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Belluno",
    ),
    "bitonto": ArchiveJurisdiction(
        comune="Bitonto",
        provincia="Bari",
        distretto_militare="Bari",
        archivio_di_stato="Archivio di Stato di Bari",
        archivio_di_stato_url="https://archiviodistatobari.beniculturali.it/",
        fondo_matricolare="Rubriche Fogli Matricolari",
        note="Distretto militare di Bari",
    ),
}


def _normalize_comune(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def get_jurisdiction(birth_place: str) -> Optional[ArchiveJurisdiction]:
    """Get verified archival jurisdiction for a comune.

    Returns None if the comune is not in the verified registry.
    The caller must handle None by outputting a generic statement.
    """
    if not birth_place:
        return None
    key = _normalize_comune(birth_place)
    return _REGISTRY.get(key)


def generate_archival_suggestions(
    birth_place: str,
    birth_year: str,
    full_name: str,
    paternity: str = "",
    conflict: str = "ww1",
    research_goal: str = "",
) -> List[dict]:
    """Generate archival suggestions using ONLY verified registry data.

    If the comune is not in the registry, outputs a generic statement
    rather than inventing an institute name.
    """
    suggestions = []
    base_data = f"Nome: {full_name}"
    if birth_year:
        base_data += f", classe {birth_year}"
    if birth_place:
        base_data += f", nato a {birth_place}"
    if paternity:
        base_data += f", di {paternity}"

    # 1. Archivio di Stato (from verified registry)
    jurisdiction = get_jurisdiction(birth_place)
    if jurisdiction:
        suggestions.append({
            "ente": jurisdiction.archivio_di_stato,
            "fondo": jurisdiction.fondo_matricolare,
            "documento_richiesto": "Foglio matricolare",
            "dati_conosciuti": base_data,
            "motivazione": f"Ricostruzione percorso militare — distretto di {jurisdiction.distretto_militare}",
            "url": jurisdiction.archivio_di_stato_url,
            "verified": True,
        })
    else:
        # Generic statement — no invented institute
        suggestions.append({
            "ente": "Verificare presso l'Archivio di Stato territorialmente competente",
            "fondo": "Ruoli/Fogli Matricolari",
            "documento_richiesto": "Foglio matricolare",
            "dati_conosciuti": base_data,
            "motivazione": f"Verificare il distretto militare competente per il comune di {birth_place} e consultare l'Archivio di Stato corrispondente",
            "url": "",
            "verified": False,
        })

    # 2. Archivio Centrale dello Stato — Roma (always valid, verified)
    suggestions.append({
        "ente": "Archivio Centrale dello Stato — Roma",
        "fondo": "Ministero della Guerra — Ruoli Matricolari",
        "documento_richiesto": "Ruolo matricolare",
        "dati_conosciuti": base_data,
        "motivazione": "Verifica matricola e reparto di assegnazione",
        "url": "https://acs.beniculturali.it/",
        "verified": True,
    })

    # 3. ICRC — only for prisoner/dispersi research goals
    from source_capability_registry import is_eligible_for_suggestion
    if is_eligible_for_suggestion("icrc_ww1", conflict, research_goal):
        fondo = "Prisoners of the First World War" if conflict == "ww1" else "WW2 Prisoners"
        suggestions.append({
            "ente": "ICRC — International Committee of the Red Cross",
            "fondo": fondo,
            "documento_richiesto": "Scheda prigioniero",
            "dati_conosciuti": base_data,
            "motivazione": "Verifica cattura, campo di prigionia, trasferimenti",
            "url": "https://grandeguerre.icrc.org/" if conflict == "ww1" else "https://www.icrc.org/",
            "verified": True,
        })

    # 4. LeBI/ANRP — only for WWII targets (capability routing)
    if is_eligible_for_suggestion("lebi", conflict, research_goal):
        suggestions.append({
            "ente": "ANRP — Lessico Biografico degli IMI",
            "fondo": "Schede biografiche internati militari italiani",
            "documento_richiesto": "Scheda biografica",
            "dati_conosciuti": base_data,
            "motivazione": "Verifica internamento, campi attraversati, rimpatrio",
            "url": "https://www.lessicobiograficoimi.it/",
            "verified": True,
        })

    # 5. USSME — for operational history of specific units (not personal files)
    suggestions.append({
        "ente": "Ufficio Storico dello Stato Maggiore dell'Esercito (USSME)",
        "fondo": "Storia e documentazione operativa dei reparti",
        "documento_richiesto": "Diari storici di reparto (non fascicoli personali)",
        "dati_conosciuti": base_data,
        "motivazione": "Documentazione operativa del reparto — non deposito di fascicoli personali",
        "url": "http://www.esercito.difesa.it/storia/Pagine/default.aspx",
        "verified": True,
    })

    return suggestions
