"""Update routing: Mistral primary for generation, Ollama fallback. OpenAI/Mistral for validation."""
from database import get_conn

conn = get_conn()

# Generation tasks: Mistral primary, Ollama fallback
for task in ["narration", "generate_biography", "generate_viewpoints", "generate_timeline",
             "generate_research_plan", "generate_followup_queries"]:
    conn.execute("""
        UPDATE ai_routing_policies 
        SET primary_model_id='mistral',
            fallback_model_ids_json='["ollama","gemini","anthropic","openai"]',
            version='v7.4-mistral-primary'
        WHERE task_type=?
    """, (task,))
    print(f"Updated {task}: mistral primary, ollama fallback")

# Validation tasks: OpenAI primary, Mistral fallback (unchanged)
for task in ["validate_output", "verify_citations"]:
    conn.execute("""
        UPDATE ai_routing_policies 
        SET primary_model_id='openai',
            fallback_model_ids_json='["mistral","anthropic","gemini"]',
            version='v7.4-mistral-primary'
        WHERE task_type=?
    """, (task,))
    print(f"Updated {task}: openai primary, mistral fallback")

conn.commit()
conn.close()
print("Done.")
