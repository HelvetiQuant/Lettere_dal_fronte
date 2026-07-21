# VOCI DAL FRONTE — IMI Extractor

Sistema di ricerca storica su Internati Militari Italiani (IMI) e caduti delle guerre mondiali, con intelligenza artificiale, federazione di archivi internazionali e indicizzazione semantica.

## Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (index.html)                     │
│  Search bar → Results → Investigative Tabs                       │
│  [AI Response] [Cross-DB] [Sources] [Events] [Gaps]              │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP API
┌──────────────▼──────────────────────────────────────────────────┐
│                        app.py (FastAPI)                          │
│  85 endpoint: search, biography, research, sources, gaps        │
└──────┬──────────────┬──────────────┬────────────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼──────────────────────┐
│ database.py │ │ biography  │ │ source_providers/         │
│ SQLite star │ │ GPT/Claude │ │ 16 provider reali         │
│ schema      │ │ Mistral    │ │ Arolsen, Bundesarchiv,    │
│             │ │ Perplexity │ │ TNA, Europeana, Gallica,  │
│ 688k entità │ │            │ │ DDB, SHD, LAC, ABMC,      │
│ 4.8M link   │ │            │ │ Internet Archive, ecc.    │
└─────────────┘ └────────────┘ └───────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                    research_to_index.py                          │
│  Subject creation → Source linking → Gap identification          │
│  Confidence scoring → Auto-index pipeline                        │
└─────────────────────────────────────────────────────────────────┘
```

## Flusso Research-to-Index

```
Query utente (es. "Gaiaschi Giuseppe")
    │
    ▼
┌───────────────────┐
│ search_all()      │  Ricerca locale su 12 tabelle
│ database.py       │  (internati, caduti, decorati, fonti_narrative, ...)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Federation Layer  │  16 provider interrogati in parallelo
│ source_providers/ │  (TNA, Europeana, Arolsen, Bundesarchiv, ...)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ AI Biography      │  GPT-4o → Claude → Mistral → Perplexity (fallback)
│ biography.py      │  Genera biografia narrativa con fonti verificate
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Research-to-Index │  Crea/aggiorna research_subjects
│ research_to_index │  Collega fonti, calcola confidence
│                   │  Identifica gaps (campi mancanti)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ UI Tabs           │  AI Response | Cross-DB | Sources | Events | Gaps
│ index.html        │  Ogni tab mostra dati specifici
└───────────────────┘
```

## Moduli principali

| File | Descrizione |
|------|-------------|
| `app.py` | Server FastAPI, 85 endpoint REST |
| `database.py` | Accesso DB SQLite, search_all(), star schema |
| `biography.py` | Generazione biografie AI multi-provider con fallback |
| `research_to_index.py` | Indicizzazione semantica, gap identification, confidence scoring |
| `extractor.py` | Estrazione PDF/OCR, caricamento env, client AI |
| `import_fonti_personali.py` | Import unificato lettere + fonti narrative → DB |
| `source_providers/base.py` | Classe base SourceProvider, cache, scoring |
| `source_providers/providers.py` | 16 provider: Arolsen, Bundesarchiv, TNA, Europeana, Gallica, DDB, SHD, LAC, ABMC, AWM, Internet Archive, Google Books, HathiTrust, Internet Culturale, USSME, Archivi di Stato |
| `templates/index.html` | UI completa con tabs investigativi |

## Database

**File**: `imi_internati.db` (~1.4 GB)

**Star schema**:
- `entita` — 688.738 nodi (persone, luoghi, eventi, unità)
- `collegamenti` — 4.832.063 archi (menzionato, correlato, ecc.)
- `internati` — IMI WW2 dall'Archivio di Stato di Bolzano
- `caduti_ministero` — Caduti WW1 del Ministero
- `caduti_albooro` — Albo d'Oro
- `caduti_cwgc` — 506.446 record Commonwealth War Graves Commission
- `caduti_sardi`, `caduti_bologna` — Database locali
- `decorati_nastroazzurro` — Decorati
- `fonti_narrative` — 40 fonti personali (biografie, memoriali, foto, ARO)
- `lettere_personali` — Lettere OCR dal database secondario
- `research_subjects` — Soggetti di ricerca indicizzati
- `research_gaps` — Gap identificati (campi mancanti)
- `fondi_archivistici` — Catalogo fondi archivistici
- `fonti_indice` — Fonti indicizzate remote
- `source_fetch_cache` — Cache download documenti

## Provider Federation

| Provider | Paese | API | Autenticazione |
|----------|-------|-----|----------------|
| Arolsen Archives (ITS) | DE | ITS-WS.asmx (reverse-engineered) | Sessione ASP.NET |
| Bundesarchiv | DE | Invenio REST API | Pubblica (lettura) |
| Archivportal-D (DDB) | DE | DDB REST API (OpenAPI 3.0) | API key (OAuth) |
| TNA (National Archives UK) | UK | Discovery API | Pubblica |
| Europeana | EU | Record API v2 | API key (api2demo) |
| Gallica/BnF | FR | SRU 1.2 | Pubblica |
| SHD/Mémoire des Hommes | FR | HTML parsing | Pubblica |
| Internet Archive | US | Advanced Search API | Pubblica |
| Google Books | US | Books API v1 | Pubblica |
| HathiTrust | US | Catalog API v1 | Pubblica |
| ABMC | US | Database API | Pubblica |
| AWM (Australian War Memorial) | AU | Collection API | Pubblica |
| LAC (Library and Archives Canada) | CA | Canadiana API + Collection Search | Pubblica |
| Internet Culturale (OPAC SBN) | IT | OPAC SBN JSON | Pubblica |
| USSME | IT | DB locale (fondi_archivistici) | Locale |
| Archivi di Stato | IT | DB locale (menzioni) | Locale |

## Avvio

```bash
cd C:\Users\eryma\CascadeProjects\imi_extractor
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8123
```

Apri il browser su `http://localhost:8123`.

## Configurazione

File `.env` (cercato in `~/Desktop/lettere dal fronte backup_2026-06-28/.env` o `cwd/.env`):

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
PERPLEXITY_API_KEY=pplx-...
EUROPEANA_API_KEY=...
GEMINI_API_KEY=...
DDB_API_KEY=...  (opzionale, per Archivportal-D)
```

## API principali

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/search` | GET | Ricerca multi-tabella con tokenizzazione AND |
| `/api/biography` | POST | Biografia AI (soldato o evento) |
| `/api/research/subjects` | GET | Lista soggetti di ricerca |
| `/api/research/gaps` | GET | Gap identificati (campi mancanti) |
| `/api/research/auto-index` | POST | Auto-indicizzazione batch |
| `/api/sources/search` | GET | Ricerca federata su 16 provider |
| `/api/cwgc/search` | GET | Ricerca CWGC |

## AI nel frontend

- **Pulsanti AI sui risultati di ricerca**: ogni card persona nella home ha i bottoni `Dossier AI` (biografia verificata) e `Immagini AI` (ricostruzione visiva), che aprono il dossier e avviano la generazione.
- **Report AI con progress bar**: nella scheda evento, i bottoni `Genera Report Convergenze Fonti AI` e `Genera Report Cronologico AI` mostrano una barra di avanzamento percentuale durante la generazione.
- **Fallback multi-provider**: le chiamate AI usano la catena OpenAI → Anthropic → Mistral → Perplexity per garantire risposta anche in caso di indisponibilità o esaurimento crediti.

## Testing

```bash
python -m pytest tests/ -v
```
