# Budget Dettagliato — MEMORIA FEDERATA

## Richiesta di contributo: €37.000

---

## Riepilogo per categoria di spesa

| # | Categoria | Descrizione | Importo (€) | % |
|---|---|---|---:|---:|
| 1 | Personale | Sviluppatore AI, operatore dati, ricercatore storico | 27.500 | 74,3% |
| 2 | API commerciali + genealogiche | OpenAI, Mistral, Perplexity, Ancestry, MyHeritage, recapito corrispondenza | 3.345 | 9,0% |
| 3 | Infrastruttura | Server cloud, server locale, dominio, backup | 1.240 | 3,4% |
| 4 | Costi energetici | Elettricita' server locale 24/7 | 300 | 0,8% |
| 5 | Trasferte | Sopralluoghi archivi, musei, istituzioni | 1.000 | 2,7% |
| 6 | Comunicazione | Diffusione, eventi, materiali | 800 | 2,2% |
| 7 | Rendicontazione | Report finale, documentazione | 300 | 0,8% |
| 8 | Tasse e oneri | IVA su acquisti, bolli, imposte | 600 | 1,6% |
| 9 | Contingenza | Margine 5% per imprevisti | 1.915 | 5,2% |
| | **TOTALE** | | **€37.000** | **100%** |

---

## 1. Personale — €27.500

### 1.1 Sviluppatore AI / Backend Engineer

Sviluppo e manutenzione piattaforma: estensione federation layer, dashboard investigativa, API REST, mappa geospaziale, Research-to-Index, integrazione provider reali.

| Voce | Descrizione | U.d.m. | Qta | Costo unitario | Totale (€) |
|---|---|---|---|---|---:|
| 1.1a | Sviluppo backend: API REST, federation layer, memory router | giornate | 35 | 250 | 8.750 |
| 1.1b | Sviluppo frontend: dashboard, mappa geospaziale, responsive | giornate | 25 | 250 | 6.250 |
| 1.1c | Integrazione AI: OpenAI/Mistral/Perplexity, scoring, routing | giornate | 20 | 250 | 5.000 |
| | **Subtotale sviluppatore** | | 80 gg | | **20.000** |

### 1.2 Operatore inserimento dati manuale (UI/DB)

Inserimento manuale di record non disponibili via API: fondi archivistici cartacei, schede non digitalizzate, correzioni e validazioni. Lavoro tramite interfaccia web della piattaforma.

| Voce | Descrizione | U.d.m. | Qta | Costo unitario | Totale (€) |
|---|---|---|---|---|---:|
| 1.2a | Inserimento manuale record da fonti cartacee (archivi, musei) | ore | 100 | 20 | 2.000 |
| 1.2b | Validazione e correzione record ambigui/omonimie via UI | ore | 50 | 20 | 1.000 |
| | **Subtotale operatore** | | 150 ore | | **3.000** |

### 1.3 Ricercatore storico (QA e validazione)

Verifica storica dei dati cross-dataset, identificazione errori, validazione collegamenti semantici, contatti con istituzioni.

| Voce | Descrizione | U.d.m. | Qta | Costo unitario | Totale (€) |
|---|---|---|---|---|---:|
| 1.3a | Censimento e contatto istituzioni archivistiche | giornate | 15 | 150 | 2.250 |
| 1.3b | Validazione storica record e cross-linking | giornate | 15 | 150 | 2.250 |
| | **Subtotale ricercatore** | | 30 gg | | **4.500** |

---

## 2. API commerciali — €1.800 (12 mesi)

Costi basati sui prezzi ufficiali aggiornati a Luglio 2026 e sull'uso effettivo registrato nel sistema (`credits.py`, tabella `api_usage`). Include API AI per ricerca/parsing e API genealogiche per tracciamento discendenti e recapito corrispondenza storica.

### 2.1 OpenAI API

