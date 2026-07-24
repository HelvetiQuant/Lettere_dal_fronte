# Frontend Audit — IMI Extractor / Voci dal Fronte

Data: 24 luglio 2026
Fase: 1 — Audit (nessuna modifica al codice)

---

## 1. Inventario delle viste

### Frontend pubblico (`templates/index.html` — 2628 righe, SPA basata su Signals)

| Vista | Stato interno | Descrizione |
|-------|--------------|-------------|
| Home | `view: 'home'` | Hero, search bar, statistiche DB, eventi in evidenza |
| Search | `view: 'search'` | Risultati soggetti + eventi, conferme/validazioni, fonti esterne |
| Dossier persona | `view: 'dossier', activeKind: 'subject'` | Panoramica, Punti di vista, Fonti, Lacune, Biografia AI, Immagini AI |
| Dossier evento | `view: 'dossier', activeKind: 'event'` | Panoramica, Punti di vista, Fonti, Caduti, Decorati, Internati, Immagini AI, Lacune, Report AI, Chat AI |
| Explore | `view: 'explore'` | Tabelle DB (internati, caduti, decorati, provider) |
| Events | `view: 'events'` | Griglia eventi canonici |
| Graph | `view: 'graph'` | 5 sub-viste: Eventi, Luoghi, Anni, Teatri, Soldati |
| Admin | `view: 'admin'` | KPI admin, import, estrazione, provider, crediti |
| Lightbox | `lightbox: {...}` | Modale anteprima fonte (immagine/PDF) |
| Soldato modal | `_soldatoModal: {...}` | Modale dettaglio soldato (caduto/decorato/internato) |

### Frontend operatori (`templates/rc.html` — 1995 righe, SPA vanilla JS)

| Vista | Stato interno | Descrizione |
|-------|--------------|-------------|
| Login | `view: 'login'` | Form autenticazione |
| Dashboard | `view: 'dashboard'` | KPI operativi, pratiche, candidati per stato, recenti |
| Scopri | `view: 'discover'` | Ricerca federata multi-fonte con filtri |
| Croce Rossa | `view: 'red-cross'` | Ricerca ICRC WW1 + CRI Milano |
| Fonti Esterne | `view: 'external-sources'` | Lista record archivistici federati CRI |
| Dettaglio record esterno | `view: 'external-record-detail'` | Metadati, gerarchia, menzioni, fatti, oggetti digitali, collegamenti |
| Candidati | `view: 'candidates'` | Lista candidati con filtri e paginazione |
| Dettaglio candidato | `view: 'candidate-detail'` | 9 tab: Dati, Fonti, Eventi, Valutazione, AI, Genealogia, Contatti, Pratiche, Cronologia |
| Catalogo | `view: 'recognition-types'` | Tipi riconoscimento |
| Conformità | `view: 'compliance'` | 3 tab: Policy, Coda revisione, Log decisioni |
| Audit | `view: 'audit'` | Registro audit |
| Users | `view: 'users'` | **ASSENTE** — nav visibile per admin ma nessun handler |

---

## 2. Endpoint API mappati

### API pubbliche (`app.py` + moduli)

