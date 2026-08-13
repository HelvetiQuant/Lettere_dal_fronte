"""Quick test on 5 random names — clean output."""
import sqlite3, random, time, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
random.seed(99)

tables = [
    ("lebi_records", "cognome", "nome"),
    ("internati", "cognome", "nome"),
    ("caduti_ministero", "cognome", "nome"),
    ("caduti_albooro", "nominativo", None),
    ("decorati_nastroazzurro", "cognome", "nome"),
]

names = []
for table, ccol, ncol in tables:
    if ncol:
        rows = db.execute(f"SELECT {ccol}, {ncol} FROM {table} WHERE {ccol} != '' ORDER BY RANDOM() LIMIT 1").fetchall()
        for r in rows:
            names.append((f"{r[ccol]} {r[ncol]}", table))
    else:
        rows = db.execute(f"SELECT {ccol} FROM {table} WHERE {ccol} != '' ORDER BY RANDOM() LIMIT 1").fetchall()
        for r in rows:
            names.append((r[ccol], table))
db.close()

orch = UnifiedResearchOrchestratorV7()

results = []
for i, (name, table) in enumerate(names):
    t0 = time.time()
    try:
        result = orch.execute(name, intent="PERSON_LOOKUP")
        elapsed = time.time() - t0
        snap = result.get("snapshot", {})
        nr = result.get("narration_result")
        gen = nr.get("generation", {}) if nr else {}
        status = nr.get("status", "?") if nr else "?"
        provider = gen.get("provider", "")
        model = gen.get("model", "")
        claims = len(nr.get("used_claim_ids", [])) if nr else 0
        id_status = snap.get("identity_status", "?")
        answer = (nr.get("answer_markdown", "") if nr else "")

        # Simple duplicate detection on sentences
        import re
        sentences = [s.strip() for s in re.split(r'[.\n]', answer) if len(s.strip()) > 40]
        seen = []
        dups = []
        for s in sentences:
            tokens = set(s.lower().split())
            for prev in seen:
                ov = len(tokens & prev) / min(len(tokens), len(prev)) if tokens and prev else 0
                if ov >= 0.6:
                    dups.append(s[:80])
                    break
            seen.append(tokens)

        results.append({
            "name": name, "table": table, "status": status, "provider": f"{provider}/{model}",
            "claims": claims, "id_status": id_status, "elapsed": round(elapsed, 1),
            "dups": len(dups), "answer": answer
        })
        print(f"[{i+1}/5] {name} ({table})")
        print(f"  {status} | {provider}/{model} | {claims} claims | {id_status} | {elapsed:.1f}s | dups={len(dups)}")
        print(f"  {answer[:300]}")
        print()
    except Exception as e:
        elapsed = time.time() - t0
        results.append({"name": name, "table": table, "error": str(e), "elapsed": round(elapsed, 1)})
        print(f"[{i+1}/5] {name} ({table}) — ERROR: {e}\n")

print("\n=== SUMMARY ===")
for r in results:
    if "error" in r:
        print(f"  {r['name']}: ERROR ({r['elapsed']}s)")
    else:
        print(f"  {r['name']}: {r['status']} | {r['provider']} | {r['claims']} claims | {r['id_status']} | {r['elapsed']}s | dups={r['dups']}")
