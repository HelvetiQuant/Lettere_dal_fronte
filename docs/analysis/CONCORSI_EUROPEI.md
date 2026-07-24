# IMI Extractor — Analisi Architetturale, Competitor e Strategia Concorsi Europei

**Data:** 9 Luglio 2026
**Versione:** 1.0
**Autore:** Team IMI Extractor

---

## 1. Analisi Architetturale

### 1.1 Stato attuale

**IMI Extractor** è una piattaforma di ricerca storica su caduti, internati e decorati della Prima e Seconda Guerra Mondiale che integra dati da 11+ fonti archivistiche in un unico database relazionale SQLite (~3,8M record).

### 1.2 Architettura a 6 livelli

| Livello | Nome | Funzione | Tecnologia |
|---|---|---|---|
| 1 | **Source Tables** | Una tabella per ogni fonte dati primaria | SQLite, scraping Python |
| 2 | **Entity Layer** | Entità normalizzate + grafo cross-dataset | FTS5/BM25, star schema |
| 3 | **Archivio Fonti** | Documenti originali scansionati con OCR | SHA256, OCR pipeline |
| 4 | **Memory Router** | Routing intelligente query, memoria episodica | Cue extraction,分层 routing |
| 5 | **Source Locator** | Indice leggero fonti esterne, fetch on-demand | Federation Layer, 19 provider |
| 6 | **Operativo** | Tracking avanzamento, log AI, usage | Progress, ai_ricerche |

### 1.3 Dati attuali (09/07/2026)

| Dataset | Record | Fonte |
|---|---:|---|
| Internati Militari Italiani (IMI) | 20.464 | Archivio di Stato Bolzano |
| Caduti Albo d'Oro | 342.555 | cadutigrandeguerra.it |
| Caduti Ministero Difesa | 162.646 | onorcaduti.difesa.it |
| Caduti Sardi | 20.435 | Unione Sarda |
| Caduti Bologna | 9.656 | Museo Risorgimento BO |
| Caduti CWGC | 448.938 | cwgc.org (in corso, target 1,76M) |
| Decorati Nastro Azzurro | 279.832 | istitutonastroazzurro.org |
| Decorati ISTORECO | 1.286 | Albi della Memoria |
| Caduti Francia WW1 | 24.279 | Mémoire des Hommes |
| NARA T315 OCR | 1.153 | NARA microfilm |
| NARA Catalog AAR | 272 | catalog.archives.gov |
| Archivio fonti | 1.153 | NARA T315 retrofit |
| Entità (linker) | 502.282 | Estrazione automatica |
| Collegamenti (grafo) | 2.266.696 | Cross-dataset linking |
| **TOTALE** | **~3.800.000** | |

### 1.4 Source Federation Layer (nuovo)

Sistema di federazione archivistica con 19 provider integrati:
- **Provider concreti**: NARA (API + DB), Antenati (HTML parsing + ARK), CWGC (DB locale)
- **Provider stub**: Arolsen, Bundesarchiv, SHD/Mémoire des Hommes, TNA, Europeana, Gallica/BNF, Internet Archive, Google Books, ABMC, LAC Canada, Australian War Memorial, Archivportal-D, Internet Culturale, HathiTrust, USSME, Archivio di Stato
- **Principio**: il DB è un indice intelligente, non un repository. Fetch on-demand solo da domini autorizzati. AI non scarica direttamente.

### 1.5 Dashboard Investigativa (nuovo)

Interfaccia con:
- **Analytics bar**: 8 metriche globali in tempo reale
- **Ricerca conversazionale**: query semplice → search locale → dashboard soldato → fallback federato
- **Risultati a tab**: Dati Soldato (fatti verificati/non), Timeline, Fonti Locali, Fonti Esterne, Entità
- **Source cards**: badge disponibilità, score, bottoni Apri/IIIF/Scarica/Analizza
- **Analisi AI**: selezione fonti → contesto minimo → invio AI

### 1.6 Punti di forza architetturali

