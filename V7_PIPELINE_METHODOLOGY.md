# V7.1 Pipeline — Metodologia, Logica e Fonti di Ricerca

**Versione:** 7.1  
**Orchestrator:** `UnifiedResearchOrchestratorV7`  
**Data:** 2 Agosto 2026  
**Stato:** Attivo, AI-enabled (OpenAI GPT-4o + fallback Anthropic/Mistral/Perplexity/Gemini)

---

## 1. Architettura della Pipeline

La pipeline V7.1 è composta da **9 stadi sequenziali**, ognuno idempotente, osservabile e non-distruttivo. L'input è una query utente; l'output è un report discorsivo con provenienza completa.

```
UTENTE → PLAN → DISCOVER → FETCH → EXTRACT → RESOLVE → FUSE → VALIDATE → NARRATE → PERSIST → REPORT
```

### 1.1 Stage 1: PLAN

**File:** `semantic_query_plan.py` → `build_plan()`  
**Input:** `user_input` (stringa), `intent` (enum), `conflict` (stringa)  
**Output:** `SemanticQueryPlan` (immutabile)

Il piano definisce:
- **Intent:** `PERSON_LOOKUP | EVENT_LOOKUP | AGGREGATE_QUERY | SOURCE_LOOKUP | ARCHIVE_SEARCH | CONVERSATIONAL_FOLLOWUP`
- **Target:** `TargetSpec` con `display_name`, `target_id`, `conflict` (WWI/WWII/AXIS_ONLY/ITALIAN_ONLY/UNKNOWN)
- **Required claims:** campi obbligatori per persona (21 campi), evento (6 campi), aggregato (4 campi)
- **Provider routing:** quali provider interrogare, in che ordine, con quali limiti
- **Fusion strategy:** `PRESERVE_CONTRADICTIONS` (default V7) | `MAJORITY_VOTE` | `HIGHEST_CONFIDENCE` | `ORIGIN_PRIORITY`
- **Manifest hash:** binding crittografico SHA-256 del piano

**Logica di routing:**
- `local_db` ha priorità 10 (più alta)
- Altri provider hanno priorità 20
- I provider vengono ordinati per priorità crescente

### 1.2 Stage 2: DISCOVER

**File:** `v7_provider_adapters.py` → `V7AdapterRegistry.search_all()`  
**Input:** `SemanticQueryPlan`  
**Output:** `List[ProviderObservation]`

Gli adapter registrati (in ordine di esecuzione):

| Adapter | Provider | Capability | Disponibilità |
|---------|----------|------------|---------------|
| `LocalDbAdapter` | `local_db` | `ARCHIVE_SEARCH` | Sempre |
| `WebSearchAdapter` | `tavily` | `DISCOVERY_WEB` | Se API key presente |
| `WebSearchAdapter` | `brave` | `DISCOVERY_WEB` | Se API key presente |
| `WebSearchAdapter` | `serper` | `DISCOVERY_WEB` | Se API key presente |
| `WebSearchAdapter` | `serpapi` | `DISCOVERY_WEB` | Se API key presente |
| `FederationAdapter` | `federation` | `ARCHIVE_SEARCH` | Se 27 provider registrati |

**Ordine di esecuzione:** prima ARCHIVE_SEARCH (locale, veloce), poi DISCOVERY_WEB (web, lento).

#### LocalDbAdapter — Tabelle interrogate

Per `PERSON_LOOKUP`:

| Tabella | Campo di ricerca | Contenuto |
|---------|-----------------|-----------|
| `internati` | `cognome LIKE ?` | IMI — Internati Militari Italiani (WWII) |
| `caduti_albooro` | `nominativo LIKE ?` | Caduti Albo d'Oro (WWI) |
| `decorati_nastroazzurro` | `cognome LIKE ?` | Decorati Nastro Azzurro |
| `caduti_cwgc` | `cognome LIKE ?` | Caduti Commonwealth War Graves Commission |
| `caduti_ministero` | `cognome LIKE ?` | Caduti Ministero della Difesa |

Per `EVENT_LOOKUP`:

