"""Test: verify LeBI records flow through the V7 pipeline with debug output."""
import sqlite3
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(message)s")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imi_internati.db")

# Pick 3 names that have exact matches in lebi_records
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT cognome, nome, grado, sorte, data_nascita, luogo_nascita, reparto, arma
    FROM lebi_records
    WHERE cognome IS NOT NULL AND cognome != ''
    AND sorte = 'sopravvissuto'
    AND reparto != ''
    AND data_nascita != ''
    ORDER BY RANDOM() LIMIT 3
""").fetchall()
conn.close()

names = []
for r in rows:
    full_name = f"{r['cognome']} {r['nome']}".strip()
    names.append(full_name)
    print(f"  Selected: {full_name} | {r['grado']} | {r['sorte']} | nato {r['data_nascita']} a {r['luogo_nascita']}")
    print(f"    Reparto: {r['reparto']} | Arma: {r['arma']}")

print(f"\n{'='*70}")
print(f"Testing {len(names)} names through V7 pipeline")
print(f"{'='*70}\n")

# First test: directly query LocalDbAdapter
from v7_provider_adapters import LocalDbAdapter
from semantic_query_plan import SemanticQueryPlan, TargetSpec

adapter = LocalDbAdapter()

for name in names:
    target = TargetSpec(
        target_type="person",
        display_name=name,
        conflict="WW2",
        parsed_fields={"cognome": name.split()[0], "nome": " ".join(name.split()[1:])},
    )
    plan = SemanticQueryPlan(
        target=target,
        intent="PERSON_LOOKUP",
        provider_routes=[],
    )
    obs = adapter.search(plan)
    lebi_obs = [o for o in obs if o.provider_metadata and o.provider_metadata.get("table") == "lebi_records"]
    internati_obs = [o for o in obs if o.provider_metadata and o.provider_metadata.get("table") == "internati"]
    print(f"\n{name}:")
    print(f"  Total observations: {len(obs)}")
    print(f"  LeBI observations: {len(lebi_obs)}")
    print(f"  Internati observations: {len(internati_obs)}")
    for o in lebi_obs[:3]:
        print(f"    [LeBI] {o.title} | score={o.provider_score} | class={o.classification}")

# Now test full pipeline on first name
print(f"\n{'='*70}")
print(f"Full pipeline test: {names[0]}")
print(f"{'='*70}\n")

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
t0 = time.time()
result = orch.execute(user_input=names[0], intent="PERSON_LOOKUP", conflict="WW2")
elapsed = time.time() - t0

snapshot = result.get("snapshot", {})
report = result.get("report", "")
identity = snapshot.get("identity_status", "UNKNOWN") if snapshot else "UNKNOWN"
obs_count = result.get("observation_count", 0)

print(f"\nIdentity: {identity} | Obs: {obs_count} | Elapsed: {elapsed:.1f}s")
print(f"\n--- REPORT ---\n")
print(report if report else "(no report)")
print(f"\n--- END REPORT ---")
