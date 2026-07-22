import { useEffect, useState } from 'react';
import { api, type PrepStats, type GroupStats, fmtSec } from '../api';

type GroupBy = 'category' | 'product' | 'station';

function Bar({ sec, max, color }: { sec: number | null; max: number; color: string }) {
  const pct = sec && max > 0 ? Math.max(2, (sec / max) * 100) : 0;
  return (
    <div style={{ background: '#eee', borderRadius: 4, height: 18, position: 'relative', minWidth: 120 }}>
      <div style={{ width: `${pct}%`, background: color, height: '100%', borderRadius: 4 }} />
      <span style={{ position: 'absolute', right: 6, top: 0, fontSize: 11, lineHeight: '18px', color: '#333', fontVariantNumeric: 'tabular-nums' }}>
        {fmtSec(sec)}
      </span>
    </div>
  );
}

function StatRow({ g, max }: { g: GroupStats; max: number }) {
  return (
    <tr>
      <td style={{ padding: '6px 8px' }}>
        {g.label}
        {g.station && <span style={{ marginLeft: 6, fontSize: 10, color: '#fff', background: g.station === 'BAR' ? '#1565c0' : '#e65100', padding: '1px 6px', borderRadius: 8 }}>{g.station === 'BAR' ? 'Bar' : 'Cucina'}</span>}
      </td>
      <td style={{ padding: '6px 8px', textAlign: 'center' }}>{g.stationTotal.count}</td>
      <td style={{ padding: '6px 8px' }}><Bar sec={g.stationTotal.avgSec} max={max} color="#5c6bc0" /></td>
      <td style={{ padding: '6px 8px', textAlign: 'center', color: '#666' }}>{fmtSec(g.stationTotal.medianSec)}</td>
      <td style={{ padding: '6px 8px', textAlign: 'center', color: '#c62828' }}>{fmtSec(g.stationTotal.p90Sec)}</td>
      <td style={{ padding: '6px 8px', textAlign: 'center', color: '#888' }}>{fmtSec(g.queue.avgSec)}</td>
      <td style={{ padding: '6px 8px', textAlign: 'center', color: '#888' }}>{fmtSec(g.prep.avgSec)}</td>
    </tr>
  );
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 10, padding: '12px 16px', minWidth: 150, background: '#fff' }}>
      <div style={{ fontSize: 12, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#999' }}>{sub}</div>}
    </div>
  );
}

const RANGES: Record<string, number> = { 'Oggi': 24, '7 giorni': 24 * 7, '30 giorni': 24 * 30 };

export default function PrepTimeStats() {
  const [groupBy, setGroupBy] = useState<GroupBy>('category');
  const [station, setStation] = useState<'' | 'BAR' | 'TAVOLA_CALDA'>('');
  const [rangeLabel, setRangeLabel] = useState('Oggi');
  const [stats, setStats] = useState<PrepStats | null>(null);
  const [error, setError] = useState('');

  async function load() {
    try {
      const hours = RANGES[rangeLabel];
      const to = new Date();
      const from = new Date(to.getTime() - hours * 3600 * 1000);
      const data = await api.prepStats({
        groupBy,
        station: station || undefined,
        from: from.toISOString(),
        to: to.toISOString(),
      });
      setStats(data);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupBy, station, rangeLabel]);

  const max = stats ? Math.max(1, ...stats.groups.map((g) => g.stationTotal.avgSec ?? 0)) : 1;
  const bar = stats?.byStation.find((s) => s.station === 'BAR')?.stationTotal;
  const kit = stats?.byStation.find((s) => s.station === 'TAVOLA_CALDA')?.stationTotal;

  return (
    <section>
      <h2>Tempi di preparazione</h2>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
        <label>Periodo:{' '}
          <select value={rangeLabel} onChange={(e) => setRangeLabel(e.target.value)}>
            {Object.keys(RANGES).map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label>Raggruppa per:{' '}
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
            <option value="category">Tipologia (categoria)</option>
            <option value="product">Piatto / Cocktail</option>
            <option value="station">Postazione</option>
          </select>
        </label>
        <label>Postazione:{' '}
          <select value={station} onChange={(e) => setStation(e.target.value as any)}>
            <option value="">Tutte</option>
            <option value="BAR">Bar</option>
            <option value="TAVOLA_CALDA">Tavola calda</option>
          </select>
        </label>
        <button onClick={load}>Aggiorna</button>
      </div>

      {error && <p style={{ color: '#c62828' }}>{error}</p>}

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <KpiCard label="Ordine → consegna" value={fmtSec(stats?.delivery.medianSec ?? null)} sub={`mediana · ${stats?.delivery.count ?? 0} ordini`} />
        <KpiCard label="Bar (prep media)" value={fmtSec(bar?.avgSec ?? null)} sub={`${bar?.count ?? 0} righe`} />
        <KpiCard label="Tavola calda (prep media)" value={fmtSec(kit?.avgSec ?? null)} sub={`${kit?.count ?? 0} righe`} />
        <KpiCard label="P90 consegna" value={fmtSec(stats?.delivery.p90Sec ?? null)} sub="90° percentile" />
      </div>

      <table style={{ borderCollapse: 'collapse', width: '100%', background: '#fff', fontSize: 14 }}>
        <thead>
          <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
            <th style={{ padding: '8px' }}>Voce</th>
            <th style={{ padding: '8px', textAlign: 'center' }}>N.</th>
            <th style={{ padding: '8px' }}>Tempo medio (sent→ready)</th>
            <th style={{ padding: '8px', textAlign: 'center' }}>Mediana</th>
            <th style={{ padding: '8px', textAlign: 'center' }}>P90</th>
            <th style={{ padding: '8px', textAlign: 'center' }}>Coda</th>
            <th style={{ padding: '8px', textAlign: 'center' }}>Prep</th>
          </tr>
        </thead>
        <tbody>
          {stats?.groups.map((g) => <StatRow key={g.key} g={g} max={max} />)}
          {stats && stats.groups.length === 0 && (
            <tr><td colSpan={7} style={{ padding: 16, color: '#999', textAlign: 'center' }}>Nessun dato nel periodo selezionato.</td></tr>
          )}
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
        Coda = attesa prima della lavorazione (inviato→in preparazione). Prep = lavorazione (in preparazione→pronto).
        Tempo medio = inviato→pronto. Ordine→consegna = presa comanda al tavolo→servito al tavolo.
      </p>
    </section>
  );
}
