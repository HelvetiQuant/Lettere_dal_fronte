# Legacy Quarantine — Adapter e Revalidazione Relazioni Legacy

**Versione**: 1.0  
**Data**: 2026-08-17  
**Modulo di riferimento**: `legacy_relation_adapter.py`  
**Schema di riferimento**: `linking/schema_v2.py` (colonne `origin`, `temporal_gate`, `identity_gate`)

---

## 1. Strategia

```
Legacy Tables (read-only)     →  LegacyRelationAdapter  →  V2 relations (origin='legacy')
────────────────────────                                    ──────────────────────────────
record_links (~1.7M rows)    →  scan + import            →  status='legacy_candidate'
collegamenti (~50K rows)     →  scan + import            →  status='legacy_candidate'
event_links (~1.5M rows)     →  scan + import            →  status='legacy_candidate'
                                                              │
                                                              ↓
                                                         revalidate_batch()
                                                              │
                                                    ┌─────────┼──────────┐
                                                    ↓         ↓          ↓
                                               accepted   needs_review  rejected
                                               (origin=   (origin=      (origin=
                                                legacy_    legacy_       legacy)
                                                revalidated) revalidated)
```

### Principi

1. **Non-distruttivo**: le tabelle legacy NON vengono modificate, rinominate o eliminate
2. **Reversibile**: ogni azione dell'adapter può essere annullata
3. **Gated**: le relazioni legacy non possono mai raggiungere status `verified` senza revalidazione
4. **Tracciato**: ogni relazione legacy importata ha `pipeline_run_id` e `origin='legacy'`
5. **Bloccato da AI**: `legacy_candidate` è bloccato dal contesto AI (`is_safe_for_ai_context = False`)

---

## 2. Tabelle Legacy Gestite

| Tabella | DB | Righe (stimate) | Campo Usable | Note |
|---------|----|---------|-------------|------|
| `record_links` | main (imi_internati.db) | ~1.7M | `usable_as_evidence` | V7.3-FIX: quarantena additiva |
| `collegamenti` | main (imi_internati.db) | ~50K | N/A (tutte considerate) | Legacy entity extraction |
| `event_links` | events (eventi_1gm.db) | ~1.5M | `usable_as_evidence` | V7.3-FIX: + war_period |

---

## 3. Ciclo di Vita Legacy → V2

```
                    ┌─────────────────┐
                    │  Legacy Table   │
                    │  (read-only)    │
                    └────────┬────────┘
                             │ import_table()
                             ↓
                    ┌─────────────────┐
                    │  V2 relations   │
                    │  origin=legacy  │
                    │  status=        │
                    │  legacy_candidate│
                    └────────┬────────┘
                             │ revalidate_batch()
                             │
                    ┌────────┼────────┐
                    │        │        │
                    ↓        ↓        ↓
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ accepted │ │ needs_   │ │ rejected │
              │ origin=  │ │ review   │ │ origin=  │
              │ legacy_  │ │ origin=  │ │ legacy   │
              │ validated│ │ legacy_  │ │          │
              │          │ │ validated│ │          │
              │ score≥0.7│ │ score<0.7│ │ score<0.3│
              │ temporal │ │ OR       │ │ OR       │
              │ compat.  │ │ temporal │ │ temporal │
              │          │ │ ambig.   │ │ incompat.│
              └──────────┘ └──────────┘ └──────────┘
```

### Gate di Revalidazione

| Gate | Condizione | Esito |
|------|-----------|-------|
| **Confidence** | `raw_score < 0.3` | rejected |
| **Temporal** | `war_period` WW1 vs WW2 mismatch | rejected |
| **Temporal** | `war_period` non determinabile | needs_review |
| **Confidence** | `raw_score < 0.7` | needs_review |
| **Confidence + Temporal** | `raw_score ≥ 0.7` + temporal compatible | accepted |

**Not critica**: `accepted` ≠ `verified`. Le relazioni legacy revalidate possono raggiungere al massimo `accepted`, mai `verified` direttamente.

---

## 4. Safety Checks

### `is_safe_for_verified(status, origin)`

| origin | status | Safe? |
|--------|--------|-------|
| `legacy` | any | ❌ NO |
| `legacy_revalidated` | `accepted` | ✅ Sì (probable) |
| `legacy_revalidated` | `needs_review` | ❌ NO |
| `v2` | `confirmed`/`accepted` | ✅ Sì |

### `is_safe_for_ai_context(status, origin)`

| origin | status | Safe? |
|--------|--------|-------|
| `legacy` | `legacy_candidate` | ❌ NO |
| `legacy` | `rejected` | ❌ NO |
| `legacy_revalidated` | `accepted` | ✅ Sì |
| `legacy_revalidated` | `needs_review` | ✅ Sì (come probable) |
| `v2` | any active | ✅ Sì |

---

## 5. API di Utilizzo

```python
from legacy_relation_adapter import LegacyRelationAdapter

adapter = LegacyRelationAdapter(conn, events_conn=events_conn)

# Audit — solo lettura
stats = adapter.scan_all()
# → [record_links: 1.7M total, 1.2M usable, ...]

# Import — dry-run
stats = adapter.import_all(dry_run=True)
# → Conta quante verrebbe importate

# Import — execute
stats = adapter.import_all(dry_run=False, pipeline_run_id="run_2026_08_17")
# → Importa come legacy_candidate

# Revalidation
stats = adapter.revalidate_batch(dry_run=False, limit=1000)
# → Applica gate: accepted/needs_review/rejected

# Report
report = adapter.get_quarantine_report()
# → Stato completo: legacy tables + V2 legacy relations
```

---

## 6. Modifiche Apportate (Fase 4)

### Modulo nuovo

- `legacy_relation_adapter.py` — 3 classi + 2 dataclass:
  - `LegacyRelationAdapter`: scan, import, revalidation, report
  - `LegacyRelation` / `AdapterStats`: dataclass
  - Safety checks statici: `is_safe_for_verified`, `is_safe_for_ai_context`

### Fix schema

- `_safe_alter()`: fix parsing commenti multi-linea in ALTER TABLE statements
- `temporal_gate`: aggiunto `'unknown'` al CHECK constraint
- `identity_gate`: aggiunto `'unknown'` al CHECK constraint, default cambiato a `'unverified'`

### Test

- 9/9 test PASS: scan, import (dry-run + execute), idempotency, collegamenti, revalidation, report, safety checks

---

*Fase 4 completata — pronto per Fase 5: AnswerEvidenceBundle*
