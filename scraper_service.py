"""Scraper service per IMI Extractor.

Recupera metadati e link da fonti esterne (Ufficio Storico SME, ANPI, CWGC, ecc.)
e li cataloga nella tabella `fonti_risorse`.

IMPORTANTE: Questo modulo NON memorizza contenuti protetti da copyright.
Salva solo:
  - URL della pagina
  - URL del documento/immagine
  - Metadati (titolo, autore, ente, data, lingua, licenza, note copyright)

Nessun testo integrale, PDF completo o immagine full-res viene salvato nel DB.
"""
import re
import time
import hashlib
import threading
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, urlunparse
from typing import Optional
from html.parser import HTMLParser

import requests

from config import (
    SCRAPER_USER_AGENT,
    SCRAPER_MAX_REQUESTS_PER_MINUTE,
    SCRAPER_TIMEOUT_SECONDS,
    SCRAPER_TTL_DAYS,
    SCRAPER_MAX_HTML_BYTES,
    SCRAPER_ALLOWED_DOMAINS,
)
from database import (
    get_fonti_risorsa_by_url,
    insert_fonti_risorsa,
    update_fonti_risorsa,
    get_fonti_risorse_by_fonte_id,
)


# ─── Rate limiting per-dominio ────────────────────────────────────────────────
_domain_timestamps: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _check_rate_limit(domain: str) -> bool:
    """Verifica che il dominio non abbia superato il rate limit. Ritorna True se ok."""
    with _rate_lock:
        now = time.time()
        window = 60.0  # 1 minuto
        if domain not in _domain_timestamps:
            _domain_timestamps[domain] = []
        # Rimuovi timestamp vecchi
        _domain_timestamps[domain] = [t for t in _domain_timestamps[domain] if now - t < window]
        if len(_domain_timestamps[domain]) >= SCRAPER_MAX_REQUESTS_PER_MINUTE:
            return False
        _domain_timestamps[domain].append(now)
        return True


