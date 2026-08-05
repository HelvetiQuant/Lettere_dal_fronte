"""Canary V5 — test conversazionale reale su 3 nomi per DB, 3 eventi, 3 fatti.

Usa il backend reale su http://127.0.0.1:8000.
Per ogni target:
1. Ricerca nel backend
2. Costruzione EvidenceSnapshotV5 dai risultati
3. Report conversazionale (3 follow-up)
4. Validazione semantica

Output: report discorsivo + dettagli analitici.
"""
import json
import hashlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

BACKEND = "http://127.0.0.1:8000"
OUTPUT_FILE = Path(__file__).parent / "CANARY_V5_REAL_RESULTS.json"
REPORT_FILE = Path(__file__).parent / "CANARY_V5_REAL_REPORT.md"

# ─── Targets ─────────────────────────────────────────────────────────────────

TARGETS_NOMI = [
    {
        "category": "internati",
        "id": 2433,
        "cognome": "ALFORI",
        "nome": "Divino",
        "luogo_nascita": "Trento",
        "grado": "Serg.Magg",
        "luogo_internamento": "Amburgo",
        "sorte": "deceduto",
        "conflict": "WWII",
        "questions": [
            "Chi era ALFORI Divino?",
            "Dove era internato e cosa gli successe?",
            "Quali fonti possiamo consultare per saperne di piu?",
        ],
    },
    {
        "category": "internati",
        "id": 14286,
        "cognome": "L. NGELLA",
        "nome": "Maresc. Magg.",
        "luogo_nascita": "Roma",
        "grado": "Maresciallo Maggiore",
        "luogo_internamento": "ospedale",
        "sorte": "deceduto",
        "conflict": "WWII",
        "questions": [
            "Cosa sappiamo di questo maresciallo?",
            "Perche era in ospedale?",
            "Ci sono omonimi da escludere?",
        ],
    },
    {
        "category": "internati",
        "id": 21284,
        "cognome": "TURCONI",
        "nome": "Paolo",
        "luogo_nascita": "Como",
        "grado": "Serg.",
        "luogo_internamento": "Madenburg",
        "sorte": "deceduto",
        "conflict": "WWII",
        "questions": [
            "Chi era TURCONI Paolo?",
            "Dove si trova Madenburg?",
            "Quali sono i prossimi passi di ricerca?",
        ],
    },
    {
        "category": "caduti_albooro",
        "id": 1,
        "nominativo": "ABATE MARIO ANTONIO",
        "paternita": "FRANCESCO",
        "classe": "1896",
        "comune_attuale": "Chieti",
        "grado": "Soldato",
        "reparto": "Comando Generale Genio",
        "anno_morte": "1919",
        "luogo_morte": "Trieste",
        "causa_morte": "Infortunio",
        "conflict": "WWI",
        "questions": [
            "Chi era ABATE MARIO ANTONIO?",
            "Come mori a Trieste nel 1919?",
            "Quali fonti militari possiamo verificare?",
        ],
    },
    {
        "category": "caduti_albooro",
        "id": 2,
        "nominativo": "ABBATTISTA ATTILIO",
        "paternita": "SALVATORE",
        "classe": "1896",
        "comune_attuale": "Fossacesia",
        "grado": "Sotto capo meccanico",
        "reparto": "RR. equipaggi",
        "anno_morte": "1916",
        "luogo_morte": "-",
        "causa_morte": "Affondamento Di Nave",
        "conflict": "WWI",
        "questions": [
            "Chi era ABBATTISTA ATTILIO?",
            "In quale nave perse la vita?",
            "Quali archivi navali possiamo consultare?",
        ],
    },
    {
        "category": "caduti_albooro",
        "id": 3,
        "nominativo": "ABBIUSO DOMENICO",
        "paternita": "ANTONIO",
        "classe": "1895",
        "comune_attuale": "San Martino in Pensilis",
        "grado": "Soldato",
        "reparto": "12 Reggimento Fanteria",
        "anno_morte": "1916",
        "luogo_morte": "Alessandria",
        "causa_morte": "Ferite Riportate in Combattimento",
        "conflict": "WWI",
        "questions": [
            "Chi era ABBIUSO DOMENICO?",
            "Perche mori ad Alessandria?",
            "Il 12 Reggimento Fanteria ha diari di guerra?",
        ],
    },
    {
        "category": "decorati",
        "id": 1,
        "cognome": "A",
        "nome": "GIOVANNI",
        "anno_decorazione": "1918",
        "tipo_decorazione": "Promozione per Merito di Guerra",
        "arma": "Esercito",
        "conflict": "WWI",
        "questions": [
            "Chi era il decorato A GIOVANNI?",
            "Cosa significa Promozione per Merito di Guerra?",
            "Come possiamo verificare questa decorazione?",
        ],
    },
    {
        "category": "decorati",
        "id": 2,
        "cognome": "A RONCH",
        "nome": "GIOVANNI",
        "anno_decorazione": "1941",
        "tipo_decorazione": "Croce di Guerra al Valor Militare",
        "arma": "Esercito",
        "conflict": "WWII",
        "questions": [
            "Chi era A RONCH GIOVANNI?",
            "Perche fu decorato con Croce di Guerra nel 1941?",
            "Quali fonti confermano questa decorazione?",
        ],
    },
    {
        "category": "decorati",
        "id": 3,
        "cognome": "A-PRATO",
        "nome": "SILVIO",
        "anno_decorazione": "1922",
        "tipo_decorazione": "Medaglia di Bronzo",
        "arma": "Esercito",
        "conflict": "WWI",
        "questions": [
            "Chi era A-PRATO SILVIO?",
            "Perche la decorazione e del 1922 e non durante la guerra?",
            "Dove possiamo trovare l'atto di concessione?",
        ],
    },
]

