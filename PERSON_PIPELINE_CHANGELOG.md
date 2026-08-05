# PERSON Pipeline Refinement — Before/After Comparison & Changelog

## Date: 2026-08-05
## Branch: fix/provenance-linking-v2
## Resolver version: 1.0.0

---

## Executive Summary

The PERSON pipeline was refined to replace flawed surname-only matching with a deterministic, versioned `PersonIdentityResolver`. Local `internati` records are now properly extracted as narratable claims with provenance. API counts now use semantic counters instead of generic observation counts. Security improved by hiding API key prefixes.

---

## Root Causes Fixed

| # | Root Cause | Impact | Fix |
|---|-----------|--------|-----|
| 1 | `_query_local_db` used `LIKE '%cognome%'` prefix match | False positives, homonym contamination | Changed to exact `cognome=? AND nome=?` match |
| 2 | `LocalDbAdapter` observations included `raw_record` but `_query_local_db` helper did not | Local DB records never classified by `IdentityResolver` | Added `raw_record` to `provider_metadata` |
| 3 | `_stage_extract` PERSON only ran `classify_observation` but never extracted claims from local DB | "Nessun claim narrabile" for all PERSON cases | Added `_stage_extract_person_claims` method |
| 4 | No claims extracted from records with partial data (only `cognome`+`nome`) | ARMANNO Luigi A had 0 claims despite having a DB record | Added provenance claims (lettera, file_pdf, pagina) and raw_text/data_quality_note extraction |
| 5 | `_stage_fuse` overwrote `_person_claims` set by extraction | Local DB claims lost during fusion | Fusion now preserves existing person claims and merges with web-sourced claims |
| 6 | API output used `observation_count` (all web results) | Misleading "n_fonti" count included irrelevant web results | Added `semantic_counts` with `person_sources_confirmed`, `person_sources_probable`, etc. |
| 7 | `_check_keys.py` output format could expose key names alongside status | Minor security concern | Changed to `KEY_NAME: PRESENT/MISSING/INVALID` format, no value leakage |
| 8 | Narration selector missing predicates for new claim types | New claims (military_unit, birth_date, etc.) not scored | Added all new predicates to `PREDICATE_RELEVANCE_PERSON` and diversity categories |

---

## Before/After Comparison — 6 PERSON Cases

| Case | Before: Claims | After: Claims | Before: Status | After: Status | Before: Narration | After: Narration |
|------|---------------|---------------|----------------|---------------|-------------------|-------------------|
| ALTA Antonio | 0 | **49** | RESOLVED_IDENTITY | RESOLVED_IDENTITY | "Nessun claim narrabile" | AI narration with 49 claims |
| ARMANNO Luigi A | 0 | **5** | RESOLVED_IDENTITY | RESOLVED_IDENTITY | "Nessun claim narrabile" | AI narration with 5 claims (partial data) |
| AMAROTTI Enrico | 0 | **8** | RESOLVED_IDENTITY | RESOLVED_IDENTITY | "Nessun claim narrabile" | AI narration with 8 claims |
| ANFOSSO Carlo | 0 | **8** | RESOLVED_IDENTITY | RESOLVED_IDENTITY | "Nessun claim narrabile" | AI narration with 8 claims |
| ARTI Saverio | 0 | **43** | RESOLVED_IDENTITY | RESOLVED_IDENTITY | "Nessun claim narrabile" | AI narration with 43 claims |
| ANVISIO Remo | 0 | **9** | RESOLVED_IDENTITY | RESOLVED_IDENTITY | "Nessun claim narrabile" | AI narration with 9 claims |

### Semantic Counts (After)

| Case | web_candidates_seen | person_sources_confirmed | claims_accepted |
|------|---------------------|--------------------------|-----------------|
| ALTA Antonio | 90 | 21 | 49 |
| ARMANNO Luigi A | 67 | 1 | 5 |
| AMAROTTI Enrico | 66 | 1 | 8 |
| ANFOSSO Carlo | 82 | 1 | 8 |
| ARTI Saverio | 90 | 20 | 43 |
| ANVISIO Remo | 65 | 1 | 9 |

---

## Before/After Comparison — 3 EVENT Cases (Regression)

| Case | Before: Claims | After: Claims | Regression? |
|------|---------------|---------------|-------------|
| Battaglia del Monte Ortigara | 0 | 0 | ✅ No change |
| Battaglia di Vittorio Veneto | 4 | 4 | ✅ No change |
| Guerra bianca | 0 | 0 | ✅ No change |

---

## New Files

| File | Purpose |
|------|---------|
| `person_identity_resolver.py` | `PersonIdentityResolver` with normalization, identifiers, decision rules, query builder |
| `migrate_person_source_matches.py` | SQLite migration for `person_source_matches` table |
| `backfill_person_source_matches.py` | Idempotent backfill with dry-run support |
| `test_person_identity_resolver.py` | 27 unit tests for resolver |
| `test_person_pipeline_integration.py` | Integration test for 6 PERSON + 3 EVENT cases |

