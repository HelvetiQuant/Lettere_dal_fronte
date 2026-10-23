"""V7.2 Canary Baseline — run 6 frozen targets through V7.1 pipeline and save outputs."""
import json
import sys
import time
import traceback

sys.path.insert(0, '.')

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

CANARY_TARGETS = [
    ("CAIS Arduino", "PERSON_LOOKUP", "WWII"),
    ("BROGNARA Cristino", "PERSON_LOOKUP", "WWII"),
    ("TONIOLI Pasquale", "PERSON_LOOKUP", "WWII"),
    ("DEVINCENZI GIOVANNI", "PERSON_LOOKUP", "WWI"),
    ("EGINETI ARTURO", "PERSON_LOOKUP", "WWI"),
    ("RIGAMONTI PIETRO", "PERSON_LOOKUP", "WWI"),
]

def run_baseline():
    orch = UnifiedResearchOrchestratorV7()
    results = {}

    for name, intent, conflict in CANARY_TARGETS:
        print(f"\n{'='*60}")
        print(f"V7.2 → {name} ({intent}, {conflict})")
        print(f"{'='*60}")

        try:
            t0 = time.time()
            result = orch.execute(
                user_input=name,
                intent=intent,
                conflict=conflict,
            )
            elapsed = time.time() - t0

            entry = {
                "name": name,
                "intent": intent,
                "conflict": conflict,
                "elapsed_seconds": round(elapsed, 2),
                "run_id": result.get("run_id", ""),
                "plan_id": result.get("plan_id", ""),
                "observation_count": result.get("observation_count", 0),
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
                "stage_timings": result.get("stage_timings", {}),
                "snapshot_identity_resolution": "",
                "snapshot_identity_status": "",
                "snapshot_corroboration_status": "",
                "snapshot_external_corroboration": "",
                "snapshot_resolved_cluster_id": "",
                "snapshot_accepted_claims_count": 0,
                "snapshot_conflicting_claims_count": 0,
                "snapshot_asserted_claims_count": 0,
                "snapshot_person_claims_count": 0,
                "snapshot_context_claims_count": 0,
                "snapshot_candidate_identities_count": 0,
                "snapshot_rejected_candidates_count": 0,
                "report": result.get("report", ""),
            }

            snap = result.get("snapshot")
            if snap:
                entry["snapshot_identity_resolution"] = snap.get("identity_resolution", "")
                entry["snapshot_identity_status"] = snap.get("identity_status", "")
                entry["snapshot_corroboration_status"] = snap.get("corroboration_status", "")
                entry["snapshot_external_corroboration"] = snap.get("external_corroboration", "")
                entry["snapshot_resolved_cluster_id"] = snap.get("resolved_identity_cluster_id", "")
                entry["snapshot_accepted_claims_count"] = len(snap.get("accepted_claims", []))
                entry["snapshot_conflicting_claims_count"] = len(snap.get("conflicting_claims", []))
                entry["snapshot_asserted_claims_count"] = len(snap.get("asserted_claims", []))
                entry["snapshot_person_claims_count"] = len(snap.get("person_claims", []))
                entry["snapshot_context_claims_count"] = len(snap.get("context_claims", []))
                entry["snapshot_candidate_identities_count"] = len(snap.get("candidate_identities", []))
                entry["snapshot_rejected_candidates_count"] = len(snap.get("rejected_candidates", []))

            results[name] = entry

            print(f"  Observations: {entry['observation_count']}")
            print(f"  Identity (legacy): {entry['snapshot_identity_resolution']}")
            print(f"  Identity (V7.2): {entry['snapshot_identity_status']}")
            print(f"  Corroboration: {entry['snapshot_corroboration_status']}")
            print(f"  Person claims: {entry['snapshot_person_claims_count']}, Context claims: {entry['snapshot_context_claims_count']}")
            print(f"  Accepted: {entry['snapshot_accepted_claims_count']}, Conflicting: {entry['snapshot_conflicting_claims_count']}, Asserted: {entry['snapshot_asserted_claims_count']}")
            print(f"  Rejected candidates: {entry['snapshot_rejected_candidates_count']}")
            print(f"  Candidate identities: {entry['snapshot_candidate_identities_count']}")
            print(f"  Errors: {entry['errors']}")
            print(f"  Warnings: {entry['warnings']}")
            print(f"  Elapsed: {elapsed:.2f}s")
            print(f"\n--- REPORT (first 500 chars) ---")
            print(entry["report"][:500] if entry["report"] else "(no report)")

        except Exception as e:
            results[name] = {
                "name": name,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            print(f"  ERROR: {e}")
            traceback.print_exc()

    with open("CANARY_V7_2_RESULTS.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to CANARY_V7_2_RESULTS.json")

    print("\n" + "=" * 60)
    print("CANARY SUMMARY V7.2")
    print("=" * 60)
    for name, r in results.items():
        if "error" in r:
            print(f"  {name}: ERROR: {r['error']}")
        else:
            print(f"  {name}: id={r['snapshot_identity_status']}, obs={r['observation_count']}, accepted={r['snapshot_accepted_claims_count']}, conflicting={r['snapshot_conflicting_claims_count']}, rejected={r['snapshot_rejected_candidates_count']}, person_claims={r['snapshot_person_claims_count']}")

if __name__ == "__main__":
    run_baseline()
