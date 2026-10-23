"""Authority Registry — versioned authority records for acronyms, archives, and sources.

Prevents AI hallucination of:
- Acronym expansions (M.T., Btg., etc.)
- Archive names and competences
- Source suggestions without capability match

The AI model receives only authority_ids from this registry.
It cannot expand acronyms or suggest archives not in this registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


REGISTRY_VERSION = "1.0.0"


@dataclass
class AuthorityRecord:
    """An authority record for an acronym, archive, or source."""
    authority_id: str
    record_type: str  # acronym | archive | source | military_unit
    label: str  # canonical label
    expansion: str = ""  # full expansion if acronym
    description: str = ""
    conflict_scope: List[str] = field(default_factory=list)  # WWI, WWII, both
    geographic_scope: str = ""  # Italy, Germany, etc.
    capability: str = ""  # matricolari, diari, prigionia, sepoltura, etc.
    verified: bool = True
    notes: str = ""


# ─── Acronym authority records ───────────────────────────────────────────────

_ACRONYMS: Dict[str, AuthorityRecord] = {
    "MT": AuthorityRecord(
        authority_id="acr_mt",
        record_type="acronym",
        label="M.T.",
        expansion="",  # NOT expanded — no authority proof
        description="Sigla non espansa. Non assumere 'Mitraglieri Truppe' o altre espansioni senza authority record.",
        conflict_scope=["WWI"],
        verified=True,
        notes="Riscontrata in reparti della Grande Guerra. Espansione non provata.",
    ),
    "BTG": AuthorityRecord(
        authority_id="acr_btg",
        record_type="acronym",
        label="Btg.",
        expansion="Battaglione",
        description="Battaglione — unità tattica intermedia.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "RGMT": AuthorityRecord(
        authority_id="acr_rgmt",
        record_type="acronym",
        label="Rgmt.",
        expansion="Reggimento",
        description="Reggimento — grande unità militare.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "FANTR": AuthorityRecord(
        authority_id="acr_fantr",
        record_type="acronym",
        label="Fantr.",
        expansion="Fanteria",
        description="Fanteria — arma dell'Esercito.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "ALP": AuthorityRecord(
        authority_id="acr_alp",
        record_type="acronym",
        label="Alp.",
        expansion="Alpini",
        description="Alpini — truppe da montagna.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "ART": AuthorityRecord(
        authority_id="acr_art",
        record_type="acronym",
        label="Art.",
        expansion="Artiglieria",
        description="Artiglieria — arma dell'Esercito.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "GEN": AuthorityRecord(
        authority_id="acr_gen",
        record_type="acronym",
        label="Gen.",
        expansion="Genio",
        description="Genio — arma dell'Esercito.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "IMI": AuthorityRecord(
        authority_id="acr_imi",
        record_type="acronym",
        label="IMI",
        expansion="Internati Militari Italiani",
        description="Internati Militari Italiani — soldati italiani internati in Germania dopo l'8 settembre 1943.",
        conflict_scope=["WWII"],
        verified=True,
    ),
    "ANRP": AuthorityRecord(
        authority_id="acr_anrp",
        record_type="acronym",
        label="ANRP",
        expansion="Associazione Nazionale Reduci di Prigionia",
        description="Associazione Nazionale Reduci di Prigionia.",
        conflict_scope=["WWII"],
        verified=True,
    ),
    "ICRC": AuthorityRecord(
        authority_id="acr_icrc",
        record_type="acronym",
        label="ICRC",
        expansion="International Committee of the Red Cross",
        description="Comitato Internazionale della Croce Rossa — archivio prigionieri.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "CIRC": AuthorityRecord(
        authority_id="acr_circ",
        record_type="acronym",
        label="CIRC",
        expansion="Croce Rossa Italiana",
        description="Croce Rossa Italiana.",
        conflict_scope=["WWI", "WWII"],
        verified=True,
    ),
    "AUSSME": AuthorityRecord(
        authority_id="acr_aussme",
        record_type="acronym",
        label="AUSSME",
        expansion="Archivio dell'Ufficio Storico dello Stato Maggiore dell'Esercito",
        description="Archivio dell'Ufficio Storico dello Stato Maggiore dell'Esercito. Pertinente per diari di reparto, carteggi operativi, storia operativa. NON e' il deposito universale di fogli matricolari e fascicoli personali.",
        conflict_scope=["WWI", "WWII"],
        capability="diari_reparto",
        verified=True,
    ),
    "ACS": AuthorityRecord(
        authority_id="acr_acs",
        record_type="acronym",
        label="ACS",
        expansion="Archivio Centrale dello Stato",
        description="Archivio Centrale dello Stato. Conserva documenti di Stato italiani.",
        conflict_scope=["WWI", "WWII"],
        capability="documenti_stato",
        verified=True,
    ),
}


# ─── Archive authority records ───────────────────────────────────────────────

_ARCHIVES: Dict[str, AuthorityRecord] = {
    "aussme": AuthorityRecord(
        authority_id="arch_aussme",
        record_type="archive",
        label="Archivio dell'Ufficio Storico dello Stato Maggiore dell'Esercito",
        description="Conserva diari di reparto, carteggi operativi, storia operativa. I fogli matricolari sono conservati negli Archivi di Stato territoriali, non all'AUSSME.",
        conflict_scope=["WWI", "WWII"],
        geographic_scope="Italy",
        capability="diari_reparto",
        verified=True,
    ),
    "acs": AuthorityRecord(
        authority_id="arch_acs",
        record_type="archive",
        label="Archivio Centrale dello Stato",
        description="Conserva documenti di Stato italiani. Non e' il deposito universale di fogli matricolari.",
        conflict_scope=["WWI", "WWII"],
        geographic_scope="Italy",
        capability="documenti_stato",
        verified=True,
    ),
    "icrc": AuthorityRecord(
        authority_id="arch_icrc",
        record_type="archive",
        label="International Committee of the Red Cross Archives",
        description="Archivio ICRC per prigionieri di guerra. Pertinente solo per prigionia/internimento.",
        conflict_scope=["WWI", "WWII"],
        geographic_scope="International",
        capability="prigionia",
        verified=True,
    ),
    "onorcaduti": AuthorityRecord(
        authority_id="arch_onorcaduti",
        record_type="archive",
        label="Onorcaduti / Ministero della Difesa",
        description="Onorcaduti per luogo di sepoltura e sacrari. Non suggerire sacrari specifici non supportati.",
        conflict_scope=["WWI", "WWII"],
        geographic_scope="Italy",
        capability="sepoltura",
        verified=True,
    ),
    "lebi": AuthorityRecord(
        authority_id="arch_lebi",
        record_type="archive",
        label="LeBI — Lessico Biografico degli IMI (ANRP)",
        description="Lessico Biografico degli IMI. Pertinente solo per soggetti WWII/IMI.",
        conflict_scope=["WWII"],
        geographic_scope="Italy",
        capability="biografie_imi",
        verified=True,
    ),
    "archivio_stato": AuthorityRecord(
        authority_id="arch_archivio_stato",
        record_type="archive",
        label="Archivi di Stato (provinciali)",
        description="Gli Archivi di Stato conservano fogli matricolari, ruoli di leva, stati di famiglia secondo competenze territoriali e storiche. La competenza specifica dipende dal comune di residenza/leva.",
        conflict_scope=["WWI", "WWII"],
        geographic_scope="Italy",
        capability="matricolari",
        verified=True,
    ),
}


# ─── Lookup functions ────────────────────────────────────────────────────────


def get_acronym_authority(acronym: str) -> Optional[AuthorityRecord]:
    """Look up an acronym in the authority registry."""
    normalized = acronym.strip().rstrip(".").upper().replace(".", "").replace(" ", "")
    return _ACRONYMS.get(normalized)


def get_archive_authority(archive_id: str) -> Optional[AuthorityRecord]:
    """Look up an archive in the authority registry."""
    return _ARCHIVES.get(archive_id)


def is_verified_acronym(acronym: str) -> bool:
    """Check if an acronym has a verified authority record."""
    record = get_acronym_authority(acronym)
    return record is not None and record.verified


def is_verified_archive(archive_id: str) -> bool:
    """Check if an archive has a verified authority record."""
    record = get_archive_authority(archive_id)
    return record is not None and record.verified


def get_all_acronyms() -> List[AuthorityRecord]:
    """Return all acronym authority records."""
    return list(_ACRONYMS.values())


def get_all_archives() -> List[AuthorityRecord]:
    """Return all archive authority records."""
    return list(_ARCHIVES.values())


def get_archives_by_capability(capability: str) -> List[AuthorityRecord]:
    """Return archives with a specific capability."""
    return [a for a in _ARCHIVES.values() if a.capability == capability]


def get_archives_by_conflict(conflict: str) -> List[AuthorityRecord]:
    """Return archives relevant to a conflict."""
    return [a for a in _ARCHIVES.values() if conflict in a.conflict_scope or "both" in a.conflict_scope]


def to_dict() -> dict:
    """Serialize registry for API responses."""
    return {
        "version": REGISTRY_VERSION,
        "acronyms": {k: v.__dict__ for k, v in _ACRONYMS.items()},
        "archives": {k: v.__dict__ for k, v in _ARCHIVES.items()},
    }
