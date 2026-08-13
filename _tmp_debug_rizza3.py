"""Debug RIZZA GIOVANNI — dump claims and observations from dict result."""
import json, time
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
t0 = time.time()
result = orch.execute("RIZZA GIOVANNI", intent="PERSON_LOOKUP")
elapsed = time.time() - t0

snap = result.get("snapshot")
if not snap:
    print("No snapshot!")
    print(list(result.keys()))
    exit()

print(f"Identity Status: {snap.get('identity_status')}")
print(f"Corroboration: {snap.get('corroboration_status')}")
print(f"Person Claims: {len(snap.get('person_claims', []))}")
print(f"Context Claims: {len(snap.get('context_claims', []))}")
print(f"Provider Ledger: {len(snap.get('provider_ledger', []))} observations")
print(f"Target: {snap.get('target')}")
print(f"Origin: {snap.get('origin')}")

print(f"\n=== PERSON CLAIMS (ALL) ===")
for i, c in enumerate(snap.get("person_claims", [])):
    print(f"  [{i}] id={c.get('claim_id')} pred={c.get('predicate')} "
          f"val_norm={c.get('value_normalized')} val_raw={c.get('value_raw','')[:60]} "
          f"status={c.get('status')} src={c.get('source')} "
          f"cluster={c.get('identity_cluster_id')} "
          f"func={c.get('source_function')}")

print(f"\n=== CONTEXT CLAIMS ===")
for i, c in enumerate(snap.get("context_claims", [])):
    print(f"  [{i}] {c}")

print(f"\n=== CANDIDATE IDENTITIES ===")
for ci in snap.get("candidate_identities", []):
    print(f"  {ci}")

print(f"\n=== PROVIDER LEDGER (first 30) ===")
for i, obs in enumerate(snap.get("provider_ledger", [])[:30]):
    print(f"  [{i}] provider={obs.get('provider','?')} source_id={obs.get('source_id','?')} "
          f"class={obs.get('classification','?')} is_origin={obs.get('is_origin')}")

# Count by provider
tables = {}
for obs in snap.get("provider_ledger", []):
    t = obs.get("provider", "?")
    tables[t] = tables.get(t, 0) + 1
print(f"\n=== OBSERVATIONS BY PROVIDER ===")
for t, c in sorted(tables.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

# Check narration result
nr = result.get("narration_result")
if nr:
    print(f"\n=== NARRATION RESULT ===")
    print(f"Status: {nr.get('status')}")
    gen = nr.get("generation", {})
    print(f"Mode: {gen.get('mode')} Provider: {gen.get('provider')} Model: {gen.get('model')}")
    print(f"Claims used: {nr.get('used_claim_ids', [])}")
    print(f"Omitted: {len(nr.get('omitted_claims', []))}")
    print(f"Flags: {nr.get('validation_flags', [])}")
    print(f"\nAnswer:\n{nr.get('answer_markdown', '')[:2000]}")

print(f"\nElapsed: {elapsed:.1f}s")
