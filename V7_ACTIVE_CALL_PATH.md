# V7_ACTIVE_CALL_PATH.md — Trace del Call Path Reale (Pre-V7)

**Data:** 2026-08-02
**Repository:** imi_extractor (Lettere dal Fronte / IMI Extractor)
**Branch attiva:** fix/provenance-linking-v2

---

## 1. Endpoint pubblici invocabili

### 1.1 Ricerca probatoria principale

| Endpoint | Modulo | Orchestratore | Versione |
|----------|--------|---------------|----------|
| `POST /api/research-protocol` | `app.py:2549` → `research_protocol.py` | `research_person()` | **V4** |
| `POST /api/chat/research` | `app.py:2586` → `chat_research.py` | `chat_research()` | **V4** |
| `POST /api/research-engine/search` | `research_engine_api.py:93` → `research_orchestrator.py` | `run_research()` | **Legacy (pre-V4)** |
| `POST /api/research-engine/plans/{id}/run` | `research_engine_api.py:73` → `research_orchestrator.py` | `run_cycle()` | **Legacy (pre-V4)** |

### 1.2 Report conversazionale

| Endpoint | Modulo | Provider | Versione |
|----------|--------|----------|----------|
| `POST /research/reports/{id}/conversations` | `report_conversation_api.py:86` → `report_conversation_provider_v6.py` | `ReportConversationProviderV6` | **V6** |
| `POST /research/conversations/{id}/messages` | `report_conversation_api.py:102` → `report_conversation_provider_v6.py` | `ReportConversationProviderV6` | **V6** |
| `GET /research/conversations/{id}` | `report_conversation_api.py:127` | `ReportConversationProviderV6` | **V6** |

### 1.3 Altri endpoint rilevanti

| Endpoint | Modulo | Note |
|----------|--------|------|
| `POST /api/chat` | `chat_api.py:48` → `ai_runtime.py` | Chat generale, no snapshot |
| `POST /api/rag/retrieve` | `rag_api.py` → `rag_pipeline.py` | RAG retrieval, separato |
| `GET /api/graph/entity/{table}/{id}` | `graph_api.py` | Graph provenance, separato |

---

## 2. Trace end-to-end: query persona (POST /api/research-protocol)

```
UserQuery (body JSON)
  → app.py:2569 from research_protocol import research_person
  → research_protocol.py: research_person(body, use_ai, persist)
    → [Fase 1] SearchInput parsing
      → name_parser_v4.parse_display_name()          ← V4 import
    → [Fase 2] Local DB search
      → person_finder.py (SQLite: internati, caduti_albooro, decorati)
    → [Fase 3] Federated web search
      → source_providers/federation.py → federated_search()
      → 27 provider (ICRC, LeBI, CWGC, NARA, etc.)
      → search_validator.py (per-name validation)
    → [Fase 4] Relevance filtering
      → relevance_gate_v4.classify_relevance_v4()    ← V4 import
      → filter_relevant_results_v4()
    → [Fase 5] AI normalization (optional)
      → ai_runtime.py → get_adapter() → adapter.generate()
      → LM Studio / Mistral (Qwen2.5-0.5B)
    → [Fase 6] Snapshot construction
      → evidence_snapshot_v4.build_snapshot_v4_from_dossier()  ← V4 import
      → EvidenceSnapshotV4 (NOT V6!)
    → [Fase 7] Archival suggestions
      → archive_jurisdiction_registry.generate_archival_suggestions()  ← V4 import
    → [Fase 8] AI dossier generation
      → ai_output_validator.validate_ai_output()     ← V4 import
      → generate_deterministic_report()              ← V4 fallback
    → [Fase 9] Supabase persistence (optional)
      → claim_service / entity_resolution
  → Return dossier.to_dict()
```

**PROBLEMA 1:** La pipeline di ricerca probatoria usa `EvidenceSnapshotV4`, non V6. I moduli V6 (`evidence_snapshot_v6.py`, `multi_provider_fusion.py`, `provider_observation.py`) non sono nel call path.

**PROBLEMA 2:** `multi_provider_fusion.py` non è importato da nessun modulo runtime. È referenziato solo in `test_v6_master.py`.

**PROBLEMA 3:** `openai_responses_adapter.py` è importato solo da `report_conversation_provider_v6.py` come narratore, non per discovery.

---

## 3. Trace end-to-end: query conversazionale (POST /research/conversations/{id}/messages)

