"""V7.2 Multi-Albo Conversational Report Generator.

Esegue la pipeline V7.2 su 6 nomi reali da vari albi + 3 eventi storici,
generando report conversazionali (AI se disponibile, deterministic fallback altrimenti).

6 nomi da albi diversi:
  1. BROGNARA Cristino     — internati (IMI)
  2. ABATE MARIO ANTONIO   — caduti_albooro
  3. EGINETI ARTURO        — caduti_ministero
  4. DEVINCENZI GIOVANNI   — caduti_albooro + caduti_ministero
  5. TONIOLI PASQUALE      — internati (IMI)
  6. CAIS Arduino          — internati (IMI)

3 eventi:
  1. Caporetto             — EVENT_LOOKUP
  2. Vittorio Veneto       — EVENT_LOOKUP
  3. San Matteo            — EVENT_LOOKUP
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7
from v7_narrator import ReportRenderer

# ─── Targets ─────────────────────────────────────────────────────────────────

PERSON_TARGETS = [
    {"name": "BROGNARA Cristino",    "conflict": "WWII", "albo": "internati"},
    {"name": "ABATE MARIO ANTONIO",  "conflict": "WWI",  "albo": "caduti_albooro"},
    {"name": "EGINETI ARTURO",       "conflict": "WWI",  "albo": "caduti_ministero"},
    {"name": "DEVINCENZI GIOVANNI",  "conflict": "WWI",  "albo": "caduti_albooro + caduti_ministero"},
    {"name": "TONIOLI PASQUALE",     "conflict": "WWII", "albo": "internati"},
    {"name": "CAIS Arduino",         "conflict": "WWII", "albo": "internati"},
]

EVENT_TARGETS = [
    {"name": "Battaglia di Caporetto",   "conflict": "WWI"},
    {"name": "Battaglia di Vittorio Veneto", "conflict": "WWI"},
    {"name": "Battaglia di San Matteo",  "conflict": "WWI"},
]

# ─── Run ─────────────────────────────────────────────────────────────────────

def run_all():
    orch = UnifiedResearchOrchestratorV7()
    renderer = ReportRenderer()

    all_results = []

    # ── Person lookups ──────────────────────────────────────────────────────
    print("=" * 70)
    print("V7.2 REPORT CONVERSAZIONALE — 6 NOMI DA VARI ALBI")
    print("=" * 70)

    for i, t in enumerate(PERSON_TARGETS, 1):
        name = t["name"]
        conflict = t["conflict"]
        albo = t["albo"]

        print(f"\n{'─' * 70}")
        print(f"[{i}/6] PERSON_LOOKUP: {name} (albo: {albo}, conflict: {conflict})")
        print(f"{'─' * 70}")

        t0 = time.time()
        result = orch.execute(
            user_input=name,
            intent="PERSON_LOOKUP",
            conflict=conflict,
        )
        elapsed = time.time() - t0

        snap = result["snapshot"]
        report = result["report"]
        errors = result.get("errors", [])
        warnings = result.get("warnings", [])

        # Summary
        print(f"  Observations: {result['observation_count']}")
        print(f"  Identity (V7.2): {snap.get('identity_status', 'N/A')}")
        print(f"  Corroboration: {snap.get('corroboration_status', 'N/A')}")
        print(f"  Person claims: {len(snap.get('person_claims', []))}")
        print(f"  Context claims: {len(snap.get('context_claims', []))}")
        print(f"  Accepted: {len(snap.get('accepted_claims', []))}")
        print(f"  Conflicting: {len(snap.get('conflicting_claims', []))}")
        print(f"  Asserted: {len(snap.get('asserted_claims', []))}")
        print(f"  Rejected candidates: {len(snap.get('rejected_candidates', []))}")
        print(f"  Candidate identities: {len(snap.get('candidate_identities', []))}")
        print(f"  Errors: {errors}")
        print(f"  Warnings: {warnings[:3]}")
        print(f"  Elapsed: {elapsed:.1f}s")

        # Save report
        safe_name = name.replace(" ", "_").replace(".", "")
        report_file = f"REPORT_V72_{safe_name}.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  Report saved: {report_file}")

        # Save JSON narrative
        from evidence_snapshot_v7 import EvidenceSnapshotV7
        snap_obj = EvidenceSnapshotV7.from_dict(snap) if isinstance(snap, dict) else snap
        json_narrative = renderer.render_narrative_json(snap_obj)
        json_file = f"REPORT_V72_{safe_name}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            f.write(json_narrative)
        print(f"  JSON narrative saved: {json_file}")

        # Print first 600 chars of report
        print(f"\n  --- REPORT (first 600 chars) ---")
        print(f"  {report[:600]}")
        print()

        all_results.append({
            "target": name,
            "type": "PERSON_LOOKUP",
            "albo": albo,
            "conflict": conflict,
            "identity_status": snap.get("identity_status"),
            "corroboration_status": snap.get("corroboration_status"),
            "observation_count": result["observation_count"],
            "person_claims": len(snap.get("person_claims", [])),
            "context_claims": len(snap.get("context_claims", [])),
            "accepted": len(snap.get("accepted_claims", [])),
            "conflicting": len(snap.get("conflicting_claims", [])),
            "asserted": len(snap.get("asserted_claims", [])),
            "rejected_candidates": len(snap.get("rejected_candidates", [])),
            "candidate_identities": len(snap.get("candidate_identities", [])),
            "errors": errors,
            "warnings": warnings[:3],
            "elapsed_s": round(elapsed, 1),
            "report_file": report_file,
            "json_file": json_file,
        })

    # ── Event lookups ───────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("V7.2 REPORT CONVERSAZIONALE — 3 EVENTI STORICI")
    print(f"{'=' * 70}")

    for i, t in enumerate(EVENT_TARGETS, 1):
        name = t["name"]
        conflict = t["conflict"]

        print(f"\n{'─' * 70}")
        print(f"[{i}/3] EVENT_LOOKUP: {name} (conflict: {conflict})")
        print(f"{'─' * 70}")

        t0 = time.time()
        result = orch.execute(
            user_input=name,
            intent="EVENT_LOOKUP",
            conflict=conflict,
        )
        elapsed = time.time() - t0

        snap = result["snapshot"]
        report = result["report"]
        errors = result.get("errors", [])

        print(f"  Observations: {result['observation_count']}")
        print(f"  Identity (V7.2): {snap.get('identity_status', 'N/A')}")
        print(f"  Errors: {errors}")
        print(f"  Elapsed: {elapsed:.1f}s")

        safe_name = name.replace(" ", "_").replace(".", "")
        report_file = f"REPORT_V72_EVENT_{safe_name}.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  Report saved: {report_file}")

        # Print first 600 chars
        print(f"\n  --- REPORT (first 600 chars) ---")
        print(f"  {report[:600]}")
        print()

        all_results.append({
            "target": name,
            "type": "EVENT_LOOKUP",
            "conflict": conflict,
            "identity_status": snap.get("identity_status"),
            "observation_count": result["observation_count"],
            "errors": errors,
            "elapsed_s": round(elapsed, 1),
            "report_file": report_file,
        })

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SUMMARY — V7.2 MULTI-ALBO + EVENTI")
    print(f"{'=' * 70}")

    for r in all_results:
        if r["type"] == "PERSON_LOOKUP":
            print(f"  {r['target']:30s} albo={r['albo']:30s} id={r['identity_status']:25s} obs={r['observation_count']:3d} person={r['person_claims']} ctx={r['context_claims']} err={len(r['errors'])}")
        else:
            print(f"  {r['target']:30s} EVENT{'':25s} id={r['identity_status']:25s} obs={r['observation_count']:3d} err={len(r['errors'])}")

    # Save summary JSON
    with open("V72_MULTI_ALBO_RESULTS.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to V72_MULTI_ALBO_RESULTS.json")


if __name__ == "__main__":
    run_all()