TARGETS_EVENTI = [
    {
        "id": 16,
        "nome": "Battaglia di Caporetto",
        "data_inizio": "1917-10-24",
        "data_fine": "1917-11-12",
        "luogo": "Isonzo, settore Tolmino-Caporetto",
        "descrizione": "Sconfitta italiana 24 ott - 12 nov 1917. Rottura del fronte Isonzo, ritirata al Piave.",
        "conflict": "WWI",
        "questions": [
            "Cosa successe a Caporetto nell'ottobre 1917?",
            "Quanti soldati italiani furono fatti prigionieri?",
            "Quali fonti d'archivio documentano la ritirata?",
        ],
    },
    {
        "id": 17,
        "nome": "Battaglie dell'Isonzo",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-09-12",
        "luogo": "Fronte Isonzo, Carso",
        "descrizione": "12 offensive italiane sul fiume Isonzo giun-1915 / set-1917.",
        "conflict": "WWI",
        "questions": [
            "Quante battaglie dell'Isonzo ci furono?",
            "Quali unita italiane combatterono sull'Isonzo?",
            "Dove si trovano i diari di reparto?",
        ],
    },
    {
        "id": 18,
        "nome": "Battaglia del Carso",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-11-12",
        "luogo": "Altopiano del Carso",
        "descrizione": "Combattimenti sul Carso durante tutte le battaglie dell'Isonzo.",
        "conflict": "WWI",
        "questions": [
            "Cosa fu la battaglia del Carso?",
            "Quali reparti combatterono sul Carso?",
            "Esistono fonti fotografiche del Carso?",
        ],
    },
]

TARGETS_FATTI = [
    {
        "fact": "IMI deceduti in Germania",
        "query": "internati deceduti Germania",
        "questions": [
            "Quanti internati militari italiani morirono in Germania?",
            "In quali campi morirono piu soldati?",
            "Dove sono i registri di sepoltura?",
        ],
    },
    {
        "fact": "Decorati al Valor Militare WWI",
        "query": "decorati valor militare prima guerra mondiale",
        "questions": [
            "Quanti italiani furono decorati al valor militare nella WWI?",
            "Quali tipi di decorazioni esistevano?",
            "Dove sono gli atti di concessione?",
        ],
    },
    {
        "fact": "Caduti per affondamento di nave",
        "query": "caduti affondamento nave militare",
        "questions": [
            "Quali navi militari italiane furono affondate nella WWI?",
            "Quanti marinai perirono?",
            "Dove sono i registri della Marina Militare?",
        ],
    },
]


