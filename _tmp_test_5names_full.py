"""Print full backend answers for 5 names."""
import sqlite3, random, time, warnings, logging, json
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

output_lines = []
for i, (name, table) in enumerate(names):
    t0 = time.time()
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
    fallback = gen.get("fallback_reason", "") if nr else ""

    header = f"{'='*80}\n[{i+1}/5] {name} ({table})\nStatus: {status} | {provider}/{model} | {claims} claims | {id_status} | {elapsed:.1f}s\n"
    if fallback:
        header += f"Fallback reason: {fallback}\n"
    header += f"{'='*80}\n"
    block = header + answer + "\n\n"
    output_lines.append(block)
    print(block)

with open("_tmp_5names_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))
print("\n--- Saved to _tmp_5names_output.txt ---")
