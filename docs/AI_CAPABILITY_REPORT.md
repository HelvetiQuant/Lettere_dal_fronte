# Report: Capacità della nuova AI storica — Dataset, Fonti e Copertura Tematica

**Data:** 25 luglio 2026  
**Branch:** `devin/ai-storica-eventi-mappe`  
**Modello:** Qwen2.5-3B-Instruct (LM Studio, `127.0.0.1:1234`)  
**Runtime:** `ai_runtime.py` → `LMStudioAdapter` (locale, nessuna chiamata remota)

---

## 1. Architettura della AI

### Runtime locale
L'AI gira interamente in locale tramite **LM Studio** con il modello **Qwen2.5-3B-Instruct**. Nessun dato viene inviato a server esterni quando `local_only=true`.

**Componenti:**
- `ai_runtime.py` — interfaccia `InferenceAdapter` con adapter `LMStudioAdapter`, `RemoteAIAdapter`, `DeterministicTestAdapter`
- `chat_api.py` — endpoint `POST /api/chat` con history conversazionale e contesto opzionale
- `ai_runtime_api.py` — health, config, benchmark, reset
- `rag_pipeline.py` — retrieval ibrido FTS5 + reranking + context builder + validazione output
- `event_narrative_builder.py` — generazione dossier narrativi con citazioni fonti

### System prompt predefinito
```
Sei un ricercatore storico specializzato negli eventi bellici del Novecento,
in particolare la Prima e Seconda Guerra Mondiale, con focus sul fronte italiano.
Rispondi in italiano con accuratezza storica.
Cita le fonti quando possibile. Se non sei sicuro, dichiara la tua incertezza.
Sii conciso ma preciso. Non inventare dati.
```

---

## 2. Dataset di training scaricati

### 2.1 Dataset italiani

| Dataset | ID HuggingFace | Righe | Lingua | Formato | Fonte |
|---|---|---|---|---|---|
| **Quandho** | `mik3ml/quandho` | 1.800 | IT | Q&A con contesto | HuggingFace |
| **Aya ITA** | `giux78/aya_dataset_ita` | 668 (40 filtrate) | IT | Q&A multi-tematico | HuggingFace |

#### Quandho — Q&A storia italiana XX secolo
- **Copertura:** Storia italiana della prima metà del Novecento
- **Formato:** `question` + `answer` + `context`
- **Argomenti attestati:**
  - Regno del Sud e cobelligerazione italiana
  - Processo di Verona (condanne a morte, Ciano, fascismo repubblicano)
  - Eccidio delle Fosse Ardeatine (Kesselring, Kappler)
  - Impresa del Gran Sasso (liberazione di Mussolini, Operazione Quercia)
  - Scissione CGIL in CISL e UIL (1948, attentato Togliatti)
  - Censura postale nella prima guerra mondiale
  - Organizzazione delle trincee sul fronte
  - Operazione Quercia (Fall Eiche, 12 settembre 1943)

#### Aya ITA — Q&A italiana (filtrato storico)
- **Copertura:** 40 esempi filtrati per keyword storiche da 668 totali
- **Keyword filtro:** guerra, fascismo, nazismo, resistenza, partigiano, militare, esercito, trincea, fronte, Caporetto, Piave, Carso, Isonzo, Grappa, D'Annunzio, Mussolini, Hitler, alleanza, pace, armistizio, occupazione, liberazione, soldato, medaglia, decorazione, caduto, prigionia, internato
- **Esempi:** Crisi di Suez, medaglie d'argento, Congresso e dichiarazioni di guerra

### 2.2 Dataset internazionali

| Dataset | ID HuggingFace | Righe | Lingua | Formato | Fonte |
|---|---|---|---|---|---|
| **Muninn WW1** | `biglam/muninn-ww1-documents` | 28.700 | EN | Documenti d'archivio | HuggingFace / Muninn Project |
| **CommandNet** | `Euroswarms/CommandNet` | 10.000 | EN | ShareGPT conversazionale | HuggingFace |

