"""Modulo per ricerche AI-assisted sui dataset IMI.
Tre provider: OpenAI GPT, Mistral, Perplexity.
Ognuno interroga il DB locale, riceve i dati come contesto, e produce un'analisi."""
import json
import os
from pathlib import Path
from typing import Optional

import requests

from database import get_all_records_for_ai, save_ai_ricerca, get_conn
from credits import log_openai_usage, log_mistral_ocr
from extractor import _load_env, _get_client, _get_mistral_client, PARSE_MODEL_MINI

try:
    import anthropic
except ImportError:
    anthropic = None


# ─── Provider config ───

PROVIDERS = {
    "gpt": {"label": "OpenAI GPT-4o-mini", "model": "gpt-4o-mini"},
    "mistral": {"label": "Mistral Large", "model": "mistral-large-latest"},
    "perplexity": {"label": "Perplexity Sonar", "model": "sonar"},
    "claude": {"label": "Anthropic Claude Sonnet", "model": "claude-sonnet-4-5-20250929"},
}

RESEARCH_PROMPT = """Sei un ricercatore storico specializzato negli Internati Militari Italiani (IMI)
della Seconda Guerra Mondiale e nei decorati/caduti dei conflitti del '900.

Analizza i dati estratti dai seguenti dataset archivistici:
1. INTERNATI: elenchi dall'Archivio di Stato di Bolzano (IMI)
2. DECORATI: Albi della Memoria ISTORECO Reggio Emilia
3. MENZIONI: persone/luoghi estratti dai fondi dell'Ufficio Storico SME
4. FONDI ARCHIVISTICI: inventari e carteggi militari
5. ENTITA: entita' estratte e collegate cross-dataset

Dati forniti dal database locale per la query dell'utante:
{context}

Query dell'utente: "{query}"

Istruzioni:
1. Analizza tutti i record trovati nei vari dataset
2. Identifica collegamenti tra persone, luoghi, date ed eventi
3. Fornisci un'analisi strutturata con:
   - SINTESI: riassunto dei ritrovamenti
   - PERSONE: elenco persone trovate con dettagli (chi, dove, quando)
   - LUOGHI: luoghi menzionati e loro significato
   - EVENTI: eventi collegati (cattura, internamento, decorazione, morte)
   - FONTI: da quale dataset proviene ogni informazione
   - COLLEGAMENTI: possibili collegamenti cross-dataset (stessa persona in dataset diversi?)
   - APPROFONDIMENTI: suggerimenti per ricerche ulteriori
4. Se i dati sono insufficienti, indica quali fonti consultare
5. Cita sempre il dataset di origine (es. [INTERNATI], [DECORATI], [MENZIONI])
6. Non inventare dati: usa solo quelli forniti dal DB
"""


def _load_perplexity_key() -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if key:
        return key
    env = _load_env()
    if "PERPLEXITY_API_KEY" in env:
        return env["PERPLEXITY_API_KEY"]
    raise RuntimeError("PERPLEXITY_API_KEY non trovata")


def _load_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    env = _load_env()
    if "ANTHROPIC_API_KEY" in env:
        return env["ANTHROPIC_API_KEY"]
    raise RuntimeError("ANTHROPIC_API_KEY non trovata")


def _extract_search_terms(query: str) -> list[str]:
    """Estrae termini di ricerca significativi da una query in linguaggio naturale.
    Identifica anni, nomi propri, luoghi e parole chiave."""
    import re
    terms = []
    # Estrai anni (4 cifre 1900-2099)
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", query)
    terms.extend(years)
    # Rimuovi parole vuote italiane e token troppo corti
    stopwords = {"soldati", "soldato", "decorati", "decorato", "deceduti", "deceduto",
                 "nel", "nel", "morti", "morto", "caduti", "caduto", "guerra",
                 "internati", "internato", "militari", "militare", "italiani",
                 "italiano", "del", "della", "dei", "di", "da", "in", "per",
                 "con", "su", "tra", "fra", "e", "o", "che", "non", "sono",
                 "stato", "stata", "stati", "state", "trovati", "trovato",
                 "ricerca", "cerca", "cerco", "voglio", "vorrei", "mostra",
                 "elenco", "lista", "tutti", "tutte", "ogni", "qualsiasi"}
    # Tokenizza: prendi parole di 3+ caratteri che non sono stopwords
    tokens = re.findall(r"[A-Za-zÀ-ÿ]{3,}", query)
    for t in tokens:
        tl = t.lower()
        if tl not in stopwords and tl not in [x.lower() for x in terms]:
            terms.append(t)
    return terms if terms else [query]


