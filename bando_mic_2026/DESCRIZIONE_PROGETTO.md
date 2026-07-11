# Descrizione del Progetto — Form di Candidatura Online

> Questo testo va trascritto nei campi del form online sul portale
> https://grandeguerra.cultura.gov.it/presenta-la-tua-domanda/

---

## Titolo del progetto

VOCI DAL FRONTE — Piattaforma federata per la memoria e la ricostruzione delle storie familiari della Grande Guerra

## Tipologie di interento (art. 1, c. 2 L. 78/2001)

- **A — Ricognizione e censimento**
- **B — Catalogazione**
- **E — Valorizzazione**

## Soggetto proponente

> Compilare con i propri dati anagrafici nel form

- **Nome/Cognome o Ente**: [DA COMPILARE]
- **Codice Fiscale**: [DA COMPILARE]
- **Email**: [DA COMPILARE]
- **Telefono**: [DA COMPILARE]
- **Indirizzo**: [DA COMPILARE]

## Descrizione del progetto

### Contesto e problematica

Il patrimonio documentale relativo alla Prima Guerra Mondiale è custodito in numerose istituzioni archivistiche italiane (Archivi di Stato, Ufficio Storico SME, musei storici, associazioni) e internazionali (NARA, CWGC, Archivi di Stato europei), ciascuna con interfacce, formati e linguaggi di catalogazione diversi. Questa frammentazione rende estremamente difficile la ricerca cross-fonte: per ricostruire il percorso di un singolo soldato — dal momento di arruolamento, al reparto di assegnazione, agli eventi bellici, fino all'eventuale decorazione o caduta — è necessario consultare manualmente più archivi, spesso con sistemi di ricerca non interoperabili.

