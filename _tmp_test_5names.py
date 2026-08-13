"""Quick test on 5 random names from different DB tables."""
import sqlite3, random, time
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

print("=== 5 RANDOM NAMES TEST ===\n")
for name, table in names:
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
        # Check for duplicates
        lines = [l.strip() for l in answer.split("\n") if l.strip() and len(l.strip()) > 30]
        seen = []
        dups = []
        for l in lines:
            tokens = set(l.lower().split())
            for prev_tokens in seen:
                overlap = len(tokens & prev_tokens) / min(len(tokens), len(prev_tokens)) if tokens else 0
                if overlap >= 0.6:
                    dups.append(l[:80])
                    break
            seen.append(tokens)

        print(f"[{names.index((name, table))+1}/5] {name} ({table})")
        print(f"  Status: {status} | {provider}/{model} | {claims} claims | {id_status} | {elapsed:.1f}s")
        print(f"  Duplicates found: {len(dups)}")
        print(f"  Answer preview (first 500 chars):")
        print(f"  {answer[:500]}")
        print()
    except Exception as e:
        elapsed = time.time() - t0
        print(f"{name} ({table}) — ERROR: {e}\n")
