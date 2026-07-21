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
italiano, in prosa (NON elenchi puntati), basato sui dati e sulle fonti
verificate elencate sotto, INTEGRANDO sia le fonti locali che le fonti web.
Non inventare nulla: se un dato manca, dillo esplicitamente invece di supporlo.

Regole:
1. Ogni affermazione di fatto deve riportare tra parentesi quadre la fonte da
   cui proviene, es. [INTERNATI], [ARCHIVIO_FONTI #123], [LETTERE #4],
   [WEB #1] per le fonti online verificate elencate sotto.
2. Struttura OBBLIGATORIA del report, con questi titoli di sezione:
   ## SINTESI — 3-5 righe con i fatti essenziali accertati.
   ## RICOSTRUZIONE CRONOLOGICA — prosa in ordine cronologico (nascita,
      arruolamento, cattura/eventi bellici, internamento/decorazione, esito).
      Integra qui TUTTI i fatti disponibili, sia dalle fonti locali che web.
      Ogni fatto con la sua citazione tra parentesi quadre.
   ## CONTESTO STORICO — usa le fonti online verificate [WEB #n] per
      inquadrare il contesto storico-militare (reparti, operazioni, campi di
      internamento, condizioni di prigionia, rimpatrio). Se non ci sono fonti
      web, ometti la sezione.
   ## FONTI CITATE — elenco numerato di TUTTE le fonti effettivamente usate
      nel testo, una per riga, con identificativo e (se disponibile) URL.
   ## LACUNE — cosa NON e' stato trovato nei dati forniti e andrebbe cercato
      altrove (indica archivio/fonte suggerita).
   ## FONTI DA VERIFICARE — le fonti esterne trovate ma non ancora
      recuperate (solo elencate, MAI usate nel testo).
3. Non usare MAI le fonti "da verificare" per affermazioni di fatto.
4. Se una data o un luogo e' incerto o discordante tra le fonti, segnalalo
   esplicitamente indicando entrambe le versioni con le rispettive fonti.
5. Le fonti web verificate [WEB #n] hanno la STESSA dignita' delle fonti locali:
   usale attivamente nella narrazione, non solo nel contesto storico.
   Se il web fornisce dati aggiuntivi (es. medaglie, memoriali, testimonianze
   familiari, progetti storici regionali), integrali nella ricostruzione.

=== SOGGETTO ===
{subject_label}

=== DATI E FONTI VERIFICATE (fonti locali, utilizzabili nel testo) ===
{verified_context}

=== FONTI ONLINE VERIFICATE (ricerche web con citazioni, utilizzabili con [WEB #n]) ===
{online_context}

=== FONTI TROVATE MA NON ANCORA VERIFICATE (solo da elencare, non usare) ===
{unverified_context}
"""


EVENT_REPORT_PROMPT = """Sei un ricercatore storico. Analizza TUTTE le fonti verificate elencate sotto
sull'evento indicato e produci un report OGGETTIVO che riporta SOLO i fatti su cui
le fonti CONVERGONO (punti in comune tra piu' fonti). Non inventare nulla: se un dato
non e' confermato da almeno due fonti indipendenti, non includerlo nei fatti accertati.

Regole:
1. Ogni affermazione di fatto deve riportare tra parentesi quadre la fonte da cui
   proviene, es. [EVENT_DB], [ARCHIVIO_FONTI #123], [WEB #1].
2. Un fatto e' considerato "accertato" solo se confermato da almeno 2 fonti indipendenti
   (es. EVENT_DB + WEB #1, oppure due fonti web diverse). Fatti supportati da una sola
   fonte vanno nella sezione CONVERGENZE PARZIALI.
3. Struttura OBBLIGATORIA del report, con questi titoli di sezione:
   ## FATTI ACCERTATI — solo fatti confermati da 2+ fonti indipendenti, in prosa
      discorsiva (non elenchi puntati). Ogni fatto con citazioni multiple.
   ## CONVERGENZE TRA FONTI — elenca esplicitamente quali fonti concordano su quali
      punti (es. "Data: EVENT_DB e WEB #1 concordano su...").
   ## CONVERGENZE PARZIALI — fatti supportati da una sola fonte, con citazione.
   ## DIVERGENZE — dove le fonti NON concordano, riporta entrambe le versioni con
      le rispettive fonti. Se non ci sono divergenze, scrivi "Nessuna divergenza rilevata."
   ## FONTI CITATE — elenco numerato di TUTTE le fonti effettivamente usate nel report,
      una per riga, con identificativo e (se disponibile) URL.
4. Non usare MAI fonti non verificate per affermazioni di fatto.
5. Se i dati sono insufficienti per un report, scrivi esplicitamente quali fonti
   mancano e cosa servirebbe per completare l'analisi.

=== EVENTO ===
{subject_label}

=== DATI E FONTI VERIFICATE (uniche utilizzabili nel report) ===
{verified_context}

=== FONTI ONLINE VERIFICATE (contesto storico con citazioni web, utilizzabili con [WEB #n]) ===
{online_context}

=== FONTI TROVATE MA NON ANCORA VERIFICATE (solo da elencare, non usare) ===
{unverified_context}
"""


CHRONOLOGICAL_REPORT_PROMPT = """Sei un ricercatore storico. Produci una ricostruzione CRONOLOGICA e NARRATIVA
dell'evento indicato, basata ESCLUSIVAMENTE sulle fonti verificate elencate sotto.
La narrazione deve essere discorsiva (in prosa, NON elenchi puntati) e seguire
l'ordine cronologico dei fatti, dal contesto pre-evento fino alle conseguenze.

Regole:
1. Ogni affermazione di fatto deve riportare tra parentesi quadre la fonte da
   cui proviene, es. [EVENT_DB], [ARCHIVIO_FONTI #123], [WEB #1].
2. Struttura OBBLIGATORIA del report, con questi titoli di sezione:
   ## CONTESTO GENERALE — situazione storica e geopolitica prima dell'evento,
      in prosa discorsiva. Solo fatti supportati dalle fonti.
   ## CRONOLOGIA DEI FATTI — il cuore del report: narrazione in ordine
   cronologico, dal primo evento rilevante fino all'epilogo. Ogni fatto con la
   sua citazione tra parentesi quadre. Usa paragrafi, non elenchi.
   ## PROTAGONISTI — persone, reparti e unita' militari coinvolti, descritti
      in prosa con il loro ruolo nell'evento.
   ## FONTI CITATE — elenco numerato di TUTTE le fonti effettivamente usate
      nel testo, una per riga, con identificativo e (se disponibile) URL.
3. Non inventare nulla: se un dato non e' nelle fonti, scrivi esplicitamente
   che non e' disponibile.
4. Se date o luoghi sono incerti o discordanti tra le fonti, segnalalo nel
   testo indicando entrambe le versioni con le rispettive fonti.

=== EVENTO ===
{subject_label}

=== DATI E FONTI VERIFICATE (uniche utilizzabili nel testo) ===
{verified_context}

=== FONTI ONLINE VERIFICATE (contesto storico con citazioni web, utilizzabili con [WEB #n]) ===
{online_context}

=== FONTI TROVATE MA NON ANCORA VERIFICATE (solo da elencare, non usare) ===
{unverified_context}
"""


SOURCE_ANALYSIS_PROMPT = """Sei un ricercatore storico e archivista. Analizza la singola fonte indicata sotto
e produci un riassunto strutturato. Se la fonte non contiene immagini o documenti
multimediali, cerca sul web immagini e documenti correlati al contesto storico
della fonte.

Regole:
1. Struttura OBBLIGATORIA del report, con questi titoli di sezione:
   ## RIASSUNTO — sintesi della fonte in 3-5 righe (titolo, archivio, tipo,
      contenuto principale).
   ## CONTENUTO ANALIZZATO — analisi dettagliata del contenuto testuale
      disponibile (se in cache). Se non c'e' testo, descrivi cosa ci si
      aspetterebbe di trovare in questo tipo di fonte.
   ## IMMAGINI E DOCUMENTI TROVATI — elenca immagini e documenti trovati
      nella fonte o sul web. Per ogni risorsa: titolo, URL e breve descrizione.
      Se cerchi sul web, usa [WEB #n] per citare le fonti online.
   ## COLLEGAMENTI STORICI — come questa fonte si collega all'evento o alla
      persona oggetto della ricerca.
2. Non inventare dati: se non trovi immagini o documenti, dillo esplicitamente.
3. Cita sempre la fonte di origine di ogni informazione.

=== FONTE DA ANALIZZARE ===
{source_metadata}

=== CONTENUTO IN CACHE (se disponibile) ===
{source_content}

=== CONTESTO EVENTO ===
{event_context}
"""


IMAGE_PROMPT_GENERATOR = """Sei un esperto di ricostruzione storica visiva. Analizza il contenuto della fonte
storica indicata sotto e segui questi passi:

PASSO 1 — CHUNKING: Dividi il testo in sezioni tematiche significative
(es. "prigionieri di guerra", "ritirata", "trincee", "bombardamento").
Identifica i fatti storici concreti e visivamente rappresentabili in ogni chunk.

PASSO 2 — SELEZIONE EPISODI: Scegli da 3 a 5 episodi specifici piu'
significativi e visivamente evocativi. Preferisci scene con persone,
azioni, luoghi reali (es. "6000 prigionieri italiani marciati a piedi
verso i campi di prigionia in Austria", non concetti astratti).

PASSO 3 — GENERAZIONE PROMPT: Per ogni episodio, genera un prompt
in INGLESE, dettagliato (minimo 40 parole), che raffiguri la scena
in modo fotorealistic e storicamente accurato.

Regole:
1. Ogni prompt deve includere: "photorealistic, historical accuracy, detailed".
2. L'era storica deve essere corretta (WW1 = 1910s, WW2 = 1940s, ecc.).
3. Non includere volti riconoscibili di persone reali.
4. Basati SOLO sui fatti storici forniti nel testo della fonte.
5. Ogni prompt deve raffigurare un episodio SPECIFICO, non scene generiche.
6. Restituisci ESCLUSIVAMENTE un array JSON valido:
   [{{"prompt": "...", "title": "...", "chunk": "...", "episode": "..."}}]
   dove title e' una breve descrizione italiana dell'immagine,
   chunk e' il tema/sezione di appartenenza,
   episode e' la descrizione italiana dell'episodio storico raffigurato.
7. Genera tra 3 e 5 prompt, non di piu'.

=== CONTESTO FONTE ===
{source_metadata}

=== CONTENUTO FONTE (testo da dividere in chunk) ===
{source_content}

=== CONTESTO EVENTO ===
{event_context}
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


def _call_with_fallback(system: str, prompt: str, tag: str, preferred: Optional[str] = None,
                        fallback_order: Optional[list] = None) -> dict:
    base_order = fallback_order if fallback_order is not None else _FALLBACK_ORDER
    order = ([preferred] if preferred in base_order else []) + \
            [p for p in base_order if p != preferred]
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

def _online_verified_context(subject_label: str, soldier_data: dict = None) -> tuple[str, list[dict]]:
    """Interroga Perplexity (ricerca web con citazioni) per contesto storico
    VERIFICABILE: ogni fatto restituito e' ancorato a un URL citato.
    Ritorna (testo_contesto, [{title, url}, ...]).
    Fallisce in silenzio (contesto vuoto) se la chiave manca o la rete non va:
    il dossier resta generabile dalle sole fonti locali.

    Se soldier_data e' fornito, costruisce una query piu' specifica con
    nome, luogo di nascita, data, unita' militare, luogo di cattura/internamento
    per ottenere risultati web pertinenti al soldato specifico."""
    try:
        api_key = air._load_perplexity_key()

        # Build a specific query if soldier data is available
        if soldier_data:
            parts = []
            cognome = soldier_data.get("cognome", "")
            nome = soldier_data.get("nome", "")
            if cognome or nome:
                parts.append(f"{nome} {cognome}".strip())
            luogo_nascita = soldier_data.get("luogo_nascita", "")
            if luogo_nascita:
                parts.append(f"nato a {luogo_nascita}")
            data_nascita = soldier_data.get("data_nascita", "")
            if data_nascita:
                parts.append(f"il {data_nascita}")
            luogo_cattura = soldier_data.get("luogo_cattura", "")
            if luogo_cattura:
                parts.append(f"catturato a {luogo_cattura}")
            data_cattura = soldier_data.get("data_cattura", "")
            if data_cattura:
                parts.append(f"il {data_cattura}")
            luogo_internamento = soldier_data.get("luogo_internamento", "")
            if luogo_internamento:
                parts.append(f"internato a {luogo_internamento}")
            arbeitskommando = soldier_data.get("arbeitskommando", "")
            if arbeitskommando:
                parts.append(f"Arbeitskommando {arbeitskommando}")
            sorte = soldier_data.get("sorte", "")
            if sorte:
                parts.append(f"sorte: {sorte}")
            # Add IMI context for better web results
            parts.append("Internato Militare Italiano IMI seconda guerra mondiale")
            web_query = " ".join(parts)
        else:
            web_query = subject_label

        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": air.PROVIDERS["perplexity"]["model"],
                "messages": [
                    {"role": "system", "content": "Sei un ricercatore storico specializzato in Internati Militari Italiani (IMI) e storia militare italiana del '900. Riporta SOLO fatti documentati da fonti attendibili (archivi, enti pubblici, pubblicazioni storiche, memoriali). Niente speculazioni. Se trovi informazioni specifiche sulla persona cercata (data di nascita, luogo, reparto, campo di internamento, rimpatrio), riportale con precisione."},
                    {"role": "user", "content": (
                        f"Ricerca informazioni storiche documentate su: {web_query}. "
                        "Cerca in particolare: dati anagrafici, reparto militare di appartenenza, "
                        "luogo e data di cattura, campi di internamento, Arbeitskommando, "
                        "date di trasferimento, liberazione e rimpatrio. "
                        "Riassumi in max 500 parole tutti i fatti verificabili trovati. "
                        "Ogni fatto deve derivare dalle fonti che citi. "
                        "Se trovi informazioni su progetti memoriali (es. internatimilitaripiacentini.it, "
                        "lessicobiograficoimi.it, decretopresidenziale medaglie IMI), riportale."
                    )},
                ],
                "max_tokens": 2048, "temperature": 0.2,
            },
            timeout=60,
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
    online_ctx, online_sources = _online_verified_context(label, soldier_data=s)
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


def generate_event_report(query: str, provider: Optional[str] = None,
                         options: Optional[dict] = None, mode: str = "specialist") -> dict:
    """Genera la scheda per il tab 'punti_di_vista' (default)."""
    return generate_event_tab_report(query, tab="punti_di_vista", provider=provider,
                                     options=options, mode=mode)


def generate_event_tab_report(query: str, tab: str = "punti_di_vista",
                                provider: Optional[str] = None,
                                options: Optional[dict] = None,
                                mode: str = "specialist") -> dict:
    """Genera una scheda storica documentata per l'evento specifica per tab."""
    import event_research_engine as ere
    return ere.research_event(query, options=options or {}, provider=provider,
                              tab=tab, mode=mode)


def generate_biography(subject_type: str, ref, provider: Optional[str] = None) -> dict:
    """Dispatcher usato dall'endpoint /api/biography."""
    if subject_type == "soldier":
        return generate_soldier_biography(int(ref), provider=provider)
    if subject_type == "event":
        return generate_event_biography(str(ref), provider=provider)
    return {"ok": False, "error": f"subject_type sconosciuto: {subject_type}"}


# ─── Report cronologico (tab Cronologia) ────────────────────────────────────

def generate_chronological_report(query: str, provider: Optional[str] = None) -> dict:
    """Genera un report cronologico narrativo dell'evento. Riusa la stessa
    pipeline di raccolta dati di generate_event_report ma con un prompt
    diverso che enfatizza la narrazione cronologica discorsiva."""
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

    event_ctx, event_sources = _event_centric_context(query)
    if event_ctx:
        verified = event_ctx + "\n\n" + verified
    if event_sources:
        online_sources = online_sources + event_sources

    prompt = CHRONOLOGICAL_REPORT_PROMPT.format(
        subject_label=f"Evento: {query}",
        verified_context=verified,
        online_context=online_ctx,
        unverified_context=unverified,
    )

    result = _call_with_fallback(
        system=(
            "Sei un ricercatore storico specializzato in eventi bellici italiani del '900. "
            "Il tuo compito e' produrre una ricostruzione cronologica narrativa, "
            "in prosa discorsiva, basata esclusivamente sulle fonti verificate."
        ),
        prompt=prompt, tag=f"report cronologico: {query}",
        preferred=provider or None,
    )
    result["subject_type"] = "chronological_report"
    result["query"] = query
    result["cues"] = cues
    result["confidence_locale"] = routed.get("confidence")
    result["verified_sources"] = _verified_labels_event(routed)
    if event_sources:
        result["verified_sources"] = result["verified_sources"] + [
            f"[EVENT_DB] {s['title']} — {s['url']}" for s in event_sources
        ]
    result["online_sources"] = online_sources
    return result


# ─── Analisi singola fonte (tab Fonti) ──────────────────────────────────────

def _get_source_metadata(source_id: int) -> Optional[dict]:
    """Recupera metadati di una fonte da fonti_indice."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM fonti_indice WHERE id=?", (source_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def _fetch_source_text(url: str) -> str:
    """Scarica il contenuto testuale da un URL della fonte (HTTP GET semplice).
    Non usa scraper_service (che ha domini limitati). Pulisce HTML -> testo plain.
    Ritorna stringa vuota se fallisce."""
    if not url or not url.startswith("http"):
        return ""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (research-bot)"},
            timeout=15,
            stream=True,
        )
        resp.raise_for_status()
        content = b""
        for chunk in resp.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > 512 * 1024:
                break
        encoding = resp.encoding or "utf-8"
        text = content.decode(encoding, errors="replace")
        if "text/html" in (resp.headers.get("Content-Type") or ""):
            import re as _re
            text = _re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=_re.DOTALL | _re.IGNORECASE)
            text = _re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=_re.DOTALL | _re.IGNORECASE)
            text = _re.sub(r"<[^>]+>", " ", text)
            text = _re.sub(r"\s+", " ", text)
        return text.strip()[:8000]
    except Exception:
        return ""


def _get_source_cached_content(source_id: int) -> str:
    """Legge il contenuto testuale in cache per una fonte, se disponibile."""
    import re as _re
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT path_file, content_type FROM source_fetch_cache "
        "WHERE source_id=? AND content_type IN ('application/json','text/plain','text/html') "
        "ORDER BY fetched_at DESC LIMIT 1", (source_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row["path_file"]:
        return ""
    p = Path(row["path_file"])
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
        if row["content_type"] == "text/html":
            text = _re.sub(r"<[^>]+>", " ", text)
            text = _re.sub(r"\s+", " ", text)
        return text.strip()[:3000]
    except Exception:
        return ""


def analyze_single_source(source_id: int, event_name: str = "",
                          provider: Optional[str] = None) -> dict:
    """Analizza una singola fonte con l'AI e produce un riassunto strutturato.
    Se la fonte non ha immagini/documenti, il prompt istruisce l'AI a cercarli
    sul web (via Perplexity nel contesto online)."""
    meta = _get_source_metadata(source_id)
    if not meta:
        return {"ok": False, "error": f"Fonte {source_id} non trovata"}

    source_metadata = (
        f"ID: {source_id}\n"
        f"Archivio: {meta.get('archivio', '?')}\n"
        f"Fondo: {meta.get('fondo', '?')}\n"
        f"Segnatura: {meta.get('segnatura', '?')}\n"
        f"Titolo: {meta.get('titolo', '?')}\n"
        f"Tipo fonte: {meta.get('tipo_fonte', '?')}\n"
        f"Reparto: {meta.get('reparto', '?')}\n"
        f"Luogo: {meta.get('luogo', '?')}\n"
        f"Data: {meta.get('data_inizio', '?')}\n"
        f"URL catalogo: {meta.get('url_catalogo', '')}\n"
        f"URL file: {meta.get('url_file', '')}\n"
        f"Access type: {meta.get('access_type', '?')}\n"
        f"Note: {meta.get('note', '')}"
    )

    source_content = _get_source_cached_content(source_id) or "(nessun contenuto testuale in cache)"

    event_context = ""
    if event_name:
        try:
            event_ctx, _ = _event_centric_context(event_name)
            event_context = event_ctx or "(nessun contesto evento disponibile)"
        except Exception:
            event_context = "(errore recupero contesto evento)"
    else:
        event_context = "(nessun evento specificato)"

    # Aggiungi contesto web se disponibile
    online_ctx = ""
    if event_name:
        online_ctx, _ = _online_verified_context(f"Evento: {event_name}")
        event_context = event_context + "\n\n" + online_ctx if online_ctx else event_context

    prompt = SOURCE_ANALYSIS_PROMPT.format(
        source_metadata=source_metadata,
        source_content=source_content,
        event_context=event_context,
    )

    result = _call_with_fallback(
        system=(
            "Sei un ricercatore storico e archivista specializzato in fonti belliche "
            "italiane del '900. Analizza la fonte indicata e produci un riassunto "
            "strutturato, cercando anche sul web immagini e documenti correlati."
        ),
        prompt=prompt, tag=f"analisi fonte #{source_id}",
        preferred=provider or None,
    )
    result["source_id"] = source_id
    result["source_title"] = meta.get("titolo", "")
    result["archivio"] = meta.get("archivio", "")
    return result


# ─── Generazione immagini AI (tab Fonti) ────────────────────────────────────

def _generate_image_dalle(prompt: str) -> dict:
    """Genera immagine con OpenAI (gpt-image-1) via REST API diretta.
    Ritorna {ok, image_b64, content_type, revised_prompt}."""
    from extractor import _load_api_key
    api_key = _load_api_key()
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1024",
            "n": 1,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    item = data["data"][0]
    # gpt-image-1 restituisce b64_json direttamente
    if "b64_json" in item:
        img_b64 = item["b64_json"]
    elif "url" in item:
        # Fallback: scarica da URL temporaneo
        img_resp = requests.get(item["url"], timeout=60)
        img_resp.raise_for_status()
        import base64 as _b64
        img_b64 = _b64.b64encode(img_resp.content).decode("utf-8")
    else:
        raise RuntimeError("Nessun b64_json o url nella risposta OpenAI")
    revised = item.get("revised_prompt", prompt)
    return {
        "ok": True,
        "image_b64": img_b64,
        "content_type": "image/png",
        "revised_prompt": revised,
    }


def _generate_image_stability(prompt: str) -> dict:
    """Fallback: genera immagine con Stability AI SD3."""
    import os
    from extractor import _load_env
    api_key = os.environ.get("STABILITY_API_KEY", "")
    if not api_key:
        env = _load_env()
        api_key = env.get("STABILITY_API_KEY", "")
    if not api_key:
        raise RuntimeError("STABILITY_API_KEY non configurata")
    resp = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/sd3",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"none": ""},
        data={"prompt": prompt, "output_format": "png"},
        timeout=90,
    )
    resp.raise_for_status()
    return {
        "ok": True,
        "image_bytes": resp.content,
        "content_type": resp.headers.get("Content-Type", "image/png"),
    }


def _save_generated_image(source_id: int, prompt: str, image_bytes: bytes,
                          content_type: str = "image/png",
                          title: str = "",
                          chunk: str = "",
                          episode: str = "") -> str:
    """Salva un'immagine generata in cache e registra nel DB.
    Ritorna il path locale del file salvato."""
    import hashlib
    import json as _json
    from source_locator import CACHE_DIR, get_conn as _get_conn
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    ext = ".png" if "png" in content_type else ".jpg"
    path = CACHE_DIR / f"ai_img_{sha[:16]}{ext}"
    path.write_bytes(image_bytes)

    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    meta_json = _json.dumps({"prompt": prompt, "title": title, "chunk": chunk, "episode": episode})
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO source_fetch_cache (source_id, url_fetched, path_file, sha256, "
        "size_bytes, content_type, permanent, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
        (source_id, f"ai_generated:{sha[:16]}:{meta_json}", str(path), sha,
         len(image_bytes), content_type, 1, now))
    conn.commit()
    conn.close()
    return str(path)


def _check_cached_images(source_id: int) -> list[dict]:
    """Controlla se esistono già immagini AI generate per questa fonte."""
    import json as _json
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT path_file, sha256, content_type, url_fetched FROM source_fetch_cache "
        "WHERE source_id=? AND url_fetched LIKE 'ai_generated:%' "
        "ORDER BY fetched_at DESC", (source_id,))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        # Estrai prompt e titolo dal campo url_fetched
        parts = d.get("url_fetched", "").split(":", 2)
        if len(parts) >= 3:
            try:
                meta = _json.loads(parts[2])
                d["prompt"] = meta.get("prompt", "")
                d["title"] = meta.get("title", "")
                d["chunk"] = meta.get("chunk", "")
                d["episode"] = meta.get("episode", "")
            except Exception:
                d["prompt"] = ""
                d["title"] = ""
                d["chunk"] = ""
                d["episode"] = ""
        else:
            d["prompt"] = ""
            d["title"] = ""
            d["chunk"] = ""
            d["episode"] = ""
        result.append(d)
    return result


def generate_source_images(source_id: int, event_name: str = "",
                           provider: Optional[str] = None) -> dict:
    """Genera immagini AI fotorealistiche per una fonte.
    1. L'AI analizza il contesto e genera 3-5 prompt
    2. Per ogni prompt, genera immagine con DALL-E 3 (fallback Stability AI)
    3. Salva le immagini in cache (source_fetch_cache) per persistenza
    4. Ritorna lista immagini con URL locale per visualizzazione"""
    import json as _json
    import hashlib
    import base64

    # Controlla cache: se già ci sono immagini per questa fonte, restituisci quelle
    cached = _check_cached_images(source_id)
    if cached:
        images = []
        for c in cached:
            try:
                img_bytes = Path(c["path_file"]).read_bytes()
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                images.append({
                    "title": c.get("title", "Immagine AI (cached)"),
                    "prompt": c.get("prompt", ""),
                    "chunk": c.get("chunk", ""),
                    "episode": c.get("episode", ""),
                    "image_base64": f"data:{c.get('content_type', 'image/png')};base64,{b64}",
                    "cached": True,
                })
            except Exception:
                pass
        if images:
            return {"ok": True, "source_id": source_id, "images": images,
                    "total": len(images), "from_cache": True}

    meta = _get_source_metadata(source_id)
    if not meta:
        return {"ok": False, "error": f"Fonte {source_id} non trovata"}

    source_metadata = (
        f"ID: {source_id}\n"
        f"Archivio: {meta.get('archivio', '?')}\n"
        f"Titolo: {meta.get('titolo', '?')}\n"
        f"Tipo fonte: {meta.get('tipo_fonte', '?')}\n"
        f"Luogo: {meta.get('luogo', '?')}\n"
        f"Data: {meta.get('data_inizio', '?')}\n"
        f"Reparto: {meta.get('reparto', '?')}\n"
        f"Note: {meta.get('note', '')}"
    )

    source_content = _get_source_cached_content(source_id) or ""

    # Prova a scaricare il contenuto dall'URL della fonte (se disponibile)
    url_catalogo = meta.get('url_catalogo', '') or ''
    url_file = meta.get('url_file', '') or ''
    fetched_text = ""
    for url in [url_catalogo, url_file]:
        if url:
            fetched = _fetch_source_text(url)
            if fetched and len(fetched) > 100:
                fetched_text = fetched
                break

    # Combina: testo fetchato + contenuto cache + fallback
    combined_content = ""
    if fetched_text:
        combined_content += fetched_text
    if source_content and source_content != "(nessun contenuto testuale in cache)":
        combined_content += "\n\n" + source_content
    if not combined_content:
        combined_content = "(nessun contenuto testuale disponibile per questa fonte)"

    event_context = ""
    if event_name:
        try:
            event_ctx, _ = _event_centric_context(event_name)
            event_context = event_ctx or ""
        except Exception:
            pass
        if not event_context:
            online_ctx, _ = _online_verified_context(f"Evento: {event_name}")
            event_context = online_ctx
    if not event_context:
        event_context = "(nessun contesto evento disponibile)"

    prompt = IMAGE_PROMPT_GENERATOR.format(
        source_metadata=source_metadata,
        source_content=combined_content,
        event_context=event_context,
    )

    # Step 1: genera i prompt con l'AI (text)
    result = _call_with_fallback(
        system=(
            "Sei un esperto di ricostruzione storica visiva. Genera prompt dettagliati "
            "per la creazione di immagini fotorealistiche di contesto storico militare."
        ),
        prompt=prompt, tag=f"prompt immagini fonte #{source_id}",
        preferred=provider or None,
    )

    if not result.get("risposta"):
        return {"ok": False, "error": "Generazione prompt AI fallita: " + result.get("error", "errore sconosciuto")}

    # Parse JSON dei prompt
    raw = result["risposta"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        prompt_list = _json.loads(raw.strip())
    except _json.JSONDecodeError:
        # Fallback: prova a estrarre JSON dall'interno del testo
        import re as _re
        m = _re.search(r'\[.*\]', raw, _re.DOTALL)
        if m:
            try:
                prompt_list = _json.loads(m.group(0))
            except _json.JSONDecodeError:
                return {"ok": False, "error": "Parse JSON prompt fallito", "raw": raw[:500]}
        else:
            return {"ok": False, "error": "Nessun JSON valido trovato nei prompt", "raw": raw[:500]}

    if not isinstance(prompt_list, list) or not prompt_list:
        return {"ok": False, "error": "Lista prompt vuota o malformata"}

    # Limita a 5 prompt
    prompt_list = prompt_list[:5]

    # Step 2: genera immagini per ogni prompt
    images = []
    errors = []
    for i, p in enumerate(prompt_list):
        img_prompt = p.get("prompt", "") if isinstance(p, dict) else str(p)
        img_title = p.get("title", f"Immagine {i+1}") if isinstance(p, dict) else f"Immagine {i+1}"
        img_chunk = p.get("chunk", "") if isinstance(p, dict) else ""
        img_episode = p.get("episode", "") if isinstance(p, dict) else ""
        if not img_prompt:
            continue

        try:
            # Prova OpenAI gpt-image-1
            dalle_result = _generate_image_dalle(img_prompt)
            if dalle_result.get("ok") and dalle_result.get("image_b64"):
                img_b64 = dalle_result["image_b64"]
                content_type = dalle_result.get("content_type", "image/png")

                # Decodifica per salvare in cache
                img_bytes = base64.b64decode(img_b64)
                local_path = _save_generated_image(source_id, img_prompt, img_bytes, content_type,
                                                   title=img_title, chunk=img_chunk, episode=img_episode)

                images.append({
                    "title": img_title,
                    "prompt": img_prompt,
                    "chunk": img_chunk,
                    "episode": img_episode,
                    "image_base64": f"data:{content_type};base64,{img_b64}",
                    "provider": "gpt-image-1",
                })
            else:
                raise RuntimeError("OpenAI non ha restituito immagine")
        except Exception as dalle_err:
            # Fallback: Stability AI
            try:
                stab_result = _generate_image_stability(img_prompt)
                if stab_result.get("ok") and stab_result.get("image_bytes"):
                    img_bytes = stab_result["image_bytes"]
                    content_type = stab_result.get("content_type", "image/png")

                    local_path = _save_generated_image(source_id, img_prompt, img_bytes, content_type,
                                                       title=img_title, chunk=img_chunk, episode=img_episode)

                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    images.append({
                        "title": img_title,
                        "prompt": img_prompt,
                        "chunk": img_chunk,
                        "episode": img_episode,
                        "image_base64": f"data:{content_type};base64,{b64}",
                        "provider": "stability-ai",
                    })
                else:
                    raise RuntimeError("Stability AI non ha restituito immagine")
            except Exception as stab_err:
                errors.append(f"Immagine {i+1} ({img_title}): DALL-E={dalle_err}, Stability={stab_err}")

    if not images and errors:
        return {"ok": False, "error": "Tutti i provider immagini hanno fallito", "details": errors}

    return {
        "ok": True,
        "source_id": source_id,
        "images": images,
        "total": len(images),
        "errors": errors if errors else None,
        "from_cache": False,
    }


def get_cached_images(source_id: int) -> dict:
    """Recupera immagini AI cached per una fonte, restituendole come base64."""
    import base64
    cached = _check_cached_images(source_id)
    if not cached:
        return {"ok": True, "source_id": source_id, "images": [], "total": 0}
    images = []
    for c in cached:
        try:
            img_bytes = Path(c["path_file"]).read_bytes()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            ct = c.get("content_type", "image/png")
            images.append({
                "title": c.get("title", "Immagine AI (cached)"),
                "prompt": c.get("prompt", ""),
                "chunk": c.get("chunk", ""),
                "episode": c.get("episode", ""),
                "image_base64": f"data:{ct};base64,{b64}",
                "cached": True,
            })
        except Exception:
            pass
    return {"ok": True, "source_id": source_id, "images": images, "total": len(images)}


def generate_soldier_images(soldier_id: int = None, name: str = "",
                            subtitle: str = "", subject_id: str = "",
                            provider: Optional[str] = None) -> dict:
    """Genera immagini AI per un soldato/persona.
    Usa i dati del soldato (dal DB se soldier_id, o dal nome/subtitle) per
    generare prompt contestuali e poi immagini con DALL-E (fallback Stability).
    """
    import json as _json
    import base64

    soldier_data = {}
    if soldier_id:
        try:
            dash = get_soldier_dashboard(soldier_id)
            if dash.get("ok"):
                soldier_data = dash.get("soldier", {})
        except Exception:
            pass

    cognome = soldier_data.get("cognome", "") or (name.split()[-1] if name else "")
    nome = soldier_data.get("nome", "") or (name.split()[0] if name else "")
    luogo_nascita = soldier_data.get("luogo_nascita", "")
    data_nascita = soldier_data.get("data_nascita", "")
    grado = soldier_data.get("grado", "")
    luogo_cattura = soldier_data.get("luogo_cattura", "")
    data_cattura = soldier_data.get("data_cattura", "")
    luogo_internamento = soldier_data.get("luogo_internamento", "")
    sorte = soldier_data.get("sorte", "")
    reparto = soldier_data.get("reparto") or soldier_data.get("unita_principale") or ""

    # Costruisci contesto per i prompt
    context_parts = []
    if nome or cognome:
        context_parts.append(f"Soldato: {nome} {cognome}")
    if grado:
        context_parts.append(f"Grado: {grado}")
    if luogo_nascita:
        context_parts.append(f"Nato a: {luogo_nascita}")
    if data_nascita:
        context_parts.append(f"Data nascita: {data_nascita}")
    if reparto:
        context_parts.append(f"Reparto: {reparto}")
    if luogo_cattura:
        context_parts.append(f"Catturato a: {luogo_cattura}")
    if data_cattura:
        context_parts.append(f"Data cattura: {data_cattura}")
    if luogo_internamento:
        context_parts.append(f"Internato a: {luogo_internamento}")
    if sorte:
        context_parts.append(f"Sorte: {sorte}")
    if subtitle:
        context_parts.append(f"Contesto: {subtitle}")

    soldier_context = "\n".join(context_parts) or name or subtitle

    # Aggiungi contesto web
    online_ctx, _ = _online_verified_context(
        f"Soldato: {nome} {cognome} {luogo_nascita} {data_nascita}",
        soldier_data=soldier_data if soldier_data else None,
    )

    prompt_gen = f"""Sei un esperto di ricostruzione storica visiva per la seconda guerra mondiale.
Genera 3 prompt dettagliati in inglese per creare immagini fotorealistiche di contesto storico
relativi al soldato descritto sotto. Le immagini devono essere storicamente plausibili e
rispettose — niente scene di violenza esplicita.

Dati del soldato:
{soldier_context}

Contesto storico web:
{online_ctx}

Genera prompt per:
1. Una scena di contesto (es. campo di internamento, ambiente di lavoro, viaggio)
2. Una scena personale (es. ritratto stilizzato, documento d'epoca, lettera)
3. Una scena storica collegata (es. operazione militare, liberazione, rimpatrio)

Rispondi SOLO con un array JSON, ogni elemento con:
{{"title": "titolo italiano", "prompt": "prompt inglese dettagliato per DALL-E", "episode": "breve descrizione episodio"}}
"""

    result = _call_with_fallback(
        system=(
            "Sei un esperto di ricostruzione storica visiva. Genera prompt dettagliati "
            "per la creazione di immagini fotorealistiche di contesto storico militare."
        ),
        prompt=prompt_gen, tag=f"prompt immagini soldato {subject_id or soldier_id}",
        preferred=provider or None,
    )

    if not result.get("risposta"):
        return {"ok": False, "error": "Generazione prompt AI fallita: " + result.get("error", "errore sconosciuto")}

    raw = result["risposta"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        prompt_list = _json.loads(raw.strip())
    except _json.JSONDecodeError:
        import re as _re
        m = _re.search(r'\[.*\]', raw, _re.DOTALL)
        if m:
            try:
                prompt_list = _json.loads(m.group(0))
            except _json.JSONDecodeError:
                return {"ok": False, "error": "Parse JSON prompt fallito", "raw": raw[:500]}
        else:
            return {"ok": False, "error": "Nessun JSON valido trovato nei prompt", "raw": raw[:500]}

    if not isinstance(prompt_list, list) or not prompt_list:
        return {"ok": False, "error": "Lista prompt vuota o malformata"}

    prompt_list = prompt_list[:5]
    images = []
    errors = []

    # Usa source_id fittizio (0) per il caching dei soldati
    cache_source_id = soldier_id or 0

    for i, p in enumerate(prompt_list):
        img_prompt = p.get("prompt", "") if isinstance(p, dict) else str(p)
        img_title = p.get("title", f"Immagine {i+1}") if isinstance(p, dict) else f"Immagine {i+1}"
        img_episode = p.get("episode", "") if isinstance(p, dict) else ""
        if not img_prompt:
            continue

        try:
            dalle_result = _generate_image_dalle(img_prompt)
            if dalle_result.get("ok") and dalle_result.get("image_b64"):
                img_b64 = dalle_result["image_b64"]
                content_type = dalle_result.get("content_type", "image/png")
                img_bytes = base64.b64decode(img_b64)
                _save_generated_image(cache_source_id, img_prompt, img_bytes, content_type,
                                      title=img_title, episode=img_episode)
                images.append({
                    "title": img_title,
                    "prompt": img_prompt,
                    "episode": img_episode,
                    "image_base64": f"data:{content_type};base64,{img_b64}",
                    "provider": "gpt-image-1",
                })
            else:
                raise RuntimeError("OpenAI non ha restituito immagine")
        except Exception as dalle_err:
            try:
                stab_result = _generate_image_stability(img_prompt)
                if stab_result.get("ok") and stab_result.get("image_bytes"):
                    img_bytes = stab_result["image_bytes"]
                    content_type = stab_result.get("content_type", "image/png")
                    _save_generated_image(cache_source_id, img_prompt, img_bytes, content_type,
                                          title=img_title, episode=img_episode)
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    images.append({
                        "title": img_title,
                        "prompt": img_prompt,
                        "episode": img_episode,
                        "image_base64": f"data:{content_type};base64,{b64}",
                        "provider": "stability-ai",
                    })
                else:
                    raise RuntimeError("Stability AI non ha restituito immagine")
            except Exception as stab_err:
                errors.append(f"Immagine {i+1} ({img_title}): DALL-E={dalle_err}, Stability={stab_err}")

    if not images and errors:
        return {"ok": False, "error": "Tutti i provider immagini hanno fallito", "details": errors}

    return {
        "ok": True,
        "images": images,
        "total": len(images),
        "errors": errors if errors else None,
    }
