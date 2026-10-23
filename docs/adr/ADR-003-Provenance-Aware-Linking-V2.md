# ADR-003: Provenance-Aware Linking v2

**Status**: Accepted  
**Date**: 2026-07-28  
**Branch**: `fix/provenance-linking-v2`

## Context

The existing linking pipeline (`_gen_event_links.py`, `_gen_record_links.py`) produces 1.7M relations using uncalibrated substring matching, generic keywords, star topology hubs, and no provenance tracking. These relations are treated as historical facts in the UI despite having no evidence, no algorithm version, and no review process.

Key problems:
- **No provenance**: Relations have no algorithm name, version, features, or evidence
- **No candidate/confirmed distinction**: All links are immediately "facts"
- **WW1/WW2 mixing**: Generic keyword "campo" matches both WW1 prisoners and WW2 internees
- **Destructive operations**: `_gen_record_links.py` deletes fonte_personale on startup
- **No idempotency**: Scripts skip if any links exist, or create duplicates
- **No conflict detection**: Born-after-event and died-before-event not checked

## Decision

Implement a new **append-only, candidate-first, provenance-aware** linking system:

### Data Model
- **resource_registry**: Typed UUID registry eliminating namespace confusion
- **relations**: All relations start as `candidate`, never auto-promoted to `confirmed`
- **features**: JSON column stores extracted features for reproducibility
- **pipeline_runs**: Every run tracked with algorithm_version, code_commit_sha, configuration_hash
- **legacy_relation_quarantine**: Legacy relations preserved with SHA-256, not deleted

### Algorithm
1. **Normalization** (v2.0.0): Unicode NFKD, accent stripping, original preservation
2. **Blocking**: Phonetic prefix + year + place + matricola → O(N+M) not O(N×M)
3. **Feature extraction**: Name match, date compatibility, place match, matricola, unit, temporal overlap, document citation
4. **Conflict detection**: WW1/WW2 mismatch, born_after_event, died_before_event, matricola_mismatch, omonimia_no_discriminator
5. **Scoring**: raw_score from features, evidence_strength from discriminator count, confidence_calibrated=NULL until calibration dataset exists
6. **Persistence**: Idempotent upsert via semantic unique key (source+target+type+algorithm+version)

### Safety
- **Kill switch**: All legacy jobs frozen by default, env var override required
- **Dry-run default**: CLI defaults to `--dry-run`, `--execute` required for mutations
- **Snapshot**: SQLite Backup API snapshot before any migration
- **Quarantine**: Legacy relations preserved, not deleted

## Consequences

### Positive
- Weak heuristic links can no longer become asserted facts
- Every relation has full provenance (algorithm, version, features, run)
- Pipeline is idempotent, reversible, and measurable
- WW1/WW2 conflicts are detected and vetoed
- Golden dataset enables calibration and regression testing

### Negative
- 1.7M legacy relations need quarantine (1.5M event_links + 169K record_links)
- No auto-promotion means manual review required for confirmation
- Calibration not yet active (confidence_calibrated is NULL)
- Frontend needs updates to consume API v2 with provenance metadata

### Risks
- Legacy relations still exist in production tables (not yet quarantined)
- event_links sync to Supabase still running in background
- No staging Supabase environment for safe testing
