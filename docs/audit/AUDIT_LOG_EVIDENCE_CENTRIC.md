# Audit Log — Evidence-Centric Architecture Migration

**Sessione**: 2026-08-17  
**Branch**: `fix/provenance-linking-v2`  
**Scope**: Fasi 2-7 (Evidence Contract → Event Ontology)

---

## Riepilogo Esecutivo

6 fasi completate in sequenza, 6 moduli nuovi, 1 modulo modificato, 6 documenti di architettura, 54 test totali (tutti PASS).

---

## Fase 2: Evidence Contract

**Modulo**: `evidence_contract.py` (533 righe)  
**Test**: — (fase fondazionale, test integrati nelle fasi successive)  
**Doc**: `docs/architecture/EVIDENCE_CONTRACT.md`

### Cosa è stato fatto
- Definito il contratto centrale: SOURCE → OBSERVATION → EVIDENCE → CLAIM → RELATION → ANSWER
- 10 invarianti architetturali codificate
- `ClaimStatus` con 8 livelli di verifica
- Dataclass: `SourceRef`, `ObservationRef`, `EvidenceRef`, `ClaimRef`, `RelationRef`, `AnswerEvidenceBundle`
- `EvidenceContract` con `build_answer_bundle()` e `to_prompt_context()`
- Gate policies: authority/relevance e independence

### Errori risolti
- Nessuno (fase greenfield)

---

## Fase 3: Source Lineage

**Modulo**: `source_lineage_service.py` (470 righe)  
**Test**: 10/10 PASS  
**Doc**: `docs/architecture/SOURCE_LINEAGE.md`

### Cosa è stato fatto
- `LineageRegistry`: CRUD per `source_lineages` / `source_lineage_members`
- `LineageBootstrap`: 12 lineages da `source_authority_registry`
- `LineageAwareAssessor`: DB-backed independence scoring
- `LineageSync`: sincronizza `SourceFamilyGraph` → DB

### Errori risolti
- **Bug**: `get_independence_score` restituiva score alto per risorse nella stessa lineage
- **Fix**: Risorse nella stessa lineage NON sono indipendenti (score 0.05-0.2 basato su `origin_type`)

---

## Fase 4: Legacy Quarantine

**Modulo**: `legacy_relation_adapter.py` (608 righe)  
**Test**: 9/9 PASS  
**Doc**: `docs/architecture/LEGACY_QUARANTINE.md`

### Cosa è stato fatto
- `LegacyRelationAdapter`: scan, import, revalidation, quarantine report
- 3 tabelle legacy: `record_links`, `collegamenti`, `event_links`
- Gate di revalidazione: confidence + temporal + identity
- Safety checks: `is_safe_for_verified()`, `is_safe_for_ai_context()`

### Errori risolti
- **Bug 1**: `AssertionError` — `import_stats.imported == 0` con `skipped_duplicate == 2` su tabella vuota
  - **Root cause**: `IntegrityError` da CHECK constraint, non da UNIQUE
  - **Fix**: Distinguere `IntegrityError` causes (UNIQUE vs CHECK vs FK)
- **Bug 2**: `CHECK constraint failed: identity_gate IN (...)` — 'unknown' non nei valori ammessi
  - **Fix**: Aggiunto `'unknown'` al CHECK constraint di `identity_gate` e `temporal_gate`
- **Bug 3**: `_safe_alter()` saltava statement con commenti multi-linea
  - **Fix**: Strip comment lines prima di verificare se lo statement è vuoto

---

## Fase 5: AnswerEvidenceBundle

**Modulo**: `answer_evidence_gate.py` (290 righe)  
**Test**: 10/10 PASS  
**Doc**: `docs/architecture/ANSWER_EVIDENCE_BUNDLE.md`

### Cosa è stato fatto
- `AnswerEvidenceGate`: converte `EvidenceSnapshotV7` → `AnswerEvidenceBundle`
- Mapping status ClaimV7 → EvidenceContract (10 mapping)
- Pre-generation gate: `validate_bundle()`
- Post-generation gate: `verify_answer()`
- AI prompt generation con `context_hash` + `answer_hash`
- Authority tier inference da provider name

### Errori risolti
- Nessuno (fase greenfield)

---

## Fase 6: EvidenceSnapshot Persistente

**Modulo**: `evidence_snapshot_service.py` (230 righe)  
**Test**: 10/10 PASS  
**Doc**: `docs/architecture/EVIDENCE_SNAPSHOT_PERSISTENT.md`

