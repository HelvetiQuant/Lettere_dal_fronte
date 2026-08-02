"""Generate discursive conversational reports for each canary target.

Uses existing CANARY_DOSSIERS.json data (from live canary run).
Uses ReportConversationProvider with Mistral/local AI (no OpenAI).
Each report is a natural-language narrative based on the V4 snapshot.
"""
import os, sys, json, time
from pathlib import Path
from datetime import datetime

# Fix Windows encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from report_conversation_provider import ReportConversationProvider
from ai_output_validator import generate_deterministic_report
from run_canary import CANARY_TARGETS


def generate_reports():
    provider = ReportConversationProvider()
    reports = []

    # Load existing canary dossiers
    dossiers_path = Path(__file__).parent / "CANARY_DOSSIERS.json"
    if not dossiers_path.exists():
        print("ERROR: CANARY_DOSSIERS.json not found. Run run_canary.py first.")
        return

    canary_data = json.loads(dossiers_path.read_text(encoding="utf-8"))
    print(f"\n{'='*80}")
    print(f"CONVERSATIONAL REPORTS — {datetime.now().isoformat()}")
    print(f"Provider: Mistral/local (OpenAI disabled)")
    print(f"Targets: {len(canary_data)}")
    print(f"Source: {dossiers_path.name}")
    print(f"{'='*80}\n")

    for entry in canary_data:
        ordinal = entry["ordinal"]
        full_name = entry["full_name"]
        target_id = entry["target_id"]
        dossier = entry["dossier"]
        all_candidates = entry.get("all_candidates", [])
        omonimi = entry.get("omonimi_esclusi", [])

        print(f"[{ordinal}/{len(canary_data)}] {full_name}...", flush=True)

        t_start = time.time()
        try:
            profilo = dossier.get("profilo", {})
            snap_dict = profilo.get("evidence_snapshot_v4", {})

            if not snap_dict:
                print(f"  WARNING: no evidence_snapshot_v4 in dossier, building minimal...")
                snap_dict = {
                    "snapshot_id": f"snap_{target_id}",
                    "snapshot_hash": "",
                    "target_id": profilo.get("target_id", target_id),
                    "target_hash": profilo.get("target_hash", ""),
                    "resolution_state": profilo.get("resolution_state", "UNRESOLVED"),
                    "origin_record_state": "ABSENT",
                    "accepted_claims": [],
                    "missing_claims": [],
                    "rejected_candidates": [],
                    "accepted_origin_evidence_sources": [],
                    "research_limitations": [],
                    "reconciliation": {},
                }

            # Create conversation bound to snapshot
            report_id = f"report_{target_id}"
            conv = provider.create_conversation(report_id, snap_dict)

            # Ask for a discursive report
            question = (
                "Genera un report discorsivo e conversazionale completo su questa persona. "
                "Descrivi cosa sappiamo, quali fonti sono state consultate, "
                "quali dati sono confermati e quali mancano. "
                "Includi il percorso di ricerca, gli archivi suggeriti, "
                "e i prossimi passi raccomandati. "
                "Usa un tono narrativo, non tecnico."
            )

            msg = provider.send_message(conv, question, snap_dict)

            # Deterministic fallback as reference
            det_report = generate_deterministic_report(snap_dict)

            # Candidates summary
            candidates_summary = []
            for c in all_candidates[:5]:
                candidates_summary.append({
                    "name": c.get("name", ""),
                    "stato": c.get("stato", ""),
                    "confidence": c.get("confidence", 0),
                    "birth_year": c.get("birth_year", ""),
                    "birth_place": c.get("birth_place", ""),
                    "paternita": c.get("paternita", ""),
                    "unit": c.get("unit", ""),
                    "grado": c.get("grado", ""),
                    "compatibilita": c.get("compatibilita", []),
                    "contraddizioni": c.get("contraddizioni", []),
                    "fonti_count": len(c.get("fonti", [])),
                })

            # Web search results
            ws = dossier.get("web_search_results", {})
            ws_sources = ws.get("sources", []) if isinstance(ws, dict) else []
            ws_classifications = ws.get("source_classifications", []) if isinstance(ws, dict) else []

            # Target data from CANARY_TARGETS
            target_data = {}
            for t in CANARY_TARGETS:
                if t["target_id"] == target_id:
                    target_data = {
                        "anno_nascita": t.get("anno_nascita", ""),
                        "luogo_nascita": t.get("luogo_nascita", ""),
                        "reparto": t.get("reparto", ""),
                        "paternita": t.get("paternita", ""),
                        "grado": t.get("grado", ""),
                    }
                    break

            elapsed = time.time() - t_start

            report = {
                "target_id": target_id,
                "ordinal": ordinal,
                "full_name": full_name,
                "target_data": target_data,
                "elapsed_seconds": round(elapsed, 1),
                "stato_identificazione": dossier.get("stato_identificazione", ""),
                "resolution_state": snap_dict.get("resolution_state", ""),
                "origin_record_state": snap_dict.get("origin_record_state", ""),
                "conversational_report": msg.content,
                "validation_state": msg.validation_state,
                "deterministic_fallback": det_report[:2000] + "..." if len(det_report) > 2000 else det_report,
                "snapshot_id": snap_dict.get("snapshot_id", ""),
                "accepted_claims": snap_dict.get("accepted_claims", []),
                "missing_claims": snap_dict.get("missing_claims", []),
                "candidates_count": dossier.get("candidati_count", 0),
                "top_candidates": candidates_summary,
                "omonimi_count": len(omonimi),
                "web_search_used": dossier.get("web_search_used", False),
                "web_search_sources": len(ws_sources),
                "web_search_classifications": [
                    {"url": s.get("url", "")[:80], "kind": s.get("object_kind", ""), "eligible": s.get("evidence_eligible", False)}
                    for s in ws_classifications[:5]
                ],
                "ai_used": dossier.get("ai_used", False),
                "provider": conv.provider,
                "model": conv.model,
                "richieste": dossier.get("richieste", [])[:3],
                "piste": dossier.get("piste", [])[:3],
            }

            reports.append(report)
            print(f"  -> stato: {dossier.get('stato_identificazione', '?')} | validation: {msg.validation_state}")
            print(f"  -> claims: {len(snap_dict.get('accepted_claims', []))} accepted, {len(snap_dict.get('missing_claims', []))} missing")
            print(f"  -> elapsed: {elapsed:.1f}s")

        except Exception as e:
            import traceback
            traceback.print_exc()
            reports.append({
                "target_id": target_id,
                "ordinal": ordinal,
                "full_name": full_name,
                "error": str(e)[:500],
                "elapsed_seconds": round(time.time() - t_start, 1),
            })

    # Save JSON
    out_json = Path(__file__).parent / "CONVERSATIONAL_REPORTS.json"
    out_json.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate markdown
    generate_markdown(reports)

    print(f"\n{'='*80}")
    print(f"DONE — {len(reports)} reports generated")
    print(f"  JSON: {out_json}")
    print(f"  MD:   CONVERSATIONAL_REPORTS.md")
    print(f"{'='*80}\n")


