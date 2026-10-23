"""Event Ontology Service — hierarchical event management with DB persistence.

This module manages the event hierarchy:

  1. CRUD for event hierarchy (parent/child relationships)
  2. Alias management (multiple names for same event)
  3. Hierarchy queries (ancestors, descendants, siblings)
  4. Temporal containment validation (child must fit within parent's date range)
  5. Event type classification (campaign, battle, phase, skirmish)
  6. Integration with existing event_resolver.py HIERARCHY dict

Key principles:
  - Hierarchy is persistent in eventi_1gm.parent_event_id
  - Aliases are persistent in event_aliases table
  - Temporal containment: child.data_inizio >= parent.data_inizio
  - Event types form a strict hierarchy: campaign > battle > phase > skirmish
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

SERVICE_VERSION = "1.0.0"

# Event type hierarchy (higher = broader)
EVENT_TYPE_HIERARCHY = {
    "campaign": 0,
    "battle": 1,
    "phase": 2,
    "skirmish": 3,
    "operation": 1,  # same level as battle
    "event": 0,      # generic, same as campaign
}

# Reverse mapping for display
EVENT_TYPE_LABELS = {
    0: "campaign",
    1: "battle",
    2: "phase",
    3: "skirmish",
}


@dataclass
class EventNode:
    """A node in the event hierarchy."""
    event_id: int
    stable_id: str
    name: str
    event_type: str = "event"
    parent_event_id: Optional[int] = None
    parent_stable_id: str = ""
    data_inizio: str = ""
    data_fine: str = ""
    general_location: str = ""
    conflict: str = "WWI"
    review_status: str = "candidate"
    aliases: List[str] = field(default_factory=list)
    children: List[int] = field(default_factory=list)
    depth: int = 0


class EventOntologyService:
    """Manages the hierarchical event ontology."""

    def __init__(self, events_conn: sqlite3.Connection):
        self.conn = events_conn

    # ─── Hierarchy queries ────────────────────────────────────────────────────

    def get_event(self, event_id: int) -> Optional[EventNode]:
        """Get a single event by ID with its hierarchy info."""
        row = self.conn.execute(
            "SELECT * FROM eventi_1gm WHERE id = ?",
            (event_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def get_event_by_stable_id(self, stable_id: str) -> Optional[EventNode]:
        """Get a single event by stable_id."""
        row = self.conn.execute(
            "SELECT * FROM eventi_1gm WHERE stable_id = ?",
            (stable_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def get_children(self, event_id: int) -> List[EventNode]:
        """Get direct children of an event."""
        rows = self.conn.execute(
            "SELECT * FROM eventi_1gm WHERE parent_event_id = ? ORDER BY data_inizio",
            (str(event_id),)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_descendants(self, event_id: int, max_depth: int = 10) -> List[EventNode]:
        """Get all descendants of an event (recursive)."""
        result: List[EventNode] = []
        visited: Set[int] = set()

        def _recurse(eid: int, depth: int):
            if depth >= max_depth or eid in visited:
                return
            visited.add(eid)
            children = self.get_children(eid)
            for child in children:
                child.depth = depth + 1
                result.append(child)
                _recurse(child.event_id, depth + 1)

        _recurse(event_id, 0)
        return result

    def get_ancestors(self, event_id: int) -> List[EventNode]:
        """Get all ancestors of an event (walk up the tree)."""
        result: List[EventNode] = []
        visited: Set[int] = set()
        current = event_id

        while current and current not in visited:
            visited.add(current)
            node = self.get_event(current)
            if not node or not node.parent_event_id:
                break
            parent_id = self._parse_parent_id(node.parent_event_id)
            if parent_id is None:
                break
            parent = self.get_event(parent_id)
            if parent:
                result.append(parent)
                current = parent.event_id
            else:
                break

        return result

    def get_siblings(self, event_id: int) -> List[EventNode]:
        """Get siblings of an event (same parent)."""
        node = self.get_event(event_id)
        if not node or not node.parent_event_id:
            # Root-level events — get all with no parent
            rows = self.conn.execute(
                "SELECT * FROM eventi_1gm WHERE (parent_event_id IS NULL OR parent_event_id = '') "
                "AND id != ? ORDER BY data_inizio",
                (event_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM eventi_1gm WHERE parent_event_id = ? AND id != ? ORDER BY data_inizio",
                (str(node.parent_event_id), event_id)
            ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_full_tree(self) -> List[EventNode]:
        """Get the full event tree (root nodes with children populated)."""
        # Get root nodes (no parent)
        rows = self.conn.execute(
            "SELECT * FROM eventi_1gm WHERE parent_event_id IS NULL OR parent_event_id = '' "
            "ORDER BY data_inizio"
        ).fetchall()
        roots = [self._row_to_node(r) for r in rows]

        # Populate children for each root
        for root in roots:
            root.children = [c.event_id for c in self.get_children(root.event_id)]

        return roots

    # ─── Hierarchy management ─────────────────────────────────────────────────

    def set_parent(self, event_id: int, parent_event_id: int,
                   dry_run: bool = False) -> Tuple[bool, str]:
        """Set the parent of an event. Validates temporal containment.

        Returns (success, message).
        """
        event = self.get_event(event_id)
        parent = self.get_event(parent_event_id)

        if not event:
            return False, f"Event {event_id} not found"
        if not parent:
            return False, f"Parent event {parent_event_id} not found"
        if event_id == parent_event_id:
            return False, "Cannot set event as its own parent"

        # Check for cycles
        ancestors = self.get_ancestors(parent_event_id)
        if any(a.event_id == event_id for a in ancestors):
            return False, f"Cycle detected: {event_id} is an ancestor of {parent_event_id}"

        # Temporal containment check
        if event.data_inizio and parent.data_inizio:
            if event.data_inizio < parent.data_inizio:
                return False, (
                    f"Temporal violation: child starts {event.data_inizio} "
                    f"before parent starts {parent.data_inizio}"
                )
        if event.data_fine and parent.data_fine:
            if event.data_fine > parent.data_fine:
                return False, (
                    f"Temporal violation: child ends {event.data_fine} "
                    f"after parent ends {parent.data_fine}"
                )

        # Event type hierarchy check
        child_level = EVENT_TYPE_HIERARCHY.get(event.event_type, 0)
        parent_level = EVENT_TYPE_HIERARCHY.get(parent.event_type, 0)
        if child_level <= parent_level:
            logger.warning(
                f"Type hierarchy warning: child type '{event.event_type}' (level {child_level}) "
                f"is not more specific than parent type '{parent.event_type}' (level {parent_level})"
            )

        if dry_run:
            return True, f"Would set parent of '{event.name}' to '{parent.name}'"

        self.conn.execute(
            "UPDATE eventi_1gm SET parent_event_id = ? WHERE id = ?",
            (str(parent_event_id), event_id)
        )
        self.conn.commit()

        return True, f"Set parent of '{event.name}' to '{parent.name}'"

    def remove_parent(self, event_id: int, dry_run: bool = False) -> Tuple[bool, str]:
        """Remove the parent relationship (make event a root)."""
        event = self.get_event(event_id)
        if not event:
            return False, f"Event {event_id} not found"
        if not event.parent_event_id:
            return False, f"Event {event_id} has no parent"

        if dry_run:
            return True, f"Would remove parent from '{event.name}'"

        self.conn.execute(
            "UPDATE eventi_1gm SET parent_event_id = NULL WHERE id = ?",
            (event_id,)
        )
        self.conn.commit()

        return True, f"Removed parent from '{event.name}'"

    # ─── Alias management ─────────────────────────────────────────────────────

    def add_alias(self, event_id: int, alias: str, alias_type: str = "alias") -> bool:
        """Add an alias to an event."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO event_aliases (event_id, alias, alias_type, created_at) "
                "VALUES (?, ?, ?, ?)",
                (event_id, alias.strip(), alias_type, now)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_aliases(self, event_id: int) -> List[Dict[str, str]]:
        """Get all aliases for an event."""
        rows = self.conn.execute(
            "SELECT alias, alias_type FROM event_aliases WHERE event_id = ? ORDER BY alias",
            (event_id,)
        ).fetchall()
        return [{"alias": r["alias"], "type": r["alias_type"]} for r in rows]

    def remove_alias(self, event_id: int, alias: str) -> bool:
        """Remove an alias from an event."""
        count = self.conn.execute(
            "DELETE FROM event_aliases WHERE event_id = ? AND alias = ?",
            (event_id, alias)
        ).rowcount
        self.conn.commit()
        return count > 0

    # ─── Bootstrap from event_resolver HIERARCHY ──────────────────────────────

    def bootstrap_from_resolver(self, dry_run: bool = True) -> Dict[str, int]:
        """Populate parent_event_id from event_resolver.py HIERARCHY dict.

        Returns stats: {matched, set, skipped, errors}.
        """
        try:
            from event_resolver import HIERARCHY
        except ImportError:
            return {"matched": 0, "set": 0, "skipped": 0, "errors": 0}

        stats = {"matched": 0, "set": 0, "skipped": 0, "errors": 0}

        for parent_name, child_names in HIERARCHY.items():
            # Find parent event by name
            parent_row = self.conn.execute(
                "SELECT id FROM eventi_1gm WHERE nome = ?",
                (parent_name,)
            ).fetchone()
            if not parent_row:
                stats["skipped"] += 1
                continue

            parent_id = parent_row["id"]
            stats["matched"] += 1

            for child_name in child_names:
                child_row = self.conn.execute(
                    "SELECT id FROM eventi_1gm WHERE nome = ?",
                    (child_name,)
                ).fetchone()
                if not child_row:
                    stats["skipped"] += 1
                    continue

                child_id = child_row["id"]
                success, msg = self.set_parent(child_id, parent_id, dry_run=dry_run)
                if success:
                    stats["set"] += 1
                else:
                    stats["errors"] += 1
                    logger.warning(f"Failed to set parent: {msg}")

        return stats

    # ─── Validation ───────────────────────────────────────────────────────────

    def validate_hierarchy(self) -> List[Dict[str, Any]]:
        """Validate the entire event hierarchy. Returns list of violations."""
        violations: List[Dict[str, Any]] = []

        all_events = self.conn.execute(
            "SELECT id, stable_id, nome, data_inizio, data_fine, parent_event_id, event_type "
            "FROM eventi_1gm WHERE parent_event_id IS NOT NULL AND parent_event_id != ''"
        ).fetchall()

        for row in all_events:
            r = dict(row)
            event_id = r["id"]
            parent_id = self._parse_parent_id(r["parent_event_id"])
            if parent_id is None:
                violations.append({
                    "event_id": event_id,
                    "stable_id": r["stable_id"],
                    "name": r["nome"],
                    "violation": "invalid_parent_id",
                    "detail": f"Cannot parse parent_event_id: {r['parent_event_id']}",
                })
                continue

            parent = self.get_event(parent_id)
            if not parent:
                violations.append({
                    "event_id": event_id,
                    "stable_id": r["stable_id"],
                    "name": r["nome"],
                    "violation": "parent_not_found",
                    "detail": f"Parent event {parent_id} not found",
                })
                continue

            # Temporal containment
            if r["data_inizio"] and parent.data_inizio:
                if r["data_inizio"] < parent.data_inizio:
                    violations.append({
                        "event_id": event_id,
                        "stable_id": r["stable_id"],
                        "name": r["nome"],
                        "violation": "temporal_start_before_parent",
                        "detail": f"Child starts {r['data_inizio']} before parent {parent.data_inizio}",
                    })
            if r["data_fine"] and parent.data_fine:
                if r["data_fine"] > parent.data_fine:
                    violations.append({
                        "event_id": event_id,
                        "stable_id": r["stable_id"],
                        "name": r["nome"],
                        "violation": "temporal_end_after_parent",
                        "detail": f"Child ends {r['data_fine']} after parent {parent.data_fine}",
                    })

        return violations

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _row_to_node(self, row: sqlite3.Row) -> EventNode:
        """Convert a DB row to an EventNode."""
        d = dict(row)
        event_id = d["id"]
        parent_id = self._parse_parent_id(d.get("parent_event_id", ""))

        # Get children
        children = self.get_children(event_id)

        # Get aliases
        aliases = []
        try:
            alias_rows = self.conn.execute(
                "SELECT alias FROM event_aliases WHERE event_id = ?",
                (event_id,)
            ).fetchall()
            aliases = [r["alias"] for r in alias_rows]
        except sqlite3.OperationalError:
            pass

        return EventNode(
            event_id=event_id,
            stable_id=d.get("stable_id", "") or f"evt_{event_id:04d}",
            name=d.get("nome", ""),
            event_type=d.get("event_type", "event") or "event",
            parent_event_id=parent_id,
            parent_stable_id="",
            data_inizio=d.get("data_inizio", "") or "",
            data_fine=d.get("data_fine", "") or "",
            general_location=d.get("general_location", "") or "",
            conflict=d.get("conflict", "WWI") or "WWI",
            review_status=d.get("review_status", "candidate") or "candidate",
            aliases=aliases,
            children=[c.event_id for c in children],
            depth=0,
        )

    @staticmethod
    def _parse_parent_id(parent_event_id: str) -> Optional[int]:
        """Parse parent_event_id which may be stored as string or int."""
        if not parent_event_id:
            return None
        try:
            return int(parent_event_id)
        except (ValueError, TypeError):
            return None

    # ─── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get ontology statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM eventi_1gm").fetchone()[0]
        with_parent = self.conn.execute(
            "SELECT COUNT(*) FROM eventi_1gm WHERE parent_event_id IS NOT NULL AND parent_event_id != ''"
        ).fetchone()[0]
        roots = total - with_parent

        aliases_count = 0
        try:
            aliases_count = self.conn.execute(
                "SELECT COUNT(*) FROM event_aliases"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass

        # By type
        by_type = {}
        for row in self.conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM eventi_1gm GROUP BY event_type"
        ).fetchall():
            by_type[row["event_type"] or "unknown"] = row["cnt"]

        # By conflict
        by_conflict = {}
        for row in self.conn.execute(
            "SELECT conflict, COUNT(*) as cnt FROM eventi_1gm GROUP BY conflict"
        ).fetchall():
            by_conflict[row["conflict"] or "unknown"] = row["cnt"]

        # Max depth
        max_depth = 0
        all_events = self.conn.execute(
            "SELECT id FROM eventi_1gm WHERE parent_event_id IS NOT NULL AND parent_event_id != ''"
        ).fetchall()
        for row in all_events:
            ancestors = self.get_ancestors(row["id"])
            depth = len(ancestors)
            if depth > max_depth:
                max_depth = depth

        return {
            "total_events": total,
            "root_events": roots,
            "with_parent": with_parent,
            "max_depth": max_depth,
            "aliases": aliases_count,
            "by_type": by_type,
            "by_conflict": by_conflict,
            "service_version": SERVICE_VERSION,
        }