def build_snapshot_v5_from_target(target: dict, search_results: list = None) -> dict:
    """Build a V5 snapshot dict from target data and optional search results."""
    from evidence_snapshot_v5 import EvidenceSnapshotV5
    from research_next_step_planner import plan_next_steps

    category = target.get("category", "unknown")
    conflict = target.get("conflict", "WWI")

    # Build target identity
    if "cognome" in target and "nome" in target:
        surname = target["cognome"]
        given = target["nome"]
        display_name = f"{surname} {given}"
    elif "nominativo" in target:
        parts = target["nominativo"].split()
        surname = parts[0] if parts else ""
        given = " ".join(parts[1:]) if len(parts) > 1 else ""
        display_name = target["nominativo"]
    else:
        surname = ""
        given = ""
        display_name = target.get("nome", target.get("fact", "unknown"))

    # Build asserted claims from target data
    asserted = []
    claim_id_counter = 0
    def next_claim_id():
        nonlocal claim_id_counter
        claim_id_counter += 1
        return f"cl_{claim_id_counter:03d}"

    field_map = {
        "luogo_nascita": "birth_place",
        "data_nascita": "birth_date",
        "grado": "rank",
        "reparto": "unit",
        "luogo_internamento": "internment_place",
        "sorte": "fate",
        "matricola": "service_number",
        "luogo_cattura": "capture_place",
        "data_cattura": "capture_date",
        "anno_morte": "death_year",
        "luogo_morte": "death_place",
        "causa_morte": "death_cause",
        "paternita": "paternity",
        "classe": "draft_class",
        "comune_attuale": "municipality",
        "anno_decorazione": "decoration_year",
        "tipo_decorazione": "decoration_type",
        "arma": "branch",
    }

    for src_field, claim_field in field_map.items():
        val = target.get(src_field)
        if val and str(val).strip():
            asserted.append({
                "claim_id": next_claim_id(),
                "field_name": claim_field,
                "object_value": str(val),
                "source": "origin_record",
                "confidence": 0.9 if category != "decorati" else 0.7,
            })

    # Origin presence
    origin_presence = "PRESENT_LOCAL"
    origin_provenance = "UNVERIFIED"

    # Identity resolution
    identity_resolution = "UNRESOLVED"
    if surname and given and target.get("luogo_nascita"):
        identity_resolution = "PARTIAL"

    # External corroboration
    external_corroboration = "NONE"
    if search_results:
        accepted = [r for r in search_results if r.get("score", 0) > 0.5]
        if accepted:
            external_corroboration = "PARTIAL"

    # Next steps
    next_steps = plan_next_steps(
        {"conflict": conflict, "surname": surname, "given_names": [given] if given else []},
        {"presence": origin_presence, "provenance": origin_provenance},
        identity_resolution,
        external_corroboration,
    )

    # Build snapshot
    snap = EvidenceSnapshotV5(
        target={
            "target_id": f"target_{category}_{target.get('id', 'unknown')}",
            "surname": surname,
            "given_names": [given] if given else [],
            "display_name": display_name,
            "source_order": "SURNAME_GIVEN",
            "conflict": conflict,
            "assertions": asserted,
        },
        origin={
            "presence": origin_presence,
            "provenance": origin_provenance,
            "source_id": f"origin_{target.get('id', 'unknown')}",
            "supported_claim_ids": [],
        },
        identity_resolution=identity_resolution,
        external_corroboration=external_corroboration,
        asserted_claims=asserted,
        next_steps=next_steps,
        limitations=["NO_LIVE_WEB_SEARCH"] if not search_results else [],
        research_mode="LOCAL_WITH_MODEL" if os.environ.get("OPENAI_API_KEY") else "LOCAL_ONLY",
    )

    snap._compute_conditional_gaps()

    return snap.to_dict()


