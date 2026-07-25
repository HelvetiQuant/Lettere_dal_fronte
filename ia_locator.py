"""ia_locator.py — Estrazione locator pagina/passaggio da item Internet Archive.

Recupera e analizza:
1. hOCR (format _djvu.xml o hOCR endpoint) — estrae testo per pagina con coordinate
2. DjVu text layer — estrae testo per pagina
3. Page index / leaf count — metadati strutturali

Produce un Locator con:
- identifier IA
- page_start / page_end (1-indexed)
- snippet (testo estratto della pagina)
- bounding_box (coordinate hOCR se disponibili)
- confidence (0.0–1.0)

Non inventa dati: se il text layer non è disponibile, ritorna locator con
confidence=0 e note esplicative.
"""
from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger("ia_locator")

IA_BASE = "https://archive.org"
FETCH_TIMEOUT = 30
USER_AGENT = "IMI-Extractor/1.0 (research; contact: imi-extractor@example.org)"


@dataclass
class PageLocator:
    """Locator di pagina/passaggio per un item IA."""
    identifier: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    snippet: str = ""
    bounding_box: Optional[Dict[str, float]] = None  # {x0, y0, x1, y1}
    confidence: float = 0.0
    source: str = ""  # "hocr" | "djvu" | "page_index" | "metadata"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "snippet": self.snippet[:500],
            "bounding_box": self.bounding_box,
            "confidence": self.confidence,
            "source": self.source,
            "note": self.note,
        }


@dataclass
class AssetSelection:
    """Selezione del miglior asset per un item IA."""
    identifier: str
    best_format: str = ""  # "hocr" | "djvu" | "pdf" | "text"
    best_url: str = ""
    available_formats: List[str] = field(default_factory=list)
    page_count: int = 0
    has_ocr: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "best_format": self.best_format,
            "best_url": self.best_url,
            "available_formats": self.available_formats,
            "page_count": self.page_count,
            "has_ocr": self.has_ocr,
            "note": self.note,
        }


# ─── Asset selection ─────────────────────────────────────────────────────────

# Priorità formati: OCR > DjVu > PDF > text
FORMAT_PRIORITY = {
    "hocr": 5,
    "djvu": 4,
    "djvtxt": 3,
    "text pdf": 3,
    "pdf": 2,
    "txt": 1,
    "image": 0,
}


def select_best_asset(identifier: str, files: List[Dict[str, Any]]) -> AssetSelection:
    """Seleziona il miglior asset dall'item IA, priorità OCR.

    Args:
        identifier: IA identifier
        files: lista file dall'API metadata (server.files)

    Returns:
        AssetSelection con formato, URL e metadati
    """
    sel = AssetSelection(identifier=identifier)
    if not files:
        sel.note = "Nessun file disponibile nell'item"
        return sel

    best_score = -1
    for f in files:
        fmt = (f.get("format") or "").lower().strip()
        name = f.get("name", "")
        sel.available_formats.append(fmt)

        if fmt in ("hocr", "djvu", "djvtxt"):
            sel.has_ocr = True

        score = FORMAT_PRIORITY.get(fmt, -1)
        if score > best_score:
            best_score = score
            sel.best_format = fmt
            if fmt == "hocr":
                sel.best_url = f"{IA_BASE}/download/{identifier}/{name}"
            elif fmt == "djvu":
                sel.best_url = f"{IA_BASE}/download/{identifier}/{name}"
            elif fmt == "pdf":
                sel.best_url = f"{IA_BASE}/download/{identifier}/{name}"
            elif fmt == "txt":
                sel.best_url = f"{IA_BASE}/download/{identifier}/{name}"
            else:
                sel.best_url = f"{IA_BASE}/download/{identifier}/{name}"

    # Page count from metadata
    for f in files:
        if f.get("format", "").lower() in ("hocr", "djvu", "pdf"):
            try:
                sel.page_count = int(f.get("length", 0) or 0)
            except (ValueError, TypeError):
                pass
            break

    if not sel.best_format:
        sel.note = "Nessun formato leggibile trovato"
    elif sel.has_ocr:
        sel.note = f"OCR disponibile ({sel.best_format})"
    else:
        sel.note = f"Solo {sel.best_format} — OCR non disponibile"

    return sel


# ─── hOCR parsing ────────────────────────────────────────────────────────────

def _fetch_hocr(identifier: str, file_name: str = None) -> Optional[str]:
    """Scarica il file hOCR per un item IA."""
    if file_name is None:
        file_name = f"{identifier}_hocr.html"
    url = f"{IA_BASE}/download/{identifier}/{file_name}"
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT
        )
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception as e:
        logger.debug("hOCR fetch failed for %s: %s", identifier, e)
    return None


