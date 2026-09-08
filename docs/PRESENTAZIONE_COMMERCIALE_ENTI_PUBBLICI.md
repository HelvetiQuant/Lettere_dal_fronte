# PIATTAFORMA DI DIGITALIZZAZIONE E RICERCA STORICA DOCUMENTALE

## Presentazione Commerciale per Enti Pubblici

**Prodotto**: Voci dal Fronte — IMI Extractor | Versione 1.0 | Settembre 2026

---

## 1. IL PROBLEMA

Gli enti pubblici gestiscono patrimoni documentali storici con problemi strutturali:

- **Frammentazione**: documenti dispersi tra archivi fisici, database isolati, formati eterogenei
- **Indicizzazione manuale**: tempi lunghi, costi elevati, personale specializzato
- **Accesso limitato**: ricercatori e cittadini devono recarsi fisicamente presso gli archivi
- **Nessun collegamento automatico** tra persone, eventi, luoghi e documenti
- **Contaminazione tra conflitti**: dati WWI mescolati con WWII
- **Omonimie non gestite**: persone con lo stesso nome confuse
- **Nessuna tracciabilita delle fonti**: affermazioni senza citazioni verificabili

**Costo stimato modello attuale (ente medio): 250K-500K EUR/anno**

---

## 2. LA SOLUZIONE

**Voci dal Fronte** trasforma archivi cartacei e database isolati in un **archivio digitale unificato, ricercabile e interconnesso**.

Non si limita a digitalizzare: comprende semanticamente i documenti, li collega ad altre fonti, verifica l'identita delle persone, rileva contraddizioni, genera narrazioni con citazioni verificabili.

| Acquisizione | Indicizzazione | Ricerca |
|---|---|---|
| OCR multi-engine | Entity resolution | Pipeline evidenza 4 livelli |
| Federazione 27 provider | Graph provenance | Narrazione AI con citazioni |
| Compliance gate | Claim extraction | Viewpoints multi-fazione |
| Storage cloud | Cross-linking sicuro | Follow-up conversazionale |

---

## 3. ARCHITETTURA

### Stack
- **Backend**: Python 3.11, FastAPI, 163+ endpoint REST
- **DB locale**: SQLite 3 (WAL, 3 DB, ~2GB)
- **DB remoto**: Supabase PostgreSQL 15 (6 schemi: archive, evidence, ops, ai, api_public, public)
- **Frontend**: React 19, TypeScript 6, Vite 8, Leaflet (16 pagine)
- **AI**: OpenAI GPT-4o, Mistral Large, Anthropic Claude 3.5, Gemini 1.5, LM Studio (locale)
- **Auth**: bcrypt, RBAC (admin/operator/researcher/viewer)

### Pipeline V7 (9 stage)
`PLAN -> DISCOVER -> FETCH -> EXTRACT -> RESOLVE -> FUSE -> VALIDATE -> NARRATE -> PERSIST`
Idempotente, non distruttivo. L'AI non inventa: ogni output da una chiamata reale.

---

## 4. CONFORMITA E SICUREZZA

- **Compliance gate**: ogni operazione su fonti esterne valutata e loggata
- **RLS PostgreSQL**: accesso pubblico solo su documenti confermati
- **Reversibilita**: audit table con old/new value, revert completo o selettivo
- **Anti-allucinazione AI**: evidence-locked narrator, post-generation check, deterministic fallback
- **GDPR**: estrazione dati personali solo con autorizzazione, log completo

---

## 5. NUMERI DEL SISTEMA

### ~9,5 milioni di record gestiti

| Dataset | Record |
|---------|--------|
| Caduti CWGC | 506K |
| Caduti Albo d'Oro | 343K |
| Decorati Nastro Azzurro | 280K |
| Caduti Ministero Difesa | 163K |
| LeBI (ANRP) | 166K |
| Internati Militari Italiani | 20K |
| Event links | 1,5M |
| Graph edges | 1,5M |

