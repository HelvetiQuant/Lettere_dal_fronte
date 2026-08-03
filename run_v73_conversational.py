"""V7.3 — Genera risposte conversazionali per 9 casi reali.

Esegue la pipeline V7.3 completa e produce il testo narrativo
per ogni caso, stampandolo a video e salvandolo in JSON.
"""
import sys
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from domain_model_v73 import (
    IdentityCandidate, IdentifierMatch, IdentifierStrength, IdentityStatus,
    Claim, ClaimStatus, Evidence, EvidenceType,
    evaluate_identity, WarPeriod, SemanticRole,
)
from narration_planner_v73 import (
    ClaimSelector, CoveragePlanner, NarrationPlanner,
    SemanticValidator, GlobalValidator,
)
from conversational_renderer_v73 import ConversationalRenderer, ConversationalResponse

DB_MAIN = Path(__file__).parent / "imi_internati.db"

# ─── Test cases ─────────────────────────────────────────────────────────────

PERSON_CASES = [
    {"id": 2344, "query": "ALTA Antonio"},
    {"id": 2357, "query": "ARMANNO Luigi A"},
    {"id": 2360, "query": "AMAROTTI Enrico"},
    {"id": 2353, "query": "ANFOSSO Carlo"},
    {"id": 2350, "query": "ARTI Saverio"},
    {"id": 2356, "query": "ANVISIO Remo"},
]

EVENT_CASES = [
    {"stable_id": "evt_0051", "query": "Battaglia del Monte Ortigara"},
    {"stable_id": "evt_0020", "query": "Battaglia di Vittorio Veneto"},
    {"stable_id": "evt_0061", "query": "Guerra bianca"},
]


# ─── Pipeline ───────────────────────────────────────────────────────────────

def run_person(query, internato_id):
    """Run full V7.3 pipeline for a PERSON and return conversational response."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM internati WHERE id = ?", (internato_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    db_record = dict(row)

    # Identity
    identifiers = [
        IdentifierMatch("nome_cognome", query, IdentifierStrength.WEAK),
    ]
    if db_record.get("luogo_internamento"):
        identifiers.append(IdentifierMatch("luogo_internamento", db_record["luogo_internamento"], IdentifierStrength.MEDIUM))
    if db_record.get("sorte"):
        identifiers.append(IdentifierMatch("sorte", db_record["sorte"], IdentifierStrength.WEAK))

    candidate = IdentityCandidate(query_subject=query, match_identifiers=identifiers)
    candidate.identity_status = evaluate_identity(candidate)

    # Claims
    claims = []
    if db_record.get("luogo_internamento"):
        claims.append(Claim(
            predicate="interned_at", object_value=db_record["luogo_internamento"],
            candidate_id=candidate.candidate_id, status=ClaimStatus.PROBABLE,
            usable_as_evidence=True, semantic_role=SemanticRole.DETENTION_PLACE.value,
        ))
    if db_record.get("sorte"):
        pred = "died_at" if db_record["sorte"] == "deceduto" else "liberated_from"
        claims.append(Claim(
            predicate=pred, object_value=db_record["sorte"],
            candidate_id=candidate.candidate_id, status=ClaimStatus.PROBABLE,
            usable_as_evidence=True,
        ))
    if db_record.get("luogo_nascita"):
        claims.append(Claim(
            predicate="born_in", object_value=db_record["luogo_nascita"],
            candidate_id=candidate.candidate_id, status=ClaimStatus.CANDIDATE,
            usable_as_evidence=True, semantic_role=SemanticRole.BIRTH_PLACE.value,
        ))
    if db_record.get("grado"):
        claims.append(Claim(
            predicate="served_in", object_value=db_record["grado"],
            candidate_id=candidate.candidate_id, status=ClaimStatus.CANDIDATE,
            usable_as_evidence=True,
        ))

    # Evidence
    evidence = []
    for claim in claims:
        ev = Evidence(
            candidate_id=candidate.candidate_id,
            evidence_type=EvidenceType.PERSON_EVIDENCE,
            evidence_role="supports",
            source_authority=0.7, artifact_directness=0.8, extraction_confidence=0.9,
            identity_match_confidence=0.6 if candidate.strong_count == 0 else 0.9,
            semantic_confidence=0.8, temporal_compatibility=1.0,
            geographical_compatibility=0.8, source_independence=0.5,
            family_id="db_internati",
        )
        claim.evidence_ids.append(ev.evidence_id)
        evidence.append(ev)

    # Selection
    selector = ClaimSelector()
    selected = selector.select_claims(claims, evidence, [candidate])

    # Coverage
    planner = CoveragePlanner()
    coverage = planner.evaluate_person_coverage(selected)

    # Narration plan
    narr_planner = NarrationPlanner()
    plan = narr_planner.build_person_plan(selected, coverage, selector.identity_warnings)

    # Render
    renderer = ConversationalRenderer()
    response = renderer.render_person(query, selected, plan, coverage, candidate, db_record)

    return response


def run_event(query, stable_id):
    """Run full V7.3 pipeline for an EVENT and return conversational response."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM canonical_event_registry WHERE stable_id = ?", (stable_id,))
    evt = cur.fetchone()
    conn.close()

    if not evt:
        return None
    evt = dict(evt)

    # Create event claims
    claims = []
    if evt.get("description"):
        claims.append(Claim(predicate="event_context", object_value=evt["description"][:200],
                            status=ClaimStatus.PROBABLE, usable_as_evidence=True))
    if evt.get("general_location"):
        claims.append(Claim(predicate="event_location", object_value=evt["general_location"],
                            status=ClaimStatus.PROBABLE, usable_as_evidence=True))
    claims.append(Claim(predicate="event_duration", object_value=f"{evt['data_inizio']} - {evt['data_fine']}",
                        status=ClaimStatus.PROBABLE, usable_as_evidence=True))

    # Dummy identity for events
    candidate = IdentityCandidate(
        query_subject=evt["name"],
        match_identifiers=[IdentifierMatch("event_name", evt["name"], IdentifierStrength.STRONG)],
    )
    candidate.identity_status = IdentityStatus.RESOLVED
    for c in claims:
        c.candidate_id = candidate.candidate_id

    # Evidence
    evidence = []
    for claim in claims:
        ev = Evidence(
            evidence_type=EvidenceType.EVENT_CONTEXT, evidence_role="supports",
            source_authority=0.9, artifact_directness=0.8, extraction_confidence=0.85,
            identity_match_confidence=1.0, semantic_confidence=0.9,
            temporal_compatibility=1.0, geographical_compatibility=0.9,
            source_independence=0.7, family_id="canonical_event_registry",
        )
        claim.evidence_ids.append(ev.evidence_id)
        evidence.append(ev)

    # Selection
    selector = ClaimSelector()
    selected = selector.select_claims(claims, evidence, [candidate])

    # Coverage
    planner = CoveragePlanner()
    coverage = planner.evaluate_event_coverage(selected)

    # Narration plan
    narr_planner = NarrationPlanner()
    plan = narr_planner.build_event_plan(selected, coverage, [])

    # Render
    renderer = ConversationalRenderer()
    response = renderer.render_event(query, evt, selected, plan, coverage)

    return response