```
UserQuery (message + snapshot dict)
  → report_conversation_api.py:102 send_message()
  → report_conversation_provider_v6.py: send_message()
    → _try_provider()
      → [Provider 1] OpenAI
        → openai_responses_adapter.OpenAIResponsesAdapter()
        → adapter.generate_conversation(context, question, history)
          → client.responses.create(model="gpt-4o-mini", text.format=json_schema)
          → return OpenAIAdapterResult(report_json=...)
        → _render_and_validate(report_json, snapshot_dict, ...)
          → answer = report_json.get("answer", "")
          → _strip_markdown_json(answer)
          → validate_v6(content, snapshot_dict, ...)
            → ai_output_validator_v6.validate_v6()
              → [Check 1] Internal marker detection
              → [Check 2] Grounding validation (FACTUAL_PATTERNS vs claims)
              → [Check 3] Semantic validation
              → [Check 4] Conversation validation
          → if validation.responses_valid == False:
              → _deterministic_response()  ← FALLBACK
              → det.validation_details = {violations, ai_raw_answer, ...}
          → else:
              → ConversationMessageV6(validation_state="valid")
      → [Provider 2] Mistral / LM Studio
        → ai_runtime.get_adapter()
        → adapter.generate(system, user, ...)
        → json.loads(result.text) or {"answer": result.text}
        → _render_and_validate() (same flow as above)
      → [Fallback] Deterministic
        → _deterministic_response()
        → generate_deterministic_v6(snapshot_dict, question)
  → Return ConversationMessageV6
```

**PROBLEMA 4:** Il snapshot viene passato dal client (canary script), non costruito dall'orchestratore. Non c'è validazione che il snapshot corrisponda a una ricerca reale.

**PROBLEMA 5:** Il validatore `ai_output_validator_v6.py` tratta `claim_id` come token vietato nel testo renderizzato, ma lo fa anche nel JSON strutturato prima del rendering. Il check avviene su `content` (già renderizzato), non sul JSON interno.

---

## 4. Trace end-to-end: canary V6 (run_canary_v6.py)

```
run_canary_v6.py: main()
  → extract_internati(3)    ← SELECT * FROM internati LIMIT 3 (NON deterministico!)
  → extract_caduti_albooro(3)  ← SELECT * FROM caduti_albooro LIMIT 3
  → extract_decorati(3)     ← SELECT * FROM decorati_nastroazzurro LIMIT 3
  → extract_events(3)       ← SELECT * FROM eventi_1gm LIMIT 3
  → for each target:
    → build_person_snapshot(record, db_type)  ← COSTRUISCE SNAPSHOT MANUALMENTE
      → QueryManifest.for_person()
      → EvidenceSnapshotV6(
          origin.provenance = "UNVERIFIED",
          identity_resolution = "PARTIAL",  ← SEMPRE PARTIAL, nessun gate
          external_corroboration = "NONE",
          asserted_claims = [...],  ← DA RECORD DB, non da fusion
          accepted_claims = [],     ← SEMPRE VUOTO
          accepted_evidence = [],   ← SEMPRE VUOTO
        )
    → run_conversation(snapshot, questions)
      → POST /research/reports/{id}/conversations
      → POST /research/conversations/{id}/messages (×3)
```

**PROBLEMA 6:** Il canary V6 usa `LIMIT 3` senza `ORDER BY` → target non deterministici. I target cambiano ad ogni run.

**PROBLEMA 7:** I target V6 sono diversi dai target V5. Nessun confronto è possibile.

**PROBLEMA 8:** Lo snapshot è costruito manualmente dal canary, non dall'orchestratore. `accepted_claims` e `accepted_evidence` sono sempre vuoti. `identity_resolution` è sempre "PARTIAL" senza gate identitario.

**PROBLEMA 9:** Nessun provider di ricerca web viene chiamato. Nessuna fusione multi-provider. Nessun fetch di pagine. Nessun gate di target-binding.

---

## 5. Moduli V4/V5/V6 importati dal runtime

### 5.1 Moduli V4 attivi nel call path di ricerca

| Modulo | Importato da | Funzione |
|--------|-------------|----------|
| `evidence_snapshot_v4.py` | `research_protocol.py:23` | `build_snapshot_v4_from_dossier()` |
| `source_capability_registry.py` | `research_protocol.py:24` | `get_routing_matrix()` |
| `archive_jurisdiction_registry.py` | `research_protocol.py:25` | `generate_archival_suggestions()` |
| `relevance_gate_v4.py` | `research_protocol.py:26` | `classify_relevance_v4()` |
| `name_parser_v4.py` | `research_protocol.py:27` | `parse_display_name()` |
| `ai_output_validator.py` | `research_protocol.py:28` | `validate_ai_output()` |

