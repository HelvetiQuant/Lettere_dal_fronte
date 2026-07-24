"""Adapter per Archimista — piattaforma archivistica usata da CRI Milano.

URL patterns:
  /fonds/{id}              → fondo o sottoserie
  /fonds/{id}/units/{uid}  → unità archivistica
  /fonds/{id}/units        → lista unità di un fondo

Struttura HTML (da analisi reale):
  - h1: titolo + periodo
  - "Segnatura definitiva: b. X fasc. Y"
  - "Link risorsa: URL"
  - Descrizione testuale
  - Navigazione: "Descrizione" | "Unità archivistiche"
"""
import re
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from sources_external_base import (
    SourceAdapter, normalize_url, is_canonical_record_url,
    compute_metadata_hash, RateLimiter
)


class ArchimistaAdapter(SourceAdapter):
    """Adapter per portali basati su Archimista (es: CRI Milano)."""

    provider_id = "cri_milano"
    display_name = "Archivio Storico CRI Milano"
    archive_name = "Archivio Storico della Croce Rossa Italiana - Comitato di Milano"
    archive_branch = "Milano"
    base_url = "https://cri-mi.archimista.com"
    user_agent = "IMI-Extractor/1.0 (research; +https://imi-extractor.org)"
    rate_limiter = RateLimiter(min_delay=2.0)

    # ─── Pattern regex ────────────────────────────────────────────────
    RE_SEGNATURA = re.compile(r"Segnatura\s+definitiva:\s*(.+?)(?:\n|$)", re.IGNORECASE)
    RE_BOX_FILE = re.compile(r"b\.\s*(\d+)\s*fasc\.\s*(\d+)", re.IGNORECASE)
    RE_DATE_RANGE = re.compile(r"\((\d{4})\s*[-–]\s*(\d{4}|s\.d\.)\)")
    RE_DATE_SINGLE = re.compile(r"\((\d{4})\)")
    RE_LINK_RISORSA = re.compile(r"Link risorsa:\s*(https?://[^\s\]]+)", re.IGNORECASE)
    RE_PROTOCOLLO = re.compile(r"numero di protocollo|protocollo\s+n\.?\s*(\d+)", re.IGNORECASE)
    RE_PERSON_MENTION = re.compile(
        r"(?:cittadinanza|cittadino|sig\.|signor|signora|gentile)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        re.UNICODE
    )

    def discover_resources(self, start_url: str, max_records: int = 0) -> List[Dict[str, Any]]:
        """Scopre ricorsivamente fondo → serie → sottoserie → unità."""
        results = []
        visited = set()

        def _discover(url: str, depth: int = 0):
            if url in visited:
                return
            visited.add(url)
            if max_records and len(results) >= max_records:
                return

            html, status = self.fetch_page(url)
            if not html or status >= 400:
                return

            soup = BeautifulSoup(html, "html.parser")

            # Estrai info dalla pagina corrente
            record = self._parse_page_metadata(url, soup, status)
            if record:
                results.append(record)

            # Trova link a unità archivistiche
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(self.base_url, href)
                normalized = normalize_url(full_url)

                # Link a unità
                if "/units/" in normalized and normalized not in visited:
                    _discover(normalized, depth + 1)
                # Link a sottofondi/serie
                elif re.match(r".*/fonds/\d+$", normalized) and normalized != url and normalized not in visited:
                    if depth < 3:  # limita profondità
                        _discover(normalized, depth + 1)

                if max_records and len(results) >= max_records:
                    return

        _discover(start_url)
        return results

    def parse_record(self, url: str) -> Optional[Dict[str, Any]]:
        """Recupera e analizza una singola scheda Archimista."""
        html, status = self.fetch_page(url)
        if not html or status >= 400:
            return {
                "canonical_record_url": normalize_url(url),
                "external_id": self.normalize_external_id(url),
                "record_level": self.get_record_level_from_url(url),
                "http_status": status,
                "access_status": "unreachable" if status >= 400 else "active",
            }

        soup = BeautifulSoup(html, "html.parser")
        return self._parse_page_metadata(url, soup, status)

    def _parse_page_metadata(self, url: str, soup: BeautifulSoup, http_status: int) -> Dict[str, Any]:
        """Estrae metadati strutturati dalla pagina Archimista."""
        canonical = normalize_url(url)
        external_id = self.normalize_external_id(url)
        record_level = self.get_record_level_from_url(url)

        # Titolo da h1
        h1 = soup.find("h1")
        title_raw = h1.get_text(strip=True) if h1 else ""

        # Estrai titolo e date dal h1: "Titolo (1948 - 1952)"
        title = title_raw
        date_text = None
        date_from = None
        date_to = None

        m_range = self.RE_DATE_RANGE.search(title_raw)
        m_single = self.RE_DATE_SINGLE.search(title_raw)
        if m_range:
            date_text = f"{m_range.group(1)} - {m_range.group(2)}"
            date_from = m_range.group(1)
            date_to = m_range.group(2) if m_range.group(2) != "s.d." else None
            title = self.RE_DATE_RANGE.sub("", title_raw).strip()
        elif m_single:
            date_text = m_single.group(1)
            date_from = m_single.group(1)
            date_to = m_single.group(1)
            title = self.RE_DATE_SINGLE.sub("", title_raw).strip()

        # Pulisci titolo
        title = title.rstrip(" ()[]").strip()

        # Testo completo della pagina
        full_text = soup.get_text(separator="\n", strip=True)

        # Segnatura
        reference_code = None
        box_number = None
        file_number = None
        m_seg = self.RE_SEGNATURA.search(full_text)
        if m_seg:
            reference_code = m_seg.group(1).strip()
            m_box = self.RE_BOX_FILE.search(reference_code)
            if m_box:
                box_number = m_box.group(1)
                file_number = m_box.group(2)

        # Link risorsa (URL canonico dichiarato dalla scheda)
        canonical_declared = None
        m_link = self.RE_LINK_RISORSA.search(full_text)
        if m_link:
            canonical_declared = normalize_url(m_link.group(1))
        # Usa il link dichiarato se valido, altrimenti l'URL corrente
        final_canonical = canonical_declared if canonical_declared else canonical

        # Descrizione: testo dopo "Sottoserie"/"Unità"/"Serie" e prima di "Link risorsa"
        description = None
        level_markers = ["Sottoserie", "Unità", "Serie", "Fondo", "Sottofondo"]
        text_lines = full_text.split("\n")
        desc_lines = []
        in_desc = False
        for line in text_lines:
            line = line.strip()
            if not line:
                continue
            if line in level_markers:
                in_desc = True
                continue
            if "Link risorsa" in line:
                in_desc = False
                continue
            if in_desc and line and line != title_raw:
                desc_lines.append(line)
        if desc_lines:
            description = " ".join(desc_lines)

        # Livello archivistico dalla pagina
        if "Sottoserie" in full_text:
            record_level = "subseries"
        elif "Unità" in full_text and "archivistiche" not in full_text.split("Unità")[0][-50:]:
            record_level = "archival_unit"
        elif "Serie" in full_text and "Sottoserie" not in full_text:
            record_level = "series"
        elif "Fondo" in full_text:
            record_level = "fonds"

        # Rileva oggetti digitali
        digital_available = False
        digital_url = None
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and "placeholder" not in src.lower():
                digital_available = True
                digital_url = urljoin(self.base_url, src)
                break
        # Link a viewer/oggetti digitali
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            if "digital" in href or "viewer" in href or "object" in href:
                digital_available = True
                digital_url = urljoin(self.base_url, link["href"])
                break

        # Protocollo
        protocol_number = None
        if self.RE_PROTOCOLLO.search(full_text):
            m_proto = self.RE_PROTOCOLLO.search(full_text)
            if m_proto.group(1):
                protocol_number = m_proto.group(1)
            else:
                protocol_number = "presente"

        # Parent URL
        parent_url = self.get_parent_url(canonical)

        # Estrai fonds_id e series dalla gerarchia URL
        parsed = urlparse(canonical)
        parts = [p for p in parsed.path.split("/") if p]
        fonds_external_id = None
        series_external_id = None
        if parts and parts[0] == "fonds":
            fonds_external_id = parts[1]
            if len(parts) >= 4 and parts[2] == "series":
                series_external_id = parts[3]

        # Metadati JSON strutturati
        places_metadata = self._extract_places(full_text, description)
        subjects_metadata = self._extract_subjects(full_text, description)
        people_metadata = self._extract_people_metadata(full_text, description)

        data = {
            "provider": self.provider_id,
            "archive_name": self.archive_name,
            "archive_branch": self.archive_branch,
            "external_id": external_id,
            "record_level": record_level,
            "title": title or None,
            "description": description,
            "date_text": date_text,
            "date_from": date_from,
            "date_to": date_to,
            "fonds_external_id": fonds_external_id,
            "fonds_title": None,  # Da arricchire con query parent
            "series_external_id": series_external_id,
            "series_title": None,
            "parent_external_id": self.normalize_external_id(parent_url) if parent_url else None,
            "reference_code": reference_code,
            "box_number": box_number,
            "file_number": file_number,
            "protocol_number": protocol_number,
            "language": "ita",
            "canonical_record_url": final_canonical,
            "parent_record_url": parent_url,
            "digital_object_available": digital_available,
            "digital_object_url": digital_url,
            "access_status": "active" if http_status < 400 else "unreachable",
            "http_status": http_status,
            "people_metadata_json": json.dumps(people_metadata, ensure_ascii=False) if people_metadata else None,
            "places_metadata_json": json.dumps(places_metadata, ensure_ascii=False) if places_metadata else None,
            "subjects_metadata_json": json.dumps(subjects_metadata, ensure_ascii=False) if subjects_metadata else None,
            "military_units_metadata_json": None,
            "camps_metadata_json": None,
        }

        data["metadata_hash"] = compute_metadata_hash(data)
        return data

    def _extract_places(self, full_text: str, description: str) -> List[str]:
        """Estrae luoghi menzionati nei metadati."""
        text = description or full_text
        places = set()
        # Pattern: nomi propri di luogo italiani comuni
        place_patterns = [
            r"\b(Milano|Roma|Trieste|Torino|Napoli|Bologna|Firenze|Genova|Venezia|Brescia|Bergamo|Como|Varese|Monza|Pavia|Verona|Padova|Bologna|Bari|Palermo|Cagliari)\b",
        ]
        for pattern in place_patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                places.add(m.group(1).capitalize())
        return list(places)

    def _extract_subjects(self, full_text: str, description: str) -> List[str]:
        """Estrae soggetti/argomenti dai metadati."""
        text = description or full_text
        subjects = set()
        subject_keywords = [
            "dispersi", "scomparsi", "prigionieri", "internati", "profughi",
            "feriti", "deceduti", "rimpatrio", "ricerca", "corrispondenza",
            "Ufficio Prigionieri", "Servizio sociale", "Comitato Regionale",
            "Croce Rossa", "guerra", "prima guerra mondiale", "seconda guerra mondiale",
        ]
        for kw in subject_keywords:
            if kw.lower() in text.lower():
                subjects.add(kw)
        return list(subjects)

    def _extract_people_metadata(self, full_text: str, description: str) -> List[Dict[str, str]]:
        """Estrae metadati di persone esplicitamente menzionate.
        
        NON inventa nominativi. Estrae solo se esplicitamente presenti.
        """
        text = description or full_text
        people = []
        # Pattern: "cittadino Nome Cognome" o "sig. Nome Cognome"
        for m in self.RE_PERSON_MENTION.finditer(text):
            name = m.group(1).strip()
            if name and len(name) > 2:
                people.append({"raw": name, "context": m.group(0)})
        return people

    def extract_person_mentions(self, record_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Estrae menzioni nominative dai metadati.
        
        Solo nominativi esplicitamente presenti. Non usa il titolo generale
        del fascicolo come prova della presenza di una persona specifica.
        """
        mentions = []
        people_json = record_data.get("people_metadata_json")
        if not people_json:
            return mentions

        try:
            people = json.loads(people_json)
        except (json.JSONDecodeError, TypeError):
            return mentions

        for p in people:
            raw = p.get("raw", "")
            if not raw or len(raw) < 3:
                continue
            # Split cognome/nome (separatore spazio)
            parts = raw.strip().split(None, 1)
            surname = parts[0] if parts else raw
            name = parts[1] if len(parts) > 1 else None

            mentions.append({
                "surname_raw": surname,
                "name_raw": name,
                "full_name_raw": raw,
                "normalized_surname": surname.lower().strip() if surname else None,
                "normalized_name": name.lower().strip() if name else None,
                "role_in_metadata": "mentioned",
                "source_text": p.get("context", raw),
                "extraction_method": "regex",
                "extraction_confidence": 0.7,
                "human_verified": False,
            })

        return mentions

    def extract_facts(self, record_data: Dict[str, Any], mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Estrae fatti descritti nei metadati.
        
        Distingue tra fatto riferito a una persona e argomento generale del fascicolo.
        Non converte una descrizione generale in un fatto personale.
        """
        facts = []
        description = record_data.get("description") or ""
        title = record_data.get("title") or ""

        # Fatto generale: tipo di corrispondenza
        if "dispersi" in description.lower() or "scomparsi" in description.lower():
            facts.append({
                "fact_type": "ricerca_disperso",
                "fact_value": "Corrispondenza relativa a informazioni su dispersi e/o scomparsi",
                "description": description[:500] if description else None,
                "source_text": description[:200] if description else title,
                "extraction_method": "keyword_match",
                "confidence": 0.9,
                "human_verified": False,
            })

        # Protocollo
        if record_data.get("protocol_number"):
            facts.append({
                "fact_type": "numero_protocollo",
                "fact_value": record_data["protocol_number"],
                "description": "Le lettere riportano un numero di protocollo",
                "source_text": description[:200] if description else None,
                "extraction_method": "regex",
                "confidence": 0.95,
                "human_verified": False,
            })

        # Non creare fatti personali da descrizioni generali
        # I fatti personali verranno estratti solo da OCR di documenti specifici

        return facts

    def detect_digital_objects(self, record_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rileva oggetti digitali senza presumere che siano scaricabili."""
        objects = []
        if not record_data.get("digital_object_available"):
            return objects

        obj = {
            "external_object_id": None,
            "object_type": "image",
            "media_type": "unknown",
            "label": record_data.get("title", "Digital object"),
            "viewer_url": record_data.get("digital_object_url"),
            "page_url": record_data.get("canonical_record_url"),
            "download_url": None,  # Non presumere che sia scaricabile
            "digital_object_available": True,
            "publicly_viewable": True,  # Visibile nella pagina pubblica
            "public_download_allowed": False,  # Da verificare
            "authorization_required": True,  # Prudenziale
            "rights_statement": "Diritti riservati - Archivio Storico CRI Milano",
            "credit_line": "© Archivio Storico della Croce Rossa Italiana - Comitato di Milano",
        }
        objects.append(obj)
        return objects
