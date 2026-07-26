"""Provider ICRC WW1 — Prisoners of the First World War (grandeguerre.icrc.org).

Archivio online del CICR Ginevra: 5M+ schede prigionieri 1GM.
Accesso libero per consultazione. Scansione schede online.
Nessuna API pubblica. Scraping HTML rispettoso con compliance gate.

Classificazione: METADATA_ONLY (diritti non chiari, principio prudenziale).
"""
import re
import time
import logging
from typing import List
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .base import SourceProvider
from compliance_gate import METADATA_ONLY, evaluate as compliance_evaluate

logger = logging.getLogger("icrc_ww1")


class ProviderICRCWW1(SourceProvider):
    name = "icrc_ww1"
    display_name = "ICRC — Prisoners of the First World War (1914-1918)"
    country = "Internazionale"
    archive_name = "ICRC Archives — Prisoners of the First World War"
    base_url = "https://grandeguerre.icrc.org"
    authorized_domains = {"grandeguerre.icrc.org", "icrc.org"}
    cache_ttl_days = 60

    # Nazionalità disponibili sul portale ICRC
    NATIONALITIES = {
        "italy": "Italy",
        "france": "France",
        "germany": "Germany",
        "united_kingdom": "United Kingdom",
        "austria_hungary": "Austria-Hungary",
        "russia": "Russia",
        "romania": "Romania",
        "serbia": "Serbia",
        "belgium": "Belgium",
        "ottoman_empire": "Ottoman Empire",
        "bulgaria": "Bulgaria",
        "portugal": "Portugal",
        "united_states": "United States",
    }

    # Status disponibili: militare o civile
    STATUSES = {"military": "military", "civilian": "civilian"}

    # Files/dataset disponibili (gruppi di schede)
    FILE_TYPES = {
        "index_cards": "index_cards",
        "family_requests": "family_requests",
        "all": "all",
    }

    def build_search_url(self, query: str, filters: dict = None) -> str:
        """Costruisce l'URL di ricerca con tutti i parametri del form ICRC."""
        filters = filters or {}
        name = quote(query)
        nationality = filters.get("nationality", "italy")
        status = filters.get("status", "")
        files = filters.get("files", "")

        params_parts = [f"name={name}", f"nationality={nationality}"]
        if status:
            params_parts.append(f"status={status}")
        if files:
            params_parts.append(f"files={files}")

        return f"{self.base_url}/en/File/Search?{'&'.join(params_parts)}"

    def search(self, query: str, filters: dict = None, *, context=None) -> List[dict]:
        """Cerca prigionieri per nome con filtri auto-compilati.
        
        Filtri supportati (auto-compilati dal contesto):
        - nationality: nazionalità del prigioniero (default: italy)
        - status: military | civilian
        - files: index_cards | family_requests | all
        
        Ritorna metadati + URL diretto. Non scarica immagini delle schede."""
        filters = filters or {}
        nationality = filters.get("nationality", "italy")
        status = filters.get("status", "")
        files = filters.get("files", "")

        search_url = f"{self.base_url}/en/File/Search"
        params = {"name": query, "nationality": nationality}
        if status:
            params["status"] = status
        if files:
            params["files"] = files

        try:
            resp = requests.get(
                search_url, params=params, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"ICRC search failed: {e}")
            return [{
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Ricerca: {query}",
                "description": f"Ricerca ICRC WW1 — errore di accesso: {e}",
                "source_type": "prisoner_record",
                "catalog_url": self.build_search_url(query, filters),
                "direct_url": "",
                "classification": METADATA_ONLY,
                "domain": "grandeguerre.icrc.org",
                "filters_applied": {"nationality": nationality, "status": status, "files": files},
            }]

        results = []
        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse result links — ICRC usa link /en/File/Details/{id}/{type}/{sub}
        for link in soup.find_all("a", href=re.compile(r"/en/File/Details/\d+")):
            href = link.get("href", "")
            full_url = urljoin(self.base_url, href)
            text = link.get_text(strip=True)

            # Extract record ID from URL
            match = re.search(r"/en/File/Details/(\d+)", href)
            record_id = match.group(1) if match else ""

            results.append({
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": text or f"Record ICRC #{record_id}",
                "description": "Scheda prigioniero ICRC WW1 — metadati minimi.",
                "source_type": "prisoner_record",
                "catalog_url": full_url,
                "direct_url": full_url,
                "provider_record_id": record_id,
                "classification": METADATA_ONLY,
                "domain": "grandeguerre.icrc.org",
                "filters_applied": {"nationality": nationality, "status": status, "files": files},
            })

        # If no results parsed, return metadata-only fallback with pre-filled URL
        if not results:
            results.append({
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Ricerca ICRC WW1: {query}",
                "description": "Consultare il portale ICRC per la ricerca manuale.",
                "source_type": "prisoner_record",
                "catalog_url": self.build_search_url(query, filters),
                "direct_url": "",
                "classification": METADATA_ONLY,
                "domain": "grandeguerre.icrc.org",
                "filters_applied": {"nationality": nationality, "status": status, "files": files},
            })

        return results

    def get_metadata(self, record_id: str) -> dict:
        """Recupera metadati da una scheda specifica. Solo metadati, no immagini."""
        detail_url = f"{self.base_url}/en/File/Details/{record_id}/1/2"

        try:
            resp = requests.get(
                detail_url, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"ICRC detail failed: {e}")
            return {
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Record ICRC #{record_id}",
                "description": f"Errore accesso: {e}",
                "catalog_url": detail_url,
                "classification": METADATA_ONLY,
                "domain": "grandeguerre.icrc.org",
            }

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract name from page title or heading
        title_tag = soup.find("h1") or soup.find("title")
        name = title_tag.get_text(strip=True) if title_tag else f"Record #{record_id}"

        # Extract any visible metadata (no images)
        meta = {
            "provider": self.name,
            "archivio": self.archive_name,
            "titolo": name,
            "description": "Scheda prigioniero ICRC WW1.",
            "source_type": "prisoner_record",
            "catalog_url": detail_url,
            "direct_url": detail_url,
            "provider_record_id": record_id,
            "classification": METADATA_ONLY,
            "domain": "grandeguerre.icrc.org",
        }

        # Look for structured data in the page
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                key = dt.get_text(strip=True).lower().replace(" ", "_")
                val = dd.get_text(strip=True)
                if key and val and key not in ("", "provider"):
                    meta[key] = val

        return meta

    def get_document(self, record_id: str) -> dict:
        """Override: ICRC non permette download automatico delle schede."""
        return {
            "ok": False,
            "error": "Download non autorizzato. Classificazione METADATA_ONLY. "
                     "Consultare il portale ICRC per visualizzare la scheda.",
            "catalog_url": f"{self.base_url}/en/File/Details/{record_id}/1/2",
        }

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        return f"{self.base_url}/en/File/Details/{record_id}/1/2"
