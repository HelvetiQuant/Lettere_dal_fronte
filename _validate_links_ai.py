"""Validazione AI dei record_links: 5 cicli di test.
Per ogni ciclo, estrae un campione di link casuali dal grafo,
recupera i dati dei record collegati, e sottopone ad API AI
(OpenAI, Anthropic, Mistral, Gemini, Perplexity) per validazione.

L'AI valuta se il collegamento è corretto (VALID), errato (INVALID),
o incerto (UNCERTAIN), con motivazione.
"""
import os, sqlite3, json, random, time, sys
from pathlib import Path
from datetime import datetime

DB = Path(__file__).parent / "imi_internati.db"
SAMPLE_SIZE = 20  # link per ciclo
CYCLES = 5

# ─── Carica .env ────────────────────────────────────────────────────────────
def _load_env():
    env = {}
    for p in [Path.home() / "Desktop" / "lettere dal fronte backup_2026-06-28" / ".env",
              Path.cwd() / ".env"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    for k in list(env.keys()):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env

ENV = _load_env()
for k, v in ENV.items():
    os.environ.setdefault(k, v)

# ─── DB helpers ─────────────────────────────────────────────────────────────
# DB principale in read-only per evitare lock
conn_ro = sqlite3.connect(str(DB), timeout=30)
conn_ro.row_factory = sqlite3.Row
conn_ro.execute("PRAGMA journal_mode=WAL")
conn_ro.execute("PRAGMA query_only=ON")

# DB validazioni separato
VDB = Path(__file__).parent / "validazioni_ai.db"
conn = sqlite3.connect(str(VDB))
conn.row_factory = sqlite3.Row

def get_record(table, rid):
    """Recupera un record da una tabella con tutti i campi significativi."""
    try:
        r = conn_ro.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
        if not r:
            r = conn_ro.execute(f"SELECT * FROM {table} WHERE rowid=?", (rid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        # Filtra campi None/vuoti
        return {k: v for k, v in d.items() if v and str(v).strip()}
    except Exception:
        return None

def describe_record(table, rid):
    """Crea una descrizione testuale del record per l'AI."""
    r = get_record(table, rid)
    if not r:
        return f"[{table}#{rid}] Record non trovato"
    parts = [f"[{table}#{rid}]"]
    for k, v in r.items():
        if k in ("id", "rowid", "elaborato_il", "raw_json", "source_id", "volume_id"):
            continue
        parts.append(f"  {k}: {v}")
    return "\n".join(parts)

# ─── AI validators ──────────────────────────────────────────────────────────
VALIDATION_PROMPT = """Sei un validatore di collegamenti tra record storici di un database della Prima Guerra Mondiale.
Ti viene dato un collegamento tra due record. Devi valutare se è corretto.

COLLEGAMENTO: {link_type} (confidence: {confidence})
TIPO: {from_table} → {to_table}

RECORD A ({from_table}):
{record_a}

RECORD B ({to_table}):
{record_b}

Valuta se questo collegamento ha senso storico. Considera:
1. Coerenza temporale (anni, date)
2. Coerenza geografica (luoghi)
3. Coerenza nominativa (cognome+nome, non solo cognome — attenzione alle omonimie)
4. Plausibilità storica

Rispondi SOLO con JSON:
{{"verdict": "VALID"|"INVALID"|"UNCERTAIN", "reason": "breve motivazione in italiano", "score": 0.0-1.0}}
"""

import re

def _parse_json(text):
    """Parse JSON from AI response, handling markdown wrappers and extra text."""
    text = text.strip()
    # Remove markdown code blocks
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else parts[0]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to extract JSON object from text
    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # Last resort: return uncertain
    return {"verdict": "UNCERTAIN", "reason": f"AI response non parseable: {text[:100]}", "score": 0.5}

def _validate_openai(link_type, conf, ft, tt, ra, rb):
    import requests
    prompt = VALIDATION_PROMPT.format(
        link_type=link_type, confidence=conf, from_table=ft, to_table=tt,
        record_a=ra, record_b=rb)
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 200, "temperature": 0.1},
        timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"]))[:200])
    text = data["choices"][0]["message"]["content"].strip()
    return _parse_json(text)

def _validate_anthropic(link_type, conf, ft, tt, ra, rb):
    import requests
    prompt = VALIDATION_PROMPT.format(
        link_type=link_type, confidence=conf, from_table=ft, to_table=tt,
        record_a=ra, record_b=rb)
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json={"model": "claude-3-5-haiku-20241022", "max_tokens": 200,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"]))[:200])
    text = data["content"][0]["text"].strip()
    return _parse_json(text)

def _validate_mistral(link_type, conf, ft, tt, ra, rb):
    import requests
    prompt = VALIDATION_PROMPT.format(
        link_type=link_type, confidence=conf, from_table=ft, to_table=tt,
        record_a=ra, record_b=rb)
    r = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": "mistral-small-latest",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 200, "temperature": 0.1},
        timeout=30)
    data = r.json()
    text = data["choices"][0]["message"]["content"].strip()
    return _parse_json(text)

def _validate_gemini(link_type, conf, ft, tt, ra, rb):
    import requests
    prompt = VALIDATION_PROMPT.format(
        link_type=link_type, confidence=conf, from_table=ft, to_table=tt,
        record_a=ra, record_b=rb)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={os.environ['GEMINI_API_KEY']}"
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.1}
    }, timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"]["message"][:200])
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return _parse_json(text.strip())

