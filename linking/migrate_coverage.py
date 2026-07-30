"""
Migration: add coverage_* columns to fonti_indice (SQLite + Supabase).

This is an additive, idempotent migration. It adds:
- coverage_start TEXT
- coverage_end TEXT
- coverage_precision TEXT DEFAULT 'unknown'
- coverage_source_field TEXT
- coverage_extraction_method TEXT
- coverage_confidence REAL DEFAULT 0.0

Then runs a backfill from existing data_inizio/data_fine and regex on titolo.

Usage:
    python -m linking.migrate_coverage           # SQLite only
    python -m linking.migrate_coverage --supabase # SQLite + Supabase
    python -m linking.migrate_coverage --dry-run  # Show what would change
"""
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "imi_internati.db"

COVERAGE_COLUMNS = [
    ("coverage_start", "TEXT", None),
    ("coverage_end", "TEXT", None),
    ("coverage_precision", "TEXT", "unknown"),
    ("coverage_source_field", "TEXT", None),
    ("coverage_extraction_method", "TEXT", None),
    ("coverage_confidence", "REAL", 0.0),
]


def _column_exists(conn, table, col):
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c[1] == col for c in cols)


def migrate_sqlite(dry_run=False):
    """Add coverage_* columns to fonti_indice in SQLite."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    added = 0
    for col_name, col_type, col_default in COVERAGE_COLUMNS:
        if _column_exists(conn, "fonti_indice", col_name):
            print(f"  [SQLite] fonti_indice.{col_name} already exists, skipping")
            continue
        if dry_run:
            print(f"  [SQLite] DRY-RUN: ALTER TABLE fonti_indice ADD COLUMN {col_name} {col_type}")
            added += 1
        else:
            default_clause = f" DEFAULT {col_default!r}" if col_default is not None else ""
            conn.execute(f"ALTER TABLE fonti_indice ADD COLUMN {col_name} {col_type}{default_clause}")
            print(f"  [SQLite] Added fonti_indice.{col_name} {col_type}")
            added += 1
    if not dry_run:
        conn.commit()
    conn.close()
    return added


def _extract_year_from_text(text):
    """Extract a year or year range from text using regex."""
    if not text:
        return None, None, None

    # Year range: 1915-1918, 1943-45, 1943–45
    m = re.search(r"\b(19\d{2})\s*[-–]\s*(?:(19)\s*)?(\d{2})\b", text)
    if m:
        y1 = int(m.group(1))
        y2_suffix = m.group(3)
        y2_prefix = m.group(2) or str(y1)[:2]
        y2 = int(f"{y2_prefix}{y2_suffix}") if len(y2_suffix) == 2 else int(y2_suffix)
        if 1900 <= y1 <= 1950 and 1900 <= y2 <= 1950:
            return str(y1), str(y2), "range"

    # Single year: 1917
    m = re.search(r"\b(19[0-4]\d)\b", text)
    if m:
        y = m.group(1)
        return y, y, "year"

    return None, None, None


def backfill_sqlite(dry_run=False):
    """Backfill coverage_* from data_inizio/data_fine and titolo regex."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, titolo, data_inizio, data_fine, soggetti_collegati, note, "
        "coverage_start FROM fonti_indice"
    ).fetchall()

    updated = 0
    skipped = 0

    for row in rows:
        row = dict(row)

        # Skip if already has coverage_start
        if row.get("coverage_start"):
            skipped += 1
            continue

        cov_start = None
        cov_end = None
        cov_precision = "unknown"
        source_field = None
        method = "none"
        confidence = 0.0

        # 1. Try data_inizio/data_fine
        di = (row.get("data_inizio") or "").strip()
        df = (row.get("data_fine") or "").strip()
        if di:
            cov_start = di
            cov_end = df or di
            cov_precision = "direct"
            source_field = "data_inizio"
            method = "direct_copy"
            confidence = 1.0
        else:
            # 2. Try regex on titolo + soggetti_collegati + note
            text = " ".join(filter(None, [
                row.get("titolo", ""),
                row.get("soggetti_collegati", ""),
                row.get("note", ""),
            ]))
            ys, ye, prec = _extract_year_from_text(text)
            if ys:
                cov_start = ys
                cov_end = ye
                cov_precision = prec
                source_field = "titolo"
                method = "regex_year"
                confidence = 0.7

        if cov_start:
            if not dry_run:
                conn.execute(
                    "UPDATE fonti_indice SET coverage_start=?, coverage_end=?, "
                    "coverage_precision=?, coverage_source_field=?, "
                    "coverage_extraction_method=?, coverage_confidence=? "
                    "WHERE id=?",
                    (cov_start, cov_end, cov_precision, source_field,
                     method, confidence, row["id"])
                )
            updated += 1
        else:
            skipped += 1

    if not dry_run:
        conn.commit()

    print(f"  [SQLite] Backfill: {updated} updated, {skipped} skipped (already have coverage or no data)")
    conn.close()
    return updated, skipped


