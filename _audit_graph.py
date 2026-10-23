"""Check for graph tables and legacy link tables in imi_internati.db"""
import sqlite3

conn = sqlite3.connect('imi_internati.db')
conn.row_factory = sqlite3.Row

# Check for graph schema tables
graph_tables = ['graph_nodes', 'graph_edges', 'graph_edge_reviews',
                'graph_pipeline_runs', 'graph_integrity_issues', 'archival_metadata']

print("=== Graph schema tables ===")
for t in graph_tables:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {count} rows")
    except:
        print(f"  {t}: NOT FOUND")

# Check legacy link tables
print("\n=== Legacy link tables ===")
for t in ['record_links', 'event_links', 'collegamenti', 'entita']:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info([{t}])")]
        print(f"  {t}: {count} rows, cols={cols}")
    except:
        print(f"  {t}: NOT FOUND")

# Check event_links in eventi_1gm.db
print("\n=== eventi_1gm.db ===")
conn2 = sqlite3.connect('eventi_1gm.db')
conn2.row_factory = sqlite3.Row
for t in ['eventi_1gm', 'event_links']:
    try:
        count = conn2.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        cols = [c[1] for c in conn2.execute(f"PRAGMA table_info([{t}])")]
        print(f"  {t}: {count} rows, cols={cols}")
    except:
        print(f"  {t}: NOT FOUND")

# Sample event_links
print("\n=== Sample event_links (first 5) ===")
rows = conn2.execute("SELECT * FROM event_links LIMIT 5").fetchall()
for r in rows:
    print(f"  {dict(r)}")

# Sample eventi_1gm
print("\n=== Sample eventi_1gm (first 5) ===")
rows = conn2.execute("SELECT * FROM eventi_1gm LIMIT 5").fetchall()
for r in rows:
    print(f"  {dict(r)}")

# Check for claims/claim_evidence
print("\n=== Claims tables ===")
for t in ['claims', 'claim_evidence', 'external_source_records', 'external_person_mentions', 'external_record_links']:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {count} rows")
    except:
        print(f"  {t}: NOT FOUND")

# Check record_links sample
print("\n=== Sample record_links (first 3) ===")
rows = conn.execute("SELECT * FROM record_links LIMIT 3").fetchall()
for r in rows:
    print(f"  {dict(r)}")

# Check for FTS tables
print("\n=== FTS tables ===")
fts = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'idx_%'").fetchall()
for f in fts:
    print(f"  {f[0]}")

conn.close()
conn2.close()
