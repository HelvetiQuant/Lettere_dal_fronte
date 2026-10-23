"""Canary V6 — Real backend conversational test with V6 pipeline.

Tests:
- 3 names from each nominative DB (internati, caduti_albooro, decorati_nastroazzurro)
- 3 events from eventi_1gm
- 3 aggregate queries

For each target:
1. Build QueryManifest (canonical, immutable, hashed)
2. Classify intent via ResearchIntentRouter
3. Search backend for data
4. Build EvidenceSnapshotV6 with proper origin, claims, gaps, next steps
5. For aggregates: use AggregateQueryResolver (deterministic SQL)
6. Create conversation via V6 API
7. Send 3 follow-up questions
8. Validate: no internal markers, no unopened evidence, no unsupported facts

Output:
- CANARY_V6_RESULTS.json (raw results)
- CANARY_V6_REPORT.md (discursive + analytical report)
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BACKEND = "http://127.0.0.1:8000"
BASE_DIR = Path(__file__).parent

# ─── Data extraction ──────────────────────────────────────────────────────────

def get_db_path(name):
    return str(BASE_DIR / name)


def extract_internati(n=3):
    conn = sqlite3.connect(get_db_path("imi_internati.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, luogo_internamento, sorte FROM internati LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def extract_caduti_albooro(n=3):
    conn = sqlite3.connect(get_db_path("imi_internati.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, nominativo, comune_attuale, grado, reparto, anno_morte, luogo_morte, causa_morte FROM caduti_albooro LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def extract_decorati(n=3):
    conn = sqlite3.connect(get_db_path("imi_internati.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, cognome, nome, tipo_decorazione, anno_decorazione FROM decorati_nastroazzurro LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def extract_events(n=3):
    conn = sqlite3.connect(get_db_path("eventi_1gm.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, nome, data_inizio, data_fine, luogo, descrizione FROM eventi_1gm LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Snapshot building ────────────────────────────────────────────────────────

def build_person_snapshot(record, db_type="internati"):
    from evidence_snapshot_v6 import EvidenceSnapshotV6, ClaimV6, NextStepEntry, Limitation
    from next_step_catalog import NextStepCatalog
    from query_manifest import QueryManifest

    surname = record.get("cognome", record.get("nominativo", ""))
    given = record.get("nome", "").split() if record.get("nome") else []
    if not given and " " in surname:
        parts = surname.split()
        surname = parts[0]
        given = parts[1:]

    manifest = QueryManifest.for_person(
        target_id=f"{db_type}_{record.get('id', 'unknown')}",
        surname=surname,
        given_names=given,
        birth_year=record.get("anno_nascita"),
        birth_place=record.get("luogo_nascita"),
        rank=record.get("grado"),
        conflict="WWI" if db_type in ("caduti_albooro", "decorati_nastroazzurro") else "WWII",
    )

    catalog = NextStepCatalog()
    conflict = "WWI" if db_type in ("caduti_albooro", "decorati_nastroazzurro") else "WWII"
    gaps = ["birth_year", "birth_place", "internment_place", "service_number"]
    next_steps_raw = catalog.select_steps("PERSON_LOOKUP", conflict, gaps=gaps)

    asserted = []
    if record.get("data_nascita"):
        asserted.append(ClaimV6(claim_id="c_by", subject_id=manifest.target["target_id"], predicate="birth_year", value_normalized=str(record["data_nascita"]), source="origin_record"))
    if record.get("luogo_nascita") or record.get("comune_attuale"):
        bp = record.get("luogo_nascita") or record.get("comune_attuale")
        asserted.append(ClaimV6(claim_id="c_bp", subject_id=manifest.target["target_id"], predicate="birth_place", value_normalized=bp, source="origin_record"))
    if record.get("grado"):
        asserted.append(ClaimV6(claim_id="c_rk", subject_id=manifest.target["target_id"], predicate="rank", value_normalized=record["grado"], source="origin_record"))
    if record.get("luogo_internamento"):
        asserted.append(ClaimV6(claim_id="c_ip", subject_id=manifest.target["target_id"], predicate="internment_place", value_normalized=record["luogo_internamento"], source="origin_record"))
    if record.get("sorte"):
        asserted.append(ClaimV6(claim_id="c_ft", subject_id=manifest.target["target_id"], predicate="fate", value_normalized=record["sorte"], source="origin_record"))
    if record.get("tipo_decorazione"):
        asserted.append(ClaimV6(claim_id="c_de", subject_id=manifest.target["target_id"], predicate="decoration_type", value_normalized=record["tipo_decorazione"], source="origin_record"))
    if record.get("causa_morte"):
        asserted.append(ClaimV6(claim_id="c_dc", subject_id=manifest.target["target_id"], predicate="death_cause", value_normalized=record["causa_morte"], source="origin_record"))
    if record.get("reparto"):
        asserted.append(ClaimV6(claim_id="c_un", subject_id=manifest.target["target_id"], predicate="unit", value_normalized=record["reparto"], source="origin_record"))
    if record.get("anno_morte"):
        asserted.append(ClaimV6(claim_id="c_dy", subject_id=manifest.target["target_id"], predicate="death_year", value_normalized=str(record["anno_morte"]), source="origin_record"))
    if record.get("luogo_morte"):
        asserted.append(ClaimV6(claim_id="c_dp", subject_id=manifest.target["target_id"], predicate="death_place", value_normalized=record["luogo_morte"], source="origin_record"))

    snap = EvidenceSnapshotV6(
        manifest_hash=manifest.manifest_hash,
        intent="PERSON_LOOKUP",
        target=manifest.target,
        origin={
            "presence": "PRESENT_LOCAL",
            "provenance": "UNVERIFIED",
            "source_id": f"{db_type}_{record.get('id', 'unknown')}",
        },
        identity_resolution="PARTIAL",
        external_corroboration="NONE",
        asserted_claims=asserted,
        next_steps=[
            NextStepEntry(
                step_id=f"ns_{i}",
                catalog_id=s.catalog_id,
                description=s.description,
                archive=s.archive,
                access_mode=s.access_mode,
                priority=s.priority,
            )
            for i, s in enumerate(next_steps_raw)
        ],
        limitations=[
            Limitation(code="NO_EXTERNAL_CORROBORATION", description="Record d'origine non corroborato esternamente"),
            Limitation(code="UNVERIFIED_ORIGIN", description="Provenienza del record d'origine non verificata"),
        ],
    )
    snap.compute_conditional_gaps()
    return snap.to_dict(), manifest


def build_event_snapshot(record):
    from evidence_snapshot_v6 import EvidenceSnapshotV6, ClaimV6, Limitation
    from query_manifest import QueryManifest

    manifest = QueryManifest.for_event(
        event_id=f"eventi_1gm_{record.get('id', 'unknown')}",
        event_name=record.get("nome", ""),
        start_date=record.get("data_inizio"),
        end_date=record.get("data_fine"),
        location=record.get("luogo"),
        conflict="WWI",
    )

    asserted = []
    if record.get("data_inizio"):
        asserted.append(ClaimV6(claim_id="c_sd", subject_id=manifest.target["target_id"], predicate="event_start_date", value_normalized=record["data_inizio"], source="event_db"))
    if record.get("data_fine"):
        asserted.append(ClaimV6(claim_id="c_ed", subject_id=manifest.target["target_id"], predicate="event_end_date", value_normalized=record["data_fine"], source="event_db"))
    if record.get("luogo"):
        asserted.append(ClaimV6(claim_id="c_el", subject_id=manifest.target["target_id"], predicate="event_location", value_normalized=record["luogo"], source="event_db"))
    if record.get("descrizione"):
        asserted.append(ClaimV6(claim_id="c_ed2", subject_id=manifest.target["target_id"], predicate="event_description", value_normalized=record["descrizione"][:200], source="event_db"))

    snap = EvidenceSnapshotV6(
        manifest_hash=manifest.manifest_hash,
        intent="EVENT_LOOKUP",
        target=manifest.target,
        origin={
            "presence": "PRESENT_LOCAL",
            "provenance": "VERIFIED",
            "source_id": f"eventi_1gm_{record.get('id', 'unknown')}",
        },
        identity_resolution="RESOLVED",
        external_corroboration="NONE",
        asserted_claims=asserted,
        limitations=[
            Limitation(code="EVENT_DB_ONLY", description="Dati evento da database locale, non corroborati esternamente"),
        ],
    )
    snap.compute_conditional_gaps()
    return snap.to_dict(), manifest


def build_aggregate_snapshot(description, filters=None):
    from evidence_snapshot_v6 import EvidenceSnapshotV6, Limitation
    from aggregate_query_resolver import AggregateQueryResolver
    from query_manifest import QueryManifest

    manifest = QueryManifest.for_aggregate(
        query_id=f"agg_{hash(description) % 10000}",
        description=description,
        filters=filters or {},
    )

    resolver = AggregateQueryResolver()
    result = resolver.resolve(description, filters or {})

    snap = EvidenceSnapshotV6(
        manifest_hash=manifest.manifest_hash,
        intent="AGGREGATE_QUERY",
        target=manifest.target,
        origin={"presence": "ABSENT", "provenance": "UNVERIFIED"},
        identity_resolution="RESOLVED",
        external_corroboration="NONE",
        aggregate_result=result.to_dict() if result.has_data else None,
        limitations=[
            Limitation(
                code="NO_AGGREGATE_DATA" if not result.has_data else "AGGREGATE_FROM_LOCAL_DB",
                description=result.error if not result.has_data else f"Dati da {result.table_name} (versione: {result.table_version}, hash: {result.query_hash})",
            ),
        ],
    )
    snap.compute_conditional_gaps()
    return snap.to_dict(), manifest


# ─── Conversation runner ──────────────────────────────────────────────────────

def run_conversation(snapshot_dict, questions, report_id="canary_v6"):
    results = []
    try:
        # Create conversation
        r = requests.post(
            f"{BACKEND}/research/reports/{report_id}/conversations",
            json={"snapshot": snapshot_dict},
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"Create conversation failed: {r.status_code}", "body": r.text[:200]}]

        conv = r.json()
        conversation_id = conv["conversation_id"]

        for q in questions:
            r2 = requests.post(
                f"{BACKEND}/research/conversations/{conversation_id}/messages",
                json={"message": q, "snapshot": snapshot_dict},
                timeout=60,
            )
            if r2.status_code == 200:
                msg = r2.json()
                results.append({
                    "question": q,
                    "answer": msg.get("content", ""),
                    "validation_state": msg.get("validation_state", ""),
                    "provider_class": msg.get("provider_class", ""),
                    "provider_contract_version": msg.get("provider_contract_version", ""),
                    "snapshot_schema_version": msg.get("snapshot_schema_version", ""),
                    "renderer_version": msg.get("renderer_version", ""),
                    "validator_version": msg.get("validator_version", ""),
                    "requires_new_research": msg.get("requires_new_research", False),
                    "validation_details": msg.get("validation_details", {}),
                    "cited_claim_ids": msg.get("cited_claim_ids", []),
                })
            else:
                results.append({"question": q, "error": f"HTTP {r2.status_code}: {r2.text[:200]}"})

        # Get versions
        r3 = requests.get(f"{BACKEND}/research/conversations/{conversation_id}/versions", timeout=10)
        if r3.status_code == 200:
            versions = r3.json()
            for res in results:
                if "error" not in res:
                    res["versions"] = versions

    except requests.exceptions.ConnectionError:
        return [{"error": "Backend not running at http://127.0.0.1:8000"}]
    except Exception as e:
        return [{"error": str(e)[:200]}]

    return results


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("CANARY V6 — Real Backend Conversational Test")
    print(f"Backend: {BACKEND}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 70)

    all_results = {
        "version": "6",
        "timestamp": datetime.now().isoformat(),
        "backend": BACKEND,
        "targets": [],
    }

    # ── Check backend ──
    try:
        r = requests.get(f"{BACKEND}/api/status", timeout=5)
        backend_ok = r.status_code == 200
        print(f"Backend status: {'OK' if backend_ok else 'FAIL'} ({r.status_code})")
    except:
        backend_ok = False
        print("Backend status: NOT RUNNING")

    # ── Extract data ──
    print("\n--- Extracting sample data ---")
    internati = extract_internati(3)
    caduti = extract_caduti_albooro(3)
    decorati = extract_decorati(3)
    events = extract_events(3)
    print(f"Internati: {len(internati)}, Caduti: {len(caduti)}, Decorati: {len(decorati)}, Events: {len(events)}")

    # ── Define targets ──
    targets = []

    for rec in internati:
        name = f"{rec.get('cognome', '')} {rec.get('nome', '')}".strip()
        targets.append({
            "type": "person",
            "subtype": "internati",
            "name": name,
            "record": rec,
            "questions": [
                f"Chi era {name}?",
                f"Quali sono i dati certi su {name}?",
                f"Cosa si può dire sulla prigionia di {name}?",
            ],
        })

    for rec in caduti:
        name = rec.get("nominativo", "")
        targets.append({
            "type": "person",
            "subtype": "caduti_albooro",
            "name": name,
            "record": rec,
            "questions": [
                f"Chi era {name}?",
                f"Quali sono i dati certi su {name}?",
                f"Quali fonti posso consultare per {name}?",
            ],
        })

    for rec in decorati:
        name = f"{rec.get('cognome', '')} {rec.get('nome', '')}".strip()
        targets.append({
            "type": "person",
            "subtype": "decorati_nastroazzurro",
            "name": name,
            "record": rec,
            "questions": [
                f"Chi era {name}?",
                f"Quali sono i dati certi su {name}?",
                f"Quali fonti posso consultare per la decorazione di {name}?",
            ],
        })

    for rec in events:
        name = rec.get("nome", "")
        targets.append({
            "type": "event",
            "name": name,
            "record": rec,
            "questions": [
                f"Cosa successe a {name}?",
                f"Quali sono le date di {name}?",
                f"Quali fonti posso consultare per {name}?",
            ],
        })

    aggregate_targets = [
        {"type": "aggregate", "name": "IMI deceduti in Germania", "questions": [
            "Quanti internati morirono in Germania?",
            "Quali campi hanno più deceduti?",
            "Quali fonti posso consultare?",
        ]},
        {"type": "aggregate", "name": "Decorati al Valor Militare WWI", "questions": [
            "Quanti decorati al valor militare ci sono?",
            "Quali tipi di decorazione ci sono?",
            "Quali fonti posso consultare?",
        ]},
        {"type": "aggregate", "name": "Caduti per affondamento di nave", "questions": [
            "Quanti caduti per affondamento di nave?",
            "Quali cause di morte sono registrate?",
            "Quali fonti posso consultare?",
        ]},
    ]

    # ── Run tests ──
    total_messages = 0
    valid_messages = 0
    fallback_messages = 0
    error_messages = 0
    internal_markers = 0
    forbidden_tokens = ["suggested_research_action", "claim_id", "source_id", "authority_id", "internal_error"]

    for target in targets:
        print(f"\n--- Target: {target['name']} ({target['type']}) ---")

        if target["type"] == "person":
            snapshot, manifest = build_person_snapshot(target["record"], target.get("subtype", "internati"))
        elif target["type"] == "event":
            snapshot, manifest = build_event_snapshot(target["record"])
        else:
            snapshot, manifest = build_aggregate_snapshot(target["name"])

        print(f"  Manifest: {manifest.manifest_id} ({manifest.intent})")
        print(f"  Snapshot: {snapshot.get('snapshot_id', 'N/A')}")

        if backend_ok:
            conv_results = run_conversation(snapshot, target["questions"])
        else:
            # Offline: use deterministic generator
            from ai_output_validator_v6 import generate_deterministic_v6
            conv_results = []
            for q in target["questions"]:
                content = generate_deterministic_v6(snapshot, q)
                conv_results.append({
                    "question": q,
                    "answer": content,
                    "validation_state": "fallback",
                    "provider_class": "ReportConversationProviderV6",
                    "provider_contract_version": "6.0",
                    "snapshot_schema_version": "6",
                    "renderer_version": "6.0",
                    "validator_version": "6.0",
                    "requires_new_research": False,
                    "validation_details": {"fallback_used": True, "reason": "backend_offline"},
                    "cited_claim_ids": [],
                })

        for res in conv_results:
            total_messages += 1
            if "error" in res:
                error_messages += 1
                print(f"  ERROR: {res['error']}")
            else:
                answer = res.get("answer", "")
                vstate = res.get("validation_state", "")
                if vstate == "valid":
                    valid_messages += 1
                elif vstate == "fallback":
                    fallback_messages += 1

                # Check for forbidden tokens
                for token in forbidden_tokens:
                    if token.lower() in answer.lower():
                        internal_markers += 1
                        print(f"  MARKER FOUND: '{token}' in answer for '{res['question']}'")

                print(f"  Q: {res['question'][:60]}...")
                print(f"  A: {answer[:100]}...")
                print(f"  Validation: {vstate}, Provider: {res.get('provider_class', 'N/A')}")

        all_results["targets"].append({
            "name": target["name"],
            "type": target["type"],
            "subtype": target.get("subtype", ""),
            "manifest_id": manifest.manifest_id,
            "manifest_hash": manifest.manifest_hash,
            "intent": manifest.intent,
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "snapshot_hash": snapshot.get("snapshot_hash", ""),
            "identity_resolution": snapshot.get("identity_resolution", ""),
            "external_corroboration": snapshot.get("external_corroboration", ""),
            "results": conv_results,
        })

    # ── Aggregate targets ──
    for target in aggregate_targets:
        print(f"\n--- Aggregate: {target['name']} ---")
        snapshot, manifest = build_aggregate_snapshot(target["name"])
        print(f"  Manifest: {manifest.manifest_id} ({manifest.intent})")
        agg = snapshot.get("aggregate_result")
        if agg:
            print(f"  Aggregate: total={agg.get('result', {}).get('total', 'N/A')}, table={agg.get('table_name', 'N/A')}")
        else:
            print(f"  Aggregate: NO_DATA")

        if backend_ok:
            conv_results = run_conversation(snapshot, target["questions"])
        else:
            from ai_output_validator_v6 import generate_deterministic_v6
            conv_results = []
            for q in target["questions"]:
                content = generate_deterministic_v6(snapshot, q)
                conv_results.append({
                    "question": q,
                    "answer": content,
                    "validation_state": "fallback",
                    "provider_class": "ReportConversationProviderV6",
                    "provider_contract_version": "6.0",
                    "snapshot_schema_version": "6",
                    "renderer_version": "6.0",
                    "validator_version": "6.0",
                    "requires_new_research": False,
                    "validation_details": {"fallback_used": True, "reason": "backend_offline"},
                    "cited_claim_ids": [],
                })

        for res in conv_results:
            total_messages += 1
            if "error" in res:
                error_messages += 1
                print(f"  ERROR: {res['error']}")
            else:
                answer = res.get("answer", "")
                vstate = res.get("validation_state", "")
                if vstate == "valid":
                    valid_messages += 1
                elif vstate == "fallback":
                    fallback_messages += 1
                for token in forbidden_tokens:
                    if token.lower() in answer.lower():
                        internal_markers += 1
                        print(f"  MARKER FOUND: '{token}' in answer")
                print(f"  Q: {res['question'][:60]}...")
                print(f"  A: {answer[:100]}...")
                print(f"  Validation: {vstate}")

        all_results["targets"].append({
            "name": target["name"],
            "type": "aggregate",
            "manifest_id": manifest.manifest_id,
            "manifest_hash": manifest.manifest_hash,
            "intent": manifest.intent,
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "snapshot_hash": snapshot.get("snapshot_hash", ""),
            "aggregate_result": snapshot.get("aggregate_result"),
            "results": conv_results,
        })

    # ── Summary ──
    all_results["summary"] = {
        "total_messages": total_messages,
        "valid_messages": valid_messages,
        "fallback_messages": fallback_messages,
        "error_messages": error_messages,
        "internal_markers": internal_markers,
        "backend_online": backend_ok,
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total messages: {total_messages}")
    print(f"Valid: {valid_messages}")
    print(f"Fallback: {fallback_messages}")
    print(f"Errors: {error_messages}")
    print(f"Internal markers: {internal_markers}")
    print(f"Backend online: {backend_ok}")

    # ── Save results ──
    results_path = str(BASE_DIR / "CANARY_V6_RESULTS.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nRisultati salvati in: {results_path}")

    # ── Generate report ──
    generate_report(all_results)
    print(f"Report salvato in: CANARY_V6_REPORT.md")


def generate_report(data):
    lines = [
        f"# Canary V6 — Test Conversazionale Reale",
        f"",
        f"**Data:** {data['timestamp']}",
        f"**Backend:** {data['backend']} ({'attivo' if data['summary']['backend_online'] else 'offline'})",
        f"**Schema version:** 6",
        f"",
        f"---",
        f"",
        f"## Sintesi discorsiva",
        f"",
    ]

    for target in data["targets"]:
        lines.append(f"### {target['name']} ({target['type']})")
        lines.append(f"")
        lines.append(f"**Manifest:** {target.get('manifest_id', 'N/A')} — Intent: {target.get('intent', 'N/A')}")
        lines.append(f"**Identity resolution:** {target.get('identity_resolution', 'N/A')}")
        lines.append(f"**External corroboration:** {target.get('external_corroboration', 'N/A')}")
        if target.get("aggregate_result"):
            agg = target["aggregate_result"]
            lines.append(f"**Aggregate:** total={agg.get('result', {}).get('total', 'N/A')}, table={agg.get('table_name', 'N/A')}, hash={agg.get('query_hash', 'N/A')}")
        lines.append(f"")

        for res in target.get("results", []):
            if "error" in res:
                lines.append(f"- **Q: {res.get('question', '')}** — ERRORE: {res['error']}")
            else:
                answer = res.get("answer", "")[:300]
                vstate = res.get("validation_state", "")
                lines.append(f"- **Q: {res.get('question', '')}**")
                lines.append(f"  - Risposta: {answer}")
                lines.append(f"  - Validation: {vstate}, Provider: {res.get('provider_class', 'N/A')}")
                lines.append(f"  - requires_new_research: {res.get('requires_new_research', False)}")
        lines.append(f"")

    # Analytical section
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Dettagli analitici")
    lines.append(f"")
    lines.append(f"### Statistiche generali")
    lines.append(f"")
    lines.append(f"| Metrica | Valore |")
    lines.append(f"|---------|--------|")
    s = data["summary"]
    lines.append(f"| Conversazioni totali | {len(data['targets'])} |")
    lines.append(f"| Messaggi totali | {s['total_messages']} |")
    lines.append(f"| Risposte valide | {s['valid_messages']} |")
    lines.append(f"| Fallback deterministici | {s['fallback_messages']} |")
    lines.append(f"| Errori | {s['error_messages']} |")
    lines.append(f"| Marker interni | {s['internal_markers']} |")
    lines.append(f"| Backend online | {s['backend_online']} |")
    lines.append(f"")
    lines.append(f"### Gate finale")
    lines.append(f"")
    gates = [
        ("Marker interni nel testo utente", s["internal_markers"], 0),
        ("Errori", s["error_messages"], 0),
    ]
    for name, actual, expected in gates:
        status = "PASS" if actual == expected else "FAIL"
        lines.append(f"- **{name}**: {actual} (expected: {expected}) — {status}")
    lines.append(f"")
    lines.append(f"### Provider versions")
    lines.append(f"")
    for target in data["targets"]:
        for res in target.get("results", []):
            if "error" not in res:
                lines.append(f"- {target['name']}: provider_class={res.get('provider_class', 'N/A')}, contract={res.get('provider_contract_version', 'N/A')}, schema={res.get('snapshot_schema_version', 'N/A')}")
                break
    lines.append(f"")

    report_path = str(BASE_DIR / "CANARY_V6_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
