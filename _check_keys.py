import os
from pathlib import Path

env = {}
paths = [
    Path.cwd() / ".env",
]
for p in paths:
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

keys = [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "PERPLEXITY_API_KEY",
    "DATABASE_URL", "LM_STUDIO_API_URL", "EUROPEANA_API_KEY",
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
    "HOST", "PORT",
]
for k in keys:
    val = os.environ.get(k) or env.get(k, "")
    if not val:
        print(f"  {k}=NOT_SET")
    elif val.startswith("sk-") or val.startswith("sk-ant-") or len(val) < 10:
        print(f"  {k}=SET")
    else:
        print(f"  {k}=SET")

