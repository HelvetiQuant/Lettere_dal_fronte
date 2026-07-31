"""Canary run: 10 target con dati CORRETTI dal benchmark.

Usa il manifest system per tracciare target_id, hash, stati.
Manda query reali al backend (research_person) e raccoglie risposte strutturate.

7 derive note + 3 casi di controllo:
- LARI GIUSEPPE 1886 Canneto (derive: 1883 Ronciglione)
- FEDERICO LUIGI 1885 Longobucco (derive: 1895 Larino)
- GIUNTA GIUSEPPE 1879 Modica (derive: 1883 San Lorenzo)
- VENEZIANO NICOLA 1898 Lioni (derive: 1879 Casaluce)
- FANTUZ ANTONIO 1896 Pasiano (derive: 1894 Pasiano)
- FEDELE AGOSTINO 1880 Magnano (derive: 1895 Brienza)
- RUSSO GAETANO 1888 Misterbianco (derive: 1876 Lettere)
- PAPINI PUBLIO 1890 Roccalbegna (controllo: no derive)
- FOLLADOR GIOVANNI 1898 Falcade (controllo: no derive)
- SIFANNO TOMMASO 1884 Bitonto (controllo: no derive)
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
log = logging.getLogger("canary")

# ── CORRECT target data from benchmark spec ──
CANARY_TARGETS = [
    # 7 derive note — target data is CORRECT, omonimo will be found in DB
    {"ordinal": 1, "target_id": "WWI-001", "cognome": "LARI", "nome": "GIUSEPPE",
     "paternita": "EMANUELE", "anno_nascita": "1886", "luogo_nascita": "Canneto sull'Oglio",
     "grado": "Soldato", "reparto": "206 Reggimento Fanteria", "conflitto_presunto": "ww1"},
    {"ordinal": 2, "target_id": "WWI-002", "cognome": "FEDERICO", "nome": "LUIGI",
     "paternita": "GIUSEPPE", "anno_nascita": "1885", "luogo_nascita": "Longobucco",
     "grado": "Soldato", "reparto": "138 Reggimento Fanteria", "conflitto_presunto": "ww1"},
    {"ordinal": 3, "target_id": "WWI-003", "cognome": "GIUNTA", "nome": "GIUSEPPE",
     "paternita": "RAFFAELE", "anno_nascita": "1879", "luogo_nascita": "Modica",
     "grado": "Maggiore In Servizio Attivo", "reparto": "2 Reggimento Granatieri", "conflitto_presunto": "ww1"},
    {"ordinal": 4, "target_id": "WWI-004", "cognome": "VENEZIANO", "nome": "NICOLA",
     "paternita": "VITO", "anno_nascita": "1898", "luogo_nascita": "Lioni",
     "grado": "Soldato", "reparto": "4 Reggimento Fanteria", "conflitto_presunto": "ww1"},
    {"ordinal": 5, "target_id": "WWI-005", "cognome": "FANTUZ", "nome": "ANTONIO",
     "paternita": "PIETRO", "anno_nascita": "1896", "luogo_nascita": "Pasiano di Pordenone",
     "grado": "Soldato", "reparto": "228 Reggimento Fanteria", "conflitto_presunto": "ww1"},
    {"ordinal": 6, "target_id": "WWI-006", "cognome": "FEDELE", "nome": "AGOSTINO",
     "paternita": "PIETRO", "anno_nascita": "1880", "luogo_nascita": "Magnano in Riviera",
     "grado": "Soldato", "reparto": "128 Battaglione M. T.", "conflitto_presunto": "ww1"},
    {"ordinal": 7, "target_id": "WWI-007", "cognome": "RUSSO", "nome": "GAETANO",
     "paternita": "FRANCESCO", "anno_nascita": "1888", "luogo_nascita": "Misterbianco",
     "grado": "Soldato", "reparto": "48 Reggimento Fanteria", "conflitto_presunto": "ww1"},
    # 3 casi di controllo — no known derive
    {"ordinal": 8, "target_id": "WWI-008", "cognome": "PAPINI", "nome": "PUBLIO",
     "paternita": "GIOVANNI", "anno_nascita": "1890", "luogo_nascita": "Roccalbegna",
     "grado": "Soldato", "reparto": "351 Batteria Bombardieri", "conflitto_presunto": "ww1"},
    {"ordinal": 9, "target_id": "WWI-009", "cognome": "FOLLADOR", "nome": "GIOVANNI",
     "paternita": "", "anno_nascita": "1898", "luogo_nascita": "Falcade",
     "grado": "Soldato", "reparto": "117 Reggimento Fanteria", "conflitto_presunto": "ww1"},
    {"ordinal": 10, "target_id": "WWI-010", "cognome": "SIFANNO", "nome": "TOMMASO",
     "paternita": "GIUSEPPE", "anno_nascita": "1884", "luogo_nascita": "Bitonto",
     "grado": "Soldato", "reparto": "139 Reggimento Fanteria", "conflitto_presunto": "ww1"},
]


def run_canary():
    from research_protocol import research_person, SearchInput
    from research_manifest import build_manifest, RunStatus, TargetPhase, save_manifest

    # Build manifest
    manifest_targets = []
    for t in CANARY_TARGETS:
        raw_input = {k: v for k, v in t.items() if k not in ("ordinal", "target_id")}
        manifest_targets.append({
            "ordinal": t["ordinal"],
            "target_id": t["target_id"],
            "target_type": "person",
            "conflict": t.get("conflitto_presunto", "unknown"),
            "raw_input": raw_input,
        })
    manifest = build_manifest(
        run_id=f"canary_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        scope="people-only",
        targets_data=manifest_targets,
        benchmark_version="2026-07-31-v1-canary",
    )
    save_manifest(manifest)

    run_status = RunStatus(
        run_id=manifest.run_id,
        manifest_hash=manifest.manifest_hash,
        expected=manifest.expected_targets,
        scope="people-only",
    )
    run_status.started_at = datetime.now().isoformat()

    results = []

    print(f"\n{'='*80}")
    print(f"CANARY RUN — {manifest.run_id}")
    print(f"Manifest hash: {manifest.manifest_hash}")
    print(f"Targets: {manifest.expected_targets}")
    print(f"{'='*80}\n")

    for t in CANARY_TARGETS:
        target_id = t["target_id"]
        ordinal = t["ordinal"]
        full_name = f"{t['cognome']} {t['nome']}"

        print(f"\n[{ordinal}/{manifest.expected_targets}] {target_id}: {full_name}")
        print(f"  Target: {t.get('anno_nascita', '?')}, {t.get('luogo_nascita', '?')}, {t.get('reparto', '?')}")

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
            dossier = research_person(si.__dict__, use_ai=True, persist=False)
            elapsed = time.time() - t_start

            # Extract structured results
            resolution_state = dossier.profilo.get("resolution_state", "UNRESOLVED")
            local_match = dossier.profilo.get("local_match_state", "NOT_SEARCHED")
            external_val = dossier.profilo.get("external_validation_state", "NOT_RUN")
            typed_counts = dossier.profilo.get("typed_counts", {})
            ai_error = dossier.profilo.get("ai_error")

            # Candidates — ALL of them, with ALL fields
            candidates_summary = []
            for c in dossier.candidati:
                candidates_summary.append({
                    "name": c.nome_originale,
                    "stato": c.stato,
                    "confidence": c.confidence,
                    "birth_year": c.data_nascita,
                    "birth_place": c.luogo_nascita,
                    "paternita": c.paternita,
                    "maternita": c.maternita,
                    "residenza": c.residenza,
                    "professione": c.professione,
                    "matricola": c.matricola,
                    "distretto": c.distretto,
                    "unit": c.reparto,
                    "grado": c.grado,
                    "morte": c.morte,
                    "prigionia": c.prigionia,
                    "sepoltura": c.sepoltura,
                    "compatibilita": c.compatibilita,
                    "contraddizioni": c.contraddizioni,
                    "fonti": [{"istituzione": f.istituzione, "url": f.url, "source_level": f.source_level, "esito": f.esito} for f in c.fonti],
                })

            # Omonimi esclusi — ALL of them, with ALL fields
            omonimi = []
            for c in dossier.omonimi_esclusi:
                omonimi.append({
                    "name": c.nome_originale,
                    "birth_year": c.data_nascita,
                    "birth_place": c.luogo_nascita,
                    "paternita": c.paternita,
                    "unit": c.reparto,
                    "grado": c.grado,
                    "morte": c.morte,
                    "conflicts": c.contraddizioni if c.contraddizioni else [],
                    "compatibilita": c.compatibilita,
                    "fonti": [{"istituzione": f.istituzione, "url": f.url} for f in c.fonti],
                })

            # Search log
            search_log = []
            for sl in dossier.search_log:
                search_log.append({
                    "query": sl.query,
                    "motore": sl.motore_o_archivio,
                    "connection_type": sl.connection_type,
                    "risultati": sl.risultati_trovati,
                    "esito": sl.esito,
                })

            # Full dossier dump for backend verification
            full_dossier = {
                "stato_identificazione": dossier.stato_identificazione,
                "candidati_count": len(dossier.candidati),
                "omonimi_count": len(dossier.omonimi_esclusi),
                "varianti": [{"text": v.text, "type": v.variant_type, "source": v.source} for v in dossier.varianti],
                "search_log": search_log,
                "ricerche_negative": [{"query": sl.query, "motore": sl.motore_o_archivio, "esito": sl.esito} for sl in dossier.ricerche_negative],
                "piste": dossier.piste,
                "richieste": dossier.richieste,
                "profilo": dossier.profilo,
                "web_search_used": dossier.web_search_used,
                "web_search_results": dossier.web_search_results,
                "ai_used": dossier.ai_used,
            }

            # Web search
            ws = dossier.web_search_results or {}
            ws_error = ws.get("error") if isinstance(ws, dict) else None
            ws_sources = ws.get("sources", []) if isinstance(ws, dict) else []
            ws_classifications = ws.get("source_classifications", []) if isinstance(ws, dict) else []

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
                "resolution_state": resolution_state,
                "local_match_state": local_match,
                "external_validation_state": external_val,
                "typed_counts": typed_counts,
                "candidates_count": len(dossier.candidati),
                "omonimi_esclusi_count": len(dossier.omonimi_esclusi),
                "all_candidates": candidates_summary,
                "omonimi_esclusi": omonimi,
                "search_log": search_log,
                "full_dossier": full_dossier,
                "web_search_used": dossier.web_search_used,
                "web_search_sources_count": len(ws_sources),
                "web_search_error": ws_error,
                "web_search_source_classifications": ws_classifications[:5],
                "ai_error": ai_error,
                "ai_used": dossier.ai_used,
            }

            results.append(result)
            run_status.update_target_phase(target_id, TargetPhase.COMPLETED)

            # Print summary
            print(f"  → stato: {dossier.stato_identificazione} | resolution: {resolution_state}")
            print(f"  → local_match: {local_match} | external: {external_val}")
            print(f"  → candidates: {len(dossier.candidati)} | omonimi: {len(dossier.omonimi_esclusi)}")
            print(f"  → typed_counts: {json.dumps(typed_counts, ensure_ascii=False)}")
            # Print ALL candidates with full data
            for i, c in enumerate(dossier.candidati, 1):
                print(f"    [{i}] {c.nome_originale} | stato={c.stato} conf={c.confidence:.2f} "
                      f"year={c.data_nascita} place={c.luogo_nascita} unit={c.reparto} "
                      f"grado={c.grado} paternita={c.paternita}")
            # Print ALL omonimi
            for i, c in enumerate(dossier.omonimi_esclusi, 1):
                print(f"    EXCLUDED[{i}] {c.nome_originale} | year={c.data_nascita} place={c.luogo_nascita} "
                      f"unit={c.reparto} conflicts={c.contraddizioni}")
            print(f"  → web_search: {'✅' if dossier.web_search_used else '❌'} ({len(ws_sources)} sources)")
            if ws_error:
                print(f"  → web_search_error: {ws_error.get('error_code', '?')} — {ws_error.get('safe_message', '')[:80]}")
            if ai_error:
                print(f"  → ai_error: {ai_error.get('error_code', '?')} — {ai_error.get('safe_message', '')[:80]}")
            print(f"  → elapsed: {elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - t_start
            log.error("Failed for %s: %s", full_name, e)
            results.append({
                "target_id": target_id,
                "ordinal": ordinal,
                "full_name": full_name,
                "error": str(e)[:200],
                "elapsed_seconds": round(elapsed, 1),
            })
            run_status.update_target_phase(target_id, TargetPhase.PERMANENT_ERROR)

    run_status.finalize()

    # ── Manifest completeness verification ──
    expected_ids = {t["target_id"] for t in CANARY_TARGETS}
    processed_ids = {r.get("target_id", "") for r in results if "error" not in r}
    failed_ids = {r.get("target_id", "") for r in results if "error" in r}
    missing_ids = expected_ids - processed_ids - failed_ids
    unexpected_ids = processed_ids - expected_ids

    print(f"\n{'='*80}")
    print(f"MANIFEST COMPLETENESS CHECK")
    print(f"  Expected: {len(expected_ids)} targets")
    print(f"  Processed: {len(processed_ids)} targets")
    print(f"  Failed: {len(failed_ids)} targets")
    print(f"  Missing: {len(missing_ids)} targets — {missing_ids if missing_ids else 'none'}")
    print(f"  Unexpected: {len(unexpected_ids)} targets — {unexpected_ids if unexpected_ids else 'none'}")
    if missing_ids:
        print(f"  ⚠️ INCOMPLETE RUN: {len(missing_ids)} targets missing from output!")
    if unexpected_ids:
        print(f"  ⚠️ SUBJECT DRIFT: {len(unexpected_ids)} unexpected targets in output!")
    if not missing_ids and not unexpected_ids:
        print(f"  ✅ Manifest complete — all expected targets processed, no drift")
    print(f"{'='*80}\n")

    # Save results — full JSON with all candidates
    out_json = Path(__file__).parent / "CANARY_RESULTS.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save full dossier dump separately for backend verification
    out_dossiers = Path(__file__).parent / "CANARY_DOSSIERS.json"
    dossiers_data = [{
        "target_id": r.get("target_id", ""),
        "ordinal": r.get("ordinal", 0),
        "full_name": r.get("full_name", ""),
        "dossier": r.get("full_dossier", {}),
        "all_candidates": r.get("all_candidates", []),
        "omonimi_esclusi": r.get("omonimi_esclusi", []),
    } for r in results]
    out_dossiers.write_text(json.dumps(dossiers_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate report
    out_md = Path(__file__).parent / "CANARY_REPORT.md"
    generate_report(results, manifest, run_status, out_md)

    print(f"\n{'='*80}")
    print(f"RUN COMPLETE — state: {run_status.state.value}")
    print(f"  Expected: {run_status.expected}")
    print(f"  Completed: {run_status.completed}")
    print(f"  Failed: {run_status.failed}")
    print(f"  Results: {out_json}")
    print(f"  Dossiers: {out_dossiers}")
    print(f"  Report: {out_md}")
    print(f"{'='*80}\n")

    return results


def generate_report(results, manifest, run_status, out_path):
    lines = []
    lines.append(f"# Canary Report — {manifest.run_id}\n")
    lines.append(f"**Manifest hash:** `{manifest.manifest_hash}`  ")
    lines.append(f"**Scope:** {manifest.scope}  ")
    lines.append(f"**Expected targets:** {manifest.expected_targets}  ")
    lines.append(f"**Run state:** `{run_status.state.value}`  ")
    lines.append(f"**Completed:** {run_status.completed} | **Failed:** {run_status.failed}\n")

    lines.append("## Riepilogo per target\n")
    lines.append("| # | Target | Target data | Stato | Resolution | Candidates | Omonimi | Web | AI | Elapsed |")
    lines.append("|---|--------|-------------|-------|------------|------------|---------|-----|----|---------|")

    for r in results:
        if "error" in r:
            lines.append(f"| {r['ordinal']} | {r['full_name']} | — | ERROR | — | — | — | — | — | {r['elapsed_seconds']}s |")
            continue
        td = r["target_data"]
        target_str = f"{td.get('anno_nascita', '?')}, {td.get('luogo_nascita', '?')}"
        ws = "✅" if r["web_search_used"] else "❌"
        ai = "✅" if r["ai_used"] else "❌"
        lines.append(
            f"| {r['ordinal']} | {r['full_name']} | {target_str} | {r['stato_identificazione']} | "
            f"{r['resolution_state']} | {r['candidates_count']} | {r['omonimi_esclusi_count']} | "
            f"{ws} | {ai} | {r['elapsed_seconds']}s |"
        )

    lines.append("\n## Dettaglio per target\n")
    for r in results:
        if "error" in r:
            lines.append(f"### {r['ordinal']}. {r['full_name']} — ERROR\n")
            lines.append(f"```\n{r['error']}\n```\n")
            continue

        lines.append(f"### {r['ordinal']}. {r['target_id']} — {r['full_name']}\n")
        td = r["target_data"]
        lines.append(f"**Target:** {td.get('anno_nascita', '?')}, {td.get('luogo_nascita', '?')}, {td.get('reparto', '?')}\n")
        lines.append(f"**Stato identificazione:** `{r['stato_identificazione']}`  ")
        lines.append(f"**Resolution state:** `{r['resolution_state']}`  ")
        lines.append(f"**Local match:** `{r['local_match_state']}`  ")
        lines.append(f"**External validation:** `{r['external_validation_state']}`\n")

        tc = r["typed_counts"]
        lines.append(f"**Typed counts:**\n```json\n{json.dumps(tc, ensure_ascii=False, indent=2)}\n```\n")

        if r.get("all_candidates"):
            lines.append(f"**All candidates ({len(r['all_candidates'])}):**\n")
            lines.append("| # | Name | Stato | Conf | Year | Place | Paternita | Unit | Grado | Fonti |")
            lines.append("|---|------|-------|------|------|--------|-----------|------|-------|-------|")
            for i, c in enumerate(r["all_candidates"], 1):
                fonti_str = "; ".join(f.get("istituzione", "") for f in c.get("fonti", []))
                lines.append(
                    f"| {i} | {c['name']} | {c['stato']} | {c['confidence']:.2f} | "
                    f"{c.get('birth_year', '')} | {c.get('birth_place', '')} | "
                    f"{c.get('paternita', '')} | {c.get('unit', '')} | {c.get('grado', '')} | "
                    f"{fonti_str[:60]} |"
                )
            lines.append("")

        if r["omonimi_esclusi"]:
            lines.append(f"**Omonimi esclusi ({len(r['omonimi_esclusi'])}):**\n")
            lines.append("| # | Name | Year | Place | Unit | Paternita | Conflicts |")
            lines.append("|---|------|------|--------|------|-----------|-----------|")
            for i, o in enumerate(r["omonimi_esclusi"], 1):
                conflicts_str = "; ".join(o.get("conflicts", []))[:80]
                lines.append(
                    f"| {i} | {o['name']} | {o.get('birth_year', '')} | "
                    f"{o.get('birth_place', '')} | {o.get('unit', '')} | "
                    f"{o.get('paternita', '')} | {conflicts_str} |"
                )
            lines.append("")

        if r.get("search_log"):
            lines.append(f"**Search log ({len(r['search_log'])} entries):**\n")
            lines.append("| Query | Motore | Connection | Risultati | Esito |")
            lines.append("|-------|--------|------------|-----------|-------|")
            for sl in r["search_log"]:
                lines.append(
                    f"| {sl.get('query', '')} | {sl.get('motore', '')} | "
                    f"{sl.get('connection_type', '')} | {sl.get('risultati', 0)} | "
                    f"{sl.get('esito', '')} |"
                )
            lines.append("")

        if r["web_search_error"]:
            lines.append(f"**Web search error:**\n```json\n{json.dumps(r['web_search_error'], ensure_ascii=False, indent=2)}\n```\n")
        elif r["web_search_used"]:
            lines.append(f"**Web search:** ✅ ({r['web_search_sources_count']} sources)\n")
            if r["web_search_source_classifications"]:
                lines.append("**Source classifications:**\n")
                for sc in r["web_search_source_classifications"]:
                    lines.append(f"- `{sc['object_kind']}` — {sc['url'][:80]} (evidence_eligible: {sc['evidence_eligible']})")
                lines.append("")

        if r["ai_error"]:
            lines.append(f"**AI error:**\n```json\n{json.dumps(r['ai_error'], ensure_ascii=False, indent=2)}\n```\n")

        lines.append(f"**Elapsed:** {r['elapsed_seconds']}s\n")
        lines.append("---\n")

    lines.append(f"\n## Run status\n")
    lines.append(f"```json\n{json.dumps(run_status.to_dict(), ensure_ascii=False, indent=2)}\n```\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Report saved to %s", out_path)


if __name__ == "__main__":
    run_canary()