def _is_domain_allowed(url: str) -> bool:
    """Verifica se il dominio dell'URL è nella lista degli autorizzati."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    for allowed in SCRAPER_ALLOWED_DOMAINS:
        if domain == allowed or domain.endswith("." + allowed):
            return True
    return False


# ─── robots.txt check (semplificato) ──────────────────────────────────────────
_robots_cache: dict[str, dict] = {}


def _check_robots_txt(url: str) -> bool:
    """Check semplificato di robots.txt. Ritorna True se lo scraping è permesso."""
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{domain}/robots.txt"

    if domain in _robots_cache:
        rules = _robots_cache[domain]
    else:
        try:
            resp = requests.get(
                robots_url,
                headers={"User-Agent": SCRAPER_USER_AGENT},
                timeout=SCRAPER_TIMEOUT_SECONDS,
            )
            if resp.status_code == 200:
                rules = _parse_robots_txt(resp.text)
            else:
                rules = {"disallowed": set()}  # No robots.txt = tutto permesso
        except Exception:
            rules = {"disallowed": set()}  # Errore = tutto permesso (fail-open)
        _robots_cache[domain] = rules

    path = parsed.path or "/"
    for disallowed_path in rules["disallowed"]:
        if path.startswith(disallowed_path):
            return False
    return True


def _parse_robots_txt(text: str) -> dict:
    """Parser semplificato per robots.txt. Estrae solo Disallow per User-Agent: *."""
    disallowed = set()
    current_section = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            ua = line.split(":", 1)[1].strip()
            current_section = (ua == "*")
        elif current_section and line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                disallowed.add(path)
    return {"disallowed": disallowed}


# ─── 1. fetch_html ────────────────────────────────────────────────────────────

def fetch_html(url: str) -> str:
    """Scarica l'HTML di una pagina esterna.

    Rispetta:
      - robots.txt
      - rate limiting per dominio
      - timeout
      - limiti di dimensione

    Args:
        url: URL della pagina da scaricare

    Returns:
        HTML della pagina come stringa

    Raises:
        ValueError: se il dominio non è autorizzato o robots.txt blocca
        requests.RequestException: per errori HTTP
    """
    if not _is_domain_allowed(url):
        raise ValueError(f"Dominio non autorizzato per scraping: {urlparse(url).netloc}")

    if not _check_robots_txt(url):
        raise ValueError(f"robots.txt disallow per URL: {url}")

    domain = urlparse(url).netloc
    if not _check_rate_limit(domain):
        raise ValueError(f"Rate limit superato per dominio: {domain}")

    resp = requests.get(
        url,
        headers={"User-Agent": SCRAPER_USER_AGENT},
        timeout=SCRAPER_TIMEOUT_SECONDS,
        stream=True,
    )
    resp.raise_for_status()

    # Leggi con limite di dimensione
    content = b""
    for chunk in resp.iter_content(chunk_size=8192):
        content += chunk
        if len(content) > SCRAPER_MAX_HTML_BYTES:
            break

    # Rileva encoding dal header o dal content
    encoding = resp.encoding or "utf-8"
    return content.decode(encoding, errors="replace")


# ─── 2. estrai_risorse ────────────────────────────────────────────────────────

class _LinkExtractor(HTMLParser):
    """Parser HTML per estrarre link a PDF, immagini e risorse rilevanti."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.resources = []
        self._in_title = False
        self._title_text = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a" and "href" in attrs_dict:
            href = attrs_dict["href"]
            full_url = urljoin(self.base_url, href)
            lower_url = full_url.lower()
            if lower_url.endswith(".pdf"):
                self.resources.append({
                    "url_pagina": full_url,
                    "url_documento": full_url,
                    "tipo": "pdf",
                    "html": None,
                })
            elif any(lower_url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".tiff", ".webp"]):
                self.resources.append({
                    "url_pagina": full_url,
                    "url_documento": full_url,
                    "tipo": "immagine",
                    "html": None,
                })
        elif tag == "img" and "src" in attrs_dict:
            src = attrs_dict["src"]
            full_url = urljoin(self.base_url, src)
            self.resources.append({
                "url_pagina": full_url,
                "url_documento": full_url,
                "tipo": "immagine",
                "html": None,
            })
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._in_title:
            self._title_text += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def estrai_risorse(html: str, base_url: str) -> list:
    """Estrae link rilevanti (PDF, immagini, pagine) dall'HTML.

    Args:
        html: HTML della pagina
        base_url: URL base per risolvere link relativi

    Returns:
        Lista di dict con: url_pagina, url_documento, tipo, html
    """
    resources = []

    # La pagina stessa è una risorsa di tipo 'pagina'
    resources.append({
        "url_pagina": base_url,
        "url_documento": None,
        "tipo": "pagina",
        "html": html,
    })

    # Estrai link a PDF e immagini
    parser = _LinkExtractor(base_url)
    try:
        parser.feed(html)
    except Exception:
        pass
    resources.extend(parser.resources)

    # Deduplica per url_pagina
    seen = set()
    unique = []
    for r in resources:
        if r["url_pagina"] not in seen:
            seen.add(r["url_pagina"])
            unique.append(r)

    return unique


# ─── 3. estrai_metadati ───────────────────────────────────────────────────────

class _MetaExtractor(HTMLParser):
    """Parser HTML per estrarre metadati da tag <meta>, <title>, <html lang>."""

    def __init__(self):
        super().__init__()
        self.metas = {}
        self.title = ""
        self.lang = None
        self.h1 = None
        self._in_title = False
        self._in_h1 = False
        self._h1_text = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "")
            if name and content:
                self.metas[name] = content
            if prop and content:
                self.metas[prop] = content
        elif tag == "html":
            self.lang = attrs_dict.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_h1:
            self._h1_text += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
            if self._h1_text.strip():
                self.h1 = self._h1_text.strip()


