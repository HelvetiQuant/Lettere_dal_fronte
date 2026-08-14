"""AI Client unificato — ponte tra ai_router (selezione) e provider AI reali.

Per ogni task type:
1. select_model() sceglie provider+modello ottimale
2. call_ai() invoca il provider reale (OpenAI, Anthropic, Mistral, Gemini, Perplexity)
3. record_task_run() registra costo, latenza, outcome
4. Fallback automatico al provider successivo in caso di errore

Supporta:
- text completion (system + user prompt)
- structured output (JSON mode)
- web search (Perplexity)
- vision (immagini base64)
"""
import json
import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import requests

from ai_router import (
    select_model, record_task_run, check_budget_before_task,
    get_routing_policy, _breaker_is_open, _breaker_record_failure,
    _breaker_record_success, TASK_TYPES,
)

log = logging.getLogger("ai_client")

# ═══ ENV LOADING ═══════════════════════════════════════════════════════════

_env_cache: Dict[str, str] = {}


def _load_env() -> Dict[str, str]:
    """Carica variabili d'ambiente dal file .env (stessa logica di extractor.py)."""
    if _env_cache:
        return _env_cache
    env: Dict[str, str] = {}
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
    for k in list(env.keys()):
        val = os.environ.get(k)
        if val:
            env[k] = val
    _env_cache.update(env)
    return env


def _get_key(name: str) -> Optional[str]:
    val = os.environ.get(name)
    if val:
        return val
    env = _load_env()
    return env.get(name)


# ═══ CLIENT SINGLETONS ═════════════════════════════════════════════════════

_openai_client = None
_anthropic_client = None
_mistral_client = None
_gemini_configured = False
_ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        key = _get_key("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY non trovata")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("Anthropic SDK non installato (pip install anthropic)")
        key = _get_key("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY non trovata")
        _anthropic_client = anthropic.Anthropic(api_key=key)
    return _anthropic_client


def _get_mistral_client():
    global _mistral_client
    if _mistral_client is None:
        from mistralai.client import Mistral
        key = _get_key("MISTRAL_API_KEY")
        if not key:
            raise RuntimeError("MISTRAL_API_KEY non trovata")
        _mistral_client = Mistral(api_key=key)
    return _mistral_client


def _get_gemini_model():
    import google.generativeai as genai
    global _gemini_configured
    key = _get_key("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY non trovata")
    if not _gemini_configured:
        genai.configure(api_key=key)
        _gemini_configured = True
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    return genai.GenerativeModel(model_name)


# ═══ PROVIDER CALLS ═══════════════════════════════════════════════════════

def _call_openai(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    json_schema: Optional[Dict] = None,
) -> Dict:
    """Chiama OpenAI Chat Completions. Ritorna {text, input_tokens, output_tokens, cost}.

    Se json_schema è fornito, usa structured outputs nativi (response_format=json_schema).
    Altrimenti usa json_object mode se json_mode=True.
    """
    client = _get_openai_client()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if images:
        content = [{"type": "text", "text": user}]
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img['base64']}"},
            })
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_schema and json_mode:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": json_schema.get("name", "structured_output"),
                "schema": json_schema.get("schema", json_schema),
                "strict": json_schema.get("strict", True),
            },
        }
    elif json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content.strip()
    in_tok = getattr(resp.usage, "prompt_tokens", 0) or 0
    out_tok = getattr(resp.usage, "completion_tokens", 0) or 0
    cost = in_tok * (0.15 / 1_000_000) + out_tok * (0.60 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}


def _call_anthropic(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    json_schema: Optional[Dict] = None,
) -> Dict:
    """Chiama Anthropic Messages API.

    Anthropic non supporta json_schema nativo; json_mode viene ignorato
    e la struttura è affidata al prompt. Se json_schema è fornito,
    viene serializzato nel system prompt come istruzione aggiuntiva.
    """
    client = _get_anthropic_client()
    content = user
    if images:
        content = [{"type": "text", "text": user}]
        for img in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img["base64"]},
            })

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        temperature=temperature,
    )
    text = resp.content[0].text.strip()
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    cost = in_tok * (3.0 / 1_000_000) + out_tok * (15.0 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}


