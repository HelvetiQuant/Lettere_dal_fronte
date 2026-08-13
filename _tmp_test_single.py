"""Quick single-name test to verify AI cross-validation is now triggered."""
import json, time
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
name = "ALBERINI ANTONIO"

t0 = time.time()
result = orch.execute(name, intent="PERSON_LOOKUP")
elapsed = time.time() - t0

# Extract narration result
if hasattr(result, 'narration_result'):
    nr = result.narration_result
else:
    nr = result.get('narration_result', result)

print(f"Name: {name}")
print(f"Elapsed: {elapsed:.1f}s")

# Check generation info
gen = None
if hasattr(nr, 'generation'):
    gen = nr.generation
elif isinstance(nr, dict):
    gen = nr.get('generation')

if gen:
    if hasattr(gen, 'mode'):
        print(f"Mode: {gen.mode}")
        print(f"Provider: {gen.provider}")
        print(f"Model: {gen.model}")
        print(f"AI Validation: {gen.ai_validation}")
    else:
        print(f"Mode: {gen.get('mode','?')}")
        print(f"Provider: {gen.get('provider','?')}")
        print(f"Model: {gen.get('model','?')}")
        print(f"AI Validation: {gen.get('ai_validation')}")
else:
    print("No generation info found")
    print(f"Result type: {type(nr)}")
    if isinstance(nr, dict):
        print(f"Keys: {list(nr.keys())[:10]}")

# Print full answer
answer = ""
if hasattr(nr, 'answer_markdown'):
    answer = nr.answer_markdown
elif isinstance(nr, dict):
    answer = nr.get('answer_markdown', nr.get('answer_text', nr.get('answer', '')))
print(f"\n--- FULL ANSWER ---")
print(answer)
print(f"--- END ANSWER ---")
