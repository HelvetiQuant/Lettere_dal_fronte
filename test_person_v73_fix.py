"""Unit tests for V7.3-PERSON-FIX: schema mapping, identity resolution, semantic counts.

Tests:
  1. PERSON_SOURCE_SCHEMAS: 5 tables, field mappings, validators, normalizers
  2. extract_claims_from_record: correct extraction per table
  3. IdentityResolver: war-period separation, strong-ID conflicts, no homonym fusion
  4. PersonPipelineModels: PersonCandidate, PersonFact, FactEvidence, ConflictSet
  5. Semantic counts: fact/evidence/provenance separation
"""
import unittest
import hashlib
from dataclasses import dataclass

from person_source_schemas import (
    PERSON_SOURCE_SCHEMAS, SourceSchema,
    get_schema, get_all_claim_predicates, get_all_provenance_predicates,
    validate_and_normalize_value,
    get_identity_fields_for_table, get_conflict_fields_for_table,
    get_war_period_for_table, get_name_fields_for_table,
    extract_claims_from_record,
    WAR_PERIOD_WWI, WAR_PERIOD_WWII, WAR_PERIOD_BOTH,
)

from person_pipeline_models import (
    PersonCandidate, FactEvidence, SourceProvenance, PersonFact,
    ConflictSet, ConflictEntry, RejectedObservation, PersonPipelineResult,
)

