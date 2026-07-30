"""Check presence of API keys and environment variables.

Reports only: presente / assente / non valido.
Never prints or logs actual key values.
"""
import os
import re
from pathlib import Path


def _load_env() -> dict:
    env = {}
    p = Path.cwd() / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "MISTRAL_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "PERPLEXITY_API_KEY",
    "DATABASE_URL",
    "LM_STUDIO_API_URL",
    "LM_STUDIO_MODEL",
    "EUROPEANA_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "HOST",
    "PORT",
    "IA_S3_ACCESS_KEY",
    "IA_S3_SECRET_KEY",
]

_VALID_PATTERN = re.compile(r"^.{8,}$")


def check_keys() -> dict:
    """Return dict of key -> 'presente' | 'assente' | 'non valido'."""
    env = _load_env()
    result = {}
    for k in _KEYS:
        val = os.environ.get(k) or env.get(k, "")
        if not val:
            result[k] = "assente"
        elif not _VALID_PATTERN.match(val):
            result[k] = "non valido"
        else:
            result[k] = "presente"
    return result


if __name__ == "__main__":
    status = check_keys()
    for k in _KEYS:
        print(f"  {k}={status[k]}")

