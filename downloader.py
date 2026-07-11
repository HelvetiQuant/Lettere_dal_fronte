import os
import urllib.request
from pathlib import Path

from config import IMI_PDFS

PDF_DIR = Path(__file__).parent / "pdfs"
PDF_DIR.mkdir(exist_ok=True)


def pdf_path(letter: str) -> Path:
    return PDF_DIR / f"Elenco_{letter}.pdf"


def is_downloaded(letter: str) -> bool:
    p = pdf_path(letter)
    return p.exists() and p.stat().st_size > 1000


def download_letter(letter: str) -> Path:
    if letter not in IMI_PDFS:
        raise ValueError(f"Lettera non valida: {letter}")
    dest = pdf_path(letter)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    url = IMI_PDFS[letter]
    print(f"  Download {letter}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(dest, "wb") as f:
            f.write(resp.read())
    print(f"  Salvato: {dest} ({dest.stat().st_size} bytes)")
    return dest


def download_all():
    for letter in IMI_PDFS:
        if is_downloaded(letter):
            print(f"  [{letter}] gia scaricato, skip")
            continue
        download_letter(letter)


def get_downloaded_letters() -> list[str]:
    return [l for l in IMI_PDFS if is_downloaded(l)]
