# IMI Extractor — Pipeline Complete

> Documento di riferimento per il flusso dati end-to-end.
> Versione: 2026-07-28 — Linking v2 + RAG Pipeline + AI Runtime + Graph Provenance + Event Canonical + Map Features

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

---

## 12. Pipeline Linking v2 (Provenance-Aware)

### 12.1 Architettura

Sostituisce i 6 script legacy frozen (`_gen_event_links.py`, `_gen_record_links.py`, ecc.) con un sistema modulare, provenance-aware, idempotente.

```
Record sorgente (es. internati #12345)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. NORMALIZATION — linking/normalization.py             │
│     normalize_name(): NFKD + accent stripping + lower    │
│     normalize_date(): ISO/Italian/year/range → precision │
│     normalize_place(): NFKD + strip, historical aliases  │
│     VERSION = "2.0.0" (versionata per reproducibilità)   │
│     Output: NormalizedName, NormalizedDate, NormalizedPlace │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. CANDIDATE GENERATION — linking/candidate_generation  │
│     Blocking indexes (O(N+M), non O(N*M)):               │
│       - phonetic_cognome: 3 consonanti prefisso          │
│       - name_initial: cognome[:4] + nome[:1]             │
│       - birth_year: anno nascita bucket                   │
│       - place_prefix: luogo normalizzato[:6]             │
│       - matricola: exact match                           │
│     Dedup per (source_ns, source_key, target_ns,         │
│                target_key, block_type)                   │
│     Output: list[CandidatePair]                          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. FEATURE EXTRACTION — linking/feature_extraction.py   │
│     extract_features_person_source():                    │
│       - name_cognome_exact / phonetic                    │
│       - birth_date_compatible (date_overlap)             │
│       - birth_place_compatible (_place_match con \b)     │
│       - same_matricola, same_unit                        │
│     extract_features_person_event():                     │
│       - temporal_overlap (date_overlap persona↔evento)   │
│       - geographic_compatible                            │
│       - unit_in_theater (keyword match con \b)           │
│     extract_features_document_event():                   │
│       - _word_boundary_match(keyword, text) con \b       │
│       - Salta AMBIGUOUS_KEYWORDS (campo, russia, ecc.)   │
│       - keyword_in_title bonus                           │
│     ConflictFlags:                                       │
│       - ww1_ww2_mismatch (veto)                          │
│       - born_after_event (veto)                          │
│       - died_before_event (veto)                         │
│       - omonimia_no_discriminator (veto)                 │
│       - matricola_mismatch (veto)                        │
│       - geo_incompatible, unit_not_active, event_too_broad│
│     Output: (Features, ConflictFlags)                    │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. SCORING — linking/scoring.py                        │
│     score_candidate(features, conflicts):                │
│       - Base: name_cognome_exact +0.15, phonetic +0.08  │
│       - name_nome_exact +0.05                            │
│       - 0 discriminatori → weak, score 0.0-0.2          │
│       - 1 discriminatore → moderate, +0.2               │
│       - 2 discriminatori → moderate, +0.35              │
│       - 3+ discriminatori → strong, +0.45               │
│       - same_matricola +0.2 (fortissimo)                 │
│       - birth_date + birth_place +0.1                    │
│       - document_citation +0.1                           │
│       - Cap 0.95 (mai 1.0)                               │
│       - Veto → score max 0.15, evidence_strength=weak   │
│       - confidence_calibrated = NULL (no golden dataset) │
│     can_be_confirmed:                                    │
│       not has_veto AND n_discriminators >= 2             │
│       AND evidence_strength in (moderate, strong)        │
│       AND features.name_match                            │
│     Output: ScoreResult(raw_score, evidence_strength,    │
│             conflict_flags, can_be_confirmed)            │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  5. PERSISTENCE — linking/persistence.py                 │
│     create_pipeline_run(): UUID + code_commit_sha +      │
│       configuration_hash (SHA256 del config JSON)       │
│     register_resource(): idempotente su (namespace, key) │
│     upsert_relation():                                   │
│       - Chiave semantica: (source, target, type,         │
│         algorithm_name, algorithm_version)              │
│       - Symmetric: normalizza orientazione A-B vs B-A    │
│       - Se esiste → UPDATE features/score/pipeline_run   │
│       - Se nuovo → INSERT con tutti i campi provenance   │
│     finish_pipeline_run(): counts + status + error       │
│     Output: relation_id (UUID)                           │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  6. CLI — linking/cli.py                                │
│     python -m linking.cli generate --dry-run             │
│     python -m linking.cli generate --execute             │
│     python -m linking.cli legacy-relations audit         │
│     python -m linking.cli legacy-relations quarantine    │
│       --dry-run / --execute                              │
│     python -m linking.cli legacy-relations restore       │
│     python -m linking.cli legacy-relations list          │
│     python -m linking.cli kill-switch                    │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  7. API v2 — linking_v2_api.py                          │
│     GET  /api/v2/status/manifest   (conteggi + kill switch)│
│     GET  /api/v2/events            (eventi canonici v2)  │
│     GET  /api/v2/relations         (relazioni con features)│
│     POST /api/v2/kill-switch       (toggle legacy jobs)  │
└──────────────────────────────────────────────────────────┘
```

