"""Contratti canonici per relazioni, evidenze e metadati archivistici."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


GraphStatus = Literal[
    "confirmed",
    "probable",
    "candidate",
    "to_review",
    "rejected",
    "conflicting",
    "unverifiable",
    "broken",
]


class GraphNode(BaseModel):
    id: str
    namespace: str
    type: str
    label: str
    source_table: str
    source_id: int
    external_id: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    status: str = "active"

    @field_validator("label")
    @classmethod
    def label_must_be_readable(cls, value: str) -> str:
        value = (value or "").strip()
        if not value or value.lower() in {"undefined", "null", "none"}:
            raise ValueError("Il nodo non ha un'etichetta leggibile")
        return value


class GraphEvidence(BaseModel):
    type: str
    label: str
    value: Optional[str] = None
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    source_url: Optional[str] = None
    role: Literal["supports", "contradicts", "context"] = "supports"
    strength: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GraphReview(BaseModel):
    required: bool = True
    decision: Optional[Literal["accepted", "rejected", "needs_more_evidence"]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    note: Optional[str] = None


class GraphRelation(BaseModel):
    type: str
    label: str
    direction: Literal["directed", "undirected"] = "directed"


class GraphEdge(BaseModel):
    id: str
    source: GraphNode
    target: GraphNode
    relation: GraphRelation
    status: GraphStatus
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_label: Optional[Literal["alta", "media", "bassa"]] = None
    confidence_meaning: str = (
        "Punteggio tecnico del metodo di collegamento; non è una percentuale "
        "di verità storica."
    )
    explanation: str
    evidence: List[GraphEvidence] = Field(default_factory=list)
    contrary_signals: List[GraphEvidence] = Field(default_factory=list)
    algorithm: str
    algorithm_version: str
    source_system: str
    source_edge_id: Optional[str] = None
    review: GraphReview = Field(default_factory=GraphReview)
    created_at: Optional[str] = None
    last_verified_at: Optional[str] = None


class GraphIntegrityIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    source_system: Optional[str] = None
    source_edge_id: Optional[str] = None


class GraphResponse(BaseModel):
    root: GraphNode
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    issues: List[GraphIntegrityIssue] = Field(default_factory=list)
    truncated: bool = False
    generated_at: str


class GraphSearchItem(BaseModel):
    node: GraphNode
    matches: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class GraphSearchResponse(BaseModel):
    query: str
    items: List[GraphSearchItem]
    total: int
    databases: List[str] = Field(default_factory=list)
    partial: bool = False
    issues: List[str] = Field(default_factory=list)


class EdgeReviewRequest(BaseModel):
    decision: Literal["accepted", "rejected", "needs_more_evidence"]
    status: Optional[GraphStatus] = None
    note: Optional[str] = Field(default=None, max_length=2000)


class ArchivalMetadata(BaseModel):
    stable_id: str
    source_table: str
    source_id: int
    metadata_standard: str = "dcterms-compatible-v1"
    title: str
    creator: List[str] = Field(default_factory=list)
    subject: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    publisher: Optional[str] = None
    contributor: List[str] = Field(default_factory=list)
    date: Optional[str] = None
    type: Optional[str] = None
    format: Optional[str] = None
    identifier: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
    language: Optional[str] = None
    relation: List[str] = Field(default_factory=list)
    coverage: List[str] = Field(default_factory=list)
    rights: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)
    checksum: Optional[str] = None
    status: Literal["generated", "reviewed", "incomplete", "conflicting"] = "generated"
    algorithm_version: str
    generated_at: str
