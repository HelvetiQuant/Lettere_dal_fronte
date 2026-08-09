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

---

## Fase 19 — Report Discorsivi V7.3 con Military Ontology e Contesto Storico

**Data**: 2026-08-06
**Branch**: fix/provenance-linking-v2

### Modifiche

- **`run_5_random_narrative.py`**: Script semplificato per estrarre 5 nomi casuali dai DB (internati, caduti_albooro, decorati_nastroazzurro, caduti_cwgc) e mostrare le risposte discorsive generate dal AI del backend (GPT-4o via NarratorV7_v2). Rimossa la sovrastruttura ResponseBuilder che sostituiva il report AI con elenchi strutturati. Ora il report AI discorsivo è il contenuto principale.

### Output verificati

5 risposte discorsive generate con successo:
1. **PIETRO DELLA GIOVANNA** (caduti_albooro) — soldato 13° Reggimento Bersaglieri, morto 1918 sul Piave
2. **MARIANO ZOLLOSCHI** (internati) — deceduto 23 marzo 1944, residente Ascoli Piceno
3. **MICHELE SANTORO** (caduti_albooro) — soldato 93° Reggimento Fanteria, morto 1917, identity AMBIGUOUS
4. **TULLIO ZANETTI** (decorati_nastroazzurro) — soldato Reparto Mitraglieri Fiat Brescia, morto 1919, identity CONFLICTED
5. **FRITZ ZAHN** (caduti_cwgc) — deceduto 9 maggio 1947, sepolto Fayid War Cemetery (Egitto)

### TODO

- ~~Ampliare i report AI con informazioni contestuali sul ruolo del reparto (se presente nei claim)~~ — **FATTO (Fase 20-22)**
- Aggiungere contesto geografico (luogo di nascita, residenza, luogo di decesso, sepoltura)
- Integrare military_ontology (parse_rank/parse_unit) nel prompt del narrator per arricchire il contesto
- Ampliare lista internati IMI (DB attuale: 20.465 record da ASBZ, ~3% dei ~600K IMI totali)

---

## Fase 20 — Military Context Enrichment nel Narrator AI

**Data**: 2026-08-09
**Branch**: fix/provenance-linking-v2

### Modifiche

- **`military_ontology.py`**: Aggiunta `UNIT_BRANCH_DESCRIPTIONS` (16 descrizioni per fanteria, artiglieria, bersaglieri, alpini, granatieri, cavalleria, genio, trasmissioni, sanita, intendenza, carabinieri, aviazione, marina, fucilieri, mitraglieri, paracadutisti) e `UNIT_TYPE_DESCRIPTIONS` (15 descrizioni per tipi di unita). Aggiunta funzione `build_military_context()` che estrae grado e reparto dai claim e genera contesto narrativo. Nuove keyword: `reparto`/`unita` come `unit_generic`, `mitraglieri` come branch.
- **`v7_narrator.py`**: `_build_ai_input` ora inietta `military_context` nel payload AI (campo separato con rank, unit, summary).
- **`v7_narrator_prompt_v2.py`**: Prompt aggiornato con sezione "CONTESTO MILITARE" che istruisce l'AI a usare `military_context` per arricchire i blocchi `context` con descrizioni del ruolo del reparto, senza attribuire fatti non supportati dai claim.

### Output verificato

Test su **ZANETTI TULLIO** (decorati_nastroazzurro, CONFLICTED_IDENTITY):
- AI: GPT-4o, 5 blocchi, validated_ai
- Prima: "Il Reparto Mitraglieri Fiat Brescia era parte dell'Esercito italiano" (generico)
- Dopo: "un'unita specializzata nell'uso delle mitragliatrici, armi fondamentali per la difesa di trincea e il fuoco di soppressione. Queste unita erano organizzate in reparti autonomi o aggregati a reggimenti di fanteria" (contesto arricchito da military_ontology)

---

## Fase 21 — Rank Role Descriptions nel Narrator AI

**Data**: 2026-08-09
**Branch**: fix/provenance-linking-v2

### Modifiche

- **`military_ontology.py`**: Aggiunta `RANK_ROLE_DESCRIPTIONS` (27 voci: soldato, fante, caporale, caporale maggiore, bersagliere, alpino, artigliere, granatiere, fuciliere, marinaio, aviere, sergente, sergente maggiore, sergente capo, maresciallo, maresciallo maggiore, sottotenente, tenente, primo tenente, capitano, maggiore, tenente colonnello, colonnello, generale di brigata/divisione/corpo d'armata). Aggiunta `RANK_CATEGORY_DESCRIPTIONS` (6 fallback per categoria). `build_military_context` ora include `rank.role_description` nel payload.
- **`v7_narrator_prompt_v2.py`**: Prompt aggiornato — l'AI deve usare `rank.role_description` per spiegare le funzioni del grado nel reparto (es. "comandava un plotone di 30-40 uomini"), non solo il nome del grado.

### Output verificato

- Sergente + Granatieri → "comandava un plotone di 30-40 uomini... guidava personalmente il plotone negli assalti"
- Tenente + Fanteria → "comandava un plotone o... vice-comandante di compagnia... in combattimento era al fronte con i suoi uomini"
- Caporale + Bersaglieri → "comandava una squadra di 8-12 uomini... guidava la squadra in combattimento"

---

## Fase 22 — Web Context Tavily con Validazione Storica

**Data**: 2026-08-09
**Branch**: fix/provenance-linking-v2

### Modifiche

- **`military_ontology.py`**: Nuove funzioni:
  - `_infer_war_period(claims)`: inferisce WWI/WWII dai claim (date 1915-1918, keyword "Isonzo/Piave/Caporetto" = WWI; 1940-1945, "Stalag/IMI/Arbeitskommando" = WWII)
  - `_validate_unit_snippet(snippet, title, unit_info, war_period)`: valida che lo snippet Tavily si riferisca allo stesso reparto (match numero reggimento) e stesso periodo bellico. Restituisce `match_confidence`: `high` (numero + branch + periodo confermati), `medium` (parziale), `low` (numero non trovato), `rejected` (periodo bellico diverso)
  - `_search_unit_history(unit_info, war_period)`: ricerca Tavily scoped al periodo bellico, filtra snippet con `_validate_unit_snippet`, ordina per confidence, restituisce top-3
  - `build_military_context` ora inferisce il war period e passa snippet validati come `unit.web_context`
- **`v7_narrator_prompt_v2.py`**: Prompt aggiornato — l'AI usa snippet `high`/`medium` come fatto storico, snippet `low` solo con marcatori di incertezza ("potrebbe aver partecipato")

### Output verificato

Test su **ZANETTI TULLIO** (WWI, GPT-4o, 6 blocchi, validated_ai):
- 64° Fanteria WWI → 3/3 snippet `high` (Brigata Cagliari, Isonzo 1915)
- Mitraglieri Fiat Brescia WWI → 3/3 snippet `high` (scuola 1916, WW1)
- Snippet WWII contro unita WWI → `rejected` (scartato)
- L'AI ha parafrasato: "La scuola dei mitraglieri Fiat fu inaugurata a Brescia nel 1916"
