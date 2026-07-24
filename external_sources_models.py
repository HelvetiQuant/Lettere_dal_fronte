"""Modelli Pydantic per il modulo Fonti Esterne Federate."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ExternalSourceRecordBase(BaseModel):
    provider: str
    archive_name: Optional[str] = None
    archive_branch: Optional[str] = None
    external_id: str
    record_level: str
    record_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    date_text: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    fonds_external_id: Optional[str] = None
    fonds_title: Optional[str] = None
    series_external_id: Optional[str] = None
    series_title: Optional[str] = None
    subseries_external_id: Optional[str] = None
    subseries_title: Optional[str] = None
    parent_external_id: Optional[str] = None
    reference_code: Optional[str] = None
    box_number: Optional[str] = None
    file_number: Optional[str] = None
    register_number: Optional[str] = None
    protocol_number: Optional[str] = None
    extent: Optional[str] = None
    language: Optional[str] = None
    people_metadata_json: Optional[str] = None
    places_metadata_json: Optional[str] = None
    military_units_metadata_json: Optional[str] = None
    camps_metadata_json: Optional[str] = None
    subjects_metadata_json: Optional[str] = None
    canonical_record_url: str
    parent_record_url: Optional[str] = None
    digital_object_available: bool = False
    digital_object_url: Optional[str] = None
    access_status: str = "active"
    source_notes: Optional[str] = None


class ExternalSourceRecordCreate(ExternalSourceRecordBase):
    pass


class ExternalSourceRecordOut(ExternalSourceRecordBase):
    id: int
    metadata_hash: Optional[str] = None
    http_status: Optional[int] = None
    first_seen_at: str
    last_verified_at: Optional[str] = None
    created_at: str
    updated_at: str
    person_mentions: List[Dict[str, Any]] = []
    digital_objects: List[Dict[str, Any]] = []
    record_links: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class ExternalPersonMentionBase(BaseModel):
    external_source_record_id: int
    surname_raw: Optional[str] = None
    name_raw: Optional[str] = None
    full_name_raw: Optional[str] = None
    normalized_surname: Optional[str] = None
    normalized_name: Optional[str] = None
    father_name_raw: Optional[str] = None
    mother_name_raw: Optional[str] = None
    birth_date_text: Optional[str] = None
    birth_date: Optional[str] = None
    birth_place_raw: Optional[str] = None
    residence_raw: Optional[str] = None
    rank_raw: Optional[str] = None
    military_unit_raw: Optional[str] = None
    service_number: Optional[str] = None
    prisoner_number: Optional[str] = None
    camp_raw: Optional[str] = None
    status_raw: Optional[str] = None
    event_date_text: Optional[str] = None
    event_place_raw: Optional[str] = None
    role_in_metadata: Optional[str] = None
    source_text: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_confidence: float = 1.0
    human_verified: bool = False


class ExternalPersonMentionOut(ExternalPersonMentionBase):
    id: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ExternalSourceFactBase(BaseModel):
    external_source_record_id: int
    external_person_mention_id: Optional[int] = None
    fact_type: str
    fact_value: Optional[str] = None
    date_text: Optional[str] = None
    date_value: Optional[str] = None
    place_raw: Optional[str] = None
    description: Optional[str] = None
    source_text: Optional[str] = None
    extraction_method: Optional[str] = None
    confidence: float = 1.0
    human_verified: bool = False


class ExternalSourceFactOut(ExternalSourceFactBase):
    id: int
    created_at: str

    class Config:
        from_attributes = True


class ExternalDigitalObjectBase(BaseModel):
    external_source_record_id: int
    external_object_id: Optional[str] = None
    object_type: Optional[str] = None
    media_type: Optional[str] = None
    label: Optional[str] = None
    viewer_url: Optional[str] = None
    page_url: Optional[str] = None
    download_url: Optional[str] = None
    iiif_manifest_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    digital_object_available: bool = False
    publicly_viewable: bool = False
    public_download_allowed: bool = False
    authorization_required: bool = False
    rights_statement: Optional[str] = None
    credit_line: Optional[str] = None


class ExternalDigitalObjectOut(ExternalDigitalObjectBase):
    id: int
    local_file_path: Optional[str] = None
    sha256: Optional[str] = None
    file_size: Optional[int] = None
    ocr_status: str = "pending"
    retrieved_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ExternalRecordLinkBase(BaseModel):
    external_source_record_id: int
    external_person_mention_id: Optional[int] = None
    target_table: str
    target_record_id: int
    target_entity_id: Optional[int] = None
    link_type: str
    match_status: str = "candidate"
    match_score: float = 0.0
    match_method: Optional[str] = None
    matched_fields_json: Optional[str] = None
    conflicting_fields_json: Optional[str] = None
    evidence_json: Optional[str] = None
    explanation: Optional[str] = None
    review_status: str = "pending"


class ExternalRecordLinkOut(ExternalRecordLinkBase):
    id: int
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ExternalRecordLinkReview(BaseModel):
    review_status: str = Field(..., pattern="^(accepted|rejected|needs_more_evidence)$")
    match_status: Optional[str] = Field(None, pattern="^(candidate|probable|confirmed|rejected|ambiguous)$")
    explanation: Optional[str] = None


class ExternalAccessRequestBase(BaseModel):
    external_source_record_id: int
    candidate_id: Optional[int] = None
    research_subject_id: Optional[int] = None
    request_status: str = "da_valutare"
    recipient: Optional[str] = None
    request_reason: Optional[str] = None
    requested_documents: Optional[str] = None
    usage_scope: Optional[str] = None
    publication_allowed: bool = False
    notes: Optional[str] = None


class ExternalAccessRequestOut(ExternalAccessRequestBase):
    id: int
    requested_at: Optional[str] = None
    response_received_at: Optional[str] = None
    authorization_reference: Optional[str] = None
    authorization_date: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ImportRequest(BaseModel):
    provider: str = Field(..., description="Provider ID (es: cri_milano, cri_central, grande_guerra)")
    fonds_url: Optional[str] = None
    max_records: Optional[int] = None
    force_refresh: bool = False


class ImportJobOut(BaseModel):
    id: int
    provider: str
    job_type: str
    status: str
    total_records: int = 0
    processed_records: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    items: List[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_next: bool = False
