import type { ReactNode } from 'react';

export function Card({ children, variant = 'default' }: { children: ReactNode; variant?: 'default' | 'alt' | 'info' }) {
  const cls = variant === 'alt' ? 'card card--alt' : variant === 'info' ? 'card card--info' : 'card';
  return <div className={cls}>{children}</div>;
}

export function Tag({ variant = 'neutral', children }: { variant?: 'accent' | 'success' | 'warning' | 'danger' | 'neutral'; children: ReactNode }) {
  return <span className={`tag tag--${variant}`}>{children}</span>;
}

export function Button({
  variant = 'primary', size, children, ...props
}: {
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost';
  size?: 'sm';
  children: ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`btn btn--${variant}${size ? ` btn--${size}` : ''}`} {...props}>
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className, ...rest } = props;
  return <input className={`input${className ? ' ' + className : ''}`} {...rest} />;
}

export function LoadingState({ label = 'Caricamento…' }: { label?: string }) {
  return <div className="state-loading">{label}</div>;
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state-empty">{message}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-error">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{message}</span>
        {onRetry && <button className="btn btn--ghost btn--sm" onClick={onRetry}>Riprova</button>}
      </div>
    </div>
  );
}

export function PartialDataNotice({ message }: { message: string }) {
  return <div className="state-partial">{message}</div>;
}

export function StatCard({ value, label, sub, onClick }: {
  value: string | number;
  label: string;
  sub?: string;
  onClick?: () => void;
}) {
  return (
    <div className={`stat-card${onClick ? ' stat-card--clickable' : ''}`} onClick={onClick} role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}>
      <div className="stat-card__value">{value}</div>
      <div className="stat-card__label">{label}</div>
      {sub && <div className="stat-card__sub">{sub}</div>}
    </div>
  );
}
