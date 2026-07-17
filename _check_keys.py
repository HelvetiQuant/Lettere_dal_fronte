import os
from pathlib import Path

env = {}
paths = [
    Path.home() / "Desktop" / "lettere dal fronte backup_2026-06-28" / ".env",
    Path.cwd() / ".env",
]
for p in paths:
    if p.exists():
        print(f"Found .env: {p}")
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY",
        "GEMINI_API_KEY", "PERPLEXITY_API_KEY"]
for k in keys:
    val = os.environ.get(k) or env.get(k, "")
    if val:
        print(f"  {k}: YES ({val[:8]}...)")
    else:
        print(f"  {k}: NO")
