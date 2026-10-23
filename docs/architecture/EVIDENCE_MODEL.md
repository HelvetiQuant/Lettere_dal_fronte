# Evidence Model — Contratto Centrale

**Versione**: 1.0  
**Data**: 2026-08-17  
**Modulo di riferimento**: `evidence_contract.py`  
**Schema di riferimento**: `linking/schema_v2.py` (v2.1)

---

## 1. Catena Evidence-Centric

```
SOURCE → OBSERVATION → EVIDENCE → CLAIM → RELATION → ANSWER
  │           │            │          │          │          │
  │           │            │          │          │          └── AnswerEvidenceBundle
  │           │            │          │          └── RelationRef (temporal/geo/identity gates)
  │           │            │          └── ClaimRef (verification_status, evidence_ids)
  │           │            └── EvidenceRef (support_type, is_independent, lineage)
  │           └── ObservationRef (raw_value, extraction_method, extractor_version)
  └── SourceRef (authority_tier, lineage_id, origin_type)
```

### Strutture trasversali

| Struttura | Dove | Scopo |
|-----------|------|-------|
| **PROVENANCE** | `provenance_chain` su ClaimRef | Traccia observation→evidence→claim |
| **SOURCE LINEAGE** | `source_lineages` + `source_lineage_members` | Traccia derivazione fonti (independent/derived/republication/mirror) |
| **CONFLICTS** | `conflict_status` su ClaimRef, `conflict_flags` su relations | Temporal/geographic/identity/source/factual |
| **ASSESSMENT** | `verification_status` (8 livelli) | unsupported→candidate→supported→probable→verified / contradicted / disputed / rejected |
| **EVIDENCE SNAPSHOT** | `evidence_snapshots` table | Snapshot immutabile persistito per riproducibilità |

---

## 2. Entità del Contratto

### 2.1 SOURCE

Un source è un'entità che fornisce dati storici.

| Attributo | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `source_id` | TEXT | ✅ | ID univoco (UUID) |
| `provider` | TEXT | ✅ | Nome provider (es. "Albo d'Oro", "CWGC") |
| `source_type` | TEXT | ✅ | archive\|document\|web\|ocr\|ai_extracted\|user_submitted |
| `authority_tier` | INT | ✅ | 1=official, 2=primary, 3=secondary, 4=unofficial |
| `lineage_id` | TEXT | — | ID in `source_lineages` |
| `origin_type` | TEXT | ✅ | independent\|derived\|republication\|mirror\|unknown |

**Regola AUTHORITY ≠ RELEVANCE**: Una fonte con authority_tier=1 ma relevance_score=0.05 NON produce evidence. Il gate è moltiplicativo con soglia minima, non una media pesata.

### 2.2 OBSERVATION

Un'osservazione è un dato effettivamente osservato dentro una fonte.

| Attributo | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `observation_id` | TEXT | ✅ | UUID |
| `source_id` | TEXT | ✅ | Riferimento al source |
| `observation_type` | TEXT | ✅ | field_extraction\|entity_mention\|date\|place\|unit\|matricola\|event_ref |
| `field_name` | TEXT | ✅ | Campo osservato (es. "cognome", "data_nascita") |
| `raw_value` | TEXT | ✅ | Valore esatto osservato (NON normalizzato) |
| `normalized_value` | TEXT | — | Forma normalizzata |
| `extraction_method` | TEXT | ✅ | ocr\|regex\|ai\|manual\|federated |
| `extractor_version` | TEXT | ✅ | Versione algoritmo |

**Invariante**: `raw_value` non viene MAI sovrascritto dalla normalizzazione.

### 2.3 EVIDENCE

Evidence è un frammento qualificato di un'osservazione, con support_type esplicito.

| Attributo | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `evidence_id` | TEXT | ✅ | UUID |
| `observation_id` | TEXT | ✅ | Riferimento all'osservazione |
| `support_type` | TEXT | ✅ | supports\|contradicts\|mentions\|context |
| `evidence_type` | TEXT | ✅ | direct\|indirect\|contextual\|metadata |
| `is_independent` | BOOL | ✅ | True se la fonte è indipendente da altre fonti per lo stesso claim |
| `lineage_id` | TEXT | — | Riferimento alla source lineage |
| `verification_status` | TEXT | ✅ | unverified\|verified\|contradicted\|superseded |

**Invariante**: `is_independent` richiede verifica del lineage. Due fonti dello stesso archivio NON sono indipendenti.

### 2.4 CLAIM

Un claim è un'affermazione atomica storica con subject, predicate, object.

