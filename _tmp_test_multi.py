"""Test pipeline: 2 random names from each DB table, AI chat mode, evaluate responses."""
import logging
import json
import sys
import random
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from database import get_conn

# Pick 2 random names from each table
conn = get_conn()
test_names = []

tables = [
    ("lebi_records", "cognome", "nome"),
    ("internati", "cognome", "nome"),
    ("caduti_ministero", "cognome", "nome"),
    ("caduti_cwgc", "cognome", "nome"),
    ("decorati_nastroazzurro", "cognome", "nome"),
]

for table, cog_col, nom_col in tables:
    try:
        rows = conn.execute(
            f"SELECT {cog_col}, {nom_col} FROM {table} "
            f"WHERE {cog_col} IS NOT NULL AND {nom_col} IS NOT NULL "
            f"ORDER BY RANDOM() LIMIT 2"
        ).fetchall()
        for r in rows:
            name = f"{r[0]} {r[1]}".strip()
            test_names.append((table, name))
            print(f"  [{table}] {name}")
    except Exception as e:
        print(f"  [{table}] ERROR: {e}")

conn.close()

print(f"\n=== {len(test_names)} names selected ===\n")

# Run pipeline for each name
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7
from v7_narrator import NarratorV7_v2

orch = UnifiedResearchOrchestratorV7()
narrator = NarratorV7_v2()

results = []

for table, name in test_names:
    print(f"\n{'='*60}")
    print(f"Testing: {name} (from {table})")
    print(f"{'='*60}")

    t0 = time.time()
    try:
        result = orch.execute(name, intent="PERSON_LOOKUP")
        elapsed = time.time() - t0

        if not result:
            print(f"  ERROR: No result returned")
            results.append({"name": name, "table": table, "error": "no_result"})
            continue

        snapshot = result.get("snapshot")
        narration = result.get("narration_result")

        if not snapshot:
            print(f"  ERROR: No snapshot in result")
            print(f"  Result keys: {list(result.keys())}")
            results.append({"name": name, "table": table, "error": "no_snapshot"})
            continue

        # Handle both dict and object snapshots
        if isinstance(snapshot, dict):
            obs_count = len(snapshot.get("observations", []))
            identity = snapshot.get("identity_status", "unknown")
        else:
            obs_count = len(snapshot.observations) if hasattr(snapshot, 'observations') else 0
            identity = snapshot.identity_status if hasattr(snapshot, 'identity_status') else "unknown"

        if narration is None:
            # Run narrator manually if not in result
            if hasattr(snapshot, 'intent'):
                narration = narrator.narrate(snapshot, use_ai=True)
            else:
                print(f"  Snapshot is dict, checking narration in result...")
                narration = result.get("narration_result")

        gen_mode = ""
        gen_provider = ""
        gen_model = ""
        ai_val = None
        status = ""
        answer_md = ""
        flags = []
        n_claims = 0

        if narration:
            if hasattr(narration, 'generation'):
                gen_mode = narration.generation.mode
                gen_provider = narration.generation.provider
                gen_model = narration.generation.model
                ai_val = narration.generation.ai_validation
                status = narration.status
                answer_md = narration.answer_markdown
                flags = narration.validation_flags
                n_claims = len(narration.used_claim_ids)
            elif isinstance(narration, dict):
                gen = narration.get("generation", {})
                gen_mode = gen.get("mode", "")
                gen_provider = gen.get("provider", "")
                gen_model = gen.get("model", "")
                ai_val = gen.get("ai_validation")
                status = narration.get("status", "")
                answer_md = narration.get("answer_markdown", "")
                flags = narration.get("validation_flags", [])
                n_claims = len(narration.get("used_claim_ids", []))

        print(f"  Observations: {obs_count}")
        print(f"  Identity: {identity}")
        print(f"  Status: {status}")
        print(f"  Generation: {gen_mode} via {gen_provider}/{gen_model}")
        if ai_val:
            print(f"  AI Validation: valid={ai_val.get('valid')}, severity={ai_val.get('severity')}, "
                  f"validator={ai_val.get('provider')}/{ai_val.get('model')}")
            if ai_val.get('issues'):
                print(f"  Validation issues: {ai_val['issues'][:3]}")
        else:
            print(f"  AI Validation: None (not run or unavailable)")
        print(f"  Claims used: {n_claims}")
        print(f"  Flags: {flags[:5]}")
        print(f"  Elapsed: {elapsed:.1f}s")
        print(f"  --- FULL ANSWER ---")
        print(answer_md)
        print(f"  --- END ANSWER ---\n")

        results.append({
            "name": name, "table": table, "status": status,
            "gen_mode": gen_mode, "gen_provider": gen_provider,
            "gen_model": gen_model, "ai_validation": ai_val,
            "n_claims": n_claims, "flags": flags[:5],
            "elapsed": round(elapsed, 1),
            "answer": answer_md,
        })

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results.append({"name": name, "table": table, "error": str(e),
                        "elapsed": round(elapsed, 1)})

# Summary
print(f"\n\n{'='*60}")
print(f"=== SUMMARY ===")
print(f"{'='*60}")
for r in results:
    if "error" in r:
        print(f"  {r['name']}: ERROR ({r['error']}) [{r.get('elapsed','?')}s]")
    else:
        val_str = ""
        if r.get("ai_validation"):
            av = r["ai_validation"]
            val_str = f" | AI-Val: {av.get('valid')}/{av.get('severity')} via {av.get('provider')}"
        print(f"  {r['name']}: {r['status']} via {r['gen_provider']}/{r['gen_model']}"
              f" | {r['n_claims']} claims | {r['elapsed']}s{val_str}")

# Save results
with open("_tmp_test_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\nResults saved to _tmp_test_results.json")

# Also save full answers to readable text file
with open("_tmp_test_answers.txt", "w", encoding="utf-8") as f:
    for r in results:
        if "error" in r:
            f.write(f"\n{'='*60}\n{r['name']} (from {r['table']}) — ERROR: {r['error']}\n{'='*60}\n\n")
            continue
        f.write(f"\n{'='*60}\n")
        f.write(f"{r['name']} (from {r['table']})\n")
        f.write(f"Status: {r['status']} | Provider: {r['gen_provider']}/{r['gen_model']} | Claims: {r['n_claims']} | Time: {r['elapsed']}s\n")
        if r.get('flags'):
            f.write(f"Flags: {r['flags']}\n")
        if r.get('ai_validation'):
            av = r['ai_validation']
            f.write(f"AI Validation: valid={av.get('valid')}, severity={av.get('severity')}, validator={av.get('provider')}/{av.get('model')}\n")
            if av.get('issues'):
                f.write(f"Validation issues: {av['issues']}\n")
        f.write(f"{'='*60}\n\n")
        f.write(r.get('answer', '(no answer)'))
        f.write(f"\n\n")
print(f"Full answers saved to _tmp_test_answers.txt")