| Endpoint | Metodo | Frontend chiamante |
|----------|--------|-------------------|
| `/api/search` | GET | index.html (via `voci-data.js` `searchLive`) |
| `/api/search-validated` | GET | index.html (via `voci-data.js` `searchLive`) |
| `/api/search/confirm` | POST | index.html (`confirmSearchFix`) |
| `/api/events/1gm` | GET | index.html (`componentDidMount`, `goGraph`) |
| `/api/events/1gm/{name}/caduti` | GET | index.html (`loadMoreCaduti`, `_loadCadutiOffset`, `_searchCadutiServer`) |
| `/api/events/1gm/{name}/decorati` | GET | index.html (`loadMoreDecorati`, `_searchDecoratiServer`) |
| `/api/events/{name}/internati` | GET | index.html (`loadMoreInternati`, `_searchInternatiServer`) |
| `/api/graph/luoghi` | GET | index.html (`goGraph`) |
| `/api/graph/mesi` | GET | index.html (`goGraph`) |
| `/api/graph/paesi` | GET | index.html (`goGraph`) |
| `/api/graph/soldati/architecture` | GET | index.html (`goGraph`) |
| `/api/graph/soldati/clusters` | GET | index.html (`loadSoldatiClusters`) |
| `/api/graph/soldati/cluster/{field}/{cluster}` | GET | index.html (`loadClusterSoldati`) |
| `/api/biography` | POST | index.html (`generateSoldierBio`) |
| `/api/soldier/images` | POST | index.html (`generateSoldierImages`) |
| `/api/event/report/{tab}` | POST | index.html (`generateEventReport`) |
| `/api/event/report/chronological` | POST | index.html (`generateChronologicalReport`) |
| `/api/event/chat` | POST | index.html (`sendEventChatMessage`) |
| `/api/fonte/analyze` | POST | index.html (`analyzeSource`) |
| `/api/fonte/generate-images` | POST | index.html (`generateSourceImages`) |
| `/api/fonti-risorse` | GET | index.html (`loadExternalSources`) |
| `/api/caduti/{id}` | GET | index.html (`openSoldatoModal`) |
| `/api/decorati/{id}` | GET | index.html (`openSoldatoModal`) |
| `/api/internati/{id}/detail` | GET | index.html (`openSoldatoModal`) |

### API operatori (`rc_api.py` + `rc_api_ext.py`)

| Endpoint | Metodo | Frontend chiamante |
|----------|--------|-------------------|
| `/api/rc/auth/login` | POST | rc.html (`apiLogin`) |
| `/api/rc/auth/logout` | POST | rc.html (`apiLogout`) |
| `/api/rc/auth/me` | GET | rc.html (`checkAuth`) |
| `/api/rc/dashboard` | GET | rc.html (`loadDashboard`) |
| `/api/rc/dashboard-ext` | GET | rc.html (`loadDashboard`) |
| `/api/rc/candidates` | GET/POST | rc.html (`loadCandidates`, `createCandidate`) |
| `/api/rc/candidates/{id}` | GET | rc.html (`loadCandidate`) |
| `/api/rc/candidates/{id}/sources` | GET/POST | rc.html (`loadCandidate`, `createSource`) |
| `/api/rc/candidates/{id}/events` | GET | rc.html (`loadCandidate`) |
| `/api/rc/candidates/{id}/assessments` | GET/POST | rc.html (`loadCandidate`, `createAssessment`) |
| `/api/rc/candidates/{id}/family` | GET/POST | rc.html (`loadCandidate`, `createFamilyPerson`) |
| `/api/rc/candidates/{id}/contacts` | GET | rc.html (`loadCandidate`) |
| `/api/rc/candidates/{id}/admin-cases` | GET | rc.html (`loadCandidate`) |
| `/api/rc/candidates/{id}/history` | GET | rc.html (`loadCandidate`) |
| `/api/rc/candidates/{id}/ai-analyses` | GET | rc.html (`loadCandidate`) |
| `/api/rc/candidates/{id}/descendant-contacts` | GET/POST | rc.html (`loadCandidate`, `createDescContact`) |
| `/api/rc/candidates/{id}/practices` | GET/POST | rc.html (`loadCandidate`, `createExtPractice`) |
| `/api/rc/candidates/{id}/practice-documents` | GET/POST | rc.html (`loadCandidate`, `uploadPracticeDoc`) |
| `/api/rc/candidates/{id}/dossier` | POST | rc.html (`generateDossier`) |
| `/api/rc/candidates/{id}/ai-analysis` | POST | rc.html (`runAiAnalysis`) |
| `/api/rc/candidates/{id}/transition` | POST | rc.html (`doTransition`) |
| `/api/rc/descendant-contacts/{id}` | DELETE/PUT | rc.html (`deleteDescContact`, `editDescContact`) |
| `/api/rc/practice-documents/{id}/verify` | PUT | rc.html (`verifyDoc`) |
| `/api/rc/practice-documents/{id}/archive` | PUT | rc.html (`archiveDoc`) |
| `/api/rc/practice-documents/{id}` | DELETE | rc.html (`deleteDoc`) |
| `/api/rc/practice-documents/{id}/ocr` | POST/GET | rc.html (`ocrDoc`, `viewOcr`) |
| `/api/rc/recognition-types` | GET | rc.html (`loadRecognitionTypes`) |
| `/api/rc/audit` | GET | rc.html (`loadAudit`) |
| `/api/rc/discover-candidates` | GET | rc.html (`discoverSearch`) |
| `/api/rc/discover-candidates/{source}/{id}/import` | POST | rc.html (`importCandidate`) |
| `/api/rc/red-cross/search` | GET | rc.html (`redCrossSearch`) |
| `/api/rc/red-cross/{provider}/{id}` | GET | rc.html (`redCrossDetail`) |
| `/api/rc/compliance/policies` | GET | rc.html (`loadCompliance`) |
| `/api/rc/compliance/policies/{id}` | PUT | rc.html (`updatePolicy`) |
| `/api/rc/compliance/decisions` | GET | rc.html (`loadCompliance`) |
| `/api/rc/compliance/review-queue` | GET | rc.html (`loadCompliance`) |
| `/api/rc/compliance/review-queue/{id}/resolve` | POST | rc.html (`resolveReviewItem`) |

