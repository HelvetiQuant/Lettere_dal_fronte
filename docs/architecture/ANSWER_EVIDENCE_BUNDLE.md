# Answer Evidence Bundle — Gate Narrativo AI

**Versione**: 1.0  
**Data**: 2026-08-17  
**Modulo di riferimento**: `answer_evidence_gate.py`  
**Contratto di riferimento**: `evidence_contract.py` (AnswerEvidenceBundle)

---

## 1. Posizione nell'Architettura

```
EvidenceSnapshotV7 (in-memory)
       │
       ↓
AnswerEvidenceGate.build_bundle()
       │
       ↓
AnswerEvidenceBundle (gated, strutturato)
       │
       ├── verified_claims    → AI: "stata come fatto"
       ├── probable_claims    → AI: "probabilmente"
       ├── disputed_claims    → AI: "mostrare conflitto"
       ├── unsupported_claims → AI: "NON come fatto"
       ├── rejected_claims    → AI: "NON usare"
       ├── sources            → AI: citazioni [ID]
       ├── conflicts          → AI: mostrare esplicitamente
       ├── gaps               → AI: "non documentato"
       ├── context_hash       → integrità input
       └── answer_hash        → integrità output
       │
       ↓
AnswerEvidenceGate.build_ai_prompt()
       │
       ↓
AI Narrator (GPT-4o / Mistral)
       │
       ↓
AnswerEvidenceGate.verify_answer()
       │
       ↓
Report finale con citazioni
```

### Principio fondamentale

> **L'AI riceve SOLO l'AnswerEvidenceBundle, mai record raw o relazioni legacy non validate.**

---

## 2. Mapping Status ClaimV7 → EvidenceContract

| ClaimV7 status | EvidenceContract verification_status | Significato |
|----------------|--------------------------------------|-------------|
| `VERIFIED` | `verified` | ≥2 fonti indipendenti + provenance |
| `ACCEPTED` | `probable` | Multi-fonte, alta confidenza |
| `ASSERTED` | `supported` | Singola fonte, claim supportato |
| `SUPPORTED` | `supported` | Evidence verificato |
| `CONFLICTING` | `disputed` | Fonti discordi |
| `CANDIDATE` | `candidate` | Non ancora verificato |
| `DISCOVERED` | `candidate` | Trovato ma non verificato |
| `REJECTED` | `rejected` | Refutato o veto gate |
| `UNSUPPORTED` | `unsupported` | Nessun evidence |

---

## 3. Gate di Validazione

### Pre-generazione (`validate_bundle`)

| Check | Violazione |
|-------|-----------|
| VERIFIED claim senza evidence_ids | `VERIFIED claim has no evidence_ids` |
| VERIFIED claim senza provenance_chain | `VERIFIED claim has no provenance_chain` |
| UNSUPPORTED claim con status non corretto | `UNSUPPORTED claim has wrong status` |
| REJECTED claim in verified/probable | `REJECTED claim also in verified/probable` |

### Post-generazione (`verify_answer`)

| Check | Violazione |
|-------|-----------|
| UNSUPPORTED claim affermato come fatto | `UNSUPPORTED claim stated as fact without hedging` |
| REJECTED claim menzionato nell'output | `REJECTED claim mentioned in output` |
| DISPUTED claim senza riconoscimento del conflitto | `DISPUTED claim mentioned without acknowledging dispute` |

---

## 4. Hash di Integrità

### `context_hash` (input)

SHA-256 di tutti i claim verificati, probabili, disputati, non supportati e fonti nel bundle. Deterministico per lo stesso input.

### `answer_hash` (output)

SHA-256 di `context_hash + ai_output`. Permette di verificare che l'output AI corrisponda a un specifico bundle.

---

## 5. API di Utilizzo

```python
from answer_evidence_gate import AnswerEvidenceGate

gate = AnswerEvidenceGate()

# Build bundle from snapshot
bundle = gate.build_bundle(snapshot, query="Rossi Mario", intent="PERSON_LOOKUP")

# Validate bundle
violations = gate.validate_bundle(bundle)
assert not violations

# Build AI prompt
prompt = gate.build_ai_prompt(bundle, query="Rossi Mario")

# ... send prompt to AI, get response ...

# Verify AI output
is_valid, violations = gate.verify_answer(bundle, ai_output)

# Compute answer hash
answer_hash = gate.compute_answer_hash(bundle, ai_output)
```

---

## 6. Modifiche Apportate (Fase 5)

### Modulo nuovo

- `answer_evidence_gate.py` — `AnswerEvidenceGate` class:
  - `build_bundle()`: EvidenceSnapshotV7 → AnswerEvidenceBundle
  - `validate_bundle()`: pre-generation gate
  - `build_ai_prompt()`: structured prompt with evidence context
  - `verify_answer()`: post-generation verification
  - `compute_answer_hash()`: integrity hash
  - Status mapping: ClaimV7 → EvidenceContract (10 mapping)
  - Authority tier inference from provider name

### Test

- 10/10 test PASS: status mapping, bundle building, validation, prompt generation, hash determinism, post-gen verification (valid + invalid), authority inference, empty snapshot

---

*Fase 5 completata — pronto per Fase 6: EvidenceSnapshot persistente*
