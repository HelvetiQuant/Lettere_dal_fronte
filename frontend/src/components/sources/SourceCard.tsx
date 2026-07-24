import { Tag } from '@/components/feedback/States';

export function SourceCard({ provider, title, description, url, score }: {
  provider: string;
  title: string;
  description?: string;
  url: string;
  score?: number;
}) {
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
        <div>
          <Tag variant="accent">{provider}</Tag>
          <div style={{ fontWeight: 600, marginTop: 6 }}>{title}</div>
          {description && <div className="text-sm text-muted mt-2">{description}</div>}
        </div>
        <a href={url} target="_blank" rel="noopener" aria-label="Apri fonte esterna">
          ↗
        </a>
      </div>
      {score !== undefined && (
        <div className="text-xs text-muted mt-2">Score: {(score * 100).toFixed(0)}%</div>
      )}
    </div>
  );
}

export function SourceCitation({ source, url }: { source: string; url?: string }) {
  return (
    <span className="text-xs text-muted">
      Fonte: {url ? <a href={url} target="_blank" rel="noopener">{source}</a> : source}
    </span>
  );
}

export function EvidenceStatus({ status }: { status: 'confirmed' | 'probable' | 'unverified' | 'conflict' }) {
  const map: Record<string, { variant: 'success' | 'accent' | 'neutral' | 'danger'; label: string }> = {
    confirmed: { variant: 'success', label: 'Verificato' },
    probable: { variant: 'accent', label: 'Probabile' },
    unverified: { variant: 'neutral', label: 'Non verificato' },
    conflict: { variant: 'danger', label: 'Conflitto' },
  };
  const cfg = map[status] || map.unverified;
  return <Tag variant={cfg.variant}>{cfg.label}</Tag>;
}

export function ConfidenceIndicator({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const variant = pct >= 80 ? 'success' : pct >= 50 ? 'accent' : 'neutral';
  return <Tag variant={variant}>{pct}%</Tag>;
}