### 5.2 Moduli V6 attivi nel call path conversazionale

| Modulo | Importato da | Funzione |
|--------|-------------|----------|
| `evidence_snapshot_v6.py` | `report_conversation_provider_v6.py` | `EvidenceSnapshotV6` |
| `ai_output_validator_v6.py` | `report_conversation_provider_v6.py` | `validate_v6()` |
| `openai_responses_adapter.py` | `report_conversation_provider_v6.py` | `OpenAIResponsesAdapter` |
| `ai_runtime.py` | `report_conversation_provider_v6.py` | `get_adapter()` |

### 5.3 Moduli V6 NON nel call path runtime

| Modulo | Referenziato da | Status |
|--------|----------------|--------|
| `multi_provider_fusion.py` | solo `test_v6_master.py` | **MAI importato da endpoint** |
| `provider_observation.py` | solo `multi_provider_fusion.py` | **MAI importato da endpoint** |
| `aggregate_query_resolver.py` | `run_canary_v6.py` | Solo canary, non endpoint |

### 5.4 Moduli legacy pre-V4

| Modulo | Importato da | Status |
|--------|-------------|--------|
| `research_orchestrator.py` | `research_engine_api.py` | Attivo su `/api/research-engine/*` |
| `claim_service.py` | `research_engine_api.py` | Attivo |
| `entity_resolution.py` | `research_engine_api.py` | Attivo |
| `archive_registry.py` | `research_engine_api.py` | Attivo |
| `ai_router.py` | `research_engine_api.py` | Attivo |

---

## 6. Punto di creazione del QueryManifest

- **Pipeline ricerca (V4):** `research_protocol.py` non crea un `QueryManifest` V6. Usa `SearchInput` dataclass.
- **Pipeline conversazionale (V6):** `run_canary_v6.py` crea `QueryManifest.for_person()` / `for_event()` / `for_aggregate()`, ma è il canary script, non l'endpoint.
- **Endpoint conversazionale:** Non crea QueryManifest. Riceve il snapshot già costruito dal client.

**Conclusione:** `QueryManifest` non esiste nel runtime dell'endpoint. È solo nel canary.

---

## 7. Punto di chiamata provider

### 7.1 Provider di ricerca (discovery)

| Provider | Modulo | Chiamato da | Status |
|----------|--------|------------|--------|
| Federated search (27 provider) | `source_providers/federation.py` | `research_protocol.py` | **Attivo su /api/research-protocol** |
| OpenAI Web Search | non implementato | — | **Non esiste** |
| Tavily | non implementato | — | **Non esiste** |

### 7.2 Provider narrativi (AI)

| Provider | Modulo | Chiamato da | Status |
|----------|--------|------------|--------|
| OpenAI Responses | `openai_responses_adapter.py` | `report_conversation_provider_v6.py` | **Attivo, solo narratore** |
| Mistral / LM Studio | `ai_runtime.py` | `report_conversation_provider_v6.py` | **Attivo, solo narratore** |
| Deterministic | `ai_output_validator_v6.py` | `report_conversation_provider_v6.py` | **Fallback** |

---

## 8. Punto di creazione del ProviderObservation

**Non esiste nel runtime.** `ProviderObservation` è definito in `provider_observation.py` ma è usato solo da `multi_provider_fusion.py`, che non è importato da nessun endpoint.

La pipeline V4 usa `relevance_gate_v4.classify_relevance_v4()` che produce `RelevanceResult`, non `ProviderObservation`.

---

## 9. Punto di apertura pagina / estrazione contenuto

- **Pipeline V4:** `research_protocol.py` chiama `federated_search()` che restituisce risultati con URL, ma l'apertura della pagina (fetch) avviene in `person_finder.py` o nello scraper service, non in un gate strutturato.
- **Pipeline V6:** Nessun fetch di pagine. Il snapshot è pre-costruito.

---

## 10. Punto di target-binding e identity gate

- **Pipeline V4:** `research_protocol.py` ha `apply_resolution_gate()` che usa `name_parser_v4` per confrontare nome/cognome/anno. Ma non c'è un gate identitario formale con stati `VALID/INVALID/NEEDS_REVIEW`.
- **Pipeline V6:** Nessun gate identitario. `identity_resolution` è hardcoded a "PARTIAL" nel canary.

