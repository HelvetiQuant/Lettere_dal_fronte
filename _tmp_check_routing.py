from ai_router import select_model
r = select_model("narration")
print(f"Provider: {r['provider_code']}")
print(f"Model: {r['model_identifier']}")
print(f"Reason: {r['reason']}")
print(f"Policy: {r['policy_version']}")
