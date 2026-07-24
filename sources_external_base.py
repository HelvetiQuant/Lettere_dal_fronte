"""Base adapter per fonti archivistiche esterne federate.

Ogni adapter specifico implementa l'interfaccia SourceAdapter e contiene
solo la logica necessaria per interpretare la singola fonte.
Il motore generale non dipende dalla struttura HTML di alcuna fonte.
"""
import abc
import hashlib
import json
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse, urlunparse, urlencode, parse_qs

import httpx


# ─── Rate limiter semplice ──────────────────────────────────────────────
class RateLimiter:
    """Rate limiter semplice: aspetta min_delay secondi tra richieste."""
    def __init__(self, min_delay: float = 1.5):
        self.min_delay = min_delay
        self._last_request = 0.0

    def wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.time()


# ─── Normalizzazione URL ────────────────────────────────────────────────
def normalize_url(url: str) -> str:
    """Normalizza un URL: rimuove fragment, trailing slash, parametri di sessione."""
    if not url:
        return url
    parsed = urlparse(url.strip())
    # Rimuovi fragment
    parsed = parsed._replace(fragment="")
    # Rimuovi trailing slash dal path (eccetto root)
    path = parsed.path
    if path and path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    # Rimuovi parametri di sessione/tracking
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in qs.items()
                   if not k.lower() in ("session", "sid", "utm_source", "utm_medium", "utm_campaign", "ref")}
        query = urlencode(cleaned, doseq=True) if cleaned else ""
    else:
        query = ""
    parsed = parsed._replace(path=path, query=query)
    return urlunparse(parsed)


def is_canonical_record_url(url: str) -> bool:
    """Verifica che un URL sia una scheda specifica, non una homepage o ricerca."""
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    # Pattern accettati: /fonds/123, /fonds/123/units/456, /fonds/123/series/456
    if re.search(r'/(fonds|series|subseries|units|items|complessi)/\d+', path):
        return True
    # Pattern generici con identificativo numerico
    if re.search(r'/\d{3,}', path):
        return True
    # Pattern rifiutati
    bad_patterns = ["/search", "/ricerca", "?q=", "/login", "/auth", "/api/", "/homepage"]
    for bp in bad_patterns:
        if bp in url.lower():
            return False
    return True


