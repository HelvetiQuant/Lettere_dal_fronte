"""Pick 5 random LeBI names and run the full narrative pipeline."""
import sqlite3
import random
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imi_internati.db")

# Get 5 random names from lebi_records
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT cognome, nome, grado, sorte, data_nascita, luogo_nascita
    FROM lebi_records
    WHERE cognome IS NOT NULL AND cognome != ''
    ORDER BY RANDOM() LIMIT 5
""").fetchall()
conn.close()

names = []
for r in rows:
    full_name = f"{r['cognome']} {r['nome']}".strip()
    names.append(full_name)
    print(f"  Selected: {full_name} | {r['grado']} | {r['sorte']} | nato {r['data_nascita']} a {r['luogo_nascita']}")

print(f"\n{'='*70}")
print(f"Testing {len(names)} names through UnifiedResearchOrchestratorV7")
print(f"{'='*70}\n")

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()

for i, name in enumerate(names, 1):
    print(f"\n{'='*70}")
    print(f"TEST {i}/5: {name}")
    print(f"{'='*70}")

    t0 = time.time()
    try:
        result = orch.execute(
            user_input=name,
            intent="PERSON_LOOKUP",
            conflict="WW2"
        )
        elapsed = time.time() - t0

        snapshot = result.get("snapshot", {})
        report = result.get("report", "")
        identity = snapshot.get("identity_status", "UNKNOWN") if snapshot else "UNKNOWN"
        obs = result.get("observation_count", 0)

        print(f"Identity: {identity} | Obs: {obs} | Elapsed: {elapsed:.1f}s")
        print(f"\n--- REPORT ---\n")
        print(report if report else "(no report generated)")
        print(f"\n--- END REPORT ---\n")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"ERROR after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
