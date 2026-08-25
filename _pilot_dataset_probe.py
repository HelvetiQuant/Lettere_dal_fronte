"""Probe databases for pilot dataset stratification."""
import sqlite3

def probe_imi():
    conn = sqlite3.connect("imi_internati.db")
    conn.row_factory = sqlite3.Row

    print("=== IMI DB: record_links ===")
    r = conn.execute("SELECT COUNT(*) as c FROM record_links").fetchone()
    print(f"  total: {r['c']}")

    for col in ["usable_as_evidence", "algorithm_version", "origin", "war_period", "semantic_role"]:
        try:
            rows = conn.execute(f"SELECT {col}, COUNT(*) as c FROM record_links GROUP BY {col} ORDER BY c DESC LIMIT 10").fetchall()
            print(f"  {col}:")
            for row in rows:
                print(f"    {row[col]}: {row['c']}")
        except Exception as e:
            print(f"  {col}: ERROR {e}")

    print("\n=== IMI DB: collegamenti ===")
    r = conn.execute("SELECT COUNT(*) as c FROM collegamenti").fetchone()
    print(f"  total: {r['c']}")

    print("\n=== IMI DB: internati ===")
    r = conn.execute("SELECT COUNT(*) as c FROM internati").fetchone()
    print(f"  total: {r['c']}")

    print("\n=== IMI DB: cross_link_audit ===")
    try:
        r = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit").fetchone()
        print(f"  total: {r['c']}")
        r = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=0").fetchone()
        print(f"  active: {r['c']}")
        r = conn.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=1").fetchone()
        print(f"  reverted: {r['c']}")
    except Exception as e:
        print(f"  ERROR: {e}")

    conn.close()

def probe_events():
    conn = sqlite3.connect("eventi_1gm.db")
    conn.row_factory = sqlite3.Row

    print("\n=== EVENTS DB: event_links ===")
    r = conn.execute("SELECT COUNT(*) as c FROM event_links").fetchone()
    print(f"  total: {r['c']}")

    for col in ["usable_as_evidence", "algorithm_version", "origin", "war_period", "semantic_role", "link_type"]:
        try:
            rows = conn.execute(f"SELECT {col}, COUNT(*) as c FROM event_links GROUP BY {col} ORDER BY c DESC LIMIT 10").fetchall()
            print(f"  {col}:")
            for row in rows:
                print(f"    {row[col]}: {row['c']}")
        except Exception as e:
            print(f"  {col}: ERROR {e}")

    print("\n=== EVENTS DB: eventi_1gm ===")
    r = conn.execute("SELECT COUNT(*) as c FROM eventi_1gm").fetchone()
    print(f"  total: {r['c']}")

    print("\n=== EVENTS DB: event_links sample (5 rows) ===")
    rows = conn.execute("SELECT * FROM event_links LIMIT 5").fetchall()
    for row in rows:
        print(f"  id={row['id']}, evento_id={row['evento_id']}, target_table={row['target_table']}, target_id={row['target_id']}, link_type={row['link_type']}, match_field={row['match_field']}, confidence={row['confidence']}")

    conn.close()

if __name__ == "__main__":
    probe_imi()
    probe_events()