def _validate_perplexity(link_type, conf, ft, tt, ra, rb):
    import requests
    prompt = VALIDATION_PROMPT.format(
        link_type=link_type, confidence=conf, from_table=ft, to_table=tt,
        record_a=ra, record_b=rb)
    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": "sonar",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 200, "temperature": 0.1},
        timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"])[:200])
    if "choices" not in data:
        raise RuntimeError(f"No choices in response: {str(data)[:200]}")
    text = data["choices"][0]["message"]["content"].strip()
    # Perplexity può aggiungere citations, pulisci
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return _parse_json(text.strip())

VALIDATORS = [
    ("anthropic", _validate_anthropic),
    ("mistral", _validate_mistral),
    ("perplexity", _validate_perplexity),
]

# ─── Schema tabella validazioni ─────────────────────────────────────────────
conn.execute("""CREATE TABLE IF NOT EXISTS record_link_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    cycle INTEGER NOT NULL,
    ai_provider TEXT NOT NULL,
    verdict TEXT NOT NULL,
    score REAL,
    reason TEXT,
    validated_at TEXT,
    FOREIGN KEY (link_id) REFERENCES record_links(id)
)""")
conn.commit()

# ─── 5 cicli di validazione ─────────────────────────────────────────────────
print(f"{'='*70}")
print(f"VALIDAZIONE AI RECORD_LINKS -- {CYCLES} cicli x {SAMPLE_SIZE} link x {len(VALIDATORS)} AI")
print(f"{'='*70}")

all_results = []
for cycle in range(1, CYCLES + 1):
    print(f"\n{'-'*60}")
    print(f"CICLO {cycle}/{CYCLES}")
    print(f"{'-'*60}")

    # Estrai campione casuale di link
    links = conn_ro.execute(
        "SELECT * FROM record_links ORDER BY RANDOM() LIMIT ?", (SAMPLE_SIZE,)
    ).fetchall()
    print(f"  Campione: {len(links)} link casuali")

    cycle_results = []
    for ai_name, ai_fn in VALIDATORS:
        print(f"\n  [{ai_name}] Validazione {len(links)} link...")
        valid = 0
        invalid = 0
        uncertain = 0
        errors = 0
        t0 = time.time()

        for link in links:
            ft = link["from_table"]
            tt = link["to_table"]
            ra = describe_record(ft, link["from_id"])
            rb = describe_record(tt, link["to_id"])
            lt = link["link_type"]
            conf = link["confidence"]

            try:
                result = ai_fn(lt, conf, ft, tt, ra, rb)
                verdict = result.get("verdict", "UNCERTAIN")
                score = result.get("score", 0.5)
                reason = result.get("reason", "")

                conn.execute(
                    "INSERT INTO record_link_validations (link_id, cycle, ai_provider, verdict, score, reason, validated_at) VALUES (?,?,?,?,?,?,?)",
                    (link["id"], cycle, ai_name, verdict, score, reason, datetime.now().isoformat(timespec="seconds"))
                )
                conn.commit()

                if verdict == "VALID":
                    valid += 1
                elif verdict == "INVALID":
                    invalid += 1
                else:
                    uncertain += 1

                cycle_results.append({
                    "cycle": cycle, "ai": ai_name, "link_id": link["id"],
                    "link_type": lt, "verdict": verdict, "score": score, "reason": reason
                })

            except Exception as e:
                errors += 1
                print(f"    ERROR link #{link['id']} ({lt}): {e}")

        elapsed = time.time() - t0
        print(f"    VALID={valid} INVALID={invalid} UNCERTAIN={uncertain} ERRORS={errors} ({elapsed:.1f}s)")

    all_results.extend(cycle_results)