### 12.2 Schema v2 (16 tabelle nuove)

```
LINKING V2 SCHEMA (SQLite — imi_internati.db)
├── resource_registry          (UUID PK, kind, namespace, key)
├── historical_events          (conflict_code, event_type, parent_event_id)
├── relations                  (source_id, target_id, type, algorithm,
│                               features JSON, raw_score, evidence_strength,
│                               conflict_flags, pipeline_run_id)
├── claims_v2                  (claim_type, subject_id, predicate, object_id)
├── pipeline_runs              (algorithm_version, code_commit_sha,
│                               configuration_hash, status, counts)
├── legacy_relation_quarantine (migration_run_id, restored_at)
├── golden_dataset_labels      (case_id, expected_status, expected_score)
├── snapshot_metadata          (snap_id, checksum, table_count)
├── archival_metadata          (resource_id, provenance_json)
└── ... (6 tabelle graph provenance, vedi §15)
```

### 12.3 Kill Switch

```python
# linking/kill_switch.py
class LegacyJob(Enum):
    EVENT_LINKS              # _gen_event_links.py
    RECORD_LINKS             # _gen_record_links.py
    CLEAN_BAD_LINKS          # _clean_bad_links.py
    FIX_GAIASCHI             # _fix_gaiaschi_db.py
    SYNC_EVENT_LINKS_SUPABASE
    SYNC_RECORD_LINKS_SUPABASE

# Tutti disabled by default
# Enable via env: LEGACY_JOB_LEGACY_EVENT_LINKS=true
# Force execute: LEGACY_JOB_FORCE_EXECUTE=true
# assert_frozen() → RuntimeError se disabled
```

### 12.4 Golden Dataset

8 casi obbligatori per calibrazione:
- 2 positive (match confermato, 2+ discriminatori)
- 2 negative (veto conflict, same name different person)
- 2 uncertain (1 discriminatore, omonimia possibile)
- 2 edge cases (WW1/WW2 same place, date range overlap)

### 12.5 Fix tecnici v2 vs legacy

| # | Errore legacy | Fix v2 | File |
|---|--------------|--------|------|
| 1 | `in` substring matching | `\b` word boundary regex | `feature_extraction.py:341-349` |
| 2 | Keyword ambigue senza discriminatore | `AMBIGUOUS_KEYWORDS` set + skip | `feature_extraction.py:78-82` |
| 3 | WW1/WW2 misti senza conflict detection | `ww1_ww2_mismatch` veto | `feature_extraction.py:173-176` |
| 4 | Confidence 0.9 arbitraria | `evidence_strength` + `confidence_calibrated=NULL` | `scoring.py:105` |
| 5 | Skip-or-insert (no idempotency) | `upsert_relation()` con chiave semantica | `persistence.py:118-196` |
| 6 | No provenance | `algorithm_version` + `pipeline_run_id` + `features` JSON | `persistence.py:180-193` |
| 7 | `_place_match()` substring | `_word_boundary_match()` per luoghi | `feature_extraction.py:325-338` |

