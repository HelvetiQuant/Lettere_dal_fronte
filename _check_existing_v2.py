import sqlite3
conn = sqlite3.connect('imi_internati.db')
existing = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('claims','claim_evidence','evidence_fragments','relations','pipeline_runs','resource_registry')").fetchall()]
print("Existing tables:", existing)
for t in existing:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    print(f"\n{t}:")
    for c in cols:
        print(f"  {c[1]} {c[2]}")
conn.close()
