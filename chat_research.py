"""Chat Research — interfaccia conversazionale per ricerca storica.

Flusso:
1. Utente scrive in linguaggio naturale ("trovami info su Francesco Siracusa nato a Messina nel 1886")
2. Qwen parse la domanda → estrae SearchInput strutturato
3. research_protocol.esegue ricerca completa (DB locali + 27 provider + web)
4. Qwen sintetizza risposta conversazionale stile ChatGpt con dossier allegato
5. Mantieni contesto conversazione (domande di follow-up)

Usage:
    from chat_research import chat_research
    resp = chat_research("cerca Francesco Siracusa nato a Messina classe 1886")
    print(resp["answer"])  # risposta in linguaggio naturale
    print(resp["dossier"]["stato_identificazione"])  # dossier strutturato
"""
from __future__ import annotations

import json, logging, re, uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ─── Conversation memory ──────────────────────────────────────────────────────

@dataclass
class ConversationTurn:
    role: str  # user, assistant
    content: str
    timestamp: str = ""
    dossier_summary: dict = field(default_factory=dict)


@dataclass
class Conversation:
    id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    last_search_input: dict = field(default_factory=dict)
    created_at: str = ""

    def add_turn(self, role: str, content: str, dossier_summary: dict = None) -> ConversationTurn:
        t = ConversationTurn(role=role, content=content, timestamp=datetime.now().isoformat(), dossier_summary=dossier_summary or {})
        self.turns.append(t)
        return t

    def history_text(self, max_turns: int = 6) -> str:
        recent = self.turns[-max_turns:] if len(self.turns) > max_turns else self.turns
        lines = []
        for t in recent:
            prefix = "Utente" if t.role == "user" else "Assistente"
            lines.append(f"{prefix}: {t.content[:500]}")
        return "\n".join(lines)


# In-memory conversation store (per sessione API)
_conversations: Dict[str, Conversation] = {}


def get_or_create_conversation(conversation_id: str = None) -> Conversation:
    if conversation_id and conversation_id in _conversations:
        return _conversations[conversation_id]
    cid = conversation_id or str(uuid.uuid4())
    conv = Conversation(id=cid, created_at=datetime.now().isoformat())
    _conversations[cid] = conv
    return conv


# ─── NLP parsing with Qwen ────────────────────────────────────────────────────

PARSE_SYSTEM = """Sei un estrattore di dati strutturati da testo in linguaggio naturale italiano.
Estrai i dati anagrafici e militari dalla domanda dell'utente e restituisci SOLO un oggetto JSON.

Campi disponibili (lascia vuoto "" se non presente, usa [] per liste vuote):
{
  "nome": "",
  "cognome": "",
  "secondi_nomi": [],
  "varianti_nome": [],
  "varianti_cognome": [],
  "soprannome": "",
  "data_nascita": "",
  "anno_nascita": "",
  "luogo_nascita": "",
  "provincia_nascita": "",
  "paese_nascita": "",
  "paternita": "",
  "maternita": "",
  "coniuge": "",
  "residenza": "",
  "professione": "",
  "grado": "",
  "arma": "",
  "reparto": "",
  "battaglione": "",
  "compagnia": "",
  "distretto_militare": "",
  "numero_matricola": "",
  "numero_prigioniero": "",
  "conflitto_presunto": "",
  "periodo_presunto": "",
  "luogo_evento": "",
  "stato_presunto": "",
  "informazioni_familiari": "",
  "documenti_iniziali": [],
  "note_utente": ""
}

Regole:
- "classe 1886" → anno_nascita: "1886"
- "nato a Messina" → luogo_nascita: "Messina"
- "prima guerra mondiale" → conflitto_presunto: "ww1"
- "seconda guerra mondiale" → conflitto_presunto: "ww2"
- "figlio di Giovanni" → paternita: "Giovanni"
- "matricola 12345" → numero_matricola: "12345"
- "prigioniero n. 67890" → numero_prigioniero: "67890"
- "81° fanteria" → reparto: "81° fanteria"
- "tenente" → grado: "tenente"
- Non inventare dati. Se un campo non è menzionato, lascialo vuoto.
- Se l'utente fa una domanda di follow-up su una ricerca precedente, usa il contesto.
- Rispondi SOLO con il JSON, nessun altro testo."""

