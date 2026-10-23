# Analisi Tecnica — PERSON Pipeline V7.3: Identity Resolution, Claim Extraction, Linking

**Data:** 2026-08-05  
**Branch:** `fix/provenance-linking-v2`  
**Autore:** Cascade (AI pair programmer)  
**Scopo:** Diagnosi completa del call graph PERSON, identificazione root cause, specifica implementativa per fix.

---

## 0. Call Graph effettivo — PERSON_LOOKUP

```
User Input
  ↓
UnifiedResearchOrchestratorV7.execute()                    [unified_orchestrator_v7.py:125]
  ├─ 1. _stage_plan()                                      [unified_orchestrator_v7.py:148]
  │    └─ SemanticQueryPlan(target=TargetSpec(...))        [semantic_query_plan.py:96]
  │
  ├─ 2. _stage_discover()                                  [unified_orchestrator_v7.py:158]
  │    ├─ LocalDbAdapter.search()                          [v7_provider_adapters.py:156]
  │    │    └─ SQLite: internati, caduti_albooro, decorati_nastroazzurro, caduti_cwgc, caduti_ministero
  │    │       (exact match + surname-only match)
  │    ├─ WebSearchAdapter (Tavily, SerpAPI)
  │    └─ FederationAdapter (27 provider)
  │
  ├─ 3. _stage_fetch()                                     [unified_orchestrator_v7.py:163]
  │
  ├─ 4. _stage_extract()                                   [unified_orchestrator_v7.py:168]
  │    └─ _stage_extract_person_claims()                   [unified_orchestrator_v7.py:561]
  │         ├─ Filter: table IN (internati, caduti_albooro, decorati_nastroazzurro, caduti_cwgc)
  │         │   ⚠️ caduti_ministero ESCLUSO
  │         ├─ PERSON_CLAIM_FIELDS: 13 campi (solo internati)
  │         │   ⚠️ campi altre tabelle non mappati
  │         ├─ PROVENANCE_FIELDS: 3 campi (solo internati)
  │         └─ raw_text / needs_review → claim
  │
  ├─ 5. _stage_resolve()                                   [unified_orchestrator_v7.py:173]
  │    └─ IdentityResolver.resolve()                       [v7_identity_model.py:385]
  │         ├─ classify_observation() per ogni obs          [v7_identity_model.py:324]
  │         │   └─ split nominativo: parts[0]=cognome      ⚠️ no word boundary
  │         ├─ _make_cluster_id()                          [v7_identity_model.py:458]
  │         │   └─ hash su cognome+nome+discriminants
  │         │   ⚠️ record con stessi discriminants → stesso cluster anche se dati incompatibili
  │         └─ resolve() → status                          [v7_identity_model.py:385]
  │              ├─ 0 cluster → UNRESOLVED
  │              ├─ 1 cluster, no conflict → RESOLVED or PARTIAL
  │              ├─ 1 cluster, conflict → ⚠️ non gestito esplicitamente
  │              └─ 2+ cluster → AMBIGUOUS or separable
  │
  ├─ 6. _stage_fuse()                                      [unified_orchestrator_v7.py:890]
  │    ├─ AMBIGUOUS_IDENTITY → block fusion, keep person_claims
  │    │   ⚠️ person_claims passano comunque al narrator
  │    └─ RESOLVED → fuse cluster observations only
  │
  ├─ 7. _stage_validate()                                  [unified_orchestrator_v7.py:183]
  │
  ├─ 8. _stage_narrate()                                   [unified_orchestrator_v7.py:1002]
  │    ├─ _build_snapshot()                                [unified_orchestrator_v7.py:~990]
  │    ├─ NarrationEvidenceSelector.select()               [narration_evidence_selector.py]
  │    └─ NarratorV7_v2.narrate()                          [v7_narrator.py]
  │         ├─ Provider rotation: OpenAI → Anthropic → Mistral
  │         │   ⚠️ OpenAI: schema error (followup_question missing in required)
  │         │   ⚠️ Anthropic: 401 Unauthorized
  │         │   └─ Mistral: success
  │         └─ Validation → fallback deterministico
  │
  ├─ 9. _stage_persist()                                   [unified_orchestrator_v7.py:1046]
  │    └─ pass (no-op)
  │
  └─ _compute_semantic_counts()                            [unified_orchestrator_v7.py:1052]
       ⚠️ conta observation class, non fatti unici
       ⚠️ provenance contati come claim
```

