"""Quick test: call_ai with Ollama provider."""
from ai_client import call_ai

result = call_ai(
    task_type="generate_biography",
    system="Sei un narratore storico.",
    user="Rispondi in italiano: chi era Giulio Cesare in una frase.",
    max_tokens=200,
    temperature=0.3,
)

print(f"OK={result['ok']}")
print(f"Provider={result['provider']}")
print(f"Model={result['model']}")
print(f"Latency={result['latency_ms']}ms")
print(f"Tokens: in={result['input_tokens']} out={result['output_tokens']}")
print(f"Cost={result['cost']}")
print("---")
print(result["text"][:500])
