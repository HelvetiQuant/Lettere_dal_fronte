"""Adattatore read-through dei sistemi di collegamento esistenti.

Il servizio presenta un solo contratto al frontend ma conserva, per ogni arco,
il sistema e l'identificativo originali. Nessun candidato legacy viene
trasformato in fatto confermato solo perché possiede un punteggio alto.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import get_conn
from database_registry import (
    EVENTS_DB_PATH,
    TABLE_SPECS,
    connect_database,
    fetch_record,
    get_table_spec,
    record_description,
    record_label,
    record_urls,
    table_exists,
)
from graph_models import (
    EdgeReviewRequest,
    GraphEdge,
    GraphEvidence,
    GraphIntegrityIssue,
    GraphNode,
    GraphRelation,
    GraphResponse,
    GraphReview,
)


RELATION_LABELS = {
    "stesso_evento_luogo": "potenzialmente collegato allo stesso evento e luogo",
    "stesso_anno_decorazione": "decorazione registrata nello stesso anno",
    "documento_evento": "potenzialmente documentato da",
    "documento_luogo": "collegato per luogo a",
    "fonte_personale": "potenzialmente citato nella fonte",
    "soldato_caduto": "persona associata all'evento",
    "soldato_caduto_cwgc": "persona associata all'evento",
    "soldato_decorato": "decorazione associata all'evento",
    "internato_ww2": "internato associato all'evento",
    "documento": "evento documentato da",
    "fonte_archivistica": "evento citato nella fonte",
    "mentions": "menziona",
    "same_person": "potenziale identità comune",
    "entity_extraction": "entità estratta dal record",
    "claim": "afferma",
}


@dataclass
class GraphBatch:
    roots: list[GraphNode]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    issues: list[GraphIntegrityIssue]
    truncated: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_value(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _confidence(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _confidence_label(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if value >= 0.8:
        return "alta"
    if value >= 0.55:
        return "media"
    return "bassa"


def _relation_label(relation_type: str) -> str:
    return RELATION_LABELS.get(relation_type, relation_type.replace("_", " "))


def _evidence_items(
    value: Any,
    *,
    role: str = "supports",
    source_table: str | None = None,
    source_id: int | None = None,
) -> list[GraphEvidence]:
    raw = _json_value(value, [])
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    items: list[GraphEvidence] = []
    for index, item in enumerate(raw[:30]):
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("field") or item.get("type") or f"Evidenza {index + 1}")
            val = item.get("value")
            if val is None:
                remainder = {k: v for k, v in item.items() if k not in {"label", "field", "type"}}
                val = json.dumps(remainder, ensure_ascii=False, default=str) if remainder else None
            items.append(
                GraphEvidence(
                    type=str(item.get("type") or item.get("field") or "field_match"),
                    label=label,
                    value=str(val) if val is not None else None,
                    source_table=source_table,
                    source_id=source_id,
                    role=role,
                    strength=_confidence(item.get("strength")),
                )
            )
        elif str(item).strip():
            items.append(
                GraphEvidence(
                    type="statement",
                    label="Evidenza registrata",
                    value=str(item).strip(),
                    source_table=source_table,
                    source_id=source_id,
                    role=role,
                )
            )
    return items


def _status_from_row(
    row: dict[str, Any],
    *,
    source_system: str,
    review: GraphReview | None = None,
) -> str:
    if review and review.decision:
        return {
            "accepted": "confirmed",
            "rejected": "rejected",
            "needs_more_evidence": "to_review",
        }[review.decision]

    values = {
        str(row.get("review_status") or "").lower(),
        str(row.get("match_status") or "").lower(),
        str(row.get("status") or "").lower(),
    }
    if values & {"rejected", "respinto"}:
        return "rejected"
    if values & {"conflicting", "conflict", "ambiguous", "discordant"}:
        return "conflicting"
    if values & {"confirmed", "accepted", "validated", "verified"}:
        return "confirmed"
    if source_system == "record_links" and (
        row.get("legacy_unverified") or str(row.get("algorithm_version") or "") == "legacy"
    ):
        return "to_review"
    if source_system in {"event_links", "collegamenti"}:
        if str(row.get("algorithm_version") or "") == "legacy" or not row.get("algorithm_version"):
            return "to_review"
        return "candidate"
    if values & {"probable"}:
        return "probable"
    return "candidate"


class GraphBuilder:
    def __init__(
        self,
        *,
        max_nodes: int = 100,
        max_edges: int = 200,
        include_candidates: bool = True,
        include_rejected: bool = False,
    ):
        self.max_nodes = max(1, min(int(max_nodes), 500))
        self.max_edges = max(1, min(int(max_edges), 1000))
        self.include_candidates = include_candidates
        self.include_rejected = include_rejected
        self.main = connect_database("main", read_only=True)
        self.events: sqlite3.Connection | None = None
        if EVENTS_DB_PATH.exists():
            try:
                self.events = connect_database("events", read_only=True)
            except (OSError, sqlite3.Error):
                self.events = None
        self.connections = {"main": self.main}
        if self.events:
            self.connections["events"] = self.events
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.issues: list[GraphIntegrityIssue] = []
        self.truncated = False
        self.reviews = self._load_reviews()

    def close(self) -> None:
        self.main.close()
        if self.events:
            self.events.close()

    def _load_reviews(self) -> dict[str, GraphReview]:
        if not table_exists(self.main, "graph_edge_reviews"):
            return {}
        reviews = {}
        for row in self.main.execute("SELECT * FROM graph_edge_reviews").fetchall():
            item = dict(row)
            reviews[item["edge_id"]] = GraphReview(
                required=False,
                decision=item.get("decision"),
                reviewed_by=item.get("reviewed_by"),
                reviewed_at=item.get("reviewed_at"),
                note=item.get("note"),
            )
        return reviews

    def node_for_record(self, table: str, record_id: int) -> GraphNode | None:
        if table not in TABLE_SPECS:
            self.issue("unknown_table", "warning", f"Tabella non mappata: {table}")
            return None
        spec = get_table_spec(table)
        node_id = f"{spec.database}:{table}:{int(record_id)}"
        if node_id in self.nodes:
            return self.nodes[node_id]
        try:
            record = fetch_record(table, int(record_id), connections=self.connections)
        except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
            self.issue("record_read_error", "warning", str(exc), table, str(record_id))
            return None
        if not record:
            self.issue(
                "orphan_target",
                "error",
                f"Record destinazione inesistente: {table}#{record_id}",
                table,
                str(record_id),
            )
            return None
        if len(self.nodes) >= self.max_nodes:
            self.truncated = True
            return None
        node_type = str(record.get("tipo") or spec.node_type) if table == "entita" else spec.node_type
        node = GraphNode(
            id=node_id,
            namespace=spec.database,
            type=node_type,
            label=record_label(table, record),
            source_table=table,
            source_id=int(record_id),
            external_id=str(record.get("external_id")) if record.get("external_id") else None,
            attributes={
                "description": record_description(table, record),
                "dates": {
                    field: record.get(field)
                    for field in spec.date_fields
                    if record.get(field) not in (None, "")
                },
                "places": {
                    field: record.get(field)
                    for field in spec.place_fields
                    if record.get(field) not in (None, "")
                },
                "sources": record_urls(table, record),
            },
        )
        self.nodes[node.id] = node
        return node

    def issue(
        self,
        code: str,
        severity: str,
        message: str,
        source_system: str | None = None,
        source_edge_id: str | None = None,
    ) -> None:
        key = (code, source_system, source_edge_id, message)
        if any(
            (item.code, item.source_system, item.source_edge_id, item.message) == key
            for item in self.issues
        ):
            return
        self.issues.append(
            GraphIntegrityIssue(
                code=code,
                severity=severity,
                message=message,
                source_system=source_system,
                source_edge_id=source_edge_id,
            )
        )

    def add_edge(
        self,
        *,
        edge_id: str,
        source: GraphNode | None,
        target: GraphNode | None,
        relation_type: str,
        source_system: str,
        source_edge_id: str,
        row: dict[str, Any],
        explanation: str,
        evidence: Iterable[GraphEvidence] = (),
        contrary: Iterable[GraphEvidence] = (),
        algorithm: str,
        algorithm_version: str,
        direction: str = "directed",
        created_at: str | None = None,
    ) -> None:
        if not source or not target or source.id == target.id:
            return
        if edge_id in self.edges:
            return
        if len(self.edges) >= self.max_edges:
            self.truncated = True
            return
        review = self.reviews.get(edge_id, GraphReview(required=True))
        status = _status_from_row(row, source_system=source_system, review=review)
        if status == "rejected" and not self.include_rejected:
            return
        if status in {"candidate", "to_review", "probable", "conflicting"} and not self.include_candidates:
            return
        confidence = _confidence(
            row.get("confidence")
            if row.get("confidence") is not None
            else row.get("match_score")
        )
        self.edges[edge_id] = GraphEdge(
            id=edge_id,
            source=source,
            target=target,
            relation=GraphRelation(
                type=relation_type,
                label=_relation_label(relation_type),
                direction="undirected" if direction == "undirected" else "directed",
            ),
            status=status,
            confidence=confidence,
            confidence_label=_confidence_label(confidence),
            explanation=explanation,
            evidence=list(evidence),
            contrary_signals=list(contrary),
            algorithm=algorithm,
            algorithm_version=algorithm_version,
            source_system=source_system,
            source_edge_id=source_edge_id,
            review=review,
            created_at=created_at,
            last_verified_at=row.get("reviewed_at") or row.get("updated_at"),
        )

    def add_record_links(self, table: str, record_id: int) -> None:
        if not table_exists(self.main, "record_links"):
            return
        rows = self.main.execute(
            """
            SELECT * FROM record_links
            WHERE (from_table=? AND from_id=?) OR (to_table=? AND to_id=?)
            ORDER BY id LIMIT ?
            """,
            (table, record_id, table, record_id, self.max_edges * 2),
        ).fetchall()
        for raw in rows:
            row = dict(raw)
            source = self.node_for_record(row["from_table"], row["from_id"])
            target = self.node_for_record(row["to_table"], row["to_id"])
            evidence = _evidence_items(
                row.get("evidence_json") or row.get("matched_fields_json"),
                source_table=row["from_table"],
                source_id=row["from_id"],
            )
            contrary = _evidence_items(
                row.get("contrary_signals_json") or row.get("conflicting_fields_json"),
                role="contradicts",
                source_table=row["from_table"],
                source_id=row["from_id"],
            )
            explanation = (row.get("explanation") or "").strip()
            if not explanation:
                explanation = (
                    "Collegamento legacy generato automaticamente. "
                    "La regola originale non ha registrato una spiegazione verificabile."
                )
            self.add_edge(
                edge_id=f"record_links:{row['id']}",
                source=source,
                target=target,
                relation_type=row["link_type"],
                source_system="record_links",
                source_edge_id=str(row["id"]),
                row=row,
                explanation=explanation,
                evidence=evidence,
                contrary=contrary,
                algorithm=row.get("match_method") or "legacy-record-linker",
                algorithm_version=row.get("algorithm_version") or "legacy",
                direction=row.get("direction") or "undirected",
                created_at=row.get("elaborato_il"),
            )

    def add_entity_links(self, table: str, record_id: int) -> None:
        if not table_exists(self.main, "collegamenti") or not table_exists(self.main, "entita"):
            return
        if table == "entita":
            memberships = self.main.execute(
                "SELECT * FROM collegamenti WHERE entita_id=? ORDER BY id LIMIT ?",
                (record_id, self.max_edges),
            ).fetchall()
        else:
            memberships = self.main.execute(
                """
                SELECT * FROM collegamenti
                WHERE tabella_origine=? AND record_id=?
                ORDER BY id LIMIT ?
                """,
                (table, record_id, self.max_edges),
            ).fetchall()
        entity_ids: list[int] = []
        for raw in memberships:
            row = dict(raw)
            entity_ids.append(int(row["entita_id"]))
            entity = self.node_for_record("entita", row["entita_id"])
            record = self.node_for_record(row["tabella_origine"], row["record_id"])
            evidence = [
                GraphEvidence(
                    type="record_extraction",
                    label="Presenza estratta dal record",
                    value=row.get("tipo_collegamento"),
                    source_table=row["tabella_origine"],
                    source_id=row["record_id"],
                    strength=_confidence(row.get("confidenza")),
                )
            ]
            self.add_edge(
                edge_id=f"collegamenti:{row['id']}",
                source=record,
                target=entity,
                relation_type="entity_extraction",
                source_system="collegamenti",
                source_edge_id=str(row["id"]),
                row={"confidence": row.get("confidenza")},
                explanation=(
                    f"L'entità è stata estratta dal campo «{row.get('tipo_collegamento') or 'non specificato'}» "
                    f"del record {row['tabella_origine']}#{row['record_id']}."
                ),
                evidence=evidence,
                algorithm="entity-extractor",
                algorithm_version="legacy",
                created_at=row.get("elaborato_il"),
            )
        if table != "entita" and entity_ids:
            unique_entity_ids = list(dict.fromkeys(entity_ids))
            if len(unique_entity_ids) > 850:
                unique_entity_ids = unique_entity_ids[:850]
                self.truncated = True
            placeholders = ",".join("?" for _ in unique_entity_ids)
            neighbours = self.main.execute(
                f"""
                SELECT * FROM collegamenti
                WHERE entita_id IN ({placeholders})
                  AND NOT (tabella_origine=? AND record_id=?)
                ORDER BY entita_id, id
                LIMIT ?
                """,
                (
                    *unique_entity_ids,
                    table,
                    record_id,
                    min(self.max_edges * 2, len(unique_entity_ids) * 8),
                ),
            ).fetchall()
            per_entity: dict[int, int] = {}
            for neighbour_raw in neighbours:
                neighbour = dict(neighbour_raw)
                entity_id = int(neighbour["entita_id"])
                if per_entity.get(entity_id, 0) >= 8:
                    continue
                entity = self.node_for_record("entita", entity_id)
                neighbour_record = self.node_for_record(
                    neighbour["tabella_origine"], neighbour["record_id"]
                )
                self.add_edge(
                    edge_id=f"collegamenti:{neighbour['id']}",
                    source=entity,
                    target=neighbour_record,
                    relation_type="mentions",
                    source_system="collegamenti",
                    source_edge_id=str(neighbour["id"]),
                    row={"confidence": neighbour.get("confidenza")},
                    explanation=(
                        f"Lo stesso indice di entità compare nel record "
                        f"{neighbour['tabella_origine']}#{neighbour['record_id']}. "
                        "La co-occorrenza non dimostra da sola identità o causalità."
                    ),
                    evidence=[
                        GraphEvidence(
                            type="shared_entity_index",
                            label="Entità indicizzata in comune",
                            value=entity.label if entity else str(entity_id),
                            source_table=neighbour["tabella_origine"],
                            source_id=neighbour["record_id"],
                            strength=_confidence(neighbour.get("confidenza")),
                        )
                    ],
                    algorithm="entity-index-traversal",
                    algorithm_version="1.0.0",
                    direction="undirected",
                    created_at=neighbour.get("elaborato_il"),
                )
                per_entity[entity_id] = per_entity.get(entity_id, 0) + 1

    def add_event_links(self, table: str, record_id: int) -> None:
        if not self.events or not table_exists(self.events, "event_links"):
            self.issue("events_database_unavailable", "warning", "Collegamenti evento non disponibili")
            return
        if table == "eventi_1gm":
            rows = self.events.execute(
                "SELECT * FROM event_links WHERE evento_id=? ORDER BY id LIMIT ?",
                (record_id, self.max_edges * 2),
            ).fetchall()
        else:
            rows = self.events.execute(
                """
                SELECT * FROM event_links
                WHERE target_table=? AND target_id=?
                ORDER BY id LIMIT ?
                """,
                (table, record_id, self.max_edges * 2),
            ).fetchall()
        for raw in rows:
            row = dict(raw)
            event_node = self.node_for_record("eventi_1gm", row["evento_id"])
            target = self.node_for_record(row["target_table"], row["target_id"])
            evidence = []
            if row.get("match_field") or row.get("match_value"):
                evidence.append(
                    GraphEvidence(
                        type="event_match",
                        label=str(row.get("match_field") or "Regola evento"),
                        value=str(row.get("match_value") or ""),
                        source_table=row["target_table"],
                        source_id=row["target_id"],
                        strength=_confidence(row.get("confidence")),
                    )
                )
            self.add_edge(
                edge_id=f"event_links:{row['id']}",
                source=event_node,
                target=target,
                relation_type=row["link_type"],
                source_system="event_links",
                source_edge_id=str(row["id"]),
                row=row,
                explanation=(
                    f"Associazione automatica tramite "
                    f"{row.get('match_field') or 'regola non registrata'}"
                    f"{': ' + str(row.get('match_value')) if row.get('match_value') else ''}. "
                    "Richiede verifica storica."
                ),
                evidence=evidence,
                algorithm=row.get("match_method") or "event-linker",
                algorithm_version=row.get("algorithm_version") or "legacy",
                created_at=row.get("created_at"),
            )

    def add_external_links(self, table: str, record_id: int) -> None:
        if not table_exists(self.main, "external_record_links"):
            return
        rows = self.main.execute(
            """
            SELECT * FROM external_record_links
            WHERE target_table=? AND target_record_id=?
            ORDER BY match_score DESC, id LIMIT ?
            """,
            (table, record_id, self.max_edges),
        ).fetchall()
        for raw in rows:
            row = dict(raw)
            source = self.node_for_record(
                "external_source_records", row["external_source_record_id"]
            )
            target = self.node_for_record(table, record_id)
            evidence = _evidence_items(
                row.get("evidence_json") or row.get("matched_fields_json"),
                source_table="external_source_records",
                source_id=row["external_source_record_id"],
            )
            contrary = _evidence_items(
                row.get("conflicting_fields_json"),
                role="contradicts",
                source_table="external_source_records",
                source_id=row["external_source_record_id"],
            )
            self.add_edge(
                edge_id=f"external_record_links:{row['id']}",
                source=source,
                target=target,
                relation_type=row["link_type"],
                source_system="external_record_links",
                source_edge_id=str(row["id"]),
                row=row,
                explanation=(row.get("explanation") or "Candidato generato dal confronto con una fonte esterna."),
                evidence=evidence,
                contrary=contrary,
                algorithm=row.get("match_method") or "external-source-matcher",
                algorithm_version="legacy",
                created_at=row.get("created_at"),
            )

    def add_claims(self, table: str, record_id: int) -> None:
        if not table_exists(self.main, "claims"):
            return
        aliases = {table}
        if table == "internati":
            aliases.update({"internato", "soldier", "persona"})
        placeholders = ",".join("?" for _ in aliases)
        rows = self.main.execute(
            f"""
            SELECT * FROM claims
            WHERE subject_id=? AND subject_type IN ({placeholders})
            ORDER BY id LIMIT ?
            """,
            (record_id, *sorted(aliases), min(50, self.max_edges)),
        ).fetchall()
        root = self.node_for_record(table, record_id)
        for raw in rows:
            row = dict(raw)
            if len(self.nodes) >= self.max_nodes:
                self.truncated = True
                return
            claim_id = int(row["id"])
            object_value = (
                row.get("object_label") or row.get("object_value") or row.get("original_value") or "valore non indicato"
            )
            claim_node = GraphNode(
                id=f"main:claims:{claim_id}",
                namespace="main",
                type="fatto",
                label=f"{str(row.get('predicate') or 'affermazione').replace('_', ' ')}: {object_value}",
                source_table="claims",
                source_id=claim_id,
                attributes={
                    "epistemic_status": row.get("epistemic_status"),
                    "review_status": row.get("review_status"),
                    "temporal_range_start": row.get("temporal_range_start"),
                    "temporal_range_end": row.get("temporal_range_end"),
                    "place": row.get("place"),
                },
            )
            self.nodes[claim_node.id] = claim_node
            evidence: list[GraphEvidence] = []
            if table_exists(self.main, "claim_evidence"):
                evidence_rows = self.main.execute(
                    "SELECT * FROM claim_evidence WHERE claim_id=? ORDER BY id LIMIT 20",
                    (claim_id,),
                ).fetchall()
                for evidence_row in evidence_rows:
                    item = dict(evidence_row)
                    evidence.append(
                        GraphEvidence(
                            type="claim_evidence",
                            label=item.get("page_or_frame") or "Evidenza della fonte",
                            value=item.get("supporting_quote") or item.get("note"),
                            source_table=item.get("source_table") or item.get("document_table"),
                            source_id=item.get("source_id") or item.get("document_id"),
                            role="contradicts" if item.get("evidence_role") == "contradicts" else "supports",
                            strength=_confidence(item.get("strength")),
                        )
                    )
            self.add_edge(
                edge_id=f"claims:{claim_id}",
                source=root,
                target=claim_node,
                relation_type="claim",
                source_system="claims",
                source_edge_id=str(claim_id),
                row={
                    "confidence": row.get("confidence"),
                    "match_status": row.get("epistemic_status"),
                    "review_status": row.get("review_status"),
                },
                explanation=(
                    f"Affermazione registrata con stato epistemico "
                    f"«{row.get('epistemic_status') or 'non specificato'}»."
                ),
                evidence=[item for item in evidence if item.role == "supports"],
                contrary=[item for item in evidence if item.role == "contradicts"],
                algorithm=row.get("extraction_method") or "claim-service",
                algorithm_version=str(row.get("version") or "1"),
                created_at=row.get("created_at"),
            )

    def expand(self, table: str, record_id: int) -> GraphNode:
        root = self.node_for_record(table, record_id)
        if not root:
            raise LookupError(f"Record {table}#{record_id} non trovato")
        if table == "eventi_1gm":
            self.add_event_links(table, record_id)
        elif table == "entita":
            self.add_entity_links(table, record_id)
        else:
            self.add_record_links(table, record_id)
            self.add_entity_links(table, record_id)
            self.add_event_links(table, record_id)
            self.add_external_links(table, record_id)
            self.add_claims(table, record_id)
        return root

    def build(self, table: str, record_id: int) -> GraphResponse:
        root = self.expand(table, record_id)
        if self.truncated:
            self.issue(
                "result_truncated",
                "warning",
                f"Grafo limitato a {self.max_nodes} nodi e {self.max_edges} relazioni.",
            )
        return GraphResponse(
            root=root,
            nodes=list(self.nodes.values()),
            edges=list(self.edges.values()),
            issues=self.issues,
            truncated=self.truncated,
            generated_at=_now(),
        )


def get_graph(
    table: str,
    record_id: int,
    *,
    max_nodes: int = 100,
    max_edges: int = 200,
    include_candidates: bool = True,
    include_rejected: bool = False,
) -> GraphResponse:
    get_table_spec(table)
    builder = GraphBuilder(
        max_nodes=max_nodes,
        max_edges=max_edges,
        include_candidates=include_candidates,
        include_rejected=include_rejected,
    )
    try:
        return builder.build(table, int(record_id))
    finally:
        builder.close()


def get_graph_many(
    records: Iterable[tuple[str, int]],
    *,
    max_nodes: int = 500,
    max_edges: int = 800,
    include_candidates: bool = True,
    include_rejected: bool = False,
) -> GraphBatch:
    builder = GraphBuilder(
        max_nodes=max_nodes,
        max_edges=max_edges,
        include_candidates=include_candidates,
        include_rejected=include_rejected,
    )
    roots: list[GraphNode] = []
    seen: set[tuple[str, int]] = set()
    try:
        for table, raw_id in records:
            key = (table, int(raw_id))
            if key in seen:
                continue
            seen.add(key)
            try:
                roots.append(builder.expand(*key))
            except (LookupError, ValueError) as exc:
                builder.issue("root_unavailable", "warning", str(exc), table, str(raw_id))
        if builder.truncated:
            builder.issue(
                "result_truncated",
                "warning",
                f"Grafo aggregato limitato a {builder.max_nodes} nodi e {builder.max_edges} relazioni.",
            )
        return GraphBatch(
            roots=roots,
            nodes=list(builder.nodes.values()),
            edges=list(builder.edges.values()),
            issues=list(builder.issues),
            truncated=builder.truncated,
        )
    finally:
        builder.close()


def _edge_exists(edge_id: str) -> bool:
    try:
        system, raw_id = edge_id.split(":", 1)
        source_id = int(raw_id)
    except (ValueError, TypeError):
        return False
    table_by_system = {
        "record_links": ("main", "record_links"),
        "collegamenti": ("main", "collegamenti"),
        "external_record_links": ("main", "external_record_links"),
        "claims": ("main", "claims"),
        "event_links": ("events", "event_links"),
    }
    if system not in table_by_system:
        return False
    database, table = table_by_system[system]
    try:
        conn = connect_database(database, read_only=True)
    except (FileNotFoundError, sqlite3.Error):
        return False
    try:
        if not table_exists(conn, table):
            return False
        return bool(conn.execute(f'SELECT 1 FROM "{table}" WHERE id=?', (source_id,)).fetchone())
    finally:
        conn.close()


def review_edge(edge_id: str, request: EdgeReviewRequest, reviewer: str) -> dict[str, Any]:
    if not _edge_exists(edge_id):
        raise LookupError(f"Relazione {edge_id} non trovata")
    status = request.status or {
        "accepted": "confirmed",
        "rejected": "rejected",
        "needs_more_evidence": "to_review",
    }[request.decision]
    if request.decision == "accepted" and status != "confirmed":
        raise ValueError("Una revisione accettata deve avere stato confirmed")
    if request.decision == "rejected" and status != "rejected":
        raise ValueError("Una revisione rifiutata deve avere stato rejected")
    conn = get_conn()
    try:
        available = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='graph_edge_reviews'"
        ).fetchone()
        if not available:
            raise RuntimeError("Migrazione graph core non applicata")
        reviewed_at = _now()
        conn.execute(
            """
            INSERT INTO graph_edge_reviews
                (edge_id, decision, status, note, reviewed_by, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
                decision=excluded.decision,
                status=excluded.status,
                note=excluded.note,
                reviewed_by=excluded.reviewed_by,
                reviewed_at=excluded.reviewed_at
            """,
            (edge_id, request.decision, status, request.note, reviewer, reviewed_at),
        )
        conn.commit()
        return {
            "edge_id": edge_id,
            "decision": request.decision,
            "status": status,
            "note": request.note,
            "reviewed_by": reviewer,
            "reviewed_at": reviewed_at,
        }
    finally:
        conn.close()