# Mapping domini -> ente titolare noto
_DOMAIN_TO_ENTE = {
    "cadutigrandeguerra.it": "Albo d'Oro dei Caduti della Grande Guerra",
    "onorcaduti.difesa.it": "Ministero della Difesa - Onorcaduti",
    "www.cwgc.org": "Commonwealth War Graves Commission",
    "memoiredeshommes.sga.defense.gouv.fr": "Mémoire des Hommes (France)",
    "archiviodistatobolzano.cultura.gov.it": "Archivio di Stato di Bolzano",
    "www.istoreco.it": "ISTORECO - Istituto per la Storia della Resistenza",
    "www.nastroazzurro.org": "Nastro Azzurro",
    "www.anpi.it": "ANPI - Associazione Nazionale Partigiani d'Italia",
    "www.ussme.gov.it": "Ufficio Storico Stato Maggiore Esercito",
    "www.bundesarchiv.de": "Bundesarchiv (Archivio Federale Tedesco)",
    "discovery.nationalarchives.gov.uk": "The National Archives (UK)",
    "catalog.archives.gov": "U.S. National Archives and Records Administration",
}


def estrai_metadati(url_pagina: str, html_fragment: Optional[str] = None,
                    html_full: Optional[str] = None) -> dict:
    """Estrae metadati (titolo, autore, ente, data, lingua, licenza) dall'HTML.

    Args:
        url_pagina: URL della pagina
        html_fragment: frammento HTML specifico (opzionale)
        html_full: HTML completo della pagina (usato se html_fragment è None)

    Returns:
        Dict con chiavi compatibili con fonti_risorse
    """
    html_source = html_fragment or html_full or ""
    parser = _MetaExtractor()
    try:
        parser.feed(html_source)
    except Exception:
        pass

    # Titolo: priority <title> > og:title > h1
    titolo = parser.title.strip() if parser.title else None
    if not titolo:
        titolo = parser.metas.get("og:title")
    if not titolo and parser.h1:
        titolo = parser.h1

    # Autore
    autore = parser.metas.get("author") or parser.metas.get("article:author")

    # Ente titolare: dal dominio o da meta
    parsed = urlparse(url_pagina)
    domain = parsed.netloc.lower()
    ente_titolare = _DOMAIN_TO_ENTE.get(domain)
    if not ente_titolare:
        for d, e in _DOMAIN_TO_ENTE.items():
            if domain.endswith(d):
                ente_titolare = e
                break
    if not ente_titolare:
        ente_titolare = domain

    # Data pubblicazione
    data_pub = (
        parser.metas.get("article:published_time")
        or parser.metas.get("date")
        or parser.metas.get("dc.date")
        or parser.metas.get("dc.date.issued")
    )

    # Lingua
    lingua = parser.lang or parser.metas.get("language") or parser.metas.get("og:locale")

    # Licenza
    licenza = (
        parser.metas.get("license")
        or parser.metas.get("dc.rights")
        or parser.metas.get("copyright")
    )
    if not licenza:
        licenza = "tutti i diritti riservati"

    # Descrizione
    descrizione = (
        parser.metas.get("description")
        or parser.metas.get("og:description")
        or parser.metas.get("dc.description")
    )

    # Note copyright
    note_copyright = None
    if html_source:
        # Cerca testo nel footer che menziona copyright
        match = re.search(r'(?:©|copyright|diritti riservati)[^<]{0,200}', html_source, re.IGNORECASE)
        if match:
            note_copyright = match.group(0).strip()

    return {
        "titolo": titolo,
        "autore": autore,
        "ente_titolare": ente_titolare,
        "data_pubblicazione": data_pub,
        "lingua": lingua,
        "licenza": licenza,
        "descrizione": descrizione,
        "note_copyright": note_copyright,
    }


# ─── 4. scrape_fonte ──────────────────────────────────────────────────────────

