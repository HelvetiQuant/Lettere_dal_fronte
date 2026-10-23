"""Create canonical updated_at triggers on Supabase."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TRIGGERS = [
    "archive.repositories",
    "archive.collections",
    "archive.external_items",
    "archive.representations",
    "archive.text_versions",
    "archive.passages",
    "ai.datasets",
    "ai.dataset_versions",
]

ok = fail = 0
for table in TRIGGERS:
    name = f"trg_updated_{table.split('.')[-1]}"
    sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = '{name}' AND tgrelid = '{table}'::regclass
        ) THEN
            CREATE TRIGGER {name}
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at();
        END IF;
    END $$;
    """
    print(f"Creating trigger {name} on {table}...")
    r = execute_sql(sql, timeout=60)
    if r.get("ok"):
        data = r.get("data") or {}
        if isinstance(data, dict) and data.get("ok") is False:
            print(f"  FAIL: {data.get('error', '')[:120]}")
            fail += 1
        else:
            print("  OK")
            ok += 1
    else:
        print(f"  FAIL: {r.get('error', '')[:120]}")
        fail += 1

print(f"\nTriggers: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