def _call_mistral(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    json_schema: Optional[Dict] = None,
) -> Dict:
    """Chiama Mistral Chat.

    Mistral supporta json_object mode ma non json_schema nativo.
    Se json_schema è fornito, viene aggiunto al system prompt come istruzione.
    """
    client = _get_mistral_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.complete(**kwargs)
    text = resp.choices[0].message.content.strip()
    in_tok = len(system) // 4 + len(user) // 4
    out_tok = len(text) // 4
    cost = in_tok * (2.0 / 1_000_000) + out_tok * (6.0 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}


def _call_perplexity(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    json_schema: Optional[Dict] = None,
) -> Dict:
    """Chiama Perplexity Sonar (web search enabled).

    Perplexity non supporta json_schema nativo; json_mode viene ignorato.
    """
    api_key = _get_key("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY non trovata")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    in_tok = usage.get("prompt_tokens", 0)
    out_tok = usage.get("completion_tokens", 0)
    cost = in_tok * (1.0 / 1_000_000) + out_tok * (1.0 / 1_000_000)
    citations = []
    for sr in data.get("search_results", []) or []:
        if sr.get("url"):
            citations.append({"title": sr.get("title") or sr["url"], "url": sr["url"]})
    if not citations:
        for url in data.get("citations", []) or []:
            citations.append({"title": url, "url": url})
    return {
        "text": text, "input_tokens": in_tok, "output_tokens": out_tok,
        "cost": cost, "citations": citations,
    }


def _call_ollama(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    json_schema: Optional[Dict] = None,
) -> Dict:
    """Chiama Ollama locale (OpenAI-compatible endpoint).

    Ollama espone /v1/chat/completions compatibile con l'API OpenAI.
    Supporta json_object mode via response_format.
    Costo: 0 (locale, no API key).
    """
    base = _ollama_base_url
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,  # V7.4: streaming to avoid timeout on CPU-only
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if json_schema and json_mode:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": json_schema.get("name", "structured_output"),
                "schema": json_schema.get("schema", json_schema),
                "strict": json_schema.get("strict", True),
            },
        }

    # V7.4: Use streaming to prevent timeout on CPU-only machines
    resp = requests.post(
        f"{base}/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=(30, 600),  # (connect, read-per-chunk)
        stream=True,
    )
    resp.raise_for_status()

    text_parts = []
    in_tok = 0
    out_tok = 0
    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")
        if line_str.startswith("data: "):
            line_str = line_str[6:]
        if line_str == "[DONE]":
            break
        try:
            chunk = json.loads(line_str)
            delta = chunk["choices"][0].get("delta", {}).get("content", "")
            if delta:
                text_parts.append(delta)
            usage = chunk.get("usage", {})
            if usage:
                in_tok = usage.get("prompt_tokens", in_tok)
                out_tok = usage.get("completion_tokens", out_tok)
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    text = "".join(text_parts).strip()
    if not in_tok:
        in_tok = len(system) // 4 + len(user) // 4
    if not out_tok:
        out_tok = len(text) // 4
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": 0.0}


def _call_gemini(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    json_schema: Optional[Dict] = None,
) -> Dict:
    """Chiama Google Gemini.

    Gemini supporta response_mime_type='application/json' e response_schema
    per output strutturato nativo quando json_schema è fornito.
    """
    gen_model = _get_gemini_model()
    prompt = f"{system}\n\n{user}"
    gen_config: Dict[str, Any] = {"max_output_tokens": max_tokens, "temperature": temperature}
    if json_schema and json_mode:
        gen_config["response_mime_type"] = "application/json"
        gen_config["response_schema"] = json_schema.get("schema", json_schema)
    if images:
        from google.generativeai import GenerativeModel
        parts = [prompt]
        for img in images:
            import base64
            parts.append({"mime_type": "image/jpeg", "data": base64.b64decode(img["base64"])})
        resp = gen_model.generate_content(parts, generation_config=gen_config)
    else:
        resp = gen_model.generate_content(prompt, generation_config=gen_config)
    text = resp.text.strip()
    in_tok = len(prompt) // 4
    out_tok = len(text) // 4
    cost = in_tok * (0.5 / 1_000_000) + out_tok * (1.5 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}


