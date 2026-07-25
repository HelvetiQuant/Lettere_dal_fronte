# IMI Extractor — Pipeline Complete

> Documento di riferimento per il flusso dati end-to-end.
> Versione: 2026-07-25 — Internet Archive Integration + AI Provider Consolidation + LeBI Fase 4

---

## 1. Pipeline di Ricerca (Search Pipeline)

```
Utente digita query (es. "Rossi Mario")
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. SEARCH LOCALE — database.py search_all()             │
│     Tokenizzazione AND multi-parola                      │
│     Tabelle: internati, caduti_albooro, caduti_ministero,│
│     caduti_cwgc, caduti_sardi, caduti_bologna,           │
│     decorati, decorati_nastroazzurro, fonti_narrative,   │
│     fondi_archivistici, lettere_personali                │
│     Output: lista record con score di rilevanza          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. FEDERAZIONE PROVIDER — source_providers/federation   │
│     27 provider interrogati in parallelo (ThreadPool)    │
│     Provider reali: Arolsen, Bundesarchiv, TNA, NARA,    │
│     Europeana, Gallica, DDB, SHD, LAC, ABMC, AWM,        │
│     Internet Archive, Google Books, HathiTrust,          │
│     Internet Culturale, USSME, Archivi di Stato,         │
│     ICRC WW1, CRI Milano, LeBI/ANRP, Teca Digitale ACS   │
│     Output: metadati + URL diretti (no download)         │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. VALIDAZIONE — search_validator.py                    │
│     Estrae cues (cognome, nome, luogo) dai risultati     │
│     Filtra falsi positivi con _matches_entity()          │
│     Ricerca LeBI per-name (max 5 nomi estratti)          │
│     Ricerca ICRC WW1 per-name                             │
│     Output: external_sources con score e classificazione │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. COMPLIANCE GATE — compliance_gate.py                 │
│     Valuta ogni risultato contro source_policies          │
│     Classificazioni: PUBLIC_VIEW, METADATA_ONLY,         │
│     REQUEST_REQUIRED, AUTHORIZATION_REQUIRED,            │
│     RESTRICTED, UNREACHABLE, RIGHTS_UNKNOWN              │
│     Output: decisione + azione permessa                  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  5. RENDERING FRONTEND — templates/index.html            │
│     Mostra risultati locali + fonti esterne verificate   │
│     Badge provider (LeBI, ICRC, Arolsen, ecc.)           │
│     Link diretti + PDF dove disponibile                  │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Pipeline AI (AI Pipeline)

### 2.1 Architettura Multi-Provider

```
Richiesta AI (task_type: text, vision, ocr, web_search, embeddings)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  AI ROUTER — ai_router.py                                │
│  select_model(task_type, strategy)                       │
│     1. Query ai_providers WHERE status='active'          │
│     2. Filtra per capabilities richieste                 │
│     3. Esclude provider con circuit breaker aperto       │
│     4. Score combinato: quality × cost × latency         │
│     5. Policy: OpenAI primario per tutti i task          │
│     Output: {provider_code, model_identifier}            │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  AI CLIENT — ai_client.py call_ai()                      │
│  Ordine tentativi: [primario] + fallback rimanenti       │
│                                                        │
│  FALLBACK ORDER (2026-07-24):                           │
│  OpenAI → Anthropic → Mistral → Perplexity → Gemini     │
│                                                        │
│  Per ogni provider:                                     │
│    - Controlla budget rimanente                         │
│    - Chiama _PROVIDER_FUNCS[pcode]()                   │
│    - Registra task_run (provider, model, tokens, cost)  │
│    - Se ok: ritorna risultato                           │
│    - Se errore: attiva circuit breaker, prova prossimo  │
│                                                        │
│  Output: {ok, provider, model, content, tokens, cost,   │
│           latency_ms, fallback_used}                    │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Modelli AI attivi (2026-07-24)

| Provider | Codice | Modello default | Capability |
|----------|--------|-----------------|------------|
| OpenAI | `openai` | `gpt-4o-mini` | text, vision, ocr, embeddings, json |
| Anthropic | `anthropic` | `claude-sonnet-4-5-20250929` | text, vision, long-context |
| Mistral | `mistral` | `mistral-small-latest` | text, vision, ocr |
| Perplexity | `perplexity` | `sonar` | text, web_search |
| Google Gemini | `gemini` | `gemini-2.0-flash` | text, vision, embeddings |

