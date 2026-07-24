import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Calendar, Users, GitCompare, Network, Brain, Award } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { EventRecord, StatusResponse, DecoratiStatusResponse, EntitaStatsResponse, FondiListResponse, SourceStatsResponse } from '@/api/types';
import { Card, StatCard, Input, Button, LoadingState, ErrorState, PartialDataNotice } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';

const OBJECTIVES = [
  { icon: Users, label: 'Persona', desc: 'Cerca un soldato, internato o decorato', to: '/esplora' },
  { icon: Calendar, label: 'Evento', desc: 'Esplora battaglie e operazioni', to: '/eventi' },
  { icon: GitCompare, label: 'Confronto fonti', desc: 'Confronta versioni diverse di un fatto', to: '/punti-di-vista' },
  { icon: Network, label: 'Grafo', desc: 'Visualizza collegamenti tra fonti', to: '/collegamenti' },
  { icon: Brain, label: 'Ricerca assistita', desc: 'Lascia che l\u2019IA costruisca una biografia', to: '/ricerca' },
  { icon: Award, label: 'Riconoscimento', desc: 'Valuta un candidato al riconoscimento', to: '/riconoscimenti' },
];

const EXAMPLES = ['Gaiaschi Luigi', 'Caporetto', 'Monte Grappa', 'Stalag XIII B', '9° Reggimento'];

export function HomePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [stats, setStats] = useState<Record<string, number>>({});
  const [statsError, setStatsError] = useState(false);
  const [statsPartial, setStatsPartial] = useState(false);
  const [statsLoading, setStatsLoading] = useState(true);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [eventsError, setEventsError] = useState(false);

  useEffect(() => {
    let loadedCount = 0;
    const totalEndpoints = 6;

    const checkPartial = () => {
      loadedCount++;
      if (loadedCount < totalEndpoints) setStatsPartial(true);
    };

    api.status()
      .then((d: StatusResponse) => setStats((s) => ({ ...s, Internati: d.total_internati ?? 0 })))
      .catch(() => { setStatsError(true); checkPartial(); })
      .finally(() => { checkPartial(); setStatsLoading(false); });

    api.decoratiStatus()
      .then((d: DecoratiStatusResponse) => setStats((s) => ({ ...s, Decorati: d.count ?? 0 })))
      .catch(() => checkPartial());

    api.entitaStats()
      .then((d: EntitaStatsResponse) => setStats((s) => ({ ...s, 'Entità': d.count_entita ?? 0, 'Collegamenti': d.count_collegamenti ?? 0 })))
      .catch(() => checkPartial());

    api.fondiList()
      .then((d: FondiListResponse) => setStats((s) => ({ ...s, 'Fondi': d.count_fondi ?? 0, 'Menzioni': d.count_menzioni ?? 0 })))
      .catch(() => checkPartial());

    api.sourceStats()
      .then((d: SourceStatsResponse) => setStats((s) => ({ ...s, 'Fonti esterne': d.total_sources ?? 0 })))
      .catch(() => checkPartial());

    api.events1gm()
      .then((d) => { setEvents(d.eventi?.slice(0, 6) ?? []); })
      .catch(() => setEventsError(true));
  }, []);

  const onSearch = () => {
    if (query.trim().length >= 2) navigate(`/esplora?q=${encodeURIComponent(query.trim())}`);
  };

  return (
    <>
      <PageIntro
        title="Voci dal Fronte"
        description="Motore AI-native di ricerca storica federata. Interroga database locali e archivi internazionali, estrae fatti documentati, risolve identità e ricostruisce biografie con citazioni di fonte."
        aiNote="L'IA ricerca simultaneamente nei database locali e negli archivi esterni, estrae fatti con riferimenti alle fonti, risolve identità tra dataset diversi e produce ricostruzioni narrative citate."
      />

      <Section>
        <div className="flex" style={{ gap: 'var(--s-2)' }}>
          <Input
            type="text"
            placeholder="Cerca persone, eventi, luoghi, reparti…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onSearch()}
            className="input--lg"
            aria-label="Campo di ricerca"
          />
          <Button onClick={onSearch} aria-label="Avvia ricerca">
            <Search size={16} /> Cerca
          </Button>
        </div>
        <div className="flex flex--wrap mt-2" style={{ alignItems: 'center' }}>
          <span className="text-sm text-muted">Esempi:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              className="btn btn--ghost btn--sm"
              onClick={() => navigate(`/esplora?q=${encodeURIComponent(ex)}`)}
            >
              {ex}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Sei obiettivi">
        <div className="grid grid--auto">
          {OBJECTIVES.map((obj) => {
            const Icon = obj.icon;
            return (
              <Card key={obj.label}>
                <div onClick={() => navigate(obj.to)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <Icon size={24} style={{ color: 'var(--c-accent)' }} aria-hidden="true" />
                  <div style={{ fontWeight: 600, marginTop: 'var(--s-2)' }}>{obj.label}</div>
                  <div className="text-sm text-muted">{obj.desc}</div>
                </div>
              </Card>
            );
          })}
        </div>
      </Section>

      <Section title="Statistiche archivio">
        {statsError && <ErrorState message="Impossibile caricare alcune statistiche dal backend." />}
        {statsPartial && !statsError && <PartialDataNotice message="Caricamento parziale: alcune statistiche sono ancora in attesa." />}
        {statsLoading ? (
          <LoadingState label="Caricamento statistiche…" />
        ) : (
          <div className="grid grid--auto">
            {Object.entries(stats).map(([label, value]) => (
              <StatCard
                key={label}
                value={value.toLocaleString('it-IT')}
                label={label}
                onClick={() => navigate('/esplora')}
              />
            ))}
          </div>
        )}
      </Section>

      <Section title="Eventi storici" action={<button className="btn btn--ghost btn--sm" onClick={() => navigate('/eventi')}>Vedi tutti →</button>}>
        {eventsError ? (
          <ErrorState message="Impossibile caricare gli eventi." />
        ) : (
          <div className="grid grid--auto">
            {events.map((ev) => (
              <Card key={ev.nome}>
                <div onClick={() => navigate(`/eventi/${encodeURIComponent(ev.nome)}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <span className="text-xs text-muted">
                    <Calendar size={12} aria-hidden="true" /> {ev.data_inizio || '?'}
                  </span>
                  <div style={{ fontFamily: 'var(--f-heading)', fontWeight: 600, fontSize: 18, marginTop: 4 }}>
                    {ev.nome}
                  </div>
                  {ev.luogo && <span className="text-sm text-muted">{ev.luogo}</span>}
                </div>
              </Card>
            ))}
          </div>
        )}
      </Section>
    </>
  );
}
