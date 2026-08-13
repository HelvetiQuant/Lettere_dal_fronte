"""Test Ollama generation + AI cross-validation pipeline on BRUTTI ALFIO."""
import logging
import json
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7 as UnifiedOrchestrator
from v7_narrator import NarratorV7_v2

target_name = "BRUTTI ALFIO"

print(f"=== Pipeline test: {target_name} ===")
print()

# Step 1: Run orchestrator to get snapshot
orch = UnifiedOrchestrator()
result = orch.execute(target_name, intent="PERSON_LOOKUP")

if not result or not result.get("snapshot"):
    print("ERROR: No snapshot returned")
    print(f"Result keys: {list(result.keys()) if result else 'None'}")
    sys.exit(1)

snapshot = result["snapshot"]
print(f"Snapshot: {snapshot.intent}")
print(f"Observations: {len(snapshot.observations)}")
print(f"Accepted evidence: {len(snapshot.accepted_evidence)}")
print(f"Identity status: {snapshot.identity_status}")
print()

# Step 2: Narrate with AI
narrator = NarratorV7_v2()
narration = narrator.narrate(snapshot, use_ai=True)

print(f"Status: {narration.status}")
print(f"Generation mode: {narration.generation.mode}")
print(f"Generation provider: {narration.generation.provider}")
print(f"Generation model: {narration.generation.model}")
print(f"AI validation: {narration.generation.ai_validation}")
print(f"Validation flags: {narration.validation_flags[:5]}")
print(f"Used claims: {len(narration.used_claim_ids)}")
print()

print("=== ANSWER MARKDOWN (first 2000 chars) ===")
print(narration.answer_markdown[:2000])
print()

if narration.generation.ai_validation:
    av = narration.generation.ai_validation
    print(f"=== AI CROSS-VALIDATION ===")
    print(f"Validator: {av.get('provider')}/{av.get('model')}")
    print(f"Valid: {av.get('valid')}")
    print(f"Severity: {av.get('severity')}")
    if av.get('issues'):
        print(f"Issues: {av['issues']}")
    if av.get('suggestions'):
        print(f"Suggestions: {av['suggestions']}")
