import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "imi_internati.db"

# Official pricing (per 1M tokens or per unit)
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # per 1M tokens
    "gpt-4o": {"input": 2.50, "output": 10.00},      # per 1M tokens
    "mistral-ocr": {"per_page": 0.001},               # per OCR page
    "mistral-ocr-free": {"per_page": 0.0, "free_limit": 1000},  # free tier
}

# Default monthly budget (USD) - can be overridden via .env
DEFAULT_BUDGET = 50.0


def _get_budget() -> float:
    import os
    from extractor import _load_api_key
    try:
        env_path = Path.home() / "Desktop" / "lettere dal fronte backup_2026-06-28" / ".env"
        if env_path.exists():
            for line in env_path.read_text(errors="ignore").splitlines():
                if line.startswith("AI_BUDGET_USD="):
                    return float(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return DEFAULT_BUDGET


def init_usage_table():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            ocr_pages INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            lettera TEXT,
            pagina INTEGER
        )
    """)
    conn.commit()
    conn.close()


def log_openai_usage(model: str, input_tokens: int, output_tokens: int,
                     lettera: str = None, pagina: int = None):
    """Log OpenAI API usage and compute cost."""
    pricing = PRICING.get(model, PRICING["gpt-4o-mini"])
    cost = (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO api_usage (timestamp, provider, model, input_tokens, output_tokens, cost_usd, lettera, pagina) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), "openai", model, input_tokens, output_tokens, cost, lettera, pagina),
    )
    conn.commit()
    conn.close()


def log_mistral_ocr(pages: int, lettera: str = None, pagina: int = None):
    """Log Mistral OCR usage and compute cost."""
    cost = pages * PRICING["mistral-ocr"]["per_page"]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO api_usage (timestamp, provider, model, ocr_pages, cost_usd, lettera, pagina) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), "mistral", "mistral-ocr-latest", pages, cost, lettera, pagina),
    )
    conn.commit()
    conn.close()


def get_usage_summary() -> dict:
    """Get usage summary with costs and estimated remaining budget."""
    budget = _get_budget()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT SUM(cost_usd) as total FROM api_usage").fetchone()
    total_cost = total["total"] or 0.0

    by_provider = conn.execute(
        "SELECT provider, SUM(cost_usd) as cost, SUM(input_tokens) as input_tok, SUM(output_tokens) as output_tok, SUM(ocr_pages) as pages FROM api_usage GROUP BY provider"
    ).fetchall()

    by_model = conn.execute(
        "SELECT model, SUM(cost_usd) as cost, COUNT(*) as calls FROM api_usage GROUP BY model ORDER BY cost DESC"
    ).fetchall()

    today = conn.execute(
        "SELECT SUM(cost_usd) as cost FROM api_usage WHERE date(timestamp) = date('now')"
    ).fetchone()

    conn.close()

    remaining = budget - total_cost
    pct_used = (total_cost / budget * 100) if budget > 0 else 0

    return {
        "budget_usd": round(budget, 2),
        "total_cost_usd": round(total_cost, 4),
        "remaining_usd": round(remaining, 2),
        "pct_used": round(pct_used, 1),
        "today_cost_usd": round(today["cost"] or 0, 4),
        "by_provider": [
            {"provider": r["provider"], "cost": round(r["cost"] or 0, 4),
             "input_tokens": r["input_tok"] or 0, "output_tokens": r["output_tok"] or 0,
             "ocr_pages": r["pages"] or 0}
            for r in by_provider
        ],
        "by_model": [
            {"model": r["model"], "cost": round(r["cost"] or 0, 4), "calls": r["calls"]}
            for r in by_model
        ],
    }