---

## 1. File coinvolti e responsabilità

| File | Ruolo | Linee chiave |
|------|-------|-------------|
| `unified_orchestrator_v7.py` | Orchestratore pipeline 9 stage | 125-218 (execute), 561-708 (extract person), 830-888 (resolve), 890-988 (fuse), 1002-1044 (narrate), 1052-1103 (semantic counts) |
| `semantic_query_plan.py` | Piano query immutabile | 37-45 (PERSON_CLAIM_FIELDS), 96-159 (SemanticQueryPlan) |
| `v7_provider_adapters.py` | LocalDbAdapter, WebSearchAdapter | 156-255 (LocalDbAdapter.search) |
| `person_identity_resolver.py` | Resolver deterministico per-source | 280-550 (PersonIdentityResolver) |
| `v7_identity_model.py` | Cluster, IdentityResolver, CorrectionLedger | 54-90 (IdentityCluster), 294-549 (IdentityResolver) |
| `evidence_snapshot_v7.py` | Snapshot DTO con claim | ClaimV7 dataclass |
| `narration_evidence_selector.py` | Selettore claim per narrator | 107-141 (PREDICATE_RELEVANCE_PERSON) |
| `narration_models.py` | NarrationDraft/Result + JSON schema | 299-343 (NARRATION_DRAFT_SCHEMA) |
| `v7_narrator.py` | NarratorV7 con AI + fallback | OutputValidatorV7, NarratorV7_v2 |
| `narration_planner_v73.py` | V7.3 ClaimSelector, CoveragePlanner | Phase D canonical |
| `barriers_v73.py` | Barriere temporali/geografiche | WWI/WWII veto |
| `text_matching_v73.py` | Word-boundary matching | Phase C canonical |
| `domain_model_v73.py` | Domain model tipizzato | Phase C canonical |
| `_gen_record_links.py` | ⚠️ DEPRECATED linker record | 62 (DELETE), 97 (hub), 122 (anno decorazione), 200 (substring) |
| `_gen_event_links.py` | ⚠️ DEPRECATED linker eventi | 337 (substring bidirezionale), 358 (skip totale) |
| `_check_keys.py` | Check API keys | ✅ Già corretto (no .env, solo boolean) |
| `_find_best_candidates.py` | Trova candidati | ✅ Già corretto (no LIKE cognome) |
| `_clean_bad_links.py` | ⚠️ DEPRECATED cleanup | 100 (DELETE), 112 (DELETE fonti) |
| `_fix_gaiaschi_db.py` | ⚠️ DEPRECATED correzione | 39 (UPDATE diretto) |
| `linking/kill_switch.py` | Freeze legacy script | ✅ Tutti 13 job disabilitati |

---

## 2. Problema A — Estrazione PERSON incompleta

### Root cause

`@/unified_orchestrator_v7.py:615`:
```python
if table not in ("internati", "caduti_albooro", "decorati_nastroazzurro", "caduti_cwgc"):
    continue
```

**`caduti_ministero` è escluso** — 162.646 record non vengono mai processati.

### Mappatura campi — solo `internati`

`@/unified_orchestrator_v7.py:576-590`:
```python
PERSON_CLAIM_FIELDS = {
    "sorte": "fate",
    "luogo_internamento": "internment_place",
    "residenza": "residence",
    "data": "date_note",
    "grado": "rank",
    "matricola": "military_id",
    "luogo_nascita": "birth_place",
    "data_nascita": "birth_date",
    "luogo_cattura": "capture_place",
    "data_cattura": "capture_date",
    "arbeitskommando": "work_command",
    "mansione": "assignment",
    "reparto": "military_unit",
}
```