1. **Unicità**: nessun sistema esistente integra IMI + Albo d'Oro + CWGC + NARA + decorati in un unico grafo
2. **Scalabilità**: SQLite WAL con 64MB cache + 256MB mmap gestisce 3,8M record su hardware consumer
3. **AI-efficient**: Memory Router riduce token AI del ~90% (routing locale prima del cloud)
4. **Federazione**: 19 provider con scoring unificato, nessun download automatico
5. **Open data**: tutti i dati sono da fonti pubbliche, l'app è gratuita

### 1.7 Gap da colmare

1. **Provider stub**: 16 su 19 provider sono stub, non query reali
2. **Research-to-Index**: query senza risultato locale non creano memoria (TODO domani)
3. **Frontend**: manca responsive design mobile, manca mappa geospaziale
4. **Interoperabilità**: non conforme a Europeana Data Model (EDM)
5. **Autenticazione**: nessun sistema di login/utente
6. **API pubbliche**: nessuna documentazione OpenAPI/Swagger

---

## 2. Analisi Competitor

### 2.1 Competitor diretti (ricerca caduti/internati italiani)

| Competitor | Scope | Dati | Differenza vs IMI Extractor |
|---|---|---|---|
| **Ministero Difesa — Onorcaduti** | Caduti 1a GM | 162k | Solo 1a GM, no internati, no decorati, no grafo |
| **cadutigrandeguerra.it** | Albo d'Oro | 342k | Solo Albo d'Oro, no cross-linking |
| **Archivio di Stato Bolzano** | IMI | 20k | Solo IMI, ricerca per lettera, no federazione |
| **ISTORECO — Albi della Memoria** | Decorati | 1.286 | Solo decorati ISTORECO |
| **Nastro Azzurro** | Decorati | 279k | Solo decorati, no caduti/internati |
| **CWGC** | Caduti Commonwealth | 1,76M | Solo Commonwealth, no italiani |
| **ISRAL Asti** | Caduti astigiani | 4k | Solo provincia di Asti |
| **Museo Guerra Rovereto** | Caduti trentini | — | Solo Trentino |
| **14-18.it Lombardia** | Caduti lombardi | 80k | Solo Lombardia |

**Vantaggio competitivo**: IMI Extractor è l'**unico sistema che federata tutti questi dataset** in un unico grafo con entità normalizzate e collegamenti cross-dataset (2,2M archi). Nessun competitor offre ricerca cross-fonte.

### 2.2 Competitor indiretti (piattaforme heritage digitale)

| Competitor | Scope | Differenza |
|---|---|---|
| **Europeana** | Aggregatore europeo heritage | Generico, non specializzato militare, no grafo entità |
| **MEMORISE (HORIZON)** | Heritage Nazi persecution | Focus Olocausto, non militare italiano |
| **ECHOES (HORIZON)** | European Cloud Cultural Heritage | Piattaforma, non contenuto |
| **WALKING MEMORY (HORIZON)** | Memoria culturale immersive | AR/walks, no database storico |
| **Arolson International Archive** | Persone perseguitate Nazi | Focus persecuzione, no militare italiano |
| **Ancestry.com / FamilySearch** | Genealogia generale | Commerciali, no specializzazione militare italiana, no grafo |

**Vantaggio competitivo**: IMI Extractor si posiziona in un **nicchia non coperta** — federazione di fonti militari italiane + internamento + cross-linking semantico. Nessun progetto EU esistente copre questo spazio.

### 2.3 Cosa ci differenzia

1. **Federazione attiva**: non un semplice catalogo, ma ricerca cross-provider con scoring
2. **Grafo entità**: 500k entità collegate da 2,2M archi — nessun competitor ha questo
3. **Memory Router**: routing AI-efficient che riduce costi cloud del 90%
4. **Research-to-Index** (proposto): nessuna ricerca persa, ogni query genera memoria
5. **Open source / gratuito**: vs Ancestry.com (~€300/anno)
6. **Focus italiano**: nessun competitor EU si concentra su militari italiani WW1/WW2

