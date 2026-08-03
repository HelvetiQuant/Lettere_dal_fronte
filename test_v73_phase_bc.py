"""V7.3 Phase B/C Tests — quarantine, domain model, text matching, barriers.

Tests cover:
1. Quarantine migration (schema, columns, status)
2. Event registry (Isonzo date correction, war classification)
3. Domain model (identity resolution, claim lifecycle)
4. Text matching (word boundaries, specificity, OCR variants)
5. Temporal barriers (WWI/WWII, date roles)
6. Geographic barriers (semantic roles, burial != event)
7. Combined match evaluation
"""
import sys
import os
import sqlite3
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from domain_model_v73 import (
    IdentityCandidate, IdentifierMatch, IdentifierStrength, IdentityStatus,
    Claim, ClaimStatus, ClaimType, Evidence, EvidenceType,
    evaluate_identity, can_combine_claims,
    SourceArtifact, Observation, Entity, Relation, RelationStatus,
    ReviewDecision, EventRegistryEntry, WarPeriod,
)
from text_matching_v73 import (
    normalize_text, tokenize, matches_word_boundary, matches_any_keyword,
    classify_keyword_specificity, has_sufficient_specificity,
    parse_name, names_compatible, generate_ocr_variants,
    match_aliases, has_specific_alias_match,
)
from barriers_v73 import (
    DateRole, TemporalCompatibility, GeographicCompatibility,
    check_temporal_compatibility, check_geographic_compatibility,
    evaluate_match, MatchEvaluation,
)

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"

passed = 0
failed = 0
errors = []


def test(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} — {detail}")


# ─── 1. Quarantine migration ────────────────────────────────────────────────

print("\n=== 1. Quarantine Migration ===")

# Check event_links columns
conn_evt = sqlite3.connect(str(DB_EVENTS))
cur = conn_evt.cursor()
for col in ["origin", "usable_as_evidence", "war_period", "semantic_role", "quarantined_at", "quarantine_reason"]:
    cur.execute(f"PRAGMA table_info(event_links)")
    cols = [r[1] for r in cur.fetchall()]
    test(f"event_links has column {col}", col in cols)

# Check all event_links are quarantined
cur.execute("SELECT COUNT(*) FROM event_links WHERE usable_as_evidence = 0 AND status = 'CANDIDATE'")
quarantined = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM event_links")
total = cur.fetchone()[0]
test("All event_links quarantined", quarantined == total, f"{quarantined}/{total}")

# Check record_links columns
conn_main = sqlite3.connect(str(DB_MAIN))
cur = conn_main.cursor()
for col in ["origin", "usable_as_evidence", "war_period", "semantic_role", "quarantined_at", "quarantine_reason"]:
    cur.execute(f"PRAGMA table_info(record_links)")
    cols = [r[1] for r in cur.fetchall()]
    test(f"record_links has column {col}", col in cols)

# Check all record_links are quarantined
cur.execute("SELECT COUNT(*) FROM record_links WHERE usable_as_evidence = 0 AND status = 'CANDIDATE'")
quarantined = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM record_links")
total = cur.fetchone()[0]
test("All record_links quarantined", quarantined == total, f"{quarantined}/{total}")

# Check canonical tables exist
canonical_tables = [
    "canonical_source_artifacts", "canonical_source_families",
    "canonical_observations", "canonical_entities",
    "canonical_identity_candidates", "canonical_evidence",
    "canonical_claims", "canonical_relations",
    "canonical_review_decisions", "canonical_research_snapshots",
    "canonical_sync_outbox", "canonical_event_registry",
]
for t in canonical_tables:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
    test(f"Table {t} exists", cur.fetchone() is not None)

conn_evt.close()
conn_main.close()


# ─── 2. Event Registry ──────────────────────────────────────────────────────

print("\n=== 2. Event Registry ===")

conn_main = sqlite3.connect(str(DB_MAIN))
conn_main.row_factory = sqlite3.Row
cur = conn_main.cursor()

# Check 49 events populated
cur.execute("SELECT COUNT(*) FROM canonical_event_registry")
count = cur.fetchone()[0]
test("49 events in registry", count == 49, f"got {count}")

# Check Isonzo date correction
cur.execute("SELECT data_fine FROM canonical_event_registry WHERE stable_id = 'evt_0017'")
row = cur.fetchone()
test("Isonzo data_fine corrected to 1917-11-12", row and row["data_fine"] == "1917-11-12", f"got {row['data_fine'] if row else 'None'}")

