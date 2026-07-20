"""Provider stub per archivi non ancora integrati con dati locali.

Ogni stub implementa search() che cerca nel DB locale se ci sono tabelle,
altrimenti ritorna metadati con URL catalogo per ricerca manuale.
Estendibile: sostituire search() con chiamate API reali quando disponibili.
"""

import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from database import get_conn
from .base import SourceProvider, _dict_factory

logger = logging.getLogger("tna_provider")


class ProviderArolsen(SourceProvider):
    """Arolsen Archives — International Tracing Service (ITS).

    Usa l'endpoint reverse-engineered ITS-WS.asmx (ASP.NET JSON).
    Flusso: BuildQueryGlobalForAngular → GetCount → GetPersonList/GetArchiveList.
    Le sessioni sono cookie-keyed (ASP.NET_SessionId).
    """
    name = "arolsen"
    display_name = "Arolsen Archives — ITS"
    country = "Germania"
    archive_name = "Arolsen"
    base_url = "https://collections.arolsen-archives.org"
    api_url = "https://collections-server.arolsen-archives.org/ITS-WS.asmx"
    authorized_domains = {"collections.arolsen-archives.org", "collections-server.arolsen-archives.org"}
    cache_ttl_days = 90

    def _post_asmx(self, method: str, body: dict, session_cookie: str = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        if session_cookie:
            headers["Cookie"] = session_cookie
        resp = requests.post(
            f"{self.api_url}/{method}",
            json=body, headers=headers, timeout=30, verify=False,
        )
        resp.raise_for_status()
        return resp.json().get("d", {})

    def search(self, query: str, filters: dict = None) -> List[dict]:
        import uuid as _uuid
        unique_id = str(_uuid.uuid4())
        session_cookie = None

        try:
            # Step 1: BuildQueryGlobalForAngular (inizializza sessione di ricerca)
            build_resp = requests.post(
                f"{self.api_url}/BuildQueryGlobalForAngular",
                json={
                    "uniqueId": unique_id,
                    "lang": "en",
                    "archiveIds": [],
                    "strSearch": query,
                    "synSearch": True,
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/",
                },
                timeout=30, verify=False,
            )
            if build_resp.status_code != 200:
                raise Exception(f"BuildQuery failed: {build_resp.status_code}")
            # Capture session cookie
            cookies = build_resp.headers.get("set-cookie", "")
            if cookies:
                for raw in cookies.split(","):
                    part = raw.strip().split(";")[0]
                    if "ASP.NET_SessionId" in part:
                        session_cookie = part
                        break
            if not session_cookie and cookies:
                session_cookie = cookies.split(";")[0].strip()

            results = []

            # Step 2a: GetCount (person)
            try:
                count_resp = requests.post(
                    f"{self.api_url}/GetCount",
                    json={"uniqueId": unique_id, "lang": "en", "searchType": "person", "useFilter": False},
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Origin": self.base_url,
                        "Referer": f"{self.base_url}/",
                        **({"Cookie": session_cookie} if session_cookie else {}),
                    },
                    timeout=30, verify=False,
                )
                person_count = int(count_resp.json().get("d", 0)) if count_resp.status_code == 200 else 0
            except Exception:
                person_count = 0

            # Step 2b: GetPersonList
            if person_count > 0:
                try:
                    plist_resp = requests.post(
                        f"{self.api_url}/GetPersonList",
                        json={"uniqueId": unique_id, "lang": "en", "rowNum": 0, "orderBy": "LastName", "orderType": "asc"},
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "Origin": self.base_url,
                            "Referer": f"{self.base_url}/",
                            **({"Cookie": session_cookie} if session_cookie else {}),
                        },
                        timeout=30, verify=False,
                    )
                    if plist_resp.status_code == 200:
                        persons = plist_resp.json().get("d", [])
                        for p in persons[:10]:
                            last = p.get("LastName", "")
                            first = p.get("FirstName", "")
                            obj_id = p.get("ObjId", "")
                            desc_id = p.get("DescId", "")
                            sig = p.get("Signature", "")
                            results.append({
                                "provider": self.name,
                                "provider_record_id": str(obj_id or desc_id),
                                "archivio": "Arolsen Archives",
                                "titolo": f"{last}, {first}".strip(", "),
                                "description": f"Prisoner #: {p.get('PrisonerNumber', '')}; Born: {p.get('PlaceBirth', '')} {p.get('Dob', '')}".strip(),
                                "source_type": "tracing_document",
                                "catalog_url": f"{self.base_url}/en/search/{query.replace(' ', '%20')}",
                                "direct_url": f"{self.base_url}/en/document/{obj_id}" if obj_id else "",
                                "access_type": "login",
                                "downloadable": False,
                                "confidence": 0.8,
                            })
                except Exception:
                    pass

            # Step 2c: GetCount (archive) + GetArchiveList
            try:
                acount_resp = requests.post(
                    f"{self.api_url}/GetCount",
                    json={"uniqueId": unique_id, "lang": "en", "searchType": "archive", "useFilter": False},
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Origin": self.base_url,
                        "Referer": f"{self.base_url}/",
                        **({"Cookie": session_cookie} if session_cookie else {}),
                    },
                    timeout=30, verify=False,
                )
                archive_count = int(acount_resp.json().get("d", 0)) if acount_resp.status_code == 200 else 0
            except Exception:
                archive_count = 0

            if archive_count > 0 and len(results) < 10:
                try:
                    alist_resp = requests.post(
                        f"{self.api_url}/GetArchiveList",
                        json={"uniqueId": unique_id, "lang": "en", "orderBy": "RN", "orderType": "asc", "rowNum": 0},
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "Origin": self.base_url,
                            "Referer": f"{self.base_url}/",
                            **({"Cookie": session_cookie} if session_cookie else {}),
                        },
                        timeout=30, verify=False,
                    )
                    if alist_resp.status_code == 200:
                        archives = alist_resp.json().get("d", [])
                        for a in archives[:max(0, 10 - len(results))]:
                            title = a.get("Title", "")
                            desc_id = a.get("id", "")
                            refcode = a.get("RefCode", "")
                            sig = a.get("Signature", "")
                            results.append({
                                "provider": self.name,
                                "provider_record_id": str(desc_id),
                                "archivio": "Arolsen Archives",
                                "titolo": title or refcode or sig,
                                "description": f"RefCode: {refcode}; Signature: {sig}",
                                "source_type": "archival_unit",
                                "catalog_url": f"{self.base_url}/en/archive/{desc_id}" if desc_id else f"{self.base_url}/en/search/{query.replace(' ', '%20')}",
                                "direct_url": "",
                                "access_type": "login",
                                "downloadable": False,
                                "confidence": 0.7,
                            })
                except Exception:
                    pass

            if results:
                return results
        except Exception:
            pass

        return [{
            "provider": self.name,
            "provider_record_id": "",
            "archivio": "Arolsen Archives",
            "titolo": f"Ricerca: {query}",
            "description": "Arolsen Archives (ITS) — ricerca non disponibile via API. "
                           "Usa il portale web per ricerca manuale.",
            "source_type": "tracing_document",
            "catalog_url": f"{self.base_url}/en/search/{query.replace(' ', '%20')}",
            "direct_url": "",
            "access_type": "login",
            "downloadable": False,
            "confidence": 0.5,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "login"}


class ProviderBundesarchiv(SourceProvider):
    """Bundesarchiv — Archivio Federale Tedesco.

    Usa l'API Invenio (REST JSON) con endpoint /api/records.
    L'API è pubblica per la ricerca (lettura), richiede autenticazione
    solo per il download di digital objects.
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

    def search(self, query: str, filters: dict = None) -> List[dict]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (ricerca-storica-IMI/1.0)",
        }
        endpoints = [
            f"{self.invenio_url}/api/records",
            f"{self.invenio_url}/invenio/api/records",
        ]
        for url in endpoints:
            try:
                resp = requests.get(url, params={"q": query, "size": 10, "sort": "bestmatch"},
                                    timeout=15, verify=False, headers=headers)
                if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                    data = resp.json()
                    hits = data.get("hits", {}).get("hits", [])
                    if hits:
                        results = []
                        for hit in hits:
                            md = hit.get("metadata", {})
                            title = md.get("title", "") or md.get("description", "") or f"Record {hit.get('id', '')}"
                            desc = (md.get("description") or "")[:200]
            # Extract digital object info
                            files = hit.get("files", {})
                            digital_url = ""
                            downloadable = False
                            if isinstance(files, dict):
                                for f in files.get("entries", []):
                                    if f.get("key", "").endswith((".pdf", ".jpg", ".png", ".tiff")):
                                        digital_url = f.get("links", {}).get("download", "")
                                        downloadable = True
                                        break
                            results.append({
                                "provider": self.name,
                                "provider_record_id": str(hit.get("id", "")),
                                "archivio": "Bundesarchiv",
                                "titolo": title,
                                "description": desc,
                                "source_type": "military_document",
                                "catalog_url": f"{self.invenio_url}/invenio/record/{hit.get('id', '')}",
                                "direct_url": digital_url,
                                "access_type": "online" if downloadable else "login",
                                "downloadable": downloadable,
                                "confidence": 0.7,
                            })
                        return results
            except Exception:
                continue

        # Fallback: link di ricerca catalogo e open data
        q = query.replace(" ", "+")
        return [
            {
                "provider": self.name,
                "provider_record_id": "",
                "archivio": "Bundesarchiv",
                "titolo": f"Ricerca in Invenio: {query}",
                "description": "Catalogo online del Bundesarchiv (Invenio).",
                "source_type": "military_document",
                "catalog_url": f"{self.open_data_url}/",
                "direct_url": "",
                "access_type": "online",
                "downloadable": False,
                "confidence": 0.5,
            },
            {
                "provider": self.name,
                "provider_record_id": "",
                "archivio": "Bundesarchiv",
                "titolo": f"Open Data / DDB-Bestand: {query}",
                "description": "Dump XML pubblici del catalogo (GovData).",
                "source_type": "open_data",
                "catalog_url": f"{self.open_data_url}/",
                "direct_url": "",
                "access_type": "online",
                "downloadable": True,
                "confidence": 0.4,
            },
        ]

    def get_metadata(self, record_id: str) -> dict:
        try:
            url = f"{self.invenio_url}/api/records/{record_id}"
            resp = requests.get(url, timeout=15, verify=False,
                                headers={"Accept": "application/json"})
            if resp.status_code == 200:
                return {"provider": self.name, **resp.json().get("metadata", {})}
        except Exception:
            pass
        return {"provider": self.name, "access_type": "online"}


class ProviderSHD(SourceProvider):
    """Service Historique de la Défense (Francia) — Mémoire des Hommes.

    Il portale non espone API JSON pubblica. Usa endpoint HTML con
    parsing strutturato dei risultati di ricerca.
    Basi dati: Morts pour la France (WW1/WW2), Fusillés, Combattants.
    """
    name = "shd"
    display_name = "SHD — Service Historique de la Défense"
    country = "Francia"
    archive_name = "SHD"
    base_url = "https://www.servicehistorique.sga.defense.gouv.fr"
    mdh_url = "https://www.memoiredeshommes.sga.defense.gouv.fr"
    authorized_domains = {"www.servicehistorique.sga.defense.gouv.fr", "www.memoiredeshommes.sga.defense.gouv.fr"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        q = query.replace(" ", "+")
        results = []

        # Endpoint 1: Ricerca generale Mémoire des Hommes
        try:
            url = f"{self.mdh_url}/fr/search.php"
            params = {"q": query, "n": 10}
            resp = requests.get(url, params=params, timeout=20,
                                headers={"Accept": "text/html",
                                         "User-Agent": "ricerca-storica-IMI/1.0"})
            if resp.status_code == 200:
                import re
                # Estrai link ai risultati
                links = re.findall(r'href="(/fr/article\.php[^"]*?)"', resp.text)
                # Estrai nomi dai link (spesso contengono l'ID del record)
                seen = set()
                for link in links[:10]:
                    full_url = f"{self.mdh_url}{link}"
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    # Estrai eventuale nome dal testo circostante
                    title_match = re.search(r'<a[^>]*href="' + re.escape(link) + r'"[^>]*>(.*?)</a>', resp.text, re.S)
                    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else f"Risultato: {query}"
                    results.append({
                        "provider": self.name,
                        "provider_record_id": link,
                        "archivio": "SHD — Mémoire des Hommes",
                        "titolo": title,
                        "description": "Service Historique de la Défense — Mémoire des Hommes.",
                        "source_type": "military_record",
                        "catalog_url": full_url,
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": 0.6,
                    })
        except Exception:
            pass

        # Endpoint 2: Basi dati specifiche (WW1 morts)
        if not results:
            try:
                url2 = f"{self.mdh_url}/fr/article.php?source=&q={q}"
                resp2 = requests.get(url2, timeout=20,
                                     headers={"User-Agent": "ricerca-storica-IMI/1.0"})
                if resp2.status_code == 200:
                    results.append({
                        "provider": self.name,
                        "provider_record_id": "",
                        "archivio": "SHD — Mémoire des Hommes",
                        "titolo": f"Ricerca: {query}",
                        "description": "Basi dati Mémoire des Hommes: Morts pour la France (14-18, 39-45), Fusillés, Combattants.",
                        "source_type": "military_record",
                        "catalog_url": url2,
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": 0.5,
                    })
            except Exception:
                pass

        if results:
            return results

        return [{
            "provider": self.name,
            "provider_record_id": "",
            "archivio": "SHD",
            "titolo": f"Ricerca: {query}",
            "description": "Service Historique de la Défense — Mémoire des Hommes.",
            "source_type": "military_record",
            "catalog_url": f"{self.mdh_url}/fr/search.php?q={q}",
            "direct_url": "",
            "access_type": "online",
            "downloadable": False,
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "access_type": "online"}


# --------------------------------------------------------------------------- #
# WAF Session manager per TNA (AWS WAF Bot Control challenge)
# --------------------------------------------------------------------------- #
_TNA_BASE = "https://discovery.nationalarchives.gov.uk"
_TNA_API = f"{_TNA_BASE}/API"
_TNA_SEARCH_URL = f"{_TNA_API}/search/records"
_TNA_DETAILS_URL = f"{_TNA_API}/records/v1/details/{{record_id}}"
_TNA_WAF_WARMUP_URL = f"{_TNA_BASE}/results/r?_sd=&_ed=&_q=archive"

_TNA_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9,it;q=0.8",
    "Origin": _TNA_BASE,
    "Referer": f"{_TNA_BASE}/",
}


class _WafSession:
    """Requests.Session con cookie aws-waf-token ottenuto via Playwright.

    Il 202 con header x-amzn-waf-action:challenge e' un JS challenge
    di AWS WAF Bot Control. Playwright (headless Chromium) lo risolve
    automaticamente caricando una pagina del dominio; il cookie risultante
    viene trasferito nella Session per tutte le chiamate REST successive.
    """

    def __init__(self, headless: bool = True, waf_ttl: int = 25 * 60) -> None:
        self.session = requests.Session()
        self.session.headers.update(_TNA_DEFAULT_HEADERS)
        self._headless = headless
        self._waf_ttl = waf_ttl
        self._token_ts: float = 0.0
        self._lock = threading.Lock()

    def _token_is_fresh(self) -> bool:
        return (
            self.session.cookies.get("aws-waf-token") is not None
            and (time.time() - self._token_ts) < self._waf_ttl
        )

    def _refresh_token(self, force: bool = False) -> None:
        with self._lock:
            if not force and self._token_is_fresh():
                return
            logger.info("WAF: risoluzione challenge JS via Playwright...")
            self._solve_challenge_with_playwright()
            self._token_ts = time.time()
            token = self.session.cookies.get("aws-waf-token")
            if token:
                logger.info("WAF: token ottenuto (%d char).", len(token))
            else:
                logger.warning(
                    "WAF: nessun aws-waf-token dopo il challenge; "
                    "le chiamate potrebbero continuare a ricevere 202."
                )

    def _solve_challenge_with_playwright(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright non installato. Esegui:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium\n"
                "Necessario per superare l'AWS WAF challenge (HTTP 202)."
            ) from exc

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context = browser.new_context(
                    user_agent=_TNA_DEFAULT_HEADERS["User-Agent"],
                    locale="en-GB",
                    viewport={"width": 1366, "height": 768},
                )
                page = context.new_page()
                page.goto(_TNA_WAF_WARMUP_URL, wait_until="domcontentloaded", timeout=45_000)
                deadline = time.time() + 20
                while time.time() < deadline:
                    cookies = context.cookies(_TNA_BASE)
                    if any(c["name"] == "aws-waf-token" for c in cookies):
                        break
                    page.wait_for_timeout(500)
                for c in context.cookies(_TNA_BASE):
                    self.session.cookies.set(
                        c["name"], c["value"],
                        domain=c.get("domain"), path=c.get("path", "/"),
                    )
            finally:
                browser.close()

    def get(self, url: str, *, params: Optional[dict] = None,
            max_retries: int = 4) -> requests.Response:
        if not self._token_is_fresh():
            self._refresh_token()

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                last_exc = exc
                self._sleep_backoff(attempt)
                continue

            waf_challenged = (
                resp.status_code == 202
                or resp.headers.get("x-amzn-waf-action", "").lower() == "challenge"
            )
            if waf_challenged:
                logger.warning(
                    "WAF challenge su %s (tentativo %d/%d): rinnovo token.",
                    url, attempt + 1, max_retries,
                )
                self._refresh_token(force=True)
                self._sleep_backoff(attempt, base=1.0)
                continue

            if resp.status_code == 429:
                logger.warning("HTTP 429 su %s: backoff.", url)
                self._sleep_backoff(attempt)
                continue

            if 500 <= resp.status_code < 600:
                # HTTP 5xx su TNA è deterministico (query non supportata),
                # NON retriable — solleva subito senza backoff
                logger.warning("HTTP %d su %s: errore deterministic, no retry.", resp.status_code, url)
                resp.raise_for_status()

            resp.raise_for_status()
            return resp

        if last_exc:
            raise last_exc
        raise RuntimeError(
            f"Impossibile completare GET {url} dopo {max_retries} tentativi (WAF/limite)."
        )

    @staticmethod
    def _sleep_backoff(attempt: int, base: float = 1.5) -> None:
        delay = base * (2 ** attempt) + random.uniform(0, 1)
        time.sleep(min(delay, 30))


class ProviderNationalArchivesUK(SourceProvider):
    """The National Archives (UK) — Discovery API.

    Risolve due problemi dell'integrazione TNA:

    1. AWS WAF challenge (HTTP 202): il portale usa AWS WAF Bot Control che
       restituisce 202 con un JS challenge. Playwright headless risolve il
       challenge ottenendo il cookie aws-waf-token, poi riusato in requests.

    2. Query parameter: l'endpoint corretto e' /API/search/records (senza v1)
       e il parametro e' sps.searchQuery (non q). Con q il filtro viene
       ignorato e si ottiene sempre l'intero catalogo (42M record).

    Dipendenze: requests>=2.31; playwright (opzionale ma consigliato).
        pip install playwright && python -m playwright install chromium
    """
    name = "tna"
    display_name = "The National Archives (UK)"
    country = "UK"
    archive_name = "TNA"
    base_url = _TNA_BASE
    authorized_domains = {"discovery.nationalarchives.gov.uk", "www.nationalarchives.gov.uk"}
    cache_ttl_days = 90

    # Singleton WafSession condiviso tra istanze
    _waf: Optional[_WafSession] = None
    _waf_lock = threading.Lock()

    def __init__(self):
        cls = type(self)
        if cls._waf is None:
            with cls._waf_lock:
                if cls._waf is None:
                    cls._waf = _WafSession(headless=True)

    def search(self, query: str, filters: dict = None) -> List[dict]:
        filters = filters or {}
        params: Dict[str, any] = {
            "sps.searchQuery": query or "*",
            "sps.resultsPageSize": int(filters.get("page_size", 50)),
        }
        # NOTA: sps.dateFrom/sps.dateTo causano HTTP 500 — non usarli mai
        # (confermato con test diretto sull'API TNA, luglio 2026)
        if filters.get("record_series"):
            params["sps.recordSeries[0]"] = str(filters["record_series"])
        if filters.get("sort_by"):
            params["sps.sortByOption"] = str(filters["sort_by"])

        try:
            resp = type(self)._waf.get(_TNA_SEARCH_URL, params=params)
            data = resp.json()
        except Exception as e:
            logger.warning("TNA search failed: %s", e)
            return [{
                "provider": self.name,
                "archivio": "TNA",
                "titolo": f"Ricerca: {query}",
                "description": f"TNA Discovery — errore API: {e}",
                "source_type": "military_document",
                "catalog_url": f"{self.base_url}/results/r?q={query.replace(' ', '+')}",
                "access_type": "online",
                "confidence": 0.3,
            }]

        records = data.get("records", []) or []
        results = []
        for r in records:
            rid = r.get("id") or r.get("iaid") or ""
            held_by = r.get("heldBy")
            if isinstance(held_by, list):
                held_by = "; ".join(str(h) for h in held_by if h)
            results.append({
                "provider": self.name,
                "provider_record_id": rid,
                "archivio": "TNA",
                "titolo": (r.get("title") or "").strip(),
                "description": (r.get("description") or "")[:200],
                "source_type": "military_document",
                "date_start": r.get("coveringDates", ""),
                "catalog_url": f"{self.base_url}/details/r/{rid}" if rid else "",
                "direct_url": "",
                "access_type": "online",
                "downloadable": False,
                "confidence": 0.8,
            })
        return results[:10]

    def get_metadata(self, record_id: str) -> dict:
        rid = requests.utils.quote(str(record_id), safe="")
        url = _TNA_DETAILS_URL.format(record_id=rid)
        try:
            resp = type(self)._waf.get(url)
            return {"provider": self.name, **resp.json()}
        except Exception:
            return {"provider": self.name, "catalog_url": f"{self.base_url}/details/r/{record_id}"}

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        return f"{self.base_url}/details/r/{record_id}"


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
            resp = requests.get(url, params=params, timeout=20)
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

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        return f"https://www.europeana.eu/en/item/{record_id}"


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
    """Internet Archive — advanced search con filtri temporali WW2.

    Usa la advancedsearch.php con sintassi Solr:
    - date:[1940 TO 1946] per filtro temporale
    - mediatype:(texts) per documenti testuali
    - Termini inglesi + italiani combinati
    """
    name = "internetarchive"
    display_name = "Internet Archive"
    country = "USA"
    archive_name = "Internet Archive"
    base_url = "https://archive.org"
    authorized_domains = {"archive.org"}
    cache_ttl_days = 120

    # Italian military terms for broader search
    _IT_MILITARY = [
        "internati militari italiani",
        "prigionieri di guerra italiani",
        "Italian prisoner of war",
        "Italian military internee",
        "IMI Italy WW2",
        "prigionia guerra 1943",
        "campo prigionieri italia",
    ]

    def search(self, query: str, filters: dict = None) -> List[dict]:
        results = []
        seen_ids = set()

        # Strategy 1: Direct query with WW2 date filter
        queries = [
            f'({query}) AND date:[1940 TO 1946]',
            f'({query}) AND mediatype:(texts) AND date:[1940 TO 1946]',
        ]

        # Add Italian military terms if query looks like a name
        if len(query.split()) <= 3:
            queries.append(f'("{query}" AND (Italian OR Italy OR prisoner OR internato)) AND date:[1940 TO 1946]')

        for q in queries:
            if len(results) >= 10:
                break
            try:
                url = "https://archive.org/advancedsearch.php"
                params = {
                    "q": q,
                    "fl[]": ["identifier", "title", "description", "date", "mediatype", "collection", "language"],
                    "rows": 15,
                    "output": "json",
                    "sort": "downloads desc",
                }
                resp = requests.get(url, params=params, timeout=20, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    docs = data.get("response", {}).get("docs", [])
                    for doc in docs:
                        did = doc.get("identifier", "")
                        if did in seen_ids:
                            continue
                        seen_ids.add(did)
                        results.append({
                            "provider": self.name,
                            "provider_record_id": did,
                            "archivio": "Internet Archive",
                            "titolo": doc.get("title", ""),
                            "description": (doc.get("description") or "")[:200],
                            "source_type": "digitized_document",
                            "date_start": doc.get("date", ""),
                            "catalog_url": f"https://archive.org/details/{did}",
                            "direct_url": f"https://archive.org/details/{did}",
                            "access_type": "online",
                            "downloadable": True,
                            "confidence": 0.6,
                        })
            except Exception:
                continue

        # Strategy 2: Broad Italian military search if not enough results
        if len(results) < 5:
            for term in self._IT_MILITARY:
                if len(results) >= 10:
                    break
                try:
                    q2 = f'({term}) AND date:[1940 TO 1946] AND mediatype:(texts)'
                    resp2 = requests.get(
                        "https://archive.org/advancedsearch.php",
                        params={
                            "q": q2,
                            "fl[]": ["identifier", "title", "description", "date", "mediatype", "language"],
                            "rows": 5,
                            "output": "json",
                            "sort": "downloads desc",
                        },
                        timeout=20, verify=False,
                    )
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        docs2 = data2.get("response", {}).get("docs", [])
                        for doc in docs2:
                            did = doc.get("identifier", "")
                            if did in seen_ids:
                                continue
                            seen_ids.add(did)
                            results.append({
                                "provider": self.name,
                                "provider_record_id": did,
                                "archivio": "Internet Archive",
                                "titolo": doc.get("title", ""),
                                "description": (doc.get("description") or "")[:200],
                                "source_type": "digitized_document",
                                "date_start": doc.get("date", ""),
                                "catalog_url": f"https://archive.org/details/{did}",
                                "direct_url": f"https://archive.org/details/{did}",
                                "access_type": "online",
                                "downloadable": True,
                                "confidence": 0.5,
                            })
                except Exception:
                    continue

        return results[:10]

    def get_metadata(self, record_id: str) -> dict:
        try:
            url = f"https://archive.org/metadata/{record_id}"
            resp = requests.get(url, timeout=15, verify=False)
            if resp.status_code == 200:
                return {"provider": self.name, **resp.json()}
        except Exception:
            pass
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
    """Library and Archives Canada.

    Usa due endpoint:
    1. Canadiana API (search.canadiana.ca) — pubblica, JSON, collezioni digitali canadesi
    2. LAC Collection Search — portale ufficiale, export JSON/CSV disponibile
    """
    name = "lac"
    display_name = "Library and Archives Canada"
    country = "Canada"
    archive_name = "LAC"
    base_url = "https://www.bac-lac.gc.ca"
    canadiana_url = "http://search.canadiana.ca"
    authorized_domains = {"www.bac-lac.gc.ca", "recherche-collection-search.bac-lac.gc.ca", "search.canadiana.ca"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        results = []

        # Endpoint 1: Canadiana API (JSON pubblico)
        try:
            url = f"{self.canadiana_url}/search"
            params = {"q": query, "fmt": "json", "page": 1}
            resp = requests.get(url, params=params, timeout=20,
                                headers={"User-Agent": "ricerca-storica-IMI/1.0",
                                         "Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                for doc in data.get("docs", [])[:10]:
                    item_id = doc.get("id", "") or doc.get("key", "")
                    title = doc.get("title", "") or doc.get("label", "")
                    pub_year = doc.get("pubmin", "") or doc.get("year", "")
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item_id,
                        "archivio": "LAC — Canadiana",
                        "titolo": title,
                        "description": f"Canadiana digital collection. Published: {pub_year}",
                        "source_type": "digitized_document",
                        "date_start": str(pub_year) if pub_year else "",
                        "catalog_url": f"{self.canadiana_url}/view/{item_id}" if item_id else f"{self.canadiana_url}/search?q={query.replace(' ', '+')}",
                        "direct_url": f"{self.canadiana_url}/view/{item_id}" if item_id else "",
                        "access_type": "online",
                        "downloadable": True,
                        "confidence": 0.7,
                    })
        except Exception:
            pass

        if results:
            return results

        # Endpoint 2: LAC Collection Search (fallback)
        try:
            url = "https://recherche-collection-search.bac-lac.gc.ca/Search"
            params = {"q": query, "page": 1, "pageSize": 10, "format": "json"}
            resp = requests.get(url, params=params, timeout=20,
                headers={"User-Agent": "ricerca-storica-IMI/1.0",
                         "Accept": "application/json"})
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
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
        except Exception:
            pass

        if results:
            return results

        return [{
            "provider": self.name,
            "archivio": "LAC",
            "titolo": f"Ricerca: {query}",
            "description": "Library and Archives Canada — Collection Search.",
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
    """Archivportal-D — Deutsche Digitale Bibliothek (DDB).

    Usa l'API REST ufficiale DDB (OpenAPI 3.0).
    Richiede API key gratuita (registrata su deutsche-digitale-bibliothek.de).
    L'API key viene trasmessa nell'header Authorization come OAuth consumer key.
    Endpoint: GET /search con parametri query, rows, offset, sort.
    """
    name = "archivportal_d"
    display_name = "Archivportal-D"
    country = "Germania"
    archive_name = "Archivportal-D"
    base_url = "https://www.archivportal-d.de"
    api_url = "https://api.deutsche-digitale-bibliothek.de"
    authorized_domains = {"www.archivportal-d.de", "api.deutsche-digitale-bibliothek.de"}
    cache_ttl_days = 90

    def _get_api_key(self) -> str:
        import os
        key = os.environ.get("DDB_API_KEY", "")
        if key:
            return key
        try:
            from extractor import _load_env
            env = _load_env()
            return env.get("DDB_API_KEY", "")
        except Exception:
            return ""

    def search(self, query: str, filters: dict = None) -> List[dict]:
        api_key = self._get_api_key()
        headers = {
            "Accept": "application/json",
            "User-Agent": "ricerca-storica-IMI/1.0",
        }
        if api_key:
            headers["Authorization"] = f'OAuth oauth_consumer_key="{api_key}"'

        try:
            url = f"{self.api_url}/search"
            params = {
                "query": query,
                "rows": 10,
                "offset": 0,
                "sort": "RELEVANCE",
            }
            # Add time filter for WW2 if provided
            if filters and filters.get("time"):
                params["time_fct"] = filters["time"]

            resp = requests.get(url, params=params, timeout=20, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("results", []):
                    item_id = item.get("id", "") or item.get("identifier", "")
                    title = item.get("title", "") or item.get("label", "")
                    desc = (item.get("description") or item.get("subtitle") or "")[:200]
                    digital = item.get("binary", {})
                    digital_url = digital.get("url", "") if isinstance(digital, dict) else ""
                    results.append({
                        "provider": self.name,
                        "provider_record_id": item_id,
                        "archivio": "Archivportal-D",
                        "titolo": title,
                        "description": desc,
                        "source_type": "archival_document",
                        "catalog_url": f"{self.base_url}/content/{item_id}" if item_id else f"{self.base_url}/search?query={query.replace(' ', '+')}",
                        "direct_url": digital_url,
                        "access_type": "online",
                        "downloadable": bool(digital_url),
                        "confidence": 0.7 if api_key else 0.5,
                    })
                if results:
                    return results
        except Exception:
            pass

        return [{
            "provider": self.name,
            "archivio": "Archivportal-D",
            "titolo": f"Ricerca: {query}",
            "description": "Deutsche Digitale Bibliothek — API key richiesta per risultati completi. "
                           "Registrati su deutsche-digitale-bibliothek.de per ottenere la key.",
            "source_type": "archival_document",
            "catalog_url": f"{self.base_url}/search?query={query.replace(' ', '+')}",
            "access_type": "online",
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        api_key = self._get_api_key()
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f'OAuth oauth_consumer_key="{api_key}"'
        try:
            url = f"{self.api_url}/items/{record_id}"
            resp = requests.get(url, timeout=15, headers=headers)
            if resp.status_code == 200:
                return {"provider": self.name, **resp.json()}
        except Exception:
            pass
        return {"provider": self.name, "access_type": "online"}


class ProviderInternetCulturale(SourceProvider):
    """Internet Culturale — Portale del libro antico (ICCU).

    Usa OPAC SBN (opac.sbn.it) con endpoint JSON pubblico.
    Cerca in tutto il catalogo delle biblioteche italiane.
    """
    name = "internetculturale"
    display_name = "Internet Culturale"
    country = "Italia"
    archive_name = "Internet Culturale"
    base_url = "https://www.internetculturale.it"
    opac_url = "http://opac.sbn.it"
    authorized_domains = {"www.internetculturale.it", "opac.sbn.it"}
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        # Endpoint 1: OPAC SBN JSON
        try:
            url = f"{self.opac_url}/opacmobilegw/search.json"
            params = {"any": query, "type": 0, "start": 0, "rows": 10}
            resp = requests.get(url, params=params, timeout=20, verify=False,
                                headers={"User-Agent": "ricerca-storica-IMI/1.0",
                                         "Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("briefRecords", []) if isinstance(data, dict) else data
                results = []
                for r in records:
                    bid = r.get("codiceIdentificativo", "")
                    titolo = r.get("titolo", "")
                    autore = r.get("autorePrincipale", "")
                    pub = r.get("pubblicazione", "")
                    anno = r.get("anno", "")
                    results.append({
                        "provider": self.name,
                        "provider_record_id": bid,
                        "archivio": "Internet Culturale — OPAC SBN",
                        "titolo": titolo,
                        "description": f"Autore: {autore}. Pubblicazione: {pub}",
                        "source_type": "bibliographic_record",
                        "date_start": str(anno) if anno else "",
                        "catalog_url": f"https://opac.sbn.it/bid/{bid}" if bid else f"{self.base_url}/opac/search?q={query.replace(' ', '+')}",
                        "direct_url": "",
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": 0.7,
                    })
                if results:
                    return results
        except Exception:
            pass

        # Endpoint 2: Internet Culturale search (fallback)
        try:
            url2 = f"{self.base_url}/opac/search"
            params2 = {"q": query, "n": 10}
            resp2 = requests.get(url2, params=params2, timeout=20, verify=False,
                                 headers={"User-Agent": "ricerca-storica-IMI/1.0"})
            if resp2.status_code == 200:
                import re
                bids = re.findall(r'bid/([A-Z]{2}\d{8})', resp2.text)
                seen = set()
                results = []
                for bid in bids[:10]:
                    if bid in seen:
                        continue
                    seen.add(bid)
                    results.append({
                        "provider": self.name,
                        "provider_record_id": bid,
                        "archivio": "Internet Culturale",
                        "titolo": f"Record SBN: {bid}",
                        "description": "Bibliographic record dal catalogo OPAC SBN.",
                        "source_type": "bibliographic_record",
                        "catalog_url": f"https://opac.sbn.it/bid/{bid}",
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
            "archivio": "Internet Culturale",
            "titolo": f"Ricerca: {query}",
            "description": "OPAC SBN — catalogo biblioteche italiane.",
            "catalog_url": f"{self.base_url}/opac/search?q={query.replace(' ', '+')}",
            "access_type": "online",
            "confidence": 0.4,
        }]

    def get_metadata(self, record_id: str) -> dict:
        try:
            url = f"{self.opac_url}/opacmobilegw/bid/{record_id}.json"
            resp = requests.get(url, timeout=15, verify=False,
                                headers={"Accept": "application/json"})
            if resp.status_code == 200:
                return {"provider": self.name, **resp.json()}
        except Exception:
            pass
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


# --------------------------------------------------------------------------- #
# Teca Digitale ACS — Archivio Centrale dello Stato
# Fondo: MINISTERO DELLA DIFESA / ONORCADUTI / Internati militari italiani (IMI)
# 85 registri per provincia, Croce Rossa Italiana, 1945
# --------------------------------------------------------------------------- #

# UUID dei 79 registri IMI (provincia → uuid), scrappati dalla Teca Digitale ACS
# Fonte: https://tecadigitaleacs.cultura.gov.it/media/ricercadl
#         ?rictree=MINISTERO DELLA DIFESA/ONORCADUTI/Internati militari italiani (IMI)
_ACS_IMI_REGISTRI: Dict[str, str] = {
    "Agrigento":       "c7c33820-2ce6-4ab1-9209-79411636aa4e",
    "Alessandria":     "8394df69-486f-4ae1-ba84-d3cd8f09622b",
    "Ancona":          "50b82a1b-6d41-4129-b191-8f0ddc589446",
    "Ascoli Piceno":   "b7a5ba25-c5ee-44b2-94d3-6f6046b8a42b",
    "Asti":            "4deba0d9-8275-431e-a469-bea7283128b6",
    "Avellino":        "c5f426f7-e772-4038-bc9c-5c2b14c02743",
    "Bari":            "d32d31fd-a847-40e1-9470-6452b21dd280",
    "Benevento":       "21fe8d45-1795-4dee-88cc-6ff5db061d99",
    "Bergamo":         "9edd9847-ce16-4bdc-a2fd-f332f2c70c9c",
    "Bologna":         "204c0590-6eba-4480-9de8-13b089cd9a90",
    "Bolzano":         "47cc0ee8-08e6-4814-8853-17a8c7f7a3f3",
    "Brescia":         "7005461b-4541-4e9f-b9da-7f6c11de4eb3",
    "Brindisi":        "09c83507-da06-4bfd-ab87-a8e348f31073",
    "Cagliari":        "3fcef7c3-9264-4437-bd0e-a988d7c213f7",
    "Caltanissetta":   "246b7d3d-a42e-48c9-8b2d-a959349642e8",
    "Campobasso":      "25b1b3d3-7bf2-455d-a316-faee94aca6d3",
    "Catania":         "88d0e80a-40af-4def-b508-9bc4f8d7243e",
    "Catanzaro":       "70253903-aaac-4fdc-a7a9-bb026fb25bfe",
    "Chieti":          "6fc9007a-635d-46d4-9de7-b41ddec96bbb",
    "Como":            "d08cd289-a16a-46e2-ae2e-d301d5ccb135",
    "Cosenza":         "27773853-2c45-46c7-aec9-33fec56a2006",
    "Cremona":         "c925bd3d-3e3c-40f0-ab84-92d90cc8b341",
    "Cuneo":           "0728d004-39e2-40c1-a22d-343f0526f2be",
    "Enna":            "a5d0fbd4-5f4e-4f6f-a72b-4f3d489d55f4",
    "Ferrara":         "12ae137e-4b81-4716-9839-e3c8a903861f",
    "Firenze":         "7aebd8c3-b8d5-4083-85f8-866194fc7599",
    "Fiume":           "387550f5-bd5c-45f7-baa5-09255150bbf3",
    "Forlì":           "17c9e390-79d9-4210-a27f-6704a1072f86",
    "Frosinone":       "bc552103-8df9-47ca-af90-21e71bdd70e2",
    "Genova":          "89e540e4-8bc9-4bae-ad25-2245f05d1093",
    "Gorizia":         "749ee254-bf91-45ed-9adf-90d679247b62",
    "Grosseto":        "e75f3e87-b534-499b-a34b-462e73ec39bf",
    "Imperia":         "db0112f0-12f0-495c-aea0-2fa7e992f07a",
    "L'Aquila":        "01967a84-193d-4c19-b6e3-8999c80b3c8e",
    "La Spezia":       "a134c757-b277-4ef7-b293-9556538e1451",
    "Lecce":           "37105557-7ba0-4353-8ce4-3f795efe6858",
    "Littoria":        "397e94b1-a640-4398-a0c6-e38ffbc60262",
    "Livorno":         "3bcdc2ab-38cf-4b68-9567-c7063562758c",
    "Lucca":           "1e0c57db-4eb4-4799-ab18-75cd7b7b7500",
    "Macerata":        "6f50f91c-884f-486c-ae13-b6317db82a73",
    "Mantova":         "8d5142a6-af6a-43b4-9ddd-85b4c8d23908",
    "Matera":          "589f91fa-a759-43e2-94ef-f1665bed81fd",
    "Messina":         "6b69b21d-91d0-403e-b993-91712ea40af8",
    "Milano":          "026e2bc2-8a23-4bd8-8e43-8d64af8bde93",
    "Napoli":          "19ae5902-fdad-4a71-962d-2f02ebee4860",
    "Novara":          "61d62ff8-365e-4e47-b0f8-44f603be8f14",
    "Nuoro":           "b9c0e5a6-1cdf-4fe1-b2df-44051a54c641",
    "Padova":          "9602ed4f-7fc5-4764-a4d7-5c94bc3b656f",
    "Palermo":         "c7c4efbe-998f-4f00-b563-0bbcf9db97af",
    "Parma":           "f8c38ece-ced5-424b-bf2f-8a8f643cbb77",
    "Pavia":           "8465ea62-df2c-485b-ba8d-09c929decc68",
    "Perugia":         "898a4a20-ee0f-4aeb-8b09-17991380ed5c",
    "Pesaro":          "b4e6a077-2c8d-41df-8aba-a465a505a370",
    "Pescara":         "ad0a650c-c72f-41ca-99a5-66acfa7ee5b6",
    "Piacenza":        "88d8c6c3-f60e-4423-95ec-2aac9f49109f",
    "Pisa":            "d60076e8-6d8a-4bca-8e5b-17b16292f053",
    "Pistoia":         "dcbacee7-3f8c-4f8f-a35e-67372727cdbb",
    "Pola":            "0a833bff-d0f5-4566-af81-08b82c991bc0",
    "Potenza":         "85a289e9-5081-4348-aac4-3de3a1177658",
    "Ragusa":          "4cb8e4aa-ff33-4a42-8176-1551a97aeae9",
    "Ravenna":         "6915baa3-f444-4d10-9d49-1fc28cae7401",
    "Reggio Calabria": "4b265c10-7597-41ce-b56f-6bfc712c0513",
    "Reggio Emilia":   "985d6817-577b-459a-abcd-2553c8e62bc6",
    "Rieti":           "cbc5807d-04bc-4ce4-ba4b-b24de2af5ec8",
    "Roma":            "33c2b460-3df6-4b8f-8a83-5c937443629e",
    "Rovigo":          "5015ba96-4785-410e-a15c-4ec59576382c",
    "Teramo":          "d7e849bb-f7f2-4d2e-8dcb-a9073aba8941",
    "Torino":          "20be0c92-31c3-4dcc-9340-60bca78b6e1e",
    "Trapani":         "908950b0-243e-4314-a50c-98e227e7dcd2",
    "Trento":          "7bece73f-bf26-417d-9ac9-2e83fc0aa229",
    "Treviso":         "0c109246-0fbf-4cbe-b2ec-23f208f098b1",
    "Udine":           "1e121768-7bff-4db2-8b95-479d5099795b",
    "Varese":          "80a3a161-5603-4def-869e-e87f499f6232",
    "Venezia":         "69ef79ef-65d4-460a-8777-c815e777f9cd",
    "Vercelli":        "d703ea78-aff7-4f2d-b2ca-dff7a3f6587e",
    "Verona":          "69381620-b222-4fe3-8c90-17cbbfff6962",
    "Vicenza":         "1982cc98-6c1b-4bd6-a8cd-092fb8184665",
    "Viterbo":         "44c348f7-8619-40e3-acde-d946f1179022",
    "Zara":            "23207800-9fbd-4a64-8d91-a5af6d9052b0",
}

_ACS_BASE = "https://tecadigitaleacs.cultura.gov.it"
_ACS_SEARCH_URL = (
    f"{_ACS_BASE}/media/ricercadl"
    "?rictree=MINISTERO%20DELLA%20DIFESA%2FCOMMISSARIATO%20GENERALE%20PER%20LE%20ONORANZE%20AI%20CADUTI%20(ONORCADUTI)%2FInternati%20militari%20italiani%20(IMI)"
    "&rictip=registro"
)


class ProviderTecaDigitaleACS(SourceProvider):
    """Teca Digitale ACS — registri IMI ONORCADUTI per provincia.

    Fonte primaria: Archivio Centrale dello Stato, fondo MINISTERO DELLA
    DIFESA / COMMISSARIATO GENERALE PER LE ONORANZE AI CADUTI (ONORCADUTI) /
    Internati militari italiani (IMI). 85 registri digitalizzati (CRI, 1945).

    Strategia search():
    - Cerca per provincia corrispondente al luogo di nascita/residenza del soldato
    - Ritorna sempre il registro della provincia corrispondente se trovato
    - Aggiunge link diretto all'item ACS (visualizzatore digitale)
    - Per cognomi senza match di provincia: ritorna link alla lista completa IMI
    """
    name = "teca_acs"
    display_name = "Teca Digitale ACS — Registri IMI ONORCADUTI"
    country = "Italia"
    archive_name = "Archivio Centrale dello Stato"
    base_url = _ACS_BASE
    authorized_domains = {"tecadigitaleacs.cultura.gov.it"}
    cache_ttl_days = 365

    def search(self, query: str, filters: dict = None) -> List[dict]:
        """
        Cerca il registro IMI per provincia.
        query: cognome (eventualmente con nome) del soldato
        filters: può contenere 'provincia' o 'luogo_nascita' per match diretto
        """
        filters = filters or {}
        provincia = (
            filters.get("provincia") or
            filters.get("luogo_nascita") or
            filters.get("luogo_residenza") or
            ""
        ).strip().title()

        results = []

        # Match diretto per provincia
        for prov, uuid in _ACS_IMI_REGISTRI.items():
            if provincia and prov.lower() in provincia.lower():
                results.append(self._make_result(prov, uuid, query))
                break

        # Se nessun match di provincia, ritorna il link alla lista completa
        if not results:
            results.append({
                "provider": self.name,
                "archivio": "Archivio Centrale dello Stato — ONORCADUTI",
                "titolo": f"Registri IMI ONORCADUTI — cerca per: {query}",
                "description": (
                    "85 registri digitalizzati degli Internati Militari Italiani "
                    "(CRI, 1945), organizzati per provincia. Ministero della Difesa / "
                    "COMMISSARIATO GENERALE PER LE ONORANZE AI CADUTI."
                ),
                "source_type": "registro",
                "catalog_url": _ACS_SEARCH_URL,
                "direct_url": _ACS_SEARCH_URL,
                "access_type": "online",
                "downloadable": False,
                "confidence": 0.6,
                "date_start": "1945",
            })

        return results

    def get_all_registri(self) -> List[dict]:
        """Ritorna tutti gli 85 registri IMI come lista di fonti."""
        return [self._make_result(prov, uuid, "") for prov, uuid in _ACS_IMI_REGISTRI.items()]

    def _make_result(self, provincia: str, uuid: str, query: str) -> dict:
        item_url = f"{_ACS_BASE}/item/{uuid}"
        return {
            "provider": self.name,
            "provider_record_id": uuid,
            "archivio": "Archivio Centrale dello Stato — ONORCADUTI",
            "fondo": "MINISTERO DELLA DIFESA / ONORCADUTI / IMI",
            "titolo": f"Registro IMI — {provincia} (CRI, 1945)",
            "description": (
                f"Elenco dei reduci IMI dalla Germania, anno 1945. "
                f"Provincia di {provincia}. "
                "Croce Rossa Italiana, Ufficio centrale prigionieri di guerra, "
                "Sezione distaccata Alta Italia, Milano."
            ),
            "source_type": "registro",
            "catalog_url": item_url,
            "direct_url": item_url,
            "access_type": "online",
            "downloadable": False,
            "confidence": 0.9,
            "date_start": "1945",
        }

    def get_metadata(self, record_id: str) -> dict:
        for prov, uuid in _ACS_IMI_REGISTRI.items():
            if uuid == record_id:
                return self._make_result(prov, uuid, "")
        return {"provider": self.name, "catalog_url": f"{_ACS_BASE}/item/{record_id}"}
