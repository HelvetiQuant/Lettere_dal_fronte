"""Phase A — Inspect legacy scripts, event_links data, and key tables."""
import sqlite3
import json
import os

# 1. Legacy scripts inventory
print("=" * 80)
print("LEGACY SCRIPTS INVENTORY")
print("=" * 80)
legacy_patterns = ["_gen_", "_clean_", "_fix_", "_check_", "_status", "_find_", "_inspect_", "_schema_"]
for f in sorted(os.listdir(".")):
    if f.endswith(".py") and any(f.startswith(p) for p in legacy_patterns):
        size = os.path.getsize(f)
        print(f"  {f} ({size:,} bytes)")

# 2. Event links in eventi_1gm.db — sample and stats
print("\n" + "=" * 80)
print("EVENT_LINKS IN eventi_1gm.db")
print("=" * 80)
conn = sqlite3.connect("eventi_1gm.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Total
cur.execute("SELECT COUNT(*) FROM event_links")
total = cur.fetchone()[0]
print(f"Total event_links: {total:,}")

# By status
cur.execute("SELECT status, COUNT(*) as cnt FROM event_links GROUP BY status ORDER BY cnt DESC")
for r in cur.fetchall():
    print(f"  status={r['status']}: {r['cnt']:,}")

# By rule_version
cur.execute("SELECT rule_version, COUNT(*) as cnt FROM event_links GROUP BY rule_version ORDER BY cnt DESC")
for r in cur.fetchall():
    print(f"  rule_version={r['rule_version']}: {r['cnt']:,}")

# By link_type
cur.execute("SELECT link_type, COUNT(*) as cnt FROM event_links GROUP BY link_type ORDER BY cnt DESC")
for r in cur.fetchall():
    print(f"  link_type={r['link_type']}: {r['cnt']:,}")

# By target_table
cur.execute("SELECT target_table, COUNT(*) as cnt FROM event_links GROUP BY target_table ORDER BY cnt DESC")
for r in cur.fetchall():
    print(f"  target_table={r['target_table']}: {r['cnt']:,}")

# By confidence distribution
cur.execute("SELECT confidence, COUNT(*) as cnt FROM event_links GROUP BY confidence ORDER BY confidence DESC")
for r in cur.fetchall():
    print(f"  confidence={r['confidence']}: {r['cnt']:,}")

# Sample 5 event_links
print("\nSample event_links (5):")
cur.execute("SELECT * FROM event_links LIMIT 5")
for r in cur.fetchall():
    print(f"  {dict(r)}")

# 3. Eventi_1gm content
print("\n" + "=" * 80)
print("EVENTI_1GM CONTENT (eventi_1gm.db)")
print("=" * 80)
cur.execute("SELECT id, nome, data_inizio, data_fine, event_type, parent_event_id, stable_id FROM eventi_1gm ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r['id']} | {r['nome']} | {r['data_inizio']} -> {r['data_fine']} | type={r['event_type']} | parent={r['parent_event_id']} | stable={r['stable_id']}")

# 4. Record_links in imi_internati.db
print("\n" + "=" * 80)
print("RECORD_LINKS IN imi_internati.db")
print("=" * 80)
conn2 = sqlite3.connect("imi_internati.db")
conn2.row_factory = sqlite3.Row
cur2 = conn2.cursor()

cur2.execute("SELECT COUNT(*) FROM record_links")
total_rl = cur2.fetchone()[0]
print(f"Total record_links: {total_rl:,}")

cur2.execute("SELECT status, COUNT(*) as cnt FROM record_links GROUP BY status ORDER BY cnt DESC")
for r in cur2.fetchall():
    print(f"  status={r['status']}: {r['cnt']:,}")

cur2.execute("SELECT link_type, COUNT(*) as cnt FROM record_links GROUP BY link_type ORDER BY cnt DESC LIMIT 10")
for r in cur2.fetchall():
    print(f"  link_type={r['link_type']}: {r['cnt']:,}")

cur2.execute("SELECT rule_version, COUNT(*) as cnt FROM record_links GROUP BY rule_version ORDER BY cnt DESC")
for r in cur2.fetchall():
    print(f"  rule_version={r['rule_version']}: {r['cnt']:,}")

cur2.execute("SELECT legacy_unverified, COUNT(*) as cnt FROM record_links GROUP BY legacy_unverified ORDER BY cnt DESC")
for r in cur2.fetchall():
    print(f"  legacy_unverified={r['legacy_unverified']}: {r['cnt']:,}")

# 5. Collegamenti
print("\n" + "=" * 80)
print("COLLEGAMENTI IN imi_internati.db")
print("=" * 80)
cur2.execute("SELECT COUNT(*) FROM collegamenti")
total_col = cur2.fetchone()[0]
print(f"Total collegamenti: {total_col:,}")

cur2.execute("SELECT tipo_collegamento, COUNT(*) as cnt FROM collegamenti GROUP BY tipo_collegamento ORDER BY cnt DESC LIMIT 10")
for r in cur2.fetchall():
    print(f"  tipo={r['tipo_collegamento']}: {r['cnt']:,}")

# 6. Entita
print("\n" + "=" * 80)
print("ENTITA IN imi_internati.db")
print("=" * 80)
cur2.execute("SELECT tipo, COUNT(*) as cnt FROM entita GROUP BY tipo ORDER BY cnt DESC LIMIT 15")
for r in cur2.fetchall():
    print(f"  tipo={r['tipo']}: {r['cnt']:,}")

# 7. Eventi_1gm in imi_internati.db (different from eventi_1gm.db!)
print("\n" + "=" * 80)
print("EVENTI_1GM IN imi_internati.db (local copy)")
print("=" * 80)
cur2.execute("SELECT id, nome, data_inizio, data_fine FROM eventi_1gm ORDER BY id")
for r in cur2.fetchall():
    print(f"  id={r['id']} | {r['nome']} | {r['data_inizio']} -> {r['data_fine']}")

# 8. Claims
print("\n" + "=" * 80)
print("CLAIMS IN imi_internati.db")
print("=" * 80)
cur2.execute("SELECT COUNT(*) FROM claims")
print(f"Total claims: {cur2.fetchone()[0]:,}")
cur2.execute("SELECT * FROM claims LIMIT 3")
for r in cur2.fetchall():
    print(f"  {dict(r)}")

# 9. Claim evidence
print("\n" + "=" * 80)
print("CLAIM_EVIDENCE IN imi_internati.db")
print("=" * 80)
cur2.execute("SELECT COUNT(*) FROM claim_evidence")
print(f"Total claim_evidence: {cur2.fetchone()[0]:,}")
cur2.execute("SELECT role, COUNT(*) as cnt FROM claim_evidence GROUP BY role ORDER BY cnt DESC LIMIT 10")
for r in cur2.fetchall():
    print(f"  role={r['role']}: {r['cnt']:,}")

# 10. Sync outbox
print("\n" + "=" * 80)
print("SYNC_OUTBOX IN imi_internati.db")
print("=" * 80)
cur2.execute("SELECT * FROM sync_outbox LIMIT 5")
for r in cur2.fetchall():
    print(f"  {dict(r)}")

conn.close()
conn2.close()
