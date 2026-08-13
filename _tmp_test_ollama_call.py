"""Quick test: call_ai_json with narration task to verify Ollama is used."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from ai_client import call_ai_json

result = call_ai_json(
    task_type="narration",
    system="Sei un narratore storico. Rispondi in JSON.",
    user='Genera un breve blocco narrativo di test. Rispondi con JSON: {"blocks":[{"block_id":"b1","role":"direct_answer","text":"Test","claim_ids":[],"certainty":"non_factual"}],"needs_followup":false}',
    max_tokens=500,
    temperature=0.3,
)

print(f"OK: {result.get('ok')}")
print(f"Provider: {result.get('provider')}")
print(f"Model: {result.get('model')}")
print(f"Error: {result.get('error', 'none')}")
if result.get('data'):
    print(f"Data: {str(result['data'])[:300]}")
elif result.get('raw'):
    print(f"Raw: {result['raw'][:300]}")