---

## 11. Punto di accettazione/rifiuto claim

- **Pipeline V4:** `evidence_snapshot_v4.build_snapshot_v4_from_dossier()` costruisce `accepted_claims` dai risultati della ricerca. `ai_output_validator.validate_ai_output()` valida l'output AI.
- **Pipeline V6:** `multi_provider_fusion.py` ha la logica di fusione, ma **non è nel call path**. Nel canary, `asserted_claims` vengono dal record DB, `accepted_claims` è sempre vuoto.
- **multi_provider_fusion.py:296-298:** `"Agreement: mark as ACCEPTED"` — questa regola è nel codice ma non viene eseguita da nessun endpoint.

---

## 12. Punto di nascita dello snapshot

- **Pipeline V4:** `evidence_snapshot_v4.build_snapshot_v4_from_dossier()` → `EvidenceSnapshotV4`
- **Pipeline V6:** `run_canary_v6.py:build_person_snapshot()` → `EvidenceSnapshotV6` (manuale, nel canary)
- **Endpoint V6:** Non crea snapshot. Lo riceve dal client.

---

## 13. Punto di persistenza conversazione

- `report_conversation_provider_v6.py` usa SQLite per persistere conversazioni:
  - `create_conversation()` → INSERT in `conversations_v6` table
  - `send_message()` → INSERT in `conversation_messages_v6` table
  - `get_conversation()` → SELECT from both tables

---

## 14. Caso ABBATTISTA ATTILIO — analisi contaminazione

### 14.1 Record reale (caduti_albooro, id=2)

```json
{
  "id": 2,
  "nominativo": "ABBATTISTA ATTILIO",
  "paternita": "SALVATORE",
  "classe": "1896",
  "comune_attuale": "Fossacesia",
  "grado": "Sotto capo meccanico",
  "reparto": "RR. equipaggi",
  "anno_morte": "1916",
  "luogo_morte": "-",
  "causa_morte": "Affondamento Di Nave",
  "conflict": "WWI"
}
```

### 14.2 Fixture sintetica (_test_ai_raw.py)

```python
"asserted_claims": [
    {"predicate": "birth_year", "value_normalized": "1910"},       # REALE: classe 1896
    {"predicate": "birth_place", "value_normalized": "Torino"},     # REALE: Fossacesia
    {"predicate": "rank", "value_normalized": "soldato"},           # REALE: Sotto capo meccanico
    {"predicate": "internment_place", "value_normalized": "Campo 85"},  # REALE: RR. equipaggi, affondamento nave
]
```

### 14.3 Diagnosi

**Tutti i dati della fixture sono inventati.** ABBATTISTA ATTILIO è:
- Un caduto del **Albo d'Oro** (WWI), non un internato WWII
- Classe **1896**, non nato nel 1910
- Di **Fossacesia** (Chieti), non di Torino
- **Sotto capo meccanico** dei RR. equipaggi, non soldato
- Morto per **affondamento di nave** nel 1916, non internato nel Campo 85

La fixture `_test_ai_raw.py` usa il nome di una persona reale con dati completamente inventati. Questo è un **contaminazione di fixture sintetica con identità reale**.

### 14.4 Root cause

Il test `_test_ai_raw.py` è stato creato per debug della validazione V6, ma:
1. Usa il nome reale ABBATTISTA ATTILIO invece di SYNTHETIC_PERSON_A
2. Costruisce claim inventati (1910, Torino, soldato, Campo 85) che non corrispondono al record DB
3. Il validatore ha correttamente rifiutato le risposte AI che narravano questi dati inventati come fatti
4. Il "fix" proposto (promuovere asserted_claims a grounding) era sbagliato perché i dati sono falsi

---

## 15. Script legacy — analisi side-effect

### 15.1 _gen_record_links.py

```python
# Linea 31 (IMPORT TIME, dopo assert_frozen):
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")

# Linea 38-46 (IMPORT TIME):
conn.execute("""CREATE TABLE IF NOT EXISTS record_links (...)""")
conn.commit()
```

**PROBLEMA:** Anche con kill switch, l'import apre una connessione SQLite, imposta WAL mode e crea una tabella. Il `assert_frozen` previene l'esecuzione dello script come `__main__`, ma se il modulo viene importato (es. da un endpoint o da un altro script), le side-effect al top level vengono eseguite prima di qualsiasi check.