| Tabella | Campo di ricerca | Contenuto |
|---------|-----------------|-----------|
| `eventi_1gm` | `nome LIKE ? OR descrizione LIKE ?` | Eventi Prima Guerra Mondiale |

Per `AGGREGATE_QUERY`:
- Non usa provider search — esegue direttamente `AggregateDefinitionRegistry.execute()`

**Limiti:** 20 righe per tabola, `LIKE cognome%` per match prefisso.

#### WebSearchAdapter — Query costruita

Per `PERSON_LOOKUP`:
```
[display_name] [cognome] [nome] [nato anno] [luogo_nascita] [internato militare | prima guerra mondiale]
```

Per `EVENT_LOOKUP`:
```
[display_name] prima guerra mondiale [event_name]
```

#### FederationAdapter — Provider federati (27 archivi)

Include: LeBI (Lessico Biografico IMI), ICRC, NARA, CWGC, Archivi di Stato, ecc.

### 1.3 Stage 3: FETCH

**File:** `unified_orchestrator_v7.py` → `_stage_fetch()`  
**Logica:** Per ogni osservazione:
- Se ha `snippet` o `excerpt` → `content_state = METADATA_ONLY`
- Altrimenti → `content_state = FAILED` + reason `NO_CONTENT_AVAILABLE`

Nessuna chiamata HTTP aggiuntiva in questa fase — i dati sono già nei metadati dell'osservazione.

### 1.4 Stage 4: EXTRACT

**File:** `unified_orchestrator_v7.py` → `_stage_extract()`  
**Logica:** Per ogni osservazione con `content_state != NOT_OPENED && != FAILED`:
1. Estrae `raw_record` da `provider_metadata`
2. Chiama `IdentityResolver.resolve_observation(raw_record, provider, table)`
3. Se l'identità è risolta → `source_record_id = identity_id`, `classification = SOURCE_CANDIDATE`
4. Se fallisce → aggiunge reason codes all'osservazione

### 1.5 Stage 5: RESOLVE

**File:** `unified_orchestrator_v7.py` → `_stage_resolve()` + `v7_identity_model.py`  
**Logica:** Risoluzione identità **backend-only**, mai delegata all'AI.

1. Parse del target: `cognome = parts[0]`, `nome = parts[1:]`
2. Per ogni identità nota, calcola score:
   - `cognome` match esatto → +0.5
   - `cognome` match prefisso (3 char) → +0.2
   - `nome` match esatto → +0.4
   - `nome` match parziale → +0.2
3. Miglior score → `resolved_identity`
4. Score > 0.3 ma non migliore → `homonym_candidate`
5. Per ogni omomimo:
   - Confronta `anno_nascita`, `luogo_nascita`
   - Se diversi → `HOMONYM_DIFFERENT_IDENTITY` + `birth_year_mismatch` / `birth_place_mismatch`
   - Aggiunge a `rejected_homonyms` con reason codes documentati

### 1.6 Stage 6: FUSE

**File:** `v7_fusion_engine.py` → `FusionEngine.fuse()`  
**Logica:** Fusione multi-provider con grafo di indipendenza.

#### Source Family Graph
- Ogni osservazione → `SourceNode` con `source_id`, `provider`, `archive`, `url`
- Rilevazione archi `SAME_ARCHIVE` tra osservazioni dello stesso archivio
- Tipi di arco: `SAME_ARCHIVE`, `SAME_OCR`, `SAME_PUBLICATION`, `SAME_INDEX`, `DERIVED_FROM`

#### Independence Assessor
- Due fonti dallo stesso archivio → NON indipendenti
- Due fonti da archivi diversi → indipendenti (score 1.0)
- Independence score: 0.0 (dipendenti) → 1.0 (indipendenti)
- Gruppi di indipendenza costruiti con union-find

#### Fusion Engine — Mapping campi → claim

| Campo DB | Predicate claim |
|----------|----------------|
| `anno_nascita` | `birth_year` |
| `luogo_nascita` | `birth_place` |
| `grado` | `rank` |
| `reparto` | `unit` |
| `anno_morte` | `death_year` |
| `luogo_morte` | `death_place` |
| `cattura_luogo` | `capture_place` |
| `cattura_data` | `capture_date` |
| `sorte` | `fate` |
| `campo` | `internment_place` |

