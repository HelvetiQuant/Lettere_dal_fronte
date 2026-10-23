# CHANGELOG — Provenance & Linking Refactor v2

**Branch**: `fix/provenance-linking-v2`  
**Data**: 2026-07-28  
**Commit base**: `56ac618`

---

## Summary

Refactoring completo del pipeline di linking per garantire verificabilità scientifica, immutabilità dei dati originali, idempotency, reversibilità, e measurability. Le relazioni deboli euristiche non sono più trattate come fatti storici.

---

## Modifiche

### 1. Audit e Stato Iniziale
- **`artifacts/state_before.json`** — Snapshot machine-readable del sistema: 75 tabelle, 4.1M righe, checksum SHA-256 di 3 DB, conteggi relazioni per tipo, stato sync Supabase, blockers
- **`docs/audit/REAL_STATE_BEFORE.md`** — Documento audit completo con diagnosi di 6 script legacy, discrepanze eventi (15 vs 49), collegamenti_backup (4.9M > 2.3M attivo)

### 2. Freeze Pipeline Legacy
- **`linking/kill_switch.py`** — Kill switch centralizzato con `LegacyJob` enum, `assert_frozen()`, env var override
- **`_gen_event_links.py`** — Aggiunto freeze + deprecation docstring (22 eventi hardcoded, mix WW1/WW2, substring match, no provenance)
- **`_gen_record_links.py`** — Aggiunto freeze + deprecation docstring (import-time execution, star topology, DELETE fonte_personale, LIMIT 50)
- **`_clean_bad_links.py`** — Aggiunto freeze + deprecation docstring (namespace confusion, destructive DELETE)
- **`_fix_gaiaschi_db.py`** — Aggiunto freeze + deprecation docstring (direct UPDATE, no claim model)
- Verificato: tutti gli script legacy ora raisono `RuntimeError` se eseguiti senza env var esplicita

### 3. Snapshot SQLite
- **`linking/snapshot.py`** — Utility snapshot con SQLite Backup API, integrity check, SHA-256, manifest JSON
- Snapshot creato: `snap_20260728T174952_f45e60ad` (1.87GB, 125 tabelle, quick_check=ok)

### 4. Nuovo Modello Dati v2 (16 tabelle)
- **`linking/schema_v2.py`** — Schema SQL completo per:
  - `resource_registry` — Registry tipizzato con UNIQUE(namespace, record_key)
  - `historical_events` — Eventi con conflict_code, parent_event_id, temporal_precision
  - `event_aliases_v2` — Alias con specificity, is_ambiguous, valid_place, valid_period
  - `source_artifacts` — Artefatti immutabili con content_sha256
  - `ocr_observations` — OCR append-only con supersedes_id
  - `claims_v2` — Claim con status (proposed/confirmed/rejected/superseded/disputed)
  - `evidence_fragments` — Frammenti con locator_uri, content_sha256
  - `claim_evidence_v2` — Claim ↔ Evidence con support_type
  - `review_decisions` — Decisioni append-only con previous_decision_id
  - `source_families` — Famiglie di fonti con derivation_notes
  - `source_family_members` — Membri con relation_to_root
  - `relations` — Relazioni candidate/confirmed con algorithm_name, algorithm_version, features, raw_score, confidence_calibrated, evidence_strength, conflict_flags, pipeline_run_id
  - `relation_evidence` — Relazione ↔ Evidence
  - `pipeline_runs` — Run con code_commit_sha, configuration_hash, checkpoint, metrics
  - `legacy_relation_quarantine` — Quarantena con legacy_payload_sha256, restored_at
  - `golden_dataset_labels` — Dataset etichettato con case_id, label, dataset_version

### 5. Nuovo Motore Linking v2
- **`linking/normalization.py`** — Normalizzatori versionati (name, date, place) con preservazione originale, date_overlap()
- **`linking/candidate_generation.py`** — Blocking indexes (phonetic prefix, year, place, matricola) → O(N+M) invece di O(N×M)
- **`linking/feature_extraction.py`** — Feature extraction con:
  - `extract_features_person_source()` — Nome, data, luogo, matricola, unità
  - `extract_features_person_event()` — Temporal overlap, geo, unit in theater, WW1/WW2 conflict
  - `extract_features_document_event()` — Word boundary match (non substring), keyword in title
  - `ConflictFlags` — Veto: ww1_ww2_mismatch, born_after_event, died_before_event, matricola_mismatch, omonimia_no_discriminator
  - `AMBIGUOUS_KEYWORDS` — campo, Russia, Africa, Nero, Corno, Lana, prigionia, etc.
- **`linking/scoring.py`** — Scoring con:
  - raw_score da features (mai presentato come probabilità)
  - evidence_strength: weak (0 discriminators), moderate (1), strong (2+)
  - confidence_calibrated sempre NULL (no calibration dataset yet)
  - Veto override: has_veto → evidence_strength=weak, can_be_confirmed=False
  - Cap 0.95 (incertezza sempre presente)
