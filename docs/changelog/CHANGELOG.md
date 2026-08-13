# CHANGELOG - IMI Extractor

## 2026-08-13 — V7.8: Fix Contaminazione Cross-War e Name Parsing

### Contesto
La pipeline V7.2 restituiva risultati completamente errati per ricerche di persone WWII (es. "Luigi Gaiaschi"): claim da tabelle WWI (`caduti_albooro`, `decorati_nastroazzurro`) venivano inclusi nei dossier WWII, causando narrazioni storiche inaccurate con dati della Prima Guerra Mondiale attribuiti a internati della Seconda.

### Problemi identificati (6 root cause)

1. **Case sensitivity SQLite** — `v7_provider_adapters.py` e `unified_orchestrator_v7.py` usavano query `=` con nome in case misto ("Gaiaschi") ma il DB memorizza uppercase ("GAIASCHI"). SQLite `=` è case-sensitive per TEXT → nessun match trovato.

2. **Assunzione ordine nome** — Tutti i componenti assumevano `parts[0]=cognome, parts[1:]=nome`. L'utente digita "Luigi Gaiaschi" (nome cognome) ma il DB ha cognome="GAIASCHI", nome="LUIGI" → match mancante.

3. **Legacy fallback per PERSON_LOOKUP** — `unified_orchestrator_v7.py:604-609`: quando `classify_observation` restituiva `IRRELEVANT` (nome non corrisponde), il legacy `resolve_observation` promuoveva comunque il record a `SOURCE_CANDIDATE` se aveva un cognome → claim WWI di omonimi inclusi.

4. **war_period errato in schema** — `person_source_schemas.py`: `caduti_albooro` e `decorati_nastroazzurro` erano classificati `WAR_PERIOD_WWII` invece di `WAR_PERIOD_WWI` → bypass dei filtri temporali.

5. **`lebi_records` mancante in `TABLE_WAR_PERIOD`** — `v7_identity_model.py`: la tabella non era mappata → war_period default "UNKNOWN".

6. **Web observations senza filtro WWI** — Observation da web search contenenti marker WWI (1915-1918, Caporetto, Isonzo, Piave) non venivano filtrate per target WWII.

### Soluzioni applicate

| File | Modifica |
|------|----------|
| `v7_provider_adapters.py` | Uppercase di cognome/nome/query; tentativo entrambi ordini (standard + reversed) per full-name e surname match |
| `unified_orchestrator_v7.py` | Uppercase in `_lookup_origin_record` e `_stage_extract`; rilevamento ordine nome via DB lookup; filtro WWI marker su web obs per target WWII; skip legacy fallback per PERSON_LOOKUP |
| `v7_identity_model.py` | Aggiunto `lebi_records: WWII` in `TABLE_WAR_PERIOD`; match reversed name in `classify_observation` |
| `person_source_schemas.py` | Corretto `caduti_albooro` → `WAR_PERIOD_WWI`, `decorati_nastroazzurro` → `WAR_PERIOD_WWI` |

### Risultati verificati (Luigi Gaiaschi)
- **Before**: 63 person claims da 8 tabelle diverse (WWI+WWII), identity UNRESOLVED, narrazione con dati Caporetto/Isonzo/Piave
- **After**: 5 person claims esclusivamente da `internati:22808` (WWII), identity RESOLVED_IDENTITY, zero contaminazione WWI
- **Narrative**: AI discorsiva via gpt-4o (5 blocchi, 18.4s) con contesto storico Operazione Achse, divergenza fonti Belgrado/Grecia, conferma luogo nascita Nibbiano

### Fix hallucination check (V7.8-FIX)
Il narratore AI (`v7_narrator.py`) falliva la hallucination check su "19" (estratto da "1912") e "Grecia" (presente nel `source_text` claim) → fallback a deterministic. Root cause: `_post_gen_hallucination_check` raccoglieva date/luoghi/nomi solo da predicati strutturati (`birth_date`, `birth_place`, ecc.) ignorando `source_text`, `date_note`, `data_quality_note`.

**Fix** (`v7_narrator.py:1198-1237`): estrazione date (`(18|19)\d{2}`), luoghi (capitalized words ≥4 chars) e nomi anche da `source_text`, `date_note`, `data_quality_note`. L'AI ora genera correttamente la narrazione discorsiva senza false-positive.

### Warning residui (non bloccanti, ≤5)
L'hallucination check flagga ancora parole italiane comuni come "Molti", "Internati", "Tuttavia" come `HALLUCINATED_PLACE_OR_NAME`. Da aggiungere alla skip list in `v7_narrator.py:1245-1265`.

---

## 2026-08-12 — V7.6: Cross-Linking Sicuro con Reversibilità

### Contesto
I record `internati` (20.465) avevano copertura molto bassa per campi chiave: `data_nascita` 4%, `luogo_nascita` 1%, `grado` 28%, `reparto` 26%. Le tabelle `lebi_records` (166K), `caduti_ministero` (162K) e `decorati_nastroazzurro` (280K) contengono dati militari e biografici completi per le stesse persone. Obiettivo: arricchire `internati` con dati verificabili, senza mescolare omonimi.

### Problema identificato
Il primo tentativo (`populate_internati_v2.py`) usava match deboli (`fuzzy_first3`, `name_unique` senza validazione anno) che hanno prodotto **278 record con anno di nascita implausibile** (< 1890 o > 1928) — probabili omonimi di altre epoche. Nessun tracciamento delle modifiche: operazione non reversibile.

### Soluzione: cross-linking sicuro con audit table

#### 1. Audit table (`cross_link_audit`)
Tabella SQLite che traccia ogni singola modifica con:
- `internati_id`, `column_name`, `old_value`, `new_value`
- `source_table`, `source_record_id` (provenienza del dato)
- `match_method`, `match_score` (strategia di matching usata)
- `reverted`, `reverted_at` (per rollback)
- `created_at` (timestamp)

#### 2. Script `cross_link_safe.py` — 4 comandi
```
python cross_link_safe.py --audit    # Registra baseline (valori pre-cross-link)
python cross_link_safe.py --run      # Esegue cross-linking sicuro (solo match forti)
python cross_link_safe.py --revert   # Reverte tutte le modifiche (ripristina old_value)
python cross_link_safe.py --status   # Mostra stato audit (attivi/revertiti per metodo)
```

#### 3. Strategie di matching (solo sicure)
| Metodo | Score | Requisiti |
|--------|-------|-----------|
| `name+year` | 100 | Cognome+nome esatto + stesso anno di nascita in entrambe le tabelle |
| `name+place` | 90 | Cognome+nome esatto + stesso luogo di nascita |
| `name_unique+year_verified` | 85 | Nome esatto + candidato unico + anno coincide |
| `name_unique+lebi_year_plausible` | 75 | Nome esatto + candidato unico in LeBI + anno WWII plausibile (1895-1928) |
| `name_ambiguous+single_plausible_year` | 70 | Nome esatto + multipli candidati ma solo 1 con anno WWII plausibile |
| `name+deco_year_wwii` | 90 | Nome esatto + anno decorazione 1940-1947 |

**Strategie escluse** (troppo rischiose): `fuzzy_first3`, `name_unique` senza validazione anno, `cognome_single_partial`.

#### 4. Regole anti-mixing
- **Solo nome esatto**: niente fuzzy matching, niente prefissi parziali
- **Validazione anno WWII**: filtra omonimi di epoche diverse (WWI vs WWII)
- **Candidato unico o singolo plausibile**: niente ambiguità nella selezione
- **Solo campi vuoti popolati**: nessuna sovrascrittura di dati esistenti
- **Anno di nascita plausibile**: 1895-1928 (internee WWII avevano 15-48 anni nel 1943)

### Reversibilità

#### Revert completo
```bash
python cross_link_safe.py --revert
```
Ripristina ogni campo al `old_value` registrato in `cross_link_audit`. Marca ogni record come `reverted=1` con timestamp.

#### Revert selettivo (per tabella fonte)
```sql
-- Revert solo modifiche da lebi_records
UPDATE internati SET data_nascita = NULL 
WHERE id IN (
  SELECT internati_id FROM cross_link_audit 
  WHERE source_table='lebi_records' AND reverted=0
);
UPDATE cross_link_audit SET reverted=1, reverted_at=datetime('now')
WHERE source_table='lebi_records' AND reverted=0;
```

#### Revert per metodo di match
```sql
-- Revert solo match deboli (se si vuole stringere ulteriormente)
UPDATE cross_link_audit SET reverted=1, reverted_at=datetime('now')
WHERE match_method='name_ambiguous+single_plausible_year' AND reverted=0;
-- Poi ripristinare i valori:
SELECT internati_id, column_name, old_value FROM cross_link_audit
WHERE match_method='name_ambiguous+single_plausible_year' AND reverted=1;
```

### Risultati

| Metrica | Valore |
|---------|--------|
| Record internati arricchiti | 4.438 / 20.465 (21%) |
| Aggiornamenti totali | 40.587 |
| Match da lebi_records | 4.438 |
| Match da caduti_ministero | 13 |
| Match da decorati_nastroazzurro | 353 |

#### Copertura campi prima → dopo
| Campo | Prima | Dopo | Delta |
|-------|-------|------|-------|
| data_nascita | 2% | 21% | +19% |
| luogo_nascita | 15% | 21% | +6% |
| grado | 11% | 19% | +8% |
| reparto | 9% | 19% | +10% |
| arma | 18% | 21% | +3% |
| data_decesso | 0% | 17% | +17% |
| luogo_morte | 0% | 17% | +17% |
| luogo_sepoltura | 0% | 14% | +14% |
| campi_internamento | 0% | 10% | +10% |
| fronte_cattura | 0% | 8% | +8% |
| data_cattura | 2% | 8% | +6% |
| causa_morte | 0% | 7% | +7% |
| luogo_cattura | 2% | 6% | +4% |
| data_rientro | 0% | 3% | +3% |
| decorazione | 0% | 1% | +1% |

### File creati/modificati
- `cross_link_safe.py` — **NUOVO**: script cross-linking sicuro con audit + revert
- `cross_link_audit` table — **NUOVA**: tabella SQLite per tracciamento modifiche
- `internati` table — **MODIFICATA**: 11 nuove colonne aggiunte (data_decesso, causa_morte, luogo_morte, luogo_sepoltura, campi_internamento, fronte_cattura, data_rientro, decorazione, anno_decorazione, anno_morte)
- `docs/ARCHITETTURA_COMPLETA.md` — **AGGIORNATO**: v4.0 con pipeline V7, cross-linking, pipeline di ragionamento

### File temporanei (da pulire)
- `_tmp_analyze_rawtext.py` — analisi raw_text OCR
- `_tmp_reapply_rawtext.py` — re-apply estrazione raw_text
- `_tmp_check_all_schemas.py` — audit copertura campi
- `_tmp_audit_crosslink.py` — audit qualità match
- `_tmp_revert_untracked.py` — revert manuale modifiche non tracciate
- `parse_internati_rawtext.py` — parser raw_text OCR (primo tentativo, non tracciato)
- `populate_internati_v2.py` — primo cross-linking non sicuro (sostituito da cross_link_safe.py)

---

## 2026-08-12 (sera) — V7.6.1: Test Pipeline Eventi + Personale su Dati Reali

### Contesto
Verifica end-to-end del backend discorsivo su eventi storici e persone reali, dopo il cross-linking sicuro V7.6.

### Test 1: 3 eventi via `event_research_engine.research_event()`

| Evento | Provider | Fonti | Tempo | Confidence | Dati disputati | Non verificati |
|--------|----------|-------|-------|------------|----------------|----------------|
| Caporetto | gpt | 15 | 59s | ALTA (date/luogo/esito), MEDIA (perdite) | 0 | 2 (perdite, comandanti) |
| Isonzo | gpt | 16 | 196s | ALTA (cronologia/luogo), MEDIA (perdite) | 1 (11 vs 12 offensive) | 1 (perdite) |
| Asiago | gpt | 17 | 84s | MEDIA | 2 (comandanti, perdite) | 2 (perdite, comandanti) |

**Risultati**: 3/3 OK. Disambiguazione corretta via `eventi_1gm.db`. Ogni fatto citato con `[ID]` fonte. Dati non verificati esplicitamente dichiarati. Fonti: USSME (archivio militare), OPAC SBN (bibliografiche), Internet Archive, cadutigrandeguerra.it, cadutisardi.it.

### Test 2: 5 nomi casuali via `UnifiedResearchOrchestratorV7.execute()`

| # | Tabella | Nome | Time | Obs | Identity | Claims | Errors |
|---|---------|------|------|-----|----------|--------|--------|
| 1 | internati | VILLERA Beniamino | 21.1s | 17 | RESOLVED | 6 | 0 |
| 2 | lebi_records | DI CARLO Nicola | 15.6s | 101 | UNRESOLVED | 71 | 0 |
| 3 | caduti_ministero | BERTANO Maurizio | 11.4s | 25 | RESOLVED | 3 | 0 |
| 4 | decorati_nastroazzurro | RICCIOLI Francesco | 13.8s | 42 | CONFLICTED | 14 | 0 |
| 5 | caduti_albooro | RAGGI Luigi | 13.3s | 121 | AMBIGUOUS | 96 | 0 |

**Risultati**: 5/5 OK, 0 errori, 0 contaminazioni cross-war. Identity resolution corretta:
- **RESOLVED** (Villera, Bertano): identità univoca, dati coerenti
- **UNRESOLVED** (Di Carlo): omonimia non risolvibile con dati disponibili (9 fonti confermate, 34 ambigue)
- **CONFLICTED** (Riccioli): due omonimi distinti correttamente (caduto WWI 1916 vs. decorato 1937)
- **AMBIGUOUS** (Raggi): multipli candidati, 1 rigettato per omonimia (12 fonti confermate, 63 ambigue)

### File temporanei (creati e rimossi)
- `_tmp_test_3events.py` — test 3 eventi (cancellato)
- `_tmp_print_3events.py` — stampa completa 3 eventi su file (cancellato)
- `_tmp_3events_output.md` — output 3 eventi (cancellato)
- `_tmp_test_5persons.py` — test 5 nomi casuali (cancellato)
- `_tmp_5persons_output.md` — output 5 nomi (cancellato)

### File modificati
- `docs/ARCHITETTURA_COMPLETA.md` — sezione 5.1b aggiornata con cross-linking sicuro V7.6

---

## 2026-08-11 (sera) — V7.5.1: Anti-Duplicazione Narrazione + AMBIGUOUS_IDENTITY Fix

### Contesto
L'output narrativo AI presentava due problemi: (1) frasi duplicate tra blocchi narrativi (stesso fatto ripetuto con parole diverse in `direct_answer` e `identity`), e (2) contaminazione cross-persona in casi di omonimia (RIZZA GIOVANNI: 3 persone diverse WWI/WWII mescolate in un unico report AI).

### Fix implementati (3)

1. **Prompt anti-duplicazione** (`v7_narrator_prompt_v2.py:130-137`)
   - Nuova sezione "REGOLA ANTI-DUPLICAZIONE OBBLIGATORIA" con istruzioni esplicite
   - Esempi corretti/errati per guidare l'AI a non ripetere fatti tra blocchi
   - Regola: ogni fatto in UN SOLO blocco; blocchi successivi devono AGGIUNGERE informazioni

2. **Dedup nel renderer** (`v7_narrator.py:1533-1571` — `_render_blocks_to_markdown`)
   - Token overlap ratio ≥ 0.55 → blocco scartato
   - Shared 4-gram ≥ 2 → blocco scartato
   - Safety net programmatico anche se l'AI ignora le istruzioni del prompt

3. **Block AI per AMBIGUOUS_IDENTITY** (`v7_narrator.py:851-865`)
   - Quando `identity_status == AMBIGUOUS_IDENTITY` con cluster conflittuali → forza deterministic
   - Previene contaminazione cross-persona: l'AI riceveva 132 claim da 3 persone diverse
   - `fallback_reason = "ambiguous_identity_conflicting_clusters"`

