# Lettere dal fronte — Analisi, test e correzioni (12/07/2026)

## Esito analisi

**Collegamenti backend–frontend**: tutti i ~50 endpoint chiamati da `index.html` esistono in `app.py`. Nessun endpoint orfano o rotto.

**Connessioni AI multiple**: i 4 provider (GPT-4o-mini, Claude Sonnet 4.5, Mistral Large, Perplexity Sonar) sono configurati correttamente in `ai_research.py`, con chiamate parallele dal frontend e fallback sequenziale nel dossier. Funzionanti a livello di codice (le chiavi API vanno nel `.env`).

**Query database**: testate con DB di prova (schema `init_db()` + tabelle `fonti_narrative` e `lettere_personali`). `search_all()` e `get_all_records_for_ai()` restituiscono correttamente tutti i dataset, incluse lettere e fonti personali.

## Bug trovati e corretti

### 1. `Errore: letterePersonali is not defined` (templates/index.html)
In `renderSourcesTab()` la variabile `letterePersonali` era usata senza dichiarazione. L'eccezione risaliva fino al `catch` di `convSearch()`, che la mostrava **nel riquadro Risposta AI** e — punto chiave — **bloccava l'avvio delle 4 chiamate AI** (step 4 mai eseguito). Lo stesso crash lasciava il tab Fonti vuoto: il contatore era già stato scritto, l'elenco no. Un solo bug causava entrambi i sintomi segnalati.
**Fix**: dichiarata la variabile, inclusa nel conteggio, e i render avvolti in try/catch così un errore grafico non blocca mai più la ricerca AI.

### 2. Fonti: numero senza elenco né link
Oltre al crash sopra:
- **Testo lettere invisibile**: l'API `/api/search` restituisce il campo `excerpt` (SUBSTR di `corpo_testo`), ma il frontend leggeva solo `corpo_testo` → sempre vuoto. Fix: `corpo_testo || excerpt`.
- **Link mancanti**: aggiunta colonna Link con `url_scheda` (decorati) e `url` (documenti NARA); lettere e fonti narrative hanno già il dettaglio cliccabile e il download.
- **Citazioni Perplexity scartate** (`ai_research.py`): l'API restituisce `search_results`/`citations` ma venivano ignorate. Ora sono restituite al frontend e mostrate come elenco numerato di link cliccabili sotto la risposta.

### 3. Lettere e fonti personali assenti dal contesto AI (`ai_research.py`)
`get_all_records_for_ai()` recuperava `lettere_personali` e `fonti_narrative`, ma `_prepare_context()` non le inseriva nel prompt: le AI non vedevano mai le lettere, cuore dell'app. Aggiunte due sezioni dedicate al contesto.

### 4. Dossier verificato: report strutturati con fonti certe anche online (`biography.py`)
- **Nuovo passo di ricerca web verificata**: prima di generare il dossier, `_online_verified_context()` interroga Perplexity per contesto storico documentato; ogni fatto è ancorato a un URL citato. Se la chiave manca o la rete fallisce, il dossier si genera comunque dalle sole fonti locali.
- **Prompt con struttura obbligatoria**: SINTESI → RICOSTRUZIONE CRONOLOGICA (ogni fatto citato) → CONTESTO STORICO (solo se supportato da [WEB #n]) → FONTI CITATE (numerate, con URL) → LACUNE → FONTI DA VERIFICARE. Regola esplicita anti-invenzione e segnalazione delle discordanze tra fonti.
- **Fonti visibili, non solo un numero**: la risposta ora include `verified_sources` (elenco leggibile delle fonti locali usate) e `online_sources` (titolo + URL), mostrati nel frontend come elenchi espandibili con link cliccabili.

## File modificati (da copiare nel progetto)

| File | Sostituisce |
|---|---|
| `templates/index.html` | `Lettere_dal_fronte-main/templates/index.html` |
| `ai_research.py` | `Lettere_dal_fronte-main/ai_research.py` |
| `biography.py` | `Lettere_dal_fronte-main/biography.py` |

## Verifiche eseguite

- `py_compile` su `ai_research.py` e `biography.py`: OK
- Coerenza placeholder del prompt dossier (`format` vs template): OK
- Sintassi JS dell'intero script di `index.html` (`node --check`): OK
- Test funzionale `renderSourcesTab` con dati simulati: nessun ReferenceError, contatore corretto, elenco e link renderizzati
- Test query DB (`search_all`, `get_all_records_for_ai`) con record di prova su tutte le tabelle: OK
- Contesto AI: verificata presenza delle sezioni LETTERE PERSONALI OCR e FONTI NARRATIVE PERSONALI

## Suggerimenti successivi (non applicati)

1. Persistere le citazioni web in `ai_ricerche` (nuova colonna JSON) per riaverle nello storico.
2. Escapare l'HTML dei campi DB inseriti via template literal (rischio XSS da dati OCR).
3. Aggiungere `corpo_testo` completo all'API `/api/search` per le lettere (ora arriva solo l'excerpt di 500 caratteri).