Questi 13 campi corrispondono **esclusivamente** ai nomi colonna di `internati`. Le altre 4 tabelle hanno nomi campo diversi:

### Campi non mappati per tabella

**`caduti_albooro`** (342.555 record):
| Campo DB | Predicate atteso | Stato |
|----------|-----------------|-------|
| `nominativo` | identity label (non claim) | non mappato |
| `paternita` | `paternity` | non mappato |
| `classe` | `draft_class_year` | non mappato |
| `comune_attuale` | `current_municipality` | non mappato |
| `grado` | `rank` | ✅ mappato |
| `reparto` | `military_unit` | ✅ mappato |
| `anno_morte` | `death_year` | non mappato |
| `luogo_morte` | `death_place` | ⚠️ narrato come `military_unit` (bug semantico CATENA) |
| `causa_morte` | `death_cause` | non mappato |

**`decorati_nastroazzurro`** (279.832 record):
| Campo DB | Predicate atteso | Stato |
|----------|-----------------|-------|
| `anno_decorazione` | `decoration_year` | non mappato |
| `tipo_decorazione` | `decoration_type` | non mappato |
| `arma` | `military_branch` (non `military_unit`) | non mappato |

**`caduti_cwgc`** (506.446 record):
| Campo DB | Predicate atteso | Stato |
|----------|-----------------|-------|
| `rank` | `rank` | non mappato (nome campo inglese) |
| `regiment` | `military_unit` | non mappato |
| `service_number` | `military_id` | non mappato |
| `data_morte` | `death_date` | non mappato |
| `eta` | `age_at_death` | non mappato |
| `cimitero` | `burial_place` | non mappato |
| `paese_cimitero` | `burial_country` | non mappato |
| `guerra` | temporal_scope (non claim) | non mappato |

**`caduti_ministero`** (162.646 record):
| Campo DB | Predicate atteso | Stato |
|----------|-----------------|-------|
| `data_nascita` | `birth_date` | non mappato |
| `data_decesso` | `death_date` | non mappato |
| `provincia_nascita` | `birth_province` | non mappato |
| `comune_nascita` | `birth_place` | non mappato |
| `nazione_decesso` | `death_country` | non mappato |
| `luogo_sepoltura` | `burial_place` | non mappato |
| `paternita` | `paternity` | non mappato |
| `maternita` | `maternity` | non mappato |

### Provenance fields — solo `internati`

`@/unified_orchestrator_v7.py:593-597`:
```python
PROVENANCE_FIELDS = {
    "lettera": "archive_letter",
    "file_pdf": "source_document",
    "pagina": "source_page",
}
```

Altre tabelle hanno campi provenance diversi non estratti:
- `caduti_albooro`: `detail_url`, `volume_name`
- `caduti_cwgc`: `cwgc_id`, `memorial`, `grave_ref`
- `caduti_ministero`: `scheda_url`, `codice_volume`, `pagina`, `sub`
- `decorati_nastroazzurro`: `source_id`

### Impatto quantificato (test su 20 nomi)

| Caso | Tabella | Campi valorizzati | Claim estratti | Claim attesi |
|------|---------|-------------------|----------------|--------------|
| GIACOLLO COSIMO | decorati_nastroazzurro | 8 | 0 | 3 |
| MURNANE HUGH | caduti_cwgc | 11 | 0 | 7 |
| BADELLINO GIACINTO | decorati_nastroazzurro | 8 | 0 | 3 |
| BARBARINI ANGELO DI PIETRO | caduti_ministero | 10 | 0 | 8 |
| WENSING THEODOOR | caduti_cwgc | 11 | 0 | 7 |
| BOVERI GIUSEPPE DI GIOVANNI | caduti_ministero | 10 | 0 | 8 |

---

## 3. Problema B — Identity resolver permissivo

