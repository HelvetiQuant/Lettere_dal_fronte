"""V7 Legacy Derived Data Quarantine & Regeneration.

This module implements:
  - DerivedDataInventory: identifies all derived tables and their sources
  - QuarantineManager: moves derived tables to quarantine namespace
  - RegenerationPlan: plans regeneration of derived data through V7 pipeline
  - QuarantineReport: structured report of quarantine status

Key principles:
  1. Derived tables (record_links, event_links, collegamenti, etc.) are QUARANTINED
  2. Raw data tables are NEVER touched
  3. Quarantine means: rename table to _quarantine_<name>, mark as deprecated
  4. Regeneration means: re-derive from raw data through V7 pipeline
  5. All quarantine operations are REVERSIBLE
"""
from __future__ import annotations

import os
import sqlite3
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# ─── Derived table inventory ────────────────────────────────────────────────

DERIVED_TABLES = [
    {
        "name": "record_links",
        "source_tables": ["internati", "caduti_albooro", "decorati_nastroazzurro"],
        "source_script": "_gen_record_links.py",
        "deprecated_reason": "Star topology with arbitrary hub, no evidence, O(N×M) scan",
        "v7_replacement": "v7_fusion_engine.SourceFamilyGraph",
    },
    {
        "name": "event_links",
        "source_tables": ["eventi_1gm", "internati"],
        "source_script": "_gen_event_links.py",
        "deprecated_reason": "Unverified event-person links, no provenance chain",
        "v7_replacement": "v7_event_aggregate.EventOntology",
    },
    {
        "name": "collegamenti",
        "source_tables": ["fonti_indice", "internati"],
        "source_script": "linking pipeline",
        "deprecated_reason": "Unverified links, no independence check",
        "v7_replacement": "v7_fusion_engine.IndependenceAssessor",
    },
    {
        "name": "graph_nodes",
        "source_tables": ["internati", "caduti_albooro", "decorati_nastroazzurro"],
        "source_script": "graph_service.py",
        "deprecated_reason": "Derived from unverified legacy links",
        "v7_replacement": "v7_identity_model.CanonicalIdentity",
    },
    {
        "name": "graph_edges",
        "source_tables": ["record_links", "event_links", "collegamenti"],
        "source_script": "graph_service.py",
        "deprecated_reason": "Derived from unverified legacy links",
        "v7_replacement": "v7_fusion_engine.SourceFamilyGraph",
    },
]


@dataclass
class QuarantineEntry:
    """A single quarantine entry."""
    original_name: str
    quarantine_name: str
    row_count: int = 0
    deprecated_reason: str = ""
    v7_replacement: str = ""
    quarantined_at: str = ""
    reversible: bool = True
    status: str = "PENDING"  # PENDING|QUARANTINED|REGENERATED|VERIFIED


class DerivedDataInventory:
    """Inventories all derived tables in the database."""

    def __init__(self, db_path: str = "imi_internati.db"):
        self.db_path = db_path

    def scan(self) -> List[Dict[str, Any]]:
        """Scan database for derived tables and return their status."""
        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            for entry in DERIVED_TABLES:
                name = entry["name"]
                qname = f"_quarantine_{name}"

                # Check if original table exists
                orig_exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (name,),
                ).fetchone() is not None

                # Check if quarantine table exists
                q_exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (qname,),
                ).fetchone() is not None

                # Get row count
                row_count = 0
                table_name = name if orig_exists else (qname if q_exists else None)
                if table_name:
                    try:
                        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    except Exception:
                        pass

                status = "PENDING"
                if q_exists and not orig_exists:
                    status = "QUARANTINED"
                elif not orig_exists and not q_exists:
                    status = "ABSENT"
                elif orig_exists and q_exists:
                    status = "DUPLICATE"

                results.append({
                    "name": name,
                    "quarantine_name": qname,
                    "exists": orig_exists,
                    "quarantine_exists": q_exists,
                    "row_count": row_count,
                    "status": status,
                    "deprecated_reason": entry["deprecated_reason"],
                    "v7_replacement": entry["v7_replacement"],
                })
            conn.close()
        except Exception as e:
            logger.error(f"Derived data inventory failed: {e}")

        return results


