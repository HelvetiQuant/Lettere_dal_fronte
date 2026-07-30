# IMI Extractor — Architettura Aggiornata: Generazione Collegamenti Post-Query

> Versione: 2026-07-30
> Focus: pipeline di generazione collegamenti (linking) a seguito di una query utente
> Stato: linking v2 implementato, linking v1 legacy frozen (kill switch attivo)

---

## 1. Visione d'insieme

Quando un utente invia una query (chat AI, ricerca persona, o apertura evento), il sistema attiva una **catena di linking** che connette entità (persone, eventi, documenti, fonti) attraverso 4 layer:

1. **Layer locale** — DB SQLite (internati, caduti, decorati, fonti_indice, archivio_documenti)
2. **Layer federato** — 27 provider esterni (Arolsen, Bundesarchiv, TNA, NARA, ICRC, LeBI, ecc.)
3. **Layer web** — Ricerca web su archivi affidabili
4. **Layer AI** — Sintesi conversazionale con modello locale (LM Studio) o cloud (OpenAI/Anthropic/Mistral)

Il linking avviene in **due modalità**:

| Modalità | Trigger | Pipeline | Latenza |
|---|---|---|---|
| **Reattiva** (query-time) | Query utente via chat/ricerca | `research_protocol.py` → `person_finder.py` → `federation.py` | 30s–5min |
| **Batch** (offline) | Esecuzione `linking/cli.py generate` | `normalization.py` → `candidate_generation.py` → `feature_extraction.py` → `scoring.py` → `persistence.py` | Ore |

---

## 2. Pipeline Reattiva (Query-Time)

### 2.1 Entry point: Chat Research

```
Utente scrive: "cerca Francesco Siracusa nato a Messina classe 1886"
    │
    ▼
POST /api/chat/research (app.py:2523, timeout=300s)
    │
    ▼
chat_research.py → handle_research_question(question, conversation_id)
    │
    ├── 1. AI PARSING: _ai_parse_question(question)
    │   └── LM Studio / cloud AI estrae: nome, cognome, anno, luogo, unità
    │       Output: ParsedQuestion { full_name, birth_year, birth_place, ... }
    │
    ├── 2. RESEARCH PROTOCOL: research_protocol.research_person(input_data)
    │   │
    │   ├── 2a. VARIANT GENERATION
    │   │   └── generate_variants(si) → varianti nome (es. "Francesco" → "Franco")
    │   │   └── _ai_normalize_variants(si, variants) → AI filtra varianti plausibili
    │   │
    │   ├── 2b. PARALLEL SEARCH (ThreadPoolExecutor)
    │   │   ├── _search_local(si, variants, dossier)     ← DB SQLite
    │   │   ├── _search_supabase(si, dossier)             ← Supabase PostgreSQL
    │   │   ├── _search_federated(si, variants, dossier)  ← 27 provider esterni
    │   │   └── _search_web(si, dossier)                  ← Web search
    │   │
    │   │   Ogni fase è thread-safe (dossier lock)
    │   │   La prima che finisce "ruba" lavoro alle altre (work-stealing)
    │   │
    │   ├── 2c. AI DOSSIER SYNTHESIS
    │   │   └── _ai_build_dossier(dossier) → AI genera sintesi biografica
    │   │
    │   └── 2d. PERSISTENCE
    │       └── Salva dossier in DB + Supabase
    │
    ├── 3. AI ANSWER GENERATION: _ai_generate_answer(dossier, question)
    │   └── Costruisce summary compatto del dossier
    │   └── Chiama ai_client.call_ai() con fallback chain:
    │       OpenAI → Anthropic → Mistral → Perplexity → Gemini → LM Studio (Qwen/Gemma)
    │   └── Prompt: ANSWER_SYSTEM (conversazionale, non template)
    │   └── Output: risposta narrativa in linguaggio naturale
    │
    └── 4. RESPONSE: { answer, dossier, ai_used, ai_model, conversation_id }
```

### 2.2 Dettaglio: _search_local

