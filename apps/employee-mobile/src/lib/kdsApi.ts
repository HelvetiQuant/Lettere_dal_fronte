// Client KDS per l'app dipendenti (Expo/React Native).
// L'URL API arriva da EXPO_PUBLIC_API_URL (vedi FRONTEND.md).
const API = (process.env.EXPO_PUBLIC_API_URL as string | undefined) || 'http://localhost:3000/api/v1';

// In produzione questi header sono sostituiti dal JWT reale (Authorization: Bearer).
// In dev usiamo l'header dev-auth con il ruolo della postazione.
function headers(role: 'BARMAN' | 'COOK') {
  return {
    'content-type': 'application/json',
    'x-venue-id': 'venue_piazzetta',
    'x-user-id': role === 'BARMAN' ? 'u_bar' : 'u_cook',
    'x-user-roles': `${role},WAITER`,
  };
}

export type Station = 'BAR' | 'TAVOLA_CALDA';

export interface KdsItem {
  id: string;
  name: string;
  quantity: number;
  station: Station;
  status: string;
}
export interface KdsOrder {
  id: string;
  table: string;
  status: string;
  placedAt: string;
  waitingSec: number;
  items: KdsItem[];
}

const roleFor = (s: Station): 'BARMAN' | 'COOK' => (s === 'BAR' ? 'BARMAN' : 'COOK');

/** Comande della postazione, con solo le sue righe. */
export async function fetchBoard(station: Station): Promise<KdsOrder[]> {
  const res = await fetch(`${API}/orders-tables/board?station=${station}`, { headers: headers(roleFor(station)) });
  if (!res.ok) throw new Error(`Errore ${res.status}`);
  const data = await res.json();
  return (data.orders ?? []) as KdsOrder[];
}

/**
 * Avanza lo stato di una singola riga. Registrare IN_PREPARATION è ciò che
 * popola il tempo di CODA nelle statistiche; READY il tempo di PREP.
 */
export async function advanceItem(station: Station, itemId: string, status: 'IN_PREPARATION' | 'READY' | 'SERVED'): Promise<void> {
  const res = await fetch(`${API}/orders-tables/order-items/${itemId}/status`, {
    method: 'PATCH',
    headers: headers(roleFor(station)),
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.error || `Errore ${res.status}`);
  }
}

/** Prossimo stato nel ciclo della riga (null se già consegnata). */
export function nextItemStatus(status: string): 'IN_PREPARATION' | 'READY' | 'SERVED' | null {
  switch (status) {
    case 'PENDING':
      return 'IN_PREPARATION';
    case 'IN_PREPARATION':
      return 'READY';
    case 'READY':
      return 'SERVED';
    default:
      return null;
  }
}

export const ITEM_ACTION_LABEL: Record<string, string> = {
  IN_PREPARATION: 'Prendi in preparazione',
  READY: 'Segna pronto',
  SERVED: 'Segna consegnato',
};
