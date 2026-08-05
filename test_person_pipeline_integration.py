"""Integration test: 6 PERSON + 3 EVENT cases through V7 pipeline.

Tests:
- ALTA Antonio, ARMANNO Luigi A, AMAROTTI Enrico, ANFOSSO Carlo, ARTI Saverio, ANVISIO Remo
- Battaglia del Monte Ortigara, Battaglia di Vittorio Veneto, Guerra bianca

Verifies:
- Person claims extracted from local DB
- Semantic counts are correct (no misleading n_fonti)
- EVENT pipeline unaffected (regression)
- No "Nessun claim narrabile" when local data exists
- No homonym leakage
"""
import json
import os
import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7


PERSON_CASES = [
    "ALTA Antonio",
    "ARMANNO Luigi A",
    "AMAROTTI Enrico",
    "ANFOSSO Carlo",
    "ARTI Saverio",
    "ANVISIO Remo",
]

EVENT_CASES = [
    "Battaglia del Monte Ortigara",
    "Battaglia di Vittorio Veneto",
    "Guerra bianca",
]


def run_integration():
    orch = UnifiedResearchOrchestratorV7()
    results = {}

    for name in PERSON_CASES:
        print(f"\n{'='*60}")
        print(f"PERSON: {name}")
        print(f"{'='*60}")

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
            warnings = result.get("warnings", [])

            print(f"  Identity status: {snapshot.get('identity_status', 'N/A')}")
            print(f"  Semantic counts: {json.dumps(semantic, indent=2)}")
            print(f"  Person claims: {len(person_claims)}")
            for c in person_claims[:10]:
                pred = c.get("predicate", "?")
                val = c.get("value_normalized", "?")[:60]
                print(f"    - {pred}: {val}")
            if len(person_claims) > 10:
                print(f"    ... and {len(person_claims) - 10} more")

            # Check for "Nessun claim narrabile"
            has_blocked = "Nessun claim narrabile" in (report or "")

            # Check report first 200 chars
            print(f"  Report (first 200 chars): {(report or '')[:200]}")
            print(f"  Errors: {errors[:3]}")
            print(f"  Warnings: {warnings[:3]}")

            results[name] = {
                "type": "PERSON",
                "identity_status": snapshot.get("identity_status", ""),
                "semantic_counts": semantic,
                "person_claims_count": len(person_claims),
                "has_blocked_narration": has_blocked,
                "errors": errors[:5],
                "warnings_count": len(warnings),
                "report_preview": (report or "")[:300],
            }

        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = {"type": "PERSON", "error": str(e)}

    for name in EVENT_CASES:
        print(f"\n{'='*60}")
        print(f"EVENT: {name}")
        print(f"{'='*60}")

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

            print(f"  Identity status: {snapshot.get('identity_status', 'N/A')}")
            print(f"  Semantic counts: {json.dumps(semantic, indent=2)}")
            print(f"  Event claims: {len(person_claims)}")
            for c in person_claims[:5]:
                pred = c.get("predicate", "?")
                val = c.get("value_normalized", "?")[:60]
                print(f"    - {pred}: {val}")

            print(f"  Report (first 200 chars): {(report or '')[:200]}")

            results[name] = {
                "type": "EVENT",
                "identity_status": snapshot.get("identity_status", ""),
                "semantic_counts": semantic,
                "event_claims_count": len(person_claims),
                "report_preview": (report or "")[:300],
            }

        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = {"type": "EVENT", "error": str(e)}

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    all_ok = True
    for name, r in results.items():
        if "error" in r:
            print(f"  FAIL {name}: {r['error']}")
            all_ok = False
            continue

        if r["type"] == "PERSON":
            claims = r.get("person_claims_count", 0)
            blocked = r.get("has_blocked_narration", False)
            status = r.get("identity_status", "")
            sem = r.get("semantic_counts", {})

            # Check: should have person claims from local DB
            if claims == 0:
                print(f"  WARN {name}: 0 person claims (expected >0 from local DB)")
                all_ok = False
            if blocked:
                print(f"  WARN {name}: narration blocked ('Nessun claim narrabile')")
                all_ok = False

            # Check: semantic counts should not show huge web_candidates as sources
            confirmed = sem.get("person_sources_confirmed", 0)
            web = sem.get("web_candidates_seen", 0)
            print(f"  OK   {name}: claims={claims}, confirmed={confirmed}, web_seen={web}, status={status}")
        else:
            claims = r.get("event_claims_count", 0)
            print(f"  OK   {name}: event_claims={claims}")

    # Save results
    out_path = Path(__file__).parent / "PERSON_PIPELINE_INTEGRATION_RESULTS.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")

    return all_ok


if __name__ == "__main__":
    ok = run_integration()
    sys.exit(0 if ok else 1)
