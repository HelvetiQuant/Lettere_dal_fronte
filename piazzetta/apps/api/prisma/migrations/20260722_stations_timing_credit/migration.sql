-- Migrazione: postazioni + timestamp ciclo ordine + crediti clienti
-- Generata a mano per allinearsi allo schema aggiornato. Idempotente dove possibile.

-- === Order: timestamp del ciclo di vita ===
ALTER TABLE "Order" ADD COLUMN IF NOT EXISTS "placedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "Order" ADD COLUMN IF NOT EXISTS "sentAt"   TIMESTAMP(3);
ALTER TABLE "Order" ADD COLUMN IF NOT EXISTS "servedAt" TIMESTAMP(3);
ALTER TABLE "Order" ADD COLUMN IF NOT EXISTS "paidAt"   TIMESTAMP(3);

-- Backfill: per gli ordini già inviati, allinea placedAt/sentAt al createdAt.
UPDATE "Order" SET "placedAt" = "createdAt" WHERE "placedAt" IS NULL;
UPDATE "Order" SET "sentAt" = "createdAt" WHERE "sentAt" IS NULL AND "status" <> 'DRAFT';

CREATE INDEX IF NOT EXISTS "Order_sessionId_idx" ON "Order"("sessionId");
CREATE INDEX IF NOT EXISTS "Order_status_idx"    ON "Order"("status");
CREATE INDEX IF NOT EXISTS "Order_placedAt_idx"  ON "Order"("placedAt");

-- === OrderItem: postazione + timestamp ===
ALTER TABLE "OrderItem" ADD COLUMN IF NOT EXISTS "station"   TEXT NOT NULL DEFAULT 'BAR';
ALTER TABLE "OrderItem" ADD COLUMN IF NOT EXISTS "sentAt"    TIMESTAMP(3);
ALTER TABLE "OrderItem" ADD COLUMN IF NOT EXISTS "startedAt" TIMESTAMP(3);
ALTER TABLE "OrderItem" ADD COLUMN IF NOT EXISTS "readyAt"   TIMESTAMP(3);
ALTER TABLE "OrderItem" ADD COLUMN IF NOT EXISTS "servedAt"  TIMESTAMP(3);

-- Backfill station dalle category dei prodotti esistenti.
UPDATE "OrderItem" oi
SET "station" = CASE
  WHEN lower(trim(p."category")) IN
    ('pizza','primo','secondo','contorno','panino','piadina','toast','insalata',
     'dolce','piatto','tavola_calda','griglia','frittura')
    THEN 'TAVOLA_CALDA'
  ELSE 'BAR'
END
FROM "Product" p
WHERE oi."productId" = p."id";

CREATE INDEX IF NOT EXISTS "OrderItem_orderId_idx" ON "OrderItem"("orderId");
CREATE INDEX IF NOT EXISTS "OrderItem_station_idx" ON "OrderItem"("station");
CREATE INDEX IF NOT EXISTS "OrderItem_status_idx"  ON "OrderItem"("status");

-- === Customer: conti aperti / crediti ===
CREATE TABLE IF NOT EXISTS "Customer" (
  "id"           TEXT NOT NULL,
  "venueId"      TEXT NOT NULL,
  "name"         TEXT NOT NULL,
  "phone"        TEXT,
  "email"        TEXT,
  "notes"        TEXT,
  "balanceCents" INTEGER NOT NULL DEFAULT 0,
  "limitCents"   INTEGER NOT NULL DEFAULT 0,
  "active"       BOOLEAN NOT NULL DEFAULT true,
  "createdAt"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Customer_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Customer_venueId_idx"      ON "Customer"("venueId");
CREATE INDEX IF NOT EXISTS "Customer_venueId_name_idx" ON "Customer"("venueId","name");
ALTER TABLE "Customer" ADD CONSTRAINT "Customer_venueId_fkey"
  FOREIGN KEY ("venueId") REFERENCES "Venue"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TABLE IF NOT EXISTS "CreditTransaction" (
  "id"                TEXT NOT NULL,
  "customerId"        TEXT NOT NULL,
  "type"              TEXT NOT NULL,
  "amountCents"       INTEGER NOT NULL,
  "balanceAfterCents" INTEGER NOT NULL,
  "orderId"           TEXT,
  "method"            TEXT,
  "note"              TEXT,
  "createdBy"         TEXT,
  "createdAt"         TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "CreditTransaction_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "CreditTransaction_customerId_idx" ON "CreditTransaction"("customerId");
CREATE INDEX IF NOT EXISTS "CreditTransaction_createdAt_idx"  ON "CreditTransaction"("createdAt");
ALTER TABLE "CreditTransaction" ADD CONSTRAINT "CreditTransaction_customerId_fkey"
  FOREIGN KEY ("customerId") REFERENCES "Customer"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
