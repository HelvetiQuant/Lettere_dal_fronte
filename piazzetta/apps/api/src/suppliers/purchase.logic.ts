/**
 * Logica pura del ciclo ordine d'acquisto — testabile senza DB.
 *
 * Stati: DRAFT -> SENT -> PARTIAL -> RECEIVED, con CANCELLED da DRAFT/SENT.
 */

export type PoStatus = 'DRAFT' | 'SENT' | 'PARTIAL' | 'RECEIVED' | 'CANCELLED';

const PO_TRANSITIONS: Record<PoStatus, PoStatus[]> = {
  DRAFT: ['SENT', 'CANCELLED'],
  SENT: ['PARTIAL', 'RECEIVED', 'CANCELLED'],
  PARTIAL: ['PARTIAL', 'RECEIVED', 'CANCELLED'],
  RECEIVED: [],
  CANCELLED: [],
};

export function canPoTransition(from: PoStatus, to: PoStatus): boolean {
  return PO_TRANSITIONS[from].includes(to);
}

export interface PoItemState {
  packsOrdered: number;
  packsReceived: number;
}

/** Righe ricevute in questo evento: quante confezioni aggiungere per riga. */
export interface ReceiptLine {
  itemId: string;
  packs: number; // confezioni ricevute ora (>0)
}

export interface ReceiptResultLine {
  itemId: string;
  newPacksReceived: number;
  /** confezioni effettivamente accettate (clampate al residuo ordinato) */
  acceptedPacks: number;
}

export interface ReceiptOutcome {
  lines: ReceiptResultLine[];
  /** stato complessivo dopo la ricezione */
  status: 'PARTIAL' | 'RECEIVED';
}

/**
 * Applica una ricezione: per ogni riga somma le confezioni ricevute (clampando al
 * residuo ordinato) e determina se l'ordine è completo o parziale.
 * `items` è lo stato attuale delle righe indicizzato per itemId.
 */
export function applyReceipt(
  items: Record<string, PoItemState>,
  received: ReceiptLine[],
): ReceiptOutcome {
  const receivedById = new Map(received.map((r) => [r.itemId, Math.max(0, Math.trunc(r.packs))]));
  const lines: ReceiptResultLine[] = [];
  let complete = true;

  for (const [itemId, state] of Object.entries(items)) {
    const add = receivedById.get(itemId) ?? 0;
    const residual = Math.max(0, state.packsOrdered - state.packsReceived);
    const accepted = Math.min(add, residual);
    const newReceived = state.packsReceived + accepted;
    if (newReceived < state.packsOrdered) complete = false;
    lines.push({ itemId, acceptedPacks: accepted, newPacksReceived: newReceived });
  }

  return { lines, status: complete ? 'RECEIVED' : 'PARTIAL' };
}