#### Muninn WW1 Documents
- **Fonte originale:** Muninn Project (rdf.muninn-project.org) — archivio linked data WWI
- **Copertura:** 28.700 documenti d'archivio della Prima Guerra Mondiale
- **Provenienza:** 28.676 Attestation Papers + 24 altri documenti
- **Paese:** 100% Canada (Canadian Expeditionary Force)
- **Campi per documento:** document_id, title, description, primary_topic (nome, cognome, data nascita, alleanza), publisher, custodian, creator, jurisdiction, license, access_rights, country, source_url, date_created, date_published, num_pages, first_page_image_url
- **Utilizzo nel training:** istruzioni di analisi documentale ("Analizza il seguente documento d'archivio della Prima Guerra Mondiale")

#### CommandNet — Dottrina militare 1900-1999
- **Fonte originale:** Euroswarms (dataset sintetico basato su dottrina militare storica)
- **Copertura:** 10.000 esempi conversazionali in formato ShareGPT
- **Periodo:** 1900-1999
- **Dottrine militari coperte:**
  - Industrial Attrition and Trench Penetration
  - Infiltration and Decentralized Assault Groups
  - Deep Operation (dottrina sovietica)
  - Blitz and Mobile Combined Arms
  - Amphibious Operational Sequencing
  - Protracted People's War
  - Population-Centric Counterinsurgency
  - Maneuver Warfare and Decision-Cycle Pressure
  - AirLand Battle
  - Deterrence and Escalation Management
- **Formato conversazione:** system (analista strategico) + human (scenario tattico) + gpt (analisi dottrinale)
- **Esempio:** "Staff-college analysis request (1966, conventional). Doctrine frame: Amphibious Operational Sequencing. Terrain: desert steppe..."

### 2.3 Dataset non scaricati (formato non supportato)

| Dataset | Motivo |
|---|---|
| `DeepMount00/cultura_generale-ITA` | No supported data files su HuggingFace |
| `dtufail/nuremberg-trials-corpus` | No supported data files (formato custom JSONL+embeddings) |

### 2.4 Risorse esterne non su HuggingFace (raccomandate)

| Risorsa | Lingua | Contenuto | URL |
|---|---|---|---|
| **Voci della Grande Guerra (VGG)** | IT | 99 testi, 22.000 pagine, italiano WWI (CNR Pisa/Accademia della Crusca) | vocidellagrandeguerra.it |
| **Europeana Newspapers** | Multi | 32 miliardi token, 12 lingue, include italiano, epoca WWI | biglam/europeana_newspapers |
| **Bollettini di Guerra WWI** | IT | 1.361 bollettini (24 maggio 1915 - 11 novembre 1918) | CoLingLab, Università di Pisa |
| **Memorie partigiane WWII** | IT | 25 libri, memorie partigiani italiani NW Italia (1943-45) | Università di Pisa (arxiv 1904.05439) |

---

## 3. Dataset convertito per fine-tuning

### Formato ChatML
Tutti i dataset sono stati convertiti in formato `messages` (system/user/assistant) compatibile con Qwen2.5.

| File | Esempi | Dimensione |
|---|---|---|
| `quandho_chatml.jsonl` | 1.800 | 1.7 MB |
| `aya_ita_chatml.jsonl` | 40 | 0.0 MB |
| `muninn_ww1_chatml.jsonl` | 28.700 | 19.4 MB |
| `commandnet_chatml.jsonl` | 10.000 | 28.9 MB |
| **`train_merged.jsonl`** | **40.540** | **50.0 MB** |

### Configurazione LoRA
```yaml
base_model: Qwen/Qwen2.5-3B-Instruct
method: lora
lora_r: 16
lora_alpha: 32
target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]
learning_rate: 2e-4
epochs: 3
batch_size: 4
max_seq_length: 2048
quantization: 4-bit (NF4)
```

---

## 4. Database locale (dati reali)

### Database `imi_internati.db`

| Tabella | Record | Descrizione |
|---|---|---|
| `internati` | 20.465 | Internati Militari Italiani (IMI) |
| `decorati` | 1.286 | Decorati al valor militare |
| `archivio_documenti` | 433 | Documenti d'archivio |
| `fonti_indice` | 35.664 | Fonti indicizzate |
| `collegamenti` | 2.349.417 | Collegamenti tra record |
| `record_links` | 169.184 | Link strutturati tra record |
| `claims` | 40 | Claim storici strutturati |