### Root cause: cluster ID basato su discriminants, non su valori

`@/v7_identity_model.py:458-465`:
```python
def _make_cluster_id(self, cognome, nome, obs):
    discriminant_str = ""
    for f in ["anno_nascita", "luogo_nascita", "paternita", "reparto", "anno_morte"]:
        v = str(obs.get(f, "")).strip()
        if v and v != "-":
            discriminant_str += f"|{f}={v}"
    raw = f"person|{cognome}|{nome}{discriminant_str}"
    return f"cluster_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
```

**Problema**: due record con stesso cognome, stesso nome, stessi campi discriminant (es. stesso `reparto`) ma **diversi valori** per quei campi (es. diversa `data_morte`, diversa `causa_morte`) vengono fusi nello stesso cluster se i campi in conflitto non sono nel subset `["anno_nascita", "luogo_nascita", "paternita", "reparto", "anno_morte"]`.

### Caso NAVA Nino — fusione di ≥3 record omonimi

I record di NAVA Nino provengono da `internati` con dati incompatibili:
- Record 1: morte 1 settembre 1944, peritonite, Sandbostel
- Record 2: morte ottobre 1944, tubercolosi, Blumental (Brema)
- Record 3: ulteriori dati

Il `_make_cluster_id` usa `anno_morte` come discriminant. Se i record hanno stesso `anno_morte` (1944), finiscono nello stesso cluster. Il `conflicting_fields` viene popolato ma `is_ambiguous` restituisce `True` solo se `len(conflicting_fields) > 0`. Tuttavia il resolver:

`@/v7_identity_model.py:396-402`:
```python
if len(candidate_clusters) == 1:
    cluster = candidate_clusters[0]
    if self._origin_record_id:
        return "ANCHORED_RECORD", cluster, []
    if cluster.has_discriminants and not cluster.is_ambiguous:
        return "RESOLVED_IDENTITY", cluster, []
    return "PARTIAL_IDENTITY", cluster, []
```

**Se il cluster ha `has_discriminants=True` e `is_ambiguous=False`** (perché i campi in conflitto non sono nei `DISCRIMINANT_FIELDS`), viene classificato come `RESOLVED_IDENTITY` anche se contiene record con dati incompatibili.

### Missing: conflitto intra-cluster non gestito

`@/v7_identity_model.py:85-87`:
```python
@property
def is_ambiguous(self) -> bool:
    return len(self.conflicting_fields) > 0
```

Ma `conflicting_fields` viene popolato solo se lo stesso campo ha valori diverse tra record nello stesso cluster. Il problema è che `add_record()` confronta solo i `DISCRIMINANT_FIELDS` (11 campi), non tutti i campi biografici. Se due record hanno stessa `data_nascita` ma diversa `causa_morte`, e `causa_morte` è nei `DISCRIMINANT_FIELDS`, allora viene rilevato. Ma se il conflitto è su un campo non in `DISCRIMINANT_FIELDS`, non viene rilevato.

### Missing: barriera temporale WWI/WWII non applicata nel resolver

Il `barriers_v73.py` esiste ma **non è integrato** nel `_stage_resolve()` dell'orchestratore. Il resolver `v7_identity_model.py` non chiama `barriers_v73.py`. Due record WWI e WWII con stesso nome finiscono nello stesso cluster se i discriminant coincidono.

### Missing: `nominativo` split con `split()[0]`

`@/v7_identity_model.py:341-343`:
```python
if obs_nominativo:
    parts = obs_nominativo.split(None, 1)
    obs_cognome = parts[0].upper() if parts else ""
    obs_nome = parts[1].upper() if len(parts) > 1 else ""
```

Questo assume che la prima parola sia sempre il cognome. Per `caduti_albooro`, `nominativo` può essere "BOVERI GIUSEPPE DI GIOVANNI" → cognome="BOVERI", nome="GIUSEPPE DI GIOVANNI" (corretto), ma anche "DI PIETRO ANGELO" → cognome="DI", nome="PIETRO ANGELO" (errato).

