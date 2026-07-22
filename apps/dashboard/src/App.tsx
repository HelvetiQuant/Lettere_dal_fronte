import { useState } from 'react';
import OrdersBoard from './components/OrdersBoard';
import PrepTimeStats from './components/PrepTimeStats';
import CreditManagement from './components/CreditManagement';
import Inventory from './components/Inventory';
import Suppliers from './components/Suppliers';
import PurchaseOrders from './components/PurchaseOrders';

type Tab = 'board' | 'stats' | 'credit' | 'inventory' | 'suppliers' | 'purchases';

const TABS: { id: Tab; label: string }[] = [
  { id: 'board', label: 'Comande Bar / Tavola calda' },
  { id: 'stats', label: 'Tempi di preparazione' },
  { id: 'credit', label: 'Crediti clienti' },
  { id: 'inventory', label: 'Magazzino' },
  { id: 'suppliers', label: 'Fornitori / Riordino' },
  { id: 'purchases', label: "Ordini d'acquisto" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('board');

  return (
    <div style={{ fontFamily: 'system-ui', background: '#f4f5f7', minHeight: '100vh' }}>
      <header style={{ background: '#1a1a2e', color: '#fff', padding: '14px 24px', display: 'flex', alignItems: 'center', gap: 20 }}>
        <strong style={{ fontSize: 18 }}>La Piazzetta · Dashboard proprietario</strong>
        <nav style={{ display: 'flex', gap: 4 }}>
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                background: tab === t.id ? '#fff' : 'transparent',
                color: tab === t.id ? '#1a1a2e' : '#fff',
                border: '1px solid #ffffff55',
                borderRadius: 6,
                padding: '6px 12px',
                cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main style={{ padding: 24 }}>
        {tab === 'board' && <OrdersBoard />}
        {tab === 'stats' && <PrepTimeStats />}
        {tab === 'credit' && <CreditManagement />}
        {tab === 'inventory' && <Inventory />}
        {tab === 'suppliers' && <Suppliers />}
        {tab === 'purchases' && <PurchaseOrders />}
      </main>
    </div>
  );
}
