"""Baseline audit script — Phase A.
Inspects all databases, counts rows, checks integrity.
Does NOT modify any data."""
import sqlite3
import os
import json
import sys

DBS = {
    "imi_internati.db": "DB principale (internati, decorati, entita, collegamenti, fonti)",
    "eventi_1gm.db": "DB eventi Prima Guerra Mondiale",
    "validazioni_ai.db": "DB validazioni AI",
    "imi_extractor.db": "DB vuoto/legacy",
}

def audit_db(path):
    if not os.path.exists(path):
        return {"error": "not found", "size_bytes": 0}
    size = os.path.getsize(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Integrity check
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

    # Foreign key check
    fk_issues = []
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        fk_result = conn.execute("PRAGMA foreign_key_check").fetchall()
        fk_issues = [dict(r) for r in fk_result]
    except Exception as e:
        fk_issues = [{"error": str(e)}]

    # Tables
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()

    table_info = {}
    for t in tables:
        tname = t[0]
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM [{tname}]").fetchone()[0]
        except Exception as e:
            count = f"error: {e}"

        # Get columns
        try:
            cols = conn.execute(f"PRAGMA table_info([{tname}])").fetchall()
            col_names = [c[1] for c in cols]
        except:
            col_names = []

        table_info[tname] = {
            "count": count,
            "columns": col_names,
        }

    # Indexes
    indexes = conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name"
    ).fetchall()
    idx_list = [{"name": r[0], "table": r[1]} for r in indexes]

    conn.close()
    return {
        "size_bytes": size,
        "size_mb": round(size / (1024*1024), 2),
        "integrity": integrity,
        "fk_issues": fk_issues,
        "tables": table_info,
        "table_count": len(tables),
        "index_count": len(indexes),
        "indexes": idx_list,
    }


results = {}
for db_path, description in DBS.items():
    print(f"\n{'='*60}")
    print(f"Auditing: {db_path} ({description})")
    print(f"{'='*60}")
    info = audit_db(db_path)
    results[db_path] = {"description": description, **info}

    if "error" in info:
        print(f"  ERROR: {info['error']}")
        continue

    print(f"  Size: {info['size_mb']} MB")
    print(f"  Integrity: {info['integrity']}")
    print(f"  FK issues: {len(info['fk_issues'])}")
    print(f"  Tables: {info['table_count']}")
    print(f"  Indexes: {info['index_count']}")
    print()
    for tname, tdata in sorted(info["tables"].items()):
        cnt = tdata["count"]
        if isinstance(cnt, int) and cnt > 0:
            print(f"    {tname:45s} {cnt:>10,} rows  cols={len(tdata['columns'])}")
        elif isinstance(cnt, int):
            print(f"    {tname:45s} {cnt:>10} rows  (empty)")

# Save JSON
out_path = "docs/audits/baseline_audit.json"
os.makedirs("docs/audits", exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
print(f"\n\nJSON saved to {out_path}")
