# CHANGELOG — Sessione 27 Luglio 2026

## Modifiche applicate

### 1. Espansione provider fonti federate
**File:** `event_research_engine.py` (`_federated_sources_context`)

- Aggiunti 4 nuovi provider: `gallica`, `hathitrust`, `googlebooks`, `internetculturale`
- Da 7 a **11 provider** totali (nara, antenati, cwgc, ussme, archivio_stato, europeana, internetarchive + 4 nuovi)
- Ora copre: giornali, libri, manoscritti, cataloghi OPAC SBN, fonti geografiche

### 2. Campo `summary` (5 righe) per ogni fonte
**File:** `event_research_engine.py` (`_build_source_summary`)

- Nuova funzione `_build_source_summary()` che compone riassunto da titolo, descrizione, provider, tipo, data
- Campo `summary` aggiunto all'output di `_federated_sources_context()`
- Limite 400 caratteri, formato discorsivo

### 3. Frontend: EventSource type + SourceCard
**File:** `frontend/src/api/types.ts`, `frontend/src/pages/EventResearchPage.tsx`

- Aggiunto `summary: string` all'interfaccia `EventSource`
- `SourceCard` aggiornata: mostra summary con bordino sinistro, corsivo, clamping 5 righe (`WebkitLineClamp: 5`)
- Sostituito il vecchio `excerpt` troncato a 200 char con il nuovo `summary`

### 4. Fix mapping Internet Archive
**File:** `source_providers/providers.py`, `ia_evaluation.py`

- Provider IA: aggiunti campi `identifier`, `title`, `date`, `mediatype`, `collection`, `language`, `downloads`
- Evaluator: aggiunta `_normalize_ia_item()` per mappare `titolo`→`title`, `date_start`→`date`, `provider_record_id`→`identifier`

### 5. Fix Vite proxy
**File:** `frontend/vite.config.ts`

- Proxy target corretto da porta `8001` a `8123`

### 6. Prompt discorsivi per tab AI
**File:** `event_research_engine.py` (`TAB_INSTRUCTIONS`)

- **Panoramica**: saggio storico narrativo 600-1200 parole, paragrafi 4-8 righe, niente elenchi
- **Punti di vista**: analisi comparativa discorsiva 500-1000 parole, convergenze/divergenze/silenzi

### 7. Ottimizzazione AI per ricostruzione da frammenti
**File:** `biography.py`, `event_research_engine.py`, `ai_research.py`

- `max_tokens`: 4096 → **16000**
- `temperature`: 0.3 → **0.5**
- Context limit: 15000 → **30000** caratteri
- Modello: hardcoded `gpt-4o-mini` → **`gpt-4.1`** (da env `OPENAI_MODEL`)

### 8. 27 nuovi eventi WWI nel database
**File:** `add_wwi_events.py` (script idempotente)

Database eventi: 22 → **49 eventi** (42 WWI + 7 WWII), 161 alias

Nuovi eventi:
- 11 battaglie dell'Isonzo (1ª-11ª)
- Battaglia degli Altipiani (Strafexpedition)
- Battaglia del Monte Ortigara
- Ripiegamento dal Carso al Piave
- Riorganizzazione dopo Caporetto
- Prima e Seconda battaglia del Piave
- Internamento militari WWI (~600k prigionieri)
- Internamento civile irredenti
- Patto di Londra, Armistizio di Villa Giusti, Vittoria mutilata
- Guerra bianca, Fronte del Tonale
- Battaglia del Monte Sabotino, Difesa del Grappa

### 9. Fix crash tab "Punti di vista"
**File:** `frontend/src/pages/EventResearchPage.tsx`

- Null-safe guards su `.map()`: `(f.fonti || [])` per `fattiConcordanti`, `elementiIncerti`, `cronologia`
- Preveniva `TypeError: Cannot read properties of undefined (reading 'map')`

### 10. Fonti reali invece di provider AI
**File:** `event_narrative_builder.py`

- `fatti_concordanti`, `versioni_divergenti`, `elementi_incerti` ora presi da `evidence.*` (fonti reali) non da AI JSON
- L'AI genera solo il testo narrativo; i dati strutturati di confronto vengono dalle evidenze raccolte

### 11. Provider default GPT
**File:** `event_narrative_builder.py`, `frontend/src/pages/EventResearchPage.tsx`

- Default provider: `mistral` → `gpt` (GPT-4.1)
- Fallback order: `["gpt", "mistral", "perplexity", "claude"]`
- Frontend toggle label: "AI attiva (GPT-4.1)"
- Perplexity: quota esaurita | Claude: credito insufficiente

### 12. Chiave OpenAI aggiornata
**File:** `.env`

- Nuova chiave OpenAI sostituita e verificata funzionante con `gpt-4.1`