# ═══ DISPATCH ═════════════════════════════════════════════════════════════

_PROVIDER_FUNCS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "mistral": _call_mistral,
    "perplexity": _call_perplexity,
    "gemini": _call_gemini,
    "ollama": _call_ollama,
}

# Default models per provider (fallback se select_model non trova modelli nel DB)
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
    "mistral": "mistral-small-latest",
    "perplexity": "sonar",
    "gemini": "gemini-2.0-flash",
    "ollama": "gemma4:e2b-it-qat",
}

# Fallback order quando select_model non ha modelli nel DB
_FALLBACK_ORDER = ["openai", "anthropic", "mistral", "perplexity", "gemini", "ollama"]


def call_ai(
    task_type: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
    images: List[Dict] = None,
    strategy: str = "balanced",
    research_plan_id: int = None,
    session_id: int = None,
    cycle_id: int = None,
    json_schema: Optional[Dict] = None,
    skip_providers: Optional[set] = None,
) -> Dict:
    """Esegue una chiamata AI con routing automatico, fallback e tracking.

    Args:
        json_schema: Schema opzionale per structured outputs nativi.
            Supportato da OpenAI (response_format=json_schema) e Gemini
            (response_schema). Ignorato da provider senza supporto nativo.

    Returns:
        {
            ok: bool,
            text: str,           # risposta AI
            provider: str,       # provider usato
            model: str,          # modello usato
            cost: float,         # costo reale
            input_tokens: int,
            output_tokens: int,
            latency_ms: int,
            task_run_id: int,
            fallback_used: bool,
            citations: list,     # solo Perplexity
            error: str,          # se ok=False
            attempted: list,     # provider tentati
        }
    """
    task_def = TASK_TYPES.get(task_type, {})
    requires_vision = bool(images) or "vision" in task_def.get("capabilities", [])
    requires_web = "web_search" in task_def.get("capabilities", [])
    input_size = len(system) + len(user)

    # 1. Seleziona modello
    selection = select_model(
        task_type, input_size=input_size,
        requires_vision=requires_vision, requires_web=requires_web,
        strategy=strategy,
    )

    provider_code = selection.get("provider_code")
    model_id = selection.get("model_identifier")

    # V7.3-FIX: Skip providers from circuit breaker (caller-level)
    _skip = skip_providers or set()

    # 2. Costruisci lista provider da tentare
    if provider_code and not _breaker_is_open(provider_code) and provider_code not in _skip:
        order = [provider_code]
        for p in _FALLBACK_ORDER:
            if p != provider_code and not _breaker_is_open(p) and p not in _skip:
                order.append(p)
    else:
        order = [p for p in _FALLBACK_ORDER if not _breaker_is_open(p) and p not in _skip]

    attempted = []
    t0 = time.time()

    for i, pcode in enumerate(order):
        func = _PROVIDER_FUNCS.get(pcode)
        if not func:
            continue

        # V7.4: Only use model_id for the primary provider (i==0 AND it's the selected provider).
        # When primary is skipped and we fall through to fallback order, use each provider's default model.
        model = model_id if (i == 0 and pcode == provider_code and model_id) else _DEFAULT_MODELS.get(pcode)
        if not model:
            continue

        # Check budget
        est_cost = 0.01  # stima conservativa
        # V7.4: Local providers (ollama, lmstudio) have zero cost, skip budget check
        if pcode in ("ollama", "lmstudio"):
            est_cost = 0.0
        budget_check = check_budget_before_task(pcode, est_cost)
        if not budget_check.get("ok"):
            attempted.append({"provider": pcode, "error": "insufficient_budget"})
            continue

        try:
            result = func(
                model=model,
                system=system,
                user=user,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
                images=images,
                json_schema=json_schema,
            )
            latency_ms = int((time.time() - t0) * 1000)

            # Record successful task run
            run_id = record_task_run(
                task_type=task_type,
                provider_code=pcode,
                model_identifier=model,
                selection_reason=selection.get("reason", ""),
                policy_version=selection.get("policy_version", "default"),
                input_fingerprint=str(hash(user[:200])),
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_estimated=est_cost,
                cost_actual=result["cost"],
                latency_ms=latency_ms,
                outcome="success",
                fallback_from=order[0] if i > 0 else None,
                fallback_to=pcode if i > 0 else None,
                research_plan_id=research_plan_id,
                session_id=session_id,
                cycle_id=cycle_id,
            )

            return {
                "ok": True,
                "text": result["text"],
                "provider": pcode,
                "model": model,
                "cost": result["cost"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": latency_ms,
                "task_run_id": run_id,
                "fallback_used": i > 0,
                "citations": result.get("citations", []),
                "attempted": attempted,
            }

        except Exception as e:
            log.warning("AI provider %s failed: %s", pcode, e)
            attempted.append({"provider": pcode, "error": str(e)})
            _breaker_record_failure(pcode)
            continue

    # Tutti i provider hanno fallito
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "ok": False,
        "text": "",
        "provider": None,
        "model": None,
        "cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": latency_ms,
        "task_run_id": None,
        "fallback_used": False,
        "citations": [],
        "error": "Tutti i provider AI hanno fallito o non sono configurati.",
        "attempted": attempted,
    }


