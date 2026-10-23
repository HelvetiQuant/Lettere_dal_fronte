"""NextStepCatalog V6 — deterministic archival next-step catalog.

The model does not invent archives, fonds, institutes or URLs.
The backend selects next steps from this versioned catalog based on
intent, conflict, location, unit, and gaps.

Access modes:
  LINK_ONLY, METADATA_ONLY, API_METADATA, OAI_METADATA, IIIF_METADATA,
  CONTENT_ALLOWED, DOWNLOAD_ALLOWED, REQUEST_REQUIRED,
  AUTHORIZATION_REQUIRED, MANUAL_CATALOGUING, BLOCKED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CatalogEntry:
    catalog_id: str
    description: str
    archive: str
    access_mode: str
    conflict: str = "BOTH"  # WWI|WWII|BOTH
    category: str = ""  # prigionia|decorazioni|caduti|naval|sepolture|matricolari|diari
    priority: int = 0
    url: str = ""
    requires_location: bool = False
    requires_unit: bool = False


class NextStepCatalog:
    """Versioned catalog of deterministic next-step suggestions."""

    VERSION = "6.0"

    def __init__(self):
        self._entries: Dict[str, CatalogEntry] = {}
        self._register_defaults()

    def _register_defaults(self):
        entries = [
            # ── WWI — Prigionia/IMI ──
            CatalogEntry("wwi_icrc", "Consultare l'archivio CICR (Croce Rossa Internazionale) per prigionieri di guerra WWI", "CICR Ginevra", "REQUEST_REQUIRED", "WWI", "prigionia", 10),
            CatalogEntry("wwi_lebi", "Consultare il Lessico Biografico degli IMI (ANRP) per schede nominative", "ANRP LeBI", "LINK_ONLY", "WWI", "prigionia", 9),
            CatalogEntry("wwi_nara_t315", "Consultare i records T315 NARA per campi di prigionia tedeschi", "NARA T315", "DOWNLOAD_ALLOWED", "WWI", "prigionia", 8),

            # ── WWII — Prigionia/IMI ──
            CatalogEntry("wwii_icrc", "Consultare l'archivio CICR per prigionieri di guerra WWII", "CICR Ginevra", "REQUEST_REQUIRED", "WWII", "prigionia", 10),
            CatalogEntry("wwii_lebi", "Consultare il Lessico Biografico degli IMI (ANRP) per internati militari italiani", "ANRP LeBI", "LINK_ONLY", "WWII", "prigionia", 9),
            CatalogEntry("wwii_nara", "Consultare gli archivi NARA per documentazione sui campi di prigionia", "NARA College Park", "DOWNLOAD_ALLOWED", "WWII", "prigionia", 7),

            # ── Matricolari ──
            CatalogEntry("mat_distrettuale", "Richiedere il foglio matricolare presso l'Archivio di Stato del distretto militare di nascita", "Archivio di Stato distrettuale", "REQUEST_REQUIRED", "BOTH", "matricolari", 8, requires_location=True),
            CatalogEntry("mat_storico", "Consultare i ruoli matricolari storici presso l'Archivio Centrale dello Stato", "Archivio Centrale dello Stato Roma", "MANUAL_CATALOGUING", "BOTH", "matricolari", 6),

            # ── Diari di guerra ──
            CatalogEntry("diari_reparto", "Consultare i diari di guerra del reparto presso l'Ufficio Storico dello Stato Maggiore Esercito", "USMME Roma", "REQUEST_REQUIRED", "BOTH", "diari", 8, requires_unit=True),
            CatalogEntry("diari_archivio", "Consultare i diari storici dei comandi presso l'Archivio Centrale dello Stato", "Archivio Centrale dello Stato Roma", "MANUAL_CATALOGUING", "BOTH", "diari", 6, requires_unit=True),

            # ── Caduti ──
            CatalogEntry("caduti_albooro", "Verificare l'Albo d'Oro dei caduti nella Grande Guerra", "Albo d'Oro online", "LINK_ONLY", "WWI", "caduti", 9),
            CatalogEntry("caduti_onorcaduti", "Consultare il portale Onorcaduti del Ministero della Difesa", "Onorcaduti", "LINK_ONLY", "BOTH", "caduti", 8),
            CatalogEntry("caduti_cwgc", "Consultare il Commonwealth War Graves Commission per caduti internati", "CWGC", "LINK_ONLY", "WWII", "caduti", 7),

            # ── Decorazioni ──
            CatalogEntry("decorazioni_bollettino", "Verificare il Bollettino Ufficiale delle decorazioni al Valor Militare", "Bollettino Ufficiale", "LINK_ONLY", "BOTH", "decorazioni", 9),
            CatalogEntry("decorazioni_archivio", "Richiedere l'atto di concessione presso l'Archivio Centrale dello Stato", "Archivio Centrale dello Stato Roma", "REQUEST_REQUIRED", "BOTH", "decorazioni", 7),

            # ── Naval ──
            CatalogEntry("naval_marina", "Consultare l'Archivio Storico della Marina Militare per caduti in mare", "Archivio Storica Marina Militare", "REQUEST_REQUIRED", "BOTH", "naval", 8),
            CatalogEntry("naval_affondamenti", "Consultare i registri di affondamento presso l'Ufficio Storico della Marina", "USM Roma", "MANUAL_CATALOGUING", "BOTH", "naval", 6),

            # ── Sepolture ──
            CatalogEntry("sepolture_onorcaduti", "Consultare il portale Onorcaduti per le sepolture militari", "Onorcaduti", "LINK_ONLY", "BOTH", "sepolture", 7),
            CatalogEntry("sepolture_cwgc", "Consultare il CWGC per sepolture nei cimiteri di guerra", "CWGC", "LINK_ONLY", "WWII", "sepolture", 6),

            # ── Generici ──
            CatalogEntry("generic_archivio_stato", "Consultare l'Archivio di Stato competente per territorio", "Archivio di Stato", "REQUEST_REQUIRED", "BOTH", "generic", 5, requires_location=True),
            CatalogEntry("generic_archivio_centrale", "Consultare l'Archivio Centrale dello Stato per documentazione storico-militare", "Archivio Centrale dello Stato Roma", "MANUAL_CATALOGUING", "BOTH", "generic", 4),
        ]
        for e in entries:
            self._entries[e.catalog_id] = e

    def get(self, catalog_id: str) -> Optional[CatalogEntry]:
        return self._entries.get(catalog_id)

    def select_steps(
        self,
        intent: str,
        conflict: str = "UNKNOWN",
        location: str = "",
        unit: str = "",
        gaps: List[str] = None,
        max_steps: int = 5,
    ) -> List[CatalogEntry]:
        """Select deterministic next steps based on context."""
        gaps = gaps or []
        scored: List[tuple[int, CatalogEntry]] = []

        for entry in self._entries.values():
            # Conflict filter
            if entry.conflict != "BOTH" and conflict != "UNKNOWN" and entry.conflict != conflict:
                continue

            # Requirements filter
            if entry.requires_location and not location:
                continue
            if entry.requires_unit and not unit:
                continue

            # Score
            score = entry.priority

            # Boost based on gaps
            if "internment_place" in gaps and entry.category == "prigionia":
                score += 5
            if "service_number" in gaps and entry.category == "matricolari":
                score += 5
            if "unit" in gaps and entry.category == "diari":
                score += 5
            if "death_place" in gaps and entry.category == "caduti":
                score += 3
            if "decoration_type" in gaps and entry.category == "decorazioni":
                score += 5
            if "burial" in gaps and entry.category == "sepolture":
                score += 5

            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_steps]]

    def all_entries(self) -> Dict[str, CatalogEntry]:
        return dict(self._entries)
