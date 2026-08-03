"""Phase A — Inspect SQLite schema, row counts, indexes, foreign keys."""
import sqlite3
import json
import sys

DBS = ["imi_internati.db", "eventi_1gm.db"]

for db_path in DBS:
    print(f"\n{'='*80}")
    print(f"DATABASE: {db_path}")
    print(f"{'='*80}")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        print(f"\nTables ({len(tables)}):")
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM [{t}]")
            count = cur.fetchone()[0]
            print(f"  {t}: {count:,} rows")

        # Indexes
        cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name")
        indexes = cur.fetchall()
        print(f"\nIndexes ({len(indexes)}):")
        for idx in indexes:
            print(f"  {idx['name']} on {idx['tbl_name']}")

        # Foreign keys
        for t in tables:
            cur.execute(f"PRAGMA foreign_key_list([{t}])")
            fks = cur.fetchall()
            if fks:
                print(f"\nForeign keys for {t}:")
                for fk in fks:
                    print(f"  {fk['table']}.{fk['to']} <- {t}.{fk['from']}")

        # Views
        cur.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
        views = [r[0] for r in cur.fetchall()]
        if views:
            print(f"\nViews ({len(views)}):")
            for v in views:
                print(f"  {v}")

        # Schema for key tables
        key_tables = ["eventi_1gm", "event_links", "record_links", "collegamenti",
                       "entita", "fonti_indice", "internati", "decorati", "caduti_albooro",
                       "caduti_ww1", "archivio_documenti", "source_authority_registry"]
        for t in key_tables:
            if t in tables:
                cur.execute(f"PRAGMA table_info([{t}])")
                cols = cur.fetchall()
                print(f"\nSchema [{t}]:")
                for c in cols:
                    pk = " PK" if c["pk"] else ""
                    print(f"  {c['name']} {c['type']}{pk}")

        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")

# Also check for other DBs
import os
for f in os.listdir("."):
    if f.endswith(".db") and f not in DBS:
        print(f"\n{'='*80}")
        print(f"OTHER DB: {f}")
        try:
            conn = sqlite3.connect(f)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]
            print(f"  Tables ({len(tables)}): {', '.join(tables[:20])}")
            conn.close()
        except Exception as e:
            print(f"  ERROR: {e}")