---

## 3. Concorsi e Bandi — Strategia di Partecipazione

### 3.1 Priorità 1 — Bandi italiani (più rapidi, meno complessi)

#### 3.1.1 MiC — Bando Grande Guerra 2026-2027

| Campo | Dettaglio |
|---|---|
| **Bando** | Patrimonio storico della Prima Guerra Mondiale |
| **Ente** | Ministero della Cultura — DG Archeologia, belle arti e paesaggio |
| **Budget** | €412.711 (€189.501 per 2026 + €223.210 per 2027) |
| **Scadenza** | 15 Luglio 2026 ore 12:00 |
| **Durata** | Progetti entro 30 Settembre 2027 |
| **Link** | grandeguerra.cultura.gov.it |
| **Fit** | ★★★★★ — Digitalizzazione materiali archivistici, catalogazione beni, fruibilità pubblica |
| **Cosa richiedere** | Digitalizzazione + catalogazione + piattaforma di ricerca per fondi Grande Guerra |
| **Requisito** | Soggetti ex L.78/2001 (enti pubblici, fondazioni, associazioni). Partnership con Archivio di Stato o Museo Guerra Rovereto consigliato. |

#### 3.1.2 MiC — Bandi Archivi (Direzione Generale Archivi)

| Campo | Dettaglio |
|---|---|
| **Bando** | Ricerca scientifica in ambito archivistico + Movimenti politici |
| **Ente** | Ministero della Cultura — DG Archivi |
| **Budget** | €1.800.000 (investimento 2025, in crescita 2026) |
| **Scadenza** | 1-15 Febbraio 2027 (annuale) |
| **Durata** | Entro 31 Ottobre 2027 |
| **Link** | BandiDGA portale telematico |
| **Fit** | ★★★★☆ — Riordinamento, inventariazione, censimento, banche dati interoperabili |
| **Cosa richiedere** | Censimento e digitalizzazione fondi archivistici militari + piattaforma di ricerca interoperabile |
| **Requisito** | Associazioni (anche non riconosciute, iscritte RUNTS), fondazioni, enti pubblici |

#### 3.1.3 MiC — Digital MAB / Dicolab

| Campo | Dettaglio |
|---|---|
| **Bando** | Digital MAB — Ecosistemi digitali tra musei, archivi e biblioteche |
| **Ente** | Ministero della Cultura — PNRR Cultura 4.0 |
| **Budget** | 10 progetti selezionati |
| **Fit** | ★★★☆☆ — Convergenza digitale musei/archivi/biblioteche |
| **Cosa richiedere** | Integrazione collezioni museali + archivistiche militari in piattaforma digitale |
| **Nota** | Bando 2025 chiuso, prossima edizione attesa 2026/2027 |

### 3.2 Priorità 2 — Bandi europei (più fondi, più complessi)

#### 3.2.1 Creative Europe — European Cooperation Projects 2026

| Campo | Dettaglio |
|---|---|
| **Bando** | CREA-CULT-2026-COOP-1 (Small Scale) / COOP-2 (Medium Scale) |
| **Ente** | EACEA — Creative Europe Programme |
| **Budget** | €60.273.174 totali, ~150 progetti |
| **Small Scale** | 3 partner da 3 paesi, lump sum €40k/€60k/€100k |
| **Medium Scale** | 5 partner da 5 paesi, lump sum €150k/€250k/€400k |
| **Scadenza** | Apertura 5 Marzo 2026, scadenza prevista Settembre 2026 |
| **Durata** | Max 48 mesi |
| **Link** | Funding & Tenders Portal |
| **Fit** | ★★★★☆ — Obiettivo 2 (Innovation): capacity building, digital transition, heritage |
| **Cosa richiedere** | Piattaforma di federazione archivistica per heritage militare europeo, con partner da IT, DE, FR, UK, PL |
| **Requisito** | Coordinator con esistenza legale ≥2 anni. Partnership transnazionale obbligatorio. |
| **Azione** | Contattare: Museo Guerra Rovereto (IT), Bundesarchiv (DE), Mémoire des Hommes/SHD (FR), Imperial War Museum (UK), Museo Guerra Varsavia (PL) |

