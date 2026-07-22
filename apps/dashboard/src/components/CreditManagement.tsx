import { useEffect, useState } from 'react';
import { api, type Customer, type CreditTx, fmtEuro } from '../api';

function euroToCents(v: string): number {
  const n = parseFloat(v.replace(',', '.'));
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

// --- Form inserimento manuale nuovo cliente creditore ---
function NewCustomerForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [limit, setLimit] = useState('');
  const [opening, setOpening] = useState('');
  const [err, setErr] = useState('');

  async function submit() {
    if (!name.trim()) { setErr('Nome obbligatorio'); return; }
    try {
      await api.createCustomer({
        name: name.trim(),
        phone: phone.trim() || undefined,
        limitCents: euroToCents(limit),
        openingBalanceCents: euroToCents(opening),
      });
      setName(''); setPhone(''); setLimit(''); setOpening(''); setErr(''); setOpen(false);
      onCreated();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  if (!open) return <button onClick={() => setOpen(true)}>+ Nuovo cliente a credito</button>;
  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 12, background: '#fafafa', maxWidth: 460 }}>
      <h4 style={{ marginTop: 0 }}>Nuovo cliente creditore</h4>
      <div style={{ display: 'grid', gap: 8 }}>
        <input placeholder="Nome e cognome *" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Telefono (opzionale)" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <label style={{ fontSize: 13 }}>Limite fido € (0 = nessun limite)
          <input placeholder="0,00" value={limit} onChange={(e) => setLimit(e.target.value)} style={{ width: '100%' }} />
        </label>
        <label style={{ fontSize: 13 }}>Debito pregresso € (opzionale)
          <input placeholder="0,00" value={opening} onChange={(e) => setOpening(e.target.value)} style={{ width: '100%' }} />
        </label>
      </div>
      {err && <p style={{ color: '#c62828' }}>{err}</p>}
      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
        <button onClick={submit}>Salva</button>
        <button onClick={() => setOpen(false)}>Annulla</button>
      </div>
    </div>
  );
}

// --- Pannello movimento (addebito / pagamento) ---
function CustomerDetail({ id, onChange }: { id: string; onChange: () => void }) {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [txs, setTxs] = useState<CreditTx[]>([]);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');

  async function load() {
    const d = await api.customerDetail(id);
    setCustomer(d.customer);
    setTxs(d.transactions);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  async function move(type: 'CHARGE' | 'PAYMENT', method?: 'CASH' | 'POS') {
    const cents = euroToCents(amount);
    if (cents <= 0) { setErr('Importo non valido'); return; }
    try {
      await api.addTransaction(id, { type, amountCents: cents, method, note: note.trim() || undefined });
      setAmount(''); setNote(''); setErr('');
      await load();
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  if (!customer) return <p>Caricamento…</p>;
  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 14, background: '#fff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h3 style={{ margin: 0 }}>{customer.name}</h3>
        <strong style={{ fontSize: 22, color: customer.balanceCents > 0 ? '#c62828' : '#2e7d32' }}>{fmtEuro(customer.balanceCents)}</strong>
      </div>
      <div style={{ fontSize: 12, color: '#888' }}>
        {customer.phone || 'nessun telefono'} · limite {customer.limitCents ? fmtEuro(customer.limitCents) : 'nessuno'}
      </div>

      <div style={{ display: 'flex', gap: 8, margin: '12px 0', flexWrap: 'wrap', alignItems: 'center' }}>
        <input placeholder="Importo €" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 100 }} />
        <input placeholder="Causale (opz.)" value={note} onChange={(e) => setNote(e.target.value)} />
        <button onClick={() => move('CHARGE')} style={{ background: '#c62828', color: '#fff', border: 0, padding: '6px 10px', borderRadius: 6 }}>Addebita</button>
        <button onClick={() => move('PAYMENT', 'CASH')} style={{ background: '#2e7d32', color: '#fff', border: 0, padding: '6px 10px', borderRadius: 6 }}>Incassa contanti</button>
        <button onClick={() => move('PAYMENT', 'POS')} style={{ background: '#1565c0', color: '#fff', border: 0, padding: '6px 10px', borderRadius: 6 }}>Incassa POS</button>
      </div>
      {err && <p style={{ color: '#c62828' }}>{err}</p>}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead><tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
          <th style={{ padding: 6 }}>Data</th><th style={{ padding: 6 }}>Tipo</th>
          <th style={{ padding: 6, textAlign: 'right' }}>Importo</th><th style={{ padding: 6, textAlign: 'right' }}>Saldo</th>
        </tr></thead>
        <tbody>
          {txs.map((t) => (
            <tr key={t.id} style={{ borderTop: '1px solid #eee' }}>
              <td style={{ padding: 6 }}>{new Date(t.createdAt).toLocaleString('it-IT')}</td>
              <td style={{ padding: 6 }}>{t.type === 'CHARGE' ? 'Addebito' : t.type === 'PAYMENT' ? `Pagamento${t.method ? ' ' + t.method : ''}` : 'Rettifica'}</td>
              <td style={{ padding: 6, textAlign: 'right', color: t.type === 'CHARGE' ? '#c62828' : '#2e7d32' }}>
                {t.type === 'CHARGE' ? '+' : '−'}{fmtEuro(t.amountCents)}
              </td>
              <td style={{ padding: 6, textAlign: 'right' }}>{fmtEuro(t.balanceAfterCents)}</td>
            </tr>
          ))}
          {txs.length === 0 && <tr><td colSpan={4} style={{ padding: 10, color: '#999' }}>Nessun movimento.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function CreditManagement() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [onlyDebtors, setOnlyDebtors] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');

  async function load() {
    try {
      const d = await api.customers({ debtors: onlyDebtors, q: search || undefined });
      setCustomers(d.customers);
      setTotal(d.totalOutstandingCents);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [onlyDebtors, search]);

  return (
    <section>
      <h2>Crediti clienti (conti aperti)</h2>
      <div style={{ marginBottom: 12, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <span>Totale a credito: <strong style={{ color: '#c62828' }}>{fmtEuro(total)}</strong></span>
        <label><input type="checkbox" checked={onlyDebtors} onChange={(e) => setOnlyDebtors(e.target.checked)} /> solo con debito</label>
        <input placeholder="Cerca cliente…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <NewCustomerForm onCreated={load} />
      {error && <p style={{ color: '#c62828' }}>{error}</p>}

      <div style={{ display: 'flex', gap: 20, marginTop: 14, alignItems: 'flex-start' }}>
        <div style={{ flex: '0 0 320px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', fontSize: 14 }}>
            <thead><tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
              <th style={{ padding: 8 }}>Cliente</th><th style={{ padding: 8, textAlign: 'right' }}>Saldo</th>
            </tr></thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id} onClick={() => setSelected(c.id)}
                  style={{ cursor: 'pointer', borderTop: '1px solid #eee', background: selected === c.id ? '#e3f2fd' : undefined }}>
                  <td style={{ padding: 8 }}>{c.name}</td>
                  <td style={{ padding: 8, textAlign: 'right', color: c.balanceCents > 0 ? '#c62828' : '#2e7d32' }}>{fmtEuro(c.balanceCents)}</td>
                </tr>
              ))}
              {customers.length === 0 && <tr><td colSpan={2} style={{ padding: 12, color: '#999' }}>Nessun cliente.</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ flex: 1 }}>
          {selected ? <CustomerDetail id={selected} onChange={load} /> : <p style={{ color: '#999' }}>Seleziona un cliente per vedere l'estratto conto e registrare movimenti.</p>}
        </div>
      </div>
    </section>
  );
}