---

## 4. Problema C — Claim count e source count semanticamente errati

### Root cause: `_compute_semantic_counts` conta observation, non fatti unici

`@/unified_orchestrator_v7.py:1052-1103`:
```python
def _compute_semantic_counts(self, ctx):
    # ...
    for obs in ctx.observations:
        if obs.provider == "local_db" and obs.classification == "SOURCE_CANDIDATE":
            person_confirmed += 1
        # ...
    person_claims = getattr(ctx, '_person_claims', [])
    claims_accepted = len([c for c in person_claims if c.status in ("ASSERTED", "ACCEPTED", "VERIFIED")])
```

**Problemi**:
1. `person_confirmed` conta observation (record DB), non fonti distinte
2. `claims_accepted` conta tutti i claim including provenance (archive_letter, source_document, source_page, source_text, data_quality_note)
3. Non c'è dedup per `subject_cluster_id + predicate + normalized_value`
4. Non ci sono metriche separate per fatti unici, evidenze, provenance, conflitti

### Esempio: NAVA Nino

| Metrica | Valore attuale | Valore corretto |
|---------|---------------|-----------------|
| `claims_accepted` | 43 | ~8 unique_person_facts |
| `person_sources_confirmed` | 15 | 3-4 unique_source_records |
| Provenance items | (inclusi nei 43) | ~6 (separati) |
| Conflict sets | (non conteggiati) | 2 (peritonite vs tubercolosi, Sandbostel vs Blumental) |

### Esempio: BARBATO Pasquale

| Metrica | Valore attuale | Valore corretto |
|---------|---------------|-----------------|
| `claims_accepted` | 8 | ~3 unique_person_facts |
| Provenance | (inclusi negli 8) | ~5 (Elenco_B.pdf, pagina 182, lettera B, ecc.) |

---

## 5. Problema D — Linker PERSON pericoloso

### Stato attuale: FROZEN ✅

`@/_gen_record_links.py:25`:
```python
assert_frozen(LegacyJob.RECORD_LINKS, "_gen_record_links.py is deprecated")
```

Tutti i job legacy sono frozen tramite `linking/kill_switch.py`. Il script non può essere eseguito senza `LEGACY_JOB_LEGACY_RECORD_LINKS=true`.

### Tuttavia, i link legacy esistono ancora nel DB

I link generati in precedenza sono ancora presenti in `record_links` e `event_links`. La quarantena V7.3 (`migrate_v73_quarantine.py`) ha aggiunto colonne `usable_as_evidence=0` e `status=CANDIDATE` ma non ha eliminato i link.

### Problemi strutturali nel codice (anche se frozen)

| Linea | Problema | Descrizione |
|-------|----------|-------------|
| 62 | `DELETE FROM record_links WHERE link_type='fonte_personale'` | Cancellazione globale all'avvio |
| 97 | `hub = ids[0]` | Star topology: primo soldato come hub |
| 99 | `stesso_evento_luogo` | Link tra soldati per (anno_morte, luogo_morte) |
| 122 | `stesso_anno_decorizione` | Link tra decorati per solo anno |
| 149 | `documento_evento` | Link caduto-documento per solo anno |
| 200 | `fonte_personale` conf=0.8 | Substring `COGNOME NOME` in haystack |
| 246 | `documento_evento` CWGC | Link CWGC-documento per solo anno |

### V3 replacement esistente

`_gen_record_links_v3.py` esiste già con:
- Richiesta secondo identificatore oltre nome
- Temporal veto
- --dry-run / --execute / --re-evaluate
- Rule version 3.0.0

---

## 6. Problema E — Linker EVENT permissivo

### Stato attuale: FROZEN ✅

`@/_gen_event_links.py:28`:
```python
assert_frozen(LegacyJob.EVENT_LINKS, "_gen_event_links.py is deprecated")
```

### Problemi strutturali