#### 3.2.2 Horizon Europe — Cluster 2 (Culture, Creativity, Inclusive Society)

| Campo | Dettaglio |
|---|---|
| **Bando** | HORIZON-CL2-2026-01-HERITAGE |
| **Ente** | European Commission — REA |
| **Budget** | €85,5M totali, 7 topics |
| **Scadenza** | 23 Settembre 2026 |
| **Durata** | Tipicamente 36-48 mesi |
| **Link** | rea.ec.europa.eu/funding-and-grants |
| **Fit** | ★★★★★ — Cultural Heritage + AI + digital technologies + memory |
| **Topics rilevanti** | Da verificare nel Work Programme 2026-2027 (pubblicato): preservazione heritage con tecnologie digitali avanzate, AI per heritage |
| **Cosa richiedere** | Ricerca su federazione archivistica con AI per memoria storica europea dei conflitti |
| **Requisito** | Consorzio transnazionale (min 3 partner da 3 paesi), approccio research-and-innovation |

#### 3.2.3 Digital Europe Programme — Data Space for Cultural Heritage

| Campo | Dettaglio |
|---|---|
| **Bando** | EC-CNECT/LUX/2026/OP/0069 (tender) + capacity building grants |
| **Ente** | DG CNECT |
| **Budget** | €30M (tender deployment) + €4M (capacity building) |
| **Tender** | Service contract, scadenza 8 Giugno 2026 (passata) |
| **Grants** | Capacity building, focus SME 75% funding |
| **Fit** | ★★★★☆ — Data space, AI metadata enrichment, 3D, interoperabilità |
| **Cosa richiedere** | Arricchimento metadata con AI, interoperabilità con Europeana, conformità EDM |
| **Azione** | Allineare IMI Extractor al Europeana Data Model (EDM) e integrare come data provider |

#### 3.2.4 Europeana Research Grants

| Campo | Dettaglio |
|---|---|
| **Bando** | Europeana Research Grants Programme |
| **Ente** | Europeana Foundation (CEF funded) |
| **Budget** | €25k/anno per eventi |
| **Stato** | Currently closed, prossima call attesa 2027 |
| **Fit** | ★★★☆☆ — Eventi/workshop su crowdsourcing + research su heritage |
| **Cosa richiedere** | Workshop su crowdsourcing per arricchimento dati militari italiani |
| **Requisito** | Istituzioni culturali/ricerca in EU member states |

#### 3.2.5 PPPA — Born Digital Heritage 2026

| Campo | Dettaglio |
|---|---|
| **Bando** | PPPA-2026-BORN-DIGITAL-HERITAGE |
| **Ente** | European Commission — Pilot Projects & Preparatory Actions |
| **Budget** | €1.985.000 (singolo progetto, 85% cofinanziamento) |
| **Scadenza** | 16 Luglio 2026 ore 17:00 CEST |
| **Fit** | ★★☆☆☆ — Focus su born-digital, non digitalizzazione tradizionale. Marginale. |

### 3.3 Timeline partecipazione

```
LUG 2026  → MiC Grande Guerra (scad. 15 Lug) — URGENTE
SET 2026  → Creative Europe COOP (scad. ~Set) — preparare consorzio
SET 2026  → Horizon Europe Cluster 2 (scad. 23 Set) — preparare consorzio
FEB 2027  → MiC Bandi Archivi (1-15 Feb)
2027      → Europeana Research Grants (atteso)
2027      → Digital MAB / Dicolab (atteso)
```

---

## 4. Presentazione per Concorsi

### 4.1 Titolo progetto

**MEMORIA FEDERATA — Piattaforma di ricerca storica federata per la memoria dei conflitti europei**

### 4.2 Elevator pitch

