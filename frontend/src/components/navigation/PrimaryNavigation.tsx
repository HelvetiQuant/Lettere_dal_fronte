import { Link, useLocation } from 'react-router-dom';
import { Home, Compass, Calendar, Brain, Eye, Network, Award, LayoutDashboard, FileSearch, Users, AlertCircle, Database, Link2, ScrollText, Settings } from 'lucide-react';
import type { Audience } from '@/hooks/useAudience';

const PUBLIC_NAV = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/esplora', label: 'Esplora', icon: Compass },
  { to: '/eventi', label: 'Eventi', icon: Calendar },
  { to: '/ricerca', label: 'Ricerca AI', icon: Brain, highlight: true },
  { to: '/punti-di-vista', label: 'Punti di vista', icon: Eye, highlight: true },
  { to: '/collegamenti', label: 'Collegamenti', icon: Network, highlight: true },
  { to: '/riconoscimenti', label: 'Riconoscimenti', icon: Award, highlight: true },
];

const RESEARCHER_NAV = [
  { to: '/ricerca', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/ricerca/piani', label: 'Piani di ricerca', icon: FileSearch },
  { to: '/ricerca/soggetti', label: 'Soggetti', icon: Users },
  { to: '/ricerca/lacune', label: 'Lacune', icon: AlertCircle },
  { to: '/esplora', label: 'Fonti', icon: Database },
  { to: '/collegamenti', label: 'Entità e collegamenti', icon: Link2 },
  { to: '/riconoscimenti', label: 'Pratiche di riconoscimento', icon: ScrollText },
];

export function PrimaryNavigation({ audience }: { audience: Audience }) {
  const location = useLocation();
  const items = audience === 'public' ? PUBLIC_NAV : RESEARCHER_NAV;

  return (
    <nav className="app-header__nav" aria-label="Navigazione principale">
      {items.map((item) => {
        const Icon = item.icon;
        const active = location.pathname === item.to ||
          (item.to !== '/' && location.pathname.startsWith(item.to));
        return (
          <Link
            key={item.to}
            to={item.to}
            className={`app-header__nav-link${active ? ' app-header__nav-link--active' : ''}${'highlight' in item && item.highlight ? ' app-header__nav-link--highlight' : ''}`}
          >
            <Icon size={16} aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