### 2.3 Task Types e Routing

| Task Type | Capabilities | Primario | Fallback Chain |
|-----------|-------------|----------|----------------|
| `text_generation` | text | OpenAI | Anthropic → Mistral → Perplexity → Gemini |
| `web_search` | web_search | OpenAI | Perplexity → Anthropic → Mistral → Gemini |
| `vision_ocr` | vision, ocr | OpenAI | Mistral → Gemini → Anthropic |
| `embeddings` | embeddings | OpenAI | Gemini → Mistral |
| `biography` | text | OpenAI (gpt) | Claude → Mistral → Perplexity |
| `event_report` | text | OpenAI (gpt) | Perplexity → Claude → Mistral |

### 2.4 Circuit Breaker

Ogni provider ha un circuit breaker che si attiva dopo errori consecutivi:
- **Stato CLOSED**: funzionamento normale
- **Stato OPEN**: provider saltato per `breaker_timeout` secondi (default 300s)
- **Stato HALF-OPEN**: primo tentativo dopo timeout, se ok → CLOSED, se fail → OPEN

---

## 3. Pipeline Research-to-Index

```
Risultati ricerca (locali + federati)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. SUBJECT CREATION — research_to_index.py              │
│     Crea research_subjects da risultati rilevanti        │
│     Normalizza nomi (indexing_rules.titlecase_name)      │
│     Deduplica per match_key (cognome+nome+data_nascita)  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. SOURCE LINKING                                       │
│     Collega fonti trovate al subject                     │
│     Score di confidence basato su:                       │
│       - Match esatto cognome+nome (1.0)                  │
│       - Match parziale (0.5-0.8)                         │
│       - Match luogo/data (boost +0.2)                    │
│     Registra in research_sources                          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. GAP IDENTIFICATION                                   │
│     Confronta campi subject vs fonti collegate           │
│     Identifica campi mancanti (data_nascita, luogo,      │
│     grado, reparto, sorte, ecc.)                         │
│     Suggerisce provider per colmare gap                  │
│     Registra in research_gaps con priorità               │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. AUTO-INDEX PIPELINE — mass_index.py                  │
│     Batch processing: soldati/reparti/eventi/luoghi      │
│     ThreadPoolExecutor (4 AI in parallelo)               │
│     Watchdog: monitor ogni 5 min, riavvio automatico     │
│     Output: fonti_indice popolata (113K+ record)         │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Pipeline LeBI/ANRP

```
┌──────────────────────────────────────────────────────────┐
│  FASE 1: RICERCA — ProviderLeBI.search()                │
│  URL: /frontend_prodimi.php/caduti/search                │
│  Params: q=cognome, n=nome, l=luogo, y=anno, d=0         │
│  Parsing HTML: link /caduti/show/{ID}                    │
│  Output: lista record con ID, URL, metadati base         │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  FASE 2: METADATA — ProviderLeBI.get_metadata(id)        │
│  URL: /frontend_prodimi.php/caduti/show/{ID}             │
│  Parsing HTML (struttura verificata 2026-07):            │
│    - Sezioni: span.fallen-box-title (6 sezioni)          │
│    - Label: div.fallen-label                             │
│    - Valore: sibling div senza fallen-label              │
│    - Campi: div.col-xs-5.fallen-field-margins            │
│  Sezioni: ANAGRAFICA, POSIZIONE MILITARE, CATTURA,       │
│           DECESSO o RIENTRO, INTERNAMENTO, FONTI         │
│  Output: dict con cognome, nome, data_nascita, grado,    │
│          campi_internamento, pdf_url, ecc.                │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  FASE 3: CONFRONTO — /api/lebi/compare/{soldier_id}      │
│  Recupera record IMI locale (internati)                  │
│  Cerca su LeBI per cognome+nome                          │
│  Per ogni match:                                         │
│    - Recupera metadata dettagliata                       │
│    - Confronta 6 campi chiave (cognome, nome, data,      │
│      luogo, grado, internamento)                         │
│    - Calcola match_score (0-100%)                        │
│  Output: soldato locale + lista match ordinati per score │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  FASE 4: RENDERING FRONTEND — templates/index.html       │
│  Tab "LeBI" nel dossier soldato (solo IMI)               │
│  Card per ogni match con:                                │
│    - Titolo + match score badge (colorato)               │
│    - Campi corrispondenti (verde, con =)                 │
│    - Campi divergenti (rosso, con ≠)                     │
│    - Dettagli espandibili (scheda completa)              │
│    - Link scheda LeBI + PDF download                     │
└──────────────────────────────────────────────────────────┘
```

### 4.1 Endpoint API LeBI

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/lebi/search` | GET | Ricerca per cognome/nome/luogo/anno |
| `/api/lebi/record/{record_id}` | GET | Scheda biografica dettagliata |
| `/api/lebi/compare/{soldier_id}` | GET | Confronto IMI locale vs LeBI |