### 27 provider federati internazionali
USSME, Archivio di Stato, Antenati/SAN, NARA, CWGC, Europeana, Internet Archive, Gallica/BnF, Bundesarchiv, Arolsen, ICRC, LeBI, e altri 15

### 285+ test (100% PASS)
160 test V7.3 + 82 test V4 + 43 test person-fix

---

## 6. CASI D'USO

**Archivio di Stato**: 50K documenti cartacei -> OCR -> entity resolution -> cross-link con Albo d'Oro/CWGC/decorati -> API pubblica

**USSME**: 49 pub. storiche -> import metadati -> link 49 eventi WW1 -> viewpoints multi-fazione (467 fonti IT, 28 DE, 3 AT per Caporetto)

**Comune**: elenchi cartacei caduti -> OCR -> cross-link LeBI/caduti_ministero -> dossier con biografia AI -> mappe interattive

**Ministero Difesa**: 280K decorati -> import -> cross-link 5 database -> identity resolution omonimie -> API pubblica

---

## 7. VANTAGGI COMPETITIVI

1. **Anti-allucinazione AI**: citazioni verificabili per ogni affermazione
2. **Barriere temporali WWI/WWII**: nessuna contaminazione tra conflitti
3. **Cross-linking reversibile**: audit table, revert completo/selettivo
4. **Viewpoints multi-fazione**: ricostruzione comparativa unica nel settore
5. **27 provider federati**: nessun'altra piattaforma italiana con questa copertura
6. **Compliance gate automatico**: conformita valutata per ogni operazione

### vs digitalizzazione tradizionale
Comprensione semantica vs solo immagine | Cross-linking 9,5M record vs archivio isolato | Narrazione AI vs nessuna sintesi

### vs CMS archivistici standard
27 provider federati vs nessuno | AI multi-provider vs nessuna | Pipeline evidenza 4 livelli vs keyword base

---

## 8. MODELLO PER ENTI PUBBLICI

### Delivery
- **On-premise** (dati sensibili): SQLite, OCR, AI locale, compliance gate
- **Cloud supervised** (dati pubblici): Supabase PostgreSQL, RLS, API pubblica
- **Frontend web**: React, accesso 24/7, RBAC

### Fasi

| Fase | Durata | Output |
|------|--------|--------|
| Audit | 2-4 sett | Report inventario |
| Setup | 1-2 mesi | Ambiente operativo |
| Import | 2-6 mesi | Database popolato |
| Indicizzazione | 1-3 mesi | Grafo provenance |
| Pubblicazione | 1 mese | API + frontend |
| Mantenimento | Continuo | SLA |

### Costo indicativo

| | Setup | Annuale |
|---|---|---|
| Licenza | 40K-80K | 20K-40K |
| Implementazione | 60K-150K | — |
| Cloud + AI | — | 15K-50K |
| Training | 10K-20K | 5K-15K |
| **Totale** | **110K-250K** | **40K-105K/anno** |

**Risparmio vs modello attuale: 150K-400K EUR/anno (ROI 12-18 mesi)**

---

## 9. PROSSIMI PASSI

1. **Demo live** (1h): piattaforma su dati reali (Caporetto, internati IMI)
2. **Audit gratuito** (2-4 sett): inventario patrimonio, analisi gap, stima volumetria
3. **Proof of Concept** (1-2 mesi): fondo pilota 500-1000 documenti, misurazione ROI
4. **Proposta commerciale** dettagliata

### Cosa serve per iniziare
- Elenco fondi documentali (volume, formato, stato)
- Database esistenti (struttura, formato)
- Requisiti di accesso (pubblico/ristretto/misto)
- Budget indicativo e finestra temporale

---

**Prodotto**: Voci dal Fronte — IMI Extractor
**Repository**: https://github.com/HelvetiQuant/Lettere_dal_fronte
**Branch**: fix/provenance-linking-v2