def build_snapshot_v5_from_event(event: dict) -> dict:
    """Build a V5 snapshot dict from an event."""
    from evidence_snapshot_v5 import EvidenceSnapshotV5
    from research_next_step_planner import plan_next_steps

    asserted = []
    if event.get("data_inizio"):
        asserted.append({"claim_id": "cl_001", "field_name": "start_date", "object_value": event["data_inizio"], "source": "event_db", "confidence": 0.95})
    if event.get("data_fine"):
        asserted.append({"claim_id": "cl_002", "field_name": "end_date", "object_value": event["data_fine"], "source": "event_db", "confidence": 0.95})
    if event.get("luogo"):
        asserted.append({"claim_id": "cl_003", "field_name": "location", "object_value": event["luogo"], "source": "event_db", "confidence": 0.9})
    if event.get("descrizione"):
        asserted.append({"claim_id": "cl_004", "field_name": "description", "object_value": event["descrizione"], "source": "event_db", "confidence": 0.85})

    next_steps = plan_next_steps(
        {"conflict": event.get("conflict", "WWI"), "surname": "", "given_names": [], "display_name": event["nome"]},
        {"presence": "PRESENT_LOCAL", "provenance": "VERIFIED"},
        "RESOLVED",
        "NONE",
    )

    snap = EvidenceSnapshotV5(
        target={
            "target_id": f"event_{event['id']}",
            "surname": "",
            "given_names": [],
            "display_name": event["nome"],
            "source_order": "SURNAME_GIVEN",
            "conflict": event.get("conflict", "WWI"),
            "assertions": asserted,
        },
        origin={
            "presence": "PRESENT_LOCAL",
            "provenance": "VERIFIED",
            "source_id": f"eventi_1gm_{event['id']}",
            "supported_claim_ids": [c["claim_id"] for c in asserted],
        },
        identity_resolution="RESOLVED",
        external_corroboration="NONE",
        asserted_claims=asserted,
        origin_supported_claims=asserted,
        next_steps=next_steps,
        limitations=[],
        research_mode="LOCAL_WITH_MODEL" if os.environ.get("OPENAI_API_KEY") else "LOCAL_ONLY",
    )
    snap._compute_conditional_gaps()
    return snap.to_dict()


def build_snapshot_v5_from_fact(fact: dict, search_results: list = None) -> dict:
    """Build a V5 snapshot from a factual query."""
    from evidence_snapshot_v5 import EvidenceSnapshotV5
    from research_next_step_planner import plan_next_steps

    snap = EvidenceSnapshotV5(
        target={
            "target_id": f"fact_{hashlib.sha256(fact['fact'].encode()).hexdigest()[:8]}",
            "surname": "",
            "given_names": [],
            "display_name": fact["fact"],
            "source_order": "SURNAME_GIVEN",
            "conflict": "BOTH",
            "assertions": [],
        },
        origin={
            "presence": "ABSENT",
            "provenance": "UNVERIFIED",
        },
        identity_resolution="UNRESOLVED",
        external_corroboration="NONE",
        asserted_claims=[],
        next_steps=plan_next_steps(
            {"conflict": "BOTH", "surname": "", "given_names": [], "display_name": fact["fact"]},
            {"presence": "ABSENT", "provenance": "UNVERIFIED"},
            "UNRESOLVED",
            "NONE",
        ),
        limitations=["NO_LIVE_WEB_SEARCH", "AGGREGATE_QUERY"],
        research_mode="LOCAL_WITH_MODEL" if os.environ.get("OPENAI_API_KEY") else "LOCAL_ONLY",
    )
    snap._compute_conditional_gaps()
    return snap.to_dict()