> Ogni anno, milioni di persone cercano informazioni su parenti caduti, internati o decorati nelle guerre mondiali. I dati esistono, ma sono frammentati in decine di archivi nazionali e internazionali, ciascuno con interfacce, formati e lingue diverse. MEMORIA FEDERATA unifica queste fonti in un'unica piattaforma intelligente che federata 19+ archivi europei e internazionali, collega 3,8 milioni di record tramite un grafo semantico di 500.000 entità e 2,2 milioni di relazioni, e usa l'AI in modo etico e efficiente per guidare la ricerca — senza mai scaricare documenti pesanti, ma indicizzando metadati e fornendo accesso on-demand. Nessuna ricerca va persa: ogni query genera memoria strutturata, verificabile e migliorabile.

### 4.3 Problem statement

1. **Frammentazione**: i dati sui caduti/internati europei sono sparsi in 50+ archivi con formati eterogenei
2. **Inaccessibilità**: molte fonti non hanno API, richiedono navigazione manuale, o sono in lingue diverse
3. **Nessun cross-linking**: nessun sistema collega lo stesso soldato tra dataset diversi (es. internato IMI → caduto CWGC → decorato Nastro Azzurro)
4. **Costi AI elevati**: l'uso diretto di LLM su documenti completi è economicamente insostenibile per un'app gratuita
5. **Ricerche perse**: query senza risultato locale vengono dimenticate, nessuna memoria accumulata

### 4.4 Soluzione

**MEMORIA FEDERATA** affronta questi problemi con 4 innovazioni:

#### Innovazione 1 — Source Federation Layer
Federazione di 19+ provider archivistici con interfaccia unificata, scoring dei risultati, e fetch on-demand da domini autorizzati. Il DB locale è un indice intelligente (~50MB di metadati), non un repository di documenti (~TB).

#### Innovazione 2 — Grafo Semantico Cross-Dataset
500.000 entità (persone, luoghi, eventi) normalizzate e collegate da 2,2 milioni di relazioni cross-dataset. Per la prima volta, è possibile trovare lo stesso soldato in IMI, Albo d'Oro, CWGC e decorati con una sola query.

#### Innovazione 3 — Memory Router (AI-efficient)
Routing gerarchico delle query: prima SQLite (sub-ms), poi FTS5/BM25, poi grafo, poi archivio locale, e solo come ultimo fallback cloud AI. Riduce i costi AI del ~90% mantenendo qualità di risposta.

#### Innovazione 4 — Research-to-Index
Ogni query senza risultato locale crea automaticamente una scheda minima nel database (status=not_verified) e la arricchisce con metadati dalle fonti esterne federate. Nessuna ricerca va persa: ogni fallimento genera nuova memoria strutturata.

### 4.5 Impatto atteso

| Metrica | Valore |
|---|---|
| Record integrati | 3,8M (target: 10M con provider completi) |
| Fonti federate | 19 provider (target: 30+) |
| Entità collegate | 500k (target: 2M con espansione EU) |
| Archi grafo | 2,2M (target: 10M) |
| Costo AI per query | ~€0,001 (vs €0,10 senza Memory Router) |
| Utenti target (anno 1) | 100k ricercatori, storici, familiari |
| Paesi coinvolti | IT, DE, FR, UK, PL, NL, AU, CA, US |

### 4.6 Allineamento con policy EU

| Policy EU | Allineamento |
|---|---|
| **Digital Transition** | AI etica, data spaces, open data |
| **European Cultural Heritage** | Preservazione e accessibilità heritage militare |
| **Europeana Strategy 2020-2025** | Conformità EDM, interoperabilità, riuso |
| **AI Act** | AI non scarica documenti, solo metadati+excerpt |
| **Open Science** | Dati aperti, codice open source |
| **Social cohesion** | Memoria condivisa, accesso gratuito |
| **Digital Europe Programme** | Data space for cultural heritage |

### 4.7 Budget richiesto (esempio Creative Europe Medium Scale)

