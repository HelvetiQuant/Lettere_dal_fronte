"""Biografie narrative — sintesi AI dei dati gia' aggregati su un soldato o un evento.

Non reinventa la ricerca: riusa la pipeline esistente cosi' com'e'.
  - Soldato → soldier_dashboard.get_soldier_dashboard() (dati certi, timeline,
    fonti locali, fonti esterne federate — gia' tutto orchestrato).
  - Evento / query libera → memory_router.route_query(use_cloud_fallback=False)
    (lo stesso Memory Router ippocampale: sql_exact → fts/BM25 → graph →
    archivio_fonti, con verified_sources gia' separate da image_only_sources).

Principio "nessun dato inventato": nel prompt di sintesi entrano SOLO
  1) fatti locali certi (tabelle sorgente)
  2) fonti gia' verificate/leggibili (archivio_fonti readable, testo_ocr di
     menzioni/fondi/NARA, fonti_indice con fetch_status='scaricato' + cache
     testuale, lettere OCR importate in import_ocr_lettere/ocr_lettere.db)
  3) contesto storico web con citazioni verificabili (Perplexity, URL espliciti)
Le fonti esterne trovate ma non ancora recuperate (federated_search,
image_only_sources, fetch_status != 'scaricato') vengono SOLO elencate come
"da verificare" in una sezione separata del prompt — l'AI ha istruzioni
esplicite di non usarle per scrivere il testo.

Orchestrazione AI: la scrittura finale della biografia usa i 4 provider gia'
configurati in ai_research.PROVIDERS (gpt, claude, mistral, perplexity) con
FALLBACK SEQUENZIALE automatico — stesso principio di resilienza del fallback
Perplexity nel Memory Router, esteso qui a tutta la catena, cosi' una singola
biografia costa una sola chiamata AI (non 4, a differenza di ai_research.
research_all che le confronta tutte apposta per il pannello "Tutti i provider").

Scrittura sui DB: SOLO INSERT su ai_ricerche, lo stesso meccanismo di logging
gia' usato da ai_research.py per ogni ricerca AI. Nessuna tabella esistente
viene alterata; import_ocr_lettere/ocr_lettere.db viene solo interrogato
in lettura (mai scritto).
"""
import sqlite3
from pathlib import Path
from typing import Optional

import requests

from database import get_conn, save_ai_ricerca
from credits import log_openai_usage, log_mistral_ocr
from extractor import _get_client, _get_mistral_client
import ai_research as air
from soldier_dashboard import get_soldier_dashboard

# DB delle lettere importato in sola lettura da CascadeProjects/ocr_lettere
# (vedi import_ocr_lettere/). Non e' stato fuso in imi_internati.db per
# scelta esplicita: nessuna scrittura sui DB esistenti durante l'import.
_LETTERE_DB = Path(__file__).parent / "import_ocr_lettere" / "ocr_lettere.db"

# Ordine di fallback per la scrittura della biografia: se il provider
# preferito (o il primo della lista) fallisce — chiave API assente, rate
# limit, errore rete — si passa automaticamente al successivo.
_FALLBACK_ORDER = ["gpt", "claude", "mistral", "perplexity"]

BIOGRAPHY_PROMPT = """Sei un ricercatore storico. Scrivi una biografia/dossier narrativo in
italiano, in prosa (NON elenchi puntati), basato ESCLUSIVAMENTE sui dati e
sulle fonti gia' verificate elencate sotto. Non inventare nulla: se un dato
manca, dillo esplicitamente invece di supporlo.

Regole:
1. Ogni affermazione di fatto deve riportare tra parentesi quadre la fonte da
   cui proviene, es. [INTERNATI], [ARCHIVIO_FONTI #123], [LETTERE #4],
   [WEB #1] per le fonti online verificate elencate sotto.
2. Struttura OBBLIGATORIA del report, con questi titoli di sezione:
   ## SINTESI — 3-5 righe con i fatti essenziali accertati.
   ## RICOSTRUZIONE CRONOLOGICA — prosa in ordine cronologico (nascita,
      arruolamento, cattura/eventi bellici, internamento/decorazione, esito),
      ogni fatto con la sua citazione tra parentesi quadre.
   ## CONTESTO STORICO — solo se supportato dalle fonti online verificate
      sotto (citare [WEB #n]); altrimenti ometti la sezione.
   ## FONTI CITATE — elenco numerato di TUTTE le fonti effettivamente usate
      nel testo, una per riga, con identificativo e (se disponibile) URL.
   ## LACUNE — cosa NON e' stato trovato nei dati forniti e andrebbe cercato
      altrove (indica archivio/fonte suggerita).
   ## FONTI DA VERIFICARE — le fonti esterne trovate ma non ancora
      recuperate (solo elencate, MAI usate nel testo).
3. Non usare MAI le fonti "da verificare" per affermazioni di fatto.
4. Se una data o un luogo e' incerto o discordante tra le fonti, segnalalo
   esplicitamente indicando entrambe le versioni con le rispettive fonti.

=== SOGGETTO ===
{subject_label}

=== DATI E FONTI VERIFICATE (uniche utilizzabili nel testo) ===
{verified_context}

=== FONTI ONLINE VERIFICATE (contesto storico con citazioni web, utilizzabili con [WEB #n]) ===
{online_context}

=== FONTI TROVATE MA NON ANCORA VERIFICATE (solo da elencare, non usare) ===
{unverified_context}
"""


