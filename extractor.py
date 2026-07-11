import base64
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pdfplumber
import fitz

import threading
from openai import OpenAI
from PIL import Image

from config import COLUMNS
from database import (
    save_internato, init_progress, update_progress, finish_progress,
    is_page_processed, get_progress,
)
from downloader import pdf_path, is_downloaded
from geocoder import validate_record_locations
from credits import log_openai_usage, log_mistral_ocr, init_usage_table

stop_event = threading.Event()
_last_completed_letter = None


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def is_stop_requested():
    return stop_event.is_set()


def get_last_completed_letter() -> str | None:
    return _last_completed_letter


def clear_last_completed_letter():
    global _last_completed_letter
    _last_completed_letter = None

# ─── Token optimization strategy ───
# 1. Mistral OCR for text extraction (image→text): no LLM tokens, dedicated OCR model
# 2. GPT-4o-mini for parsing (text→JSON): 10x cheaper than GPT-4o, excellent for text parsing
# 3. GPT-4o Vision only as last-resort fallback for illegible pages
# 4. Dual mode: split pages between Mistral OCR + GPT-4o-mini and pdfplumber + GPT-4o-mini
# 5. Concurrent page processing with ThreadPoolExecutor for speed

PARSE_MODEL_MINI = "gpt-4o-mini"
PARSE_MODEL_FULL = "gpt-4o"
MAX_WORKERS = 4


def _load_env() -> dict:
    env = {}
    env_paths = [
        Path.home() / "Desktop" / "lettere dal fronte backup_2026-06-28" / ".env",
        Path.cwd() / ".env",
    ]
    for p in env_paths:
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    # Override with actual env vars
    for k in list(env.keys()):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def _load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    env = _load_env()
    if "OPENAI_API_KEY" in env:
        return env["OPENAI_API_KEY"]
    raise RuntimeError("OPENAI_API_KEY non trovata")


def _load_mistral_key() -> str:
    key = os.environ.get("MISTRAL_API_KEY", "")
    if key:
        return key
    env = _load_env()
    if "MISTRAL_API_KEY" in env:
        return env["MISTRAL_API_KEY"]
    raise RuntimeError("MISTRAL_API_KEY non trovata")


_client = None
_mistral_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=_load_api_key())
    return _client


def _get_mistral_client():
    global _mistral_client
    if _mistral_client is None:
        from mistralai.client import Mistral
        _mistral_client = Mistral(api_key=_load_mistral_key())
    return _mistral_client


