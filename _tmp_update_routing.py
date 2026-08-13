"""Update ai_routing_policies: Ollama primary for generation tasks, OpenAI for validation."""
import json
from database import get_conn

conn = get_conn()

generation_tasks = [
    "generate_biography", "generate_viewpoints", "generate_timeline",
    "generate_research_plan", "generate_followup_queries", "narration",
]
validation_tasks = [
    "compare_claims", "propose_entity_matches", "evaluate_search_cycle",
    "decide_continue_or_stop", "verify_citations",
]

for task_type in generation_tasks:
    exists = conn.execute(
        "SELECT id FROM ai_routing_policies WHERE task_type=?", (task_type,)
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE ai_routing_policies SET primary_model_id=?, "
            "fallback_model_ids_json=?, version=? WHERE task_type=?",
            ("ollama", json.dumps(["mistral", "gemini", "anthropic", "openai"]),
             "v7.4-ollama-primary", task_type),
        )
    else:
        conn.execute(
            "INSERT INTO ai_routing_policies (task_type, min_requirements_json, "
            "primary_model_id, fallback_model_ids_json, max_cost, "
            "min_reserve_credit, timeout_seconds, max_retries, "
            "quality_criterion, version, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_type, json.dumps({"capabilities": ["text", "structured_output"], "min_quality": 0.7}),
             "ollama", json.dumps(["mistral", "gemini", "anthropic", "openai"]),
             0.50, 0.0, 120, 2, "structured_output_valid", "v7.4-ollama-primary",
             "2026-08-10T12:00:00", "2026-08-10T12:00:00"),
        )

for task_type in validation_tasks:
    exists = conn.execute(
        "SELECT id FROM ai_routing_policies WHERE task_type=?", (task_type,)
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE ai_routing_policies SET primary_model_id=?, "
            "fallback_model_ids_json=?, version=? WHERE task_type=?",
            ("openai", json.dumps(["mistral", "anthropic", "gemini", "ollama"]),
             "v7.4-openai-validator", task_type),
        )

conn.commit()

# Verify
rows = conn.execute(
    "SELECT task_type, primary_model_id, fallback_model_ids_json, version "
    "FROM ai_routing_policies ORDER BY task_type"
).fetchall()
for r in rows:
    d = dict(r)
    print(f"  {d['task_type']}: primary={d['primary_model_id']}, "
          f"fallback={d['fallback_model_ids_json'][:60]}, ver={d['version']}")

conn.close()
print("Done.")