def _prepare_context(term: str, limit: int = 20) -> str:
    """Recupera dati dal DB e li formatta come contesto per l'AI.
    Usa search_all/get_all_records_for_ai (tokenizzata, cross-DB)."""
    data = get_all_records_for_ai(term, limit_per_table=limit)
    parts = []
    if data["internati"]:
        parts.append("=== INTERNATI (Archivio di Stato di Bolzano) ===")
        for r in data["internati"]:
            parts.append(
                f"  ID:{r['id']} | {r['cognome']} {r['nome'] or ''} | "
                f"nato: {r['luogo_nascita'] or '?'} {r['data_nascita'] or ''} | "
                f"residenza: {r['residenza'] or '?'} | grado: {r['grado'] or '?'} | "
                f"internamento: {r['luogo_internamento'] or '?'} | sorte: {r['sorte'] or '?'} | "
                f"lettera: {r['lettera']} pag.{r['pagina']}"
            )
    if data["decorati"]:
        parts.append("\n=== DECORATI (Albi della Memoria ISTORECO + Nastro Azzurro) ===")
        for r in data["decorati"]:
            parts.append(
                f"  ID:{r['id']} | {r.get('cognome', '?')} {r.get('nome', '')} | "
                f"nato: {r.get('comune_nascita') or '?'} | grado: {r.get('grado', '?')} | "
                f"corpo: {r.get('corpo_militare', r.get('arma', '?'))} | reparto: {r.get('reparto', '?')} | "
                f"decorazione: {r.get('decorazione', r.get('tipo_decorazione', '?'))} | "
                f"fonte: {r.get('source', 'ISTORECO')} | "
                f"morte: {r.get('luogo_morte') or '?'} {r.get('data_morte') or r.get('anno_morte', '')}"
            )
    if data["menzioni"]:
        parts.append("\n=== MENZIONI (Fondi Ufficio Storico SME) ===")
        for r in data["menzioni"]:
            parts.append(
                f"  ID:{r['id']} | {r['cognome']} {r['nome'] or ''} | "
                f"grado: {r['grado'] or '?'} | reparto: {r['reparto'] or '?'} | "
                f"luogo: {r['luogo'] or '?'} | data: {r['data'] or '?'} | "
                f"contesto: {r['contesto'] or '?'} | fondo: {r['codice_fondo'] or '?' }"
            )
    if data["caduti"]:
        parts.append("\n=== CADUTI EREDI (varie fonti) ===")
        for r in data["caduti"][:limit]:
            label = r.get("_source_label", "caduti")
            nome = r.get("cognome") or r.get("nome") or r.get("nominativo") or r.get("nom") or "?"
            secondo = r.get("nome") if r.get("cognome") else r.get("paternita", "")
            parts.append(
                f"  ID:{r['id']} | {label} | {nome} {secondo} | "
                f"grado: {r.get('grado', r.get('rank', r.get('grade', '?')))} | "
                f"morte: {r.get('luogo_morte', r.get('lieu_deces', r.get('data_morte', '?')))}"
            )
    if data["fondi_archivistici"]:
        parts.append("\n=== FONDI ARCHIVISTICI ===")
        for r in data["fondi_archivistici"]:
            parts.append(
                f"  ID:{r['id']} | {r['codice_fondo'] or '?'} | {r['titolo'] or '?'} | "
                f"periodo: {r['periodo'] or '?'} | luoghi: {r['luoghi'] or '?' }"
            )
    if data["entita"]:
        parts.append("\n=== ENTITA COLLEGATE ===")
        for r in data["entita"]:
            parts.append(
                f"  ID:{r['id']} | tipo: {r['tipo']} | valore: {r['valore']} | "
                f"collegamenti: {r['num_collegamenti']}"
            )
    if data["documenti"]:
        parts.append("\n=== DOCUMENTI NARA ===")
        for r in data["documenti"][:limit]:
            parts.append(f"  {r.get('source', '?')} | {r.get('title', '?')} | {r.get('date', '')}")
    if not parts:
        return "Nessun dato trovato nel database per questo termine."
    return "\n".join(parts)


# ─── Provider: OpenAI GPT ───

def research_with_gpt(query: str, limit: int = 20) -> dict:
    """Ricerca AI usando OpenAI GPT-4o-mini sui dati del DB locale."""
    context = _prepare_context(query, limit)
    client = _get_client()
    model = PROVIDERS["gpt"]["model"]
    prompt = RESEARCH_PROMPT.format(context=context, query=query)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Sei un ricercatore storico esperto di IMI e decorati italiani."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.3,
    )
    risposta = response.choices[0].message.content.strip()
    cost = 0.0
    if hasattr(response, "usage") and response.usage:
        log_openai_usage(model, response.usage.prompt_tokens or 0,
                         response.usage.completion_tokens or 0, lettera="AI_RESEARCH")
        pricing_in = 0.15 / 1_000_000
        pricing_out = 0.60 / 1_000_000
        cost = (response.usage.prompt_tokens or 0) * pricing_in + (response.usage.completion_tokens or 0) * pricing_out
    rid = save_ai_ricerca(query, "gpt", model, risposta, context[:5000], cost)
    return {"id": rid, "provider": "gpt", "model": model, "risposta": risposta, "cost_usd": cost}