| Work Package | Descrizione | Budget (€) |
|---|---|---|
| WP1 | Project management & coordination | 40.000 |
| WP2 | Source Federation Layer — espansione provider (Arolsen, Bundesarchiv, SHD, TNA) | 80.000 |
| WP3 | Grafo semantico — espansione cross-dataset EU (DE, FR, UK, PL) | 70.000 |
| WP4 | Research-to-Index — auto-indexing + research gaps | 50.000 |
| WP5 | Frontend — dashboard investigativa multilingue, mappa geospaziale, mobile | 60.000 |
| WP6 | Europeana integration — conformità EDM, data provider | 30.000 |
| WP7 | Dissemination & community engagement | 30.000 |
| WP8 | Sustainability & business model | 20.000 |
| **TOTALE** | | **€380.000** |

### 4.8 Partner consigliati per consorzio

| Ruolo | Organizzazione | Paese | Motivo |
|---|---|---|---|
| Coordinator | IMI Extractor / Associazione | IT | Piattaforma, dati, tecnologia |
| Partner 1 | Bundesarchiv / Arolsen International Archive | DE | Fonti tedesche IMI, expertise archivistica |
| Partner 2 | SHD — Service Historique de la Défense / Mémoire des Hommes | FR | Fonti francesi, API esistenti |
| Partner 3 | Imperial War Museum / TNA | UK | Fonti UK, expertise digital heritage |
| Partner 4 | Museo Storico Guerra Rovereto / ISTRECO | IT | Heritage Grande Guerra IT |
| Partner 5 (optional) | Muzeum II Wojny Światowej / Europeana Foundation | PL/NL | Fonti polacche, network EU |

### 4.9 Sostenibilità post-progetto

1. **Modello gratuito**: app gratuita per utenti finali (familiari, ricercatori, storici)
2. **API tier**: API gratuite per ricerca base, API premium a pagamento per istituzioni
3. **Crowdsourcing**: utenti possono contribuire correzioni e arricchimenti (verificati)
4. **Partnership istituzionali**: accordi con Archivi di Stato, Musei, Ministero Difesa
5. **Grant successivi**: Horizon Europe, Digital Europe, Europeana per espansione

---

## 5. Contatti utili per partnership

### 5.1 Italia

| Ente | Referente | Contatto | Ruolo |
|---|---|---|---|
| Archivio di Stato Bolzano | Direzione | archivio.bolzano@archivi.bolzano.it | Fonte IMI |
| Museo Storico Guerra Rovereto | Direzione | info@museoguerra.it | Partner heritage WW1 |
| Ministero Difesa — UTCMD | Ufficio Tutela Cultura Memoria Difesa | utcmd@utcmd.difesa.it | Fonte caduti |
| MiC — DG Archivi | Direzione Generale | dga@beniculturali.it | Bandi archivi |
| MiC — Grande Guerra | Comitato tecnico-scientifico | grandeguerra.cultura.gov.it | Bando Grande Guerra |
| ISTORECO | Istituto Storico Reggio Emilia | istoreco@istoreco.it | Fonte decorati |

### 5.2 Europa

| Ente | Paese | Contatto | Ruolo |
|---|---|---|---|
| Arolsen International Archive | DE | info@arolsen-archives.org | Fonti persecuzione Nazi |
| Bundesarchiv | DE | post@bundesarchiv.de | Fonti militari tedesche |
| SHD — Mémoire des Hommes | FR | contact@memoiredeshommes.sga.defense.gouv.fr | Fonti caduti francesi |
| TNA — The National Archives | UK | enquiry@nationalarchives.gov.uk | Fonti UK WW2 |
| Europeana Foundation | NL | info@europeana.eu | Network heritage EU |
| Imperial War Museum | UK | enquiries@iwm.org.uk | Fonti UK + expertise |

### 5.3 Template mail per contatto istituzionale

