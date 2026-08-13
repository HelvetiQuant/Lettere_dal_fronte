"""Test discursive response for Ferruccio Guccini."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
t0 = time.time()
result = orch.execute(user_input="FERRUCCIO GUCCINI", intent="PERSON_LOOKUP", conflict="UNKNOWN")
elapsed = time.time() - t0

snapshot = result.get("snapshot", {})
report = result.get("report", "")
identity = snapshot.get("identity_status", "UNKNOWN") if snapshot else "UNKNOWN"
obs = result.get("observation_count", 0)
semantic = result.get("semantic_counts", {})

print(f"Identity: {identity} | Obs: {obs} | Elapsed: {elapsed:.1f}s")
if semantic:
    claims = semantic.get("unique_person_facts", "?")
    evidence = semantic.get("supporting_evidence_records", "?")
    sources = semantic.get("unique_source_records", "?")
    print(f"Claims: {claims} | Evidence: {evidence} | Sources: {sources}")
print()
print(report)
