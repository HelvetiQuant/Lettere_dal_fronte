# CHANGELOG — V7.3 Structural Correction

## [7.3.0] — 2026-08-03

### Structural Correction V7.3: Logic, Architecture, and Probatory Pipeline

Correzione strutturale del sistema di linking e narrazione: quarantena legacy,
modello canonico, matching con word boundary, barriere temporali/geografiche,
selezione claim, narrazione conversazionale, adapter con feature flag.

---

### Phase A — Diagnosi e baseline

- Ispezione di 141 tabelle SQLite, 284 indici, 1.7M legacy links
- Identificata contaminazione WWI/WWII: 12,759 cross-war event_links
- Identificati 10,270 match generici "Campo" senza word boundary
- Identificati 7 path hardcoded `C:\Users\eryma\Desktop`
- Documentati 9 problemi sistemici in `docs/V73_PHASE_A_DIAGNOSIS.md`
- Creati backup verificati: `imi_internati_backup_v73_phase_a.db`, `eventi_1gm_backup_v73_phase_a.db`

### Phase B — Quarantena e migrazioni

- `migrate_v73_quarantine.py`: colonne additive su `event_links` + `record_links`
  - `origin`, `usable_as_evidence`, `war_period`, `semantic_role`, `quarantined_at`, `quarantine_reason`
- Tutti i 1,708,869 legacy links marcati `CANDIDATE` con `usable_as_evidence=0`
- 12 tabelle canonical domain model create:
  - `canonical_source_artifacts`, `canonical_source_families`, `canonical_observations`
  - `canonical_entities`, `canonical_identity_candidates`, `canonical_evidence`
  - `canonical_claims`, `canonical_relations`, `canonical_review_decisions`
  - `canonical_research_snapshots`, `canonical_sync_outbox`, `canonical_event_registry`
- 26 indici su tabelle canoniche
- `legacy_link_quarantine_audit` popolato con audit trail completo
- Migrazione idempotente, additiva, non distruttiva, con dry-run/rollback

### Phase C — Matching, identità, eventi

- `migrate_v73_event_registry.py`: 49 eventi popolati con correzioni
  - Battaglie dell'Isonzo: `data_fine` corretta da 1917-09-12 a 1917-11-12
  - Caporetto: direzione offensiva marcata come Austro-Ungarico/Tedesco
  - Classificazione war: 42 WWI, 7 WWII
  - Provenienza registrata per ogni evento
- `domain_model_v73.py`: entità tipizzate con identity resolution
  - IdentifierStrength: STRONG (data nascita, matricola), MEDIUM (luogo), WEAK (nome)
  - IdentityStatus: CANDIDATE, RESOLVED, UNRESOLVED, NEEDS_REVIEW, REJECTED_HOMONYM, CONFLICTING
  - Claim lifecycle: CANDIDATE -> VERIFIED/PROBABLE/CONFLICTING/REJECTED
  - `can_combine_claims`: non combina mai claim da candidati diversi
- `text_matching_v73.py`: matching con word boundary
  - "Lana" != "Castellana", "Roma" != "Romania", "Nero" != "nerofumo"
  - Classificazione specificità: specific (Caporetto), generic (Campo), very_generic (guerra)
  - OCR variants, alias matching, name parsing con patronimico
- `barriers_v73.py`: barriere temporali e geografiche
  - WWI/WWII hard veto (cross-war links bloccati)
  - Date roles: PUBLICATION_DATE non prova partecipazione
  - Geographic semantic roles: BURIAL_PLACE != EVENT_PLACE, DEATH_PLACE != CAPTURE_PLACE
  - `evaluate_match`: combinazione text + temporal + geographic -> CONFIRMED/CANDIDATE/NEEDS_REVIEW/REJECTED

### Phase D — Selezione e narrazione

- `narration_planner_v73.py`:
  - `ClaimSelector`: seleziona claim per identità (non mescola candidati), priorità per evidence strength, exclude quarantined
  - `CoveragePlanner`: PERSON (16 campi biografici), EVENT (10 dimensioni stratificate con critical/important/minor)
  - `NarrationPlanner`: blocchi cronologici per PERSON, stratificati per EVENT, certainty aggregation
  - `SemanticValidator`: contraddizioni, homonym leakage, temporal consistency, geographic compatibility, legacy leakage
  - `GlobalValidator`: evidence coverage, certainty consistency, hallucination detection, identity warnings

