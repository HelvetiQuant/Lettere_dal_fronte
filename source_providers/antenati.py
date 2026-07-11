"""Provider Antenati — Portale Antenati (Ministero della Cultura / CINECA).

Registri di stato civile digitalizzati dagli Archivi di Stato italiani.
Ricerca via HTML parsing di /search-registry.
Manifest IIIF disponibili ma dietro AWS WAF (richiede browser headless per download).
"""

import re
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

from .base import SourceProvider

class ProviderAntenati(SourceProvider):
    name = "antenati"
    display_name = "Portale Antenati — Archivi di Stato Italia"
    country = "Italia"
    archive_name = "Antenati"
    base_url = "https://antenati.cultura.gov.it"
    authorized_domains = {"antenati.cultura.gov.it",
                          "dam-antenati.cultura.gov.it",
                          "iiif-antenati.cultura.gov.it"}
    cache_ttl_days = 90

    # Tipologie mappate per la ricerca
    TIPOLOGIE = {
        "nati": "Nati",
        "morti": "Morti",
        "matrimoni": "Matrimoni",
        "allegati_nati": "Allegati nati",
        "allegati_morti": "Allegati morti",
        "allegati_matrimoni": "Allegati matrimoni",
        "leva": "Leva",
        "cittadinanza": "Cittadinanza",
    }

    def search(self, query: str, filters: dict = None) -> List[dict]:
        """Cerca registri per comune + anno + tipologia.
        Non cerca per nome (gli allegati non hanno indici nominativi affidabili).
        """
        filters = filters or {}
        comune = filters.get("comune") or filters.get("localita") or ""
        anno = filters.get("anno") or ""
        tipologia = filters.get("tipologia") or ""

        # se la query contiene un nome persona, estrai comune dai cue
        if not comune:
            # prova a estrarre un toponimo dalla query
            m = re.search(r'\b(?:a|in|di|da|presso)\s+([A-Z][a-z]+)', query)
            if m:
                comune = m.group(1)

        if not comune:
            return []

        results = []
        # se anno non specificato, cerca anni rilevanti
        anni = [anno] if anno else self._guess_years(query, filters)

        for a in anni:
            if not a:
                continue
            registri = self._search_registry(comune, a, tipologia)
            results.extend(registri)

        return results[:30]

    def _guess_years(self, query: str, filters: dict) -> List[str]:
        """Stima anni rilevanti: nascita, morte, leva."""
        anni = []
        if filters.get("anno_nascita"):
            anni.append(str(filters["anno_nascita"]))
            anni.append(str(int(filters["anno_nascita"]) + 20))  # leva
        if filters.get("anno_morte"):
            anni.append(str(filters["anno_morte"]))
            # trascrizioni morte post-belliche
            for offset in range(1, 4):
                anni.append(str(int(filters["anno_morte"]) + offset))
        # anni dalla query
        for m in re.finditer(r'\b(19\d{2})\b', query):
            y = m.group(1)
            if y not in anni:
                anni.append(y)
        return anni[:6]

    def _search_registry(self, comune: str, anno: str, tipologia: str = "") -> List[dict]:
        """Chiama /search-registry e parsea i risultati HTML."""
        params = {"lang": "it", "localita": comune, "anno": str(anno)}
        if tipologia:
            params["tipologia"] = tipologia

        try:
            resp = requests.get(
                f"{self.base_url}/search-registry",
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 ricerca-storica-IMI/1.0"},
                timeout=30, verify=False,
            )
            if resp.status_code != 200:
                return []
        except Exception:
            return []

        html = resp.text
        # estrai ARK links unici
        ark_ids = list(set(re.findall(r'href=["\x27](/ark:/[^"\x27]+)["\x27]', html)))
        results = []

        for ark_path in ark_ids[:10]:
            ark_id = ark_path.split("/")[-1]
            meta = self._parse_ark_page(ark_path)
            if meta:
                results.append({
                    "provider": self.name,
                    "provider_record_id": ark_id,
                    "archivio": meta.get("archivio", "Archivio di Stato"),
                    "fondo": meta.get("fondo", ""),
                    "serie": "Stato civile",
                    "segnatura": ark_id,
                    "titolo": meta.get("registro", ""),
                    "description": f"Registro di stato civile - {meta.get('tipologia', '')}",
                    "source_type": "civil_registry",
                    "document_type": meta.get("tipologia", "Stato civile italiano"),
                    "place": meta.get("comune", comune),
                    "date_start": str(anno),
                    "catalog_url": f"{self.base_url}{ark_path}",
                    "direct_url": f"{self.base_url}{ark_path}",
                    "iiif_manifest": meta.get("iiif_manifest", ""),
                    "access_type": "online" if meta.get("iiif_manifest") else "catalog_only",
                    "downloadable": bool(meta.get("iiif_manifest")),
                    "confidence": 0.7,
                })

        return results

    def _parse_ark_page(self, ark_path: str) -> Optional[dict]:
        """Visita la pagina ARK ed estrae metadati dal breadcrumb + manifestId."""
        try:
            resp = requests.get(
                f"{self.base_url}{ark_path}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 ricerca-storica-IMI/1.0"},
                timeout=30, verify=False,
            )
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        html = resp.text
        meta = {}

        # H2 = titolo registro
        h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S)
        h2_clean = [re.sub(r'<[^>]+>', '', h).strip() for h in h2]
        if len(h2_clean) > 1:
            meta["registro"] = h2_clean[1]

        # Breadcrumb
        breadcrumb = re.search(
            r'class=["\x27][^"\x27]*breadcrumb[^"\x27]*["\x27][^>]*>(.*?)</(?:ul|ol|nav)>',
            html, re.S)
        if breadcrumb:
            items = [re.sub(r'<[^>]+>', '', a).strip()
                     for a in re.findall(r'<a[^>]*>([^<]+)</a>', breadcrumb.group(0))]
            items = [i for i in items if i and i not in
                     ("Home", "Il Portale", "Istruzioni per l\u2019uso",
                      "Richieste di certificati")]
            if len(items) >= 1: meta["tipologia"] = items[0]
            if len(items) >= 2: meta["comune"] = items[1]
            if len(items) >= 3: meta["archivio"] = items[2]
            if len(items) >= 4: meta["fondo"] = items[3]

        # manifestId
        m = re.search(r"manifestId['\x22]\s*[:=]\s*['\x22]([^'\x22]+)", html)
        if m:
            meta["iiif_manifest"] = m.group(1)

        return meta if meta.get("registro") or meta.get("comune") else None

    def get_metadata(self, record_id: str) -> dict:
        ark_path = f"/ark:/12657/{record_id}"
        meta = self._parse_ark_page(ark_path)
        if not meta:
            return {}
        return {
            "provider": self.name,
            "provider_record_id": record_id,
            "archivio": meta.get("archivio", ""),
            "fondo": meta.get("fondo", ""),
            "titolo": meta.get("registro", ""),
            "catalog_url": f"{self.base_url}{ark_path}",
            "iiif_manifest": meta.get("iiif_manifest", ""),
            "access_type": "online" if meta.get("iiif_manifest") else "catalog_only",
        }

    def get_iiif_manifest(self, record_id: str) -> Optional[dict]:
        meta = self.get_metadata(record_id)
        manifest_url = meta.get("iiif_manifest")
        if not manifest_url:
            return None
        try:
            resp = requests.get(manifest_url, timeout=20, verify=False,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                return resp.json()
        except Exception:
            pass
        return None

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        link = f"{self.base_url}/ark:/12657/{record_id}"
        return link
