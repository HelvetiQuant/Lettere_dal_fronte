import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from v7_provider_adapters import LocalDbAdapter
from semantic_query_plan import SemanticQueryPlan, TargetSpec

plan = SemanticQueryPlan(
    target=TargetSpec(
        target_type="person",
        display_name="Luigi Gaiaschi",
    ),
    intent="PERSON_LOOKUP",
)

adapter = LocalDbAdapter()
obs_list = adapter.search(plan)

print(f"Total observations: {len(obs_list)}")
print(f"Query: {plan.target.display_name}")
print(f"Parts: cognome={plan.target.display_name.split()[0]}, nome={' '.join(plan.target.display_name.split()[1:])}")
print()

for obs in obs_list:
    meta = obs.provider_metadata
    table = meta.get("table", "")
    raw = meta.get("raw_record", {})
    label = raw.get("nominativo") or f"{raw.get('cognome','')} {raw.get('nome','')}"
    print(f"  obs: table={table} id={raw.get('id')} label={label} classification={obs.classification}")