```
_search_local(si, variants, dossier)
    │
    ├── Query internati (imi_internati.db)
    │   └── SELECT * FROM internati WHERE cognome MATCH varianti
    │   └── Filtro: luogo_nascita, data_nascita compatibili
    │
    ├── Query caduti_albooro (1.5M+ record)
    │   └── SELECT * FROM caduti_albooro WHERE nominativo LIKE varianti
    │
    ├── Query decorati (280K+ record)
    │   └── SELECT * FROM decorati_nastroazzurro WHERE cognome + nome MATCH
    │
    ├── Query fonti_indice (35K+ record)
    │   └── source_locator.find_sources_by_subject(nome_persona)
    │   └── source_locator.find_candidate_sources(nome_persona)
    │
    └── Output: List[PersonMatch] → aggiunti a dossier.candidati (thread-safe)
```

### 2.3 Dettaglio: _search_federated

```
_search_federated(si, variants, dossier)
    │
    ├── person_finder._search_federated(pq)
    │   │
    │   ├── build_federated_search_context(subject_type="person", canonical_name=pq.full_name)
    │   │
    │   ├── federated_search(query, cues, context)
    │   │   │
    │   │   ├── 27 provider registrati in federation.py
    │   │   ├── Concurrency: 6 worker paralleli (ThreadPoolExecutor)
    │   │   ├── Timeout per provider: 8s
    │   │   ├── Work-stealing: chunk dinamico, prima che finisce prende altro
    │   │   ├── Score: score_source(result, cues) basato su match persona/luogo/data
    │   │   └── Output: List[SearchResult] con provider, url, snippet, score
    │   │
    │   ├── Per-name search ICRC + LeBI
    │   │   └── ICRC: ricerca per nome su Grand Mémoire (CICR)
    │   │   └── LeBI: ricerca per cognome su lessicobiograficoimi.it
    │   │
    │   └── Output: List[PersonMatch] con source="federated", source_detail=provider
    │
    └── Aggiunti a dossier.candidati (thread-safe lock)
```

### 2.4 Dettaglio: _search_web

```
_search_web(si, dossier)
    │
    ├── person_finder._search_web(si)
    │   ├── Provider web: USSME, GoogleBooks, Gallica, Europeana, InternetArchive, HathiTrust
    │   ├── federated_search con web_providers subset
    │   ├── IA Evaluation: evaluate_candidates_from_context() per Internet Archive
    │   │   └── Filtra risultati non pertinenti (war mismatch, search page, score basso)
    │   └── Output: List[PersonMatch] con source="web"
    │
    └── Aggiunti a dossier.candidati (thread-safe lock)
```

### 2.5 Dettaglio: AI Answer Generation

```
_ai_generate_answer(dossier, question)
    │
    ├── Costruisce summary compatto del dossier:
    │   ├── Candidati top (max 3): nome, grado, data_nascita, luogo, sorte
    │   ├── Fonti trovate (max 5): archivio, titolo, url
    │   └── Statistiche: N candidati, N fonti, N provider interrogati
    │
    ├── Prompt system (ANSWER_SYSTEM):
    │   "Sei un ricercatore storico specializzato in eventi bellici italiani del '900.
    │    Rispondi in modo conversazionale, come se parlassi con un ricercatore.
    │    Non usare elenchi numerati rigidi. Cita le fonti inline.
    │    Se non trovi dati, dillo chiaramente."
    │
    ├── ai_client.call_ai(system, user, max_tokens=2048, temperature=0.7)
    │   └── Fallback chain automatica:
    │       1. OpenAI GPT-4o (se API key + quota)
    │       2. Anthropic Claude Sonnet (se API key + quota)
    │       3. Mistral Large (se API key + quota)
    │       4. Perplexity Sonar (se API key + quota)
    │       5. Gemini 2.0 Flash (se API key + quota)
    │       6. LM Studio locale (Qwen 2.5 / Gemma — sempre disponibile)
    │
    └── Output: testo narrativo conversazionale
```

---

## 3. Pipeline Batch (Offline Linking v2)

### 3.1 Architettura modulare

La pipeline v2 sostituisce i 6 script legacy (frozen via kill switch). È provenance-aware, idempotente, e con conflict detection.