def migrate_supabase(dry_run=False):
    """Add coverage_* columns to fonti_indice in Supabase."""
    try:
        from supabase_client import execute_sql
    except ImportError:
        print("  [Supabase] supabase_client not available, skipping")
        return 0

    statements = []
    for col_name, col_type, col_default in COVERAGE_COLUMNS:
        default_clause = f" DEFAULT '{col_default}'" if col_default is not None else ""
        if col_type == "REAL":
            default_clause = f" DEFAULT {col_default}" if col_default is not None else ""
        stmt = f"ALTER TABLE archive.fonti_indice ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause};"
        statements.append(stmt)

    full_sql = "\n".join(statements)

    if dry_run:
        print(f"  [Supabase] DRY-RUN: would execute:\n{full_sql}")
        return len(statements)

    try:
        execute_sql(full_sql)
        print(f"  [Supabase] Added {len(statements)} columns to archive.fonti_indice")
        return len(statements)
    except Exception as e:
        print(f"  [Supabase] ERROR: {e}")
        return 0


def backfill_supabase(dry_run=False):
    """Backfill coverage_* in Supabase from existing data."""
    try:
        from supabase_client import execute_sql
    except ImportError:
        print("  [Supabase] supabase_client not available, skipping backfill")
        return 0

    sql = """
    UPDATE archive.fonti_indice
    SET 
        coverage_start = COALESCE(coverage_start, data_inizio),
        coverage_end = COALESCE(coverage_end, data_fine),
        coverage_precision = CASE 
            WHEN coverage_start IS NOT NULL THEN 'direct'
            ELSE coverage_precision
        END,
        coverage_source_field = CASE 
            WHEN coverage_start IS NOT NULL THEN 'data_inizio'
            ELSE coverage_source_field
        END,
        coverage_extraction_method = CASE 
            WHEN coverage_start IS NOT NULL THEN 'direct_copy'
            ELSE coverage_extraction_method
        END,
        coverage_confidence = CASE 
            WHEN coverage_start IS NOT NULL THEN 1.0
            ELSE coverage_confidence
        END
    WHERE coverage_start IS NULL AND data_inizio IS NOT NULL;
    """

    if dry_run:
        print("  [Supabase] DRY-RUN: would backfill coverage from data_inizio/data_fine")
        return 0

    try:
        result = execute_sql(sql)
        print(f"  [Supabase] Backfill completed")
        return 1
    except Exception as e:
        print(f"  [Supabase] Backfill ERROR: {e}")
        return 0


def main():
    dry_run = "--dry-run" in sys.argv
    do_supabase = "--supabase" in sys.argv

    print("=" * 60)
    print(f"Migration: coverage_* columns on fonti_indice")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"Supabase: {'YES' if do_supabase else 'NO'}")
    print("=" * 60)

    print("\n[1/4] SQLite: add columns")
    migrate_sqlite(dry_run=dry_run)

    print("\n[2/4] SQLite: backfill from existing data")
    backfill_sqlite(dry_run=dry_run)

    if do_supabase:
        print("\n[3/4] Supabase: add columns")
        migrate_supabase(dry_run=dry_run)

        print("\n[4/4] Supabase: backfill from existing data")
        backfill_supabase(dry_run=dry_run)

    print("\n" + "=" * 60)
    print("Migration complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
