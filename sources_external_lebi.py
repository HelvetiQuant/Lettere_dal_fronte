"""Adapter LeBI per il modulo Fonti Esterne Federate.

Implementa l'interfaccia SourceAdapter per il portale LeBI
(Lessico Biografico degli Internati Militari Italiani — ANRP).

URL verificati:
- Ricerca: GET /frontend_prodimi.php/caduti/search?q=COGNOME&n=NOME&l=LUOGO&y=ANNO&d=0
- Scheda: /frontend_prodimi.php/caduti/show/{ID}
- PDF: /frontend_prodimi.php/caduti/showpdf/{ID}

Struttura HTML scheda:
- Sezioni: span.fallen-box-title (ANAGRAFICA, POSIZIONE MILITARE, CATTURA, DECESSO, INTERNAMENTO, FONTI)
- Label/valori: div.col-xs-5 (label) + div.fallen-field-margins (valore)
- Note: div.col-xs-12 con testo libero
"""
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sources_external_base import SourceAdapter, compute_metadata_hash

logger = logging.getLogger("lebi_adapter")


class LeBIAdapter(SourceAdapter):
    provider_id = "lebi"
    display_name = "LeBI — Lessico Biografico degli IMI"
    archive_name = "ANRP — Lessico Biografico degli Internati Militari Italiani"
    archive_branch = "ANRP"
    base_url = "https://www.lessicobiograficoimi.it"
    user_agent = "IMI-Extractor/1.0 (research; LeBI adapter)"
    rate_limiter = None  # usa default

    def __init__(self):
        from sources_external_base import RateLimiter
        self.rate_limiter = RateLimiter(min_delay=1.5)

    # ─── Discover ─────────────────────────────────────────────────────
    def discover_resources(self, start_url: str, max_records: int = 0) -> List[Dict[str, Any]]:
        """Scopre record LeBI tramite ricerca per cognome.

        LeBI non espone un elenco completo. Si usa la ricerca per cognome
        con paginazione. Il portale ha ~305K nominativi.
        """
        results = []
        page = 1
        base_search = f"{self.base_url}/frontend_prodimi.php/caduti/search"

        while True:
            params = {"d": "0", "q": start_url, "page": str(page)}
            html, status = self.fetch_page(
                f"{base_search}?d=0&q={start_url}&n=&l=&y=&page={page}"
            )
            if not html or status >= 400:
                break

            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=re.compile(r"/caduti/show/\d+"))

            if not links:
                break

            for link in links:
                href = link.get("href", "")
                full_url = urljoin(self.base_url, href)
                match = re.search(r"/caduti/show/(\d+)", href)
                record_id = match.group(1) if match else ""

                results.append({
                    "external_id": record_id,
                    "canonical_record_url": full_url,
                    "record_level": "item",
                })

                if max_records and len(results) >= max_records:
                    return results

            # Check pagination — if no next page, stop
            next_link = soup.find("a", string=re.compile(r">>", re.I))
            if not next_link:
                break
            page += 1

            # Safety limit
            if page > 1000:
                break

        return results

    # ─── Parse record ─────────────────────────────────────────────────
    def parse_record(self, url: str) -> Optional[Dict[str, Any]]:
        """Recupera e analizza una scheda biografica LeBI."""
        html, status = self.fetch_page(url)
        if not html or status >= 400:
            logger.warning(f"LeBI parse_record failed: HTTP {status} for {url}")
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract record ID from URL
        match = re.search(r"/caduti/show/(\d+)", url)
        record_id = match.group(1) if match else ""

        # Title
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        name_from_title = title_text.replace("LeBI - ", "").strip() if "LeBI - " in title_text else ""

        # Parse sections
        sections = self._parse_sections(soup)

        anag = sections.get("ANAGRAFICA", {}).get("fields", {})
        militare = sections.get("POSIZIONE MILITARE", {}).get("fields", {})
        cattura = sections.get("CATTURA", {}).get("fields", {})
        decesso = sections.get("DECESSO", {}).get("fields", {})
        rientro = sections.get("RIENTRO", {}).get("fields", {})
        internamento = sections.get("INTERNAMENTO", {}).get("fields", {})
        fonti_notes = sections.get("FONTI", {}).get("notes", [])

        # Parse matricola from notes
        matricola = ""
        for note in sections.get("CATTURA", {}).get("notes", []):
            m = re.search(r"Matricola:\s*(\S+)", note)
            if m:
                matricola = m.group(1)
                break

        # Camps list
        camps = internamento.get("camp", [])
        if isinstance(camps, str):
            camps = [camps]

        # Sources text
        sources_text = " | ".join(fonti_notes) if fonti_notes else ""

        # Build record data
        record_data = {
            "provider": self.provider_id,
            "archive_name": self.archive_name,
            "archive_branch": self.archive_branch,
            "external_id": record_id,
            "record_level": "item",
            "record_type": "biographical_record",
            "title": name_from_title or f"LeBI #{record_id}",
            "description": f"Scheda biografica LeBI — {name_from_title}",
            "canonical_record_url": url,
            "access_status": "active",
            "http_status": status,
            # JSON metadata
            "people_metadata_json": self._build_people_json(anag, militare, matricola),
            "places_metadata_json": self._build_places_json(anag, cattura, decesso, camps),
            "military_units_metadata_json": self._build_military_json(militare),
            "camps_metadata_json": self._build_camps_json(camps),
            "subjects_metadata_json": self._build_subjects_json(decesso),
            # Digital object
            "digital_object_available": 1,
            "digital_object_url": f"{self.base_url}/frontend_prodimi.php/caduti/showpdf/{record_id}",
        }

        record_data["metadata_hash"] = compute_metadata_hash(record_data)
        return record_data

    def _parse_sections(self, soup: BeautifulSoup) -> Dict[str, Dict]:
        """Estrae sezioni e campi dalla scheda HTML LeBI.

        Struttura HTML verificata (2026-07):
        - Label: div.col-xs-6.fallen-field-margins.fallen-label
        - Valore: div.col-xs-6.fallen-field-margins (senza fallen-label)
        - Internamento: div.col-xs-5.fallen-field-margins (senza fallen-label) = campi
        """
        sections = {}
        active_section = "ANAGRAFICA"

        # Initialize sections from fallen-box-title spans
        for span in soup.find_all("span", class_="fallen-box-title"):
            section_name = span.get_text(strip=True)
            sections[section_name] = {"fields": {}, "notes": []}

        # Parse label-value pairs using fallen-label class
        for element in soup.find_all(["span", "div"], class_=True):
            classes = element.get("class", [])
            text = element.get_text(strip=True)

            if "fallen-box-title" in classes:
                if text:
                    active_section = text
                    sections.setdefault(active_section, {"fields": {}, "notes": []})
                continue

            if "fallen-label" in classes:
                label = text
                if not label:
                    continue
                value_div = element.find_next_sibling("div", class_="fallen-field-margins")
                if value_div and "fallen-label" not in value_div.get("class", []):
                    value = value_div.get_text(strip=True)
                    if value:
                        sections.setdefault(active_section, {"fields": {}, "notes": []})
                        sections[active_section]["fields"][label] = value
                continue

        # Separate pass for INTERNAMENTO camps (col-xs-5 structure)
        intern_camps = []
        in_internment = False
        for element in soup.find_all(["span", "div"], class_=True):
            classes = element.get("class", [])
            text = element.get_text(strip=True)

            if "fallen-box-title" in classes:
                in_internment = (text == "INTERNAMENTO")
                continue

            if in_internment and "fallen-field-margins" in classes and "fallen-label" not in classes:
                if text and text not in ("Luogo internamento", "Impiego"):
                    intern_camps.append(text)

        if intern_camps:
            sections.setdefault("INTERNAMENTO", {"fields": {}, "notes": []})
            sections["INTERNAMENTO"]["fields"]["camp"] = intern_camps

        return sections

    def _build_people_json(self, anag: Dict, militare: Dict, matricola: str) -> str:
        import json
        people = [{
            "surname": anag.get("COGNOME", ""),
            "name": anag.get("NOME", ""),
            "birth_date": anag.get("Data di nascita", ""),
            "birth_place": anag.get("Comune di nascita", ""),
            "province": anag.get("Provincia", ""),
            "region": anag.get("Regione", ""),
            "rank": militare.get("Grado", ""),
            "unit": militare.get("Reparto", ""),
            "branch": militare.get("Arma", ""),
            "service_number": matricola,
        }]
        return json.dumps(people, ensure_ascii=False)

    def _build_places_json(self, anag: Dict, cattura: Dict, decesso: Dict, camps: List) -> str:
        import json
        places = []
        if anag.get("Comune di nascita"):
            places.append({"type": "birth_place", "name": anag["Comune di nascita"], "province": anag.get("Provincia", "")})
        if cattura.get("Luogo di cattura"):
            places.append({"type": "capture_place", "name": cattura["Luogo di cattura"]})
        if decesso.get("Luogo/Fronte"):
            places.append({"type": "death_place", "name": decesso["Luogo/Fronte"]})
        if decesso.get("Luogo di sepoltura"):
            places.append({"type": "burial_place", "name": decesso["Luogo di sepoltura"]})
        for camp in camps:
            places.append({"type": "internment_camp", "name": camp})
        return json.dumps(places, ensure_ascii=False)

    def _build_military_json(self, militare: Dict) -> str:
        import json
        units = []
        if militare.get("Reparto"):
            units.append({"unit": militare["Reparto"], "branch": militare.get("Arma", ""), "rank": militare.get("Grado", "")})
        return json.dumps(units, ensure_ascii=False)

    def _build_camps_json(self, camps: List) -> str:
        import json
        return json.dumps([{"name": c} for c in camps], ensure_ascii=False)

    def _build_subjects_json(self, decesso: Dict) -> str:
        import json
        subjects = []
        if decesso.get("Causa morte"):
            subjects.append({"type": "cause_of_death", "value": decesso["Causa morte"]})
        return json.dumps(subjects, ensure_ascii=False)

    # ─── Person mentions ──────────────────────────────────────────────
    def extract_person_mentions(self, record_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Estrae la menzione nominativa principale dalla scheda LeBI.

        Ogni scheda LeBI corrisponde a UNA persona. Non inventa nominativi.
        """
        import json
        people_json = record_data.get("people_metadata_json", "[]")
        try:
            people = json.loads(people_json)
        except (json.JSONDecodeError, TypeError):
            people = []

        mentions = []
        for p in people:
            surname = p.get("surname", "")
            name = p.get("name", "")
            full = f"{surname} {name}".strip()

            mentions.append({
                "surname_raw": surname,
                "name_raw": name,
                "full_name_raw": full,
                "normalized_surname": surname.upper().strip() if surname else "",
                "normalized_name": name.upper().strip() if name else "",
                "birth_date_text": p.get("birth_date", ""),
                "birth_place_raw": p.get("birth_place", ""),
                "rank_raw": p.get("rank", ""),
                "military_unit_raw": p.get("unit", ""),
                "service_number": p.get("service_number", ""),
                "role_in_metadata": "subject",
                "extraction_method": "html_parser",
                "extraction_confidence": 1.0,
            })

        return mentions

    # ─── Facts ────────────────────────────────────────────────────────
    def extract_facts(self, record_data: Dict[str, Any], mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Estrae fatti biografici strutturati dalla scheda LeBI.

        Tipi di fatto: birth, capture, death, internment.
        """
        import json
        facts = []
        mention_id = mentions[0].get("id") if mentions else None

        people_json = record_data.get("people_metadata_json", "[]")
        places_json = record_data.get("places_metadata_json", "[]")
        camps_json = record_data.get("camps_metadata_json", "[]")
        subjects_json = record_data.get("subjects_metadata_json", "[]")

        try:
            people = json.loads(people_json)
        except (json.JSONDecodeError, TypeError):
            people = []
        try:
            places = json.loads(places_json)
        except (json.JSONDecodeError, TypeError):
            places = []
        try:
            camps = json.loads(camps_json)
        except (json.JSONDecodeError, TypeError):
            camps = []
        try:
            subjects = json.loads(subjects_json)
        except (json.JSONDecodeError, TypeError):
            subjects = []

        person = people[0] if people else {}

        # Birth
        if person.get("birth_date") or person.get("birth_place"):
            facts.append({
                "fact_type": "birth",
                "date_text": person.get("birth_date", ""),
                "place_raw": person.get("birth_place", ""),
                "description": f"Nascita a {person.get('birth_place', '?')}",
                "extraction_method": "html_parser",
                "confidence": 1.0,
            })

        # Capture
        for place in places:
            if place.get("type") == "capture_place":
                facts.append({
                    "fact_type": "capture",
                    "place_raw": place.get("name", ""),
                    "description": f"Cattura a {place.get('name', '?')}",
                    "extraction_method": "html_parser",
                    "confidence": 1.0,
                })

        # Internment
        for camp in camps:
            facts.append({
                "fact_type": "internment",
                "place_raw": camp.get("name", ""),
                "description": f"Internamento a {camp.get('name', '?')}",
                "extraction_method": "html_parser",
                "confidence": 1.0,
            })

        # Death
        for place in places:
            if place.get("type") == "death_place":
                cause = ""
                for s in subjects:
                    if s.get("type") == "cause_of_death":
                        cause = s.get("value", "")
                facts.append({
                    "fact_type": "death",
                    "place_raw": place.get("name", ""),
                    "description": f"Decesso a {place.get('name', '?')}" + (f" — causa: {cause}" if cause else ""),
                    "extraction_method": "html_parser",
                    "confidence": 1.0,
                })

        # Burial
        for place in places:
            if place.get("type") == "burial_place":
                facts.append({
                    "fact_type": "burial",
                    "place_raw": place.get("name", ""),
                    "description": f"Sepoltura a {place.get('name', '?')}",
                    "extraction_method": "html_parser",
                    "confidence": 1.0,
                })

        # Set mention_id on all facts
        for f in facts:
            f["external_person_mention_id"] = mention_id

        return facts

    # ─── Digital objects ──────────────────────────────────────────────
    def detect_digital_objects(self, record_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rileva oggetti digitali (PDF scheda) senza presumere download autorizzato."""
        objects = []
        pdf_url = record_data.get("digital_object_url", "")
        if pdf_url:
            objects.append({
                "external_object_id": f"pdf_{record_data.get('external_id', '')}",
                "object_type": "pdf",
                "media_type": "application/pdf",
                "label": "Scheda PDF LeBI",
                "viewer_url": record_data.get("canonical_record_url", ""),
                "page_url": record_data.get("canonical_record_url", ""),
                "download_url": pdf_url,
                "digital_object_available": True,
                "publicly_viewable": True,
                "public_download_allowed": True,
                "authorization_required": False,
                "rights_statement": "ANRP — LeBI. Consultazione pubblica.",
                "credit_line": "ANRP — Lessico Biografico degli IMI",
            })
        return objects

    # ─── URL helpers ──────────────────────────────────────────────────
    def normalize_external_id(self, url: str) -> str:
        match = re.search(r"/caduti/show/(\d+)", url)
        return match.group(1) if match else url

    def get_canonical_url(self, url: str) -> str:
        return url

    def get_record_level_from_url(self, url: str) -> str:
        return "item"