# ─── Provider dispatch (riusa client/costi gia' configurati in ai_research) ────

def _dispatch(provider: str, system: str, prompt: str):
    """Esegue la chiamata al provider richiesto. Solleva eccezione se fallisce
    (chiave mancante, errore rete, ecc.) cosi' che _call_with_fallback passi
    al provider successivo."""
    if provider == "gpt":
        client = _get_client()
        model = air.PROVIDERS["gpt"]["model"]
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        risposta = resp.choices[0].message.content.strip()
        cost = 0.0
        if getattr(resp, "usage", None):
            log_openai_usage(model, resp.usage.prompt_tokens or 0,
                              resp.usage.completion_tokens or 0, lettera="BIOGRAFIA")
            cost = (resp.usage.prompt_tokens or 0) * (0.15 / 1_000_000) + \
                   (resp.usage.completion_tokens or 0) * (0.60 / 1_000_000)
        return risposta, model, cost

    if provider == "claude":
        if air.anthropic is None:
            raise RuntimeError("Anthropic SDK non installato (pip install anthropic)")
        api_key = air._load_anthropic_key()
        model = air.PROVIDERS["claude"]["model"]
        client = air.anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=4096, system=system,
            messages=[{"role": "user", "content": prompt}], temperature=0.3,
        )
        risposta = resp.content[0].text.strip()
        cost = resp.usage.input_tokens * (3.0 / 1_000_000) + resp.usage.output_tokens * (15.0 / 1_000_000)
        log_openai_usage(model, resp.usage.input_tokens, resp.usage.output_tokens, lettera="BIOGRAFIA")
        return risposta, model, cost

    if provider == "mistral":
        client = _get_mistral_client()
        model = air.PROVIDERS["mistral"]["model"]
        resp = client.chat.complete(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=4096, temperature=0.3,
        )
        risposta = resp.choices[0].message.content.strip()
        cost = (len(prompt) // 4) * (2.0 / 1_000_000) + (len(risposta) // 4) * (6.0 / 1_000_000)
        log_mistral_ocr(0, lettera="BIOGRAFIA")
        return risposta, model, cost

    if provider == "perplexity":
        api_key = air._load_perplexity_key()
        model = air.PROVIDERS["perplexity"]["model"]
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "max_tokens": 4096, "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        risposta = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        in_tok, out_tok = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        cost = in_tok * (1.0 / 1_000_000) + out_tok * (1.0 / 1_000_000)
        log_openai_usage(model, in_tok, out_tok, lettera="BIOGRAFIA")
        return risposta, model, cost

    raise ValueError(f"Provider sconosciuto: {provider}")


def _call_with_fallback(system: str, prompt: str, tag: str, preferred: Optional[str] = None) -> dict:
    order = ([preferred] if preferred in _FALLBACK_ORDER else []) + \
            [p for p in _FALLBACK_ORDER if p != preferred]
    attempted = []
    for provider in order:
        try:
            risposta, model, cost = _dispatch(provider, system, prompt)
            rid = save_ai_ricerca(f"[BIOGRAFIA] {tag}", provider, model, risposta, prompt[:5000], cost)
            return {
                "ok": True, "id": rid, "provider": provider, "model": model,
                "risposta": risposta, "cost_usd": cost,
                "fallback_used": provider != order[0], "attempted_before_success": attempted,
            }
        except Exception as e:
            attempted.append({"provider": provider, "error": str(e)})
            continue
    return {"ok": False, "error": "Tutti i provider AI configurati hanno fallito.", "attempted": attempted}


# ─── Contesto: soldato (riusa soldier_dashboard, aggiunge lettere + fonti fetchate) ──

def _find_letters_mentioning(cognome: str) -> list[dict]:
    """Cerca nel DB lettere importato (sola lettura) menzioni del cognome."""
    if not cognome or not _LETTERE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(_LETTERE_DB))
        conn.row_factory = sqlite3.Row
        like = f"%{cognome}%"
        rows = conn.execute(
            """SELECT id, filename, mittente, destinatario, data_lettera, luogo,
                      oggetto, corpo_testo, confidenza
               FROM lettere
               WHERE mittente LIKE ? OR destinatario LIKE ? OR corpo_testo LIKE ?
               LIMIT 10""",
            (like, like, like),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _verified_fetched_external(cues: dict) -> list[dict]:
    """Fonti esterne gia' scaricate (fetch_status='scaricato' in fonti_indice),
    quindi trattabili come verificate — stesso criterio di 'disponibilita
    locale' usato altrove nell'app (source_locator / analyze_sources)."""
    persona = (cues.get("persona") or "").strip()
    reparto = (cues.get("reparto") or "").strip()
    if not persona and not reparto:
        return []
    conn = get_conn()
    like_parts, params = [], []
    if persona:
        like_parts += ["fi.persone_possibili LIKE ?", "fi.titolo LIKE ?"]
        params += [f"%{persona}%", f"%{persona}%"]
    if reparto:
        like_parts.append("fi.reparto LIKE ?")
        params.append(f"%{reparto}%")
    try:
        rows = conn.execute(
            f"""SELECT fi.id, fi.archivio, fi.titolo, fi.reparto, fi.luogo,
                       sfc.path_file, sfc.content_type
                FROM fonti_indice fi
                LEFT JOIN source_fetch_cache sfc ON sfc.source_id = fi.id
                WHERE fi.fetch_status = 'scaricato' AND ({" OR ".join(like_parts)})
                LIMIT 5""",
            params,
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        excerpt = ""
        path_file, content_type = d.get("path_file"), d.get("content_type") or ""
        if path_file and content_type.startswith("text/"):
            try:
                with open(path_file, "r", encoding="utf-8", errors="replace") as f:
                    excerpt = f.read()[:1500]
            except OSError:
                pass
        d["excerpt"] = excerpt
        out.append(d)
    return out


def _soldier_verified_context(dash: dict) -> str:
    s = dash.get("soldier", {})
    parts = [
        "[INTERNATI] " + ", ".join(
            f"{k}={v}" for k, v in s.items()
            if v not in (None, "", 0) and k not in ("raw_text", "id", "needs_review", "review_reason")
        )
    ]
    for f in dash.get("facts", []):
        if f.get("verified"):
            parts.append(f"- {f['fact']}: {f['value']}")

    if dash.get("timeline"):
        parts.append("\nTIMELINE:")
        for t in dash["timeline"]:
            parts.append(f"- {t.get('date', '?')}: {t.get('event', '')} a {t.get('place', '') or '?'} [{t.get('source', 'locale')}]")

    local = dash.get("local_sources", [])
    if local:
        parts.append("\nFONTI LOCALI (documenti/menzioni gia' presenti):")
        for r in local:
            excerpt = r.get("ocr_excerpt") or r.get("context") or ""
            parts.append(f"- [{r.get('table', '').upper()} #{r.get('id')}] {r.get('titolo', '')}{(' — ' + excerpt) if excerpt else ''}")

    letters = _find_letters_mentioning(s.get("cognome", ""))
    if letters:
        parts.append("\nLETTERE (archivio posta importato, corrispondenza dal fronte):")
        for l in letters:
            corpo = (l.get("corpo_testo") or "")[:300]
            parts.append(
                f"- [LETTERE #{l['id']}] {l.get('data_lettera') or '?'} — "
                f"da {l.get('mittente') or '?'} a {l.get('destinatario') or '?'}, {l.get('luogo') or ''}: {corpo}"
            )

    fetched = _verified_fetched_external(dash.get("cues", {}))
    if fetched:
        parts.append("\nFONTI ESTERNE GIA' SCARICATE E VERIFICATE:")
        for r in fetched:
            parts.append(f"- [{(r.get('archivio') or '?').upper()}] {r.get('titolo', '')}{(' — ' + r['excerpt']) if r.get('excerpt') else ''}")

    return "\n".join(parts)


def _soldier_unverified_context(dash: dict) -> str:
    pending = [r for r in dash.get("external_sources", [])
               if r.get("availability") not in ("locale",) and not r.get("error")]
    if not pending:
        return "Nessuna."
    lines = []
    for r in pending[:15]:
        titolo = r.get("titolo") or r.get("title") or "(senza titolo)"
        provider = r.get("provider") or r.get("archivio") or "?"
        lines.append(f"- [{provider.upper()}] {titolo} (stato: {r.get('availability', 'online')})")
    return "\n".join(lines)


# ─── Contesto: evento / query libera (riusa memory_router.route_query) ────

def _event_verified_context(query: str, routed: dict) -> str:
    parts = [f"Query originale: {query}", f"Cue estratti: {routed.get('cues', {})}"]
    verified = routed.get("verified_sources", [])
    if not verified:
        parts.append("Nessuna fonte locale verificata trovata nel Memory Router per questa query.")
    for r in verified:
        d = r.get("data", {})
        label = d.get("valore") or d.get("titolo_documento") or \
            f"{d.get('cognome', '')} {d.get('nome', '')}".strip() or r.get("table", "")
        excerpt = (d.get("testo_ocr") or d.get("contesto") or "")[:300]
        parts.append(f"- [{r.get('source', '').upper()}:{r.get('table', '')}] {label}{(' — ' + excerpt) if excerpt else ''}")
    return "\n".join(parts)


def _event_unverified_context(routed: dict, ext_candidates: list[dict]) -> str:
    lines = []
    for r in routed.get("image_only_sources", []):
        d = r.get("data", {})
        lines.append(f"- [ARCHIVIO_FONTI #{d.get('id')}] {d.get('titolo_documento', '')} (immagine non OCR-verificata)")
    for r in ext_candidates:
        if r.get("error"):
            continue
        titolo = r.get("titolo") or r.get("title") or "(senza titolo)"
        lines.append(f"- [{(r.get('provider') or '?').upper()}] {titolo} (non ancora recuperata)")
    return "\n".join(lines) if lines else "Nessuna."


# ─── Fonti online verificate (Perplexity con citazioni web) ────────────────

def _online_verified_context(subject_label: str) -> tuple[str, list[dict]]:
    """Interroga Perplexity (ricerca web con citazioni) per contesto storico
    VERIFICABILE: ogni fatto restituito e' ancorato a un URL citato.
    Ritorna (testo_contesto, [{title, url}, ...]).
    Fallisce in silenzio (contesto vuoto) se la chiave manca o la rete non va:
    il dossier resta generabile dalle sole fonti locali."""
    try:
        api_key = air._load_perplexity_key()
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": air.PROVIDERS["perplexity"]["model"],
                "messages": [
                    {"role": "system", "content": "Sei un ricercatore storico. Riporta SOLO fatti documentati da fonti attendibili (archivi, enti pubblici, pubblicazioni storiche). Niente speculazioni."},
                    {"role": "user", "content": (
                        f"Contesto storico documentato su: {subject_label}. "
                        "Riassumi in max 400 parole i fatti verificabili (date, luoghi, "
                        "reparti, eventi) utili a un dossier storico. Ogni fatto deve "
                        "derivare dalle fonti che citi."
                    )},
                ],
                "max_tokens": 1024, "temperature": 0.2,
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        testo = data["choices"][0]["message"]["content"].strip()
        sources = []
        for sr in data.get("search_results", []) or []:
            if sr.get("url"):
                sources.append({"title": sr.get("title") or sr["url"], "url": sr["url"]})
        if not sources:
            sources = [{"title": u, "url": u} for u in (data.get("citations", []) or [])]
        if not sources:
            return "Nessuna fonte online verificata disponibile.", []
        numbered = "\n".join(f"[WEB #{i+1}] {s['title']} — {s['url']}" for i, s in enumerate(sources))
        return f"{testo}\n\nELENCO FONTI WEB (usa questi numeri per citare):\n{numbered}", sources
    except Exception:
        return "Nessuna fonte online verificata disponibile (ricerca web non riuscita).", []


def _verified_labels_soldier(dash: dict) -> list[str]:
    """Elenco leggibile delle fonti locali verificate usate per il dossier
    soldato (restituito al frontend, cosi' l'utente vede QUALI sono)."""
    labels = ["[INTERNATI] scheda IMI Archivio di Stato di Bolzano"]
    for r in dash.get("local_sources", []):
        labels.append(f"[{(r.get('table') or '').upper()} #{r.get('id')}] {r.get('titolo', '') or '(documento locale)'}")
    letters = _find_letters_mentioning(dash.get("soldier", {}).get("cognome", ""))
    for l in letters:
        labels.append(f"[LETTERE #{l['id']}] {l.get('data_lettera') or '?'} — da {l.get('mittente') or '?'} a {l.get('destinatario') or '?'}")
    fetched = _verified_fetched_external(dash.get("cues", {}))
    for r in fetched:
        labels.append(f"[{(r.get('archivio') or '?').upper()}] {r.get('titolo', '')} (scaricata e verificata)")
    return labels


def _verified_labels_event(routed: dict) -> list[str]:
    labels = []
    for r in routed.get("verified_sources", []):
        d = r.get("data", {})
        label = d.get("valore") or d.get("titolo_documento") or \
            f"{d.get('cognome', '')} {d.get('nome', '')}".strip() or r.get("table", "")
        labels.append(f"[{(r.get('source') or '').upper()}:{r.get('table', '')}] {label}")
    return labels


def _event_centric_context(query: str) -> tuple[str, list[dict]]:
    """Interroga event_query_engine per dati strutturati sull'evento.
    Ritorna (testo_contesto, lista_fonti_con_url).
    Fallisce in silenzio se event_query_engine non trova l'evento."""
    try:
        from event_query_engine import query_event
        result = query_event(query, verbose=False)
        if not result.get("ok"):
            return "", []

        lines = []
        sources = []

        ev = result.get("event", {})
        lines.append(f"[EVENT_DB] Evento: {ev.get('nome', query)}")
        lines.append(f"[EVENT_DB] Date: {ev.get('data_inizio', '?')} - {ev.get('data_fine', '?')}")
        lines.append(f"[EVENT_DB] Luogo: {ev.get('luogo', '?')}")
        lines.append(f"[EVENT_DB] Descrizione: {ev.get('descrizione', '')}")

        caduti = result.get("caduti", {})
        if caduti.get("count", 0) > 0:
            lines.append(f"[EVENT_DB] Caduti collegati: {caduti['count']}")
            for luogo, n in (caduti.get("top_luoghi") or [])[:5]:
                lines.append(f"[EVENT_DB]   Caduti a {luogo}: {n}")
            for anno, n in (caduti.get("top_anni") or [])[:5]:
                lines.append(f"[EVENT_DB]   Caduti anno {anno}: {n}")
            for reparto, n in (caduti.get("top_reparti") or [])[:5]:
                lines.append(f"[EVENT_DB]   Reparto {reparto}: {n}")

        decorati = result.get("decorati", {})
        if decorati.get("count", 0) > 0:
            lines.append(f"[EVENT_DB] Decorati collegati: {decorati['count']}")
            for dec, n in (decorati.get("top_decorazioni") or [])[:5]:
                lines.append(f"[EVENT_DB]   Decorazione {dec}: {n}")

        doc_links = result.get("documenti", {}).get("items", [])
        if doc_links:
            lines.append(f"[EVENT_DB] Documenti collegati: {len(doc_links)}")
            for d in doc_links[:10]:
                title = d.get("title") or d.get("description") or "(senza titolo)"
                url = d.get("source_url") or ""
                lines.append(f"[EVENT_DB]   Doc: {title[:80]}  URL: {url}")
                if url:
                    sources.append({"title": title, "url": url})

        fonti_links = result.get("fonti", {}).get("items", [])
        if fonti_links:
            lines.append(f"[EVENT_DB] Fonti archivistiche: {len(fonti_links)}")
            for f in fonti_links[:10]:
                title = f.get("titolo") or "(senza titolo)"
                url = f.get("url_catalogo") or f.get("url_file") or ""
                lines.append(f"[EVENT_DB]   Fonte: {title[:80]}  Archivio: {f.get('archivio', '?')}  URL: {url}")
                if url:
                    sources.append({"title": title, "url": url})

        return "\n".join(lines), sources
    except Exception:
        return "", []


# ─── Entry point pubblici ──────────────────────────────────────────────────

def generate_soldier_biography(soldier_id: int, provider: Optional[str] = None) -> dict:
    dash = get_soldier_dashboard(soldier_id)
    if not dash.get("ok"):
        return dash

    s = dash["soldier"]
    label = f"Soldato: {s.get('nome', '')} {s.get('cognome', '')} (internati id={soldier_id})".strip()
    verified = _soldier_verified_context(dash)
    unverified = _soldier_unverified_context(dash)
    online_ctx, online_sources = _online_verified_context(label)
    prompt = BIOGRAPHY_PROMPT.format(subject_label=label, verified_context=verified,
                                     online_context=online_ctx, unverified_context=unverified)

    result = _call_with_fallback(
        system="Sei un ricercatore storico specializzato in Internati Militari Italiani (IMI), caduti e decorati dei conflitti italiani del '900.",
        prompt=prompt, tag=f"soldato #{soldier_id} — {s.get('cognome', '')} {s.get('nome', '')}",
        preferred=provider,
    )
    result["subject_type"] = "soldier"
    result["soldier_id"] = soldier_id
    result["dashboard_summary"] = dash.get("summary")
    result["unverified_sources_count"] = len([
        r for r in dash.get("external_sources", []) if r.get("availability") != "locale"
    ])
    # Elenco fonti restituito al frontend: l'utente vede QUALI fonti sono
    # state usate (locali e web, con link), non solo un conteggio.
    result["verified_sources"] = _verified_labels_soldier(dash)
    result["online_sources"] = online_sources
    return result


def generate_event_biography(query: str, provider: Optional[str] = None) -> dict:
    import memory_router as mr
    routed = mr.route_query(query, use_cloud_fallback=False)
    cues = routed.get("cues", {})

    ext_candidates = []
    try:
        from source_providers.federation import federated_search
        priority_providers = ["nara", "antenati", "cwgc", "ussme", "archivio_stato",
                               "europeana", "internetarchive"]
        ext_candidates = federated_search(query, cues=cues, providers=priority_providers)
    except Exception:
        pass

    verified = _event_verified_context(query, routed)
    unverified = _event_unverified_context(routed, ext_candidates)
    online_ctx, online_sources = _online_verified_context(f"Evento: {query}")

    # Event-centric data from event_query_engine
    event_ctx, event_sources = _event_centric_context(query)
    if event_ctx:
        verified = event_ctx + "\n\n" + verified
    if event_sources:
        online_sources = online_sources + event_sources

    prompt = BIOGRAPHY_PROMPT.format(subject_label=f"Evento: {query}", verified_context=verified,
                                     online_context=online_ctx, unverified_context=unverified)

    result = _call_with_fallback(
        system="Sei un ricercatore storico specializzato in eventi bellici italiani del '900 (reparti, battaglie, campi di internamento).",
        prompt=prompt, tag=f"evento: {query}", preferred=provider,
    )
    result["subject_type"] = "event"
    result["query"] = query
    result["cues"] = cues
    result["confidence_locale"] = routed.get("confidence")
    result["unverified_sources_count"] = len(routed.get("image_only_sources", [])) + \
        len([r for r in ext_candidates if not r.get("error")])
    result["verified_sources"] = _verified_labels_event(routed)
    if event_sources:
        result["verified_sources"] = result["verified_sources"] + [
            f"[EVENT_DB] {s['title']} — {s['url']}" for s in event_sources
        ]
    result["online_sources"] = online_sources
    return result


def generate_biography(subject_type: str, ref, provider: Optional[str] = None) -> dict:
    """Dispatcher usato dall'endpoint /api/biography."""
    if subject_type == "soldier":
        return generate_soldier_biography(int(ref), provider=provider)
    if subject_type == "event":
        return generate_event_biography(str(ref), provider=provider)
    return {"ok": False, "error": f"subject_type sconosciuto: {subject_type}"}
