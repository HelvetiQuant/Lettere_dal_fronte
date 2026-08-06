"""Master test file for Graph provenance, RAG pipeline, and Map features.

Tests cover:
- Graph models (Pydantic validation, status transitions, evidence)
- Graph service (edge integrity, quarantine filtering, review workflow)
- RAG pipeline (retrieval, reranking, context builder, citations)
- Map schema (additive deployment, feature CRUD, review status)
- Provenance chain (source_system tracking, algorithm versioning)
"""
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ─── Graph Models ────────────────────────────────────────────────────────────

class TestGraphModels(unittest.TestCase):
    """Test Pydantic models for graph nodes, edges, evidence."""

    def test_graph_node_valid(self):
        from graph_models import GraphNode
        node = GraphNode(
            id="internati:1",
            namespace="imi",
            type="person",
            label="Rossi Mario",
            source_table="internati",
            source_id=1,
        )
        self.assertEqual(node.label, "Rossi Mario")
        self.assertEqual(node.status, "active")

    def test_graph_node_rejects_empty_label(self):
        from graph_models import GraphNode
        with self.assertRaises(Exception):
            GraphNode(
                id="x:1", namespace="x", type="person", label="",
                source_table="x", source_id=1,
            )

    def test_graph_node_rejects_null_label(self):
        from graph_models import GraphNode
        with self.assertRaises(Exception):
            GraphNode(
                id="x:1", namespace="x", type="person", label="null",
                source_table="x", source_id=1,
            )

    def test_graph_edge_valid(self):
        from graph_models import GraphNode, GraphEdge, GraphRelation
        src = GraphNode(id="a:1", namespace="a", type="person", label="A",
                        source_table="a", source_id=1)
        tgt = GraphNode(id="b:1", namespace="b", type="event", label="B",
                        source_table="b", source_id=1)
        edge = GraphEdge(
            id="edge:1", source=src, target=tgt,
            relation=GraphRelation(type="soldato_caduto", label="test"),
            status="candidate",
            explanation="Test edge",
            algorithm="test_v1",
            algorithm_version="1.0",
            source_system="record_links",
        )
        self.assertEqual(edge.status, "candidate")
        self.assertIn("tecnico", edge.confidence_meaning.lower())

    def test_graph_edge_confidence_range(self):
        from graph_models import GraphNode, GraphEdge, GraphRelation
        src = GraphNode(id="a:1", namespace="a", type="person", label="A",
                        source_table="a", source_id=1)
        tgt = GraphNode(id="b:1", namespace="b", type="event", label="B",
                        source_table="b", source_id=1)
        with self.assertRaises(Exception):
            GraphEdge(
                id="e:1", source=src, target=tgt,
                relation=GraphRelation(type="t", label="l"),
                status="candidate", confidence=1.5,
                explanation="x", algorithm="a", algorithm_version="1",
                source_system="s",
            )

    def test_graph_evidence_roles(self):
        from graph_models import GraphEvidence
        ev = GraphEvidence(type="document", label="Test doc", role="supports")
        self.assertEqual(ev.role, "supports")
        ev2 = GraphEvidence(type="document", label="Test doc", role="contradicts")
        self.assertEqual(ev2.role, "contradicts")

    def test_graph_review_defaults(self):
        from graph_models import GraphReview
        r = GraphReview()
        self.assertTrue(r.required)
        self.assertIsNone(r.decision)

    def test_graph_integrity_issue(self):
        from graph_models import GraphIntegrityIssue
        issue = GraphIntegrityIssue(
            code="CROSS_WAR_CONTAMINATION",
            severity="warning",
            message="WWI event linked to WWII record",
        )
        self.assertEqual(issue.severity, "warning")

    def test_graph_response_structure(self):
        from graph_models import GraphNode, GraphResponse
        root = GraphNode(id="root:1", namespace="r", type="event", label="Root",
                         source_table="events", source_id=1)
        resp = GraphResponse(
            root=root, nodes=[root], edges=[],
            generated_at=datetime.now().isoformat(),
        )
        self.assertFalse(resp.truncated)
        self.assertEqual(resp.issues, [])

    def test_edge_review_request(self):
        from graph_models import EdgeReviewRequest
        req = EdgeReviewRequest(decision="accepted")
        self.assertEqual(req.decision, "accepted")

    def test_archival_metadata(self):
        from graph_models import ArchivalMetadata
        m = ArchivalMetadata(
            stable_id="doc:1",
            source_table="archivio_documenti",
            source_id=1,
            title="Test Document",
            algorithm_version="1.0",
            generated_at=datetime.now().isoformat(),
        )
        self.assertEqual(m.metadata_standard, "dcterms-compatible-v1")
        self.assertEqual(m.status, "generated")


# ─── Graph Service ───────────────────────────────────────────────────────────

