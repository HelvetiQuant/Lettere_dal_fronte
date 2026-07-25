# ADR: AI Historical RAG, Event Maps, and Graph Architecture

**Date:** 2026-07-25  
**Status:** Proposed  
**Branch:** `devin/ai-storica-eventi-mappe`

---

## Context

The platform "Lettere dal Fronte" manages historical data about Italian soldiers (IMI, decorated, fallen) across multiple conflicts (WWI, WWII). The current system has:

- 162 backend endpoints (FastAPI)
- 15 frontend routes (React 19)
- 1.8 GB SQLite database with 68 tables
- 169K legacy record_links (all candidate, zero evidence)
- 891K event_links (no evidence column)
- 22 events mixing WWI and WWII in `eventi_1gm`
- Graph schema tables defined in refactor but NOT deployed
- Only Mistral AI provider functional (OpenAI/Perplexity invalid keys, Anthropic no credit)
- No GPU (Intel i5-1135G7, 16 GB RAM)

## Decision

### 1. RAG as primary operational source

**Rationale:** The system already has rich structured data (20K internati, 35K fonti_indice, 10K menzioni, 1.5K NARA documents). RAG retrieves and cites these real sources. Fine-tuning would risk hallucination and cannot provide per-query citations.

**Implementation:**
- Hybrid retrieval: full-text (FTS5) + semantic (embeddings) + metadata filters
- Reranking by source quality, temporal/geographic compatibility, independence
- Context builder with explicit "no external knowledge" instruction
- Structured output validation (Pydantic) rejecting uncited claims

### 2. Fine-tuning is optional and deferred

**Rationale:** Fine-tuning improves format/style, not factual accuracy. It cannot replace source citations. The RAG pipeline must work first.

**Condition:** Fine-tuning (LoRA/QLoRA) only after RAG + evaluation passes, with reviewed gold dataset, hardware compatibility, and explicit approval.

### 3. SQLite remains in use

**Rationale:** The 1.8 GB database is operational and performant. Switching to PostgreSQL during this integration would risk data loss and break existing endpoints.

**Implementation:**
- SQLite with WAL mode for concurrent reads
- `db_adapter.py` already provides abstraction layer
- New tables use standard SQL compatible with both SQLite and PostgreSQL
- Supabase migration prepared but not activated

### 4. Supabase compatibility prepared

**Rationale:** Future migration to PostgreSQL/Supabase with pgvector is desirable for production scale.

**Implementation:**
- All new tables have PostgreSQL equivalent migrations
- UUID stable IDs where appropriate
- JSONB instead of TEXT for JSON fields (in PG version)
- pgvector for embeddings (in PG version)
- RLS policies documented
- No service-role key in frontend

### 5. Event map is deterministic and data-driven

**Rationale:** AI cannot invent cartography. Maps must be generated from verified geographic data with provenance.

**Implementation:**
- GeoJSON features from structured data (coordinates, phases, movements)
- AI extracts toponyms and proposes coordinates, but does not generate geometry
- Interactive Leaflet map (already implemented as `HistoricalMap.tsx`)
- SVG/PNG export deterministic
- Partial maps declared when data insufficient
- No invented arrows or interpolated fronts

### 6. Graph remains primary visualization for persons

**Rationale:** Persons have complex relational networks (sources, documents, events, other persons). Graph visualization reveals patterns that lists cannot.

**Implementation:**
- `ForceGraph.tsx` component (already exists, needs anti-collision fixes)
- Graph at end of person report
- Graph as secondary view in event dossier
- Canonical graph schema (`graph_nodes`, `graph_edges`) to be deployed
- Legacy `record_links` imported as candidates, not promoted

### 7. Uncertainty and divergences preserved

**Rationale:** Historical research requires preserving conflicting sources, not majority-voting them.

**Implementation:**
- Epistemic states: confirmed, probable, candidate, to_review, rejected, conflicting, unverifiable, broken
- `claims` + `claim_evidence` tables already exist
- Viewpoints service compares multiple AI providers
- Confidence is technical metric, not historical probability
- Single-source facts labeled "attestato da una sola fonte"
- Minority versions preserved

## Consequences

- **Positive:** Citations are verifiable, uncertainty is visible, data integrity preserved
- **Negative:** RAG requires good retrieval; if corpus is thin, outputs are sparse (honest)
- **Risk:** LM Studio CPU-only may be slow for large contexts; mitigate with chunking
- **Risk:** Graph schema deployment requires migration; mitigate with additive, reversible migration
