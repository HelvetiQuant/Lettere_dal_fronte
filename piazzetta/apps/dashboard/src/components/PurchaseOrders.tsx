import { useEffect, useState } from 'react';
import { inv, fmtEuro, type PurchaseOrder, type PoItem } from '../api';

const STATUS_LABEL: Record<string, string> = {
  DRAFT: 'Bozza', SENT: 'Inviato', PARTIAL: 'Ricevuto in parte', RECEIVED: 'Ricevuto', CANCELLED: 'Annullato',
};
const STATUS_COLOR: Record<string, string> = {
  DRAFT: '#888', SENT: '#1565c0', PARTIAL: '#f9a825', RECEIVED: '#2e7d32', CANCELLED: '#c62828',
};

// Pannello ricezione: per ogni riga si indicano le confezioni ricevute ora.
function ReceivePanel({ po, onDone }: { po: PurchaseOrder; onDone: () => void }) {
  const [qty, setQty] = useState<Record<string, string>>(() =>
    Object.fromEntries(po.items.map((i) => [i.id, String(Math.max(0, i.packsOrdered - i.packsReceived))])),
  );
  const [err, setErr] = useState('');

  async function submit() {
    const lines = po.items
      .map((i) => ({ itemId: i.id, packs: parseInt(qty[i.id] || '0', 10) || 0 }))
      .filter((l) => l.packs > 0);
    if (lines.length === 0) { setErr('Indica almeno una quantità'); return; }
    try {
      await inv.receivePurchaseOrder(po.id, lines);
      setErr('');
      onDone();
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div style={{ background: '#fafafa', padding: 10, borderRadius: 6, marginTop: 8 }}>
      <strong style={{ fontSize: 13 }}>Registra ricezione (confezioni)</strong>
      <table style={{ width: '100%', fontSize: 13, marginTop: 4 }}>
        <tbody>
          {po.items.map((i: PoItem) => (
            <tr key={i.id}>
              <td>{i.product.name}</td>
              <td style={{ color: '#888' }}>ricevute {i.packsReceived}/{i.packsOrdered}</td>
              <td style={{ textAlign: 'right' }}>
                <input value={qty[i.id]} onChange={(e) => setQty({ ...qty, [i.id]: e.target.value })} style={{ width: 60 }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {err && <p style={{ color: '#c62828', fontSize: 12 }}>{err}</p>}
      <button onClick={submit} style={{ marginTop: 6, background: '#2e7d32', color: '#fff', border: 0, padding: '6px 12px', borderRadius: 6 }}>Conferma ricezione</button>
    </div>
  );
}

export default function PurchaseOrders() {
  const [pos, setPos] = useState<PurchaseOrder[]>([]);
  const [receiving, setReceiving] = useState<string | null>(null);
  const [error, setError] = useState('');

  async function load() {
    try {
      setPos(await inv.purchaseOrders());
      setError('');
    } catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { load(); }, []);

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <section>
      <h2>Ordini d'acquisto</h2>
      <p style={{ color: '#888', fontSize: 13 }}>Gli ordini si generano dalle proposte di riordino (tab Fornitori) o manualmente via API.</p>
      {error && <p style={{ color: '#c62828' }}>{error}</p>}
      {pos.length === 0 && <p style={{ color: '#999' }}>Nessun ordine d'acquisto.</p>}

      {pos.map((po) => (
        <div key={po.id} style={{ background: '#fff', border: '1px solid #ddd', borderRadius: 8, padding: 12, marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              <strong>{po.supplier.name}</strong> · #{po.id.slice(-6)}{' '}
              <span style={{ fontSize: 12, color: '#fff', background: STATUS_COLOR[po.status], padding: '1px 8px', borderRadius: 8 }}>
                {STATUS_LABEL[po.status] ?? po.status}
              </span>
            </span>
            <strong>{fmtEuro(po.totalCents)}</strong>
          </div>
          <table style={{ width: '100%', fontSize: 13, marginTop: 6 }}>
            <tbody>
              {po.items.map((i) => (
                <tr key={i.id}>
                  <td>{i.product.name}</td>
                  <td>{i.packsOrdered} conf. × {i.packSize} {i.product.unit}</td>
                  <td style={{ color: '#888' }}>ricevute {i.packsReceived}</td>
                  <td style={{ textAlign: 'right' }}>{fmtEuro(i.packsOrdered * i.packPriceCents)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            {po.status === 'DRAFT' && <button onClick={() => act(() => inv.sendPurchaseOrder(po.id))}>Invia al fornitore</button>}
            {(po.status === 'SENT' || po.status === 'PARTIAL') && (
              <button onClick={() => setReceiving(receiving === po.id ? null : po.id)}>
                {receiving === po.id ? 'Chiudi' : 'Ricevi merce'}
              </button>
            )}
            {(po.status === 'DRAFT' || po.status === 'SENT') && (
              <button onClick={() => act(() => inv.cancelPurchaseOrder(po.id))} style={{ color: '#c62828' }}>Annulla</button>
            )}
          </div>
          {receiving === po.id && <ReceivePanel po={po} onDone={() => { setReceiving(null); load(); }} />}
        </div>
      ))}
    </section>
  );
}