| Attributo | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `claim_id` | TEXT | ✅ | UUID |
| `subject_id` | TEXT | ✅ | Riferimento al resource_registry |
| `predicate` | TEXT | ✅ | es. "birth_place", "unit", "death_date" |
| `object_value` | TEXT | ✅ | Valore affermato |
| `normalized_value` | TEXT | — | Forma normalizzata |
| `evidence_ids` | LIST | ✅* | Evidence di supporto (*obbligatorio per status ≥ supported) |
| `verification_status` | TEXT | ✅ | unsupported\|candidate\|supported\|probable\|verified\|contradicted\|disputed\|rejected |
| `support_score` | REAL | ✅ | Punteggio di supporto [0.0, 1.0] |
| `conflict_status` | TEXT | ✅ | none\|temporal\|geographic\|identity\|source\|factual |
| `identity_cluster_id` | TEXT | — | Cluster di identità (per person_claims) |
| `source_lineage_ids` | LIST | — | Lineages delle fonti di evidence |
| `provenance_chain` | LIST | — | Catena observation→evidence→claim |

**Invariante**: Nessun claim con status `verified` senza almeno 1 evidence indipendente.

### 2.5 RELATION

Una relazione strutturata derivata da claim/evidence.

| Attributo | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `relation_id` | TEXT | ✅ | UUID |
| `source_resource_id` | TEXT | ✅ | Resource sorgente |
| `target_resource_id` | TEXT | ✅ | Resource target |
| `relation_type` | TEXT | ✅ | es. "same_person", "source_describes_event" |
| `claim_ids` | LIST | ✅* | Claim di supporto (*non richiesto per origin=legacy) |
| `temporal_gate` | TEXT | ✅ | direct_contemporary\|retrospective\|compatible\|ambiguous\|incompatible |
| `geographic_gate` | TEXT | ✅ | exact\|compatible\|ambiguous\|incompatible\|unknown |
| `identity_gate` | TEXT | ✅ | verified\|probable\|candidate\|unverified\|rejected |
| `origin` | TEXT | ✅ | v2\|legacy\|legacy_revalidated\|manual\|imported |
| `verification_status` | TEXT | ✅ | Come claim verification_status |

**Invariante**: Relazioni legacy NON possono essere verified. Devono essere revalidate.

### 2.6 ANSWER (AnswerEvidenceBundle)

Il bundle passato al narratore AI.

| Sezione | Contenuto | Regola AI |
|---------|-----------|-----------|
| `verified_claims` | Claim con status=verified | Può essere affermato come fatto |
| `probable_claims` | Claim con status=probable | Frasaggio probabilistico ("probabilmente") |
| `disputed_claims` | Claim con status=disputed/contradicted | Mostrare il conflitto esplicitamente |
| `unsupported_claims` | Claim con status=unsupported | NON presentare come fatto |
| `rejected_claims` | Claim con status=rejected | NON usare |
| `sources` | Fonti con authority e lineage | Citazioni |
| `conflicts` | Conflitti espliciti | Mostrare |
| `gaps` | Gap informativi | Menzionare come limitazione |

**Invariante**: L'AI riceve SOLO l'AnswerEvidenceBundle, mai record raw o relazioni legacy non validate.

---

## 3. Livelli di Verification Status

```
unsupported    → Nessun evidence trovato
candidate      → Evidence trovato ma non verificato
supported      → Evidence verificato, 1 fonte indipendente
probable       → Evidence verificato, 1 fonte indipendente + coerenza interna
verified       → Evidence verificato, ≥2 fonti indipendenti + provenance chain
contradicted   → Evidence in conflitto (una fonte contradice)
disputed       → Evidence ambiguo (fonti discordi, non risolvibile)
rejected       → Evidence refutato o veto gate superato
```

### Transizioni permesse

```
unsupported → candidate (evidence trovato)
candidate → supported (evidence verificato)
candidate → contradicted (evidence contradice)
candidate → rejected (veto gate)
supported → probable (coerenza interna verificata)
probable → verified (≥2 fonti indipendenti)
probable → disputed (conflitto emergente)
verified → disputed (nuovo evidence contradice)
disputed → verified (conflitto risolto)
disputed → rejected (conflitto irresolvibile)
any → superseded (nuovo claim sostituisce)
```

---

## 4. Gate Policy

### 4.1 Temporal Gate

| Stato | Significato | Azione |
|-------|-------------|--------|
| `direct_contemporary` | Fonte contemporanea all'evento | ✅ Massima attendibilità |
| `retrospective` | Fonte postuma ma compatibile | ⚠️ Attendibilità ridotta |
| `temporally_compatible` | Periodo fonte sovrappone evento | ✅ Attendibile |
| `temporally_ambiguous` | Periodo fonte non determinabile | ⚠️ Non bloccante, ma non verified |
| `temporally_incompatible` | Periodo fonte NON sovrappone | 🔴 VETO — nessun evidence |

