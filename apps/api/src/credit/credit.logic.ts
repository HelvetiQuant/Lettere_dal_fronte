/**
 * Contabilità del credito cliente — logica pura, testabile senza DB.
 *
 * Convenzione: `balanceCents` > 0 significa che il cliente DEVE soldi al locale
 * (conto aperto). Un addebito (CHARGE) aumenta il saldo, un pagamento (PAYMENT)
 * lo riduce, una rettifica (ADJUST) può fare entrambi.
 */

export type CreditTxType = 'CHARGE' | 'PAYMENT' | 'ADJUST';

export interface ApplyInput {
  currentBalanceCents: number;
  limitCents: number; // 0 = nessun limite
  type: CreditTxType;
  amountCents: number; // per CHARGE/PAYMENT positivo; per ADJUST può essere +/-
}

export interface ApplyResult {
  ok: boolean;
  newBalanceCents: number;
  error?: string;
}

/**
 * Calcola il nuovo saldo applicando una transazione, validando il limite di fido.
 * Non tocca il DB: restituisce solo il risultato da persistere.
 */
export function applyTransaction(input: ApplyInput): ApplyResult {
  const { currentBalanceCents, limitCents, type, amountCents } = input;

  if (type === 'CHARGE' || type === 'PAYMENT') {
    if (!Number.isFinite(amountCents) || amountCents <= 0) {
      return { ok: false, newBalanceCents: currentBalanceCents, error: 'Importo non valido' };
    }
  }

  let delta: number;
  if (type === 'CHARGE') delta = amountCents;
  else if (type === 'PAYMENT') delta = -amountCents;
  else delta = amountCents; // ADJUST: segno libero

  const newBalance = currentBalanceCents + delta;

  // Un pagamento non può portare il saldo sotto zero (non si "paga" più del dovuto
  // trasformandolo in credito a favore del cliente: quello è un ADJUST esplicito).
  if (type === 'PAYMENT' && newBalance < 0) {
    return {
      ok: false,
      newBalanceCents: currentBalanceCents,
      error: `Pagamento superiore al dovuto (saldo ${currentBalanceCents})`,
    };
  }

  // Limite di fido: un addebito non può superare il limite (se impostato > 0).
  if ((type === 'CHARGE' || type === 'ADJUST') && delta > 0 && limitCents > 0 && newBalance > limitCents) {
    return {
      ok: false,
      newBalanceCents: currentBalanceCents,
      error: `Limite di fido superato (limite ${limitCents}, richiesto ${newBalance})`,
    };
  }

  return { ok: true, newBalanceCents: newBalance };
}

/** Formatta centesimi in euro "€ 12,50". */
export function fmtEuro(cents: number): string {
  return '€ ' + (cents / 100).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