```
Record sorgente (es. internati #12345, fonti_indice #61342)
    │
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  1. NORMALIZATION — linking/normalization.py                         │
│                                                                      │
│  normalize_name(cognome, nome):                                      │
│    ├── NFKD unicode decomposition                                    │
│    ├── Accent stripping (à→a, è→e, ü→u)                             │
│    ├── Lowercase + whitespace collapse                               │
│    ├── Output: NormalizedName { cognome_normalized, nome_normalized }│
│                                                                      │
│  normalize_date(date_str):                                           │
│    ├── ISO format: "1915-05-24"                                     │
│    ├── Italian: "24 maggio 1915"                                    │
│    ├── Year only: "1915"                                            │
│    ├── Range: "1915-1918"                                           │
│    ├── Output: NormalizedDate { start, end, precision }              │
│                                                                      │
│  normalize_place(place_str):                                         │
│    ├── NFKD + accent stripping                                      │
│    ├── Historical aliases mapping (es. "Fiume" → "Rijeka")          │
│    ├── Output: NormalizedPlace { normalized, original }              │
│                                                                      │
│  date_overlap(s1, e1, s2, e2):                                       │
│    └── True se intervalli si sovrappongono (anche parzialmente)      │
│                                                                      │
│  VERSION = "2.0.0" (versionata per reproducibilità)                  │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. CANDIDATE GENERATION — linking/candidate_generation.py           │
│                                                                      │
│  Blocking indexes (O(N+M), non O(N*M)):                              │
│    ├── phonetic_cognome: 3 consonanti prefisso (es. "SRCS" → Siracusa)│
│    ├── name_initial: cognome[:4] + nome[:1] (es. "SIRAF" → Siracusa F)│
│    ├── birth_year: anno nascita bucket                               │
│    ├── place_prefix: luogo normalizzato[:6]                          │
│    └── matricola: exact match                                        │
│                                                                      │
│  Per ogni coppia (source, target) nello stesso block:                │
│    ├── Dedup per (source_ns, source_key, target_ns, target_key,      │
│    │             block_type)                                         │
│    ├── No self-match (source_key ≠ target_key)                       │
│    └── Output: list[CandidatePair]                                   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. FEATURE EXTRACTION — linking/feature_extraction.py               │
│                                                                      │
│  Tre tipi di estrazione:                                             │
│                                                                      │
│  ┌─ person ↔ source ─────────────────────────────────────┐          │
│  │  extract_features_person_source(source, target):       │          │
│  │    ├── name_cognome_exact (exact match)                │          │
│  │    ├── name_cognome_phonetic (3-consonant prefix)      │          │
│  │    ├── name_nome_exact                                  │          │
│  │    ├── birth_date_compatible (date_overlap)             │          │
│  │    ├── birth_place_compatible (_place_match con \b)    │          │
│  │    ├── same_matricola                                   │          │
│  │    ├── same_unit                                        │          │
│  │    └── discriminators[]: lista feature indipendenti    │          │
│  └────────────────────────────────────────────────────────┘          │
│                                                                      │
│  ┌─ person ↔ event ──────────────────────────────────────┐          │
│  │  extract_features_person_event(person, event):          │          │
│  │    ├── temporal_overlap (date_overlap persona↔evento)   │          │
│  │    ├── geographic_compatible (_place_match)             │          │
│  │    ├── unit_in_theater (keyword match con \b)           │          │
│  │    ├── ConflictFlags:                                   │          │
│  │    │   ├── ww1_ww2_mismatch (VETO)                      │          │
│  │    │   ├── born_after_event (VETO)                      │          │
│  │    │   ├── died_before_event (VETO)                     │          │
│  │    │   ├── omonimia_no_discriminator (VETO)             │          │
│  │    │   ├── matricola_mismatch (VETO)                    │          │
│  │    │   ├── geo_incompatible                             │          │
│  │    │   ├── unit_not_active                              │          │
│  │    │   └── event_too_broad                              │          │
│  │    └── AMBIGUOUS_KEYWORDS: {campo, russia, africa,     │          │
│  │        prigionia, lager, cattura, fronte, guerra, ...}  │          │
│  │        → non generano strong match da sole              │          │
│  └────────────────────────────────────────────────────────┘          │
│                                                                      │
│  ┌─ document ↔ event ────────────────────────────────────┐          │
│  │  extract_features_document_event(doc, event):           │          │
│  │    ├── _word_boundary_match(keyword, text) con \b       │          │
│  │    ├── Salta AMBIGUOUS_KEYWORDS                         │          │
│  │    ├── keyword_in_title bonus                           │          │
│  │    ├── temporal_overlap (doc year vs event range)       │          │
│  │    └── ConflictFlags: ww1_ww2_mismatch, etc.            │          │
│  └────────────────────────────────────────────────────────┘          │
│                                                                      │
│  Output: (Features, ConflictFlags)                                   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. SCORING — linking/scoring.py                                    │
│                                                                      │
│  score_candidate(features, conflicts):                               │
│                                                                      │
│  Base score:                                                         │
│    ├── name_cognome_exact:     +0.15                                 │
│    ├── name_cognome_phonetic:  +0.08                                 │
│    ├── name_nome_exact:        +0.05                                 │
│    │                                                                  │
│    ├── 0 discriminatori  → weak,     score 0.0–0.2                  │
│    ├── 1 discriminatore   → moderate, +0.2                          │
│    ├── 2 discriminatori   → moderate, +0.35                         │
│    ├── 3+ discriminatori  → strong,   +0.45                         │
│    │                                                                  │
│    ├── same_matricola:          +0.2 (fortissimo)                   │
│    ├── birth_date + birth_place: +0.1                               │
│    ├── document_citation:       +0.1                                │
│    │                                                                  │
│    └── CAP 0.95 (mai 1.0 — incertezza sempre presente)              │
│                                                                      │
│  Veto conflicts:                                                     │
│    ├── has_veto → score max 0.15, evidence_strength=weak            │
│    └── can_be_confirmed = False                                      │
│                                                                      │
│  can_be_confirmed (criteri):                                         │
│    ├── NOT has_veto                                                  │
│    ├── n_discriminators >= 2                                         │
│    ├── evidence_strength in (moderate, strong)                       │
│    └── features.name_match = True                                    │
│                                                                      │
│  confidence_calibrated = NULL (no golden dataset calibration yet)    │
│                                                                      │
│  Output: ScoreResult(raw_score, evidence_strength, conflict_flags,   │
│                      can_be_confirmed)                               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  5. PERSISTENCE — linking/persistence.py                             │
│                                                                      │
│  create_pipeline_run():                                               │
│    ├── UUID run_id                                                   │
│    ├── code_commit_sha (git revision)                                │
│    ├── configuration_hash (SHA256 del config JSON)                   │
│    └── status: running → completed/failed                            │
│                                                                      │
│  register_resource():                                                 │
│    ├── Idempotente su (namespace, key)                               │
│    └── UUID resource_id                                              │
│                                                                      │
│  upsert_relation():                                                   │
│    ├── Chiave semantica: (source_id, target_id, type,                │
│    │   algorithm_name, algorithm_version)                            │
│    ├── Symmetric: normalizza orientazione A-B vs B-A                 │
│    ├── Se esiste → UPDATE features/score/pipeline_run                │
│    ├── Se nuovo → INSERT con tutti i campi provenance                │
│    └── Output: relation_id (UUID)                                    │
│                                                                      │
│  finish_pipeline_run(): counts + status + error                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 CLI

```bash
# Dry-run (no write)
python -m linking.cli generate --dry-run

