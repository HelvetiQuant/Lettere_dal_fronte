"""
Test obbligatori per la source pipeline v2 — 26 test.

Categorie:
  1. Contract & data structures (5 test)
  2. Registry & YAML loading (4 test)
  3. Adapters (4 test)
  4. Ingestion & Supabase (4 test)
  5. Worker (3 test)
  6. Schema & RLS (3 test)
  7. Pilot results (3 test)

Run: python -m pytest test_source_pipeline.py -v
     python test_source_pipeline.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ════════════════════════════════════════════════════════════════════════════
# 1. CONTRACT & DATA STRUCTURES (5 test)
# ════════════════════════════════════════════════════════════════════════════

class TestContract:
    def test_stable_id_deterministic(self):
        """compute_stable_id must be deterministic for same inputs."""
        from source_pipeline import compute_stable_id
        a = compute_stable_id("ext", "abc123", "europeana")
        b = compute_stable_id("ext", "abc123", "europeana")
        assert a == b
        assert a.startswith("sha256:")

    def test_stable_id_different_inputs(self):
        """Different inputs must produce different stable IDs."""
        from source_pipeline import compute_stable_id
        a = compute_stable_id("ext", "abc123", "europeana")
        b = compute_stable_id("ext", "abc456", "europeana")
        c = compute_stable_id("ext", "abc123", "nara")
        assert a != b
        assert a != c

    def test_content_hash(self):
        """compute_content_hash must be deterministic SHA-256."""
        from source_pipeline import compute_content_hash
        h = compute_content_hash("test content")
        assert h.startswith("sha256:")
        assert len(h) == 71  # "sha256:" + 64 hex chars
        assert compute_content_hash("test content") == h
        assert compute_content_hash("different") != h

    def test_source_provider_is_abstract(self):
        """SourceProvider must be abstract and not instantiable directly."""
        from source_pipeline import SourceProvider
        with pytest.raises(TypeError):
            SourceProvider()

    def test_search_page_defaults(self):
        """SearchPage must have correct defaults."""
        from source_pipeline import SearchPage, SearchResult
        page = SearchPage(results=[])
        assert page.has_more is False
        assert page.next_cursor is None
        assert page.total_count is None
        assert page.results == []


# ════════════════════════════════════════════════════════════════════════════
# 2. REGISTRY & YAML LOADING (4 test)
# ════════════════════════════════════════════════════════════════════════════

class TestRegistry:
    def test_load_providers_count(self):
        """Registry must load 26 providers from YAML."""
        from source_pipeline.registry import load_providers
        yaml_path = Path(__file__).parent / "config" / "archive_providers.yml"
        providers = load_providers(yaml_path)
        assert len(providers) == 26

    def test_provider_has_authority_class(self):
        """Every provider must have a non-empty authority_class."""
        from source_pipeline.registry import load_providers
        yaml_path = Path(__file__).parent / "config" / "archive_providers.yml"
        providers = load_providers(yaml_path)
        for code, cfg in providers.items():
            assert cfg.authority_class, f"Provider {code} has empty authority_class"
            assert cfg.authority_class in (
                "PRIMARY_ARCHIVAL", "OFFICIAL_DERIVED", "SCHOLARLY_CURATED",
                "AGGREGATOR", "DISCOVERY_ONLY", "USER_CONTRIBUTED",
            ), f"Provider {code} has invalid authority_class: {cfg.authority_class}"

    def test_provider_independence_group(self):
        """Key providers must have independence_group set."""
        from source_pipeline.registry import load_providers
        yaml_path = Path(__file__).parent / "config" / "archive_providers.yml"
        providers = load_providers(yaml_path)
        expected_groups = {
            "ussme": "ussme",
            "archiviodistato": "san",
            "antenati": "san",
            "cri_milano": "cri",
            "lebi": "anrp",
            "nara": "nara",
            "europeana": "europeana",
            "gallica": "bnf",
            "icrc_ww1": "icrc",
            "arolsen": "arolsen",
        }
        for code, expected_group in expected_groups.items():
            assert code in providers, f"Provider {code} not found in registry"
            assert providers[code].independence_group == expected_group, \
                f"Provider {code} independence_group={providers[code].independence_group}, expected {expected_group}"

    def test_provider_terms_url(self):
        """Key providers must have terms_url set."""
        from source_pipeline.registry import load_providers
        yaml_path = Path(__file__).parent / "config" / "archive_providers.yml"
        providers = load_providers(yaml_path)
        for code in ["ussme", "archiviodistato", "nara", "europeana", "icrc_ww1", "arolsen"]:
            assert code in providers
            assert providers[code].terms_url, f"Provider {code} has empty terms_url"


# ════════════════════════════════════════════════════════════════════════════
# 3. ADAPTERS (4 test)
# ════════════════════════════════════════════════════════════════════════════

class TestAdapters:
    def test_get_all_adapters_count(self):
        """get_all_adapters must return at least 20 adapters."""
        from source_pipeline.adapters import get_all_adapters
        adapters = get_all_adapters()
        assert len(adapters) >= 20

    def test_europeana_adapter_contract(self):
        """EuropeanaAdapter must implement SourceProvider correctly."""
        from source_pipeline.adapters import EuropeanaAdapter
        from source_pipeline import SourceProvider, ProviderCapabilities, ProviderPolicy
        adapter = EuropeanaAdapter()
        assert isinstance(adapter, SourceProvider)
        assert adapter.provider_code == "europeana"
        caps = adapter.capabilities()
        assert isinstance(caps, ProviderCapabilities)
        policy = adapter.policy()
        assert isinstance(policy, ProviderPolicy)
        assert policy.authority_class == "AGGREGATOR"

    def test_lebi_adapter_representations(self):
        """LeBI adapter must return PDF representation."""
        from source_pipeline.adapters import LeBIAdapter
        adapter = LeBIAdapter()
        reps = adapter.fetch_representations("12345")
        assert len(reps) == 1
        assert reps[0].mime_type == "application/pdf"
        assert "showpdf" in reps[0].file_url

    def test_legacy_bridge_adapter(self):
        """LegacyBridgeAdapter must wrap a legacy provider correctly."""
        from source_pipeline.adapters import LegacyBridgeAdapter
        from source_pipeline import SourceProvider

        class FakeLegacy:
            name = "fake"
            def search(self, query, filters=None, *, context=None):
                return [{"provider_record_id": "1", "titolo": "Test", "catalog_url": "http://example.com/1"}]
            def get_metadata(self, record_id):
                return {"provider_record_id": record_id, "titolo": "Test Meta"}

        adapter = LegacyBridgeAdapter(FakeLegacy(), "europeana")
        assert isinstance(adapter, SourceProvider)
        assert adapter.provider_code == "europeana"
        page = adapter.search("test")
        assert len(page.results) == 1
        assert page.results[0].title == "Test"
        assert page.results[0].external_id == "1"


# ════════════════════════════════════════════════════════════════════════════
# 4. INGESTION & SUPABASE (4 test)
# ════════════════════════════════════════════════════════════════════════════

class TestIngestion:
    def test_get_provider_id_real(self):
        """_get_provider_id must return an ID for europeana on Supabase."""
        from source_pipeline.ingestion import _get_provider_id
        pid = _get_provider_id("europeana")
        assert pid is not None
        assert isinstance(pid, int)
        assert pid > 0

    def test_ingest_search_result_idempotent(self):
        """Ingesting the same SearchResult twice must return the same item ID."""
        from source_pipeline.ingestion import ingest_search_result
        from source_pipeline import SearchResult
        result = SearchResult(
            external_id="test-idempotent-001",
            title="Test Idempotent Item",
            description="Test description for idempotency",
            canonical_url="https://example.com/test/001",
            item_type="document",
            provider_code="europeana",
        )
        id1 = ingest_search_result(result, provider_id=9)
        id2 = ingest_search_result(result, provider_id=9)
        assert id1 is not None
        assert id2 is not None
        assert id1 == id2, f"Idempotency violated: {id1} != {id2}"

    def test_create_claim_idempotent(self):
        """Creating the same claim twice must return the same claim ID."""
        from source_pipeline.ingestion import create_claim
        from source_pipeline import compute_stable_id
        entity_id = 50  # Use existing entity from pilots
        pipeline_run = "test_idempotent_claim"
        cid1 = create_claim(
            subject_entity_id=entity_id,
            predicate="test_predicate",
            object_value="test_object",
            pipeline_run_id=pipeline_run,
        )
        cid2 = create_claim(
            subject_entity_id=entity_id,
            predicate="test_predicate",
            object_value="test_object",
            pipeline_run_id=pipeline_run,
        )
        assert cid1 is not None
        assert cid2 is not None
        assert cid1 == cid2

    def test_add_evidence_idempotent(self):
        """Adding the same evidence twice must return the same evidence ID."""
        from source_pipeline.ingestion import create_claim, add_evidence
        # Use existing claim from pilots
        claim_id = 9  # Pilot A claim
        ev1 = add_evidence(
            claim_id=claim_id,
            evidence_type="documentary",
            text_span="test idempotent evidence",
            independence_group="test_group",
        )
        ev2 = add_evidence(
            claim_id=claim_id,
            evidence_type="documentary",
            text_span="test idempotent evidence",
            independence_group="test_group",
        )
        assert ev1 is not None
        assert ev2 is not None
        assert ev1 == ev2


# ════════════════════════════════════════════════════════════════════════════
# 5. WORKER (3 test)
# ════════════════════════════════════════════════════════════════════════════

class TestWorker:
    def test_worker_config_defaults(self):
        """WorkerConfig must have sensible defaults."""
        from source_pipeline.worker import WorkerConfig
        cfg = WorkerConfig()
        assert cfg.max_concurrent_per_provider >= 1
        assert cfg.max_attempts >= 1
        assert cfg.base_backoff_seconds > 0
        assert cfg.circuit_breaker_threshold >= 1

    def test_worker_metrics(self):
        """WorkerMetrics must initialize to zero."""
        from source_pipeline.worker import WorkerMetrics
        metrics = WorkerMetrics()
        assert metrics.jobs_succeeded == 0
        assert metrics.jobs_failed == 0
        assert metrics.jobs_retried == 0
        assert metrics.jobs_dead_lettered == 0
        assert metrics.items_ingested == 0

    def test_worker_stop_event(self):
        """Worker stop event must be threadable."""
        from source_pipeline.worker import JobQueueWorker, WorkerConfig
        import threading
        cfg = WorkerConfig(max_concurrent_per_provider=1)
        worker = JobQueueWorker(config=cfg, providers={}, db_conn_func=lambda: None)
        assert worker._stop_event is not None
        assert isinstance(worker._stop_event, threading.Event)
        assert worker._stop_event.is_set() is False
        worker.stop()
        assert worker._stop_event.is_set() is True


# ════════════════════════════════════════════════════════════════════════════
# 6. SCHEMA & RLS (3 test)
# ════════════════════════════════════════════════════════════════════════════

class TestSchema:
    def test_providers_table_has_data(self):
        """archive.providers must have 26 rows on Supabase."""
        import httpx
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept-Profile": "archive",
        }
        r = httpx.get(
            f"{url}/rest/v1/providers?select=id&limit=50",
            headers=headers,
            timeout=30,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 26

    def test_evidence_claims_table_exists(self):
        """evidence.claims table must exist and be queryable."""
        from source_pipeline.ingestion import _exec_sql_returning
        sql = "SELECT json_agg(row_to_json(x)) FROM (SELECT count(*) as n FROM evidence.claims) x;"
        result = _exec_sql_returning(sql)
        assert isinstance(result, list)
        assert result[0].get("n") is not None

    def test_published_claims_view_exists(self):
        """api_public.published_claims view must exist."""
        from source_pipeline.ingestion import _exec_sql_returning
        sql = "SELECT json_agg(row_to_json(x)) FROM (SELECT count(*) as n FROM api_public.published_claims) x;"
        result = _exec_sql_returning(sql)
        # View exists if no error
        if isinstance(result, dict) and result.get("__error__"):
            pytest.fail(f"published_claims view error: {result.get('error')}")


# ════════════════════════════════════════════════════════════════════════════
# 7. PILOT RESULTS (3 test)
# ════════════════════════════════════════════════════════════════════════════

class TestPilotResults:
    def test_pilot_results_file_exists(self):
        """PILOT_RESULTS.json must exist after pilot run."""
        report_path = Path(__file__).parent / "docs" / "audit" / "PILOT_RESULTS.json"
        assert report_path.exists(), f"Pilot results not found at {report_path}"

    def test_pilot_a_has_items(self):
        """Pilot A (Carso) must have discovered items."""
        report_path = Path(__file__).parent / "docs" / "audit" / "PILOT_RESULTS.json"
        if not report_path.exists():
            pytest.skip("Pilot results not found")
        data = json.loads(report_path.read_text(encoding="utf-8"))
        pilots = {p["pilot"]: p for p in data.get("pilots", [])}
        assert "A" in pilots
        assert pilots["A"]["status"] == "completed"
        assert pilots["A"]["items_discovered"] > 0
        assert pilots["A"]["claim_id"] is not None

    def test_pilot_c_has_lebi_items(self):
        """Pilot C (IMI WW2) must have LeBI items ingested."""
        report_path = Path(__file__).parent / "docs" / "audit" / "PILOT_RESULTS.json"
        if not report_path.exists():
            pytest.skip("Pilot results not found")
        data = json.loads(report_path.read_text(encoding="utf-8"))
        pilots = {p["pilot"]: p for p in data.get("pilots", [])}
        assert "C" in pilots
        assert pilots["C"]["status"] == "completed"
        assert pilots["C"]["lebi_results"] > 0
        assert pilots["C"]["claim_id"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
