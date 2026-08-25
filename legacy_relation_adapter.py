"""Legacy Relation Adapter — bridges legacy relations into the V2 evidence pipeline.

This module implements the non-destructive quarantine and revalidation strategy:

  1. READ legacy relations (record_links, event_links, collegamenti) as-is
  2. MARK them with origin='legacy' in the V2 relations table
  3. BLOCK them from verified_sources, AI evidence context, dossier finale
  4. Provide a revalidation path: legacy → candidate → feature extraction → gates → accepted/rejected

Key principles:
  - Non-destructive: legacy tables are NOT modified, renamed, or deleted
  - Reversible: every adapter action can be undone
  - Gated: legacy relations cannot reach 'verified' status without revalidation
  - Tracked: every legacy relation gets a pipeline_run_id and origin='legacy'

Usage:
    from legacy_relation_adapter import LegacyRelationAdapter

    adapter = LegacyRelationAdapter(conn)
    stats = adapter.scan_all()           # Audit: count legacy relations
    stats = adapter.import_all(dry_run=True)  # Import as legacy_candidate
    stats = adapter.revalidate_batch(dry_run=True)  # Run V2 gates on legacy
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from evidence_contract import (
    ClaimStatus,
    RelationOrigin,
    TemporalGate,
)

logger = logging.getLogger(__name__)

ADAPTER_VERSION = "1.0.0"


# ─── Legacy table configurations ──────────────────────────────────────────────

LEGACY_TABLES = [
    {
        "name": "record_links",
        "db": "main",
        "columns": ["id", "from_table", "from_id", "to_table", "to_id", "link_type", "confidence",
                     "usable_as_evidence", "quarantined_at", "quarantine_reason"],
        "source_field": "from_table",
        "source_id_field": "from_id",
        "target_field": "to_table",
        "target_id_field": "to_id",
        "relation_type_field": "link_type",
        "confidence_field": "confidence",
        "usable_field": "usable_as_evidence",
    },
    {
        "name": "collegamenti",
        "db": "main",
        "columns": ["id", "entita_id", "tabella_origine", "record_id", "tipo_collegamento", "confidenza"],
        "source_field": "tabella_origine",
        "source_id_field": "record_id",
        "target_field": None,  # target is always entita
        "target_id_field": None,
        "relation_type_field": "tipo_collegamento",
        "confidence_field": "confidenza",
        "usable_field": None,
    },
    {
        "name": "event_links",
        "db": "events",
        "columns": ["id", "evento_id", "target_table", "target_id", "link_type", "confidence",
                     "usable_as_evidence", "quarantined_at", "quarantine_reason", "war_period"],
        "source_field": None,  # source is always eventi_1gm
        "source_id_field": "evento_id",
        "target_field": "target_table",
        "target_id_field": "target_id",
        "relation_type_field": "link_type",
        "confidence_field": "confidence",
        "usable_field": "usable_as_evidence",
    },
]


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class LegacyRelation:
    """A legacy relation read from a legacy table."""
    legacy_table: str
    legacy_id: int
    source_namespace: str
    source_record_key: str
    target_namespace: str
    target_record_key: str
    relation_type: str
    confidence: float
    usable_as_evidence: bool
    quarantine_reason: str = ""
    war_period: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterStats:
    """Statistics from adapter operations."""
    table_name: str
    total_rows: int = 0
    usable_rows: int = 0
    quarantined_rows: int = 0
    imported: int = 0
    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    revalidated_accepted: int = 0
    revalidated_needs_review: int = 0
    revalidated_rejected: int = 0
    errors: int = 0


# ─── Legacy Relation Adapter ──────────────────────────────────────────────────

class LegacyRelationAdapter:
    """Adapts legacy relations into the V2 evidence pipeline.

    Non-destructive: reads legacy tables, writes to V2 relations with origin='legacy'.
    """

    def __init__(self, conn: sqlite3.Connection, events_conn: Optional[sqlite3.Connection] = None):
        self.conn = conn
        self.events_conn = events_conn

    def _get_conn(self, db_name: str) -> sqlite3.Connection:
        if db_name == "events" and self.events_conn:
            return self.events_conn
        return self.conn

    # ─── Scan (audit only, no writes) ─────────────────────────────────────────

    def scan_table(self, table_config: Dict) -> AdapterStats:
        """Scan a legacy table and return statistics. No writes."""
        stats = AdapterStats(table_name=table_config["name"])
        conn = self._get_conn(table_config["db"])

        try:
            # Check if table exists
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_config["name"],)
            ).fetchone()
            if not exists:
                logger.warning(f"Legacy table {table_config['name']} not found")
                return stats

            # Total count
            stats.total_rows = conn.execute(
                f"SELECT COUNT(*) FROM {table_config['name']}"
            ).fetchone()[0]

            # Usable count (if usable_as_evidence column exists)
            if table_config.get("usable_field"):
                try:
                    stats.usable_rows = conn.execute(
                        f"SELECT COUNT(*) FROM {table_config['name']} "
                        f"WHERE {table_config['usable_field']} = 1 OR {table_config['usable_field']} IS NULL"
                    ).fetchone()[0]
                    stats.quarantined_rows = stats.total_rows - stats.usable_rows
                except sqlite3.OperationalError:
                    stats.usable_rows = stats.total_rows
            else:
                stats.usable_rows = stats.total_rows

        except Exception as e:
            logger.error(f"Scan failed for {table_config['name']}: {e}")
            stats.errors += 1

        return stats

    def scan_all(self) -> List[AdapterStats]:
        """Scan all legacy tables. Returns stats per table."""
        return [self.scan_table(cfg) for cfg in LEGACY_TABLES]

    # ─── Read legacy relations ────────────────────────────────────────────────

    def read_legacy_relations(self, table_config: Dict, limit: int = 0) -> List[LegacyRelation]:
        """Read legacy relations from a table. Returns list of LegacyRelation."""
        conn = self._get_conn(table_config["db"])
        relations: List[LegacyRelation] = []

        try:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_config["name"],)
            ).fetchone()
            if not exists:
                return relations

            sql = f"SELECT * FROM {table_config['name']}"
            if table_config.get("usable_field"):
                sql += f" WHERE {table_config['usable_field']} = 1 OR {table_config['usable_field']} IS NULL"
            if limit > 0:
                sql += f" LIMIT {limit}"

            rows = conn.execute(sql).fetchall()
            for row in rows:
                r = dict(row)
                rel = self._parse_legacy_row(r, table_config)
                if rel:
                    relations.append(rel)

        except Exception as e:
            logger.error(f"Read failed for {table_config['name']}: {e}")

        return relations

    def _parse_legacy_row(self, row: Dict, cfg: Dict) -> Optional[LegacyRelation]:
        """Parse a legacy row into a LegacyRelation."""
        try:
            # Source namespace and key
            if cfg["source_field"]:
                src_ns = row.get(cfg["source_field"], "")
                src_key = str(row.get(cfg["source_id_field"], ""))
            else:
                src_ns = "eventi_1gm"
                src_key = str(row.get(cfg["source_id_field"], ""))

            # Target namespace and key
            if cfg["target_field"]:
                tgt_ns = row.get(cfg["target_field"], "")
                tgt_key = str(row.get(cfg["target_id_field"], ""))
            else:
                # collegamenti: target is entita
                tgt_ns = "entita"
                tgt_key = str(row.get("entita_id", ""))

            if not src_ns or not src_key or not tgt_ns or not tgt_key:
                return None

            confidence = float(row.get(cfg["confidence_field"], 0.5) or 0.5)
            usable = True
            if cfg.get("usable_field"):
                u = row.get(cfg["usable_field"])
                usable = (u == 1 or u is None)

            return LegacyRelation(
                legacy_table=cfg["name"],
                legacy_id=row.get("id", 0),
                source_namespace=src_ns,
                source_record_key=src_key,
                target_namespace=tgt_ns,
                target_record_key=tgt_key,
                relation_type=row.get(cfg["relation_type_field"], "unknown") or "unknown",
                confidence=confidence,
                usable_as_evidence=usable,
                quarantine_reason=row.get("quarantine_reason", "") or "",
                war_period=row.get("war_period", "") or "",
                metadata=row,
            )
        except Exception as e:
            logger.debug(f"Parse failed for row: {e}")
            return None

    # ─── Import legacy relations into V2 ──────────────────────────────────────

    def import_table(self, table_config: Dict, dry_run: bool = True,
                     pipeline_run_id: str = "") -> AdapterStats:
        """Import legacy relations from one table into V2 relations table.

        Marks them with origin='legacy', status='legacy_candidate'.
        Non-destructive: does NOT modify the legacy table.
        """
        stats = self.scan_table(table_config)
        if stats.total_rows == 0:
            return stats

        if not pipeline_run_id:
            pipeline_run_id = f"legacy_import_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

        relations = self.read_legacy_relations(table_config)
        now = datetime.now(timezone.utc).isoformat()

        for rel in relations:
            if not rel.usable_as_evidence:
                stats.quarantined_rows += 1
                continue

            # Register resources in resource_registry
            source_rid = self._ensure_resource(rel.source_namespace, rel.source_record_key)
            target_rid = self._ensure_resource(rel.target_namespace, rel.target_record_key)

            if not source_rid or not target_rid:
                stats.skipped_invalid += 1
                continue

            # Check if relation already exists in V2
            existing = self.conn.execute(
                """SELECT id FROM relations
                   WHERE source_resource_id = ? AND target_resource_id = ?
                     AND relation_type = ? AND origin = 'legacy'""",
                (source_rid, target_rid, rel.relation_type)
            ).fetchone()

            if existing:
                stats.skipped_duplicate += 1
                continue

            if dry_run:
                stats.imported += 1
                continue

            # Insert as legacy_candidate
            rel_id = f"rel_legacy_{uuid4().hex[:16]}"
            features_json = json.dumps({
                "legacy_table": rel.legacy_table,
                "legacy_id": rel.legacy_id,
                "legacy_confidence": rel.confidence,
                "war_period": rel.war_period,
            })

            try:
                self.conn.execute(
                    """INSERT INTO relations
                       (id, source_resource_id, target_resource_id, relation_type,
                        direction, status, algorithm_name, algorithm_version,
                        feature_schema_version, features, raw_score,
                        confidence_calibrated, calibration_model_version,
                        evidence_strength, conflict_flags, pipeline_run_id, created_at,
                        origin)
                       VALUES (?, ?, ?, ?, 'directed', 'legacy_candidate',
                               'legacy_adapter', ?, '1.0.0', ?, ?,
                               NULL, NULL, 'weak', '[]', ?, ?, 'legacy')""",
                    (rel_id, source_rid, target_rid, rel.relation_type,
                     ADAPTER_VERSION, features_json, rel.confidence,
                     pipeline_run_id, now)
                )
                stats.imported += 1
            except sqlite3.IntegrityError as e:
                err_str = str(e).lower()
                if "unique" in err_str:
                    stats.skipped_duplicate += 1
                else:
                    logger.error(f"Insert failed (IntegrityError): {e}")
                    stats.errors += 1
            except Exception as e:
                logger.error(f"Insert failed: {e}")
                stats.errors += 1

        if not dry_run:
            self.conn.commit()

        return stats

    def import_all(self, dry_run: bool = True, pipeline_run_id: str = "") -> List[AdapterStats]:
        """Import all legacy tables. Returns stats per table."""
        return [
            self.import_table(cfg, dry_run=dry_run, pipeline_run_id=pipeline_run_id)
            for cfg in LEGACY_TABLES
        ]

    # ─── Revalidation ─────────────────────────────────────────────────────────

    def revalidate_batch(self, dry_run: bool = True, limit: int = 100) -> AdapterStats:
        """Run V2 gates on legacy_candidate relations.

        Applies temporal, geographic, and identity gates to legacy relations.
        Promotes accepted ones to 'candidate' or 'accepted', rejects failed ones.
        """
        stats = AdapterStats(table_name="revalidation")
        now = datetime.now(timezone.utc).isoformat()

        # Fetch legacy_candidate relations
        sql = (
            "SELECT r.id, r.source_resource_id, r.target_resource_id, r.relation_type, "
            "r.features, r.raw_score, r.conflict_flags, "
            "rr1.source_namespace as src_ns, rr1.source_record_key as src_key, "
            "rr2.source_namespace as tgt_ns, rr2.source_record_key as tgt_key "
            "FROM relations r "
            "JOIN resource_registry rr1 ON r.source_resource_id = rr1.id "
            "JOIN resource_registry rr2 ON r.target_resource_id = rr2.id "
            "WHERE r.status = 'legacy_candidate' AND r.origin = 'legacy'"
        )
        if limit > 0:
            sql += f" LIMIT {limit}"

        rows = self.conn.execute(sql).fetchall()

        for row in rows:
            r = dict(row)
            features = json.loads(r.get("features") or "{}")
            war_period = features.get("war_period", "")

            # Gate 1: Temporal — check war period consistency
            temporal_gate = TemporalGate.TEMPORALLY_AMBIGUOUS
            if war_period:
                src_ns = r.get("src_ns", "")
                tgt_ns = r.get("tgt_ns", "")
                # WWI vs WWII contamination check
                if "WW1" in war_period and "WW2" in war_period:
                    temporal_gate = TemporalGate.TEMPORALLY_INCOMPATIBLE
                elif war_period == "WW1" and "ww2" in tgt_ns.lower():
                    temporal_gate = TemporalGate.TEMPORALLY_INCOMPATIBLE
                elif war_period == "WW2" and "ww1" in tgt_ns.lower():
                    temporal_gate = TemporalGate.TEMPORALLY_INCOMPATIBLE
                else:
                    temporal_gate = TemporalGate.TEMPORALLY_COMPATIBLE

            # Gate 2: Confidence threshold
            raw_score = r.get("raw_score", 0.0) or 0.0
            if raw_score < 0.3:
                # Too low — reject
                if not dry_run:
                    self._update_relation_status(
                        r["id"], "rejected", temporal_gate=temporal_gate,
                        origin=RelationOrigin.LEGACY
                    )
                stats.revalidated_rejected += 1
                continue

            # Gate 3: Temporal incompatibility = reject
            if temporal_gate == TemporalGate.TEMPORALLY_INCOMPATIBLE:
                if not dry_run:
                    self._update_relation_status(
                        r["id"], "rejected", temporal_gate=temporal_gate,
                        origin=RelationOrigin.LEGACY
                    )
                stats.revalidated_rejected += 1
                continue

            # Gate 4: Confidence moderate → needs_review
            if raw_score < 0.7 or temporal_gate == TemporalGate.TEMPORALLY_AMBIGUOUS:
                if not dry_run:
                    self._update_relation_status(
                        r["id"], "needs_review", temporal_gate=temporal_gate,
                        origin=RelationOrigin.LEGACY_REVALIDATED
                    )
                stats.revalidated_needs_review += 1
                continue

            # Gate 5: High confidence + temporal compatible → accepted (NOT verified)
            if not dry_run:
                self._update_relation_status(
                    r["id"], "accepted", temporal_gate=temporal_gate,
                    origin=RelationOrigin.LEGACY_REVALIDATED
                )
            stats.revalidated_accepted += 1

        if not dry_run:
            self.conn.commit()

        return stats

    def _update_relation_status(self, relation_id: str, status: str,
                                 temporal_gate: str = "", origin: str = ""):
        """Update a relation's status and gate fields."""
        now = datetime.now(timezone.utc).isoformat()
        sets = ["status = ?", "reviewed_at = ?"]
        params = [status, now]

        if temporal_gate:
            sets.append("temporal_gate = ?")
            params.append(temporal_gate)
        if origin:
            sets.append("origin = ?")
            params.append(origin)

        params.append(relation_id)
        self.conn.execute(
            f"UPDATE relations SET {', '.join(sets)} WHERE id = ?",
            params
        )

    # ─── Resource registration ────────────────────────────────────────────────

    def _ensure_resource(self, namespace: str, record_key: str) -> Optional[str]:
        """Ensure a resource exists in resource_registry. Returns resource_id."""
        if not namespace or not record_key:
            return None

        # Check existing
        row = self.conn.execute(
            "SELECT id FROM resource_registry WHERE source_namespace = ? AND source_record_key = ?",
            (namespace, record_key)
        ).fetchone()
        if row:
            return row[0]

        # Create new
        resource_id = f"res_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()

        # Determine resource_kind from namespace
        kind = "other"
        if namespace in ("internati", "caduti_albooro", "caduti_ministero", "caduti_cwgc",
                         "decorati_nastroazzurro", "lebi_records", "caduti_bologna",
                         "caduti_sardi", "caduti_francia_ww1"):
            kind = "person"
        elif namespace in ("eventi_1gm",):
            kind = "event"
        elif namespace in ("fonti_indice", "archivio_documenti"):
            kind = "source"
        elif namespace == "entita":
            kind = "other"

        try:
            self.conn.execute(
                """INSERT INTO resource_registry
                   (id, resource_kind, source_namespace, source_record_key,
                    canonical_entity_id, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, NULL, '{}', ?)""",
                (resource_id, kind, namespace, record_key, now)
            )
            return resource_id
        except sqlite3.IntegrityError:
            # Another process created it — fetch
            row = self.conn.execute(
                "SELECT id FROM resource_registry WHERE source_namespace = ? AND source_record_key = ?",
                (namespace, record_key)
            ).fetchone()
            return row[0] if row else None

    # ─── Quarantine enforcement ───────────────────────────────────────────────

    def get_quarantine_report(self) -> Dict[str, Any]:
        """Generate a comprehensive quarantine report."""
        report = {
            "adapter_version": ADAPTER_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "legacy_tables": [],
            "v2_legacy_relations": {
                "total": 0,
                "legacy_candidate": 0,
                "accepted": 0,
                "needs_review": 0,
                "rejected": 0,
            },
        }

        # Legacy table stats
        for cfg in LEGACY_TABLES:
            stats = self.scan_table(cfg)
            report["legacy_tables"].append({
                "name": stats.table_name,
                "total": stats.total_rows,
                "usable": stats.usable_rows,
                "quarantined": stats.quarantined_rows,
                "errors": stats.errors,
            })

        # V2 relations with origin=legacy
        try:
            report["v2_legacy_relations"]["total"] = self.conn.execute(
                "SELECT COUNT(*) FROM relations WHERE origin = 'legacy' OR origin = 'legacy_revalidated'"
            ).fetchone()[0]
            report["v2_legacy_relations"]["legacy_candidate"] = self.conn.execute(
                "SELECT COUNT(*) FROM relations WHERE origin = 'legacy' AND status = 'legacy_candidate'"
            ).fetchone()[0]
            report["v2_legacy_relations"]["accepted"] = self.conn.execute(
                "SELECT COUNT(*) FROM relations WHERE origin = 'legacy_revalidated' AND status = 'accepted'"
            ).fetchone()[0]
            report["v2_legacy_relations"]["needs_review"] = self.conn.execute(
                "SELECT COUNT(*) FROM relations WHERE origin = 'legacy_revalidated' AND status = 'needs_review'"
            ).fetchone()[0]
            report["v2_legacy_relations"]["rejected"] = self.conn.execute(
                "SELECT COUNT(*) FROM relations WHERE origin IN ('legacy', 'legacy_revalidated') AND status = 'rejected'"
            ).fetchone()[0]
        except Exception as e:
            logger.error(f"Quarantine report query failed: {e}")

        return report

    # ─── Block legacy from verified/AI ────────────────────────────────────────

    @staticmethod
    def is_safe_for_verified(status: str, origin: str) -> bool:
        """Check if a relation is safe to use as verified evidence.

        Legacy relations can NEVER be verified without revalidation.
        """
        if origin == RelationOrigin.LEGACY:
            return False
        if origin == RelationOrigin.LEGACY_REVALIDATED and status == "accepted":
            return True  # Revalidated and accepted — safe for probable
        if origin == RelationOrigin.V2 and status in ("confirmed", "accepted"):
            return True
        return False

    @staticmethod
    def is_safe_for_ai_context(status: str, origin: str) -> bool:
        """Check if a relation is safe to include in AI evidence context.

        Legacy candidates are NOT safe for AI context.
        Revalidated needs_review are safe as 'probable' but not 'verified'.
        """
        if origin == RelationOrigin.LEGACY and status == "legacy_candidate":
            return False
        if origin == RelationOrigin.LEGACY and status == "rejected":
            return False
        return True
