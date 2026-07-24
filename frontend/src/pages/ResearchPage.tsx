import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Brain, Clock, AlertTriangle, FileSearch, BookOpen } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ResearchV2Result, ResearchV2PlansResponse, Fragment, TimelineEntry, ResearchPlan } from '@/api/types';
import { Card, Tag, Input, Button, LoadingState, ErrorState, EmptyState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { Timeline } from '@/components/dossier/DossierParts';

export function ResearchPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [result, setResult] = useState<ResearchV2Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [plans, setPlans] = useState<ResearchPlan[]>([]);
  const [plansError, setPlansError] = useState(false);

  useEffect(() => {
    api.researchV2Plans(undefined, 5)
      .then((d: ResearchV2PlansResponse) => setPlans(d.plans || []))
      .catch(() => setPlansError(true));
  }, []);

  const runResearch = async () => {
    if (query.trim().length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.researchV2Create(query.trim());
      setResult(data);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setLoading(false);
    }
  };

  const allFragments: Fragment[] = result?.cycles?.flatMap(c => c.fragments || []) || [];
  const timeline: TimelineEntry[] = result?.timeline || result?.facts?.timeline || [];
  const conflicts: unknown[] = result?.facts?.conflicts || [];
  const narrative = result?.narrative;

  return (
    <>
      <PageIntro
        title="Ricerca AI"
        description="L'orchestratore federato costruisce un piano di ricerca, interroga fonti interne ed esterne in cicli successivi, estrae fatti con citazioni, risolve identità e produce una sintesi narrativa."
        aiNote="L'IA pianifica la ricerca, sceglie le fonti, estrae fatti strutturati, rileva conflitti e lacune, e produce una ricostruzione narrativa. Ogni affermazione è collegata alla fonte che la sostiene."
        steps={[
          'Scrivi una domanda di ricerca (persona, evento, luogo)',
          'L\u2019IA esegue cicli di ricerca su fonti interne ed esterne',
          'Esamina fatti, cronologia, conflitti e sintesi',
        ]}
      />

      <Section>
        <div className="flex" style={{ gap: 'var(--s-2)' }}>
          <Input
            placeholder="Es: Gaiaschi Luigi internato a Sandbostel"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runResearch()}
            className="input--lg"
            aria-label="Domanda di ricerca"
          />
          <Button onClick={runResearch} disabled={loading}>
            <Brain size={16} /> {loading ? 'Ricerca…' : 'Avvia ricerca'}
          </Button>
        </div>
      </Section>

      {error && <ErrorState message={error.userMessage} onRetry={runResearch} />}
      {loading && <LoadingState label="Ricerca federata in corso. L'IA interroga più fonti in cicli successivi…" />}

      {result && (
        <>
          <Section title={`Piano #${result.plan_id}`}>
            <Card>
              <div className="flex flex--wrap" style={{ gap: 'var(--s-2)' }}>
                <Tag variant="accent">Tipo: {result.entity_type}</Tag>
                <Tag variant="neutral">Cicli: {result.cycles?.length || 0}</Tag>
                <Tag variant="neutral">Frammenti: {allFragments.length}</Tag>
              </div>
            </Card>
          </Section>

          {narrative?.text && (
            <Section title="Sintesi narrativa">
              <Card variant="info">
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{narrative.text}</div>
                <div className="text-xs text-muted mt-3">Provider: {narrative.provider}</div>
              </Card>
            </Section>
          )}

          {timeline.length > 0 && (
            <Section title="Cronologia">
              <Timeline entries={timeline} />
            </Section>
          )}

          <Section title={`Frammenti (${allFragments.length})`}>
            <div className="grid grid--auto">
              {allFragments.map((f, i) => (
                <Card key={i}>
                  <div className="flex flex--between flex--center">
                    <Tag variant="accent">{f.type}</Tag>
                    {f.score !== undefined && <span className="text-xs text-muted">{(f.score * 100).toFixed(0)}%</span>}
                  </div>
                  <div className="text-sm mt-2">{f.clue}</div>
                  {f.source && <div className="text-xs text-muted mt-2">Fonte: {f.source}</div>}
                  {f.url && <a href={f.url} target="_blank" rel="noopener" className="text-xs mt-2" style={{ display: 'inline-block' }}>Apri →</a>}
                </Card>
              ))}
            </div>
          </Section>

          {conflicts.length > 0 && (
            <Section title="Conflitti">
              <Card variant="info">
                <div className="flex flex--center" style={{ gap: 'var(--s-2)', color: 'var(--c-warning)' }}>
                  <AlertTriangle size={18} /> {conflicts.length} conflitto/i rilevato/i tra le fonti.
                </div>
              </Card>
            </Section>
          )}

          <Section title="Lacune">
            <Card>
              <EmptyState message={result.facts?.claims_created ? 'Nessuna lacuna esplicita segnalata in questo piano.' : 'Dati insufficienti per identificare lacune.'} />
            </Card>
          </Section>
        </>
      )}

      <Section title="Ricerche recenti">
        {plansError ? (
          <ErrorState message="Impossibile caricare le ricerche recenti." />
        ) : plans.length === 0 ? (
          <EmptyState message="Nessuna ricerca precedente." />
        ) : (
          <div className="grid grid--auto">
            {plans.map((p) => (
              <Card key={p.id}>
                <div className="flex flex--between flex--center">
                  <strong>#{p.id}</strong>
                  <Tag variant={p.status === 'completed' ? 'success' : p.status === 'running' ? 'accent' : 'neutral'}>
                    {p.status}
                  </Tag>
                </div>
                <div className="text-sm mt-2">{p.original_input}</div>
                <div className="text-xs text-muted mt-2">
                  <Clock size={11} aria-hidden="true" /> {p.created_at}
                </div>
                <Button variant="ghost" size="sm" className="mt-2" onClick={() => { setQuery(p.original_input); }}>
                  <FileSearch size={12} /> Riprendi
                </Button>
              </Card>
            ))}
          </div>
        )}
      </Section>
    </>
  );
}