### 4.2 Geographic Gate

| Stato | Significato | Azione |
|-------|-------------|--------|
| `exact` | Luogo fonte = luogo evento | ✅ |
| `compatible` | Luogo fonte compatibile | ✅ |
| `ambiguous` | Luogo non determinabile | ⚠️ |
| `incompatible` | Luogo incompatibile | 🔴 VETO |

### 4.3 Identity Gate

| Stato | Significato | Azione |
|-------|-------------|--------|
| `verified` | Identità verificata (≥4 discriminatori) | ✅ |
| `probable` | Identità probabile (2-3 discriminatori) | ⚠️ |
| `candidate` | Candidato (1 discriminatore) | ⚠️ |
| `unverified` | Non verificato | 🔴 Non verified |
| `rejected` | Omonimia confermata | 🔴 VETO |

---

## 5. Invarianti del Contratto

```python
# 1. No claim without evidence
assert all(c.evidence_ids for c in claims if c.verification_status >= "supported")

# 2. No evidence without observation
assert all(e.observation_id for e in evidence_items)

# 3. No observation without source
assert all(o.source_id for o in observations)

# 4. No relation without claim(s) — unless legacy
assert all(r.claim_ids for r in relations if r.origin != "legacy")

# 5. No verified status without evidence + provenance
assert all(c.evidence_ids and c.provenance_chain for c in claims if c.verification_status == "verified")

# 6. No AI answer without AnswerEvidenceBundle
assert narrator_input is AnswerEvidenceBundle

# 7. AUTHORITY ≠ RELEVANCE
assert not (authority_tier == 1 and relevance_score < 0.1)  # → no evidence

# 8. MULTIPLE SOURCES ≠ INDEPENDENT
assert independent_lineage_count <= evidence_count

# 9. RETRIEVAL ≠ VERIFICATION
assert retrieval_result.verification_status != "verified"  # must be "candidate"

# 10. No legacy shortcut to truth
assert not (relation.origin == "legacy" and relation.verification_status == "verified")
```

---

## 6. Mapping Schema V2 → Evidence Contract

| Evidence Contract | Schema V2 Table | Note |
|-------------------|-----------------|------|
| SourceRef | `resource_registry` + `source_authority_registry` | authority_tier da source_authority_registry |
| ObservationRef | `observations` (NEW) | Tra source_artifacts e evidence_fragments |
| EvidenceRef | `evidence_fragments` + `claim_evidence_v2` | + nuove colonne: observation_id, evidence_type, is_independent |
| ClaimRef | `claims_v2` | + nuove colonne: temporal_context, geographic_context, support_score, conflict_status, verification_status, identity_cluster_id, source_lineage_id |
| RelationRef | `relations` | + nuove colonne: temporal_gate, geographic_gate, identity_gate, origin, snapshot_id |
| AnswerEvidenceBundle | (in-memory) | Costruito da `EvidenceContract.build_answer_bundle()` |
| EvidenceSnapshot | `evidence_snapshots` (NEW) | Persistito per riproducibilità |
| SourceLineage | `source_lineages` (NEW) + `source_lineage_members` (NEW) | Sostituisce/estende source_families |
| ExplainableScore | `explainable_scores` (NEW) | Feature breakdown per relation |
| PlaceAuthority | `place_authority` (NEW) | Geographic authority layer |

---

## 7. Modifiche Apportate (Fase 2)

### Schema (`linking/schema_v2.py`)

**Nuove tabelle** (6):
- `observations` — osservazioni tra source_artifacts e evidence_fragments
- `source_lineages` — lineage delle fonti con origin_type
- `source_lineage_members` — membership resource ↔ lineage
- `evidence_snapshots` — snapshot immutabili persistiti
- `explainable_scores` — feature breakdown per relation
- `place_authority` — geographic authority layer

**Colonne aggiuntive** (additive, idempotent):
- `claims_v2`: +11 colonne (temporal_context, geographic_context, support_score, conflict_status, verification_status, evidence_scope, identity_cluster_id, source_lineage_id, pipeline_run_id, reviewed_at, reviewed_by)
- `evidence_fragments`: +5 colonne (observation_id, evidence_type, verification_status, source_lineage_id, is_independent)
- `relations`: +5 colonne (temporal_gate, geographic_gate, identity_gate, origin, snapshot_id)

### Modulo nuovo

- `evidence_contract.py` — validator centrale con 10 invarianti, gate policy, AnswerEvidenceBundle

---

*Fase 2 completata — pronto per Fase 3: Source Lineage*