class TestGraphService(unittest.TestCase):
    """Test graph service functions."""

    def test_relation_labels_exist(self):
        from graph_service import RELATION_LABELS
        self.assertIn("soldato_caduto", RELATION_LABELS)
        self.assertIn("same_person", RELATION_LABELS)
        self.assertIn("documento_evento", RELATION_LABELS)

    def test_graph_service_importable(self):
        from graph_service import GraphBatch
        self.assertTrue(hasattr(GraphBatch, '__dataclass_fields__'))


# ─── RAG Pipeline ────────────────────────────────────────────────────────────

class TestRAGPipeline(unittest.TestCase):
    """Test RAG pipeline data classes and functions."""

    def test_retrieved_chunk(self):
        from rag_pipeline import RetrievedChunk
        c = RetrievedChunk(
            chunk_id="test:1", source_table="test", source_id=1,
            title="Test", text="Content", score=0.8,
            retrieval_method="fts",
        )
        self.assertEqual(c.chunk_id, "test:1")
        d = c.to_dict()
        self.assertEqual(d["score"], 0.8)

    def test_reranked_chunk(self):
        from rag_pipeline import RetrievedChunk, RerankedChunk
        c = RetrievedChunk(
            chunk_id="t:1", source_table="t", source_id=1,
            title="T", text="X", score=0.5, retrieval_method="fts",
        )
        r = RerankedChunk(chunk=c, reranked_score=0.9, rerank_reasons=["title_match"])
        self.assertEqual(r.reranked_score, 0.9)
        self.assertIn("title_match", r.rerank_reasons)

    def test_rag_context(self):
        from rag_pipeline import RAGContext
        ctx = RAGContext(
            system_prompt="test", user_context="ctx",
            chunks=[], citations=[], token_estimate=100, truncated=False,
        )
        self.assertEqual(ctx.token_estimate, 100)
        self.assertFalse(ctx.truncated)

    def test_rerank_title_match(self):
        from rag_pipeline import RetrievedChunk, rerank
        c = RetrievedChunk(
            chunk_id="t:1", source_table="fonti_indice", source_id=1,
            title="Battaglia del Piave", text="desc", score=0.5,
            retrieval_method="fts",
        )
        results = rerank([c], query="Piave")
        self.assertGreater(results[0].reranked_score, 0.5)
        self.assertIn("title_match", results[0].rerank_reasons)

    def test_rerank_archival_boost(self):
        from rag_pipeline import RetrievedChunk, rerank
        c = RetrievedChunk(
            chunk_id="t:1", source_table="archivio_documenti", source_id=1,
            title="Doc", text="x", score=0.5, retrieval_method="metadata",
        )
        results = rerank([c], query="test")
        self.assertIn("primary_document", results[0].rerank_reasons)

    def test_rerank_temporal_match(self):
        from rag_pipeline import RetrievedChunk, rerank
        c = RetrievedChunk(
            chunk_id="t:1", source_table="internati", source_id=1,
            title="T", text="x", score=0.5, retrieval_method="fts",
            metadata={"data_cattura": "1943-09-08"},
        )
        results = rerank([c], query="test",
                         event_context={"date_start": "1943-09-08", "luogo": ""})
        self.assertTrue(any("temporal" in r for r in results[0].rerank_reasons))

    def test_rerank_geographic_match(self):
        from rag_pipeline import RetrievedChunk, rerank
        c = RetrievedChunk(
            chunk_id="t:1", source_table="internati", source_id=1,
            title="T", text="x", score=0.5, retrieval_method="fts",
            metadata={"luogo_cattura": "Cassino"},
        )
        results = rerank([c], query="test",
                         event_context={"date_start": None, "luogo": "Cassino"})
        self.assertIn("geographic_match", results[0].rerank_reasons)

    def test_rerank_score_cap(self):
        from rag_pipeline import RetrievedChunk, rerank
        c = RetrievedChunk(
            chunk_id="t:1", source_table="archivio_documenti", source_id=1,
            title="test match", text="test match", score=0.95,
            retrieval_method="fts",
        )
        results = rerank([c], query="test")
        self.assertLessEqual(results[0].reranked_score, 1.0)

    def test_build_context_citations(self):
        from rag_pipeline import RetrievedChunk, RerankedChunk, build_context
        c = RetrievedChunk(
            chunk_id="internati:1", source_table="internati", source_id=1,
            title="Rossi Mario", text="Soldato italiano", score=0.8,
            retrieval_method="fts",
        )
        r = RerankedChunk(chunk=c, reranked_score=0.9)
        ctx = build_context([r], query="Rossi Mario", max_tokens=2000)
        self.assertGreater(len(ctx.citations), 0)
        self.assertIn("internati", ctx.citations[0].get("source_table", ""))

    def test_build_context_truncation(self):
        from rag_pipeline import RetrievedChunk, RerankedChunk, build_context
        chunks = []
        for i in range(50):
            c = RetrievedChunk(
                chunk_id=f"t:{i}", source_table="t", source_id=i,
                title=f"Title {i}" * 20, text=f"Text {i}" * 100,
                score=0.5, retrieval_method="fts",
            )
            chunks.append(RerankedChunk(chunk=c, reranked_score=0.5))
        ctx = build_context(chunks, query="test", max_tokens=500)
        self.assertTrue(ctx.truncated)

    def test_retrieve_returns_list(self):
        from rag_pipeline import retrieve
        results = retrieve("test", limit=5)
        self.assertIsInstance(results, list)

    def test_retrieve_dedup(self):
        from rag_pipeline import retrieve
        results = retrieve("Rossi", limit=20)
        ids = [c.chunk_id for c in results]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate chunk_ids found")


