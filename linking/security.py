"""
Security utilities for linking v2.

- Secret redaction in logs
- .env exclusion verification
- Packaging allowlist
- Supabase hardening recommendations
"""
import re
import os
from pathlib import Path


# Patterns that should never appear in logs or output
SECRET_PATTERNS = [
    (re.compile(r"sb_secret_[a-zA-Z0-9]{20,}"), "sb_secret_***REDACTED***"),
    (re.compile(r"sb_publishable_[a-zA-Z0-9]{20,}"), "sb_publishable_***REDACTED***"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "sk-***REDACTED***"),
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "***JWT_REDACTED***"),
    (re.compile(r"postgres://[^:]+:[^@]+@"), "postgres://***:***@"),
    (re.compile(r"supabase_key\s*=\s*['\"][^'\"]+['\"]"), "supabase_key='***REDACTED***'"),
    (re.compile(r"SERVICE_ROLE_KEY\s*=\s*['\"][^'\"]+['\"]"), "SERVICE_ROLE_KEY='***REDACTED***'"),
]


def redact_secrets(text: str) -> str:
    """Redact known secret patterns from text."""
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def check_env_not_tracked(repo_root: Path) -> dict:
    """Verify .env is not tracked by git."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "ls-files", ".env"],
            capture_output=True, text=True, cwd=str(repo_root)
        )
        tracked = bool(r.stdout.strip())
        return {
            "env_tracked_by_git": tracked,
            "safe": not tracked,
        }
    except Exception as e:
        return {"env_tracked_by_git": None, "error": str(e)}


def check_gitignore_has_env(repo_root: Path) -> dict:
    """Verify .env is in .gitignore."""
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        return {"gitignore_exists": False, "env_in_gitignore": False}
    content = gitignore.read_text(encoding="utf-8", errors="ignore")
    has_env = ".env" in content and not ".env.example" in content.split(".env")[0][-20:]
    # More precise check
    lines = content.splitlines()
    env_ignored = any(line.strip() == ".env" or line.strip() == ".env*" for line in lines)
    return {"gitignore_exists": True, "env_in_gitignore": env_ignored}


PACKAGING_ALLOWLIST = {
    "fastapi", "uvicorn", "pydantic", "sqlite3", "requests",
    "httpx", "python-multipart", "openai", "anthropic",
    "beautifulsoup4", "lxml", "playwright", "aiofiles",
    "python-dotenv", "PyYAML", "redis", "psycopg2-binary",
}


def check_packaging_allowlist(repo_root: Path) -> dict:
    """Check requirements.txt against allowlist."""
    req_file = repo_root / "requirements.txt"
    if not req_file.exists():
        return {"requirements_exists": False}
    
    content = req_file.read_text(encoding="utf-8", errors="ignore")
    packages = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Extract package name (before == or >= or ~=)
        pkg = re.split(r"[=<>!~]", line)[0].strip().lower()
        if pkg:
            packages.add(pkg)
    
    unknown = packages - PACKAGING_ALLOWLIST
    return {
        "requirements_exists": True,
        "total_packages": len(packages),
        "unknown_packages": sorted(unknown),
    }


def security_audit(repo_root: Path) -> dict:
    """Run full security audit."""
    return {
        "env_tracking": check_env_not_tracked(repo_root),
        "gitignore": check_gitignore_has_env(repo_root),
        "packaging": check_packaging_allowlist(repo_root),
        "recommendations": [
            "Disable exec_sql RPC on Supabase — use typed RPC functions instead",
            "Enable RLS on all v2 tables (already done in canonical schema)",
            "Use service role key only on backend, never expose to frontend",
            "Add rate limiting to API v2 endpoints",
            "Log redaction: use redact_secrets() before logging any external data",
        ],
    }
