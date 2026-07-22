/**
 * Calcolo dei tempi di preparazione — logica pura, senza DB, così è testabile
 * a runtime e riusabile lato dashboard.
 *
 * Le metriche, tutte in secondi:
 *  - queueSec : sentAt  -> startedAt  (attesa in coda alla postazione)
 *  - prepSec  : startedAt -> readyAt  (preparazione vera e propria)
 *  - stationSec: sentAt -> readyAt    (tempo totale alla postazione)
 *  - deliverySec (solo a livello ordine): placedAt -> servedAt
 *                (dal momento in cui il cameriere prende la comanda al tavolo
 *                 a quando è interamente consegnata al tavolo)
 */

export interface ItemTiming {
  productId: string;
  productName: string;
  category: string;
  station: string;
  sentAt: Date | string | null;
  startedAt: Date | string | null;
  readyAt: Date | string | null;
  servedAt: Date | string | null;
}

export interface OrderTiming {
  placedAt: Date | string | null;
  servedAt: Date | string | null;
}

function ms(d: Date | string | null): number | null {
  if (!d) return null;
  const t = typeof d === 'string' ? Date.parse(d) : d.getTime();
  return Number.isFinite(t) ? t : null;
}

/** Differenza in secondi tra due istanti, o null se uno manca o è negativa. */
export function diffSec(from: Date | string | null, to: Date | string | null): number | null {
  const a = ms(from);
  const b = ms(to);
  if (a === null || b === null) return null;
  const s = (b - a) / 1000;
  return s >= 0 ? s : null;
}

/** Percentile (0..100) con interpolazione lineare. Ritorna null su input vuoto. */
export function percentile(values: number[], p: number): number | null {
  const xs = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (xs.length === 0) return null;
  if (xs.length === 1) return xs[0];
  const rank = (p / 100) * (xs.length - 1);
  const lo = Math.floor(rank);
  const hi = Math.ceil(rank);
  if (lo === hi) return xs[lo];
  const w = rank - lo;
  return xs[lo] * (1 - w) + xs[hi] * w;
}

export function mean(values: number[]): number | null {
  const xs = values.filter((v) => Number.isFinite(v));
  if (xs.length === 0) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

export interface Summary {
  count: number;
  avgSec: number | null;
  medianSec: number | null;
  p90Sec: number | null;
  minSec: number | null;
  maxSec: number | null;
}

export function summarize(values: number[]): Summary {
  const xs = values.filter((v) => Number.isFinite(v));
  return {
    count: xs.length,
    avgSec: round(mean(xs)),
    medianSec: round(percentile(xs, 50)),
    p90Sec: round(percentile(xs, 90)),
    minSec: xs.length ? round(Math.min(...xs)) : null,
    maxSec: xs.length ? round(Math.max(...xs)) : null,
  };
}

function round(v: number | null): number | null {
  return v === null ? null : Math.round(v);
}

export interface GroupStats {
  key: string;
  label: string;
  station?: string;
  queue: Summary;
  prep: Summary;
  stationTotal: Summary;
}

export type GroupBy = 'station' | 'category' | 'product';

/** Aggrega i tempi delle righe per station / category / product. */
export function aggregateItems(items: ItemTiming[], groupBy: GroupBy): GroupStats[] {
  const buckets = new Map<string, { label: string; station?: string; queue: number[]; prep: number[]; total: number[] }>();

  for (const it of items) {
    let key: string;
    let label: string;
    if (groupBy === 'station') {
      key = it.station;
      label = it.station;
    } else if (groupBy === 'category') {
      key = it.category || 'generic';
      label = it.category || 'generic';
    } else {
      key = it.productId;
      label = it.productName;
    }

    let b = buckets.get(key);
    if (!b) {
      b = { label, station: it.station, queue: [], prep: [], total: [] };
      buckets.set(key, b);
    }
    const q = diffSec(it.sentAt, it.startedAt);
    const p = diffSec(it.startedAt, it.readyAt);
    const t = diffSec(it.sentAt, it.readyAt);
    if (q !== null) b.queue.push(q);
    if (p !== null) b.prep.push(p);
    if (t !== null) b.total.push(t);
  }

  return Array.from(buckets.entries())
    .map(([key, b]) => ({
      key,
      label: b.label,
      station: b.station,
      queue: summarize(b.queue),
      prep: summarize(b.prep),
      stationTotal: summarize(b.total),
    }))
    .sort((a, b) => (b.stationTotal.count - a.stationTotal.count));
}

/** Tempo ordine->consegna al tavolo, aggregato su tutti gli ordini. */
export function aggregateDelivery(orders: OrderTiming[]): Summary {
  const xs: number[] = [];
  for (const o of orders) {
    const d = diffSec(o.placedAt, o.servedAt);
    if (d !== null) xs.push(d);
  }
  return summarize(xs);
}

/** Formatta secondi in "m:ss" per la UI. */
export function fmtSec(sec: number | null): string {
  if (sec === null) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}
