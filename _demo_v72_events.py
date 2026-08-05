"""V7.2 Orchestrator — 3 eventi storici tramite pipeline completa."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()

eventi = [
    "Prima battaglia dell'Isonzo",
    "Battaglia di Caporetto",
    "Battaglia del Monte Grappa",
]

lines = []
for i, evento in enumerate(eventi, 1):
    lines.append(f"\n{'=' * 80}")
    lines.append(f"EVENTO {i}/3: {evento}")
    lines.append(f"{'=' * 80}")

    result = orch.execute(
        user_input=evento,
        intent="EVENT_LOOKUP",
    )

    lines.append(f"\nRun ID: {result.get('run_id','?')}")
    lines.append(f"Observations: {result.get('observation_count',0)}")
    lines.append(f"Errors: {result.get('errors',[])}")
    lines.append(f"Warnings: {result.get('warnings',[])}")

    if result.get("report"):
        lines.append(f"\n{'- ' * 40}")
        lines.append("REPORT:")
        lines.append(f"{'- ' * 40}")
        lines.append(result["report"])
    else:
        lines.append("\nNESSUN REPORT GENERATO")

    if result.get("snapshot"):
        snap = result["snapshot"]
        lines.append(f"\nSnapshot ID: {snap.get('snapshot_id','?')}")
        lines.append(f"Identity status: {snap.get('identity_status','?')}")
        lines.append(f"Corroboration: {snap.get('corroboration_status','?')}")
        lines.append(f"Web leads: {len(snap.get('web_leads',[]))}")
        lines.append(f"Provider ledger: {len(snap.get('provider_ledger',[]))}")

output = "\n".join(lines)
with open("_v72_events_output.txt", "w", encoding="utf-8") as f:
    f.write(output)
print(f"Output written to _v72_events_output.txt ({len(output)} chars)")