def run_conversation(snapshot: dict, questions: list, report_id: str) -> list:
    """Run a 3-question conversation against the backend."""
    results = []

    # Create conversation
    try:
        r = requests.post(
            f"{BACKEND}/research/reports/{report_id}/conversations",
            json={"snapshot": snapshot},
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"Create conversation failed: {r.status_code}", "detail": r.text[:200]}]

        conv_data = r.json()
        conversation_id = conv_data["conversation_id"]
    except Exception as e:
        return [{"error": f"Create conversation error: {str(e)[:100]}"}]

    # Send messages
    for i, question in enumerate(questions):
        try:
            r = requests.post(
                f"{BACKEND}/research/conversations/{conversation_id}/messages",
                json={"message": question, "snapshot": snapshot},
                timeout=60,
            )
            if r.status_code == 200:
                msg = r.json()
                results.append({
                    "question": question,
                    "answer": msg.get("content", ""),
                    "validation_state": msg.get("validation_state", ""),
                    "cited_claim_ids": msg.get("cited_claim_ids", []),
                    "cited_source_ids": msg.get("cited_source_ids", []),
                })
            else:
                results.append({
                    "question": question,
                    "error": f"HTTP {r.status_code}",
                    "detail": r.text[:200],
                })
        except Exception as e:
            results.append({
                "question": question,
                "error": str(e)[:100],
            })

    return results


