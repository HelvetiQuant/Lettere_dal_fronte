# Voci dal Fronte — Frontend Refactor v2.0

## Build

```bash
cd frontend
npm install
npx tsc --noEmit   # type check
npx vite build     # production build
npm run dev        # dev server (port 5173)
```

Build verificata: TypeScript e Vite completati senza errori.

## Struttura

```
src/
├── app/
│   └── router.tsx              # BrowserRouter + routes
├── api/
│   ├── client.ts               # 70+ endpoint tipizzati
│   ├── errors.ts               # ApiError, TimeoutError
│   ├── http.ts                 # fetch wrapper con AbortController, timeout, retry GET
│   └── types.ts                # interfacce per tutte le risposte API
├── components/
│   ├── feedback/States.tsx     # Card, Tag, Button, Input, LoadingState, ErrorState, EmptyState, PartialDataNotice, StatCard
│   ├── layout/AppShell.tsx     # shell con header, nav, banner, footer
│   ├── layout/PageIntro.tsx    # PageIntro + Section
│   ├── navigation/AudienceSwitch.tsx
│   ├── navigation/PrimaryNavigation.tsx
│   ├── sources/SourceCard.tsx  # SourceCard, SourceCitation, EvidenceStatus, ConfidenceIndicator
│   ├── dossier/DossierParts.tsx # Timeline, DossierFacts, ResultGroup
│   └── forms/OperationConfirm.tsx
├── hooks/
│   ├── useAsync.ts
│   └── useAudience.ts
├── pages/
│   ├── HomePage.tsx
│   ├── ExplorePage.tsx
│   ├── EventsPage.tsx          # EventsPage + EventDossierPage
│   ├── SoldierDossierPage.tsx
│   ├── ResearchPage.tsx
│   ├── ResearchPlansPage.tsx
│   ├── ResearchSubjectsPage.tsx
│   ├── ResearchGapsPage.tsx
│   ├── ViewpointsPage.tsx
│   ├── HeuristicLinksPage.tsx
│   ├── RecognitionsPage.tsx
│   ├── AdminPage.tsx
│   └── NotFoundPage.tsx
├── styles/
│   ├── tokens.css              # design tokens, color-scheme: light, no dark mode
│   ├── base.css                # reset, body white bg, skip-link, reduced-motion
│   ├── layout.css              # header, nav, footer, audience switch
│   └── utilities.css           # grid, flex, cards, buttons, inputs, states
└── main.tsx
```

## Mappa Route → Pagina → Endpoint

| Route | Pagina | Endpoint API |
|-------|--------|-------------|
| `/` | HomePage | `/api/status`, `/api/decorati`, `/api/entita`, `/api/fondi`, `/api/source/stats`, `/api/events/1gm` |
| `/esplora` | ExplorePage | `/api/search-validated` |
| `/eventi` | EventsPage | `/api/events/1gm` |
| `/eventi/:eventName` | EventDossierPage | `/api/events/:name` |
| `/ricerca` | ResearchPage | `/api/research/v2/create`, `/api/research/v2/plans` |
| `/ricerca/piani` | ResearchPlansPage | `/api/research/v2/plans`, `/api/research/v2/plan/:id` |
| `/ricerca/soggetti` | ResearchSubjectsPage | `/api/research/subjects` |
| `/ricerca/lacune` | ResearchGapsPage | `/api/research/gaps` |
| `/punti-di-vista` | ViewpointsPage | `/api/ai-research` (fallback) |
| `/collegamenti` | HeuristicLinksPage | `/api/search`, `/api/internati/:id/links`, `/api/entita/search` |
| `/riconoscimenti` | RecognitionsPage | `/api/search` |
| `/admin` | AdminPage | `/api/status`, `/api/source/stats`, `/api/entita/build`, `/api/decorati/scrape`, `/api/fondi/extract-all` |
| `/soldato/:type/:id` | SoldierDossierPage | `/api/internati/:id/detail`, `/api/internati/:id/links`, `/api/lebi/compare/:id` |
| `*` | NotFoundPage | — |

## Contratti backend mancanti

### 1. Viewpoints (`/api/viewpoints/create`)

Non esiste un endpoint dedicato. Il frontend usa `/api/ai-research` come fallback.

**Contratto richiesto:**
```
POST /api/viewpoints/create
Body: { query: string, sources?: string[] }
Response: {
  synthesis: string,
  shared_facts: { fact: string, sources: string[] }[],
  divergences: { fact: string, versions: { source: string, value: string }[] }[],
  uncertainties: { topic: string, reason: string }[],
  sources_used: { name: string, url?: string }[]
}
```

### 2. Riconoscimenti (API CRUD)

Non esiste API per gestire pratiche di riconoscimento. Solo pagina HTML statica (`rc.html`).

**Contratti richiesti:**
- `GET /api/riconoscimenti/candidates?q=...` — cerca candidati
- `POST /api/riconoscimenti/pratiche` — crea pratica
- `GET /api/riconoscimenti/pratiche/:id` — dettaglio pratica
- `PATCH /api/riconoscimenti/pratiche/:id` — aggiorna pratica
- `POST /api/riconoscimenti/pratiche/:id/documenti` — upload documento
- `POST /api/riconoscimenti/pratiche/:id/comunicazioni` — registra comunicazione

### 3. Collegamenti euristici (confirm/reject)

Esistono `/api/internati/:id/links` e `/api/entita/:id` ma mancano endpoint per confermare/respingere collegamenti suggeriti.

**Contratti richiesti:**
- `POST /api/links/:id/confirm` — conferma collegamento suggerito
- `POST /api/links/:id/reject` — respingi collegamento
- `GET /api/graph/entity/:type/:id` — grafo completo per entità

## Funzioni legacy conservate

- Ricerca validata con conferme (`/api/search-validated`, `/api/search/confirm`)
- ICRC search (`/api/icrc/search`)
- LeBI search e compare (`/api/lebi/search`, `/api/lebi/compare/:id`)
- Research-to-Index subjects, gaps, dashboard
- Research Orchestrator V2 (create, plan, plans, locator validate, preflight, prompt)
- AI Research multi-provider (`/api/ai-research`)
- Graph endpoints (luoghi, mesi, paesi, soldati clusters)
- Admin batch operations (entita build, decorati scrape, fondi extract, stop)
- Fonti-risorse (list, stats, detail, scrape)
- Source file serving (`/api/source/file`)

## Criteri di accettazione

- [x] Sfondo bianco permanente (`color-scheme: light`, `#ffffff` su html/body/header/main/footer)
- [x] Nessuna `@media (prefers-color-scheme: dark)`
- [x] Nessuna funzione esistente rimossa
- [x] Punti di vista implementato come modulo reale (con avviso se backend non supporta)
- [x] Collegamenti euristici implementato con grafo, filtri, conferma/respingi
- [x] Riconoscimenti non reindirizza alla Home
- [x] Area pubblica e area ricercatore riconoscibili (AudienceSwitch)
- [x] Ogni pagina ha PageIntro con titolo, descrizione, nota IA, passaggi
- [x] Nessun dato fittizio o mock
- [x] Loading, empty, error, partial states gestiti
- [x] Route 404 utile
- [x] Build TypeScript e Vite senza errori
- [x] AbortController e timeout su tutte le richieste
- [x] Retry solo su GET idempotenti
- [x] Tipi specifici al posto di `any`
- [x] Stili centralizzati, niente inline salvo valori dinamici
- [x] Skip link, focus-visible, prefers-reduced-motion
- [x] Responsive: grid 3→2→1 colonne