---

## 13. Pipeline RAG (Retrieval-Augmented Generation)

### 13.1 Architettura

```
Query utente (es. "Mauthausen prigionia italiana WW1")
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. RETRIEVAL — rag_pipeline.py retrieve()               │
│     Hybrid: FTS5 (BM25) + metadata filters              │
│                                                        │
│     FTS5:                                               │
│       - Tokenizzazione \w{2,} + wildcard *              │
│       - idx_{table}_fts (FTS5 virtual table)            │
│       - ORDER BY rank (BM25 scoring)                    │
│       - Tabelle: internati, caduti_albooro, decorati,   │
│         menzioni, fonti_indice, archivio_documenti,     │
│         fondi_archivistici                               │
│                                                        │
│     Metadata filters:                                   │
│       - date_start / date_end → date_fields[]           │
│       - place → place_fields[] LIKE %place%             │
│       - TABLE_SPECS definisce campi per tabella         │
│                                                        │
│     Events DB (eventi_1gm):                             │
│       - LIKE search su nome, descrizione, aliases,      │
│         keywords                                        │
│                                                        │
│     Dedup per chunk_id ({table}:{id})                   │
│     Output: list[RetrievedChunk] (max 30)               │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. RERANKING — rag_pipeline.py rerank()                 │
│     Boost factors:                                      │
│       - title_match: +0.2 (query in title)              │
│       - text_match: +0.1 (query in text)                │
│       - archival_source: +0.15 (fonti_indice, fondi)    │
│       - primary_document: +0.2 (archivio_documenti,     │
│         lettere_personali)                               │
│       - mention_record: +0.1 (menzioni)                 │
│       - temporal_match: +0.15 (same year as event)      │
│       - temporal_close: +0.08 (±1 year)                 │
│       - geographic_match: +0.12 (place overlap)         │
│     Cap 1.0, sort desc by reranked_score                │
│     Output: list[RerankedChunk] with reasons[]          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. CONTEXT BUILDER — rag_pipeline.py build_context()    │
│     System prompt: regole citazione [fonte: table#id]   │
│       - Solo dati verificati, no invenzioni             │
│       - Distingui confirmed vs single-source            │
│       - Stato epistemico: confirmed, probable,          │
│         candidate, to_review, conflicting, unverifiable │
│     Token budget: max 6000 (default)                    │
│     Truncation: se superato, tronca + warning           │
│     Output: RAGContext(system_prompt, user_context,     │
│             chunks, citations, token_estimate)          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4. AI GENERATION — ai_runtime.get_adapter().generate() │
│     Adapter: LMStudioAdapter | RemoteAIAdapter |        │
│              DeterministicTestAdapter                   │
│     Input: RAGContext.system_prompt + user_context      │
│     Output: GenerateResult(text, tokens, latency,       │
│             provider, model)                            │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  5. OUTPUT VALIDATION — rag_pipeline.py                 │
│     validate_ai_output(text, citations):                │
│       - Check [fonte: table#id] references              │
│       - Hallucination patterns:                         │
│         "secondo la storiografia", "come è noto",       │
│         "probabilmente morto/catturato/ferito"          │
│       - Long output senza citazioni → warning           │
│     Output: (is_valid, issues[])                        │
└──────────────────────────────────────────────────────────┘
```