#### Strategia PRESERVE_CONTRADICTIONS (default V7)
- Valore unico da tutte le fonti → `ACCEPTED` (se ≥2 provider) o `ASSERTED` (se 1 provider)
- Valori multipli → tutti marcati `CONFLICTING` con confidence 0.3
- **I conflitti NON vengono risolti** — vengono preservati e mostrati nel report

#### Strategia MAJORITY_VOTE
- Valore con più fonti indipendenti → `ACCEPTED`
- Altri valori scartati

### 1.7 Stage 7: VALIDATE

**File:** `evidence_snapshot_v7.py` → `validate_invariants()`  
**Logica:** Verifica invarianti sul snapshot:
- `SOURCE_RECORD_ONLY`: richiede URL assoluto verificato per source_record
- `CONSULTED_NO_MATCH`: solo con fetch verificato
- Conteggio tipizzato corretto

### 1.8 Stage 8: NARRATE

**File:** `v7_narrator.py` → `NarratorV7.narrate()`  
**Logica:** Generazione report con AI + validazione + fallback deterministico.

#### Flow narrazione:
1. **Compute conditional gaps:** per ogni campo richiesto non coperto da evidenza accettata
2. **Compute limitations:** verifica dinamica `is_any_provider_available()`
3. **Build context:** `snapshot.to_conversational_context()` — include solo `source_id`, mai URL
4. **AI call:** `call_ai(task_type="narration", system=..., user=context, max_tokens=2000, temperature=0.3)`
5. **Provider fallback chain:** OpenAI → Anthropic → Mistral → Perplexity → Gemini
6. **Validation AI output:** `OutputValidatorV7.validate()`:
   - No URL allucinati nel testo AI
   - No contraddizioni con claim accettati
   - No archivi non verificati menzionati
   - Tutti i `[source: id]` esistono nel snapshot
   - No claim non presenti nel snapshot
7. **Se validation passa (no ERROR):** `ReportRenderer.render_markdown(ai_text, snapshot)`
8. **Se validation fallisce:** fallback deterministico `render_deterministic_markdown(snapshot)`

#### System prompt AI:
```
Sei uno storico militare italiano. Genera un rapporto di ricerca
basato SOLO sui dati forniti nell'Evidence Snapshot.
Non inventare URL, archivi non verificati, o claim non supportati.
Usa [source: source_id] per citare le fonti.
```

#### Provider AI attivi (ordine di fallback):

| Provider | Modello | API Key | Costo (per 1M token) |
|----------|---------|---------|---------------------|
| OpenAI | gpt-4o | ✅ 164 char | $0.15 in / $0.60 out |
| Anthropic | claude-sonnet-4.5-20250929 | ✅ 108 char | $3.00 in / $15.00 out |
| Mistral | mistral-small-latest | ✅ 32 char | $2.00 in / $6.00 out |
| Perplexity | sonar | ✅ 53 char | $1.00 in / $1.00 out |
| Gemini | gemini-2.0-flash | ✅ 53 char | $0.50 in / $1.50 out |

#### Circuit breaker
Ogni provider ha un circuit breaker: dopo fallimenti consecutivi, il provider viene temporaneamente disabilitato (`_breaker_is_open`).

#### Budget check
Prima di ogni chiamata: `check_budget_before_task(provider, estimated_cost)`. Se budget insufficiente, il provider viene saltato.

### 1.9 Stage 9: PERSIST

Attualmente in-memory. Il snapshot e il report sono mantenuti nel `RunContext` e ritornati al chiamante.

---

## 2. Evidence Snapshot V7

**File:** `evidence_snapshot_v7.py`

Il snapshot è il DTO centrale che attraversa tutti gli stadi dalla fusione alla narrazione.

