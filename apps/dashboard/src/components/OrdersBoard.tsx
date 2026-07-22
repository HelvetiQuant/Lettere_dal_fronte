import { useEffect, useState } from 'react';
import { api, type Board, type BoardOrder, fmtSec } from '../api';

// Colore dell'attesa: verde < 5', giallo < 10', rosso oltre.
function waitColor(sec: number): string {
  if (sec < 300) return '#2e7d32';
  if (sec < 600) return '#f9a825';
  return '#c62828';
}

function Column({ title, accent, orders }: { title: string; accent: string; orders: BoardOrder[] }) {
  return (
    <div style={{ flex: 1, minWidth: 300 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ width: 12, height: 12, borderRadius: 3, background: accent }} />
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span style={{ color: '#666' }}>({orders.length})</span>
      </div>
      {orders.length === 0 && <p style={{ color: '#999' }}>Nessuna comanda in coda.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {orders.map((o) => (
          <div key={o.id} style={{ border: `1px solid ${accent}44`, borderLeft: `4px solid ${accent}`, borderRadius: 8, padding: 10, background: '#fff' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <strong>{o.table}</strong>
              <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600, color: waitColor(o.waitingSec) }}>
                {fmtSec(o.waitingSec)}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>#{o.id.slice(-6)} · {o.status}</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {o.items.map((it) => (
                <li key={it.id}>
                  {it.name} × {it.quantity}
                  <span style={{ fontSize: 11, color: '#999' }}> · {it.status}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function OrdersBoard() {
  const [board, setBoard] = useState<Board>({ BAR: [], TAVOLA_CALDA: [] });
  const [error, setError] = useState('');

  async function load() {
    try {
      setBoard(await api.board());
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <section>
      <h2>Comande in tempo reale</h2>
      {error && <p style={{ color: '#c62828' }}>{error}</p>}
      <div style={{ display: 'flex', gap: 20 }}>
        <Column title="Bar" accent="#1565c0" orders={board.BAR} />
        <Column title="Tavola calda" accent="#e65100" orders={board.TAVOLA_CALDA} />
      </div>
    </section>
  );
}
