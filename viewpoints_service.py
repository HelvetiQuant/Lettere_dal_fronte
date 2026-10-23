"""Confronto strutturato delle fonti: Punti di vista.

Raccoglie analisi da piu' provider AI sui dati del DB locale,
le confronta e struttura in fatti condivisi, divergenze e incertezze.
Non appiattisce le differenze: le conserva e le evidenzia."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


def _extract_claims(text: str) -> list[dict[str, Any]]:
    """Estrae affermazioni strutturate dal testo di un provider AI."""
    if not text:
        return []
    claims: list[dict[str, Any]] = []
    # Dividi per sezioni marcate (SINTESI, PERSONE, LUOGHI, EVENTI, FONTI, COLLEGAMENTI)
    sections = re.split(r"\n(?=[A-ZÀ-Ý]{3,}:)", text)
    for section in sections:
        lines = [l.strip() for l in section.split("\n") if l.strip()]
        if not lines:
            continue
        header_match = re.match(r"^([A-ZÀ-Ý]{3,}):", lines[0])
        category = header_match.group(1).lower() if header_match else "generale"
        for line in lines[1:] if header_match else lines:
            # Saluta righe troppo corte o placeholder
            if len(line) < 10:
                continue
            claims.append({"category": category, "text": line})
    return claims


def _find_shared_claims(per_provider_claims: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Trova affermazioni condivise tra piu' provider (stesso category + keyword overlap)."""
    shared: list[dict[str, Any]] = []
    providers = list(per_provider_claims.keys())
    if len(providers) < 2:
        return shared

    seen: set[str] = set()
    for i, p1 in enumerate(providers):
        for claim1 in per_provider_claims[p1]:
            key_words = set(re.findall(r"\b[A-Za-zÀ-ÿ]{4,}\b", claim1["text"].lower()))
            if not key_words:
                continue
            for p2 in providers[i + 1:]:
                for claim2 in per_provider_claims[p2]:
                    if claim2["category"] != claim1["category"]:
                        continue
                    other_words = set(re.findall(r"\b[A-Za-zÀ-ÿ]{4,}\b", claim2["text"].lower()))
                    overlap = key_words & other_words
                    if len(overlap) >= 3:
                        fact_key = f"{claim1['category']}:{'|'.join(sorted(overlap)[:5])}"
                        if fact_key not in seen:
                            shared.append({
                                "fact": claim1["text"][:200],
                                "sources": [p1, p2],
                                "category": claim1["category"],
                                "overlap_keywords": sorted(overlap)[:5],
                            })
                            seen.add(fact_key)
                        break
    return shared