### Cosa è stato fatto
- `EvidenceSnapshotService`: save/load/list/link/verify/delete
- `context_hash` (SHA-256 del snapshot JSON) per integrità input
- `answer_hash` (SHA-256 di context_hash + answer_text) per integrità output
- Idempotente: stesso contenuto → stesso hash → no duplicati
- `link_relations()`: collega relazioni via `snapshot_id` FK

### Errori risolti
- Nessuno (fase greenfield)

---

## Fase 7: Event Ontology Gerarchica

**Modulo**: `event_ontology_service.py` (310 righe)  
**Test**: 15/15 PASS  
**Doc**: `docs/architecture/EVENT_ONTOLOGY.md`

### Cosa è stato fatto
- `EventOntologyService`: gerarchia eventi con `parent_event_id` persistente
- Query: `get_children()`, `get_descendants()`, `get_ancestors()`, `get_siblings()`, `get_full_tree()`
- Management: `set_parent()`, `remove_parent()` con validazione
- Alias management: `add_alias()`, `get_aliases()`, `remove_alias()`
- Validazioni: ciclo detection, contenimento temporale, tipo gerarchia
- `bootstrap_from_resolver()`: popola da `event_resolver.py` HIERARCHY dict

### Errori risolti
- **Bug test**: Tolmino (1915-06-23) come figlio di Caporetto (1917-10-24) → violazione temporale
  - **Fix**: Tolmino è figlio di Isonzo (non Caporetto), poi riposizionato sotto Caporetto dopo adjust date

---

## Fix Schema (`linking/schema_v2.py`)

| Fix | Descrizione |
|-----|-------------|
| `_safe_alter()` | Strip comment lines multi-linea prima di verificare se statement è vuoto |
| `temporal_gate` CHECK | Aggiunto `'unknown'` ai valori ammessi |
| `identity_gate` CHECK | Aggiunto `'unknown'` ai valori ammessi, default cambiato a `'unverified'` |

---

## Inventario File

### File nuovi (7)
| File | Righe | Tipo |
|------|-------|------|
| `evidence_contract.py` | 533 | Modulo |
| `source_lineage_service.py` | 470 | Modulo |
| `legacy_relation_adapter.py` | 608 | Modulo |
| `answer_evidence_gate.py` | 290 | Modulo |
| `evidence_snapshot_service.py` | 230 | Modulo |
| `event_ontology_service.py` | 310 | Modulo |
| `docs/architecture/EVIDENCE_ARCHITECTURE_AUDIT.md` | — | Doc (Fase 1) |

### File modificati (2)
| File | Modifica |
|------|----------|
| `linking/schema_v2.py` | Fix `_safe_alter()`, CHECK constraint, table count |
| `docs/ARCHITETTURA_COMPLETA.md` | Versione 5.0, roadmap aggiornata |
| `docs/changelog/CHANGELOG.md` | Entry Evidence-Centric Architecture |

### Documenti architettura nuovi (7)
| File | Fase |
|------|------|
| `docs/architecture/EVIDENCE_ARCHITECTURE_AUDIT.md` | 1 |
| `docs/architecture/EVIDENCE_CONTRACT.md` | 2 |
| `docs/architecture/SOURCE_LINEAGE.md` | 3 |
| `docs/architecture/LEGACY_QUARANTINE.md` | 4 |
| `docs/architecture/ANSWER_EVIDENCE_BUNDLE.md` | 5 |
| `docs/architecture/EVIDENCE_SNAPSHOT_PERSISTENT.md` | 6 |
| `docs/architecture/EVENT_ONTOLOGY.md` | 7 |

### File temporanei (creati e eliminati)
| File | Test |
|------|------|
| `_test_source_lineage.py` | 10 test, eliminato |
| `_test_legacy_adapter.py` | 9 test, eliminato |
| `_test_answer_gate.py` | 10 test, eliminato |
| `_test_snapshot_service.py` | 10 test, eliminato |
| `_test_event_ontology.py` | 15 test, eliminato |

---

## Metriche

| Metrica | Valore |
|---------|--------|
| Moduli nuovi | 6 |
| File modificati | 2 |
| Documenti nuovi | 7 |
| Test eseguiti | 54 |
| Test PASS | 54 (100%) |
| Bug risolti | 4 |
| Fix schema | 3 |
| Fasi completate | 6 (Fasi 2-7) |
| Fasi rimanenti | 3 (Fasi 8-10) |

---

*Audit log generato 2026-08-17*
