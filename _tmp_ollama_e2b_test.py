"""Test gemma4:e2b-it-qat speed with narration-like prompt."""
import requests, json, time

system = "Sei un narratore storico. Rispondi in JSON."
user = 'Scrivi una breve narrazione su un soldato italiano della WWII. Format: {"blocks":[{"block_id":"b1","role":"direct_answer","text":"...","claim_ids":[],"certainty":"verified"}],"needs_followup":false}'

t0 = time.time()
resp = requests.post(
    "http://localhost:11434/v1/chat/completions",
    headers={"Content-Type": "application/json"},
    json={
        "model": "gemma4:e2b-it-qat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 1000,
        "temperature": 0.3,
        "stream": False,
    },
    timeout=300,
)
elapsed = time.time() - t0
print(f"Status: {resp.status_code}")
print(f"Elapsed: {elapsed:.1f}s")
data = resp.json()
content = data["choices"][0]["message"]["content"]
print(f"Content length: {len(content)} chars")
print(f"Content: {content[:600]}")
print(f"Usage: {data.get('usage', {})}")
