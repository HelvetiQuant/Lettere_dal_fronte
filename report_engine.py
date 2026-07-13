"""Report Engine — genera report narrativi da query su grafo+metadati.

Query esempio: "Battaglia di Cassino" → escursus storico + soldati
               coinvolti + fonti primarie per ciascuno.

Tipi supportati:
  evento  — battaglia, operazione militare, evento storico
  unita   — reggimento, divisione, battaglione
  luogo   — campo di internamento, città, fronte
  persona — singolo soldato (dossier esteso)

Flusso:
  1. Estrai entità rilevanti dal DB (entita + collegamenti)
  2. Recupera soldati collegati (internati + caduti)
  3. Recupera fonti archivistiche (fonti_indice) per ogni entità
  4. Componi contesto compatto per AI
  5. Genera narrative via OpenAI/Anthropic/Mistral (fallback chain)
  6. Ritorna report strutturato JSON
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from database import get_conn

log = logging.getLogger("report_engine")

MAX_SOLDIERS_IN_REPORT = 50   # max soldati listati nel report
MAX_SOURCES_PER_ENTITY = 10   # max fonti per entità
MAX_CONTEXT_CHARS = 12000     # limite contesto AI


# ─── Ricerca entità nel DB ────────────────────────────────────────────────────

def _search_entities(query: str, tipo: str = None, limit: int = 20) -> list:
    """Cerca entità nel DB per valore simile alla query."""
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    tokens = [t.strip() for t in query.split() if len(t.strip()) > 2]
    where_parts = []
    params = []
    for tok in tokens[:4]:
        where_parts.append("valore_normalizzato LIKE ?")
        params.append(f"%{tok.lower()}%")
    where = " AND ".join(where_parts) if where_parts else "1=1"
    if tipo:
        where += " AND tipo=?"
        params.append(tipo)
    rows = conn.execute(
        f"SELECT id, tipo, valore, contesto, fonte_tabella FROM entita "
        f"WHERE {where} ORDER BY id LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return rows


def _get_soldiers_for_entity(entita_ids: list, limit: int = MAX_SOLDIERS_IN_REPORT) -> list:
    """Recupera soldati (internati) collegati a una lista di entità."""
    if not entita_ids:
        return []
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    placeholders = ",".join("?" * len(entita_ids))
    rows = conn.execute(
        f"SELECT DISTINCT i.id, i.cognome, i.nome, i.grado, "
        f"i.luogo_cattura, i.luogo_internamento, i.sorte, i.data_cattura "
        f"FROM internati i "
        f"JOIN collegamenti c ON c.soggetto_tabella='internati' AND c.soggetto_id=i.id "
        f"WHERE c.entita_id IN ({placeholders}) "
        f"ORDER BY i.cognome, i.nome LIMIT ?",
        entita_ids + [limit]
    ).fetchall()
    conn.close()
    return rows


def _get_sources_for_entity(entita_id: int, limit: int = MAX_SOURCES_PER_ENTITY) -> list:
    """Recupera fonti archivistiche collegate a un'entità."""
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = conn.execute(
        "SELECT fi.archivio, fi.titolo, fi.url_catalogo, fi.access_type, fi.confidence "
        "FROM fonti_indice fi "
        "JOIN collegamenti c ON c.entita_id=fi.id "
        "WHERE c.soggetto_tabella='entita' AND c.soggetto_id=? "
        "AND fi.url_catalogo IS NOT NULL AND fi.url_catalogo != '' "
        "ORDER BY fi.confidence DESC LIMIT ?",
        (entita_id, limit)
    ).fetchall()
    conn.close()
    return rows


def _get_sources_for_soldier(soldier_id: int, limit: int = 5) -> list:
    """Fonti dirette per un soldato da fonti_indice."""
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    soldier = conn.execute("SELECT cognome, nome FROM internati WHERE id=?", (soldier_id,)).fetchone()
    if not soldier:
        conn.close()
        return []
    cognome = (soldier["cognome"] or "").strip().upper()
    rows = conn.execute(
        "SELECT archivio, titolo, url_catalogo, access_type FROM fonti_indice "
        "WHERE (note LIKE ? OR titolo LIKE ?) "
        "AND url_catalogo IS NOT NULL AND url_catalogo != '' "
        "ORDER BY confidence DESC LIMIT ?",
        (f"%{cognome}%", f"%{cognome}%", limit)
    ).fetchall()
    conn.close()
    return rows


