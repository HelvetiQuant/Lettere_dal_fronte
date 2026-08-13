"""Test RIZZA GIOVANNI specifically — verify AMBIGUOUS_IDENTITY forces deterministic."""
import time
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
t0 = time.time()
result = orch.execute("RIZZA GIOVANNI", intent="PERSON_LOOKUP")
elapsed = time.time() - t0

snap = result.get("snapshot", {})
nr = result.get("narration_result", {})

print(f"Identity Status: {snap.get('identity_status')}")
print(f"Candidate Identities: {len(snap.get('candidate_identities', []))}")
print(f"Person Claims: {len(snap.get('person_claims', []))}")

gen = nr.get("generation", {})
print(f"\nMode: {gen.get('mode')}")
print(f"Provider: {gen.get('provider')}")
print(f"Status: {nr.get('status')}")
print(f"Claims used: {len(nr.get('used_claim_ids', []))}")
print(f"Omitted: {len(nr.get('omitted_claims', []))}")
print(f"Flags: {nr.get('validation_flags', [])}")

answer = nr.get("answer_markdown", "")
print(f"\n--- FULL ANSWER ---")
print(answer[:3000])
print(f"--- END ANSWER ---")
print(f"\nElapsed: {elapsed:.1f}s")