# ─── Provider: Mistral ───

def research_with_mistral(query: str, limit: int = 20) -> dict:
    """Ricerca AI usando Mistral Large sui dati del DB locale."""
    context = _prepare_context(query, limit)
    client = _get_mistral_client()
    model = PROVIDERS["mistral"]["model"]
    prompt = RESEARCH_PROMPT.format(context=context, query=query)
    response = client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": "Sei un ricercatore storico esperto di IMI e decorati italiani."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.3,
    )
    risposta = response.choices[0].message.content.strip()
    # Stima costi Mistral (input ~2€/M, output ~6€/M per mistral-large)
    approx_in = len(prompt) // 4
    approx_out = len(risposta) // 4
    cost = approx_in * (2.0 / 1_000_000) + approx_out * (6.0 / 1_000_000)
    log_mistral_ocr(0, lettera="AI_RESEARCH")
    rid = save_ai_ricerca(query, "mistral", model, risposta, context[:5000], cost)
    return {"id": rid, "provider": "mistral", "model": model, "risposta": risposta, "cost_usd": cost}


# ─── Provider: Perplexity ───

def research_with_perplexity(query: str, limit: int = 20) -> dict:
    """Ricerca AI usando Perplexity Sonar sui dati del DB locale.
    Perplexity puo' anche cercare sul web per arricchire le risposte."""
    context = _prepare_context(query, limit)
    api_key = _load_perplexity_key()
    model = PROVIDERS["perplexity"]["model"]
    prompt = RESEARCH_PROMPT.format(context=context, query=query)
    resp = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Sei un ricercatore storico esperto di IMI e decorati italiani."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 4096,
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    risposta = data["choices"][0]["message"]["content"].strip()
    # Perplexity Sonar: ~1€/M input, ~1€/M output
    usage = data.get("usage", {})
    in_tok = usage.get("prompt_tokens", 0)
    out_tok = usage.get("completion_tokens", 0)
    cost = in_tok * (1.0 / 1_000_000) + out_tok * (1.0 / 1_000_000)
    # Log come openai per tracking costi
    log_openai_usage(model, in_tok, out_tok, lettera="AI_RESEARCH")
    rid = save_ai_ricerca(query, "perplexity", model, risposta, context[:5000], cost)
    return {"id": rid, "provider": "perplexity", "model": model, "risposta": risposta, "cost_usd": cost}


# ─── Provider: Anthropic Claude ───

def research_with_claude(query: str, limit: int = 20) -> dict:
    """Ricerca AI usando Anthropic Claude Sonnet sui dati del DB locale."""
    if anthropic is None:
        raise RuntimeError("Anthropic SDK non installato. Esegui: pip install anthropic")
    context = _prepare_context(query, limit)
    api_key = _load_anthropic_key()
    model = PROVIDERS["claude"]["model"]
    prompt = RESEARCH_PROMPT.format(context=context, query=query)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system="Sei un ricercatore storico esperto di IMI e decorati italiani.",
        messages=[
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    risposta = response.content[0].text.strip()
    # Claude Sonnet pricing: ~$3/M input, ~$15/M output
    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens
    cost = in_tok * (3.0 / 1_000_000) + out_tok * (15.0 / 1_000_000)
    log_openai_usage(model, in_tok, out_tok, lettera="AI_RESEARCH")
    rid = save_ai_ricerca(query, "claude", model, risposta, context[:5000], cost)
    return {"id": rid, "provider": "claude", "model": model, "risposta": risposta, "cost_usd": cost}


# ─── Dispatch ───

def research(query: str, provider: str = "gpt", limit: int = 20) -> dict:
    """Esegue ricerca AI con il provider specificato."""
    if provider == "gpt":
        return research_with_gpt(query, limit)
    elif provider == "mistral":
        return research_with_mistral(query, limit)
    elif provider == "perplexity":
        return research_with_perplexity(query, limit)
    elif provider == "claude":
        return research_with_claude(query, limit)
    else:
        raise ValueError(f"Provider non supportato: {provider}. Usa: gpt, mistral, perplexity, claude")


def research_all(query: str, limit: int = 20) -> dict:
    """Esegue ricerca con tutti i provider e restituisce i risultati comparati."""
    results = {}
    for p in ("gpt", "mistral", "perplexity", "claude"):
        try:
            results[p] = research(query, provider=p, limit=limit)
        except Exception as e:
            results[p] = {"provider": p, "error": str(e), "risposta": None}
    return results