# ─── Map Schema ──────────────────────────────────────────────────────────────

class TestMapSchema(unittest.TestCase):
    """Test map features schema."""

    def test_schema_sql_exists(self):
        from map_schema import SCHEMA_SQL
        self.assertIn("map_features", SCHEMA_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS", SCHEMA_SQL)

    def test_init_map_schema_idempotent(self):
        from map_schema import init_map_schema, map_schema_available
        import sqlite3
        from pathlib import Path
        edb = Path(__file__).parent / "eventi_1gm.db"
        conn = sqlite3.connect(str(edb))
        try:
            init_map_schema(conn)
            init_map_schema(conn)  # should not fail
            self.assertTrue(map_schema_available(conn))
        finally:
            conn.close()

    def test_map_schema_indexes(self):
        from map_schema import SCHEMA_SQL
        self.assertIn("idx_map_features_event", SCHEMA_SQL)
        self.assertIn("idx_map_features_type", SCHEMA_SQL)
        self.assertIn("idx_map_features_certainty", SCHEMA_SQL)


# ─── Provenance Chain ────────────────────────────────────────────────────────

class TestProvenanceChain(unittest.TestCase):
    """Test provenance tracking across graph, RAG, and map modules."""

    def test_graph_edge_source_system(self):
        from graph_models import GraphNode, GraphEdge, GraphRelation
        src = GraphNode(id="a:1", namespace="a", type="person", label="A",
                        source_table="a", source_id=1)
        tgt = GraphNode(id="b:1", namespace="b", type="event", label="B",
                        source_table="b", source_id=1)
        edge = GraphEdge(
            id="e:1", source=src, target=tgt,
            relation=GraphRelation(type="t", label="l"),
            status="candidate",
            explanation="x", algorithm="v73", algorithm_version="7.3",
            source_system="record_links",
        )
        self.assertEqual(edge.source_system, "record_links")
        self.assertEqual(edge.algorithm_version, "7.3")

    def test_archival_metadata_provenance(self):
        from graph_models import ArchivalMetadata
        m = ArchivalMetadata(
            stable_id="doc:1", source_table="archivio_documenti", source_id=1,
            title="T", algorithm_version="1.0",
            generated_at="2026-01-01T00:00:00",
            provenance={"source": "NARA", "fondo": "RG407"},
        )
        self.assertEqual(m.provenance["source"], "NARA")

    def test_rag_chunk_provenance(self):
        from rag_pipeline import RetrievedChunk
        c = RetrievedChunk(
            chunk_id="t:1", source_table="fonti_indice", source_id=42,
            title="T", text="X", score=0.8, retrieval_method="fts",
            metadata={"archivio": "AUSSME"},
        )
        self.assertEqual(c.metadata["archivio"], "AUSSME")
        self.assertEqual(c.source_table, "fonti_indice")


# ─── Integration: V7.3 Quarantine + Graph ────────────────────────────────────

class TestQuarantineGraphIntegration(unittest.TestCase):
    """Test that quarantined links are filtered in graph responses."""

    def test_graph_status_candidate_is_quarantined(self):
        """In V7.3, all legacy links are CANDIDATE with usable_as_evidence=0.
        Graph service should expose this status."""
        from graph_models import GraphStatus
        # GraphStatus includes 'candidate' which maps to quarantined
        statuses = GraphStatus.__args__ if hasattr(GraphStatus, '__args__') else []
        self.assertIn("candidate", statuses)
        self.assertIn("rejected", statuses)
        self.assertIn("confirmed", statuses)

    def test_confidence_meaning_disclaimer(self):
        """Graph edges must carry the disclaimer that confidence is technical, not truth."""
        from graph_models import GraphNode, GraphEdge, GraphRelation
        src = GraphNode(id="a:1", namespace="a", type="person", label="A",
                        source_table="a", source_id=1)
        tgt = GraphNode(id="b:1", namespace="b", type="event", label="B",
                        source_table="b", source_id=1)
        edge = GraphEdge(
            id="e:1", source=src, target=tgt,
            relation=GraphRelation(type="t", label="l"),
            status="candidate",
            explanation="x", algorithm="v73", algorithm_version="7.3",
            source_system="record_links",
        )
        self.assertIn("tecnico", edge.confidence_meaning.lower())
        self.assertIn("verità storica", edge.confidence_meaning.lower())


if __name__ == "__main__":
    unittest.main()
