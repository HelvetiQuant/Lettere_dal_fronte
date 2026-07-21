"""Event research engine — ricerca storica documentata su eventi militari.

Flusso:
1. disambigua l'evento usando il DB eventi_1gm e gli eventi curati;
2. raccoglie fonti locali, federate e dall'indice archivistico;
3. invia i metadati/snippet all'AI con un prompt rigoroso;
4. restituisce una scheda leggibile + JSON strutturato + matrice evidenze.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import events
import source_locator as sl
import search_service as ss
from database import DB_PATH


EVENT_RESEARCH_SYSTEM = (
    "Sei un ricercatore storico specializzato in eventi bellici del '900. "
    "Non inventare dati. Associa ogni affermazione a una fonte con URL. "
    "Usa solo le fonti fornite nel contesto. "
    "Se un dato non è verificato scrivi 'non verificato' o 'non disponibile'. "
    "Restituisci SEMPRE un JSON valido seguito dal testo della scheda."
)


EVENT_RESEARCH_PROMPT = """Scrivi in italiano.

L'utente chiede di ricostruire l'evento: "{subject_label}".

Contesto fornito:
{context}

--- ISTRUZIONI OBBLIGATORIE ---

1. Disambigua l'evento. Se il nome potrebbe riferirsi a più eventi, elenca le possibili corrispondenze e scegli quella più probabile motivando la scelta.
2. Stabilisci a quale conflitto appartiene (Prima guerra mondiale, Seconda guerra mondiale, altro).
3. Per ogni dato centrale (date, località, forze, comandanti, esito, perdite) cita almeno una fonte presente nel contesto. Se ci sono discordanze, riportale entrambe e spiega.
4. Non inventare URL. Usa solo gli URL presenti nelle fonti fornite.
5. Non presentare il titolo di una pagina come unica prova.
6. Non sommare cifre provenienti da criteri diversi.
7. Distingui fonti primarie, istituzionali, storiografia scientifica e divulgative.
8. Assegna uno stato di affidabilità a ogni dato: ALTA, MEDIA, BASSA, CONTROVERSA, NON VERIFICATA.
9. Produci una SCHEDA LEGGIBILE e un OUTPUT JSON strutturato.

--- FORMATO RICHIESTO ---

Prima il JSON esattamente così (non wrapparlo in markdown):

{{
  "event": {{
    "canonical_name": "",
    "alternative_names": [],
    "original_language_names": [],
    "event_type": "",
    "conflict": "",
    "theatre": "",
    "campaign": ""
  }},
  "chronology": {{
    "start_date": "",
    "end_date": "",
    "date_precision": "",
    "alternative_dates": [],
    "phases": []
  }},
  "location": {{
    "main_place": "",
    "municipality": "",
    "province_or_area": "",
    "region": "",
    "current_country": "",
    "historical_administration": "",
    "coordinates": null,
    "additional_places": []
  }},
  "belligerents": [],
  "commanders": [],
  "units": [],
  "objectives": [],
  "summary": "",
  "outcome": "",
  "consequences": [],
  "casualties": [],
  "related_documents": [],
  "disputed_data": [],
  "unverified_claims": [],
  "sources": [],
  "research_status": {{
    "overall_confidence": "",
    "missing_information": [],
    "suggested_next_searches": []
  }}
}}

Subito dopo, separa con una riga contenente ===SCHEDA=== e scrivi:
1. Titolo normalizzato
2. Guerra e teatro
3. Date verificate
4. Localizzazione
5. Sintesi storica
6. Schieramenti/unità
7. Svolgimento
8. Esito e conseguenze
9. Perdite con stime distinte
10. Documenti collegati
11. Dati discordanti
12. Fonti utilizzate
13. Piste di ricerca successive

