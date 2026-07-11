# Presentazione Progetto — VOCI DAL FRONTE

> Slide deck di supporto per incontri con il Comitato, partner istituzionali, o presentazioni pubbliche.
> **Non richiesta dal bando** ma utile come supporto.

---

## Slide 1 — Titolo

**VOCI DAL FRONTE**
Piattaforma federata per la memoria e la ricostruzione delle storie familiari della Grande Guerra

Bando MiC Grande Guerra 2026/2027
Tipologie: A (censimento) + B (catalogazione) + E (valorizzazione)

---

## Slide 2 — Il problema

**I dati della Grande Guerra sono frammentati**

- 342.555 caduti nell'Albo d'Oro (cadutigrandeguerra.it)
- 162.646 caduti nel Ministero della Difesa (onorcaduti.difesa.it)
- 279.832 decorati (Nastro Azzurro)
- 20.464 internati militari (Archivio di Stato Bolzano)
- 446.443 caduti Commonwealth (CWGC)
- 24.279 caduti francesi (Memoire des Hommes)
- 1.153 documenti OCR (NARA T-315)

**Nessun sistema esistente li collega tra loro.**

Per ricostruire il percorso di un soldato bisogna consultare manualmente 5-10 archivi diversi, con interfacce, formati e lingue diverse.

---

## Slide 3 — La soluzione

**MEMORIA FEDERATA** — un'unica piattaforma che:

1. **Censisce** (Tipologia A) fondi archivistici non digitalizzati
2. **Cataloga** (Tipologia B) 3,5M+ record con entita' normalizzate e grafo cross-dataset
3. **Valorizza** (Tipologia E) con piattaforma digitale pubblica e gratuita

---

## Slide 4 — Architettura a 6 livelli

```
LIVELLO 1 — SORGENTI: 11 tabelle, 3,5M record da fonti primarie
LIVELLO 2 — SEMANTICO: 455k entita', 2M collegamenti, FTS5/BM25
LIVELLO 3 — ARCHIVISTICO: 1.153 documenti OCR, SHA256, metadati militari
LIVELLO 4 — IPPOCAMPALE: Memory Router, routing AI-efficient, memoria episodica
LIVELLO 5 — SOURCE LOCATOR: 20 provider federati, fetch on-demand
LIVELLO 6 — OPERATIVO: tracking, log AI, usage
```

---

## Slide 5 — Numeri attuali

| Metrica | Valore |
|---|---:|
| Record integrati | 3.500.000 |
| Fonti archivistiche | 11 |
| Provider federati | 20 |
| Entita' normalizzate | 455.295 |
| Collegamenti grafo | 2.026.064 |
| Documenti OCR | 1.153 |
| Indici FTS5 | 455.295 |
| Dimensione DB | 907 MB |

---

## Slide 6 — Innovazione 1: Grafo Semantico Cross-Dataset

Per la prima volta, lo stesso soldato e' collegato tra:
- Albo d'Oro (caduto)
- Ministero Difesa (caduto)
- Nastro Azzurro (decorato)
- Archivio di Stato Bolzano (internato)
- CWGC (caduto Commonwealth)
- Fondi archivistici (menzionato)

**455.295 entita' collegate da 2.026.064 relazioni**

Esempio: "Rossi Mario" → trovato in 3 fonti diverse con una sola query

---

## Slide 7 — Innovazione 2: Source Federation Layer

20 provider archivistici integrati:
- **API reali**: NARA, Antenati, CWGC, Internet Archive, Europeana, Gallica/BNF, TNA, Google Books, HathiTrust, WikiTree
- **Stub da implementare**: Arolsen, Bundesarchiv, SHD/MDH, ABMC, LAC, AWM, Archivportal-D, Internet Culturale, USSME

**Principio**: il DB e' un indice intelligente (~50MB metadati), non un repository (~TB documenti). Fetch on-demand solo da domini autorizzati.

---

## Slide 8 — Innovazione 3: Routing Intelligente (AI etica)

Routing gerarchico delle query:
1. Ricerca esatta locale (sub-ms)
2. Ricerca full-text (sub-ms)
3. Grafo entita' (< 10ms)
4. Archivio documenti OCR
5. Fonti esterne federate
6. Cloud AI (solo se 0 risultati locali)

**Risultato**: costi AI ridotti del ~90%, risposte piu' veloci, nessun download non necessario.

---

## Slide 9 — Innovazione 4: Indicizzazione Automatica delle Ricerche

Ogni query senza risultato locale:
1. Crea automaticamente una scheda minima
2. Interroga 20 provider esterni
3. Indicizza fonti trovate con scoring e classificazione rilevanza
4. Identifica dati mancanti
5. Aggiorna confidence in base alle fonti

**Nessuna ricerca va persa.** Ogni fallimento genera nuova memoria strutturata.

