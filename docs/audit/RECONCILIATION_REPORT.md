# Reconciliation Report — Before/After

**Generated**: 2026-07-28  
**Branch**: `fix/provenance-linking-v2`

---

## Before (State at audit)

| Metric | Value |
|--------|-------|
| Legacy event_links | 1,539,685 (eventi_1gm.db) |
| Legacy record_links | 169,184 (imi_internati.db) |
| Legacy collegamenti | 2,349,417 (imi_internati.db) |
| Total legacy relations | **4,058,286** |
| Relations with provenance | 0 |
| Relations with algorithm version | 0 |
| Relations with evidence | 0 |
| Relations with conflict detection | 0 |
| Candidate vs confirmed distinction | None |
| Kill switch | None |
| Snapshot capability | None |
| Golden dataset | None |
| Test suite | None |
| Security redaction | None |

### Legacy relation quality
| Issue | Affected | Severity |
|-------|----------|----------|
| WW1/WW2 keyword mixing | All event_links with "campo", "Russia" | Critical |
| Substring matching (no word boundary) | All event_links | High |
| Star topology arbitrary hub | 142,594 record_links | High |
| No discriminators (cognome only) | 9,546 fonte_personale links | High |
| Search page URLs as sources | Unknown count | Medium |
| Born-after-event not checked | All person-event links | High |
| Confidence not calibrated | All 4M relations | Medium |

---

## After (State after refactor)

| Metric | Value |
|--------|-------|
| V2 schema tables | 16 |
| V2 relations (candidate) | 0 (dry-run only, not yet executed) |
| V2 relations (confirmed) | 0 |
| Legacy relations quarantined | 0 (dry-run verified, not yet executed) |
| Resource registry entries | 0 (ready for population) |
| Pipeline runs tracked | 0 (ready for execution) |
| Golden dataset cases | 8 seeded |
| Tests passing | 20/20 |
| Kill switch active | 6 jobs frozen |
| API v2 endpoints | 4 |
| Snapshot created | 1 (1.87GB, verified) |

### New capabilities
| Capability | Status |
|------------|--------|
| Provenance tracking (algorithm, version, features) | ✅ Implemented |
| Candidate/confirmed distinction | ✅ Implemented |
| Conflict detection (WW1/WW2, dates, matricola) | ✅ Implemented |
| Word boundary matching (no substring) | ✅ Implemented |
| Ambiguous keyword filtering | ✅ Implemented |
| Idempotent upsert | ✅ Implemented + tested |
| Kill switch for legacy jobs | ✅ Implemented + tested |
| SQLite snapshot with integrity check | ✅ Implemented + verified |
| Legacy relation quarantine | ✅ Implemented (dry-run verified) |
| Golden dataset with mandatory cases | ✅ Implemented + seeded |
| Security redaction | ✅ Implemented + tested |
| API v2 with provenance metadata | ✅ Implemented + tested |
| CLI with dry-run default | ✅ Implemented + tested |

---

## Delta Summary

| Area | Before | After |
|------|--------|-------|
| Data model | Flat tables, no provenance | 16 normalized tables with full provenance |
| Linking algorithm | Substring match, no calibration | Blocking + features + scoring + conflict detection |
| Safety | None (destructive, non-idempotent) | Kill switch, dry-run default, snapshot, quarantine |
| Testing | None | 20 tests, 100% pass |
| Security | None | Secret redaction, .env check, packaging allowlist |
| API | Legacy only | 4 new v2 endpoints with provenance |
| Documentation | None | ADR, CHANGELOG, audit report, reconciliation |

---

## Pending execution (requires explicit approval)

1. `python -m linking.cli legacy-relations quarantine --execute` — Quarantine 1.7M legacy relations
2. `python -m linking.cli generate --execute` — Generate v2 candidates on full dataset
3. Disable `exec_sql` RPC on Supabase
4. Create staging Supabase environment
5. Calibrate raw_score using golden dataset
6. Implement review workflow
7. Update frontend to consume API v2