### API external sources (`external_sources_api.py`)

| Endpoint | Metodo | Frontend chiamante |
|----------|--------|-------------------|
| `/api/external-sources/records` | GET | rc.html (`loadExternalSources`) — **BUG: usa `getAuthHeaders()` non definita** |
| `/api/external-sources/records/{id}` | GET | rc.html (`loadExternalRecordDetail`) — **BUG** |
| `/api/external-sources/records/{id}/children` | GET | rc.html — **BUG** |
| `/api/external-sources/records/{id}/parents` | GET | rc.html — **BUG** |
| `/api/external-sources/import` | POST | rc.html (`startExternalImport`) — **BUG** |
| `/api/external-sources/import/status` | GET | rc.html (`pollImportStatus`) — **BUG** |
| `/api/external-sources/records/{id}/generate-matches` | POST | rc.html (`generateMatches`) — **BUG** |
| `/api/external-sources/links/{id}/review` | PUT | rc.html (`reviewExternalLink`) — **BUG** |
| `/api/external-sources/records/{id}/verify-url` | POST | rc.html (`verifyExternalUrl`) — **BUG** |
| `/api/external-sources/records/{id}/refresh` | POST | rc.html (`refreshSingleRecord`) — **BUG** |

---

## 3. Problemi classificati

### CRITICAL (bloccante)