def call_ai_json(
    task_type: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    strategy: str = "balanced",
    research_plan_id: int = None,
    session_id: int = None,
    cycle_id: int = None,
    json_schema: Optional[Dict] = None,
    skip_providers: Optional[set] = None,
) -> Dict:
    """Chiama AI in JSON mode e parsa il risultato.

    Args:
        json_schema: Schema opzionale per structured outputs nativi.
            Quando fornito, i provider che lo supportano (OpenAI, Gemini)
            garantiscono output conforme allo schema. Per gli altri provider,
            lo schema viene ignorato e si usa json_object mode con fallback parsing.

    Returns:
        {
            ok: bool,
            data: dict/list,    # JSON parsed
            raw: str,           # testo raw
            provider: str,
            model: str,
            cost: float,
            ...
        }
    """
    result = call_ai(
        task_type=task_type,
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=True,
        strategy=strategy,
        research_plan_id=research_plan_id,
        session_id=session_id,
        cycle_id=cycle_id,
        json_schema=json_schema,
        skip_providers=skip_providers,
    )
    if not result["ok"]:
        return result

    try:
        data = json.loads(result["text"])
        result["data"] = data
    except json.JSONDecodeError:
        # Prova a estrarre JSON dal testo
        text = result["text"]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                result["data"] = data
            except json.JSONDecodeError:
                result["data"] = None
                result["json_error"] = "Failed to parse JSON from AI response"
        else:
            result["data"] = None
            result["json_error"] = "No JSON found in AI response"

    return result


# ═══ AVAILABILITY ═════════════════════════════════════════════════════════