def _find_divergences(per_provider_claims: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Trova divergenze: stessa categoria ma keyword molto diverse tra provider."""
    divergences: list[dict[str, Any]] = []
    providers = list(per_provider_claims.keys())
    if len(providers) < 2:
        return divergences

    seen: set[str] = set()
    for i, p1 in enumerate(providers):
        for claim1 in per_provider_claims[p1]:
            key_words = set(re.findall(r"\b[A-Za-zÀ-ÿ]{4,}\b", claim1["text"].lower()))
            if not key_words:
                continue
            for p2 in providers[i + 1:]:
                for claim2 in per_provider_claims[p2]:
                    if claim2["category"] != claim1["category"]:
                        continue
                    other_words = set(re.findall(r"\b[A-Za-zÀ-ÿ]{4,}\b", claim2["text"].lower()))
                    overlap = key_words & other_words
                    # Divergenza: stessa categoria ma overlap < 1 keyword
                    if len(overlap) <= 1 and len(key_words) >= 3 and len(other_words) >= 3:
                        div_key = f"{claim1['category']}:{p1}:{p2}:{claim1['text'][:30]}"
                        if div_key not in seen:
                            divergences.append({
                                "fact": f"Category '{claim1['category']}'",
                                "versions": [
                                    {"source": p1, "value": claim1["text"][:200], "role": "supports"},
                                    {"source": p2, "value": claim2["text"][:200], "role": "supports"},
                                ],
                            })
                            seen.add(div_key)
                        break
    return divergences[:10]  # limit


def _find_uncertainties(provider_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Identifica incertezze: provider che hanno fallito o dato risposte vuote."""
    uncertainties: list[dict[str, Any]] = []
    for provider, result in provider_results.items():
        if isinstance(result, dict) and result.get("error"):
            uncertainties.append({
                "topic": f"Provider {provider}",
                "reason": f"Errore: {result['error']}",
            })
        elif isinstance(result, dict) and not result.get("risposta"):
            uncertainties.append({
                "topic": f"Provider {provider}",
                "reason": "Nessuna risposta ricevuta",
            })
    return uncertainties


def _ai_synthesis(query: str, shared: list, divergences: list, uncertainties: list,
                  provider_texts: dict[str, str]) -> dict[str, Any]:
    """Genera sintesi AI che conserva le differenze."""
    try:
        from ai_client import call_ai
    except ImportError:
        return {"used": False, "text": "", "error": "ai_client non disponibile"}

    system = (
        "Sei un analista storico. Confronti le analisi prodotte da diversi provider AI "
        "sugli stessi dati archivistici. Il tuo compito e' produrre una sintesi che "
        "conservi le differenze senza appiattirle. Evidenzia: (1) fatti su cui tutti "
        "concordano, (2) divergenze tra le fonti, (3) lacune e incertezze. "
        "Non inventare fatti. Cita il provider di origine tra parentesi."
    )
    payload = json.dumps({
        "query": query,
        "shared_facts": shared[:10],
        "divergences": divergences[:10],
        "uncertainties": uncertainties,
        "provider_summaries": {p: t[:500] for p, t in provider_texts.items()},
    }, ensure_ascii=False, default=str)[:16_000]

    try:
        result = call_ai(
            "generate_viewpoints",
            system,
            payload,
            max_tokens=1200,
            temperature=0.1,
            strategy="quality_max",
        )
        return {
            "used": bool(result.get("ok")),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "text": result.get("text", "") if result.get("ok") else "",
            "error": result.get("error") if not result.get("ok") else None,
        }
    except Exception as exc:
        return {"used": False, "text": "", "error": str(exc)}


def compare_viewpoints(query: str, *, use_ai: bool = False) -> dict[str, Any]:
    """Confronta le analisi di piu' provider AI su una stessa query.

    Args:
        query: termine di ricerca (persona, evento, luogo, domanda)
        use_ai: se True, genera sintesi AI; altrimenti solo analisi deterministica

    Returns:
        dict con synthesis, shared_facts, divergences, uncertainties, sources_used
    """
    from ai_research import research_all

    # Raccogli analisi da tutti i provider
    raw_results = research_all(query, limit=20)

    # Estrai testi e claim per provider
    provider_texts: dict[str, str] = {}
    per_provider_claims: dict[str, list[dict[str, Any]]] = {}
    sources_used: list[dict[str, Any]] = []

    for provider, result in raw_results.items():
        if isinstance(result, dict) and result.get("risposta"):
            text = result["risposta"]
            provider_texts[provider] = text
            claims = _extract_claims(text)
            per_provider_claims[provider] = claims
            sources_used.append({
                "name": f"AI Provider: {provider} ({result.get('model', '?')})",
                "provider": provider,
                "model": result.get("model"),
            })
            # Aggiungi citazioni web se disponibili (Perplexity)
            if result.get("citations"):
                for cit in result["citations"][:5]:
                    sources_used.append({
                        "name": cit.get("title", cit.get("url", "")),
                        "url": cit.get("url"),
                    })

    # Analisi deterministica
    shared = _find_shared_claims(per_provider_claims)
    divergences = _find_divergences(per_provider_claims)
    uncertainties = _find_uncertainties(raw_results)

    deterministic_synthesis = (
        f"Il confronto tra {len(provider_texts)} provider AI ha individuato "
        f"{len(shared)} fatti condivisi, {len(divergences)} divergenze esplicite "
        f"e {len(uncertainties)} incertezze. "
        "Le sezioni sottostanti mantengono separati fatti concordanti, "
        "divergenze e lacune."
    )

    # Sintesi AI opzionale
    ai = _ai_synthesis(query, shared, divergences, uncertainties, provider_texts) if use_ai else {
        "used": False,
        "model": None,
        "text": "",
        "note": "Sintesi AI non richiesta. Usare use_ai=true per attivarla.",
    }

    return {
        "ok": True,
        "query": query,
        "synthesis": ai.get("text") or deterministic_synthesis,
        "shared_facts": shared,
        "divergences": divergences,
        "uncertainties": uncertainties,
        "sources_used": sources_used,
        "providers_used": list(provider_texts.keys()),
        "ai": ai,
        "generated_at": datetime.now().isoformat(),
    }
