"""Apply 002_supabase_core_events.sql to Supabase — statement by statement.

Riusa lo split_sql_statements/is_meaningful_statement di apply_migration_v2.py
per non duplicare il parser SQL.
"""
import sys
import time
from pathlib import Path

from apply_migration_v2 import split_sql_statements, is_meaningful_statement
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SQL_FILE = Path(__file__).parent / "sql" / "002_supabase_core_events.sql"


def main():
    if not SQL_FILE.exists():
        print(f"Migration file not found: {SQL_FILE}")
        return 1

    sql_text = SQL_FILE.read_text(encoding="utf-8")
    raw_statements = split_sql_statements(sql_text)
    statements = [s for s in raw_statements if is_meaningful_statement(s)]

    print(f"SQL migration: {len(sql_text):,} bytes -> {len(statements)} statements")
    print("=" * 72)

    ok = skip = fail = 0
    errors = []

    for idx, stmt in enumerate(statements):
        first_line = ""
        for line in stmt.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("--") and not stripped.startswith("/*"):
                first_line = stripped[:68]
                break
        if not first_line:
            first_line = stmt.strip()[:68]

        label = f"[{idx + 1}/{len(statements)}]"
        print(f"{label} {first_line}...")

        result = execute_sql(stmt, timeout=120)
        handled = False
        if result.get("ok"):
            data = result.get("data") or {}
            if isinstance(data, dict) and data.get("ok") is False:
                err = str(data.get("error", ""))
                if "already exists" in err.lower() or "duplicate key" in err.lower():
                    print("      SKIP (already exists)")
                    skip += 1
                    handled = True
                else:
                    print(f"      FAIL: {err[:200]}")
                    fail += 1
                    errors.append((first_line, err))
                    handled = True
        else:
            err = str(result.get("error", ""))
            if "already exists" in err.lower() or "duplicate key" in err.lower():
                print("      SKIP (already exists)")
                skip += 1
                handled = True
            else:
                print(f"      FAIL: {err[:200]}")
                fail += 1
                errors.append((first_line, err))
                handled = True

        if not handled:
            print("      OK")
            ok += 1

        time.sleep(0.1)

    print("=" * 72)
    print(f"Migration: {ok} OK, {skip} SKIP, {fail} FAIL / {len(statements)} statements")

    if errors:
        print("\nErrors:")
        for line, err in errors[:20]:
            print(f"  - {line[:60]}: {err[:200]}")

    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
