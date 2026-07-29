export interface SearchResult {
  internati?: InternatoRecord[];
  menzioni?: MenzioneRecord[];
  decorati?: DecoratoRecord[];
  caduti?: CadutoRecord[];
  documenti?: DocumentoRecord[];
  fonti_narrative?: FonteNarrativa[];
  lettere_personali?: LetteraPersonale[];
  events?: EventRecord[];
}

export interface ValidatedSearchResult extends SearchResult {
  status?: 'ok' | 'needs_confirmation';
  confirmations?: ConfirmationItem[];
  external_results?: ExternalSourceHit[];
}

export interface InternatoRecord {
  id: number;
  cognome: string;
  nome: string;
  data_nascita?: string;
  luogo_nascita?: string;
  grado?: string;
  luogo_internamento?: string;
  data_cattura?: string;
  luogo_cattura?: string;
  matricola?: string;
  sorte?: string;
  raw_text?: string;
  has_fonti?: boolean;
  fonti_indice?: FonteIndiceRecord[];
  eventi?: { nome: string; descrizione?: string }[];
}

export interface CadutoRecord {
  id: number;
  nominativo: string;
  grado?: string;
  reparto?: string;
  anno_morte?: number;
  luogo_morte?: string;
  detail_url?: string;
  img_url?: string;
}

export interface DecoratoRecord {
  id: number;
  cognome: string;
  nome: string;
  grado?: string;
  decorazione?: string;
  motivazione?: string;
}

export interface MenzioneRecord {
  id: number;
  nominativo?: string;
  fonte?: string;
  testo?: string;
}

export interface DocumentoRecord {
  id: number;
  titolo?: string;
  tipo?: string;
  url?: string;
}

export interface FonteNarrativa {
  id: number;
  titolo?: string;
  autore?: string;
  url?: string;
  path_locale?: string;
}

export interface LetteraPersonale {
  id: number;
  mittente?: string;
  destinatario?: string;
  data?: string;
  testo?: string;
  file_path?: string;
}

export interface FonteIndiceRecord {
  id: number;
  titolo?: string;
  archivio?: string;
  url_catalogo?: string;
  url_file?: string;
  tipo_fonte?: string;
  note?: string;
}

export interface EventRecord {
  id?: number;
  nome: string;
  descrizione?: string;
  data_inizio?: string;
  data_fine?: string;
  luogo?: string;
  total_links?: number;
  caduti?: number;
  decorati?: number;
  documenti?: number;
  fonti?: number;
  internati?: number;
}

export interface ExternalSourceHit {
  provider: string;
  title: string;
  url: string;
  description?: string;
  score?: number;
  error?: string;
}

export interface ConfirmationItem {
  type: string;
  record_id: number;
  record_table: string;
  field: string;
  current_value: string;
  corrected_value: string;
  confidence: number;
}

export interface StatusResponse {
  letters: { letter: string; total: number; done: number; downloaded: boolean; progress?: { lettera: string; total_pages: number; processed_pages: number; status: string } }[];
  total_internati: number;
  needs_review: number;
  running: string | null;
}

export interface DecoratiStatusResponse {
  count: number;
  albo: { id: string; nome: string; count: number }[];
  progress: { status: string; albo: string; processed: number; total: number };
}

export interface EntitaStatsResponse {
  count_entita: number;
  count_collegamenti: number;
  progress: { status: string; processed: number; total: number; current: string };
}

export interface FondiListResponse {
  fondi: { id: number; titolo: string; menzioni: number }[];
  count_fondi: number;
  count_menzioni: number;
  running: string | null;
}

export interface SourceStatsResponse {
  total_sources: number;
  by_archive: { archivio: string; count: number }[];
  by_fetch_status: { mai_scaricato: number };
  cache_count: number;
  cache_total_bytes: number;
  providers: number;
  provider_names: string[];
}

export interface ResearchPlan {
  id: number;
  original_input: string;
  entity_type: string;
  entity_id?: number;
  objective: string;
  status: string;
  budget_cycles: number;
  budget_cost_usd: number;
  created_at: string;
  updated_at: string;
  initial_context_json?: string;
  gaps_to_fill_json?: string;
}

