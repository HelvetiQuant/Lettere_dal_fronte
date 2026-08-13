"""Direct Ollama test with simple prompt."""
import requests, json, time

t0 = time.time()
resp = requests.post(
    "http://localhost:11434/v1/chat/completions",
    headers={"Content-Type": "application/json"},
    json={
        "model": "gemma4:e4b",
        "messages": [{"role": "user", "content": "Ciao, rispondi in una frase."}],
        "max_tokens": 100,
        "stream": False,
    },
    timeout=300,
)
elapsed = time.time() - t0
print(f"Status: {resp.status_code}")
print(f"Elapsed: {elapsed:.1f}s")
data = resp.json()
print(f"Content: {data['choices'][0]['message']['content'][:200]}")
print(f"Usage: {data.get('usage', {})}")