def _get_fonti_indice_for_query(query: str, limit: int = 15) -> list:
    """Cerca fonti direttamente in fonti_indice per parole chiave."""
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    tokens = [t.strip() for t in query.split() if len(t.strip()) > 3]
    where_parts = []
    params = []
    for tok in tokens[:3]:
        where_parts.append("(titolo LIKE ? OR note LIKE ?)")
        params.extend([f"%{tok}%", f"%{tok}%"])
    where = " AND ".join(where_parts) if where_parts else "1=1"
    rows = conn.execute(
        f"SELECT archivio, titolo, url_catalogo, access_type, confidence "
        f"FROM fonti_indice WHERE {where} "
        f"AND url_catalogo IS NOT NULL AND url_catalogo != '' "
        f"ORDER BY confidence DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return rows


# ─── Contesto AI ─────────────────────────────────────────────────────────────

def _build_context(query: str, tipo: str, entities: list,
                   soldiers: list, sources: list) -> str:
    parts = [
        f"QUERY: {query}",
        f"TIPO: {tipo}",
        "",
        f"ENTITÀ TROVATE NEL DB ({len(entities)}):",
    ]
    for e in entities[:10]:
        parts.append(f"  - [{e['tipo']}] {e['valore']} (fonte: {e['fonte_tabella']})")

    parts += ["", f"FONTI ARCHIVISTICHE ({len(sources)}):"]
    for s in sources[:MAX_SOURCES_PER_ENTITY]:
        url = s.get("url_catalogo") or ""
        parts.append(f"  - {s.get('archivio','')}: {s.get('titolo','')[:80]} | {url[:80]}")

    parts += ["", f"SOLDATI COLLEGATI ({len(soldiers)}):"]
    for s in soldiers[:30]:
        sorte = s.get("sorte") or "?"
        cattura = s.get("luogo_cattura") or "?"
        internamento = s.get("luogo_internamento") or "?"
        parts.append(
            f"  - {s.get('grado','')} {s.get('cognome','')} {s.get('nome','')} "
            f"| cattura: {cattura} | internamento: {internamento} | sorte: {sorte}"
        )
    if len(soldiers) > 30:
        parts.append(f"  ... e altri {len(soldiers)-30} soldati.")

    ctx = "\n".join(parts)
    if len(ctx) > MAX_CONTEXT_CHARS:
        ctx = ctx[:MAX_CONTEXT_CHARS] + "\n[...troncato per limite token]"
    return ctx


# ─── AI Narrative ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Sei un ricercatore storico specializzato nella Seconda Guerra Mondiale e negli "
    "Internati Militari Italiani (IMI). Rispondi SOLO con dati verificabili dalle fonti "
    "fornite. Non inventare nomi, date, o fatti. Se un dato è incerto, indicalo. "
    "Rispondi in italiano. Struttura la risposta come: "
    "1) Contesto storico (200-300 parole) "
    "2) Analisi delle fonti disponibili "
    "3) Soldati/personaggi coinvolti (lista) "
    "4) Lacune documentali e suggerimenti di ricerca."
)

USER_PROMPT_TEMPLATE = (
    "Genera un report storico dettagliato su: {query}\n\n"
    "Usa ESCLUSIVAMENTE i seguenti dati dal database:\n\n{context}"
)


def _call_openai(prompt: str) -> Optional[str]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.warning("OpenAI error: %s", e)
        return None


def _call_anthropic(prompt: str) -> Optional[str]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        log.warning("Anthropic error: %s", e)
        return None


def _call_mistral(prompt: str) -> Optional[str]:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        return None
    try:
        from mistralai import Mistral
        client = Mistral(api_key=key)
        resp = client.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.warning("Mistral error: %s", e)
        return None


def _generate_narrative(prompt: str) -> dict:
    """Fallback chain: OpenAI → Anthropic → Mistral."""
    for fn, name in [(_call_openai, "openai"), (_call_anthropic, "anthropic"),
                     (_call_mistral, "mistral")]:
        text = fn(prompt)
        if text:
            return {"ok": True, "narrative": text, "model": name}
    return {"ok": False, "narrative": "", "model": None,
            "error": "Nessuna AI disponibile — verifica le chiavi API in .env"}