export interface ResearchCycle {
  cycle_id: number;
  cycle_number: number;
  decision: string;
  stop_reason: string;
  internal_results: number;
  external_results: number;
  fragments: Fragment[];
}

export interface Fragment {
  type: string;
  source: string;
  entity_id?: number;
  value?: string;
  clue: string;
  url?: string;
  title?: string;
  score?: number;
}

export interface TimelineEntry {
  date_start?: string;
  date_end?: string;
  predicate: string;
  object_value: string;
  epistemic_status?: string;
}

export interface ResearchV2Result {
  plan_id: number;
  entity_type: string;
  entity_id: number;
  cycles: ResearchCycle[];
  facts?: {
    claims_created: number;
    claims_existing: number;
    claim_ids: number[];
    conflicts: unknown[];
    timeline: TimelineEntry[];
  };
  timeline?: TimelineEntry[];
  narrative?: { text: string; provider: string } | null;
}

export interface ResearchV2PlanResponse {
  plan: ResearchPlan;
  sessions: { id: number; plan_id: number; started_at: string; ended_at?: string; status: string }[];
  cycles: ResearchCycle[];
  traces: unknown[];
}

export interface ResearchV2PlansResponse {
  plans: ResearchPlan[];
}

export interface LocatorValidation {
  url: string;
  url_kind: 'source' | 'search_page' | 'homepage' | 'empty';
  is_valid_locator: boolean;
  scheme_ok: boolean;
  domain: string;
  issues: string[];
}

export interface PreflightResult {
  allowed: boolean;
  decision: string;
  reason: string;
  policy_id: number | null;
  policy_version?: string;
}

export interface ResearchSubject {
  id: number;
  name: string;
  subject_type: string;
  status: string;
  confidence: number;
  created_at: string;
  updated_at: string;
  date_start?: string;
  date_end?: string;
  place?: string;
  unit?: string;
  linked_soldier_id?: number;
}

export interface ResearchSubjectDetail {
  subject: ResearchSubject;
  sources: (ResearchSubjectSource & Record<string, unknown>)[];
  gaps: ResearchGap[];
}

export interface ResearchSubjectSource {
  subject_id: number;
  source_locator_id: number;
  confidence: number;
  archivio?: string;
  titolo?: string;
  url_catalogo?: string;
  access_type?: string;
  segnatura?: string;
}

export interface ResearchGap {
  id: number;
  subject_id: number;
  gap_type: string;
  description: string;
  priority: number;
  status: string;
  created_at: string;
  subject_name?: string;
  subject_type?: string;
}

export interface ResearchStats {
  total_subjects?: number;
  total_sources?: number;
  total_gaps?: number;
  open_gaps?: number;
  [key: string]: unknown;
}

export interface InternatiDetailResponse extends InternatoRecord {
  ok?: boolean;
}

export interface InternatiLinksResponse {
  links: {
    id: number;
    from_table: string;
    from_id: number;
    to_table: string;
    to_id: number;
    link_type: string;
    confidence?: number;
  }[];
}

export interface InternatiFontiResponse {
  fonti: FonteIndiceRecord[];
}

export interface InternatiOpenGraphResponse {
  card?: {
    title?: string;
    description?: string;
    image?: string;
    url?: string;
  };
}

export interface LeBICompareResponse {
  records?: {
    id: string;
    nome: string;
    cognome: string;
    camp?: string;
    match: boolean;
    pdf_url?: string;
    fields?: { label: string; imi_value: string; lebi_value: string; match: boolean }[];
  }[];
}

export interface LeBISearchResponse {
  results?: {
    id: string;
    nome: string;
    cognome: string;
    camp?: string;
    pdf_url?: string;
  }[];
}

export interface AIResearchResponse {
  provider: string;
  query: string;
  analysis?: string;
  sintesi?: string;
  persone?: unknown[];
  luoghi?: unknown[];
  eventi?: unknown[];
  fonti?: string[];
  collegamenti?: unknown[];
  approfondimenti?: string[];
  error?: string;
}