| Modello | Uso | Prezzo | Volume stimato/anno | Costo (€) |
|---|---|---|---|---:|
| GPT-4o-mini | Parsing testi, ricerca AI su DB locale | $0.15/1M input, $0.60/1M output | ~40M token (10k query x 4k token) | ~€25 |
| GPT-4o | Analisi immagini OCR, parsing visivo | $2.50/1M input, $10.00/1M output | ~5M token (500 pagine x 10k token) | ~€40 |
| | | | **Subtotale OpenAI** | **€600** |

> Stima prudente con buffer per picchi di traffico e nuove funzionalita'. Il Memory Router riduce le chiamate AI del ~90% instradando prima localmente (SQLite, FTS5, grafo).

### 2.2 Mistral API

| Modello | Uso | Prezzo | Volume stimato/anno | Costo (€) |
|---|---|---|---|---:|
| Pixtral-12B (OCR) | OCR documenti scansionati (microfilm, foto d'epoca) | $0.001/pagina | ~2.000 pagine | ~€2 |
| Mistral Large | Ricerca AI su DB locale (fallback) | ~€2/1M input, €6/1M output | ~10M token | ~€40 |
| | | | **Subtotale Mistral** | **€400** |

> Stima prudente con buffer per OCR di nuovi fondi archivistici e ricerca AI multi-provider.

### 2.3 Perplexity API

| Modello | Uso | Prezzo | Volume stimato/anno | Costo (€) |
|---|---|---|---|---:|
| Sonar | Ricerca web-enriched (fallback cloud, solo se 0 risultati locali) | ~$1/1M input, $1/1M output | ~5M token | ~€10 |
| | | | **Subtotale Perplexity** | **€300** |

> Il Memory Router attiva Perplexity solo come ultimo fallback quando 0 risultati locali. Volume stimato basso ma con buffer per fase di lancio.

### Riepilogo API

### 2.4 API genealogiche — ricerca antenati e discendenti

Servizi per tracciare discendenti viventi di soldati caduti/internati, al fine di recapitare corrispondenza e documenti mai consegnati alle famiglie durante la Grande Guerra.

| Provider | Uso | Prezzo | Volume stimato/anno | Costo (€) |
|---|---|---|---|---:|
| WikiTree API | Ricerca profili genealogici pubblici, match soldato→albero familiare | Gratuito (API pubblica) | ~5.000 query | 0 |
| FamilySearch API | Ricerca anagrafica, stato civile, alberi familiari (auth OAuth2) | Gratuito (con account istituzionale) | ~3.000 query | 0 |
| Ancestry API | Ricerca anagrafica estesa, record militari, alberi privati | $0.02/query (API partner) | ~2.000 query | ~€40 |
| MyHeritage API | Ricerca record italiani, matching DNA opzionale | $0.03/query | ~1.000 query | ~€30 |
| TrovaParenti/Archivi.it | Ricerca anagrafica italiana, stato civile localizzato | €0.05/query | ~500 query | ~€25 |
| | | | **Subtotale genealogia** | **€95** |

> WikiTree e FamilySearch sono gratuiti ma richiedono sviluppo di adapter API e gestione autenticazione. Ancestry e MyHeritage hanno costi per query ma offrono copertura piu' ampia (alberi privati, record military, DNA matching). Il volume stimato si basa su ~500 soldati target per recapito corrispondenza × 5-10 query genealogiche per soldato.

### 2.5 Servizio recapito corrispondenza storica

Costi operativi per il recapito fisico di lettere, cartoline e documenti mai consegnati alle famiglie durante il conflitto, una volta rintracciati i discendenti.

| Voce | Descrizione | Qta | Costo unitario | Costo (€) |
|---|---|---|---|---:|
| Raccomandata internazionale | Spedizione tracciata per recapito oltreoceano | 50 | 15 | 750 |
| Raccomandata nazionale | Spedizione tracciata in Italia | 100 | 8 | 800 |
| Buste archivistiche | Buste acid-free per documenti originali | 200 | 0,50 | 100 |
| Stampa digitale | Riproduzione fotografica documenti per archivio | 200 | 1,50 | 300 |
| | | | **Subtotale recapito** | **€1.950** |

> Stima su 150 recapiti (100 nazionali + 50 internazionali) con materiali archivistici adeguati. I documenti originali vengono maneggiati con cura (buste acid-free, riproduzione digitale per conservazione). Il servizio e' gratuito per le famiglie destinatarie.

### Riepilogo API

| Provider/Categoria | Costo/anno (€) | Uso |
|---|---:|---|
| OpenAI | 600 | Parsing + ricerca AI + image OCR |
| Mistral | 400 | OCR documenti + ricerca AI |
| Perplexity | 300 | Fallback web-enriched |
| API genealogiche (Ancestry+MyHeritage+Archivi.it) | 95 | Ricerca antenati/discendenti |
| Recapito corrispondenza storica | 1.950 | Spedizioni + materiali archivistici |
| WikiTree + FamilySearch | 0 | Gratuiti (API pubbliche) |
| **TOTALE API + GENEALOGIA** | **3.345** | |

> Tutti i costi API AI sono tracciati in tempo reale dalla tabella `api_usage` con `cost_usd` per ogni chiamata. Il sistema ha un budget guard ($50/mese default) che blocca automaticamente le chiamate se superato. I costi genealogici e di recapito sono gestiti come spese dirette di progetto.

---

## 3. Infrastruttura — €1.240

### 3.1 Server cloud (backend production)

| Voce | Descrizione | Costo/mese | Mesi | Totale (€) |
|---|---|---:|---|---:|
| VPS production | Hetzner Cloud CX51: 16 vCPU, 32GB RAM, 320GB SSD NVMe | 30 | 12 | 360 |

**Specifica tecnica**:
- **Provider**: Hetzner Cloud
- **Datacenter**: Falkenstein, Germania (UE)
- **Conformita'**: GDPR compliant, data residency UE
- **Stack**: Python FastAPI + SQLite WAL + Nginx + Let's Encrypt
- **Backup**: snapshot giornaliero automatico Hetzner + backup S3
- **Servizi ospitati**: API REST, dashboard web, DB SQLite (907 MB), federation layer, cache fonti

> Hetzner scelta per rapporto qualita'/prezzo e datacenter in UE (GDPR compliant).

### 3.2 Server locale (AI processing)

| Voce | Descrizione | Costo | Totale (€) |
|---|---|---:|---:|
| Mini PC | Beelink SER5 Pro: AMD Ryzen 7 5800H, 32GB RAM, 500GB NVMe | 800 | 800 |

**Specifica tecnica**:
- **Hardware**: Mini PC AMD Ryzen 7, 32GB RAM, 500GB NVMe SSD
- **Location**: domicilio proponente (Italia)
- **Uso**: OCR locale (Mistral Pixtral), scraping dati, processing batch, linker cross-dataset
- **Consumo**: TDP 35W idle, ~100W under load

> Il server locale esegue i job pesanti (scraping, OCR, linker) che non richiedono latenza bassa. I risultati vengono sincronizzati al server cloud. Riduce i costi API cloud (OCR locale vs cloud).

### 3.3 Dominio e servizi web

| Voce | Descrizione | Costo/anno | Totale (€) |
|---|---|---:|---:|
| Dominio | Registrazione .it o .org (es. memoriafederata.it) | 20 | 20 |
| SSL | Let's Encrypt (gratuito) | 0 | 0 |
| Backup storage | S3-compatible object storage (Backblaze B2, 50GB) | 5/mese x 12 | 60 |

### Riepilogo infrastruttura

| Voce | Totale (€) |
|---|---:|
| Server cloud (12 mesi) | 360 |
| Server locale (hardware one-time) | 800 |
| Dominio | 20 |
| Backup storage | 60 |
| **TOTALE** | **1.240** |

---

## 4. Costi energetici — €300

### Server locale 24/7 (12 mesi)

| Parametro | Valore |
|---|---|
| Consumo medio server locale | 100 W (0,1 kW) |
| Ore funzionamento/anno | 24h x 365g = 8.760 h |
| Consumo annuo | 876 kWh |
| Tariffa elettrica Italia (PEA + trasporto + imposte) | ~€0,28/kWh |
| Costo elettricita' server | 876 x €0,28 = €245 |
| Overhead cooling/ventilazione (~20%) | €49 |
| Router/switch di rete (10W x 24h x 365) | 88 kWh x €0,28 = €25 |
| **Totale energetico** | **~€300** |

> Il server locale e' ottimizzato: mini PC con CPU AMD a basso consumo (TDP 35W in idle). Consumo reale inferiore a un desktop tradizionale. Calcolo prudente.

---

## 5. Trasferte e sopralluoghi — €1.000

| Voce | Descrizione | Qta | Costo unitario | Totale (€) |
|---|---|---|---|---:|
| 5.1 | Visite Archivi di Stato (Roma, Bolzano, Trento) | 4 | 150 | 600 |
| 5.2 | Visite musei storici (Rovereto, Bologna, Reggio Emilia) | 3 | 100 | 300 |
| 5.3 | Eventi/conferenze patrimonio Grande Guerra | 1 | 100 | 100 |
| | **TOTALE** | | | **1.000** |

> Include trasporto (treno/auto), eventuali pernottamenti, accessi ad archivi e musei.

---

## 6. Comunicazione e diffusione — €800

| Voce | Descrizione | Costo (€) |
|---|---|---:|
| 6.1 | Sito web progetto (landing page, hosting incluso nel VPS) | 0 |
| 6.2 | Materiali divulgativi (brochure, poster per conferenze) | 300 |
| 6.3 | Social media management (12 mesi, strumenti e ads minimi) | 200 |
| 6.4 | 1 evento di presentazione pubblica (location, materiali) | 300 |
| | **TOTALE** | **800** |

---

## 7. Rendicontazione e admin — €300

| Voce | Descrizione | Costo (€) |
|---|---|---:|
| 7.1 | Report finale di progetto (stampa, rilegatura) | 100 |
| 7.2 | Documentazione tecnica (OpenAPI, manuale utente) | 100 |
| 7.3 | Spese amministrative (posta certificata, comunicazioni) | 100 |
| | **TOTALE** | **300** |

---

## 8. Tasse e oneri — €600

| Voce | Descrizione | Costo (€) |
|---|---|---:|
| 8.1 | IVA 22% su acquisti di beni e servizi (server locale, materiali) | ~€200 |
| 8.2 | IVA 22% su costi API esteri (reverse charge / assimilata) | ~€150 |
| 8.3 | Marca da bollo €16 per dichiarazione sostitutiva | 16 |
| 8.4 | Imposte di bollo su documenti rendicontazione | 50 |
| 8.5 | Eventuali contributi INPS/INAIL su collaborazioni (10% co.co.co.) | ~€184 |
| | **TOTALE** | **~€600** |

> Nota: i contributi MiC non sono soggetti a IVA come corrispettivo, ma gli acquisti effettuati con il contributo sono soggetti a IVA dove applicabile. Le collaborazioni occasionali sono soggette a ritenuta d'acconto del 20% (a credito del collaboratore). Stima prudente.

---

## 9. Contingenza — €1.915

Margine ~5% per imprevisti: aumento costi API, sostituzione hardware, trasferte aggiuntive, spedizioni aggiuntive per recapito corrispondenza, costi di segreteria non previsti.

---

## Riepilogo finale

| # | Categoria | Importo (€) | % |
|---|---|---:|---:|
| 1 | Personale (sviluppatore + operatore + ricercatore) | 27.500 | 74,3% |
| 2 | API AI + genealogiche + recapito corrispondenza | 3.345 | 9,0% |
| 3 | Infrastruttura (cloud + locale + dominio + backup) | 1.240 | 3,4% |
| 4 | Costi energetici (server locale 24/7) | 300 | 0,8% |
| 5 | Trasferte e sopralluoghi | 1.000 | 2,7% |
| 6 | Comunicazione e diffusione | 800 | 2,2% |
| 7 | Rendicontazione e admin | 300 | 0,8% |
| 8 | Tasse e oneri | 600 | 1,6% |
| 9 | Contingenza (~5%) | 1.915 | 5,2% |
| | **TOTALE RICHIESTO** | **€37.000** | **100%** |

---

## Cofinanziamento e risorse proprie

| Fonte | Descrizione | Valore stimato (€) |
|---|---|---:|
| Lavoro volontario pregresso | Sviluppo piattaforma, acquisizione 3,5M record, OCR, federation layer | 50.000 |
| Hardware esistente | Workstation sviluppo, monitor, rete | 2.000 |
| Software esistente | Codice Python (~15 moduli), DB schema, UI | 30.000 |
| Dati gia' acquisiti | 11 fonti, 3,5M record, 455k entita', 2M collegamenti | Non monetizzabile |
| **Cofinanziamento totale** | | **€82.000** |

---

## Piano di spesa trimestrale

| Trimestre | Periodo | Personale | API | Infra | Energia | Altro | Totale (€) |
|---|---|---:|---:|---:|---:|---:|---:|
| T1 | Ott — Dic 2026 | 7.000 | 836 | 1.180 | 75 | 700 | 10.591 |
| T2 | Gen — Mar 2027 | 7.000 | 836 | 60 | 75 | 700 | 9.471 |
| T3 | Apr — Giu 2027 | 7.000 | 836 | 0 | 75 | 700 | 9.411 |
| T4 | Lug — Set 2027 | 6.500 | 837 | 0 | 75 | 1.600 | 9.812 |
| | **TOTALE** | **27.500** | **3.345** | **1.240** | **300** | **3.700** | **37.085** |

> T1 include acquisto server locale (€800) e setup cloud. T4 include rendicontazione finale + contingenza residua.

---

## Location server e data residency

| Componente | Location | Provider | Conformita' |
|---|---|---|---|
| Server cloud (production) | Falkenstein, Germania (UE) | Hetzner Cloud | GDPR compliant, data residency UE |
| Server locale (AI processing) | Italia (domicilio proponente) | Hardware proprio | Dati non trasferiti fuori UE |
| Backup object storage | Europa (region EU-Central) | Backblaze B2 | GDPR compliant |
| Database SQLite | Replicato cloud + locale | — | Nessun dato personale sensibile |

> Tutti i dati sono relativi a persone decedute (caduti/internati della Prima Guerra Mondiale, 1915-1918). Nessun dato personale di persone viventi. Conformita' GDPR semplificata (art. 5 - dati storici).

---

## Riepilogo per tipologia di intervento (bando L. 78/2001)

| Tipologia | Descrizione | Importo (€) | % |
|---|---|---:|---:|
| A — Censimento | Ricognizione e acquisizione fondi archivistici | 10.500 | 28% |
| B — Catalogazione | Normalizzazione, cross-linking, QA, inserimento dati | 11.500 | 31% |
| E — Valorizzazione | Piattaforma digitale, API, mappa, server, genealogia, recapito corrispondenza | 11.500 | 31% |
| Trasversale | Diffusione, rendicontazione, tasse, contingenza | 3.500 | 10% |
| **TOTALE** | | **€37.000** | **100%** |

---

## Note metodologiche

- I costi API sono stimati prudentemente includendo buffer per picchi di traffico e nuove funzionalita'. Il Memory Router riduce il consumo AI del ~90%.
- I costi del personale sono calcolati su tariffe congrue per il mercato italiano (sviluppatore €250/gg, ricercatore €150/gg, operatore €20/h).
- Il server locale e' un mini PC a basso consumo (AMD Ryzen, TDP 35W idle) — i costi energetici sono inferiori a un desktop tradizionale.
- Il server cloud e' in datacenter UE (Germania) per conformita' GDPR.
- Il budget e' realistico: €37.000 su un bando con budget storico di ~€400-500k per 17 progetti (media ~€29k, range €10-50k).
- Il cofinanziamento (€82.000) dimostra l'impegno sostanziale gia' investito nel progetto.
- I costi genealogici e di recapito corrispondenza (~€2.045) sono unici e innovativi: nessun bando precedente ha previsto il recapito fisico di documenti storici alle famiglie dei soldati.
