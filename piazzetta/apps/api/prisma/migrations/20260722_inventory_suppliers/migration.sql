-- Migrazione: movimenti magazzino storicizzati + fornitori/listini + par level.
-- Additiva e idempotente dove possibile.

-- === Product: unità base ===
ALTER TABLE "Product" ADD COLUMN IF NOT EXISTS "unit" TEXT NOT NULL DEFAULT 'pz';

-- === StockItem: livello target ===
ALTER TABLE "StockItem" ADD COLUMN IF NOT EXISTS "parLevel" INTEGER NOT NULL DEFAULT 0;

-- === StockMovement ===
CREATE TABLE IF NOT EXISTS "StockMovement" (
  "id"        TEXT NOT NULL,
  "productId" TEXT NOT NULL,
  "type"      TEXT NOT NULL,
  "qtyDelta"  INTEGER NOT NULL,
  "qtyAfter"  INTEGER NOT NULL,
  "reason"    TEXT,
  "orderId"   TEXT,
  "createdBy" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "StockMovement_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "StockMovement_productId_idx" ON "StockMovement"("productId");
CREATE INDEX IF NOT EXISTS "StockMovement_type_idx"      ON "StockMovement"("type");
CREATE INDEX IF NOT EXISTS "StockMovement_createdAt_idx" ON "StockMovement"("createdAt");
ALTER TABLE "StockMovement" ADD CONSTRAINT "StockMovement_productId_fkey"
  FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- === Supplier ===
CREATE TABLE IF NOT EXISTS "Supplier" (
  "id"        TEXT NOT NULL,
  "venueId"   TEXT NOT NULL,
  "name"      TEXT NOT NULL,
  "email"     TEXT,
  "phone"     TEXT,
  "notes"     TEXT,
  "active"    BOOLEAN NOT NULL DEFAULT true,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Supplier_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Supplier_venueId_idx" ON "Supplier"("venueId");
ALTER TABLE "Supplier" ADD CONSTRAINT "Supplier_venueId_fkey"
  FOREIGN KEY ("venueId") REFERENCES "Venue"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- === SupplierProduct (listino) ===
CREATE TABLE IF NOT EXISTS "SupplierProduct" (
  "id"             TEXT NOT NULL,
  "supplierId"     TEXT NOT NULL,
  "productId"      TEXT NOT NULL,
  "supplierSku"    TEXT,
  "packSize"       INTEGER NOT NULL DEFAULT 1,
  "packPriceCents" INTEGER NOT NULL DEFAULT 0,
  "leadTimeDays"   INTEGER NOT NULL DEFAULT 2,
  "preferred"      BOOLEAN NOT NULL DEFAULT false,
  "createdAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "SupplierProduct_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "SupplierProduct_supplierId_productId_key" ON "SupplierProduct"("supplierId","productId");
CREATE INDEX IF NOT EXISTS "SupplierProduct_productId_idx" ON "SupplierProduct"("productId");
ALTER TABLE "SupplierProduct" ADD CONSTRAINT "SupplierProduct_supplierId_fkey"
  FOREIGN KEY ("supplierId") REFERENCES "Supplier"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "SupplierProduct" ADD CONSTRAINT "SupplierProduct_productId_fkey"
  FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