Ad oggi, nessuna piattaforma esistente federà in un unico sistema i dati dell'Albo d'Oro dei Caduti (342.555 record), i Caduti del Ministero della Difesa (162.646 record), i Caduti Sardi (20.435 record), i Caduti Bolognesi (9.656 record), i Decorati al Valor Militare (279.832 record del Nastro Azzurro + 1.286 dell'ISTORECO), i Caduti Francesi (24.279 record da Mémoire des Hommes) e i Caduti del Commonwealth (446.443 record dal CWGC), collegandoli tramite un grafo semantico di entità normalizzate.

### Obiettivi del progetto

Il progetto VOCI DAL FRONTE intende:

1. **Censire** (Tipologia A) i fondi archivistici digitali relativi alla Prima Guerra Mondiale attualmente dispersi tra molteplici istituzioni, creando un catalogo unificato di metadati conforme a standard archivistici;

2. **Catalogare** (Tipologia B) i record di 11+ fonti archivistiche in un database relazionale con entità normalizzate (persone, luoghi, eventi, unità militari) e collegamenti cross-dataset, applicando standard di catalogazione coerenti e deduplicazione automatica;

3. **Valorizzare** (Tipologia E) il patrimonio censito e catalogato attraverso una piattaforma digitale di ricerca pubblica e gratuita, dotata di ricerca full-text (BM25), navigazione grafo, dashboard investigativa per singolo soldato, e federazione di 20+ provider archivistici internazionali con accesso on-demand ai documenti originali;
4. **Riconnettere le famiglie** (Tipologia E — valorizzazione sociale) integrando piattaforme genealogiche pubbliche e collaborative (WikiTree, FamilySearch, Antenati) per tracciare discendenti di soldati, dispersi, caduti e reduci della Grande Guerra, al fine di recapitare documenti, lettere e corrispondenza mai consegnata alle famiglie durante il conflitto.

### Stato di avanzamento pregresso

Il progetto ha già raggiunto una base operativa significativa, interamente sviluppata con risorse proprie:

- **~3,5 milioni di record** integrati da 11 fonti archivistiche
- **455.295 entità** normalizzate (persone, luoghi, eventi)
- **2.026.064 collegamenti** cross-dataset nel grafo semantico
- **1.153 documenti** originali OCR da microfilm NARA T-315
- **20 provider archivistici** federati (NARA, Antenati, CWGC, Europeana, Internet Archive, Gallica/BNF, TNA, WikiTree, ecc.)
- **Architettura a 6 livelli** funzionante: tabelle sorgente, grafo semantico, archivio documenti, sistema di routing intelligente delle query, indicizzatore di fonti esterne, operativo
- **Dashboard investigativa** con ricerca conversazionale, timeline, fonti locali/esterne, entità collegate
- **Sistema di indicizzazione automatica** che crea schede di ricerca per soldati non presenti in DB, arricchendole con metadati da fonti esterne federate
- **Integrazione WikiTree API** (20° provider) per ricerca genealogica: collegamento tra soldati nel DB e profili genealogici pubblici, con scoring di confidenza e match per cognome/nome/date/luogo
- **Sistema di recapito corrispondenza storica**: identificazione di discendenti viventi tramite catene genealogiche (soldato → genitori → fratelli → discendenti) per la restituzione di lettere, documenti e effetti personali mai consegnati alle famiglie durante la Grande Guerra

### Attività previste con il contributo

Il contributo richiesto finanzierà le seguenti attività nel periodo Ottobre 2026 — Settembre 2027:

#### Fase 1 — Censimento e acquisizione (Ottobre 2026 — Gennaio 2027)

- **Censimento di fondi archivistici non ancora digitalizzati**: identificazione e contatto di Archivi di Stato, musei storici, istituzioni culturali che custodiscono fondi della Grande Guerra non ancora accessibili online
- **Estensione del censimento a fondi regionali e locali**: diocesani, comunali, associazioni combattentistiche
- **Acquisizione metadati** (non documenti pesanti) da fonti accessibili via API o scraping: completamento CWGC (target 1,76M record), espansione Antenati (registri di stato civile), Europeana (documenti militari italiani)
- **Censimento fotografico**: identificazione e catalogazione di fondi fotografici della Grande Guerra (Gabinetto Fotografico Nazionale, archivi locali)

#### Fase 2 — Catalogazione strutturata (Febbraio 2027 — Maggio 2027)

- **Normalizzazione entità**: estensione del linker cross-dataset a tutti i nuovi fondi censiti, con deduplicazione automatica e validazione manuale
- **Catalogazione con metadati strutturati**: applicazione di schema di metadati coerente a tutti i record (cognome, nome, data/luogo nascita, grado, reparto, data/luogo eventi, decorazioni, fonte)
- **Cross-linking semantico**: collegamento automatico dello stesso soldato tra dataset diversi (es. caduto nell'Albo d'Oro → decorato nel Nastro Azzurro → menzionato in fondo archivistico)
- **Indicizzazione full-text**: estensione dell'indice FTS5/BM25 a tutti i nuovi record
- **Quality assurance**: verifica di record ambigui, omonimie, dati contraddittori tra fonti

#### Fase 3 — Valorizzazione e piattaforma (Giugno 2027 — Settembre 2027)

- **Piattaforma digitale pubblica gratuita**: dashboard investigativa con ricerca conversazionale, timeline soldato, fonti locali/esterne, entità collegate
- **Federazione archivistica**: 20+ provider con scoring unificato, accesso on-demand ai documenti originali da domini autorizzati
- **Indicizzazione automatica delle ricerche**: ogni ricerca senza risultato locale crea automaticamente una scheda minima e la arricchisce con metadati da fonti esterne — nessuna ricerca va persa
- **Mappa geospaziale**: visualizzazione su mappa dei luoghi di nascita, arruolamento, eventi bellici, sepoltura
- **API pubbliche**: endpoint REST per ricerca, dashboard soldato, federazione — documentazione OpenAPI
- **Accessibilità**: interfaccia responsive, accessibile, multilingue (IT/EN)
- **Integrazione piattaforme genealogiche pubbliche e collaborative**: WikiTree (API pubblica), FamilySearch (API pubblica con auth), Antenati/ICAR (portale MiC), per arricchimento anagrafico e tracciamento discendenti
- **Servizio di recapito corrispondenza storica**: cross-match tra soldati, dispersi, caduti e reduci e alberi genealogici per identificare discendenti viventi a cui recapitare lettere, cartoline e documenti mai consegnati alle famiglie — un ponte tra memoria archivistica e memoria familiare

### Innovatività

1. **Uno dei primi progetti in Europa**: fra le prime piattaforme in Europa a federare in un unico grafo semantico i dati dell'Albo d'Oro, del Ministero della Difesa, dei decorati, dei caduti regionali e internazionali
2. **Grafo cross-dataset**: 455.295 entità collegate da 2.026.064 relazioni — per la prima volta in Italia è possibile trovare lo stesso soldato in fonti diverse con una sola query
3. **Intelligenza artificiale etica ed efficiente**: un sistema di routing intelligente instrada le query prima localmente (ricerca testuale, grafo semantico, archivio documenti), ricorrendo ai servizi AI cloud solo come ultimo fallback — riducendo i costi del ~90%
4. **Indicizzazione automatica delle ricerche**: nessuna ricerca persa, ogni query genera memoria strutturata verificabile e migliorabile
5. **Open source e gratuito**: tutti i dati provengono da fonti pubbliche, la piattaforma è gratuita per ricercatori, storici, familiari
6. **Primo progetto in Europa per il recapito di corrispondenza storica ai discendenti**: integrazione con piattaforme genealogiche pubbliche e collaborative (WikiTree, FamilySearch, Antenati) per tracciare discendenti viventi di soldati, dispersi, caduti e reduci, con l'obiettivo di recapitare corrispondenza e documenti mai consegnati alle famiglie durante il conflitto — nessun altro progetto europeo ha mai attivato un ponte operativo tra archivio storico e memoria familiare attiva con consegna fisica di documenti originali
7. **Federazione multi-tipo**: non solo archivi statali, ma anche piattaforme genealogiche pubbliche e collaborative, archivi di stato civile (Antenati/ICAR), memoriali internazionali (CWGC, Mémoire des Hommes) e archivi digitali (Internet Archive, Europeana, Gallica) in un unico sistema

### Risultati attesi

| Metrica | Valore atteso a fine progetto |
|---|---|
| Record integrati | 5.000.000+ (da 3,5M attuali) |
| Fonti federate | 30+ provider (da 20 attuali) |
| Entità collegate | 1.000.000+ (da 455k attuali) |
| Collegamenti grafo | 5.000.000+ (da 2M attuali) |
| Fondi archivistici censiti | 50+ (nuovi fondi regionali/locali) |
| Utenti target anno 1 | 100.000+ |
| Costo AI per query | ~€0,001 (vs €0,10 senza routing intelligente) |
| Discendenti rintracciati | 500+ (lettere/documenti recapitati) |
| Piattaforme genealogiche integrate | 4 (WikiTree, FamilySearch, Antenati, Ancestry) |

### Conformità ai requisiti del bando

- **L. 78/2001, art. 1 c. 2**: il progetto rientra nelle tipologie A (ricognizione e censimento), B (catalogazione) ed E (valorizzazione) del patrimonio storico della Prima Guerra Mondiale
- **L. 78/2001, art. 4 c. 2**: il progetto si rivolge al Comitato tecnico-scientifico speciale per la tutela del patrimonio storico della Prima Guerra Mondiale
- **DM 4 ottobre 2002**: le attività di censimento, catalogazione e valorizzazione sono conformi alle tipologie di intervento previste
- **Fruibilità pubblica**: la piattaforma è gratuita e accessibile a tutti
- **Standard archivistici**: metadati strutturati, deduplicazione, cross-linking, conformità a standard di catalogazione

### Sostenibilità post-progetto

1. **Modello gratuito**: la piattaforma resta gratuita per utenti finali
2. **API pubbliche**: endpoint REST documentati per integrazione da parte di istituzioni
3. **Crowdsourcing**: utenti possono contribuire correzioni e arricchimenti (verificati)
4. **Partnership istituzionali**: accordi con Archivi di Stato, Musei, Ministero Difesa
5. **Grant successivi**: Creative Europe, Horizon Europe Cluster 2 per espansione transnazionale

### Chiusura

Il progetto mira non solo alla conservazione digitale del patrimonio documentale, ma anche alla restituzione della memoria alle comunità e alle famiglie, favorendo nuove forme di partecipazione civica, ricerca genealogica e trasmissione intergenerazionale della storia della Grande Guerra.

## Allegati da caricare nel form

1. Allegato A — Dichiarazione sostitutiva (firmata)
2. Allegato B — Cronoprogramma (Excel compilato)
3. Screenshot della piattaforma (dashboard investigativa, ricerca, grafo entità)
4. Esempio di scheda soldato con fonti federate
