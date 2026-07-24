"""Provider CRI Milano — Archivio Storico Croce Rossa Italiana, Comitato di Milano.

Catalogo su piattaforma archimista. Metadati pubblici via web.
Documenti fisici su richiesta. Contiene corrispondenza dispersi/scomparsi 2GM.

Classificazione: METADATA_ONLY (nessuna licenza esplicita, dati personali).
"""
import re
import logging
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .base import SourceProvider
from compliance_gate import METADATA_ONLY, REQUEST_REQUIRED

logger = logging.getLogger("cri_milano")


class ProviderCRIMilano(SourceProvider):
    name = "cri_milano"
    display_name = "Archivio Storico CRI — Comitato di Milano"
    country = "Italia"
    archive_name = "Archivio Storico Croce Rossa Italiana — Comitato di Milano"
    base_url = "https://cri-mi.archimista.com"
    authorized_domains = {"cri-mi.archimista.com"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> list:
        """Cerca nell'archivio CRI Milano. Solo metadati, no documenti."""
        filters = filters or {}
        search_url = f"{self.base_url}/search"
        params = {"q": query}

        try:
            resp = requests.get(
                search_url, params=params, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"CRI Milano search failed: {e}")
            return [{
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Ricerca: {query}",
                "description": f"Archivio CRI Milano — errore di accesso: {e}",
                "source_type": "archival_unit",
                "catalog_url": f"{self.base_url}/search?q={quote(query)}",
                "direct_url": "",
                "classification": METADATA_ONLY,
                "domain": "cri-mi.archimista.com",
            }]

        results = []
        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse results from archimista platform
        for link in soup.find_all("a", href=re.compile(r"/(fonds|units|items)/\d+")):
            href = link.get("href", "")
            full_url = urljoin(self.base_url, href)
            text = link.get_text(strip=True)

            match = re.search(r"/(fonds|units|items)/(\d+)", href)
            record_type = match.group(1) if match else "unknown"
            record_id = match.group(2) if match else ""

            results.append({
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": text or f"Unità archivistica #{record_id}",
                "description": f"Unità archivistica CRI Milano ({record_type}). "
                               f"Documento su richiesta.",
                "source_type": "archival_unit",
                "catalog_url": full_url,
                "direct_url": full_url,
                "provider_record_id": record_id,
                "classification": REQUEST_REQUIRED,
                "domain": "cri-mi.archimista.com",
            })

        if not results:
            results.append({
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Ricerca CRI Milano: {query}",
                "description": "Consultare il catalogo archimista per la ricerca manuale.",
                "source_type": "archival_unit",
                "catalog_url": f"{self.base_url}/search?q={quote(query)}",
                "direct_url": "",
                "classification": METADATA_ONLY,
                "domain": "cri-mi.archimista.com",
            })

        return results

    def get_metadata(self, record_id: str) -> dict:
        """Recupera metadati da una unità archivistica specifica."""
        detail_url = f"{self.base_url}/units/{record_id}"

        try:
            resp = requests.get(
                detail_url, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"CRI Milano detail failed: {e}")
            return {
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Unità #{record_id}",
                "description": f"Errore accesso: {e}",
                "catalog_url": detail_url,
                "classification": METADATA_ONLY,
                "domain": "cri-mi.archimista.com",
            }

        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else f"Unità #{record_id}"

        meta = {
            "provider": self.name,
            "archivio": self.archive_name,
            "titolo": title,
            "description": "Unità archivistica CRI Milano. Documento su richiesta.",
            "source_type": "archival_unit",
            "catalog_url": detail_url,
            "direct_url": detail_url,
            "provider_record_id": record_id,
            "classification": REQUEST_REQUIRED,
            "domain": "cri-mi.archimista.com",
        }

        # Extract structured metadata from archimista page
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower().replace(" ", "_")
                val = cells[1].get_text(strip=True)
                if key and val:
                    meta[key] = val

        # Extract segnatura if present
        segnatura = soup.find(string=re.compile("segnatura", re.I))
        if segnatura:
            meta["segnatura"] = segnatura.find_next().get_text(strip=True) if segnatura.find_next() else ""

        return meta

    def get_document(self, record_id: str) -> dict:
        """CRI Milano: documenti fisici su richiesta."""
        return {
            "ok": False,
            "error": "Documento su richiesta. Contattare l'archivio: archivio@crimi.it",
            "catalog_url": f"{self.base_url}/units/{record_id}",
            "request_contact": "archivio@crimi.it",
        }

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        return f"{self.base_url}/units/{record_id}"