| Linea | Problema | Descrizione |
|-------|----------|-------------|
| 176-240 | Eventi WWII in `EVENTI_1GM` | `eventi_1gm` contiene eventi WWII (Achse, Cefalonia, Russia, Tobruk, Mauthausen, Cassino) |
| 337 | `alias.upper() in lm_up or lm_up in alias.upper()` | Substring bidirezionale senza word boundary |
| 358 | `if existing_caduti == 0: ... else: skip` | Skip totale se link esistenti |
| 155 | `"Lana"` come keyword | Col di Lana → matcha "Castellana", "Lana" generica |
| 129 | `"Campo"` come keyword | Prigionia → matcha qualunque "Campo" |

### V3 replacement esistente

`_gen_event_links_v3.py` esiste già con:
- Valutazione authority prima del keyword matching
- Out-of-period rejection
- --dry-run / --execute

---

## 7. Problema F — Errori semantici osservati

### F.1: `luogo_morte` narrato come `military_unit`

**Caso CATENA GIOVANNI**: `caduti_albooro.luogo_morte` = "127 Reparto Someggiato di Sanità"

Il campo `luogo_morte` non è mappato in `PERSON_CLAIM_FIELDS`. Tuttavia `reparto` è mappato come `military_unit`. Se il record ha `reparto` = "127 Reparto Someggiato di Sanità", viene correttamente mappato. Ma se il valore è in `luogo_morte`, non dovrebbe essere narrato come reparto.

**Root cause**: Il mapping è corretto per `reparto` → `military_unit`, ma il valore "127 Reparto Someggiato di Sanità" in `luogo_morte` non dovrebbe essere trattato come `military_unit`. Il problema è che il narratore non distingue semanticamente tra campi.

### F.2: Località trasformate in residenza

**Caso VINCIMENGA Giuseppe**: "Benevento" narrato come residenza.

Il campo `residenza` in `internati` contiene il valore. Ma negli elenchi CAR/IMI, la località associata al nominativo non è necessariamente la residenza — può essere il luogo di registrazione o associazione archivistica.

**Root cause**: Il mapping `residenza` → `residence` è semanticamente corretto per `internati`, ma il valore nel DB potrebbe non rappresentare la residenza reale. Il narratore non ha modo di distinguere.

### F.3: OCR corretto arbitrariamente

**Caso TAVERIO Alessandro**: "Pelluna" trasformato in "Belluna".

**Root cause**: Non c'è tracciamento delle correzioni OCR. Il `CorrectionLedger` esiste in `v7_identity_model.py` ma non è integrato nel pipeline. Il valore nel DB è già stato corretto senza traccia.

### F.4: `anno_decorazione` trattato come anno dell'azione

**Root cause**: `decorati_nastroazzurro.anno_decorazione` non è mappato. Se lo fosse come `decoration_year`, il narratore non deve dedurre che l'azione militare sia avvenuta in quell'anno.

### F.5: `arma` trattato come `military_unit`

**Root cause**: `decorati_nastroazzurro.arma` non è mappato. Se lo fosse, deve essere `military_branch` (es. "Fanteria", "Artiglieria"), non `military_unit` (es. "78° Reggimento Fanteria").

### F.6: Placeholder nell'output

**Caso PAVAN Vittorio**: "[dati dal DB]" nell'output.

**Root cause**: Il narratore AI genera testo con placeholder quando mancano dati. Il `OutputValidatorV7` non ha un check per placeholder pattern.

### F.7: Narratore aggiunge spiegazioni non nei claim

**Root cause**: Il narratore AI (Mistral) genera testo interpretativo. Il `NarrationValidator` valida struttura ma non contenuto semantico contro i claim.

---

## 8. Problema G — Utility che falsano i dati

### G.1: `_check_keys.py` — ✅ GIÀ CORRETTO

Il file attuale legge solo `os.environ`, non cerca file in Desktop/backup, stampa solo `PRESENT/MISSING/INVALID`. Nessuna correzione necessaria.