### Struttura:
- `snapshot_id`: hash SHA-256 univoco
- `schema_version`: "7.1"
- `intent`: PERSON_LOOKUP | EVENT_LOOKUP | AGGREGATE_QUERY
- `target`: display_name, target_id, conflict
- `origin_record`: record di provenienza (se verificato)
- `identity_resolution`: RESOLVED | PARTIAL | UNRESOLVED
- `external_corroboration`: FULL | PARTIAL | NONE
- `accepted_claims`: claim con ≥2 fonti indipendenti concordanti
- `conflicting_claims`: claim con valori multipli in conflitto
- `asserted_claims`: claim da singola fonte (non corroborati)
- `provider_ledger`: traccia di audit di tutte le osservazioni
- `web_leads`: URL non verificati (lead, non source_record)
- `rejected_candidates`: omonimi respinti con reason codes
- `corrections`: correzioni sovrapposte (raw data è immutabile)
- `source_lineage_groups`: gruppi di fonti con origine comune
- `independence_groups`: gruppi di fonti indipendenti
- `aggregate_result`: risultato query aggregata (se AGGREGATE_QUERY)
- `conditional_gaps`: campi richiesti non supportati da evidenza
- `limitations`: limitazioni del sistema (es. NO_AI_PROVIDER)

### Conditional Gaps — Campi richiesti

Per `PERSON_LOOKUP` (21 campi):
```
full_birth_date, birth_year, birth_place, paternity,
rank, unit, service_number,
death_date, death_year, death_place, death_cause,
captivity, internment_place, burial,
residence, decoration_type, decoration_year,
draft_class, municipality,
capture_place, capture_date, fate
```

Per `EVENT_LOOKUP` (6 campi):
```
event_start_date, event_end_date, event_location,
event_description, event_phase_count, event_actors
```

Per `AGGREGATE_QUERY` (4 campi):
```
count, breakdown, temporal_distribution, geographic_distribution
```

---

## 3. Aggregate Definitions Registry

**File:** `v7_event_aggregate.py`