### Database `eventi_1gm.db`

| Tabella | Record | Descrizione |
|---|---|---|
| `eventi_1gm` | 22 | Eventi canonici WWI/WII |
| `event_aliases` | 90 | Alias eventi (sinonimi, nomi alternativi) |
| `map_features` | 0 | Feature geografiche (schema pronto, vuoto) |

### Eventi canonici coperti

**WWI (15 eventi):**
- Battaglie dell'Isonzo (parent di Carso, Caporetto, Monte Nero, Tolmino)
- Battaglia del Piave (parent di Monte Grappa, Pasubio)
- Battaglia di Vittorio Veneto
- Altopiano di Asiago
- Monte Col di Lana
- Monte San Michele
- Fronte Albanese, Fronte Macedone
- Prigionia (fase)

**WWII (7 eventi):**
- Operazione Achse (armistizio 8 settembre 1943)
- Eccidio di Cefalonia
- Campagna di Russia (ARMIR)
- Battaglia di Tobruk
- Battaglia di Cassino
- Mauthausen e Gusen (internamento)
- Lavoro forzato nel Reich (deportazione)

### Alias eventi (90 totali, esempi)
- Caporetto → Kobarid, Ripiegamento al Piave, Settore di Tolmino
- Isonzo → Medio Isonzo, Basso Isonzo, Alto Isonzo, Soča
- Carso → Carso

---

## 5. Argomenti a cui risponde la nuova AI

### 5.1 Chat diretta (`/api/chat`)
La chat AI risponde a domande su:

**Storia italiana XX secolo:**
- Regno del Sud e cobelligerazione
- Processo di Verona, RSI, fascismo
- Eccidio delle Fosse Ardeatine
- Impresa del Gran Sasso / Operazione Quercia
- Scissioni politiche post-belliche (CGIL/CISL/UIL)
- Censura militare e posta dal fronte
- Organizzazione delle trincee

**Eventi bellici canonici (dal DB):**
- Tutti i 22 eventi canonici con descrizione, date, luoghi
- Gerarchia eventi (es. Isonzo → Carso, Caporetto, Monte Nero)
- Alias e disambiguazione (es. "Soča" = Isonzo, "Kobarid" = Caporetto)

**Dottrina militare 1900-1999:**
- Analisi tattico-operativa
- Dottrine: Blitz, Deep Operation, Counterinsurgency, AirLand Battle
- Scenari ipotetici con terrain/weather constraints

**Documenti d'archivio WWI:**
- Analisi di Attestation Papers canadesi
- Estrazione metadati (persona, alleanza, data, pagine)

### 5.2 RAG pipeline (`/api/rag/retrieve`)
Il sistema RAG recupera contesto da:
- `eventi_1gm` (descrizioni eventi)
- `internati` (biografie IMI)
- `decorati` (decorazioni)
- `archivio_documenti` (documenti)
- `fonti_indice` (fonti archivistiche)

Con reranking basato su:
- Qualità della fonte
- Compatibilità temporale
- Compatibilità geografica
- Indipendenza delle fonti

### 5.3 Dossier narrativi (`event_narrative_builder.py`)
Genera report strutturati con 13 sezioni:
1. Inquadramento storico
2. Narrazione
3. Cronologia
4. Luoghi
5. Unità coinvolte
6. Cause e conseguenze
7. Fatti concordanti
8. Versioni divergenti
9. Elementi incerti
10. Fonti archivistiche
11. Fonti bibliografiche
12. Grafo delle relazioni
13. Persone collegate

---

## 6. Endpoint API attivi