### G.2: `_find_best_candidates.py` — ✅ GIÀ CORRETTO

Il file attuale usa `JOIN collegamenti` e `JOIN relations`, non `LIKE '%cognome%'`. Nessuna correzione necessaria.

### G.3: `_fix_gaiaschi_db.py` — FROZEN ✅

Il file è frozen tramite kill_switch. Tuttavia, il codice ancora contiene:
- `UPDATE internati SET luogo_nascita = 'Nibbiano (Piacenza)' WHERE id = 22808` (linea 39)
- `UPDATE entita SET luogo = 'Nibbiano (Piacenza)'` (linea 50)

**Raccomandazione**: Sostituire con `data_corrections` table come specificato nel prompt.

### G.4: `_clean_bad_links.py` — FROZEN ✅

Il file è frozen. Tuttavia, il codice ancora contiene:
- `DELETE FROM collegamenti WHERE entita_id IN (...)` (linea 100)
- `DELETE FROM fonti_indice WHERE id IN (...)` (linea 112)

**Raccomandazione**: Sostituire con quarantena reversibile.

---

## 9. Schema OpenAI — bug `followup_question`

### Root cause

`@/narration_models.py:299-343`:
```python
NARRATION_DRAFT_SCHEMA = {
    "name": "narration_draft",
    "schema": {
        # ...
        "properties": {
            # ...
            "followup_question": {"type": ["string", "null"]},
        },
        "required": ["schema_version", "request_type", "blocks", "needs_followup"],
        # ⚠️ followup_question NON in required
        "additionalProperties": False,
    },
    "strict": True,
}
```

OpenAI strict mode richiede che **tutte** le proprietà in `properties` siano anche in `required`. `followup_question` è in `properties` ma non in `required`.

### Fix

Aggiungere `"followup_question"` a `required`:
```python
"required": ["schema_version", "request_type", "blocks", "needs_followup", "followup_question"],
```

---

## 10. Circuit breaker provider AI

### Stato attuale

Il narrator prova OpenAI → Anthropic → Mistral per ogni persona. Se OpenAI fallisce (schema error) e Anthropic fallisce (401), spreca 2 API call per ogni persona.

### Fix richiesto

1. Marcare provider come non disponibile per il resto del run dopo primo fallimento
2. Non ripetere chiamate sicuramente fallimentari
3. Implementare health check / circuit breaker

---

## 11. Metriche attuali vs attese

### Metriche attuali (da `_compute_semantic_counts`)

```python
{
    "web_candidates_seen": int,      # observation SEARCH_RESULT
    "person_sources_confirmed": int, # observation SOURCE_CANDIDATE local_db
    "person_sources_probable": int,  # observation SOURCE_CANDIDATE non-local
    "person_sources_ambiguous": int, # observation SURNAME_ONLY_NON_CANDIDATE
    "person_candidates_rejected": int, # observation REJECTED + rejected_homonyms
    "context_sources": int,          # observation CONTEXT
    "claims_accepted": int,          # claim count (includes provenance)
    "claims_rejected": int,          # rejected claims
}
```

### Metriche attese (per invarianti)

```python
{
    "queries_total": int,
    "queries_with_candidate_records": int,
    "resolved_identities": int,
    "partial_identities": int,
    "ambiguous_identities": int,
    "no_match": int,
    "unique_person_facts": int,        # dedup per cluster+predicate+value
    "supporting_evidence_records": int, # record che attestano lo stesso fatto
    "unique_source_records": int,       # record distinti
    "provenance_items": int,            # lettera, PDF, pagina (separati)
    "context_facts": int,
    "conflicted_facts": int,
    "rejected_observations": int,
    "candidate_clusters": int,
    "facts_with_provenance": int,
    "conflict_sets": int,
    "unsupported_inferences_blocked": int,
    "legacy_links_quarantined": int,
    "cross_war_links_blocked": int,
    "deterministic_fallbacks": int,
    "ai_provider_failures_by_reason": Dict[str, int],
}
```

