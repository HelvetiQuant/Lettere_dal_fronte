# Resoconto Tecnico: Test del Narratore Storico Conversazionale V7.2-narrator-v1

**Data test:** 2026-08-03 19:34:20  
**Contratto:** 7.2-narrator-v1  
**File di output:** `_v72_narrator_test_output.txt` (2044 righe)  
**Script di test:** `_test_narrator_v1.py`  
**Modello AI:** Mistral (via `ai_client.py`)  
**Seed randomico:** 42 (riproducibile)

---

## 1. Obiettivo del Test

Verificare che il backend generi risposte conversazionali conformi al nuovo narratore V7.2, rispettando:
- Il system prompt `NARRATOR_SYSTEM_PROMPT_V1` (`v7_narrator_prompt.py`)
- Il formato JSON obbligatorio in output
- Le regole evidenziali (claim approvati, citazioni source_id, divieto di allucinazione)
- La classificazione dell'identità (`RESOLVED`, `PARTIAL`, `AMBIGUOUS`)
- Il fallback deterministico in caso di assenza AI

Sono state eseguite **9 query**: 6 `PERSON_LOOKUP` (2 nomi casuali ciascuno da `internati`, `caduti_albooro`, `decorati_nastroazzurro`) e 3 `EVENT_LOOKUP` (da `eventi_1gm`).

---

## 2. Sintomi Osservati

### 2.1 Produzione JSON — Tasso di Fallimento 89%

| Query | Tipo | Output JSON? | Note |
|-------|------|:---:|------|
| CASINI Italo | PERSON | ❌ | Testo conversazionale raw |
| GRAZZIOTTI Giuseppe | PERSON | ❌ | Testo conversazionale raw |
| FANTINO Alessandro | PERSON | ❌ | Testo conversazionale raw |
| FERRARIO Pietro | PERSON | ❌ | Fallback deterministico (AMBIGUOUS_IDENTITY) |
| ABUKAR ALì UADAN | PERSON | ❌ | Testo conversazionale raw |
| ALESSANDRONI Giovanni | PERSON | ❌ | Fallback deterministico (AMBIGUOUS_IDENTITY) |
| Monte Col di Lana | EVENT | ❌ | Testo conversazionale raw |
| Battaglia del Piave | EVENT | ❌ | Testo conversazionale raw |
| Fronte Macedone | EVENT | ✅ | JSON completo e valido |

**Solo 1 query su 9 (11%) ha prodotto output JSON conforme.**

### 2.2 Warning Ricorrenti

| Tipo Warning | Frequenza | Descrizione |
|-------------|-----------|-------------|
| `UNKNOWN_SOURCE_REFERENCE` | 4/9 query | L'AI cita `obs_` ID non presenti nello snapshot |
| `OCR_DEFORMED_PLACE` | 5/6 person | Toponimi con cifre o mixed_case in `internati` |
| `INCOMPLETE_NAME` | 6/6 person | Campo `cognome` vuoto in `caduti_albooro` |
| `NARRATION_WARNING` | 4/9 query | Sub-type di UNKNOWN_SOURCE_REFERENCE |

### 2.3 Contaminazione da Omonimi nei Web Lead