| Endpoint | Metodo | Funzione |
|---|---|---|
| `/api/chat` | POST | Chat AI con history e contesto |
| `/api/chat/health` | GET | Stato runtime AI |
| `/api/ai-runtime/health` | GET | Health adapter (LM Studio) |
| `/api/ai-runtime/config` | GET | Configurazione (no segreti) |
| `/api/ai-runtime/benchmark` | POST | Benchmark latenza |
| `/api/rag/retrieve` | GET | RAG retrieval + reranking + context |
| `/api/rag/validate` | POST | Validazione output AI |
| `/api/canonical-events` | GET | Lista eventi canonici |
| `/api/canonical-events/{id}` | GET/PUT | Evento singolo |
| `/api/canonical-events/{id}/children` | GET | Eventi figlio |
| `/api/map-features/event/{id}` | GET | Feature mappa per evento |
| `/api/map-features` | POST | Crea/aggiorna feature |
| `/api/map-features/{id}/review` | PUT | Review feature |
| `/api/graph/entity/{table}/{id}` | GET | Grafo canonico entità |
| `/api/graph/edges/{id}/review` | POST | Review arco grafo |
| `/api/event/chat` | POST | Chat evento (legacy, provider remoti) |

---

## 7. Frontend integrato

| Pagina | Route | Funzione |
|---|---|---|
| Chat AI | `/chat` | Chat standalone con stato runtime |
| Eventi | `/eventi` | Lista eventi con tag WWI/WWII |
| Dossier evento | `/eventi/:name` | Dossier + Chat AI con contesto evento |
| Grafo entità | `/grafo/:table/:id` | Visualizzazione ForceGraph + filtri |
| Ricerca AI | `/ricerca` | Ricerca AI federata |

---

## 8. Limitazioni e raccomandazioni

### Limitazioni attuali
1. **Modello 3B**: Qwen2.5-3B ha capacità limitate su domande molto specifiche o complesse
2. **Dataset italiano scarso**: solo 1.840 esempi in italiano vs 38.700 in inglese
3. **Muninn WW1**: 100% documenti canadesi, nessun documento italiano
4. **CommandNet**: sintetico, non basato su fonti primarie
5. **Fine-tuning non ancora eseguito**: il modello usa il base Qwen2.5-3B senza addestramento specifico

### Raccomandazioni
1. **Eseguire fine-tuning LoRA** su Colab T4 con `finetune_qwen.py --train` (30 min)
2. **Scaricare VGG** (Voci della Grande Guerra) dal sito CNR per arricchire il dataset italiano
3. **Generare Q&A dai dati locali**: creare coppie domanda-risposta dai 20.465 internati e 22 eventi canonici
4. **Valutare modello 7B**: se la qualità del 3B non basta, testare Qwen2.5-7B-Instruct (Q4_K_M, ~4.5GB)
5. **Integrare Europeana Newspapers** per fonti primarie italiane WWI

---

## 9. File creati in questa sessione

| File | Righe | Descrizione |
|---|---|---|
| `ai_runtime.py` | 322 | Interfaccia InferenceAdapter + 3 adapter |
| `ai_runtime_api.py` | 85 | API health/benchmark/config |
| `chat_api.py` | 95 | API chat con LM Studio |
| `rag_pipeline.py` | ~400 | RAG pipeline completo |
| `rag_api.py` | ~60 | API RAG |
| `graph_schema.py` | 153 | Schema grafo canonico |
| `graph_service.py` | 152 | Servizio grafo |
| `graph_api.py` | ~80 | API grafo |
| `graph_models.py` | 93 | Modelli Pydantic grafo |
| `event_schema.py` | ~120 | Schema eventi canonici |
| `event_canonical_api.py` | ~100 | API eventi canonici |
| `canonical_models.py` | ~250 | Modelli Pydantic canonici |
| `map_schema.py` | 80 | Schema map features |
| `map_features_api.py` | 100 | API map features |
| `database_registry.py` | 265 | Registry tabelle DB |
| `download_training_datasets.py` | 150 | Download dataset HuggingFace |
| `convert_training_datasets.py` | 180 | Conversione ChatML |
| `finetune_qwen.py` | 160 | Script LoRA training |
| `frontend/.../ChatPanel.tsx` | 200 | Componente chat React |
| `frontend/.../ChatPage.tsx` | 90 | Pagina chat standalone |
| `frontend/.../GraphEntityPage.tsx` | 220 | Pagina grafo canonico |

---

*Report generato il 25 luglio 2026 dal sistema IMI Extractor.*
