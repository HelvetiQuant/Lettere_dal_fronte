"""Update routing: OpenAI primary for generation, Mistral fallback. No Ollama/Gemma for report generation."""
from database import get_conn

conn = get_conn()

# Generation tasks: OpenAI primary, Mistral fallback, NO Ollama/Gemma
for task in ["narration", "generate_biography", "generate_viewpoints", "generate_timeline",
             "generate_research_plan", "generate_followup_queries"]:
    conn.execute("""
        UPDATE ai_routing_policies 
        SET primary_model_id='openai',
            fallback_model_ids_json='["mistral","anthropic","gemini"]',
            version='v7.5-openai-primary'
        WHERE task_type=?
    """, (task,))
    print(f"Updated {task}: openai primary, mistral fallback")

# Validation tasks: OpenAI primary, Mistral fallback
for task in ["validate_output", "verify_citations"]:
    conn.execute("""
        UPDATE ai_routing_policies 
        SET primary_model_id='openai',
            fallback_model_ids_json='["mistral","anthropic","gemini"]',
            version='v7.5-openai-primary'
        WHERE task_type=?
    """, (task,))
    print(f"Updated {task}: openai primary, mistral fallback")

# Disable Ollama for report generation but keep as provider
conn.execute("""
    UPDATE ai_models
    SET status='disabled'
    WHERE provider_id = (SELECT id FROM ai_providers WHERE code='ollama')
      AND model_identifier = 'gemma4:e2b-it-qat'
""")
print("Disabled gemma4:e2b-it-qat for report generation")

conn.commit()
conn.close()
print("Done.")