### 4.2 Frontend LeBI

| File | Funzione | Descrizione |
|------|----------|-------------|
| `templates/voci-data.js` | `loadLeBIComparison(id)` | Carica confronto via API |
| `templates/voci-data.js` | `loadLeBISearch(q, filters)` | Ricerca standalone LeBI |
| `templates/index.html` | Tab "LeBI" | Vista comparison nel dossier |

---

## 5. Pipeline Compliance Gate

```
Fonte esterna (URL, provider, classification)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  compliance_gate.evaluate(source, action, context)       │
│                                                        │
│  1. Lookup source_policy per domain                     │
│  2. Applica regole:                                      │
│     - UNREACHABLE → blocca                              │
│     - RESTRICTED → richiede authorization               │
│     - RIGHTS_UNKNOWN → blocca download                   │
│     - Persona vivente → richiede review                  │
│     - Dati sanitari → esclude dal log                    │
│     - METADATA_ONLY → solo metadati, no download         │
│     - PUBLIC_VIEW → visualizzazione permessa             │
│     - PUBLIC_DOWNLOAD → download permesso                │
│     - REQUEST_REQUIRED → richiesta formale necessaria    │
│     - AUTHORIZATION_REQUIRED → autorizzazione esplicita  │
│  3. Registra compliance_decision                         │
│  4. Se review necessaria → aggiunge a review_queue       │
│  Output: {decision, action_allowed, conditions}          │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Pipeline OCR

```
Documento (PDF/immagine)
    │
    ├──── Mistral OCR (mistral-ocr-latest) ──── primario
    │         │
    │         ▼ (se fallisce)
    ├──── GPT-4o Vision ──── fallback 1
    │         │
    │         ▼ (se fallisce)
    └──── pdfplumber ──── fallback 2 (text extraction)
              │
              ▼
    Testo estratto + metadata strutturati
              │
              ▼
    Compliance Gate (se dati sanitari → authorization required)
