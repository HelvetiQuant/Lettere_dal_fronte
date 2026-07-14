"""Pipeline di indicizzazione massiva con AI parallele.

Ogni AI ha un compito specifico e lavora su un sottoinsieme distinto:

  OpenAI    → soldati A-F  (ricerca + arricchimento biografia)
  Anthropic → soldati G-L  (ricerca + estrazione entità)
  Gemini    → soldati M-R  (ricerca + linking fonti)
  Mistral   → soldati S-Z  (ricerca + validazione)
  Perplexity→ eventi/battaglie (ha accesso web live)
  LM Studio → reparti/unità militari (locale, no rate limit)
  Scraper   → luoghi/lager (puro scraping, no AI)

Ogni AI:
  1. Legge il proprio batch di soldati dal DB
  2. Per ogni soldato: costruisce query cognome+nome
  3. Chiede all'AI di arricchire la ricerca (sinonimi, grafia tedesca, ID Arolsen)
  4. Esegue federated_search con query arricchita
  5. Salva metadati in fonti_indice + collegamenti

Avvio: python mass_index_parallel.py [--mode all|soldati|eventi|reparti|luoghi]
"""

import argparse
import logging
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from database import get_conn
from source_providers.federation import federated_search
from mass_index import (
    _upsert_fonte, _add_collegamento,
    _is_search_page_url, _is_direct_record_url, _matches_entity,
    pipeline_reparti, pipeline_luoghi,
    MIN_SCORE, MAX_PER_QUERY, BATCH_SLEEP,
)

LOG_FILE = Path(__file__).parent / "mass_index_parallel.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ─── Contatori globali thread-safe ────────────────────────────────────────────

_lock   = threading.Lock()
_stats  = {"saved": 0, "done": 0, "errors": 0}

def _inc(saved=0, done=0, error=False):
    with _lock:
        _stats["saved"]  += saved
        _stats["done"]   += done
        _stats["errors"] += 1 if error else 0


# ─── Client AI per arricchimento query ───────────────────────────────────────