Test su 50 soldati: 437 fonti indicizzate, 50 soggetti creati, 1.174 link, 200 gap identificati.

---

## Slide 10 — Cosa faremo con il contributo

### Fase 1 — Censimento (Ott 2026 — Gen 2027) — €9.000
- Censimento 50+ fondi archivistici non digitalizzati
- Acquisizione 1M+ nuovi record da API pubbliche
- Censimento fotografico

### Fase 2 — Catalogazione (Feb — Mag 2027) — €10.000
- Normalizzazione 1M+ nuove entita'
- Cross-linking semantico
- Quality assurance

### Fase 3 — Valorizzazione (Giu — Set 2027) — €8.000
- Piattaforma digitale pubblica gratuita
- Mappa geospaziale
- API pubbliche (OpenAPI)
- Lancio beta

---

## Slide 11 — Budget

| Categoria | Importo |
|---|---:|
| Personale (sviluppatore AI + operatore + ricercatore) | €27.500 |
| API AI (OpenAI + Mistral + Perplexity) | €1.300 |
| API genealogiche (Ancestry + MyHeritage + Archivi.it) | €95 |
| Recapito corrispondenza storica (spedizioni + materiali) | €1.950 |
| Infrastruttura (cloud + locale + dominio + backup) | €1.240 |
| Costi energetici (server locale 24/7) | €300 |
| Trasferte e sopralluoghi | €1.000 |
| Comunicazione e diffusione | €800 |
| Rendicontazione e admin | €300 |
| Tasse e oneri | €600 |
| Contingenza (~5%) | €1.915 |
| **TOTALE richiesto** | **€37.000** |
| Cofinanziamento (lavoro pregresso) | €82.000+ |

**€37.000 su ~€400-500k di budget bando** — progetto contained, realistico, ad alto impatto

---

## Slide 12 — Risultati attesi

| Metrica | Oggi | Fine progetto |
|---|---:|---:|
| Record integrati | 3,5M | 5M+ |
| Provider federati | 20 | 30+ |
| Entita' collegate | 455k | 1M+ |
| Collegamenti grafo | 2M | 5M+ |
| Fondi censiti | 11 | 50+ |
| Utenti | 0 | 100k+ |
| Costo AI/query | €0,001 | €0,001 |

---

## Slide 13 — Competitor

**Uno dei primi progetti in Europa** a federare fonti militari italiane in un grafo semantico.

| Sistema | Cosa fa | Cosa non fa |
|---|---|---|
| Onorcaduti (Min. Difesa) | Caduti 1a GM | No dispersi, no decorati, no grafo |
| cadutigrandeguerra.it | Albo d'Oro | Solo Albo d'Oro, no cross-link |
| Archivio Stato Bolzano | Soldati | Solo fondo locale, no federazione |
| CWGC | Caduti Commonwealth | Solo Commonwealth |
| Europeana | Heritage EU | Generico, no specializzazione militare IT |
| Ancestry.com | Genealogia | Commerciale (~€300/anno), no grafo, no recapito corrispondenza |

---

## Slide 14 — Sostenibilita'

1. **Gratuito** per utenti finali (familiari, ricercatori, storici)
2. **API pubbliche** documentate (OpenAPI/Swagger)
3. **Open source** — dati da fonti pubbliche
4. **Crowdsourcing** — utenti contribuiscono correzioni verificate
5. **Partnership istituzionali** — Archivi di Stato, Musei, Ministero Difesa
6. **Grant successivi** — Creative Europe, Horizon Europe per espansione transnazionale

---

## Slide 15 — Contatti

**Proponente**: [NOME COGNOME]
**Email**: [EMAIL]
**Telefono**: [TELEFONO]
**Piattaforma**: [URL DEMO]

**Comitato Grande Guerra MiC**:
- comitatograndeguerra@cultura.gov.it
- mbac-comitatograndeguerra@mailcert.beniculturali.it
- Via di San Michele 22, 00153 Roma

---

## Suggerimenti per la presentazione

- **Se si usa in incontro con il Comitato**: portare screenshot della piattaforma funzionante (dashboard, ricerca, grafo)
- **Durata consigliata**: 10-15 minuti (15 slide × ~1 min)
- **Focus**: enfatizzare il grafo cross-dataset, la base operativa gia' esistente (3,5M record) e il **primo servizio in Europa di recapito corrispondenza storica ai discendenti**
- **Risposta a obiezioni**:
  - "E' solo digitale?" → Si, il bando prevede tipologia E (valorizzazione digitale), non restauro materiale
  - "I dati sono affidabili?" → Fonti pubbliche ufficiali, deduplicazione automatica, QA manuale
  - "Sara' mantenuto dopo?" → Modello gratuito + API + crowdsourcing + grant successivi
