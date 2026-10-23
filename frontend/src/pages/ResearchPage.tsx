import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Brain, Clock, AlertTriangle, FileSearch, BookOpen, Zap, ShieldCheck, Activity, MessageSquare, Send } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type {
  ResearchV2Result, ResearchV2PlansResponse, Fragment, TimelineEntry, ResearchPlan,
  V7ResearchResult, V7SemanticCounts, V7Snapshot, V7ChatMessage, V7FollowupResponse,
} from '@/api/types';
import { Card, Tag, Input, Button, LoadingState, ErrorState, EmptyState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { Timeline } from '@/components/dossier/DossierParts';

type PipelineMode = 'v7' | 'v2';

interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
  generation?: V7FollowupResponse['generation'];
}

function FollowupChat({ runId, initialReport }: { runId: string; initialReport: string }) {
  const [turns, setTurns] = useState<ChatTurn[]>([
    { role: 'assistant', content: initialReport },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns, loading]);

  const sendFollowup = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setLoading(true);
    setError(null);
    setInput('');

    const newTurns: ChatTurn[] = [...turns, { role: 'user', content: question }];
    setTurns(newTurns);

    try {
      const history: V7ChatMessage[] = newTurns.map(t => ({ role: t.role, content: t.content }));
      const resp = await api.v7Followup(runId, question, history);
      setTurns([...newTurns, {
        role: 'assistant',
        content: resp.answer,
        generation: resp.generation,
      }]);
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : String(e));
      setTurns(newTurns);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-2)' }}>
      <div
        ref={scrollRef}
        style={{
          maxHeight: '500px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--s-2)',
          paddingRight: 'var(--s-1)',
        }}
      >
        {turns.map((turn, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: turn.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <div
              style={{
                maxWidth: '85%',
                padding: 'var(--s-2) var(--s-3)',
                borderRadius: 'var(--r-md)',
                background: turn.role === 'user'
                  ? 'var(--c-accent-bg, #e3f2fd)'
                  : 'var(--c-surface-2, #f5f5f5)',
                border: turn.role === 'user'
                  ? '1px solid var(--c-accent-border, #90caf9)'
                  : '1px solid var(--c-border, #e0e0e0)',
              }}
            >
              {turn.role === 'assistant' && i === 0 && (
                <div className="text-xs text-muted mb-1" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <BookOpen size={11} /> Report iniziale
                </div>
              )}
              {turn.role === 'assistant' && i > 0 && turn.generation && (
                <div className="text-xs text-muted mb-1" style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-1)' }}>
                  <MessageSquare size={11} />
                  {turn.generation.provider}/{turn.generation.model}
                  {turn.generation.input_tokens != null && (
                    <span>· {turn.generation.input_tokens} in / {turn.generation.output_tokens} out</span>
                  )}
                </div>
              )}
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, fontSize: '0.9rem' }}>
                {turn.content}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div
              style={{
                padding: 'var(--s-2) var(--s-3)',
                borderRadius: 'var(--r-md)',
                background: 'var(--c-surface-2, #f5f5f5)',
                border: '1px solid var(--c-border, #e0e0e0)',
              }}
            >
              <span className="text-sm text-muted">L'IA sta elaborando la risposta…</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="text-sm" style={{ color: 'var(--c-warning)' }}>{error}</div>
      )}

      <div className="flex flex--wrap" style={{ gap: 'var(--s-2)', alignItems: 'center' }}>
        <Input
          placeholder="Fai una domanda di follow-up…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendFollowup()}
          className="input--lg"
          aria-label="Domanda di follow-up"
          disabled={loading}
        />
        <Button onClick={sendFollowup} disabled={loading || !input.trim()}>
          <Send size={16} /> {loading ? 'Attendi…' : 'Invia'}
        </Button>
      </div>
    </div>
  );
}

function IdentityBadge({ status }: { status?: string }) {
  if (!status) return null;
  const variant = status === 'RESOLVED_IDENTITY' ? 'success' :
    status === 'AMBIGUOUS_IDENTITY' ? 'warning' :
    status === 'CONFLICTED_IDENTITY' ? 'warning' :
    status === 'UNRESOLVED_IDENTITY' ? 'neutral' : 'neutral';
  const label = status.replace('_IDENTITY', '').replace('_', ' ');
  return <Tag variant={variant as 'success' | 'warning' | 'neutral'}>Identity: {label}</Tag>;
}