def generate_markdown(reports):
    lines = []
    lines.append(f"# Report Discorsivi e Conversazionali — Canary V4\n")
    lines.append(f"**Generato:** {datetime.now().isoformat()}\n")
    lines.append(f"**Provider:** Mistral/local (OpenAI disabled)\n")
    lines.append(f"**Target:** {len(reports)}\n")

    # Summary
    lines.append("## Riepilogo\n")
    lines.append("| # | Target | Stato | Resolution | Claims | Validation | Elapsed |")
    lines.append("|---|--------|-------|------------|--------|------------|---------|")
    for r in reports:
        if "error" in r:
            lines.append(f"| {r['ordinal']} | {r['full_name']} | ERROR | — | — | — | {r['elapsed_seconds']}s |")
            continue
        n_accepted = len(r.get('accepted_claims', []))
        n_missing = len(r.get('missing_claims', []))
        lines.append(
            f"| {r['ordinal']} | {r['full_name']} | {r['stato_identificazione']} | "
            f"{r['resolution_state']} | {n_accepted}/{n_accepted+n_missing} | "
            f"{r['validation_state']} | {r['elapsed_seconds']}s |"
        )

    # Per-target reports
    lines.append("\n---\n")
    for r in reports:
        if "error" in r:
            lines.append(f"## {r['ordinal']}. {r['full_name']} — ERROR\n")
            lines.append(f"```\n{r['error']}\n```\n")
            continue

        td = r["target_data"]
        lines.append(f"## {r['ordinal']}. {r['full_name']}\n")
        lines.append(f"**Dati target:** {td.get('anno_nascita', '?')}, {td.get('luogo_nascita', '?')}, {td.get('reparto', '?')}\n")
        lines.append(f"**Stato identificazione:** `{r['stato_identificazione']}`\n")
        lines.append(f"**Resolution state:** `{r['resolution_state']}`\n")
        lines.append(f"**Origin record:** `{r['origin_record_state']}`\n")
        lines.append(f"**Snapshot:** `{r['snapshot_id']}`\n")
        lines.append(f"**Claims:** {len(r.get('accepted_claims', []))} confermati, {len(r.get('missing_claims', []))} mancanti\n")
        lines.append(f"**Provider:** {r['provider']} | **Validation:** {r['validation_state']}\n")
        lines.append(f"**Web search:** {'si' if r['web_search_used'] else 'no'} ({r['web_search_sources']} sources)\n")
        lines.append(f"**AI:** {'si' if r['ai_used'] else 'no'}\n")
        if r.get("ai_error"):
            lines.append(f"**AI error:** `{r['ai_error'].get('error_code', '?')}`\n")
        lines.append(f"**Elapsed:** {r['elapsed_seconds']}s\n")

        # Conversational report
        lines.append(f"\n### Report Conversazionale\n")
        lines.append(f"{r['conversational_report']}\n")

        # Top candidates
        if r.get("top_candidates"):
            lines.append(f"\n### Candidati top ({len(r['top_candidates'])})\n")
            lines.append("| # | Nome | Stato | Conf | Anno | Luogo | Paternita | Reparto | Fonti |")
            lines.append("|---|------|-------|------|------|--------|-----------|---------|-------|")
            for i, c in enumerate(r["top_candidates"], 1):
                lines.append(
                    f"| {i} | {c['name']} | {c['stato']} | {c['confidence']:.2f} | "
                    f"{c.get('birth_year', '')} | {c.get('birth_place', '')} | "
                    f"{c.get('paternita', '')} | {c.get('unit', '')} | "
                    f"{c.get('fonti_count', 0)} |"
                )

        # Missing claims
        if r.get("missing_claims"):
            lines.append(f"\n### Dati mancanti\n")
            for mc in r["missing_claims"]:
                lines.append(f"- {mc}")

        # Web search classifications
        if r.get("web_search_classifications"):
            lines.append(f"\n### Classificazione fonti web\n")
            lines.append("| URL | Tipo | Evidence eligible |")
            lines.append("|-----|------|-------------------|")
            for wc in r["web_search_classifications"]:
                lines.append(f"| {wc['url']} | {wc['kind']} | {wc['eligible']} |")

        # Deterministic fallback
        if r.get("deterministic_fallback"):
            lines.append(f"\n### Fallback deterministico (riferimento)\n")
            lines.append(f"```\n{r['deterministic_fallback']}\n```\n")

        lines.append("\n---\n")

    out_md = Path(__file__).parent / "CONVERSATIONAL_REPORTS.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    generate_reports()
