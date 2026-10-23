"""Run backend search on 6 random persons + 3 events from DB.

Prints full narrative report and semantic counts for each case.
"""
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Suppress urllib3 warnings
warnings.filterwarnings("ignore")

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

PERSON_CASES = [
    "PIERROBONE Cesare",
    "MOROSI Riccardo",
    "BERNERI Pietro",
    "PATRONE Mario",
    "CATTANEO Luigi",
    "BELLINO Guido",
]

EVENT_CASES = [
    "Battaglie dell'Isonzo",
    "Fronte Macedone",
    "Prigionia",
]


def main():
    orch = UnifiedResearchOrchestratorV7()
    results = {}

    for name in PERSON_CASES:
        print(f"\n{'='*70}")
        print(f"PERSON: {name}")
        print(f"{'='*70}")

        try:
            result = orch.execute(
                user_input=name,
                intent="PERSON_LOOKUP",
                target_id="",
                conflict="UNKNOWN",
                manifest_hash="",
                metadata={},
            )

            semantic = result.get("semantic_counts", {})
            snapshot = result.get("snapshot", {})
            person_claims = snapshot.get("person_claims", [])
            report = result.get("report", "")
            errors = result.get("errors", [])
            narration = result.get("narration_result", {})
            identity_status = snapshot.get("identity_status", "N/A")

            print(f"  Identity status: {identity_status}")
            print(f"  Semantic counts: {json.dumps(semantic, indent=4)}")
            print(f"  Person claims: {len(person_claims)}")

            for c in person_claims[:15]:
                pred = c.get("predicate", "?")
                val = c.get("value_normalized", "?")[:80]
                status = c.get("status", "?")
                conf = c.get("confidence", 0)
                print(f"    [{status:12s} conf={conf:.2f}] {pred:25s} = {val}")

            if len(person_claims) > 15:
                print(f"    ... and {len(person_claims) - 15} more claims")

            print(f"\n  --- NARRATIVE REPORT ---")
            print(report[:2000] if report else "(empty)")
            if len(report) > 2000:
                print(f"\n  ... [report truncated, total {len(report)} chars]")

            if errors:
                print(f"\n  Errors: {errors[:3]}")

            narration_mode = narration.get("generation_info", {}).get("mode", "unknown")
            narration_provider = narration.get("generation_info", {}).get("provider", "unknown")
            print(f"\n  Narration: mode={narration_mode}, provider={narration_provider}")

            results[name] = {
                "type": "PERSON",
                "identity_status": identity_status,
                "semantic_counts": semantic,
                "person_claims_count": len(person_claims),
                "narration_mode": narration_mode,
                "narration_provider": narration_provider,
                "report_length": len(report),
                "report_preview": report[:500],
                "errors": errors[:5],
            }

        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            results[name] = {"type": "PERSON", "error": str(e)}

    for name in EVENT_CASES:
        print(f"\n{'='*70}")
        print(f"EVENT: {name}")
        print(f"{'='*70}")

        try:
            result = orch.execute(
                user_input=name,
                intent="EVENT_LOOKUP",
                target_id="",
                conflict="UNKNOWN",
                manifest_hash="",
                metadata={},
            )

            snapshot = result.get("snapshot", {})
            person_claims = snapshot.get("person_claims", [])
            report = result.get("report", "")
            semantic = result.get("semantic_counts", {})
            narration = result.get("narration_result", {})
            identity_status = snapshot.get("identity_status", "N/A")

            print(f"  Identity status: {identity_status}")
            print(f"  Semantic counts: {json.dumps(semantic, indent=4)}")
            print(f"  Event claims: {len(person_claims)}")

            for c in person_claims[:10]:
                pred = c.get("predicate", "?")
                val = c.get("value_normalized", "?")[:80]
                print(f"    {pred:25s} = {val}")

            print(f"\n  --- NARRATIVE REPORT ---")
            print(report[:2000] if report else "(empty)")
            if len(report) > 2000:
                print(f"\n  ... [report truncated, total {len(report)} chars]")

            narration_mode = narration.get("generation_info", {}).get("mode", "unknown")
            narration_provider = narration.get("generation_info", {}).get("provider", "unknown")
            print(f"\n  Narration: mode={narration_mode}, provider={narration_provider}")

            results[name] = {
                "type": "EVENT",
                "identity_status": identity_status,
                "semantic_counts": semantic,
                "event_claims_count": len(person_claims),
                "narration_mode": narration_mode,
                "narration_provider": narration_provider,
                "report_length": len(report),
                "report_preview": report[:500],
            }

        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            results[name] = {"type": "EVENT", "error": str(e)}

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Case':<35} {'Type':<7} {'Claims':>7} {'Confirmed':>10} {'Web':>5} {'Status':<25} {'Narration':<15}")
    print("-" * 110)

    all_ok = True
    for name, r in results.items():
        if "error" in r:
            print(f"  {name:<35} {'ERROR':<7} {r['error'][:50]}")
            all_ok = False
            continue

        rtype = r["type"]
        if rtype == "PERSON":
            claims = r.get("person_claims_count", 0)
            sem = r.get("semantic_counts", {})
            confirmed = sem.get("person_sources_confirmed", 0)
            web = sem.get("web_candidates_seen", 0)
            status = r.get("identity_status", "")
            mode = r.get("narration_mode", "?")
            print(f"  {name:<35} {'PERSON':<7} {claims:>7} {confirmed:>10} {web:>5} {status:<25} {mode:<15}")

            if claims == 0:
                print(f"    WARN: 0 person claims")
                all_ok = False
        else:
            claims = r.get("event_claims_count", 0)
            status = r.get("identity_status", "")
            mode = r.get("narration_mode", "?")
            print(f"  {name:<35} {'EVENT':<7} {claims:>7} {'':>10} {'':>5} {status:<25} {mode:<15}")

    # Save results
    out_path = Path(__file__).parent / "RANDOM_SEARCH_RESULTS.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")

    return all_ok


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
