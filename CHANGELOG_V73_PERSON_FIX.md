# CHANGELOG — V7.3-PERSON-FIX Session (2026-08-05)

## Contesto
Refactoring completo del pipeline V7 per correzione strutturale: retrieval multi-tabella, identity resolution cluster-based, narratore evidence-locked con hallucination detection, migrazioni DB additive, sicurezza script non-distruttiva, regression benchmark.

## Task completate (14/14)

### 1. Diagnosi call graph + baseline su 20 nomi
- Analisi call graph orchestrator → 5 tabelle PERSON non queryate
- Baseline: 20 nomi, osservazioni medie 12.3, identity resolution 30%

### 2. Modelli tipizzati
- `person_pipeline_models.py` — PersonCandidate, PersonFact, FactEvidence, SourceProvenance, ConflictSet, PersonRecord, PersonCluster

### 3. PERSON_SOURCE_SCHEMAS
- `person_source_schemas.py` — registro mapping per 5 tabelle (internati, caduti_ministero, caduti_cwgc, caduti_albooro, decorati_nastroazzurro) con validator/normalizer

### 4. Fix retrieval multi-tabella
- `unified_orchestrator_v7.py` — query su 5 tabelle, normalizzazione nominativo, word boundary matching
- `v7_identity_model.py` — cluster IDs war-period-aware, strong identifier conflict detection

### 5. Fix schema OpenAI + circuit breaker
- `narration_models.py` — schema fix per OpenAI structured output
- `ai_client.py` — parametro `skip_providers` in call_ai/call_ai_json
- `v7_narrator.py` — circuit breaker per provider AI falliti

### 6. Separazione fatti/evidenze/provenance
- Dedup per cluster+predicate+value, metriche distinte (accepted/conflicting/asserted)

### 7. Identity resolver cluster-based
- `v7_identity_model.py` — identificatori forti (matricola, data_nascita, luogo+paternità), no fusione omonimi, war-period-aware

### 8. Unit test mapping (43/43 PASS)
- `test_person_v73_fix.py` — 43 test: mapping 5 tabelle, identity/conflict, link scope

### 9. _gen_record_links.py refactor
- Rimozione DELETE, CLI esplicita (--dry-run/--execute), quarantena archi legacy, pairwise linking, exact matching

### 10. _gen_event_links.py refactor
- Word boundary matching, barriere temporali (WWI/WWII veto), incremental linking (no skip totale), CLI

### 11. Narratore evidence-locked
- `v7_narrator.py`:
  - `_validate_payload()` — validazione claims prima di chiamare AI
  - `_compute_evidence_hash()` — SHA-256 hash claim IDs per integrità payload
  - `_post_gen_hallucination_check()` — detection post-generazione di date/luoghi/nomi non supportati da evidence
  - Integrazione in `narrate()`: >5 warning → fallback deterministico
  - `_build_result()` — `extra_flags` per hallucination warnings

### 12. Migrazioni DB
- `migrate_v73_data_corrections.py`:
  - `data_corrections` table + 3 indici (persistent CorrectionLedger overlay)
  - `sync_parity_audit` table (SQLite vs Supabase row counts)
  - Supabase parity check via REST API
  - Risultati: 6/8 tabelle allineate (eventi_1gm mismatch per DB separato)

### 13. Sicurezza script
- `_clean_bad_links.py` — DELETE sostituito con quarantena (UPDATE confidence=0.0, fetch_status='quarantined')
- `_fix_gaiaschi_db.py` — direct UPDATE sostituito con `data_corrections` overlay (raw data immutabile)
- `_check_keys.py` — verificato sicuro (no print valori sensibili)
- `_find_best_candidates.py` — verificato read-only

### 14. Regression benchmark
- `run_regression_v73.py` — 20 PERSON + 3 EVENT, 8 check per target
- Quick run: 5/5 PASS (100%), 450 observations, 0 errors, avg 23.2s
- Backend test 6 nomi: 6/6 PASS, 611 observations, report discorsivi generati

## File nuovi (5)
- `person_source_schemas.py` — Schema registry 5 tabelle PERSON
- `person_pipeline_models.py` — Typed data contracts
- `test_person_v73_fix.py` — 43 unit test
- `migrate_v73_data_corrections.py` — Migration + Supabase parity
- `run_regression_v73.py` — Regression benchmark runner

## File modificati (10)
- `unified_orchestrator_v7.py` — Schema-driven extraction, 5-table query, semantic counts
- `v7_narrator.py` — Circuit breaker, evidence-locked payload, hallucination check
- `ai_client.py` — skip_providers parameter
- `narration_models.py` — OpenAI schema fix
- `v7_identity_model.py` — War-period-aware cluster IDs, strong identifier conflicts
- `_gen_record_links.py` — Quarantine instead of DELETE, CLI, pairwise linking
- `_gen_event_links.py` — Word boundary, temporal barriers, incremental linking
- `_clean_bad_links.py` — DELETE → quarantine
- `_fix_gaiaschi_db.py` — Direct UPDATE → data_corrections overlay

## Metriche
| Metrica | Valore |
|---------|--------|
| Unit test | 43/43 PASS |
| Regression benchmark | 5/5 PASS (100%) |
| Backend test 6 nomi | 6/6 PASS (100%) |
| Supabase parity | 6/8 OK |
| Osservazioni totali (6 nomi) | 611 |
| Errori totali | 0 |
| Avg elapsed per target | 18-23s |
