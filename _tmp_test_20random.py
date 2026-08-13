"""Test 20 random names from all DBs + 5 events."""
import sqlite3, random, time, json
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

random.seed(42)

# 4 names from each table
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
        rows = db.execute(f"SELECT {ccol}, {ncol} FROM {table} WHERE {ccol} != '' ORDER BY RANDOM() LIMIT 4").fetchall()
        for r in rows:
            names.append((f"{r[ccol]} {r[ncol]}", table))
    else:
        rows = db.execute(f"SELECT {ccol} FROM {table} WHERE {ccol} != '' ORDER BY RANDOM() LIMIT 4").fetchall()
        for r in rows:
            names.append((r[ccol], table))

db.close()

# 5 events from eventi_1gm.db
db2 = sqlite3.connect('eventi_1gm.db')
db2.row_factory = sqlite3.Row
events = []
erows = db2.execute("SELECT nome FROM eventi_1gm ORDER BY RANDOM() LIMIT 5").fetchall()
for r in erows:
    events.append(r['nome'])
db2.close()

orch = UnifiedResearchOrchestratorV7()
results = []

print("=== 20 RANDOM NAMES ===\n")
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
        answer = (nr.get("answer_markdown", "") if nr else "")[:200]
        results.append({"name": name, "table": table, "status": status, "provider": provider, "model": model, "claims": claims, "id_status": id_status, "elapsed": round(elapsed, 1), "answer_preview": answer})
        print(f"[{len(results)}/20] {name} ({table})")
        print(f"  Status: {status} | {provider}/{model} | {claims} claims | {id_status} | {elapsed:.1f}s")
        print(f"  Preview: {answer[:150]}...")
        print()
    except Exception as e:
        elapsed = time.time() - t0
        results.append({"name": name, "table": table, "status": "ERROR", "error": str(e), "elapsed": round(elapsed, 1)})
        print(f"[{len(results)}/20] {name} ({table}) — ERROR: {e}\n")

print("\n=== 5 EVENTS ===\n")
for evt in events:
    t0 = time.time()
    try:
        result = orch.execute(evt, intent="EVENT_LOOKUP")
        elapsed = time.time() - t0
        snap = result.get("snapshot", {})
        nr = result.get("narration_result")
        gen = nr.get("generation", {}) if nr else {}
        status = nr.get("status", "?") if nr else "?"
        provider = gen.get("provider", "")
        model = gen.get("model", "")
        claims = len(nr.get("used_claim_ids", [])) if nr else 0
        answer = (nr.get("answer_markdown", "") if nr else "")[:200]
        results.append({"name": evt, "type": "EVENT", "status": status, "provider": provider, "model": model, "claims": claims, "elapsed": round(elapsed, 1), "answer_preview": answer})
        print(f"[E{len(results)-20}] {evt}")
        print(f"  Status: {status} | {provider}/{model} | {claims} claims | {elapsed:.1f}s")
        print(f"  Preview: {answer[:150]}...")
        print()
    except Exception as e:
        elapsed = time.time() - t0
        results.append({"name": evt, "type": "EVENT", "status": "ERROR", "error": str(e), "elapsed": round(elapsed, 1)})
        print(f"[E{len(results)-20}] {evt} — ERROR: {e}\n")

print("\n=== SUMMARY ===\n")
for r in results:
    tag = r.get("type", "PERSON")
    print(f"  {r['name']}: {r['status']} via {r.get('provider','')}/{r.get('model','')} | {r.get('claims',0)} claims | {r.get('id_status','')} | {r['elapsed']}s")

with open("_tmp_test_20random.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nSaved to _tmp_test_20random.json")
