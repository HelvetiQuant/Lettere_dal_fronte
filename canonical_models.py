"""Contratti canonici Pydantic per AI Historical Integration.

Modelli tipizzati per:
- Evento canonico (con gerarchia, alias, fasi)
- Claim atomica (con evidenze, stato epistemico)
- Map feature (geometrie con provenance)
- Graph payload (nodi, archi, revisioni)
- Research job (asincrono, cancellabile)
- Report (discriminated union persona/evento)
- Errori strutturati
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ─── Enum ────────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    person = "person"
    event = "event"
    place = "place"
    unit = "unit"
    document = "document"
    source = "source"
    fact = "fact"
    organization = "organization"
    unknown = "unknown"


class ConflictType(str, Enum):
    wwi = "WWI"
    wwii = "WWII"
    other = "other"


class EventLevel(str, Enum):
    guerra = "guerra"
    campagna = "campagna"
    fronte = "fronte"
    offensiva = "offensiva"
    battaglia = "battaglia"
    fase = "fase"
    combattimento = "combattimento"
    occupazione = "occupazione"
    cattura = "cattura"
    deportazione = "deportazione"
    internamento = "internamento"
    eccidio = "eccidio"
    trattato = "trattato"
    amministrativo = "amministrativo"
    altro = "altro"


class EpistemicStatus(str, Enum):
    confirmed = "confirmed"
    probable = "probable"
    candidate = "candidate"
    to_review = "to_review"
    rejected = "rejected"
    conflicting = "conflicting"
    unverifiable = "unverifiable"
    broken = "broken"


class URLType(str, Enum):
    document = "document"
    record = "record"
    catalog_entry = "catalog_entry"
    search_page = "search_page"
    homepage = "homepage"
    download = "download"
    viewer = "viewer"
    broken = "broken"
    unknown = "unknown"
    empty = "empty"


class MapFeatureType(str, Enum):
    point = "point"
    line = "line"
    polygon = "polygon"
    front = "front"
    movement = "movement"
    advance = "advance"
    retreat = "retreat"
    position = "position"
    objective = "objective"
    defensive_line = "defensive_line"
    uncertain_area = "uncertain_area"


class MapCertainty(str, Enum):
    verified = "verified"
    probable = "probable"
    hypothesis = "hypothesis"
    uncertain = "uncertain"


class GraphEdgeStatus(str, Enum):
    confirmed = "confirmed"
    probable = "probable"
    candidate = "candidate"
    to_review = "to_review"
    rejected = "rejected"
    conflicting = "conflicting"
    unverifiable = "unverifiable"
    broken = "broken"


class ResearchJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# ─── Evento canonico ─────────────────────────────────────────────────────────

class EventAlias(BaseModel):
    name: str
    type: str = "alias"  # alias | variant | former_name | codename


class EventBase(BaseModel):
    stable_id: str = Field(description="ID stabile unico")
    preferred_name: str
    aliases: List[EventAlias] = []
    conflict: ConflictType
    event_type: EventLevel
    parent_event_id: Optional[str] = None
    child_event_ids: List[str] = []
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    temporal_precision: str = "day"  # day | month | year | approximate
    general_location: Optional[str] = None
    localities: List[str] = []
    subjects: List[str] = []
    units: List[str] = []
    description: Optional[str] = None
    review_status: EpistemicStatus = EpistemicStatus.candidate


class EventOut(EventBase):
    narrative: Optional[str] = None
    narrative_version: Optional[str] = None
    narrative_updated_at: Optional[str] = None
    map_available: bool = False
    people_count: int = 0
    sources_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class EventResolution(BaseModel):
    query: str
    resolved: bool
    event: Optional[EventOut] = None
    alternatives: List[EventOut] = []
    ambiguity: bool = False
    message: str = ""


# ─── Claim atomica ───────────────────────────────────────────────────────────

class ClaimEvidence(BaseModel):
    id: int
    claim_id: int
    source_id: Optional[int] = None
    source_table: Optional[str] = None
    document_id: Optional[int] = None
    document_table: Optional[str] = None
    page_or_frame: str = ""
    coordinates: str = ""
    supporting_quote: str = ""
    evidence_role: str = "supports"  # supports | contradicts | contextual
    source_independence_group: Optional[int] = None
    strength: float = 0.0
    note: str = ""
    created_at: str = ""


class Claim(BaseModel):
    id: int
    stable_id: str
    subject_type: str
    subject_id: Optional[int] = None
    subject_label: str
    predicate: str
    object_type: str
    object_id: Optional[int] = None
    object_label: str
    object_value: str
    original_value: str = ""
    temporal_range_start: str = ""
    temporal_range_end: str = ""
    temporal_precision: str = "day"
    temporal_uncertainty: Optional[str] = None
    place: str = ""
    epistemic_status: EpistemicStatus = EpistemicStatus.candidate
    confidence: float = 0.0
    extraction_method: str = ""
    review_status: str = "proposed"
    created_at: str = ""
    evidence: List[ClaimEvidence] = []


# ─── Map feature ─────────────────────────────────────────────────────────────

class MapFeature(BaseModel):
    id: str
    event_id: str
    phase: str = ""
    feature_type: MapFeatureType
    geojson: Dict[str, Any]
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    alignment: str = ""  # schieramento
    unit: str = ""
    function: str = ""
    label: str
    certainty: MapCertainty = MapCertainty.uncertain
    precision: str = ""
    source: str = ""
    evidence_id: Optional[int] = None
    note: str = ""
    review_status: str = "proposed"


class MapPayload(BaseModel):
    event_id: str
    event_name: str
    features: List[MapFeature] = []
    legend: Dict[str, str] = {}
    bounds: Optional[List[float]] = None  # [minLat, minLng, maxLat, maxLng]
    partial: bool = False
    missing_data_note: str = ""
    basemap_attribution: str = ""


# ─── Graph payload ───────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    namespace: str
    type: str
    label: str
    source_table: str = ""
    source_id: Optional[int] = None
    attributes: Dict[str, Any] = {}
    status: str = "active"


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    status: GraphEdgeStatus = GraphEdgeStatus.candidate
    confidence: float = 0.0
    explanation: str = ""
    evidence: List[Dict[str, Any]] = []
    contrary_signals: List[str] = []
    algorithm: str = ""
    algorithm_version: str = ""
    source_system: str = ""
    review_status: str = "pending"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None


class GraphPayload(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    total_nodes: int = 0
    total_edges: int = 0
    truncated: bool = False


# ─── Research job ────────────────────────────────────────────────────────────

class ResearchJobCreate(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    entity_type: EntityType = EntityType.unknown
    use_ai: bool = False
    use_external: bool = False
    options: Dict[str, Any] = {}


class ResearchJobOut(BaseModel):
    id: str
    query: str
    entity_type: EntityType
    status: ResearchJobStatus
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: str = ""
    created_at: str = ""
    updated_at: str = ""


# ─── Report (discriminated union) ────────────────────────────────────────────

class PersonReport(BaseModel):
    entity_type: Literal["person"] = "person"
    entity_id: str
    narrative: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []
    claims: List[Claim] = []
    conflicts: List[Dict[str, Any]] = []
    visualization_kind: Literal["relationship_graph"] = "relationship_graph"
    graph: Optional[GraphPayload] = None


class EventReport(BaseModel):
    entity_type: Literal["event"] = "event"
    entity_id: str
    narrative: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []
    claims: List[Claim] = []
    timeline: List[Dict[str, Any]] = []
    phases: List[Dict[str, Any]] = []
    visualization_kind: Literal["event_map"] = "event_map"
    map: Optional[MapPayload] = None
    people: List[Dict[str, Any]] = []
    documents: List[Dict[str, Any]] = []


Report = Union[PersonReport, EventReport]


# ─── Errori strutturati ──────────────────────────────────────────────────────

class StructuredError(BaseModel):
    code: str
    message: str
    detail: str = ""
    request_id: str = ""
    retryable: bool = False
    partial_state: Optional[Dict[str, Any]] = None
    action_required: str = ""


class InsufficientEvidenceError(StructuredError):
    code: str = "insufficient_evidence"
    message: str = "Evidenze insufficienti per generare una narrazione."
    retryable: bool = False