export interface AIResearchHistoryResponse {
  ricerche: {
    id: number;
    query: string;
    provider: string;
    created_at: string;
    analysis?: string;
  }[];
}

export interface GraphLuoghiResponse {
  nodes: { id: string; label: string; size: number }[];
  links: { source: string; target: string; value: number }[];
}

export interface GraphMesiResponse {
  mesi: { mese: string; caduti: number; decorati: number }[];
}

export interface GraphPaesiResponse {
  paesi: { paese: string; caduti: number }[];
}

export interface EventDossierResponse {
  ok?: boolean;
  source?: string;
  event?: EventRecord;
  evento?: EventRecord;
  caduti?: { items: CadutoRecord[]; total: number };
  decorati?: { items: DecoratoRecord[]; total: number };
  internati?: { items: InternatoRecord[]; total: number };
  documenti?: { items: DocumentoRecord[]; total: number };
  fonti?: { items: FonteIndiceRecord[]; total: number };
  total_fonti?: number;
}

// ── Event Research Pipeline (nuova architettura) ──

export interface EventMatch {
  id: number;
  nome: string;
  aliases: string[];
  keywords: string[];
  data_inizio: string;
  data_fine: string;
  luogo: string;
  descrizione: string;
  score: number;
  match_source: string;
  event_type: string;
  parent_events: string[];
  child_events: string[];
  is_collection: boolean;
}

export interface EventResolution {
  query: string;
  is_event: boolean;
  canonical: string | null;
  canonical_id: number | null;
  matches: EventMatch[];
  ambiguity_warning: string | null;
  proposed_distinctions: { type: string; nome: string; periodo: string; luogo: string; descrizione: string }[];
  conflict: string;
  confidence: number;
}

export interface EventSource {
  source_id: string;
  title: string;
  source_type: string;
  authority: string;
  url: string;
  archive_reference: string;
  author_or_institution: string;
  date: string;
  excerpt: string;
  summary: string;
  availability: string;
  relevance_score: number;
  temporal_compatible: boolean;
  geographic_compatible: boolean;
  verification_status: string;
  verification_note: string;
}

export interface EventClaim {
  claim_id: string;
  text: string;
  claim_type: string;
  value: string;
  sources: string[];
  confidence: string;
  concordance: string;
  conflicting_claims: string[];
}

export interface EvidencePackage {
  event_name: string;
  event_id: number | null;
  resolution: EventResolution;
  sources: EventSource[];
  claims: EventClaim[];
  concordant_facts: EventClaim[];
  divergent_versions: EventClaim[];
  uncertain_elements: EventClaim[];
  archival_sources: EventSource[];
  bibliographic_sources: EventSource[];
  web_sources: EventSource[];
  related_people: Record<string, unknown>[];
  related_documents: Record<string, unknown>[];
  graph_data: { nodes: Record<string, unknown>[]; edges: Record<string, unknown>[] };
  collection_date: string;
}

export interface NarrativeParagraph {
  section: string;
  text: string;
  source_ids: string[];
  source_labels: string[];
}

export interface NarrativeReport {
  event_name: string;
  event_id: number | null;
  resolution: EventResolution;
  sections: NarrativeParagraph[];
  inquadramento: string;
  narrazione: string;
  cronologia: { data: string; fase: string; descrizione: string; fonti: string[] }[];
  luoghi: { nome: string; ruolo: string; fonti: string[] }[];
  reparti: { nome: string; ruolo: string; fonti: string[] }[];
  cause_conseguenze: string;
  sintesi_concordanti: string;
  fatti_concordanti: { fatto: string; fonti: string[] }[];
  versioni_divergenti: { fatto: string; versione_a: string; fonte_a: string; versione_b: string; fonte_b: string }[];
  elementi_incerti: { elemento: string; motivo: string; fonti: string[] }[];
  fonti_archivistiche: EventSource[];
  fonti_bibliografiche: EventSource[];
  grafo: { nodes: Record<string, unknown>[]; edges: Record<string, unknown>[] };
  persone_collegate: Record<string, unknown>[];
  evidence_package: EvidencePackage;
  ai_used: boolean;
  ai_model: string | null;
}