def _enrich_openai(cognome: str, nome: str) -> list[str]:
    """Restituisce varianti del nome per ricerca (grafia tedesca, ID noti, ecc.)"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{
                "role": "user",
                "content": (
                    f"Sei un ricercatore di archivi militari WW2. Il soldato è: {cognome} {nome} (italiano, IMI 1943-1945).\n"
                    f"Restituisci SOLO una lista JSON di max 4 varianti del nome utili per ricerche su archivi tedeschi/internazionali.\n"
                    f"Includi: grafia tedesca (es. ROSSI→ROSSI, nomi composti separati), "
                    f"possibili errori di trascrizione, forma cognome-nome invertita.\n"
                    f"Formato: [\"COGNOME NOME\", \"variante2\", ...]. Solo JSON, nessun testo extra."
                ),
            }],
            max_tokens=100, temperature=0.1,
        )
        import json
        text = r.choices[0].message.content.strip()
        variants = json.loads(text)
        return [v for v in variants if isinstance(v, str) and len(v) > 3][:4]
    except Exception as e:
        logging.getLogger("openai").debug("enrich error: %s", e)
        return []


def _enrich_anthropic(cognome: str, nome: str) -> list[str]:
    try:
        import anthropic, json
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": (
                    f"Soldato italiano IMI: {cognome} {nome}. "
                    f"Lista JSON max 4 varianti nome per archivi tedeschi/internazionali. "
                    f"Solo JSON array di stringhe."
                ),
            }],
        )
        return json.loads(msg.content[0].text.strip())[:4]
    except Exception:
        return []


def _enrich_gemini(cognome: str, nome: str) -> list[str]:
    try:
        import google.generativeai as genai, json
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"))
        resp = model.generate_content(
            f"Soldato italiano IMI WW2: {cognome} {nome}. "
            f"Restituisci SOLO JSON array max 4 varianti nome per archivi tedeschi. "
            f"Es: [\"COGNOME NOME\", \"variante\"]. Solo JSON."
        )
        return json.loads(resp.text.strip())[:4]
    except Exception:
        return []


def _enrich_mistral(cognome: str, nome: str) -> list[str]:
    try:
        from mistralai import Mistral
        import json
        client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
        resp = client.chat.complete(
            model="mistral-small-latest",
            messages=[{
                "role": "user",
                "content": (
                    f"IMI soldier: {cognome} {nome}. "
                    f"JSON array max 4 name variants for German/international archives. Only JSON."
                ),
            }],
            max_tokens=80,
        )
        return json.loads(resp.choices[0].message.content.strip())[:4]
    except Exception:
        return []


_lmstudio_available: bool | None = None  # None = non ancora testato


def _call_lmstudio(messages: list, max_tokens: int = 100) -> str:
    """Chiama LM Studio Qwen2.5-3B-Instruct. Se non disponibile ritorna '' silenziosamente."""
    global _lmstudio_available
    if _lmstudio_available is False:
        return ""  # già verificato offline, skip immediato
    import requests
    base_url = os.environ.get("LM_STUDIO_API_URL", "http://127.0.0.1:1234/v1")
    key      = os.environ.get("LM_STUDIO_API_KEY", "")
    model    = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-3b-instruct")
    payload  = {"model": model, "messages": messages,
                "max_tokens": max_tokens, "temperature": 0.1}
    headers_list = []
    if key:
        headers_list.append({"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    headers_list.append({"Content-Type": "application/json"})
    for headers in headers_list:
        try:
            resp = requests.post(f"{base_url}/chat/completions",
                                 headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                _lmstudio_available = True
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            continue
    _lmstudio_available = False
    logging.getLogger("lmstudio").debug("LM Studio non disponibile — skip")
    return ""


def _enrich_lmstudio(cognome: str, nome: str) -> list[str]:
    """LM Studio locale Qwen2.5-3B-Instruct — nessun rate limit, usato per reparti."""
    import re, json
    try:
        content = _call_lmstudio([
            {"role": "system", "content": "Rispondi SOLO con un JSON array. Nessun testo aggiuntivo."},
            {"role": "user", "content": (
                f"Unità militare italiana WW2: {cognome} {nome}. "
                f"JSON array max 3 varianti nome per archivi tedeschi/italiani/inglesi. "
                f"Es: [\"17 Divisione Pavia\",\"17. Division Pavia\"]. Solo JSON."
            )},
        ])
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            return json.loads(match.group())[:3]
    except Exception:
        pass
    return []


def _enrich_perplexity(query: str) -> str:
    """Perplexity con accesso web — restituisce contesto storico per eventi."""
    try:
        import requests
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.environ.get("PERPLEXITY_MODEL", "llama-3.1-sonar-small-128k-online"),
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Ricerca storica WW2: {query}\n"
                        f"Trova URL diretti a documenti/fonti primarie su archivi online "
                        f"(Arolsen, NARA, Bundesarchiv, TNA, Europeana, IA). "
                        f"Rispondi con lista JSON: [{{\"titolo\":\"...\",\"url\":\"...\",\"archivio\":\"...\"}}]. "
                        f"Solo URL verificabili, no Wikipedia."
                    ),
                }],
                "max_tokens": 500,
                "return_citations": True,
            },
            timeout=30,
        )
        import json
        content = resp.json()["choices"][0]["message"]["content"]
        # Estrai JSON dalla risposta
        import re
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            items = json.loads(match.group())
            return items
        return []
    except Exception as e:
        logging.getLogger("perplexity").debug("error: %s", e)
        return []


# ─── Pipeline soldati per singola AI ─────────────────────────────────────────

SOLDATI_PROVIDERS = [
    "arolsen", "bundesarchiv", "nara", "cwgc", "europeana",
    "internet_archive", "hathitrust", "gallica", "tna", "awm",
    "antenati", "wikitree",
]


def _process_soldier(row: dict, enrich_fn) -> int:
    """Processa un singolo soldato: arricchisce query con AI, cerca, salva."""
    log = logging.getLogger(f"soldier.{row['id']}")
    cognome = (row["cognome"] or "").strip().upper()
    nome    = (row["nome"]    or "").strip()
    if len(cognome) < 2:
        return 0

    base_query = f"{cognome} {nome}".strip()
    queries    = [base_query]

    # Arricchimento AI — varianti nome
    try:
        variants = enrich_fn(cognome, nome)
        for v in variants:
            if v and v != base_query and v not in queries:
                queries.append(v)
    except Exception:
        pass

    saved = 0
    cues  = {"persona": base_query, "cognome": cognome, "nome": nome,
             "nazione": "Italia", "periodo": "1943-1945"}

    for q in queries[:4]:
        try:
            results = federated_search(q, cues=cues,
                                       providers=SOLDATI_PROVIDERS,
                                       filters={"page_size": 15})
        except Exception as e:
            log.debug("search error: %s", e)
            continue

        for r in results:
            if r.get("error") or r.get("score", 0) < MIN_SCORE:
                continue
            url = r.get("direct_url") or r.get("catalog_url") or ""
            if not url or _is_search_page_url(url):
                continue
            meta = {
                "archivio":    r.get("archivio") or r.get("provider", ""),
                "segnatura":   r.get("provider_record_id") or "",
                "titolo":      (r.get("titolo") or q)[:200],
                "tipo_fonte":  r.get("source_type") or "",
                "url_catalogo": url,
                "url_file":    r.get("direct_url") or "",
                "access_type": r.get("access_type") or "online",
                "confidence":  round(r.get("score", 0.5), 3),
                "note":        (r.get("description") or "")[:400],
            }
            if not _matches_entity(meta, cues):
                continue
            try:
                fid = _upsert_fonte(meta)
                _add_collegamento("internati", row["id"], fid)
                saved += 1
            except Exception:
                pass
            if saved >= MAX_PER_QUERY:
                break

    return saved


def _run_soldati_batch(letter_from: str, letter_to: str,
                       enrich_fn, ai_name: str, limit: int = None):
    """Processa soldati dalla lettera X alla Y con la AI specificata."""
    log = logging.getLogger(ai_name)
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    where = "cognome >= ? AND cognome <= ? AND cognome IS NOT NULL AND cognome != ''"
    params = [letter_from.upper(), letter_to.upper() + "ZZZ"]
    q = f"SELECT id, cognome, nome FROM internati WHERE {where} ORDER BY cognome, nome"
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q, params).fetchall()
    conn.close()

    log.info("AI=%s batch %s-%s: %d soldati", ai_name, letter_from, letter_to, len(rows))
    total_saved = 0
    done = 0

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_process_soldier, row, enrich_fn): row for row in rows}
        for fut in as_completed(futures):
            done += 1
            try:
                n = fut.result()
                total_saved += n
                _inc(saved=n, done=1)
            except Exception as e:
                log.warning("error: %s", e)
                _inc(error=True)
            if done % 50 == 0:
                log.info("AI=%s %d/%d — fonti: %d", ai_name, done, len(rows), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("AI=%s DONE: %d soldati, %d fonti", ai_name, done, total_saved)
    return total_saved


# ─── Pipeline eventi con Perplexity ──────────────────────────────────────────

EVENTI_STORICI = [
    "Armistizio 8 settembre 1943 Italia",
    "Operazione Achse 1943 prigionieri italiani",
    "Battaglia di Cassino 1944",
    "Sbarco in Sicilia Operazione Husky 1943",
    "Battaglia di Anzio 1944",
    "Eccidio di Cefalonia Divisione Acqui 1943",
    "ARMIR campagna di Russia 1942 1943",
    "Battaglia di Stalingrado italiani CSIR",
    "Resistenza italiana 1943 1945 partigiani",
    "IMI internati militari italiani Germania lager",
    "Divisione Julia fronte russo 1943",
    "Lager Mauthausen italiani deportati",
    "Liberazione di Roma 4 giugno 1944",
    "Campagna d'Africa Rommel italiani 1942",
    "Battaglia del Don italiani inverno 1942",
    "Campo di concentramento Dachau italiani",
    "Stalag XVII-B Krems internati italiani",
    "Battaglia di El Alamein seconda 1942",
    "8 settembre 1943 dispersione esercito italiano",
    "Rifiuto di collaborare IMI Badoglio 1943",
]


def pipeline_eventi_perplexity() -> int:
    """Usa Perplexity (web access) per trovare fonti primarie su eventi storici."""
    log = logging.getLogger("perplexity.eventi")
    log.info("=== PIPELINE EVENTI via Perplexity ===")
    total_saved = 0
    now = datetime.now().isoformat(timespec="seconds")

    for evento in EVENTI_STORICI:
        log.info("Evento: %s", evento)
        try:
            items = _enrich_perplexity(evento)
            for item in (items or []):
                if not isinstance(item, dict):
                    continue
                url = item.get("url") or ""
                if not url or not url.startswith("http"):
                    continue
                meta = {
                    "archivio":    item.get("archivio") or "Web",
                    "segnatura":   "",
                    "titolo":      (item.get("titolo") or evento)[:200],
                    "tipo_fonte":  "evento_storico",
                    "url_catalogo": url,
                    "url_file":    "",
                    "access_type": "online",
                    "confidence":  0.7,
                    "note":        evento[:300],
                }
                try:
                    _upsert_fonte(meta)
                    total_saved += 1
                except Exception:
                    pass
        except Exception as e:
            log.warning("Perplexity error su '%s': %s", evento, e)
        time.sleep(1.5)  # rispetta rate limit Perplexity

    log.info("EVENTI Perplexity DONE: %d fonti", total_saved)
    return total_saved


# ─── Orchestratore principale ─────────────────────────────────────────────────

def run_all_parallel(limit_per_ai: int = None):
    """Lancia tutte le AI in parallelo su batch distinti."""
    log = logging.getLogger("orchestrator")
    log.info("=== AVVIO PIPELINE PARALLELA CON %d AI ===", 7)
    start = time.time()

    # Mappa AI → batch lettere → funzione di arricchimento
    ai_batches = [
        ("OpenAI",    "A", "F", _enrich_openai),
        ("Anthropic", "G", "L", _enrich_anthropic),
        ("Gemini",    "M", "R", _enrich_gemini),
        ("Mistral",   "S", "Z", _enrich_mistral),
    ]

    threads = []

    # Thread soldati per ogni AI
    for ai_name, lf, lt, fn in ai_batches:
        t = threading.Thread(
            target=_run_soldati_batch,
            args=(lf, lt, fn, ai_name, limit_per_ai),
            daemon=True,
            name=f"ai_{ai_name}",
        )
        threads.append(t)

    # Thread eventi con Perplexity
    t_eventi = threading.Thread(
        target=pipeline_eventi_perplexity,
        daemon=True, name="perplexity_eventi",
    )
    threads.append(t_eventi)

    # Thread reparti — LM Studio opzionale, pipeline gira sempre
    def _reparti_worker():
        if _lmstudio_available is not False:
            log.info("Reparti: verifica LM Studio...")
            _call_lmstudio([{"role": "user", "content": "ping"}], max_tokens=5)
        if _lmstudio_available:
            log.info("Reparti: LM Studio online — arricchimento attivo")
        else:
            log.info("Reparti: LM Studio offline — pipeline standard")
        pipeline_reparti()

    t_reparti = threading.Thread(
        target=_reparti_worker,
        daemon=True, name="reparti_worker",
    )
    threads.append(t_reparti)

    # Thread luoghi (puro scraping, nessuna AI)
    t_luoghi = threading.Thread(
        target=pipeline_luoghi,
        daemon=True, name="scraper_luoghi",
    )
    threads.append(t_luoghi)

    # Avvia tutti
    for t in threads:
        t.start()
        log.info("Avviato thread: %s", t.name)

    # Monitor progressi ogni 30s
    while any(t.is_alive() for t in threads):
        time.sleep(30)
        with _lock:
            log.info(
                "PROGRESS — done: %d | saved: %d | errors: %d | threads attivi: %d",
                _stats["done"], _stats["saved"], _stats["errors"],
                sum(1 for t in threads if t.is_alive()),
            )

    for t in threads:
        t.join(timeout=5)

    elapsed = time.time() - start
    log.info(
        "=== PIPELINE COMPLETA in %.0fs — saved: %d | done: %d | errors: %d ===",
        elapsed, _stats["saved"], _stats["done"], _stats["errors"],
    )

    # Stats finali
    from mass_index import print_stats
    print_stats()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all","soldati","eventi","reparti","luoghi"],
                        default="all")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max soldati PER AI (default: tutti)")
    args = parser.parse_args()

    if args.mode == "all":
        run_all_parallel(limit_per_ai=args.limit)
    elif args.mode == "soldati":
        threads = []
        ai_batches = [
            ("OpenAI",    "A", "F", _enrich_openai),
            ("Anthropic", "G", "L", _enrich_anthropic),
            ("Gemini",    "M", "R", _enrich_gemini),
            ("Mistral",   "S", "Z", _enrich_mistral),
        ]
        for ai_name, lf, lt, fn in ai_batches:
            t = threading.Thread(target=_run_soldati_batch,
                                 args=(lf, lt, fn, ai_name, args.limit),
                                 daemon=True, name=f"ai_{ai_name}")
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    elif args.mode == "eventi":
        pipeline_eventi_perplexity()
    elif args.mode == "reparti":
        pipeline_reparti()
    elif args.mode == "luoghi":
        pipeline_luoghi()
