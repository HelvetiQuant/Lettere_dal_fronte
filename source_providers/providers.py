"""Provider stub per archivi non ancora integrati con dati locali.

Ogni stub implementa search() che cerca nel DB locale se ci sono tabelle,
altrimenti ritorna metadati con URL catalogo per ricerca manuale.
Estendibile: sostituire search() con chiamate API reali quando disponibili.
"""

from typing import Dict, List, Optional

import requests

from database import get_conn
from .base import SourceProvider, _dict_factory


class ProviderArolsen(SourceProvider):
    """Arolsen Archives — International Tracing Service (ITS)."""
    name = "arolsen"
    display_name = "Arolsen Archives — ITS"
    country = "Germania"
    archive_name = "Arolsen"
    base_url = "https://collections.arolsen-archives.org"
    authorized_domains = {"collections.arolsen-archives.org"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        q = query.replace(" ", "+")
        try:
            url = f"{self.base_url}/search/"
            params = {"q": query, "page": 1, "per_page": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False,
                                headers={"Accept": "application/json",
                                         "User-Agent": "ricerca-storica-IMI/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("results", data.get("items", [])):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": str(item.get("id", "")),
                        "archivio": "Arolsen Archives",
                        "titolo": item.get("title", ""),
                        "description": (item.get("description") or "")[:200],
                        "source_type": "tracing_document",
                        "catalog_url": f"{self.base_url}/archive/{item.get('id', '')}",
                        "direct_url": item.get("digital_object", {}).get("url", "") if isinstance(item.get("digital_object"), dict) else "",
                        "access_type": "login",
                        "downloadable": False,
                        "confidence": 0.7,
                    })
                if results:
                    return results
        except Exception:
            pass
        return [{
            "provider": self.name,
            "provider_record_id": "",
            "archivio": "Arolsen Archives",
            "titolo": f"Ricerca: {query}",
            "description": "Cerca nel catalogo Arolsen Archives (ITS). "
                           "Accesso richiede account gratuito.",
            "source_type": "tracing_document",
            "catalog_url": f"{self.base_url}/search/?q={q}",
            "direct_url": f"{self.base_url}/search/?q={q}",
            "access_type": "login",
            "downloadable": False,
            "confidence": 0.6,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "login"}


class ProviderBundesarchiv(SourceProvider):
    """Bundesarchiv — Archivio Federale Tedesco.

    Invenio (il catalogo online) è un'applicazione JSF che richiede login
    e non espone un endpoint JSON pubblico. Questo provider prova i
    possibili endpoint, quindi ritorna link di ricerca catalogo e al dump
    open data per consentire ricerca manuale o bulk.
    """
    name = "bundesarchiv"
    display_name = "Bundesarchiv"
    country = "Germania"
    archive_name = "Bundesarchiv"
    base_url = "https://www.bundesarchiv.de"
    invenio_url = "https://invenio.bundesarchiv.de"
    open_data_url = "https://open-data.bundesarchiv.de/ddb-bestand"
    authorized_domains = {"www.bundesarchiv.de", "invenio.bundesarchiv.de", "open-data.bundesarchiv.de"}
    cache_ttl_days = 90

    def _try_api(self, query: str) -> Optional[List[dict]]:
        """Prova gli endpoint JSON noti; ritorna None se nessuno risponde."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (ricerca-storica-IMI/1.0)",
        }
        endpoints = [
            "https://invenio.bundesarchiv.de/invenio/api/records",
            "https://invenio.bundesarchiv.de/api/records",
            "https://invenio.bundesarchiv.de/api/records/",
        ]
        for url in endpoints:
            try:
                resp = requests.get(url, params={"q": query, "size": 10, "sort": "bestmatch"},
                                    timeout=12, verify=False, headers=headers)
                if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                    data = resp.json()
                    hits = data.get("hits", {}).get("hits", [])
                    if hits:
                        results = []
                        for hit in hits:
                            md = hit.get("metadata", {})
                            results.append({
                                "provider": self.name,
                                "provider_record_id": str(hit.get("id", "")),
                                "archivio": "Bundesarchiv",
                                "titolo": md.get("title", "") or md.get("description", "") or f"Record {hit.get('id', '')}",
                                "description": (md.get("description") or "")[:200],
                                "source_type": "military_document",
                                "catalog_url": f"{self.invenio_url}/invenio/record/{hit.get('id', '')}",
                                "direct_url": md.get("digital_object", {}).get("url", "") if isinstance(md.get("digital_object"), dict) else "",
                                "access_type": "online",
                                "downloadable": bool(md.get("digital_object")),
                                "confidence": 0.7,
                            })
                        return results
            except Exception:
                continue
        return None

    def search(self, query: str, filters: dict = None) -> List[dict]:
        # 1. API JSON
        api_results = self._try_api(query)
        if api_results:
            return api_results

        # 2. Fallback: link di ricerca catalogo e risorse correlate
        q = query.replace(" ", "+")
        results = [
            {
                "provider": self.name,
                "provider_record_id": "",
                "archivio": "Bundesarchiv",
                "titolo": f"Ricerca in Invenio: {query}",
                "description": "Catalogo online del Bundesarchiv (Invenio). Richiede autenticazione per la ricerca avanzata.",
                "source_type": "military_document",
                "catalog_url": f"{self.invenio_url}/invenio/",
                "direct_url": "",
                "access_type": "login",
                "downloadable": False,
                "confidence": 0.5,
            },
            {
                "provider": self.name,
                "provider_record_id": "",
                "archivio": "Bundesarchiv",
                "titolo": f"Open Data / DDB-Bestand: {query}",
                "description": "Dump XML pubblici del catalogo (GovData). Possibile ricerca offline sul testo completo.",
                "source_type": "open_data",
                "catalog_url": f"{self.open_data_url}/",
                "direct_url": "",
                "access_type": "online",
                "downloadable": True,
                "confidence": 0.4,
            },
            {
                "provider": self.name,
                "provider_record_id": "",
                "archivio": "Bundesarchiv",
                "titolo": f"Recherchesysteme: {query}",
                "description": "Panoramica dei sistemi di ricerca del Bundesarchiv (invenio, Digitaler Lesesaal, Bildarchiv, ecc.).",
                "source_type": "reference_page",
                "catalog_url": f"{self.base_url}/im-archiv-recherchieren/archivgut-recherchieren/recherchesysteme/",
                "direct_url": "",
                "access_type": "online",
                "downloadable": False,
                "confidence": 0.4,
            },
        ]

        # 3. Se disponibile un file XML open data corrispondente a 'filters', potremmo cercare lì
        if filters and filters.get("fondo_xml"):
            xml_url = f"{self.open_data_url}/{filters['fondo_xml']}"
            results.append({
                "provider": self.name,
                "provider_record_id": filters["fondo_xml"],
                "archivio": "Bundesarchiv",
                "titolo": f"XML fondo: {filters['fondo_xml']}",
                "description": "File XML specifico del fondo indicato, scaricabile dal portale open data.",
                "source_type": "open_data",
                "catalog_url": xml_url,
                "direct_url": xml_url,
                "access_type": "online",
                "downloadable": True,
                "confidence": 0.6,
            })
        return results

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderSHD(SourceProvider):
    """Service Historique de la Défense (Francia)."""
    name = "shd"
    display_name = "SHD — Service Historique de la Défense"
    country = "Francia"
    archive_name = "SHD"
    base_url = "https://www.servicehistorique.sga.defense.gouv.fr"
    authorized_domains = {"www.servicehistorique.sga.defense.gouv.fr"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        q = query.replace(" ", "+")
        try:
            url = "https://www.memoiredeshommes.sga.defense.gouv.fr/fr/search.php"
            params = {"q": query, "n": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False,
                                headers={"Accept": "text/html",
                                         "User-Agent": "ricerca-storica-IMI/1.0"})
            if resp.status_code == 200:
                import re
                links = re.findall(r'href="(/fr/article\.php[^"]*?)"', resp.text)
                results = []
                seen = set()
                for link in links[:10]:
                    full_url = f"https://www.memoiredeshommes.sga.defense.gouv.fr{link}"
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    title_match = re.search(r'<title>(.*?)</title>', resp.text[:5000])
                    results.append({
                        "provider": self.name,
                        "provider_record_id": link,
                        "archivio": "SHD — Mémoire des Hommes",
                        "titolo": f"Risultato: {query}",
                        "description": "Service Historique de la Défense — Mémoire des Hommes.",
                        "source_type": "military_document",
                        "catalog_url": full_url,
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": 0.5,
                    })
                if results:
                    return results
        except Exception:
            pass
        return [{
            "provider": self.name,
            "provider_record_id": "",
            "archivio": "SHD",
            "titolo": f"Ricerca: {query}",
            "description": "Service Historique de la Défense — Mémoire des Hommes.",
            "source_type": "military_document",
            "catalog_url": f"https://www.memoiredeshommes.sga.defense.gouv.fr/fr/search.php?q={q}",
            "direct_url": "",
            "access_type": "online",
            "downloadable": False,
            "confidence": 0.5,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderNationalArchivesUK(SourceProvider):
    """The National Archives (UK)."""
    name = "tna"
    display_name = "The National Archives (UK)"
    country = "UK"
    archive_name = "TNA"
    base_url = "https://discovery.nationalarchives.gov.uk"
    authorized_domains = {"discovery.nationalarchives.gov.uk", "www.nationalarchives.gov.uk"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        # TNA Discovery API
        try:
            url = f"{self.base_url}/API/search/records"
            params = {"q": query, "max": 10}
            resp = requests.get(url, params=params, timeout=20,
                                headers={"Accept": "application/json"},
                                verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for r in data.get("records", []):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": r.get("id"),
                        "archivio": "TNA",
                        "titolo": r.get("title", ""),
                        "description": r.get("scopeContent", {}).get("description", "")[:200],
                        "source_type": "military_document",
                        "catalog_url": f"{self.base_url}/details/r/{r.get('id')}",
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": r.get("isDigital", False),
                        "confidence": 0.7,
                    })
                return results
        except Exception:
            pass
        return [{
            "provider": self.name,
            "archivio": "TNA",
            "titolo": f"Ricerca: {query}",
            "catalog_url": f"{self.base_url}/results/r?q={query.replace(' ', '+')}",
            "access_type": "online",
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": f"{self.base_url}/details/r/{record_id}"}


class ProviderEuropeana(SourceProvider):
    """Europeana — aggregator europeo."""
    name = "europeana"
    display_name = "Europeana"
    country = "Europa"
    archive_name = "Europeana"
    base_url = "https://www.europeana.eu"
    authorized_domains = {"www.europeana.eu", "api.europeana.eu"}
    cache_ttl_days = 60

    def search(self, query: str, filters: dict = None) -> List[dict]:
        # Europeana Search API (key pubblica demo)
        try:
            url = "https://api.europeana.eu/record/v2/search.json"
            params = {
                "wskey": "api2demo",
                "query": f"{query} AND type:TEXT",
                "rows": 10,
                "profile": "rich",
            }
            resp = requests.get(url, params=params, timeout=20, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("items", []):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item.get("id"),
                        "archivio": "Europeana",
                        "titolo": (item.get("title") or [""])[0] if isinstance(item.get("title"), list) else str(item.get("title", "")),
                        "description": (item.get("dcDescription") or [""])[0] if isinstance(item.get("dcDescription"), list) else "",
                        "source_type": "digitized_document",
                        "catalog_url": f"https://www.europeana.eu/item/{item.get('id')}",
                        "direct_url": (item.get("edmIsShownAt") or [""])[0] if isinstance(item.get("edmIsShownAt"), list) else "",
                        "thumbnail": (item.get("edmPreview") or [""])[0] if isinstance(item.get("edmPreview"), list) else "",
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": 0.6,
                    })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": f"https://www.europeana.eu/item/{record_id}"}


class ProviderGallica(SourceProvider):
    """Gallica — BnF (Bibliothèque nationale de France)."""
    name = "gallica"
    display_name = "Gallica — BnF"
    country = "Francia"
    archive_name = "Gallica"
    base_url = "https://gallica.bnf.fr"
    authorized_domains = {"gallica.bnf.fr"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://gallica.bnf.fr/SRU"
            params = {
                "operation": "searchRetrieve",
                "version": "1.2",
                "query": f'gallica all "{query}"',
                "maximumRecords": 10,
            }
            resp = requests.get(url, params=params, timeout=20, verify=False,
                                headers={"User-Agent": "ricerca-storica-IMI/1.0"})
            if resp.status_code == 200:
                # parse XML SRU (semplificato)
                import re
                records = re.findall(r'<record>(.*?)</record>', resp.text, re.S)
                results = []
                for rec in records[:10]:
                    title = re.search(r'<dc:title>(.*?)</dc:title>', rec, re.S)
                    identifier = re.search(r'<dc:identifier>(.*?)</dc:identifier>', rec, re.S)
                    if identifier:
                        ark = identifier.group(1)
                        results.append({
                            "provider": self.name,
                            "provider_record_id": ark,
                            "archivio": "Gallica",
                            "titolo": title.group(1) if title else "",
                            "source_type": "digitized_book",
                            "catalog_url": ark,
                            "direct_url": ark,
                            "iiif_manifest": f"https://gallica.bnf.fr/iiif/ark:/12148/{ark.split('/')[-1]}/manifest.json",
                            "access_type": "online",
                            "downloadable": True,
                            "confidence": 0.6,
                        })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": record_id}


class ProviderInternetArchive(SourceProvider):
    """Internet Archive."""
    name = "internetarchive"
    display_name = "Internet Archive"
    country = "USA"
    archive_name = "Internet Archive"
    base_url = "https://archive.org"
    authorized_domains = {"archive.org"}
    cache_ttl_days = 120

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://archive.org/advancedsearch.php"
            params = {
                "q": query,
                "fl[]": ["identifier", "title", "description", "date", "mediatype"],
                "rows": 10,
                "output": "json",
            }
            resp = requests.get(url, params=params, timeout=20, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for doc in data.get("response", {}).get("docs", []):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": doc.get("identifier"),
                        "archivio": "Internet Archive",
                        "titolo": doc.get("title", ""),
                        "description": (doc.get("description") or "")[:200],
                        "source_type": "digitized_document",
                        "date_start": doc.get("date", ""),
                        "catalog_url": f"https://archive.org/details/{doc.get('identifier')}",
                        "direct_url": f"https://archive.org/details/{doc.get('identifier')}",
                        "access_type": "online",
                        "downloadable": True,
                        "confidence": 0.5,
                    })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": f"https://archive.org/details/{record_id}"}


class ProviderGoogleBooks(SourceProvider):
    """Google Books."""
    name = "googlebooks"
    display_name = "Google Books"
    country = "USA"
    archive_name = "Google Books"
    base_url = "https://books.google.com"
    authorized_domains = {"books.google.com"}
    cache_ttl_days = 60

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://www.googleapis.com/books/v1/volumes"
            params = {"q": query, "maxResults": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("items", []):
                    vi = item.get("volumeInfo", {})
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item.get("id"),
                        "archivio": "Google Books",
                        "titolo": vi.get("title", ""),
                        "description": (vi.get("description") or "")[:200],
                        "source_type": "book",
                        "date_start": vi.get("publishedDate", ""),
                        "catalog_url": vi.get("infoLink", ""),
                        "direct_url": vi.get("previewLink", ""),
                        "thumbnail": vi.get("imageLinks", {}).get("thumbnail", ""),
                        "access_type": "online",
                        "downloadable": "full" in (vi.get("accessInfo", {}).get("viewability", "")).lower(),
                        "confidence": 0.5,
                    })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": f"https://books.google.com/books?id={record_id}"}


class ProviderABMC(SourceProvider):
    """American Battle Monuments Commission."""
    name = "abmc"
    display_name = "ABMC — American Battle Monuments Commission"
    country = "USA"
    archive_name = "ABMC"
    base_url = "https://www.abmc.gov"
    authorized_domains = {"www.abmc.gov"}
    cache_ttl_days = 120

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = f"{self.base_url}/database/api/search"
            params = {"name": query, "limit": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for r in data.get("results", []):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": r.get("id"),
                        "archivio": "ABMC",
                        "titolo": f"{r.get('first_name', '')} {r.get('last_name', '')}",
                        "source_type": "casualty_record",
                        "catalog_url": f"{self.base_url}/database/search?name={query}",
                        "access_type": "online",
                        "confidence": 0.7,
                    })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderLibraryCanada(SourceProvider):
    """Library and Archives Canada."""
    name = "lac"
    display_name = "Library and Archives Canada"
    country = "Canada"
    archive_name = "LAC"
    base_url = "https://www.bac-lac.gc.ca"
    authorized_domains = {"www.bac-lac.gc.ca"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://recherche-collection-search.bac-lac.gc.ca/Search"
            params = {"q": query, "page": 1, "pageSize": 10, "format": "json"}
            resp = requests.get(url, params=params, timeout=20, verify=False,
                headers={"User-Agent": "ricerca-storica-IMI/1.0",
                         "Accept": "application/json"})
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
                results = []
                for item in data.get("results", data.get("items", [])):
                    item_id = item.get("id", "") or item.get("key", "")
                    title = item.get("title", "") or item.get("label", "")
                    pub_year = item.get("year", "") or item.get("date", "")
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item_id,
                        "archivio": "LAC — Library and Archives Canada",
                        "titolo": title,
                        "description": (item.get("description") or "")[:200],
                        "source_type": "digitized_document",
                        "date_start": str(pub_year) if pub_year else "",
                        "catalog_url": f"https://recherche-collection-search.bac-lac.gc.ca/eng/Record/{item_id}" if item_id else f"{self.base_url}/eng/search/Pages/search.aspx?k={query.replace(' ', '+')}",
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": True,
                        "confidence": 0.6,
                    })
                if results:
                    return results
        except Exception:
            pass
        return [{
            "provider": self.name,
            "archivio": "LAC",
            "titolo": f"Ricerca: {query}",
            "catalog_url": f"{self.base_url}/eng/search/Pages/search.aspx?k={query.replace(' ', '+')}",
            "access_type": "online",
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderAustralianWarMemorial(SourceProvider):
    """Australian War Memorial."""
    name = "awm"
    display_name = "Australian War Memorial"
    country = "Australia"
    archive_name = "AWM"
    base_url = "https://www.awm.gov.au"
    authorized_domains = {"www.awm.gov.au", "collection.awm.gov.au"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://api.awm.gov.au/search/collection-items"
            params = {"q": query, "limit": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("items", data.get("data", [])):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item.get("id"),
                        "archivio": "AWM",
                        "titolo": item.get("title", ""),
                        "source_type": "military_document",
                        "catalog_url": item.get("url", ""),
                        "access_type": "online",
                        "confidence": 0.6,
                    })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderArchivportalD(SourceProvider):
    """Archivportal-D — Deutsche Digitale Bibliothek."""
    name = "archivportal_d"
    display_name = "Archivportal-D"
    country = "Germania"
    archive_name = "Archivportal-D"
    base_url = "https://www.archivportal-d.de"
    authorized_domains = {"www.archivportal-d.de", "api.deutsche-digitale-bibliothek.de"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://api.deutsche-digitale-bibliothek.de/search"
            params = {"query": query, "rows": 10, "offset": 0}
            resp = requests.get(url, params=params, timeout=20, verify=False,
                                headers={"Accept": "application/json",
                                         "User-Agent": "ricerca-storica-IMI/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("results", data.get("items", [])):
                    item_id = item.get("id", "")
                    title = item.get("title", "") or item.get("label", "")
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item_id,
                        "archivio": "Archivportal-D",
                        "titolo": title,
                        "description": (item.get("description") or "")[:200],
                        "source_type": "archival_document",
                        "catalog_url": f"{self.base_url}/content/{item_id}" if item_id else f"{self.base_url}/search?query={query.replace(' ', '+')}",
                        "direct_url": item.get("digitalObject", {}).get("url", "") if isinstance(item.get("digitalObject"), dict) else "",
                        "access_type": "online",
                        "downloadable": bool(item.get("digitalObject")),
                        "confidence": 0.6,
                    })
                if results:
                    return results
        except Exception:
            pass
        return [{
            "provider": self.name,
            "archivio": "Archivportal-D",
            "titolo": f"Ricerca: {query}",
            "catalog_url": f"{self.base_url}/search?query={query.replace(' ', '+')}",
            "access_type": "online",
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderInternetCulturale(SourceProvider):
    """Internet Culturale — Portale del libro antico (ICCU)."""
    name = "internetculturale"
    display_name = "Internet Culturale"
    country = "Italia"
    archive_name = "Internet Culturale"
    base_url = "https://www.internetculturale.it"
    authorized_domains = {"www.internetculturale.it", "opac.sbn.it"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "http://opac.sbn.it/opacmobilegw/search.json"
            params = {"any": query, "type": 0, "start": 0, "rows": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False,
                                headers={"User-Agent": "ricerca-storica-IMI/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("briefRecords", []) if isinstance(data, dict) else data
                results = []
                for r in records:
                    bid = r.get("codiceIdentificativo", "")
                    titolo = r.get("titolo", "")
                    autore = r.get("autorePrincipale", "")
                    pub = r.get("pubblicazione", "")
                    results.append({
                        "provider": self.name,
                        "provider_record_id": bid,
                        "archivio": "Internet Culturale — OPAC SBN",
                        "titolo": titolo,
                        "description": f"Autore: {autore}. Pubblicazione: {pub}",
                        "source_type": "bibliographic_record",
                        "catalog_url": f"https://opac.sbn.it/bid/{bid}" if bid else f"{self.base_url}/opac/search?q={query.replace(' ', '+')}",
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": 0.6,
                    })
                if results:
                    return results
        except Exception:
            pass
        return [{
            "provider": self.name,
            "archivio": "Internet Culturale",
            "titolo": f"Ricerca: {query}",
            "catalog_url": f"{self.base_url}/opac/search?q={query.replace(' ', '+')}",
            "access_type": "online",
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderHathiTrust(SourceProvider):
    """HathiTrust Digital Library."""
    name = "hathitrust"
    display_name = "HathiTrust"
    country = "USA"
    archive_name = "HathiTrust"
    base_url = "https://www.hathitrust.org"
    authorized_domains = {"www.hathitrust.org", "babel.hathitrust.org"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        try:
            url = "https://catalog.hathitrust.org/api/v1/brief/search"
            params = {"q": query, "rows": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("items", []):
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item.get("htid"),
                        "archivio": "HathiTrust",
                        "titolo": item.get("title", ""),
                        "source_type": "digitized_book",
                        "catalog_url": f"https://catalog.hathitrust.org/Record/{item.get('recordID', '')}",
                        "direct_url": f"https://babel.hathitrust.org/cgi/pt?id={item.get('htid', '')}",
                        "access_type": "online",
                        "confidence": 0.5,
                    })
                return results
        except Exception:
            pass
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


class ProviderUSSME(SourceProvider):
    """Ufficio Storico Stato Maggiore Esercito (Italia)."""
    name = "ussme"
    display_name = "USSME — Ufficio Storico SME"
    country = "Italia"
    archive_name = "USSME"
    base_url = "https://www.esercito.difesa.it/istituzioni/stato-maggiore/ufficio-storico"
    authorized_domains = {"www.esercito.difesa.it"}
    cache_ttl_days = 120

    def search(self, query: str, filters: dict = None) -> List[dict]:
        # Cerca nei fondi_archivistici locali
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        q = f"%{query}%"
        cur.execute("""
            SELECT * FROM fondi_archivistici
            WHERE LOWER(titolo) LIKE ? OR LOWER(raw_text) LIKE ?
               OR LOWER(luoghi) LIKE ?
            LIMIT 10
        """, (q, q, q))
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append({
                "provider": self.name,
                "provider_record_id": r.get("id"),
                "archivio": "USSME",
                "fondo": r.get("codice_fondo", ""),
                "titolo": r.get("titolo", ""),
                "description": r.get("descrizione", ""),
                "source_type": "military_archive",
                "date_start": r.get("periodo", ""),
                "place": r.get("luoghi", ""),
                "catalog_url": r.get("url", ""),
                "direct_url": r.get("url", ""),
                "access_type": "locale" if r.get("file_pdf") else "online",
                "downloadable": bool(r.get("file_pdf")),
                "confidence": 0.8,
            })
        return results

    def get_metadata(self, record_id: str) -> dict:
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        cur.execute("SELECT * FROM fondi_archivistici WHERE id=?", (record_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return {}
        return {"provider": self.name, "titolo": r.get("titolo", ""),
                "catalog_url": r.get("url", "")}


class ProviderArchivioDiStato(SourceProvider):
    """Archivi di Stato italiani (generico, oltre Antenati)."""
    name = "archivio_stato"
    display_name = "Archivi di Stato Italia"
    country = "Italia"
    archive_name = "Archivio di Stato"
    base_url = "https://www.archiviodistato.bologna.it"
    authorized_domains = set()
    cache_ttl_days = 120

    def search(self, query: str, filters: dict = None) -> List[dict]:
        # Cerca nelle menzioni locali
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        q = f"%{query}%"
        cur.execute("""
            SELECT m.*, f.titolo as fondo_titolo, f.codice_fondo
            FROM menzioni m
            LEFT JOIN fondi_archivistici f ON m.fondo_id = f.id
            WHERE LOWER(m.cognome) LIKE ? OR LOWER(m.nome) LIKE ?
               OR LOWER(m.luogo) LIKE ? OR LOWER(m.contesto) LIKE ?
            LIMIT 15
        """, (q, q, q, q))
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append({
                "provider": self.name,
                "provider_record_id": r.get("id"),
                "archivio": "Archivio di Stato",
                "fondo": r.get("codice_fondo", ""),
                "titolo": f"Menzione: {r.get('cognome', '')} {r.get('nome', '')}",
                "description": r.get("contesto", "")[:200],
                "source_type": "mention",
                "place": r.get("luogo", ""),
                "date_start": r.get("data", ""),
                "person": f"{r.get('cognome', '')} {r.get('nome', '')}",
                "access_type": "locale",
                "confidence": 0.7,
            })
        return results

    def get_metadata(self, record_id: str) -> dict:
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        cur.execute("SELECT * FROM menzioni WHERE id=?", (record_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return {}
        return {"provider": self.name, "access_type": "locale"}