### Phase E — Integrazione

- `adapters_v73.py`: adapter legacy con feature flag
  - `V73_CANONICAL_DOSSIER`, `V73_CANONICAL_GRAPH`, `V73_CANONICAL_MAP`, `V73_CANONICAL_SEARCH`, `V73_CANONICAL_LINKS`
  - Tutti default OFF (backward compatible)
  - Quarantine filtering: usable vs quarantined links separati
  - `get_dossier/graph/map/search` route through canonical o legacy

### Phase F — Test con dati reali

- 9 nuovi casi test (6 PERSON + 3 EVENT) diversi dai 9 baseline:
  - PERSON: ALTA Antonio, ARMANNO Luigi A, AMAROTTI Enrico, ANFOSSO Carlo, ARTI Saverio, ANVISIO Remo
  - EVENT: Battaglia del Monte Ortigara, Battaglia di Vittorio Veneto, Guerra bianca
- Pipeline completa: text matching -> barriers -> identity -> claims -> coverage -> narration -> validation
- `conversational_renderer_v73.py`: renderer conversazionale deterministico in italiano
  - Blocchi cronologici per PERSON, stratificati per EVENT
  - Certainty phrasing: CONFIRMED -> "documentato", PROBABLE -> "probabilmente"
  - Identity status chiaramente dichiarato in apertura
  - Coverage gaps con severity
  - Provenienza da canonical_event_registry
- Risultati: 9/9 execution_success, 9/9 no_legacy_leakage, 9/9 no_homonym_leakage, 9/9 no_validation_errors, 3/3 cross_war_veto
- 160 test totali: 79 (Phase B/C) + 35 (Phase D) + 37 (Phase E) + 9 (Phase F) — tutti PASS

### File creati

| File | Descrizione |
|------|-------------|
| `docs/V73_PHASE_A_DIAGNOSIS.md` | Report diagnosi Phase A |
| `migrate_v73_quarantine.py` | Migrazione quarantena (additiva, idempotente, rollback) |
| `migrate_v73_event_registry.py` | Popolamento registro eventi con correzioni |
| `domain_model_v73.py` | Modello canonico (SourceArtifact, Entity, Claim, Evidence, etc.) |
| `text_matching_v73.py` | Matching con word boundary, specificità, OCR variants |
| `barriers_v73.py` | Barriere temporali e geografiche |
| `narration_planner_v73.py` | Claim selection, coverage, narration planning, validation |
| `adapters_v73.py` | Adapter legacy con feature flag |
| `conversational_renderer_v73.py` | Renderer conversazionale deterministico |
| `run_v73_conversational.py` | Script esecuzione 9 casi conversazionali |
| `test_v73_phase_bc.py` | 79 test Phase B/C |
| `test_v73_phase_d.py` | 35 test Phase D |
| `test_v73_phase_e.py` | 37 test Phase E |
| `test_v73_phase_f_real.py` | 9 test end-to-end Phase F |
| `V73_PHASE_F_RESULTS.json` | Risultati Phase F |
| `V73_CONVERSATIONAL_RESPONSES.json` | Risposte conversazionali |

### Regole enforce

1. Tutti i legacy links quarantenati (`usable_as_evidence=0`, `status=CANDIDATE`)
2. Barriera temporale WWI/WWII: cross-war links hard vetoed
3. Ruoli geografici semantici: burial != event, death != capture, detention != event
4. Word-boundary matching: "Lana" != "Castellana", "Roma" != "Romania"
5. Keyword generiche da sole insufficienti (Campo, Piave, Isonzo richiedono match specifico)
6. Identity resolution: solo nome -> NEEDS_REVIEW, conflitto forte -> REJECTED_HOMONYM
7. Claim da candidati diversi mai combinati
8. Claim lifecycle: CANDIDATE -> VERIFIED/PROBABLE/CONFLICTING/REJECTED
9. Event registry versionato con provenance e correzioni
10. Zero legacy leakage nella pipeline canonica

### Git

- Branch: `fix/provenance-linking-v2`
- Commits: 6b24fab (B/C), 9fca1b2 (D), fcb58ed (E/F), 7c3a52f (conversational)