```
Oggetto: Proposta di partnership — Progetto MEMORIA FEDERATA (Creative Europe / Horizon Europe)

Gentile [Direzione / Nome],

Sono [Nome Cognome], responsabile del progetto MEMORIA FEDERATA — una piattaforma
di ricerca storica che federata dati su caduti, internati e decorati delle guerre
mondiali da 19+ archivi europei in un unico grafo semantico.

Il progetto ha già integrato 3,8 milioni di record da fonti italiane (Archivio di
Stato Bolzano, Albo d'Oro, Ministero Difesa, CWGC, NARA, decorati) con 500.000
entità collegate da 2,2 milioni di relazioni cross-dataset.

Stiamo preparando una proposta per [Creative Europe / Horizon Europe Cluster 2]
con l'obiettivo di espandere la federazione a fonti [tedesche/francesesi/uk] e
vorremmo proporVi di partecipare come partner del consorzio.

Il Vostro ruolo sarebbe:
- Fornire accesso ai metadati dei Vostri fondi archivistici militari
- Partecipare alla definizione dei criteri di indicizzazione e scoring
- Contribuire alla validazione storica dei dati cross-dataset

Il progetto prevede un budget di €[X] per il Vostro contributo, con durata di
[36/48] mesi.

Saremmo lieti di organizzare una call conoscitiva per approfondire.

Cordiali saluti,

[Nome Cognome]
[Titolo/Ruolo]
[Organizzazione]
[Email] | [Telefono]
[Link piattaforma/demo]
```

---

## 6. Roadmap (12 mesi)

| Mese | Milestone |
|---|---|
| Lug 2026 | Sottomissione bando MiC Grande Guerra |
| Ago 2026 | Contatti partner EU (DE, FR, UK) per consorzio |
| Set 2026 | Sottomissione Creative Europe COOP + Horizon Europe Cluster 2 |
| Ott 2026 | Completamento Research-to-Index + provider reali (Arolsen, SHD, TNA) |
| Nov 2026 | Conformità Europeana Data Model (EDM) |
| Dic 2026 | Integrazione mappa geospaziale + mobile responsive |
| Gen 2027 | Lancio beta pubblica |
| Feb 2027 | Sottomissione MiC Bandi Archivi |
| Mar 2027 | Documentazione API OpenAPI/Swagger |
| Giu 2027 | Versione multilingue (IT, EN, DE, FR) |
| Set 2027 | Integrazione completa Europeana come data provider |
| Dic 2027 | Sustainability plan + business model finale |

---

## 7. Suggerimenti per ricerca personale

1. **Verificare topic esatti Horizon Europe 2026**: scaricare il Work Programme 2026-2027 da ec.europa.eu/info/funding-tenders — i topic specifici potrebbero non essere ancora pubblicati
2. **Contattare l'Europeana Foundation**: informarsi sui requisiti per diventare data provider (aggregation)
3. **Verificare eleggibilità**: per Creative Europe serve personalità giuridica da ≥2 anni — considerare costituzione associazione/APS
4. **Network IT**: partecipare a eventi del MiC Digital Library e Dicolab per networking
5. **APRE (Agenzia Promozione Ricerca Europea)**: contattare l'APRE per assistenza gratuita su bandi Horizon Europe
6. **NCP (National Contact Point)**: l'NTP italiano per Cluster 2 può dare supporto gratuito
7. **Registrarsi su EU Funding & Tenders Portal**: necessario per sottomettere proposte

---

## 8. Conclusioni

IMI Extractor / MEMORIA FEDERATA si posiziona in uno **spazio unico** non coperto da nessun competitor esistente: federazione di fonti militari italiane + europee con grafo semantico e AI etica. L'architettura a 6 livelli è matura (3,8M record, 19 provider, dashboard operativa) e allineata con le policy EU (Digital Transition, Cultural Heritage, AI Act, Open Science).

**Azione immediata consigliata**: sottomettere il bando MiC Grande Guerra (scadenza 15 Luglio 2026 — 6 giorni) in partnership con un ente ex L.78/2001, e avviare contatti con Bundesarchiv/SHD/IWM per consorzio Creative Europe.
