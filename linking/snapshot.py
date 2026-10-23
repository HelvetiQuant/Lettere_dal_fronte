"""
SQLite snapshot utility using the Backup API.

Creates a safe, consistent copy of a SQLite database with:
- PRAGMA quick_check and integrity_check
- SHA-256 checksum
- Manifest with metadata
- Read-only verification

Usage:
    python -m linking.snapshot create --database imi_internati --reason "pre-linking-v2"
    python -m linking.snapshot list
    python -m linking.snapshot verify --id <snapshot-id>
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).parent.parent
SNAPSHOT_DIR = ROOT / "snapshots"


def _db_path(name: str) -> Path:
    """Resolve database name to path."""
    if name.endswith(".db"):
        return ROOT / name
    return ROOT / f"{name}.db"


def _snapshot_manifest_path(snapshot_id: str) -> Path:
    return SNAPSHOT_DIR / f"{snapshot_id}.manifest.json"


def _snapshot_db_path(snapshot_id: str, db_name: str) -> Path:
    return SNAPSHOT_DIR / f"{snapshot_id}.{db_name}"


def create_snapshot(database: str, reason: str) -> dict:
    """
    Create a safe snapshot of a SQLite database.
    
    Uses the SQLite Backup API for a consistent copy,
    regardless of WAL mode.
    """
    src_path = _db_path(database)
    if not src_path.exists():
        raise FileNotFoundError(f"Database not found: {src_path}")
    
    snapshot_id = f"snap_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    
    # Step 1: Integrity checks on source
    src_conn = sqlite3.connect(str(src_path), timeout=30)
    src_conn.row_factory = sqlite3.Row
    
    quick_check = src_conn.execute("PRAGMA quick_check").fetchone()[0]
    integrity_check = src_conn.execute("PRAGMA integrity_check").fetchone()[0]
    journal_mode = src_conn.execute("PRAGMA journal_mode").fetchone()[0]
    
    # Checkpoint WAL
    checkpoint_result = None
    if journal_mode.lower() == "wal":
        checkpoint_result = src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    
    # Critical table counts
    tables = [r[0] for r in src_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'idx_%' ORDER BY name"
    ).fetchall()]
    counts = {}
    for t in tables:
        try:
            counts[t] = src_conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        except Exception:
            counts[t] = None
    
    src_conn.close()
    
    # Step 2: Backup using SQLite Backup API
    dst_path = _snapshot_db_path(snapshot_id, src_path.name)
    if dst_path.exists():
        dst_path.unlink()
    dst_conn = sqlite3.connect(str(dst_path))
    src_conn = sqlite3.connect(str(src_path), timeout=30)
    
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()
    
    # Step 3: SHA-256 of snapshot
    sha256 = hashlib.sha256(dst_path.read_bytes()).hexdigest()
    size = dst_path.stat().st_size
    
    # Step 4: Verify snapshot is readable
    verify_conn = sqlite3.connect(str(dst_path))
    verify_conn.execute("PRAGMA query_only=ON")
    verify_quick = verify_conn.execute("PRAGMA quick_check").fetchone()[0]
    verify_count = len(verify_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall())
    verify_conn.close()
    
    # Step 5: Write manifest
    manifest = {
        "snapshot_id": snapshot_id,
        "database": src_path.name,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(src_path),
        "snapshot_path": str(dst_path),
        "size_bytes": size,
        "sha256": sha256,
        "source_integrity": {
            "quick_check": quick_check,
            "integrity_check": integrity_check,
            "journal_mode": journal_mode,
            "wal_checkpoint": list(checkpoint_result) if checkpoint_result else None,
        },
        "snapshot_integrity": {
            "quick_check": verify_quick,
            "table_count": verify_count,
        },
        "table_counts": counts,
        "table_count_total": len(tables),
    }
    
    manifest_path = _snapshot_manifest_path(snapshot_id)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    return manifest


def list_snapshots() -> list:
    """List all snapshots."""
    if not SNAPSHOT_DIR.exists():
        return []
    snapshots = []
    for f in SNAPSHOT_DIR.glob("*.manifest.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            snapshots.append({
                "snapshot_id": data["snapshot_id"],
                "database": data["database"],
                "reason": data["reason"],
                "created_at": data["created_at"],
                "size_bytes": data["size_bytes"],
                "sha256": data["sha256"][:16] + "...",
                "quick_check": data["snapshot_integrity"]["quick_check"],
            })
        except Exception:
            pass
    return snapshots


def verify_snapshot(snapshot_id: str) -> dict:
    """Verify a snapshot's integrity."""
    manifest_path = _snapshot_manifest_path(snapshot_id)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Snapshot manifest not found: {manifest_path}")
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_path = Path(manifest["snapshot_path"])
    
    if not db_path.exists():
        return {"valid": False, "reason": "snapshot file missing"}
    
    # Check SHA-256
    actual_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
    if actual_sha != manifest["sha256"]:
        return {"valid": False, "reason": "sha256 mismatch", "expected": manifest["sha256"], "actual": actual_sha}
    
    # Check readability
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only=ON")
    quick = conn.execute("PRAGMA quick_check").fetchone()[0]
    conn.close()
    
    return {
        "valid": quick == "ok",
        "sha256_match": True,
        "quick_check": quick,
        "size_bytes": db_path.stat().st_size,
    }


def main():
    parser = argparse.ArgumentParser(description="SQLite snapshot utility")
    sub = parser.add_subparsers(dest="command")
    
    create_p = sub.add_parser("create", help="Create a snapshot")
    create_p.add_argument("--database", required=True, help="Database name (without .db)")
    create_p.add_argument("--reason", required=True, help="Reason for snapshot")
    
    sub.add_parser("list", help="List all snapshots")
    
    verify_p = sub.add_parser("verify", help="Verify a snapshot")
    verify_p.add_argument("--id", required=True, help="Snapshot ID")
    
    args = parser.parse_args()
    
    if args.command == "create":
        result = create_snapshot(args.database, args.reason)
        print(f"Snapshot created: {result['snapshot_id']}")
        print(f"  Database: {result['database']}")
        print(f"  Size: {result['size_bytes']:,} bytes")
        print(f"  SHA-256: {result['sha256']}")
        print(f"  Quick check: {result['snapshot_integrity']['quick_check']}")
        print(f"  Tables: {result['table_count_total']}")
        print(f"  Manifest: {_snapshot_manifest_path(result['snapshot_id'])}")
        
    elif args.command == "list":
        snapshots = list_snapshots()
        if not snapshots:
            print("No snapshots found.")
        for s in snapshots:
            print(f"  {s['snapshot_id']}  {s['database']:30s}  {s['size_bytes']:>12,}  {s['quick_check']}  {s['reason']}")
            
    elif args.command == "verify":
        result = verify_snapshot(args.id)
        print(json.dumps(result, indent=2))
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