| # | Pagina | Comportamento | Conseguenza | Soluzione proposta | File |
|---|--------|--------------|-------------|-------------------|------|
| C1 | rc.html — Fonti Esterne (tutte le chiamate) | `getAuthHeaders()` è chiamata 12 volte ma **mai definita** in tutto il file | Tutte le operazioni su Fonti Esterne CRI lanciano `ReferenceError: getAuthHeaders is not defined` — l'intera sezione è non funzionante | Definire `function getAuthHeaders()` che restituisce `{}` o header di sessione appropriati. Le API `/api/external-sources/*` usano `require_auth(request)` che legge il cookie di sessione, quindi basta inviare credenziali: `{ credentials: 'include' }` | `templates/rc.html:1370,1382,1389,1390,1402,1413,1427,1439,1450,1702` |
| C2 | Entrambi — Navigazione | Nessun URL routing. `index.html` usa `state.view`, `rc.html` usa `state.view`. L'URL non cambia mai | Niente bookmark, deep link, back/forward, condivisione URL. Refresh della pagina perde tutto lo stato | Implementare router basato su `history.pushState()` / `popstate`. Mappare ogni vista a un URL: `/#/search?q=...`, `/#/dossier/event/caporetto`, `/riconoscimenti/#/candidates`, ecc. | `templates/index.html`, `templates/rc.html` |
| C3 | rc.html — Tutte le viste | `render()` ricostruisce l'intero DOM via `app.innerHTML = ...` ad ogni cambio di stato | Perdita scroll, perdita focus input, flickering, performance pessima con liste lunghe. Ogni `setState` → re-render completo | Diffing mirato: aggiornare solo la sezione cambiata. O migrare a un sistema di componenti con render targettato | `templates/rc.html:429-438` |
| C4 | rc.html — Tutte le viste | Nessun CSS responsive. Nessun `@media`, nessun breakpoint. Tabelle e griglie overflow su mobile | Inusabile su tablet e smartphone. Nav non si adatta | Aggiungere breakpoint responsive: `@media (max-width: 768px)` con griglie a colonna singola, tabelle scrollabili, nav hamburger | `templates/rc.html:1-115` |
| C5 | rc.html — Users (admin) | Nav "Utenti" visibile per ruolo admin, ma `renderContent()` non ha `case 'users'` | Click su "Utenti" → "Sezione non disponibile". Funzione attesa ma mancante | Aggiungere `renderUsers()` con CRUD utenti (endpoint `/api/rc/users` esiste in `auth.py`) | `templates/rc.html:479,519` |

### HIGH (impatto significativo)

| # | Pagina | Comportamento | Conseguenza | Soluzione proposta | File |
|---|--------|--------------|-------------|-------------------|------|
| H1 | Entrambi — Dossier / Dettaglio candidato | Perdita della posizione di scroll ad ogni re-render | UX degradante per liste lunghe (caduti, decorati, internati) | Preservare scroll position: salvare `scrollTop` prima del render, ripristinarlo dopo | `templates/index.html:1379-1407`, `templates/rc.html:429-438` |
| H2 | Entrambi — Filtri | Filtri persi ad ogni navigazione. `index.html`: filtri caduti/decorati/internati resettati. `rc.html`: filtri candidati persi | L'utente deve re-applicare i filtri ogni volta | Persistere filtri nello stato globale o in URL query params | `templates/index.html:1730-1813`, `templates/rc.html:274-282` |
| H3 | rc.html — Dettaglio candidato | `loadCandidate()` esegue 12 chiamate API parallele ad ogni apertura. Nessuna cache. Switch tab → nessun re-fetch (ok), ma navigazione away+back → 12 chiamate di nuovo | Lentezza, carico server inutile | Cache lato client: non ricaricare se `state.selectedCandidate.id === cid` e dati già presenti | `templates/rc.html:285-308` |
| H4 | Entrambi — Design system | `index.html` e `rc.html` hanno CSS variables diverse, nomi diversi, valori diversi. Nessun componente condiviso | Inconsistenza visiva, manutenzione duplicata | Creare `shared.css` con design token unificati (colori, tipografia, spacing, radius, ombre) e componenti comuni (button, card, tag, table, input, modal) | `templates/index.html:1-50`, `templates/rc.html:1-115` |
| H5 | index.html — Admin | Pulsante "Upload…" senza handler. Card con dati hardcoded ($14.20, 15/20 lettere, 16/16 provider). Nessuna funzione reale | Sezione admin non funzionale, elementi morti | Collegare a endpoint reali (`/api/status`, `/api/ai-research/history`, credits API) o rimuovere se non richiesta | `templates/index.html:1026-1055` |
| H6 | Entrambi — Error states | Molti fallimenti API sono silenziosi (`console.warn` o catch vuoto). L'utente resta su "Caricamento..." indefinitamente | L'utente non sa che c'è stato un errore, non può reagire | Aggiungere error state visibile per ogni vista: banner di errore con bottone "Riprova" | `templates/index.html:1292,1312`, `templates/rc.html:608,708` |
| H7 | rc.html — Azioni critiche | `doTransition()` usa `prompt()` per motivazione. `editDescContact()` usa `prompt()` per stato. `verifyDoc()` usa `prompt()` per stato. `archiveDoc()` usa `confirm()` | UX pessima, niente validazione, dialoghi bloccanti nativi del browser incoerenti | Sostituire con modali personalizzati con select/textarea e validazione | `templates/rc.html:356,1241,1290,1305` |
| H8 | Entrambi — Accessibilità | Nessun ARIA label, nessun ruolo semantico, nessun focus management, nessun keyboard shortcut | Non accessibile a screen reader, non navigabile da tastiera | Aggiungere `role`, `aria-label`, `aria-selected` per tab, `aria-live` per toast, focus trap nei modali | `templates/index.html` (tutto), `templates/rc.html` (tutto) |
| H9 | Entrambi — Inline styles | Massiccio uso di `style="..."` inline in entrambi i file | Niente caching CSS, niente override responsive, codice verboso, difficile manutenzione | Estrarre classi CSS riutilizzabili. Sostituire inline styles con classi | `templates/index.html` (tutto), `templates/rc.html` (tutto) |
| H10 | index.html — Graph | SVG generato client-side da `buildGraphSVG()`, `buildGraphLuoghiSVG()`, `buildGraphMesiSVG()`, `buildGraphPaesiSVG()`, `buildGraphSoldatiSVG()`. Nessun canvas, nessun virtual DOM | Performance degradata con dataset grandi (342K soldati). Stringhe SVG concatenate manualmente | Valutare rendering canvas (es. D3.js o PixiJS) o pre-rendering server-side. Per ora, almeno aggiungere lazy loading dei dati del grafo | `templates/index.html:1936-2117` |