Per ogni affermazione indica la fonte tra parentesi quadre [ID].
"""


def _normalize(s: str) -> str:
    return re.sub(r"[\s_]+", " ", s.strip().lower())


def _match_score(a: str, b: str) -> float:
    a = _normalize(a)
    b = _normalize(b)
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8
    a_words = set(a.split())
    b_words = set(b.split())
    inter = a_words & b_words
    if not inter:
        return 0.0
    return len(inter) / max(len(a_words), len(b_words))


def disambiguate_event(query: str) -> Dict[str, Any]:
    """Trova il miglior evento nel DB eventi_1gm; se ambiguo ritorna matches."""
    from event_query_engine import DB as EDB

    matches = []
    if not Path(EDB).exists():
        return {"canonical": query, "matches": [], "confidence": 1.0, "db_match": False}

    conn = sqlite3.connect(str(EDB), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, nome, aliases, keywords, data_inizio, data_fine, luogo, descrizione FROM eventi_1gm"
        ).fetchall()
        for r in rows:
            alias_list = json.loads(r["aliases"]) if r["aliases"] else []
            kw_list = json.loads(r["keywords"]) if r["keywords"] else []
            names = [r["nome"]] + alias_list + kw_list
            best = max(_match_score(query, n) for n in names)
            if best > 0.4:
                matches.append({
                    "id": r["id"],
                    "nome": r["nome"],
                    "aliases": alias_list,
                    "data_inizio": r["data_inizio"],
                    "data_fine": r["data_fine"],
                    "luogo": r["luogo"],
                    "score": round(best, 2),
                })
        matches.sort(key=lambda x: x["score"], reverse=True)
        if not matches:
            return {"canonical": query, "matches": [], "confidence": 0.0, "db_match": False}
        top = matches[0]
        return {
            "canonical": top["nome"],
            "matches": matches[:5],
            "confidence": top["score"],
            "db_match": True,
            "event_id": top["id"],
            "date_range": f"{top['data_inizio']} → {top['data_fine']}",
            "place": top["luogo"],
        }
    finally:
        conn.close()


def _event_db_context(canonical: str) -> Dict[str, Any]:
    """Recupera contesto dall'event_query_engine e dagli eventi_1gm."""
    from event_query_engine import query_event
    return query_event(canonical, verbose=False)


