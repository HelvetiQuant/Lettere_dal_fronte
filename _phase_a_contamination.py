"""Phase A — Check WWI/WWII contamination in event_links and record_links."""
import sqlite3

# 1. Event links: WWI events linked to WWII internati
print("=" * 80)
print("WWI/WWII CONTAMINATION IN event_links (eventi_1gm.db)")
print("=" * 80)
conn = sqlite3.connect("eventi_1gm.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Events by war period
cur.execute("""
    SELECT id, nome, data_inizio, data_fine, event_type
    FROM eventi_1gm
    WHERE data_inizio >= '1939' OR data_fine >= '1939'
    ORDER BY id
""")
wwii_events = {r["id"]: dict(r) for r in cur.fetchall()}
print(f"\nWWII events in registry: {len(wwii_events)}")
for eid, e in wwii_events.items():
    print(f"  id={eid} | {e['nome']} | {e['data_inizio']} -> {e['data_fine']}")

# How many event_links point WWI events to internati (WWII)?
cur.execute("""
    SELECT el.evento_id, e.nome, el.target_table, el.link_type, COUNT(*) as cnt
    FROM event_links el
    JOIN eventi_1gm e ON el.evento_id = e.id
    WHERE el.target_table = 'internati'
    AND e.data_inizio < '1939'
    GROUP BY el.evento_id, e.nome, el.target_table, el.link_type
    ORDER BY cnt DESC
""")
print("\nWWI events linked to WWII internati:")
for r in cur.fetchall():
    print(f"  {r['nome']} (id={r['evento_id']}) -> {r['target_table']} ({r['link_type']}): {r['cnt']:,}")

# How many event_links point WWII events to WWI tables (caduti_albooro, decorati)?
cur.execute("""
    SELECT el.evento_id, e.nome, el.target_table, el.link_type, COUNT(*) as cnt
    FROM event_links el
    JOIN eventi_1gm e ON el.evento_id = e.id
    WHERE e.data_inizio >= '1939'
    AND el.target_table IN ('caduti_albooro', 'decorati_nastroazzurro', 'caduti_ministero', 'caduti_bologna', 'caduti_sardi', 'caduti_francia_ww1')
    GROUP BY el.evento_id, e.nome, el.target_table, el.link_type
    ORDER BY cnt DESC
""")
print("\nWWII events linked to WWI tables:")
for r in cur.fetchall():
    print(f"  {r['nome']} (id={r['evento_id']}) -> {r['target_table']} ({r['link_type']}): {r['cnt']:,}")

# 2. Keyword contamination: "Campo" as match_value
cur.execute("""
    SELECT el.match_field, el.match_value, COUNT(*) as cnt
    FROM event_links el
    WHERE el.match_value = 'Campo'
    GROUP BY el.match_field, el.match_value
""")
print("\nLinks with match_value='Campo' (generic keyword):")
for r in cur.fetchall():
    print(f"  match_field={r['match_field']}, match_value={r['match_value']}: {r['cnt']:,}")

# 3. Confidence distribution for internato_ww2 links
cur.execute("""
    SELECT el.confidence, COUNT(*) as cnt
    FROM event_links el
    WHERE el.link_type = 'internato_ww2'
    GROUP BY el.confidence
    ORDER BY el.confidence DESC
""")
print("\nConfidence for internato_ww2 links:")
for r in cur.fetchall():
    print(f"  confidence={r['confidence']}: {r['cnt']:,}")

# 4. Sample internato_ww2 links
cur.execute("""
    SELECT el.evento_id, e.nome, el.target_id, el.match_field, el.match_value, el.confidence
    FROM event_links el
    JOIN eventi_1gm e ON el.evento_id = e.id
    WHERE el.link_type = 'internato_ww2'
    LIMIT 10
""")
print("\nSample internato_ww2 links:")
for r in cur.fetchall():
    print(f"  {r['nome']} (id={r['evento_id']}) -> internati#{r['target_id']} | field={r['match_field']} val={r['match_value']} conf={r['confidence']}")

# 5. Check if "Battaglie dell'Isonzo" has a 12th battle child
cur.execute("""
    SELECT id, nome, data_inizio, data_fine, parent_event_id, stable_id
    FROM eventi_1gm
    WHERE parent_event_id = 'evt_0017'
    ORDER BY data_inizio
""")
print("\nChildren of 'Battaglie dell'Isonzo' (evt_0017):")
for r in cur.fetchall():
    print(f"  id={r['id']} | {r['nome']} | {r['data_inizio']} -> {r['data_fine']} | stable={r['stable_id']}")

# 6. Check Caporetto — is it child of Isonzo?
cur.execute("""
    SELECT id, nome, data_inizio, data_fine, parent_event_id, stable_id
    FROM eventi_1gm
    WHERE nome LIKE '%Caporetto%' OR stable_id = 'evt_0016'
""")
print("\nCaporetto entries:")
for r in cur.fetchall():
    print(f"  id={r['id']} | {r['nome']} | {r['data_inizio']} -> {r['data_fine']} | parent={r['parent_event_id']} | stable={r['stable_id']}")

# 7. Record_links: how many use same-year decoration as link?
conn2 = sqlite3.connect("imi_internati.db")
conn2.row_factory = sqlite3.Row
cur2 = conn2.cursor()
cur2.execute("""
    SELECT link_type, COUNT(*) as cnt
    FROM record_links
    WHERE link_type = 'stesso_anno_decorazione'
    GROUP BY link_type
""")
print("\n" + "=" * 80)
print("RECORD_LINKS: stesso_anno_decorazione")
print("=" * 80)
for r in cur2.fetchall():
    print(f"  {r['link_type']}: {r['cnt']:,}")

# 8. Check .env tracking
import os
print("\n" + "=" * 80)
print("SECRET SCANNING")
print("=" * 80)
result = os.popen("git ls-files .env 2>&1").read().strip()
print(f".env tracked by git: {result if result else 'NO (good)'}")

# Check for hardcoded paths
print("\nChecking for hardcoded personal paths in .py files:")
import subprocess
try:
    result = subprocess.run(
        ["git", "grep", "-n", "Desktop.*lettere", "--", "*.py"],
        capture_output=True, text=True, cwd="."
    )
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    print(f"  Files with hardcoded Desktop paths: {len(lines)}")
    for line in lines[:5]:
        print(f"    {line}")
except Exception:
    pass

# Check for API key patterns
try:
    result = subprocess.run(
        ["git", "grep", "-n", "sk-[a-zA-Z0-9]", "--", "*.py"],
        capture_output=True, text=True, cwd="."
    )
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    print(f"  Files with sk- API key patterns: {len(lines)}")
    for line in lines[:5]:
        print(f"    {line}")
except Exception:
    pass

conn.close()
conn2.close()