# Execute (write to DB)
python -m linking.cli generate --execute

# Legacy relations audit
python -m linking.cli legacy-relations audit

# Legacy relations quarantine
python -m linking.cli legacy-relations quarantine --execute

# Kill switch status
python -m linking.cli kill-switch
```

---

## 4. Pipeline Event Linking (Legacy — Frozen)

### 4.1 _gen_event_links.py (FROZEN via kill switch)

Lo script legacy `_gen_event_links.py` genera collegamenti tra `fonti_indice` e `eventi_1gm` tramite **keyword matching puro**:

```
Per ogni fonti_indice:
    text = titolo + luogo + soggetti_collegati (UPPERCASE)
    Per ogni evento in eventi_1gm:
        keywords = json.loads(evento.keywords)
        aliases = json.loads(evento.aliases)
        Per ogni keyword:
            if keyword.upper() IN text:  ← SUBSTRING MATCH, no \b
                INSERT event_links (confidence=0.7)
                break
```

### 4.2 Problema noto: WW1/WW2 cross-contamination

**Caso reale**: Evento "Internamento militari italiani in Austria-Ungheria (WWI)" (1915-1918)

- **Keywords evento**: `['internamento', 'prigionia', 'campo', 'Austria', 'Ungheria', 'Germania', 'prigioniero', 'WWI', 'Rastatt', 'Mauthausen', 'Sigmundsherberg']`
- **Problema 1**: `Mauthausen` è un campo WWII (non WWI) ma è nelle keywords
- **Problema 2**: `campo` è keyword ambigua → matcha 365 fonti Bundesarchiv (campi WWII)
- **Problema 3**: Nessun filtro temporale — fonti con date 1943-45 collegate a evento 1915-18
- **Risultato**: 402 fonti collegate, ~30 chiaramente WWII, solo 7 WWI, 365 ambigue

### 4.3 Fix v2 vs legacy

| # | Errore legacy | Fix v2 | File |
|---|---|---|---|
| 1 | `in` substring matching | `\b` word boundary regex | `feature_extraction.py:341-349` |
| 2 | Keyword ambigue senza discriminatore | `AMBIGUOUS_KEYWORDS` set + skip | `feature_extraction.py:78-82` |
| 3 | WW1/WW2 misti senza conflict detection | `ww1_ww2_mismatch` veto | `feature_extraction.py:173-176` |
| 4 | Confidence 0.9 arbitraria | `evidence_strength` + `confidence_calibrated=NULL` | `scoring.py:105` |
| 5 | Skip-or-insert (no idempotency) | `upsert_relation()` con chiave semantica | `persistence.py:118-196` |
| 6 | No provenance | `algorithm_version` + `pipeline_run_id` + `features` JSON | `persistence.py:180-193` |
| 7 | `_place_match()` substring | `_word_boundary_match()` per luoghi | `feature_extraction.py:325-338` |
| 8 | No temporal filter | `date_overlap()` + `born_after_event` / `died_before_event` veto | `feature_extraction.py:178-196` |

### 4.4 Kill switch

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
# assert_frozen() → RuntimeError se disabled
```

