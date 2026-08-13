"""Test Ollama with streaming and smaller output."""
import requests, json, time

system = "Sei un narratore storico. Rispondi in JSON."
user = "Scrivi una frase su un soldato italiano della WWII. Format: {\"text\":\"...\"}"

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
        "max_tokens": 500,
        "temperature": 0.3,
        "stream": True,
    },
    timeout=120,
    stream=True,
)
elapsed = time.time() - t0
print(f"Status: {resp.status_code}")

full_content = ""
chunks = 0
for line in resp.iter_lines():
    if line:
        line_str = line.decode("utf-8")
        if line_str.startswith("data: "):
            line_str = line_str[6:]
        if line_str == "[DONE]":
            break
        try:
            chunk = json.loads(line_str)
            delta = chunk["choices"][0].get("delta", {}).get("content", "")
            if delta:
                full_content += delta
                chunks += 1
        except:
            pass

elapsed = time.time() - t0
print(f"Elapsed: {elapsed:.1f}s")
print(f"Chunks: {chunks}")
print(f"Content ({len(full_content)} chars): {full_content[:500]}")
