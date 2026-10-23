"""Source Lineage Service — DB-backed source lineage management.

Integrates the in-memory SourceFamilyGraph (v7_fusion_engine.py) with the
persistent source_lineages / source_lineage_members DB tables.

This module provides:
  - LineageRegistry: CRUD for source_lineages and source_lineage_members
  - LineageBootstrap: populates lineages from source_authority_registry
  - LineageAwareAssessor: DB-backed independence assessment
  - LineageSync: syncs in-memory SourceFamilyGraph to DB

Key principles:
  1. MULTIPLE SOURCES ≠ INDEPENDENT SOURCES — same lineage = 1 independent
  2. Lineage type determines independence score
  3. Authority level is inherited from parent lineage
  4. Lineage membership is evidence-based (observation_id)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from evidence_contract import (
    SourceOriginType,
    SourceRef,
)

logger = logging.getLogger(__name__)

LINEAGE_SERVICE_VERSION = "1.0.0"


# ─── Lineage types → Independence scores ──────────────────────────────────────

LINEAGE_INDEPENDENCE_SCORES = {
    SourceOriginType.INDEPENDENT: 1.0,
    SourceOriginType.DERIVED: 0.1,
    SourceOriginType.REPUBLICATION: 0.2,
    SourceOriginType.MIRROR: 0.05,
    SourceOriginType.UNKNOWN: 0.5,
}

# Lineage edge types from SourceFamilyGraph → origin_type mapping
EDGE_TO_ORIGIN = {
    "SAME_ARCHIVE": SourceOriginType.DERIVED,
    "SAME_OCR": SourceOriginType.DERIVED,
    "SAME_PUBLICATION": SourceOriginType.REPUBLICATION,
    "SAME_INDEX": SourceOriginType.DERIVED,
    "DERIVED_FROM": SourceOriginType.DERIVED,
}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class LineageEntry:
    """A source lineage entry."""
    lineage_id: str
    canonical_origin: str
    origin_type: str
    parent_lineage_id: str = ""
    description: str = ""
    authority_level: float = 0.5
    created_at: str = ""


@dataclass
class LineageMembership:
    """Membership of a resource in a lineage."""
    resource_id: str
    lineage_id: str
    relation_to_root: str  # root|derived|republication|mirror|unknown
    evidence_observation_id: str = ""


# ─── Lineage Registry (DB CRUD) ───────────────────────────────────────────────

class LineageRegistry:
    """CRUD operations for source_lineages and source_lineage_members."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_lineage(
        self,
        canonical_origin: str,
        origin_type: str,
        parent_lineage_id: str = "",
        description: str = "",
        authority_level: float = 0.5,
    ) -> str:
        """Create a new source lineage. Returns lineage_id."""
        lineage_id = f"lin_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute(
            """INSERT INTO source_lineages
               (id, canonical_origin, origin_type, parent_lineage_id,
                description, authority_level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lineage_id, canonical_origin, origin_type, parent_lineage_id or None,
             description, authority_level, now)
        )
        self.conn.commit()
        return lineage_id

    def get_or_create_lineage(
        self,
        canonical_origin: str,
        origin_type: str = SourceOriginType.UNKNOWN,
        authority_level: float = 0.5,
    ) -> str:
        """Get existing lineage by canonical_origin or create new one."""
        row = self.conn.execute(
            "SELECT id FROM source_lineages WHERE canonical_origin = ?",
            (canonical_origin,)
        ).fetchone()
        if row:
            return row[0]
        return self.create_lineage(
            canonical_origin=canonical_origin,
            origin_type=origin_type,
            authority_level=authority_level,
        )

    def add_member(
        self,
        resource_id: str,
        lineage_id: str,
        relation_to_root: str = "root",
        evidence_observation_id: str = "",
    ) -> bool:
        """Add a resource to a lineage. Returns True if inserted, False if already member."""
        existing = self.conn.execute(
            "SELECT 1 FROM source_lineage_members WHERE resource_id = ? AND lineage_id = ?",
            (resource_id, lineage_id)
        ).fetchone()
        if existing:
            return False

        self.conn.execute(
            """INSERT INTO source_lineage_members
               (resource_id, lineage_id, relation_to_root, evidence_observation_id)
               VALUES (?, ?, ?, ?)""",
            (resource_id, lineage_id, relation_to_root,
             evidence_observation_id or None)
        )
        self.conn.commit()
        return True

    def get_lineage(self, lineage_id: str) -> Optional[LineageEntry]:
        """Get a lineage by ID."""
        row = self.conn.execute(
            "SELECT * FROM source_lineages WHERE id = ?",
            (lineage_id,)
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        return LineageEntry(
            lineage_id=r["id"],
            canonical_origin=r["canonical_origin"],
            origin_type=r["origin_type"],
            parent_lineage_id=r.get("parent_lineage_id") or "",
            description=r.get("description") or "",
            authority_level=r.get("authority_level", 0.5),
            created_at=r.get("created_at", ""),
        )

    def get_lineage_by_origin(self, canonical_origin: str) -> Optional[LineageEntry]:
        """Get a lineage by canonical_origin."""
        row = self.conn.execute(
            "SELECT * FROM source_lineages WHERE canonical_origin = ?",
            (canonical_origin,)
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        return LineageEntry(
            lineage_id=r["id"],
            canonical_origin=r["canonical_origin"],
            origin_type=r["origin_type"],
            parent_lineage_id=r.get("parent_lineage_id") or "",
            description=r.get("description") or "",
            authority_level=r.get("authority_level", 0.5),
            created_at=r.get("created_at", ""),
        )

    def get_members(self, lineage_id: str) -> List[LineageMembership]:
        """Get all members of a lineage."""
        rows = self.conn.execute(
            "SELECT * FROM source_lineage_members WHERE lineage_id = ?",
            (lineage_id,)
        ).fetchall()
        return [
            LineageMembership(
                resource_id=dict(r)["resource_id"],
                lineage_id=dict(r)["lineage_id"],
                relation_to_root=dict(r)["relation_to_root"],
                evidence_observation_id=dict(r).get("evidence_observation_id") or "",
            )
            for r in rows
        ]

    def get_resource_lineages(self, resource_id: str) -> List[LineageEntry]:
        """Get all lineages a resource belongs to."""
        rows = self.conn.execute(
            """SELECT sl.* FROM source_lineages sl
               JOIN source_lineage_members slm ON sl.id = slm.lineage_id
               WHERE slm.resource_id = ?""",
            (resource_id,)
        ).fetchall()
        return [
            LineageEntry(
                lineage_id=dict(r)["id"],
                canonical_origin=dict(r)["canonical_origin"],
                origin_type=dict(r)["origin_type"],
                parent_lineage_id=dict(r).get("parent_lineage_id") or "",
                description=dict(r).get("description") or "",
                authority_level=dict(r).get("authority_level", 0.5),
                created_at=dict(r).get("created_at", ""),
            )
            for r in rows
        ]

    def count_independent_lineages(self, resource_ids: List[str]) -> Tuple[int, int]:
        """Count total resources and independent lineages among given resources.

        Returns (resource_count, independent_lineage_count).
        """
        if not resource_ids:
            return 0, 0

        placeholders = ",".join("?" * len(resource_ids))
        rows = self.conn.execute(
            f"""SELECT DISTINCT sl.id, sl.origin_type
                FROM source_lineages sl
                JOIN source_lineage_members slm ON sl.id = slm.lineage_id
                WHERE slm.resource_id IN ({placeholders})""",
            resource_ids
        ).fetchall()

        lineage_ids = set()
        for r in rows:
            r = dict(r)
            if r["origin_type"] == SourceOriginType.INDEPENDENT:
                lineage_ids.add(r["id"])

        return len(resource_ids), len(lineage_ids)

    def are_same_lineage(self, resource_a: str, resource_b: str) -> bool:
        """Check if two resources share any lineage."""
        rows = self.conn.execute(
            """SELECT sl1.lineage_id FROM source_lineage_members sl1
               JOIN source_lineage_members sl2 ON sl1.lineage_id = sl2.lineage_id
               WHERE sl1.resource_id = ? AND sl2.resource_id = ?
               AND sl1.lineage_id != ''""",
            (resource_a, resource_b)
        ).fetchall()
        return len(rows) > 0

    def get_independence_score(self, resource_a: str, resource_b: str) -> float:
        """Get independence score between two resources based on shared lineages."""
        if resource_a == resource_b:
            return 0.0

        lineages_a = self.get_resource_lineages(resource_a)
        lineages_b = self.get_resource_lineages(resource_b)

        if not lineages_a and not lineages_b:
            return 0.7  # unknown — assume partially independent

        # Check for shared lineages
        ids_a = {l.lineage_id for l in lineages_a}
        ids_b = {l.lineage_id for l in lineages_b}
        shared = ids_a & ids_b

        if shared:
            # Resources sharing a lineage are NOT independent — they share an origin.
            # The lineage's origin_type describes relation to OTHER lineages,
            # not intra-lineage independence. Same lineage = dependent.
            # Use the most restrictive shared lineage's derived score.
            min_score = 1.0
            for l in lineages_a:
                if l.lineage_id in shared:
                    # Intra-lineage: members share origin → low independence
                    # DERIVED/MIRROR/REPUBLICATION lineage → even lower
                    if l.origin_type in (SourceOriginType.DERIVED, SourceOriginType.MIRROR):
                        score = 0.05
                    elif l.origin_type == SourceOriginType.REPUBLICATION:
                        score = 0.1
                    else:
                        score = 0.2  # same independent lineage still means shared origin
                    min_score = min(min_score, score)
            return min_score

        # No shared lineage — check if any lineage pair is related via parent
        for la in lineages_a:
            for lb in lineages_b:
                if la.parent_lineage_id and la.parent_lineage_id == lb.lineage_id:
                    return LINEAGE_INDEPENDENCE_SCORES[SourceOriginType.DERIVED]
                if lb.parent_lineage_id and lb.parent_lineage_id == la.lineage_id:
                    return LINEAGE_INDEPENDENCE_SCORES[SourceOriginType.DERIVED]

        # No relationship found — independent
        return 0.9


# ─── Lineage Bootstrap (from source_authority_registry) ───────────────────────

class LineageBootstrap:
    """Populates source_lineages from source_authority_registry defaults."""

    # Mapping from source_authority_registry entries to lineage structure
    LINEAGE_DEFINITIONS = [
        {
            "canonical_origin": "ANRP — LeBI (Lessico Biografico IMI)",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.95,
            "source_keys": ["anrp_lebi"],
            "description": "Archivio ufficiale ANRP per gli IMI",
        },
        {
            "canonical_origin": "CICR — International Committee of the Red Cross",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.95,
            "source_keys": ["icrc"],
            "description": "Archivio CICR prigionieri di guerra",
        },
        {
            "canonical_origin": "Ministero della Difesa — Caduti in Guerra",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.92,
            "source_keys": ["ministero_difesa"],
            "description": "Archivio ufficiale caduti Ministero della Difesa",
        },
        {
            "canonical_origin": "Albo d'Oro dei Caduti della Grande Guerra",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.85,
            "source_keys": ["albo_oro"],
            "description": "Albo d'Oro ufficiale WWI",
        },
        {
            "canonical_origin": "Commonwealth War Graves Commission",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.82,
            "source_keys": ["cwgc"],
            "description": "CWGC — caduti del Commonwealth",
        },
        {
            "canonical_origin": "Decorati al Nastro Azzurro",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.80,
            "source_keys": ["nastro_azzurro"],
            "description": "Registro decorati Nastro Azzurro",
        },
        {
            "canonical_origin": "Internati Militari Italiani — DB locale",
            "origin_type": SourceOriginType.INDEPENDENT,
            "authority_level": 0.78,
            "source_keys": ["internati_imi"],
            "description": "DB locale IMI (elaborato da fonti primarie)",
        },
        {
            "canonical_origin": "Fonti Indice — Raccolte testuali",
            "origin_type": SourceOriginType.DERIVED,
            "authority_level": 0.50,
            "source_keys": ["fonti_indice"],
            "description": "Fonti secondarie indicizzate",
        },
        {
            "canonical_origin": "Archivio Documenti Digitale",
            "origin_type": SourceOriginType.DERIVED,
            "authority_level": 0.45,
            "source_keys": ["archivio_documenti"],
            "description": "Documenti digitali raccolti",
        },
        {
            "canonical_origin": "Lettere dal Fronte — OCR",
            "origin_type": SourceOriginType.DERIVED,
            "authority_level": 0.40,
            "source_keys": ["ocr_lettere"],
            "description": "OCR lettere dal fronte (elaborazione locale)",
        },
        {
            "canonical_origin": "Ricerca Web — Tavily/Google",
            "origin_type": SourceOriginType.UNKNOWN,
            "authority_level": 0.20,
            "source_keys": ["web_search"],
            "description": "Risultati ricerca web (non strutturati)",
        },
        {
            "canonical_origin": "Wikipedia",
            "origin_type": SourceOriginType.REPUBLICATION,
            "authority_level": 0.15,
            "source_keys": ["wikipedia"],
            "description": "Wikipedia (fonte terziaria)",
        },
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.registry = LineageRegistry(conn)

    def bootstrap(self) -> Dict[str, int]:
        """Populate source_lineages from DEFAULT_SOURCES.

        Returns stats: {lineages_created, members_added, skipped}
        """
        stats = {"lineages_created": 0, "members_added": 0, "skipped": 0}

        for defn in self.LINEAGE_DEFINITIONS:
            # Create or get lineage
            existing = self.registry.get_lineage_by_origin(defn["canonical_origin"])
            if existing:
                stats["skipped"] += 1
                continue

            lineage_id = self.registry.create_lineage(
                canonical_origin=defn["canonical_origin"],
                origin_type=defn["origin_type"],
                description=defn["description"],
                authority_level=defn["authority_level"],
            )
            stats["lineages_created"] += 1

            # Register source keys as resources in resource_registry
            for source_key in defn["source_keys"]:
                # Check if resource already exists in resource_registry
                resource_id = self._ensure_resource(source_key)
                if resource_id:
                    self.registry.add_member(
                        resource_id=resource_id,
                        lineage_id=lineage_id,
                        relation_to_root="root",
                    )
                    stats["members_added"] += 1

        return stats

    def _ensure_resource(self, source_key: str) -> Optional[str]:
        """Ensure a resource_registry entry exists for the source_key. Returns resource_id."""
        # Check if already registered
        row = self.conn.execute(
            "SELECT id FROM resource_registry WHERE source_namespace = ? AND source_record_key = ?",
            ("source_authority", source_key)
        ).fetchone()
        if row:
            return row[0]

        # Create new resource
        resource_id = f"res_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO resource_registry
               (id, resource_kind, source_namespace, source_record_key,
                canonical_entity_id, metadata_json, created_at)
               VALUES (?, 'source', 'source_authority', ?, NULL, ?, ?)""",
            (resource_id, source_key, json.dumps({"source_key": source_key}), now)
        )
        self.conn.commit()
        return resource_id


