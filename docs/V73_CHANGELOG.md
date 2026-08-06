# V7.3 Changelog — Semantic Pipeline Implementation

## Overview

Implementation of 18 phases (Fase 1-18) for the V7.3 semantic pipeline,
covering: source quality assessment, semantic field modeling, identity
resolution, military ontology, linking, temporal filtering, geo-context,
source hierarchy, semantic validation, claim lifecycle, response structure,
API integration, legacy migration, regression tests, and benchmarks.

## Phases Completed

### Fase 1: Audit + Baseline
- Complete codebase audit
- `BEFORE_IMPLEMENTATION_AUDIT.md` with baseline metrics

### Fase 2: Legacy Linking Fixes
- Fixed `_gen_event_links`, `_gen_record_links`, `_clean_bad_links`, `_fix_gaiaschi_db`

### Fase 3: PERSON_EVIDENCE vs CONTEXT_EVIDENCE
- Inviolable separation between person-level and context-level evidence
- `evidence_scope` field on `ClaimV7` (`PERSON_EVIDENCE` / `CONTEXT_EVIDENCE`)

### Fase 4: Semantic Field Model
- Typed places (`geo_context.py`), dates with precision, family relations
- `military_ontology.py` for rank/unit/duty modeling

### Fase 5: Identity Resolution
- 6 identity states: `ANCHORED_RECORD`, `RESOLVED_IDENTITY`, `CONFLICTED_IDENTITY`, `AMBIGUOUS_IDENTITY`, `PARTIAL_IDENTITY`, `UNRESOLVED_IDENTITY`
- No destructive merges

### Fase 6: Military Ontology
- `rank_fact` vs `rank_context` vs `personal_duty` separation
- Grade/reparto ontology in `military_ontology.py`

### Fase 7: Person-Unit-Event Linking
- Versioned candidates with probatory hierarchy
- Linking pipeline with provenance metadata

### Fase 8: Adaptive Temporal Window
- Temporal filter for WWI/WWII contamination prevention
- `linking/temporal_filter.py`

### Fase 9: Historical-Geographic Context
- Place types, historical borders, geo-context resolution
- `geo_context.py`

### Fase 10: Source Hierarchy and Quality
- Multi-dimensional quality assessment (authority, freshness, coverage, etc.)
- `source_quality.py` with `assess_source_quality()` and `combine_evidence_quality()`

### Fase 11: Semantic Validator
- Claim-by-claim entailment checking
- Scope violation detection, contradiction detection, provenance chain validation
- `semantic_validator.py` with `SemanticValidator` class

### Fase 12: Claim States + Publishability
- 4 states: `PUBLISHED`, `PUBLISHED_WITH_CAVEAT`, `REVIEW_PENDING`, `SUPPRESSED`
- State transitions are append-only (audit trail)
- `claim_lifecycle.py` with `determine_claim_state()`, `filter_publishable_claims()`, `build_caveat_summary()`

### Fase 13: Final Response Structure (11 Sections)
- Canonical sections: sintesi, identita, dati_anagrafici, percorso_militare, luoghi, eventi_collegati, fonti_evidence, conflitti, caveat, validazione, meta
- `response_structure.py` with `ResponseBuilder` class
- Markdown rendering support

### Fase 14: API + Frontend Integration
- 5 new V7.3 API endpoints in `v7_api.py`:
  - `GET /api/v7/source-quality/{source_key}`
  - `POST /api/v7/validate-snapshot`
  - `POST /api/v7/claim-states`
  - `POST /api/v7/build-response`
  - `GET /api/v7/response-schema`
- Frontend client methods in `frontend/src/api/client.ts`:
  - `v73SourceQuality()`, `v73ValidateSnapshot()`, `v73ClaimStates()`, `v73BuildResponse()`, `v73ResponseSchema()`

### Fase 15: Legacy Link Migration
- Idempotent, reversible migration script: `migrate_v73_links.py`
- Adds V7.3 columns: `v73_quality_level`, `v73_quality_score`, `v73_claim_state`, `v73_caveat`, `v73_rule_version`
- Backup table `link_migration_backup` for rollback
- Supports `--dry-run`, `--execute`, `--rollback`
- Dry-run verified: 169K record_links + 1.5M event_links processed

### Fase 16: Regression Tests (10 Cases A-J)
- `test_v73_regression.py` with 10 automated test cases:
  - A: Source quality assessment
  - B: Evidence quality combination
  - C: Semantic validator (valid claims)
  - D: Semantic validator (scope violations)
  - E: Claim lifecycle PUBLISHED
  - F: Claim lifecycle SUPPRESSED
  - G: Claim lifecycle REVIEW_PENDING
  - H: Claim lifecycle PUBLISHED_WITH_CAVEAT
  - I: Response structure with claims
  - J: Response structure empty query
- **Result: 10/10 PASS (100%)**

### Fase 17: Acceptance Metrics + Benchmark
- `run_v73_benchmark.py` with 6 measurement dimensions
- Report saved to `docs/v73_benchmark.json`
- Results:
  - Source quality: 6 high, 4 medium, 2 very_low
  - Regression: 10/10 (100%)
  - API routes: 10 total (5 new V7.3)
  - Modules: 7/7 importable
  - Response sections: 11/11

### Fase 18: Final Deliverables
- This changelog
- Command reference (below)

## New Files

| File | Description |
|------|-------------|
| `source_quality.py` | Multi-dimensional source quality assessment |
| `semantic_validator.py` | Claim-by-claim entailment and scope validation |
| `claim_lifecycle.py` | 4-state publishability with append-only transitions |
| `response_structure.py` | 11-section canonical response builder |
| `military_ontology.py` | Rank/unit/duty ontology |
| `geo_context.py` | Historical-geographic place context |
| `migrate_v73_links.py` | Idempotent, reversible link migration |
| `test_v73_regression.py` | 10-case regression test suite |
| `run_v73_benchmark.py` | Acceptance metrics benchmark |
| `docs/v73_benchmark.json` | Benchmark report output |

## Modified Files

| File | Changes |
|------|---------|
| `v7_api.py` | 5 new V7.3 API endpoints + imports |
| `frontend/src/api/client.ts` | 5 new V7.3 client methods |

## Command Reference

```bash
# Run regression tests (10 cases A-J)
python test_v73_regression.py

# Run acceptance benchmark
python run_v73_benchmark.py

# Link migration (dry-run audit)
python migrate_v73_links.py --dry-run

# Link migration (execute)
python migrate_v73_links.py --execute

# Link migration (rollback)
python migrate_v73_links.py --rollback

# Existing V3 link migration
python migrate_links_v3.py --dry-run
python migrate_links_v3.py --execute

# Existing regression (20 persons + 3 events)
python run_regression_v73.py
python run_regression_v73.py --quick
```

## Key Invariants Enforced

1. **PERSON_EVIDENCE cannot be asserted by CONTEXT_EVIDENCE** (scope violation → SUPPRESSED)
2. **Claim without evidence → REJECTED** (no orphan claims)
3. **UNRESOLVED_IDENTITY → REVIEW_PENDING** (cannot publish)
4. **Validation REJECTED → SUPPRESSED** (absolute)
5. **Single source → PUBLISHED_WITH_CAVEAT** (corroboration needed)
6. **State transitions are append-only** (audit trail preserved)
7. **Migration is non-destructive** (original data backed up, rollback available)
