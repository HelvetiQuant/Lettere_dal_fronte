"""Inspect actual claim structure and why military details are missing."""
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

# Focus on first 2 names for detailed inspection
for i, (name, table) in enumerate(names[:3]):
    result = orch.execute(name, intent="PERSON_LOOKUP")
    snap = result.get("snapshot", {})
    nr = result.get("narration_result")
    used_ids = set(nr.get("used_claim_ids", [])) if nr else set([])
    omitted = nr.get("omitted_claims", []) if nr else []

    person_claims = snap.get("person_claims", [])

    print(f"\n{'='*80}")
    print(f"[{i+1}] {name} ({table}) — {len(person_claims)} claims, {len(used_ids)} used, {len(omitted)} omitted")
    print(f"{'='*80}")

    # Print first 3 claims with ALL fields
    print(f"\n--- CLAIM STRUCTURE (first 3 claims, all keys) ---")
    for c in person_claims[:3]:
        if isinstance(c, dict):
            print(f"  Keys: {list(c.keys())}")
            for k, v in c.items():
                print(f"    {k} = {v}")
        else:
            print(f"  Type: {type(c)}")
            print(f"  Dir: {[a for a in dir(c) if not a.startswith('_')]}")
            for a in dir(c):
                if not a.startswith('_'):
                    try:
                        print(f"    {a} = {getattr(c, a)}")
                    except:
                        pass
        print()

    # Print all claims with predicate + value
    print(f"--- ALL CLAIMS (predicate → value) ---")
    for c in person_claims:
        if isinstance(c, dict):
            cid = c.get("claim_id", "")
            pred = c.get("predicate", "")
            val = c.get("value", c.get("claim_value", c.get("text_value", "???")))
            used = "✅" if cid in used_ids else "❌"
            print(f"  {used} {pred}: {val}")
        else:
            cid = getattr(c, "claim_id", "")
            pred = getattr(c, "predicate", "")
            val = getattr(c, "value", getattr(c, "claim_value", "???"))
            used = "✅" if cid in used_ids else "❌"
            print(f"  {used} {pred}: {val}")

    # Omitted reasons
    if omitted:
        reasons = {}
        for o in omitted:
            r = o.get("reason", "unknown") if isinstance(o, dict) else str(o)
            reasons[r] = reasons.get(r, 0) + 1
        print(f"\n--- OMITTED REASONS ---")
        for r, cnt in reasons.items():
            print(f"  {r}: {cnt}")

    print(f"\n--- ANSWER (first 400 chars) ---")
    print(nr.get("answer_markdown", "")[:400] if nr else "N/A")