def parse_hocr_pages(hocr_text: str) -> List[Dict[str, Any]]:
    """Parse hOCR HTML e estrae testo per pagina.

    hOCR usa microformat HTML con classi:
    - div.ocr_page (pagina)
    - span.ocr_line (riga)
    - title="bbox x0 y0 x1 y1; ..." (coordinate)

    Returns:
        Lista di dict: {page_num, text, bbox}
    """
    pages = []
    page_num = 0

    # Pattern per pagine hOCR
    page_pattern = re.compile(
        r'<div[^>]*class="[^"]*ocr_page[^"]*"[^>]*title="([^"]*)"[^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE,
    )
    line_pattern = re.compile(
        r'<span[^>]*class="[^"]*ocr_line[^"]*"[^>]*>(.*?)</span>',
        re.DOTALL | re.IGNORECASE,
    )
    word_pattern = re.compile(
        r'<span[^>]*class="[^"]*ocrx_word[^"]*"[^>]*>(.*?)</span>',
        re.DOTALL | re.IGNORECASE,
    )
    bbox_pattern = re.compile(r"bbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)")

    for page_match in page_pattern.finditer(hocr_text):
        page_num += 1
        title_str = page_match.group(1)
        page_content = page_match.group(2)

        # Extract bbox from title
        bbox_match = bbox_pattern.search(title_str)
        page_bbox = None
        if bbox_match:
            page_bbox = {
                "x0": int(bbox_match.group(1)),
                "y0": int(bbox_match.group(2)),
                "x1": int(bbox_match.group(3)),
                "y1": int(bbox_match.group(4)),
            }

        # Extract text from lines
        lines_text = []
        for line_match in line_pattern.finditer(page_content):
            line_content = line_match.group(1)
            # Try word-level first
            words = word_pattern.findall(line_content)
            if words:
                line_text = " ".join(re.sub(r"<[^>]+>", "", w).strip() for w in words)
            else:
                line_text = re.sub(r"<[^>]+>", "", line_content).strip()
            if line_text:
                lines_text.append(line_text)

        full_text = "\n".join(lines_text)
        pages.append({
            "page_num": page_num,
            "text": full_text,
            "bbox": page_bbox,
        })

    return pages


def find_passage_in_hocr(
    hocr_pages: List[Dict[str, Any]],
    search_terms: List[str],
) -> Optional[PageLocator]:
    """Cerca termini di evento nelle pagine hOCR e localizza il passaggio.

    Args:
        hocr_pages: output di parse_hocr_pages
        search_terms: termini da cercare (keywords evento, nomi, luoghi)

    Returns:
        PageLocator con pagina, snippet e confidence
    """
    if not hocr_pages or not search_terms:
        return None

    terms_lower = [t.lower() for t in search_terms if len(t) >= 4]
    if not terms_lower:
        return None

    best_page = None
    best_score = 0
    best_snippet = ""

    for page in hocr_pages:
        text = page["text"].lower()
        if not text:
            continue
        matches = sum(1 for t in terms_lower if t in text)
        if matches > best_score:
            best_score = matches
            best_page = page["page_num"]
            # Extract snippet around first match
            text_orig = page["text"]
            for t in terms_lower:
                idx = text.find(t)
                if idx >= 0:
                    start = max(0, idx - 100)
                    end = min(len(text_orig), idx + len(t) + 200)
                    best_snippet = text_orig[start:end]
                    break

    if best_page and best_score > 0:
        confidence = min(best_score / len(terms_lower), 1.0)
        return PageLocator(
            identifier="",
            page_start=best_page,
            page_end=best_page,
            snippet=best_snippet,
            confidence=confidence,
            source="hocr",
            note=f"Trovati {best_score} termini su {len(terms_lower)} cercati",
        )
    return None


# ─── DjVu text parsing ───────────────────────────────────────────────────────

def _fetch_djvu_text(identifier: str) -> Optional[str]:
    """Scarica il text layer DjVu per un item IA."""
    url = f"{IA_BASE}/download/{identifier}/{identifier}_djvu.txt"
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT
        )
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception as e:
        logger.debug("DjVu text fetch failed for %s: %s", identifier, e)
    return None


def parse_djvu_text(djvu_text: str) -> List[Dict[str, Any]]:
    """Parse DjVu text layer e estrae testo per pagina.

    DjVu text ha marcatori di pagina come:
    - "Page 1" / "PAGE 1"
    - oppure formattazione con coordinate
    """
    pages = []
    # Split su marker di pagina
    page_splits = re.split(r"\n\s*(?:Page|PAGE)\s+(\d+)\s*\n", djvu_text)

    if len(page_splits) > 1:
        # Format: [pre, num1, text1, num2, text2, ...]
        for i in range(1, len(page_splits) - 1, 2):
            page_num = int(page_splits[i])
            text = page_splits[i + 1].strip()
            pages.append({"page_num": page_num, "text": text, "bbox": None})
    else:
        # Nessun marker: tutto in una pagina
        if djvu_text.strip():
            pages.append({"page_num": 1, "text": djvu_text.strip(), "bbox": None})

    return pages