class QuarantineManager:
    """Manages quarantine of derived tables.

    Quarantine means: rename table to _quarantine_<name>
    This is reversible — the table can be restored by renaming back.
    """

    def __init__(self, db_path: str = "imi_internati.db"):
        self.db_path = db_path
        self._inventory = DerivedDataInventory(db_path)

    def quarantine_table(self, table_name: str, dry_run: bool = True) -> Dict[str, Any]:
        """Quarantine a single table by renaming it."""
        qname = f"_quarantine_{table_name}"

        try:
            conn = sqlite3.connect(self.db_path)

            # Check if table exists
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()

            if not exists:
                return {"ok": False, "error": f"Table {table_name} does not exist"}

            # Check if quarantine name already exists
            q_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (qname,),
            ).fetchone()

            if q_exists:
                return {"ok": False, "error": f"Quarantine table {qname} already exists"}

            # Get row count
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

            if dry_run:
                conn.close()
                return {
                    "ok": True,
                    "dry_run": True,
                    "table": table_name,
                    "quarantine_name": qname,
                    "row_count": row_count,
                    "action": f"Would rename {table_name} -> {qname}",
                }

            # Execute rename
            conn.execute(f"ALTER TABLE {table_name} RENAME TO {qname}")
            conn.commit()
            conn.close()

            logger.info(f"Quarantined {table_name} -> {qname} ({row_count} rows)")
            return {
                "ok": True,
                "dry_run": False,
                "table": table_name,
                "quarantine_name": qname,
                "row_count": row_count,
                "action": f"Renamed {table_name} -> {qname}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def restore_table(self, table_name: str, dry_run: bool = True) -> Dict[str, Any]:
        """Restore a quarantined table by renaming it back."""
        qname = f"_quarantine_{table_name}"

        try:
            conn = sqlite3.connect(self.db_path)

            q_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (qname,),
            ).fetchone()

            if not q_exists:
                return {"ok": False, "error": f"Quarantine table {qname} does not exist"}

            orig_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()

            if orig_exists:
                return {"ok": False, "error": f"Table {table_name} already exists (would conflict)"}

            row_count = conn.execute(f"SELECT COUNT(*) FROM {qname}").fetchone()[0]

            if dry_run:
                conn.close()
                return {
                    "ok": True,
                    "dry_run": True,
                    "table": table_name,
                    "quarantine_name": qname,
                    "row_count": row_count,
                    "action": f"Would restore {qname} -> {table_name}",
                }

            conn.execute(f"ALTER TABLE {qname} RENAME TO {table_name}")
            conn.commit()
            conn.close()

            return {
                "ok": True,
                "dry_run": False,
                "table": table_name,
                "row_count": row_count,
                "action": f"Restored {qname} -> {table_name}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def quarantine_all(self, dry_run: bool = True) -> List[Dict[str, Any]]:
        """Quarantine all derived tables."""
        results = []
        for entry in DERIVED_TABLES:
            result = self.quarantine_table(entry["name"], dry_run=dry_run)
            result["deprecated_reason"] = entry["deprecated_reason"]
            result["v7_replacement"] = entry["v7_replacement"]
            results.append(result)
        return results


class RegenerationPlan:
    """Plans regeneration of derived data through V7 pipeline."""

    def __init__(self):
        self._steps: List[Dict[str, Any]] = []

    def build_plan(self) -> List[Dict[str, Any]]:
        """Build regeneration plan for all quarantined derived data."""
        self._steps = [
            {
                "step": 1,
                "target": "canonical_identities",
                "source": "raw tables (internati, caduti_*, decorati_*)",
                "v7_module": "v7_identity_model.IdentityResolver",
                "action": "Resolve all persons to CanonicalIdentity objects",
                "depends_on": [],
            },
            {
                "step": 2,
                "target": "source_family_graph",
                "source": "ProviderObservation records",
                "v7_module": "v7_fusion_engine.SourceFamilyGraph",
                "action": "Build source family graph from all observations",
                "depends_on": [1],
            },
            {
                "step": 3,
                "target": "independence_groups",
                "source": "source_family_graph",
                "v7_module": "v7_fusion_engine.IndependenceAssessor",
                "action": "Assess independence between all source pairs",
                "depends_on": [2],
            },
            {
                "step": 4,
                "target": "fused_claims",
                "source": "ProviderObservation + independence_groups",
                "v7_module": "v7_fusion_engine.FusionEngine",
                "action": "Fuse claims from multiple providers with independence weighting",
                "depends_on": [3],
            },
            {
                "step": 5,
                "target": "event_hierarchy",
                "source": "eventi_1gm + event_aliases",
                "v7_module": "v7_event_aggregate.EventOntology",
                "action": "Build canonical event hierarchy with aliases",
                "depends_on": [],
            },
            {
                "step": 6,
                "target": "aggregate_results",
                "source": "raw tables",
                "v7_module": "v7_event_aggregate.AggregateDefinitionRegistry",
                "action": "Execute all registered aggregate definitions",
                "depends_on": [1, 5],
            },
            {
                "step": 7,
                "target": "evidence_snapshots",
                "source": "fused_claims + independence_groups + corrections",
                "v7_module": "evidence_snapshot_v7.EvidenceSnapshotV7",
                "action": "Build V7 evidence snapshots for each resolved identity",
                "depends_on": [4],
            },
        ]
        return self._steps
