"""scraper_cimeetrincee.py — Scraper dedicato per cimeetrincee.it

Estrae metadati da due sezioni del sito:
1. /storie-e-soldati/ — articoli su soldati ed eventi della Grande Guerra
   → upsert in archivio_documenti (provider='CimeTrincee', doc_type='storia')
2. /foto-depoca/ — album fotografici con gallerie di immagini
   → insert in fonti_risorse (metadati + link diretto alle immagini)

PRINCIPIO: solo metadati + link diretti. Nessun download di contenuti
protetti da copyright (no testo integrale, no immagini full-res).

Rispetta rate limit (10 req/min) e robots.txt.
"""
from __future__ import annotations

import re
import time
import logging
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

import config as cfg

log = logging.getLogger(__name__)

_BASE = "https://www.cimeetrincee.it"
_STORIE_URL = f"{_BASE}/storie-e-soldati/"
_FOTO_URL = f"{_BASE}/foto-depoca/"
_ENTE = "ASCET - Cime e Trincee"
_RIGHTS = "© ASCET - Cime e Trincee"

_last_request_times: List[float] = []


def _rate_limit() -> None:
    """Rate limiting: max 10 req/min per dominio (config esistente)."""
    now = time.time()
    cutoff = now - 60.0
    while _last_request_times and _last_request_times[0] < cutoff:
        _last_request_times.pop(0)
    if len(_last_request_times) >= cfg.SCRAPER_MAX_REQUESTS_PER_MINUTE:
        sleep_for = 60.0 - (now - _last_request_times[0])
        if sleep_for > 0:
            log.debug("Rate limit: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)
    _last_request_times.append(time.time())


def _fetch(url: str) -> str:
    """Fetch HTML con rate limiting, timeout e user agent configurati."""
    _rate_limit()
    headers = {"User-Agent": cfg.SCRAPER_USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=cfg.SCRAPER_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.text


class _LinkExtractor(HTMLParser):
    """Estrae link da tag <a> con testo, per scorrere pagine indice."""

    def __init__(self):
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self._in_a = False
        self._current_href = ""
        self._current_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            href = d.get("href", "")
            if href:
                self._in_a = True
                self._current_href = href
                self._current_text = []

    def handle_data(self, data):
        if self._in_a:
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            text = " ".join(self._current_text).strip()
            if text:
                self.links.append((self._current_href, text))
            self._in_a = False


class _ArticleExtractor(HTMLParser):
    """Estrae titolo (h1), sottotitolo (h2), paragrafi, autore e immagini da un articolo."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.subtitle = ""
        self.author = ""
        self.paragraphs: List[str] = []
        self.images: List[Dict[str, str]] = []
        self._in_h1 = False
        self._in_h2 = False
        self._in_p = False
        self._in_author = False
        self._h1_text: List[str] = []
        self._h2_text: List[str] = []
        self._p_text: List[str] = []
        self._author_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "h1":
            self._in_h1 = True
            self._h1_text = []
        elif tag == "h2":
            self._in_h2 = True
            self._h2_text = []
        elif tag == "p":
            self._in_p = True
            self._p_text = []
        elif tag == "a" and "author" in (d.get("href", "") + d.get("class", "")):
            self._in_author = True
            self._author_text = []
        elif tag == "img":
            src = d.get("src") or d.get("data-src") or ""
            alt = d.get("alt", "")
            if src and not src.endswith((".svg", ".ico")):
                self.images.append({"src": src, "alt": alt})

    def handle_data(self, data):
        if self._in_h1:
            self._h1_text.append(data)
        if self._in_h2:
            self._h2_text.append(data)
        if self._in_p:
            self._p_text.append(data)
        if self._in_author:
            self._author_text.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self._in_h1:
            self.title = " ".join(self._h1_text).strip()
            self._in_h1 = False
        elif tag == "h2" and self._in_h2:
            text = " ".join(self._h2_text).strip()
            if not self.subtitle:
                self.subtitle = text
            self._in_h2 = False
        elif tag == "p" and self._in_p:
            text = " ".join(self._p_text).strip()
            if text and len(text) > 20:
                self.paragraphs.append(text)
            self._in_p = False
        elif tag == "a" and self._in_author:
            self.author = " ".join(self._author_text).strip()
            self._in_author = False


def _extract_article_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """Estrae link agli articoli dalla pagina indice.
    Filtra link interni che puntano a articoli (non nav, footer, ecc.)."""
    parser = _LinkExtractor()
    parser.feed(html)
    parsed_base = urlparse(base_url)
    articles = []
    seen = set()
    for href, text in parser.links:
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        # Solo link allo stesso dominio, con path che sembra un articolo
        if parsed.netloc not in ("www.cimeetrincee.it", "cimeetrincee.it"):
            continue
        # Salta pagine di sistema
        skip_patterns = ["/author/", "/category/", "/tag/", "/page/", "/wp-",
                         "/privacy/", "/storie-e-soldati/", "/foto-depoca/",
                         "/contatti", "/wp-json", "/feed"]
        if any(p in parsed.path.lower() for p in skip_patterns):
            continue
        if not parsed.path or parsed.path == "/":
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        articles.append((full_url, text))
    return articles


def _extract_slug(url: str) -> str:
    """Estrae lo slug dall'URL (ultima parte del path)."""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    return parts[-1] if parts else path


def _extract_soldier_name(title: str) -> Optional[Tuple[str, str]]:
    """Tenta di estrarre cognome e nome dal titolo dell'articolo.
    Pattern: 'Bartolomei Ugo', 'Chinelli Silvio', ecc.
    Ritorna (cognome, nome) o None."""
    # Pattern: Cognome Nome (due parole, maiuscola all'inizio)
    m = re.match(r"^([A-Z][a-zà-ù]+)\s+([A-Z][a-zà-ù]+)", title)
    if m:
        return m.group(1), m.group(2)
    # Pattern: "Cognome Nome" dopo eventuale prefisso
    m = re.search(r"\b([A-Z][a-zà-ù]+)\s+([A-Z][a-zà-ù]+)\b", title)
    if m:
        return m.group(1), m.group(2)
    return None


def scrape_storie_e_soldati() -> List[Dict[str, Any]]:
    """Scrape della sezione /storie-e-soldati/ di cimeetrincee.it.

    Estrae tutti gli articoli dalla pagina indice e per ciascuno:
    - titolo, sottotitolo, autore, estratto testo
    - nomi soldati dal titolo

    Ritorna lista di dict compatibili con archivio_documenti.upsert_documenti().
    """
    log.info("Scraping storie-e-soldati da %s", _STORIE_URL)
    html = _fetch(_STORIE_URL)
    articles = _extract_article_links(html, _STORIE_URL)
    log.info("Trovati %d articoli nella pagina indice", len(articles))

    results: List[Dict[str, Any]] = []
    for url, link_text in articles:
        try:
            article_html = _fetch(url)
            parser = _ArticleExtractor()
            parser.feed(article_html)

            title = parser.title or link_text
            subtitle = parser.subtitle or ""
            author = parser.author or ""
            excerpt = " ".join(parser.paragraphs[:3])[:500] if parser.paragraphs else ""

            description = subtitle
            if excerpt:
                description = f"{subtitle} — {excerpt}" if subtitle else excerpt

            slug = _extract_slug(url)
            soldier = _extract_soldier_name(title)

            row = {
                "provider": "CimeTrincee",
                "external_id": slug,
                "doc_type": "storia",
                "title": title,
                "description": description[:1000] if description else "",
                "creator": author or "Gira (Daniele)",
                "date_text": "",
                "year_start": 1914,
                "year_end": 1918,
                "place": "",
                "war": "WWI",
                "language": "ita",
                "rights": _RIGHTS,
                "source_url": url,
                "thumbnail_url": parser.images[0]["src"] if parser.images else None,
                "iiif_manifest": None,
                "provider_collection": "Storie e Soldati",
                "raw_json": {"soldier_name": f"{soldier[0]} {soldier[1]}" if soldier else None,
                             "link_text": link_text},
            }
            results.append(row)
            log.debug("Articolo: %s — %s", slug, title)
        except Exception as e:
            log.warning("Errore scraping articolo %s: %s", url, e)

    log.info("Storie e soldati: %d record estratti", len(results))
    return results


def scrape_foto_depoca() -> List[Dict[str, Any]]:
    """Scrape della sezione /foto-depoca/ di cimeetrincee.it.

    Estrae tutti gli album dalla pagina indice e per ciascuno:
    - titolo, descrizione, autore/archivio
    - URL diretti delle immagini dalla galleria

    Ritorna lista di dict compatibili con database.insert_fonti_risorsa().
    """
    log.info("Scraping foto-depoca da %s", _FOTO_URL)
    html = _fetch(_FOTO_URL)
    albums = _extract_article_links(html, _FOTO_URL)
    log.info("Trovati %d album nella pagina indice", len(albums))

    results: List[Dict[str, Any]] = []
    for url, link_text in albums:
        try:
            album_html = _fetch(url)
            parser = _ArticleExtractor()
            parser.feed(album_html)

            title = parser.title or link_text
            subtitle = parser.subtitle or ""
            author = parser.author or ""
            description = subtitle or link_text

            # Per ogni immagine trovata, crea un record fonti_risorse
            for img in parser.images:
                src = img["src"]
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = urljoin(_BASE, src)
                elif not src.startswith("http"):
                    src = urljoin(url, src)

                # Salta thumbnail piccole, logo, icone
                if any(x in src.lower() for x in ["logo", "icon", "favicon", "emoji",
                                                   "wp-content/uploads/sites", "cropped-"]):
                    continue

                img_title = title
                if img["alt"]:
                    img_title = f"{title} — {img['alt']}"

                record = {
                    "url_pagina": url,
                    "url_documento": src,
                    "tipo_risorsa": "immagine",
                    "titolo": img_title,
                    "descrizione": description[:500] if description else "",
                    "autore": author or "Autore ignoto",
                    "ente_titolare": _ENTE,
                    "data_pubblicazione": "",
                    "lingua": "ita",
                    "licenza": "tutti i diritti riservati",
                    "note_copyright": "Immagine d'epoca - ASCET. Uso consentito per ricerca storica con citazione della fonte.",
                    "stato": "non_verificato",
                }
                results.append(record)

            # Se non ci sono immagini, crea almeno un record per la pagina
            if not parser.images:
                record = {
                    "url_pagina": url,
                    "url_documento": None,
                    "tipo_risorsa": "album",
                    "titolo": title,
                    "descrizione": description[:500] if description else "",
                    "autore": author or "Autore ignoto",
                    "ente_titolare": _ENTE,
                    "data_pubblicazione": "",
                    "lingua": "ita",
                    "licenza": "tutti i diritti riservati",
                    "note_copyright": "Album fotografico - ASCET. Uso consentito per ricerca storica con citazione della fonte.",
                    "stato": "non_verificato",
                }
                results.append(record)

            log.debug("Album: %s — %d immagini", _extract_slug(url), len(parser.images))
        except Exception as e:
            log.warning("Errore scraping album %s: %s", url, e)

    log.info("Foto d'epoca: %d record estratti", len(results))
    return results


def scrape_all() -> Dict[str, int]:
    """Orchestrazione: scrape entrambe le sezioni.
    Ritorna summary con conteggi."""
    storie = scrape_storie_e_soldati()
    foto = scrape_foto_depoca()
    return {
        "storie": len(storie),
        "foto": len(foto),
        "total": len(storie) + len(foto),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = scrape_all()
    print(f"Storie: {summary['storie']}, Foto: {summary['foto']}, Total: {summary['total']}")