## Modified Files

| File | Changes |
|------|---------|
| `unified_orchestrator_v7.py` | `_query_local_db` exact match + raw_record; `_stage_extract_person_claims` new method; `_stage_fuse` preserves local claims; `_compute_semantic_counts` new method; `execute` returns `semantic_counts` |
| `narration_evidence_selector.py` | Added new predicates to relevance map and diversity categories |
| `_check_keys.py` | Output format changed to PRESENT/MISSING/INVALID |

---

## Database Changes

### New Table: `person_source_matches`

```sql
CREATE TABLE person_source_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_table TEXT NOT NULL DEFAULT 'internati',
    person_id INTEGER NOT NULL,
    source_table TEXT NOT NULL DEFAULT '',
    source_id INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('confirmed','probable','ambiguous','rejected')),
    source_kind TEXT NOT NULL DEFAULT 'web',
    normalized_name TEXT NOT NULL DEFAULT '',
    matched_features_json TEXT DEFAULT '[]',
    conflicting_features_json TEXT DEFAULT '[]',
    reason_codes_json TEXT DEFAULT '[]',
    resolver_version TEXT NOT NULL DEFAULT '1.0.0',
    manually_reviewed INTEGER NOT NULL DEFAULT 0,
    reviewed_by TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    url TEXT DEFAULT '',
    title TEXT DEFAULT '',
    query_used TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(person_table, person_id, source_table, source_id)
);
```

**Indexes**: `idx_psm_person`, `idx_psm_source`, `idx_psm_status`, `idx_psm_version`, `idx_psm_review`

**Migration is additive and idempotent.** No existing tables or columns are modified.

---

## Test Results

### Unit Tests: `test_person_identity_resolver.py`
- **27 tests, all PASS**
- Covers: normalization, name parsing, ALTA/ARTI common words, ARMANNO initial matching, OCR variants, homonym rejection, conflicting identifiers, query building, counts, version

### Integration Tests: `test_person_pipeline_integration.py`
- **9 cases (6 PERSON + 3 EVENT), all OK**
- All 6 PERSON cases produce claims from local DB
- All 3 EVENT cases unchanged (regression verified)
- No "Nessun claim narrabile" for any PERSON case
- Semantic counts correctly distinguish confirmed sources from web candidates

---

## Rollback Instructions

### 1. Revert code changes
```bash
git checkout HEAD~1 -- unified_orchestrator_v7.py narration_evidence_selector.py _check_keys.py
```

### 2. Remove person_source_matches table (optional)
```sql
DROP TABLE IF EXISTS person_source_matches;
```

### 3. Remove new files (optional)
```bash
rm person_identity_resolver.py
rm migrate_person_source_matches.py
rm backfill_person_source_matches.py
rm test_person_identity_resolver.py
rm test_person_pipeline_integration.py
```

**Note**: The migration is purely additive. No existing data is modified or deleted. Rollback is safe.

---

## Resolver Decision Rules

| Status | Rule | Confidence |
|--------|------|------------|
| `confirmed` | Full name exact + strong identifier (matricola) | 0.95 |
| `confirmed` | Full name exact + 2+ medium identifiers | 0.90 |
| `probable` | Full name exact + 1 medium identifier | 0.70 |
| `probable` | Initial match + 2+ medium identifiers | 0.65 |
| `probable` | Initial match + 1 medium identifier | 0.55 |
| `ambiguous` | Full name exact, no identifiers | 0.40 |
| `ambiguous` | Surname-only match with identifiers (max status) | 0.30 |
| `rejected` | No cognome match | 0.0 |
| `rejected` | Strong identifier conflict | 0.0 |
| `rejected` | Medium identifier conflict on critical fields | 0.0 |
| `rejected` | Surname-only, no identifiers | 0.0 |

---

## Claim Predicates Added

| DB Field | Predicate | Category |
|----------|-----------|----------|
| `sorte` | `fate` | fate |
| `luogo_internamento` | `internment_place` | location |
| `residenza` | `residence` | identity |
| `data` | `date_note` | chronology |
| `grado` | `rank` | military |
| `matricola` | `military_id` | military |
| `luogo_nascita` | `birth_place` | identity |
| `data_nascita` | `birth_date` | identity |
| `luogo_cattura` | `capture_place` | chronology |
| `data_cattura` | `capture_date` | chronology |
| `arbeitskommando` | `work_command` | location |
| `mansione` | `assignment` | assignment |
| `reparto` | `military_unit` | military |
| `lettera` | `archive_letter` | provenance |
| `file_pdf` | `source_document` | provenance |
| `pagina` | `source_page` | provenance |
| `raw_text` | `source_text` | provenance |
| `review_reason` | `data_quality_note` | provenance |