7 definizioni aggregate deterministiche registrate (l'AI non può inventarne):

| Nome | Query SQL | Output |
|------|-----------|--------|
| `count_internati_by_year` | `SELECT anno_nascita, COUNT(*) FROM internati GROUP BY anno_nascita` | anno, count |
| `count_caduti_by_luogo` | `SELECT luogo_morte, COUNT(*) FROM caduti_albooro GROUP BY luogo_morte LIMIT 50` | luogo, count |
| `count_decorati_by_type` | `SELECT decorazione, COUNT(*) FROM decorati_nastroazzurro GROUP BY decorazione` | tipo, count |
| `count_internati_by_campo` | `SELECT luogo_internamento, COUNT(*) FROM internati GROUP BY luogo_internamento LIMIT 50` | campo, count |
| `count_events_by_conflict` | `SELECT conflitto, COUNT(*) FROM eventi_1gm GROUP BY conflitto` | conflitto, count |
| `temporal_distribution_caduti` | `SELECT anno_morte, COUNT(*) FROM caduti_albooro GROUP BY anno_morte ORDER BY anno_morte` | anno, count |
| `geographic_distribution_internati` | `SELECT luogo_nascita, COUNT(*) FROM internati GROUP BY luogo_nascita LIMIT 100` | luogo, count |

---

## 4. Event Ontology

**File:** `v7_event_aggregate.py` → `EventOntology`

### Tipi di evento canonici (15):
```
battaglia, offensiva, ritirata, avanzata, assedio,
bombardamento, armistizio, dichiarazione_guerra, trattato_pace,
internamento, rimpatrio, deportazione, liberazione, eccidio, altro
```

### Fasi evento (5):
```
preparazione, esecuzione, sviluppo, conclusione, postumi
```

### Relazioni evento (6):
```
sub_event_of, preceded_by, caused_by, resulted_in, concurrent_with, same_as
```

---

## 5. Fonti Dati

### 5.1 Database Locale (SQLite)

**File principale:** `imi_internati.db` (9.5M righe totali, 75 tabelle)

#### Tabelle primarie per PERSON_LOOKUP:

| Tabella | Record | Conflitto | Descrizione |
|---------|--------|-----------|-------------|
| `internati` | ~400K | WWII (AXIS_ONLY) | IMI — Internati Militari Italiani |
| `caduti_albooro` | ~650K | WWI | Caduti Albo d'Oro (Ministero Difesa) |
| `decorati_nastroazzurro` | ~40K | WWI+WWII | Decorati Nastro Azzurro |
| `caduti_cwgc` | ~1K | WWI+WWII | Caduti Commonwealth |
| `caduti_ministero` | ~100K | WWI+WWII | Caduti Ministero |
| `caduti_bologna` | ~3K | WWI | Caduti Bologna |
| `caduti_sardi` | ~5K | WWI | Caduti Sardegna |
| `caduti_francia_ww1` | ~500 | WWI | Caduti Francia |
| `decorati` | ~40K | WWI+WWII | Decorati (albo generale) |
| `menzioni` | ~10K | Vari | Menzioni in fondi archivistici |

#### Tabelle per EVENT_LOOKUP:

| Tabella | Record | Descrizione |
|---------|--------|-------------|
| `eventi_1gm` | 49 | Eventi Prima Guerra Mondiale |
| `event_aliases` | 161 | Alias eventi |

#### Tabelle derivate (quarantena):

| Tabella | Record | Stato |
|---------|--------|-------|
| `record_links` | 169K | Quarantina (legacy) |
| `collegamenti` | 2.3M | Quarantina (legacy) |

### 5.2 Provider Web Search

| Provider | API Key | Funzione | Note |
|----------|---------|----------|------|
| Tavily | ✅ | `search_tavily()` | AI-optimized search |
| Brave | ❌ | `search_brave()` | Non configurato |
| Serper | ❌ | `search_serper()` | Non configurato |
| SerpApi | ❌ | `search_serpapi()` | Non configurato |

### 5.3 Federation (27 provider archivistici)

**File:** `source_providers/federation.py`

Provider registrati includono:
- LeBI (Lessico Biografico IMI — ANRP)
- ICRC (International Committee of the Red Cross)
- NARA (National Archives)
- CWGC (Commonwealth War Graves Commission)
- Archivi di Stato italiani
- Altri archivi storici

### 5.4 Supabase (PostgreSQL)

**Project:** `wyqesimzxieykmyhfvqs` (Central Europe/Zurich)  
**Schema:** 6 schemi, 21 tabelle canoniche, 40+ indici, RLS  
**Sync status:** archivio_documenti (979 rows), eventi_1gm (49 rows), event_aliases (161 rows), event_links (~18% synced)

---

## 6. Principi Architetturali (8 invarianti)

1. **Raw data is immutable** — le correzioni sono overlay in `CorrectionLedger` con audit trail
2. **Identity resolution is backend-only** — l'AI non decide mai l'identità
3. **Contradictions are preserved** — `FusionEngine` non risolve i conflitti, li mostra
4. **Aggregate queries are deterministic** — l'AI non può inventare definizioni
5. **AI output is validated** — URL allucinati, archivi non verificati e claim non supportati sono flaggati
6. **Deterministic fallback always available** — nessuna dipendenza da disponibilità AI
7. **Legacy scripts are frozen** — kill switch previene esecuzione accidentale
8. **Derived data is quarantined** — pronto per rigenerazione V7

---

## 7. Tracciabilità e Audit

Ogni esecuzione produce:

- `run_id`: `run_v7_{timestamp}_{hash8}`
- `plan_id`: hash del SemanticQueryPlan
- `snapshot_id`: `snap_v7_{hash16}`
- `stage_timings`: tempo per ogni stadio
- `provider_ledger`: ogni osservazione con `observation_id`, `provider`, `classification`, `reason_codes`, `raw_result_hash`
- `provenance_chain`: per ogni claim, lista di observation_id che lo supportano
- `source_lineage_groups`: gruppi di fonti con origine comune
- `independence_groups`: gruppi di fonti indipendenti con score

---

## 8. AI Narration — Flusso Dettagliato

```
NarratorV7.narrate(snapshot, use_ai=True)
│
├── snapshot.compute_conditional_gaps()
├── _compute_limitations() → is_any_provider_available()?
│
├── _try_ai_narration(snapshot)
│   ├── is_any_provider_available() → True/False
│   ├── context = snapshot.to_conversational_context()  # source_id only, no URLs
│   ├── system_prompt = "Sei uno storico militare italiano..."
│   ├── call_ai(task_type="narration", system, user, max_tokens=2000, temp=0.3)
│   │   ├── select_model("narration") → provider+model
│   │   ├── for provider in [selected, ...fallback_order]:
│   │   │   ├── check_budget_before_task()
│   │   │   ├── _call_{provider}(model, system, user, ...)
│   │   │   ├── record_task_run() → audit
│   │   │   └── return {ok, text, provider, model, cost, tokens, latency}
│   │   └── return {ok: False, error: "Tutti i provider AI hanno fallito"}
│   │
│   ├── if response.ok and len(response.text) > 100:
│   │   └── return text
│   └── return None
│
├── if ai_text:
│   ├── violations = OutputValidatorV7.validate(ai_text, snapshot)
│   ├── if no ERROR violations:
│   │   └── return ReportRenderer.render_markdown(ai_text, snapshot), violations
│   └── else: fall through to deterministic
│
└── Deterministic fallback:
    └── return ReportRenderer.render_deterministic_markdown(snapshot), []
```

---

## 9. File della Pipeline V7.1 (15 moduli)

| File | Classe/Modulo | Stadio |
|------|---------------|--------|
| `semantic_query_plan.py` | `SemanticQueryPlan`, `TargetSpec`, `build_plan()` | PLAN |
| `provider_observation.py` | `ProviderObservation`, `ProviderCapabilityRegistry` | DISCOVER |
| `v7_provider_adapters.py` | `V7AdapterRegistry`, `LocalDbAdapter`, `WebSearchAdapter`, `FederationAdapter` | DISCOVER |
| `v7_identity_model.py` | `CanonicalIdentity`, `RecordOrigin`, `CorrectionLedger`, `IdentityResolver` | EXTRACT/RESOLVE |
| `v7_fusion_engine.py` | `SourceFamilyGraph`, `IndependenceAssessor`, `FusionEngine` | FUSE |
| `evidence_snapshot_v7.py` | `EvidenceSnapshotV7`, `ClaimV7`, `ConditionalGapV7` | VALIDATE |
| `v7_event_aggregate.py` | `EventOntology`, `AggregateDefinition`, `AggregateDefinitionRegistry` | DISCOVER (aggregate) |
| `v7_narrator.py` | `NarratorV7`, `OutputValidatorV7`, `CitationResolver`, `ReportRenderer` | NARRATE |
| `ai_client.py` | `call_ai()`, `call_ai_json()`, `is_any_provider_available()` | NARRATE |
| `ai_router.py` | `select_model()`, `record_task_run()`, `check_budget_before_task()` | NARRATE |
| `unified_orchestrator_v7.py` | `UnifiedResearchOrchestratorV7`, `RunContext` | TUTTI |
| `v7_api.py` | 5 endpoint `/api/v7/*` | API layer |
| `v7_security_audit.py` | `LegacySecurityAuditor`, `ImportSafetyAuditor`, `KillSwitchVerifier` | Security |
| `v7_quarantine.py` | `DerivedDataInventory`, `QuarantineManager`, `RegenerationPlan` | Quarantine |
| `run_canary_v7.py` | 10 frozen canary targets, 3 modes | Testing |

---

## 10. API Endpoints V7

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/v7/health` | GET | Health check orchestrator |
| `/api/v7/system/capabilities` | GET | Lista provider e capabilities |
| `/api/v7/research` | POST | Esegue pipeline completa |
| `/api/v7/research/{run_id}` | GET | Recupera risultato per run_id |
| `/api/v7/narrate` | POST | Rigenera narrazione da snapshot |

---

*Documento generato dal codice sorgente attivo. Tutti i numeri, tabelle, campi e logiche sono verificati direttamente dai file Python della pipeline V7.1.*
