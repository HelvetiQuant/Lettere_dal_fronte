"""Check graph tables and event_links audit in detail."""
import sqlite3, json

conn = sqlite3.connect('imi_internati.db')
conn.row_factory = sqlite3.Row

# Graph tables
print("=== Graph schema tables in imi_internati.db ===")
for t in ['graph_nodes', 'graph_edges', 'graph_edge_reviews',
          'graph_pipeline_runs', 'graph_integrity_issues', 'archival_metadata',
          'edge_evidence', 'edge_versions']:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info([{t}])")]
        print(f"  {t}: {count} rows, cols={cols}")
    except:
        print(f"  {t}: NOT FOUND")

# Claims detail
print("\n=== claims table schema ===")
cols = [c for c in conn.execute("PRAGMA table_info(claims)")]
for c in cols:
    print(f"  {c[1]} ({c[2]})")

print("\n=== claim_evidence table schema ===")
cols = [c for c in conn.execute("PRAGMA table_info(claim_evidence)")]
for c in cols:
    print(f"  {c[1]} ({c[2]})")

# Sample claims
print("\n=== Sample claims (first 3) ===")
rows = conn.execute("SELECT * FROM claims LIMIT 3").fetchall()
for r in rows:
    print(f"  {dict(r)}")

# Sample claim_evidence
print("\n=== Sample claim_evidence (first 3) ===")
rows = conn.execute("SELECT * FROM claim_evidence LIMIT 3").fetchall()
for r in rows:
    print(f"  {dict(r)}")

# Audit: record_links with no evidence
print("\n=== Audit: record_links with no evidence_json ===")
count_no_evidence = conn.execute("SELECT COUNT(*) FROM record_links WHERE evidence_json IS NULL OR evidence_json = ''").fetchone()[0]
count_total = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
print(f"  {count_no_evidence}/{count_total} links have no evidence_json")

# Audit: record_links by link_type
print("\n=== record_links by link_type ===")
rows = conn.execute("SELECT link_type, COUNT(*) as cnt FROM record_links GROUP BY link_type ORDER BY cnt DESC").fetchall()
for r in rows:
    print(f"  {r['link_type']}: {r['cnt']}")

# Audit: record_links by match_status
print("\n=== record_links by match_status ===")
rows = conn.execute("SELECT match_status, COUNT(*) as cnt FROM record_links GROUP BY match_status ORDER BY cnt DESC").fetchall()
for r in rows:
    print(f"  {r['match_status']}: {r['cnt']}")

# Audit: record_links by algorithm_version
print("\n=== record_links by algorithm_version ===")
rows = conn.execute("SELECT algorithm_version, COUNT(*) as cnt FROM record_links GROUP BY algorithm_version ORDER BY cnt DESC").fetchall()
for r in rows:
    print(f"  {r['algorithm_version']}: {r['cnt']}")

# Audit: legacy_unverified count
print("\n=== record_links legacy_unverified ===")
rows = conn.execute("SELECT legacy_unverified, COUNT(*) as cnt FROM record_links GROUP BY legacy_unverified").fetchall()
for r in rows:
    print(f"  legacy_unverified={r['legacy_unverified']}: {r['cnt']}")

# Eventi_1gm: check for WWII events mixed in
print("\n=== eventi_1gm: all events ===")
conn2 = sqlite3.connect('eventi_1gm.db')
conn2.row_factory = sqlite3.Row
rows = conn2.execute("SELECT id, nome, data_inizio, data_fine, luogo FROM eventi_1gm ORDER BY id").fetchall()
for r in rows:
    print(f"  {r['id']}: {r['nome']} ({r['data_inizio']} → {r['data_fine']}) — {r['luogo']}")

# event_links: check link types
print("\n=== event_links by link_type ===")
rows = conn2.execute("SELECT link_type, COUNT(*) as cnt FROM event_links GROUP BY link_type ORDER BY cnt DESC").fetchall()
for r in rows:
    print(f"  {r['link_type']}: {r['cnt']}")

# event_links: check evidence
print("\n=== event_links with no evidence ===")
count_no_ev = conn2.execute("SELECT COUNT(*) FROM event_links WHERE evidence IS NULL OR evidence = '' OR evidence = '[]'").fetchone()[0]
count_total_el = conn2.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
print(f"  {count_no_ev}/{count_total_el} event_links have no evidence")

conn.close()
conn2.close()
