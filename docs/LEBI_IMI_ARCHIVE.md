# BANCA DATI LEBI IMI — Archivio Completo

> Documento di riferimento dell'archivio Lessico Biografico IMI (Internati Militari Italiani).
> Ultimo aggiornamento: **2026-10-04**. Fonte dati: `https://www.lessicobiograficoimi.it`

---

## 1. Stato dell'archivio

| Voce | Valore |
|------|--------|
| **Record totali** | **166.112** |
| Copertura | 100% archivio LeBI pubblico |
| Matricola Esercito (militare) | **45.027** record |
| Matricola di Cattura | **59.738** record |
| Impiego (Arb. Kommando) | **17.347** record |
| Deceduti | ~43.642 |
| Sopravvissuti | ~100.191 |

## 2. Archiviazione dati

### SQLite locale — `imi_internati.db`
Tabella `lebi_records`, colonne chiave:

| Colonna | Contenuto |
|---------|-----------|
| `lebi_id` | ID univoco (PK) |
| `cognome`, `nome`, `data_nascita`, `luogo_nascita`, `provincia_nascita`, `regione_nascita` | Anagrafica |
| `grado`, `reparto`, `arma` | Posizione militare |
| `fronte_cattura`, `luogo_cattura`, `data_cattura` | Cattura |
| `matricola_militare` | Matricola del Distretto Militare / Marina / GdF / Aeronautica / Carabinieri |
| `matricola_cattura` | **Solo numeri** di matricola da prigioniero (es. `113541; 0565`) |
| `impiego` | Voci `Arb. Kdo.`/`impiegato...` spostate dai campi |
| `campi_internamento` | JSON array — **solo campi di prigionia** (Stalag/Oflag/KZ/Laz.), senza voci lavoro |
| `sorte`, `data_decesso`, `luogo_decesso`, `causa_morte`, `luogo_sepoltura` | Sorte |
| `data_rientro`, `luogo_rientro` | Rientro |
| `fonti`, `pdf_url`, `detail_url` | Provenienza |

### Supabase — tabella `lebi_records`
- Stesso schema, sincronizzato via upsert `on_conflict=lebi_id`
- Colonne: `matricola_militare`, `matricola_cattura`, `impiego`, `campi_internamento` (pulito)
- Credenziali in `.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- Push script: `push_lebi_matricole_supabase.py` (incrementale con checkpoint `.lebi_push_checkpoint.json`)

### Export Excel definitivo
`C:\Users\eryma\Downloads\lebi_export_MATRICOLE_IMPIEGO_20261004.xlsx`

- 166.112 righe, 27 colonne, ordine alfabetico cognome→nome
- N/O/P = **Matricola Esercito | Matricola di Cattura | Arb. Kommando (Impiego)**
- Wrap text su tutte le celle, centrato, filtri, riga 1 bloccata, header grassetto/grigio
- Larghezze: corte a misura, lunghe (Impiego 42 / Internamento 38 / Fonti 50 / URL 42-45)

## 3. Regole di classificazione (IMPORTANTE — non modificare senza riclassificare)

Parser **section-aware** (`import_lebi_bulk.py`, `update_lebi_matricole.py`):

| Pattern nota LeBI | Sezione | Destinazione |
|-------------------|---------|--------------|
| `Matricola Militare`, `Matricola del Distretto Militare di X`, `Matricola della Marina/GdF/Aeronautica`, `Carabinieri`, `Compartimento Marittimo` | qualsiasi | `matricola_militare` |
| `Matricola:` generica | `CATTURA` / `INTERNAMENTO` | `matricola_cattura` |
| `Matricola:`, `Matricola Militare` ecc. | `POSIZIONE MILITARE` | `matricola_militare` |
| `Matricola <campo>:` (Stalag/KZ/Dachau/prigioniero) | qualsiasi | `matricola_cattura` |
| `Arb. Kdo.`, `Arb.Kdo.`, `Kdo.`, `SS. Kdo.`, `kommando`, `impiegat`, `lavoro`, `arbeit` | `INTERNAMENTO` | `impiego` (**rimossa** da `campi_internamento`) |

### Regole di non-inferenza (verificate)
- Mai inferire numero prigioniero dal nome/codice del campo (`Stalag 307` → `307` è il CAMPO, non la matricola)
- Mai classificare `Matricola del Distretto Militare di Campobasso` come campo (bug regex `\bcampo\b` risolto)
- Note fuse `Matricola III A: 113541.Matricola KZ: 0565.` → splittate su `.` prima di nuovo label
- `matricola_cattura` esportata come **solo numeri** (`113541; 0565`), label rimossa in export

## 4. Pipeline e script

| Script | Funzione |
|--------|----------|
| `import_lebi_bulk.py` | Import bulk da LeBI → SQLite (schema + parser completo) |
| `update_lebi_matricole.py` | Re-fetch + riclassificazione matricole (threaded fetch, single-writer DB, checkpoint `.lebi_update_checkpoint.json`, modalità `fix`/`retry`/`scan`) |
| `sync_lebi_to_supabase.py` | Sync completo SQLite→Supabase |
| `push_lebi_matricole_supabase.py` | Push incrementale delle colonne matricole/impiego |

Pattern: thread solo fetch/parse → `executemany` nel main thread (SQLite single-writer). Checkpoint JSON per resume.

## 5. Record di verifica (ground truth)

| LeBI ID | Nome | Mil. | Cattura | Impiego |
|---------|------|------|---------|---------|
| 300438 | Odero Giorgio Antonio | 245698 | — | — |
| 290043 | Bonuccelli | 1733 | 63253 | Arb. Kdo. 501 |
| 247578 | Savastano | 24268 | 23587 | — |
| 194435 | Artuso | — | 199941 | Arb. Kdo. 6162 Hannover; 6219 Mariental; 6156 Hannover |
| 50000 | Bottero | 15022/40 | 113541; 0565 | — |
| 115058 | Galbiati | — | 3448; 117379 | Arb. Kdo. 3469 Sixlhaselbach; 3448 Berchtesgaden; 3993 Grauning |

Verifiche effettuate: 20/20 assegnazioni corrette su pagine live, 0 residui Kdo nei campi, 0 errori push Supabase.

## 6. Struttura pagine LeBI (parser)

- Endpoint: `/frontend_prodimi.php/caduti/show/{id}` — PDF: `.../showpdf/{id}`
- Sezioni: `ANAGRAFICA`, `POSIZIONE MILITARE`, `CATTURA`, `RIENTRO`, `INTERNAMENTO`, `FONTI`
- Campi: div `fallen-label` + `fallen-field-margins`; note: blocchi `white-corner-show`

## 7. Fonti esterne per dati mancanti

- **Arolsen Archives** (ITS): `https://collections.arolsen-archives.org` — Häftlingsnummer per campo
- **Deutsche Dienststelle WASt / Bundesarchiv**: `wast@bundesarchiv.de` — Kriegsgefangenenunterlagen
- **ANRP**: info@anrp.it — database reduci
- **Archivi di Stato distrettuali** — matricole militari locali

## 8. Note operative

- Per rigenerare l'Excel: query su `lebi_records` + openpyxl (script inline usato il 2026-10-04)
- Excel lock: chiudere via COM PowerShell (`GetActiveObject('Excel.Application')` → `Workbooks.Close($false)`)
- File obsoleti eliminati — unico export valido: `lebi_export_MATRICOLE_IMPIEGO_20261004.xlsx`
