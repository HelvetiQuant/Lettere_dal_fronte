"""Test Ollama with a larger prompt similar to narration."""
import requests, json, time

system = """Sei un narratore storico specializzato nella storia militare italiana del XX secolo.
Genera un report narrativo strutturato in JSON con i seguenti campi:
- blocks: lista di blocchi narrativi, ognuno con block_id, role, text, claim_ids, certainty
- needs_followup: boolean
- followup_question: string o null

Ogni blocco deve avere:
- block_id: identificatore univoco (es. b1, b2)
- role: uno tra direct_answer, identity, chronology, context, conflict, limitations
- text: il testo narrativo
- claim_ids: lista di ID claim di riferimento
- certainty: uno tra verified, probable, conflicting, unverified_limit, non_factual
"""

user = """Genera una breve narrazione storica su un soldato italiano della Seconda Guerra Mondiale.
Rispondi in JSON con il formato specificato."""

t0 = time.time()
resp = requests.post(
    "http://localhost:11434/v1/chat/completions",
    headers={"Content-Type": "application/json"},
    json={
        "model": "gemma4:e4b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
        "stream": False,
        # "response_format": {"type": "json_object"},  # disabled for test
    },
    timeout=300,
)
elapsed = time.time() - t0
print(f"Status: {resp.status_code}")
print(f"Elapsed: {elapsed:.1f}s")
data = resp.json()
content = data["choices"][0]["message"]["content"]
print(f"Content length: {len(content)} chars")
print(f"Content (first 500): {content[:500]}")
print(f"Usage: {data.get('usage', {})}")
