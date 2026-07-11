import os
import re
import time
import base64
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import COLUMNS
from database import save_internato
from extractor import _get_client, _get_mistral_client, _parse_json_response, PARSE_PROMPT, _render_page_image, _mistral_ocr_page

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
MAX_DEPTH = 2
MAX_PAGES = 50
DOWNLOAD_DIR = Path(__file__).parent / "scraped"


def _is_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _is_image(url: str) -> bool:
    return any(urlparse(url).path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


def scrape_site(base_url: str, max_depth: int = MAX_DEPTH, progress_cb=None) -> dict:
    """Scrape a website for PDF and image links, download them, and extract data."""
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    visited = set()
    found_pdfs = []
    found_images = []
    total_extracted = 0

    def _crawl(url: str, depth: int):
        nonlocal total_extracted
        if depth > max_depth or url in visited or len(visited) >= MAX_PAGES:
            return
        visited.add(url)
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code != 200:
                return
            if "text/html" in content_type:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    full_url = urljoin(url, a["href"])
                    if _is_pdf(full_url) and full_url not in found_pdfs:
                        found_pdfs.append(full_url)
                        if progress_cb:
                            progress_cb({"type": "pdf", "url": full_url, "total": len(found_pdfs)})
                    elif _is_image(full_url) and full_url not in found_images:
                        found_images.append(full_url)
                        if progress_cb:
                            progress_cb({"type": "image", "url": full_url, "total": len(found_images)})
                    elif depth < max_depth and full_url.startswith(base_url) and full_url not in visited:
                        _crawl(full_url, depth + 1)
                for img in soup.find_all("img", src=True):
                    full_url = urljoin(url, img["src"])
                    if _is_image(full_url) and full_url not in found_images:
                        found_images.append(full_url)
                        if progress_cb:
                            progress_cb({"type": "image", "url": full_url, "total": len(found_images)})
            elif _is_pdf(url):
                if url not in found_pdfs:
                    found_pdfs.append(url)
            elif _is_image(url):
                if url not in found_images:
                    found_images.append(url)
        except Exception as e:
            print(f"  [SCRAPER] Error crawling {url}: {e}")

    _crawl(base_url, 0)

    if progress_cb:
        progress_cb({"type": "status", "message": f"Trovati {len(found_pdfs)} PDF e {len(found_images)} immagini"})

    for pdf_url in found_pdfs:
        try:
            fname = Path(urlparse(pdf_url).path).name or f"scraped_{len(found_pdfs)}.pdf"
            local_path = DOWNLOAD_DIR / fname
            if not local_path.exists():
                resp = requests.get(pdf_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                local_path.write_bytes(resp.content)
            if progress_cb:
                progress_cb({"type": "downloading", "file": str(local_path)})
            count = _extract_from_pdf(local_path, source_url=pdf_url)
            total_extracted += count
            if progress_cb:
                progress_cb({"type": "pdf_done", "file": fname, "extracted": count, "total_extracted": total_extracted})
        except Exception as e:
            print(f"  [SCRAPER] Error processing PDF {pdf_url}: {e}")

    for img_url in found_images:
        try:
            fname = Path(urlparse(img_url).path).name or f"scraped_{len(found_images)}.jpg"
            local_path = DOWNLOAD_DIR / fname
            if not local_path.exists():
                resp = requests.get(img_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                local_path.write_bytes(resp.content)
            if progress_cb:
                progress_cb({"type": "downloading", "file": str(local_path)})
            count = _extract_from_image(local_path, source_url=img_url)
            total_extracted += count
            if progress_cb:
                progress_cb({"type": "image_done", "file": fname, "extracted": count, "total_extracted": total_extracted})
        except Exception as e:
            print(f"  [SCRAPER] Error processing image {img_url}: {e}")

    return {
        "pdfs_found": len(found_pdfs),
        "images_found": len(found_images),
        "total_extracted": total_extracted,
        "pdfs": found_pdfs,
        "images": found_images,
    }


def _extract_from_pdf(pdf_path: Path, source_url: str = "") -> int:
    import pdfplumber
    pdf_doc = pdfplumber.open(str(pdf_path))
    count = 0
    for i, page in enumerate(pdf_doc.pages):
        text = page.extract_text() or ""
        if len(text.strip()) < 50:
            try:
                rows = _parse_image_page_local(pdf_path, i)
            except Exception:
                rows = []
        else:
            try:
                rows = _parse_text_with_gpt(text, i + 1)
            except Exception:
                rows = []
        for row in rows:
            if row.get("cognome"):
                save_internato("SCRAPED", pdf_path.name, i + 1, row, text[:500])
                count += 1
    pdf_doc.close()
    return count


def _extract_from_image(img_path: Path, source_url: str = "") -> int:
    try:
        client = _get_mistral_client()
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        result = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
        )
        text = result.pages[0].markdown if result.pages else ""
    except Exception:
        try:
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            client = _get_client()
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": PARSE_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Analizza l'immagine ed estrai i dati degli internati."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                    ]},
                ],
                max_tokens=4096,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            rows = _parse_json_response(raw)
            count = 0
            for row in rows:
                if row.get("cognome"):
                    save_internato("SCRAPED", img_path.name, 1, row, "")
                    count += 1
            return count
        except Exception as e:
            print(f"  [SCRAPER] Image OCR failed: {e}")
            return 0

    if len(text.strip()) < 20:
        return 0
    try:
        rows = _parse_text_with_gpt(text, 1)
    except Exception:
        rows = []
    count = 0
    for row in rows:
        if row.get("cognome"):
            save_internato("SCRAPED", img_path.name, 1, row, text[:500])
            count += 1
    return count


def _parse_text_with_gpt(text: str, page_num: int) -> list[dict]:
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PARSE_PROMPT},
            {"role": "user", "content": f"Pagina {page_num}. Testo OCR:\n\n{text}"},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_json_response(raw)


def _parse_image_page_local(pdf_path: Path, page_num: int) -> list[dict]:
    client = _get_client()
    b64 = _render_page_image(pdf_path, page_num)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": PARSE_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"Pagina {page_num + 1}. Analizza l'immagine ed estrai i dati degli internati."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            ]},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_json_response(raw)


_scrape_lock = threading.Lock()
_scrape_status = {"running": False, "url": "", "logs": [], "result": None}


def run_scrape(url: str, max_depth: int = 2):
    global _scrape_status
    if not _scrape_lock.acquire(blocking=False):
        return False
    _scrape_status = {"running": True, "url": url, "logs": [], "result": None}

    def cb(info):
        _scrape_status["logs"].append(info)

    def run():
        global _scrape_status
        try:
            result = scrape_site(url, max_depth=max_depth, progress_cb=cb)
            _scrape_status["result"] = result
        except Exception as e:
            _scrape_status["logs"].append({"type": "error", "message": str(e)})
        finally:
            _scrape_status["running"] = False
            _scrape_lock.release()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return True


def get_scrape_status() -> dict:
    return _scrape_status