---

## 5. Pipeline Event Evidence (Query-Time per Eventi)

Quando l'utente apre la pagina di un evento (`/eventi/{nome}`), il sistema raccoglie fonti da 4 livelli:

```
GET /api/events/1gm/{event_name} → events.get_evento_1gm_dossier(nome)
    │
    ├── 1. EVENT LINKS (eventi_1gm.db)
    │   └── SELECT target_id FROM event_links WHERE evento_id=? AND link_type=?
    │   └── Tipi: fonte_archivistica, documento, soldato_caduto, soldato_decorato
    │
    ├── 2. FONTI INDICE (imi_internati.db)
    │   └── source_locator.find_sources_by_subject(event_name)
    │   └── SELECT * FROM fonti_indice WHERE soggetti_collegati = event_name
    │
    ├── 3. ARCHIVIO DOCUMENTI
    │   └── SELECT * FROM archivio_documenti WHERE rowid IN (linked doc_ids)
    │
    └── 4. STATS AGGREGATE
        └── COUNT caduti, decorati, documenti, fonti, internati per evento

GET /api/events/{event_name}/sources → events.get_evento_fonti(nome)
    │
    └── source_locator.find_sources_by_subject(nome)
        └── Raggruppa per fazione (italiana, Asse, Alleati)
```

### 5.1 Event Evidence Pipeline (event_evidence_pipeline.py)

Pipeline più ricca per generare dossier di fonti con 4 livelli:

```
event_evidence_pipeline.collect_evidence(event_name)
    │
    ├── Livello 1: _internal_sources(event_id, event_name, event_data)
    │   ├── event_links → fonti_indice (link_type='fonte_archivistica')
    │   ├── event_links → archivio_documenti (link_type='documento')
    │   ├── Filtro: _geographic_overlap(event_luogo, fonte_luogo)
    │   └── Output: List[Source] con relevance_score, verification_status
    │
    ├── Livello 2: _archival_sources(event_name, event_data)
    │   ├── source_locator.find_sources_by_subject() (exact match)
    │   ├── source_locator.find_candidate_sources() (fuzzy match)
    │   ├── Filtro rilevanza: _relevance_tokens(event_name) vs fonti metadata
    │   │   └── Stop words: {della, delle, battaglia, campo, campi, fronte, monte, ...}
    │   └── Output: List[Source] con relevance_score, geographic_compatible
    │
    ├── Livello 3: _federated_sources(event_name, event_data)
    │   ├── Provider: nara, ussme, archivio_stato, europeana, internetarchive,
    │   │            googlebooks, gallica, hathitrust, memoiredeshommes, iwm_lives, tna, shd
    │   ├── federated_search(event_name, cues=event_data, providers=...)
    │   ├── Filtro: _temporal_overlap(event_start, event_end, fonte_date)
    │   ├── Filtro: _geographic_overlap(event_luogo, fonte_snippet)
    │   └── Output: List[Source] con temporal_compatible, geographic_compatible
    │
    └── Livello 4: _web_sources(event_name, event_data)
        ├── Provider: ussme, googlebooks, gallica, europeana, internetarchive, hathitrust,
        │            archivio_stato, memoiredeshommes, iwm_lives
        ├── federated_search con web_providers + build_federated_search_context
        ├── IA Evaluation: evaluate_candidates_from_context() per Internet Archive
        │   └── Filtra: war mismatch, search page, score basso
        ├── Filtro: _temporal_overlap + _geographic_overlap
        └── Output: List[Source] con verification_status (probabile/candidata)
```