```

---

## 7. Pipeline Biografia AI

```
Soldato (ID)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. RACCOLTA DATI — soldier_dashboard.get_soldier_data() │
│     Record internato + fonti collegate + timeline        │
│     Perspectives (it/de/allied) dai link verificati      │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. PROMPT — biography.py BIOGRAPHY_PROMPT               │
│     Istruzioni: usa solo dati verificati, cita fonti,    │
│     non inventare, struttura in paragrafi                │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. GENERAZIONE — biography.py generate_biography()      │
│     Fallback order: gpt → claude → mistral → perplexity  │
│     Per provider: chiama AI, estrae testo, verifica      │
│     Se ok: ritorna biografia + fonti online              │
│     Se fail: prova prossimo provider                     │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. RENDERING — templates/index.html                     │
│     Tab "Biografia AI" nel dossier soldato               │
│     Mostra testo + fonti online + stato generazione      │
└──────────────────────────────────────────────────────────┘
```

---

## 8. Pipeline Event Research

```
Evento (nome)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. DATI EVENTO — events.py                              │
│     Dettagli evento + caduti + decorati + internati      │
│     Graph data (luoghi, paesi, mesi, soldati)            │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. REPORT AI — event_research_engine.py                 │
│     4 tab: Panoramica, Fonti, Punti di vista, Cronologia │
│     Provider per tab: OpenAI (gpt) per tutti             │
│     Fallback: gpt → perplexity → claude → mistral        │
│     Modalità: singola o parallela (ThreadPoolExecutor)   │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. RENDERING — templates/index.html                     │
│     Tab evento con report AI + progress bar              │
│     Graph SVG interattivi (event delegation)             │
└──────────────────────────────────────────────────────────┘
```

---

## 9. Pipeline Import Fonti Esterne

```
Provider esterno (LeBI, ICRC, CRI, ecc.)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. DISCOVERY — SourceAdapter.discover()                 │
│     Scansiona portale, estrae lista record               │
│     Rate limiting rispettato                             │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. PARSE — SourceAdapter.parse_record(url)              │
│     Download HTML, parsing BeautifulSoup                 │
│     Estrae: people, places, military_units, camps,       │
│     subjects, digital_object                             │
│     Compute metadata_hash per dedup                      │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. IMPORT — external_metadata_service.run_import()      │
│     Insert/update external_records                       │
│     Supporto checkpoint/resume (batch_size)              │
│     LeBI: import_single_lebi_record,                     │
│           import_lebi_by_surname                          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. LINKING — external_link_service.py                   │
│     Match campi: cognome, nome, data_nascita,            │
│     luogo, campo_internamento, data_decesso              │
│     Detect omonimie (same name, different person)        │
│     review_link_with_type (lebi_match bidirezionale)     │
└──────────────────────────────────────────────────────────┘
```

---

## 9.5. Pipeline Internet Archive (ia_pipeline)

```
Evento (nome) — resolve_event()
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. DISCOVERY — ia_pipeline.discover()                   │
│     Query: advancedsearch.php con filtri:                 │
│       - date:[conflict_range] (WWI: 1914-1918, WW2: 1939) │
│       - mediatype:(texts)                                │
│       - Termini: nome evento + keywords + aliases         │
│     Fallback: query più larga se <5 risultati             │
│     Output: lista item IA (identifier, title, date, ...)  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. EVALUATION — ia_evaluation.evaluate_candidates()     │
│     Per ogni item:                                       │
│       - Rileva conflitto (WWI/WW2/interwar/unknown)       │
│       - Compatibilità temporale (range evento vs item)    │
│       - Compatibilità geografica (token luogo vs metadata)│
│       - Pertinenza storiografica (keywords in title/desc) │
│       - Qualità documento (OCR, mediatype, downloads)     │
│       - Filtro search page URL (rifiuta URL generici)     │
│     Score 0.0–1.0, stato: accepted/candidate/rejected     │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. ITEM ANALYSIS — ia_pipeline.analyze_item()           │
│     a) Metadata API: GET /metadata/{identifier}          │
│     b) Asset selection: hOCR > DjVu > PDF > text          │
│        (ia_locator.select_best_asset)                    │
│     c) Locator: locate_passage()                          │
│        - Fetch hOCR → parse_hocr_pages()                 │
│        - Fallback: DjVu text → parse_djvu_text()         │
│        - Fallback: page count only                       │
│        - Search: termini evento nelle pagine              │
│        - Output: PageLocator (page, snippet, bbox, conf)  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. INGESTION PREVIEW — ia_pipeline.build_ingestion()    │
│     Precompila form con metadati reali:                  │
│       - title, description, creator, date, place         │
│       - source_url (deep link), thumbnail                │
│       - page_start, page_end, snippet (da locator)       │
│       - detected_conflict, overall_score, status         │
│       - suggested_link_type, suggested_war               │
│     Utente può modificare prima di confermare             │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  5. CONFIRM — ia_pipeline.confirm_ingestion()            │
│     a) Upsert fonti_indice (metadati + URL + locator)     │
│     b) Upsert archivio_documenti (provider=InternetArchive)│
│     c) Create event_links (evento → fonte/documento)     │
│     d) Create claim (claim_service.create_claim +         │
│        add_evidence con page_start/page_end)              │
│     Output: fonte_id, documento_id, event_link_id, claims  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  6. RECONSTRUCT — ia_pipeline.reconstruct_from_ia()      │
│     Per ogni item accepted/candidate:                    │
│       - Analysis completa (metadata + asset + locator)   │
│       - Estrazione claim da snippet (date, places, units) │
│     Output: sources[], claims[], locators[]               │
│     Integrabile in event_evidence_pipeline.collect_evidence│
└──────────────────────────────────────────────────────────┘
```

### 9.5.1 Moduli IA
| File | Funzione | Descrizione |
|------|----------|-------------|
| `ia_evaluation.py` | `evaluate_candidate()` | Valuta singolo item (war, tempo, geo, relevance, quality) |
| `ia_evaluation.py` | `evaluate_candidates()` | Valuta lista item, ordina per score |
| `ia_locator.py` | `select_best_asset()` | Seleziona miglior file (hOCR > DjVu > PDF) |
| `ia_locator.py` | `parse_hocr_pages()` | Parser hOCR HTML → testo per pagina + bbox |
| `ia_locator.py` | `parse_djvu_text()` | Parser DjVu text layer → testo per pagina |
| `ia_locator.py` | `locate_passage()` | Pipeline locator completa con fallback |
| `ia_pipeline.py` | `discover()` | Discovery + evaluation per evento |
| `ia_pipeline.py` | `analyze_item()` | Metadata + asset + locator per item |
| `ia_pipeline.py` | `build_ingestion_preview()` | Form precompilato per conferma |
| `ia_pipeline.py` | `confirm_ingestion()` | Archivia in DB + crea link + claim |
| `ia_pipeline.py` | `reconstruct_from_ia()` | Ricostruzione evento da fonti IA |

### 9.5.2 Endpoint API IA (pianificati)
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/ia/discover` | GET | Discovery item IA per evento |
| `/api/ia/item/{identifier}` | GET | Metadati + asset + locator |
| `/api/ia/analyze` | GET | Analisi completa (evaluation + locator) |
| `/api/ia/ingestion-preview` | GET | Form precompilato |
| `/api/ia/confirm` | POST | Conferma ingestion |
| `/api/ia/reconstruct` | GET | Ricostruzione evento |
| `/api/ia/audit` | GET | Audit non distruttivo vecchi link IA |