PARSE_PROMPT = """Sei un esperto archivista storico specializzato negli Internati Militari Italiani (IMI) della Seconda Guerra Mondiale. 
Analizza il testo OCR di una pagina di un elenco storico scritto a macchina proveniente dall'Archivio di Stato di Bolzano.

Ogni voce nell'elenco corrisponde a un internato militare italiano e segue generalmente questo schema:
- COGNOME Nome +LuogoOrigine. Destino/sorte del soldato (morto, disperso, rimpatriato, ecc.) con dettagli.
- (Nome riferimento, indirizzo) F.numero  <- riga di documentazione/riferimento

Estrai OGNI persona menzionata nella pagina e restituisci un array JSON. Per ogni persona, estrai questi campi:
- "cognome": cognome dell'internato
- "nome": nome dell'internato  
- "data_nascita": data di nascita se presente (formato YYYY-MM-DD se possibile), altrimenti null
- "luogo_nascita": luogo di nascita se distinguibile dalla residenza, altrimenti null
- "residenza": luogo di residenza o origine indicato (es. "Agrigento, Favara")
- "grado": grado militare se indicato (es. soldato, sergente, capitano), altrimenti null
- "luogo_cattura": luogo di cattura se menzionato, altrimenti null
- "data_cattura": data di cattura se menzionata, altrimenti null
- "luogo_internamento": campo/lager/luogo di internamento menzionato (es. Brandenburg, Kiel, Flossenburg)
- "matricola": numero di matricola se presente, altrimenti null
- "arbeitskommando": comando di lavoro se menzionato, altrimenti null
- "mansione": mansione svolta dal internato se menzionata, altrimenti null
- "sorte": sorte del soldato - una di: "deceduto", "disperso", "rimpatriato", "altro" (deduci dal contesto: "Morto"=deceduto, "disperso"=disperso, "rimpatrio"=rimpatriato)
- "data": data dell'evento (morte, scomparsa, rimpatrio) se menzionata, in formato testo originale
- "documenti": riferimento documentale tra parentesi (es. "Sonteno Romano, Siracusa, via Brenerta 19. F.9")
- "needs_review": true se alcuni dati sono illeggibili/incompleti/incerti e richiedono verifica manuale, false altrimenti
- "review_reason": motivo per cui serve revisione manuale (es. "cognome parzialmente illeggibile", "luogo di nascita incerto", "data non chiara"). Vuoto se needs_review e' false.

Regole:
1. Restituisci ESCLUSIVAMENTE un array JSON valido, nessun testo fuori dal JSON
2. Se una persona non ha un cognome chiaro MA ci sono altri dati leggibili (nome, luogo, sorte), includi la voce con needs_review=true e review_reason="cognome parzialmente illeggibile"
3. Se il testo e' completamente illeggibile o non contiene dati di internati, restituisci array vuoto []
4. Correggi ovvi errori OCR quando possibile (es. "Agrigenta" -> "Agrigento")
5. Il simbolo "+" o "†" prima del luogo indica "deceduto"
6. Le righe tra parentesi tonde sono riferimenti documentali, vanno nel campo "documenti"
7. Mantieni i nomi propri in maiuscolo se cosi appaiono nel testo
8. Se una voce ha solo il cognome leggibile e tutto il resto e' illeggibile, includila con needs_review=true e review_reason="dati parziali - solo cognome leggibile"
9. Se un luogo di nascita o morte sembra un errore OCR evidente ma non correggibile con certezza, includi il valore migliore con needs_review=true
10. NON saltare mai una voce se c'e almeno un dato leggibile - meglio inserirla con needs_review=true che perderla
"""


def _parse_text_page(text: str, letter: str, page_num: int, model: str = PARSE_MODEL_MINI) -> list[dict]:
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PARSE_PROMPT},
            {
                "role": "user",
                "content": f"Pagina {page_num} dell'elenco lettera {letter}. Testo OCR:\n\n{text}",
            },
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    if hasattr(response, 'usage') and response.usage:
        log_openai_usage(model, response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0, lettera=letter, pagina=page_num)
    return _parse_json_response(raw)


def _parse_json_response(raw: str) -> list[dict]:
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    if raw.startswith("json"):
        raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return data
    except json.JSONDecodeError:
        return []


