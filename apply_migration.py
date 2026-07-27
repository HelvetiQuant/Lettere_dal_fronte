"""Apply canonical schema migration to Supabase — statement by statement."""
import sys
import time
import re
from pathlib import Path
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SQL_FILE = Path(__file__).parent / "sql" / "001_supabase_historical_archive_core.sql"

def split_statements(sql_text: str) -> list[str]:
    """Split SQL into individual statements, respecting $$ blocks."""
    statements = []
    current = []
    in_dollar_quote = False
    dollar_tag = None
    
    lines = sql_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Detect dollar-quote start
        if not in_dollar_quote:
            # Look for $tag$ pattern
            match = re.search(r'\$([a-zA-Z0-9_]*)\$', stripped)
            if match:
                tag = match.group(0)
                # Count occurrences in this line
                count = stripped.count(tag)
                if count >= 2:
                    # Opens and closes on same line - no state change
                    pass
                else:
                    in_dollar_quote = True
                    dollar_tag = tag
        
        current.append(line)
        
        # Detect dollar-quote end (on a different line)
        if in_dollar_quote and dollar_tag:
            if dollar_tag in stripped:
                count = stripped.count(dollar_tag)
                if count >= 2:
                    pass  # Multiple on same line, could be open+close or just references
                # Check if the tag appears after the opening position
                # Simple heuristic: if line contains the closing tag followed by ;
                if stripped.rstrip().endswith(dollar_tag + ";") or stripped.rstrip().endswith(dollar_tag):
                    in_dollar_quote = False
                    dollar_tag = None
        
        if not in_dollar_quote:
            if stripped.endswith(";"):
                stmt = "\n".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
        
        i += 1
    
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)
    
    return statements

def main():
    sql_text = SQL_FILE.read_text(encoding="utf-8")
    statements = split_statements(sql_text)
    
    # Filter: keep only real statements, skip pure comments
    real_stmts = []
    for s in statements:
        lines = [l for l in s.split("\n") if l.strip() and not l.strip().startswith("--")]
        if lines:
            real_stmts.append(s)
    
    print(f"SQL file: {len(sql_text):,} bytes, {len(real_stmts)} statements")
    print("=" * 70)
    
    ok = 0
    skip = 0
    fail = 0
    errors = []
    
    for i, stmt in enumerate(real_stmts):
        first_meaningful = ""
        for l in stmt.split("\n"):
            if l.strip() and not l.strip().startswith("--"):
                first_meaningful = l.strip()[:70]
                break
        
        # Skip DO $$ blocks - they can't run via exec_sql (transaction control)
        if stmt.strip().upper().startswith("DO $$") or stmt.strip().upper().startswith("DO$"):
            print(f"  [{i+1}/{len(real_stmts)}] SKIP DO block: {first_meaningful}...")
            skip += 1
            continue
        
        # For CREATE FUNCTION with $$, send the whole thing as one call
        # exec_sql should handle it if we pass it as a single string
        print(f"  [{i+1}/{len(real_stmts)}] {first_meaningful}...")
        
        result = execute_sql(stmt, timeout=120)
        if result.get("ok"):
            data = result.get("data", {})
            if isinstance(data, dict) and data.get("ok") is False:
                err = str(data.get("error", ""))
                if "already exists" in err.lower():
                    print(f"    SKIP (already exists)")
                    skip += 1
                else:
                    print(f"    FAIL: {err[:150]}")
                    fail += 1
                    errors.append((first_meaningful, err))
            else:
                print(f"    OK")
                ok += 1
        else:
            err = str(result.get("error", ""))
            if "already exists" in err.lower():
                print(f"    SKIP (already exists)")
                skip += 1
            else:
                print(f"    FAIL: {err[:150]}")
                fail += 1
                errors.append((first_meaningful, err))
        
        time.sleep(0.15)
    
    print("\n" + "=" * 70)
    print(f"Migration: {ok} OK, {skip} SKIP, {fail} FAIL out of {len(real_stmts)} statements")
    
    if errors:
        print("\nErrors detail:")
        for desc, err in errors[:10]:
            print(f"  - {desc}: {err[:100]}")
    
    return 1 if fail > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
