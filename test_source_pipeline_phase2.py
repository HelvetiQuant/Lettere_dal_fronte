"""
Test per consumer_adapter, golden_dataset, admin_dashboard_api — 20 test.

Categorie:
  1. Consumer Adapter dataclasses & functions (7 test)
  2. Golden Dataset structure & validation (5 test)
  3. Admin Dashboard API endpoints (5 test)
  4. RAG Pipeline Supabase integration (3 test)

Run: python -m pytest test_source_pipeline_phase2.py -v
     python test_source_pipeline_phase2.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ════════════════════════════════════════════════════════════════════════════
# 1. CONSUMER ADAPTER (7 test)
# ════════════════════════════════════════════════════════════════════════════

class TestConsumerAdapter:
    def test_claim_summary_dataclass(self):
        """ClaimSummary must have all required fields and to_dict."""
        from source_pipeline.consumer_adapter import ClaimSummary
        c = ClaimSummary(
            claim_id=1, stable_id="sha256:abc", subject_entity_id=10,
            subject_name="Test", predicate="was_prisoner_in",
            object_entity_id=None, object_name="Camp A",
            object_value=None, claim_status="supported",
            valid_from="1916-01-01", valid_to="1918-01-01",
            evidence_count=3, latest_decision="needs_revision",
        )
        d = c.to_dict()
        assert d["claim_id"] == 1
        assert d["claim_status"] == "supported"
        assert d["evidence_count"] == 3
        assert d["predicate"] == "was_prisoner_in"

    def test_evidence_summary_dataclass(self):
        """EvidenceSummary must have all required fields and to_dict."""
        from source_pipeline.consumer_adapter import EvidenceSummary
        e = EvidenceSummary(
            evidence_id=1, claim_id=9, evidence_type="documentary",
            source_item_id=None, source_provider_code="europeana",
            text_span="test span", independence_group="europeana",
            review_status="pending", human_verified=False,
        )
        d = e.to_dict()
        assert d["evidence_id"] == 1
        assert d["evidence_type"] == "documentary"
        assert d["human_verified"] is False

    def test_external_item_summary_dataclass(self):
        """ExternalItemSummary must have all required fields and to_dict."""
        from source_pipeline.consumer_adapter import ExternalItemSummary
        ei = ExternalItemSummary(
            item_id=1, stable_id="sha256:ext1", provider_code="europeana",
            external_id="abc123", item_type="document",
            title="Test Document", description="A test doc",
            canonical_url="https://example.com/1",
            holding_institution="", collection_or_fonds="", archival_signature="",
            access_status="active", review_status="candidate",
        )
        d = ei.to_dict()
        assert d["provider_code"] == "europeana"
        assert d["item_type"] == "document"

    def test_search_claims_returns_list(self):
        """search_claims must return a list of ClaimSummary."""
        from source_pipeline.consumer_adapter import search_claims
        results = search_claims("Carso", limit=5)
        assert isinstance(results, list)
        # If results exist, verify type
        for r in results:
            assert hasattr(r, "claim_id")
            assert hasattr(r, "claim_status")

    def test_get_evidence_for_claim(self):
        """get_evidence_for_claim must return evidence for claim 9."""
        from source_pipeline.consumer_adapter import get_evidence_for_claim
        evidence = get_evidence_for_claim(9)
        assert isinstance(evidence, list)
        # Claim 9 has 6 evidence rows
        assert len(evidence) >= 3

    def test_get_biographical_claims(self):
        """get_biographical_claims must return claims for entity 10."""
        from source_pipeline.consumer_adapter import get_biographical_claims
        claims = get_biographical_claims(person_entity_id=10)
        assert isinstance(claims, list)

    def test_retrieve_from_supabase(self):
        """retrieve_from_supabase must return list of dicts with chunk_id."""
        from source_pipeline.consumer_adapter import retrieve_from_supabase
        results = retrieve_from_supabase("Carso", limit=5)
        assert isinstance(results, list)
        for r in results:
            assert "chunk_id" in r
            assert "text" in r


# ════════════════════════════════════════════════════════════════════════════
# 2. GOLDEN DATASET (5 test)
# ════════════════════════════════════════════════════════════════════════════

class TestGoldenDataset:
    def test_golden_cases_count(self):
        """GOLDEN_CASES must have 6 cases."""
        from golden_dataset import GOLDEN_CASES
        assert len(GOLDEN_CASES) == 6

    def test_golden_case_structure(self):
        """Each GoldenCase must have required fields."""
        from golden_dataset import GOLDEN_CASES
        for case in GOLDEN_CASES:
            assert case.case_id
            assert case.description
            assert case.expected_claim_status in (
                "discovered", "ingested", "candidate", "supported",
                "verified", "conflicting", "rejected", "superseded",
                "legacy_unverified",
            )
            assert case.min_evidence_count >= 0
            assert case.required_independent_sources >= 0

    def test_negative_controls_have_no_claim_id(self):
        """GD-005-NEG and GD-006-NEG must have claim_id=0 (control cases)."""
        from golden_dataset import GOLDEN_CASES
        neg_cases = [c for c in GOLDEN_CASES if "NEG" in c.case_id]
        assert len(neg_cases) == 2
        for c in neg_cases:
            assert c.claim_id == 0

    def test_golden_dataset_report_exists(self):
        """GOLDEN_DATASET_REPORT.json must exist after validation."""
        report_path = Path(__file__).parent / "docs" / "audit" / "GOLDEN_DATASET_REPORT.json"
        assert report_path.exists(), "Golden dataset report not found — run: python golden_dataset.py --report"

    def test_golden_dataset_all_pass(self):
        """All non-skipped golden cases must pass."""
        report_path = Path(__file__).parent / "docs" / "audit" / "GOLDEN_DATASET_REPORT.json"
        if not report_path.exists():
            pytest.skip("Golden dataset report not found")
        data = json.loads(report_path.read_text(encoding="utf-8"))
        results = data.get("results", [])
        failed = [r for r in results if r["status"] == "fail"]
        assert len(failed) == 0, f"Golden dataset has {len(failed)} failures: {[r['case_id'] for r in failed]}"


# ════════════════════════════════════════════════════════════════════════════
# 3. ADMIN DASHBOARD API (5 test)
# ════════════════════════════════════════════════════════════════════════════

class TestAdminDashboardAPI:
    def test_router_has_10_routes(self):
        """Admin dashboard router must have 10 routes."""
        from source_pipeline.admin_dashboard_api import router
        assert len(router.routes) == 10

    def test_router_prefix(self):
        """Router must have /api/admin prefix."""
        from source_pipeline.admin_dashboard_api import router
        assert router.prefix == "/api/admin"

    def test_dashboard_endpoint_path(self):
        """Dashboard endpoint must be at /dashboard."""
        from source_pipeline.admin_dashboard_api import router
        paths = [r.path for r in router.routes]
        assert any(p.endswith("/dashboard") for p in paths)

    def test_claims_patch_endpoint_exists(self):
        """Claims PATCH endpoint must exist for updating claim_status."""
        from source_pipeline.admin_dashboard_api import router
        paths = [r.path for r in router.routes]
        assert any(p.endswith("/claims/{claim_id}") for p in paths)

    def test_migration_status_endpoint_exists(self):
        """Migration status endpoint must exist."""
        from source_pipeline.admin_dashboard_api import router
        paths = [r.path for r in router.routes]
        assert any(p.endswith("/migration-status") for p in paths)


# ════════════════════════════════════════════════════════════════════════════
# 4. RAG PIPELINE SUPABASE INTEGRATION (3 test)
# ════════════════════════════════════════════════════════════════════════════

class TestRAGSupabaseIntegration:
    def test_supabase_available_flag(self):
        """_SUPABASE_AVAILABLE must be True after import."""
        from rag_pipeline import _SUPABASE_AVAILABLE
        assert _SUPABASE_AVAILABLE is True

    def test_retrieve_returns_list(self):
        """retrieve() must return a list of RetrievedChunk."""
        from rag_pipeline import retrieve
        results = retrieve("Carso", limit=10)
        assert isinstance(results, list)

    def test_retrieve_chunks_have_required_fields(self):
        """Each RetrievedChunk must have chunk_id, source_table, text."""
        from rag_pipeline import retrieve
        results = retrieve("Carso", limit=5)
        for r in results:
            assert hasattr(r, "chunk_id")
            assert hasattr(r, "source_table")
            assert hasattr(r, "text")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