FALLBACK_SYSTEM = """Sei un assistente storico-archivistico italiano. Rispondi in modo chiaro e strutturato.
Se non hai dati sufficienti, dillo apertamente e suggerisci dove cercare."""

ANSWER_SYSTEM = """Sei un ricercatore storico-archivistico digitale esperto in eventi bellici del Novecento.
Rispondi alla domanda dell'utente in linguaggio naturale, come se fossi un collega ricercatore che ha appena consultato decine di archivi.

REGOLE:
- Basati ESCLUSIVAMENTE sui dati del dossier fornito. Non inventare informazioni.
- Usa un tono conversazionale, professionale ma accessibile — come una risposta di ChatGPT.
- Non usare elenchi numerati rigidi. Piuttosto, scrivi paragrafi fluidi.
- Quando menzioni un dato specifico, cita la fonte (es: "secondo l'Albo d'Oro del Ministero della Difesa...").
- Se hai trovato candidati, descrivili in modo narrativo: chi sono, cosa combacia, cosa no.
- Se ci sono contraddizioni tra le fonti, evidenziale con onestà.
- Se la ricerca non ha trovato risultati, spiega cosa hai cercato (quali archivi, quali query) e suggerisci i prossimi passi in modo pratico.
- Se l'utente fa una domanda di follow-up, usa il contesto della conversazione precedente.
- Rispondi in italiano, con markdown leggero (grassetto per nomi e fonti, non elenchi numerati)."""


def _ai_parse_question(question: str, conversation: Conversation) -> dict:
    """Use Qwen to parse natural language question into SearchInput fields."""
    # Build context from conversation history
    history = conversation.history_text()
    user_msg = question
    if history:
        user_msg = f"Contesto conversazione precedente:\n{history}\n\nNuova domanda: {question}"

    try:
        from ai_runtime import get_adapter
        adapter = get_adapter()
        health = adapter.health()
        if not health.healthy:
            log.info("AI not healthy, using fallback parser")
            return _fallback_parse(question)

        result = adapter.generate_structured(
            PARSE_SYSTEM, user_msg,
            max_tokens=1024, temperature=0.1,
            task_type="entity_extraction", timeout=30,
        )
        if result.ok and result.text:
            data = json.loads(result.text)
            log.info("AI parsed question: %s", json.dumps(data, ensure_ascii=False)[:200])
            return data
    except json.JSONDecodeError:
        log.warning("AI returned invalid JSON, trying fallback parser")
    except Exception as e:
        log.warning("AI parse failed: %s, using fallback", e)
    return _fallback_parse(question)