# ─── Hash metadati ──────────────────────────────────────────────────────
def compute_metadata_hash(data: Dict[str, Any]) -> str:
    """Calcola SHA-256 dei metadati per confronto incrementale."""
    # Solo campi rilevanti per il confronto
    relevant_keys = [
        "title", "description", "date_text", "date_from", "date_to",
        "reference_code", "box_number", "file_number", "register_number",
        "protocol_number", "extent", "language",
        "people_metadata_json", "places_metadata_json",
        "military_units_metadata_json", "camps_metadata_json",
        "subjects_metadata_json",
    ]
    subset = {k: data.get(k) for k in relevant_keys if data.get(k) is not None}
    raw = json.dumps(subset, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ─── Classe base adapter ────────────────────────────────────────────────
class SourceAdapter(abc.ABC):
    """Interfaccia base per adapter di fonti archivistiche esterne."""

    # Identificativi
    provider_id: str = ""
    display_name: str = ""
    archive_name: str = ""
    archive_branch: str = ""
    base_url: str = ""

    # Configurazione
    user_agent: str = "IMI-Extractor/1.0 (research; contact: admin@example.org)"
    rate_limiter: RateLimiter = RateLimiter(min_delay=1.5)

    # Livelli archivistici supportati
    RECORD_LEVELS = ("archive", "fonds", "subfonds", "series", "subseries", "archival_unit", "item", "digital_object")

    @abc.abstractmethod
    def discover_resources(self, start_url: str, max_records: int = 0) -> List[Dict[str, Any]]:
        """Scopre le risorse disponibili a partire da un URL.
        
        Ritorna lista di dict con almeno: external_id, canonical_record_url, record_level.
        """
        ...

    @abc.abstractmethod
    def parse_record(self, url: str) -> Optional[Dict[str, Any]]:
        """Recupera e analizza una singola scheda.
        
        Ritorna dict con tutti i metadati estratti o None se non accessibile.
        """
        ...

    @abc.abstractmethod
    def extract_person_mentions(self, record_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Estrae nominativi esplicitamente presenti nei metadati.
        
        Non inventa nominativi non presenti.
        """
        ...

    @abc.abstractmethod
    def extract_facts(self, record_data: Dict[str, Any], mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Estrae fatti descritti nei metadati.
        
        Non converte descrizioni generali in fatti personali.
        """
        ...

    @abc.abstractmethod
    def detect_digital_objects(self, record_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rileva oggetti digitali senza presumere che siano scaricabili."""
        ...

    def normalize_external_id(self, url: str) -> str:
        """Estrae un identificativo stabile dall'URL."""
        parsed = urlparse(url)
        # Pattern: /fonds/10076/units/246473 → "fonds:10076:units:246473"
        parts = [p for p in parsed.path.split("/") if p]
        return ":".join(parts) if parts else url

    def get_canonical_url(self, url: str) -> str:
        """Normalizza e valida l'URL canonico."""
        normalized = normalize_url(url)
        if not is_canonical_record_url(normalized):
            # Non è una scheda specifica, ma proviamo comunque
            pass
        return normalized

    def fetch_page(self, url: str, timeout: float = 30.0) -> Tuple[Optional[str], int]:
        """Scarica una pagina con rate limiting e User-Agent identificabile.
        
        Ritorna (html, http_status) o (None, status_code).
        """
        self.rate_limiter.wait()
        try:
            with httpx.Client(
                headers={"User-Agent": self.user_agent},
                timeout=timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
                return resp.text, resp.status_code
        except httpx.TimeoutException:
            return None, 408
        except httpx.ConnectError:
            return None, 0
        except Exception as e:
            return None, -1

    def verify_url(self, url: str) -> Dict[str, Any]:
        """Verifica raggiungibilità di un URL.
        
        Ritorna dict con: reachable, http_status, final_url, verified_at.
        """
        self.rate_limiter.wait()
        try:
            with httpx.Client(
                headers={"User-Agent": self.user_agent},
                timeout=15.0,
                follow_redirects=True,
            ) as client:
                resp = client.head(url)
                return {
                    "reachable": resp.status_code < 400,
                    "http_status": resp.status_code,
                    "final_url": str(resp.url),
                    "verified_at": datetime.now().isoformat(),
                }
        except Exception:
            return {
                "reachable": False,
                "http_status": 0,
                "final_url": url,
                "verified_at": datetime.now().isoformat(),
            }

    def get_parent_url(self, url: str) -> Optional[str]:
        """Ricava l'URL del record genitore dalla gerarchia."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        # /fonds/10076/units/246473 → /fonds/10076
        if len(parts) >= 4 and parts[0] == "fonds" and parts[2] == "units":
            parent_path = "/" + "/".join(parts[:2])
            return urlunparse(parsed._replace(path=parent_path, query=""))
        # /fonds/10076/series/200 → /fonds/10076
        if len(parts) >= 4 and parts[0] == "fonds" and parts[2] == "series":
            parent_path = "/" + "/".join(parts[:2])
            return urlunparse(parsed._replace(path=parent_path, query=""))
        return None

    def get_record_level_from_url(self, url: str) -> str:
        """Determina il livello archivistico dall'URL."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return "archive"
        if parts[0] == "fonds" and len(parts) == 2:
            return "fonds"
        if "series" in parts:
            if "subseries" in parts:
                return "subseries"
            return "series"
        if "units" in parts:
            return "archival_unit"
        if "items" in parts:
            return "item"
        return "archival_unit"
