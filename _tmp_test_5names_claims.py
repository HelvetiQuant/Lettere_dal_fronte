"""Inspect military unit claims for 5 names."""
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

for i, (name, table) in enumerate(names):
    result = orch.execute(name, intent="PERSON_LOOKUP")
    snap = result.get("snapshot", {})
    nr = result.get("narration_result")
    gen = nr.get("generation", {}) if nr else {}

    person_claims = snap.get("person_claims", [])
    context_claims = snap.get("context_claims", [])
    used_ids = set(nr.get("used_claim_ids", [])) if nr else set([])
    omitted = nr.get("omitted_claims", []) if nr else []

    print(f"\n{'='*80}")
    print(f"[{i+1}/5] {name} ({table})")
    print(f"Mode: {gen.get('mode','')} | {gen.get('provider','')}/{gen.get('model','')}")
    print(f"{'='*80}")

    print(f"\n--- ALL PERSON CLAIMS ({len(person_claims)}) ---")
    for c in person_claims:
        cid = c.get("claim_id", "")
        pred = c.get("predicate", "")
        val = c.get("value", "")
        used = "✅ USED" if cid in used_ids else "❌ OMITTED"
        src = c.get("source_table", "")
        print(f"  {used} | {pred}: {val} | src={src}")

    print(f"\n--- CONTEXT CLAIMS ({len(context_claims)}) ---")
    for c in context_claims:
        pred = c.get("predicate", "")
        val = c.get("value", "")
        scope = c.get("scope", "")
        print(f"  {scope} | {pred}: {val}")

    if omitted:
        print(f"\n--- OMITTED CLAIMS ({len(omitted)}) ---")
        for o in omitted[:10]:
            print(f"  {o}")

    print(f"\n--- ANSWER ---")
    print(nr.get("answer_markdown", "")[:600] if nr else "N/A")
