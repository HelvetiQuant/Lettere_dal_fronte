"""Provider LeBI — Lessico Biografico degli Internati Militari Italiani.

Portale ANRP: https://www.lessicobiograficoimi.it/
Banca dati con oltre 305.000 nominativi di IMI deportati nei lager nazisti (1943-1945).

Classificazione: METADATA_ONLY (dati biografici pubblici, PDF scaricabile pubblicamente).
"""
import re
import logging
from typing import List
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .base import SourceProvider
from compliance_gate import METADATA_ONLY, PUBLIC_VIEW

logger = logging.getLogger("lebi")


class ProviderLeBI(SourceProvider):
    name = "lebi"
    display_name = "LeBI — Lessico Biografico degli IMI"
    country = "IT"
    archive_name = "ANRP — Lessico Biografico degli Internati Militari Italiani"
    base_url = "https://www.lessicobiograficoimi.it"
    authorized_domains = {"lessicobiograficoimi.it", "www.lessicobiograficoimi.it"}
    cache_ttl_days = 90

    # ─── Ricerca ──────────────────────────────────────────────────────
    def search(self, query: str, filters: dict = None, *, context=None) -> List[dict]:
        """Cerca nell'archivio LeBI per cognome/nome.

        Parametri form verificati:
        - q: cognome (campo principale)
        - n: nome
        - l: luogo di nascita
        - y: anno di nascita
        - d: flag debug (sempre 0)

        Ritorna metadati + URL diretto. Non scarica PDF.
        """
        filters = filters or {}
        search_url = f"{self.base_url}/frontend_prodimi.php/caduti/search"

        params = {"d": "0", "q": query}
        if filters.get("name"):
            params["n"] = filters["name"]
        if filters.get("birth_place"):
            params["l"] = filters["birth_place"]
        if filters.get("birth_year"):
            params["y"] = filters["birth_year"]

        try:
            resp = requests.get(
                search_url, params=params, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"LeBI search failed: {e}")
            return [{
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Ricerca: {query}",
                "description": f"LeBI — errore di accesso: {e}",
                "source_type": "biographical_database",
                "catalog_url": self.build_search_url(query, filters),
                "direct_url": "",
                "classification": METADATA_ONLY,
                "domain": "lessicobiograficoimi.it",
                "filters_applied": {k: v for k, v in filters.items() if v},
            }]

        results = []
        soup = BeautifulSoup(resp.text, "html.parser")

        for link in soup.find_all("a", href=re.compile(r"/caduti/show/\d+")):
            href = link.get("href", "")
            full_url = urljoin(self.base_url, href)
            match = re.search(r"/caduti/show/(\d+)", href)
            record_id = match.group(1) if match else ""

            results.append({
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"LeBI #{record_id}",
                "description": "Scheda biografica LeBI — ANRP.",
                "source_type": "biographical_database",
                "catalog_url": full_url,
                "direct_url": full_url,
                "provider_record_id": record_id,
                "classification": METADATA_ONLY,
                "domain": "lessicobiograficoimi.it",
                "filters_applied": {k: v for k, v in filters.items() if v},
            })

        if not results:
            results.append({
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"Ricerca LeBI: {query}",
                "description": "Nessun risultato. Consultare il portale LeBI per la ricerca manuale.",
                "source_type": "biographical_database",
                "catalog_url": self.build_search_url(query, filters),
                "direct_url": "",
                "classification": METADATA_ONLY,
                "domain": "lessicobiograficoimi.it",
                "filters_applied": {k: v for k, v in filters.items() if v},
            })

        return results

    def build_search_url(self, query: str, filters: dict = None) -> str:
        """Costruisce l'URL di ricerca con i parametri del form LeBI."""
        filters = filters or {}
        params = [f"d=0", f"q={quote(query)}"]
        if filters.get("name"):
            params.append(f"n={quote(filters['name'])}")
        if filters.get("birth_place"):
            params.append(f"l={quote(filters['birth_place'])}")
        if filters.get("birth_year"):
            params.append(f"y={quote(str(filters['birth_year']))}")
        return f"{self.base_url}/frontend_prodimi.php/caduti/search?{'&'.join(params)}"

    # ─── Metadati dettaglio ───────────────────────────────────────────
    def get_metadata(self, record_id: str) -> dict:
        """Recupera e analizza una scheda biografica LeBI.

        Struttura HTML verificata:
        - Sezioni: span.fallen-box-title (ANAGRAFICA, POSIZIONE MILITARE, CATTURA, DECESSO, INTERNAMENTO, FONTI)
        - Label: div.col-xs-5 (senza fallen-field-margins)
        - Valori: div.fallen-field-margins
        - Note: div.col-xs-12 con testo libero
        """
        detail_url = f"{self.base_url}/frontend_prodimi.php/caduti/show/{record_id}"

        try:
            resp = requests.get(
                detail_url, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"LeBI detail failed: {e}")
            return {
                "provider": self.name,
                "archivio": self.archive_name,
                "titolo": f"LeBI #{record_id}",
                "description": f"Errore accesso: {e}",
                "catalog_url": detail_url,
                "classification": METADATA_ONLY,
                "domain": "lessicobiograficoimi.it",
            }

        soup = BeautifulSoup(resp.text, "html.parser")
        parsed = self._parse_record_html(soup, record_id, detail_url)
        return parsed

    def _parse_record_html(self, soup: BeautifulSoup, record_id: str, detail_url: str) -> dict:
        """Estrae tutti i campi strutturati dalla scheda HTML LeBI.

        Struttura HTML verificata (2026-07):
        - Sezioni: span.fallen-box-title (ANAGRAFICA, POSIZIONE MILITARE, CATTURA, 
          DECESSO o RIENTRO, INTERNAMENTO, FONTI)
        - Label: div.col-xs-6.fallen-field-margins.fallen-label
        - Valore: div.col-xs-6.fallen-field-margins.corner5.white-corner-show
          (stesse classi del label ma SENZA fallen-label)
        - I campi internamento (Luogo/Impiego) usano col-xs-5 con fallen-field-margins
        """
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else f"LeBI #{record_id}"
        name_from_title = title_text.replace("LeBI - ", "").strip() if "LeBI - " in title_text else ""

        # Estrai sezioni
        sections = {}
        for span in soup.find_all("span", class_="fallen-box-title"):
            section_name = span.get_text(strip=True)
            sections[section_name] = {"fields": {}, "notes": []}

        # Parse label-value pairs
        # Labels: div with class "fallen-label"
        # Values: next sibling div with "fallen-field-margins" but WITHOUT "fallen-label"
        active_section = "ANAGRAFICA"

        # Track section by walking through all relevant elements in document order
        for element in soup.find_all(["span", "div"], class_=True):
            classes = element.get("class", [])

            # Section title
            if "fallen-box-title" in classes:
                section_name = element.get_text(strip=True)
                if section_name:
                    active_section = section_name
                    sections.setdefault(active_section, {"fields": {}, "notes": []})
                continue

            # Label div (col-xs-6 with fallen-label)
            if "fallen-label" in classes:
                label = element.get_text(strip=True)
                if not label:
                    continue
                # Find next sibling that is a value (has fallen-field-margins but not fallen-label)
                value_div = element.find_next_sibling("div", class_="fallen-field-margins")
                if value_div and "fallen-label" not in value_div.get("class", []):
                    value = value_div.get_text(strip=True)
                    if value:
                        sections.setdefault(active_section, {"fields": {}, "notes": []})
                        sections[active_section]["fields"][label] = value
                continue

        # Separate pass for INTERNAMENTO section: camp values are in col-xs-5 divs
        # with fallen-field-margins but without fallen-label
        intern_camps = []
        in_internment = False
        for element in soup.find_all(["span", "div"], class_=True):
            classes = element.get("class", [])
            text = element.get_text(strip=True)

            if "fallen-box-title" in classes:
                in_internment = (text == "INTERNAMENTO")
                continue

            if in_internment and "fallen-field-margins" in classes and "fallen-label" not in classes:
                # This is a camp value (col-xs-5 structure)
                if text and text not in ("Luogo internamento", "Impiego"):
                    intern_camps.append(text)

        if intern_camps:
            sections.setdefault("INTERNAMENTO", {"fields": {}, "notes": []})
            sections["INTERNAMENTO"]["fields"]["camp"] = intern_camps

        # Build metadata dict — handle variable section names
        anag = sections.get("ANAGRAFICA", {}).get("fields", {})
        militare = sections.get("POSIZIONE MILITARE", {}).get("fields", {})
        cattura = sections.get("CATTURA", {}).get("fields", {})
        # Some records have "DECESSO", others "RIENTRO"
        decesso = sections.get("DECESSO", {}).get("fields", {})
        rientro = sections.get("RIENTRO", {}).get("fields", {})
        internamento = sections.get("INTERNAMENTO", {}).get("fields", {})
        fonti = sections.get("FONTI", {}).get("fields", {})

        # Extract notes from CATTURA (matricola)
        cattura_notes = sections.get("CATTURA", {}).get("notes", [])
        fonti_notes = sections.get("FONTI", {}).get("notes", [])

        # Parse matricola from notes
        matricola = ""
        for note in cattura_notes:
            m = re.search(r"Matricola:\s*(\S+)", note)
            if m:
                matricola = m.group(1)
                break

        # Camps list
        camps = internamento.get("camp", [])
        if isinstance(camps, str):
            camps = [camps]

        # Sources
        sources_text = " | ".join(fonti_notes) if fonti_notes else fonti.get("Fonti", "")

        meta = {
            "provider": self.name,
            "archivio": self.archive_name,
            "titolo": name_from_title or f"LeBI #{record_id}",
            "description": f"Scheda biografica LeBI — {name_from_title}",
            "source_type": "biographical_database",
            "catalog_url": detail_url,
            "direct_url": detail_url,
            "provider_record_id": record_id,
            "classification": METADATA_ONLY,
            "domain": "lessicobiograficoimi.it",
            # Anagrafica
            "cognome": anag.get("COGNOME", ""),
            "nome": anag.get("NOME", ""),
            "data_nascita": anag.get("Data di nascita", ""),
            "comune_nascita": anag.get("Comune di nascita", ""),
            "provincia_nascita": anag.get("Provincia", ""),
            "regione_nascita": anag.get("Regione", ""),
            # Posizione militare
            "grado": militare.get("Grado", ""),
            "reparto": militare.get("Reparto", ""),
            "arma": militare.get("Arma", ""),
            # Cattura
            "fronte_cattura": cattura.get("Fronte", ""),
            "luogo_cattura": cattura.get("Luogo di cattura", ""),
            "data_cattura": cattura.get("Data cattura", ""),
            "matricola": matricola,
            # Decesso (può essere assente se l'IMI è rientrato)
            "data_decesso": decesso.get("Data decesso", ""),
            "luogo_fronte_decesso": decesso.get("Luogo/Fronte", ""),
            "luogo_sepoltura": decesso.get("Luogo di sepoltura", ""),
            "causa_morte": decesso.get("Causa morte", ""),
            # Rientro (se l'IMI è sopravvissuto)
            "data_rientro": rientro.get("Data rientro", ""),
            "luogo_rientro": rientro.get("Luogo di rientro", ""),
            "has_rientro": bool(rientro),
            # Internamento
            "campi_internamento": camps,
            # Fonti
            "fonti": sources_text,
            # PDF
            "pdf_url": f"{self.base_url}/frontend_prodimi.php/caduti/showpdf/{record_id}",
            "has_pdf": True,
            # Raw sections for adapter
            "_sections": sections,
        }

        return meta

    def get_document(self, record_id: str) -> dict:
        """Scarica il PDF della scheda LeBI se disponibile."""
        pdf_url = f"{self.base_url}/frontend_prodimi.php/caduti/showpdf/{record_id}"
        try:
            resp = requests.head(
                pdf_url, timeout=15,
                headers={"User-Agent": "Mozilla/5.0 ricerca-storica-IMI/1.0 (research)"},
                allow_redirects=True,
            )
            if resp.status_code == 200 and "application/pdf" in resp.headers.get("Content-Type", ""):
                return {"ok": True, "url": pdf_url, "content_type": "application/pdf"}
            else:
                return {"ok": False, "error": f"PDF non disponibile (HTTP {resp.status_code})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        return f"{self.base_url}/frontend_prodimi.php/caduti/show/{record_id}"