**Verifica:** `assert_frozen` è alla linea 28, ma `conn = sqlite3.connect(DB)` è alla linea 31. Se `assert_frozen` solleva `RuntimeError`, l'import fallisce e le side-effect non avvengono. **MA** se qualcuno imposta `LEGACY_JOB_LEGACY_RECORD_LINKS=true`, l'import procede e apre il DB.

### 15.2 _find_best_candidates.py

```python
# Linea 6-8 (IMPORT TIME, NESSUN kill switch):
from database import get_conn
conn = get_conn()
```

**PROBLEMA:** Nessun kill switch. Apre una connessione al DB all'import time. Se importato da qualsiasi modulo, esegue query.

### 15.3 _gen_event_links.py

```python
# Linea 28 (IMPORT TIME):
assert_frozen(LegacyJob.EVENT_LINKS, "_gen_event_links.py is deprecated")
```

**OK:** Kill switch presente. Se l'import fallisce per RuntimeError, nessuna side-effect.

### 15.4 _clean_bad_links.py

```python
# Linea 22 (IMPORT TIME):
assert_frozen(LegacyJob.CLEAN_BAD_LINKS, "_clean_bad_links.py is deprecated")
```

**OK:** Kill switch presente. Side-effect solo in `run()` function, non al top level.

---

## 16. Canary V5 vs V6 — confronto target

### V5 target (CANARY_V5_REAL_RESULTS.json)

| Tipo | Nome | ID | DB |
|------|------|----|----|
| internati | ALFORI Divino | 2433 | imi_internati |
| internati | L. NGELLA Maresc. Magg. | 14286 | imi_internati |
| internati | TURCONI Paolo | 21284 | imi_internati |
| caduti_albooro | ABATE MARIO ANTONIO | 1 | imi_internati |
| caduti_albooro | ABBATTISTA ATTILIO | 2 | imi_internati |
| caduti_albooro | ABBIUSO DOMENICO | 3 | imi_internati |
| decorati | A GIOVANNI | 1 | imi_internati |
| decorati | A RONCH GIOVANNI | 2 | imi_internati |
| decorati | A-PRATO SILVIO | 3 | imi_internati |
| evento | Battaglia di Caporetto | 16 | eventi_1gm |
| evento | Battaglie dell'Isonzo | 17 | eventi_1gm |
| evento | Battaglia del Carso | 18 | eventi_1gm |
| aggregato | IMI deceduti in Germania | — | — |
| aggregato | Decorati al Valor Militare WWI | — | — |
| aggregato | Caduti per affondamento di nave | — | — |

### V6 target (CANARY_V6_RESULTS.json)

| Tipo | Nome | ID | DB |
|------|------|----|----|
| internati | ALTA Antonio | ? | imi_internati |
| internati | AMEDEO Agostino | ? | imi_internati |
| internati | ARMUNISCO Vincenzo | ? | imi_internati |
| caduti_albooro | (diversi da V5) | ? | imi_internati |
| decorati | (diversi da V5) | ? | imi_internati |
| evento | (diversi da V5) | ? | eventi_1gm |
| aggregato | (stessi V5) | — | — |

**PROBLEMA:** 0 target sovrapposti tra V5 e V6 per persone ed eventi. Nessun confronto possibile.

---

## 17. Statistiche canary V6

Dal file `CANARY_V6_RESULTS.json`:

- Target totali: 15 (9 persone + 3 eventi + 3 aggregati)
- Messaggi totali: 45
- Risposte AI validate: 6
- Fallback deterministici: 39
- Marker interni: 0
- Errori: 0
- **Tasso fallback: 86.7%**

Il report V6 dichiara "45 risposte valide" ma 39 sono fallback deterministici, non risposte AI.

---

## 18. Readiness check endpoint

**Non esiste.** Nessun endpoint restituisce:
- `research_contract_version`
- `snapshot_schema_version`
- `active_orchestrator_class`
- `legacy_mutating_pipelines_enabled`
- `build_commit`

---

## 19. Problemi multi_provider_fusion.py

### 19.1 Regola "Agreement => ACCEPTED" (linea 296-298)

```python
# Agreement: mark as ACCEPTED
for c in claims:
    c.status = "ACCEPTED"
```

Questa regola è nel codice ma:
1. **Non è nel call path** di nessun endpoint
2. Anche se lo fosse, violerebbe il principio: due claim con stesso valore non sono due prove indipendenti

