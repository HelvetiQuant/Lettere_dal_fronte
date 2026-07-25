import { get, post, patch, del } from './http';
import type {
  SearchResult, ValidatedSearchResult, StatusResponse, DecoratiStatusResponse,
  EntitaStatsResponse, FondiListResponse, SourceStatsResponse,
  InternatoRecord, CadutoRecord, DecoratoRecord, EventRecord,
  InternatiDetailResponse, InternatiLinksResponse, InternatiFontiResponse,
  InternatiOpenGraphResponse, LeBICompareResponse, LeBISearchResponse,
  EventDossierResponse, EntitaDetailResponse,
  ResearchV2Result, ResearchV2PlanResponse, ResearchV2PlansResponse,
  LocatorValidation, PreflightResult,
  ResearchSubject, ResearchSubjectDetail, ResearchGap, ResearchStats,
  AIResearchResponse, AIResearchHistoryResponse,
  GraphLuoghiResponse, GraphMesiResponse, GraphPaesiResponse,
  EventResolution, EvidencePackage, NarrativeReport, AuditSummary, LinkAuditEntry,
  HistoricalMap,
  CanonicalEvent, CanonicalEventListResponse, CanonicalEventChildrenResponse,
  GraphEntityResponse, RAGContextResponse, RAGValidationResponse,
  MapFeatureRecord, MapFeatureListResponse,
} from './types';

