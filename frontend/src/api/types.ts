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
  caduti?: { items: CadutoRecord[]; total: number };
  decorati?: { items: DecoratoRecord[]; total: number };
  internati?: { items: InternatoRecord[]; total: number };
  documenti?: { items: DocumentoRecord[]; total: number };
  fonti?: { items: FonteIndiceRecord[]; total: number };
  total_fonti?: number;
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
