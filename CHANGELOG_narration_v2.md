# Changelog: V7.2-narration-v2 — Structured Draft→Result Pipeline

## Data: 2025-01-XX
## Versione: 7.2-narration-v2

## Sommario

Refactoring completo del pipeline di narrazione V7.2. Il narratore AI ora produce
solo un `NarrationDraft` (blocchi narrativi atomici con `claim_ids` dalla allowlist).
Il backend valida, ripara, renderizza e computa tutti i metadati (citation_map,
omitted_claims, used_claim_ids, answer_markdown).

## Problemi risolti

### 1. AI produceva answer_markdown come testo libero
**Prima:** L'AI riceveva 200-300 claim e produceva `answer_markdown` come stringa
libera. Il backend non aveva controllo strutturato sul contenuto.

**Dopo:** L'AI produce solo blocchi atomici (`NarrationBlock`) con `claim_ids`
dalla allowlist. Il backend assembla `answer_markdown` dai blocchi validati.

### 2. Nessuna allowlist sui claim
**Prima:** L'AI poteva riferirsi a qualsiasi claim, incluso claim rejected
o non pertinente.

**Dopo:** `NarrationEvidenceSelector` seleziona deterministicamente i claim
pertinenti con budget limitati. Il validator rifiuta claim non in allowlist.

### 3. source_id e URL nel testo AI
**Prima:** L'AI poteva inserire URL o `source_id` nel testo. Il validator
li rilevava ma non poteva ripararli.

**Dopo:** Il validator rifiuta URL, `source_id`, `obs_id` nel testo dei blocchi.
Il repair li rimuove sostituendo con `[fonte]`.

### 4. Nessun omitted_claims deterministico
**Prima:** `omitted_claims` era prodotto dall'AI o non esisteva.

**Dopo:** `omitted_claims = candidate_claim_ids - used_claim_ids`, computato
dal backend con reason codes deterministici.

### 5. citation_map non affidabile
**Prima:** L'AI produceva `citation_map` che poteva contenere source_id
inesistenti o hallucinated.

**Dopo:** `citation_map` è costruito dal backend dalle relazioni
claim→evidence→source persistenti nello snapshot.

### 6. Web leads come evidenza
**Prima:** Web leads non validati potevano apparire come fatti nella narrazione.

**Dopo:** Web leads sono esclusi dal payload principale. Al massimo 5
appaiono in una sezione tecnica separata, mai come fatti.

### 7. Bug: ContextClaimV7.context_scope
**Prima:** `render_deterministic_markdown` usava `c.context_scope` ma
`ContextClaimV7` ha `c.scope`. Causava `AttributeError` per EVENT_LOOKUP.

**Dopo:** Fix a `c.scope` e `c.value`.

## Nuovi file

| File | Descrizione |
|------|-------------|
| `narration_models.py` | `NarrationDraft`, `NarrationBlock`, `NarrationResult`, `CitationEntry`, `OmittedClaim`, `GenerationInfo` |
| `narration_evidence_selector.py` | `NarrationEvidenceSelector` con budget, scoring, diversity, omission |
| `narration_validator.py` | `NarrationValidator` con allowlist, URL rejection, entity-specific checks, repair |
| `v7_narrator_prompt_v2.py` | Prompt per draft-only (blocchi atomici, no source_ids) |
| `test_narration_v2_master.py` | 61 test: contratto, selector, validator, narrator, regression, edge cases |

## File modificati

| File | Modifica |
|------|----------|
| `v7_narrator.py` | Aggiunta `NarratorV7_v2` (draft→validate→render→result). Fix `ContextClaimV7.scope`. |
| `unified_orchestrator_v7.py` | `_stage_narrate` usa `NarratorV7_v2`. `RunContext.narration_result`. `execute()` ritorna `narration_result`. |

## Architettura

```
Snapshot → NarrationEvidenceSelector → [selected claims + allowlist]
                                          │
                                          ▼
                                     AI Provider
                                          │
                                          ▼
                                    NarrationDraft
                                   (atomic blocks)
                                          │
                                          ▼
                                  NarrationValidator
                                   (allowlist check)
                                          │
                                 ┌───────┴───────┐
                                 │               │
                              valid           invalid
                                 │               │
                                 │          repair attempt
                                 │               │
                                 │         ┌─────┴─────┐
                                 │         │           │
                                 │      repaired   fallback
                                 │         │       (deterministic)
                                 ▼         ▼           │
                            NarrationResult ◄──────────┘
                          (always structured)
```

## Invarianti del contratto

1. **Nessun code path ritorna una stringa invece di `NarrationResult`**
2. **`answer_markdown` è renderizzato dal backend da blocchi validati**
3. **`used_claim_ids` è l'unione deterministica dei `claim_ids` nei blocchi validati**
4. **`citation_map` è costruito dal backend da relazioni claim→evidence→source**
5. **`omitted_claims = candidate_ids - used_claim_ids`**
6. **`source_id` non è mai accettato dall'output AI**
7. **Il testo AI grezzo non è mai pubblicato o passato al renderer**
8. **Web leads non validati non appaiono mai come fatti**

## Test

```
Ran 61 tests in 0.008s
OK
```

Categorie:
- **Contract** (9): struttura NarrationDraft, NarrationResult, serialization
- **Evidence Selector** (10): selezione, budget, omission, diversity, web leads
- **Validator** (11): allowlist, URL, source_ref, obs_id, rejected claims, repair, entity-specific
- **NarratorV7_v2** (7): deterministic fallback, blocked, citation_map, omitted, structured, generation
- **Regression** (8): Sonavetti, Venturini, Sardi, Muccio, Franchini, Gridini, Col di Lana, Roma/Romania
- **Request Type Coverage** (3): PERSON, FACT, EVENT
- **Edge Cases** (7): ambiguous, insufficient, conflict, no-AI, homonym, web lead, serializable
- **AI Draft Simulation** (2): valid draft, hallucinated claim repair

## Compatibilità

- `NarratorV7` (legacy) è mantenuto per backward compatibility
- `NarratorV7_v2` è il nuovo narratore predefinito
- L'orchestrator usa `NarratorV7_v2` ma istanzia anche `NarratorV7` per compat
- `execute()` ritorna sia `report` (string, legacy) che `narration_result` (dict, nuovo)

## Pending

- **ai_client.py**: JSON schema nativo quando disponibile (task #10, medium priority)
- Integrazione con frontend per visualizzare `narration_result` strutturato
- Metriche di qualità AI vs deterministic
