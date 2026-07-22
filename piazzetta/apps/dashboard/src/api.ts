// Client API condiviso della dashboard proprietario.
const API = (import.meta.env.VITE_API_URL as string | undefined) || '/api/v1';

// In dev usiamo gli header dev-auth con ruolo OWNER (accesso completo).
const HEADERS = {
  'content-type': 'application/json',
  'x-venue-id': 'venue_piazzetta',
  'x-user-id': 'u_owner',
  'x-user-roles': 'OWNER',
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...HEADERS, ...(init?.headers ?? {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as any).error || `Errore ${res.status}`);
  return data as T;
}

// ---- Tipi ----
export type Station = 'BAR' | 'TAVOLA_CALDA';

export interface BoardItem {
  id: string;
  name: string;
  quantity: number;
  station: Station;
  status: string;
}
export interface BoardOrder {
  id: string;
  table: string;
  status: string;
  placedAt: string;
  waitingSec: number;
  items: BoardItem[];
}
export interface Board {
  BAR: BoardOrder[];
  TAVOLA_CALDA: BoardOrder[];
}

export interface Summary {
  count: number;
  avgSec: number | null;
  medianSec: number | null;
  p90Sec: number | null;
  minSec: number | null;
  maxSec: number | null;
}
export interface GroupStats {
  key: string;
  label: string;
  station?: string;
  queue: Summary;
  prep: Summary;
  stationTotal: Summary;
}
export interface PrepStats {
  range: { from: string; to: string };
  groupBy: 'station' | 'category' | 'product';
  station: string;
  groups: GroupStats[];
  delivery: Summary;
  byStation: { station: Station; stationTotal: Summary }[];
}

export interface Customer {
  id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  notes?: string | null;
  balanceCents: number;
  limitCents: number;
  active: boolean;
}
export interface CreditTx {
  id: string;
  type: 'CHARGE' | 'PAYMENT' | 'ADJUST';
  amountCents: number;
  balanceAfterCents: number;
  method?: string | null;
  note?: string | null;
  createdAt: string;
}

// ---- Endpoint ----
export const api = {
  board: () => req<Board>('/orders-tables/board'),

  prepStats: (p: { groupBy?: string; station?: string; from?: string; to?: string } = {}) => {
    const qs = new URLSearchParams();
    if (p.groupBy) qs.set('groupBy', p.groupBy);
    if (p.station) qs.set('station', p.station);
    if (p.from) qs.set('from', p.from);
    if (p.to) qs.set('to', p.to);
    return req<PrepStats>(`/stats/prep-times?${qs.toString()}`);
  },

  customers: (opts: { debtors?: boolean; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (opts.debtors) qs.set('debtors', 'true');
    if (opts.q) qs.set('q', opts.q);
    return req<{ customers: Customer[]; totalOutstandingCents: number }>(`/credit/customers?${qs.toString()}`);
  },
  customerDetail: (id: string) => req<{ customer: Customer; transactions: CreditTx[] }>(`/credit/customers/${id}`),
  createCustomer: (body: Record<string, unknown>) =>
    req<Customer>('/credit/customers', { method: 'POST', body: JSON.stringify(body) }),
  addTransaction: (id: string, body: Record<string, unknown>) =>
    req<{ customer: Customer; transaction: CreditTx }>(`/credit/customers/${id}/transactions`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};

// ---- Magazzino ----
export interface StockRow {
  productId: string;
  name: string;
  category: string;
  unit: string;
  quantity: number;
  reorderLevel: number;
  parLevel: number;
  low: boolean;
}
export interface Movement {
  id: string;
  type: string;
  qtyDelta: number;
  qtyAfter: number;
  reason?: string | null;
  createdAt: string;
  product: { name: string; unit: string };
}

// ---- Fornitori ----
export interface Supplier {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  active: boolean;
  _count?: { listings: number };
}
export interface Listing {
  id: string;
  productId: string;
  supplierSku?: string | null;
  packSize: number;
  packPriceCents: number;
  leadTimeDays: number;
  preferred: boolean;
  product: { name: string; unit: string };
}
export interface ProposalLine {
  productId: string;
  name: string;
  unit: string;
  quantity: number;
  reorderLevel: number;
  targetLevel: number;
  packSize: number;
  packs: number;
  orderedBase: number;
  packPriceCents: number;
  lineCostCents: number;
}
export interface Proposal {
  supplierId: string;
  supplierName: string;
  lines: ProposalLine[];
  totalCents: number;
}

export interface PoItem {
  id: string;
  productId: string;
  packSize: number;
  packsOrdered: number;
  packsReceived: number;
  packPriceCents: number;
  product: { name: string; unit: string };
}
export interface PurchaseOrder {
  id: string;
  status: string;
  totalCents: number;
  note?: string | null;
  supplier: { name: string };
  items: PoItem[];
  sentAt?: string | null;
  receivedAt?: string | null;
  createdAt: string;
}

// Endpoint magazzino/fornitori (namespace separato).
export const inv = {
  // magazzino
  stock: () => req<{ items: StockRow[]; lowCount: number }>('/inventory/stock'),
  movements: (productId?: string) =>
    req<Movement[]>(`/inventory/movements${productId ? `?productId=${productId}` : ''}`),
  addMovement: (body: Record<string, unknown>) =>
    req<{ productId: string; quantity: number }>('/inventory/movements', { method: 'POST', body: JSON.stringify(body) }),
  setLevels: (productId: string, body: Record<string, unknown>) =>
    req(`/inventory/stock/${productId}/levels`, { method: 'PATCH', body: JSON.stringify(body) }),
  // fornitori
  suppliers: () => req<Supplier[]>('/suppliers'),
  createSupplier: (body: Record<string, unknown>) => req<Supplier>('/suppliers', { method: 'POST', body: JSON.stringify(body) }),
  listings: (id: string) => req<Listing[]>(`/suppliers/${id}/listings`),
  addListing: (id: string, body: Record<string, unknown>) =>
    req<Listing>(`/suppliers/${id}/listings`, { method: 'POST', body: JSON.stringify(body) }),
  reorderProposals: () =>
    req<{ proposals: Proposal[]; unassigned: { productId: string; name: string; deficitBase: number }[] }>(
      '/suppliers/reorder-proposals',
    ),
  // ordini d'acquisto
  purchaseOrders: (status?: string) =>
    req<PurchaseOrder[]>(`/purchase-orders${status ? `?status=${status}` : ''}`),
  createPurchaseOrder: (body: Record<string, unknown>) =>
    req<PurchaseOrder>('/purchase-orders', { method: 'POST', body: JSON.stringify(body) }),
  sendPurchaseOrder: (id: string) => req<PurchaseOrder>(`/purchase-orders/${id}/send`, { method: 'POST' }),
  cancelPurchaseOrder: (id: string) => req<PurchaseOrder>(`/purchase-orders/${id}/cancel`, { method: 'POST' }),
  receivePurchaseOrder: (id: string, lines: { itemId: string; packs: number }[]) =>
    req<PurchaseOrder>(`/purchase-orders/${id}/receive`, { method: 'POST', body: JSON.stringify({ lines }) }),
};

export function fmtSec(sec: number | null): string {
  if (sec === null || sec === undefined) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}
export function fmtEuro(cents: number): string {
  return '€ ' + (cents / 100).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