export interface LinkAuditEntry {
  link_id: number;
  evento_id: number;
  evento_nome: string;
  target_table: string;
  target_id: number;
  link_type: string;
  match_field: string;
  match_value: string;
  original_confidence: number;
  match_method: string;
  temporal_compatible: boolean;
  geographic_compatible: boolean;
  military_context: boolean;
  review_status: string;
  review_reason: string;
  audit_date: string;
}

export interface AuditSummary {
  total_links: number;
  candidates: number;
  probable: number;
  confirmed: number;
  rejected: number;
  by_link_type: Record<string, Record<string, number>>;
  by_event: Record<string, Record<string, number>>;
  issues: string[];
}

// ── Historical Map ──

export interface MapLocation {
  name: string;
  lat: number;
  lon: number;
  role: string;
  phase: string | null;
  source_ids: string[];
  verification: string;
  label_number: number;
}

export interface MapLine {
  name: string;
  points: { lat: number; lon: number }[];
  line_type: string;
  style: string;
  color: string;
  phase: string | null;
  source_ids: string[];
  verification: string;
}

export interface MapMovement {
  name: string;
  from: { lat: number; lon: number };
  to: { lat: number; lon: number };
  movement_type: string;
  date: string;
  phase: string | null;
  source_ids: string[];
  verification: string;
  label_number: number;
}

export interface MapPhase {
  name: string;
  start_date: string;
  end_date: string;
  color: string;
  description: string;
}

export interface HistoricalMap {
  event_name: string;
  title: string;
  is_partial: boolean;
  partial_note: string;
  locations: MapLocation[];
  lines: MapLine[];
  movements: MapMovement[];
  phases: MapPhase[];
  bounding_box: { min_lat: number; min_lon: number; max_lat: number; max_lon: number };
  svg: string;
  legend: { symbol: string; meaning: string }[];
  source_references: Record<string, string>;
  sub_maps: HistoricalMap[];
}

export interface EntitaDetailResponse {
  entita: { id: number; nome: string; tipo: string };
  collegamenti: {
    id: number;
    from_table: string;
    from_id: number;
    to_table: string;
    to_id: number;
    link_type: string;
    confidence: number;
  }[];
}

// ── Canonical Event ──

export interface CanonicalEvent {
  stable_id: string;
  id: number;
  preferred_name: string;
  aliases: { name: string; type: string }[];
  conflict: string;
  event_type: string;
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
  review_status: string;
  narrative_version: string | null;
  narrative_updated_at: string | null;
}

export interface CanonicalEventListResponse {
  events: CanonicalEvent[];
  total: number;
}

export interface CanonicalEventChildrenResponse {
  parent: CanonicalEvent;
  children: CanonicalEvent[];
}

// ── Graph Entity (canonical graph) ──

export interface GraphNodeDTO {
  id: string;
  namespace: string;
  type: string;
  label: string;
  source_table: string;
  source_id: number;
  external_id: string | null;
  attributes: Record<string, unknown>;
  status: string;
}

export interface GraphEvidenceDTO {
  type: string;
  label: string;
  value: string | null;
  source_table: string | null;
  source_id: number | null;
  source_url: string | null;
  role: 'supports' | 'contradicts' | 'context';
  strength: number | null;
}

export interface GraphEdgeDTO {
  id: string;
  source: GraphNodeDTO;
  target: GraphNodeDTO;
  relation: { type: string; label: string; direction: string };
  status: string;
  confidence: number | null;
  confidence_label: string | null;
  confidence_meaning: string;
  explanation: string;
  evidence: GraphEvidenceDTO[];
  contrary_signals: GraphEvidenceDTO[];
  algorithm: string;
  algorithm_version: string;
  source_system: string;
  source_edge_id: string | null;
  review: {
    required: boolean;
    decision: string | null;
    reviewed_by: string | null;
    reviewed_at: string | null;
    note: string | null;
  };
  created_at: string | null;
  last_verified_at: string | null;
}

