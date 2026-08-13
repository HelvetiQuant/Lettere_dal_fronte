"""Disable gemma4:e4b model, keep only e2b-it-qat active for CPU usage."""
from database import get_conn

conn = get_conn()
conn.execute("""
    UPDATE ai_models SET status='disabled' 
    WHERE model_identifier='gemma4:e4b'
""")
print("Disabled gemma4:e4b")

# Verify
models = conn.execute("""
    SELECT model_identifier, status, quality_score 
    FROM ai_models WHERE provider_id=(
        SELECT id FROM ai_providers WHERE code='ollama'
    )
""").fetchall()
for m in models:
    print(f"  {m[0]}: status={m[1]}, quality={m[2]}")

conn.commit()
conn.close()