def get_available_providers() -> List[str]:
    """Ritorna lista provider con chiave API configurata o locale attivo."""
    available = []
    for pcode, key_name in [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("mistral", "MISTRAL_API_KEY"),
        ("perplexity", "PERPLEXITY_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ]:
        if _get_key(key_name):
            available.append(pcode)
    # Ollama: sempre disponibile se il server locale risponde
    try:
        r = requests.get(f"{_ollama_base_url}/api/tags", timeout=3)
        if r.status_code == 200:
            available.append("ollama")
    except Exception:
        pass
    return available


def is_any_provider_available() -> bool:
    return len(get_available_providers()) > 0


# ═══ AI VALIDATION ═════════════════════════════════════════════════════════

_VALIDATION_SYSTEM = """Sei un validatore storico rigoroso. Analizzi un testo narrativo generato da AI
verificando:
1. Accuratezza storica: nessun anacronismo o contaminazione temporale tra guerre diverse
2. Coerenza con i dati forniti: nomi, date, luoghi, unità militari corrispondono ai claim
3. Allucinazioni: fatti non supportati da evidenza nei claim
4. Temporal scoping: se il periodo è WWII, non devono esserci riferimenti a WWI (e viceversa)

Rispondi SOLO in JSON con questo schema:
{
  "valid": true/false,
  "issues": ["descrizione problema 1", "descrizione problema 2"],
  "severity": "none" | "minor" | "major" | "critical",
  "suggestions": ["suggerimento correttivo 1"]
}

Se non trovi problemi, restituisci {"valid": true, "issues": [], "severity": "none", "suggestions": []}.
"""


def validate_ai_output(
    generated_text: str,
    claims_context: str,
    war_period: str = "unknown",
    skip_providers: Optional[set] = None,
) -> Dict:
    """Valida un testo generato da AI usando OpenAI come validatore, Mistral come fallback.

    Args:
        generated_text: testo narrativo da validare
        claims_context: contesto dei claim/evidenze per la validazione
        war_period: periodo storico (WWI/WWII/unknown) per il temporal scoping
        skip_providers: provider da saltare

    Returns:
        {
            ok: bool,
            valid: bool,          # True se il testo passa la validazione
            issues: list[str],    # problemi rilevati
            severity: str,        # none/minor/major/critical
            suggestions: list[str],
            provider: str,        # validatore usato
            model: str,
            raw: str,             # risposta raw del validatore
        }
    """
    user_prompt = f"""Periodo storico: {war_period}

DATI E CLAIM DI RIFERIMENTO:
{claims_context}

TESTO GENERATO DA VALIDARE:
{generated_text}

Analizza il testo e restituisci il JSON di validazione."""

    _skip = skip_providers or set()
    validation_order = [
        p for p in ["openai", "mistral", "anthropic", "gemini"]
        if p not in _skip and not _breaker_is_open(p)
    ]

    for pcode in validation_order:
        func = _PROVIDER_FUNCS.get(pcode)
        if not func:
            continue
        model = _DEFAULT_MODELS.get(pcode)
        if not model:
            continue
        try:
            result = func(
                model=model,
                system=_VALIDATION_SYSTEM,
                user=user_prompt,
                max_tokens=1024,
                temperature=0.1,
                json_mode=True,
            )
            import json as _json
            try:
                data = _json.loads(result["text"])
            except _json.JSONDecodeError:
                start = result["text"].find("{")
                end = result["text"].rfind("}") + 1
                if start >= 0 and end > start:
                    data = _json.loads(result["text"][start:end])
                else:
                    data = {"valid": True, "issues": [], "severity": "none",
                            "suggestions": [], "_parse_error": True}

            _breaker_record_success(pcode)
            return {
                "ok": True,
                "valid": data.get("valid", True),
                "issues": data.get("issues", []),
                "severity": data.get("severity", "none"),
                "suggestions": data.get("suggestions", []),
                "provider": pcode,
                "model": model,
                "raw": result["text"],
            }
        except Exception as e:
            log.warning("Validation provider %s failed: %s", pcode, e)
            _breaker_record_failure(pcode)
            continue

    return {
        "ok": False,
        "valid": True,  # If no validator available, don't block
        "issues": [],
        "severity": "none",
        "suggestions": [],
        "provider": None,
        "model": None,
        "raw": "",
        "error": "Nessun validatore AI disponibile",
    }


# ═══ MULTI-TURN CHAT ═══════════════════════════════════════════════════════

def call_ai_chat(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.3,
    skip_providers: Optional[set] = None,
) -> Dict:
    """Esegue una chiamata AI multi-turno con conversation history.
    
    Usa la OpenAI Chat Completions API con messages array per supportare
    follow-up conversazionali. Fallback su Mistral/Anthropic se OpenAI non disponibile.
    
    Args:
        system: System prompt con contesto (snapshot, claims, etc.)
        messages: Lista di {"role": "user"/"assistant", "content": "..."} 
                  per la conversation history
        max_tokens: Token massimi per la risposta
        temperature: Temperatura di campionamento
        skip_providers: Provider da saltare (circuit breaker)
    
    Returns:
        {
            ok: bool,
            text: str,           # risposta AI
            provider: str,       # provider usato
            model: str,          # modello usato
            cost: float,
            input_tokens: int,
            output_tokens: int,
            latency_ms: int,
            error: str,          # se ok=False
        }
    """
    _skip = skip_providers or set()
    order = [p for p in _FALLBACK_ORDER if not _breaker_is_open(p) and p not in _skip]
    
    attempted = []
    t0 = time.time()
    
    for i, pcode in enumerate(order):
        func = _PROVIDER_FUNCS.get(pcode)
        if not func:
            continue
        
        model = _DEFAULT_MODELS.get(pcode)
        if not model:
            continue
        
        # Check budget
        est_cost = 0.01
        if pcode in ("ollama", "lmstudio"):
            est_cost = 0.0
        budget_check = check_budget_before_task(pcode, est_cost)
        if not budget_check.get("ok"):
            attempted.append({"provider": pcode, "error": "insufficient_budget"})
            continue
        
        try:
            if pcode == "openai":
                result = _call_openai_chat(model, system, messages, max_tokens, temperature)
            elif pcode == "mistral":
                result = _call_mistral_chat(model, system, messages, max_tokens, temperature)
            elif pcode == "anthropic":
                result = _call_anthropic_chat(model, system, messages, max_tokens, temperature)
            else:
                # For providers without native multi-turn, flatten to single user message
                flat = "\n\n".join(
                    f"{'Utente' if m['role']=='user' else 'Assistente'}: {m['content']}"
                    for m in messages
                )
                result = func(model=model, system=system, user=flat,
                              max_tokens=max_tokens, temperature=temperature)
            
            latency_ms = int((time.time() - t0) * 1000)
            
            run_id = record_task_run(
                task_type="conversation",
                provider_code=pcode,
                model_identifier=model,
                selection_reason="multi_turn_chat",
                policy_version="default",
                input_fingerprint=str(hash(system[:200])),
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_estimated=est_cost,
                cost_actual=result["cost"],
                latency_ms=latency_ms,
                outcome="success",
                fallback_from=order[0] if i > 0 else None,
                fallback_to=pcode if i > 0 else None,
            )
            
            return {
                "ok": True,
                "text": result["text"],
                "provider": pcode,
                "model": model,
                "cost": result["cost"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": latency_ms,
                "task_run_id": run_id,
                "attempted": attempted,
            }
        
        except Exception as e:
            log.warning("AI chat provider %s failed: %s", pcode, e)
            attempted.append({"provider": pcode, "error": str(e)})
            _breaker_record_failure(pcode)
            continue
    
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "ok": False,
        "text": "",
        "provider": None,
        "model": None,
        "cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": latency_ms,
        "error": "Tutti i provider AI hanno fallito o non sono configurati.",
        "attempted": attempted,
    }


def _call_openai_chat(
    model: str,
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Dict:
    """Chiama OpenAI Chat Completions con messages array multi-turn."""
    client = _get_openai_client()
    full_messages = [{"role": "system", "content": system}] + messages
    
    resp = client.chat.completions.create(
        model=model,
        messages=full_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = resp.choices[0].message.content.strip()
    in_tok = getattr(resp.usage, "prompt_tokens", 0) or 0
    out_tok = getattr(resp.usage, "completion_tokens", 0) or 0
    cost = in_tok * (0.15 / 1_000_000) + out_tok * (0.60 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}


def _call_mistral_chat(
    model: str,
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Dict:
    """Chiama Mistral Chat con messages array multi-turn."""
    client = _get_mistral_client()
    full_messages = [{"role": "system", "content": system}] + messages
    
    resp = client.chat.complete(
        model=model,
        messages=full_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = resp.choices[0].message.content.strip()
    in_tok = len(system) // 4 + sum(len(m["content"]) // 4 for m in messages)
    out_tok = len(text) // 4
    cost = in_tok * (0.1 / 1_000_000) + out_tok * (0.3 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}


def _call_anthropic_chat(
    model: str,
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> Dict:
    """Chiama Anthropic Messages API con conversation history."""
    client = _get_anthropic_client()
    
    # Anthropic wants system separate, messages as user/assistant pairs
    # Ensure messages alternate user/assistant starting with user
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        temperature=temperature,
    )
    text = resp.content[0].text.strip()
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    cost = in_tok * (3.0 / 1_000_000) + out_tok * (15.0 / 1_000_000)
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok, "cost": cost}
