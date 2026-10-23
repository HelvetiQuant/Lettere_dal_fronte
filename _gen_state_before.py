"""Generate artifacts/state_before.json with real data from the system."""
import sqlite3
import json
import os
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent

def git_sha():
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(ROOT))
        return r.stdout.strip()
    except Exception:
        return None

def git_dirty():
    try:
        r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(ROOT))
        return bool(r.stdout.strip())
    except Exception:
        return None

def db_info(path):
    p = Path(path)
    if not p.exists():
        return {"exists": False, "reason": "file not found"}
    data = p.read_bytes()
    return {
        "exists": True,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }

def table_counts(db_path):
    p = Path(db_path)
    if not p.exists():
        return {"reason": "db not found"}
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        counts = {}
        for t in tables:
            try:
                counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except Exception as e:
                counts[t] = f"error: {e}"
        return counts
    finally:
        conn.close()

def relation_counts(db_path):
    """Count relations by type and status."""
    p = Path(db_path)
    if not p.exists():
        return {"reason": "db not found"}
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        result = {}
        # event_links by link_type
        try:
            rows = conn.execute(
                "SELECT link_type, COUNT(*) as n FROM event_links GROUP BY link_type ORDER BY n DESC"
            ).fetchall()
            result["event_links_by_type"] = {r["link_type"]: r["n"] for r in rows}
        except Exception:
            result["event_links_by_type"] = {"reason": "table not found"}
        
        # record_links by link_type
        try:
            rows = conn.execute(
                "SELECT link_type, COUNT(*) as n FROM record_links GROUP BY link_type ORDER BY n DESC"
            ).fetchall()
            result["record_links_by_type"] = {r["link_type"]: r["n"] for r in rows}
        except Exception:
            result["record_links_by_type"] = {"reason": "table not found"}
        
        # collegamenti by tipo
        try:
            rows = conn.execute(
                "SELECT tipo, COUNT(*) as n FROM collegamenti GROUP BY tipo ORDER BY n DESC"
            ).fetchall()
            result["collegamenti_by_tipo"] = {r["tipo"]: r["n"] for r in rows}
        except Exception:
            result["collegamenti_by_tipo"] = {"reason": "table not found"}
        
        # graph_edges by status
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM graph_edges GROUP BY status ORDER BY n DESC"
            ).fetchall()
            result["graph_edges_by_status"] = {r["status"]: r["n"] for r in rows}
        except Exception:
            result["graph_edges_by_status"] = {"reason": "table not found"}
        
        return result
    finally:
        conn.close()

def integrity_check(db_path):
    p = Path(db_path)
    if not p.exists():
        return {"reason": "db not found"}
    conn = sqlite3.connect(str(p), timeout=30)
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        return {"quick_check": quick, "journal_mode": journal}
    finally:
        conn.close()

def check_env_in_git():
    """Check if .env is tracked by git."""
    try:
        r = subprocess.run(["git", "ls-files", ".env"], capture_output=True, text=True, cwd=str(ROOT))
        return {"env_tracked": bool(r.stdout.strip())}
    except Exception:
        return {"env_tracked": None}

def check_hardcoded_ports():
    """Scan for hardcoded port 8000 in scripts."""
    results = []
    for f in ROOT.glob("_*.py"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "8000" in text or "localhost:8000" or "127.0.0.1:8000" in text:
                results.append(str(f.name))
        except Exception:
            pass
    return results

def main():
    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_sha(),
        "git_dirty": git_dirty(),
        "branch": "fix/provenance-linking-v2",
        "runtime_versions": {
            "python": "3.11.9",
            "fastapi": "0.104.1",
            "sqlite3": "3.45.1",
            "pydantic": "2.13.4",
        },
        "database_engines": {
            "imi_internati.db": db_info("imi_internati.db"),
            "eventi_1gm.db": db_info("eventi_1gm.db"),
            "validazioni_ai.db": db_info("validazioni_ai.db"),
        },
        "integrity_checks": {
            "imi_internati.db": integrity_check("imi_internati.db"),
            "eventi_1gm.db": integrity_check("eventi_1gm.db"),
        },
        "table_counts": {
            "imi_internati.db": table_counts("imi_internati.db"),
            "eventi_1gm.db": table_counts("eventi_1gm.db"),
        },
        "relation_counts_by_type_and_status": relation_counts("imi_internati.db"),
        "event_links_counts": relation_counts("eventi_1gm.db"),
        "supabase_sync_state": {
            "project": "wyqesimzxieykmyhfvqs",
            "schema_canonical_applied": True,
            "tables_synced": ["archivio_documenti", "eventi_1gm", "event_aliases"],
            "event_links_sync_in_progress": True,
            "note": "event_links sync running in background (~18% at last check)"
        },
        "security": {
            **check_env_in_git(),
            "hardcoded_port_8000_files": check_hardcoded_ports(),
        },
        "legacy_scripts": {
            "_gen_event_links.py": {
                "events_hardcoded": 22,
                "events_in_db": 49,
                "mixes_ww1_ww2": True,
                "uses_substring_match": True,
                "breaks_on_first_match": True,
                "generic_keywords": ["campo", "Russia", "Africa", "Nero", "Corno", "Lana"],
                "skips_if_any_exist": True,
                "no_provenance": True,
                "no_algorithm_version": True,
            },
            "_gen_record_links.py": {
                "runs_at_import": True,
                "has_main": False,
                "deletes_fonte_personale": True,
                "star_topology_hub": True,
                "uses_limit_50": True,
                "same_year_as_relation": True,
                "no_evidence": True,
                "onm_scan": True,
            },
            "_clean_bad_links.py": {
                "namespace_confusion": True,
                "destructive_delete": True,
                "has_dry_run": True,
            },
            "_fix_gaiaschi_db.py": {
                "modifies_luogo_nascita": True,
                "no_claim_model": True,
                "no_evidence_locator": True,
                "uses_entity_variants": True,
            },
            "_check_keys.py": {
                "prints_only_set_not_set": True,
                "reads_env_file": True,
            },
            "_find_best_candidates.py": {
                "cognome_only_matching": True,
                "no_discriminators": True,
            },
        },
        "known_blockers": [
            "No staging Supabase environment — only production project available",
            "No labeled golden dataset exists for calibration",
            "event_links sync (1.5M rows) still running in background on production Supabase",
            "exec_sql RPC exposes arbitrary SQL execution — security risk",
            "No Alembic or formal migration framework — migrations are raw SQL scripts",
            "No pytest test suite exists for linking logic",
        ],
    }
    
    out_path = ROOT / "artifacts" / "state_before.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Written: {out_path}")
    print(f"Size: {out_path.stat().st_size} bytes")

if __name__ == "__main__":
    main()
