# CHANGELOG — V7.1 Backend AI Activation

**Data:** 2 Agosto 2026  
**Repo:** `imi_extractor`  
**Branch:** main  

---

## Fix applicati

### 1. Bug critico: `call_ai` return value non gestito in `v7_narrator.py`

**File:** `v7_narrator.py:491-501`  
**Problema:** `call_ai()` ritorna un dict `{"ok": bool, "text": str, "provider": str, ...}`, ma `_try_ai_narration()` trattava la risposta come stringa (`len(response)` su dict, ritorno del dict intero invece di `response["text"]`).  
**Fix:** Estrazione corretta di `response["text"]` dopo verifica `response.get("ok")`, con logging di successo/fallimento e provider usato.

### 2. Bug critico: `NO_AI_PROVIDER` hardcoded in `unified_orchestrator_v7.py`

**File:** `unified_orchestrator_v7.py:696`  
**Problema:** Le `limitations` del snapshot erano hardcoded con `LimitationV7(code="NO_AI_PROVIDER")` **sempre**, anche quando i provider AI erano disponibili e funzionanti. L'AI leggeva questa limitation dal context e la riportava nel report.  
**Fix:** Sostituito con metodo `_compute_limitations()` che verifica dinamicamente `is_any_provider_available()` prima di aggiungere la limitation.

---

## Test eseguiti

### PERSON_LOOKUP — 5 nomi reali

| Nome | Fonte | Observations | Identity | AI Provider |
|------|-------|-------------|----------|-------------|
| Rossi Mario | caduti_albooro | 74 | RESOLVED | GPT-4o |
| Bianchi Giovanni | caduti_albooro | 61 | RESOLVED | GPT-4o |
| Ferrari Carlo | caduti_albooro | 81 | RESOLVED | GPT-4o |
| Esposito Antonio | caduti_albooro | 75 | RESOLVED | GPT-4o |
| Zanardi Luigi | caduti_albooro | 41 | RESOLVED | GPT-4o |

### PERSON_LOOKUP — 6 nomi reali (canary definitivo)

| Nome | Fonte | Observations | Identity | AI Provider |
|------|-------|-------------|----------|-------------|
| CAIS Arduino | internati (IMI) | 10 | RESOLVED | GPT-4o |
| BROGNARA Cristino | internati (IMI) | 11 | RESOLVED | GPT-4o |
| TONIOLI Pasquale | internati (IMI) | 4 | RESOLVED | GPT-4o |
| DEVINCENZI Giovanni | caduti_albooro (WWI) | 9 | RESOLVED | GPT-4o |
| EGINETI Arturo | caduti_albooro (WWI) | 1 | PARTIAL | GPT-4o |
| RIGAMONTI Pietro | caduti_albooro (WWI) | 43 | RESOLVED | GPT-4o |

### EVENT_LOOKUP — 3 eventi

| Evento | Observations | Identity | AI Provider |
|--------|-------------|----------|-------------|
| Caporetto | 3 | UNRESOLVED | GPT-4o |
| Monte Grappa | 1 | UNRESOLVED | GPT-4o |
| Battaglia del Piave | 1 | UNRESOLVED | GPT-4o |

### AGGREGATE_QUERY — 3 fatti

| Query | Rows | AI Provider |
|-------|------|-------------|
| count_internati_by_campo | 50 | GPT-4o |
| count_caduti_by_luogo | 50 | GPT-4o |
| temporal_distribution_caduti | 8 | GPT-4o |

**Totale:** 17 query eseguite, tutte con AI narration (GPT-4o), 0 fallback deterministici.

---

## File modificati

| File | Modifica |
|------|----------|
| `v7_narrator.py:491-501` | Fix estrazione `response["text"]` da `call_ai()` dict |
| `unified_orchestrator_v7.py:579-594` | Nuovo metodo `_compute_limitations()` |
| `unified_orchestrator_v7.py:696` | Sostituito hardcoded limitations con `_compute_limitations()` |

---

## File creati

| File | Contenuto |
|------|-----------|
| `V7_PIPELINE_METHODOLOGY.md` | Documento completo pipeline V7.1 (9 stadi, 15 moduli, fonti, invarianti) |
| `prompt_devin_v7_2_fix_identita_narrazione_ricostruzione.md` | Prompt V7.2 per fix identità, narrazione, ricostruzione |

---

## Problemi identificati per V7.2

1. **Resolver premia cognome** — record con nome diverso ma cognome uguale raggiunge score 0.5
2. **Parità di score** — ordine DB elegge arbitrariamente il primo record
3. **Fusione non vincolata al cluster** — claim di record omonimi entrano in `conflicting_claims` della stessa persona
4. **FETCH non apre fonti** — snippet diventa `METADATA_ONLY` senza HTTP request
5. **Independence rule superficiale** — `different archive => independence_score 1.0` è falso
6. **Validatore richiede URL** — record archivistici senza URL pubblico vengono scartati
7. **Renderer espone ledger** — ID interni, enum, conteggi, reason code nel report visibile
8. **Context non separato da person evidence** — storia del reparto diventa biografia individuale