### 5.2 Classificazione fonti

Ogni fonte riceve:

| Campo | Valori | Descrizione |
|---|---|---|
| `source_type` | primaria, istituzionale, web | Tipo di fonte |
| `authority` | archivio, banca_dati, pagina_web | Autorevolezza |
| `verification_status` | verificata, probabile, candidata | Stato di verifica |
| `relevance_score` | 0.0–0.95 | Pertinenza calcolata |
| `temporal_compatible` | bool | Compatibilità temporale con evento |
| `geographic_compatible` | bool | Compatibilità geografica con evento |

---

## 6. Pipeline Graph Provenance (Read-Through)

```
Frontend (GraphEntityPage.tsx) → GET /api/graph/entity/{table}/{id}
    │
    ▼
graph_service.py → get_entity_graph(table, id)
    │
    ├── Read-through adapter su 5 tabelle legacy:
    │   ├── event_links (891K righe, eventi_1gm.db)
    │   ├── record_links (169K righe, imi_internati.db)
    │   ├── external_links (record esterni ↔ internati)
    │   ├── claim_relations (claim ↔ entità)
    │   └── menzioni (10K righe)
    │
    ├── Per ogni arco:
    │   ├── Sistema originale preservato (event_links, record_links, ecc.)
    │   ├── ID originale preservato
    │   ├── Nessun candidato legacy → confirmed automatico
    │   └── Label umane (RELATION_LABELS)
    │
    └── Output: GraphResponse(nodes[], edges[], evidence[])
```

### 6.1 Edge Review

```
POST /api/graph/edges/{edge_id}/review
    ├── status: confirmed | rejected | needs_review
    ├── reviewer, notes, timestamp
    └── Scrive in graph_edge_reviews
```

---

## 7. Schema DB per Linking

### 7.1 Tabelle legacy (still in use, read-only via kill switch)

```
eventi_1gm.db:
├── eventi_1gm          (49 eventi canonici, 12 colonne v2 additive)
├── event_aliases       (161 alias di nomi evento)
├── event_links         (891K righe — collegamenti evento ↔ entità)
│   ├── link_type: fonte_archivistica | documento | soldato_caduto |
│   │             soldato_decorato | soldato_caduto_cwgc |
│   │             soldato_caduto_ministero | internato_ww2
│   ├── target_table: fonti_indice | archivio_documenti | caduti_albooro |
│   │                decorati | caduti_cwgc | caduti_ministero | internati
│   ├── match_field: titolo_luogo_soggetti | nome_cognome | cimitero | ...
│   ├── match_value: keyword che ha generato il match
│   └── confidence: 0.5–0.9 (legacy, non calibrata)
└── map_features        (feature geografiche con provenance)

imi_internati.db:
├── record_links        (169K righe — link record-to-record)
│   ├── from_table / from_id → to_table / to_id
│   ├── link_type: fonte_personale | documento | evento | lebi_match
│   └── confidence: 0.3–0.9
├── fonti_indice        (35K+ fonti archivistiche indicizzate)
├── archivio_documenti  (979 documenti digitalizzati)
└── entita + collegamenti (grafo entità estratte)
```

### 7.2 Tabelle v2 (linking v2 — 16 nuove)

```
imi_internati.db:
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
├── graph_nodes                (id, table, record_id, label, kind)
├── graph_edges                (id, source_node, target_node,
│                               relation_type, source_system, source_id,
│                               confidence, status)
├── graph_edge_reviews         (edge_id, reviewer, status, notes, timestamp)
├── graph_pipeline_runs        (run_id, algorithm, started_at, status)
├── graph_integrity_issues     (edge_id, issue_type, description)
└── archival_metadata          (resource_id, provenance_json)
```

---