---

## 10. Mappa Endpoint API (312 route totali)

### Ricerca e Dossier
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/search` | GET | Ricerca multi-tabella con tokenizzazione AND |
| `/api/internati/{id}/fonti` | GET | Fonti archivistiche per soldato |
| `/api/internati/{id}/links` | GET | Ricerca federata reale per soldato |
| `/api/internati/{id}/opengraph` | GET | Card OpenGraph per condivisione |
| `/api/biography` | POST | Biografia AI (soldato o evento) |

### LeBI/ANRP
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/lebi/search` | GET | Ricerca LeBI per cognome/nome/luogo/anno |
| `/api/lebi/record/{id}` | GET | Scheda biografica dettagliata LeBI |
| `/api/lebi/compare/{soldier_id}` | GET | Confronto IMI locale vs LeBI |

### AI e Research
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/research/subjects` | GET | Lista soggetti di ricerca |
| `/api/research/gaps` | GET | Gap identificati |
| `/api/research/auto-index` | POST | Auto-indicizzazione batch |
| `/api/mass-index/start` | POST | Pipeline singola in background |
| `/api/mass-index/start-parallel` | POST | 7 AI in parallelo |
| `/api/mass-index/status` | GET | Stato pipeline |
| `/api/report` | GET | Report narrativo AI on-demand |

### Fonti Esterne
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/sources/search` | GET | Ricerca federata su 27 provider |
| `/api/red-cross/search` | GET | Ricerca ICRC + CRI Milano |
| `/api/acs/registri` | GET | Lista registri IMI Teca Digitale ACS |

### Compliance
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/compliance/policies` | GET/POST | CRUD policy |
| `/compliance/evaluate` | POST | Valuta fonte |
| `/compliance/decisions` | GET | Storico decisioni |
| `/compliance/review` | GET | Coda revisione |
| `/compliance/authorize` | POST | Autorizza fonte |

### Eventi
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/events/1gm/{name}` | GET | Dettaglio evento 1GM |
| `/api/events/1gm/{name}/caduti` | GET | Caduti evento |
| `/api/events/1gm/{name}/decorati` | GET | Decorati evento |
| `/api/events/{name}/internati` | GET | Internati evento |

---

## 11. Database Schema (tabelle principali)