def find_passage_in_djvu(
    djvu_pages: List[Dict[str, Any]],
    search_terms: List[str],
    identifier: str = "",
) -> Optional[PageLocator]:
    """Cerca termini nelle pagine DjVu text."""
    if not djvu_pages or not search_terms:
        return None

    terms_lower = [t.lower() for t in search_terms if len(t) >= 4]
    if not terms_lower:
        return None

    best_page = None
    best_score = 0
    best_snippet = ""

    for page in djvu_pages:
        text = page["text"].lower()
        if not text:
            continue
        matches = sum(1 for t in terms_lower if t in text)
        if matches > best_score:
            best_score = matches
            best_page = page["page_num"]
            text_orig = page["text"]
            for t in terms_lower:
                idx = text.find(t)
                if idx >= 0:
                    start = max(0, idx - 100)
                    end = min(len(text_orig), idx + len(t) + 200)
                    best_snippet = text_orig[start:end]
                    break

    if best_page and best_score > 0:
        confidence = min(best_score / len(terms_lower), 0.9)  # DjVu slightly lower
        return PageLocator(
            identifier=identifier,
            page_start=best_page,
            page_end=best_page,
            snippet=best_snippet,
            confidence=confidence,
            source="djvu",
            note=f"Trovati {best_score} termini su {len(terms_lower)} cercati",
        )
    return None


# ─── Page index from metadata ────────────────────────────────────────────────

def get_page_count_from_metadata(metadata: Dict[str, Any]) -> int:
    """Estrae il numero di pagine dai metadati IA."""
    # Try server.files count for image/OCR files
    files = metadata.get("server", {}).get("files", [])
    ocr_files = [
        f for f in files
        if (f.get("format") or "").lower() in ("hocr", "djvu", "pdf", "single page original")
    ]
    if ocr_files:
        # Count hOCR files = page count
        hocr_count = sum(
            1 for f in ocr_files
            if (f.get("format") or "").lower() == "hocr"
        )
        if hocr_count > 0:
            return hocr_count

    # Try metadata field
    meta = metadata.get("metadata", {})
    for key in ("imagecount", "pages", "numpages", "leafcount"):
        val = meta.get(key)
        if val:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass

    return 0


# ─── Pipeline locator ────────────────────────────────────────────────────────

def locate_passage(
    identifier: str,
    search_terms: List[str],
    metadata: Dict[str, Any] = None,
) -> PageLocator:
    """Pipeline completa di localizzazione passaggio.

    1. Seleziona miglior asset (hOCR > DjVu > PDF)
    2. Scarica e parse hOCR se disponibile
    3. Fallback a DjVu text
    4. Cerca termini evento nelle pagine
    5. Ritorna PageLocator

    Args:
        identifier: IA identifier
        search_terms: termini da cercare (keywords evento, nomi, luoghi)
        metadata: metadati IA (opzionale, per asset selection)

    Returns:
        PageLocator con pagina, snippet e confidence
    """
    metadata = metadata or {}
    files = metadata.get("server", {}).get("files", [])

    if not files:
        # Try to fetch metadata
        try:
            url = f"{IA_BASE}/metadata/{identifier}"
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT
            )
            if resp.status_code == 200:
                metadata = resp.json()
                files = metadata.get("server", {}).get("files", [])
        except Exception as e:
            logger.warning("Metadata fetch failed for %s: %s", identifier, e)

    asset = select_best_asset(identifier, files)

    # Strategy 1: hOCR
    if "hocr" in asset.available_formats or asset.best_format == "hocr":
        hocr_text = _fetch_hocr(identifier)
        if hocr_text:
            pages = parse_hocr_pages(hocr_text)
            if pages:
                locator = find_passage_in_hocr(pages, search_terms)
                if locator:
                    locator.identifier = identifier
                    return locator
                return PageLocator(
                    identifier=identifier,
                    page_count=len(pages),
                    confidence=0.0,
                    source="hocr",
                    note=f"hOCR disponibile ({len(pages)} pagine) ma termini non trovati",
                )

    # Strategy 2: DjVu text
    djvu_text = _fetch_djvu_text(identifier)
    if djvu_text:
        pages = parse_djvu_text(djvu_text)
        if pages:
            locator = find_passage_in_djvu(pages, search_terms, identifier)
            if locator:
                return locator
            return PageLocator(
                identifier=identifier,
                page_start=None,
                page_end=None,
                confidence=0.0,
                source="djvu",
                note=f"DjVu text disponibile ({len(pages)} pagine) ma termini non trovati",
            )

    # Strategy 3: Page count only
    page_count = get_page_count_from_metadata(metadata)
    if page_count > 0:
        return PageLocator(
            identifier=identifier,
            confidence=0.0,
            source="page_index",
            note=f"Page count disponibile ({page_count} pagine) ma nessun text layer accessibile",
        )

    return PageLocator(
        identifier=identifier,
        confidence=0.0,
        source="metadata",
        note="Nessun text layer o page index disponibile",
    )