## 8. Flusso Completo: Dal Query al Dossier

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                     │
│                                                                      │
│  ResearchChatPanel.tsx          EventsPage.tsx                       │
│  ├── POST /api/chat/research    ├── GET /api/events/1gm              │
│  ├── timeout: 300s              ├── GET /api/events/1gm/{name}       │
│  ├── AbortController            ├── AbortController (unmount-safe)   │
│  └── ErrorBoundary              └── ErrorBoundary                    │
│                                                                      │
│  Vite proxy → http://127.0.0.1:8001 (timeout 300s)                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                            │
│                                                                      │
│  app.py (3000+ righe, 310+ endpoint)                                │
│  ├── /api/chat/research → chat_research.handle_research_question()  │
│  ├── /api/events/1gm/{name} → events.get_evento_1gm_dossier()       │
│  ├── /api/events/{name}/sources → events.get_evento_fonti()         │
│  └── /api/graph/entity/{table}/{id} → graph_service.get_entity_graph│
└──────────────────────────────┬──────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  CHAT RESEARCH   │ │  EVENT DOSSIER   │ │  GRAPH ENTITY    │
│                  │ │                  │ │                  │
│  research_       │ │  events.py       │ │  graph_service   │
│  protocol.py     │ │  source_locator  │ │  .py             │
│  person_finder   │ │  event_evidence  │ │  5 tabelle       │
│  .py             │ │  _pipeline.py    │ │  legacy read-    │
│  federation.py   │ │                  │ │  through         │
│  (27 provider)   │ │                  │ │                  │
│  ai_client.py    │ │                  │ │                  │
│  (fallback chain)│ │                  │ │                  │
└────────┬─────────┘ └────────┬─────────┘ └──────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                   │
│                                                                      │
│  imi_internati.db (SQLite)          eventi_1gm.db (SQLite)          │
│  ├── internati (20K)               ├── eventi_1gm (49)              │
│  ├── caduti_albooro (342K)         ├── event_aliases (161)          │
│  ├── decorati (280K)               ├── event_links (891K)           │
│  ├── fonti_indice (35K+)           └── map_features                 │
│  ├── archivio_documenti (979)                                        │
│  ├── record_links (169K)                                            │
│  ├── entita + collegamenti                                          │
│  └── linking v2 tables (16)                                         │
│                                                                      │
│  Supabase PostgreSQL (wyqesimzxieykmyhfvqs)                         │
│  ├── archive.archivio_documenti (979 synced)                        │
│  ├── archive.eventi_1gm (49 synced)                                 │
│  ├── archive.event_aliases (161 synced)                             │
│  └── archive.event_links (1.5M, ~18% synced — in progress)          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 9. AI Runtime — Adapter Architecture

```
Codice applicativo (chat_research, biography, event_research, RAG)
    │
    ▼
ai_runtime.get_adapter() → InferenceAdapter (singleton)
    │
    ├── Selezione (priorità):
    │   1. LM_STUDIO_API_URL env → LMStudioAdapter
    │      (OpenAI-compatible, CPU quantized, locale — Qwen/Gemma)
    │   2. AI_LOCAL_ONLY=true → DeterministicTestAdapter
    │      (no real AI, per test)
    │   3. Default → RemoteAIAdapter
    │      (delega ad ai_client.py con fallback chain)
    │
    ├── LMStudioAdapter
    │   ├── POST /v1/chat/completions (OpenAI-compatible)
    │   ├── POST /v1/embeddings
    │   ├── GET /v1/models (health check)
    │   ├── Modello attivo: google/gemma-4-e4b (LM Studio)
    │   └── Timeout: 120s per generazione
    │
    ├── RemoteAIAdapter
    │   ├── ai_client.call_ai() con fallback:
    │   │   1. OpenAI GPT-4o (se OPENAI_API_KEY + quota)
    │   │   2. Anthropic Claude Sonnet 4.5 (se ANTHROPIC_API_KEY + quota)
    │   │   3. Mistral Large (se MISTRAL_API_KEY + quota)
    │   │   4. Perplexity Sonar (se PERPLEXITY_API_KEY + quota)
    │   │   5. Gemini 2.0 Flash (se GOOGLE_API_KEY + quota)
    │   │   6. LM Studio locale (sempre disponibile come ultimo fallback)
    │   └── Ogni provider loggato in api_usage con costo
    │
    └── DeterministicTestAdapter
        ├── Echo / static response (per test)
        └── embed(): [0.0]*384
```

---

## 10. Problemi Noti e Azioni Correttive

