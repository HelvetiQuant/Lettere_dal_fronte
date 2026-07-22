import { useCallback, useEffect, useState } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, RefreshControl } from 'react-native';
import {
  fetchBoard,
  advanceItem,
  nextItemStatus,
  ITEM_ACTION_LABEL,
  type Station,
  type KdsOrder,
} from '../lib/kdsApi';

// Kitchen Display System per postazione: bar o tavola calda (cucina).
// Ogni riga della comanda si avanza col tocco: PENDING -> IN PREP -> PRONTO -> CONSEGNATO.
// Registrare IN_PREPARATION è ciò che alimenta il tempo di coda nelle statistiche.

function fmt(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}
function waitColor(sec: number): string {
  if (sec < 300) return '#2e7d32';
  if (sec < 600) return '#f9a825';
  return '#c62828';
}
const STATUS_LABEL: Record<string, string> = {
  PENDING: 'In coda',
  IN_PREPARATION: 'In preparazione',
  READY: 'Pronto',
  SERVED: 'Consegnato',
};

export default function KdsScreen() {
  const [station, setStation] = useState<Station>('BAR');
  const [orders, setOrders] = useState<KdsOrder[]>([]);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrders(await fetchBoard(station));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, [station]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  async function onAdvance(itemId: string, status: 'IN_PREPARATION' | 'READY' | 'SERVED') {
    try {
      await advanceItem(station, itemId, status);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const accent = station === 'BAR' ? '#1565c0' : '#e65100';

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>KDS · {station === 'BAR' ? 'Bar' : 'Tavola calda'}</Text>
        <View style={styles.switch}>
          {(['BAR', 'TAVOLA_CALDA'] as Station[]).map((s) => (
            <Pressable
              key={s}
              onPress={() => setStation(s)}
              style={[styles.switchBtn, station === s && { backgroundColor: s === 'BAR' ? '#1565c0' : '#e65100' }]}
            >
              <Text style={[styles.switchTxt, station === s && { color: '#fff' }]}>{s === 'BAR' ? 'Bar' : 'Cucina'}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <ScrollView
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        {orders.length === 0 && <Text style={styles.empty}>Nessuna comanda in coda.</Text>}
        {orders.map((o) => (
          <View key={o.id} style={[styles.card, { borderLeftColor: accent }]}>
            <View style={styles.cardHead}>
              <Text style={styles.table}>{o.table}</Text>
              <Text style={[styles.wait, { color: waitColor(o.waitingSec) }]}>{fmt(o.waitingSec)}</Text>
            </View>
            <Text style={styles.orderId}>#{o.id.slice(-6)}</Text>
            {o.items.map((it) => {
              const next = nextItemStatus(it.status);
              return (
                <View key={it.id} style={styles.itemRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemName}>{it.name} × {it.quantity}</Text>
                    <Text style={styles.itemStatus}>{STATUS_LABEL[it.status] ?? it.status}</Text>
                  </View>
                  {next && (
                    <Pressable onPress={() => onAdvance(it.id, next)} style={[styles.actionBtn, { backgroundColor: accent }]}>
                      <Text style={styles.actionTxt}>{ITEM_ACTION_LABEL[next]}</Text>
                    </Pressable>
                  )}
                </View>
              );
            })}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f5f7' },
  header: { padding: 16, backgroundColor: '#1a1a2e', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: '#fff', fontSize: 18, fontWeight: '700' },
  switch: { flexDirection: 'row', gap: 6 },
  switchBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, borderWidth: 1, borderColor: '#ffffff55' },
  switchTxt: { color: '#fff', fontWeight: '600' },
  error: { color: '#c62828', padding: 12 },
  list: { padding: 12, gap: 12 },
  empty: { color: '#999', textAlign: 'center', marginTop: 40 },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 12, borderLeftWidth: 4, elevation: 2 },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  table: { fontSize: 16, fontWeight: '700' },
  wait: { fontSize: 16, fontWeight: '700', fontVariant: ['tabular-nums'] },
  orderId: { color: '#888', fontSize: 12, marginBottom: 8 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, borderTopWidth: 1, borderTopColor: '#eee' },
  itemName: { fontSize: 15 },
  itemStatus: { fontSize: 12, color: '#888' },
  actionBtn: { paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8 },
  actionTxt: { color: '#fff', fontWeight: '600', fontSize: 13 },
});
