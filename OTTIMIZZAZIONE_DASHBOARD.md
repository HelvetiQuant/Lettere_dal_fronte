# Dashboard proprietario — ottimizzazione (v0.3)

Tre interventi sui moduli già esistenti, integrati senza rompere le API attuali.

## 1. Divisione ordini Bar / Tavola calda
- La **postazione** (`BAR | TAVOLA_CALDA`) è **derivata dalla `category`** del prodotto
  (`src/stations/stations.ts`) e **denormalizzata** su `OrderItem.station` alla creazione
  della comanda, così le statistiche storiche restano stabili.
- Nuovo endpoint `GET /api/v1/orders-tables/board` → comande attive divise in due colonne
  (Bar / Tavola calda) con tempo di attesa. Filtrabile con `?station=`.
- Nuovo endpoint `PATCH /api/v1/orders-tables/order-items/:id/status` per avanzare la
  **singola riga** (bar e cucina lavorano a ritmi diversi).
- Per riclassificare un prodotto basta cambiarne la `category`, oppure estendere le liste
  in `stations.ts`.

## 2. Statistiche tempi di preparazione
- Timestamp aggiunti su `Order` (`placedAt`, `sentAt`, `servedAt`, `paidAt`) e su
  `OrderItem` (`sentAt`, `startedAt`, `readyAt`, `servedAt`).
- Endpoint `GET /api/v1/stats/prep-times?from=&to=&station=&groupBy=category|product|station`
  (solo OWNER/MANAGER). Metriche per gruppo: **coda** (inviato→in prep), **prep**
  (in prep→pronto), **totale postazione** (inviato→pronto) con media, mediana, p90, min, max;
  più il tempo **ordine→consegna al tavolo** (`placedAt`→`servedAt`).
- Logica di calcolo pura e testata in `src/stats/prep-time.ts`.

## 3. Crediti clienti in cassa (inserimento manuale)
- Nuovi modelli `Customer` e `CreditTransaction`. `balanceCents > 0` = il cliente deve al locale.
- Endpoint (OWNER/MANAGER/CASHIER):
  - `POST /api/v1/credit/customers` — inserimento manuale del cliente creditore (con limite
    fido e debito pregresso opzionali).
  - `GET /api/v1/credit/customers?debtors=&q=` — elenco con saldi e totale a credito.
  - `GET /api/v1/credit/customers/:id` — anagrafica + estratto conto.
  - `POST /api/v1/credit/customers/:id/transactions` — addebito / incasso (CASH|POS) / rettifica,
    con controllo del limite di fido e del pagamento non superiore al dovuto.
  - `PATCH /api/v1/credit/customers/:id` — modifica anagrafica/limite/disattivazione.
- Contabilità pura e testata in `src/credit/credit.logic.ts`.

## KDS app dipendenti (bar / cucina)
`apps/employee-mobile/src/screens/KdsScreen.tsx` (Expo/React Native) — schermata per
postazione con selettore Bar/Cucina. Ogni riga si avanza col tocco:
coda → in preparazione → pronto → consegnato, chiamando
`PATCH /orders-tables/order-items/:id/status`. **Registrare IN_PREPARATION** è il passo
che popola il tempo di coda nelle statistiche; senza di esso quel tempo resta vuoto.
Client in `apps/employee-mobile/src/lib/kdsApi.ts`.

## Frontend dashboard
`apps/dashboard/src/App.tsx` con 3 tab: **Comande Bar/Tavola calda**, **Tempi di
preparazione**, **Crediti clienti**. Componenti in `src/components/`, client in `src/api.ts`.

## Migrazione
`apps/api/prisma/migrations/20260722_stations_timing_credit/migration.sql` — additiva e
con backfill (station derivata dalle category esistenti, `sentAt` allineato per gli ordini
già inviati). Applicare con `prisma migrate deploy` (o `prisma db push` in dev).

## Verifica
`node tests/verify.mjs` → **33/33** (mapping station, percentili/summary, contabilità
crediti con limiti, macchina a stati ordine, ciclo di stato per riga e timestamp KDS).
