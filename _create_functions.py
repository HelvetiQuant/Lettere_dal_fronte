"""Create the remaining canonical helper functions on Supabase."""
import sys
from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION archive.generate_stable_id(p_provider TEXT, p_external_id TEXT)
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE raw TEXT;
BEGIN
    IF p_provider IS NOT NULL THEN
        raw := lower(trim(p_provider)) || ':' || lower(trim(p_external_id));
    ELSE
        raw := 'id:' || lower(trim(p_external_id));
    END IF;
    RETURN 'sha256:' || encode(digest(raw::bytea, 'sha256'), 'hex');
END;
$$""",
    """CREATE OR REPLACE FUNCTION archive.content_hash(p_text TEXT)
RETURNS TEXT LANGUAGE plpgsql AS $$
BEGIN
    RETURN 'sha256:' || encode(digest(p_text::bytea, 'sha256'), 'hex');
END;
$$""",
    """CREATE OR REPLACE FUNCTION archive.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$""",
]

TRIGGERS = [
    "CREATE TRIGGER IF NOT EXISTS trg_updated_repositories BEFORE UPDATE ON archive.repositories FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_collections BEFORE UPDATE ON archive.collections FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_external_items BEFORE UPDATE ON archive.external_items FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_representations BEFORE UPDATE ON archive.representations FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_text_versions BEFORE UPDATE ON archive.text_versions FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_passages BEFORE UPDATE ON archive.passages FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_datasets BEFORE UPDATE ON ai.datasets FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
    "CREATE TRIGGER IF NOT EXISTS trg_updated_dataset_versions BEFORE UPDATE ON ai.dataset_versions FOR EACH ROW EXECUTE FUNCTION archive.set_updated_at()",
]

ALL = FUNCTIONS + TRIGGERS

ok = skip = fail = 0
for sql in ALL:
    first = sql.split("\n")[0][:70]
    print(f"{first}...")
    r = execute_sql(sql, timeout=60)
    if r.get("ok"):
        data = r.get("data") or {}
        if isinstance(data, dict) and data.get("ok") is False:
            err = str(data.get("error", ""))
            if "already exists" in err.lower():
                print("  SKIP")
                skip += 1
            else:
                print(f"  FAIL: {err[:120]}")
                fail += 1
        else:
            print("  OK")
            ok += 1
    else:
        err = str(r.get("error", ""))
        if "already exists" in err.lower():
            print("  SKIP")
            skip += 1
        else:
            print(f"  FAIL: {err[:120]}")
            fail += 1

print(f"\nFunctions/triggers: {ok} OK, {skip} SKIP, {fail} FAIL")
sys.exit(1 if fail else 0)