# Check war classification
cur.execute("SELECT war, COUNT(*) as cnt FROM canonical_event_registry GROUP BY war")
war_counts = {r["war"]: r["cnt"] for r in cur.fetchall()}
test("WWI events = 42", war_counts.get("WWI", 0) == 42, f"got {war_counts}")
test("WWII events = 7", war_counts.get("WWII", 0) == 7, f"got {war_counts}")

# Check provenance recorded
cur.execute("SELECT source_provenance_json FROM canonical_event_registry WHERE stable_id = 'evt_0017'")
row = cur.fetchone()
if row:
    prov = json.loads(row["source_provenance_json"])
    test("Isonzo provenance has source", "source" in prov and "Ufficio Storico" in prov["source"])
    test("Isonzo provenance has correction_reason", "correction_reason" in prov)
else:
    test("Isonzo provenance exists", False, "no row")

# Check Caporetto offensive direction
cur.execute("SELECT source_provenance_json FROM canonical_event_registry WHERE stable_id = 'evt_0016'")
row = cur.fetchone()
if row:
    prov = json.loads(row["source_provenance_json"])
    test("Caporetto marked as Austro-Hungarian/German", prov.get("offensive_direction") == "AUSTRO_HUNGARIAN_GERMAN")
else:
    test("Caporetto provenance exists", False, "no row")

conn_main.close()


# ─── 3. Domain Model ────────────────────────────────────────────────────────

print("\n=== 3. Domain Model ===")

# Identity resolution: name only -> NEEDS_REVIEW
c1 = IdentityCandidate(
    query_subject="Mario Rossi",
    match_identifiers=[IdentifierMatch(identifier_type="nome_cognome", value="Mario Rossi", strength=IdentifierStrength.WEAK)],
)
status1 = evaluate_identity(c1)
test("Name only -> NEEDS_REVIEW", status1 == IdentityStatus.NEEDS_REVIEW, f"got {status1}")

# Identity resolution: strong identifier -> RESOLVED
c2 = IdentityCandidate(
    query_subject="Mario Rossi",
    match_identifiers=[
        IdentifierMatch(identifier_type="nome_cognome", value="Mario Rossi", strength=IdentifierStrength.WEAK),
        IdentifierMatch(identifier_type="data_nascita_complete", value="1912-01-09", strength=IdentifierStrength.STRONG),
    ],
)
status2 = evaluate_identity(c2)
test("Name + birth date -> RESOLVED", status2 == IdentityStatus.RESOLVED, f"got {status2}")

# Identity resolution: strong conflict -> REJECTED_HOMONYM
c3 = IdentityCandidate(
    query_subject="Mario Rossi",
    match_identifiers=[
        IdentifierMatch(identifier_type="nome_cognome", value="Mario Rossi", strength=IdentifierStrength.WEAK),
        IdentifierMatch(identifier_type="data_nascita_complete", value="1912-01-09", strength=IdentifierStrength.STRONG, compatible=False, conflict_reason="different birth date"),
    ],
)
status3 = evaluate_identity(c3)
test("Strong conflict -> REJECTED_HOMONYM", status3 == IdentityStatus.REJECTED_HOMONYM, f"got {status3}")

# Can combine claims: single resolved -> True
c2.identity_status = evaluate_identity(c2)
test("Can combine with single resolved", can_combine_claims([c2]))
# Can combine: two resolved -> False (ambiguity)
c4 = IdentityCandidate(
    query_subject="Other Person",
    match_identifiers=[IdentifierMatch(identifier_type="data_nascita_complete", value="1920", strength=IdentifierStrength.STRONG)],
)
c4.identity_status = IdentityStatus.RESOLVED
test("Cannot combine with two resolved", not can_combine_claims([c2, c4]))

# Claim lifecycle
claim = Claim(predicate="born_at", object_value="1912-01-09", status=ClaimStatus.CANDIDATE)
test("Claim starts as CANDIDATE", claim.status == ClaimStatus.CANDIDATE)
claim.status = ClaimStatus.VERIFIED
test("Claim can transition to VERIFIED", claim.status == ClaimStatus.VERIFIED)