# ─── Main ───────────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("V7.3 RISPOSTE CONVERSAZIONALI — 9 CASI REALI")
print("=" * 80)

all_responses = []

# PERSON cases
for case in PERSON_CASES:
    print(f"\n\n{'#' * 80}")
    print(f"# PERSON: {case['query']}")
    print(f"{'#' * 80}")
    response = run_person(case["query"], case["id"])
    if response:
        print(f"\n{response.text}")
        print(f"\n--- Metadata ---")
        print(f"Identity: {response.identity_status}")
        print(f"Coverage: {response.coverage_score:.0%}")
        print(f"Claims: {response.claim_count}, Sources: {response.source_count}")
        print(f"Certainty: {response.certainty_summary}")
        if response.needs_followup:
            print(f"Followup needed: {response.followup_question}")
        all_responses.append(response.to_dict())
    else:
        print(f"ERROR: No data found for id={case['id']}")

# EVENT cases
for case in EVENT_CASES:
    print(f"\n\n{'#' * 80}")
    print(f"# EVENT: {case['query']}")
    print(f"{'#' * 80}")
    response = run_event(case["query"], case["stable_id"])
    if response:
        print(f"\n{response.text}")
        print(f"\n--- Metadata ---")
        print(f"Coverage: {response.coverage_score:.0%}")
        print(f"Claims: {response.claim_count}, Sources: {response.source_count}")
        print(f"Certainty: {response.certainty_summary}")
        if response.needs_followup:
            print(f"Followup needed: {response.followup_question}")
        all_responses.append(response.to_dict())
    else:
        print(f"ERROR: No event found for {case['stable_id']}")

# Save
output = {
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "version": "7.3.0",
    "total": len(all_responses),
    "responses": all_responses,
}
output_path = Path(__file__).parent / "V73_CONVERSATIONAL_RESPONSES.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n\nRisposte salvate in {output_path}")
