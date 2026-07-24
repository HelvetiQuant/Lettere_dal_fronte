import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div style={{ padding: 'var(--s-8) 0', textAlign: 'center' }}>
      <h1 style={{ fontSize: 'var(--fs-2xl)', color: 'var(--c-accent)' }}>404</h1>
      <p className="text-muted" style={{ marginBottom: 'var(--s-4)' }}>
        La pagina cercata non esiste o è stata spostata.
      </p>
      <Link to="/" className="btn btn--primary">Torna alla Home</Link>
    </div>
  );
}