### MEDIUM (migliorabile)

| # | Pagina | Comportamento | Conseguenza | Soluzione proposta | File |
|---|--------|--------------|-------------|-------------------|------|
| M1 | Entrambi — Cache dati | Eventi 1GM re-fetchati ad ogni `goGraph('eventi')` se `_graphEventsList` è null. Dashboard re-fetchata ad ogni view switch | Richieste API ridondanti, latenza | Cache con TTL lato client. Non re-fetchare se dati già presenti e recenti | `templates/index.html:1846-1888`, `templates/rc.html:223-230` |
| M2 | Entrambi — Breadcrumb | Nessun breadcrumb di navigazione. Solo "← Indietro" in `external-record-detail` | L'utente perde contesto in navigazione profonda (dossier → tab → soldato modal) | Aggiungere breadcrumb: Home > Eventi > Caporetto > Caduti | `templates/index.html`, `templates/rc.html` |
| M3 | rc.html — Discover | Nessuna paginazione risultati (limit=50 fisso) | Non è possibile sfogliare oltre i primi 50 risultati | Aggiungere paginazione o infinite scroll | `templates/rc.html:238` |
| M4 | rc.html — Toast | Toast auto-spare dopo 3 secondi fisso | Messaggi di errore importanti possono essere persi | Toast error: durata 8s o persistente con chiusura manuale. Toast success: 3s | `templates/rc.html:188` |
| M5 | index.html — Event chat | Nuovi messaggi non scrollano automaticamente in basso | L'utente deve scrollare manualmente per vedere la risposta AI | `scrollTo(0, scrollHeight)` dopo ogni nuovo messaggio | `templates/index.html:1589-1612` |
| M6 | Entrambi — Page title | Il `<title>` della pagina non cambia in base alla vista | Tab del browser non informativi | `document.title = ...` ad ogni cambio vista | Entrambi |
| M7 | Entrambi — Skeleton loading | Tutti i loading state sono testo ("Caricamento...", "Ricerca...") | Perceived performance peggiore. L'utente non sa cosa sta caricando | Sostituire con skeleton placeholder (struttura grigia animata) | Entrambi |
| M8 | rc.html — Modali form | `renderModalForm()` genera input text per ogni campo. Nessun select, date picker, validazione | Inserimento dati prono a errori. Es: `stato_verifica` è testo libero invece di select | Generare input type-aware: select per enum, date picker per date, textarea per testo lungo | `templates/rc.html:1147-1163` |
| M9 | index.html — Explore | Tabelle explore usano dati statici da `voci-data.js` (`EXPLORE_TABLES`). Non collegate al DB | Dati potenzialmente stale, non real-time | Collegare a endpoint API reali per dati live | `templates/index.html:814-848`, `templates/voci-data.js` |
| M10 | rc.html — Candidate filters | Input ricerca richiede Enter manuale. Nessun debounce | UX di ricerca inconsistente tra viste (discover ha button, candidates ha Enter) | Aggiungere debounce 350ms come in `index.html` per caduti/decorati/internati | `templates/rc.html:678` |
| M11 | Entrambi — No data export | Nessun modo per esportare risultati di ricerca o dossier | Ricercatori non possono salvare/condividere dati | Aggiungere bottoni export CSV/PDF in search results e dossier | `templates/index.html`, `templates/rc.html` |

