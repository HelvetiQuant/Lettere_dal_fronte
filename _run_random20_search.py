"""Run backend search on 20 random persons from various DB tables."""
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

PERSON_CASES = [
    "SCIALLA GIUSEPPE",
    "GIORDANI ENRICO",
    "EPIS BASILIO ENRICO",
    "GIACOLLO COSIMO",
    "CATENA GIOVANNI",
    "MURNANE HUGH",
    "VINCIMENGA Giuseppe",
    "TAVERIO Alessandro",
    "NAVA Nino",
    "BADELLINO GIACINTO",
    "BARBARINI ANGELO DI PIETRO",
    "VINCIGUERRA Salvatore",
    "PAVAN Vittorio",
    "CREMONINI Tolmino",
    "WENSING THEODOOR",
    "BOVERI GIUSEPPE DI GIOVANNI",
    "LARINI ETTORE",
    "PALTRINIERI ZACCARIA",
    "BARBATO Pasquale",
    "CESTARI Guido",
]


def main():
    orch = UnifiedResearchOrchestratorV7()
    results = {}

    for idx, name in enumerate(PERSON_CASES, 1):
        print(f"\n{'='*70}")
        print(f"[{idx}/20] PERSON: {name}")
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
            identity_status = snapshot.get("identity_status", "N/A")

            # Extract narrative text (before provenienza section)
            narrative = report.split("---")[0].strip() if "---" in report else report

            print(f"  Identity: {identity_status}")
            print(f"  Claims: {len(person_claims)} | Confirmed: {semantic.get('person_sources_confirmed', 0)} | Web: {semantic.get('web_candidates_seen', 0)}")
            print(f"  Ambiguous: {semantic.get('person_sources_ambiguous', 0)} | Rejected: {semantic.get('person_candidates_rejected', 0)}")

            if person_claims:
                print(f"  Claim details:")
                for c in person_claims[:12]:
                    pred = c.get("predicate", "?")
                    val = c.get("value_normalized", "?")[:70]
                    print(f"    {pred:25s} = {val}")
                if len(person_claims) > 12:
                    print(f"    ... +{len(person_claims) - 12} more")

            print(f"\n  NARRATIVE:")
            print(f"  {narrative[:1500]}")
            if len(narrative) > 1500:
                print(f"  ... [truncated, {len(narrative)} chars total]")

            if errors:
                print(f"  Errors: {errors[:2]}")

            results[name] = {
                "identity_status": identity_status,
                "semantic_counts": semantic,
                "claims_count": len(person_claims),
                "narrative": narrative[:3000],
                "report_length": len(report),
                "errors": errors[:3],
            }

        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = {"error": str(e)}

    # Summary table
    print(f"\n{'='*70}")
    print("SUMMARY — 20 PERSON SEARCH")
    print(f"{'='*70}")
    print(f"{'#':>3} {'Name':<35} {'Claims':>7} {'Conf':>5} {'Amb':>5} {'Rej':>5} {'Web':>5} {'Status':<25}")
    print("-" * 95)

    total_claims = 0
    total_confirmed = 0
    ok_count = 0

    for idx, (name, r) in enumerate(results.items(), 1):
        if "error" in r:
            print(f"{idx:3d} {name:<35} ERROR: {r['error'][:40]}")
            continue

        claims = r.get("claims_count", 0)
        sem = r.get("semantic_counts", {})
        conf = sem.get("person_sources_confirmed", 0)
        amb = sem.get("person_sources_ambiguous", 0)
        rej = sem.get("person_candidates_rejected", 0)
        web = sem.get("web_candidates_seen", 0)
        status = r.get("identity_status", "")

        total_claims += claims
        total_confirmed += conf
        if claims > 0:
            ok_count += 1

        print(f"{idx:3d} {name:<35} {claims:>7} {conf:>5} {amb:>5} {rej:>5} {web:>5} {status:<25}")

    print("-" * 95)
    print(f"    TOTAL: {ok_count}/20 with claims | {total_claims} total claims | {total_confirmed} total confirmed sources")

    # Save
    out_path = Path(__file__).parent / "RANDOM20_SEARCH_RESULTS.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")

    return ok_count >= 18  # Allow 2 failures


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