| Query | Omonimo rilevato | Contesto estraneo |
|-------|-----------------|-------------------|
| FANTINO Alessandro | Alessandro & Gian Natale Fantino | Produttori di vino Barolo |
| ABUKAR ALì UADAN | Abukar Ali Adan | Leader al-Shabaab (contemporaneo) |
| ALESSANDRONI Giovanni | Alessandro Alessandroni | Musicista/fischiatore (anni '70) |
| CASINI Italo | Italo Casini | Ceramista (1892-1970), olimpionico |

Il narratore ha occasionalmente segnalato l'ambiguità, ma non in modo sistematico.

---

## 3. Analisi della Causa Radice

### 3.1 Fallimento JSON: Modello AI Non Conforme al Prompt

Il system prompt `NARRATOR_SYSTEM_PROMPT_V1` richiede output JSON strutturato con campi:
- `request_type`
- `answer_markdown`
- `used_claim_ids`
- `citation_map`
- `omitted_claims`
- `validation_flags`

Il metodo `_extract_answer_markdown()` in `v7_narrator.py:723-763` tenta di parsare JSON:

```python
# v7_narrator.py:706-714
answer_md = self._extract_answer_markdown(raw_text)
if answer_md:
    return answer_md
else:
    # If JSON parsing fails, use raw text as-is (graceful degradation)
    logger.warning("AI narration JSON parsing failed, using raw text")
    return raw_text
```

**Causa radice:** Il modello Mistral non segue consistentemente l'istruzione di output JSON. In 8 casi su 9, restituisce testo conversazionale in markdown invece di un oggetto JSON. Il fallback accetta il testo raw, perdendo:
- La struttura `citation_map` (mappatura frase → claim → source)
- La traccia di audit (`used_claim_ids`, `omitted_claims`)
- I `validation_flags` di auto-diagnosi

### 3.2 Fallback Deterministico per Identità Ambigue

Per `FERRARIO Pietro` e `ALESSANDRONI Giovanni` (entrambi `AMBIGUOUS_IDENTITY` con 0 person claims e 10+ candidate identities), il narratore ha bypassato l'AI e prodotto un report deterministico:

> "Questo rapporto è stato generato deterministicamente senza AI"

Questo è **comportamento atteso** del sistema: l'AI non viene chiamata quando l'identità è ambigua e non ci sono claim approvati. Tuttavia, significa che per identità ambigue non si ottiene mai output JSON.

### 3.3 UNKNOWN_SOURCE_REFERENCE: Allucinazione di Source ID

In 4 query, l'AI ha citato `obs_` ID non presenti nello snapshot input. Esempio dalla query Fronte Macedone:

```
NARRATION_WARNING: UNKNOWN_SOURCE_REFERENCE: Source reference not in snapshot: obs_8b924b52862c7240
```

Il warning appare 4 volte per la stessa query, sempre con lo stesso `obs_` ID. Questo indica che:
1. L'AI ha inventato un source ID, OPPURE
2. L'AI ha ricevuto un source ID nello snapshot input che non è stato correttamente mappato nel `to_narrator_input()`

**Ipotesi più probabile:** L'AI ha visto il source ID nel contesto (forse nei web leads) ma non nei claim approvati, e lo ha citato come se fosse una fonte verificata.

### 3.4 Contaminazione Omonimi: Assenza di Filtro Temporale nella Web Search

I web lead per le query `PERSON_LOOKUP` contengono risultati palesemente estranei al periodo storico (1900-1945):
- Produttori di vino contemporanei
- Leader terroristici del XXI secolo
- Musicisti degli anni '70
- Ceramisti del XX secolo

La pipeline di web search (Tavily) non applica filtri temporali. La query di ricerca è basata solo sul nome, senza aggiungere termini come "Grande Guerra", "internato", "caduto", "1915-1918", ecc.

### 3.5 Dati di Base: Qualità del Database

| Tabella | Problema | Impatto |
|---------|----------|---------|
| `internati` | Toponimi con cifre/mixed_case (OCR) | Warning in ogni query person |
| `caduti_albooro` | Campo `cognome` sistematicamente vuoto | Warning in ogni query person |
| `eventi_1gm` | Campo `cognome` vuoto su eventi | Warning in 1/3 query event |

Questi sono problemi di qualità dati preesistenti, non causati dal narratore, ma che generano rumore nei log.

---

## 4. Mappa delle Componenti Coinvolte

```
UnifiedResearchOrchestratorV7.execute()
  └─ _stage_narrate()
       └─ NarratorV7.narrate(snapshot, use_ai=True)
            ├─ snapshot.to_narrator_input()     ← JSON input per AI
            ├─ _try_ai_narration(snapshot)      ← Chiama AI con system prompt
            │    ├─ NARRATOR_SYSTEM_PROMPT_V1   ← Prompt che richiede JSON output
            │    ├─ call_ai(task_type="narration", max_tokens=4000, temperature=0.3)
            │    └─ _extract_answer_markdown()  ← Parsa JSON, fallback a raw text
            ├─ OutputValidatorV7.validate()     ← Valida output AI
            └─ ReportRenderer.render_markdown() ← Render finale con fonti
```

---

## 5. Metriche di Performance

| Metrica | Persona (media) | Evento (media) |
|---------|:---:|:---:|
| Tempo esecuzione | 47.4s | 132.3s |
| Observations | 113 | 269 |
| Person/Context claims | 1 | 235 |
| Web leads | 48 | 209 |
| Tasso successo JSON | 0% (0/6) | 33% (1/3) |

L'unica query JSON riuscita (Fronte Macedone) ha generato un oggetto con **100+ omitted_claims**, occupando ~500 righe del file di output. Questo suggerisce che il `max_tokens=4000` potrebbe essere insufficiente per eventi con molti context claims, causando troncamento del JSON in altri casi.

---

## 6. Impatto del Problema

### 6.1 Funzionalità Compromesse
- **Audit trail incompleto**: Senza `used_claim_ids` e `citation_map`, non è possibile verificare quali claim sono stati usati
- **Validazione post-generazione impossibile**: L'`OutputValidatorV7` non può validare citazioni senza la struttura JSON
- **Tracciabilità delle omissioni persa**: Senza `omitted_claims`, non si sa quali claim sono stati scartati e perché

### 6.2 Funzionalità Preservate
- **Qualità conversazionale**: Il testo raw è comunque in italiano, conversazionale, e rispetta le regole evidenziali principali
- **Fallback deterministico**: Per identità ambigue, il sistema non va in crash
- **Citazioni inline**: L'AI cita `obs_` ID nel testo anche senza struttura JSON

---

## 7. Azioni Correttive Proposte

### 7.1 Priorità Alta — Conformità JSON

| # | Azione | File | Descrizione |
|---|--------|------|-------------|
| A1 | Rinforzare prompt JSON | `v7_narrator_prompt.py` | Aggiungere "OUTPUT ONLY VALID JSON. NO TEXT BEFORE OR AFTER THE JSON OBJECT." all'inizio e fine del prompt |
| A2 | Aumentare max_tokens | `v7_narrator.py:699` | Da 4000 a 8000 per eventi con molti context claims |
| A3 | Troncare omitted_claims | `evidence_snapshot_v7.py` (to_narrator_input) | Limitare a 20 omitted_claims con reason summary invece di elencarli tutti |
| A4 | Retry con prompt semplificato | `v7_narrator.py` (_try_ai_narration) | Se JSON parsing fallisce, retry con prompt ridotto che enfatizza "RISPONDI SOLO CON JSON" |

### 7.2 Priorità Media — Qualità Dati

| # | Azione | File | Descrizione |
|---|--------|------|-------------|
| B1 | Filtro temporale web search | `v7_provider_adapters.py` o Tavily adapter | Aggiungere termini temporali alla query ("1915 1918 Grande Guerra caduto") |
| B2 | Pulizia `caduti_albooro` | Script di migrazione | Backfill campi `cognome`/`nome` vuoti o marcarli come `needs_review` |
| B3 | Validazione source_id post-AI | `v7_narrator.py` | Dopo parsing JSON, verificare che ogni source_id in `citation_map` esista nello snapshot |

### 7.3 Priorità Bassa — Osservabilità

| # | Azione | File | Descrizione |
|---|--------|------|-------------|
| C1 | Log strutturato JSON success/failure | `v7_narrator.py` | Log metriche: provider, model, tokens, parse_success, elapsed |
| C2 | Metriche di copertura | Test script | Calcolare % JSON success per run e trend nel tempo |

---

## 8. Conclusione

Il narratore V7.2-narrator-v1 **funziona** come sistema conversazionale: produce testo in italiano, rispetta le regole evidenziali, e gestisce graceful fallback. Tuttavia, **non produce output JSON nell'89% dei casi**, rendendo impossibile la validazione post-generazione e l'audit trail strutturato.

La causa radice è duplice:
1. **Il modello AI (Mistral) non segue l'istruzione JSON** in modo consistente — richiede rinforzo del prompt e/o retry logic
2. **`max_tokens=4000` è insufficiente** per eventi con centinaia di context claims — il JSON viene probabilmente troncato

Il problema è **non bloccante** (il fallback a raw text preserva la funzionalità di base) ma **degradante** (perde audit trail, validazione, e tracciabilità delle omissioni).
