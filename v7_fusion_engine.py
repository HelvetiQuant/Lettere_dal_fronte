"""V7 Source Family Graph & Fusion Engine — provenance-aware fusion.

This module implements:
  - SourceFamilyGraph: tracks which sources share a common origin
  - IndependenceAssessor: determines which sources are truly independent
  - FusionEngine: fuses claims from multiple providers using the plan's
    fusion strategy, respecting source independence

Key principles:
  1. Two sources from the same archive are NOT independent
  2. Two sources from the same OCR pipeline are NOT independent
  3. Two sources from different archives with different authors ARE independent
  4. Independence is a spectrum (0.0 = fully dependent, 1.0 = fully independent)
  5. Claims from independent sources can be fused with higher confidence
  6. Contradictions between independent sources are preserved, not resolved
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple

from provider_observation import ProviderObservation
from evidence_snapshot_v7 import (
    ClaimV7, EvidenceItemV7, SourceLineageGroup, IndependenceGroup,
    ContextClaimV7,
)


# ─── Source family graph ────────────────────────────────────────────────────

@dataclass
class SourceNode:
    """A node in the source family graph."""
    source_id: str
    provider: str
    archive: str = ""
    url: str = ""
    title: str = ""
    parent_source_id: str = ""  # if this source was derived from another
    ocr_pipeline: str = ""  # if this source was OCR'd
    metadata: Dict[str, Any] = field(default_factory=dict)


class SourceFamilyGraph:
    """Graph tracking source lineage and dependencies.

    Sources are nodes. Edges represent lineage relationships:
      - SAME_ARCHIVE: sources from the same physical archive
      - SAME_OCR: sources processed through the same OCR pipeline
      - SAME_PUBLICATION: sources from the same publication
      - SAME_INDEX: sources indexed in the same catalog
      - DERIVED_FROM: one source was derived from another
    """

    def __init__(self):
        self._nodes: Dict[str, SourceNode] = {}
        self._edges: Dict[str, List[Tuple[str, str]]] = {}  # edge_type -> [(source_a, source_b)]

    def add_source(self, node: SourceNode):
        self._nodes[node.source_id] = node

    def add_edge(self, source_a: str, source_b: str, edge_type: str):
        if edge_type not in self._edges:
            self._edges[edge_type] = []
        self._edges[edge_type].append((source_a, source_b))

    def get_lineage_groups(self) -> List[SourceLineageGroup]:
        """Build lineage groups from the graph.

        Sources connected by SAME_ARCHIVE, SAME_OCR, SAME_PUBLICATION, or SAME_INDEX
        edges form a lineage group. Each group has a root (the original source).
        """
        groups = []
        seen = set()

        for edge_type in ("SAME_ARCHIVE", "SAME_OCR", "SAME_PUBLICATION", "SAME_INDEX"):
            edges = self._edges.get(edge_type, [])
            for a, b in edges:
                if a in seen and b in seen:
                    continue

                # Find or create group
                group_id = f"lin_{edge_type.lower()}_{hashlib.sha256(f'{a}|{b}'.encode()).hexdigest()[:8]}"

                members = [a, b]
                # Expand: find all sources connected to a or b with same edge type
                for x, y in edges:
                    if x in members and y not in members:
                        members.append(y)
                    elif y in members and x not in members:
                        members.append(x)

                root = members[0]
                group = SourceLineageGroup(
                    group_id=group_id,
                    root_source_id=root,
                    member_source_ids=members,
                    lineage_type=edge_type,
                    description=f"Sources sharing {edge_type.lower().replace('_', ' ')} lineage",
                )
                groups.append(group)
                seen.update(members)

        return groups

    def are_related(self, source_a: str, source_b: str) -> bool:
        """Check if two sources are related (share any lineage edge)."""
        for edges in self._edges.values():
            for a, b in edges:
                if (a == source_a and b == source_b) or (a == source_b and b == source_a):
                    return True
        return False

    def get_relation_type(self, source_a: str, source_b: str) -> Optional[str]:
        """Get the relation type between two sources, if any."""
        for edge_type, edges in self._edges.items():
            for a, b in edges:
                if (a == source_a and b == source_b) or (a == source_b and b == source_a):
                    return edge_type
        return None


# ─── Independence assessor ──────────────────────────────────────────────────

class IndependenceAssessor:
    """Assesses independence between sources based on the source family graph.

    Independence is a spectrum:
      1.0 = fully independent (different archives, different authors, different pipelines)
      0.5 = partially independent (same archive, different processing)
      0.0 = fully dependent (same source, same OCR, same index)
    """

    def __init__(self, graph: SourceFamilyGraph):
        self._graph = graph

    def assess_independence(self, source_a: str, source_b: str) -> float:
        """Assess independence between two sources.

        Returns a score from 0.0 (dependent) to 1.0 (independent).
        """
        node_a = self._graph._nodes.get(source_a)
        node_b = self._graph._nodes.get(source_b)

        if not node_a or not node_b:
            return 0.5  # unknown, assume partial

        # Same source = fully dependent
        if source_a == source_b:
            return 0.0

        # Check explicit relations
        relation = self._graph.get_relation_type(source_a, source_b)
        if relation:
            if relation == "DERIVED_FROM":
                return 0.0
            elif relation == "SAME_OCR":
                return 0.1
            elif relation == "SAME_ARCHIVE":
                return 0.3
            elif relation == "SAME_PUBLICATION":
                return 0.2
            elif relation == "SAME_INDEX":
                return 0.4

        # Check provider
        if node_a.provider == node_b.provider:
            # Same provider but no explicit relation — partially dependent
            return 0.4

        # Different providers, no relation — check archives
        if node_a.archive and node_b.archive:
            if node_a.archive == node_b.archive:
                return 0.3
            else:
                return 0.9  # different archives = high independence

        # Different providers, unknown archives
        return 0.7

    def build_independence_groups(
        self,
        source_ids: List[str],
        min_independence: float = 0.5,
    ) -> List[IndependenceGroup]:
        """Build independence groups from a set of sources.

        Sources with independence >= min_independence are grouped together.
        """
        if not source_ids:
            return []

        # Build adjacency: for each pair, compute independence
        independent_pairs: List[Tuple[str, str, float]] = []
        for i, a in enumerate(source_ids):
            for b in source_ids[i+1:]:
                score = self.assess_independence(a, b)
                if score >= min_independence:
                    independent_pairs.append((a, b, score))

        # Build groups using union-find
        parent = {s: s for s in source_ids}

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
        for s in source_ids:
            root = find(s)
            if root not in groups_map:
                groups_map[root] = []
            groups_map[root].append(s)

        # Build IndependenceGroup objects
        groups = []
        for i, (root, members) in enumerate(groups_map.items()):
            if len(members) < 2:
                continue

            # Compute average independence within group
            total_score = 0.0
            count = 0
            for j, a in enumerate(members):
                for b in members[j+1:]:
                    score = self.assess_independence(a, b)
                    total_score += score
                    count += 1
            avg_score = total_score / count if count > 0 else 0.0

            groups.append(IndependenceGroup(
                group_id=f"ind_{i}_{hashlib.sha256('|'.join(members).encode()).hexdigest()[:8]}",
                member_source_ids=members,
                independence_score=avg_score,
                verified=avg_score >= 0.7,
            ))

        return groups


# ─── Fusion engine ──────────────────────────────────────────────────────────

class FusionEngine:
    """Fuses claims from multiple providers using the plan's fusion strategy.

    V7.2: Separates person evidence from context evidence.
    Person claims are attributable to the identified person.
    Context claims are historical context (unit history, camp conditions, etc.)

    Strategies:
      - PRESERVE_CONTRADICTIONS: keep all conflicting claims (default V7)
      - MAJORITY_VOTE: accept the value supported by most independent sources
      - HIGHEST_CONFIDENCE: accept the value with highest provider score
      - ORIGIN_PRIORITY: accept the value from the origin record
    """

    # V7.2: Person-level fields (attributable to the identified person)
    PERSON_FIELDS = {
        "birth_year", "birth_place", "rank", "unit", "death_year",
        "death_place", "capture_place", "capture_date", "fate",
        "internment_place", "paternita", "maternita", "matricola",
    }

    # V7.2: Context-level fields (historical context, NOT person evidence)
    CONTEXT_FIELDS = {
        "unit_history", "battle_details", "camp_conditions",
        "event_description", "event_start_date", "event_end_date",
        "event_location", "event_phase_count", "event_actors",
        "period_description", "place_history",
    }

    def __init__(self, graph: SourceFamilyGraph):
        self._graph = graph
        self._assessor = IndependenceAssessor(graph)

    def fuse(
        self,
        observations: List[ProviderObservation],
        strategy: str = "PRESERVE_CONTRADICTIONS",
    ) -> Tuple[List[ClaimV7], List[ClaimV7], List[ClaimV7]]:
        """Fuse observations into accepted, conflicting, and asserted claims.

        V7.2: Tags each claim with evidence_scope (PERSON_EVIDENCE or CONTEXT_EVIDENCE).
        Returns (accepted_claims, conflicting_claims, asserted_claims).
        Person claims have evidence_scope=PERSON_EVIDENCE.
        Context claims have evidence_scope=CONTEXT_EVIDENCE.
        """
        # Group observations by predicate (field name)
        claims_by_predicate: Dict[str, List[Tuple[ProviderObservation, str]]] = {}

        for obs in observations:
            if obs.content_state in ("NOT_OPENED", "FAILED"):
                continue
            # V7.2: Skip SURNAME_ONLY_NON_CANDIDATE
            if obs.classification in ("SURNAME_ONLY_NON_CANDIDATE",):
                continue
            if obs.classification not in ("SOURCE_CANDIDATE", "SEARCH_RESULT", "CONTEXT"):
                continue

            # Extract claims from observation metadata
            meta = obs.provider_metadata
            if not isinstance(meta, dict):
                continue

            raw_record = meta.get("raw_record")
            if not isinstance(raw_record, dict):
                continue

            # Map record fields to claim predicates
            field_mapping = {
                "anno_nascita": "birth_year",
                "luogo_nascita": "birth_place",
                "grado": "rank",
                "reparto": "unit",
                "anno_morte": "death_year",
                "luogo_morte": "death_place",
                "cattura_luogo": "capture_place",
                "cattura_data": "capture_date",
                "sorte": "fate",
                "campo": "internment_place",
            }

            for record_field, predicate in field_mapping.items():
                value = raw_record.get(record_field)
                if value and str(value).strip():
                    val_str = str(value).strip()
                    if predicate not in claims_by_predicate:
                        claims_by_predicate[predicate] = []
                    claims_by_predicate[predicate].append((obs, val_str))

        accepted = []
        conflicting = []
        asserted = []

        for predicate, obs_values in claims_by_predicate.items():
            # V7.2: Determine evidence_scope
            evidence_scope = "PERSON_EVIDENCE" if predicate in self.PERSON_FIELDS else "CONTEXT_EVIDENCE"

            # Group by unique value
            value_groups: Dict[str, List[ProviderObservation]] = {}
            for obs, val in obs_values:
                if val not in value_groups:
                    value_groups[val] = []
                value_groups[val].append(obs)

            if len(value_groups) == 1:
                # No conflict — all sources agree
                val = list(value_groups.keys())[0]
                obs_list = value_groups[val]
                providers = list(set(o.provider for o in obs_list))
                evidence_ids = [o.observation_id for o in obs_list]

                # Check independence
                source_ids = [o.source_record_id or o.observation_id for o in obs_list]
                ind_groups = self._assessor.build_independence_groups(source_ids)
                ind_group_ids = [g.group_id for g in ind_groups]

                claim = ClaimV7(
                    claim_id=f"claim_{predicate}_{hashlib.sha256(val.encode()).hexdigest()[:8]}",
                    subject_id=obs_list[0].source_record_id or "",
                    predicate=predicate,
                    value_normalized=val,
                    value_raw=val,
                    evidence_ids=evidence_ids,
                    independence_group_ids=ind_group_ids,
                    status="ACCEPTED" if len(providers) >= 2 else "ASSERTED",
                    confidence=0.9 if len(providers) >= 2 else 0.5,
                    source="external" if len(providers) >= 2 else "origin_record",
                    provenance_chain=[o.observation_id for o in obs_list],
                    evidence_scope=evidence_scope,
                )

                if claim.status == "ACCEPTED":
                    accepted.append(claim)
                else:
                    asserted.append(claim)

            elif len(value_groups) > 1 and strategy == "PRESERVE_CONTRADICTIONS":
                # Keep all as conflicting
                for val, obs_list in value_groups.items():
                    evidence_ids = [o.observation_id for o in obs_list]
                    claim = ClaimV7(
                        claim_id=f"claim_{predicate}_{hashlib.sha256(val.encode()).hexdigest()[:8]}",
                        subject_id=obs_list[0].source_record_id or "",
                        predicate=predicate,
                        value_normalized=val,
                        value_raw=val,
                        evidence_ids=evidence_ids,
                        status="CONFLICTING",
                        confidence=0.3,
                        source="external",
                        provenance_chain=[o.observation_id for o in obs_list],
                        evidence_scope=evidence_scope,
                    )
                    conflicting.append(claim)

            elif len(value_groups) > 1 and strategy == "MAJORITY_VOTE":
                # Accept value with most independent sources
                best_val = max(value_groups.keys(), key=lambda v: len(value_groups[v]))
                best_obs = value_groups[best_val]
                evidence_ids = [o.observation_id for o in best_obs]
                providers = list(set(o.provider for o in best_obs))

                claim = ClaimV7(
                    claim_id=f"claim_{predicate}_{hashlib.sha256(best_val.encode()).hexdigest()[:8]}",
                    subject_id=best_obs[0].source_record_id or "",
                    predicate=predicate,
                    value_normalized=best_val,
                    value_raw=best_val,
                    evidence_ids=evidence_ids,
                    status="ACCEPTED" if len(providers) >= 2 else "ASSERTED",
                    confidence=0.8,
                    source="external",
                    provenance_chain=[o.observation_id for o in best_obs],
                    evidence_scope=evidence_scope,
                )
                if claim.status == "ACCEPTED":
                    accepted.append(claim)
                else:
                    asserted.append(claim)

                # Other values as conflicting
                for val, obs_list in value_groups.items():
                    if val == best_val:
                        continue
                    claim = ClaimV7(
                        claim_id=f"claim_{predicate}_{hashlib.sha256(val.encode()).hexdigest()[:8]}",
                        subject_id=obs_list[0].source_record_id or "",
                        predicate=predicate,
                        value_normalized=val,
                        value_raw=val,
                        evidence_ids=[o.observation_id for o in obs_list],
                        status="CONFLICTING",
                        confidence=0.2,
                        source="external",
                        provenance_chain=[o.observation_id for o in obs_list],
                        evidence_scope=evidence_scope,
                    )
                    conflicting.append(claim)

            elif len(value_groups) > 1 and strategy == "HIGHEST_CONFIDENCE":
                # Accept value from highest-scoring provider
                best_val = max(value_groups.keys(), key=lambda v: max(o.provider_score for o in value_groups[v]))
                best_obs = value_groups[best_val]
                evidence_ids = [o.observation_id for o in best_obs]

                claim = ClaimV7(
                    claim_id=f"claim_{predicate}_{hashlib.sha256(best_val.encode()).hexdigest()[:8]}",
                    subject_id=best_obs[0].source_record_id or "",
                    predicate=predicate,
                    value_normalized=best_val,
                    value_raw=best_val,
                    evidence_ids=evidence_ids,
                    status="ACCEPTED",
                    confidence=max(o.provider_score for o in best_obs),
                    source="external",
                    provenance_chain=[o.observation_id for o in best_obs],
                    evidence_scope=evidence_scope,
                )
                accepted.append(claim)

        return accepted, conflicting, asserted