# Evidence overall confidence
ev = Evidence(
    source_authority=0.9,
    artifact_directness=0.8,
    extraction_confidence=0.9,
    identity_match_confidence=0.95,
    semantic_confidence=0.8,
    temporal_compatibility=1.0,
    geographical_compatibility=0.9,
    source_independence=0.7,
)
test("Evidence overall_confidence > 0.8", ev.overall_confidence > 0.8, f"got {ev.overall_confidence:.3f}")


# ─── 4. Text Matching ───────────────────────────────────────────────────────

print("\n=== 4. Text Matching ===")

# Word boundary: "Lana" != "Castellana"
test("'Lana' not in 'Castellana'", not matches_word_boundary("Lana", "Castellana"))
test("'Lana' in 'Monte Col di Lana'", matches_word_boundary("Lana", "Monte Col di Lana"))

# Word boundary: "Roma" != "Romania"
test("'Roma' not in 'Romania'", not matches_word_boundary("Roma", "Romania"))
test("'Roma' in 'Roma'", matches_word_boundary("Roma", "Roma"))

# Word boundary: "Nero" != "nerofumo"
test("'Nero' not in 'nerofumo'", not matches_word_boundary("Nero", "nerofumo"))
test("'Nero' in 'Monte Nero'", matches_word_boundary("Nero", "Monte Nero"))

# Word boundary: "Campo" alone
test("'Campo' in 'Campo di prigionia'", matches_word_boundary("Campo", "Campo di prigionia"))
test("'Campo' not in 'Campobasso'", not matches_word_boundary("Campo", "Campobasso"))

# Specificity classification
test("Caporetto is specific", classify_keyword_specificity("Caporetto") == "specific")
test("Campo is generic", classify_keyword_specificity("Campo") == "generic")
test("San Michele is specific (multi-word)", classify_keyword_specificity("San Michele") == "specific")

# Sufficient specificity
matches = [
    type('KM', (), {'matched': True, 'specificity': 'generic'})(),
]
test("Generic only -> insufficient", not has_sufficient_specificity([type('M', (), {'keyword': 'Campo', 'matched': True, 'specificity': 'generic'})()]))
test("Specific match -> sufficient", has_sufficient_specificity([type('M', (), {'keyword': 'Caporetto', 'matched': True, 'specificity': 'specific'})()]))

# Name parsing
cognome, nome = parse_name("Rossi Mario")
test("Parse 'Rossi Mario' -> (Rossi, Mario)", cognome == "Rossi" and nome == "Mario")

cognome, nome = parse_name("Rossi Mario di Giovanni")
test("Parse patronymic -> (Rossi, Mario)", cognome == "Rossi" and nome == "Mario")

# Name compatibility
test("Names compatible (same)", names_compatible("Mario Rossi", "Mario Rossi"))
test("Names compatible (subset)", names_compatible("Mario", "Mario Rossi"))
test("Names not compatible (different)", not names_compatible("Mario Rossi", "Luigi Bianchi"))

# OCR variants
variants = generate_ocr_variants("Rossi")
test("OCR variants generated", len(variants) >= 1)

# Alias matching
aliases = ["Caporetto", "Kobarid", "Isonzo", "Carso"]
fields = {"luogo_morte": "Monte Asolone", "luogo_text": "Caduto a Caporetto"}
results = match_aliases(aliases, fields)
test("Caporetto alias matched", any(r.alias == "Caporetto" and r.matched for r in results))
test("Isonzo alias not matched", all(r.alias != "Isonzo" or not r.matched for r in results))
test("Has specific alias match", has_specific_alias_match(results))


# ─── 5. Temporal Barriers ───────────────────────────────────────────────────

print("\n=== 5. Temporal Barriers ===")

# WWI source vs WWII target -> REJECTED
result = check_temporal_compatibility(
    source_date="1917-10-24",
    source_date_role=DateRole.EVENT_START,
    target_date_start="1943-09-08",
    target_date_end="1945-05-08",
    target_war=WarPeriod.WWII,
)
test("WWI source vs WWII target -> veto", result.veto and not result.compatible)

# WWII source vs WWI target -> REJECTED
result = check_temporal_compatibility(
    source_date="1943-09-08",
    source_date_role=DateRole.EVENT_START,
    target_date_start="1915-06-23",
    target_date_end="1918-11-04",
    target_war=WarPeriod.WWI,
)
test("WWII source vs WWI target -> veto", result.veto and not result.compatible)