def _render_page_image(pdf_path: Path, page_num: int, max_dim: int = 2048) -> str:
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    doc.close()
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _parse_image_page(pdf_path: Path, page_num: int, letter: str) -> list[dict]:
    client = _get_client()
    b64 = _render_page_image(pdf_path, page_num)
    response = client.chat.completions.create(
        model=PARSE_MODEL_FULL,
        messages=[
            {"role": "system", "content": PARSE_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Pagina {page_num + 1} dell'elenco lettera {letter}. Analizza l'immagine ed estrai i dati degli internati.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    if hasattr(response, 'usage') and response.usage:
        log_openai_usage(PARSE_MODEL_FULL, response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0, lettera=letter, pagina=page_num + 1)
    return _parse_json_response(raw)


def _mistral_ocr_page(pdf_path: Path, page_num: int, letter: str = None) -> str:
    client = _get_mistral_client()
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img_bytes = pix.tobytes("png")
    b64 = base64.b64encode(img_bytes).decode()
    doc.close()

    result = client.ocr.process(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
    )
    log_mistral_ocr(1, lettera=letter, pagina=page_num + 1)
    if result.pages:
        return result.pages[0].markdown or ""
    return ""


def _process_single_page(pdf_doc, pdf: Path, i: int, letter: str, engine: str, parse_model: str) -> tuple[int, list[dict], str]:
    text = ""
    if engine == "mistral":
        try:
            text = _mistral_ocr_page(pdf, i, letter=letter)
        except Exception as e:
            print(f"    [WARN] Mistral OCR fallito pag {i+1}: {e}, fallback pdfplumber")
            text = pdf_doc.pages[i].extract_text() or ""
    elif engine == "dual":
        if i % 2 == 0:
            try:
                text = _mistral_ocr_page(pdf, i, letter=letter)
            except Exception:
                text = pdf_doc.pages[i].extract_text() or ""
        else:
            text = pdf_doc.pages[i].extract_text() or ""
    else:
        text = pdf_doc.pages[i].extract_text() or ""

    if len(text.strip()) < 50:
        try:
            rows = _parse_image_page(pdf, i, letter)
        except Exception as e:
            print(f"    [WARN] Vision fallback fallito pag {i+1}: {e}")
            rows = []
    else:
        try:
            rows = _parse_text_page(text, letter, i + 1, model=parse_model)
        except Exception as e:
            print(f"    [WARN] Text parse fallito pag {i+1}: {e}")
            rows = []

    for row in rows:
        validate_record_locations(row)

    return i, rows, text[:500]


def extract_letter(letter: str, resume: bool = True, delay: float = 0.3,
                    engine: str = "openai", parallel: int = 1):
    if not is_downloaded(letter):
        raise RuntimeError(f"PDF lettera {letter} non scaricato")

    pdf = pdf_path(letter)
    pdf_doc = pdfplumber.open(str(pdf))
    total = len(pdf_doc.pages)
    init_progress(letter, total)

    start_page = 0
    if resume:
        prog = get_progress(letter)
        if prog and prog.get("processed_pages", 0) > 0:
            start_page = prog["processed_pages"]

    parse_model = PARSE_MODEL_MINI  # default: cheaper model for text parsing

    page_indices = list(range(start_page, total))

    if parallel <= 1:
        for i in page_indices:
            if stop_event.is_set():
                update_progress(letter, i, status="stopped")
                print(f"    [{letter}] Estrazione interrotta alla pagina {i + 1}")
                break
            _idx, rows, raw_snippet = _process_single_page(pdf_doc, pdf, i, letter, engine, parse_model)
            for row in rows:
                if not row.get("cognome"):
                    continue
                save_internato(letter, pdf.name, i + 1, row, raw_snippet)
            update_progress(letter, i + 1)
            print(f"    [{letter}] Pag {i+1}/{total} ({engine}): {len(rows)} internati estratti")
            if delay > 0:
                time.sleep(delay)
    else:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            batch_size = parallel
            for batch_start in range(0, len(page_indices), batch_size):
                if stop_event.is_set():
                    break
                futures = {}
                batch = page_indices[batch_start:batch_start + batch_size]
                for i in batch:
                    fut = executor.submit(_process_single_page, pdf_doc, pdf, i, letter, engine, parse_model)
                    futures[fut] = i
                for fut in as_completed(futures):
                    if stop_event.is_set():
                        break
                    i = futures[fut]
                    try:
                        _idx, rows, raw_snippet = fut.result()
                        for row in rows:
                            if not row.get("cognome"):
                                continue
                            save_internato(letter, pdf.name, i + 1, row, raw_snippet)
                        update_progress(letter, i + 1)
                        print(f"    [{letter}] Pag {i+1}/{total} ({engine}, parallel={parallel}): {len(rows)} internati estratti")
                    except Exception as e:
                        print(f"    [ERROR] Pag {i+1}: {e}")
                        update_progress(letter, i + 1)
                if delay > 0:
                    time.sleep(delay)

    global _last_completed_letter
    prog = get_progress(letter)
    if stop_event.is_set():
        if prog:
            update_progress(letter, prog.get('processed_pages', 0), status='stopped')
            print(f"  [{letter}] Interrotto a pagina {prog.get('processed_pages', 0)}")
    else:
        finish_progress(letter)
        _last_completed_letter = letter
        print(f"  [{letter}] Completato: {total} pagine processate")

    pdf_doc.close()