# ─── Report finale ──────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("REPORT FINALE")
print(f"{'='*70}")

total_val = conn.execute("SELECT COUNT(*) FROM record_link_validations").fetchone()[0]
print(f"\nTotale validazioni: {total_val}")

print("\nPer AI provider:")
for r in conn.execute(
    "SELECT ai_provider, COUNT(*) as n, "
    "SUM(CASE WHEN verdict='VALID' THEN 1 ELSE 0 END) as valid, "
    "SUM(CASE WHEN verdict='INVALID' THEN 1 ELSE 0 END) as invalid, "
    "SUM(CASE WHEN verdict='UNCERTAIN' THEN 1 ELSE 0 END) as uncertain, "
    "AVG(score) as avg_score "
    "FROM record_link_validations GROUP BY ai_provider ORDER BY ai_provider"
).fetchall():
    print(f"  {r['ai_provider']:12s}  n={r['n']:>4}  VALID={r['valid']:>3}  INVALID={r['invalid']:>3}  UNCERTAIN={r['uncertain']:>3}  avg_score={r['avg_score']:.2f}")

# Per link_type: carica link_type da conn_ro e join in Python
link_types = {r["id"]: r["link_type"] for r in conn_ro.execute("SELECT id, link_type FROM record_links").fetchall()}
print("\nPer link_type:")
vals = conn.execute("SELECT link_id, verdict, score FROM record_link_validations").fetchall()
lt_stats = {}
for v in vals:
    lt = link_types.get(v["link_id"], "?")
    if lt not in lt_stats:
        lt_stats[lt] = {"n": 0, "valid": 0, "invalid": 0, "scores": []}
    lt_stats[lt]["n"] += 1
    if v["verdict"] == "VALID":
        lt_stats[lt]["valid"] += 1
    elif v["verdict"] == "INVALID":
        lt_stats[lt]["invalid"] += 1
    lt_stats[lt]["scores"].append(v["score"])
for lt, s in sorted(lt_stats.items(), key=lambda x: -x[1]["n"]):
    avg = sum(s["scores"]) / len(s["scores"]) if s["scores"] else 0
    print(f"  {lt:25s}  n={s['n']:>4}  VALID={s['valid']:>3}  INVALID={s['invalid']:>3}  avg={avg:.2f}")

print("\nPer ciclo:")
for r in conn.execute(
    "SELECT cycle, COUNT(*) as n, "
    "SUM(CASE WHEN verdict='VALID' THEN 1 ELSE 0 END) as valid, "
    "SUM(CASE WHEN verdict='INVALID' THEN 1 ELSE 0 END) as invalid "
    "FROM record_link_validations GROUP BY cycle ORDER BY cycle"
).fetchall():
    print(f"  Ciclo {r['cycle']}: n={r['n']:>4}  VALID={r['valid']:>3}  INVALID={r['invalid']:>3}")

# Sample INVALID per analisi
print("\nSample INVALID (max 5):")
invalid_rows = conn.execute(
    "SELECT ai_provider, cycle, link_id, reason FROM record_link_validations WHERE verdict='INVALID' LIMIT 5"
).fetchall()
if invalid_rows:
    for r in invalid_rows:
        lt = link_types.get(r["link_id"], "?")
        print(f"  [{r['ai_provider']}/C{r['cycle']}] link #{r['link_id']} ({lt})")
        print(f"    Reason: {r['reason']}")
else:
    print("  Nessun INVALID trovato.")

# Consenso tra AI sullo stesso link
print("\nConsenso AI (link validati da >=3 AI):")
consensus = conn.execute(
    "SELECT link_id, "
    "SUM(CASE WHEN verdict='VALID' THEN 1 ELSE 0 END) as valid_votes, "
    "SUM(CASE WHEN verdict='INVALID' THEN 1 ELSE 0 END) as invalid_votes, "
    "COUNT(*) as total_votes "
    "FROM record_link_validations GROUP BY link_id HAVING total_votes >= 3 ORDER BY valid_votes DESC LIMIT 10"
).fetchall()
for r in consensus:
    lt = link_types.get(r["link_id"], "?")
    print(f"  Link #{r['link_id']} ({lt}): VALID={r['valid_votes']}/{r['total_votes']} INVALID={r['invalid_votes']}/{r['total_votes']}")

conn.close()
conn_ro.close()
print(f"\nDONE -- {total_val} validazioni totali in {CYCLES} cicli")