from v7_identity_model import (
    IdentityResolver, IdentityCluster, DISCRIMINANT_FIELDS,
    STRONG_IDENTIFIERS, TABLE_WAR_PERIOD,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. PERSON_SOURCE_SCHEMAS tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPersonSourceSchemas(unittest.TestCase):

    def test_all_5_tables_registered(self):
        expected = {"internati", "caduti_albooro", "decorati_nastroazzurro", "caduti_cwgc", "caduti_ministero"}
        self.assertEqual(set(PERSON_SOURCE_SCHEMAS.keys()), expected)

    def test_internati_schema(self):
        schema = get_schema("internati")
        self.assertEqual(schema.war_period, WAR_PERIOD_WWII)
        self.assertEqual(schema.name_fields, ("cognome", "nome", ""))
        self.assertEqual(schema.authority_tier, 1)
        self.assertIn("sorte", schema.claim_fields)
        self.assertEqual(schema.claim_fields["sorte"], "fate")
        self.assertIn("data_nascita", schema.claim_fields)
        self.assertEqual(schema.claim_fields["data_nascita"], "birth_date")

    def test_caduti_albooro_schema(self):
        schema = get_schema("caduti_albooro")
        self.assertEqual(schema.war_period, WAR_PERIOD_WWII)
        self.assertEqual(schema.name_fields, ("", "", "nominativo"))
        self.assertIn("paternita", schema.claim_fields)
        self.assertEqual(schema.claim_fields["anno_morte"], "death_year")

    def test_decorati_nastroazzurro_schema(self):
        schema = get_schema("decorati_nastroazzurro")
        self.assertEqual(schema.war_period, WAR_PERIOD_WWII)
        self.assertEqual(schema.name_fields, ("cognome", "nome", ""))
        self.assertEqual(schema.claim_fields["arma"], "military_branch")
        self.assertEqual(schema.claim_fields["anno_decorazione"], "decoration_year")

    def test_caduti_cwgc_schema(self):
        schema = get_schema("caduti_cwgc")
        self.assertEqual(schema.war_period, WAR_PERIOD_BOTH)
        self.assertEqual(schema.name_fields, ("cognome", "nome", ""))
        self.assertEqual(schema.claim_fields["service_number"], "service_number")
        self.assertEqual(schema.claim_fields["regiment"], "military_unit")

    def test_caduti_ministero_schema(self):
        schema = get_schema("caduti_ministero")
        self.assertEqual(schema.war_period, WAR_PERIOD_WWII)
        self.assertEqual(schema.name_fields, ("cognome", "nome", ""))
        self.assertIn("paternita", schema.claim_fields)
        self.assertIn("maternita", schema.claim_fields)
        self.assertEqual(schema.claim_fields["data_decesso"], "death_date")
        self.assertEqual(schema.claim_fields["comune_nascita"], "birth_place")

    def test_war_period_classification(self):
        self.assertEqual(get_war_period_for_table("internati"), WAR_PERIOD_WWII)
        self.assertEqual(get_war_period_for_table("caduti_albooro"), WAR_PERIOD_WWII)
        self.assertEqual(get_war_period_for_table("caduti_cwgc"), WAR_PERIOD_BOTH)
        self.assertEqual(get_war_period_for_table("caduti_ministero"), WAR_PERIOD_WWII)
        self.assertEqual(get_war_period_for_table("nonexistent"), "UNKNOWN")

    def test_name_fields_lookup(self):
        cognome, nome, nominativo = get_name_fields_for_table("caduti_albooro")
        self.assertEqual(cognome, "")
        self.assertEqual(nome, "")
        self.assertEqual(nominativo, "nominativo")

        cognome, nome, nominativo = get_name_fields_for_table("internati")
        self.assertEqual(cognome, "cognome")
        self.assertEqual(nome, "nome")
        self.assertEqual(nominativo, "")

    def test_identity_fields_per_table(self):
        internati_ids = get_identity_fields_for_table("internati")
        self.assertIn("data_nascita", internati_ids)
        self.assertIn("matricola", internati_ids)

        ministero_ids = get_identity_fields_for_table("caduti_ministero")
        self.assertIn("paternita", ministero_ids)
        self.assertIn("maternita", ministero_ids)

    def test_conflict_fields_per_table(self):
        ministero_conflicts = get_conflict_fields_for_table("caduti_ministero")
        self.assertIn("data_nascita", ministero_conflicts)
        self.assertIn("paternita", ministero_conflicts)

    def test_all_predicates_covered(self):
        claim_preds = get_all_claim_predicates()
        self.assertIn("birth_date", claim_preds)
        self.assertIn("death_date", claim_preds)
        self.assertIn("rank", claim_preds)
        self.assertIn("paternity", claim_preds)
        self.assertIn("military_unit", claim_preds)

        prov_preds = get_all_provenance_predicates()
        self.assertIn("source_url", prov_preds)
        self.assertIn("source_page", prov_preds)


# ═══════════════════════════════════════════════════════════════════════════
# 2. extract_claims_from_record tests
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractClaimsFromRecord(unittest.TestCase):

    def test_internati_extraction(self):
        record = {
            "id": 1,
            "cognome": "ROSSI",
            "nome": "MARIO",
            "data_nascita": "1920-05-15",
            "luogo_nascita": "Milano",
            "grado": "sergente",
            "sorte": "internato",
            "matricola": "12345",
            "lettera": "A",
            "file_pdf": "doc.pdf",
            "pagina": 12,
        }
        claims, provenance = extract_claims_from_record("internati", record, 1)
        predicates = {c["predicate"] for c in claims}
        self.assertIn("birth_date", predicates)
        self.assertIn("birth_place", predicates)
        self.assertIn("rank", predicates)
        self.assertIn("fate", predicates)
        self.assertIn("military_id", predicates)

        prov_preds = {p["predicate"] for p in provenance}
        self.assertIn("archive_letter", prov_preds)
        self.assertIn("source_document", prov_preds)
        self.assertIn("source_page", prov_preds)

    def test_caduti_ministero_extraction(self):
        record = {
            "id": 100,
            "cognome": "BIANCHI",
            "nome": "LUIGI",
            "paternita": "Giovanni",
            "maternita": "Maria",
            "data_nascita": "1910-03-20",
            "data_decesso": "1944-07-15",
            "comune_nascita": "Roma",
            "provincia_nascita": "RM",
            "luogo_sepoltura": "Cimitero Verano",
            "scheda_url": "http://example.com/100",
        }
        claims, provenance = extract_claims_from_record("caduti_ministero", record, 100)
        predicates = {c["predicate"] for c in claims}
        self.assertIn("paternity", predicates)
        self.assertIn("maternity", predicates)
        self.assertIn("birth_date", predicates)
        self.assertIn("death_date", predicates)
        self.assertIn("birth_place", predicates)
        self.assertIn("birth_province", predicates)
        self.assertIn("burial_place", predicates)

        prov_preds = {p["predicate"] for p in provenance}
        self.assertIn("source_url", prov_preds)

    def test_caduti_cwgc_extraction(self):
        record = {
            "id": 200,
            "cwgc_id": "CWGC123",
            "cognome": "SMITH",
            "nome": "JOHN",
            "rank": "Private",
            "service_number": "S/12345",
            "regiment": "Royal Scots",
            "data_morte": "1916-07-01",
            "cimitero": "Thiepval",
            "paese_cimitero": "France",
        }
        claims, provenance = extract_claims_from_record("caduti_cwgc", record, 200)
        predicates = {c["predicate"] for c in claims}
        self.assertIn("rank", predicates)
        self.assertIn("service_number", predicates)
        self.assertIn("military_unit", predicates)
        self.assertIn("death_date", predicates)
        self.assertIn("burial_place", predicates)
        self.assertIn("burial_country", predicates)

    def test_empty_values_skipped(self):
        record = {
            "id": 1,
            "cognome": "ROSSI",
            "nome": "MARIO",
            "data_nascita": "",
            "luogo_nascita": "-",
            "sorte": "",
        }
        claims, _ = extract_claims_from_record("internati", record, 1)
        predicates = {c["predicate"] for c in claims}
        self.assertNotIn("birth_date", predicates)
        self.assertNotIn("birth_place", predicates)
        self.assertNotIn("fate", predicates)

    def test_invalid_values_flagged(self):
        record = {
            "id": 1,
            "cognome": "ROSSI",
            "nome": "MARIO",
            "data_nascita": "not a date",
            "luogo_nascita": "12345",
        }
        claims, _ = extract_claims_from_record("internati", record, 1)
        for c in claims:
            if c["predicate"] == "birth_date":
                self.assertEqual(c["validation_status"], "invalid")
            if c["predicate"] == "birth_place":
                self.assertEqual(c["validation_status"], "invalid")

    def test_normalization_applied(self):
        record = {
            "id": 1,
            "cognome": "ROSSI",
            "nome": "MARIO",
            "data_nascita": "15/05/1920",
        }
        claims, _ = extract_claims_from_record("internati", record, 1)
        for c in claims:
            if c["predicate"] == "birth_date":
                self.assertEqual(c["value_normalized"], "1920-05-15")
                self.assertEqual(c["validation_status"], "valid")
                self.assertIn("normalized_from", c["normalizer_note"])

    def test_unregistered_table_returns_empty(self):
        claims, provenance = extract_claims_from_record("nonexistent_table", {"id": 1}, 1)
        self.assertEqual(claims, [])
        self.assertEqual(provenance, [])


# ═══════════════════════════════════════════════════════════════════════════
# 3. IdentityResolver tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIdentityResolverV73Fix(unittest.TestCase):

    def test_cross_war_homonyms_separated(self):
        """WWI and WWII soldiers with same name get different cluster IDs."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        wwi_obs = {"cognome": "ROSSI", "nome": "MARIO", "anno_morte": "1917"}
        wwii_obs = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1920-01-01"}

        cls1, cluster1 = resolver.classify_observation(wwi_obs, table="caduti_albooro")
        cls2, cluster2 = resolver.classify_observation(wwii_obs, table="internati")

        self.assertEqual(cls1, "FULL_NAME_CANDIDATE")
        self.assertEqual(cls2, "FULL_NAME_CANDIDATE")
        self.assertNotEqual(cluster1.cluster_id, cluster2.cluster_id)

    def test_cross_table_no_strong_id_separated(self):
        """Records from different tables with no strong IDs get different clusters."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs1 = {"cognome": "ROSSI", "nome": "MARIO"}
        obs2 = {"cognome": "ROSSI", "nome": "MARIO"}

        cls1, cluster1 = resolver.classify_observation(obs1, table="internati")
        cls2, cluster2 = resolver.classify_observation(obs2, table="caduti_ministero")

        self.assertNotEqual(cluster1.cluster_id, cluster2.cluster_id)

    def test_same_table_same_strong_id_merged(self):
        """Records from same table with same strong ID get same cluster."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs1 = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1920-01-01"}
        obs2 = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1920-01-01", "grado": "sergente"}

        cls1, cluster1 = resolver.classify_observation(obs1, table="internati")
        cls2, cluster2 = resolver.classify_observation(obs2, table="internati")

        self.assertEqual(cluster1.cluster_id, cluster2.cluster_id)

    def test_strong_id_conflict_marks_ambiguous(self):
        """Single cluster with conflicting data_nascita = AMBIGUOUS."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs1 = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1920-01-01"}
        obs2 = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1925-06-15"}

        resolver.classify_observation(obs1, table="internati")
        resolver.classify_observation(obs2, table="internati")

        status, resolved, candidates = resolver.resolve()
        self.assertEqual(status, "AMBIGUOUS_IDENTITY")
        self.assertIsNone(resolved)

    def test_surname_only_not_candidate(self):
        """Surname-only match = SURNAME_ONLY_NON_CANDIDATE."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs = {"cognome": "ROSSI", "nome": "GIOVANNI"}
        cls, cluster = resolver.classify_observation(obs, table="internati")

        self.assertEqual(cls, "SURNAME_ONLY_NON_CANDIDATE")
        self.assertIsNone(cluster)

    def test_irrelevant_observation(self):
        """Different surname = IRRELEVANT."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs = {"cognome": "BIANCHI", "nome": "MARIO"}
        cls, cluster = resolver.classify_observation(obs, table="internati")

        self.assertEqual(cls, "IRRELEVANT")
        self.assertIsNone(cluster)

    def test_resolved_with_discriminants(self):
        """Single cluster with consistent discriminants = RESOLVED_IDENTITY."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs1 = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1920-01-01", "luogo_nascita": "Milano"}
        obs2 = {"cognome": "ROSSI", "nome": "MARIO", "data_nascita": "1920-01-01", "grado": "sergente"}

        resolver.classify_observation(obs1, table="internati")
        resolver.classify_observation(obs2, table="internati")

        status, resolved, candidates = resolver.resolve()
        self.assertEqual(status, "RESOLVED_IDENTITY")
        self.assertIsNotNone(resolved)

    def test_partial_without_discriminants(self):
        """Single cluster with no discriminants = PARTIAL_IDENTITY."""
        resolver = IdentityResolver()
        resolver.set_target("ROSSI", "MARIO")

        obs = {"cognome": "ROSSI", "nome": "MARIO"}
        resolver.classify_observation(obs, table="internati")

        status, resolved, candidates = resolver.resolve()
        self.assertEqual(status, "PARTIAL_IDENTITY")
        self.assertIsNotNone(resolved)

    def test_unresolved_no_candidates(self):
        """No candidates = UNRESOLVED_IDENTITY."""
        resolver = IdentityResolver()
        resolver.set_target("NONEXISTENT", "PERSON")

        status, resolved, candidates = resolver.resolve()
        self.assertEqual(status, "UNRESOLVED_IDENTITY")
        self.assertIsNone(resolved)
        self.assertEqual(candidates, [])

    def test_table_war_period_mapping(self):
        self.assertEqual(TABLE_WAR_PERIOD["internati"], "WWII")
        self.assertEqual(TABLE_WAR_PERIOD["caduti_albooro"], "WWI")
        self.assertEqual(TABLE_WAR_PERIOD["caduti_cwgc"], "BOTH")

    def test_strong_identifiers_list(self):
        self.assertIn("data_nascita", STRONG_IDENTIFIERS)
        self.assertIn("paternita", STRONG_IDENTIFIERS)
        self.assertIn("matricola", STRONG_IDENTIFIERS)


# ═══════════════════════════════════════════════════════════════════════════
# 4. PersonPipelineModels tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPersonPipelineModels(unittest.TestCase):

    def test_person_candidate_auto_id(self):
        cand = PersonCandidate(
            candidate_id="",
            source_table="internati",
            record_id=42,
            cognome="ROSSI",
            nome="MARIO",
        )
        self.assertTrue(cand.candidate_id.startswith("cand_"))
        self.assertEqual(cand.display_name, "ROSSI MARIO")

    def test_person_candidate_nominativo(self):
        cand = PersonCandidate(
            candidate_id="",
            source_table="caduti_albooro",
            record_id=1,
            nominativo="ROSSI MARIO",
        )
        self.assertEqual(cand.display_name, "ROSSI MARIO")

    def test_fact_evidence_auto_id(self):
        ev = FactEvidence(
            evidence_id="",
            candidate_id="cand_abc123",
            source_table="internati",
            record_id=1,
            source_field="data_nascita",
            value_raw="1920-01-01",
            value_normalized="1920-01-01",
        )
        self.assertTrue(ev.evidence_id.startswith("ev_"))

    def test_person_fact_add_evidence(self):
        fact = PersonFact(
            fact_id="",
            cluster_id="cluster_123",
            predicate="birth_date",
            value_normalized="1920-01-01",
            value_raw_first="1920-01-01",
        )
        ev1 = FactEvidence(
            evidence_id="ev_1",
            candidate_id="cand_1",
            source_table="internati",
            record_id=1,
            source_field="data_nascita",
            value_raw="1920-01-01",
            value_normalized="1920-01-01",
        )
        ev2 = FactEvidence(
            evidence_id="ev_2",
            candidate_id="cand_2",
            source_table="caduti_ministero",
            record_id=100,
            source_field="data_nascita",
            value_raw="1920-01-01",
            value_normalized="1920-01-01",
        )
        fact.add_evidence(ev1)
        fact.add_evidence(ev2)

        self.assertEqual(fact.evidence_count, 2)
        self.assertTrue(fact.is_multi_source)
        self.assertEqual(fact.status, "VERIFIED")

    def test_person_fact_dedup_evidence(self):
        fact = PersonFact(
            fact_id="",
            cluster_id="cluster_123",
            predicate="rank",
            value_normalized="sergente",
            value_raw_first="sergente",
        )
        ev = FactEvidence(
            evidence_id="ev_dup",
            candidate_id="cand_1",
            source_table="internati",
            record_id=1,
            source_field="grado",
            value_raw="sergente",
            value_normalized="sergente",
        )
        fact.add_evidence(ev)
        fact.add_evidence(ev)  # duplicate
        self.assertEqual(fact.evidence_count, 1)

    def test_conflict_set(self):
        cs = ConflictSet(
            conflict_id="",
            cluster_id="cluster_123",
            predicate="birth_date",
        )
        cs.add_entry("1920-01-01", "cand_1", "internati", 1, "data_nascita")
        cs.add_entry("1925-06-15", "cand_2", "caduti_ministero", 100, "data_nascita")

        self.assertTrue(cs.is_active)
        self.assertEqual(len(cs.values), 2)

    def test_conflict_set_inactive_single_value(self):
        cs = ConflictSet(
            conflict_id="",
            cluster_id="cluster_123",
            predicate="rank",
        )
        cs.add_entry("sergente", "cand_1", "internati", 1, "grado")
        cs.add_entry("sergente", "cand_2", "internati", 2, "grado")

        self.assertFalse(cs.is_active)
        self.assertEqual(len(cs.values), 1)

    def test_person_pipeline_result_metrics(self):
        result = PersonPipelineResult(
            query_name="ROSSI MARIO",
            identity_status="RESOLVED_IDENTITY",
        )
        cand = PersonCandidate(candidate_id="c1", source_table="internati", record_id=1)
        result.candidates.append(cand)

        ev = FactEvidence(
            evidence_id="e1", candidate_id="c1",
            source_table="internati", record_id=1,
            source_field="grado", value_raw="sergente", value_normalized="sergente",
        )
        result.all_evidence.append(ev)

        prov = SourceProvenance(
            provenance_id="p1", candidate_id="c1",
            source_table="internati", record_id=1,
            predicate="archive_letter", value_raw="A", value_normalized="A",
            source_field="lettera",
        )
        result.provenance.append(prov)

        fact = PersonFact(
            fact_id="f1", cluster_id="cluster_1",
            predicate="rank", value_normalized="sergente",
            value_raw_first="sergente",
        )
        fact.add_evidence(ev)
        result.facts.append(fact)

        d = result.to_dict()
        self.assertEqual(d["metrics"]["unique_person_facts"], 1)
        self.assertEqual(d["metrics"]["supporting_evidence_records"], 1)
        self.assertEqual(d["metrics"]["provenance_items"], 1)
        self.assertEqual(d["metrics"]["unique_source_records"], 1)

    def test_source_provenance_auto_id(self):
        prov = SourceProvenance(
            provenance_id="",
            candidate_id="cand_1",
            source_table="internati",
            record_id=1,
            predicate="archive_letter",
            value_raw="A",
            value_normalized="A",
            source_field="lettera",
        )
        self.assertTrue(prov.provenance_id.startswith("prov_"))


# ═══════════════════════════════════════════════════════════════════════════
# 5. Validator/Normalizer tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidatorsAndNormalizers(unittest.TestCase):

    def test_validate_year(self):
        v, status, _ = validate_and_normalize_value("birth_year", "1920")
        self.assertEqual(status, "valid")
        self.assertEqual(v, "1920")

        v, status, _ = validate_and_normalize_value("birth_year", "not a year")
        self.assertEqual(status, "invalid")

    def test_validate_date(self):
        v, status, _ = validate_and_normalize_value("birth_date", "1920-05-15")
        self.assertEqual(status, "valid")
        self.assertEqual(v, "1920-05-15")

        v, status, _ = validate_and_normalize_value("birth_date", "15/05/1920")
        self.assertEqual(status, "valid")
        self.assertEqual(v, "1920-05-15")

    def test_validate_place(self):
        v, status, _ = validate_and_normalize_value("birth_place", "Milano")
        self.assertEqual(status, "valid")

        v, status, _ = validate_and_normalize_value("birth_place", "12345")
        self.assertEqual(status, "invalid")

    def test_validate_empty(self):
        v, status, _ = validate_and_normalize_value("birth_date", "")
        self.assertEqual(status, "skipped")
        self.assertEqual(v, "")

        v, status, _ = validate_and_normalize_value("birth_date", "-")
        self.assertEqual(status, "skipped")

    def test_normalize_year_from_string(self):
        v, status, _ = validate_and_normalize_value("death_year", "morto nel 1917")
        self.assertEqual(status, "valid")
        self.assertEqual(v, "1917")


if __name__ == "__main__":
    unittest.main()