function V7ResultView({ result }: { result: V7ResearchResult }) {
  const snapshot: V7Snapshot | null = result.snapshot;
  const semantic: V7SemanticCounts = result.semantic_counts || {};
  const claims = snapshot?.person_claims || [];
  const identity = snapshot?.identity_status;
  const corroboration = snapshot?.corroboration_status;
  const warPeriod = snapshot?.war_period;
  const crossWar = semantic.cross_war_contamination;
  const timings = result.stage_timings || {};

  return (
    <>
      <Section title={`Run ${result.run_id}`} >
        <Card>
          <div className="flex flex--wrap" style={{ gap: 'var(--s-2)' }}>
            <IdentityBadge status={identity} />
            {corroboration && <Tag variant="neutral">Corroboration: {corroboration}</Tag>}
            {warPeriod && <Tag variant="accent">War: {warPeriod}</Tag>}
            <Tag variant={crossWar ? 'warning' : 'success'}>Cross-war: {crossWar ? 'DETECTED' : 'Clean'}</Tag>
            <Tag variant="neutral">Obs: {result.observation_count}</Tag>
            <Tag variant="neutral">Claims: {claims.length}</Tag>
            {result.errors.length > 0 && <Tag variant="warning">Errors: {result.errors.length}</Tag>}
          </div>
        </Card>
      </Section>

      {result.errors.length > 0 && (
        <Section title="Errors">
          <Card variant="info">
            {result.errors.map((e, i) => (
              <div key={i} className="text-sm" style={{ color: 'var(--c-warning)' }}>{e}</div>
            ))}
          </Card>
        </Section>
      )}

      {result.warnings.length > 0 && (
        <Section title={`Warnings (${result.warnings.length})`}>
          <Card>
            {result.warnings.slice(0, 10).map((w, i) => (
              <div key={i} className="text-sm text-muted">{w}</div>
            ))}
          </Card>
        </Section>
      )}

      {Object.keys(timings).length > 0 && (
        <Section title="Stage Timings">
          <Card>
            <div className="flex flex--wrap" style={{ gap: 'var(--s-2)' }}>
              {Object.entries(timings).map(([stage, t]) => (
                <Tag key={stage} variant="neutral">{stage}: {t.toFixed(1)}s</Tag>
              ))}
            </div>
          </Card>
        </Section>
      )}

      {claims.length > 0 && (
        <Section title={`Person Claims (${claims.length})`}>
          <div className="grid grid--auto">
            {claims.slice(0, 30).map((c, i) => (
              <Card key={i}>
                <div className="flex flex--between flex--center">
                  <strong>{c.predicate || '—'}</strong>
                  {c.certainty && <Tag variant="neutral">{c.certainty}</Tag>}
                </div>
                <div className="text-sm mt-1">{c.value || '—'}</div>
                <div className="text-xs text-muted mt-1">Sources: {c.source_count ?? c.evidence_count ?? 0}</div>
              </Card>
            ))}
            {claims.length > 30 && (
              <Card><div className="text-sm text-muted">+{claims.length - 30} more claims…</div></Card>
            )}
          </div>
        </Section>
      )}

      {result.report && (
        <Section title={`Report (${result.report.length} chars)`}>
          <Card variant="info">
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{result.report}</div>
          </Card>
        </Section>
      )}

      {!result.report && (
        <Section title="Report">
          <Card><EmptyState message="Nessun report generato." /></Card>
        </Section>
      )}

      {result.report && (
        <Section title="Conversazione Follow-Up">
          <Card>
            <FollowupChat runId={result.run_id} initialReport={result.report} />
          </Card>
        </Section>
      )}
    </>
  );
}

export function ResearchPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [mode, setMode] = useState<PipelineMode>('v7');
  const [v2Result, setV2Result] = useState<ResearchV2Result | null>(null);
  const [v7Result, setV7Result] = useState<V7ResearchResult | null>(null);
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
    setV2Result(null);
    setV7Result(null);
    try {
      if (mode === 'v7') {
        const data = await api.v7Research(query.trim());
        setV7Result(data);
      } else {
        const data = await api.researchV2Create(query.trim());
        setV2Result(data);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setLoading(false);
    }
  };

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
        <div className="flex flex--wrap" style={{ gap: 'var(--s-2)', alignItems: 'center' }}>
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
        <div className="flex flex--center mt-2" style={{ gap: 'var(--s-2)' }}>
          <Button
            variant={mode === 'v7' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setMode('v7')}
          >
            <Zap size={12} /> V7 Pipeline
          </Button>
          <Button
            variant={mode === 'v2' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setMode('v2')}
          >
            <Activity size={12} /> V2 Legacy
          </Button>
        </div>
      </Section>

      {error && <ErrorState message={error.userMessage} onRetry={runResearch} />}
      {loading && (
        <LoadingState label={
          mode === 'v7'
            ? 'Pipeline V7 in esecuzione: Plan → Discover → Fetch → Extract → Resolve → Fuse → Validate → Narrate…'
            : "Ricerca federata V2 in corso. L'IA interroga più fonti in cicli successivi…"
        } />
      )}

      {v7Result && mode === 'v7' && <V7ResultView result={v7Result} />}

      {v2Result && mode === 'v2' && (() => {
        const result = v2Result;
        const allFragments: Fragment[] = result?.cycles?.flatMap(c => c.fragments || []) || [];
        const timeline: TimelineEntry[] = result?.timeline || result?.facts?.timeline || [];
        const conflicts: unknown[] = result?.facts?.conflicts || [];
        const narrative = result?.narrative;
        return (
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
        );
      })()}

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
