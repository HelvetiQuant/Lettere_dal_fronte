"""Schema additivo per eventi canonici.

Aggiunge colonne canoniche alla tabella eventi_1gm esistente senza cancellare
o riscrivere dati. Crea anche la tabella event_aliases per varianti multiple.

Usage:
    python event_schema.py              # deploy (additive, safe)
    python event_schema.py --dry-run    # show what would be changed
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

EDB = Path(__file__).parent / "eventi_1gm.db"


ADDITIVE_COLUMNS = [
    ("stable_id", "TEXT"),
    ("conflict", "TEXT DEFAULT 'WWI'"),
    ("event_type", "TEXT DEFAULT 'battaglia'"),
    ("parent_event_id", "TEXT"),
    ("temporal_precision", "TEXT DEFAULT 'day'"),
    ("general_location", "TEXT"),
    ("localities_json", "TEXT DEFAULT '[]'"),
    ("subjects_json", "TEXT DEFAULT '[]'"),
    ("units_json", "TEXT DEFAULT '[]'"),
    ("review_status", "TEXT DEFAULT 'candidate'"),
    ("narrative_version", "TEXT"),
    ("narrative_updated_at", "TEXT"),
]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    alias TEXT NOT NULL,
    alias_type TEXT DEFAULT 'alias',
    created_at TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES eventi_1gm(id),
    UNIQUE(event_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_event_aliases_event ON event_aliases(event_id);
CREATE INDEX IF NOT EXISTS idx_event_aliases_text ON event_aliases(alias);
"""


def init_event_schema(conn=None) -> None:
    own = conn is None
    conn = conn or sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row
    try:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(eventi_1gm)").fetchall()}
        for col_name, col_type in ADDITIVE_COLUMNS:
            if col_name not in existing:
                conn.execute(f'ALTER TABLE eventi_1gm ADD COLUMN "{col_name}" {col_type}')
        conn.executescript(SCHEMA_SQL)

        # Populate stable_id for existing rows if missing
        rows = conn.execute(
            "SELECT id, nome FROM eventi_1gm WHERE stable_id IS NULL OR stable_id = ''"
        ).fetchall()
        for row in rows:
            stable_id = f"evt_{row['id']:04d}"
            conn.execute(
                "UPDATE eventi_1gm SET stable_id=? WHERE id=?",
                (stable_id, row["id"]),
            )

        # Populate event_aliases from existing JSON aliases column
        import json
        rows = conn.execute("SELECT id, aliases FROM eventi_1gm WHERE aliases IS NOT NULL AND aliases != '[]'").fetchall()
        for row in rows:
            try:
                aliases = json.loads(row["aliases"])
            except (json.JSONDecodeError, TypeError):
                continue
            for alias in aliases:
                if alias and alias.strip():
                    conn.execute(
                        "INSERT OR IGNORE INTO event_aliases (event_id, alias, alias_type, created_at) VALUES (?, ?, 'alias', datetime('now'))",
                        (row["id"], alias.strip()),
                    )

        conn.commit()
    finally:
        if own:
            conn.close()


def event_schema_available(conn=None) -> bool:
    own = conn is None
    conn = conn or sqlite3.connect(str(EDB), uri=True)
    try:
        has_aliases = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_aliases'"
        ).fetchone()
        if not has_aliases:
            return False
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(eventi_1gm)").fetchall()}
        required = {"stable_id", "conflict", "event_type", "review_status"}
        return required.issubset(cols)
    finally:
        if own:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Event canonical schema migration")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        conn = sqlite3.connect(str(EDB), uri=True)
        conn.row_factory = sqlite3.Row
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(eventi_1gm)").fetchall()}
        missing = [c for c, _ in ADDITIVE_COLUMNS if c not in existing]
        has_aliases = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_aliases'"
        ).fetchone()
        conn.close()
        if missing:
            print(f"Would add columns: {', '.join(missing)}")
        else:
            print("All canonical columns already present.")
        if not has_aliases:
            print("Would create: event_aliases table + 2 indexes")
        else:
            print("event_aliases table already exists.")
        return

    print("Deploying event canonical schema (additive, safe)...")
    init_event_schema()
    conn = sqlite3.connect(str(EDB), uri=True)
    conn.row_factory = sqlite3.Row
    if event_schema_available(conn):
        print("OK: event canonical schema deployed successfully.")
        count = conn.execute("SELECT COUNT(*) FROM event_aliases").fetchone()[0]
        print(f"  event_aliases: {count} rows")
        stable = conn.execute("SELECT COUNT(*) FROM eventi_1gm WHERE stable_id IS NOT NULL AND stable_id != ''").fetchone()[0]
        print(f"  eventi_1gm with stable_id: {stable}")
    else:
        print("ERROR: schema deployment failed verification.")
    conn.close()


if __name__ == "__main__":
    main()