### 19.2 Corroboration logic (linea 265-273)

```python
independent_evidence = [ev for ev in result.accepted_evidence if ev.is_independent]
if len(independent_evidence) >= 2:
    if result.conflicting_claims:
        return "CONFLICTING"
    return "ACCEPTED"
```

Il check `is_independent` è basato su `independence_groups`, che viene calcolato da `_compute_independence_groups()`. Ma non c'è un grafo di lineage con `source_family_id`, `derived_from`, `mirror_of`.

---

## 20. Diagnosi aggregati

### 20.1 IMI deceduti in Germania

Il canary V6 non produce dati aggregati reali per questa query. Il canary V5 restituisce `suggested_research_action`.

L'`AggregateQueryResolver` (usato solo dal canary V6) esegue SQL diretto ma:
- Non distingue tra luogo di internamento, luogo di morte, nazione
- Non normalizza Germania vs Austria
- Vienna e Linz (Austria) potrebbero essere conteggiati come Germania

### 20.2 Decorati al Valor Militare WWI

L'aggregazione usa `anno_decorazione` per inferire il conflitto, ma:
- Un anno postbellico (es. 1922) può riferirsi a una decorazione WWI
- Non c'è classificazione WWI_CONFIRMED / WWI_PLAUSIBLE / UNKNOWN

### 20.3 Caduti per affondamento di nave

Non normalizza varianti di maiuscole e cause ("Affondamento Di Nave" vs "affondamento di nave" vs "Affondamento nave").

---

## 21. Eventi — problemi ontologici

L'`EvidenceSnapshotV6` per eventi usa `identity_resolution` (ereditato da persone):
- `identity_resolution = "RESOLVED"` per eventi nel canary V6
- Gli eventi non hanno identità, hanno `object_resolution`
- Non c'è `event_type` (BATTLE, CAMPAIGN, THEATER, etc.)
- Non c'è `temporal_extent` con precisione
- Non c'è `parent_event_id` / fasi nello snapshot

---

## 22. Sintesi: problemi architetturali

1. **Due pipeline separate:** V4 (ricerca) e V6 (conversazione) non comunicano
2. **multi_provider_fusion.py non integrato:** modulo utile ma mai chiamato
3. **QueryManifest non nel runtime:** esiste solo nel canary
4. **ProviderObservation non nel runtime:** esiste solo in test
5. **Nessun fetch/normalizzazione nella pipeline V6:** il snapshot è pre-costruito
6. **Canary non deterministico:** `LIMIT 3` senza `ORDER BY`
7. **Canary V5 ≠ V6:** target diversi, nessun confronto possibile
8. **Fixture sintetica con nome reale:** ABBATTISTA ATTILIO con dati inventati
9. **Validatore confonde JSON interno e testo renderizzato:** `claim_id` vietato ovunque
10. **Fusion ha regola "agreement => ACCEPTED":** viola l'indipendenza delle fonti
11. **Aggregati senza definizione operazionale:** filtri non documentati
12. **Eventi usano `identity_resolution`:** semantica errata
13. **Legacy script con side-effect:** `_gen_record_links.py` e `_find_best_candidates.py` aprono DB all'import
14. **Nessun readiness check:** impossibile verificare la versione del contratto runtime

---

## 23. Cosa serve per V7

1. **UnifiedResearchOrchestratorV7** che unifica ricerca + conversazione
2. **Pipeline unica:** QueryManifest → provider execution → ProviderObservation → fusion → EvidenceSnapshotV7 → narration → validation → rendering
3. **Facade di compatibilità** per V4/V5/V6 che delegano a V7
4. **Readiness check endpoint** con contract version e orchestrator class
5. **Canary con target congelati** (stessi V5 + 100+20 gold set)
6. **Fixture sintetiche con namespace SYNTHETIC_***
7. **Validatore a due livelli:** JSON interno (ID consentiti) + testo renderizzato (ID vietati)
8. **Fusion basata su source family graph**, non su agreement
9. **AggregateDefinitionRegistry** con filtri documentati
10. **Event ontology** con event_type, temporal_extent, parent_event_id
11. **Legacy scripts side-effect-free** all'import
12. **Cache key con target_hash + snapshot_hash + question_hash**

---

*Fine del trace pre-V7. Questo documento dimostra che l'architettura attuale ha due pipeline separate, moduli V6 non integrati, e un canary non comparabile. La V7 deve unificare tutto in un solo orchestratore.*
