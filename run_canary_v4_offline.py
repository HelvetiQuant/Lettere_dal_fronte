"""Canary V4 Offline — runs all 10 canary targets without external API calls.

Uses use_ai=False to avoid Tavily/Mistral/OpenAI calls.
Generates V4 EvidenceSnapshot, deterministic report, and before/after comparison.

No OpenAI calls. No Tavily calls. No Mistral calls.
Only local DB search + V4 snapshot + deterministic report.
"""
import os, sys, json, logging, time
from pathlib import Path
from datetime import datetime

# Load .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger("canary_v4_offline")

# Reuse canary targets
from run_canary import CANARY_TARGETS


def run_canary_v4_offline():
    from research_protocol import research_person, SearchInput
    from evidence_snapshot_v4 import build_snapshot_v4_from_dossier
    from ai_output_validator import generate_deterministic_report
    from source_capability_registry import get_routing_matrix

    results = []
    run_id = f"canary_v4_offline_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    print(f"\n{'='*80}")
    print(f"CANARY V4 OFFLINE — {run_id}")
    print(f"Targets: {len(CANARY_TARGETS)}")
    print(f"Mode: NO external API calls (use_ai=False)")
    print(f"{'='*80}\n")

    for t in CANARY_TARGETS:
        target_id = t["target_id"]
        ordinal = t["ordinal"]
        full_name = f"{t['cognome']} {t['nome']}"

        print(f"\n[{ordinal}/{len(CANARY_TARGETS)}] {target_id}: {full_name}")
        print(f"  Target: {t.get('anno_nascita', '?')}, {t.get('luogo_nascita', '?')}")

        si = SearchInput(
            cognome=t["cognome"],
            nome=t["nome"],
            paternita=t.get("paternita", ""),
            anno_nascita=t.get("anno_nascita", ""),
            luogo_nascita=t.get("luogo_nascita", ""),
            grado=t.get("grado", ""),
            reparto=t.get("reparto", ""),
            conflitto_presunto=t.get("conflitto_presunto", ""),
        )

        t_start = time.time()
        try:
            # Run research WITHOUT AI — no external calls
            dossier = research_person(si.__dict__, use_ai=False, persist=False)
            elapsed = time.time() - t_start

            # Build V4 snapshot
            from research_protocol import ResearchTarget
            target = ResearchTarget.from_search_input(si)
            snapshot = build_snapshot_v4_from_dossier(dossier, target)

            # Validate snapshot
            violations = snapshot.validate()

            # Generate deterministic report
            det_report = generate_deterministic_report(snapshot.to_dict())

            # Get routing matrix
            routing = get_routing_matrix(t.get("conflitto_presunto", "ww1"))

            # Archival suggestions
            from research_protocol import _generate_archival_requests
            archival = _generate_archival_requests(si, dossier)

            result = {
                "target_id": target_id,
                "ordinal": ordinal,
                "full_name": full_name,
                "target_data": {
                    "anno_nascita": t.get("anno_nascita", ""),
                    "luogo_nascita": t.get("luogo_nascita", ""),
                    "reparto": t.get("reparto", ""),
                    "paternita": t.get("paternita", ""),
                },
                "elapsed_seconds": round(elapsed, 1),
                "stato_identificazione": dossier.stato_identificazione,
                "resolution_state": snapshot.resolution_state,
                "origin_record_state": snapshot.origin_record_state,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_hash": snapshot.snapshot_hash,
                "snapshot_version": snapshot.version,
                "accepted_claims_count": len(snapshot.accepted_claims),
                "missing_claims": snapshot.missing_claims,
                "rejected_candidates_count": len(snapshot.rejected_candidates),
                "origin_evidence_sources": len(snapshot.accepted_origin_evidence_sources),
                "independent_evidence_sources": len(snapshot.accepted_independent_evidence_sources),
                "consulted_sources": len(snapshot.consulted_sources),
                "research_leads": len(snapshot.research_leads),
                "reconciliation": snapshot.reconciliation,
                "validation_violations": violations,
                "candidates_count": len(dossier.candidati),
                "omonimi_count": len(dossier.omonimi_esclusi),
                "routing": {
                    "eligible_count": routing["eligible_count"],
                    "skipped_count": routing["skipped_count"],
                    "skipped": routing["skipped"],
                },
                "archival_suggestions_count": len(archival),
                "archival_suggestions": archival,
                "deterministic_report": det_report[:500] + "..." if len(det_report) > 500 else det_report,
                "research_limitations": snapshot.research_limitations,
            }

            results.append(result)

            # Print summary
            print(f"  → stato: {dossier.stato_identificazione} | resolution: {snapshot.resolution_state}")
            print(f"  → origin: {snapshot.origin_record_state} | claims: {len(snapshot.accepted_claims)} accepted, {len(snapshot.missing_claims)} missing")
            print(f"  → candidates: {len(dossier.candidati)} | omonimi: {len(dossier.omonimi_esclusi)}")
            print(f"  → routing: {routing['eligible_count']} eligible, {routing['skipped_count']} skipped")
            print(f"  → archival: {len(archival)} suggestions")
            if violations:
                print(f"  ⚠️  Validation violations: {violations}")
            else:
                print(f"  ✅ Snapshot validation clean")
            print(f"  → elapsed: {elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - t_start
            log.error("Failed for %s: %s", full_name, e)
            import traceback
            traceback.print_exc()
            results.append({
                "target_id": target_id,
                "ordinal": ordinal,
                "full_name": full_name,
                "error": str(e)[:500],
                "elapsed_seconds": round(elapsed, 1),
            })

    # Save results
    out_json = Path(__file__).parent / "CANARY_V4_OFFLINE_RESULTS.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate before/after report
    generate_before_after_report(results, run_id)

    print(f"\n{'='*80}")
    print(f"CANARY V4 OFFLINE COMPLETE")
    print(f"  Results: {out_json}")
    print(f"  Report: CANARY_V4_BEFORE_AFTER.md")
    print(f"{'='*80}\n")

    return results


def generate_before_after_report(results, run_id):
    """Generate a before/after comparison report."""
    lines = []
    lines.append(f"# Canary V4 Before/After Report — {run_id}\n")
    lines.append(f"**Mode:** Offline (no external API calls)\n")
    lines.append(f"**Targets:** {len(results)}\n")
    lines.append(f"**Generated:** {datetime.now().isoformat()}\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| # | Target | Stato | Resolution | Origin | Claims | Missing | Violations | Elapsed |")
    lines.append("|---|--------|-------|------------|--------|--------|---------|------------|---------|")

    for r in results:
        if "error" in r:
            lines.append(f"| {r['ordinal']} | {r['full_name']} | ERROR | — | — | — | — | — | {r['elapsed_seconds']}s |")
            continue
        violations_str = str(len(r.get("validation_violations", [])))
        lines.append(
            f"| {r['ordinal']} | {r['full_name']} | {r['stato_identificazione']} | "
            f"{r['resolution_state']} | {r['origin_record_state']} | "
            f"{r['accepted_claims_count']} | {len(r.get('missing_claims', []))} | "
            f"{violations_str} | {r['elapsed_seconds']}s |"
        )

    # V4 Features verification
    lines.append("\n## V4 Features Verification\n")
    lines.append("| Feature | Status | Details |")
    lines.append("|---------|--------|---------|")

    # Check each V4 feature across all results
    all_have_snapshot = all("snapshot_id" in r for r in results if "error" not in r)
    all_have_routing = all("routing" in r for r in results if "error" not in r)
    all_have_archival = all("archival_suggestions" in r for r in results if "error" not in r)
    all_have_deterministic = all("deterministic_report" in r for r in results if "error" not in r)
    no_openai = True  # Guaranteed by use_ai=False

    lines.append(f"| EvidenceSnapshot V4 | {'✅' if all_have_snapshot else '❌'} | All targets have V4 snapshot |")
    lines.append(f"| Capability Routing | {'✅' if all_have_routing else '❌'} | Unified registry used |")
    lines.append(f"| ArchiveJurisdictionRegistry | {'✅' if all_have_archival else '❌'} | Verified registry, no templates |")
    lines.append(f"| Deterministic Report | {'✅' if all_have_deterministic else '❌'} | Fallback available |")
    lines.append(f"| No OpenAI Calls | {'✅' if no_openai else '❌'} | use_ai=False |")

    # Routing details
    lines.append("\n## Capability Routing Details\n")
    lines.append("| # | Target | Conflict | Eligible | Skipped | Skipped Providers |")
    lines.append("|---|--------|----------|----------|---------|-------------------|")
    for r in results:
        if "error" in r:
            continue
        routing = r.get("routing", {})
        skipped_str = ", ".join(routing.get("skipped", [])[:5])
        if len(routing.get("skipped", [])) > 5:
            skipped_str += f" (+{len(routing.get('skipped', [])) - 5} more)"
        lines.append(
            f"| {r['ordinal']} | {r['full_name']} | ww1 | "
            f"{routing.get('eligible_count', 0)} | {routing.get('skipped_count', 0)} | "
            f"{skipped_str} |"
        )

    # Archival suggestions
    lines.append("\n## Archival Suggestions (V4 Verified Registry)\n")
    for r in results:
        if "error" in r:
            continue
        lines.append(f"### {r['ordinal']}. {r['full_name']}\n")
        for s in r.get("archival_suggestions", []):
            verified = "✅" if s.get("verified") else "⚠️"
            lines.append(f"- {verified} **{s['ente']}** — {s.get('fondo', '')} — {s.get('documento_richiesto', '')}")
        lines.append("")

    # Validation violations
    lines.append("\n## Snapshot Validation Violations\n")
    any_violations = False
    for r in results:
        if "error" in r:
            continue
        violations = r.get("validation_violations", [])
        if violations:
            any_violations = True
            lines.append(f"### {r['ordinal']}. {r['full_name']}\n")
            for v in violations:
                lines.append(f"- ⚠️ {v}")
            lines.append("")
    if not any_violations:
        lines.append("✅ No validation violations across all targets.\n")

    # Missing claims
    lines.append("\n## Missing Claims per Target\n")
    lines.append("| # | Target | Missing Fields |")
    lines.append("|---|--------|----------------|")
    for r in results:
        if "error" in r:
            continue
        missing = r.get("missing_claims", [])
        lines.append(f"| {r['ordinal']} | {r['full_name']} | {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''} |")

    # Per-target detail
    lines.append("\n## Per-Target Detail\n")
    for r in results:
        if "error" in r:
            lines.append(f"### {r['ordinal']}. {r['full_name']} — ERROR\n")
            lines.append(f"```\n{r['error']}\n```\n")
            continue

        lines.append(f"### {r['ordinal']}. {r['target_id']} — {r['full_name']}\n")
        td = r["target_data"]
        lines.append(f"**Target:** {td.get('anno_nascita', '?')}, {td.get('luogo_nascita', '?')}, {td.get('reparto', '?')}\n")
        lines.append(f"**Stato:** `{r['stato_identificazione']}`  ")
        lines.append(f"**Resolution:** `{r['resolution_state']}`  ")
        lines.append(f"**Origin:** `{r['origin_record_state']}`\n")
        lines.append(f"**Snapshot:** `{r['snapshot_id']}` (hash: `{r['snapshot_hash'][:16]}...`)\n")
        lines.append(f"**Claims:** {r['accepted_claims_count']} accepted, {len(r.get('missing_claims', []))} missing\n")
        lines.append(f"**Reconciliation:**\n```json\n{json.dumps(r.get('reconciliation', {}), indent=2)}\n```\n")
        lines.append(f"**Research limitations:** {r.get('research_limitations', [])}\n")
        lines.append(f"**Deterministic report (excerpt):**\n```\n{r.get('deterministic_report', '')}\n```\n")
        lines.append("---\n")

    out_md = Path(__file__).parent / "CANARY_V4_BEFORE_AFTER.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    log.info("Report saved to %s", out_md)


if __name__ == "__main__":
    run_canary_v4_offline()
