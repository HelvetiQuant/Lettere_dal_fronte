"""Apply the canonical Supabase schema in chunks, handling $$ blocks and extensions."""
import re
import sys
from dotenv import load_dotenv
load_dotenv(override=True)
from supabase_client import execute_sql

SQL_FILE = "sql/001_supabase_historical_archive_core.sql"

def split_sql(sql_text: str) -> list[str]:
    """Split SQL into individual statements, respecting $$ blocks."""
    statements = []
    current = []
    in_dollar = False
    dollar_tag = ""
    lines = sql_text.split("\n")
    
    for line in lines:
        stripped = line.strip()
        
        # Track $$ blocks
        if not in_dollar:
            # Check for $$ start
            if "$$" in stripped:
                # Find the tag (e.g., $$ or $func$)
                match = re.search(r'\$[^$]*\$', stripped)
                if match:
                    dollar_tag = match.group()
                    # Check if it closes on the same line
                    rest = stripped[match.end():]
                    if dollar_tag in rest:
                        pass  # opens and closes on same line
                    else:
                        in_dollar = True
            current.append(line)
            # Check for statement end (semicolon outside $$)
            if stripped.endswith(";") and not in_dollar:
                stmt = "\n".join(current).strip()
                if stmt and not stmt.startswith("--"):
                    statements.append(stmt)
                current = []
        else:
            current.append(line)
            if dollar_tag in stripped:
                in_dollar = False
                # Check if statement ends after the closing tag
                after_tag = stripped[stripped.index(dollar_tag) + len(dollar_tag):]
                if after_tag.strip().endswith(";"):
                    stmt = "\n".join(current).strip()
                    if stmt:
                        statements.append(stmt)
                    current = []
    
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)
    
    return statements


def main():
    with open(SQL_FILE, encoding="utf-8") as f:
        sql_text = f.read()
    
    statements = split_sql(sql_text)
    print(f"Total statements: {len(statements)}")
    
    ok = 0
    errors = 0
    skipped = 0
    
    for i, stmt in enumerate(statements):
        # Skip comments-only
        clean = "\n".join(l for l in stmt.split("\n") if not l.strip().startswith("--")).strip()
        if not clean:
            skipped += 1
            continue
        
        # Skip vector-related (extension not installed)
        if "VECTOR(1536)" in stmt or "vector_cosine_ops" in stmt:
            print(f"  [{i+1}] SKIP (vector extension): {stmt[:60]}...")
            skipped += 1
            continue
        
        # Skip public.eventi_1gm references (table doesn't exist yet on new Supabase)
        if "public.eventi_1gm" in stmt:
            print(f"  [{i+1}] SKIP (eventi_1gm not yet on Supabase): {stmt[:60]}...")
            skipped += 1
            continue
        
        preview = clean[:80].replace("\n", " ")
        print(f"  [{i+1}/{len(statements)}] {preview}...", end=" ")
        
        r = execute_sql(stmt, timeout=120)
        if r.get("ok"):
            data = r.get("data")
            if isinstance(data, dict) and data.get("ok") is False:
                print(f"ERR: {data.get('error', 'unknown')[:100]}")
                errors += 1
            else:
                print("OK")
                ok += 1
        else:
            print(f"ERR: {r.get('error', 'unknown')[:100]}")
            errors += 1
    
    print(f"\n{'='*60}")
    print(f"Schema applicato: {ok} OK, {errors} errori, {skipped} skip")


if __name__ == "__main__":
    main()