# ─── Lineage-aware Independence Assessor ──────────────────────────────────────

class LineageAwareAssessor:
    """DB-backed independence assessor that uses source_lineages.

    Replaces the in-memory IndependenceAssessor when DB lineage data is available.
    Falls back to heuristic scoring when lineage data is absent.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.registry = LineageRegistry(conn)

    def assess_independence(self, resource_a: str, resource_b: str) -> float:
        """Assess independence between two resources using DB lineage data."""
        return self.registry.get_independence_score(resource_a, resource_b)

    def count_independent(self, resource_ids: List[str]) -> Tuple[int, int]:
        """Count resources and independent lineages."""
        return self.registry.count_independent_lineages(resource_ids)

    def build_independence_groups(
        self,
        resource_ids: List[str],
        min_independence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Build independence groups from DB lineage data.

        Resources sharing a non-independent lineage are grouped together.
        Returns list of groups with member_resource_ids and independence_score.
        """
        if not resource_ids:
            return []

        # Build independence matrix
        independent_pairs: List[Tuple[str, str, float]] = []
        for i, a in enumerate(resource_ids):
            for b in resource_ids[i + 1:]:
                score = self.assess_independence(a, b)
                if score >= min_independence:
                    independent_pairs.append((a, b, score))

        # Union-find for independent groups
        parent = {s: s for s in resource_ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for a, b, _ in independent_pairs:
            union(a, b)

        # Collect groups
        groups_map: Dict[str, List[str]] = {}
        for s in resource_ids:
            root = find(s)
            if root not in groups_map:
                groups_map[root] = []
            groups_map[root].append(s)

        # Build result
        groups = []
        for i, (root, members) in enumerate(groups_map.items()):
            if len(members) < 2:
                continue

            # Average independence within group
            total_score = 0.0
            count = 0
            for j, a in enumerate(members):
                for b in members[j + 1:]:
                    score = self.assess_independence(a, b)
                    total_score += score
                    count += 1
            avg_score = total_score / count if count > 0 else 0.0

            groups.append({
                "group_id": f"ind_db_{i}_{len(members)}",
                "member_resource_ids": members,
                "independence_score": avg_score,
                "verified": avg_score >= 0.7,
            })

        return groups

    def corroboration_bonus(self, resource_ids: List[str]) -> float:
        """Calculate corroboration bonus based on INDEPENDENT lineages only.

        Uses DB lineage data for accurate independence counting.
        """
        _, n_independent = self.count_independent(resource_ids)
        if n_independent <= 1:
            return 0.0
        import math
        return min(0.2, 0.1 * math.log2(n_independent))


# ─── Lineage Sync (in-memory → DB) ────────────────────────────────────────────

class LineageSync:
    """Syncs in-memory SourceFamilyGraph to DB source_lineages."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.registry = LineageRegistry(conn)

    def sync_from_graph(self, graph_nodes: Dict[str, Any],
                         graph_edges: List[Tuple[str, str, str]]) -> Dict[str, int]:
        """Sync a SourceFamilyGraph's nodes and edges to DB.

        Args:
            graph_nodes: {source_id: SourceNode-like dict}
            graph_edges: [(source_a, source_b, edge_type)]

        Returns stats: {lineages_created, members_added, edges_synced}
        """
        stats = {"lineages_created": 0, "members_added": 0, "edges_synced": 0}

        # Group edges by connected components
        parent = {s: s for s in graph_nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for a, b, edge_type in graph_edges:
            if a in parent and b in parent:
                union(a, b)

        # Build components
        components: Dict[str, List[str]] = {}
        for s in graph_nodes:
            root = find(s)
            if root not in components:
                components[root] = []
            components[root].append(s)

        # For each component, create or update lineage
        for root, members in components.items():
            if len(members) < 2:
                continue

            # Determine lineage type from edges
            origin_type = SourceOriginType.UNKNOWN
            for a, b, edge_type in graph_edges:
                if a in members and b in members:
                    mapped = EDGE_TO_ORIGIN.get(edge_type, SourceOriginType.UNKNOWN)
                    if mapped != SourceOriginType.UNKNOWN:
                        origin_type = mapped
                        break

            # Use root node's archive/provider as canonical_origin
            root_node = graph_nodes.get(root, {})
            canonical_origin = (
                root_node.get("archive") or
                root_node.get("provider") or
                f"lineage_{root[:8]}"
            )

            lineage_id = self.registry.get_or_create_lineage(
                canonical_origin=canonical_origin,
                origin_type=origin_type,
            )

            for member_id in members:
                node = graph_nodes.get(member_id, {})
                relation = "root" if member_id == root else "derived"
                added = self.registry.add_member(
                    resource_id=member_id,
                    lineage_id=lineage_id,
                    relation_to_root=relation,
                )
                if added:
                    stats["members_added"] += 1

            stats["edges_synced"] += len([e for e in graph_edges if e[0] in members and e[1] in members])

        return stats
