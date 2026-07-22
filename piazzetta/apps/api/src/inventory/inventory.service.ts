import type { Prisma } from '@prisma/client';

type Tx = Prisma.TransactionClient;

export type MovementType = 'LOAD' | 'WASTE' | 'RETURN' | 'PHYSICAL' | 'SALE' | 'RECEIPT';

/** Convenzione dei segni: quanto varia la giacenza per ciascun tipo di movimento. */
export function movementSign(type: MovementType): 1 | -1 {
  switch (type) {
    case 'LOAD':
    case 'RETURN':
    case 'RECEIPT':
      return 1;
    case 'WASTE':
    case 'SALE':
      return -1;
    case 'PHYSICAL':
      return 1; // per PHYSICAL il delta è fornito già col segno (vedi recordMovement)
  }
}

export interface RecordMovementInput {
  productId: string;
  type: MovementType;
  /** Quantità in unità BASE. Per PHYSICAL è il delta firmato; per gli altri è positiva. */
  qty: number;
  reason?: string;
  orderId?: string;
  createdBy?: string;
}

/**
 * Applica un movimento di magazzino DENTRO una transazione: aggiorna la giacenza
 * e storicizza in StockMovement. Ritorna la giacenza risultante.
 *
 * Non permette di scendere sotto zero (la giacenza viene azzerata e il delta reale
 * registrato è quello effettivamente applicato) per gli scarichi automatici da vendita;
 * per gli altri tipi solleva errore se il risultato è negativo, così l'operatore se ne accorge.
 */
export async function recordMovement(tx: Tx, venueId: string, input: RecordMovementInput): Promise<number> {
  const product = await tx.product.findFirst({
    where: { id: input.productId, venueId },
    include: { stock: true },
  });
  if (!product) throw new InventoryError(404, 'Prodotto non trovato');

  const stock = product.stock ?? (await tx.stockItem.create({ data: { productId: product.id, quantity: 0 } }));

  const signedDelta = input.type === 'PHYSICAL' ? Math.trunc(input.qty) : movementSign(input.type) * Math.abs(Math.trunc(input.qty));

  let qtyAfter = stock.quantity + signedDelta;
  let appliedDelta = signedDelta;

  if (qtyAfter < 0) {
    if (input.type === 'SALE') {
      // scarico automatico: non blocchiamo la vendita, azzeriamo e logghiamo il reale.
      appliedDelta = -stock.quantity;
      qtyAfter = 0;
    } else {
      throw new InventoryError(409, `Giacenza insufficiente: ${stock.quantity} disponibili`);
    }
  }

  await tx.stockItem.update({ where: { id: stock.id }, data: { quantity: qtyAfter } });
  await tx.stockMovement.create({
    data: {
      productId: product.id,
      type: input.type,
      qtyDelta: appliedDelta,
      qtyAfter,
      reason: input.reason,
      orderId: input.orderId,
      createdBy: input.createdBy,
    },
  });
  return qtyAfter;
}

export class InventoryError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Livello target effettivo: parLevel se impostato, altrimenti reorderLevel. */
export function effectiveParLevel(parLevel: number, reorderLevel: number): number {
  return parLevel > 0 ? parLevel : reorderLevel;
}