# ─── Report principale ────────────────────────────────────────────────────────

def generate_report(query: str, tipo: str = "auto") -> dict:
    """Genera un report storico completo per una query.

    Args:
        query: Es. "Battaglia di Cassino" / "GAIASCHI LUIGI" / "17 Divisione"
        tipo:  "evento" | "unita" | "luogo" | "persona" | "auto"

    Returns:
        dict con narrative, soldiers, sources, entities, metadata
    """
    start = datetime.now()
    log.info("report: query='%s' tipo='%s'", query, tipo)

    # Auto-detection tipo
    if tipo == "auto":
        q_low = query.lower()
        if any(k in q_low for k in ["battag","operazion","campagna","assedio","offensiv","eccidio"]):
            tipo = "evento"
        elif any(k in q_low for k in ["divisione","reggimento","battaglione","brigata","corpo"]):
            tipo = "unita"
        elif any(k in q_low for k in ["lager","stalag","oflag","campo","berlino","berlín","hannover"]):
            tipo = "luogo"
        else:
            tipo = "persona"

    # 1. Entità dal DB
    entities = _search_entities(query, tipo=(tipo if tipo != "persona" else None), limit=20)
    entity_ids = [e["id"] for e in entities]

    # 2. Soldati collegati
    soldiers = _get_soldiers_for_entity(entity_ids)

    # Se tipo persona, cerca direttamente in internati
    if tipo == "persona" and not soldiers:
        conn = get_conn()
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        tokens = query.split()
        where_parts = []
        params = []
        for tok in tokens:
            if len(tok) > 2:
                where_parts.append("(cognome LIKE ? OR nome LIKE ?)")
                params.extend([f"%{tok}%", f"%{tok}%"])
        if where_parts:
            where = " AND ".join(where_parts)
            soldiers = conn.execute(
                f"SELECT id, cognome, nome, grado, luogo_cattura, "
                f"luogo_internamento, sorte, data_cattura "
                f"FROM internati WHERE {where} LIMIT 50",
                params
            ).fetchall()
        conn.close()

    # 3. Fonti archivistiche
    sources = _get_fonti_indice_for_query(query)
    for eid in entity_ids[:5]:
        sources += _get_sources_for_entity(eid)
    # Dedup per URL
    seen_urls = set()
    sources_dedup = []
    for s in sources:
        url = s.get("url_catalogo") or ""
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources_dedup.append(s)
    sources = sources_dedup[:MAX_SOURCES_PER_ENTITY * 2]

    # 4. Arricchisci soldati con fonti
    soldiers_enriched = []
    for sol in soldiers:
        fonti_sol = _get_sources_for_soldier(sol["id"])
        soldiers_enriched.append({
            "id": sol["id"],
            "cognome": sol.get("cognome",""),
            "nome": sol.get("nome",""),
            "grado": sol.get("grado",""),
            "luogo_cattura": sol.get("luogo_cattura",""),
            "luogo_internamento": sol.get("luogo_internamento",""),
            "sorte": sol.get("sorte",""),
            "data_cattura": sol.get("data_cattura",""),
            "fonti": [
                {"archivio": f.get("archivio",""), "titolo": f.get("titolo","")[:60],
                 "url": f.get("url_catalogo",""), "access": f.get("access_type","online")}
                for f in fonti_sol
            ],
        })

    # 5. Genera narrative AI
    context = _build_context(query, tipo, entities, soldiers, sources)
    prompt  = USER_PROMPT_TEMPLATE.format(query=query, context=context)
    ai_res  = _generate_narrative(prompt)

    elapsed = (datetime.now() - start).total_seconds()
    return {
        "ok": True,
        "query": query,
        "tipo": tipo,
        "generated_at": start.isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 2),
        "ai_model": ai_res.get("model"),
        "narrative": ai_res.get("narrative",""),
        "soldiers": soldiers_enriched,
        "soldiers_total": len(soldiers_enriched),
        "sources": [
            {"archivio": s.get("archivio",""), "titolo": s.get("titolo","")[:80],
             "url": s.get("url_catalogo",""), "access": s.get("access_type","online")}
            for s in sources
        ],
        "sources_total": len(sources),
        "entities": [
            {"id": e["id"], "tipo": e["tipo"], "valore": e["valore"]}
            for e in entities
        ],
    }