export const api = {
  // ── Search ──
  search: (q: string, limit = 100) => get<SearchResult>('/api/search', { q, limit }),
  searchValidated: (q: string, limit = 100, external = true) =>
    get<ValidatedSearchResult>('/api/search-validated', { q, limit, external }),
  convSearch: (q: string, limit = 20, scope?: string) =>
    get<SearchResult>('/api/conv-search', { q, limit, ...(scope ? { scope } : {}) }),
  searchWW1: (q: string, limit = 100) => get<SearchResult>('/api/search/ww1', { q, limit }),
  searchConfirm: (confirmation: Record<string, unknown>) =>
    post<{ ok: boolean }>('/api/search/confirm', confirmation),

  // ── Stats / Status ──
  status: () => get<StatusResponse>('/api/status'),
  statsWW1: () => get<Record<string, unknown>>('/api/stats/ww1'),
  decoratiStatus: () => get<DecoratiStatusResponse>('/api/decorati'),
  entitaStats: () => get<EntitaStatsResponse>('/api/entita'),
  fondiList: () => get<FondiListResponse>('/api/fondi'),
  fontiRisorse: (fonteId?: number, limit = 100) =>
    get<Record<string, unknown>>('/api/fonti-risorse', { ...(fonteId ? { fonte_id: fonteId } : {}), limit }),
  fontiRisorseStats: () => get<Record<string, unknown>>('/api/fonti-risorse/stats'),
  sourceStats: () => get<SourceStatsResponse>('/api/source/stats'),

  // ── Internati ──
  internatiDetail: (id: number) => get<InternatiDetailResponse>(`/api/internati/${id}/detail`),
  internatiFonti: (id: number) => get<InternatiFontiResponse>(`/api/internati/${id}/fonti`),
  internatiLinks: (id: number) => get<InternatiLinksResponse>(`/api/internati/${id}/links`),
  internatiOpenGraph: (id: number) => get<InternatiOpenGraphResponse>(`/api/internati/${id}/opengraph`),

  // ── Caduti / Decorati ──
  cadutiDetail: (id: number) => get<CadutoRecord>(`/api/caduti/${id}`),
  decoratiDetail: (id: number) => get<DecoratoRecord>(`/api/decorati/${id}`),

  // ── Events ──
  events1gm: () => get<{ eventi: EventRecord[] }>('/api/events/1gm'),
  eventDossier: (eventName: string) =>
    get<EventDossierResponse>(`/api/events/1gm/${encodeURIComponent(eventName)}`),
  eventCaduti: (eventName: string, limit = 50) =>
    get<{ caduti: CadutoRecord[]; total: number }>(`/api/events/1gm/${encodeURIComponent(eventName)}/caduti`, { limit }),
  eventDecorati: (eventName: string, limit = 50) =>
    get<{ decorati: DecoratoRecord[]; total: number }>(`/api/events/1gm/${encodeURIComponent(eventName)}/decorati`, { limit }),
  eventInternati: (eventName: string, limit = 50) =>
    get<{ internati: InternatoRecord[]; total: number }>(`/api/events/${encodeURIComponent(eventName)}/internati`, { limit }),

  // ── Event Research Pipeline (nuova architettura) ──
  eventResolve: (q: string) =>
    get<EventResolution>('/api/event-research/resolve', { q }),
  eventEvidence: (q: string) =>
    get<EvidencePackage>('/api/event-research/evidence', { q }),
  eventNarrative: (q: string, ai = true, provider = 'mistral') =>
    get<NarrativeReport>('/api/event-research/narrative', { q, ai, provider }),
  eventAudit: () =>
    get<AuditSummary>('/api/event-research/audit'),
  eventAuditByEvent: (eventId: number) =>
    get<LinkAuditEntry[]>(`/api/event-research/audit/${eventId}`),
  eventMap: (q: string) =>
    get<HistoricalMap>('/api/event-research/map', { q }),
  eventMapSvgUrl: (q: string) =>
    `/api/event-research/map/svg?q=${encodeURIComponent(q)}`,

  // ── Graph (legacy stats) ──
  graphLuoghi: (limit = 50) => get<GraphLuoghiResponse>('/api/graph/luoghi', { limit }),
  graphMesi: () => get<GraphMesiResponse>('/api/graph/mesi'),
  graphPaesi: () => get<GraphPaesiResponse>('/api/graph/paesi'),
  graphSoldatiArch: () => get<Record<string, unknown>>('/api/graph/soldati/architecture'),
  graphSoldatiClusters: (field = 'luogo_morte', limit = 50) =>
    get<Record<string, unknown>>('/api/graph/soldati/clusters', { field, limit }),

  // ── Graph (canonical) ──
  graphEntity: (sourceTable: string, sourceId: number, opts?: { max_nodes?: number; max_edges?: number; include_candidates?: boolean; include_rejected?: boolean }) =>
    get<GraphEntityResponse>(`/api/graph/entity/${sourceTable}/${sourceId}`, opts),
  graphEdgeReview: (edgeId: string, body: { decision: string; status?: string; note?: string }) =>
    post<Record<string, unknown>>(`/api/graph/edges/${encodeURIComponent(edgeId)}/review`, body),

  // ── Canonical Events ──
  canonicalEvents: (opts?: { conflict?: string; event_type?: string; limit?: number }) =>
    get<CanonicalEventListResponse>('/api/canonical-events', opts),
  canonicalEvent: (stableId: string) =>
    get<CanonicalEvent>(`/api/canonical-events/${stableId}`),
  canonicalEventChildren: (stableId: string) =>
    get<CanonicalEventChildrenResponse>(`/api/canonical-events/${stableId}/children`),
  canonicalEventUpdate: (stableId: string, body: Record<string, unknown>) =>
    post<CanonicalEvent>(`/api/canonical-events/${stableId}`, body),

  // ── RAG Pipeline ──
  ragRetrieve: (q: string, opts?: { entity_type?: string; date_start?: string; date_end?: string; place?: string; max_chunks?: number; max_tokens?: number }) =>
    get<RAGContextResponse>('/api/rag/retrieve', { q, ...opts }),
  ragValidate: (body: { text: string; citations?: unknown[] }) =>
    post<RAGValidationResponse>('/api/rag/validate', body),

  // ── Map Features ──
  mapFeatures: (eventId: string) =>
    get<MapFeatureListResponse>(`/api/map-features/event/${eventId}`),
  mapFeatureCreate: (body: Record<string, unknown>) =>
    post<MapFeatureRecord>('/api/map-features/', body),
  mapFeatureReview: (featureId: string, body: { review_status: string; reviewed_by?: string }) =>
    post<MapFeatureRecord>(`/api/map-features/${featureId}/review`, body),

  // ── External Sources ──
  icrcSearch: (q: string, nationality = 'italy', status = '', files = '') =>
    get<Record<string, unknown>>('/api/icrc/search', { q, nationality, status, files }),
  icrcFilters: () => get<Record<string, unknown>>('/api/icrc/filters'),
  lebiSearch: (q: string) => post<LeBISearchResponse>('/api/lebi/search', { query: q }),
  lebiRecord: (id: string) => get<Record<string, unknown>>(`/api/lebi/record/${id}`),
  lebiCompare: (soldierId: number) => get<LeBICompareResponse>(`/api/lebi/compare/${soldierId}`),

  // ── Research Orchestrator V1 ──
  researchQuery: (query: string) => post<Record<string, unknown>>('/api/research/query', { query }),
  researchAutoIndex: (query: string) => post<Record<string, unknown>>('/api/research/auto-index', { query }),
  researchSubjects: (subjectType?: string, status?: string, limit = 50) =>
    get<{ subjects: ResearchSubject[]; total: number }>('/api/research/subjects',
      { ...(subjectType ? { subject_type: subjectType } : {}), ...(status ? { status } : {}), limit }),
  researchSubjectDetail: (id: number) => get<ResearchSubjectDetail>(`/api/research/subjects/${id}`),
  researchSubjectDashboard: (id: number) => get<ResearchSubjectDetail & { enrichment: Record<string, unknown>; stats: ResearchStats }>(`/api/research/subjects/${id}/dashboard`),
  researchSubjectUpdate: (id: number, body: Record<string, unknown>) =>
    patch<{ ok: boolean; subject_id: number; updated_fields: string[] }>(`/api/research/subjects/${id}`, body),
  researchGaps: (status = 'open', subjectId?: number) =>
    get<{ gaps: ResearchGap[]; count: number; status_filter: string }>('/api/research/gaps',
      { status, ...(subjectId ? { subject_id: subjectId } : {}) }),
  researchStats: () => get<ResearchStats>('/api/research/stats'),

  // ── Research Orchestrator V2 ──
  researchV2Create: (query: string, entityType?: string, entityId?: number,
                     budgetCycles = 5, budgetCostUsd = 1.0) =>
    post<ResearchV2Result>('/api/research/v2/create',
      { query, entity_type: entityType, entity_id: entityId, budget_cycles: budgetCycles, budget_cost_usd: budgetCostUsd }),
  researchV2Plan: (planId: number) => get<ResearchV2PlanResponse>(`/api/research/v2/plan/${planId}`),
  researchV2Plans: (status?: string, limit = 20) =>
    get<ResearchV2PlansResponse>('/api/research/v2/plans', { ...(status ? { status } : {}), limit }),
  locatorValidate: (url: string, domain?: string) =>
    post<LocatorValidation>('/api/research/v2/locator/validate', { url, domain }),
  researchV2Preflight: (connectorCode: string, operation: string,
                        targetUrl?: string, userRole = 'operator') =>
    post<PreflightResult>('/api/research/v2/preflight',
      { connector_code: connectorCode, operation, target_url: targetUrl, user_role: userRole }),
  researchV2Prompt: (promptName: string) => get<Record<string, unknown>>(`/api/research/v2/prompt/${promptName}`),

  // ── AI Research ──
  aiResearch: (data: { query: string; provider?: string; limit?: number }) =>
    post<AIResearchResponse>('/api/ai-research', data),
  aiResearchHistory: (limit = 20) =>
    get<AIResearchHistoryResponse>('/api/ai-research/history', { limit }),

  // ── Viewpoints (Punti di vista) ──
  viewpointsCreate: (query: string, useAi = false) =>
    post<Record<string, unknown>>('/api/viewpoints/create', { query, use_ai: useAi }),

  // ── Entita ──
  entitaSearch: (q: string, limit = 50) =>
    get<{ results: Record<string, unknown>[] }>('/api/entita/search', { q, limit }),
  entitaDetail: (id: number) => get<EntitaDetailResponse>(`/api/entita/${id}`),

  // ── NARA ──
  naraSearch: (q: string) => get<Record<string, unknown>>('/api/nara', { q }),
  naraEnrich: (id: number) => post<Record<string, unknown>>('/api/nara/enrich', { id }),

  // ── Admin ──
  entitaBuild: () => post<{ ok: boolean; message: string }>('/api/entita/build'),
  entitaStop: () => post<{ ok: boolean; message: string }>('/api/entita/stop'),
  decoratiScrape: (alboId?: string, details = true) =>
    post<{ ok: boolean; message: string; albo_id: string }>('/api/decorati/scrape', { albo_id: alboId, details }),
  decoratiStop: () => post<{ ok: boolean; message: string }>('/api/decorati/stop'),
  fondiExtractAll: (parallel = 2, engine = 'auto') =>
    post<{ ok: boolean; message: string }>('/api/fondi/extract-all', { parallel, engine }),
  fondiStop: () => post<{ ok: boolean; message: string }>('/api/fondi/stop'),
  fontiScrape: (fonteId?: number, url?: string) =>
    post<{ status: string; fonte_id: number; url: string }>('/api/fonti-risorse/scrape', { fonte_id: fonteId, url }),
  fondiAvailable: () => get<Record<string, unknown>>('/api/fondi/available'),
  fondiDownloadAll: () => post<Record<string, unknown>>('/api/fondi/download-all'),
};