### 13.2 API RAG

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/rag/retrieve` | POST | Retrieval + reranking + context build |
| `/api/rag/validate` | POST | Validazione output AI |

### 13.3 Data Classes

```python
@dataclass
class RetrievedChunk:
    chunk_id: str          # "{table}:{id}"
    source_table: str
    source_id: int
    title: str
    text: str
    score: float
    retrieval_method: str  # "fts" | "metadata" | "semantic"
    metadata: dict

@dataclass
class RerankedChunk:
    chunk: RetrievedChunk
    reranked_score: float
    rerank_reasons: list[str]

@dataclass
class RAGContext:
    system_prompt: str
    user_context: str
    chunks: list[RerankedChunk]
    citations: list[dict]
    token_estimate: int
    truncated: bool
    warnings: list[str]
```

---

## 14. Pipeline AI Runtime

### 14.1 Architettura Adapter

```
Codice applicativo (biography.py, event_research, RAG, ecc.)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  ai_runtime.get_adapter() → InferenceAdapter (singleton)│
│                                                        │
│  Selezione adapter (priorità):                          │
│    1. LM_STUDIO_API_URL env → LMStudioAdapter          │
│       (OpenAI-compatible, CPU quantized, locale)        │
│    2. AI_LOCAL_ONLY=true → DeterministicTestAdapter    │
│       (no real AI, per test)                            │
│    3. Default → RemoteAIAdapter                         │
│       (delega ad ai_client.py con fallback chain)       │
└──────────────────────┬───────────────────────────────────┘
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
    LMStudioAdapter  RemoteAIAdapter  DeterministicTestAdapter
    ┌────────────┐  ┌────────────┐  ┌────────────────────┐
    │ /v1/chat/  │  │ ai_client  │  │ Echo / static      │
    │ completions│  │ .call_ai() │  │ response           │
    │            │  │            │  │                    │
    │ /v1/embed  │  │ Fallback:  │  │ embed(): [0.0]*384 │
    │ dings      │  │ OpenAI→    │  │                    │
    │            │  │ Anthropic→ │  │ health(): ok       │
    │ health:    │  │ Mistral→   │  │                    │
    │ /v1/models │  │ Perplexity │  │                    │
    │            │  │ → Gemini   │  │                    │
    └────────────┘  └────────────┘  └────────────────────┘
```

### 14.2 Interfaccia InferenceAdapter

```python
class InferenceAdapter(ABC):
    def generate(system, user, *, max_tokens, temperature, task_type, timeout) -> GenerateResult
    def generate_structured(system, user, *, ...) -> GenerateResult  # JSON output
    def embed(text, *, timeout) -> EmbedResult
    def health() -> HealthResult
```

### 14.3 GenerateResult

```python
@dataclass
class GenerateResult:
    ok: bool
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    error: str
    citations: list[dict]
    fallback_used: bool
```

### 14.4 API AI Runtime

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/ai-runtime/health` | GET | Stato adapter (healthy, provider, model, local) |
| `/api/ai-runtime/config` | GET | Configurazione (no secrets): provider, local_only, fallback_order |
| `/api/ai-runtime/benchmark` | POST | Benchmark generazione + latenza |
| `/api/ai-runtime/reset` | POST | Reset singleton adapter (per test) |

### 14.5 Configurazione

```yaml
# config/ai_runtime.yaml
provider: lm_studio | remote | test
local_only: false
generation:
  max_tokens: 4096
  temperature: 0.3
embedding:
  model: bge-small-it
remote:
  fallback_order: [openai, anthropic, mistral, perplexity, gemini]
```

---

## 15. Pipeline Graph Provenance

### 15.1 Architettura

