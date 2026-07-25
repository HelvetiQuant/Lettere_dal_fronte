/** Canonical TypeScript types for AI Historical Integration.
 *
 * Mirrors the Pydantic models in canonical_models.py.
 * Eliminates `any` in critical API responses.
 */

// ─── Enums ──────────────────────────────────────────────────────────────────

export type EntityType = 'person' | 'event' | 'place' | 'unit' | 'document' | 'source' | 'fact' | 'organization' | 'unknown';

export type ConflictType = 'WWI' | 'WWII' | 'other';

export type EventLevel =
  | 'guerra' | 'campagna' | 'fronte' | 'offensiva' | 'battaglia'
  | 'fase' | 'combattimento' | 'occupazione' | 'cattura' | 'deportazione'
  | 'internamento' | 'eccidio' | 'trattato' | 'amministrativo' | 'altro';

export type EpistemicStatus =
  | 'confirmed' | 'probable' | 'candidate' | 'to_review'
  | 'rejected' | 'conflicting' | 'unverifiable' | 'broken';

export type URLType =
  | 'document' | 'record' | 'catalog_entry' | 'search_page'
  | 'homepage' | 'download' | 'viewer' | 'broken' | 'unknown' | 'empty';

export type MapFeatureType =
  | 'point' | 'line' | 'polygon' | 'front' | 'movement'
  | 'advance' | 'retreat' | 'position' | 'objective'
  | 'defensive_line' | 'uncertain_area';

export type MapCertainty = 'verified' | 'probable' | 'hypothesis' | 'uncertain';

export type GraphEdgeStatus =
  | 'confirmed' | 'probable' | 'candidate' | 'to_review'
  | 'rejected' | 'conflicting' | 'unverifiable' | 'broken';

export type ResearchJobStatus =
  | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

// ─── Event ──────────────────────────────────────────────────────────────────

export interface EventAlias {
  name: string;
  type: string;
}

export interface CanonicalEvent {
  stable_id: string;
  preferred_name: string;
  aliases: EventAlias[];
  conflict: ConflictType;
  event_type: EventLevel;
  parent_event_id: string | null;
  child_event_ids: string[];
  date_start: string | null;
  date_end: string | null;
  temporal_precision: string;
  general_location: string | null;
  localities: string[];
  subjects: string[];
  units: string[];
  description: string | null;
  review_status: EpistemicStatus;
  narrative?: string;
  narrative_version?: string;
  narrative_updated_at?: string;
  map_available?: boolean;
  people_count?: number;
  sources_count?: number;
}

export interface EventResolution {
  query: string;
  resolved: boolean;
  event: CanonicalEvent | null;
  alternatives: CanonicalEvent[];
  ambiguity: boolean;
  message: string;
}

// ─── Claim ──────────────────────────────────────────────────────────────────

export interface ClaimEvidence {
  id: number;
  claim_id: number;
  source_id: number | null;
  source_table: string | null;
  document_id: number | null;
  document_table: string | null;
  page_or_frame: string;
  coordinates: string;
  supporting_quote: string;
  evidence_role: 'supports' | 'contradicts' | 'contextual';
  source_independence_group: number | null;
  strength: number;
  note: string;
  created_at: string;
}

export interface Claim {
  id: number;
  stable_id: string;
  subject_type: string;
  subject_id: number | null;
  subject_label: string;
  predicate: string;
  object_type: string;
  object_id: number | null;
  object_label: string;
  object_value: string;
  original_value: string;
  temporal_range_start: string;
  temporal_range_end: string;
  temporal_precision: string;
  temporal_uncertainty: string | null;
  place: string;
  epistemic_status: EpistemicStatus;
  confidence: number;
  extraction_method: string;
  review_status: string;
  created_at: string;
  evidence: ClaimEvidence[];
}

// ─── Map ────────────────────────────────────────────────────────────────────

export interface MapFeature {
  id: string;
  event_id: string;
  phase: string;
  feature_type: MapFeatureType;
  geojson: GeoJSON.Feature;
  date_start: string | null;
  date_end: string | null;
  alignment: string;
  unit: string;
  function: string;
  label: string;
  certainty: MapCertainty;
  precision: string;
  source: string;
  evidence_id: number | null;
  note: string;
  review_status: string;
}

export interface MapPayload {
  event_id: string;
  event_name: string;
  features: MapFeature[];
  legend: Record<string, string>;
  bounds: [number, number, number, number] | null;
  partial: boolean;
  missing_data_note: string;
  basemap_attribution: string;
}

// ─── Graph ──────────────────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  namespace: string;
  type: string;
  label: string;
  source_table: string;
  source_id: number | null;
  attributes: Record<string, unknown>;
  status: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  status: GraphEdgeStatus;
  confidence: number;
  explanation: string;
  evidence: Record<string, unknown>[];
  contrary_signals: string[];
  algorithm: string;
  algorithm_version: string;
  source_system: string;
  review_status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  truncated: boolean;
}

// ─── Research job ───────────────────────────────────────────────────────────

export interface ResearchJobCreate {
  query: string;
  entity_type: EntityType;
  use_ai: boolean;
  use_external: boolean;
  options: Record<string, unknown>;
}

export interface ResearchJobOut {
  id: string;
  query: string;
  entity_type: EntityType;
  status: ResearchJobStatus;
  progress: number;
  result: Record<string, unknown> | null;
  error: string;
  created_at: string;
  updated_at: string;
}

// ─── Report (discriminated union) ───────────────────────────────────────────

export interface PersonReport {
  entity_type: 'person';
  entity_id: string;
  narrative: Record<string, unknown>;
  sources: Record<string, unknown>[];
  claims: Claim[];
  conflicts: Record<string, unknown>[];
  visualization_kind: 'relationship_graph';
  graph: GraphPayload | null;
}

export interface EventReport {
  entity_type: 'event';
  entity_id: string;
  narrative: Record<string, unknown>;
  sources: Record<string, unknown>[];
  claims: Claim[];
  timeline: Record<string, unknown>[];
  phases: Record<string, unknown>[];
  visualization_kind: 'event_map';
  map: MapPayload | null;
  people: Record<string, unknown>[];
  documents: Record<string, unknown>[];
}

export type Report = PersonReport | EventReport;

// ─── Errori strutturati ─────────────────────────────────────────────────────

export interface StructuredError {
  code: string;
  message: string;
  detail: string;
  request_id: string;
  retryable: boolean;
  partial_state: Record<string, unknown> | null;
  action_required: string;
}