def scrape_fonte(fonte_record: dict) -> dict:
    """Scraping di una fonte esterna: recupera HTML, estrae risorse e metadati,
    inserisce/aggiorna in fonti_risorse.

    Args:
        fonte_record: dict con almeno 'id' e 'url_base' (o 'url' o 'url_catalogo')
                      Proviene da fonti_indice, fondi_archivistici, ecc.

    Returns:
        Dict con summary: { 'scraped': int, 'inserted': int, 'updated': int, 'errors': int }
    """
    # Determina l'URL base
    url_base = (
        fonte_record.get("url_base")
        or fonte_record.get("url")
        or fonte_record.get("url_catalogo")
        or fonte_record.get("scheda_url")
        or fonte_record.get("detail_url")
    )
    if not url_base:
        return {"scraped": 0, "inserted": 0, "updated": 0, "errors": 1,
                "error": "Nessun URL trovato nel fonte_record"}

    fonte_id = fonte_record.get("id")

    summary = {"scraped": 0, "inserted": 0, "updated": 0, "errors": 0}

    try:
        html = fetch_html(url_base)
    except Exception as e:
        summary["errors"] += 1
        summary["error"] = str(e)
        return summary

    risorse = estrai_risorse(html, url_base)

    for r in risorse:
        url_pagina = r["url_pagina"]
        url_doc = r.get("url_documento")
        tipo = r.get("tipo", "pagina")

        # Salta se non autorizzato
        if not _is_domain_allowed(url_pagina):
            continue

        summary["scraped"] += 1

        # Estrai metadati
        meta = estrai_metadati(url_pagina, r.get("html"), html)

        # Cerca esistente
        existing = get_fonti_risorsa_by_url(url_pagina)

        if existing:
            # Aggiorna
            update_fonti_risorsa(existing["id"], {
                "url_documento": url_doc,
                "tipo_risorsa": tipo,
                "titolo": meta.get("titolo"),
                "descrizione": meta.get("descrizione"),
                "autore": meta.get("autore"),
                "ente_titolare": meta.get("ente_titolare"),
                "data_pubblicazione": meta.get("data_pubblicazione"),
                "lingua": meta.get("lingua"),
                "licenza": meta.get("licenza"),
                "note_copyright": meta.get("note_copyright"),
                "stato": "valido",
            })
            summary["updated"] += 1
        else:
            # Inserisci nuovo
            insert_fonti_risorsa({
                "fonte_id": fonte_id,
                "url_pagina": url_pagina,
                "url_documento": url_doc,
                "tipo_risorsa": tipo,
                "titolo": meta.get("titolo"),
                "descrizione": meta.get("descrizione"),
                "autore": meta.get("autore"),
                "ente_titolare": meta.get("ente_titolare"),
                "data_pubblicazione": meta.get("data_pubblicazione"),
                "lingua": meta.get("lingua"),
                "licenza": meta.get("licenza"),
                "note_copyright": meta.get("note_copyright"),
                "stato": "valido" if meta.get("titolo") else "non_verificato",
            })
            summary["inserted"] += 1

    return summary


# ─── 5. Caching / TTL ─────────────────────────────────────────────────────────

def needs_refresh(fonte_id: int, ttl_days: int = None) -> bool:
    """Verifica se le risorse di una fonte hanno bisogno di re-scraping
    in base al TTL (default: SCRAPER_TTL_DAYS)."""
    if ttl_days is None:
        ttl_days = SCRAPER_TTL_DAYS

    risorse = get_fonti_risorse_by_fonte_id(fonte_id)
    if not risorse:
        return True  # Nessuna risorsa = mai scrapato

    cutoff = datetime.now() - timedelta(days=ttl_days)
    for r in risorse:
        last = r.get("last_checked_at")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            if last_dt < cutoff:
                return True
        except (ValueError, TypeError):
            return True

    return False


def scrape_if_stale(fonte_record: dict, ttl_days: int = None) -> Optional[dict]:
    """Esegue scrape_fonte solo se le risorse sono stale (oltre TTL).
    Ritorna il summary se scraping eseguito, None se non necessario."""
    fonte_id = fonte_record.get("id")
    if fonte_id and not needs_refresh(fonte_id, ttl_days):
        return None
    return scrape_fonte(fonte_record)
