# Cronoprogramma — Allegato B

> Trascrivere questi dati nel template Excel ufficiale:
> https://grandeguerra.cultura.gov.it/wp-content/uploads/2026/06/ALLEGATO-B-Cronoprogramma.xlsx

---

## Dati generali

| Campo | Valore |
|---|---|
| Titolo progetto | VOCI DAL FRONTE — Piattaforma federata per la memoria e la ricostruzione delle storie familiari della Grande Guerra |
| Soggetto proponente | [DA COMPILARE] |
| Durata | 12 mesi (Ottobre 2026 — Settembre 2027) |
| Budget richiesto | €37.000 |

## Fasi e attività

| # | Fase | Attività | Inizio | Fine | Costo (€) |
|---|---|---|---|---|---|
| 1 | Fase 1 — Censimento | Identificazione e contatto di Archivi di Stato, musei, istituzioni con fondi GG non digitalizzati | Ott 2026 | Nov 2026 | 3.000 |
| 2 | Fase 1 — Censimento | Censimento fondi regionali e locali (diocesani, comunali, associazioni) | Nov 2026 | Dic 2026 | 2.000 |
| 3 | Fase 1 — Censimento | Acquisizione metadati da fonti accessibili (CWGC completamento, Antenati, Europeana) | Dic 2026 | Gen 2027 | 3.000 |
| 4 | Fase 1 — Censimento | Censimento fotografico (Gabinetto Fotografico Nazionale, archivi locali) | Gen 2027 | Gen 2027 | 1.000 |
| 5 | Fase 2 — Catalogazione | Normalizzazione entità ed estensione linker cross-dataset | Feb 2027 | Mar 2027 | 4.000 |
| 6 | Fase 2 — Catalogazione | Catalogazione con metadati strutturati, deduplicazione, inserimento dati manuale via UI | Mar 2027 | Apr 2027 | 4.500 |
| 7 | Fase 2 — Catalogazione | Cross-linking semantico e indicizzazione FTS5/BM25 | Apr 2027 | Mag 2027 | 2.000 |
| 8 | Fase 2 — Catalogazione | Quality assurance: verifica omonimie, dati contraddittori | Mag 2027 | Mag 2027 | 1.000 |
| 9 | Fase 3 — Valorizzazione | Sviluppo piattaforma: backend API REST, federation, memory router, AI integration | Giu 2027 | Ago 2027 | 8.750 |
| 10 | Fase 3 — Valorizzazione | Sviluppo frontend: dashboard, mappa geospaziale, responsive | Giu 2027 | Ago 2027 | 6.250 |
| 11 | Fase 3 — Valorizzazione | Testing, documentazione OpenAPI, lancio beta pubblica | Set 2027 | Set 2027 | 2.000 |
| 12 | Infrastruttura | Server cloud (Hetzner, 12 mesi) + server locale + dominio + backup | Ott 2026 | Set 2027 | 1.240 |
| 13 | API commerciali + genealogiche | OpenAI + Mistral + Perplexity + Ancestry + MyHeritage + Archivi.it + WikiTree + FamilySearch | Ott 2026 | Set 2027 | 1.395 |
| 14 | Recapito corrispondenza storica | Spedizioni raccomandate + buste archivistiche + stampa digitale (150 recapiti) | Gen 2027 | Set 2027 | 1.950 |
| 15 | Costi energetici | Elettricità server locale 24/7 | Ott 2026 | Set 2027 | 300 |
| 15 | Trasversale | Diffusione, comunicazione, eventi | Ott 2026 | Set 2027 | 800 |
| 16 | Trasversale | Rendicontazione, report finale, documentazione | Set 2027 | Set 2027 | 300 |
| 17 | Tasse e oneri | IVA, bolli, contributi | Ott 2026 | Set 2027 | 600 |
| 18 | Contingenza | Margine 5% imprevisti | — | Set 2027 | 1.915 |
| | | **TOTALE** | | | **€37.000** |

## Milestone

| Data | Milestone | Deliverable |
|---|---|---|
| 31 Dic 2026 | M1 — Censimento completato | Catalogo di 50+ fondi archivistici censiti, 1M+ nuovi record acquisiti |
| 31 Mag 2027 | M2 — Catalogazione completata | 1M+ entità normalizzate, 5M+ collegamenti grafo, quality report |
| 30 Set 2027 | M3 — Piattaforma pubblica | Dashboard investigativa live, API pubbliche, mappa geospaziale, report finale |

## Risorse umane

| Ruolo | Impegno (mesi) | Costo (€) |
|---|---|---|
| Sviluppatore AI/backend (80 gg) | 12 | 20.000 |
| Operatore inserimento dati (150 ore) | 6 | 3.000 |
| Ricercatore storico (30 gg) | 8 | 4.500 |
| API commerciali (OpenAI+Mistral+Perplexity) | 12 | 1.300 |
| API genealogiche (Ancestry+MyHeritage+Archivi.it) | 12 | 95 |
| Recapito corrispondenza storica (spedizioni+materiali) | — | 1.950 |
| Server cloud (Hetzner) | 12 | 360 |
| Server locale (hardware one-time) | 1 | 800 |
| Dominio + backup storage | 12 | 80 |
| Costi energetici | 12 | 300 |
| Trasferte e sopralluoghi | — | 1.000 |
| Comunicazione e diffusione | 12 | 800 |
| Rendicontazione e admin | 1 | 300 |
| Tasse e oneri | — | 600 |
| Contingenza (~5%) | — | 1.915 |
| **TOTALE** | | **€37.000** |

## Note

- Il cronoprogramma rispetta la scadenza del bando: tutti i progetti devono concludersi entro il 30 Settembre 2027
- Le attivita' sono sequenziali nelle fasi 1-2-3 ma la diffusione (attivita' 11) e' trasversale
- Il budget e' ripartito tra le 3 tipologie: A (censimento) ~€10.500, B (catalogazione) ~€11.500, E (valorizzazione + genealogia + recapito) ~€11.500, trasversale ~€3.500