### LOW (cosmetico / nice-to-have)

| # | Pagina | Comportamento | Conseguenza | Soluzione proposta | File |
|---|--------|--------------|-------------|-------------------|------|
| L1 | rc.html — Icone | Emoji usate come icone nei bottoni (🤖📄🔍✓📦🗑) | Rendering inconsistente tra OS/browser | Sostituire con icone SVG o font icon (Lucide) | `templates/rc.html:718,719,1021-1025` |
| L2 | Entrambi — Dark mode | CSS variables potrebbero supportarlo ma nessun toggle | Preferenza utente non rispettata | Aggiungere `prefers-color-scheme` media query + toggle manuale | Entrambi |
| L3 | Entrambi — Print | Nessuno stile di stampa | Dossier e report non stampabili correttamente | Aggiungere `@media print` con layout semplificato | Entrambi |
| L4 | index.html — Esempi ricerca | Esempi di ricerca hardcoded in `renderVals()` | Non data-driven, non localizzati | Spostare in `voci-data.js` con traduzioni | `templates/index.html:2188-2192` |
| L5 | rc.html — Disclaimer | Testo "Riconoscimento ipotizzato" ripetuto in login e candidate detail | Ridondante | Mostrare solo in candidate detail, non in login | `templates/rc.html:446,722` |
| L6 | Entrambi — Favicon | Nessuna favicon personalizzata | Branding assente | Aggiungere favicon.svg | Entrambi |
| L7 | Entrambi — Analytics | Nessun tracking eventi UX | Non misurabile miglioramenti | Integrare analytics privacy-first (es. Plausible) | Entrambi |

---

## 4. Funzioni duplicate

| Funzione | Posizione | Descrizione |
|----------|-----------|-------------|
| `esc()` | `rc.html:193` + `index.html:2144` (inline) | Entrambe le SPA implementano escaping HTML. Logica identica, codice duplicato |
| `linkify()` | `index.html:1614-1638` | Linkificazione testo AI. Dovrebbe essere condivisa con rc.html per future funzioni AI |
| `stateTag()` | `rc.html:198-204` | Mappatura stato → tag CSS. Logica di badge ripetuta in `complianceBadge()`, `roleBadge()`, ecc. |
| `toast()` | `rc.html:185-189` | Notifiche toast. Dovrebbe essere componente condiviso |
| Badge/tag rendering | `rc.html:198-208,1749-1762,1883-1902` | Pattern ripetuto: mappa → classe CSS → span. Unificare in un componente `<Badge>` |
| Filter + search pattern | `index.html:1730-1813` | Pattern debounce + search ripetuto 3 volte (caduti, decorati, internati). Dovrebbe essere una funzione generica |

