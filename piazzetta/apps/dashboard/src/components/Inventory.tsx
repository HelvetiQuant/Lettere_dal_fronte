import { useEffect, useState } from 'react';
import { inv, type StockRow, type Movement } from '../api';

const MOV_LABEL: Record<string, string> = {
  LOAD: 'Carico', WASTE: 'Scarto', RETURN: 'Reso', PHYSICAL: 'Inventario', SALE: 'Vendita', RECEIPT: 'Ricezione',
};

function AdjustForm({ row, onDone }: { row: StockRow; onDone: () => void }) {
  const [type, setType] = useState<'LOAD' | 'WASTE' | 'RETURN' | 'PHYSICAL'>('LOAD');
  const [qty, setQty] = useState('');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');

  async function submit() {
    const n = parseInt(qty, 10);
    if (!Number.isFinite(n) || (type !== 'PHYSICAL' && n <= 0)) { setErr('Quantità non valida'); return; }
    try {
      await inv.addMovement({ productId: row.productId, type, qty: n, reason: reason || undefined });
      setQty(''); setReason(''); setErr('');
      onDone();
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <select value={type} onChange={(e) => setType(e.target.value as any)}>
        <option value="LOAD">Carico</option>
        <option value="WASTE">Scarto</option>
        <option value="RETURN">Reso</option>
        <option value="PHYSICAL">Inventario (delta ±)</option>
      </select>
      <input placeholder="Qtà" value={qty} onChange={(e) => setQty(e.target.value)} style={{ width: 70 }} />
      <input placeholder="Causale" value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: 120 }} />
      <button onClick={submit}>Registra</button>
      {err && <span style={{ color: '#c62828', fontSize: 12 }}>{err}</span>}
    </div>
  );
}

export default function Inventory() {
  const [rows, setRows] = useState<StockRow[]>([]);
  const [lowCount, setLowCount] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [onlyLow, setOnlyLow] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    try {
      const d = await inv.stock();
      setRows(d.items);
      setLowCount(d.lowCount);
      setError('');
    } catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { load(); }, []);

  async function toggleHistory(productId: string) {
    if (expanded === productId) { setExpanded(null); return; }
    setExpanded(productId);
    setMovements(await inv.movements(productId));
  }

  const visible = onlyLow ? rows.filter((r) => r.low) : rows;

  return (
    <section>
      <h2>Magazzino {lowCount > 0 && <span style={{ color: '#c62828', fontSize: 14 }}>· {lowCount} sotto soglia</span>}</h2>
      <label style={{ display: 'block', marginBottom: 10 }}>
        <input type="checkbox" checked={onlyLow} onChange={(e) => setOnlyLow(e.target.checked)} /> solo sotto soglia
      </label>
      {error && <p style={{ color: '#c62828' }}>{error}</p>}
      <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', fontSize: 14 }}>
        <thead><tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
          <th style={{ padding: 8 }}>Prodotto</th>
          <th style={{ padding: 8, textAlign: 'right' }}>Giacenza</th>
          <th style={{ padding: 8, textAlign: 'right' }}>Soglia</th>
          <th style={{ padding: 8, textAlign: 'right' }}>Target</th>
          <th style={{ padding: 8 }}>Rettifica</th>
        </tr></thead>
        <tbody>
          {visible.map((r) => (
            <>
              <tr key={r.productId} style={{ borderTop: '1px solid #eee', background: r.low ? '#fff3f3' : undefined }}>
                <td style={{ padding: 8 }}>
                  <button onClick={() => toggleHistory(r.productId)} style={{ border: 0, background: 'none', cursor: 'pointer', fontWeight: 600 }}>
                    {expanded === r.productId ? '▾ ' : '▸ '}{r.name}
                  </button>
                  {r.low && <span style={{ marginLeft: 6, fontSize: 11, color: '#fff', background: '#c62828', padding: '1px 6px', borderRadius: 8 }}>SOTTO SOGLIA</span>}
                </td>
                <td style={{ padding: 8, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{r.quantity} {r.unit}</td>
                <td style={{ padding: 8, textAlign: 'right', color: '#888' }}>{r.reorderLevel || '—'}</td>
                <td style={{ padding: 8, textAlign: 'right', color: '#888' }}>{r.parLevel || '—'}</td>
                <td style={{ padding: 8 }}><AdjustForm row={r} onDone={async () => { await load(); if (expanded === r.productId) setMovements(await inv.movements(r.productId)); }} /></td>
              </tr>
              {expanded === r.productId && (
                <tr>
                  <td colSpan={5} style={{ padding: '4px 16px 12px', background: '#fafafa' }}>
                    <strong style={{ fontSize: 13 }}>Ultimi movimenti</strong>
                    <table style={{ width: '100%', fontSize: 12, marginTop: 4 }}>
                      <tbody>
                        {movements.map((m) => (
                          <tr key={m.id}>
                            <td>{new Date(m.createdAt).toLocaleString('it-IT')}</td>
                            <td>{MOV_LABEL[m.type] ?? m.type}</td>
                            <td style={{ color: m.qtyDelta < 0 ? '#c62828' : '#2e7d32' }}>{m.qtyDelta > 0 ? '+' : ''}{m.qtyDelta}</td>
                            <td>→ {m.qtyAfter}</td>
                            <td style={{ color: '#888' }}>{m.reason ?? ''}</td>
                          </tr>
                        ))}
                        {movements.length === 0 && <tr><td style={{ color: '#999' }}>Nessun movimento.</td></tr>}
                      </tbody>
                    </table>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </section>
  );
}