---

## 12. Roadmap implementativa

### Priorità P0 (blocking)

| Task | File | Sforzo | Impatto |
|------|------|--------|---------|
| Aggiungere `caduti_ministero` al filtro | `unified_orchestrator_v7.py:615` | 1 riga | +162K record |
| Creare `PERSON_SOURCE_SCHEMAS` registro | nuovo modulo | ~200 righe | Mapping completo 5 tabelle |
| Fix schema OpenAI `followup_question` | `narration_models.py:339` | 1 riga | -1 API fail/caso |
| Circuit breaker provider AI | `v7_narrator.py` | ~50 righe | -2 API fail/caso |

### Priorità P1 (high)

| Task | File | Sforzo | Impatto |
|------|------|--------|---------|
| Rifare cluster ID con conflitti intra-cluster | `v7_identity_model.py:458` | ~80 righe | No fusione omonimi |
| Integrare `barriers_v73.py` nel resolver | `unified_orchestrator_v7.py:173` | ~30 righe | No WWI/WWII contamination |
| Separare fatti/evidenze/provenance | `unified_orchestrator_v7.py:1052` | ~100 righe | Metriche corrette |
| Narratore evidence-locked | `v7_narrator.py` | ~80 righe | No invenzioni |
| Validazione post-gen placeholder | `v7_narrator.py` | ~30 righe | No placeholder output |
| Split `nominativo` conservativo | `v7_identity_model.py:341` | ~40 righe | No cognomi composti errati |

### Priorità P2 (medium)

| Task | File | Sforzo | Impatto |
|------|------|--------|---------|
| `data_corrections` table | nuovo modulo + migrazione | ~150 righe | Override tracciato |
| Quarantena link legacy (audit) | script migrazione | ~100 righe | Link legacy reversibili |
| Parser layout-aware elenchi CAR/IMI | nuovo modulo | ~300 righe | No associazioni errate |

### Test richiesti

| Suite | Casi | File |
|-------|------|------|
| Unit test mapping 5 tabelle | 25+ | `test_person_source_schemas.py` |
| Unit test identity/conflict | 15+ | `test_identity_resolver_v73.py` |
| Unit test link scope | 10+ | `test_link_scope_v73.py` |
| Regression benchmark 20 nomi | 20 | `test_benchmark_20.py` |
| Regression EVENT | 6+ | estensione `test_v73_phase_f_real.py` |
| Test narrativa | 10+ | `test_narration_evidence_locked.py` |

---

## 13. Rischi residui

1. **Record legittimamente poveri**: molti record in `decorati_nastroazzurro` hanno solo cognome, nome, anno decorazione e arma. La narrativa sarà necessariamente scarna. Non è un bug.
2. **Omonimie reali**: alcuni nomi sono comuni (es. "ROSSI Mario"). Il resolver deve produrre `AMBIGUOUS_IDENTITY` e il narratore deve rispettarlo.
3. **Dati OCR rumorosi**: i valori grezzi possono contenere errori OCR. Il sistema deve preservare `raw_value` e applicare `normalized_value` solo con motivo tracciato.
4. **Schema DB in evoluzione**: le tabelle possono avere colonne aggiunte o rinominate. Il `PERSON_SOURCE_SCHEMAS` deve essere validato con `PRAGMA table_info` all'avvio.

---

## 14. Confronto pre/post atteso

| Metrica | Pre-fix | Post-fix |
|---------|---------|----------|
| Claim estratti da 5 tabelle | solo `internati` | tutte 5 |
| Record narrabili | ~20K (1.6%) | ~1.3M (potenziale) |
| Fusione omonimi | sì (NAVA) | no (cluster separati) |
| WWI/WWII contamination | possibile | bloccata |
| Provenance come claim | sì | separata |
| Placeholder nell'output | sì | bloccati |
| API fail per caso | 2 (OpenAI+Anthropic) | 0 (circuit breaker) |
| Metriche | observation count | fact/evidence/provenance separate |