### Bug RIZZA GIOVANNI — Root Cause Analysis
- **3 cluster distinti** trovati: WWII (Modica, 9° Rgt Ftr, naufragio Crete 1943), WWI (Caporale, 223° Rgt Ftr, gas 1917), WWI decorato (Medaglia d'Argento)
- `NarrationEvidenceSelector` non filtra per `identity_cluster_id` → 132 claim da tutti i cluster inviati all'AI
- L'AI mescolava: "padre Angelo" (cluster WWI) attribuito alla persona WWII
- **Fix**: bloccare AI quando AMBIGUOUS + cluster conflittuali → deterministic mostra cluster separati

### Test
- **ALBERINI ANTONIO** (RESOLVED_IDENTITY): 2 blocchi puliti, nessuna duplicazione, AI via openai/gpt-4o
- **RIZZA GIOVANNI** (AMBIGUOUS_IDENTITY): deterministic fallback, 3 cluster separati, 14.1s (vs 22.7s AI)
- **20 nomi casuali** (5 tabelle: lebi, internati, caduti_ministero, caduti_albooro, decorati):
  - 15/20 validated_ai (gpt-4o) — nessuna duplicazione visibile
  - 3/20 deterministic (AMBIGUOUS_IDENTITY: PALMERI, MOSCHETTI, VOLTOLINA) — correttamente bloccati
  - 2/20 validated_ai con UNRESOLVED/CONFLICTED identity
  - 0 errori, 0 duplicazioni
- **5 eventi** (eventi_1gm): 3/5 validated_ai (Caporetto, Asiago, Fronte Macedone), 2/5 blocked (Tobruk=WWII, Piave=claim non validati)

### File modificati
- `v7_narrator_prompt_v2.py` — sezione anti-duplicazione
- `v7_narrator.py` — dedup renderer + AMBIGUOUS_IDENTITY block

---

## 2026-08-11 — V7.5: OpenAI Primary for Report Generation

### Contesto
Crediti OpenAI ricaricati. Generazione narrativa e reportistica spostata su OpenAI (`gpt-4o`) come provider primario, con Mistral (`mistral-small-latest`) come fallback. Ollama/Gemma escluso esplicitamente dalla generazione reportistica in quanto il modello `gemma4:e2b-it-qat` (3B) su CPU ha dimostrato qualità insufficiente per JSON strutturato con claim_ids e una forte tendenza alle allucinazioni.

### Routing aggiornato
- **narration** → OpenAI primary, Mistral fallback
- **generate_biography** → OpenAI primary, Mistral fallback
- **generate_viewpoints** → OpenAI primary, Mistral fallback
- **generate_timeline** → OpenAI primary, Mistral fallback
- **generate_research_plan** → OpenAI primary, Mistral fallback
- **generate_followup_queries** → OpenAI primary, Mistral fallback
- **validate_output** → OpenAI primary, Mistral fallback
- **verify_citations** → OpenAI primary, Mistral fallback
- Policy version: `v7.5-openai-primary`

### Azioni DB
- `ai_routing_policies`: primary_model_id='openai', fallback_model_ids_json='["mistral","anthropic","gemini"]'
- `ai_models`: `gemma4:e2b-it-qat` → status='disabled'

### Test iniziale (ALBERINI ANTONIO)
- Provider: openai/gpt-4o
- Tempo: ~40s
- Blocks: 5
- Claims: 6
- Status: validated_ai

---

## 2026-08-10 — V7.4: Ollama Integration + AI Cross-Validation

### Contesto
Integrazione di Ollama come provider AI locale per generazione narrativa, con modello Gemma 4 (e2b-it-qat, 4.3GB). Ollama sostituisce OpenAI come generatore primario per task di narrazione e generazione biografica. OpenAI diventa validatore primario del output generato, con Mistral come fallback per la validazione. Questo riduce i costi API (generazione locale gratuita) e mantiene un layer di quality assurance via cloud.

### Componenti implementati (5)

1. **Provider Ollama in `ai_client.py`**
   - Funzione `_call_ollama()`: usa OpenAI-compatible API su `http://localhost:11434`
   - Registrato in `_PROVIDER_FUNCS` e `_DEFAULT_MODELS`
   - Timeout 300s (CPU-only, no GPU)
   - Supporto `json_mode` e `json_schema` nativo via Ollama API

2. **Routing AI con Policy DB in `ai_router.py`**
   - `select_model()` ora rispetta `primary_model_id` della policy DB (non solo combined score)
   - `check_budget_before_task()`: skip per provider locali (cost=0, budget=0)
   - Nuovo task type `narration` aggiunto a `TASK_TYPES` e `_GENERATION_TASKS`
   - Policy DB aggiornata: Ollama primary per generation, OpenAI primary per validation
   - Policy version: `v7.4-ollama-e2b`

3. **AI Cross-Validation in `v7_narrator.py`**
   - Metodo `_ai_cross_validate()`: dopo generazione + hallucination check, valida il testo generato
   - Usa `validate_ai_output()` da `ai_client.py` (OpenAI primary, Mistral fallback)
   - Skip del provider generatore (no self-validation)
   - Severity: minor → flags, major → flags, critical → fallback deterministico
   - Metadata salvato in `GenerationInfo.ai_validation`

4. **Funzione `validate_ai_output()` in `ai_client.py`**
   - Valida accuratezza storica, coerenza con claim, allucinazioni residue
   - Prompt strutturato con claims_context e war_period
   - Ritorna: `{ok, valid, severity, issues, suggestions, provider, model}`

5. **Modello DB in `narration_models.py`**
   - `GenerationInfo`: aggiunto campo `ai_validation: Optional[Dict[str, Any]]`
   - Memorizza provider/modello validatore, severity, issues, suggestions

### Fix di routing (3 bug)

1. **Budget check bloccava Ollama**: `est_cost=0.01` hardcoded > `available=0.0` per Ollama (budget=0, reserve=0). Fix: `est_cost=0.0` per provider locali + `check_budget_before_task` skip quando `estimated_cost=0`.

2. **Policy DB ignorata**: `select_model()` selezionava solo per combined score, ignorando `primary_model_id` della routing policy. Fix: priorità ai candidati del provider primario della policy.

3. **Task type `narration` mancante**: non era registrato in `TASK_TYPES` né `_GENERATION_TASKS`, quindi non veniva mai instradato a Ollama. Fix: aggiunto a entrambi.

### Modelli Ollama

| Modello | Size | Params | Status | Note |
|---------|------|--------|--------|------|
| `gemma4:e4b` | 9.6 GB | 8B (Q4_K_M) | disabled | Troppo lento su CPU (170s/196 chars) |
| `gemma4:e2b-it-qat` | 4.3 GB | ~3B (QAT) | enabled | Primary generatore (95s/991 chars) |

### File modificati (5)
- `ai_client.py` — `_call_ollama()`, `validate_ai_output()`, budget fix, default model, timeout 300s
- `ai_router.py` — `select_model()` policy respect, `check_budget_before_task()` zero-cost fix, `narration` task type
- `v7_narrator.py` — `_ai_cross_validate()`, integrazione in `narrate()`
- `narration_models.py` — `GenerationInfo.ai_validation` field
- `research_engine_schema.py` — Ollama provider seed

### File temporanei (test)
- `_tmp_test_multi.py` — Test pipeline: 2 nomi casuali per tabella DB (10 nomi totali)
- `_tmp_test_results.json` — Risultati test salvati

### Configurazione DB
- `ai_providers`: Ollama (id=7, code='ollama', priority=6, budget=0, capabilities=text/vision/structured_output)
- `ai_models`: gemma4:e2b-it-qat (provider_id=7, quality=0.65, cost=0.0, latency=0.8, context=128K)
- `ai_routing_policies`: narration → mistral primary, ollama/gemini/anthropic/openai fallback
- Policy version: `v7.4-mistral-primary`

### Note prestazionali
- `gemma4:e4b` (8B, 9.6GB) su CPU: 170s/196 chars — impraticabile
- `gemma4:e2b-it-qat` (3B, 4.3GB) su CPU: 95-280s per generazione — streaming previene timeout
- Qualità modello 3B: insufficiente per JSON strutturato con claim_ids (0 claims, allucinazioni frequenti)
- **Routing finale**: Mistral generatore primario (25-35s, 3-15 claims validi), Ollama fallback locale quando API cloud non disponibili

---

## 2026-08-10 — V7.3-FIX: Temporal Contamination Prevention in AI Narration

### Contesto
Il narratore AI generava contesto storico sui reparti militari mescolando conflitti: per un soldato WWII (Bruti Alfio, 5° Reggimento Genio) citava il fronte dell'Isonzo e la Prima guerra mondiale. Fix strutturale su 3 livelli: prompt AI, payload dati, validatore post-generazione.

### Fix implementati (3)

1. **Payload AI con `war_period`** (`v7_narrator.py:1042-1060`)
   - `_infer_war_period()` da `military_ontology.py` ora chiamato nel `_build_ai_input`
   - Il payload AI include `"war_period": "WWI | WWII | unknown"` dedotto dai claim (date, keyword)
   - Il narratore sa esplicitamente in quale conflitto ha servito la persona

2. **Sezione AMBITO TEMPORALE OBBLIGATORIO nel prompt** (`v7_narrator_prompt_v2.py:57-63`)
   - Nuova sezione con regole esplicite: TUTTO il contesto storico limitato al `war_period`
   - Esempi concreti: se WWII → no Isonzo/Caporetto/Piave/1915-1918; se WWI → no 8 settembre/Stalag/IMI/1940-1945
   - Regola: non usare conoscenze generali sul reparto da addestramento se riguardano altro conflitto
   - Aggiornata anche sezione CONTESTO MILITARE con riferimento al war_period

3. **Validatore post-generazione con temporal contamination check** (`v7_narrator.py:1232-1263`)
   - `_post_gen_hallucination_check` ora accetta `war_period` parameter
   - Rileva marker WWI in testi WWII (`TEMPORAL_CONTAMINATION_WWI_IN_WWII`)
   - Rileva marker WWII in testi WWI (`TEMPORAL_CONTAMINATION_WWII_IN_WWI`)
   - Se >5 warning → fallback deterministico (come per hallucination standard)
   - Eccezione: marker che corrispondono a claim reali (es. capture_date 1943 in report WWI) non vengono flaggati

### File modificati (2)
- `v7_narrator.py` — `_build_ai_input` (payload + war_period), `narrate` (inferenza war_period), `_post_gen_hallucination_check` (nuovo parametro + temporal check)
- `v7_narrator_prompt_v2.py` — Schema input (war_period), sezione AMBITO TEMPORALE OBBLIGATORIO, aggiornamento CONTESTO MILITARE

### Verifica
- Test su BRUTTI ALFIO (WWII, 5° Reggimento Genio): report AI Mistral ora descrive il reparto **esclusivamente nel contesto WWII** ("Durante la Seconda guerra mondiale, il 5º Reggimento Genio era un'unità specializzata nelle costruzioni militari..."). Nessun riferimento a Isonzo/Caporetto/Prima guerra mondiale.

---

## 2026-08-09 — LeBI Bulk Import + Supabase Sync + Narrative Pipeline Integration

### Contesto
Integrazione completa del database LeBI (Lessico Biografico degli IMI — ANRP) nel sistema: bulk import di 166K+ record dal portale `lessicobiograficoimi.it`, sincronizzazione a Supabase, e integrazione nella pipeline discorsiva V7 per generazione narrazioni AI arricchite.

### Task completate (6/6)

1. **Bulk Import SQLite** (`import_lebi_bulk.py`)
   - 166K+ record importati (ID range 2345–330027) in `lebi_records` table in `imi_internati.db`
   - ThreadPoolExecutor (20 thread), BeautifulSoup HTML parsing, checkpoint/resume (`lebi_import_checkpoint.json`)
   - Fix `sqlite3.OperationalError`: 27 colonne vs 26 placeholder → aggiunto `enriched_at`

2. **Supabase Sync** (`sync_lebi_to_supabase.py`)
   - Schema `lebi_records` creato su Supabase
   - Batch upsert con `on_conflict=lebi_id` + `Prefer: return=minimal,resolution=merge-duplicates`
   - Checkpoint resumable (`sync_lebi_supabase_checkpoint.json`)
   - Verifica conteggi SQLite ↔ Supabase: match confermato

3. **LocalDbAdapter** (`v7_provider_adapters.py:183-190`)
   - Aggiunto `("lebi_records", "cognome", "nome")` alla lista tabelle `PERSON_LOOKUP`
   - LeBI records ora restituiti come `SOURCE_CANDIDATE` observations

4. **PERSON_SOURCE_SCHEMAS** (`person_source_schemas.py:351-392`)
   - Schema completo `lebi_records`: 18 claim_fields, 4 provenance_fields, 7 identity_fields, 6 conflict_fields
   - `war_period=WWII`, `authority_tier=1` (fonte ufficiale ANRP)
   - Nuovi predicate: `capture_front`, `return_date`, `return_place` con validatori/normalizzatori

5. **Research Orchestrator + Fact Extractor**
   - `research_orchestrator.py:84,505` — `lebi_records` aggiunto a ricerche entità e tabelle dirette
   - `fact_extractor.py:130-150` — `_LEBI_FIELD_MAP` con 18 mapping field→predicate
   - `unified_orchestrator_v7.py:565` — docstring aggiornata

6. **Test Pipeline Discorsiva** (5 nomi casuali, 5/5 RESOLVED_IDENTITY)
   - CURIAZZI GIOVANBATTISTA: 57 obs, 17 claims, deterministic (LeBI: Innsbruck/Stalag III D)
   - PELLEGRINI GIACOMO: 157 obs, 31 claims, AI Mistral (LeBI: 9° Reggimento Alpini, Stalag X B)
   - BULGARELLI ERMANNO: 106 obs, 11 claims, AI Mistral (LeBI: Carpi, Stalag XI A, Arb. Kdo. 427)
   - GERMANO GUIDO: 157 obs, 31 claims, deterministic (LeBI: Castel Del Monte, 9 Rgt. Alp.) + omonimo rilevato
   - BRUTTI ALFIO: 86 obs, 14 claims, AI Mistral (LeBI: Maiolati Spontini, 5° Reggimento Genio, Halle/Saale)

### File modificati (6)
- `v7_provider_adapters.py` — LocalDbAdapter PERSON_LOOKUP table list
- `person_source_schemas.py` — Schema registry + validatori/normalizzatori
- `unified_orchestrator_v7.py` — Docstring PERSON tables
- `research_orchestrator.py` — Entity search + direct table search
- `fact_extractor.py` — _LEBI_FIELD_MAP + field_map lookup + entity_label

### File nuovi (3)
- `import_lebi_bulk.py` — Bulk import script con checkpoint
- `sync_lebi_to_supabase.py` — Sync SQLite → Supabase con upsert
- `_test_lebi_narrative.py` — Test pipeline discorsiva su nomi casuali LeBI

### Verifiche chiave
- LocalDbAdapter interroga `lebi_records` → `SOURCE_CANDIDATE` observations
- `extract_claims_from_record` processa `lebi_records` tramite `PERSON_SOURCE_SCHEMAS`
- Provenance corretta: URL LeBI, PDF, source_id estratti dai campi `detail_url`, `pdf_url`, `lebi_id`
- Identity resolution: RESOLVED per nomi univoci, AMBIGUOUS per omonimi (es. GERMANO GUIDO)
- URL LeBI nei context claims: `https://www.lessicobiograficoimi.it/frontend_prodimi.php/caduti/show/{id}`
- AI provider: OpenAI esaurito (429), Anthropic non autorizzato (401), Mistral attivo (200)

---

## 2026-08-05 — V7.3-PERSON-FIX: Evidence-Locked Narration, Multi-Table Retrieval, Script Security

### Contesto
Refactoring completo del pipeline V7: retrieval multi-tabella (5 fonti PERSON), identity resolution cluster-based con identificatori forti, narratore evidence-locked con payload validation e post-generation hallucination detection, migrazioni DB additive (data_corrections + Supabase parity), sicurezza script non-distruttiva (quarantena invece di DELETE), regression benchmark.

### Task completate (14/14)
1. Diagnosi call graph + baseline 20 nomi
2. Modelli tipizzati (PersonCandidate, PersonFact, FactEvidence, etc.)
3. PERSON_SOURCE_SCHEMAS: mapping 5 tabelle con validator/normalizer
4. Fix retrieval: 5 tabelle queryate, word boundary, normalizzazione nominativo
5. Fix schema OpenAI + circuit breaker provider AI
6. Separazione fatti/evidenze/provenance con dedup
7. Identity resolver cluster-based, no fusione omonimi
8. Unit test: 43/43 PASS
9. _gen_record_links.py: quarantena, CLI, pairwise linking
10. _gen_event_links.py: word boundary, barriere temporali, incremental
11. Narratore evidence-locked: _validate_payload, _compute_evidence_hash, _post_gen_hallucination_check
12. Migrazioni DB: data_corrections table, sync_parity_audit, Supabase parity (6/8 OK)
13. Sicurezza script: _clean_bad_links (DELETE→quarantine), _fix_gaiaschi_db (UPDATE→overlay)
14. Regression benchmark: 5/5 PASS, 6/6 backend test, 0 errori

### File nuovi (5)
- `person_source_schemas.py`, `person_pipeline_models.py`, `test_person_v73_fix.py`
- `migrate_v73_data_corrections.py`, `run_regression_v73.py`

### File modificati (10)
- `unified_orchestrator_v7.py`, `v7_narrator.py`, `ai_client.py`, `narration_models.py`
- `v7_identity_model.py`, `_gen_record_links.py`, `_gen_event_links.py`
- `_clean_bad_links.py`, `_fix_gaiaschi_db.py`

### Dettagli: [CHANGELOG_V73_PERSON_FIX.md](../../CHANGELOG_V73_PERSON_FIX.md)

---

## 2026-08-01 — V4 Post-Audit: API, Fetch Integration, Archive Expansion, Canary Live

### Contesto
Dopo il completamento del V4 audit (13/13 task), eseguita integrazione post-audit: API per il conversational report provider, fetch HTTP nel relevance gate, espansione registry archivistico, canary live con Tavily + AI su 10 target.

### Modifiche

**File nuovi (2):**
- `report_conversation_api.py` — 3 endpoint FastAPI: POST create conversation, POST send message, GET conversation; Pydantic models per request/response
- `generate_conversational_reports.py` — script per generare report discorsivi per ogni target usando ReportConversationProvider con AI

**File modificati (3):**
- `app.py`:
  - Import `report_conversation_api.router`
  - `app.include_router(report_conversation_router)`
- `relevance_gate_v4.py`:
  - `_extract_text_from_html()` — estrazione testo da HTML (rimuove script/style, decodifica entità, collapse whitespace)
  - `fetch_and_classify()` — HTTP GET con timeout 15s, estrazione contenuto, classificazione con `fetch_status=SUCCESS` + `fetched_content`; gestisce HTTPError, URLError, TimeoutError
- `archive_jurisdiction_registry.py`:
  - +5 comuni verificati: Modica (Siracusa), San Lorenzo (Reggio Calabria), Casaluce (Caserta), Brienza (Potenza), Lettere (Napoli)
  - Totale: 16 comuni mappati (era 11)
- `run_canary.py`:
  - Fix encoding Windows cp1252: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`

### Canary V4 Live (Tavily + AI)
- 10/10 target completati con `use_ai=True`
- Tavily web search attiva su 9/10 target (VENEZIANO NICOLA: 0 sources)
- AI attiva su tutti i 10 target (Mistral)
- 0 fallimenti, stato: SUCCESS
- `CANARY_RESULTS.json` + `CANARY_DOSSIERS.json` + `CANARY_REPORT.md` generati

### Risultati canary live

| # | Target | Stato | Candidates | Tavily sources | AI | Elapsed |
|---|--------|-------|------------|----------------|-----|---------|
| 1 | LARI GIUSEPPE | dati_insufficienti | 51 | 7 | si | 36.6s |
| 2 | FEDERICO LUIGI | dati_insufficienti | 89 | 6 | si | 21.4s |
| 3 | GIUNTA GIUSEPPE | dati_insufficienti | 36 | 6 | si | 22.3s |
| 4 | VENEZIANO NICOLA | dati_insufficienti | 30 | 0 | si | 22.8s |
| 5 | FANTUZ ANTONIO | dati_insufficienti | 30 | 6 | si | 24.4s |
| 6 | FEDELE AGOSTINO | dati_insufficienti | 34 | 4 | si | 24.6s |
| 7 | RUSSO GAETANO | dati_insufficienti | 38 | 3 | si | 26.3s |
| 8 | PAPINI PUBLIO | dati_insufficienti | 31 | 1 | si | 25.8s |
| 9 | FOLLADOR GIOVANNI | dati_insufficienti | 30 | 7 | si | 24.3s |
| 10 | SIFANNO TOMMASO | dati_insufficienti | 30 | 5 | si | 24.1s |

### Issue note
- `Discovery persistence failed: no such column: idempotency_key` — colonna mancante nella tabella `source_registry` SQLite, non bloccante
- `AI provider perplexity failed: 401 Unauthorized` — chiave API Perplexity non valida, fallback a Mistral
- `AI provider mistral failed: Server disconnected` — intermittente, fallback deterministico attivo
- Warning `InsecureRequestWarning` su HTTPS senza certificato — non bloccante

---

## 2026-07-31 — V4 EvidenceSnapshot Reconstruction (12 Defect Categories Fixed)

### Contesto
Audit completo del backend del protocollo di ricerca. Identificate e corrette 12 categorie di difetti semantici e strutturali. Implementati 7 nuovi moduli, integrate le correzioni in `research_protocol.py`, scritti 149 test (82 V4 + 67 V3), eseguito canary offline su 10 target con 0 violazioni.

### Moduli nuovi (7)

| File | Scopo |
|------|-------|
| `evidence_snapshot_v4.py` | DTO unificato e validato con origin_record, accepted_claims, provider_ledger, reconciliation, `to_conversational_context` (source_id only, no URL) |
| `source_capability_registry.py` | Registry unificato per 25 provider con routing per conflitto (ww1/ww2/both), sostituisce i set hardcoded `_WWI_ONLY_PROVIDERS` / `_WWII_ONLY_PROVIDERS` |
| `archive_jurisdiction_registry.py` | 16 mapping verificati comune→archivio (11 originali + 5 post-audit); comuni non verificati → statement generico, nessun archivio inventato |
| `relevance_gate_v4.py` | Pipeline multi-stage: result_kind → name_match → period_compatibility → geographic_scope → fetch_status; 4 bucket (evidence, context, leads, rejected) |
| `name_parser_v4.py` | Parser corretto per pattern `COGNOME NOME DI PADRE`; preserva raw_value, parser_version, field_provenance; flag `needs_field_review` |
| `ai_output_validator.py` | Validatore post-generazione: detection contraddizioni, URL allucinati, archivi non verificati; fallback deterministico |
| `report_conversation_provider.py` | Interfaccia conversazionale report — Mistral/local only, OpenAI hardcoded disabled, persistenza SQLite |

### Moduli modificati (2)

- `research_protocol.py`:
  - Import V4 modules
  - `_web_search_enrich`: usa V4 relevance gate + invia snapshot unificato ad AI (no candidati grezzi/Tavily results)
  - `_generate_archival_requests`: usa `ArchiveJurisdictionRegistry` verificata invece di template generation
  - `apply_resolution_gate`: `SOURCE_RECORD_ONLY` richiede lineage verificata (URL assoluta)
  - `compute_typed_counts`: URL relative contate come lead, non source_record
  - `get_provider_capabilities`: delega a `source_capability_registry`
  - `score_candidate`: usa V4 name parser per paternity extraction da display_name
  - `research_person`: build V4 snapshot, validate invariants, downgrade su violazione
  - Post-AI validation con `ai_output_validator` + fallback deterministico
- `test_research_protocol_v3_master.py`:
  - 3 test aggiornati per comportamento V4 (routing unknown conflict, SOURCE_RECORD_ONLY con URL verificata, paternity parser V4)

### 12 Difetti corretti

1. **EvidenceSnapshot V4** — DTO unificato con origin_record, claims, provider_ledger, `to_conversational_context` senza URL
2. **SOURCE_RECORD_ONLY invariants** — richiede URL assoluta verificata; URL relative → lead; `compute_typed_counts` riconciliato
3. **Relevance gate multi-stage** — sostituisce gate binario V3 con pipeline 6-stage (result_kind, name_match, period, geo, fetch, state)
4. **False negative proofs** — `CONSULTED_NO_MATCH` richiede `fetch_status=SUCCESS` + nome assente nel content
5. **URL dedup e rendering** — AI riceve source_id solo; nessuna estrazione URL da AI text; renderer genera link da snapshot
6. **missing_claims** — computed da `CLAIM_FIELDS` set minus claim accettati/partial
7. **Unified capability routing** — singolo registry per retrieval, suggestions, report, UI; LeBI skipped per WWI
8. **ArchiveJurisdictionRegistry** — no template-generated archives; 16 comuni verificati (11 + 5 post-audit); comuni non mappati → statement generico
9. **Parser COGNOME NOME DI PADRE** — `PAPINI PUBLIO DI GIOVANNI` correttamente split in surname=PAPINI, given=PUBLIO, father=GIOVANNI
10. **Post-generation validator** — schema, grounding, contradiction detection, hallucinated URL/archive detection, deterministic fallback
11. **Conversational report** — `ReportConversationProvider` con SQLite, Mistral/local only, OpenAI disabled
12. **Tests** — 82 test V4 (fixture-based, property-based, parametrized regression) + 67 test V3 aggiornati = 149 PASS

### Test
- `test_research_protocol_v4_master.py` — 82 test su 12 categorie + property-based + regression
- `test_research_protocol_v3_master.py` — 67 test (3 aggiornati per V4)
- **149/149 PASS** in 0.58s

### Canary V4 Offline
- `run_canary_v4_offline.py` — 10/10 target completati, 0 violazioni, 0 chiamate OpenAI
- `CANARY_V4_OFFLINE_RESULTS.json` — risultati strutturati
- `CANARY_V4_BEFORE_AFTER.md` — report before/after con verifica features

### Vincoli enforceati
- No OpenAI API calls (hardcoded disabled)
- No template-generated archives (verified registry only)
- No false negative proofs without verified fetch
- No counting suggestion URLs as sources
- No homonyms from uncertain parser data (`needs_field_review` flag)
- No URLs in AI conversational context (`source_id` only)

### File generati
- `CANARY_V4_OFFLINE_RESULTS.json`
- `CANARY_V4_BEFORE_AFTER.md`

---

## 2026-07-30 — Discovery Persistence Pipeline (Web Search Archival System)

### Contesto
Implementata la pipeline completa di acquisizione, classificazione e persistenza delle fonti scoperte via web search. Ogni risultato di ricerca web viene ora sistematicamente classificato, deduplicato, collegato a oggetti storici, e persistito localmente (SQLite) con sync idempotente a Supabase via outbox pattern.

### File principale
- `discovery_persistence.py` (nuovo, ~1400 righe) — dataclasses, schema SQLite, pipeline completa

### Dataclasses
- `ArchivalDecision` — policy archivistica + diritti/licenze
- `SourceMetadata` — metadati provenienza completi
- `SourceObjectLink` — collegamento tipato fonte-oggetto
- `HistoricalClaim` — claim versionato con conflict detection
- `DiscoveredEntity` — entità candidata con entity resolution
- `ResearchLead` — pista di ricerca persistente
- `SyncState` — stato sync locale-Supabase
- `DiscoveryPersistenceResult` — output aggregato per dossier API

### Tabelle SQLite create
- `source_registry`, `historical_claims`, `discovered_entities`, `research_leads`, `source_object_links`, `sync_outbox`, `ingestion_runs`

### Funzioni
- `classify_archival_policy()` — classificazione via compliance_gate
- `deduplicate_sources()` — dedup per URL canonico, hash, ID
- `extract_claims_from_text()` — estrazione claim strutturati con clean encoding
- `detect_conflicting_claims()` — conflict detection vs DB esistente
- `resolve_or_create_entity()` — entity resolution + nuove entità
- `extract_research_leads()` — piste archivistiche + URL deduplicati
- `sync_outbox_to_supabase()` — sync idempotente via `insert_batch_schema`
- `process_web_search_results()` — orchestrazione pipeline

### Integrazione
- `research_protocol.py`: `_web_search_enrich()` chiama `process_web_search_results()`
- `Dossier` dataclass: campo `discovery_persistence` aggiunto
- API `/api/research-protocol`: output include `discovery_persistence`

### Fix applicati durante test
1. Column count mismatch in `_persist_source()`: 38→39 placeholder
2. Supabase sync: sostituito `get_supabase_client()` (inesistente) con `supabase_client.insert_batch_schema()`
3. Encoding mojibake: pulizia UTF-8 (Â°, Ã, etc.) su testo web search
4. Claim garbage filter: filtrati valori non informativi
5. Claim deduplicazione per predicate+normalized_value
6. Entity section headers esclusi ("CONFERMA CANDIDATI", etc.)
7. Lead deduplicazione per dominio URL e institution name

### Test end-to-end (query "damioli giovanni, nato 1899")
- 1 fonte creata (metadata_only), 6 claim estratti, 12 entità scoperte, 8 piste, 11 item in outbox
- Local persistence: completed | Supabase sync: failed (schema `core` non esposto)

### PENDING
- Vedi TODO.md sezione "Discovery Persistence — PENDING"

---

## 2026-07-27 — Audit bootstrap Internet Archive + Schema `core.events` su Supabase

### Contesto
Richiesta di avviare il bootstrap automatico Internet Archive → Supabase (28 sezioni di specifica). Prima di scrivere qualunque job/worker è stato eseguito un audit reale: verifica materiale (query dirette PostgREST, non solo lettura di file `.sql`) di cosa esiste davvero su Supabase vs cosa presupponeva la specifica.

### Finding critico
Il modello `core.events`/`core.entities` presupposto dal prompt **non esisteva** su Supabase (verificato: `Invalid schema: core` via PostgREST). Gli eventi storici vivevano solo in SQLite (`eventi_1gm.db`, 22 righe: 15 WWI, 7 WWII). Le tabelle `archive.*`/`ops.*`/`evidence.*`/`ai.*` esistevano già (migrazione `001_supabase_historical_archive_core.sql`) ma erano vuote, senza alcun worker/consumer applicativo.

### Audit
- `docs/audit/internet-archive-bootstrap-preflight.md` — tabella di audit con 15 aree (provider IA, Advanced Search, Metadata Read, job queue, valutazione pertinenza, registry, ecc.), stato reale verificato, gap, azione.

### Modifiche

#### `sql/002_supabase_core_events.sql` (nuovo, additivo)
- Schema `core` con `entities`, `events`, `entity_names`
- Trigger `updated_at` (riusa `archive.set_updated_at()` da `001_...sql`, nessuna duplicazione)
- RLS pattern identico a `001_supabase_historical_archive_core.sql`
- RPC `exec_sql_query` (SELECT semplici) ed `exec_sql_returning` (query con CTE `INSERT...RETURNING`, necessaria perché Postgres richiede che un WITH con data-modifying statement sia al livello top — `exec_sql_query` lo avvolge in una subquery e fallisce con `0A000`)

#### `apply_migration_002.py` (nuovo)
- Riusa `split_sql_statements`/`is_meaningful_statement` da `apply_migration_v2.py` (nessun parser duplicato)
- Eseguito: **41/41 statement OK**

#### `migrate_events_to_core.py` (nuovo)
- Migrazione dati idempotente `eventi_1gm.db` → `core.entities`/`core.events`/`core.entity_names` (upsert su `stable_id`/`source_id`)
- Risoluzione automatica `parent_event_id` in seconda passata (i riferimenti in SQLite sono per `stable_id` testuale, es. `evt_0017`)
- Eseguito due volte per verificare idempotenza: stesso risultato, zero duplicati

### Risultati verificati (non simulati)
- **22 eventi** migrati (15 WWI, 7 WWII)
- **84 alias** in `core.entity_names`
- **7 relazioni parent/child** risolte correttamente (es. `evt_0018` Battaglia del Carso → parent `evt_0017` Battaglie dell'Isonzo; `evt_0024` Monte San Michele → parent `evt_0018`)
- Idempotenza confermata su doppia esecuzione

### Azione manuale richiesta (non completabile da codice)
Schema `core` da aggiungere in **Supabase Dashboard → Settings → API → Exposed Schemas** (necessario per usare `repository_layer.py`/`supabase_client.select_schema` via REST diretto; le RPC `exec_sql_query`/`exec_sql_returning` funzionano già perché vivono in `public`, già esposto).

### Non fatto (fuori scope, dichiarato esplicitamente)
Job queue con worker reali, admin UI popolamento, estrazione/dedup nuovi eventi WWI/WWII con AI, sincronizzazione incrementale, claim/evidence review — stimati settimane di lavoro, non implementabili in modo credibile e verificabile in un'unica sessione. Prossimo passo: collegare `ia_pipeline.py`/`ia_evaluation.py` per scrivere in `archive.external_items`/`archive.representations` su un evento pilota (Battaglia del Carso, `evt_0018`).

---

## 2026-07-25 (sera) — Fix Internet Archive: Context Propagation + Query Planner + Evaluation Integration

### Problema
`ProviderInternetArchive.search()` usava filtri hardcoded `date:[1940 TO 1946]` e fallback `_IT_MILITARY` generico per qualsiasi query, inclusi eventi WWI. Il contesto evento (conflitto, date, luogo, alias) non veniva propagato dalla pipeline al provider. `ia_evaluation.evaluate_candidates()` esisteva ma non era integrato nel percorso runtime. `get_event_by_id()` non selezionava la colonna `conflict` dal DB.

Risultato: eventi WWI come "Battaglia del Carso" ricevevano risultati WWII irrilevanti (es. `TacticalAndTechnicalTrendsNos1-20`).

### Soluzione
Pipeline end-to-end con contesto tipizzato propagato da `_web_sources()` → `federated_search()` → `ProviderInternetArchive.search()` → query planner → evaluation.

### Modifiche

#### `source_providers/base.py`
- Aggiunto `FederatedSearchContext` (dataclass frozen): `subject_type`, `canonical_name`, `aliases`, `conflict` (ww1/ww2/other/unknown), `start_date`, `end_date`, `places`, `keywords`, `context_fingerprint`
- Aggiunto `build_federated_search_context()`: costruisce context da event_data, normalizza conflitto, inferenza date-based fallback (1914-1918 → ww1, 1939-1946 → ww2) solo quando conflict è unknown
- Aggiunto `_normalize_conflict()`: mappa varianti (WWI, 1GM, Prima guerra mondiale, WW2, 2GM, ecc.) a codici normalizzati
- Aggiunto `_parse_event_date()`: parse ISO e year-only
- Firma `SourceProvider.search()` aggiornata: `context: Optional[FederatedSearchContext] = None`

#### `source_providers/federation.py`
- `federated_search()` accetta e propaga `context` a ogni provider

#### `source_providers/providers.py`
- `ProviderInternetArchive.search()` riscritto: usa `build_internet_archive_query_plan()`, nessun filtro hardcoded, campi `discovery_score`/`discovery_strategy`/`query_plan_version`
- `_IT_MILITARY` fallback gated: solo `subject_type in (person, unit, document) AND conflict == ww2`
- Tutti gli altri provider (15 classi) aggiornati con nuova firma `search()`

#### `ia_evaluation.py`
- Aggiunto `build_internet_archive_query_plan()`: genera strategie multiple (exact_event, alias, place, contemporary, contextual) basate su FederatedSearchContext
- Aggiunto `evaluate_candidates_from_context()`: wrapper che mappa FederatedSearchContext → event_data dict per evaluate_candidates
- Aggiunto `IAQueryPlanEntry` dataclass: `query`, `strategy`, `reason`, `event_scope`, `publication_date_filter`
- Versioni cache: `IA_QUERY_PLAN_VERSION = "ia_query_plan_v2"`, `IA_RELEVANCE_VERSION = "ia_relevance_v2"`
- Fix mapping conflict: `ww1 → WWI`, `ww2 → WW2` (compatibile con _detect_conflict)

#### `event_evidence_pipeline.py`
- `_web_sources()` riscritto: costruisce `FederatedSearchContext`, passa a `federated_search()`, separa risultati IA, valuta con `evaluate_candidates_from_context()`, filtra rejected, assegna `verification_status` basato su evaluation (accepted → probabile, candidate → candidata)

#### `event_resolver.py`
- `get_event_by_id()`: aggiunta colonna `conflict` alla SELECT query

#### Provider aggiornati (firma search)
`antenati.py`, `cri_milano.py`, `cwgc.py`, `deutsche_digitale_bibliothek.py`, `grand_memorial.py`, `icrc_ww1.py`, `iwm_lives.py`, `lebi.py`, `memoire_des_hommes.py`, `nara.py`, `wikitree.py`

#### Frontend
- `frontend/src/pages/EventResearchPage.tsx`: `VerificationBadge` gestisce `probabile`, summary mostra conteggio Probabili

#### Test
- `test_event_research_master.py`: 31 test (unitari, integrazione, regressione live). **31/31 PASS**
  - `TestFederatedSearchContext` (10 test): context building, conflict normalization, date parsing, immutability, fingerprint
  - `TestIAQueryPlanner` (9 test): strategie, no hardcoded WW2 dates, no IT_MILITARY terms, date derivate dall'evento, versioning
  - `TestIAEvaluation` (7 test): TacticalAndTechnicalTrends rejected, rejection non basata su identifier, post-war WWI book non rejected, search page rejected, evaluate_candidates_from_context, discovery/relevance separation, versioning
  - `TestContextPropagation` (2 test): spy provider riceve context, provider senza context funziona
  - `TestRegressionTacticalTrends` (3 test): no TacticalAndTechnicalTrends in Carso sources, no search page URLs, no WW2 items for WW1 event

### Validazioni chiave
- `TacticalAndTechnicalTrendsNos1-20` → rejected (war mismatch: WW2 item vs WW1 event)
- `lalettura170301031917_art_02` → non rejected (WWI, pertinente)
- Nessun filtro `date:[1940 TO 1946]` nelle query del piano
- Nessun termine `_IT_MILITARY` per eventi (solo person/unit WW2)
- Cache versioning: `ia_query_plan_v2`, `ia_relevance_v2`
- Zero risultati è valido: nessun fallback a contenuto generico per eventi
- Discovery score separato da historical relevance score

### Regole rispettate
- No dati mock o simulati: test usano DB reale e API IA live
- No redesign full pipeline: fix mirato su context propagation
- No cancellazione dati legacy: audit non distruttivo
- No hardcoding event-specific identifiers: query planner generico
- Conflict unknown non inferisce WW2: marcato unknown esplicitamente

## 2026-07-25 (sera) — Internet Archive Integration (in progress)

### Riepilogo
Integrazione di Internet Archive come fonte esterna strutturata per ricerca storica eventi. Pipeline completa: discovery, valutazione storica, asset selection, locator pagina/passaggio, ingestion preview, conferma archiviazione, ricostruzione eventi. Moduli nuovi riusano componenti esistenti (fonti_indice, archivio_documenti, event_links, claim_service, event_resolver).

### Nuovi moduli backend
- **`ia_evaluation.py`** — Valutazione storica candidati IA: rilevamento conflitto (WWI/WW2/interwar), compatibilità temporale, geografica, pertinenza storiografica, qualità documento (OCR/DjVu/PDF). Score 0.0–1.0, stati accepted/candidate/rejected. Filtra search page URL generiche.
- **`ia_locator.py`** — Asset selection (priorità hOCR > DjVu > PDF > text) e locator pagina/passaggio. Parser hOCR (microformat HTML con bbox), parser DjVu text layer, page count da metadata. `locate_passage()` pipeline completa con fallback.
- **`ia_pipeline.py`** — Pipeline end-to-end: `discover()` (advancedsearch + evaluation), `analyze_item()` (metadata + asset + locator), `build_ingestion_preview()` (form precompilato), `confirm_ingestion()` (upsert fonti_indice + archivio_documenti + event_links + claim), `reconstruct_from_ia()` (ricostruzione da fonti IA accettate).

### Componenti riusati
- `source_providers/providers.py:ProviderInternetArchive` — search/metadata base (esteso con query dinamiche in ia_pipeline)
- `event_resolver.py` — risoluzione evento, get_event_by_id, get_related_events
- `archivio_documenti.py` — upsert_documenti, create_schema
- `claim_service.py` — create_claim, add_evidence
- `event_evidence_pipeline.py` — Source, Claim, EvidencePackage, _temporal_overlap, _geographic_overlap
- `mass_index.py:_is_search_page_url` — modello per filtro URL search page
- `_clean_bad_links.py` — modello per audit non distruttivo
- `event_link_audit.py` — modello per audit event_links

### Endpoint API pianificati
| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/ia/discover` | GET | Discovery item IA per evento |
| `/api/ia/item/{identifier}` | GET | Metadati + asset + locator item IA |
| `/api/ia/analyze` | GET | Analisi completa item (evaluation + locator) |
| `/api/ia/ingestion-preview` | GET | Form precompilato per conferma |
| `/api/ia/confirm` | POST | Conferma ingestion (archivia + collega) |
| `/api/ia/reconstruct` | GET | Ricostruzione evento da fonti IA |
| `/api/ia/audit` | GET | Audit non distruttivo vecchi link IA |

### Stato implementazione
- [x] `ia_evaluation.py` — completato, compila OK
- [x] `ia_locator.py` — completato, compila OK
- [x] `ia_pipeline.py` — completato, compila OK
- [ ] API endpoints in `app.py` — da implementare
- [ ] Frontend (tab IA in EventResearchPage) — da implementare
- [ ] Audit non distruttivo vecchi link IA — da implementare
- [ ] Test master — da implementare

### Regole rispettate
- No dati mock o simulati: tutti i metadati provengono da API IA reali
- No download forzato di asset: solo metadati + link diretto
- Filtro search page URL: niente pagine di ricerca generiche salvate
- War mismatch: item IA con conflitto diverso dall'evento vengono rifiutati
- Non distruttivo: audit vecchi link marca, non cancella

## 2026-07-25 — AI Historical Integration: Phases A–K (branch `devin/ai-storica-eventi-mappe`)

### Riepilogo
Integrazione completa di sistema AI storico specializzato per WWI/WII nel repository principale. 11 fasi, ~20 nuovi file backend, ~10 nuovi file frontend. Schema additive, nessuna cancellazione dati.

### Phase A — Audit baseline
- `_audit_baseline.py`: ispezione tabelle, conteggi, integrità FK, indici
- `docs/AI_HISTORICAL_INTEGRATION_BASELINE.md`: documentazione completa (312 righe)
- `docs/adr/ADR-AI-HISTORICAL-RAG-EVENT-MAPS.md`: ADR architetturale
- `.gitignore`: regole per modelli, dati, cache, refactor, handoff

### Phase B — Sicurezza e contratti
- `_check_keys.py`: verifica chiavi API senza esporre valori
- `canonical_models.py`: modelli Pydantic canonici (Event, Claim, Map, Graph, ResearchJob, Report, StructuredError)
- `frontend/src/api/canonical-types.ts`: equivalenti TypeScript
- `ai_runtime.py`: interfaccia InferenceAdapter con LMStudio, Remote, Test adapter
- `config/ai_runtime.yaml`: configurazione runtime (no segreti)
- `research_orchestrator.py`: `classify_url` espansa con 10 tipi (document, record, catalog_entry, search_page, homepage, download, viewer, broken, unknown)

### Phase C — Provenance e claims
- `graph_schema.py`: migrazione additiva (6 tabelle, 8 indici) con `--dry-run` e `--rollback`
- `graph_models.py`: modelli Pydantic per GraphNode, GraphEdge, GraphEvidence, GraphReview, etc.
- `graph_service.py`: adapter read-through per record_links, event_links, collegamenti, external_record_links, claims — preserva provenance legacy, mai promuove candidati a confirmed senza review
- `graph_api.py`: router FastAPI `/api/graph/entity/{table}/{id}` e edge review
- `database_registry.py`: registry tabelle canonico con TableSpec, connessioni read-only, estrazione label/descrizione/URL

### Phase D — Evento canonico
- `event_schema.py`: migrazione additiva su `eventi_1gm` (12 nuove colonne: stable_id, conflict, event_type, parent_event_id, review_status, etc.) + tabella `event_aliases` (90 alias importati)
- `event_canonical_api.py`: API REST `/api/canonical-events` con list, get, children, update
- Classificazione conflict: 7 eventi WWII riclassificati (Operazione Achse, Cefalonia, Russia, Tobruk, Mauthausen, Lavoro forzato, Cassino)
- Gerarchia parent_event_id: Isonzo→Carso/SanMichele/Nero/Tolmino/Caporetto, etc.

### Phase E — RAG pipeline
- `rag_pipeline.py`: pipeline completa
  - `retrieve()`: retrieval ibrido FTS5 + filtri metadata su tabelle multiple
  - `rerank()`: boost qualità fonte, compatibilità temporale/geografica, indipendenza
  - `build_context()`: contesto strutturato con citazioni `[fonte: table#id]`, budget token, warning troncamento
  - `validate_ai_output()`: check claim non citati, pattern allucinazione, dichiarazione "evidenze insufficienti"
- `rag_api.py`: API REST `/api/rag/retrieve` e `/api/rag/validate`

### Phase F — Frontend
- `types.ts`: CanonicalEvent, GraphEntityResponse, GraphEdgeDTO, GraphEvidenceDTO, RAGContextResponse, RAGValidationResponse
- `client.ts`: graphEntity(), graphEdgeReview(), canonicalEvents(), canonicalEvent(), ragRetrieve(), ragValidate()
- `EventsPage.tsx`: tag conflict (WWI/WWII) e event_type su card eventi, caricamento parallelo eventi canonici
- `EventDossierPage`: pulsante "Grafo canonico" → `/grafo/eventi_1gm/:id`
- `GraphEntityPage.tsx`: nuova pagina con filtri stato epistemico, evidenze, segnali contrari, review status
- `router.tsx`: route `/grafo/:sourceTable/:sourceId`

### Phase G — Mappa
- `map_schema.py`: tabella `map_features` con provenance (source_table, source_id, source_url), certainty, review_status, phase
- `map_features_api.py`: API REST `/api/map-features` con list, create/update (upsert), review
- Frontend: MapFeatureRecord, MapFeatureListResponse types + API client methods

### Phase H — Grafo
- `GraphEntityPage.tsx`: integrazione ForceGraph con filtri status applicati a visualizzazione e lista archi
- ForceGraph esistente (582 righe): anti-collision, zoom/pan, fullscreen, export SVG/PNG, touch support

### Phase I — Runtime locale
- `ai_runtime_api.py`: API REST `/api/ai-runtime` con health, config, benchmark, reset
- Frontend: AIRuntimeHealth, AIRuntimeConfig, AIRuntimeBenchmark types + API client methods

### Endpoint API nuovi
| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/graph/entity/{table}/{id}` | GET | Grafo canonico per entità |
| `/api/graph/edges/{edge_id}/review` | POST | Review arco grafo |
| `/api/canonical-events` | GET | Lista eventi canonici |
| `/api/canonical-events/{stable_id}` | GET/PUT | Evento canonico singolo |
| `/api/canonical-events/{stable_id}/children` | GET | Eventi figlio |
| `/api/rag/retrieve` | GET | RAG retrieval + reranking + context |
| `/api/rag/validate` | POST | Validazione output AI |
| `/api/map-features/event/{event_id}` | GET | Feature mappa per evento |
| `/api/map-features/` | POST | Crea/aggiorna feature |
| `/api/map-features/{id}/review` | PUT | Review feature |
| `/api/ai-runtime/health` | GET | Stato adapter AI |
| `/api/ai-runtime/config` | GET | Configurazione (no segreti) |
| `/api/ai-runtime/benchmark` | POST | Benchmark latenza |
| `/api/ai-runtime/reset` | POST | Reset adapter singleton |

### Schema migrazioni (tutte additive, reversibili)
- `imi_internati.db`: graph_nodes, graph_edges, graph_edge_reviews, graph_pipeline_runs, graph_integrity_issues, archival_metadata (6 tabelle, 8 indici)
- `eventi_1gm.db`: 12 colonne aggiuntive su eventi_1gm + event_aliases table (2 indici) + map_features table (3 indici)

### Test
- Schema deployment verificato con `--dry-run` e esecuzione reale
- Graph service testato con record reale (internati/22808, Gaiaschi Luigi)
- RAG pipeline testato con query "Caporetto" (3 chunks, citazioni corrette)
- Event canonical API testato (22 eventi, 90 alias, gerarchia corretta)
- TypeScript compila senza errori (`tsc --noEmit`)

## 2026-07-24 (sera) — Refactor grafo canonico, identity resolution e fonti (branch `codex/refactor-grafo-fonti-20260724`)

### Riepilogo
Refactor completo del sistema di collegamenti (grafo), risoluzione identità e gestione fonti. 62 file modificati, +7.568 / -2.147 righe. Branch `codex/refactor-grafo-fonti-20260724` su commit `a7e6231`. PR aperta, non mergiata.

### Nuovi moduli backend
- **`identity_resolution.py`** (475 righe) — Algoritmo di risoluzione identità con gradi di confidenza (candidate → probable → confirmed). Rifiuta cognome-only come prova. Corroborazioni: data nascita, luogo, matricola, reparto, campo, periodo. Gestione omonimi con marcatura ambiguous.
- **`identity_link_pipeline.py`** (248 righe) — Pipeline dry-run/execute per generare collegamenti identity-resolved. Algorithm version `identity-resolution-2.0.0`. Checkpoint/resume.
- **`graph_schema.py`** (153 righe) — Schema canonico grafo: nodi, archi, review, pipeline runs, integrity issues.
- **`graph_service.py`** (152 righe) — Servizio grafo: lettura coordinata di `collegamenti`, `record_links`, `event_links`, `external_record_links`, claims.
- **`graph_models.py`** (93 righe) — Modelli Pydantic per API grafo.
- **`graph_visualization.py`** (139 righe) — Generazione grafo SVG selezionabile e scaricabile nei report.
- **`archival_metadata_service.py`** (154 righe) — Metadati archivistici stabili con marcatura URL mancanti.
- **`validate_graph.py`** (208 righe) — Validatore read-only su 4 sistemi di collegamento.
- **`database_registry.py`** (265 righe) — Registry centralizzato per path DB main ed eventi.

### Migrazioni additive e reversibili
- **`20260724_001_graph_core.sql`** (129 righe) — 6 nuove tabelle in `imi_internati.db`: `graph_nodes`, `graph_edges`, `graph_edge_reviews`, `graph_pipeline_runs`, `graph_integrity_issues`, `archival_metadata`.
- **`20260724_001_graph_core_rollback.sql`** (22 righe) — Rollback completo.
- **`20260724_002_event_link_metadata.sql`** (24 righe) — Tabella `event_link_metadata` in `eventi_1gm.db`.
- **`20260724_002_event_link_metadata_rollback.sql`** (3 righe) — Rollback.
- **`apply_graph_migrations.py`** (80 righe) — Runner con dry-run, execute, rollback. Backup automatici con SHA-256.

### Modifiche backend
- **`app.py`** (+234/-234) — API canoniche: `/api/graph/search`, `/api/graph/entity/{table}/{id}`, `/api/graph/expand`, `/api/graph/metadata`, `/api/graph/review`. Endpoint `/api/internati/{id}/links` deprecato come alias con `is_graph: false`. Endpoint `/api/internati/{id}/fonti` ora esclude surname-only e homepage. Report con `visualization.nodes` e `visualization.edges`.
- **`report_engine.py`** (+560/-) — Generazione grafo SVG nel report, narrative con grafo grounded, no dangling edges.
- **`unified_search.py`** (+107) — Ricerca unificata con ritorno identità reale del record.
- **`external_link_service.py`** (+314/-) — Matching con data nascita, luogo, campo. Batch linking. Detection omonimie. `review_link_with_type` per link bidirezionali.
- **`link_pipeline.py`** (+445/-) — Audit read-only su 4 sistemi. Pipeline dry-run.
- **`soldier_dashboard.py`** (+160/-) — Dashboard con fonti dossier filtrate, external sources con `live_search_performed: false` di default.
- **`viewpoints_api.py`** (+174) — API per punti di vista con grafo.
- **`search_service.py`** (+93) — Servizio ricerca con identity resolution.

### Modifiche frontend
- **`ReportGraph.tsx`** (+315) — Grafo SVG interattivo, selezione nodi, download.
- **`PrimaryNavigation.tsx`** (nuovo, 300 righe) — Navigazione primaria refactor.
- **`HomePage.tsx`** (+414/-) — Home page con grafo e report integrati.
- **`HeuristicLinksPage.tsx`** (+83/-) — Pagina collegamenti euristici con nuovi contratti.
- **`SoldierDossierPage.tsx`** (+53/-) — Dossier con fonti filtrate, external sources.
- **`ViewpointsPage.tsx`** (+144/-) — Punti di vista con grafo.
- **`ResearchPage.tsx`** (+199/-) — Ricerca AI con identity resolution.
- **`AdminPage.tsx`** (+17/-) — Admin con stato migrazioni.
- **`client.ts`** (+78/-) — Client API con tipi grafo.
- **`types.ts`** (+36/-) — Tipi TypeScript per grafo, identity, metadata.

### Test
- **`tests/test_identity_resolution.py`** (107 righe) — 6 test: birth data corrobora, conflitto data non compensato, anno in contesto migliora match, omonimi marked ambiguous, full name non auto-confirmato, surname-only rejected.
- **`tests/test_graph_refactor.py`** (425 righe) — 10 test: nodi/archi/legacy validi, migrazioni apply/rollback, validator 4 sistemi, fonti dossier escludono surname-only, external mentions usano birth data, archival metadata stabile, report grafo grounded no dangling, review persistita senza cambiare legacy, unified search ritorna identità reale.
- **Totale: 16 test, 0 falliti** (0.651s).

### Documentazione
- `docs/graph-architecture-audit.md` (115 righe) — Audit architettura grafo.
- `docs/graph-data-model.md` (137 righe) — Modello dati canonico.
- `docs/graph-validation-report.md` (179 righe) — Report validazione.
- `docs/external-sources-status.md` (85 righe) — Stato fonti esterne.
- `docs/analysis/REPORT_ANALISI_E_FIX.md` (27 righe) — Analisi e fix.
- `frontend/ARCHITECTURE.md` (+276 righe) — Architettura frontend refactor.

### Verifiche eseguite
- `compileall`: PASS
- `unittest` (16 test): PASS
- `npm run lint` (oxlint): 0 warnings, 0 errors
- `npm run build` (tsc + vite): PASS (588ms, 1603 moduli)
- Migrazioni: dry-run → execute → rollback → re-execute. Tutti i conteggi legacy invariati. Integrity check OK.
- Caso regressione Luigi Gaiaschi (id=22808): fonti dossier corrette (no Mario/Camilla/Rosa), external sources senza live search, grafo senza undefined nodes, report con 26 nodes / 22 edges.
- AI Mistral: `mistral-small-latest` risponde correttamente (3.739 caratteri generati).
- `.env` e DB: gitignored, non tracciati.

### Anomalie residue (preesistenti, non introdotte dalla patch)
- `validate_graph.py` crash su `archivio_documenti` (chiave composta `provider+external_id`, no colonna `id`).
- Conflitto `httpx<0.28` vs `mistralai>=2.0.0` in `requirements.txt` — risolto localmente aggiornando httpx a 0.28.1.
- 589 FK violations preesistenti in `imi_internati.db` (foreign keys non abilitate in `get_conn()`).
- OpenAI 401 (chiave scaduta), Anthropic 400 (credito insufficiente), Gemini 429 (quota superata), Perplexity 401.

## 2026-07-24 (notte) — Research Engine Fase C: Fact Extraction + Timeline Automatica

### Nuovo modulo: Fact Extractor (`fact_extractor.py`)
- **Estrazione claim strutturati da record DB** — mapping deterministico campi → predicati
  - `internati`: 12 predicati (born_at, resident_at, held_rank, captured_at, interned_at, worked_at, has_service_number, had_role, had_fate, event_date)
  - `caduti_albooro`: 7 predicati (has_name, held_rank, served_in, died_in, died_at, from_municipality, born_in_year)
  - `decorati`: 12 predicati (born_at, died_at, cause_of_death, held_rank, served_in, decorated_with, captured_at, interned_at, has_service_number)
- **Estrazione claim da testo non strutturato via AI** (`extract_claims_from_text_ai`)
  - Prompt specializzato per estrazione fatti storici (16 predicati standard)
  - JSON mode con parsing e creazione claim idempotenti
  - Evidenza con quote originale e confidence
- **Estrazione claim da frammenti di ricerca** (`extract_claims_from_fragments`)
  - `entity_match` → claim `identified_as` con evidenza FTS
  - `external_source` → claim `mentioned_in` con evidenza federata
  - `person_record` → delega a `extract_claims_from_record`
- **Pipeline completa** (`extract_facts_for_entity`)
  - Cerca record in internati/decorati/caduti_albooro
  - Estrae claim strutturati + AI su raw_text
  - Rileva conflitti + costruisce timeline
- **Date parsing** (`_parse_date`): ISO, DD-MM-YYYY, "9 gennaio 1912", solo anno
- **Timeline automatica** (`auto_build_timeline`): ordinamento per data con None in fondo

### Orchestrator — Integrazione Fact Extraction (`research_orchestrator.py`)
- `run_research()` ora esegue fact extraction dopo i cicli di ricerca
  - Estrae claim da record DB + frammenti di ricerca
  - Timeline popolata automaticamente dai claim
  - Campo `facts` nel risultato con claims_created, claims_existing, conflicts, timeline
- La narrative synthesis ora riceve timeline popolata → sintesi più ricca

### Fix — Conflitti falsi positivi (`claim_service.py`)
- `detect_conflicts()` ora raggruppa per `object_type` prima di confrontare
- Claim con stesso predicate ma object_type diverso (es. `born_at` date vs place) non sono più conflitto

### Schema migration (`research_engine_schema.py`)
- Aggiunta colonna `updated_at` a `research_sessions` (idempotente)

### Test (`test_research_engine_master.py`)
- **137 test, 0 falliti** (97 Fase A + 16 Fase B + 24 Fase C)
- Nuovi test Fase C: `test_parse_date`, `test_extract_claims_from_record`, `test_extract_claims_from_text_ai`, `test_extract_facts_for_entity`, `test_extract_claims_from_fragments`, `test_conflict_detection_same_type`, `test_timeline_auto_build`, `test_run_research_with_facts`

## 2026-07-23 (notte) — Research Engine Fase B: AI Provider Integration + Frontend Research View

### Nuovo modulo: AI Client unificato (`ai_client.py`)
- **Client AI unificato** — ponte tra `ai_router` (selezione modello) e provider AI reali
- **5 provider supportati**: OpenAI (GPT-4o-mini), Anthropic (Claude), Mistral, Perplexity (Sonar/web search), Google Gemini
- `call_ai()` — routing automatico via `select_model()`, fallback tra provider, tracking costi/latenza tramite `record_task_run()`
- `call_ai_json()` — JSON mode con parsing automatico e fallback text-extraction
- Supporto vision (immagini base64) per OCR ed estrazione documenti
- Supporto web search (Perplexity) con citations
- `get_available_providers()` / `is_any_provider_available()` — verifica disponibilità chiavi API
- Circuit breaker integrato: provider degradati esclusi automaticamente
- Budget check pre-task con quota di riserva
- Client singleton per provider (riuso connessione)

### Orchestrator — Integrazione AI (`research_orchestrator.py`)
- **`_generate_followup_queries_ai()`** — AI genera query di follow-up intelligenti basate su frammenti trovati e lacune aperte (task type: `generate_followup_queries`)
- **`_decide_continue_or_stop_ai()`** — AI valuta se continuare o fermare la ricerca basandosi su frammenti, query generate e lacune (task type: `decide_continue_or_stop`)
- **`_generate_narrative_synthesis()`** — AI produce sintesi narrativa finale strutturata (SINTESI, PERSONE, LUOGHI, EVENTI, FONTI CONSULTATE, LACUNE, APPROFONDIMENTI CONSIGLIATI) basata esclusivamente su frammenti e timeline reali (task type: `generate_biography`)
- `run_research()` ora ritorna campo `narrative` con testo, provider, modello, costo, token
- Fallback automatico: se AI non disponibile, regole euristiche originali preservate

### Frontend — Research Engine View (`templates/index.html`)
- **Nuova vista "Ricerca AI"** — accessibile via nav bar con link "Ricerca AI"
- Route SPA `/research` registrata nel router
- UI: input query, loading indicator, error display, risultati strutturati
- Sezioni risultati: Summary (entity_type, cycles, status, plan_id), Cicli (decision, fragments, new queries), Timeline (date, predicate, epistemic_status, evidence_count), **Sintesi Narrativa AI** (text, provider, model, cost), Provider IA (budget, spent, credit_status), Archive Connectors
- Bindings: `researchQuery`, `researchLoading`, `researchError`, `researchResult`, `researchHasNarrative`, `researchNarrativeText/Provider/Model/Cost`, `researchCycles`, `researchTimeline`, `researchProviders`, `researchConnectors`
- Metodi SPA: `goResearch()`, `onResearchInput()`, `onResearchKeyDown()`, `onResearchSubmit()`, `loadResearchProviders()`, `loadResearchConnectors()`
- Title dinamico: "Ricerca AI — Voci dal Fronte"

### Fix — Router SPA (`templates/shared/router.js`)
- **Fix stack overflow**: re-entrancy guard `_handling` in `navigate()` e `handleRoute()` per prevenire ricorsione infinita (`goHome()` → `navigate('/')` → `handleRoute()` → handler → `goHome()` → ...)
- Fix `cadutiCurrentPage`: `Math.max(1, Math.min(...))` per validità input number

### Test (`test_research_engine_master.py`)
- **113 test, 0 falliti** (97 Fase A + 16 Fase B)
- Nuovi test Fase B:
  - `test_ai_client_providers_available` — verifica provider configurati
  - `test_ai_client_call_real` — chiamata AI reale (provider, text, cost, latency, task_run_id)
  - `test_ai_client_json_mode` — JSON mode con parsing
  - `test_ai_client_fallback` — fallback con circuit breaker forzato
  - `test_orchestrator_narrative_synthesis` — narrative synthesis end-to-end

### Provider AI status
- **OpenAI** ✅ attivo (primario)
- **Anthropic** ⚠️ credit balance esaurito
- **Mistral** ⚠️ import issue SDK
- **Perplexity** ⚠️ 401 unauthorized
- **Gemini** ⚠️ modello non trovato (gemini-1.5-flash deprecato)
- Il sistema funziona con fallback automatico: OpenAI come provider attivo

## 2026-07-23 (sera) — Research Engine Fase A: Fondamenta

### Nuovo modulo: Research Engine (motore agentico di ricerca multi-fonte)

**Schema migrazioni** (`research_engine_schema.py`):
- 18 nuove tabelle idempotenti: `archive_connectors`, `research_plans`, `research_sessions`, `research_queries`, `research_results`, `research_cycles`, `entity_variants`, `entity_match_candidates`, `document_extractions`, `claims`, `claim_evidence`, `claim_relations`, `generated_narratives`, `ai_providers`, `ai_models`, `ai_routing_policies`, `ai_task_runs`, `ai_usage_ledger`
- Estensione `record_links` con campi: `algorithm_version`, `score_breakdown_json`, `contrary_signals_json`, `explanation`
- Seed 6 provider IA: OpenAI, Anthropic, Mistral, Perplexity, Gemini, LM Studio
- 35 indici per performance su entita', fonte, stato, timestamp, fingerprint

**Claim Service** (`claim_service.py`):
- Affermazioni atomiche con `stable_id` deterministico (idempotente)
- Evidenze con ruolo (supports/contradicts/contextualizes), gruppo indipendenza, forza
- Rilevamento conflitti deterministico: stesso predicate, object_value diverso → contradiction o possible_sequence (se date sequenziali)
- Timeline da claim documentati
- Narrazioni versionate con claim_ids, gaps, deductions
- Revisione umana: confirmed/rejected/under_review con motivazione

**Entity Resolution** (`entity_resolution.py`):
- Generazione varianti: name_swap, initial, ocr_error, transliteration, accent_variant, title_strip
- Scoring composto con breakdown: name_similarity (Jaro-Winkler), birth_date, birth_place, service_number, military_unit, camp, temporal_coherence
- Segnali contrari e dati mancanti esplicitati
- Match candidate con review: confirmed/rejected/open/omonymy
- Normalizzazione nomi (NFKD, lowercase, no accenti/apostrofi)

**Archive Registry** (`archive_registry.py`):
- Import automatico dei 27 provider esistenti da `federation.py` in `archive_connectors`
- Selezione dinamica fonti per entity_type, periodo, geografia, nazionalita', gaps, clues
- Health check per connector
- Authority score e access mode (auto/assisted)

**AI Router** (`ai_router.py`):
- 21 task types con capabilities e min_quality
- Routing per capacita': text, vision, ocr, web_search, structured_output, embeddings
- 3 strategie: quality_max, balanced, economic
- Circuit breaker (3 fallimenti → 5 min cooldown)
- Budget check pre-task con quota di riserva
- Ledger consumi per provider/modello/periodo
- Crediti: real (API header), estimated, unknown

**Orchestrator** (`research_orchestrator.py`):
- Ciclo Plan-Retrieve-Extract-Resolve-Validate-Expand-Stop
- `resolve_input()`: identifica tipo entita', cerca match interni (DB + FTS + graph)
- `run_cycle()`: ricerca interna + federata, estrazione frammenti, generazione query followup
- `run_research()`: end-to-end con budget cycles
- Registrazione query/results con fingerprint e stato (new/linked/excluded/duplicate)
- Traccia completa sessione (queries, results, cycles)
- Criteri di arresto: budget exhausted, no new fragments, no external results

**API Router** (`research_engine_api.py`):
- 35 endpoint sotto `/api/research-engine/`
- Input resolution, plans, sessions, cycles, queries, results
- Claims CRUD + evidence + review + conflicts
- Timeline, narratives
- Entity variants, match candidates, review
- Archive connectors: list, capabilities, health, recommendations
- AI providers, models, credits, usage, routing policies, health check

**Test** (`test_research_engine_master.py`):
- 97 test, 0 falliti
- Copertura: schema idempotenza, claim CRUD/evidence/conflicts/review/timeline/narrative, entity resolution (variants/scoring/match/normalize/jaro-winkler), archive registry (listing/recommendations/health), AI router (selection/credits/circuit-breaker/budget/task-run), orchestrator (resolve_input/run_research/session_trace/query_recording), anti-allucinazione (no source/no data/search-vs-document)

**Integrazione in `app.py`**:
- Schema init in lifespan
- `seed_from_federation()` in lifespan
- Router registrato: `app.include_router(research_engine_router)`

## 2026-07-23 (notte) — Integrazione LeBI/ANRP + Aggiornamento architettura

### Backend — Provider LeBI (`source_providers/lebi.py`)
- **Nuovo provider**: `ProviderLeBI` — Lessico Biografico degli Internati Militari Italiani (ANRP)
- **Portale**: `https://www.lessicobiograficoimi.it/` — 305.827 nominativi IMI (1943-1945)
- **Ricerca**: `GET /frontend_prodimi.php/caduti/search?q=&n=&l=&y=&d=0` — parametri verificati da form HTML reale
- **Scheda**: `GET /frontend_prodimi.php/caduti/show/{ID}` — parsing HTML con BeautifulSoup
- **PDF**: `GET /frontend_prodimi.php/caduti/showpdf/{ID}` — disponibile pubblicamente (HTTP 200, `application/pdf`)
- **Parser HTML**: estrae 6 sezioni (ANAGRAFICA, POSIZIONE MILITARE, CATTURA, DECESSO, INTERNAMENTO, FONTI) da classi CSS `fallen-box-title`, `fallen-field-margins`, `col-xs-5`
- **Campi estratti**: cognome, nome, data/comune/provincia/regione nascita, grado, reparto, arma, fronte, luogo/data cattura, matricola (da note), data/luogo decesso, causa morte, sepoltura, lista campi internamento, fonti
- **Metodi**: `search()`, `get_metadata()`, `get_document()`, `build_search_url()`

### Backend — Adapter LeBI (`sources_external_lebi.py`)
- **Nuovo adapter**: `LeBIAdapter` implementa `SourceAdapter` per modulo Fonti Esterne Federate
- `discover_resources()` — ricerca per cognome con paginazione
- `parse_record()` — parsing completo scheda + `compute_metadata_hash`
- `extract_person_mentions()` — 1 menzione per scheda (persona principale)
- `extract_facts()` — fatti strutturati: birth, capture, internment, death, burial
- `detect_digital_objects()` — PDF scheda con metadati rights/credit
- JSON metadata: people, places, military_units, camps, subjects

### Backend — Federation e Compliance
- **`federation.py`**: registrato `ProviderLeBI` (27 provider totali)
- **`federation.py`**: aggiunto mapping `_match_provider`: lebi, lessico biografico, anrp → lebi
- **`compliance_gate.py`**: nuova policy `lebi` / dominio `lessicobiograficoimi.it`
  - `METADATA_ONLY` con `document_download_allowed=1` (PDF pubblico)
  - Attribution: "ANRP — LeBI, Lessico Biografico degli IMI"
  - `policy_status`: partially_verified
- **`external_metadata_service.py`**: registrato `LeBIAdapter` nel registry adapter

### Backend — Ricerca federata (`search_validator.py`)
- LeBI interrogato per ogni nome archivio (max 5) alongside ICRC
- Priorità risultati: ICRC per-nome → LeBI per-nome → ICRC query → LeBI query → altri
- Limite esterno aumentato da 20 a 25 risultati

### Frontend (`templates/index.html`)
- Pannello fonti esterne: link dinamici per provider (ICRC/LeBI/altro)
- Aggiunto link "Scarica PDF" per risultati LeBI
- Label provider dinamica: `providerLabel` calcolato da `es.provider`
- Descrizione footer aggiornata: "ICRC + LeBI/ANRP"

### Documentazione
- **`docs/architecture/ARCHITECTURE.md`**: aggiornato a 27 provider, aggiunta sezione 4.7 LeBI con tutti i dettagli tecnici
- **`docs/changelog/CHANGELOG.md`**: questa voce

## 2026-07-23 (notte 2) — LeBI F3 Linking + F6 Import incrementale

### F3 — Linking (`external_link_service.py`)
- **Matching esteso**: aggiunto confronto camp/luogo internamento (peso 1.0) e data decesso (peso 1.5)
- **grave_conflicts**: fix bug — inizializzato a lista vuota, merge da date nascita + date decesso
- **Batch linking**: `generate_links_for_provider(provider, limit)` — genera collegamenti per tutte le menzioni di un provider
- **Omonimie**: `detect_omonimie(provider, min_score)` — rileva menzioni con 2+ candidati con score gap < 0.15
- **Review con type**: `review_link_with_type(link_id, ..., link_type='lebi_match')` — link_type personalizzato per record_links bidirezionali

### F6 — Import incrementale (`external_metadata_service.py`)
- **Checkpoint/Resume**: `run_import(provider, ..., resume=True)` riprende dall'ultimo job incompleto, skippa URL già processati
- **Batch size**: update DB ogni `batch_size` record (default 50) per ridurre I/O
- **Helper LeBI**: `import_single_lebi_record(lebi_id)` — import singola scheda per ID
- **Helper LeBI**: `import_lebi_by_surname(surname, max_records)` — import batch per cognome
- **Statistiche**: ritornato anche `skipped` (record saltati in resume)

### Documentazione
- **`docs/architecture/ARCHITECTURE.md`**: aggiunte sezioni 4.7.1 (Linking) e 4.7.2 (Import incrementale)

## 2026-07-23 (sera) — Frontend Croce Rossa + Conformità + Filtri Scopri + Architettura + Docs

### Frontend `renderRedCross()` — UI completa sezione Croce Rossa

- **`templates/rc.html`**: implementata funzione `renderRedCross()` con:
  - Campo ricerca con filtro fonte (Tutte / ICRC WW1 / CRI Milano)
  - Tabella risultati con badge colorati per provider, indicatori accesso (Online / Solo metadati / Su richiesta / Login richiesto / Errore)
  - Pannello dettaglio record espandibile con tutti i metadati
  - Link diretto al catalogo esterno + bottone dettaglio per record con ID
  - Loading state e gestione errori
- **State**: aggiunti `redCrossQuery`, `redCrossSource`, `redCrossResults`, `redCrossLoading`, `redCrossDetail`
- **Funzioni**: `redCrossSearch()`, `redCrossDetail()`, `redCrossKeyDown()`, `setRedCrossSource()`, `complianceBadge()`

### Frontend `renderCompliance()` — UI completa sezione Conformità

- **`templates/rc.html`**: implementata funzione `renderCompliance()` con 3 tab:
  - **Policy**: tabella con provider, dominio, classificazione (badge colorato), licenza metadati, download permesso, stato verifica, credit line
  - **Coda revisione**: tabella con priorità (badge), azione, risorsa, motivo, data, bottoni Approva/Rifiuta/Sospendi
  - **Log decisioni**: tabella con data, azione, decisione (badge colorato), regola, motivazione, decisore
- **State**: aggiunti `compliancePolicies`, `complianceDecisions`, `complianceReviewQueue`, `complianceTab`
- **Funzioni**: `loadCompliance()` (3 API parallele), `resolveReviewItem()`, `updatePolicy()`
- **`setView()`**: caricamento automatico compliance data al click nav

### Filtri avanzati pagina Scopri

- **Frontend `renderDiscover()`**: aggiunti 3 dropdown filtri:
  - Filtro per fonte (9 opzioni: IMI, Albo d'Oro, Nastro Azzurro, Decorati ISTORECO, Caduti Ministero, CWGC, Fonti indice, Fondi archivistici, NARA T315)
  - Filtro per conflitto (Tutti / 1ª GM / 2ª GM)
  - Filtro per sorte (Tutte / Deceduto / Disperso / Rimpatriato)
- **Backend `rc_api_ext.py`**: endpoint `GET /discover-candidates` esteso con parametri `source`, `conflict`, `fate`
  - Filtro source: skip provider non selezionato
  - Filtro conflict: WHERE su colonne grado/reparto/guerra con keyword match
  - Filtro fate: WHERE su colonna sorte
- **State**: aggiunti `discoverFilterSource`, `discoverFilterConflict`, `discoverFilterFate`

### Documentazione

- **`docs/architecture/ARCHITECTURE.md`**: documento architetturale completo (spostato da root)
  - 8 sezioni: visione, architettura, frontend dettagliato, backend dettagliato, AI integration, memory router, cross-DB linking, federation layer
  - 26 provider federati mappati
  - Flussi end-to-end documentati
  - Mappa endpoint → file
- **Riorganizzazione docs**: tutti i file .md spostati in `docs/` con sottocartelle:
  - `docs/architecture/` — ARCHITECTURE.md, ARCHITETTURA_DB.md
  - `docs/manuals/` — PERCORSO_RICONOSCIMENTI.md, MANUALE_USO.md (nuovo)
  - `docs/changelog/` — CHANGELOG.md
  - `docs/todo/` — TODO.md, TODO_2026-07-10.md, TODO_2026-07-15.md
  - `docs/analysis/` — ANALISI_DB_FRONTEND.md, REPORT_ANALISI_E_FIX.md, ANALISI_117DIV_MARZO1943.md, CONCORSI_EUROPEI.md
- **`README.md`**: aggiornato con architettura corrente (26 provider, 80+ endpoint, AI multi-provider)
- **`docs/manuals/MANUALE_USO.md`** (nuovo): manuale d'uso completo per operatori e ricercatori
- **`docs/todo/TODO.md`**: aggiornato con task completati e nuovi pending

---

## 2026-07-23 — Compliance Gate + Fonti Croce Rossa + Migrazione PostgreSQL

### Compliance Gate — sistema di conformità normativo (GDPR/D.lgs 196/2003/D.lgs 42/2004)

- **`compliance_gate.py`** (nuovo): motore centralizzato `evaluate(resource, action, user_role)` che controlla ogni operazione su fonti esterne:
  - 8 classificazioni risorsa: `METADATA_ONLY`, `PUBLIC_VIEW`, `PUBLIC_DOWNLOAD`, `REQUEST_REQUIRED`, `AUTHORIZATION_REQUIRED`, `RESTRICTED`, `RIGHTS_UNKNOWN`, `UNREACHABLE`.
  - 11 azioni controllate: `INDEX_METADATA`, `GENERATE_LINKS`, `DOWNLOAD_FILE`, `RUN_OCR`, `EXTRACT_PERSONAL_DATA`, `SHOW_TO_AUTHENTICATED_USER`, `SHOW_PUBLICLY`, `INCLUDE_IN_DOSSIER`, `EXPORT`, `DELETE`, `REFRESH_SOURCE`.
  - 5 decisioni: `ALLOW`, `ALLOW_WITH_LIMITATIONS`, `REQUIRE_REVIEW`, `REQUIRE_AUTHORIZATION`, `DENY`.
  - Regole: UNREACHABLE/RESTRICTED → DENY; RIGHTS_UNKNOWN → metadati minimi + link; dati sanitari → blocco pubblicazione/export + autorizzazione per OCR; persona potenzialmente vivente → revisione obbligatoria; AUTHORIZATION_REQUIRED → verifica autorizzazione registrata.
  - Logging automatico ogni decisione in `compliance_decisions` con regola, motivazione, policy applicata.
  - Coda `compliance_review_queue` per revisione umana.
  - `seed_source_policies()`: pre-popolazione policy per ICRC, CRI Milano, CRI Trieste con condizioni reali (diritti, licenze, contatti, credit line).
- **Schema DB** (`rc_schema.py`): 4 nuove tabelle:
  - `source_policies`: registro fonti con diritti, licenze, condizioni accesso, stato verifica, scadenza review.
  - `compliance_decisions`: log ogni valutazione (azione, decisione, regola, motivazione, policy, autorizzazione).
  - `compliance_authorizations`: autorizzazioni registrate con scope, finalità, protocollo, validità, revoca.
  - `compliance_review_queue`: coda "Da verificare" con priorità, stato, decisione, motivazione.
  - Migration: `life_status` column su `rc_candidates` (deceased/possibly_living/unknown).
- **Integrazione OCR**: endpoint `POST /practice-documents/{did}/ocr` passa dal Compliance Gate prima di elaborare. Documenti sanitari (certificati morte, referti, cartelle cliniche) richiedono autorizzazione.
- **API endpoints** (`rc_api_ext.py`):
  - `GET /compliance/policies` — lista tutte le policy fonti.
  - `GET /compliance/policies/{id}` — dettaglio policy.
  - `PUT /compliance/policies/{id}` — aggiorna policy (admin only).
  - `GET /compliance/decisions` — log decisioni (ultime 100).
  - `GET /compliance/review-queue` — coda revisione (pending/resolved).
  - `POST /compliance/review-queue/{id}/resolve` — risolvi item (approve/reject/suspend/request_consultation).
  - `POST /compliance/authorize` — crea autorizzazione (admin only).
  - `DELETE /compliance/authorizations/{id}` — revoca autorizzazione (admin only).
  - `POST /compliance/evaluate` — valuta risorsa + azione → decisione.
- **Frontend** (`templates/rc.html`): nav items "Croce Rossa" e "Conformità" aggiunti. Routing `renderRedCross()` e `renderCompliance()`.

### Provider ICRC WW1 — Prisoners of the First World War

- **`source_providers/icrc_ww1.py`** (nuovo): `ProviderICRCWW1` per `grandeguerre.icrc.org`:
  - 5M+ schede prigionieri 1GM, italiani inclusi.
  - `search()`: scraping HTML rispettoso, parsing link `/en/File/Details/{id}`, metadati minimi.
  - `get_metadata()`: estrae nome e metadati strutturati da pagina dettaglio.
  - `get_document()`: bloccato — `METADATA_ONLY`, no download automatico.
  - Classificazione: `METADATA_ONLY` (diritti non chiari, principio prudenziale).
  - Credit line: "© ICRC Archives — Prisoners of the First World War".
  - Registrato in `source_providers/federation.py`.

### Provider CRI Milano — Archivio Storico Croce Rossa Italiana

- **`source_providers/cri_milano.py`** (nuovo): `ProviderCRIMilano` per `cri-mi.archimista.com`:
  - Catalogo su piattaforma archimista. Corrispondenza dispersi/scomparsi 2GM.
  - `search()`: parsing risultati archimista (fonds/units/items).
  - `get_metadata()`: estrae titolo, segnatura, metadati strutturati.
  - `get_document()`: bloccato — `REQUEST_REQUIRED`, contattare archivio.
  - Classificazione: `REQUEST_REQUIRED` (documento su richiesta).
  - Contatto: archivio@crimi.it.
  - Registrato in `source_providers/federation.py`.

### API Croce Rossa

- **`GET /api/rc/red-cross/search?q=...&source=all|icrc_ww1|cri_milano`**: ricerca simultanea nei provider Croce Rossa.
- **`GET /api/rc/red-cross/{provider}/{record_id}`**: dettaglio record da fonte Croce Rossa (solo metadati).

### Migrazione SQLite → PostgreSQL (Supabase)

- **`db_adapter.py`** (nuovo): adapter layer trasparente SQLite/PostgreSQL:
  - Rileva `DATABASE_URL` da env. Se `postgresql://` → PostgreSQL, altrimenti SQLite (retrocompatibile).
  - `PostgresConnection`: wrapper psycopg2 con `RealDictCursor` per compatibilità `sqlite3.Row`.
  - Conversione automatica: `?` → `%s`, `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`, `PRAGMA` → no-op.
  - `executescript()` con split statement + conversione AUTOINCREMENT.
- **`migrate_to_pg.py`** (nuovo): script migrazione completo:
  - `--dry-run`: solo schema, no dati.
  - `--schema-only`: creazione tabelle (69 tabelle, conversione tipi).
  - `--data-only`: migrazione dati in batch (`--batch-size=5000`, `ON CONFLICT DO NOTHING`).
  - `--full`: schema + dati + indici + FTS + verifica conteggi.
  - `--table=nome`: singola tabella.
  - FTS5 virtual tables skipate, ricreate con tsvector + GIN + trigger.
  - Verifica conteggi SQLite vs PostgreSQL alla fine.
- **`database.py`**: `get_conn()` supporta entrambi i backend.
- **`search_service.py`**: `search_entities()` supporta FTS5 (SQLite, `bm25()`) e tsvector (PostgreSQL, `ts_rank()` + `plainto_tsquery()`). `get_fts_stats()` adattato.
- **`db_init_fts.py`**: `run_migration()` crea FTS5 su SQLite o tsvector+GIN+trigger su PostgreSQL.
- **`.env.example`** (nuovo): template configurazione con istruzioni Supabase.
- **`requirements.txt`**: aggiunto `psycopg2-binary>=2.9.0`.
- **App startup** (`app.py`): `seed_source_policies()` eseguito al boot.

### Architettura compliance

```
Fonte esterna → Provider (search/get_metadata) → ComplianceGate.evaluate()
  → ALLOW / ALLOW_WITH_LIMITATIONS / REQUIRE_REVIEW / REQUIRE_AUTHORIZATION / DENY
  → Log in compliance_decisions
  → Review queue se necessario
  → Autorizzazione registrata se richiesta
```

### Principi applicati

- **Privacy by design**: metadati minimi, no copia documenti senza titolo legittimo.
- **Minimizzazione dati**: no indirizzi moderni, recapiti familiari, codici fiscali, dati sanitari dettagliati.
- **Separazione consultazione/acquisizione/riproduzione**: link diretto ≠ download autorizzato.
- **Supervisione umana**: AI propone, non decide. Revisione obbligatoria per omonimie, conflitti, dati sanitari, pubblicazione.
- **Trasparenza matching**: ogni punteggio spiegabile con campi, valori, pesi, conflitti.
- **Tracciabilità**: ogni decisione registrata con regola, motivo, policy, utente, data.
- **Principio prudenziale**: `RIGHTS_UNKNOWN` → metadato minimo + link diretto + nessuna copia.

---

## 2026-07-22 (notte 2) — Scopri Candidati: ricerca in tutti i DB storici + import

### Backend: scoperta e importazione candidati (`rc_api_ext.py`)
- **`GET /api/rc/discover-candidates?q=...`**: ricerca simultanea in 9 fonti storiche del DB:
  - `internati` (20K IMI), `caduti_albooro` (342K), `decorati_nastroazzurro` (280K), `decorati` (1.3K), `caduti_ministero` (162K), `caduti_cwgc` (506K), `fonti_indice` (35K), `fondi_archivistici` (4.8K), `documenti_nara_t315`.
  - Ricerca multi-token (AND tra token, OR tra colonne) su tutti i campi rilevanti di ogni tabella.
  - Per ogni risultato: fonte, record_id, dati completi, flag `already_imported` con `rc_candidate_id` se gia' presente.
  - Risultati ordinati: non importati prima, poi per fonte.
- **`POST /api/rc/discover-candidates/{source}/{record_id}/import`**: crea candidato RC da record storico:
  - Mappa automaticamente i campi (cognome, nome, grado, luogo nascita, residenza, reparto, matricola, luogo morte, conflitto).
  - Crea anche record in `rc_sources` collegato al candidato con riferimento alla fonte originale.
  - Note interne con provenienza, sorte, decorazione, URL.
  - Se candidato gia' esistente (match cognome+nome), restituisce `already_exists: true` con l'ID esistente.
  - Audit log automatico.
- **`DELETE /api/rc/practices/{pid}`**: nuovo endpoint con cascade su documenti, versioni, checklist, scadenze, comunicazioni, pacchetti.

### Frontend: pagina Scopri Candidati (`templates/rc.html`)
- **Nav item "Scopri"** aggiunto nella navbar tra Dashboard e Candidati.
- **`renderDiscover()`**: pagina con:
  - Campo ricerca + bottone "Cerca" con loading state.
  - Descrizione fonti cercate (IMI 20K, Albo d'Oro 342K, Nastro Azzurro 280K, ecc.).
  - Tabella risultati con: fonte (tag colorato per tipo), nominativo, dati (grado, reparto, luogo, sorte, decorazione), stato (Importato/Nuovo), azione (Apri/Importa).
  - Bottoni colorati per fonte: IMI=accent, Albo d'Oro=accent-2, Nastro Azzurro/decorati=success, Ministero=warning, altri=neutral.
- **`importCandidate(source, recordId)`**: chiama API import, mostra toast, apre il dettaglio candidato.
- **`discoverSearch()`**: chiama API con debounce, gestisce loading state.

### Frontend: dashboard estesa con conteggi reali (`rc_api.py`, `templates/rc.html`)
- **`/dashboard` API**: aggiunti 6 conteggi reali da DB: `total_practices`, `total_practice_docs`, `total_descendant_contacts`, `total_institutional_contacts`, `total_communications`, `total_ai_analyses`.
- **`renderDashboard()`**: sezione generale espansa da 4 a 12 KPI con dati reali.
- **`loadDashboard()`**: chiama `/dashboard` + `/dashboard-ext` in parallelo.

### Frontend: link nella pagina principale (`templates/index.html`)
- Sostituito link `/1gm` (rimosso) con `/riconoscimenti` nella navbar del sito principale.

### Test: cleanup automatico (`_test_ext.py`)
- Aggiunta sezione **14. Cleanup** che elimina tutti i record creati dal test dopo l'esecuzione.
- 28/28 test passati con DB pulito.

### Verifica
- Ricerca "ALMONTI": 4 risultati (3 Albo d'Oro + 1 IMI deceduto).
- Import ALMONTI Giuseppe (Albo d'Oro id=192): candidato 102 creato con grado, note, URL.
- AI analysis su candidato importato: 9 onorificenze, top Croce al Merito di Guerra 51%.
- Ricerca "Rossi": 15 risultati da Albo d'Oro con nominativi reali (ROSSI ETTORE, ALBANESE SCRIBANI ROSSI UMBERTO, ecc.).

## 2026-07-22 (notte) — Percorso Riconoscimenti: contatti, documenti, AI cross-check, dashboard estesa

### Frontend: tab Contatti con aggiunta manuale contatti discendenti
- **`templates/rc.html`**: Riscritto `renderCandidateContacts` con sezione **Contatti discendenti** (tabella con nome, parentela, email, PEC, telefono, stato verifica, consenso, fonte) + bottone **"+ Aggiungi contatto"** che apre modal con tutti i campi (nome, cognome, rapporto parentela, email, PEC, telefono, fonte, stato verifica, consenso, ecc.).
- Funzioni JS: `createDescContact`, `deleteDescContact`, `editDescContact` per CRUD completo via API.
- Sezione **Tentativi di contatto** mantenuta con tabella esistente.

### Frontend: tab Pratiche con upload documenti + pratiche estese
- **`templates/rc.html`**: Riscritto `renderCandidateAdminCases` con tre sezioni:
  - **Pratiche estese**: lista con stato, protocollo, ente, date + bottone **"+ Nuova pratica"** (modal con 11 campi).
  - **Documenti di pratica**: tabella con titolo, categoria, versione, stato verifica, **data caricamento**, **data aggiornamento** + bottoni verifica/archivia/elimina + **"+ Carica documento"** (modal con upload file, categoria, metadati, livello riservatezza).
  - **Pratiche legacy**: existing admin cases mantenute.
- Funzioni JS: `createExtPractice`, `uploadPracticeDoc`, `verifyDoc`, `archiveDoc`, `deleteDoc`.
- `loadCandidate` estesa per fetch parallela di `descContacts`, `extPractices`, `practiceDocs`.

### Frontend: dashboard estesa con KPI operativi
- **`templates/rc.html`**: `loadDashboard` ora chiama in parallelo `/dashboard` + `/dashboard-ext` e mergea i risultati.
- `renderDashboard` riscritta con 3 sezioni KPI:
  - **Generale**: candidati totali, fonti, tipi riconoscimento, pratiche.
  - **KPI Operativi**: da verificare, concessi, valutazioni pendenti, discendenti da contattare, documenti mancanti, comunicazioni bozza.
  - **Pratiche**: in preparazione, pronte revisione, trasmesse, concluse, integrazioni aperte, respinte, scadenze <30gg, comunicazioni da approvare.
  - KPI con border-left colorato per priorità (rosso=urgente, giallo=attenzione, verde=ok, blu=info).

### AI Analysis: cross-check su 9 fonti storiche del DB
- **`rc_ai_analysis.py`**: Nuova funzione `_cross_check_sources()` cerca cognome+nome in 9 tabelle:
  - `caduti_albooro` (342K), `internati` (20K), `decorati_nastroazzurro` (280K), `decorati` (1.3K), `caduti_ministero` (162K), `caduti_cwgc` (506K), `fonti_indice` (35K), `fondi_archivistici` (4.8K), `documenti_nara_t315`.
- **Processo logico**: sezione **3d. CROSS-CHECK SU FONTI STORICHE DEL DATABASE** con dettaglio match per ogni fonte.
- **% di concessione**: boost/penalty basati sui match (IMI +10%, Albo d'Oro/Nastro Azzurro +8%, Caduti Ministero +5%, NARA T315 +5%, fonti archivio +3%, nessun match -5%).
- **Fattori favorevoli/sfavorevoli**: ogni match diventa fattore esplicito.
- **Raccomandazioni**: sezione **6. Verifiche su fonti storiche** con suggerimenti specifici.

### AI Analysis: documenti di pratica nella valutazione
- **`rc_ai_analysis.py`**: `_get_candidate_full` recupera anche `practice_documents`, `ext_practices`, `descendant_contacts`.
- **Processo logico**: sezioni **3b. Documenti di pratica** e **3c. Pratiche estese**.
- **% di concessione**: boost per documenti verificati (+10 se 3+, +5 se 1+), boost per foglio matricolare (+5), penalty per non verificati (-5).
- **Fattori**: stato documenti in favorevoli/sfavorevoli.
- **Raccomandazioni**: sezione **5. Documenti di pratica** con suggerimenti specifici.

### Backend: fix minori
- **`rc_api_ext.py`**: `archive_practice_document` accetta body vuoto (`Body(default={})` invece di `Body(...)`).

### Test
- 27/27 test passati (`_test_ext.py`).
- AI analysis verificata su candidati reali: AGOSTI VASCO (5 match Nastro Azzurro, 45 fondi archivistici, 1 NARA T315), BLUM GIULIO (2 Nastro Azzurro, 1 caduti Ministero), BONDI DOMENICO (1 Nastro Azzurro, 4 caduti Ministero, 2 NARA T315).

## 2026-07-22 (sera) — Nuovo modulo: Percorso Riconoscimenti

### Modulo completo per identificazione candidati a riconoscimenti storici

**File nuovi:**
- **`auth.py`**: Autenticazione session-based (bcrypt + sessioni SQLite), 6 ruoli con permessi differenziati (admin, ricercatore, revisore, genealogista, operatore, discendente), middleware FastAPI (`require_auth`, `require_role`, `require_permission`), endpoint login/logout/me, creazione utente default admin/admin.
- **`rc_schema.py`**: 14 tabelle DB con prefisso `rc_` (candidates, historical_events, sources, recognition_types, recognition_assessments, family_persons, kinship_links, contact_attempts, descendant_cases, administrative_cases, audit_log, state_transitions, invitations, documents). Seed catalogo iniziale con 12 tipi di riconoscimento (Medaglia d'Oro/Argento/Bronzo Valor Militare, Valor Civile, Croce di Guerra, Merito di Guerra, OMRI, ecc.). Tutte con `procedura_attiva='da_verificare'`.
- **`rc_state_machine.py`**: State machine con 25 stati (BOZZA → ... → PRATICA_ARCHIVIATA), transizioni validate, permessi per transizione, audit log automatico, storico transizioni.
- **`rc_api.py`**: Router FastAPI con ~40 endpoint: auth, candidati CRUD, fonti CRUD + upload, eventi storici, valutazioni, genealogia, contatti con approvazione, casi discendenti, pratiche amministrative, catalogo riconoscimenti, dashboard, audit log, portale discendente pubblico (via token invito), modulo pubblico "Riconosci questo nominativo?", generazione fascicolo PDF.
- **`rc_dossier.py`**: Generazione fascicolo PDF con reportlab (16 sezioni: copertina, indice, dati identificativi, cronologia, relazione storico-documentale, riconoscimento ipotizzato, inquadramento normativo, genealogia, elenco fonti, pratiche). Ogni affermazione collegabile a fonte.
- **`templates/rc.html`**: Frontend SPA con login, dashboard (KPI, candidati per stato), elenco candidati con filtri, dettaglio candidato con 8 tab (dati, fonti, eventi, valutazione, genealogia, contatti, pratiche, cronologia), catalogo riconoscimenti, audit log. Design system coerente con sito esistente.
- **`tests/test_rc_master.py`**: 25 test (auth, state machine, schema, privacy, dossier, workflow completo). Nessun mock, DB temporaneo isolato.
- **`docs/PERCORSO_RICONOSCIMENTI.md`**: Documentazione tecnica e operativa completa.

**File modificati:**
- **`app.py`**: Import auth/rc_schema/rc_api, init tabelle in lifespan, route `/riconoscimenti`, mount router.
- **`requirements.txt`**: Aggiunto `bcrypt>=4.0.0`, `reportlab>=4.0.0`.
- **`tests/_helpers.py`**: Registrati `auth` e `rc_schema` in `MODULES_WITH_SCHEMA_INIT`.

**Privacy by design:**
- Dati persone viventi non esposti (data_nascita, luogo_nascita oscurati quando visibilita_limitata=1)
- Contatto mediato con approvazione umana obbligatoria
- Portale discendente accessibile solo via token invito
- Audit log completo per ogni azione
- Il sistema non attribuisce mai riconoscimenti (espressioni: "potenziale candidato", "riconoscimento ipotizzato", "procedura potenzialmente praticabile")

**Test:** 277 passed, 1 skipped, 0 failed (intera suite progetto).

## 2026-07-22 (pomeriggio) — Integrazione indexing_rules in tutti gli import

### Script di import nominativi (10 moduli)
- **`caduti_ministero.py`**: `titlecase_name` su cognome/nome/paternita/maternita, `clean_toponym` su comune_nascita/luogo_sepoltura, `is_empty_value` su nazione_decesso.
- **`caduti_cwgc.py`**: `normalize_age` su campo eta (sez. 1.4.11), `titlecase_name` su nome/cognome, `clean_toponym` su cimitero/paese_cimitero.
- **`caduti_albooro.py`**: `titlecase_name` su nominativo/paternita, `clean_toponym` su comune_attuale/luogo_morte.
- **`caduti_bologna.py`**: `titlecase_name` su nome/paternita, `clean_toponym` su luogo_nascita/luogo_dimora/luogo_morte.
- **`caduti_sardi.py`**: `titlecase_name` su cognome/nome/paternita, `clean_toponym` su luogo_nascita/comune_residenza/luogo_morte.
- **`caduti_francia_ww1.py`**: `clean_toponym` su lieu_naissance/lieu_deces/lieu_deces_suite/lieu_transcription.
- **`decorati.py`** (ISTORECO): `titlecase_name` su cognome/nome, `clean_toponym` su comune_nascita/comune_residenza/luogo_morte/luogo_cattura/luogo_internamento.
- **`decorati_nastroazzurro.py`**: `is_empty_value` sostituisce check manuale 'nd'/'ND', `titlecase_name` su nome.
- **`import_fonti_personali.py`**: `_normalizza_nome` delega a `normalize_match_key` (prima regex autonoma).
- **`import_personal_sources.py`**: `_normalize_name` delega a `normalize_match_key` (prima `.strip().lower()`).

### Moduli di analisi
- **`audit_cross_db.py`**: `normalize_text`/`normalize_name`/`is_empty` delegano a `indexing_rules` (prima implementazione autonoma con regex e set placeholder duplicato).
- **`events.py`**: `match_eventi_per_internato` applica `clean_toponym` al testo prima del keyword matching, migliorando recall su toponimi qualificati.

### Indicizzazione varianti "O" (sez. 1.4.5)
- **`linker.py`**: nuovo helper `_save_persona_with_variants` che espande i nomi con varianti "O" (es. "Giuseppe O Pino") in entità separate, tutte collegate allo stesso record. Sostituite tutte le chiamate `save_entita("persona", ...)` in `build_links` con il nuovo helper.

### Fix grafi SVG (event delegation)
- **`templates/index.html`**: sostituito `onClick="${() => ...}"` (stringa letterale stringificata nell'SVG, click non funzionante) con attributi `data-graph-idx` sui cerchi + handler delegato `onGraphSVGClick` sui container div. Fix applicato a tutti e 4 i grafi: eventi (`buildGraphSVG`), luoghi (`buildGraphLuoghiSVG`), paesi (`buildGraphPaesiSVG`), soldati (`buildGraphSoldatiSVG`).

### Migrazione in-place dataset esistenti
- Script temporaneo `_migrate_normalize.py` (eseguito e rimosso): applicato `titlecase_name` e `clean_toponym` ai record esistenti di 7 tabelle (caduti_ministero, caduti_cwgc, caduti_albooro, caduti_bologna, caduti_sardi, decorati, decorati_nastroazzurro). **6.381 record aggiornati su 1.347.135 totali, 0 errori, 0 record cancellati**. Nessun dato archiviato perso.

## 2026-07-22 — Regole di indicizzazione Antenati/FamilySearch

### Nuovo modulo (`indexing_rules.py`)
- Implementate le **"Linee guida per l'indicizzazione"** (portale Antenati — Direzione Generale Archivi / FamilySearch, ed. 9 luglio 2024) come **single source of truth** per la normalizzazione anagrafica. Ogni funzione cita la sezione del manuale:
  - `normalize_match_key` (sez. 1.3.1.1/1.3.2): chiave di matching minuscola, spazi collassati, punteggiatura rimossa tranne apostrofi/trattini interni; accenti preservati (2.4.2); placeholder → vuoto (1.3.1.1.4).
  - `is_empty_value` (1.3.1.1.4/1.3.8.2): riconosce "N.N.", "Enne", "sconosciuto"...
  - `strip_titles` (1.4.6): rimuove titoli iniziali ("signor", "don"...).
  - `expand_or_variants` / `fold_variants` (1.4.5): gestione varianti separate da "O" (oppure).
  - `titlecase_name` (1.3.7): casing con preposizioni del cognome e apostrofi/Mc (D'Amico, McGregor, Da Vinci).
  - `clean_toponym` (1.4.9.1): rimuove qualificatori ("frazione di", "comune di"...) mantenendo eccezioni ("Città di Castello"); non modernizza (1.3.1.2.1).
  - `normalize_age` (1.4.11): arrotonda per difetto, <1 anno → 0, "nato morto" → 0, intervalli → prima età, età assente → None.

### Integrazione pipeline (rimozione doppioni)
- `database._normalize_name`, `linker._norm`, `research_to_index._normalize_name` ora **delegano** a `indexing_rules.normalize_match_key` (prima tre implementazioni duplicate).
- `search_service._normalize_query`: rimuove titoli e placeholder dai termini prima della query FTS5, migliorando il recall.

### Test
- `tests/test_indexing_rules.py`: 40 nuovi test sugli esempi del manuale. Suite: **251 passed, 1 skipped** (l'unico fallimento in run completa è un problema di isolamento del test `test_source_locator`, che passa isolato — non correlato).

## 2026-07-21 (sera) — Fix crash frontend, provider AI per-tab e modalità parallela

### Frontend (`templates/index.html`)
- **Fix crash React #231**: il link "Albo ↗" nella tabella Caduti aveva `onClick="event.stopPropagation()"` come **stringa letterale**, passata a React come prop `onClick` di tipo string → crash che bloccava il mount dell'intera UI (da cui tutti i warning `{{ }}` never resolved e l'errore sul `value` del number input pagina caduti). Sostituito con handler funzione `onAlboClick` sugli item.
- **Fix 400 su report cronologico**: il nome evento era ricavato solo da `data.EVENTS[activeId]` (assente per eventi 1GM caricati dinamicamente). Ora usa `_eventDossier.event.name` come fonte primaria in `generateChronologicalReport`, `generateEventReport` e `sendEventChatMessage`, con guard se vuoto.
- **Toggle Specialista/Parallelo** per i report evento: la modalità parallela compone le risposte di tutte le AI (Perplexity, OpenAI, Anthropic, Mistral) a confronto in un'unica scheda.

### Backend (`event_research_engine.py`, `biography.py`, `app.py`)
- **Provider specialista per-tab**: rimosso il default forzato `provider="mistral"` dagli endpoint `/api/event/report` e `/api/event/report/{tab}`, così entra in azione la mappatura per-tab (Panoramica→Perplexity, Fonti→Anthropic, Punti di vista→OpenAI, Cronologia→Mistral) con fallback Perplexity→OpenAI→Anthropic→Mistral.
- **Modalità `parallel`**: nuovo parametro `mode` in `research_event()` che interroga tutti i provider in `ThreadPoolExecutor` sulla stessa ricerca e restituisce `providers_results`.
- **Filtro rilevanza fonti locali**: `_is_relevant()` scarta i falsi positivi del match full-text (es. fonti WWII agganciate a eventi WWI).

### Diagnosi
- **502 `/api/fonte/generate-images`**: verificato con chiamata reale che `gpt-image-1` risponde 200 OK — il 502 è specifico della fonte (metadata mancanti o parsing JSON prompt), non un bug di codice/chiave. Da riprodurre con il `source_id` esatto.

### Server
- Riavvio uvicorn su `http://127.0.0.1:8123` (risolto socket orfano da worker `multiprocessing-fork`). Commit `c71848b`, `eedf042`, `a8ee657` pushati su `helvetiquant/lettere_dal_fronte`.

## 2026-07-21 — Fix URL Albo d'Oro e progress bar AI

### Backend (`events.py`, `app.py`, `caduti_albooro.py`)
- **Fix link "Albo ↗" per caduti**: `detail_url` memorizzato come relativo (`DettagliNominativi.aspx?id=...`) veniva erroneamente risolto sul dominio locale (`127.0.0.1:8123`) causando 404.
- `events.normalize_albo_url()`: helper che converte URL relativi in assoluti prependendo `https://www.cadutigrandeguerra.it/`; applicato in `get_eventi_1gm_caduti`, `get_graph_soldati_cluster`, `api_caduto_detail` e nei `caduto_info` di `api_decorato_detail`.
- `caduti_albooro.py`: lo scraper ora salva `detail_url` e `img_url` già assoluti tramite `urllib.parse.urljoin(BASE, href)`.

### Frontend (`templates/index.html`)
- **Barra progresso percentuale per report AI**: durante la generazione di "Report Convergenze Fonti AI" e "Report Cronologico AI" viene mostrata una barra colorata con lo stato in percentuale (`_eventReportProgress`, `_chronoReportProgress`).

### Verifica
- `GET /api/events/1gm/battaglia_del_carso/caduti?limit=1`: restituisce `detail_url` corretto come `https://www.cadutigrandeguerra.it/DettagliNominativi.aspx?id=...`.

### Test suite (`tests/`)
- Eseguita suite completa: **220 passed, 1 skipped**.
- Fix `tests/test_project_health.py`: esclusi `.venv/` e `.git/` dalla scansione degli import per evitare falsi positivi su pacchetti installati.
- Fix `tests/test_fonti_risorse_master.py`: conteggio `SCRAPER_ALLOWED_DOMAINS` aggiornato a 14.
- Fix `tests/test_soldier_dashboard.py`: mock `federated_search` arricchito con `score` e `direct_url` per superare i filtri di `_get_external_sources`.

### Documentazione
- `README.md`: aggiunta sezione "AI nel frontend" con pulsanti Dossier/Immagini AI e progress bar sui report AI.

## 2026-07-20 — Rimozione frontend 1GM dedicato

### Frontend
- **Rimosso il sito web dedicato alla Prima Guerra Mondiale** (`/1gm`):
  - eliminato `templates/PRIMA_Guerra/` (index.html, voci-data-1gm.js);
  - eliminato `templates/voci-data-1gm.js` e `templates/index-1gm.html`;
  - rimosse le route FastAPI `/1gm` e `/voci-data-1gm.js` da `app.py`;
  - rimosso `tests/test_frontend_1gm.py`.
- **Unificazione frontend comune**: `templates/index.html` rimane l'unico punto di accesso per Prima e Seconda Guerra Mondiale.
- **Dati 1GM intatti**: nessun database `.db` eliminato; record, tabelle e API `/api/events/1gm` restano invariati.

## 2026-07-20 — Fix tab evento Caduti/Decorati e AI buttons su risultati ricerca

### Backend (`events.py`, `event_query_engine.py`)
- **Normalizzazione nome evento**: fix per ID URL-friendly con underscore (`battaglia_del_carso` → `Battaglia del Carso`) nei lookup di `find_event`, `get_eventi_1gm_caduti`, `get_eventi_1gm_decorati` e `get_internati_per_evento`.
- **Case-insensitive fallback**: i fallback dopo sostituzione underscore usano `UPPER(nome)` e `UPPER(value)` nelle query SQLite, risolvendo il mismatch tra `battaglia del carso` e `Battaglia del Carso`.
- **Endpoint verificati**: `/api/events/1gm/battaglia_del_carso`, `/.../caduti`, `/.../decorati` restituiscono ora i dati corretti (caduti: 45869, decorati: 36339 per Battaglia del Carso).

### Frontend (`templates/index.html`)
- **Stili pre-calcolati**: spostate tutte le espressioni dinamiche da inline `style` a proprietà JS pre-computate (`confBarStyle`, `dotStyle`, `labelStyle`, `cardStyle`, `linkStyle`, `bubbleStyle`, `rowStyle`), riducendo i falsi positivi del linter CSS.
- **AI buttons su risultati ricerca**: aggiunti bottoni `Dossier AI` e `Immagini AI` sulle card persona nella home search, con handler che aprono il dossier e lanciano la generazione.
- **`generateSoldierBio` / `generateSoldierImages`**: estese per accettare un `id` opzionale, permettendo la generazione direttamente dalla lista risultati.

### Server
- Riavvio del backend FastAPI/uvicorn su `http://127.0.0.1:8123` con `--reload`.

## 2026-07-20 — Ricerca universale e tab Internati WW2

### Backend (`events.py`, `app.py`)
- **`search_events`**: nuova funzione per cercare eventi curati WW2 per nome, descrizione o keyword.
- **`/api/search`**: include ora anche la sezione `events` con gli eventi curati trovati.
- **`get_internati_per_evento`**: aggiunto fallback di lookup per nome abbreviato o completo parziale, così l'endpoint funziona sia con "Operazione Achse" che con il nome esteso.

### Frontend (`templates/index.html`, `templates/PRIMA_Guerra/index.html`, `templates/voci-data.js`)
- **Tab Internati evento**: `hasInternati` ora è `true` anche quando il conteggio statico dell'evento indica internati (`src._stats.internati`), quindi il tab compare immediatamente per eventi WW2 con internati collegati.
- **`searchLive`**: popola `events` dai risultati `/api/search`; cerca "Operazione Achse" in home restituisce l'evento curato.
- **`loadEvents1gm`**: nuova funzione in `voci-data.js` per caricare eventi canonici 1GM+WW2 anche nel template PRIMA_Guerra.
- **Scheda internato in PRIMA_Guerra**: `openDossier` per subject `imi_*` carica `loadSoldierDossier` come già avveniva nel template generico.

### Test (`tests/test_api.py`)
- Aggiunti test reali (fixture DB temporaneo) per:
  - ricerca universale che include eventi curati;
  - ricerca "Gaiaschi Luigi" che trova internati;
  - endpoint `/api/events/.../internati` che restituisce internati per l'evento Operazione Achse.

## 2026-07-20 — Fix tab Fonti e anteprima file nel lightbox

### Backend: fix encoding nome evento per internati (`events.py`)
- **`get_internati_per_evento`**: decodifica `+` come spazio prima del lookup dell'evento, per allinearsi al frontend che usa `encodeURIComponent(name.replace(/\s+/g, '+'))`. Senza questo fix l'endpoint restituiva sempre 0 internati per eventi con spazi nel nome.

### Frontend: tab Fonti e lightbox (`templates/PRIMA_Guerra/index.html`, `templates/index.html`)
- **Fix `loadExternalSources`**: ora filtra per `fonte_id` quando disponibile e popola correttamente `access` (`locale`/`online`/`richiesta`) e `url` (`url_documento` o `url_pagina`). Prima il mapping mancava di questi campi, quindi i pulsanti "Apri file" / "Apri originale" non venivano mai attivati.
- **Fix pulsanti evento Fonti**: aggiunti flag booleani `hasCatalogoUrl` e `hasFileUrl` con validazione `http(s)://` per evitare link vuoti/non validi nel tab "Fonti archivistiche collegate all'evento".
- **Lightbox file preview**: il lightbox mostrava solo un placeholder; ora:
  - visualizza **immagini** (`<img>`) per URL che terminano in `.jpg/.png/.webp/...` o `data:image`;
  - visualizza **PDF** in `<iframe>` per URL `.pdf` o `data:application/pdf`;
  - mantiene il placeholder solo quando non c'è anteprima;
  - il pulsante "Apri sul sito dell'archivio" usa l'URL completo (anche se relativo).
  - **Nota tecnica**: gli elementi `<img>` e `<iframe>` vengono iniettati tramite `sc-html` per evitare che il browser tenti di caricare i placeholder `{{ ... }}` come URL reali (404).
- **Immagini AI**: stesso fix `sc-html` per evitare 404 su `{{ aim.image_base64 }}`.

### Backend: CORS (`app.py`)
- Aggiunto `CORSMiddleware` per permettere al browser preview/proxy di caricare asset JS/CSS dal server locale senza blocchi cross-origin.

## 2026-07-20 — Tab Internati WW2, Ricerca server-side, Scheda internato, Record Luigi Gaiaschi

### Backend: endpoint internati (`app.py`, `events.py`)
- **`GET /api/events/{event}/internati`**: parametro `search` aggiunto; filtro SQL LIKE su cognome, nome, grado, luogo_nascita, residenza, luogo_cattura, luogo_internamento, sorte.
- **`GET /api/internati/{rid}/detail`**: scheda dettagliata internato con fonti collegate via `record_links` e fallback per soggetti/persone in `fonti_indice`.
- **Fix** `api_internato_detail`: corretta query `record_links` (`to_id` invece di `from_id`) per recuperare fonti collegate; evitati match generici solo per nome.
- **Indici SQLite** su `imi_internati.db`: creati indici per `cognome`, `nome`, `luogo_internamento`, `luogo_cattura`, `sorte`, `luogo_nascita` per ottimizzare ricerche su grandi dataset.

### Frontend: tab Internati e modale (`templates/PRIMA_Guerra/index.html`, `templates/index.html`)
- **Tab "Internati"** visibile negli eventi che hanno internati; tab con tabella, campo ricerca server-side debounce 350ms, paginazione "Carica altri 50".
- **Modale internato**: campi specifici WW2 (luogo nascita, residenza, luogo cattura, data cattura, luogo internamento, arbeitskommando, mansione, sorte, data, matricola).
- **JS**: `_internatiFilter`, `setInternatiFilter`, `_searchInternatiServer`, `loadMoreInternati`, `openSoldatoModal` esteso a tipo `internato` con endpoint `/api/internati/{id}/detail`.
- **Moduli `voci-data.js` e `voci-data-1gm.js`**: `loadEventDossier` ora carica direttamente `/api/events/{event}/internati` con totale.

### Dati: inserimento record Luigi Gaiaschi (`imi_internati.db`)
- Inserito internato **Luigi Gaiaschi** (id `22808`):
  - Nato a **Nibbiaño (Bergamo)**, **9 gennaio 1912**.
  - Catturato in **Grecia** il **12 settembre 1943** dopo l'armistizio dell'8 settembre.
  - Evento: **Operazione Achse e internamento militare italiano (1943-1945)**.
  - **Divergenza fonti** documentata: fonti italiane indicano Belgrado; fonti dell'Asse indicano Grecia (confermata).
- Inserite 2 fonti in `fonti_indice` e collegate tramite `record_links`:
  - Fonti italiane: cattura a Belgrado (divergenza, confidence 0.5).
  - Fonti dell'Asse: cattura in Grecia (confermata, confidence 0.9).
- Inserita entità corrispondente in `entita` per ricerca globale.

### Testing
- **`/api/events/Operazione+Achse.../internati?search=Gaiaschi`**: ✅ total=1, record id 22808.
- **`/api/internati/22808/detail`**: ✅ has_fonti=true, 2 fonti corrette, luogo cattura Grecia.

## 2026-07-19/20 — Scheda soldato, Ricerca server-side, Fix bug

### Backend: endpoint scheda soldato (`app.py`, `events.py`)
- **`GET /api/caduti/{id}`**: scheda dettagliata caduto con paternità, classe, comune, causa morte, decorazioni collegate, documenti, fonti archivistiche, eventi collegati.
- **`GET /api/decorati/{id}`**: scheda dettagliata decorato con info caduto, eventi collegati.
- **Parametro `search`** in `GET /api/events/1gm/{event}/caduti` e `/decorati`: filtro SQL LIKE su nominativo, grado, reparto, luogo, anno (caduti) / cognome, nome, arma, decorazione, anno (decorati). Permette ricerca su tutti i 45.869 caduti del Carso, non solo sui primi 50 caricati.

### Frontend: modale scheda soldato + ricerca (`templates/PRIMA_Guerra/index.html`, `templates/index.html`)
- **Modale scheda**: cliccando nome caduto/decorato si apre dialog con tutti i dati anagrafici, decorazioni, eventi, documenti, fonti.
- **Campo di ricerca** sopra lista Caduti e Decorati con debounce 350ms → chiama API con `&search=` per filtrare lato server.
- **Nom cliccabili**: evidenziati in colore accento con `cursor:pointer`.
- **Stato JS**: `_soldatoModal`, `_cadutiFilter`, `_decoratiFilter` + metodi `openSoldatoModal`, `closeSoldatoModal`, `setCadutiFilter`, `setDecoratiFilter`, `_searchCadutiServer`, `_searchDecoratiServer`.

### Fix bug
- **Duplicate export `loadEventDossier`** in `voci-data-1gm.js`: rimosso dalla re-export list (era già `export async function`).
- **404 `image_base64`**: immagini AI senza data URI valido → aggiunto check `hasImage`/`noImage` con fallback "Nessuna immagine" in entrambi i template.
- **File temp `_check_schema2.py`** rimosso.

### Testing
- **`/api/caduti/109`** (ALBANI BIAGIO): ✅ 200 OK, nominativo corretto.
- **`/api/decorati/28`** (ABATE ANDREA): ✅ 200 OK, 13 eventi collegati.
- **Ricerca Carso + Gaiaschi**: ✅ Total 1, GAIASCHI GIUSEPPE (id 102126, luogo_morte: Carso).
- **Server**: avviato su `127.0.0.1:8001` con uvicorn `--reload`.

## 2026-07-18 — Report cronologico AI, Analisi fonti AI, Generazione immagini AI

### Backend: nuovi prompt e funzioni (`biography.py`)
- **`CHRONOLOGICAL_REPORT_PROMPT`**: prompt per report cronologico narrativo discorsivo che ricostruisce l'evento in ordine temporale.
- **`SOURCE_ANALYSIS_PROMPT`**: prompt per analisi dettagliata di una singola fonte (metadati + contenuto + contesto evento).
- **`IMAGE_PROMPT_GENERATOR`**: prompt che fa generare all'AI 3-5 prompt in inglese per `gpt-image-1`, con regole di accuratezza storica.
- **`generate_chronological_report()`**: raccoglie fonti verificate e genera report cronologico con fallback provider.
- **`analyze_single_source()`**: analisi singola fonte con metadati DB, contenuto in cache, e contesto evento.
- **`generate_source_images()`**: pipeline completa — genera prompt AI → `gpt-image-1` → fallback Stability AI → caching in `source_fetch_cache`.
- **`_generate_image_dalle()`**: generazione immagini via REST API diretta (bypass SDK OpenAI v1.3.7 incompatibile con httpx). Usa `gpt-image-1` (DALL-E 3 non disponibile con la key corrente).
- **`_generate_image_stability()`**: fallback Stability AI SD3.
- **`_save_generated_image()`** / **`_check_cached_images()`** / **`get_cached_images()`**: caching immagini in `source_fetch_cache` (tabella DB), evita rigenerazione.
- **Fix**: `generate_event_report` ora usa `preferred=None` invece di `"mistral"` per fallback naturale dei provider.
- **Fix**: escape parentesi graffe `{{` `}}` in `IMAGE_PROMPT_GENERATOR` per compatibilità con `.format()`.

### Backend: nuovi endpoint API (`app.py`)
- **`POST /api/event/report/chronological`**: genera report cronologico AI per evento.
- **`POST /api/fonte/analyze`**: analisi AI di singola fonte (richiede `source_id`, `event_name`).
- **`POST /api/fonte/generate-images`**: generazione 3-5 immagini AI per fonte con caching.
- **`GET /api/fonte/{source_id}/images`**: recupera immagini cached per fonte.

### Frontend: nuovi bottoni e UI (`templates/index.html`, `templates/PRIMA_Guerra/index.html`)
- **Tab Cronologia**: bottone "Genera Report Cronologico AI" con display report e gestione errori.
- **Tab Punti Vista**: etichetta aggiornata da "Genera Report" a "Genera Report Convergenze Fonti AI".
- **Tab Fonti**: per ogni fonte, due nuovi bottoni:
  - "Analizza con AI" — genera riassunto strutturato della fonte.
  - "Genera Immagini AI" — genera 3-5 immagini fotorealistiche con barra progresso.
- **Barra progresso** durante generazione immagini (CSS animato).
- **Display immagini** in grid con titolo, prompt, e click per ingrandire.
- **Metodi JS**: `generateChronologicalReport()`, `analyzeSource()`, `generateSourceImages()` in entrambi i template.
- **`renderVals`** aggiornato con stati per-fonte (`_sourceAnalysis`, `_sourceImages`) e report cronologico.

### Testing (18 luglio 2026)
- **Server**: avviato su `127.0.0.1:8000`, 22 eventi caricati, tutti endpoint rispondono.
- **`/api/event/report/chronological`** (Caporetto): ✅ 200 OK, provider Mistral, report cronologico generato.
- **`/api/fonte/analyze`** (source_id=55487, Caporetto): ✅ 200 OK, provider Mistral, analisi generata.
- **`/api/fonte/generate-images`** (source_id=55487, Caporetto): ✅ 5 immagini generate con `gpt-image-1`.
- **Caching**: ✅ seconda chiamata restituisce `from_cache: true`, 5 immagini cached.
- **`/api/fonte/55487/images`**: ✅ 200 OK, 5 immagini recuperate da cache.
- **Fix API key**: aggiornata `OPENAI_API_KEY` nel `.env` con nuova key (`sk-proj-sE-PetMIS0L...`).
- **Fix modello immagini**: DALL-E 3 non disponibile → switch a `gpt-image-1` (disponibile con key corrente).
- **Fix SDK OpenAI**: `openai==1.3.7` incompatibile con `httpx` → REST API diretta con `requests`.

## 2026-07-18 — Fetcher documenti (Gallica/TNA/IWM), Tab Fonti frontend, Chat AI report

### Nuovi fetcher documenti 1GM (`archivio_documenti.py`)
- **`fetch_gallica_sru()`**: Gallica BnF SRU API — foto, manoscritti, periodici francesi WWI. Parsing XML SRU/OAI-DC, estrazione ARK identifier, link diretto al viewer Gallica. Nessuna chiave API richiesta.
- **`fetch_tna_discovery()`**: The National Archives Discovery API — war diaries WO 95. Endpoint pubblico REST JSON, estrazione reference, coveringDates, description. Link diretto a Discovery.
- **`fetch_iwm_collections()`**: Imperial War Museum Collections API — private papers, diari, foto WWI. Endpoint pubblico REST JSON, estrazione id, title, displayDate, thumbnail.
- **Pipeline `documenti_1gm`** aggiornata in `mass_index.py`: 8 step totali (seed + IA + LoC + Wikimedia + Europeana + Gallica + TNA + IWM), stats finali per tipo e provider.

### Frontend: tab Fonti event-centric (`templates/index.html`, `templates/PRIMA_Guerra/index.html`)
- **Nuovo tab "Fonti"** nel dossier evento: visibile solo per eventi (sc-if `dossier.isEvent`), mostra lista fonti archivistiche con titolo, archivio, tipo_fonte, link a catalogo e documento.
- **Tab Caduti e Decorati** aggiunti al template generico `index.html` (erano già presenti in `PRIMA_Guerra/index.html`).
- **Stato tab** (`tabFontiActive`, `tabFontiClass`, `onTabFonti`) aggiunto a `renderVals` in entrambi i template.
- API verificata: `/api/events/1gm/{name}` restituisce 30 fonti per evento (es. Prigionia: 689 fonti totali, 30 mostrate).

### Chat AI follow-up report (`app.py`, `templates/index.html`, `templates/PRIMA_Guerra/index.html`)
- **`POST /api/event/chat`**: endpoint per domande di follow-up dopo il report AI. Riceve `event_name`, `message`, `report` (contesto), `history` (storico chat), usa `_call_with_fallback` (Mistral → Perplexity → GPT).
- **UI chat** sotto il report: area messaggi scrollabile con bubble user/AI, textarea + pulsante Invia, indicatore "AI sta scrivendo…", Enter per inviare.
- **Stato chat** (`_eventChatMessages`, `_eventChatInput`, `_eventChatLoading`) e metodi (`sendEventChatMessage`, `setEventChatInput`, `eventChatKeyDown`) in entrambi i template.

## 2026-07-17 — Integrazione event-centric: API, biography, frontend

### Grafo event-centric esteso (`_gen_event_links.py`, `eventi_1gm.db`)
- **Eventi WW2 aggiunti** (7 nuovi): Operazione Achse, Eccidio di Cefalonia, Campagna di Russia (ARMIR), Battaglia di Tobruk, Mauthausen e Gusen, Lavoro forzato nel Reich, Battaglia di Cassino.
- **Totale eventi canonici**: 22 (15 WW1 + 7 WW2).
- **Documenti collegati**: 1→13 (match multi-evento, campi estesi: title, description, place, creator, date_text, provider_collection).
- **Internati WW2 collegati**: 12.759 link `internato_ww2` (match luogo_cattura/luogo_internamento ↔ eventi WW2).
- **Confidence decorati variabile**: 0.6 per eventi ≤1 anno, 0.4 per 2 anni, 0.3 per >2 anni.
- **CWGC WW1**: 1 match (cimiteri inglesi in Francia, match "Tobruk").
- **caduti_ministero**: 0 match (dati luogo_sepoltura/nazione_decesso tutti vuoti).
- **Totale event_links**: 911.832 (688.607 decorati, 188.791 caduti, 12.759 internati, 1.703 fonti, 13 documenti, 1 CWGC).

### API endpoints (`app.py`, `events.py`)
- **`GET /api/events/1gm`**: lista eventi canonici con stats aggregate (caduti, decorati, documenti, fonti, internati, CWGC).
- **`GET /api/events/1gm/{event_name}`**: dossier completo evento via `event_query_engine.query_event()`.
- **`GET /api/events/1gm/{event_name}/caduti`**: caduti paginati per evento (temp table per large ID sets).
- **`GET /api/events/1gm/{event_name}/decorati`**: decorati paginati per evento.
- **`GET /api/events`** aggiornato: include sia eventi curati WW2 che eventi 1GM.

### Biography integration (`biography.py`)
- **`_event_centric_context()`**: estrae dati strutturati da `event_query_engine` (caduti, decorati, documenti, fonti con URL) e li inserisce nel prompt AI per `generate_event_biography()`.
- Fonti event-centric con URL aggiunte a `verified_sources` e `online_sources` restituiti al frontend.

### Frontend (`templates/PRIMA_Guerra/`)
- **`loadEvents1gm()`**: carica eventi canonici da `/api/events/1gm`, merge con eventi statici (fallback).
- **`loadEventDossier()`**: carica dossier completo (caduti, decorati, documenti, fonti) da API.
- **Dossier evento**: tab "Caduti" e "Decorati" con tabelle paginate, stats summary su overview, descrizione evento.
- **Eventi dinamici**: 22 eventi reali sostituiscono i 3 eventi statici di fallback.

### Endpoint unificato + subject_type event_1gm (`app.py`)
- **`GET /api/events/{event_name}`**: endpoint unificato con dispatch automatico — prova prima `eventi_1gm.db` (event-centric), poi fallback su eventi curati WW2 (fonti multilaterali). Posizionato dopo le route specifiche `/api/events/1gm/*` per evitare conflitti.
- **`POST /api/biography`** con `subject_type="event_1gm"`: usa `generate_event_biography()` con tutti i dati event-centric (event_query_engine + memory_router + federated_search + web search).
- **Fase 1.6 (entita → eventi)**: verificato e scartato — la tabella `entita` con `tipo='evento'` contiene eventi individuali dei soldati ("deceduto - il 13-2-1945"), non eventi storici canonici. 0 match con 168 alias/keyword degli eventi.

## 2026-07-16 — Validazione AI record_links, Grafo event-centric, Report DB completo

### Validazione AI record_links (`_validate_links_ai.py`)
- **5 cicli di validazione** completati, 20 link casuali per ciclo, 200 validazioni totali.
- **AI provider funzionanti**: Mistral (`mistral-small-latest`) e Perplexity (`sonar`) via REST API diretta (`requests`, nessun SDK).
- **AI provider non disponibili**: OpenAI (key scaduta), Anthropic (modello `claude-3-5-haiku-20241022` deprecato/non accessibile), Gemini (quota esaurita).
- **Risultati**: 93% INVALID, 5% VALID, 2% UNCERTAIN. L'AI giudica i link `stesso_evento_luogo` come non validi: due soldati morti nello stesso luogo e anno non sono necessariamente nello stesso evento specifico (stessa battaglia/stesso giorno).
- **DB separato** `validazioni_ai.db` per evitare lock con pipeline in corso. Main DB `imi_internati.db` aperto in read-only (`PRAGMA query_only=ON`).
- **Helper `_parse_json()`**: parsing robusto di risposte AI con wrapper markdown, estrazione JSON da testo libero, fallback UNCERTAIN.
- **Script stato** `_val_status.py`: report rapido validazioni per provider e ciclo.

### Grafo event-centric (`_gen_event_links.py`, `eventi_1gm.db`)
- **Nuovo paradigma**: invece di collegare soldato-soldato (grafo `record_links`, 93% falsi positivi), sistema event-centric dove ogni evento canonico aggrega soldati, documenti, fonti, diari, immagini.
- **Tabella `eventi_1gm`** (15 eventi canonici): Caporetto, Isonzo, Carso, Piave, Vittorio Veneto, Asiago, Grappa, Pasubio, San Michele, Prigionia, Fronte Macedone, Fronte Albanese, Col di Lana, Monte Nero, Settore Tolmino.
  - Ogni evento: nome, date inizio/fine, luogo, aliases (varianti nome), keywords per ricerca text-match, descrizione.
- **Tabella `event_links`** (799.103 link):
  - 188.198 `soldato_caduto`: caduti Albo d'Oro collegati a eventi per match `luogo_morte` ↔ aliases evento.
  - 610.905 `soldato_decorato`: decorati Nastro Azzurro collegati a eventi per match `anno_decorazione` ↔ range date evento (confidence 0.3, da rifinire).
- **DB separato** `eventi_1gm.db` (123 MB) per evitare lock con pipeline in corso.
- **Top eventi per caduti**: Prigionia 84.315, Carso 45.869, Isonzo 13.859, Caporetto 13.244, Asiago 11.624.
- **TODO**: linking documenti (`archivio_documenti`) e fonti (`fonti_indice`) agli eventi non ancora completato (errore colonna `id` risolto con `rowid`, da rilanciare).

### Report DB completo (`_report_all_db.py`)
- **Script report** che analizza tutti i 3 DB: schema, record, colonne, dati distinti, link, grafo.
- **DB principale** `imi_internati.db`: 1.790 MB, 43 tabelle, 11.621.745 record totali.
- **DB eventi** `eventi_1gm.db`: 123 MB, 3 tabelle, 799.120 record.
- **DB validazioni** `validazioni_ai.db`: 0,1 MB, 200 record.
- **Tabelle principali**: caduti_albooro (342.555), caduti_cwgc (506.446), caduti_ministero (162.646), decorati_nastroazzurro (279.832), internati (20.464), entita (688.738), collegamenti (2.349.417), fonti_indice (35.660), archivio_documenti (218), archivio_fonti (1.153).
- **Encoding fix**: `sys.stdout` wrapper UTF-8 per output Windows cp1252.

### Ispezione schema (`_inspect_schema.py`)
- Verifica colonne reali di tutte le tabelle, sample record, ricerche text-match ("Caporetto", "Isonzo").
- Scoperto: `archivio_documenti` non ha colonna `id` (usa `rowid`), 29 soldati con luogo_morte "Caporetto", 13.859 con "Isonzo", 12 fonti_indice con "Caporetto" nel titolo.

---

## 2026-07-15 — Pipeline 1GM, Fix CWGC, Scoring, URL Ministero Difesa

### Pipeline indicizzazione 1GM (`mass_index.py`)
- **3 nuove pipeline 1GM**: `pipeline_soldati_1gm()`, `pipeline_eventi_1gm()`, `pipeline_luoghi_1gm()`.
- CLI: `python mass_index.py soldati_1gm|eventi_1gm|luoghi_1gm|all_1gm [--limit N]`.
- **Eventi 1GM**: 525 query (25 eventi fissi + 500 dal DB), 111 fonti salvate. Completata in 7504s.
- **Luoghi 1GM**: 320 query (20 luoghi fissi + 300 dal DB), 7 fonti salvate. Interrotta al 50%.
- **Soldati 1GM**: 1000 soldati (500 Albo d'Oro + 500 Nastro Azzurro), 65 fonti salvate. Interrotta al 10%.
- **Totale fonti 1GM nuove**: 194 (109 OPAC SBN, 76 WikiTree, 7 Internet Archive, 2 CWGC).
- **Collegamenti 1GM nuovi**: 139 (127 caduti_albooro, 12 entita).
- Provider interrogati: europeana, internetarchive, gallica, hathitrust, googlebooks, cwgc, memoiredeshommes, iwm_lives, wikitree, internetculturale, ussme, antenati.

### Fix scoring `source_providers/base.py`
- `score_source()`: aggiunto scoring per cue `evento` (match token in titolo/descrizione/URL, +0.10 per token).
- `score_source()`: aggiunto scoring per cue `periodo` (match anni 1914-1918 in testo, +0.08 per anno).
- `MIN_SCORE` abbassato da 0.45 a 0.25 in `mass_index.py` (eventi/luoghi hanno meno token match rispetto a persone).

### Fix nomi provider in `mass_index.py`
- `internet_archive` → `internetarchive`, `memoire_des_hommes` → `memoiredeshommes`, `google_books` → `googlebooks`.
- Aggiunto `internetculturale` alle pipeline eventi_1gm e luoghi_1gm.

### Fix CWGC in `database.py`
- `stats_ww1()`: CWGC filtrato per `guerra='World War 1'` → 35.400 record (prima 506.446, includeva WW2).
- `search_ww1()`: stessa filtro applicato alla ricerca su `caduti_cwgc`.
- Caduti 1GM totali corretti: 594.971 (prima 1.066.017).

### Fix URL Ministero Difesa
- `config.py`: `onorcaduti.difesa.it` (dominio morto) → `www.difesa.it` in `SCRAPER_ALLOWED_DOMAINS`.
- `templates/voci-data.js`: URL `nascaduti.difesa.it/Ricerca` → `www.difesa.it/Il_Ministero/CadutiInGuerra/Pages/RicercaCaduti.aspx`.

### DB stats finali
- fonti_indice totali: 35.624 (era 35.430, +194 fonti 1GM).
- collegamenti totali: 2.349.397 (dopo dedup).
- 0 duplicati, 0 orfani.

### Generazione collegamenti OpenGraph 1GM
- **5 passaggi di generazione**:
  1. `caduti_albooro` → luogo (123k nuovi), unita (217k nuovi)
  2. `decorati_nastroazzurro` → evento (58.769 nuovi, match anno decorazione 1915-1918)
  3. `caduti_cwgc` WW1 → luogo (35k), unita (34k)
  4. `caduti_francia_ww1` → SKIP (colonne luogo/anno non compatibili)
  5. `caduti_ministero` → SKIP (colonne luogo/data non compatibili)
- **Approccio batch in-memory**: entita pre-caricate in dict Python + indice inverso per token (O(1) lookup).
- **5 verifiche**:
  1. Conteggio per tabella/tipo — 33 combinazioni attive.
  2. Duplicati — 0 (rimossi 1.108.627 duplicati preesistenti).
  3. Orfani — 0 (rimossi 2 collegamenti con entita_id inesistente).
  4. Congruenza eventi 1GM — 314k caduti_albooro, 58k decorati, 23k sardi, 54 bologna.
  5. Sample validazione — match corretti (es. "deceduto - 1917" per decorati, luoghi reali per caduti).
- **Collegamenti totali dopo cleanup**: 2.349.397 (era 3.458.024 prima di dedup).

### Archivio documenti 1GM (`archivio_documenti.py`)
- **Nuovo modulo**: archiviazione metadati + deep link di foto/diari WWI (modello Voci dal Fronte).
- **Schema `archivio_documenti`**: 19 campi (provider, external_id, doc_type, title, source_url, thumbnail_url, iiif_manifest, raw_json, ecc.).
- **18 collezioni curate** seedate: Europeana 1914-1918, LoC WWI Prints, IA diari, Gallica BnF, IWM, TNA WO 95, Archivio Diaristico Nazionale (Pieve Santo Stefano), 14-18.it ICCU, Wikimedia Commons, Fondazione Ansaldo, Mémoire des Hommes, AWM, Museo Guerra Rovereto, ACS, Oxford WW1 Poetry.
- **4 fetcher API**: Internet Archive (advancedsearch), Library of Congress (loc.gov JSON), Wikimedia Commons (MediaWiki API), Europeana (Search API con key).
- **Fetcher aggiuntivo**: `fetch_wikimedia_commons()` per foto WWI da Wikimedia.
- **Pipeline `documenti_1gm`** in `mass_index.py`: `python mass_index.py documenti_1gm`.
- **Nessun file binario scaricato**: solo metadati + link diretto alla fonte (deep link).
- **Integrato in `imi_internati.db`** via `database.get_conn()`.

### Grafo record-to-record (`record_links`)
- **Nuova tabella `record_links`**: link diretti tra record (soldati, documenti, fonti) con tipo e confidence.
- **156.694 link** generati:
  - 142.594 `stesso_evento_luogo` (caduti_albooro: soldati morti stesso anno+luogo, star topology)
  - 11.222 `stesso_anno_decorazione` (decorati_nastroazzurro: decorati stesso anno)
  - 2.878 `documento_evento` (caduti_albooro ↔ archivio_documenti: match anno+luogo)
- **Anti-omonimia**: match nomi su cognome+nome completo, non solo cognome.
- **Passo 4-5 (fonte_personale)**: 0 match — le 35.660 fonti sono prevalentemente tedesche/internazionali (Bundesarchiv, Arolsen), non contengono nomi italiani.
- **Script**: `_gen_record_links.py` (6 passi + verifiche).

## 2026-07-14 — Frontend 1GM, Test Harness, Link navigazione, Email MiC

### Frontend Prima Guerra Mondiale (`templates/PRIMA_Guerra/index.html`, `templates/voci-data-1gm.js`)
- Banner immagine 1GM aggiunto e successivamente rimosso su richiesta utente.
- Titolo pagina aggiornato: "Voci dal Fronte — Tutte le Voci, un'Unica Storia" (override `heroTitle2` in `voci-data-1gm.js` per IT/EN/DE/FR).
- Sezione `externalSources` (fonti esterne collegate) verificata: campi titolo, ente_titolare, licenza, tipo_risorsa, url_pagina, url_documento, hasDocument, note_copyright.
- Funzione `loadExternalSources()` chiama `/api/fonti-risorse` e popola `_externalSources` nel dossier.

### Link navigazione (`templates/index.html`)
- Aggiunto link "Prima Guerra Mondiale" nella nav bar del frontend generale, punta a `/1gm`, stile accento grassetto.

### Test Harness — Master file (`tests/test_fonti_risorse_master.py`)
- **83/83 test PASS** - zero failure, zero errori.
- Consolidamento di tutti i test fonti_risorse in un unico file master.
- Fix: DB temp file (Windows file locking), robots_cache clearing tra test, mock HTTP encoding string, copyright regex.
- Copertura: config, DB CRUD/constraints, scraper HTML/metadata/pipeline, robots.txt, domain allowlist, search service, API, security, E2E.

### Test Frontend 1GM (`tests/test_frontend_1gm.py`)
- **50/50 test PASS** - server reale, nessun mock.
- 6 classi: HTML (17), JS (13), Isolation (4), API Integration (8), Data Consistency (4), Assets (5).
- Verifica isolamento: nessun riferimento IMI/WW2/NARA/prigionia nel frontend 1GM.

### Mock utils (`tests/utils/`)
- `mock_db.py`: temp file SQLite DB con `get_test_conn()` e `cleanup_test_db()`.
- `mock_http_client.py`: `MockResponse` con encoding string, `patch_requests_get()`.
- `fake_html_sources.py`: 11 pagine HTML fittizie per test scraper.
- `fake_robots_txt.py`: 6 varianti robots.txt.
- `fake_domain_allowlist.py`: domini autorizzati/bloccati.

### Email MiC
- Template email preparato per Comitato Grande Guerra (Roma) e Soprintendenza ABAP Liguria.
- Richiesta parere favorevole/autorizzazione ex art. 3 punto 3.1 Bando Grande Guerra 2026/2027.
- Contatti: `comitatograndeguerra@cultura.gov.it` / PEC `mbac-comitatograndeguerra@mailcert.beniculturali.it`.
- Contatti Liguria: `sabap-liguria@cultura.gov.it` / PEC `sabap-liguria@pec.cultura.gov.it`.

### Regole memorizzate
- Regola: non usare mock nei test se non strettamente necessario (notificare e spiegare motivo).
- Regola: non creare file di test separati per la stessa feature - un solo master test.

---

## 2026-07-13 — Pipeline multi-AI parallela, Report Engine, Banner, Watchdog

### Fix server (`app.py`)
- `BackgroundTasks` aggiunto all'import FastAPI → server non avviava (`NameError`).
- Endpoint `/api/internati/{rid}/links` ora funzionante.

### Banner frontend (`templates/index.html`, `templates/header_banner.png`)
- Banner sostituisce SVG logo+titolo: immagine full-width sopra navbar sticky.
- CSS: `width:100%; aspect-ratio:5/1; object-fit:cover; max-height:240px` — responsive da mobile a 4K.
- Nuovo banner italiano generato (ratio 5:1, 2480×480px target): soldato in trincea, aereo, carro armato, lettera "cara mamma", titolo "Voci dal Fronte" + sottotitolo archivio.
- Banner cliccabile → torna alla home.

### Pipeline indicizzazione massiva (`mass_index.py`)
- 4 pipeline indipendenti: `soldati`, `reparti`, `eventi`, `luoghi`.
- `soldati`: query cognome+nome su 13 provider (Arolsen, Bundesarchiv, NARA, CWGC, Europeana, IA, HathiTrust, Gallica, TNA, AWM, Antenati, WikiTree, IWM).
- `reparti`: 10.348 unità militari da DB entita — query + varianti DE/EN su NARA/Bundesarchiv/TNA/USSME/IA.
- `eventi`: 16 eventi fissi ad alto valore + fino a 500 dal DB — query IT+EN, include giornali d'epoca (Europeana Press, IA Newspapers, Gallica/BnF, HathiTrust, Google Books).
- `luoghi`: 14 lager fissi (Stalag XVII-B, Mauthausen, Gusen, ecc.) + fino a 300 dal DB.
- ThreadPoolExecutor 4 worker, upsert idempotente su `fonti_indice`, `collegamenti` con colonne reali (`tabella_origine`, `record_id`).
- Endpoint `POST /api/mass-index/start` + `GET /api/mass-index/status`.

### Pipeline multi-AI parallela (`mass_index_parallel.py`)
- 7 agenti in parallelo su task distinti:
  - **OpenAI GPT-4o-mini** → soldati A–F: arricchisce query con varianti nome (grafia tedesca, errori trascrizione).
  - **Anthropic Claude Haiku** → soldati G–L: estrazione varianti + entity linking.
  - **Gemini 1.5 Flash** → soldati M–R: varianti nome per archivi internazionali.
  - **Mistral Small** → soldati S–Z: varianti EN per archivi angloamericani.
  - **Perplexity (web access)** → eventi/battaglie: trova URL diretti a fonti primarie via ricerca web live.
  - **LM Studio Qwen2.5-3B** → reparti: varianti nome unità — completamente opzionale, fallback silenzioso se offline.
  - **Scraper puro** → luoghi/lager: federated_search senza AI.
- Detection automatica LM Studio: `_lmstudio_available` flag, timeout 8s, skip immediato se offline.
- Endpoint `POST /api/mass-index/start-parallel`.

### Report Engine (`report_engine.py`)
- Query libera (evento/unità/luogo/persona) → report narrativo strutturato.
- Flusso: entità DB → soldati collegati → fonti archivistiche → contesto AI → narrative.
- Fallback chain AI: OpenAI → Anthropic → Mistral.
- Auto-detection tipo da keyword (battaglia/operazione → evento, divisione/reggimento → unità, lager/stalag → luogo).
- Arricchimento per soldati: fonti dirette per ciascuno dalla `fonti_indice`.
- Endpoint `GET /api/report?q=...&tipo=auto`.

### Watchdog pipeline (`pipeline_watchdog.py`)
- Monitor ogni 5 minuti: verifica server HTTP, pipeline status, log errori.
- Auto-fix: riavvio uvicorn se server down, riavvio pipeline se bloccata/in errore.
- Log su `pipeline_watchdog.log`.

### Fix DB schema
- Corretti nomi colonne `collegamenti`: `soggetto_tabella` → `tabella_origine`, `soggetto_id` → `record_id`, `tipo` → `tipo_collegamento`.

---

## 2026-07-12 (sera) — Test live Arolsen, refinement TNA/IA, popolamento DB

### Arolsen test live validato
- Flusso ASP.NET confermato: `BuildQueryGlobalForAngular` → session cookie → `GetCount` (7 persone) → `GetPersonList` (7 record GAIASCHI Arturo, nato 13/02/1902) → `GetArchiveList` (1 unità archivistica).
- 40 nuovi record inseriti in `fonti_indice` (query: Gaiaschi, Rossi, Bianchi, Ferrari, Italian internee).

### TNA refinement
- Scoperto: l'API REST Discovery (`/API/search/v1/records`) ignora il parametro `q` (restituisce sempre 42M record non filtrati). Il portale web è dietro AWS WAF (202 challenge).
- Implementato: filtro client-side per periodo WW2 (`numStartDate`/`numEndDate` 1939-1946 + fallback `coveringDates`), filtro pertinenza militare (keyword matching), fetch per reference WO specifiche (WO 392, WO 304, WO 208, WO 309, FO 916).
- 4 record fallback registrati in `fonti_indice`.

### Internet Archive refinement
- Aggiunti filtri temporali Solr: `date:[1940 TO 1946]`, `mediatype:(texts)`, `sort:downloads desc`.
- Strategy 2: broad search con termini italiani (`internati militari italiani`, `prigionieri di guerra italiani`, `campo prigionieri italia`) se query principale < 5 risultati.
- 19 nuovi record inseriti (Nazi Concentration Camps, Tactical And Technical Trends, newsreels, newspapers 1940-41).

### Popolamento DB
- **63 nuovi record** totali in `fonti_indice` da provider live.
- `fonti_indice` totale: 21.062 record (Arolsen 158, TNA 20.025, Internet Archive 66).

---

## 2026-07-12 (pomeriggio) — Consolidamento import, provider reali, README, cleanup

### Consolidamento script import (`import_fonti_personali.py`)
- Unificati `import_lettere_personali.py` + `import_personal_sources.py` in `import_fonti_personali.py`.
- Funzione `import_all(dry_run)` esegue entrambe le migrazioni (lettere OCR + fonti narrative Desktop).
- Entity linking condiviso (`_upsert_persona` con parametro `fonte_tabella` dinamico).
- Modulo verificato: import corretto, nessun errore.

### Provider federation — 6 provider da stub a reali (`source_providers/providers.py`)
- **Arolsen Archives (ITS)**: implementato endpoint reverse-engineered `ITS-WS.asmx` (`collections-server.arolsen-archives.org`). Flusso: `BuildQueryGlobalForAngular` → `GetCount` → `GetPersonList`/`GetArchiveList` con gestione sessioni ASP.NET (cookie-keyed). Estrae LastName, FirstName, PrisonerNumber, PlaceBirth, Dob, Signature.
- **Bundesarchiv**: implementato Invenio REST API (`/api/records` con `q`, `size`, `sort=bestmatch`). Parsing hits con metadata, files.entries per digital objects. Fallback a link catalogo + open data.
- **SHD/Mémoire des Hommes**: parsing HTML strutturato del portale (`/fr/search.php`). Estrazione link `/fr/article.php` con titoli da anchor text. Fallback a basi dati specifiche (WW1/WW2 morts).
- **Archivportal-D (DDB)**: implementato DDB REST API ufficiale (OpenAPI 3.0). Endpoint `/search` con OAuth API key (`DDB_API_KEY` da env). Parametri: query, rows, offset, sort, time_fct. `get_metadata()` via `/items/{id}`.
- **LAC (Library and Archives Canada)**: implementato Canadiana API (`search.canadiana.ca/search?fmt=json`) come endpoint primario + LAC Collection Search come fallback. Parsing docs con id, title, pubmin.
- **Internet Culturale (OPAC SBN)**: migliorato con endpoint OPAC SBN JSON (`/opacmobilegw/search.json`), parsing briefRecords con BID, titolo, autore, pubblicazione, anno. Fallback con regex BID dal HTML. `get_metadata()` via `/opacmobilegw/bid/{id}.json`.

### Documentazione (`README.md`)
- README completamente riscritto: architettura con diagramma ASCII, flusso Research-to-Index, tabella moduli, schema DB completo, tabella provider federation (16 provider con API e autenticazione), API principali, configurazione env.

### Cleanup script scratch
- Rimossi **59 file** con prefisso `_` (`_test_`, `_check_`, `_run_`, `_status_`, `_fix_`, `_bench_`, `_db_`, `_inspect_`, `_search_`, `_start_`, `_verify_`).
- File .py totali: da 107 a 48 (−55%).
- Verificato: nessun modulo di produzione importava gli script rimossi. Tutti i moduli si importano correttamente dopo il cleanup.

---

## 2026-07-12 — Verifica DB live, fix ricerca multi-parola, Tab Gaps, test biography

### Verifica DB live (`imi_internati.db`, 1.4 GB)
- `PRAGMA quick_check` e `PRAGMA integrity_check`: **ok** — DB integro, il "malformed" segnalato era artefatto di mount.
- `lettere_personali`: 1 record (migrazione da `ocr_lettere.db` confermata).
- `fonti_narrative`: 40 record, 69 collegamenti (migrazione Desktop confermata).
- Linker completato: **688.738 entità** (560.133 persone, 102.319 luoghi, 14.952 eventi, 10.348 unità), **4.832.063 collegamenti**.
- `fonti_indice`: 20.999 fonti (TNA 20.021, Internet Culturale 145, Arolsen 118, Bundesarchiv 118, Archivportal-D 116, LAC 116, SHD 116, Internet Archive 47).
- `caduti_cwgc`: 506.446 record (WW2: 452.395, WW1: 35.400, non classificati: 18.651).
- `research_subjects`: 118, `research_subject_sources`: 1.431, `research_gaps`: 472.

### Fix ricerca multi-parola (`database.py`)
- `_where_like_clause()`: cambiato da **OR puro tra token** a **AND tra token, OR tra colonne**.
- Prima: "Gaiaschi Giuseppe" → 14 internati, **0 contenevano "gaiaschi"** (tutti falsi positivi da "Giuseppe").
- Dopo: "Gaiaschi Giuseppe" → **0 falsi positivi** negli internati, 2 caduti pertinenti, 12 fonti_narrative pertinenti.
- "Luigi Gaiaschi" → 0 falsi positivi (prima 14), 6 fonti_narrative pertinenti.
- Test: 130 passed, 1 failed (non correlato: `test_source_locator` unable to open DB temporaneo).

### Tab Gaps in UI (`templates/index.html`)
- Aggiunto tab "Gaps" nella barra investigativa (5° tab dopo Eventi).
- Funzione `renderGapsTab()`: chiama `GET /api/research/gaps`, renderizza card con:
  - Nome soggetto e tipo (soldier/event/unit/place)
  - Campo mancante con label localizzata italiana
  - Badge priorità colorato (high=danger, medium=warning, low=muted)
  - Provider suggerito per colmare il gap
- Integrato in `convSearch()` come step 3b (dopo renderSourcesTab, prima di renderAIResponses).
- Endpoint `/api/research/gaps` verificato: 472 gap aperti, 5 restituiti correttamente.

### Test biography end-to-end (`POST /api/biography`)
- **Soldato** (id=2451, ABALIATI): GPT-4o-mini, 0 falsi positivi, biografia narrativa con 3 fatti verificati, 19 fonti non verificate elencate, fallback non necessario, costo $0.0005.
- **Evento** ("Operazione Achse 8 settembre 1943"): GPT-4o-mini, biografia 2.365 caratteri, contesto storico corretto.
- Chiavi API confermate disponibili: OPENAI, ANTHROPIC, MISTRAL, PERPLEXITY, EUROPEANA, GEMINI.

---

## 2026-07-11 (sera) — Fix pipeline arricchimento fonti + copertura test

### Catalogazione fonti (`c741bea`)
- Catalogate **25 fonti** da `fonti_scrapabili_metadata.xlsx` in `fonti_indice` tramite `import_fonti_catalogo.py`.
- Ogni fonte include archivio, dominio, access_type, confidence, note legali/tecniche.

### Arricchimento entità (`4481266`, `093e24c`)
- `enrich_entities.py`: pipeline di arricchimento con federated_search concorrente e resume.
- Risultato reale: **20.190 internati processati**, **19.868 nuove schede** in `fonti_indice`, **0 errori**.

### Arricchimento eventi (`d326552`)
- `enrich_events.py`: 6 eventi storici curati con fonti multilaterali (Italia / Asse / Alleati).
- Registrate **28 fonti** multilaterali in `fonti_indice` (Cefalonia, Mauthausen/Gusen, Tobruk, ARMIR Russia, Operazione Achse, lavoro forzato).

### Fix di questa sessione
- `enrich_entities.py`: resume granulare per ID completato; `fetch_internati` usa `WHERE id > ?` anziché OFFSET.
- `source_providers/providers.py`: rimosso `verify=False` da TNA Discovery, Europeana, Deutsche Digitale Bibliothek (Archivportal-D) e Mémoire des Hommes.
- `import_fonti_catalogo.py`: rimossa `_extract_domain()` non utilizzata (codice morto con `NameError` latente).
- `source_locator.py`: `last_checked_at` aggiunto alla whitelist di `register_source_metadata()` e popolato in insert/update.
- `enrich_events.py`: luogo geografico reale per evento, rimosso `time.sleep(0.2)`, rimosso `import json` duplicato.
- Test: `tests/test_enrich_entities.py`, `tests/test_enrich_events.py`, `tests/test_source_providers.py::TestTLSVerification`.

---

## 2026-07-11 (pomeriggio) — Integrazione lettere personali + upload GitHub

### Unificazione DB lettere personali (TODO fix tecnico #1)
- Creata tabella `lettere_personali` in `imi_internati.db` come nuova tabella sorgente.
- Scritto e eseguito `import_lettere_personali.py` per migrare i record da `import_ocr_lettere/ocr_lettere.db`.
- Migrato **1 record**; inserimento nello star schema via `entita`/`collegamenti` (quando `mittente`/`destinatario`/`luogo` sono popolati).
- Integrata `lettere_personali` in `database.py::search_all()` e `get_all_records_for_ai()`.
- Aggiornato frontend `templates/index.html`: card in `renderCrossDBLinks()` e tabella in `renderSourcesTab()`.

### Requirements.txt (TODO fix tecnico #2)
- Aggiornato con `uvicorn[standard]`, `pydantic`, `urllib3`, `schedule` e altri pacchetti mancanti.

### Upload GitHub
- Repository: `https://github.com/helvetiquant/lettere_dal_fronte`
- Inizializzato repo locale, creato `.gitignore` per escludere `.env`, DB SQLite e file grandi.
- Commit e push del codice (DB e secret esclusi).
- Token GitHub salvato in `.env` come `GITHUB_TOKEN`.

### Architettura e dati
- `ARCHITETTURA_DB.md` aggiornato con `lettere_personali`, conteggi `entita`/`collegamenti` aggiornati, CWGC segnato come completato.
- `caduti_cwgc`: stato aggiornato a **completato** (~1.07M record, UK WW2 chiuso a 401k).

---

## 2026-07-11 — Chiusura todo + aggiornamento architettura

### Aggiornamento documentazione architettura (`ARCHITETTURA_DB.md`)
- Statistiche DB aggiornate: ~1.4 GB, 25+ tabelle, ~4.8M record totali.
- Aggiunta tabella `fonti_narrative` al Livello Sorgenti con schema, indici e pipeline di import (`import_personal_sources.py`).
- Aggiornati conteggi `entita` (~688.738 record) e `collegamenti` (~4.832.063 archi), inclusi 69 collegamenti da `fonti_narrative`.
- Aggiornata pipeline Memory Router: `fonti_narrative` e' ora uno step esplicito tra `archivio_fonti` e fallback cloud.

### Frontend
- Colore pulsante **📖 Dossier verificato** cambiato da viola (`var(--accent)`) a grigio scuro (`#374151`) con hover `#1f2937`.

### Todo list
- Tutte le voci aperte chiuse: frontend verificato via API, provider Bundesarchiv implementato, dump XML open data valutato.

---

## 2026-07-10 (sera) — Schema fonti narrative + import fonti Desktop

### Verifica DB
- `PRAGMA quick_check` su `imi_internati.db` → `('ok',)`. Proceduto con creazione schema e import.

### Fix ricerca multi-parola (continuazione)
- `database.py::search_all()` e `get_all_records_for_ai()` ora tokenizzano la query e cercano su `internati`, `menzioni`, `decorati`, tabelle `caduti_*`, `decorati_nastroazzurro`, `documenti_nara_*`.
- Verificato caso reale "Gaiaschi Giuseppe fu Luigi": ora trova record in `caduti_albooro`.

### Nuova tabella `fonti_narrative`
- Creata tabella dedicata a fonti personali/narrative dal Desktop.
- Campi: `sha256`, `nome_file`, `path_locale`, `formato`, `tipo_fonte`, `archivio`, `fondo`, `autore`, `soggetti_json`, `persone_possibili`, `titolo`, `descrizione`, `testo_ocr`, `ocr_status`.
- Indici su `tipo_fonte`, `persone_possibili`, `archivio`, `data_documento`, `ocr_status`.
- Collegamento allo star schema esistente: inserimento nodi in `entita` e archi in `collegamenti` con `tabella_origine='fonti_narrative'`.
- Script: `import_personal_sources.py` (hashing, estrazione testo .odt/.docx, OCR Mistral per PDF/JPG, import, linking).

### Fonti Desktop importate (completato)
- Directory considerate:
  - `Desktop\ARCHIVIO STORIE\STORIE IMI\`
  - `Desktop\ARO\`
  - `Desktop\1945 gaiaschi è libero!\`
  - `Desktop\rebancadatiinternatimilitariitaliani\`
  - `Desktop\racconti, storie, libro\`
- Escluse: `Desktop\DOMANDE RENZI\`, `Desktop\vaticano\`.
- Totale file rilevati: 42 (13 `.odt`, 4 `.docx`, 5 `.pdf`, 15 `.jpg`, 5 `.jpeg`).
- Import effettivo: **40 record** in `fonti_narrative` (2 duplicati saltati via sha256), **69 collegamenti** in `entita/collegamenti`.
- OCR Mistral eseguito su PDF scansionati e fotografie.

### Frontend
- Aggiornati `renderCrossDBLinks()` e `renderSourcesTab()` in `templates/index.html` per mostrare anche i risultati della tabella `fonti_narrative` (card collegamenti e tabella fonti).

### Provider Bundesarchiv
- Confermato che il catalogo Invenio è un'applicazione JSF: endpoint `/invenio/api/records` e varianti restituiscono 404; login/main.xhtml risulta non raggiungibile in modo automatico (timeout/redirect a login).
- Implementato provider realistico in `source_providers/providers.py::ProviderBundesarchiv`:
  - Prova più endpoint JSON noti (`/invenio/api/records`, `/api/records`, `/api/records/`).
  - Fallback strutturato con 3 link: Invenio online (login), Open Data DDB-Bestand (dump XML pubblico), pagina "Recherchesysteme" del Bundesarchiv.
  - Supporto opzionale a `filters['fondo_xml']` per link diretto a un file XML open data.
- Identificato dump open data `https://open-data.bundesarchiv.de/ddb-bestand/` con migliaia di file XML per fondo, potenzialmente scaricabili per ricerca offline.
- Valutazione campione `DE-1958_AR_1-VII.xml`: formato EAD (`urn:isbn:1-931666-22-9`), testo in tedesco, struttura fondo/unita'/scopecontent. Ricerca offline e' fattibile ma richiede download massivo (centinaia di file, potenzialmente diversi GB) e parsing EAD mirato ai soli fondi militari (R, RH, RM, ecc.). Per uso IMI si consiglia di partire dai fondi specifici anziche' dall'intero dump.

### File modificati/ creati
| File | Modifica |
|---|---|
| `schema_proposal_fonti_narrative.sql` | proposta + DDL tabella |
| `database.py` | `search_all()` e `get_all_records_for_ai()` includono `fonti_narrative` |
| `import_personal_sources.py` | nuovo modulo import/OCR/linking |
| `templates/index.html` | render `fonti_narrative` in collegamenti e tab fonti |
| `source_providers/providers.py` | provider Bundesarchiv: tentativi API + fallback catalogo/open data |

---

## 2026-07-10 (sera) - Dossier Verificato (biografie AI) + fix frontend + import lettere + bug ricerca multi-parola

### Dossier Verificato / Biografie AI (`biography.py`, nuovo modulo)
- Nuovo modulo `biography.py`: genera una biografia/dossier narrativo per un soldato o un evento, riusando la pipeline esistente invece di duplicarla:
  - Soldato → `soldier_dashboard.get_soldier_dashboard()`
  - Evento/query libera → `memory_router.route_query(use_cloud_fallback=False)`
- Separazione netta fonti verificate/da verificare: nel prompt entrano solo fatti locali certi, fonti locali leggibili (`archivio_fonti`/menzioni/NARA), fonti esterne gia' scaricate (`fonti_indice.fetch_status='scaricato'` + `source_fetch_cache`), e le lettere in `import_ocr_lettere/ocr_lettere.db`. Le fonti solo candidate (federated_search, `image_only_sources`) vengono elencate a parte con istruzione esplicita all'AI di non usarle nel testo.
- Fallback automatico multi-provider: gpt → claude → mistral → perplexity (stessi provider di `ai_research.PROVIDERS`), un solo tentativo riuscito per biografia invece di 4 chiamate come `research_all()`.
- Logging: `save_ai_ricerca()` con tag `[BIOGRAFIA] ...`, stesso meccanismo gia' usato da `ai_research.py` — nessuna tabella nuova, nessuna alterazione di schema.
- Endpoint: `POST /api/biography` — `{subject_type: "soldier"|"event", soldier_id?, query?, provider?}`.
- Frontend: bottone "📖 Dossier verificato" nella barra di ricerca; card dedicata (`.ai-response.dossier`) mostra provider usato, eventuale fallback e conteggio fonti non utilizzate.

### Fix frontend (`templates/index.html`)
- Bug CSS: le regole `.invest-facts`/`.fact-card`/`.source-badge` del DB View Modal sovrascrivevano silenziosamente quelle condivise (fatti verificati senza bordo verde/warning, badge fonti con dimensione sbagliata). Ora scoped sotto `#dbViewContent`.
- Aggiunte media query responsive, assenti nonostante il meta viewport: header, barra ricerca, analytics bar, modali e form ora si adattano sotto 860px/480px.
- `currentSoldierId` ora valorizzato in `convSearch()` (era dichiarato ma mai assegnato dopo il redesign a 3 tab Risposta AI/Collegamenti/Fonti).

### Import dati (sola copia, nessuna modifica ai DB esistenti)
- Copiato `C:\Users\eryma\CascadeProjects\ocr_lettere` → `imi_extractor\import_ocr_lettere\` (codice + `ocr_lettere.db` + PDF/upload). Integrita' verificata via checksum. DB tenuto separato, NON fuso in `imi_internati.db` su richiesta esplicita — interrogato in sola lettura da `biography.py` per trovare lettere che citano il cognome del soldato.

### Bug trovato (non ancora corretto)
- `database.py::search_all()` (usata da `GET /api/search`) fa `LIKE '%intera query%'` su tutta la stringa multi-parola invece di tokenizzarla: cercare "Luigi Gaiaschi" o "Giuseppe Gaiaschi" ritorna sempre 0 risultati anche quando il dato esiste. Verificato sul backup `Desktop\i backup\imi_extractor_20260707_2100\imi_internati.db`: "Gaiaschi Giuseppe fu Luigi" (caduto 1916, Carso, 1° Rgt Granatieri) e' presente in `caduti_albooro` ma introvabile con la ricerca attuale. "Luigi Gaiaschi" (IMI WW2, documenti primari sul Desktop) non risulta invece in nessuna tabella di quel backup.

### File modificati
| File | Modifica |
|---|---|
| `biography.py` | nuovo modulo |
| `app.py` | +`import biography`, +endpoint `POST /api/biography` |
| `templates/index.html` | fix scoping CSS, +media query responsive, bottone Dossier verificato, +`generateBiography()`, fix `currentSoldierId` |
| `import_ocr_lettere/` | nuova cartella (copia sola lettura di ocr_lettere) |

---

## 2026-07-10 - Research-to-Index API + Frontend Integration + Architettura Update

### Endpoint API Research-to-Index (`app.py`)
- **8 nuovi endpoint API** per Research-to-Index:
  - `POST /api/research/query` — auto-index: cerca locale → se non trova, crea soggetto + arricchisce con fonti esterne federate
  - `POST /api/research/auto-index` — forza creazione soggetto (anche se esiste in DB)
  - `GET /api/research/subjects` — lista soggetti con filtri (type, status, min_confidence, pagination)
  - `GET /api/research/subjects/{id}` — dettaglio soggetto con fonti collegate e gaps
  - `GET /api/research/subjects/{id}/dashboard` — dashboard completa con arricchimento + stats
  - `PATCH /api/research/subjects/{id}` — aggiorna status/confidence/campi (whitelist campi)
  - `GET /api/research/gaps` — lista gaps aperti con suggerimenti provider
  - `GET /api/research/stats` — statistiche Research-to-Index
- Aggiunti import `sqlite3`, `datetime`, `research_to_index as rti` in `app.py`

### Frontend Integration (`templates/index.html`)
- **`convSearch()` aggiornata**: quando search_all non trova risultati locali, chiama `/api/research/query` (auto-index) invece di `/api/source/search` diretto
- **Nuova funzione `renderResearchSubject(rtiRes, query)`**: renderizza soggetti auto-indexed con:
  - Badge stato (Non verificato / Parzialmente verificato / Verificato)
  - Fonti esterne indicizzate con score, provider, access_type
  - Subject ID e tipo soggetto
  - Messaggio esplicativo "soggetto creato automaticamente"

### Documentazione (`ARCHITETTURA_DB.md`)
- Aggiunta sezione **Research-to-Index** in Livello 6 con:
  - 3 tabelle documentate: `research_subjects`, `research_subject_sources`, `research_gaps`
  - Schema colonne, indici, record count
  - Tabella endpoint API (8 endpoint)
  - Diagramma flusso Research-to-Index
- Aggiornate **Relazioni** con research_subjects → fonti_indice, research_gaps
- Aggiornati **Indici principali** con idx_rs_*, idx_rss_*, idx_rg_*

### File modificati
| File | Modifica |
|---|---|
| `app.py` | +8 endpoint API, +import sqlite3/datetime/rti |
| `templates/index.html` | convSearch → auto-index, +renderResearchSubject() |
| `ARCHITETTURA_DB.md` | +sezione Research-to-Index, +relazioni, +indici |

---

## 2026-07-09 (notte) - Research-to-Index + WikiTree Provider + Filtro Rilevanza + Bando MiC

### Research-to-Index (`research_to_index.py`)
- **Modulo completo implementato**: auto-indexing di ricerche non trovate nel DB locale.
  - 3 nuove tabelle: `research_subjects`, `research_subject_sources`, `research_gaps`
  - Funzioni: `create_minimal_subject_from_query`, `upsert_source_locator`, `link_subject_to_source`, `update_subject_confidence`, `identify_research_gaps`, `enrich_subject_from_sources`, `auto_index_if_not_found`, `index_external_sources_for_soldier`, `get_research_stats`
  - Helper `_safe_str` per conversione sicura di valori (liste, None, int) in stringhe SQLite
  - `index_external_sources_for_soldier(soldier_id)`: prende un soldato dal DB, estrae cue, esegue ricerca federata, indicizza fonti trovate in `fonti_indice`, collega a `research_subjects`
- **Filtro rilevanza risultati**: classificazione in 3 categorie:
  - **Relevant** (name_match o score >= 0.25 con record_id): indicizzate con `confirms`/`mentions`, confidence >= 0.3
  - **Catalog ref** (stub provider, score <= 0.15): salvate come `possibly_related`, confidence 0.15
  - **Skipped** (API results non pertinenti, es. TNA ritorna record casuali): non indicizzate
  - Match cognome nel titolo/descrizione rilevato automaticamente
- **Test su 50 soldati casuali** (`test_research_to_index.py`):
  - 437 fonti indicizzate in `fonti_indice` (dedup via segnatura UNIQUE)
  - 50 research_subjects creati (12 verified, 38 partially_verified)
  - 1.174 link subject-source
  - 200 research_gaps identificati (date_start, place, unit, date_end)
  - Provider con API reali: Internet Archive (122 fonti), TNA (15), NARA (1)
  - Provider stub: 6 provider × 50 soldati = 300 riferimenti catalogo

### WikiTree Provider (`source_providers/wikitree.py`)
- **Nuovo provider genealogico** integrato nella federation layer (20° provider)
- API: `https://api.wikitree.com/api.php?action=searchPerson`
- Ricerca per nome, cognome, date, luoghi — gratuita, no auth per profili pubblici
- ~40M+ profili globali, inclusi militari WW1/WW2
- Metodi: `search()`, `get_metadata()`, `get_person_bio()`
- Confidence: 0.60-0.90 basata su match nome + date
- Test: "Rossi Mario" → 5 risultati reali con date/luoghi italiani; "Mussolini Benito" → 2 profili storici

### Modifiche a file esistenti
- **`source_providers/federation.py`**: aggiunto import e registrazione `ProviderWikiTree` (20° provider)
- **`research_to_index.py`**: refactor `index_external_sources_for_soldier` con classificazione rilevanza, catalog_refs, name_match
- **`test_research_to_index.py`**: aggiornato report con relevant/catalog/skipped/name_matches

### File creati
| File | Descrizione |
|---|---|
| `research_to_index.py` | Modulo Research-to-Index: tabelle, funzioni auto-indexing, arricchimento |
| `test_research_to_index.py` | Test su 50 soldati casuali con report dettagliato |
| `source_providers/wikitree.py` | Provider WikiTree (API genealogiche) |
| `test_wikitree.py` | Test rapido provider WikiTree |
| `analyze_rti.py` | Analisi risultati Research-to-Index nel DB |
| `CONCORSI_EUROPEI.md` | Analisi architetturale + strategia funding EU/IT |

### Bando MiC Grande Guerra 2026/2027
- Identificato bando Ministero della Cultura per patrimonio storico Prima Guerra Mondiale
- Scadenza: **15 Luglio 2026 ore 12:00** (6 giorni)
- Budget stimato: ~€400-500k per biennio (bando 2024/2025: €494.647,90 / 17 progetti finanziati su 121)
- Tipologie ammissibili per IMI Extractor: A (censimento), B (catalogazione), E (valorizzazione)
- Soggetti ammissibili: qualsiasi soggetto privato o pubblico, singolarmente o in partenariato
- Documentazione: https://grandeguerra.cultura.gov.it/documentazione/
- Contatti: comitatograndeguerra@cultura.gov.it | mbac-comitatograndeguerra@mailcert.beniculturali.it

---

## 2026-07-09 (sera) - Source Federation Layer + Dashboard Investigativa + UI riprogettata

### Nuovi sistemi implementati

- **`source_providers/` — Source Federation Layer**: sistema di federazione archivistica che integra 19 provider esterni (NARA, Antenati, CWGC, Arolsen, Bundesarchiv, SHD, TNA, Europeana, Gallica, Internet Archive, Google Books, ABMC, LAC, AWM, Archivportal-D, Internet Culturale, HathiTrust, USSME, Archivio di Stato).
  - `base.py`: interfaccia astratta `SourceProvider` con metodi `search`, `get_metadata`, `get_document`, `get_iiif_manifest`, `build_direct_link`, `register_in_db`, `fetch_with_cache`. Helper `score_source` per ranking risultati.
  - `nara.py`: provider NARA (query locale + API catalog.archives.gov).
  - `antenati.py`: provider Antenati (parsing HTML `/search-registry`, estrazione ARK, gestione WAF).
  - `cwgc.py`: provider CWGC (query locale `caduti_cwgc`).
  - `providers.py`: 16 stub provider con fallback a URL catalogo.
  - `federation.py`: registry provider, ricerca federata multi-provider, fetch on-demand con cache, statistiche.

- **`soldier_dashboard.py` — Dashboard Investigativa**: aggregazione dati soldato + fonti federate.
  - `get_soldier_dashboard(id)`: ritorna dati certi, fatti verificati, timeline, fonti locali (archivio_fonti, menzioni, NARA T315), fonti esterne (federation), entità collegate.
  - `get_soldier_sources(id)`: solo fonti (locali + esterne).
  - `analyze_sources(source_ids)`: prepara contesto minimo per AI (metadati + excerpt da cache, no download diretto AI).

- **Interfaccia UI riprogettata** (`templates/index.html`):
  - **Analytics bar** in alto: 8 celle con statistiche globali (internati, caduti, decorati, entità, archi grafo, doc archivio, provider federati, fonti indicizzate).
  - **Ricerca conversazionale** centrale: input semplice → ricerca locale (FTS5 + search_all) → se trovato, carica dashboard soldato completo → se non trovato, ricerca federata diretta.
  - **Risultati investigativi** con 5 tab: Dati Soldato (fatti verificati/non), Timeline, Fonti Locali, Fonti Esterne, Entità.
  - **Source cards**: badge disponibilità (locale/online/da_richiedere/non_accessibile), score, thumbnail, bottoni Apri/IIIF/Scarica/Analizza.
  - **Analisi AI**: selezione fonti → preparazione contesto minimo → invio ad AI.
  - Pannelli operativi esistenti collassati sotto i risultati investigativi.

### Endpoint API aggiunti
- `GET /api/providers` — lista tutti i provider federati
- `GET /api/providers/{name}` — dettaglio provider
- `POST /api/source/search` — ricerca federata multi-provider
- `POST /api/source/fetch` — fetch on-demand documento (solo domini autorizzati)
- `GET /api/source/cache` — lista file in cache
- `GET /api/source/stats` — statistiche federation layer
- `POST /api/source/reindex` — re-index metadati da provider → fonti_indice
- `GET /api/soldiers/{id}/dashboard` — dashboard investigativa completa
- `GET /api/soldiers/{id}/sources` — solo fonti per soldato
- `POST /api/sources/analyze` — prepara contesto minimo per AI

### File creati
| File | Descrizione |
|---|---|
| `source_providers/__init__.py` | Package init |
| `source_providers/base.py` | Interfaccia SourceProvider + helper |
| `source_providers/nara.py` | Provider NARA |
| `source_providers/antenati.py` | Provider Antenati |
| `source_providers/cwgc.py` | Provider CWGC |
| `source_providers/providers.py` | 16 stub provider |
| `source_providers/federation.py` | Registry + orchestrazione federata |
| `soldier_dashboard.py` | Aggregazione dashboard investigativa |

### Principi architetturali
- **Nessun documento pesante scaricato automaticamente**: il DB locale è un indice intelligente, non un repository.
- **Fetch on-demand**: solo quando l'utente richiede, solo da domini autorizzati, con cache e TTL.
- **AI non scarica direttamente**: il backend seleziona fonti, prepara contesto minimo (metadati + excerpt testuali).
- **Score-based ranking**: ogni fonte ha score 0-1 basato su match persona/luogo/data/reparto.

---

## 2026-07-09 - Archivio fonti + NARA Catalog + fix NARA parsing

### Nuovi sistemi implementati
- **`archivio_fonti.py`**: sistema archivio documenti primari (PDF/JPEG/TIFF).
  Pipeline completa: ingestione → classificazione OCR → DB metadati → query semantica → risposta con file originale.
  Tabella `archivio_fonti` con 30+ campi: hash SHA256, metadati archivistici/militari/cronologici, `ocr_status` (done/partial/skip_cursive/skip_quality), `readable`, `attendibilita_fonte`.
  Retrofit NARA T315: 1.153 frame importati con metadati completi.
- **`nara_catalog.py`**: scraper NARA Catalog API (catalog.archives.gov) per After Action Reports USA WW2 relativi all'Italia. 16 query tematiche, ~35k documenti AAR Italy. In esecuzione.
- **Fix NARA T315 parsing**: 93 frame con "Errore parsing JSON" corretti senza API. Tre strategie: rimozione commenti JS inline, chiusura JSON troncati, estrazione regex per campo. 0 errori rimanenti.

### Endpoint API aggiunti
- `GET /api/archivio` — statistiche
- `POST /api/archivio/query` — query semantica (unità, teatro, data, tipo, fondo, testo libero)
- `GET /api/archivio/file/{sha256}` — download file originale (PDF/JPEG)
- `POST /api/archivio/ingest` — upload documento con metadati JSON
- `POST /api/archivio/retrofit_nara_t315` — import NARA T315 → archivio_fonti
- `GET /api/nara_catalog`, `POST /api/nara_catalog/scrape`, `POST /api/nara_catalog/stop`

### Stato database (09/07/2026 ore 18:00)

| Tabella | Record | Note |
|---|---:|---|
| `archivio_fonti` | 1.153 | Nuovo — NARA T315 retrofit, 1.115 readable |
| `documenti_nara_catalog` | in corso | AAR USA WW2 Italy, ~35k target |

## 2026-07-09 - Status e avanzamento CWGC + probe ABMC

### Stato database (09/07/2026 ore 16:00)

| Tabella | Record | Target | % | Stato |
|---|---:|---:|---:|---|
| `caduti_cwgc` | 437.758+ | ~1.763.187 | ~24,8% | 🔄 in corso |
| `caduti_albooro` | 342.555 | ~342.555 | 100% | ✅ completo |
| `caduti_ministero` | 162.646 | ~162.646 | 100% | ✅ completo |
| `caduti_sardi` | 20.435 | ~20.435 | 100% | ✅ completo |
| `caduti_bologna` | 9.656 | ~9.656 | 100% | ✅ completo |
| `caduti_francia_ww1` | 24.279 | ~1.400.000 | 1,7% | ⏸ parziale (download manuale JS) |
| `decorati_nastroazzurro` | 279.832 | 279.832 | 100% | ✅ completo |
| `internati` | 20.464 | 20.464 | 100% | ✅ completo |
| `documenti_nara_t315` | 1.153 | 1.153 | 100% | ✅ completo |
| `decorati` | 1.286 | 1.286 | 100% | ✅ completo |
| `entita` | 327.056 | — | — | 🔄 linker in esecuzione |
| `collegamenti` | 1.325.166 | — | — | 🔄 linker in esecuzione |
| **TOTALE** | **~2.645.000** | | | |

### CWGC — fix e avanzamento
- **WW1**: completato (tutte 24 nazionalità, ~35.400 nuovi record)
- **WW2 in corso**: dopo il reset delle partizioni large (UK/Indian/Canadian/Australian), il CWGC risponde correttamente — Canadian WW2 in scraping (45.388 record, p150/4539)
- **Fix `_paginate_html`**: aggiunto retry 5× con backoff esponenziale (1.2→2.4→4.8→9.6→19.2s) e tolleranza 10 pagine vuote (era 3) per resistere a timeout transitori
- **Fix campo `guerra`**: ora passato esplicitamente da `scrape_all` a `_paginate_html` ("World War 1" / "World War 2")
- **Script `_status_cwgc.py`**: aggiornato con path assoluto e riepilogo di tutte le tabelle

### ABMC — bloccato (WAF)
- `api.abmc.gov` → 403 su tutte le richieste Python (IP restriction / WAF)
- `www.abmc.gov` → reindirizzamento a "Knowvation" CDN WAF, Angular bundle 403
- Richiede **Playwright con fingerprint browser reale** per bypassare la protezione
- Stato: ⛔ **bloccato**, richiede approccio browser headless

### Todo priorità (aggiornato)
| Task | Stato |
|---|---|
| CWGC WW2 Canadian (45k) | 🔄 in corso |
| CWGC WW2 Indian (~87k) | ⏳ in coda |
| CWGC WW2 UK (~572k) | ⏳ in coda (~24h) |
| ABMC USA (~35k) | ⛔ bloccato WAF (serve Playwright) |
| Volksbund Germania (~825k) | ⛔ bloccato (questionario personale) |
| MDH Francia (~1,4M) | ⏸ parziale (download manuale JS/Arkothèque) |

---

## 2026-07-07 (sera) - Riepilogo discorsivo della giornata

### Dati inseriti nei database oggi

La giornata di oggi ha portato all'inserimento complessivo di **oltre 900.000 nuovi record** nel database `imi_internati.db`, portando il totale da ~20.500 record (internati + decorati di partenza) a **più di 920.000 record distribuiti su 8 tabelle**, più **160.191 entità** e **659.050 collegamenti** cross-dataset.

**In dettaglio, per ogni dataset:**

**Albo d'Oro** (`caduti_albooro`): 342.555 record — completato. Si tratta del database dei caduti italiani della Grande Guerra pubblicato su cimeetrincee.it / cadutigrandeguerra.it. Lo scraper ha recuperato l'intero dataset paginando attraverso tutte le lettere dell'alfabeto e gestendo correttamente i casi di omonimia. Ogni record contiene cognome, nome, data e luogo di nascita, data e luogo di morte, grado, corpo/armata,Decorazioni.

**Caduti Ministero Difesa** (`caduti_ministero`): 162.646 record — completato. Fonte: portale "Caduti in Guerra" del Ministero della Difesa, che copre sia la 1a che la 2a Guerra Mondiale. Lo scraper ha gestito il flusso di richieste POST con paginazione interna e parametri di filtro per conflitto.

**Caduti Sardi** (`caduti_sardi`): 20.435 record — completato. Fonte: Unione Sarda / eroiecadutisardi.it. Dataset regionale con caduti sardi in tutti i conflitti.

**Caduti Bolognesi** (`caduti_bologna`): 9.656 record — completato. Fonte: Museo del Risorgimento di Bologna. Dataset locale con caduti della provincia di Bologna.

**CWGC - Commonwealth War Graves Commission** (`caduti_cwgc`): 322.486 record acquisiti su un target di ~1.763.187 (18,3%) — in corso. Lo scraper multi-nazionalità ha completato australiani, indiani, canadesi, neozelandesi, sudafricani, tedeschi, polacchi e olandesi, ed è ora sulla nazionalità più numerosa (United Kingdom, 141.650 record finora). La strategia ibrida (Export CSV per partizioni piccole, paginazione HTML per quelle grandi) ha dimostrato di scalare bene. Nazionalità acquisite: United Kingdom (141.650), Indian (71.474), Canadian (37.420), Australian (35.333), New Zealand (10.716), South African (9.608), German (6.122), Polish (4.402), Dutch (3.844), Italian (621), Greek (328), Belgian (311), Norwegian (304), Czechoslovakian (200), American (79), Russian (51), Arab World (20), Austrian (2), Finnish (1).

**NARA T315 Roll 1299** (`documenti_nara_t315`): 1.111/1.153 frame processati (96,4%) — quasi completato. OCR tramite API Mistral Pixtral-12B delle 1.156 immagini JPG del microfilm T-315 Roll 1299 (Kriegstagebücher della 117. Jäger-Division, 1943). Fix critico applicato: timeout sul client Mistral (senza il quale le chiamate API si bloccavano indefinitamente) e fix della serializzazione JSON per campi di tipo lista. Ultimo frame processato: #1156 alle 22:36.

**Internati Militari Italiani** (`internati`): 20.464 record — era già completo (fonte: Archivio di Stato di Bolzano).

**Decorati al Valor Militare** (`decorati`): 1.286 record — era già completo (fonte: ISTORECO Reggio Emilia).

### Linker cross-dataset

Il linker ha continuato a lavorare per tutta la giornata, portando il numero di **entità estratte** da 42.806 a **160.191** e i **collegamenti** da 75.771 a **659.050**. Il linker collega record delle varie tabelle (internati, caduti_ministero, decorati, menzioni, fondi_archivistici) alle entità estratte (persone, luoghi, unità militari), creando la rete di relazioni che permette di navigare trasversalmente i dataset.

Distribuzione collegamenti per tabella di origine:
- `caduti_ministero`: 355.966 collegamenti
- `internati`: 280.896 collegamenti
- `decorati`: 21.020 collegamenti
- `menzioni`: 776 collegamenti
- `fondi_archivistici`: 392 collegamenti

### Totale record nel database

| Tabella | Record | Stato |
|---|---:|---|
| `caduti_albooro` | 342.555 | ✅ completo |
| `caduti_ministero` | 162.646 | ✅ completo |
| `internati` | 20.464 | ✅ completo |
| `caduti_sardi` | 20.435 | ✅ completo |
| `caduti_cwgc` | 322.486 | 🔄 in corso (target 1.763.187, 18,3%) |
| `caduti_bologna` | 9.656 | ✅ completo |
| `documenti_nara_t315` | 1.111 | 🔄 quasi completo (target 1.153, 96,4%) |
| `decorati` | 1.286 | ✅ completo |
| `entita` | 160.191 | 🔄 linker in corso |
| `collegamenti` | 659.050 | 🔄 linker in corso |
| **Totale** | **~920.000** | |

### Infrastruttura e tool

- **Script di monitoraggio** (`status.ps1`): script PowerShell per visualizzare in tempo reale lo stato di tutti i processi di acquisizione, con percentuali, barre di progresso, PID e uptime dei processi Python attivi. Supporta modalità watch con auto-refresh.
- **File workspace** (`imi_extractor.code-workspace`): configurazione Windsurf/VS Code con task integrate per status, NARA OCR e CWGC scraper.
- **Backup DB**: `imi_internati.db` (298 MB) copiato in `C:\Users\eryma\Desktop\i backup\imi_extractor_20260707_2100\` insieme a tutti i sorgenti (47 file, 597 MB totali).
- **Fix pipeline NARA**: timeout sul client Mistral e serializzazione JSON robusta per campi lista.
- **Fix pipeline CWGC**: parametro `Page` case-sensitive, endpoint Export CSV scoperto e integrato, strategia di partizionamento per nazionalità × guerra × anno × mese, resume via `cwgc_progress.json`, dedup via `cwgc_id UNIQUE`.

---

## 2026-07-07 (sera) - Fix pipeline + CWGC completo multi-nazionalità

### Fix critici
- **`database.py`** — risolto `sqlite3.OperationalError: database is locked` con troppi processi concorrenti: aggiunti `timeout=30`, `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`.
- **`nara_t315_ocr.py`** — risolti due bug che bloccavano l'OCR:
  1. Chiamata Mistral senza timeout → blocco indefinito. Aggiunto `Mistral(timeout_ms=90_000)`.
  2. `Error binding parameter 9: type 'list' is not supported` → serializzazione robusta di `unita_citate`/`luoghi_citati` con controllo `isinstance(..., list)`.
- **Processi bloccati** — terminati processi Python duplicati/stallati; linker riavviato pulito.

### CWGC — riscrittura completa (`caduti_cwgc.py`)
Obiettivo: scaricare **tutti i caduti CWGC di ogni nazionalità** (WW1 + WW2, ~1.76M) senza API pubblica.

**Scoperte tecniche** (via probing del sito):
- Endpoint reale di ricerca: `GET /find-records/find-war-dead/search-results/` (parametro paginazione `Page` maiuscolo).
- **Endpoint Export CSV pubblico**: `GET /ExportCasualtySearch` → fino a **1000 record/richiesta** in CSV strutturato (19 colonne: Id, Surname, Forename, Rank, Regiment, Unit, CountryOfService, ServiceNumber, Cemetery, GraveRef, AdditionalInfo…), **senza login**.
- **`size=100`** aumenta i risultati da 10 a 100 per pagina (10x più veloce).
- Cap: Export = 1000 record/query; paginazione HTML = 1000 pagine (100k record/query).
- Ricerca cognome = fuzzy/soundex (i prefissi a lettera singola sono inutili); filtro data attivo solo con giorno+mese+anno completi.

**Strategia di partizionamento** (nazionalità × guerra × anno × [mese]):
- partizione ≤ 1000 → **Export CSV** (1 richiesta, dati puliti)
- partizione ≤ 100k → **paginazione `size=100`**
- partizione > 100k → **sub-partizione mensile**
- Resume via `cwgc_progress.json`; dedup automatico via `cwgc_id UNIQUE`; `REQUEST_DELAY` 2.5→1.2s.
- **Nuova tabella arricchita**: `caduti_cwgc` (cwgc_id, cognome, nome, rank, service_number, regiment, nationality, data_morte, eta, cimitero, paese_cimitero, guerra).

### Stato database (07/07/2026 ore 23:22)
| Dataset | Tabella | Record | Stato |
|---|---|---:|---|
| Documenti NARA T315 R1299 | `documenti_nara_t315` | 1.111 | 🔄 OCR quasi completo (96,4%) |
| Caduti Albo d'Oro | `caduti_albooro` | 342.555 | ✅ completo |
| Caduti Ministero Difesa | `caduti_ministero` | 162.646 | ✅ completo |
| Caduti Sardi | `caduti_sardi` | 20.435 | ✅ completo |
| Caduti Bolognesi | `caduti_bologna` | 9.656 | ✅ completo |
| Caduti CWGC (tutte naz.) | `caduti_cwgc` | 322.486 | 🔄 in corso (target ~1.76M, 18,3%) |
| Internati Militari Italiani | `internati` | 20.464 | ✅ completo |
| Decorati al Valor Militare | `decorati` | 1.286 | ✅ completo |
| Entità estratte | `entita` | 160.191 | 🔄 linker in esecuzione |
| Collegamenti | `collegamenti` | 659.050 | 🔄 linker in esecuzione |

Collegamenti per tabella: `caduti_ministero` 355.966 · `internati` 280.896 · `decorati` 21.020 · `menzioni` 776 · `fondi_archivistici` 392.

### Script di monitoraggio (`status.ps1`)
- Script PowerShell per status di tutti i processi di acquisizione con percentuali
- Uso: `.\status.ps1` (snapshot) o `.\status.ps1 -Watch` (auto-refresh 10s)
- Mostra: tabella dataset con record/target/%/stato, barre progresso NARA e CWGC, distribuzione CWGC per nazionalità, stato linker, processi Python attivi
- Rilevamento processi attivi via log file timestamps

---

## 2026-07-07 - Sessione di lavoro

### Nuovi moduli implementati

#### 1. OCR NARA T315 Roll 1299 (`nara_t315_ocr.py`)
- **Fonte**: National Archives USA, Microcopy T-315, Roll 1299
- **Contenuto**: 1.156 immagini JPG — Kriegstagebücher della 717. Infanterie-Division / 117. Jäger-Division (1943)
- **Motore OCR**: Mistral `pixtral-12b-2409` via `MISTRAL_API_KEY`
- **Nuova tabella**: `documenti_nara_t315` (frame, tipo\_documento, data, mittente, destinatario, unità, luoghi, perdite, testo\_ocr, lingua, confidenza)
- **Endpoint API**: `GET /api/nara`, `POST /api/nara/scrape`, `POST /api/nara/stop`
- **Stato**: in corso (~52/1.153 frame processati al 07/07/2026 17:18)
- **Fix applicati**: JSON strict=False per caratteri di controllo; normalizzazione lista per frame multi-scheda; parsing backtick corretto

#### 2. Analisi storica 117. Jäger-Division (`analisi_117div_marzo1943.md`)
- Traduzione italiana completa dei documenti OCR (da tedesco)
- Analisi cronologica operativa: **marzo 1943**, Sarajevo–Visegrad–Grecia
- Documenti chiave tradotti: ordini di schieramento, rapporti situazione, ordine trasferimento Grecia
- **Riferimenti a forze italiane**: presidi a Gorazde/Kalinovik, collaborazione intelligence, anticipo Operazione Achse (set.1943)
- **Nota IMI**: dopo l'armistizio italiano (8 set. 1943) la 117. Jäger-Division disarmò truppe italiane in Grecia → potenziale collegamento con internati

#### 3. Estensione `linker.py` per nuovi dataset
- Aggiunti blocchi di estrazione per: `caduti_ministero` (162k), `caduti_sardi` (20k), `caduti_bologna` (9.6k), `caduti_albooro` (296k)
- Resume intelligente via `MAX(record_id)` per ogni tabella
- In esecuzione al 07/07/2026 17:18 su 516.305 record totali

### Stato database (07/07/2026 ore 17:18)
| Dataset | Tabella | Record | Stato |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | ✅ completo |
| Decorati al Valor Militare | `decorati` | 1.286 | ✅ completo |
| Caduti Albo d'Oro | `caduti_albooro` | 299.510+ | 🔄 in corso (~56%) |
| Caduti Bolognesi | `caduti_bologna` | 9.656 | ✅ completo |
| Caduti Ministero Difesa | `caduti_ministero` | 162.646 | ✅ completo |
| Caduti Sardi | `caduti_sardi` | 20.435 | ✅ completo |
| Documenti NARA T315 R1299 | `documenti_nara_t315` | 52+ | 🔄 OCR in corso (4.5%) |
| Entità estratte | `entita` | 42.806 | 🔄 linker in esecuzione |
| Collegamenti | `collegamenti` | 82.391 | 🔄 linker in esecuzione |

---

## 2026-07-06 - Sessione di lavoro

### Nuovi moduli implementati

#### 1. Sistema Entità e Collegamenti Cross-Dataset (`linker.py`)
- **Tabella `entita`**: entità estratte da tutti i dataset (persone, luoghi, eventi)
- **Tabella `collegamenti`**: link tra entità e record in `internati`, `decorati`, `menzioni`, `fondi_archivistici`
- Estrazione automatica con stop/resume e tracking del progresso
- **Risultato**: 42.806 entità, 75.771 collegamenti estratti da 21.854 record
- Endpoint API: `/api/entita`, `/api/entita/build`, `/api/entita/stop`, `/api/entita/search`, `/api/entita/{id}`

#### 2. Ricerca AI Assisted (`ai_research.py`)
- Integrazione con 3 provider AI: **OpenAI GPT-4o-mini**, **Mistral Large**, **Perplexity Sonar**
- Ogni provider interroga il DB locale per recuperare contesto (internati, decorati, menzioni, fondi)
- Estrazione termini significativi da query in linguaggio naturale (anni, nomi, luoghi)
- Prompt strutturato per ruolo di ricercatore storico con output in sezioni (SINTESI, PERSONE, LUOGHI, EVENTI, FONTI, COLLEGAMENTI, APPROFONDIMENTI)
- **Tabella `ai_ricerche`**: log di tutte le ricerche AI con provider, modello, costo, risposta
- Cost tracking integrato con `credits.py` esistente
- Endpoint API: `/api/ai-research` (POST con provider selezionabile o "all"), `/api/ai-research/history`
- **Test completati**:
  - "trova soldati decorati deceduti nel 1943" → 18 decorati trovati e analizzati (costo $0.0018)
  - "soldati presenti in più fonti" → cross-referencing tra internati/decorati/menzioni, identificati cognomi comuni (Rossi, Ferrari, Barbieri, Ferretti, Montanari, Bertolini, Rinaldi) (costo $0.0039)

#### 3. Caduti Albo d'Oro - Cimeetrincee (`caduti_albooro.py`)
- Scraping da `cadutigrandeguerra.it` (Associazione Storica Cimeetrincee)
- 35 volumi dell'Albo d'Oro dei caduti italiani della Grande Guerra (~530k nomi)
- Reverse-engineering di ASP.NET WebForms (VIEWSTATE, EVENTVALIDATION)
- **Tabella `caduti_albooro`**: nominativo, paternità, classe, comune, grado, reparto, anno/luogo/causa morte, link dettaglio
- Stop/resume con skip dei volumi già scaricati
- **Risultato in corso**: 21.041 caduti salvati da 22 volumi (su 35 totali)
- Endpoint API: `/api/albooro`, `/api/albooro/scrape`, `/api/albooro/stop`

#### 4. Frontend aggiornato (`templates/index.html`)
- Pannello "Entità e Collegamenti Cross-Dataset" con stats, bottoni estrazione/stop, ricerca entità
- Pannello "Ricerca AI Assisted" con selettore provider (GPT/Mistral/Perplexity/Tutti), input query, loading indicator, risultati formattati, storico ricerche cliccabile
- Pannello "Caduti Albo d'Oro" con stats volumi, bottoni scraping/stop, info progresso
- Polling automatico per aggiornamento stato durante operazioni background

### Modifiche a file esistenti

- **`database.py`**: Aggiunte tabelle `entita`, `collegamenti`, `ai_ricerche` con indici; funzioni CRUD per entità/collegamenti/ricerche AI; funzione `search_all` estesa con supporto multi-term
- **`app.py`**: Aggiunti import e threading locks per `linker`, `ai_research`, `caduti_albooro`; 12 nuovi endpoint API
- **`templates/index.html`**: 3 nuovi pannelli UI + ~150 righe di JavaScript per entità, AI research, Albo d'Oro

### Dati attualmente nel database

| Dataset | Tabella | Record | Fonte |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | Archivio di Stato di Bolzano |
| Decorati al Valor Militare | `decorati` | 1.286 | ISTORECO Albi della Memoria (RE) |
| Menzioni da fondi archivistici | `menzioni` | ~2.000+ | Ufficio Storico SME |
| Caduti Albo d'Oro | `caduti_albooro` | 21.041 (in corso) | Cimeetrincee / cadutigrandeguerra.it |
| Entità estratte | `entita` | 42.806 | Estrazione automatica cross-dataset |
| Collegamenti | `collegamenti` | 75.771 | Link entità ↔ record |
| Ricerche AI | `ai_ricerche` | 3 | Log ricerche AI-assisted |

### TODO - Siti di interesse tematico (aggiornato 07/07 ore 23:22)

| # | Fonte | Record | Priorità | Stato |
|---|---|---:|---|---|
| s1 | Cimeetrincee (Albo d'Oro) | 342.555 | alta | ✅ **completo** |
| s2 | Ministero Difesa (Caduti 1a/2a GM) | 162.646 | alta | ✅ **completo** |
| s3 | Caduti Bolognesi (Museo Risorgimento BO) | 9.656 | alta | ✅ **completo** |
| s4 | Eroi e Caduti Sardi (Unione Sarda) | 20.435 | alta | ✅ **completo** |
| s14 | UK/Commonwealth - CWGC (tutte naz.) | 322.486 / ~1.76M | media | 🔄 **in corso** (18,3%) |
| s5 | Istituto Nastro Azzurro (decorati VM) | n.d. | media | pending |
| s6 | Eco Museo Grande Guerra Prealpi Vicentine | museale | bassa | pending |
| s7 | Riassunti storici brigate fanteria | testuale | bassa | pending |
| s8 | 14-18 Documenti e immagini GG | documentale | bassa | pending |
| s9 | Centro Ricerche Grande Guerra | documentale | bassa | pending |
| s10 | Sacrario Redipuglia | n.d. | bassa | pending |
| s11 | The World Remembers (28 nazioni) | ~5M | media | pending |
| s12 | Francia - Mémoire des Hommes | ~1.4M | media | pending |
| s13 | Germania - Volksbund | ~825k | media | pending |
| s15 | USA - ABMC/NARA | ~116k | media | pending |

**Completati oggi**: s1 (Albo d'Oro), s2 (Ministero), s3 (Bologna), s4 (Sardi). **In corso**: s14 (CWGC multi-nazionalità, 18,3%).
**Altri task in corso**: OCR NARA T315 R1299 (1.111/1.153, 96,4% — quasi completo); linker cross-dataset (659.050 collegamenti, 160.191 entità).
**Backup DB**: `imi_internati.db` → `imi_internati_backup_20260707.db` (298 MB) + backup completo in `C:\Users\eryma\Desktop\i backup\`.

### Fonte già importata (esclusa)
- **Albi della Memoria ISTORECO Reggio Emilia** → tabella `decorati` (1.286 record)

---

## 2026-07-06 - IR Layer: FTS5 + Graph CTE (20:00)

### Stato popolamento database (snapshot 19:49)

| Dataset | Tabella | Record attuali | Target | % completamento | Stato |
|---|---|---:|---:|---:|---|
| Internati Militari Italiani | `internati` | 20.464 | 20.464 | 100% | **completo** |
| Decorati al Valor Militare | `decorati` | 1.286 | 1.286 | 100% | **completo** |
| Caduti Albo d'Oro | `caduti_albooro` | 296.568 | ~530.000 | 56% | idle (lettera A-Z in corso) |
| Caduti Bolognesi | `caduti_bologna` | 9.656 | ~10.732 | 90% | idle |
| Caduti Ministero Difesa | `caduti_ministero` | 7.334 | ~508.670 | 1.4% | **in corso** (lettera B) |
| Caduti Sardi | `caduti_sardi` | 4.910 | ~20.531 | 24% | **in corso** (lettera D) |
| Caduti CWGC | `caduti_cwgc` | 0 | ~1.700.000 | 0% | richiede Selenium |
| Menzioni fondi archivistici | `menzioni` | 98 | ~200 | 49% | completo per fonti disponibili |
| Fondi archivistici | `fondi_archivistici` | 6 | 6 | 100% | **completo** |
| Entita' estratte | `entita` | 42.806 | - | - | da estendere ai nuovi dataset |
| Collegamenti | `collegamenti` | 75.771 | - | - | da estendere ai nuovi dataset |
| Ricerche AI | `ai_ricerche` | 3 | - | - | log storico |
| **TOTALE** | | **383.196** | **~2.791.000** | **13.7%** | |

### Information Retrieval Layer implementato

#### 1. `db_init_fts.py` - Migration FTS5
- Crea virtual table `idx_entita_search` con FTS5 (tokenizer `unicode61 remove_diacritics 2`)
- Campi indicizzati: `valore`, `cognome`, `nome`, `luogo`, `contesto`
- Campi UNINDEXED: `entita_id`, `tipo` (per filtro)
- Trigger `AFTER INSERT/UPDATE/DELETE` su `entita` per sincronizzazione automatica
- Popolamento iniziale da 42.806 record esistenti (0.7s)
- Idempotente: sicuro da rieseguire

#### 2. `search_service.py` - Service Layer
- **`search_entities(query, limit, tipo)`**: FTS5 + BM25 ranking con prefix matching automatico (`*`), filtro per tipo entita' (persona/luogo/evento/decorazione/periodo)
- **`get_entity_network(entity_id, max_depth)`**: graph traversal
  - depth=2: JOIN dirette su `collegamenti` (ottimizzato per star schema)
  - depth>2: recursive CTE con temp table per evitare limite SQL variables
  - Output: `{nodes, edges, center, node_count, edge_count}` per visualizzazione grafo
- **`get_entity_full_context(entity_id)`**: deep-dive relazionale
  - Risolve dinamicamente il record sorgente da 9 tabelle (`internati`, `decorati`, `menzioni`, `fondi_archivistici`, `caduti_albooro`, `caduti_bologna`, `caduti_ministero`, `caduti_sardi`, `caduti_cwgc`)
  - Mappa `SOURCE_TABLE_FIELDS` per ogni tabella sorgente
  - Fallback graceful per tabelle non accessibili o record mancanti
- **`get_fts_stats()`**: statistiche indice (count, sync status, distribuzione tipi/fonti)

#### 3. `test_search.py` - Test Suite (31 test, 100% pass)
- **TestFTS5Sync** (3 test): trigger INSERT/UPDATE/DELETE su entita' temporanee
- **TestBM25Search** (9 test): ricerca persona, luogo, evento, prefix, multi-word, empty, nonexistent, ranking order
- **TestGraphTraversal** (7 test): depth=2, struttura nodi/edge, no self-loop, recursive depth=3, entity inesistente, centro nei nodi
- **TestEntityFullContext** (5 test): entity esistente, source record risolto, collegamenti, nonexistent, tutte le tabelle sorgente
- **TestNormalizeQuery** (4 test): empty, prefix, wildcard, multi-word
- **TestFTSStats** (3 test): struttura, sync, tipi

### File creati
- `db_init_fts.py` - migration script FTS5 + trigger
- `search_service.py` - IR service layer (3 funzioni core + stats)
- `test_search.py` - test suite 31 test

### Performance
- Popolamento FTS5: 42.806 record in 0.7s
- Query BM25: <1ms
- Graph traversal depth=2: <10ms su 75.771 collegamenti
- Graph traversal depth=3: ~2s (recursive CTE)

---

## 2026-07-06 - Sessione serale (18:00-20:00)

### Fix scraper esistenti

#### Fix Caduti Bolognesi: paginazione e parsing
- **Problema**: scraper si fermava a 482 record (paginazione errata: usava record offset invece di page number)
- **Fix**: `PAGE_SIZE=10` (cap del sito), `start` come page number, parsing tabella `id="DG"`
- **Risultato**: 4.323+ record (in corso, target 10.732)

#### Fix Ministero Difesa: da form HTML a API JSON
- **Problema**: scraper vecchio tentava di fare submit di un form HTML, ma il sito usa JavaScript con reCAPTCHA
- **Reverse engineering**: analizzato file JS `/assets/js/onorcaduti/cadutiprimaguerra.js`, scoperto endpoint API `https://sicadapi.difesa.it/sicad/v1/getprimaguerracadutopaginated`
- **API**: POST JSON con `{campoSingolo, selectedPage, pageSize}`, nessun token/reCAPTCHA richiesto, SSL self-signed (verify=False)
- **508.670 record totali** disponibili via API
- **Schema DB aggiornato**: `source_id` (UNIQUE), `nominativo_paternita`, `paternita`, `maternita`, `data_nascita`, `data_decesso`, `provincia_nascita`, `comune_nascita`, `nazione_decesso`, `luogo_sepoltura`, `codice_volume`, `pagina`, `sub`, `scheda_url` (link a scansione Albo Oro)
- **Parsing cognome/nome**: split su primo spazio del campo `nominativoePaternita` (es. "ABACOT GIUSEPPE DI MICHELE" → cognome=ABACOT, nome=GIUSEPPE DI MICHELE)
- **Risultato**: 975+ record (in corso, lettera A, target 508.670)

#### Fix Caduti Sardi: da probing generico a parsing strutturato
- **Problema**: scraper vecchio cercava tabelle HTML o split per virgola, ma il sito usa `div.itemDefunto` con struttura specifica
- **Endpoint corretto**: `/Search?query=LETTER&war=1&page=N` (20.531 risultati totali)
- **Struttura HTML**: ogni record è `div.itemDefunto` contenente:
  - `a.city` → comune di residenza
  - `a.name` → cognome + nome concatenati (es. "Abau Anacleto"), href contiene ID (es. `/Cagliari/ABAU ANACLETO-1`)
  - `div.war` → guerra (Prima/Seconda Guerra Mondiale)
  - `div.date` → date e luogo (es. "15 Maggio 1893 - 03 Giugno 1916 sul monte Cengio")
- **Parsing cognome/nome**: split su primo spazio (es. "Abau Anacleto" → cognome=Abau, nome=Anacleto) - confermato da verifica multipla
- **Parsing date**: regex per date in formato italiano "DD Mese YYYY", estrazione luogo morte dopo ultima data
- **Schema DB aggiornato**: `source_id` (UNIQUE), `guerra`, `comune_residenza`, indici su cognome e comune
- **Risultato**: 180+ record (in corso, lettera A, target 20.531)

### Nuovi file
- `ARCHITETTURA_DB.md` - documento architettura database a 3 livelli + prompt per generazione immagine + diagramma Mermaid

### File modificati
- `caduti_ministero.py` - rewrite completo: API JSON invece di form HTML, nuovo schema DB, parsing nominativoePaternita
- `caduti_sardi.py` - rewrite completo: endpoint /Search con paginazione, parsing div.itemDefunto, separazione cognome/nome, parsing date italiano
- `caduti_bologna.py` - fix paginazione (PAGE_SIZE=10, page number invece di offset)

### Stato database (in corso)
| Dataset | Tabella | Record | Fonte |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | Archivio di Stato di Bolzano |
| Decorati al Valor Militare | `decorati` | 1.286 | ISTORECO Albi della Memoria (RE) |
| Caduti Albo d'Oro | `caduti_albooro` | 238.231+ (in corso) | Cimeetrincee / cadutigrandeguerra.it |
| Caduti Bolognesi | `caduti_bologna` | 4.323+ (in corso) | Museo Risorgimento BO |
| Caduti Ministero Difesa | `caduti_ministero` | 975+ (in corso) | sicadapi.difesa.it (API JSON) |
| Caduti Sardi | `caduti_sardi` | 180+ (in corso) | eroiecadutisardi.unionesarda.it |
| Caduti CWGC | `caduti_cwgc` | 0 (richiede Selenium) | cwgc.org |
| Entità estratte | `entita` | 42.806 | Estrazione automatica cross-dataset |
| Collegamenti | `collegamenti` | 75.771 | Link entità ↔ record |

---

## 2026-07-06 - Sessione pomeridiana (16:00-18:00)

### Fix e miglioramenti

#### Fix Albo d'Oro: paginazione per lettera alfabetica
- **Problema**: ogni volume restituiva max 1000 record (cap di GridView ASP.NET)
- **Soluzione**: paginazione per lettera A-Z all'interno di ogni volume (35 volumi × 26 lettere = 910 richieste)
- Resume per singola lettera già scaricata (skip se `nominativo LIKE 'X%'` esiste)
- **Risultato**: da 31.222 a 58.137+ record (in corso, ~530k attesi)

#### Nuovo modulo: Caduti Bolognesi (`caduti_bologna.py`)
- Fonte: `badigit.comune.bologna.it/csg/ricerca.aspx` (Museo Civico del Risorgimento BO)
- 10.732 record caduti provincia di Bologna 1915-1918
- Paginazione via query string (`num=50&start=X`)
- Parsing regex estrae: nome, paternità, grado, reparto, luogo nascita, anno, dimora, causa/luogo/data morte, professione, stato civile, decorazioni
- **Tabella `caduti_bologna`** con UNIQUE constraint su nome+paternità+data_morte
- **Risultato**: 482+ record (in corso, 10.732 attesi)
- Endpoint API: `/api/bologna`, `/api/bologna/scrape`, `/api/bologna/stop`

#### Nuovo modulo: CWGC Commonwealth (`caduti_cwgc.py`)
- Fonte: `cwgc.org` - 1.7M caduti Commonwealth WW1/WW2
- Approccio: download CSV per paese (87 paesi)
- **Problema**: il sito CWGC è stato ridisegnato, l'URL `/find/find-war-dead/results` ritorna 404. Richiede Selenium/Playwright per JavaScript rendering
- **Tabella `caduti_cwgc`** creata e pronta, ma scraping non attivo
- Endpoint API: `/api/cwgc`, `/api/cwgc/scrape`, `/api/cwgc/stop`

### File creati
- `caduti_bologna.py` - scraper Caduti Bolognesi
- `caduti_cwgc.py` - scraper CWGC (richiede Selenium per JS)

### File modificati
- `caduti_albooro.py` - fix paginazione per lettera alfabetica
- `app.py` - aggiunti import, lock e endpoint per Bologna e CWGC

### Stato database (in corso)
| Dataset | Tabella | Record | Fonte |
|---|---|---|---|
| Internati Militari Italiani | `internati` | 20.464 | Archivio di Stato di Bolzano |
| Decorati al Valor Militare | `decorati` | 1.286 | ISTORECO Albi della Memoria (RE) |
| Caduti Albo d'Oro | `caduti_albooro` | 58.137+ (in corso) | Cimeetrincee / cadutigrandeguerra.it |
| Caduti Bolognesi | `caduti_bologna` | 482+ (in corso) | Museo Risorgimento BO |
| Caduti CWGC | `caduti_cwgc` | 0 (richiede Selenium) | cwgc.org |
| Entità estratte | `entita` | 42.806 | Estrazione automatica cross-dataset |
| Collegamenti | `collegamenti` | 75.771 | Link entità ↔ record |

---

## 2026-07-24 — AI Provider Consolidation + LeBI Fase 4

### AI Provider Consolidation
- **`ai_router.py`**: OpenAI impostato come provider primario per tutti i task type (text, web_search, vision+ocr, embeddings). Altri provider (Anthropic, Mistral, Perplexity, Gemini) solo come fallback.
- **`ai_client.py`**: Modelli default aggiornati — Anthropic `claude-sonnet-4-5-20250929`, Gemini `gemini-2.0-flash` (sostituisce deprecato `gemini-1.5-flash`).
- **`event_research_engine.py`**: TAB_PROVIDER usa `gpt` (OpenAI) per tutti i 4 tab (panoramica, fonti, punti_di_vista, cronologia). EVENT_RESEARCH_FALLBACK: gpt → perplexity → claude → mistral.
- **`ai_research.py`**: Modello Anthropic allineato a `claude-sonnet-4-5-20250929` nel dizionario PROVIDERS.
- **`biography.py`**: Verificato `_FALLBACK_ORDER` già prioritizza `gpt`.
- **`research_engine_schema.py`**: Verificato seed ai_providers ha OpenAI con `priority=1`.

### LeBI Fase 4 — Frontend, API, Parser Fix
- **3 nuovi endpoint API** in `app.py`:
  - `GET /api/lebi/search` — ricerca per cognome/nome/luogo/anno
  - `GET /api/lebi/record/{record_id}` — scheda biografica dettagliata
  - `GET /api/lebi/compare/{soldier_id}` — confronto IMI locale vs LeBI con match score
- **Frontend `voci-data.js`**:
  - `loadLeBIComparison(soldierId)` — chiama API comparison, restituisce match con score
  - `loadLeBISearch(query, filters)` — ricerca standalone LeBI
  - LeBI aggiunto ai filtri fonti italiane (ANRP, lessicobiografico)
- **Frontend `index.html`**:
  - Tab "LeBI" nel dossier soldato (visibile solo per IMI)
  - Vista comparison con campi corrispondenti (verde, =) e divergenti (rosso, ≠)
  - Detail espandibile con scheda completa LeBI
  - Link scheda LeBI + PDF download
  - Loading state e error handling
  - `loadLeBIComparison()` method nel controller
- **Bug fix parser HTML LeBI**:
  - `source_providers/lebi.py` `_parse_record_html`: il parser usava `col-xs-5` per le label, ma l'HTML reale usa class `fallen-label`. Fix: label identificate da `fallen-label`, valori da sibling senza `fallen-label`.
  - Pass separato per sezione INTERNAMENTO: campi usano `col-xs-5` con `fallen-field-margins` senza `fallen-label`.
  - Supporto sezione RIENTRO (IMI sopravvissuti) oltre a DECESSO.
  - `sources_external_lebi.py` `_parse_sections`: stesso fix applicato all'adapter.
- **Verifica reale**: ricerca "Rossi Mario" → 10 risultati reali. Record #78247 (MARIO DE ROSSI) parsato correttamente: cognome, nome, data nascita (07-06-1923), comune (San Severo), grado (S. Ten.), 7 campi internamento (Stalag VI C, Oflag VI C/Z, Stalag VI G, Stalag X B/Z, Stalag XIII D, Stalag III D, Stalag XI A).

### Documentazione
- **`docs/architecture/PIPELINE.md`**: nuovo documento con 11 sezioni — pipeline ricerca, AI, research-to-index, LeBI, compliance, OCR, biografia, event research, import fonti, mappa endpoint, schema DB.
- **`docs/architecture/ARCHITECTURE.md`**: aggiornata versione, stack AI (5 provider con Gemini), endpoint count (312).
- **`README.md`**: aggiornato diagramma architettura (27 provider, 5 AI provider), tabella provider federation (27), API principali (LeBI endpoints), moduli principali (lebi.py, sources_external_lebi.py, voci-data.js).
- **`docs/todo/TODO.md`**: aggiornato con sezione 2026-07-24.

### File modificati
- `ai_router.py` — `_default_policy`: OpenAI primario per tutti i task type
- `ai_client.py` — `_DEFAULT_MODELS`: Anthropic e Gemini aggiornati; `_get_gemini_model`: gemini-2.0-flash
- `event_research_engine.py` — `TAB_PROVIDER` e `EVENT_RESEARCH_FALLBACK`: OpenAI primario
- `ai_research.py` — `PROVIDERS`: modello Anthropic allineato
- `app.py` — 3 nuovi endpoint LeBI (search, record, compare)
- `source_providers/lebi.py` — `_parse_record_html`: fix parser HTML, supporto RIENTRO
- `sources_external_lebi.py` — `_parse_sections`: fix parser HTML, supporto RIENTRO
- `templates/voci-data.js` — `loadLeBIComparison`, `loadLeBISearch`, filtro fonti italiane
- `templates/index.html` — Tab LeBI, vista comparison, method `loadLeBIComparison`
- `docs/architecture/PIPELINE.md` — nuovo file pipeline completo
- `docs/architecture/ARCHITECTURE.md` — aggiornamento versione e stack
- `README.md` — aggiornamento completo
- `docs/changelog/CHANGELOG.md` — questa sezione
- `docs/todo/TODO.md` — aggiornamento task

### Stato API
- Endpoint totali: 312
- Provider federation: 27
- AI provider attivi: 5 (OpenAI primario, 4 fallback)