def search_backend(query: str) -> list:
    """Search the backend for results."""
    try:
        r = requests.get(
            f"{BACKEND}/api/conv-search",
            params={"q": query},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("soldiers", data.get("results", []))
    except:
        pass
    return []


def main():
    print("=" * 80)
    print("CANARY V5 — TEST CONVERSAZIONALE REALE")
    print(f"Backend: {BACKEND}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    all_results = {
        "timestamp": datetime.now().isoformat(),
        "backend": BACKEND,
        "nomi": [],
        "eventi": [],
        "fatti": [],
    }

    # ─── TEST NOMI ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PARTE 1: NOMI (3 internati, 3 caduti albo oro, 3 decorati)")
    print("=" * 60)

    for target in TARGETS_NOMI:
        category = target["category"]
        if category == "internati":
            display = f"{target['cognome']} {target['nome']} (ID:{target['id']})"
        elif category == "caduti_albooro":
            display = f"{target['nominativo']} (ID:{target['id']})"
        else:
            display = f"{target['cognome']} {target['nome']} (ID:{target['id']})"

        print(f"\n--- {category.upper()}: {display} ---")

        # Search backend
        search_query = target.get("cognome", target.get("nominativo", "")).split()[0]
        search_results = search_backend(search_query)
        print(f"  Ricerca backend: {len(search_results)} risultati")

        # Build snapshot
        snapshot = build_snapshot_v5_from_target(target, search_results)
        report_id = f"canary_v5_{category}_{target['id']}"

        # Run conversation
        print(f"  Avvio conversazione (3 domande)...")
        conv_results = run_conversation(snapshot, target["questions"], report_id)

        for i, cr in enumerate(conv_results):
            if "error" in cr:
                print(f"  Q{i+1}: [ERROR] {cr['error']}")
            else:
                answer_preview = cr.get("answer", "")[:120].replace("\n", " ")
                print(f"  Q{i+1}: [{cr.get('validation_state', '?')}] {answer_preview}...")

        all_results["nomi"].append({
            "target": target,
            "display": display,
            "search_results_count": len(search_results),
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "identity_resolution": snapshot.get("identity_resolution", ""),
            "conditional_gaps_count": len(snapshot.get("conditional_gaps", [])),
            "next_steps_count": len(snapshot.get("next_steps", [])),
            "conversation": conv_results,
        })

    # ─── TEST EVENTI ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PARTE 2: EVENTI (3 dalla Grande Guerra)")
    print("=" * 60)

    for event in TARGETS_EVENTI:
        print(f"\n--- EVENTO: {event['nome']} ---")

        snapshot = build_snapshot_v5_from_event(event)
        report_id = f"canary_v5_event_{event['id']}"

        print(f"  Avvio conversazione (3 domande)...")
        conv_results = run_conversation(snapshot, event["questions"], report_id)

        for i, cr in enumerate(conv_results):
            if "error" in cr:
                print(f"  Q{i+1}: [ERROR] {cr['error']}")
            else:
                answer_preview = cr.get("answer", "")[:120].replace("\n", " ")
                print(f"  Q{i+1}: [{cr.get('validation_state', '?')}] {answer_preview}...")

        all_results["eventi"].append({
            "event": event,
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "conversation": conv_results,
        })

    # ─── TEST FATTI ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PARTE 3: FATTI (3 query aggregate)")
    print("=" * 60)

    for fact in TARGETS_FATTI:
        print(f"\n--- FATTO: {fact['fact']} ---")

        search_results = search_backend(fact["query"])
        print(f"  Ricerca backend: {len(search_results)} risultati")

        snapshot = build_snapshot_v5_from_fact(fact, search_results)
        report_id = f"canary_v5_fact_{hashlib.sha256(fact['fact'].encode()).hexdigest()[:8]}"

        print(f"  Avvio conversazione (3 domande)...")
        conv_results = run_conversation(snapshot, fact["questions"], report_id)

        for i, cr in enumerate(conv_results):
            if "error" in cr:
                print(f"  Q{i+1}: [ERROR] {cr['error']}")
            else:
                answer_preview = cr.get("answer", "")[:120].replace("\n", " ")
                print(f"  Q{i+1}: [{cr.get('validation_state', '?')}] {answer_preview}...")

        all_results["fatti"].append({
            "fact": fact,
            "search_results_count": len(search_results),
            "conversation": conv_results,
        })

    # ─── SALVA RISULTATI ─────────────────────────────────────────────────
    OUTPUT_FILE.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\nRisultati salvati in: {OUTPUT_FILE}")

    # ─── GENERA REPORT DISCORSIVO ────────────────────────────────────────
    generate_report(all_results)
    print(f"Report discorsivo salvato in: {REPORT_FILE}")


def generate_report(results: dict):
    """Generate a discursive report from results."""
    lines = []
    lines.append("# Canary V5 — Test Conversazionale Reale")
    lines.append(f"\n**Data:** {results['timestamp']}")
    lines.append(f"**Backend:** {results['backend']}")
    lines.append("")

    # ─── PARTE DISCORSIVA ────────────────────────────────────────────────
    lines.append("## Sintesi discorsiva")
    lines.append("")

    # Nomi
    lines.append("### Nomi ricercati")
    lines.append("")
    for item in results["nomi"]:
        display = item["display"]
        cat = item["target"]["category"]
        id_res = item["identity_resolution"]
        gaps = item["conditional_gaps_count"]
        steps = item["next_steps_count"]
        search_count = item["search_results_count"]

        lines.append(f"**{display}** ({cat})")
        lines.append(f"  - Risultati ricerca backend: {search_count}")
        lines.append(f"  - Risoluzione identitaria: {id_res}")
        lines.append(f"  - Gap condizionali: {gaps}")
        lines.append(f"  - Prossimi passi suggeriti: {steps}")

        for cr in item["conversation"]:
            if "error" in cr:
                lines.append(f"  - Domanda: *{cr['question']}*")
                lines.append(f"    - **ERRORE:** {cr['error']}")
            else:
                lines.append(f"  - Domanda: *{cr['question']}*")
                lines.append(f"    - Stato: {cr.get('validation_state', '?')}")
                answer = cr.get("answer", "")
                # Truncate very long answers
                if len(answer) > 500:
                    answer = answer[:500] + " [...]"
                lines.append(f"    - Risposta: {answer}")
        lines.append("")

    # Eventi
    lines.append("### Eventi storici")
    lines.append("")
    for item in results["eventi"]:
        ev = item["event"]
        lines.append(f"**{ev['nome']}** ({ev['data_inizio']} – {ev['data_fine']})")
        lines.append(f"  - Luogo: {ev['luogo']}")
        lines.append(f"  - Descrizione: {ev['descrizione']}")

        for cr in item["conversation"]:
            if "error" in cr:
                lines.append(f"  - Domanda: *{cr['question']}*")
                lines.append(f"    - **ERRORE:** {cr['error']}")
            else:
                lines.append(f"  - Domanda: *{cr['question']}*")
                lines.append(f"    - Stato: {cr.get('validation_state', '?')}")
                answer = cr.get("answer", "")
                if len(answer) > 500:
                    answer = answer[:500] + " [...]"
                lines.append(f"    - Risposta: {answer}")
        lines.append("")

    # Fatti
    lines.append("### Fatti aggregati")
    lines.append("")
    for item in results["fatti"]:
        fact = item["fact"]
        lines.append(f"**{fact['fact']}**")
        lines.append(f"  - Risultati ricerca: {item['search_results_count']}")

        for cr in item["conversation"]:
            if "error" in cr:
                lines.append(f"  - Domanda: *{cr['question']}*")
                lines.append(f"    - **ERRORE:** {cr['error']}")
            else:
                lines.append(f"  - Domanda: *{cr['question']}*")
                lines.append(f"    - Stato: {cr.get('validation_state', '?')}")
                answer = cr.get("answer", "")
                if len(answer) > 500:
                    answer = answer[:500] + " [...]"
                lines.append(f"    - Risposta: {answer}")
        lines.append("")

    # ─── DETTAGLI ANALITICI ──────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Dettagli analitici")
    lines.append("")

    # Summary stats
    total_conversations = 0
    total_messages = 0
    total_errors = 0
    total_valid = 0
    total_fallback = 0

    for section in ["nomi", "eventi", "fatti"]:
        for item in results[section]:
            total_conversations += 1
            for cr in item["conversation"]:
                total_messages += 1
                if "error" in cr:
                    total_errors += 1
                else:
                    state = cr.get("validation_state", "")
                    if state == "valid":
                        total_valid += 1
                    elif state == "fallback":
                        total_fallback += 1

    lines.append("### Statistiche generali")
    lines.append(f"- Conversazioni totali: {total_conversations}")
    lines.append(f"- Messaggi totali: {total_messages}")
    lines.append(f"- Risposte valide: {total_valid}")
    lines.append(f"- Fallback deterministici: {total_fallback}")
    lines.append(f"- Errori: {total_errors}")
    lines.append("")

    # Per-target details
    lines.append("### Dettagli per target")
    lines.append("")
    for section_name, section_label in [("nomi", "Nomi"), ("eventi", "Eventi"), ("fatti", "Fatti")]:
        lines.append(f"#### {section_label}")
        lines.append("")
        for item in results[section_name]:
            if section_name == "nomi":
                title = item["display"]
            elif section_name == "eventi":
                title = item["event"]["nome"]
            else:
                title = item["fact"]["fact"]

            lines.append(f"**{title}**")
            lines.append(f"- Snapshot: {item.get('snapshot_id', 'N/A')}")
            if "identity_resolution" in item:
                lines.append(f"- Identity resolution: {item['identity_resolution']}")
                lines.append(f"- Conditional gaps: {item['conditional_gaps_count']}")
                lines.append(f"- Next steps: {item['next_steps_count']}")
            if "search_results_count" in item:
                lines.append(f"- Search results: {item['search_results_count']}")

            for i, cr in enumerate(item["conversation"]):
                q = cr.get("question", "")
                if "error" in cr:
                    lines.append(f"- Q{i+1}: {q} → **ERRORE: {cr['error']}**")
                else:
                    state = cr.get("validation_state", "?")
                    cited_claims = cr.get("cited_claim_ids", [])
                    cited_sources = cr.get("cited_source_ids", [])
                    lines.append(f"- Q{i+1}: {q}")
                    lines.append(f"  - validation: {state}")
                    if cited_claims:
                        lines.append(f"  - cited_claims: {cited_claims}")
                    if cited_sources:
                        lines.append(f"  - cited_sources: {cited_sources}")
                    answer = cr.get("answer", "")
                    if len(answer) > 300:
                        answer = answer[:300] + " [...]"
                    lines.append(f"  - answer: {answer}")
            lines.append("")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
