-- Migrazione: ordini d'acquisto e righe. Additiva.

CREATE TABLE IF NOT EXISTS "PurchaseOrder" (
  "id"         TEXT NOT NULL,
  "venueId"    TEXT NOT NULL,
  "supplierId" TEXT NOT NULL,
  "status"     TEXT NOT NULL DEFAULT 'DRAFT',
  "totalCents" INTEGER NOT NULL DEFAULT 0,
  "note"       TEXT,
  "createdBy"  TEXT,
  "sentAt"     TIMESTAMP(3),
  "receivedAt" TIMESTAMP(3),
  "createdAt"  TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt"  TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "PurchaseOrder_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "PurchaseOrder_venueId_idx"    ON "PurchaseOrder"("venueId");
CREATE INDEX IF NOT EXISTS "PurchaseOrder_supplierId_idx" ON "PurchaseOrder"("supplierId");
CREATE INDEX IF NOT EXISTS "PurchaseOrder_status_idx"     ON "PurchaseOrder"("status");
ALTER TABLE "PurchaseOrder" ADD CONSTRAINT "PurchaseOrder_supplierId_fkey"
  FOREIGN KEY ("supplierId") REFERENCES "Supplier"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TABLE IF NOT EXISTS "PurchaseOrderItem" (
  "id"              TEXT NOT NULL,
  "purchaseOrderId" TEXT NOT NULL,
  "productId"       TEXT NOT NULL,
  "packSize"        INTEGER NOT NULL DEFAULT 1,
  "packsOrdered"    INTEGER NOT NULL,
  "packsReceived"   INTEGER NOT NULL DEFAULT 0,
  "packPriceCents"  INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT "PurchaseOrderItem_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "PurchaseOrderItem_purchaseOrderId_idx" ON "PurchaseOrderItem"("purchaseOrderId");
CREATE INDEX IF NOT EXISTS "PurchaseOrderItem_productId_idx"       ON "PurchaseOrderItem"("productId");
ALTER TABLE "PurchaseOrderItem" ADD CONSTRAINT "PurchaseOrderItem_purchaseOrderId_fkey"
  FOREIGN KEY ("purchaseOrderId") REFERENCES "PurchaseOrder"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "PurchaseOrderItem" ADD CONSTRAINT "PurchaseOrderItem_productId_fkey"
  FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