def _local_sources_context(canonical: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fonti dall'indice locale legate all'evento (match esatto + full-text)."""
    exact = sl.find_sources_by_subject(canonical, limit=limit).get("candidates", [])
    candidate = sl.find_candidate_sources(canonical, limit=limit).get("candidates", [])
    seen = set()
    candidates = []
    for c in exact + candidate:
        sid = c.get("id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        candidates.append(c)
    enriched = []
    for c in candidates[:limit]:
        snippet = sl._read_cached_text(c.get("id"))
        enriched.append({
            "source_id": f"LOC-{c.get('id')}",
            "title": c.get("titolo"),
            "author_or_institution": c.get("ente", c.get("archivio", "")),
            "source_type": c.get("tipo_fonte", "fonte archivistica"),
            "url": c.get("url_catalogo", ""),
            "archive_reference": f"{c.get('archivio','')} {c.get('fondo','')} {c.get('segnatura','')}".strip(),
            "date": c.get("data_inizio", ""),
            "excerpt": (snippet or "")[:1200],
            "authority": "istituzionale" if c.get("archivio") else "locale",
            "availability": c.get("availability", "da_richiedere"),
        })
    return enriched


def _federated_sources_context(query: str, cues: Optional[Dict] = None, limit: int = 15) -> List[Dict[str, Any]]:
    """Fonti dai provider esterni autorizzati."""
    try:
        from source_providers.federation import federated_search
        providers = ["nara", "antenati", "cwgc", "ussme", "archivio_stato",
                     "europeana", "internetarchive"]
        rows = federated_search(query, cues=cues, providers=providers)
    except Exception:
        rows = []
    out = []
    for r in rows:
        if r.get("error"):
            continue
        out.append({
            "source_id": r.get("provider", "FED"),
            "title": r.get("title") or r.get("label") or query,
            "author_or_institution": r.get("provider", ""),
            "source_type": r.get("type", "fonte esterna"),
            "url": r.get("url") or r.get("direct_url") or r.get("catalog_url", ""),
            "archive_reference": "",
            "date": r.get("date", ""),
            "excerpt": (r.get("snippet") or "")[:1200],
            "authority": r.get("provider", "esterna"),
        })
    return out[:limit]


def _caduti_decorati_context(canonical: str, limit: int = 10) -> Dict[str, Any]:
    """Estrae un campione di caduti/decorati collegati all'evento."""
    try:
        cad = events.get_eventi_1gm_caduti(canonical, limit=limit, offset=0)
        dec = events.get_eventi_1gm_decorati(canonical, limit=limit, offset=0)
    except Exception:
        return {"caduti": [], "decorati": []}
    return {
        "caduti": [dict(c) for c in cad.get("caduti", [])[:limit]],
        "decorati": [dict(d) for d in dec.get("decorati", [])[:limit]],
    }


def _internal_db_context(canonical: str, query: str, limit: int = 20) -> Dict[str, Any]:
    """Cerca nel database interno (entità, grafo, record sorgente) per l'evento.

    Usa search_service per interrogare l'indice FTS5 e, per le entità più rilevanti,
    recupera il record sorgente e il grafo dei collegamenti.
    """
    try:
        entities = ss.search_entities(canonical, limit=limit)
        if canonical != query:
            more = ss.search_entities(query, limit=limit // 2)
            seen = {e["entita_id"] for e in entities}
            for e in more:
                if e["entita_id"] not in seen:
                    entities.append(e)
                    seen.add(e["entita_id"])
    except Exception:
        entities = []

    full_contexts = []
    network_nodes = []
    processed = set()
    for e in entities[:10]:
        eid = e.get("entita_id")
        if not eid or eid in processed:
            continue
        processed.add(eid)
        try:
            ctx = ss.get_entity_full_context(eid)
            full_contexts.append(ctx)
        except Exception:
            ctx = None
        if e.get("tipo") in ("evento", "luogo") and ctx:
            try:
                net = ss.get_entity_network(eid, max_depth=2)
                network_nodes.extend(net.get("nodes", [])[:20])
            except Exception:
                pass

    records_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for ctx in full_contexts:
        src = ctx.get("source_record") if ctx else None
        if not src or isinstance(src, dict) and src.get("error"):
            continue
        tbl = ctx.get("source_table") or "record"
        records_by_table.setdefault(tbl, []).append(src)

    return {
        "entities": entities[:limit],
        "records_by_table": {k: v[:10] for k, v in records_by_table.items()},
        "network_nodes": network_nodes[:limit],
    }


def _build_context(canonical: str, query: str, options: Dict[str, Any]) -> str:
    """Compila il contesto testuale per il prompt AI."""
    parts = []
    parts.append(f"EVENTO CANONICO: {canonical}")
    if options:
        parts.append(f"OPZIONI UTENTE: {json.dumps(options, ensure_ascii=False)}")

    ev_ctx = _event_db_context(canonical)
    if ev_ctx.get("evento"):
        parts.append("--- DATI EVENTO DB ---")
        parts.append(json.dumps(ev_ctx.get("evento"), ensure_ascii=False, default=str, indent=2))
        if ev_ctx.get("fonti", {}).get("items"):
            parts.append("--- FONTI EVENTO DB ---")
            for f in ev_ctx["fonti"]["items"][:10]:
                parts.append(json.dumps(f, ensure_ascii=False, default=str))

    local = _local_sources_context(canonical, limit=10)
    if local:
        parts.append("--- FONTI LOCALI ---")
        for s in local:
            parts.append(json.dumps(s, ensure_ascii=False, default=str))

    fed = _federated_sources_context(canonical, cues=ev_ctx.get("cues"), limit=10)
    if fed:
        parts.append("--- FONTI ESTERNE FEDERATE ---")
        for s in fed:
            parts.append(json.dumps(s, ensure_ascii=False, default=str))

    sold = _caduti_decorati_context(canonical, limit=10)
    if sold.get("caduti") or sold.get("decorati"):
        parts.append("--- CAMPIONE CADUTI/DECORATI ---")
        parts.append(json.dumps(sold, ensure_ascii=False, default=str))

    internal = _internal_db_context(canonical, query, limit=20)
    if internal.get("entities"):
        parts.append("--- RICERCA DATABASE INTERNO (entità, record, grafo) ---")
        parts.append(json.dumps(internal, ensure_ascii=False, default=str, indent=2))

    return "\n\n".join(parts)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Tenta di estrarre il primo JSON oggetto dalla risposta."""
    text = text or ""
    text = text.strip()
    # Cerca oggetto JSON racchiuso tra {...}
    match = re.search(r"\{[\s\S]*\}\n", text)
    if not match:
        # fallback: primo { } bilanciato
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except Exception:
                        return None
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _split_json_and_text(text: str) -> tuple:
    """Separa JSON iniziale dalla scheda testuale."""
    data = _extract_json(text)
    if not data:
        return None, text
    marker = "===SCHEDA==="
    idx = text.find(marker)
    scheda = text[idx + len(marker):].strip() if idx != -1 else text.split("\n", 1)[-1] if text.startswith("{") else text
    return data, scheda


def _build_evidence_matrix(json_data: Dict[str, Any], sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Crea una matrice semplice campo→valore→fonte."""
    matrix = []
    src_map = {s.get("source_id"): s for s in sources}
    for field, value in json_data.items():
        if isinstance(value, (str, int, float)):
            matrix.append({
                "campo": field,
                "valore": str(value),
                "fonte": "",
                "affidabilita": "NON VERIFICATA",
            })
    return matrix


TAB_INSTRUCTIONS = {
    "panoramica": (
        "Concentrati su una scheda panoramica sintetica: titolo, guerra, teatro, date, località, "
        "sintesi storica, schieramenti, esito e conseguenze. Mantieni il testo leggibile e conciso."
    ),
    "fonti": (
        "Concentrati sulle FONTI: per ogni fonte indica titolo, ente, tipologia, cosa sostiene, "
        "limitazioni e livello di autorevolezza. Costruisci la matrice delle evidenze e minimizza la narrazione."
    ),
    "punti_di_vista": (
        "Concentrati su CONVERGENZE e DIVERGENZE tra le fonti. Presenta i dati concordanti, poi "
        "i dati discordanti con le relative motivazioni e fonti. Usa la matrice delle evidenze per confrontare."
    ),
    "cronologia": (
        "Concentrati sulla CRONOLOGIA: sequenza temporale dettagliata, fasi principali, date alternative "
        "e grado di precisione. Produci una linea del tempo chiara."
    ),
}


# Provider per tab: Perplexity (panoramica/web), Anthropic (analisi fonti),
# OpenAI (sintesi punti di vista), Mistral (cronologia veloce).
TAB_PROVIDER = {
    "panoramica": "perplexity",
    "fonti": "claude",
    "punti_di_vista": "gpt",
    "cronologia": "mistral",
}

# Ordine di fallback per i report evento: Perplexity -> OpenAI -> Anthropic -> Mistral.
EVENT_RESEARCH_FALLBACK = ["perplexity", "gpt", "claude", "mistral"]


def _build_prompt(canonical: str, context: str, tab: str) -> str:
    instruction = TAB_INSTRUCTIONS.get(tab, TAB_INSTRUCTIONS["punti_di_vista"])
    return EVENT_RESEARCH_PROMPT.format(subject_label=canonical, context=context) + "\n\n" + instruction


def research_event(query: str, options: Optional[Dict[str, Any]] = None,
                   provider: Optional[str] = None, tab: str = "punti_di_vista") -> Dict[str, Any]:
    """Genera la scheda storica documentata per un evento."""
    import biography as bio

    options = options or {}
    dis = disambiguate_event(query)
    canonical = dis.get("canonical") or query

    if not dis.get("db_match"):
        return {
            "ok": False,
            "error": "Evento non identificato nel database. Verifica il nome o fornisci maggiori dettagli.",
            "matches": dis.get("matches", []),
        }

    selected_provider = provider or TAB_PROVIDER.get(tab, "perplexity")
    context = _build_context(canonical, query, options)
    prompt = _build_prompt(canonical, context[:15000], tab)

    result = bio._call_with_fallback(
        system=EVENT_RESEARCH_SYSTEM,
        prompt=prompt,
        tag=f"ricerca evento: {canonical} [{tab}]",
        preferred=selected_provider,
        fallback_order=EVENT_RESEARCH_FALLBACK,
    )
    if result.get("error"):
        return {"ok": False, "error": result.get("error"), "attempted": result.get("attempted", [])}

    raw = result.get("risposta", "")
    json_data, scheda = _split_json_and_text(raw)

    if json_data is None:
        json_data = {"event": {"canonical_name": canonical}, "research_status": {"overall_confidence": "NON VERIFICATA"}}

    sources = _local_sources_context(canonical, limit=15) + _federated_sources_context(canonical, limit=15)
    matrix = _build_evidence_matrix(json_data, sources)

    return {
        "ok": True,
        "risposta": scheda or raw,
        "json": json_data,
        "evidence_matrix": matrix,
        "sources": sources,
        "disputed_data": json_data.get("disputed_data", []),
        "unverified_claims": json_data.get("unverified_claims", []),
        "disambiguation": dis,
        "query": query,
        "canonical": canonical,
        "attempted": result.get("attempted", []),
        "provider": result.get("provider"),
    }


def format_report(data: Dict[str, Any]) -> str:
    """Utility per stampare il report leggibile da un dict research."""
    return data.get("risposta", "")
