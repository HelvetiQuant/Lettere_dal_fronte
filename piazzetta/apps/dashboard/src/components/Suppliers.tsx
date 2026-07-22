import { useEffect, useState } from 'react';
import { inv, fmtEuro, type Supplier, type Listing, type StockRow, type Proposal } from '../api';

function euroToCents(v: string): number {
  const n = parseFloat(v.replace(',', '.'));
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

// ---- Anagrafica + listino di un fornitore ----
function SupplierListings({ supplier, products }: { supplier: Supplier; products: StockRow[] }) {
  const [listings, setListings] = useState<Listing[]>([]);
  const [productId, setProductId] = useState('');
  const [packSize, setPackSize] = useState('1');
  const [price, setPrice] = useState('');
  const [preferred, setPreferred] = useState(false);
  const [err, setErr] = useState('');

  async function load() { setListings(await inv.listings(supplier.id)); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [supplier.id]);

  async function add() {
    if (!productId) { setErr('Scegli un prodotto'); return; }
    try {
      await inv.addListing(supplier.id, {
        productId,
        packSize: parseInt(packSize, 10) || 1,
        packPriceCents: euroToCents(price),
        preferred,
      });
      setProductId(''); setPrice(''); setPackSize('1'); setPreferred(false); setErr('');
      load();
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div style={{ borderTop: '1px solid #eee', padding: '8px 0' }}>
      <table style={{ width: '100%', fontSize: 13 }}>
        <thead><tr style={{ textAlign: 'left', color: '#888' }}>
          <th>Prodotto</th><th>Confez.</th><th>Prezzo conf.</th><th>Pref.</th>
        </tr></thead>
        <tbody>
          {listings.map((l) => (
            <tr key={l.id}>
              <td>{l.product.name}</td>
              <td>{l.packSize} {l.product.unit}</td>
              <td>{fmtEuro(l.packPriceCents)}</td>
              <td>{l.preferred ? '★' : ''}</td>
            </tr>
          ))}
          {listings.length === 0 && <tr><td colSpan={4} style={{ color: '#999' }}>Nessun articolo a listino.</td></tr>}
        </tbody>
      </table>
      <div style={{ display: 'flex', gap: 6, marginTop: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={productId} onChange={(e) => setProductId(e.target.value)}>
          <option value="">— prodotto —</option>
          {products.map((p) => <option key={p.productId} value={p.productId}>{p.name}</option>)}
        </select>
        <input placeholder="Unità/conf." value={packSize} onChange={(e) => setPackSize(e.target.value)} style={{ width: 80 }} />
        <input placeholder="Prezzo € conf." value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: 100 }} />
        <label style={{ fontSize: 12 }}><input type="checkbox" checked={preferred} onChange={(e) => setPreferred(e.target.checked)} /> preferito</label>
        <button onClick={add}>+ Aggiungi</button>
        {err && <span style={{ color: '#c62828', fontSize: 12 }}>{err}</span>}
      </div>
    </div>
  );
}

export default function Suppliers() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<StockRow[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [unassigned, setUnassigned] = useState<{ productId: string; name: string; deficitBase: number }[]>([]);
  const [error, setError] = useState('');

  async function load() {
    try {
      const [s, st] = await Promise.all([inv.suppliers(), inv.stock()]);
      setSuppliers(s);
      setProducts(st.items);
      setError('');
    } catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { load(); }, []);

  async function loadProposals() {
    const d = await inv.reorderProposals();
    setProposals(d.proposals);
    setUnassigned(d.unassigned);
  }
  useEffect(() => { loadProposals(); }, []);

  async function createOrder(p: Proposal) {
    try {
      await inv.createPurchaseOrder({
        supplierId: p.supplierId,
        items: p.lines.map((l) => ({
          productId: l.productId,
          packSize: l.packSize,
          packsOrdered: l.packs,
          packPriceCents: l.packPriceCents,
        })),
      });
      await loadProposals();
      alert(`Ordine creato in bozza per ${p.supplierName}. Vai al tab "Ordini d'acquisto" per inviarlo.`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addSupplier() {
    if (!name.trim()) return;
    await inv.createSupplier({ name: name.trim(), phone: phone.trim() || undefined });
    setName(''); setPhone('');
    load();
  }

  return (
    <section>
      <h2>Fornitori e riordino</h2>
      {error && <p style={{ color: '#c62828' }}>{error}</p>}

      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        {/* Colonna fornitori */}
        <div style={{ flex: '1 1 380px' }}>
          <h3>Anagrafica</h3>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <input placeholder="Nome fornitore" value={name} onChange={(e) => setName(e.target.value)} />
            <input placeholder="Telefono" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <button onClick={addSupplier}>+ Fornitore</button>
          </div>
          {suppliers.map((s) => (
            <div key={s.id} style={{ background: '#fff', borderRadius: 8, padding: 10, marginBottom: 8, border: '1px solid #ddd' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', cursor: 'pointer' }} onClick={() => setOpen(open === s.id ? null : s.id)}>
                <strong>{s.name}</strong>
                <span style={{ color: '#888', fontSize: 13 }}>{s._count?.listings ?? 0} articoli {open === s.id ? '▾' : '▸'}</span>
              </div>
              {open === s.id && <SupplierListings supplier={s} products={products} />}
            </div>
          ))}
          {suppliers.length === 0 && <p style={{ color: '#999' }}>Nessun fornitore.</p>}
        </div>

        {/* Colonna proposte riordino */}
        <div style={{ flex: '1 1 380px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Proposte di riordino</h3>
            <button onClick={loadProposals}>Ricalcola</button>
          </div>
          {proposals.length === 0 && <p style={{ color: '#999' }}>Nessuna proposta: giacenze sopra soglia.</p>}
          {proposals.map((p) => (
            <div key={p.supplierId} style={{ background: '#fff', border: '1px solid #ddd', borderRadius: 8, padding: 12, marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>{p.supplierName}</strong>
                <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <strong>{fmtEuro(p.totalCents)}</strong>
                  <button onClick={() => createOrder(p)} style={{ background: '#2e7d32', color: '#fff', border: 0, padding: '4px 10px', borderRadius: 6 }}>Crea ordine</button>
                </span>
              </div>
              <table style={{ width: '100%', fontSize: 13, marginTop: 6 }}>
                <thead><tr style={{ textAlign: 'left', color: '#888' }}>
                  <th>Prodotto</th><th>Giac.</th><th>Ordina</th><th style={{ textAlign: 'right' }}>Costo</th>
                </tr></thead>
                <tbody>
                  {p.lines.map((l) => (
                    <tr key={l.productId}>
                      <td>{l.name}</td>
                      <td style={{ color: '#c62828' }}>{l.quantity}/{l.reorderLevel}</td>
                      <td>{l.packs} conf. ({l.orderedBase} {l.unit})</td>
                      <td style={{ textAlign: 'right' }}>{fmtEuro(l.lineCostCents)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {unassigned.length > 0 && (
            <div style={{ background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 8, padding: 10, fontSize: 13 }}>
              <strong>Sotto soglia senza fornitore a listino:</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                {unassigned.map((u) => <li key={u.productId}>{u.name} (mancano {u.deficitBase})</li>)}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
