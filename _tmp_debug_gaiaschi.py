import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
result = orch.execute("Luigi Gaiaschi", intent="PERSON_LOOKUP")

print(f"Identity: {result.get('snapshot', {}).get('identity_status')}")
print(f"War period: {result.get('snapshot', {}).get('war_period')}")
print(f"Observations: {result.get('observation_count')}")
print(f"Errors: {result.get('errors', [])}")
print()

claims = result.get("snapshot", {}).get("person_claims", [])
print(f"Person claims: {len(claims)}")
for c in claims:
    print(f"  - {c.get('predicate')}: {c.get('value_raw', c.get('value_normalized', ''))[:80]} | source={c.get('source', '')} certainty={c.get('certainty', '')}")

print()
context = result.get("snapshot", {}).get("context_claims", [])
print(f"Context claims: {len(context)}")
for c in context:
    print(f"  - {c.get('predicate')}: {c.get('value_raw', c.get('value_normalized', ''))} | table={c.get('source_table', '')}")

print()
# Check observations
obs = result.get("snapshot", {}).get("source_lineage_groups", [])
print(f"Source lineage groups: {len(obs)}")

print()
report = result.get("report", "")
print(f"Report ({len(report)} chars):")
print(report[:3000])
