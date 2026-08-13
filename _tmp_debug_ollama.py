"""Debug why Ollama is not selected for narration."""
from ai_router import select_model, get_routing_policy, _breaker_is_open
from ai_client import get_available_providers
from database import get_conn
import json

print("1. Available providers:", get_available_providers())
print()

print("2. Routing policy for 'narration':")
policy = get_routing_policy("narration")
print(f"   primary_model_id: {policy.get('primary_model_id')}")
print(f"   fallback: {policy.get('fallback_model_ids_json')}")
print(f"   version: {policy.get('version')}")
print()

print("3. Circuit breaker for ollama:", _breaker_is_open("ollama"))
print()

print("4. select_model for 'narration':")
sel = select_model("narration")
print(f"   provider: {sel.get('provider_code')}")
print(f"   model: {sel.get('model_identifier')}")
print(f"   reason: {sel.get('reason')}")
print()

print("5. Check Ollama provider in DB:")
conn = get_conn()
p = conn.execute("SELECT * FROM ai_providers WHERE code='ollama'").fetchone()
if p:
    p = dict(p)
    print(f"   id={p['id']}, status={p['status']}, budget={p['budget_configured']}, reserve={p['budget_reserve']}")
    print(f"   capabilities: {p['declared_capabilities_json']}")
    models = conn.execute("SELECT * FROM ai_models WHERE provider_id=?", (p['id'],)).fetchall()
    for m in models:
        m = dict(m)
        print(f"   model: {m['model_identifier']}, status={m['status']}, caps={m['capabilities_json']}, "
              f"quality={m['quality_score']}, cost={m['cost_per_unit']}")
else:
    print("   NOT FOUND")

print()
print("6. Check budget logic:")
if p:
    budget = p['budget_configured']
    reserve = p['budget_reserve']
    estimated_cost = 0.0  # ollama is free
    available = budget - reserve
    print(f"   budget={budget}, reserve={reserve}, estimated_cost={estimated_cost}, available={available}")
    print(f"   estimated_cost > available: {estimated_cost > available}")

conn.close()