```
STAR SCHEMA
├── entita (688K nodi: persone, luoghi, eventi, unità)
├── collegamenti (4.8M archi)
│
├── DATASET STORICI
│   ├── internati (20K IMI WW2 — Bolzano)
│   ├── caduti_albooro (342K Albo d'Oro)
│   ├── caduti_ministero (162K Caduti Ministero)
│   ├── caduti_cwgc (506K Commonwealth)
│   ├── caduti_sardi, caduti_bologna
│   ├── decorati (1.3K), decorati_nastroazzurro (280K)
│   ├── fonti_narrative (40 fonti personali)
│   └── lettere_personali (lettere OCR)
│
├── RESEARCH ENGINE
│   ├── research_subjects (soggetti indicizzati)
│   ├── research_sources (fonti collegate)
│   ├── research_gaps (campi mancanti)
│   ├── ai_providers (5 provider: OpenAI, Anthropic, Mistral, Perplexity, Gemini)
│   ├── ai_models (modelli per provider)
│   └── ai_task_runs (log esecuzioni AI)
│
├── FONTI ESTERNE
│   ├── external_records (record importati da provider)
│   ├── external_links (collegamenti record esterni ↔ internati)
│   ├── fonti_indice (113K+ fonti indicizzate remote)
│   └── source_fetch_cache (cache download)
│
├── COMPLIANCE
│   ├── source_policies (policy per dominio)
│   ├── compliance_decisions (storico decisioni)
│   ├── compliance_authorizations (autorizzazioni)
│   └── compliance_review_queue (coda revisione)
│
└── PERCORSO RICONOSCIMENTI
    ├── rc_candidates, rc_sources, rc_practices
    ├── rc_documents_v2, doc_versions, doc_checklists
    ├── communications, comm_threads, deadlines
    ├── rc_descendant_contacts, institutional_contacts
    └── audit_log
```

---

## FRONTEND ARCHITECTURE (v2.0)

### Stack
- **React 19** + **TypeScript 6** + **Vite 8**
- **react-router-dom 7** — routing client-side
- **lucide-react** — icone
- **Design tokens CSS** — variabili custom, no framework esterno
- **Proxy Vite** → FastAPI backend su `:8000`

### Struttura directory
```
frontend/
├── vite.config.ts              # Proxy /api→:8000, alias @→src
├── package.json                # react, react-dom, react-router-dom, lucide-react
├── tsconfig.app.json           # Path alias @/*, verbatimModuleSyntax
├── ARCHITECTURE.md             # Documento architetturale completo
├── src/
│   ├── main.tsx                # Entry point, importa tokens.css
│   ├── App.tsx                 # BrowserRouter + Routes (7 route)
│   ├── styles/
│   │   └── tokens.css          # Design tokens (mirror templates/shared/design-tokens.css)
│   ├── api/
│   │   ├── client.ts           # API client: get/post/patch/del + oggetto api{}
│   │   └── types.ts            # Type definitions per tutte le risposte API
│   ├── components/
│   │   ├── ui.tsx              # Card, Tag, Button, Input, Loading, ErrorBanner, StatCard, EmptyState
│   │   └── Layout.tsx          # Header sticky, nav, banner, footer
│   └── pages/
│       ├── HomePage.tsx            # / — hero, search, stats, eventi
│       ├── ExplorePage.tsx         # /esplora — ricerca validata
│       ├── EventsPage.tsx          # /eventi + /eventi/:name — dossier
│       ├── ResearchPage.tsx        # /ricerca — orchestrator V2
│       ├── AdminPage.tsx           # /admin — stato, fonti, operazioni
│       └── SoldierDossierPage.tsx  # /soldato/:type/:id — dettaglio
```

### Routing
| Route | Pagina | Descrizione |
|-------|--------|-------------|
| `/` | HomePage | Hero, search bar, statistiche DB, eventi in evidenza |
| `/esplora?q=` | ExplorePage | Ricerca validata: internati, caduti, fonti esterne |
| `/eventi` | EventsPage | Lista eventi storici 1GM |
| `/eventi/:eventName` | EventDossierPage | Dossier: caduti, decorati, internati, documenti |
| `/ricerca` | ResearchPage | Ricerca AI V2: orchestrator, frammenti, timeline, narrative |
| `/admin` | AdminPage | Admin: stato sistema, fonti, operazioni batch |
| `/soldato/:type/:id` | SoldierDossierPage | Dossier: dettaglio, fonti, link, LeBI comparison |

### API Client → Backend Mapping (60+ endpoint)

#### Search (5)
- `api.search()` → `GET /api/search`
- `api.searchValidated()` → `GET /api/search-validated`
- `api.convSearch()` → `GET /api/conv-search`
- `api.searchWW1()` → `GET /api/search/ww1`
- `api.searchConfirm()` → `POST /api/search/confirm`