- **`linking/persistence.py`** — Persistenza idempotente con:
  - `register_resource()` — Idempotente via UNIQUE(namespace, key)
  - `upsert_relation()` — Idempotente via semantic unique index
  - `create_pipeline_run()` / `finish_pipeline_run()` — Con code_commit_sha, configuration_hash

### 6. CLI
- **`linking/cli.py`** — CLI completa:
  - `generate --dry-run` — Genera candidate (default: dry-run)
  - `generate --execute` — Esegue scrittura
  - `legacy-relations audit` — Audit relazioni legacy
  - `legacy-relations quarantine --dry-run/--execute` — Quarantena
  - `legacy-relations restore --run-id` — Restore
  - `legacy-relations list` — Lista quarantena
  - `kill-switch` — Stato kill switch

### 7. API v2
- **`linking_v2_api.py`** — Router FastAPI con 4 endpoint:
  - `GET /api/v2/status/manifest` — Stato reale del sistema (table counts, relations by status/strength, recent pipeline runs, kill switch)
  - `GET /api/v2/events` — Eventi con conflict_code filter
  - `GET /api/v2/relations` — Relazioni con full provenance metadata
  - `GET /api/v2/kill-switch` — Stato kill switch

### 8. Sicurezza
- **`linking/security.py`** — Utility sicurezza:
  - `redact_secrets()` — Pattern redaction per sb_secret_, sk-, JWT, postgres://
  - `check_env_not_tracked()` — Verifica .env non in git
  - `check_gitignore_has_env()` — Verifica .gitignore
  - `check_packaging_allowlist()` — Allowlist pacchetti
  - `security_audit()` — Audit completo

### 9. Golden Dataset
- **`linking/golden_dataset.py`** — 8 casi obbligatori:
  - GOLD-001: Same person, same matricola → positive
  - GOLD-002: WW1 soldier ↔ WW2 event → negative (veto)
  - GOLD-003: Born after event → negative (veto)
  - GOLD-004: Ambiguous keyword 'campo' only → negative
  - GOLD-005: Same cognome, different nome → uncertain
  - GOLD-006: Full match (name+date+place) → positive
  - GOLD-007: Document with event name in title → positive
  - GOLD-008: Search page URL as source → negative

### 10. Test
- **`test_linking_v2_master.py`** — 20 test:
  - Kill switch (frozen, env override)
  - Normalization (name, date, overlap)
  - Feature extraction (WW1/WW2, temporal, word boundary)
  - Scoring (weak/moderate/strong, veto, confidence_calibrated=NULL)
  - Schema (16 tabelle esistenti)
  - Security (redaction, .env not tracked)
  - Persistence (idempotent upsert)
  - Golden dataset (seed + verify labels)
  - Candidate generation (blocking produces pairs)
- **Risultato: 20/20 PASS**

---

## File creati/modificati

### Nuovi file
| File | Descrizione |
|------|-------------|
| `linking/__init__.py` | Package init |
| `linking/kill_switch.py` | Kill switch centralizzato |
| `linking/schema_v2.py` | Schema SQL 16 tabelle v2 |
| `linking/snapshot.py` | Snapshot SQLite con Backup API |
| `linking/normalization.py` | Normalizzatori versionati |
| `linking/candidate_generation.py` | Blocking indexes |
| `linking/feature_extraction.py` | Feature extraction + conflict detection |
| `linking/scoring.py` | Scoring + calibration |
| `linking/persistence.py` | Persistenza idempotente |
| `linking/cli.py` | CLI completa |
| `linking/security.py` | Security utilities |
| `linking/golden_dataset.py` | Golden dataset 8 casi |
| `linking_v2_api.py` | API v2 router |
| `test_linking_v2_master.py` | 20 test master |
| `artifacts/state_before.json` | Stato iniziale machine-readable |
| `docs/audit/REAL_STATE_BEFORE.md` | Audit documento |
| `_gen_state_before.py` | Script generazione state_before |

### File modificati
| File | Modifica |
|------|----------|
| `_gen_event_links.py` | Freeze + deprecation docstring |
| `_gen_record_links.py` | Freeze + deprecation docstring |
| `_clean_bad_links.py` | Freeze + deprecation docstring |
| `_fix_gaiaschi_db.py` | Freeze + deprecation docstring |
| `app.py` | Import + register linking_v2_router |

---

## Blockers rimanenti

1. **No staging Supabase** — solo produzione disponibile
2. **event_links sync in corso** — 1.5M righe legacy su produzione Supabase
3. **exec_sql RPC** — espone SQL arbitrario via PostgREST
4. **No Alembic** — migrazioni SQL manuali
5. **collegamenti_backup (4.9M)** — più grande della tabella attiva
6. **Calibration dataset** — golden dataset seeded ma non ancora usato per calibrazione

---

## Prossimi passi

1. Eseguire quarantena legacy (`python -m linking.cli legacy-relations quarantine --execute`)
2. Eseguire linking v2 su dataset completo (`python -m linking.cli generate --execute`)
3. Disabilitare `exec_sql` RPC su Supabase
4. Creare staging Supabase
5. Calibrare raw_score usando golden dataset
6. Implementare review workflow (confirm/reject via API)
7. Aggiornare frontend per usare API v2