```
Frontend (GraphEntityPage.tsx) → /api/graph/entity/{table}/{id}
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  graph_service.py — get_entity_graph()                   │
│  Read-through adapter su 5 tabelle legacy:               │
│    - event_links (891K righe, eventi_1gm.db)             │
│    - record_links (169K righe, imi_internati.db)         │
│    - external_links (record esterni ↔ internati)         │
│    - claim_relations (claim ↔ entità)                    │
│    - menzioni (10K righe)                                │
│                                                        │
│  Per ogni arco:                                          │
│    - Sistema originale (event_links, record_links, ecc.)│
│    - ID originale preservato                             │
│    - Nessun candidato legacy → confirmed automatico     │
│    - Label umane (RELATION_LABELS)                       │
│  Output: GraphResponse(nodes[], edges[], evidence[])    │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Edge Review — graph_service.py review_edge()            │
│  POST /api/graph/edges/{edge_id}/review                  │
│    - status: confirmed | rejected | needs_review        │
│    - reviewer, notes, timestamp                          │
│    - Scrive in graph_edge_reviews                        │
└──────────────────────────────────────────────────────────┘
```

### 15.2 Schema Graph (6 tabelle)

```
GRAPH SCHEMA (imi_internati.db)
├── graph_nodes          (id, table, record_id, label, kind)
├── graph_edges          (id, source_node, target_node,
│                         relation_type, source_system, source_id,
│                         confidence, status)
├── graph_edge_reviews   (edge_id, reviewer, status, notes, timestamp)
├── graph_pipeline_runs  (run_id, algorithm, started_at, status)
├── graph_integrity_issues (edge_id, issue_type, description)
└── archival_metadata    (resource_id, provenance_json)
```

### 15.3 API Graph

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/graph/entity/{table}/{id}` | GET | Grafo entità (nodi + archi + evidenze) |
| `/api/graph/edges/{edge_id}/review` | POST | Review arco (confirm/reject/needs_review) |
| `/api/graph/luoghi` | GET | Dati grafo luoghi |
| `/api/graph/mesi` | GET | Dati grafo mesi |
| `/api/graph/paesi` | GET | Dati grafo paesi |
| `/api/graph/soldati/architecture` | GET | Dati grafo soldati/architettura |

### 15.4 Frontend Graph

- `GraphEntityPage.tsx` — pagina dedicata con ForceGraph visualization
- Filtri per status (confirmed, candidate, rejected)
- Click su arco → panel di review
- Click su nodo → navigazione a entità

---

## 16. Pipeline Event Canonical

### 16.1 Architettura

```
Evento (nome o ID)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. SCHEMA — event_schema.py                             │
│     12 colonne additive su eventi_1gm:                   │
│       conflict_code (ww1/ww2/other)                     │
│       event_type (battle, capture, internment, ecc.)    │
│       parent_event_id (gerarchia)                        │
│       canonical_place_id, geometry                       │
│       languages, historical_place_names                  │
│       description_claim_id, status                       │
│     event_aliases table (90 righe, varianti nome)       │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. API — event_canonical_api.py                         │
│     GET /api/canonical-events        (lista paginata)    │
│     GET /api/canonical-events/{id}   (dettaglio)         │
│     GET /api/canonical-events/{id}/children (sotto-eventi)│
│     PATCH /api/canonical-events/{id} (update status)     │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  3. CONFLICT RECLASSIFICATION                            │
│     7 eventi WWII riclassificati con conflict_code=ww2  │
│     Parent hierarchy:                                    │
│       Operazione Achse → Mauthausen e Gusen             │
│       Operazione Achse → Lavoro forzato nel Reich        │
│       Battaglie dell'Isonzo → Battaglia del Carso       │
│       Battaglie dell'Isonzo → Monte San Michele          │
└──────────────────────────────────────────────────────────┘
```

---

## 17. Pipeline Map Features

### 17.1 Architettura

```
Feature geografica (luogo, coordinate, evento)
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  1. SCHEMA — map_schema.py                               │
│     map_features table:                                  │
│       id, feature_type (point/line/polygon)             │
│       label, description                                │
│       geometry (GeoJSON TEXT)                           │
│       source_table, source_id (provenance)              │
│       event_id (FK eventi_1gm)                          │
│       status: candidate | reviewed | published          │
│       created_at, reviewed_at, reviewed_by              │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  2. API — map_features_api.py                            │
│     GET  /api/map-features           (lista + filtri)    │
│     POST /api/map-features           (create candidate)  │
│     POST /api/map-features/{id}/review (review)          │
└──────────────────────────────────────────────────────────┘
```

### 17.2 Frontend Map

- Integrazione Leaflet in EventsPage e GraphEntityPage
- Layer per tipo (punti battle, poligoni area, linee fronte)
- Popup con dettaglio + link a evento
- Filtri per status e conflict_code

---

## 18. Mappa Endpoint API v2 (14 nuovi)

### Linking v2
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/v2/status/manifest` | GET | Conteggi DB + kill switch status |
| `/api/v2/events` | GET | Eventi canonici v2 |
| `/api/v2/relations` | GET | Relazioni con features + score |
| `/api/v2/kill-switch` | POST | Toggle legacy jobs |