---

## 5. Funzioni difficili da raggiungere

| Funzione | Posizione | Problema |
|----------|-----------|----------|
| `goAdmin()` | `index.html:1328-1335` | Link "Admin" in nav ma nessuna indicazione visiva che esista. L'utente pubblico non sa che c'è |
| `renderUsers()` | `rc.html` — **ASSENTE** | Nav "Utenti" visibile per admin ma nessun handler di render |
| `generateChronologicalReport()` | `index.html:1499-1526` | Report cronologico generabile solo dal tab "Cronologia" del dossier evento, ma il tab si chiama "Lacune" nella UI. Confusione |
| `loadClusterSoldati()` | `index.html:1903-1918` | Accessibile solo cliccando un cluster nel grafo soldati. Nessun altro percorso |
| `refreshSingleRecord()` | `rc.html:1699-1707` | Bottone "Aggiorna" nel dettaglio record esterno, ma nessun indicatore visivo che esista |

---

## 6. Problemi di navigazione

| Problema | Pagina | Dettaglio |
|----------|--------|-----------|
| No back/forward | Entrambi | L'URL non cambia, `history.pushState` mai chiamato. Back del browser esce dal sito |
| No deep link | Entrambi | Impossibile condividere URL a dossier specifico o candidato specifico |
| Scroll perso | Entrambi | Ogni `setState()` / `render()` resetta lo scroll a top |
| Tab state perso | index.html | Cambiare dossier resetta `dossierTab` a `'overview'`. Se l'utente era su "Caduti" e apre un altro evento, torna a "Panoramica" |
| View state perso | rc.html | Tornare da `candidate-detail` a `candidates` resetta la pagina a 0 |
| No breadcrumb | Entrambi | In navigazione profonda (dossier → soldato modal → fonte), l'utente perde il contesto |

---

## 7. Richieste API — problemi identificati

| Problema | Pagina | Dettaglio |
|----------|--------|-----------|
| **12 chiamate parallele** | rc.html:285-308 | `loadCandidate()` esegue 12 `apiJson()` in `Promise.all()`. Nessuna cache. Ogni ritorno al dettaglio = 12 nuove chiamate |
| **getAuthHeaders undefined** | rc.html (10 chiamate) | Tutte le chiamate a `/api/external-sources/*` usano `getAuthHeaders()` che non esiste → `ReferenceError` |
| **Re-fetch eventi** | index.html:1848 | `goGraph('eventi')` re-fetcha `/api/events/1gm` se `_graphEventsList` è null, ma non invalida mai. Se si torna alla home e si riapre il grafo, usa cache. Ma se si cambia tab grafo e si torna, non re-fetcha (ok) |
| **Re-fetch dashboard** | rc.html:223-230 | `loadDashboard()` chiamato ad ogni `setView('dashboard')`. Nessuna cache |
| **No abort controller** | Entrambi | Nessuna richiesta API viene abortita quando l'utente naviga via. Richieste orfane continuano e possono aggiornare stato stale |
| **No retry logic** | Entrambi | Fallimenti API non hanno retry. Un singolo errore di rete blocca la vista |

---

## 8. Componenti ripetuti