export interface GraphIntegrityIssueDTO {
  code: string;
  severity: 'info' | 'warning' | 'error';
  message: string;
  source_system: string | null;
  source_edge_id: string | null;
}

export interface GraphEntityResponse {
  root: GraphNodeDTO;
  nodes: GraphNodeDTO[];
  edges: GraphEdgeDTO[];
  issues: GraphIntegrityIssueDTO[];
  truncated: boolean;
  generated_at: string;
}

// ── RAG Pipeline ──

export interface RAGChunkDTO {
  chunk_id: string;
  source_table: string;
  source_id: number;
  title: string;
  text: string;
  score: number;
  retrieval_method: string;
  metadata: Record<string, unknown>;
  reranked_score: number;
  rerank_reasons: string[];
}

export interface RAGContextResponse {
  system_prompt: string;
  user_context: string;
  chunks: RAGChunkDTO[];
  citations: { index: number; source_table: string; source_id: number; title: string; score: number; reasons: string[] }[];
  token_estimate: number;
  truncated: boolean;
  warnings: string[];
}

export interface RAGValidationResponse {
  valid: boolean;
  issues: string[];
}

// ── Map Features ──

export interface MapFeatureRecord {
  id: string;
  event_id: string;
  phase: string;
  feature_type: string;
  geojson: Record<string, unknown>;
  date_start: string | null;
  date_end: string | null;
  label: string;
  description: string | null;
  certainty: string;
  source_table: string | null;
  source_id: number | null;
  source_url: string | null;
  review_status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MapFeatureListResponse {
  features: MapFeatureRecord[];
  total: number;
}

// ── AI Runtime ──

export interface AIRuntimeHealth {
  healthy: boolean;
  provider: string;
  model: string;
  detail: string;
  local: boolean;
}

export interface AIRuntimeConfig {
  provider: string;
  local_only: boolean;
  lm_studio_configured: boolean;
  generation: Record<string, unknown>;
  embedding: Record<string, unknown>;
  remote_fallback_order: string[];
}

export interface AIRuntimeBenchmark {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  text_preview: string;
  error: string;
}

// ── Chat ──

export interface ChatMessageDTO {
  role: string;
  content: string;
}

export interface ChatResponseDTO {
  risposta: string;
  provider: string;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  local: boolean;
}

export interface ChatHealthDTO {
  available: boolean;
  provider: string;
  model: string;
  local: boolean;
  detail: string;
}

// ── Chat Research (Person Finder) ──

export interface ResearchParsedInput {
  nome?: string;
  cognome?: string;
  anno_nascita?: string;
  luogo_nascita?: string;
  conflitto_presunto?: string;
  [key: string]: unknown;
}

export interface ResearchCandidate {
  nome_originale: string;
  nome_normalizzato: string;
  stato: string;
  compatibilita: string[];
  contraddizioni: string[];
  fonti: Array<{
    istituzione: string;
    source_level: string;
    url: string;
    esito: string;
  }>;
  confidence: number;
}

export interface ResearchDossier {
  stato_identificazione: string;
  profilo: Record<string, unknown>;
  candidati: ResearchCandidate[];
  omonimi_esclusi: ResearchCandidate[];
  fonti: Array<Record<string, unknown>>;
  contraddizioni: Array<Record<string, unknown>>;
  ricerche_negative: Array<Record<string, unknown>>;
  piste: Array<Record<string, unknown>>;
  richieste: Array<{
    ente: string;
    fondo: string;
    documento_richiesto: string;
    dati_conosciuti: string;
    motivazione: string;
  }>;
  varianti: Array<{ text: string; variant_type: string }>;
  ai_used: boolean;
  ai_model: string;
}

export interface ResearchChatResponse {
  conversation_id: string;
  answer: string;
  dossier: ResearchDossier;
  parsed_input: ResearchParsedInput;
  ai_used: boolean;
  ai_model: string;
}