#### Stats / Status (7)
- `api.status()` → `GET /api/status`
- `api.statsWW1()` → `GET /api/stats/ww1`
- `api.decoratiStatus()` → `GET /api/decorati`
- `api.entitaStats()` → `GET /api/entita`
- `api.fondiList()` → `GET /api/fondi`
- `api.fontiRisorse()` → `GET /api/fonti-risorse`
- `api.sourceStats()` → `GET /api/source/stats`

#### Internati / Soldati (6)
- `api.internatiDetail()` → `GET /api/internati/:id/detail`
- `api.internatiFonti()` → `GET /api/internati/:id/fonti`
- `api.internatiLinks()` → `GET /api/internati/:id/links`
- `api.internatiOpenGraph()` → `GET /api/internati/:id/opengraph`
- `api.cadutiDetail()` → `GET /api/caduti/:id`
- `api.decoratiDetail()` → `GET /api/decorati/:id`

#### Events (5)
- `api.events1gm()` → `GET /api/events/1gm`
- `api.eventDossier()` → `GET /api/events/1gm/:name`
- `api.eventCaduti()` → `GET /api/events/1gm/:name/caduti`
- `api.eventDecorati()` → `GET /api/events/1gm/:name/decorati`
- `api.eventInternati()` → `GET /api/events/:name/internati`

#### Graph (4)
- `api.graphLuoghi()` → `GET /api/graph/luoghi`
- `api.graphMesi()` → `GET /api/graph/mesi`
- `api.graphPaesi()` → `GET /api/graph/paesi`
- `api.graphSoldatiArch()` → `GET /api/graph/soldati/architecture`

#### External Sources (5)
- `api.icrcSearch()` → `GET /api/icrc/search`
- `api.icrcFilters()` → `GET /api/icrc/filters`
- `api.lebiSearch()` → `POST /api/lebi/search`
- `api.lebiRecord()` → `GET /api/lebi/record/:id`
- `api.lebiCompare()` → `GET /api/lebi/compare/:soldierId`

#### Research Orchestrator V1 (8)
- `api.researchQuery()` → `POST /api/research/query`
- `api.researchAutoIndex()` → `POST /api/research/auto-index`
- `api.researchSubjects()` → `GET /api/research/subjects`
- `api.researchSubjectDetail()` → `GET /api/research/subjects/:id`
- `api.researchSubjectDashboard()` → `GET /api/research/subjects/:id/dashboard`
- `api.researchSubjectUpdate()` → `PATCH /api/research/subjects/:id`
- `api.researchGaps()` → `GET /api/research/gaps`
- `api.researchStats()` → `GET /api/research/stats`

#### Research Orchestrator V2 (6)
- `api.researchV2Create()` → `POST /api/research/v2/create`
- `api.researchV2Plan()` → `GET /api/research/v2/plan/:id`
- `api.researchV2Plans()` → `GET /api/research/v2/plans`
- `api.locatorValidate()` → `POST /api/research/v2/locator/validate`
- `api.researchV2Preflight()` → `POST /api/research/v2/preflight`
- `api.researchV2Prompt()` → `GET /api/research/v2/prompt/:name`

#### Admin Operations (7)
- `api.entitaBuild()` → `POST /api/entita/build`
- `api.entitaStop()` → `POST /api/entita/stop`
- `api.decoratiScrape()` → `POST /api/decorati/scrape`
- `api.decoratiStop()` → `POST /api/decorati/stop`
- `api.fondiExtractAll()` → `POST /api/fondi/extract-all`
- `api.fondiStop()` → `POST /api/fondi/stop`
- `api.fontiScrape()` → `POST /api/fonti-risorse/scrape`

### Design System
- Design tokens in `src/styles/tokens.css` (mirror di `templates/shared/design-tokens.css`)
- Supporto dark mode via `@media (prefers-color-scheme: dark)`
- Componenti riutilizzabili: `Card`, `Tag`, `Button`, `Input`, `Loading`, `ErrorBanner`, `StatCard`, `EmptyState`

### Sviluppo
```bash
cd frontend
npm install
npm run dev      # Vite dev server :5173 con proxy → :8000
npm run build    # Build produzione in dist/
```

### Coesistenza con frontend legacy
- `templates/index.html` (DC runtime, 3173 righe) rimane servito da FastAPI su `/`
- `frontend/dist/` può essere montato da FastAPI su route separata (es. `/app/`) o servito da CDN
- Entrambi i frontend condividono gli stessi design tokens e gli stessi endpoint API