| Componente | Occorrenze | File | Soluzione |
|-----------|-----------|------|-----------|
| Tab navigation | 2 (index.html dossier tabs, rc.html candidate tabs) | Entrambi | Estrarre componente `<Tabs>` condiviso |
| Tag/Badge | ~15 mappe di classi CSS separate | Entrambi | Unificare in un sistema `<Badge variant="...">` |
| Card | Definita inline in entrambi i file | Entrambi | Estrarre classe `.card` condivisa |
| Table | Stile diverso tra index.html e rc.html | Entrambi | Unificare stile tabella |
| Modal/Dialog | index.html: lightbox + soldato modal. rc.html: modal form + upload form + OCR view | Entrambi | Estrarre componente `<Modal>` condiviso |
| Search input + button | 5+ occorrenze (index.html search bar, rc.html discover, red-cross, candidates filter, external sources) | Entrambi | Estrarre componente `<SearchBar>` |
| Loading indicator | "Caricamento..." ripetuto ~15 volte | Entrambi | Estrarre componente `<Loading>` o `<Skeleton>` |
| Empty state | "Nessun risultato" / "Nessun candidato" ripetuto ~20 volte | Entrambi | Estrarre componente `<EmptyState>` |
| Filter bar | Pattern ripetuto: input + select + button | Entrambi | Estrarre componente `<FilterBar>` |

---

## 9. Proposta definitiva

### Architettura target

```
templates/
├── shared/
│   ├── design-tokens.css      # CSS variables unificate (colori, tipografia, spacing)
│   ├── components.css          # Classi componenti (.btn, .card, .tag, .table, .modal, .input)
│   ├── components.js           # Componenti JS riutilizzabili (Tabs, Modal, Toast, Badge, SearchBar)
│   └── router.js               # Router basato su history API per entrambe le SPA
├── index.html                  # Frontend pubblico (refactoring)
├── rc.html                     # Frontend operatori (refactoring)
└── voci-data.js                # i18n + dati statici (esistente)
```

### Priorità intervento

1. **Fix critici immediati**: C1 (getAuthHeaders), C5 (users view)
2. **Router URL**: C2 — implementare `router.js` condiviso
3. **Design system unificato**: H4 — `design-tokens.css` + `components.css`
4. **Render mirato**: C3 — sostituire `app.innerHTML` con diffing mirato
5. **Responsive**: C4 — breakpoint mobile/tablet
6. **Error/empty/loading states**: H6, M7 — componenti shared
7. **Cache dati**: M1, H3 — cache lato client con TTL
8. **Accessibilità**: H8 — ARIA, keyboard, focus management
9. **AI-native**: Azioni contestuali per AI (Phase 5)
10. **Ottimizzazione**: Lazy loading, abort controller, debounce (Phase 6)

### Endpoint aggregati necessari

| Endpoint proposto | Motivo |
|-------------------|--------|
| `GET /api/rc/candidates/{id}/full` | Aggrega 12 chiamate in 1. Riduce latenza dettaglio candidato da 12 round-trip a 1 |
| `GET /api/dossier/{type}/{id}` | Aggrega dati dossier + fonti + timeline + external sources in 1 chiamata per index.html |
| `GET /api/graph/all?type={tab}` | Pre-calcola o aggrega dati grafo server-side invece di 5 endpoint separati |
| `POST /api/event/report/batch` | Permette generazione multi-tab report in 1 chiamata invece di 4 separate |

---

## 10. File da modificare

| File | Modifiche previste |
|------|-------------------|
| `templates/index.html` | Refactoring completo: router, design system, componenti, lazy loading, error states |
| `templates/rc.html` | Fix getAuthHeaders, router, render mirato, responsive, users view, modali |
| `templates/voci-data.js` | Aggiungere traduzioni francesi complete, spostare esmpi ricerca |
| **NUOVO** `templates/shared/design-tokens.css` | Design token unificati |
| **NUOVO** `templates/shared/components.css` | Classi componenti shared |
| **NUOVO** `templates/shared/components.js` | Componenti JS shared (Tabs, Modal, Toast, Badge, SearchBar, Loading, EmptyState) |
| **NUOVO** `templates/shared/router.js` | Router URL-based condiviso |
| `app.py` | Aggiungere endpoint aggregati se approvati |

---

*Fine audit. Nessun codice modificato in questa fase.*