def _fallback_parse(question: str) -> dict:
    """Regex-based fallback parser when AI is not available."""
    q = question.strip()
    data = {k: "" for k in [
        "nome", "cognome", "secondi_nomi", "varianti_nome", "varianti_cognome",
        "soprannome", "data_nascita", "anno_nascita", "luogo_nascita",
        "provincia_nascita", "paese_nascita", "paternita", "maternita", "coniuge",
        "residenza", "professione", "grado", "arma", "reparto", "battaglione",
        "compagnia", "distretto_militare", "numero_matricola", "numero_prigioniero",
        "conflitto_presunto", "periodo_presunto", "luogo_evento", "stato_presunto",
        "informazioni_familiari", "documenti_iniziali", "note_utente"
    ]}
    # Ensure list fields
    for k in ("secondi_nomi", "varianti_nome", "varianti_cognome", "documenti_iniziali"):
        data[k] = []

    # Extract year
    m = re.search(r"(?:classe|nato(?:\s+nel)?|anno)\s+(\d{4})", q, re.IGNORECASE)
    if m:
        data["anno_nascita"] = m.group(1)
    else:
        m = re.search(r"\b(18[5-9]\d|19[0-4]\d)\b", q)
        if m:
            data["anno_nascita"] = m.group(1)

    # Extract birth place
    m = re.search(r"nato\s+(?:a|il\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+a?)\s+([A-Za-zÀ-ÿ'\-\s]+?)(?:\s+(?:classe|nel|prima|seconda|guerra|militare|regio|esercito|soldato|caduto|prigioniero|internato|$))", q, re.IGNORECASE)
    if m:
        data["luogo_nascita"] = m.group(1).strip()

    # Extract conflict
    if re.search(r"prima\s+guerra\s+mondiale|grande\s+guerra|1915.?1918", q, re.IGNORECASE):
        data["conflitto_presunto"] = "ww1"
    elif re.search(r"seconda\s+guerra\s+mondiale|1939.?1945|1940.?1945", q, re.IGNORECASE):
        data["conflitto_presunto"] = "ww2"

    # Extract paternità
    m = re.search(r"(?:figlio\s+di|di)\s+([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?)", q)
    if m:
        data["paternita"] = m.group(1)

    # Extract matricola
    m = re.search(r"matricola\s*(?:n\.?\s*)?(\d+)", q, re.IGNORECASE)
    if m:
        data["numero_matricola"] = m.group(1)

    # Extract prigioniero number
    m = re.search(r"prigioniero\s*(?:n\.?\s*)?(\d+)", q, re.IGNORECASE)
    if m:
        data["numero_prigioniero"] = m.group(1)

    # Extract reparto
    m = re.search(r"(\d+°\s*(?:fanteria|artiglieria|cavalleria|genio|alpini|bersaglieri|granatieri))", q, re.IGNORECASE)
    if m:
        data["reparto"] = m.group(1)

    # Extract grado
    gradi = ["tenente", "sottotenente", "capitano", "maggiore", "colonnello",
             "sergente", "caporale", "soldato", "fante", "maresciallo", "aiutante"]
    for g in gradi:
        if re.search(rf"\b{g}\b", q, re.IGNORECASE):
            data["grado"] = g
            break

    # Extract name: look for patterns like "Francesco Siracusa" or "Siracusa Francesco"
    # Remove known keywords first
    cleaned = re.sub(r"\b(?:classe|nato|a|il|nel|prima|seconda|guerra|mondiale|militare|regio|esercito|soldato|caduto|disperso|prigioniero|internato|deportato|reparto|matricola|figlio|di|tenente|sottotenente|capitano|maggiore|colonnello|sergente|caporale|fante|maresciallo|cerca|trova|informazioni|su|dati|notizie|scheda|documenti|vorrei|potresti|puoi|aiutami|ricerca)\b", "", q, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d{4}", "", cleaned)
    cleaned = re.sub(r"\d+°\s*\w+", "", cleaned)
    cleaned = re.sub(r"[^\w\s'\-À-ÿ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parts = cleaned.split()
    if len(parts) >= 2:
        # Heuristic: if first word looks like a name (not all caps in original)
        if parts[0][0].isupper() and len(parts[0]) <= 12:
            data["nome"] = parts[0]
            data["cognome"] = parts[1] if len(parts) >= 2 else ""
            if len(parts) > 2:
                data["secondi_nomi"] = parts[2:3]
        else:
            data["cognome"] = parts[0]
            data["nome"] = parts[1] if len(parts) >= 2 else ""
    elif len(parts) == 1:
        data["cognome"] = parts[0]

    return data


def _ai_generate_answer(question: str, dossier_dict: dict, conversation: Conversation) -> str:
    """Use OpenAI API to generate a natural language answer from the dossier."""
    history = conversation.history_text(max_turns=4)

    # Prepare dossier summary for AI — rich details for conversational answer
    summary = {
        "stato_identificazione": dossier_dict.get("stato_identificazione"),
        "candidati_count": len(dossier_dict.get("candidati", [])),
        "candidati_top": [
            {
                "nome": c.get("nome_originale"),
                "stato": c.get("stato"),
                "confidence": c.get("confidence"),
                "data_nascita": c.get("data_nascita"),
                "luogo_nascita": c.get("luogo_nascita"),
                "reparto": c.get("reparto"),
                "grado": c.get("grado"),
                "morte": c.get("morte"),
                "compatibilita": c.get("compatibilita", []),
                "contraddizioni": c.get("contraddizioni", []),
                "fonti": [{"istituzione": f.get("istituzione"), "url": f.get("url"), "source_level": f.get("source_level")} for f in c.get("fonti", [])[:5]],
            }
            for c in dossier_dict.get("candidati", [])[:10]
        ],
        "omonimi_esclusi_count": len(dossier_dict.get("omonimi_esclusi", [])),
        "omonimi_esclusi": [c.get("nome_originale") for c in dossier_dict.get("omonimi_esclusi", [])[:5]],
        "fonti_count": len(dossier_dict.get("fonti", [])),
        "fonti_elenche": [f.get("istituzione") for f in dossier_dict.get("fonti", [])[:15]],
        "contraddizioni": dossier_dict.get("contraddizioni", [])[:5],
        "ricerche_negative_count": len(dossier_dict.get("ricerche_negative", [])),
        "ricerche_negative_archivi": [r.get("motore_o_archivio") for r in dossier_dict.get("ricerche_negative", [])[:10]],
        "piste": dossier_dict.get("piste", [])[:5],
        "richieste_archivistiche": dossier_dict.get("richieste", [])[:5],
        "varianti_generate": [v.get("text") for v in dossier_dict.get("varianti", [])[:8]],
        "search_log": [{"archivio": s.get("motore_o_archivio"), "risultati": s.get("risultati_trovati"), "esito": s.get("esito")} for s in dossier_dict.get("search_log", [])[:15]],
    }

    user_msg = f"Domanda utente: {question}\n\nDossier di ricerca:\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
    if history:
        user_msg = f"Contesto conversazione:\n{history}\n\n{user_msg}"

    # ── Try OpenAI API directly for best conversational quality ──
    try:
        import os
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=4096,
                temperature=0.7,
                timeout=90,
            )
            text = response.choices[0].message.content
            if text and len(text) > 20:
                log.info("Answer generated with OpenAI gpt-4o (%d chars)", len(text))
                return text
            log.warning("OpenAI returned short/empty answer, trying fallback")
    except Exception as e:
        log.warning("OpenAI answer failed: %s, trying Qwen/cloud fallback", e)

    # ── Fallback: try ai_runtime adapter (Qwen or cloud) ──
    try:
        from ai_runtime import get_adapter
        adapter = get_adapter()
        health = adapter.health()
        if not health.healthy:
            return _fallback_answer(question, dossier_dict)

        result = adapter.generate(
            ANSWER_SYSTEM, user_msg,
            max_tokens=4096, temperature=0.7,
            task_type="historical_research_answer", timeout=90,
        )
        if result.ok and result.text:
            return result.text
        return _fallback_answer(question, dossier_dict)
    except Exception as e:
        log.warning("AI answer failed: %s, using fallback", e)
        return _fallback_answer(question, dossier_dict)


def _fallback_answer(question: str, dossier_dict: dict) -> str:
    """Generate a basic answer without AI when Qwen is not available."""
    stato = dossier_dict.get("stato_identificazione", "non_identificata")
    candidati = dossier_dict.get("candidati", [])
    fonti = dossier_dict.get("fonti", [])
    omonimi = dossier_dict.get("omonimi_esclusi", [])
    ricerche_neg = dossier_dict.get("ricerche_negative", [])
    richieste = dossier_dict.get("richieste", [])
    varianti = dossier_dict.get("varianti", [])

    lines = []
    lines.append(f"**Stato della ricerca:** {stato}\n")

    if candidati:
        lines.append(f"**Candidati trovati:** {len(candidati)}")
        for i, c in enumerate(candidati[:5], 1):
            lines.append(f"  {i}. {c.get('nome_originale', '?')} — stato: {c.get('stato', '?')}")
            if c.get("compatibilita"):
                lines.append(f"     Compatibilità: {', '.join(c['compatibilita'])}")
            if c.get("contraddizioni"):
                lines.append(f"     Contraddizioni: {', '.join(c['contraddizioni'])}")
            fonti_c = c.get("fonti", [])
            if fonti_c:
                lines.append(f"     Fonti: {', '.join(f.get('istituzione', '?') for f in fonti_c[:3])}")
        lines.append("")
    else:
        lines.append("**Nessun candidato trovato** nei database consultati.\n")

    if omonimi:
        lines.append(f"**Omonimi esclusi:** {len(omonimi)} (non compatibili con i dati forniti)\n")

    if ricerche_neg:
        lines.append(f"**Ricerche negative:** {len(ricerche_neg)} archivi consultati senza risultato\n")

    if fonti:
        levels = {}
        for f in fonti:
            lv = f.get("source_level", "D")
            levels.setdefault(lv, []).append(f.get("istituzione", "?"))
        lines.append(f"**Fonti consultate:** {len(fonti)} totali")
        for lv in sorted(levels):
            lines.append(f"  Livello {lv}: {', '.join(levels[lv][:5])}")
        lines.append("")

    if varianti:
        lines.append(f"**Varianti generate:** {', '.join(v.get('text', '') for v in varianti[:5])}\n")

    if richieste:
        lines.append("**Richieste archivistiche suggerite:**")
        for r in richieste[:4]:
            lines.append(f"  - {r.get('ente', '?')} — {r.get('documento_richiesto', '?')}")
        lines.append("")

    lines.append("**Prossimi passi:**")
    if stato == "confermata":
        lines.append("  - Approfondire il percorso militare con documenti di reparto")
    elif stato in ("probabile", "possibile"):
        lines.append("  - Verificare identificatori forti (data nascita completa, paternità, matricola)")
        lines.append("  - Contattare gli archivi suggeriti per conferma")
    else:
        lines.append("  - Richiedere foglio matricolare presso Archivio di Stato")
        lines.append("  - Consultare Albo d'Oro presso Ministero Difesa")
        lines.append("  - Verificare registri di leva nel comune di nascita")

    return "\n".join(lines)


# ─── Main chat function ───────────────────────────────────────────────────────

def chat_research(
    question: str,
    conversation_id: str = None,
    *,
    use_ai: bool = True,
    persist: bool = True,
) -> dict:
    """Process a natural language question about a military person.

    Args:
        question: user's natural language question
        conversation_id: optional conversation ID for follow-up questions
        use_ai: use Qwen for parsing and answer generation
        persist: persist research results to Supabase

    Returns:
        {
            "conversation_id": str,
            "answer": str,           # natural language response
            "dossier": dict,         # full structured dossier
            "parsed_input": dict,    # what was extracted from the question
            "ai_used": bool,
            "ai_model": str,
        }
    """
    conv = get_or_create_conversation(conversation_id)
    conv.add_turn("user", question)

    # Step 1: Parse question → structured input
    if use_ai:
        parsed = _ai_parse_question(question, conv)
    else:
        parsed = _fallback_parse(question)

    # Check if it's a follow-up question (no new name to search)
    has_name = parsed.get("cognome") or parsed.get("nome")
    if not has_name and conv.last_search_input:
        # Follow-up: merge with previous search input
        merged = dict(conv.last_search_input)
        for k, v in parsed.items():
            if v and v != "":
                merged[k] = v
        parsed = merged

    # Step 2: Run research protocol
    from research_protocol import research_person
    dossier = research_person(parsed, use_ai=use_ai, persist=persist)
    dossier_dict = dossier.to_dict()

    # Save for future follow-ups
    conv.last_search_input = parsed

    # Step 3: Generate natural language answer
    if use_ai:
        answer = _ai_generate_answer(question, dossier_dict, conv)
    else:
        answer = _fallback_answer(question, dossier_dict)

    # Save assistant turn
    conv.add_turn("assistant", answer, {
        "stato": dossier.stato_identificazione,
        "candidati": len(dossier.candidati),
    })

    # Determine AI metadata
    ai_model = ""
    ai_used = False
    if use_ai:
        try:
            from ai_runtime import get_adapter
            h = get_adapter().health()
            ai_used = h.healthy
            ai_model = h.model
        except Exception:
            pass

    return {
        "conversation_id": conv.id,
        "answer": answer,
        "dossier": dossier_dict,
        "parsed_input": parsed,
        "ai_used": ai_used,
        "ai_model": ai_model,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print('Usage: python chat_research.py "cerca Francesco Siracusa nato a Messina classe 1886"')
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    result = chat_research(question, use_ai="--no-ai" not in sys.argv)
    print("\n" + "=" * 80)
    print("RISPOSTA:")
    print("=" * 80)
    print(result["answer"])
    print("\n" + "=" * 80)
    print(f"Stato: {result['dossier']['stato_identificazione']}")
    print(f"Candidati: {len(result['dossier']['candidati'])}")
    print(f"Fonti: {len(result['dossier']['fonti'])}")
    print(f"AI: {result['ai_used']} ({result['ai_model']})")
