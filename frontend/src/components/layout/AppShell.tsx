import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Settings } from 'lucide-react';
import { AudienceSwitch } from '@/components/navigation/AudienceSwitch';
import { PrimaryNavigation } from '@/components/navigation/PrimaryNavigation';
import { GlobalErrorBoundary } from '@/components/debug/GlobalErrorBoundary';
import { ErrorLogPanel } from '@/components/debug/ErrorLogPanel';
import type { Audience } from '@/hooks/useAudience';

export function AppShell({ children, audience, onAudienceChange }: {
  children: ReactNode;
  audience: Audience;
  onAudienceChange: (a: Audience) => void;
}) {
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">Vai al contenuto</a>

      <Link to="/" className="app-banner" aria-label="Voci dal Fronte — Home">
        <img
          src="/static/header_banner.png"
          alt="Voci dal Fronte"
          className="app-banner__img"
        />
      </Link>

      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="app-header__brand">Voci dal Fronte</Link>
          <PrimaryNavigation audience={audience} />
          <AudienceSwitch audience={audience} onChange={onAudienceChange} />
          <Link to="/admin" className="app-header__admin-link" aria-label="Amministrazione">
            <Settings size={14} aria-hidden="true" /> Admin
          </Link>
        </div>
      </header>

      <main className="app-main" id="main-content">
        <div className="app-main__inner">
          <GlobalErrorBoundary>
            {children}
          </GlobalErrorBoundary>
        </div>
      </main>

      <footer className="app-footer">
        Voci dal Fronte — IMI Extractor v2.0 · Motore AI-native di ricerca storica federata
      </footer>

      <ErrorLogPanel />
    </div>
  );
}
