# Modulo Magazzino & Riordino fornitori (v0.4)

Completa l'inventario esistente (giacenze, distinta base, scarico automatico, soglie)
con la storicizzazione dei movimenti e aggiunge fornitori e proposte di riordino.

## 1. Movimenti di magazzino storicizzati
- Nuovo modello `StockMovement` (audit trail) e servizio puro `recordMovement`
  (`src/inventory/inventory.service.ts`), usato in transazione da tutti i punti che
  toccano le giacenze.
- Tipi: `LOAD` (carico), `WASTE` (scarto), `RETURN` (reso), `PHYSICAL` (rettifica
  inventario, delta firmato), `SALE` (scarico da vendita), `RECEIPT` (ricezione).
- Lo **scarico automatico** in creazione ordine ora passa da `recordMovement`: esplode
  la **distinta base** (scala gli ingredienti) o, se il prodotto non ha ricetta, scala
  sé stesso — e ogni movimento è tracciato con l'`orderId`. La vendita non si blocca se
  la giacenza è insufficiente: azzera e registra il delta reale.
- Endpoint (OWNER/MANAGER): `GET /inventory/stock`, `GET /inventory/low-stock`,
  `POST /inventory/movements` (rettifiche), `GET /inventory/movements` (storico),
  `PATCH /inventory/stock/:productId/levels` (soglia + livello target).

## 2. Fornitori e listini
- Modelli `Supplier` e `SupplierProduct` (listino). Il listino ha `packSize`
  (unità base per confezione, es. 1 bottiglia = 75 cl), `packPriceCents`, `leadTimeDays`
  e flag `preferred`. Aggiunta `Product.unit` (unità base di consumo) e
  `StockItem.parLevel` (livello target).
- Endpoint (OWNER/MANAGER): CRUD `GET/POST/PATCH /suppliers`, listino
  `GET/POST /suppliers/:id/listings`.

## 3. Proposte di riordino (livello target / par level)
- Logica pura `computeReorder` (`src/suppliers/reorder.logic.ts`): quando la giacenza è
  ≤ soglia, propone di riportarla al **livello target** (`parLevel`, o `reorderLevel` se
  non impostato). Il fabbisogno in unità base viene convertito in **confezioni**
  (arrotondamento per eccesso).
- `GET /suppliers/reorder-proposals` raggruppa le proposte **per fornitore**, scegliendo
  per ogni prodotto il listino `preferred` o quello più economico per unità base, con
  costo di riga e totale per fornitore. I prodotti sotto soglia senza fornitore a listino
  finiscono in `unassigned`.
- La quantità è deterministica (par level). Il punto di innesto per la **previsione AI**
  dei consumi (`demand_forecast`) è isolato in `reorder.logic.ts`: basta sostituire il
  calcolo del target con la previsione, senza toccare route né UI.

## 4. Ciclo ordine d'acquisto + ricezione merce
- Modelli `PurchaseOrder` e `PurchaseOrderItem`. Stati: `DRAFT → SENT → PARTIAL →
  RECEIVED` (+ `CANCELLED` da bozza/inviato). Logica pura `purchase.logic.ts`
  (transizioni + `applyReceipt`).
- L'ordine si genera **da una proposta** (bottone "Crea ordine" nel tab Fornitori) o
  manualmente. Endpoint (OWNER/MANAGER): `POST /purchase-orders`,
  `GET /purchase-orders`, `POST /purchase-orders/:id/send`, `.../cancel`, `.../receive`.
- La **ricezione** (totale o parziale) aggiorna `packsReceived`, incrementa la giacenza
  in unità base (`packs × packSize`) tramite movimenti `RECEIPT` storicizzati, e porta
  l'ordine a `PARTIAL` o `RECEIVED`. Le confezioni ricevute in eccesso sono clampate al
  residuo ordinato.

## Frontend dashboard
Tre nuovi tab in `apps/dashboard/src/App.tsx`:
- **Magazzino** (`components/Inventory.tsx`): giacenze con evidenza sotto-soglia,
  rettifiche (carico/scarto/reso/inventario) e storico movimenti per prodotto.
- **Fornitori / Riordino** (`components/Suppliers.tsx`): anagrafica, listino per
  fornitore e proposte di riordino raggruppate con costo stimato e "Crea ordine".
- **Ordini d'acquisto** (`components/PurchaseOrders.tsx`): lista per stato, invio,
  annullo e ricezione merce con quantità ricevute.

## Migrazione
- `.../20260722_inventory_suppliers/migration.sql` — `StockMovement`, `Supplier`,
  `SupplierProduct`, `Product.unit`, `StockItem.parLevel`.
- `.../20260722_purchase_orders/migration.sql` — `PurchaseOrder`, `PurchaseOrderItem`.
Entrambe additive.

## Verifica
- `node tests/verify-inventory.mjs` → **14/14** (segni movimenti, scarico oltre giacenza,
  inventario fisico, riordino par-level con confezioni, scelta listino più economico).
- `node tests/verify-purchase.mjs` → **12/12** (transizioni PO, ricezione totale/parziale,
  over-receive clampato, unità base a magazzino).
- Modulo dashboard invariato: **33/33** (`node tests/verify.mjs`).