# Same war period -> compatible
result = check_temporal_compatibility(
    source_date="1916-08-06",
    source_date_role=DateRole.EVENT_START,
    target_date_start="1915-06-23",
    target_date_end="1917-09-12",
    target_war=WarPeriod.WWI,
)
test("WWI source vs WWI target -> compatible", result.compatible and result.war_match)

# Publication date does not prove participation
result = check_temporal_compatibility(
    source_date="1917-10-25",
    source_date_role=DateRole.PUBLICATION_DATE,
    target_date_start="1917-10-24",
    target_date_end="1917-11-12",
)
test("Publication date in range but weak", result.compatible and "does not prove" in result.conflict_reason.lower(), f"got: {result.conflict_reason}")

# Missing date -> not conflict
result = check_temporal_compatibility(
    source_date="",
    source_date_role=DateRole.UNKNOWN,
    target_date_start="1917-10-24",
    target_date_end="1917-11-12",
)
test("Missing date -> not conflict", result.compatible and "MISSING" in result.conflict_reason)


# ─── 6. Geographic Barriers ─────────────────────────────────────────────────

print("\n=== 6. Geographic Barriers ===")

# Burial place != event place
result = check_geographic_compatibility("luogo_sepoltura", "Roma", "luogo", "Monte Grappa")
test("Burial place != event place", not result.compatible, f"got: {result.conflict_reason}")

# Death place != capture place
result = check_geographic_compatibility("luogo_morte", "Bolzano", "luogo_cattura", "Grecia")
test("Death place != capture place", not result.compatible)

# Detention place != event place
result = check_geographic_compatibility("luogo_internamento", "Mauthausen", "luogo", "Monte Grappa")
test("Detention place != event place", not result.compatible)

# Same role -> compatible
result = check_geographic_compatibility("luogo_nascita", "Bolzano", "luogo_nascita", "Bolzano")
test("Same role -> compatible", result.compatible and result.same_role)

# Residence != event place
result = check_geographic_compatibility("residenza", "Trento", "luogo", "Monte Grappa")
test("Residence != event place", not result.compatible)


# ─── 7. Combined Match Evaluation ───────────────────────────────────────────

print("\n=== 7. Combined Match Evaluation ===")

# Temporal veto -> REJECTED
temporal = TemporalCompatibility(compatible=False, war_match=False, date_overlap=False, veto=True, conflict_reason="WAR_PERIOD_MISMATCH")
geo = GeographicCompatibility(compatible=True, same_role=True)
result = evaluate_match(text_match=True, has_specific_keyword=True, temporal=temporal, geographic=geo)
test("Temporal veto -> REJECTED", result.decision == "REJECTED" and result.temporal_veto)

# Geographic veto -> REJECTED
temporal = TemporalCompatibility(compatible=True, war_match=True, date_overlap=True)
geo = GeographicCompatibility(compatible=False, same_role=False, conflict_reason="BURIAL_PLACE_AS_EVENT")
result = evaluate_match(text_match=True, has_specific_keyword=True, temporal=temporal, geographic=geo)
test("Geographic veto -> REJECTED", result.decision == "REJECTED" and result.geographic_veto)

# No text match -> REJECTED
temporal = TemporalCompatibility(compatible=True, war_match=True, date_overlap=True)
geo = GeographicCompatibility(compatible=True, same_role=True)
result = evaluate_match(text_match=False, has_specific_keyword=False, temporal=temporal, geographic=geo)
test("No text match -> REJECTED", result.decision == "REJECTED")

# Generic keywords only -> NEEDS_REVIEW
result = evaluate_match(text_match=True, has_specific_keyword=False, temporal=temporal, geographic=geo)
test("Generic only -> NEEDS_REVIEW", result.decision == "NEEDS_REVIEW")

# All pass -> CANDIDATE
result = evaluate_match(text_match=True, has_specific_keyword=True, temporal=temporal, geographic=geo)
test("All pass -> CANDIDATE", result.decision == "CANDIDATE")
test("Candidate confidence > 0.5", result.confidence > 0.5, f"got {result.confidence:.3f}")


# ─── Summary ────────────────────────────────────────────────────────────────

print(f"\n{'='*80}")
print(f"V7.3 Phase B/C Tests: {passed} PASS, {failed} FAIL")
print(f"{'='*80}")

if errors:
    print("\nFailures:")
    for e in errors:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)
