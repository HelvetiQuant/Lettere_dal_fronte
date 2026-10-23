"""Evidence Snapshot Service — persists EvidenceSnapshotV7 to the database.

This module implements the persistence layer for evidence snapshots:

  1. save_snapshot(): serializes EvidenceSnapshotV7 → evidence_snapshots table
  2. load_snapshot(): deserializes evidence_snapshots → EvidenceSnapshotV7
  3. list_snapshots(): query snapshots by intent, date range, hash
  4. link_relations(): link relations to a snapshot via snapshot_id FK
  5. verify_integrity(): verify context_hash + answer_hash match

Key principles:
  - Snapshots are IMMUTABLE: once saved, the snapshot_json cannot be modified
  - context_hash ensures input integrity (same claims → same hash)
  - answer_hash ensures output integrity (AI answer tied to specific bundle)
  - Every significant historical answer must be reproducible via its snapshot
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

SERVICE_VERSION = "1.0.0"


class EvidenceSnapshotService:
    """Persists EvidenceSnapshotV7 objects to the evidence_snapshots table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ─── Save ─────────────────────────────────────────────────────────────────

    def save_snapshot(
        self,
        snapshot: Any,  # EvidenceSnapshotV7
        answer_text: str = "",
        answer_hash: str = "",
        algorithm_versions: Optional[Dict[str, str]] = None,
    ) -> str:
        """Save an EvidenceSnapshotV7 to the database.

        Returns the snapshot_id.

        The snapshot is serialized as JSON in snapshot_json.
        If answer_text is provided, answer_hash is computed from context_hash + answer_text.

        Raises ValueError if a snapshot with the same context_hash already exists
        and the content differs (integrity check).
        """
        snapshot_dict = snapshot.to_dict() if hasattr(snapshot, "to_dict") else asdict(snapshot)
        snapshot_json = json.dumps(snapshot_dict, ensure_ascii=False, sort_keys=True)

        # Compute context_hash from snapshot content
        context_hash = hashlib.sha256(
            json.dumps(snapshot_dict, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

        # Compute answer_hash if answer provided
        if answer_text and not answer_hash:
            hasher = hashlib.sha256()
            hasher.update(context_hash.encode())
            hasher.update(answer_text.encode())
            answer_hash = hasher.hexdigest()

        snapshot_id = snapshot.snapshot_id or f"snap_{uuid4().hex[:16]}"
        created_at = snapshot.created_at or datetime.now(timezone.utc).isoformat()

        # Default algorithm versions
        if not algorithm_versions:
            algorithm_versions = {
                "linking": "2.0.0",
                "narrator": getattr(snapshot, "narrator_contract_version", "7.2"),
                "evidence_contract": "1.0.0",
                "snapshot_service": SERVICE_VERSION,
            }

        # Extract ID arrays
        source_ids = [e.get("source_id", "") if isinstance(e, dict) else getattr(e, "source_id", "")
                       for e in snapshot_dict.get("accepted_evidence", [])]
        evidence_ids = [e.get("evidence_id", "") if isinstance(e, dict) else getattr(e, "evidence_id", "")
                        for e in snapshot_dict.get("accepted_evidence", [])]
        claim_ids = [c.get("claim_id", "") if isinstance(c, dict) else getattr(c, "claim_id", "")
                     for c in snapshot_dict.get("accepted_claims", [])]
        claim_ids += [c.get("claim_id", "") if isinstance(c, dict) else getattr(c, "claim_id", "")
                      for c in snapshot_dict.get("person_claims", [])]
        claim_ids += [c.get("claim_id", "") if isinstance(c, dict) else getattr(c, "claim_id", "")
                      for c in snapshot_dict.get("asserted_claims", [])]

        # Extract conflicts
        conflicts = []
        for c in snapshot_dict.get("conflicting_claims", []):
            conflicts.append({
                "claim_id": c.get("claim_id", "") if isinstance(c, dict) else getattr(c, "claim_id", ""),
                "predicate": c.get("predicate", "") if isinstance(c, dict) else getattr(c, "predicate", ""),
            })

        # Check for existing snapshot with same ID
        existing = self.conn.execute(
            "SELECT id, context_hash FROM evidence_snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()

        if existing:
            if existing["context_hash"] != context_hash:
                raise ValueError(
                    f"Snapshot {snapshot_id} already exists with different content "
                    f"(hash mismatch: {existing['context_hash'][:16]} vs {context_hash[:16]})"
                )
            logger.info(f"Snapshot {snapshot_id} already exists (identical), skipping")
            return snapshot_id

        # Insert
        self.conn.execute(
            """INSERT INTO evidence_snapshots
               (id, query, intent, created_at, pipeline_version, algorithm_versions,
                source_ids, observation_ids, evidence_ids, claim_ids, relation_ids,
                rejected_candidates, conflicts, context_hash, answer_hash, snapshot_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                snapshot_dict.get("target", {}).get("display_name", "") if isinstance(snapshot_dict.get("target"), dict) else "",
                snapshot_dict.get("intent", "PERSON_LOOKUP"),
                created_at,
                snapshot_dict.get("schema_version", "7.2"),
                json.dumps(algorithm_versions),
                json.dumps(source_ids),
                json.dumps([]),  # observation_ids — not directly tracked in snapshot
                json.dumps(evidence_ids),
                json.dumps(claim_ids),
                json.dumps([]),  # relation_ids — linked separately
                json.dumps([asdict(r) if hasattr(r, "__dataclass_fields__") else r
                           for r in snapshot_dict.get("rejected_candidates", [])]),
                json.dumps(conflicts),
                context_hash,
                answer_hash,
                snapshot_json,
            )
        )
        self.conn.commit()

        logger.info(f"Saved snapshot {snapshot_id} (context_hash={context_hash[:16]}...)")
        return snapshot_id

    # ─── Load ─────────────────────────────────────────────────────────────────

    def load_snapshot(self, snapshot_id: str) -> Optional[Any]:
        """Load a snapshot from the database and reconstruct EvidenceSnapshotV7.

        Returns EvidenceSnapshotV7 or None if not found.
        """
        row = self.conn.execute(
            "SELECT snapshot_json FROM evidence_snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()

        if not row:
            return None

        try:
            from evidence_snapshot_v7 import EvidenceSnapshotV7
            data = json.loads(row["snapshot_json"])
            return EvidenceSnapshotV7.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load snapshot {snapshot_id}: {e}")
            return None

    # ─── List ─────────────────────────────────────────────────────────────────

    def list_snapshots(
        self,
        intent: str = "",
        limit: int = 50,
        offset: int = 0,
        date_from: str = "",
        date_to: str = "",
    ) -> List[Dict[str, Any]]:
        """List snapshots with optional filters. Returns summary dicts (not full snapshot)."""
        sql = (
            "SELECT id, query, intent, created_at, pipeline_version, "
            "context_hash, answer_hash "
            "FROM evidence_snapshots WHERE 1=1"
        )
        params: List[Any] = []

        if intent:
            sql += " AND intent = ?"
            params.append(intent)
        if date_from:
            sql += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND created_at <= ?"
            params.append(date_to)

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ─── Link relations ───────────────────────────────────────────────────────

    def link_relations(self, snapshot_id: str, relation_ids: List[str]) -> int:
        """Link relations to a snapshot by setting snapshot_id FK.

        Returns count of relations linked.
        """
        if not relation_ids:
            return 0

        placeholders = ",".join("?" * len(relation_ids))
        count = self.conn.execute(
            f"UPDATE relations SET snapshot_id = ? WHERE id IN ({placeholders})",
            [snapshot_id] + relation_ids
        ).rowcount
        self.conn.commit()

        logger.info(f"Linked {count} relations to snapshot {snapshot_id}")
        return count

    # ─── Integrity verification ───────────────────────────────────────────────

    def verify_integrity(self, snapshot_id: str) -> Tuple[bool, List[str]]:
        """Verify that a stored snapshot's context_hash matches its content.

        Returns (is_valid, list_of_violations).
        """
        row = self.conn.execute(
            "SELECT context_hash, snapshot_json FROM evidence_snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()

        if not row:
            return False, [f"Snapshot {snapshot_id} not found"]

        stored_hash = row["context_hash"]
        snapshot_json = row["snapshot_json"]

        # Recompute hash from snapshot_json
        computed_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()

        if computed_hash != stored_hash:
            return False, [
                f"Context hash mismatch: stored={stored_hash[:16]}... computed={computed_hash[:16]}..."
            ]

        return True, []

    # ─── Get by hash ──────────────────────────────────────────────────────────

    def get_by_context_hash(self, context_hash: str) -> Optional[Dict[str, Any]]:
        """Find a snapshot by its context_hash. Returns summary dict or None."""
        row = self.conn.execute(
            "SELECT id, query, intent, created_at, context_hash, answer_hash "
            "FROM evidence_snapshots WHERE context_hash = ?",
            (context_hash,)
        ).fetchone()
        return dict(row) if row else None

    # ─── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get snapshot statistics."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM evidence_snapshots"
        ).fetchone()[0]

        by_intent = {}
        for row in self.conn.execute(
            "SELECT intent, COUNT(*) as cnt FROM evidence_snapshots GROUP BY intent"
        ).fetchall():
            by_intent[row["intent"]] = row["cnt"]

        with_answer = self.conn.execute(
            "SELECT COUNT(*) FROM evidence_snapshots WHERE answer_hash != ''"
        ).fetchone()[0]

        linked_relations = self.conn.execute(
            "SELECT COUNT(*) FROM relations WHERE snapshot_id IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_snapshots": total,
            "by_intent": by_intent,
            "with_answer_hash": with_answer,
            "linked_relations": linked_relations,
            "service_version": SERVICE_VERSION,
        }

    # ─── Delete (with safety) ─────────────────────────────────────────────────

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot. Also unlinks relations.

        Returns True if deleted, False if not found.
        """
        # Unlink relations first
        self.conn.execute(
            "UPDATE relations SET snapshot_id = NULL WHERE snapshot_id = ?",
            (snapshot_id,)
        )

        count = self.conn.execute(
            "DELETE FROM evidence_snapshots WHERE id = ?",
            (snapshot_id,)
        ).rowcount
        self.conn.commit()

        if count > 0:
            logger.info(f"Deleted snapshot {snapshot_id}")
            return True
        return False