### 10.1 WW1/WW2 Cross-Contamination (CRITICO)

**Sintomo**: Evento WWI "Internamento militari italiani in Austria-Ungheria (1915-1918)" mostra fonti WWII (Mauthausen, Tobruk 1941, ANPI 8 settembre 1943, Bundesarchiv IMI 1943-45).

**Root cause**: `_gen_event_links.py` (legacy, frozen) usa keyword matching puro senza:
- Filtro temporale (fonte date vs evento date range)
- Filtro conflitto (WWI vs WWII)
- Word boundary matching (`in` invece di `\b`)
- Keyword ambiguity filtering (`campo` matcha tutto)

**Fix necessario**:
1. Pulire keywords evento ID 56: rimuovere `Mauthausen` (WWII)
2. Eseguire `linking/cli.py generate --execute` per generare relazioni v2 con conflict detection
3. Quarantine legacy event_links: `linking/cli.py legacy-relations quarantine --execute`
4. Frontend: usare API v2 `/api/v2/relations` invece di legacy event_links

### 10.2 Supabase Sync Incompleto

**Stato**: `event_links` sync al ~18% (1.5M righe totali, ~280K sincronizzate)
**Impatto**: Query Supabase non restituiscono tutti i collegamenti
**Fix**: Completare sync in background

### 10.3 Frontend Timeout/Abort

**Sintomo**: `signal is aborted without reason` + React `insertBefore` crash
**Root cause**: Navigazione tra pagine abortisce fetch in corso; React reconciliation con key non stabili
**Fix applicato**:
- `http.ts`: `timedOut` flag distingue timeout da unmount abort
- `EventsPage.tsx`: `AbortController` con cleanup
- `ResearchChatPanel.tsx`: key stabili (`m.id`) + `ChatErrorBoundary`

---

## 11. Mappa Endpoint API (Linking-Related)

| Endpoint | Metodo | Descrizione | Pipeline |
|---|---|---|---|
| `/api/chat/research` | POST | Ricerca persona AI (chat) | Reattiva |
| `/api/chat/health` | GET | Stato AI provider | — |
| `/api/events/1gm` | GET | Lista eventi canonici | — |
| `/api/events/1gm/{name}` | GET | Dossier evento (fonti, caduti, doc) | Event linking |
| `/api/events/{name}/sources` | GET | Fonti multilaterali per evento | source_locator |
| `/api/events/{name}/internati` | GET | Internati collegati a evento | event_links |
| `/api/graph/entity/{table}/{id}` | GET | Grafo entità | Graph read-through |
| `/api/graph/edges/{id}/review` | POST | Review arco grafo | Graph |
| `/api/v2/status/manifest` | GET | Conteggi DB + kill switch | Linking v2 |
| `/api/v2/events` | GET | Eventi canonici v2 | Linking v2 |
| `/api/v2/relations` | GET | Relazioni con features + score | Linking v2 |
| `/api/v2/kill-switch` | POST | Toggle legacy jobs | Kill switch |
| `/api/rag/retrieve` | POST | Retrieval + reranking + context | RAG |
| `/api/ai-runtime/health` | GET | Stato adapter AI | AI Runtime |

---

## 12. Stack Tecnologico Aggiornato

| Componente | Tecnologia | Versione/Stato |
|---|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn | 3000+ righe, 310+ endpoint |
| DB locale | SQLite (dual: imi_internati.db + eventi_1gm.db) | 75 tabelle, 9.5M righe |
| DB cloud | Supabase PostgreSQL | wyqesimzxieykmyhfvqs, 21 tabelle canoniche |
| Frontend | React 18 + Vite + TypeScript | SPA moderna, 7 pagine |
| AI locale | LM Studio (OpenAI-compatible) | google/gemma-4-e4b |
| AI cloud | OpenAI/Anthropic/Mistral/Perplexity/Gemini | Fallback chain (quota esaurita) |
| Federated search | 27 provider, 6 worker paralleli | Work-stealing, 8s timeout |
| Linking v2 | 5 moduli (norm/cand/feat/score/persist) | 20/20 test pass |
| Kill switch | 6 legacy jobs frozen | assert_frozen() attivo |
| Graph | 6 tabelle graph provenance | Read-through adapter |
| RAG | FTS5 + metadata + reranking | Hybrid retrieval |
| Timeout | Backend 300s, Frontend 300s, Proxy 300s | 5 min max |
