# Source Lineage — Tracciamento Provenienza e Indipendenza Fonti

**Versione**: 1.0  
**Data**: 2026-08-17  
**Modulo di riferimento**: `source_lineage_service.py`  
**Schema di riferimento**: `linking/schema_v2.py` (tabelle `source_lineages`, `source_lineage_members`)

---

## 1. Modello

```
source_lineages (canonico)
  ├── id (UUID)
  ├── canonical_origin (es. "ANRP — LeBI")
  ├── origin_type: independent | derived | republication | mirror | unknown
  ├── parent_lineage_id (per lineage gerarchici)
  ├── authority_level [0.0, 1.0]
  └── description

source_lineage_members (membership)
  ├── resource_id → resource_registry
  ├── lineage_id → source_lineages
  ├── relation_to_root: root | derived | republication | mirror | unknown
  └── evidence_observation_id → observations
```

### Regola fondamentale

> **MULTIPLE SOURCES ≠ INDEPENDENT SOURCES**  
> Due fonti della stessa lineage = 1 fonte indipendente.  
> Il conteggio di corroboration usa `independent_lineage_count`, non `evidence_count`.

---

## 2. Tipi di Lineage

| origin_type | Significato | Independence score (intra-lineage) | Esempio |
|-------------|-------------|-----------------------------------|---------|
| `independent` | Fonte originale, non derivata | 0.2 (membri condividono origine) | ANRP LeBI, CICR, Ministero Difesa |
| `derived` | Derivata da un'altra fonte | 0.05 | Fonti Indice (da archivi primari) |
| `republication` | Ripubblicazione di contenuti | 0.1 | Wikipedia (da fonti primarie) |
| `mirror` | Copia speculare | 0.05 | Mirror di un archivio |
| `unknown` | Non classificata | 0.5 | Ricerca web non strutturata |

**Nota critica**: `origin_type` descrive la relazione della lineage verso *altre* lineages, non l'indipendenza *intra-lineage*. Membri della stessa lineage hanno sempre bassa indipendenza (condividono l'origine).

---

## 3. Bootstrap — 12 Lineages Predefinite

Popolate da `source_authority_registry.py` DEFAULT_SOURCES:

| # | Canonical Origin | Type | Authority | Source Key |
|---|-----------------|------|-----------|------------|
| 1 | ANRP — LeBI | independent | 0.95 | anrp_lebi |
| 2 | CICR — Red Cross | independent | 0.95 | icrc |
| 3 | Ministero della Difesa | independent | 0.92 | ministero_difesa |
| 4 | Albo d'Oro WWI | independent | 0.85 | albo_oro |
| 5 | CWGC | independent | 0.82 | cwgc |
| 6 | Nastro Azzurro | independent | 0.80 | nastro_azzurro |
| 7 | IMI DB locale | independent | 0.78 | internati_imi |
| 8 | Fonti Indice | derived | 0.50 | fonti_indice |
| 9 | Archivio Documenti | derived | 0.45 | archivio_documenti |
| 10 | Lettere dal Fronte OCR | derived | 0.40 | ocr_lettere |
| 11 | Ricerca Web | unknown | 0.20 | web_search |
| 12 | Wikipedia | republication | 0.15 | wikipedia |

---

## 4. Independence Scoring

### `get_independence_score(resource_a, resource_b)`

| Condizione | Score | Logica |
|------------|-------|--------|
| Stessa risorsa | 0.0 | Identica |
| Stessa lineage (independent) | 0.2 | Condividono origine |
| Stessa lineage (derived) | 0.05 | Derivata dalla stessa fonte |
| Stessa lineage (republication) | 0.1 | Ripubblicazione |
| Parent lineage relationship | 0.1 | Una deriva dall'altra |
| Lineages diverse, stessa authority | 0.3 | Stesso livello ma origine diversa |
| Lineages diverse, authority diversa | 0.9 | Fonti veramente indipendenti |
| Nessuna lineage nota | 0.7 | Default conservativo |

### `count_independent_lineages(resource_ids)`

Conta solo lineages con `origin_type = independent`. Restituisce `(resource_count, independent_lineage_count)`.

### `corroboration_bonus(resource_ids)`

Bonus logaritmico basato su `independent_lineage_count`:
- 1 independent → 0.0
- 2 independent → +0.1
- 3 independent → +0.16
- 4+ independent → +0.2 (cap)

---

## 5. Integrazione con V7 Fusion Engine

### Prima (in-memory, senza DB)

```python
# v7_fusion_engine.py — SourceFamilyGraph + IndependenceAssessor
graph = SourceFamilyGraph()
graph.add_source(SourceNode(source_id="s1", provider="lebi", archive="ANRP"))
graph.add_source(SourceNode(source_id="s2", provider="icrc", archive="CICR"))
graph.add_edge("s1", "s2", "SAME_ARCHIVE")  # sbagliato: archivi diversi

assessor = IndependenceAssessor(graph)
score = assessor.assess_independence("s1", "s2")  # 0.3 (same archive)
```

### Dopo (DB-backed, con lineage)

```python
# source_lineage_service.py — LineageAwareAssessor
assessor = LineageAwareAssessor(conn)
score = assessor.assess_independence(lebi_resource_id, icrc_resource_id)  # 0.9 (independent)
```

### Migrazione

1. `LineageBootstrap.bootstrap()` popola `source_lineages` da `DEFAULT_SOURCES`
2. `LineageSync.sync_from_graph()` sincronizza `SourceFamilyGraph` in-memory → DB
3. `LineageAwareAssessor` sostituisce `IndependenceAssessor` quando DB disponibile
4. `FusionEngine` usa `LineageAwareAssessor` per `independence_group_ids` su `ClaimV7`

---

## 6. Modifiche Apportate (Fase 3)

### Modulo nuovo

- `source_lineage_service.py` — 4 classi:
  - `LineageRegistry`: CRUD per `source_lineages` e `source_lineage_members`
  - `LineageBootstrap`: popola da `source_authority_registry` (12 lineages)
  - `LineageAwareAssessor`: DB-backed independence assessment
  - `LineageSync`: sincronizza `SourceFamilyGraph` → DB

### Schema (già creato in Fase 2)

- `source_lineages` table (6 colonne + 3 indici)
- `source_lineage_members` table (4 colonne + 1 indice)

### Test

- 10/10 test PASS: bootstrap, idempotency, independence scoring, derived membership, sync

---

## 7. API di Utilizzo

```python
from source_lineage_service import LineageRegistry, LineageBootstrap, LineageAwareAssessor

# Bootstrap
bootstrap = LineageBootstrap(conn)
stats = bootstrap.bootstrap()
# → 12 lineages created, 12 members added

# Assess independence
assessor = LineageAwareAssessor(conn)
score = assessor.assess_independence(res_a, res_b)
# → 0.9 (different independent lineages)

# Count independent
count, indep = assessor.count_independent([res_a, res_b, res_c])
# → (3, 2) — 3 resources, 2 independent lineages

# Corroboration bonus
bonus = assessor.corroboration_bonus([res_a, res_b])
# → 0.1 (2 independent sources)
```

---

*Fase 3 completata — pronto per Fase 4: Legacy Quarantine*
