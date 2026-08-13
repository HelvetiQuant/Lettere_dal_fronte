"""Update DB: add gemma4:e2b-it-qat model, set it as primary for narration."""
from database import get_conn

conn = get_conn()

# Get ollama provider id
p = conn.execute("SELECT id FROM ai_providers WHERE code='ollama'").fetchone()
if not p:
    print("ERROR: ollama provider not found")
    exit(1)
provider_id = p[0]

# Check if model already exists
existing = conn.execute(
    "SELECT id FROM ai_models WHERE provider_id=? AND model_identifier=?",
    (provider_id, "gemma4:e2b-it-qat")
).fetchone()

if existing:
    print(f"Model already exists with id={existing[0]}")
else:
    conn.execute("""
        INSERT INTO ai_models (provider_id, model_identifier, capabilities_json,
                               quality_score, cost_per_unit, latency_score, context_window, status,
                               created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'enabled', datetime('now'), datetime('now'))
    """, (
        provider_id,
        "gemma4:e2b-it-qat",
        '["text", "vision", "structured_output"]',
        0.65,  # slightly lower quality than e4b
        0.0,   # free
        0.8,   # higher latency on CPU
        128000,
    ))
    print("Inserted gemma4:e2b-it-qat model")

# Update routing policy: use e2b-it-qat as primary for narration
conn.execute("""
    UPDATE ai_routing_policies 
    SET primary_model_id='ollama',
        fallback_model_ids_json='["mistral","gemini","anthropic","openai"]',
        version='v7.4-ollama-e2b'
    WHERE task_type='narration'
""")
print("Updated narration routing policy")

# Also update generation tasks
for task in ["generate_biography", "generate_viewpoints", "generate_timeline",
             "generate_research_plan", "generate_followup_queries"]:
    conn.execute("""
        UPDATE ai_routing_policies 
        SET primary_model_id='ollama',
            fallback_model_ids_json='["mistral","gemini","anthropic","openai"]',
            version='v7.4-ollama-e2b'
        WHERE task_type=?
    """, (task,))
    print(f"Updated routing for {task}")

conn.commit()
conn.close()
print("Done.")
