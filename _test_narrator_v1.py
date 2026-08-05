"""V7.2 Narrator v1 — Test con 6 persone casuali dai DB e 3 eventi storici.

Estrae 6 nomi reali dai database (internati, caduti_albooro, decorati_nastroazzurro)
e 3 eventi da eventi_1gm, poi li passa attraverso la pipeline V7.2 completa
con il nuovo narratore storico conversazionale v1.

Output: _v72_narrator_test_output.txt
"""
import sys, os, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

# ─── Estrai 6 nomi casuali dai DB ───────────────────────────────────────────

conn = get_conn()
random.seed(42)

person_names = []

# 2 nomi da internati
rows = conn.execute("SELECT cognome, nome FROM internati WHERE cognome != '' AND nome != '' ORDER BY RANDOM() LIMIT 2").fetchall()
for r in rows:
    person_names.append(f"{r['cognome']} {r['nome']}")

# 2 nomi da caduti_albooro
rows = conn.execute("SELECT nominativo FROM caduti_albooro WHERE nominativo != '' AND nominativo NOT LIKE '%-%' ORDER BY RANDOM() LIMIT 2").fetchall()
for r in rows:
    person_names.append(r["nominativo"])

# 2 nomi da decorati_nastroazzurro
rows = conn.execute("SELECT cognome, nome FROM decorati_nastroazzurro WHERE cognome != '' AND nome != '' ORDER BY RANDOM() LIMIT 2").fetchall()
for r in rows:
    person_names.append(f"{r['cognome']} {r['nome']}")

# 3 eventi da eventi_1gm
event_names = []
rows = conn.execute("SELECT nome FROM eventi_1gm ORDER BY RANDOM() LIMIT 3").fetchall()
for r in rows:
    event_names.append(r["nome"])

conn.close()

print(f"Persone estratte: {person_names}")
print(f"Eventi estratti: {event_names}")

# ─── Esegui pipeline per ogni target ─────────────────────────────────────────

orch = UnifiedResearchOrchestratorV7()
lines = []

# Header
lines.append("=" * 80)
lines.append("V7.2 NARRATORE STORICO CONVERSAZIONALE v1 — TEST COMPLETO")
lines.append(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")
lines.append(f"Contratto: {orch._narrator.NARRATOR_CONTRACT_VERSION}")
lines.append(f"Persone: {len(person_names)} | Eventi: {len(event_names)}")
lines.append("=" * 80)

# ─── PERSON LOOKUP (6 nomi) ──────────────────────────────────────────────────

lines.append("\n\n" + "█" * 80)
lines.append("█  PARTE 1: PERSON LOOKUP (6 nomi casuali dai DB)")
lines.append("█" * 80)

for i, name in enumerate(person_names, 1):
    lines.append(f"\n\n{'─' * 80}")
    lines.append(f"PERSON {i}/6: {name}")
    lines.append(f"{'─' * 80}")

    t0 = time.time()
    result = orch.execute(
        user_input=name,
        intent="PERSON_LOOKUP",
    )
    elapsed = time.time() - t0

    lines.append(f"\nRun ID: {result.get('run_id', '?')}")
    lines.append(f"Tempo: {elapsed:.1f}s")
    lines.append(f"Observations: {result.get('observation_count', 0)}")
    if result.get("errors"):
        lines.append(f"Errors: {result['errors']}")
    if result.get("warnings"):
        lines.append(f"Warnings: {result['warnings'][:5]}")  # first 5 only

    if result.get("snapshot"):
        snap = result["snapshot"]
        lines.append(f"Identity status: {snap.get('identity_status', '?')}")
        lines.append(f"Corroboration: {snap.get('corroboration_status', '?')}")
        lines.append(f"Person claims: {len(snap.get('person_claims', []))}")
        lines.append(f"Context claims: {len(snap.get('context_claims', []))}")
        lines.append(f"Web leads: {len(snap.get('web_leads', []))}")

    lines.append(f"\n{'─ ' * 40}")
    lines.append("RISPOSTA NARRATORE:")
    lines.append(f"{'─ ' * 40}")
    if result.get("report"):
        lines.append(result["report"])
    else:
        lines.append("NESSUN REPORT GENERATO")

    print(f"  [{i}/6] {name}: {elapsed:.1f}s, obs={result.get('observation_count', 0)}, report={'si' if result.get('report') else 'no'}")

# ─── EVENT LOOKUP (3 eventi) ─────────────────────────────────────────────────

lines.append("\n\n" + "█" * 80)
lines.append("█  PARTE 2: EVENT LOOKUP (3 eventi casuali da eventi_1gm)")
lines.append("█" * 80)

for i, event in enumerate(event_names, 1):
    lines.append(f"\n\n{'─' * 80}")
    lines.append(f"EVENT {i}/3: {event}")
    lines.append(f"{'─' * 80}")

    t0 = time.time()
    result = orch.execute(
        user_input=event,
        intent="EVENT_LOOKUP",
    )
    elapsed = time.time() - t0

    lines.append(f"\nRun ID: {result.get('run_id', '?')}")
    lines.append(f"Tempo: {elapsed:.1f}s")
    lines.append(f"Observations: {result.get('observation_count', 0)}")
    if result.get("errors"):
        lines.append(f"Errors: {result['errors']}")
    if result.get("warnings"):
        lines.append(f"Warnings: {result['warnings'][:5]}")

    if result.get("snapshot"):
        snap = result["snapshot"]
        lines.append(f"Identity status: {snap.get('identity_status', '?')}")
        lines.append(f"Corroboration: {snap.get('corroboration_status', '?')}")
        lines.append(f"Person claims: {len(snap.get('person_claims', []))}")
        lines.append(f"Context claims: {len(snap.get('context_claims', []))}")
        lines.append(f"Web leads: {len(snap.get('web_leads', []))}")

    lines.append(f"\n{'─ ' * 40}")
    lines.append("RISPOSTA NARRATORE:")
    lines.append(f"{'─ ' * 40}")
    if result.get("report"):
        lines.append(result["report"])
    else:
        lines.append("NESSUN REPORT GENERATO")

    print(f"  [{i}/3] {event}: {elapsed:.1f}s, obs={result.get('observation_count', 0)}, report={'si' if result.get('report') else 'no'}")

# ─── Salva output ────────────────────────────────────────────────────────────

output = "\n".join(lines)
outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_v72_narrator_test_output.txt")
with open(outpath, "w", encoding="utf-8") as f:
    f.write(output)

print(f"\n\nOutput scritto in {outpath} ({len(output)} chars)")
