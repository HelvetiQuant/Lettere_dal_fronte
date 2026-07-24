import type { TimelineEntry } from '@/api/types';
import { Tag } from '@/components/feedback/States';

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  if (!entries.length) return null;
  return (
    <div className="card">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-2)' }}>
        {entries.map((t, i) => (
          <div key={i} style={{
            display: 'flex', gap: 'var(--s-3)', alignItems: 'baseline',
            borderBottom: i < entries.length - 1 ? '1px solid var(--c-divider)' : 'none',
            paddingBottom: 'var(--s-2)',
          }}>
            <span style={{ fontFamily: 'var(--f-mono)', fontSize: 'var(--fs-sm)', minWidth: 100, color: 'var(--c-text-muted)' }}>
              {t.date_start || '?'}
            </span>
            <span style={{ fontWeight: 600 }}>{t.predicate}</span>
            <span>{t.object_value}</span>
            {t.epistemic_status && (
              <Tag variant={t.epistemic_status === 'confirmed' ? 'success' : t.epistemic_status === 'probable' ? 'accent' : 'neutral'}>
                {t.epistemic_status}
              </Tag>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DossierFacts({ facts }: { facts: { label: string; value: string }[] }) {
  if (!facts.length) return null;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 'var(--s-3)', fontSize: 'var(--fs-base)' }}>
      {facts.map((f, i) => (
        <div key={i}>
          <div style={{ fontSize: 'var(--fs-xs)', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--c-text-muted)' }}>{f.label}</div>
          <div style={{ fontWeight: 500 }}>{f.value}</div>
        </div>
      ))}
    </div>
  );
}

export function ResultGroup<T>({ title, items, render }: {
  title: string;
  items: T[];
  render: (item: T, index: number) => React.ReactNode;
}) {
  if (!items.length) return null;
  return (
    <section className="section">
      <div className="section__header"><h2>{title} ({items.length})</h2></div>
      <div className="grid grid--auto">
        {items.map((item, i) => render(item, i))}
      </div>
    </section>
  );
}