### RAG
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/rag/retrieve` | POST | Retrieval + reranking + context |
| `/api/rag/validate` | POST | Validazione output AI |

### AI Runtime
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/ai-runtime/health` | GET | Stato adapter |
| `/api/ai-runtime/config` | GET | Configurazione (no secrets) |
| `/api/ai-runtime/benchmark` | POST | Benchmark generazione |
| `/api/ai-runtime/reset` | POST | Reset adapter singleton |

### Graph
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/graph/entity/{table}/{id}` | GET | Grafo entità |
| `/api/graph/edges/{edge_id}/review` | POST | Review arco |

### Map Features
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/map-features` | GET/POST | Lista / crea feature |
| `/api/map-features/{id}/review` | POST | Review feature |

### Event Canonical
| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/canonical-events` | GET | Lista eventi canonici |
| `/api/canonical-events/{id}` | GET | Dettaglio evento |
| `/api/canonical-events/{id}/children` | GET | Sotto-eventi |
| `/api/canonical-events/{id}` | PATCH | Update status |

---

## 19. Schema Migrations (tutte additive, reversibili)

| Migration | DB | Tabelle/Colonne | Stato |
|-----------|-----|-----------------|-------|
| `linking/schema_v2.py` | imi_internati.db | 16 tabelle nuove | Applicata |
| `graph_schema.py` | imi_internati.db | 6 tabelle graph | Applicata |
| `event_schema.py` | eventi_1gm.db | 12 colonne + event_aliases | Applicata |
| `map_schema.py` | eventi_1gm.db | map_features table | Applicata |
| `sql/001_supabase_historical_archive_core.sql` | Supabase | 5 schemi, 21 tabelle | Pendente (requires approval) |

---

## 20. Sicurezza

### 20.1 Secret Redaction — `linking/security.py`

```python
redact_secrets(text) → text con API keys, tokens, passwords mascherate
```

### 20.2 .env Tracking

Verifica che `.env` sia in `.gitignore` e non committato.

### 20.3 Packaging Allowlist

Solo file approvati inclusi in distribuzione. Script legacy esclusi.

### 20.4 Security Audit

`run_security_audit()` → report completo: secrets, .env, packaging, permissions.

---

## 21. Test Suite

### 21.1 Master Test — `test_linking_v2_master.py`

20 test coprono:
- Kill switch (frozen, enabled, force_execute)
- Normalization (name, date, place, date_overlap)
- Feature extraction (word boundary, ambiguous keywords, conflict flags)
- Scoring (weak/moderate/strong, veto, cap 0.95)
- Schema v2 (tabelle esistenti, indici, vincoli)
- Security (redaction, .env check, packaging)
- Persistence (idempotency, upsert, symmetric)
- Golden dataset (8 casi, seeding, listing)
- Candidate generation (blocking, dedup, no self-match)

### 21.2 Esecuzione

```bash
python test_linking_v2_master.py
# Expected: 20/20 PASS
```
