"""Pipeline per i fondi archivistici dell'Ufficio Storico dello Stato Maggiore
dell'Esercito (SME). Scarica i PDF degli inventari/carteggi, ne estrae il testo,
lo struttura in schede di fondo e ne estrae le menzioni di persone/luoghi per la
ricerca incrociata con il sistema IMI ("lettere dal fronte")."""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber
import requests
import urllib3

from credits import log_openai_usage
from database import (
    save_fondo, save_menzione, is_fondo_page_processed,
    init_progress, update_progress, finish_progress, get_progress,
)
from extractor import (
    _get_client, _mistral_ocr_page, _parse_json_response, PARSE_MODEL_MINI,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.esercito.difesa.it/storia/ufficio-storico-sme/archivio-documentale/93917.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FONDI_DIR = Path(__file__).parent / "fondi_pdfs"
FONDI_DIR.mkdir(exist_ok=True)

stop_event = threading.Event()


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def is_stop_requested() -> bool:
    return stop_event.is_set()


# ─── Download ───

def _get(url: str, **kwargs):
    try:
        return requests.get(url, headers=HEADERS, timeout=90, **kwargs)
    except requests.exceptions.SSLError:
        return requests.get(url, headers=HEADERS, timeout=90, verify=False, **kwargs)


def list_pdf_urls() -> list[str]:
    r = _get(BASE_URL)
    r.raise_for_status()
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', r.text, re.IGNORECASE)
    pdfs = sorted({urljoin(BASE_URL, h) for h in hrefs if h.lower().endswith(".pdf")})
    return pdfs


def _local_name(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def download_pdf(url: str) -> Path:
    dest = FONDI_DIR / _local_name(url)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    r = _get(url, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest


def download_all() -> list[dict]:
    urls = list_pdf_urls()
    results = []
    for u in urls:
        try:
            p = download_pdf(u)
            results.append({"file": _local_name(u), "status": "ok", "size": p.stat().st_size})
        except Exception as e:
            results.append({"file": _local_name(u), "status": "error", "error": str(e)})
    return results


# ─── Estrazione ───

FONDI_PROMPT = """Sei un archivista esperto. Analizzi una pagina di un INVENTARIO o CARTEGGIO
archivistico dell'Ufficio Storico dello Stato Maggiore dell'Esercito Italiano.
Questi documenti descrivono fondi archivistici (buste, fascicoli, carteggi) e a volte
contengono NOMI DI PERSONE (militari, generali, prigionieri, funzionari) e LUOGHI.

Restituisci ESCLUSIVAMENTE un oggetto JSON valido con questa struttura:
{
  "descrizione": "sintesi (max 2 frasi) del contenuto della pagina",
  "periodo": "intervallo di date o anno (es. '1915-1918') se presente, altrimenti null",
  "busta": "numero/i di busta se citati, altrimenti null",
  "fascicolo": "numero/i di fascicolo se citati, altrimenti null",
  "luoghi": "luoghi geografici citati separati da virgola, altrimenti null",
  "menzioni": [
    {
      "cognome": "cognome della persona",
      "nome": "nome se presente, altrimenti null",
      "grado": "grado/qualifica militare o civile se presente, altrimenti null",
      "reparto": "reparto/reggimento/unita' se presente, altrimenti null",
      "luogo": "luogo associato alla persona se presente, altrimenti null",
      "data": "data associata se presente, altrimenti null",
      "contesto": "breve frase di contesto in cui compare il nome",
      "battaglione": "battaglione/gruppo se citato, altrimenti null",
      "evento": "evento storico citato (es. 'Caporetto', 'Monte Grappa') se presente, altrimenti null",
      "decorazione": "decorazione o onorificanza citata se presente, altrimenti null",
      "data_decesso": "data di decesso se citata, altrimenti null",
      "prigionia": "luogo/periodo di prigionia se citato, altrimenti null",
      "ferita": "descrizione ferita/ricovero se citato, altrimenti null"
    }
  ]
}

Regole:
1. Estrai in "menzioni" SOLO nomi di persone reali chiaramente identificabili (cognome presente).
2. Se la pagina non contiene nomi di persone, restituisci "menzioni": [].
3. Non inventare dati: usa null quando l'informazione non c'e'.
4. Correggi ovvi errori OCR nei nomi propri quando evidente.
5. Restituisci SOLO il JSON, nessun altro testo.
6. I campi extra (battaglione, evento, decorazione, data_decesso, prigionia, ferita) sono opzionali:
   includili solo se l'informazione e' presente nella pagina. Se un campo non compare mai, usa null.
7. Se rilevi altri pattern ricorrenti non previsti (es. "missione", "promozione", "trasferimento"),
   aggiungili come campo aggiuntivo nella menzione con il valore trovato.
"""


def _parse_fondo_page(text: str, file_pdf: str, page_num: int) -> dict:
    client = _get_client()
    response = client.chat.completions.create(
        model=PARSE_MODEL_MINI,
        messages=[
            {"role": "system", "content": FONDI_PROMPT},
            {"role": "user", "content": f"Documento: {file_pdf} - Pagina {page_num}.\n\nTesto:\n\n{text[:12000]}"},
        ],
        max_tokens=4096,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    if hasattr(response, "usage") and response.usage:
        log_openai_usage(PARSE_MODEL_MINI, response.usage.prompt_tokens or 0,
                         response.usage.completion_tokens or 0, lettera=f"FONDO:{file_pdf}", pagina=page_num)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _codice_fondo(file_pdf: str) -> str:
    m = re.match(r"([A-Z]{1,3}[-_]?\d{0,3})", file_pdf)
    return m.group(1).replace("_", "-") if m else file_pdf.split(".")[0][:12]


def _page_text(pdf_doc, pdf: Path, i: int, engine: str) -> str:
    text = ""
    try:
        text = pdf_doc.pages[i].extract_text() or ""
    except Exception:
        text = ""
    if len(text.strip()) < 40 and engine != "text":
        try:
            text = _mistral_ocr_page(pdf, i, letter=f"FONDO:{pdf.name}")
        except Exception:
            pass
    return text


def extract_fondo(url: str, resume: bool = True, engine: str = "auto",
                  parallel: int = 2, max_pages: int = None) -> dict:
    dest = download_pdf(url)
    file_pdf = dest.name
    codice = _codice_fondo(file_pdf)
    pkey = f"FONDO:{file_pdf}"

    pdf_doc = pdfplumber.open(str(dest))
    total = len(pdf_doc.pages)
    if max_pages:
        total = min(total, max_pages)
    init_progress(pkey, total)

    start = 0
    if resume:
        prog = get_progress(pkey)
        if prog and prog.get("processed_pages", 0) > 0:
            start = prog["processed_pages"]

    def process(i: int):
        if is_fondo_page_processed(file_pdf, i + 1):
            return i, 0
        text = _page_text(pdf_doc, dest, i, engine)
        if len(text.strip()) < 20:
            return i, 0
        parsed = _parse_fondo_page(text, file_pdf, i + 1)
        titolo = parsed.get("descrizione") or codice
        fid = save_fondo(codice, titolo, file_pdf, url, i + 1, parsed, text[:2000])
        n = 0
        for m in parsed.get("menzioni", []) or []:
            if not m.get("cognome"):
                continue
            m["tipo"] = "persona"
            save_menzione(fid, file_pdf, i + 1, m)
            n += 1
        return i, n

    indices = list(range(start, total))
    total_menzioni = 0
    if parallel <= 1:
        for i in indices:
            if stop_event.is_set():
                update_progress(pkey, i, status="stopped")
                break
            _i, n = process(i)
            total_menzioni += n
            update_progress(pkey, i + 1)
    else:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            for bstart in range(0, len(indices), parallel):
                if stop_event.is_set():
                    break
                batch = indices[bstart:bstart + parallel]
                futs = {ex.submit(process, i): i for i in batch}
                for fut in as_completed(futs):
                    if stop_event.is_set():
                        break
                    try:
                        _i, n = fut.result()
                        total_menzioni += n
                        update_progress(pkey, _i + 1)
                    except Exception as e:
                        print(f"    [ERROR] {file_pdf} pag {futs[fut]+1}: {e}")

    pdf_doc.close()
    if not stop_event.is_set():
        finish_progress(pkey)
        print(f"  [{file_pdf}] Completato: {total} pagine, {total_menzioni} menzioni")
    return {"file": file_pdf, "pages": total, "menzioni": total_menzioni}


def extract_all(resume: bool = True, engine: str = "auto", parallel: int = 2):
    urls = list_pdf_urls()
    for u in urls:
        if stop_event.is_set():
            break
        try:
            extract_fondo(u, resume=resume, engine=engine, parallel=parallel)
        except Exception as e:
            print(f"Errore fondo {u}: {e}")
