"""Apply canonical schema migration to Supabase — statement by statement.

This script parses the SQL migration file, splits it into individual
PostgreSQL statements, and executes each one via the Supabase exec_sql
RPC helper. It handles dollar-quoted strings (CREATE FUNCTION / triggers)
and skips transaction-control blocks which cannot run inside PL/pgSQL
EXECUTE.
"""
import sys
import time
from pathlib import Path
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SQL_FILE = Path(__file__).parent / "sql" / "001_supabase_historical_archive_core.sql"


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL into individual statements handling comments & dollar quotes."""
    statements = []
    current = []
    in_dollar_quote = False
    dollar_tag = None
    in_single_quote = False
    in_block_comment = False
    escape_next = False

    i = 0
    chars = list(sql)
    while i < len(chars):
        c = chars[i]
        next_c = chars[i + 1] if i + 1 < len(chars) else ""

        if in_block_comment:
            current.append(c)
            if c == "*" and next_c == "/":
                current.append(next_c)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_dollar_quote:
            current.append(c)
            # Check if we're at the closing tag
            tag_len = len(dollar_tag)
            segment = "".join(chars[i:i + tag_len])
            if segment == dollar_tag:
                # Ensure it's followed by non-identifier char or end
                after_pos = i + tag_len
                after_char = chars[after_pos] if after_pos < len(chars) else " "
                if not (after_char.isalnum() or after_char == "_"):
                    in_dollar_quote = False
                    dollar_tag = None
                    i += tag_len
                    continue
            i += 1
            continue

        if in_single_quote:
            current.append(c)
            if escape_next:
                escape_next = False
            elif c == "\\" and next_c == "'":
                escape_next = True
            elif c == "'" and next_c == "'":
                current.append(next_c)
                i += 2
                continue
            elif c == "'":
                in_single_quote = False
            i += 1
            continue

        # Start of block comment
        if c == "/" and next_c == "*":
            current.append(c)
            current.append(next_c)
            in_block_comment = True
            i += 2
            continue

        # Start of single quote
        if c == "'":
            current.append(c)
            in_single_quote = True
            i += 1
            continue

        # Start of dollar quote
        if c == "$":
            # Read the full tag
            j = i
            while j < len(chars) and chars[j] == "$":
                j += 1
            tag_chars = ["$"]
            while j < len(chars):
                ch = chars[j]
                if ch == "$":
                    tag_chars.append("$")
                    j += 1
                    break
                if ch.isalnum() or ch == "_":
                    tag_chars.append(ch)
                    j += 1
                else:
                    break
            if len(tag_chars) >= 2 and tag_chars[-1] == "$":
                full_tag = "".join(tag_chars)
                current.append(full_tag)
                dollar_tag = full_tag
                in_dollar_quote = True
                i = j
                continue

        current.append(c)

        if c == ";" and not in_dollar_quote and not in_single_quote:
            stmt = "".join(current).strip()
            if stmt:
                # Remove trailing semicolon for execution (exec_sql can handle it)
                statements.append(stmt)
            current = []

        i += 1

    if current:
        stmt = "".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


def is_meaningful_statement(stmt: str) -> bool:
    """Return True if statement contains non-comment SQL."""
    cleaned = []
    in_block = False
    i = 0
    s = stmt
    while i < len(s):
        if s[i:i + 2] == "/*":
            in_block = True
            i += 2
            continue
        if in_block and s[i:i + 2] == "*/":
            in_block = False
            i += 2
            continue
        if not in_block and s[i:i + 2] == "--":
            # skip to end of line
            while i < len(s) and s[i] != "\n":
                i += 1
            continue
        if not in_block:
            cleaned.append(s[i])
        i += 1
    text = "".join(cleaned).strip()
    return len(text) > 0


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
        # Extract first non-comment line for display
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
                    print(f"      SKIP (already exists)")
                    skip += 1
                    handled = True
                else:
                    print(f"      FAIL: {err[:150]}")
                    fail += 1
                    errors.append((first_line, err))
                    handled = True
        else:
            err = str(result.get("error", ""))
            if "already exists" in err.lower() or "duplicate key" in err.lower():
                print(f"      SKIP (already exists)")
                skip += 1
                handled = True
            else:
                print(f"      FAIL: {err[:150]}")
                fail += 1
                errors.append((first_line, err))
                handled = True

        if not handled:
            print(f"      OK")
            ok += 1

        time.sleep(0.1)

    print("=" * 72)
    print(f"Migration: {ok} OK, {skip} SKIP, {fail} FAIL / {len(statements)} statements")

    if errors:
        print("\nErrors:")
        for line, err in errors[:15]:
            print(f"  - {line[:60]}: {err[:120]}")

    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
