import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Eye, AlertTriangle, CheckCircle, HelpCircle, FileText } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import { Card, Tag, Input, Button, LoadingState, ErrorState, EmptyState, PartialDataNotice } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';

interface ViewpointResult {
  ok?: boolean;
  synthesis?: string;
  shared_facts?: { fact: string; sources: string[]; category?: string }[];
  divergences?: { fact: string; versions: { source: string; value: string; role?: string }[] }[];
  uncertainties?: { topic: string; reason: string }[];
  sources_used?: { name: string; url?: string; provider?: string; model?: string }[];
  providers_used?: string[];
  ai?: { used: boolean; provider?: string; text?: string; error?: string };
  error?: string;
}

export function ViewpointsPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [result, setResult] = useState<ViewpointResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [backendSupported, setBackendSupported] = useState<boolean | null>(null);

  useEffect(() => {
    const q = params.get('q');
    if (q) { setQuery(q); runViewpoint(q); }
  }, []);

  const runViewpoint = async (q?: string) => {
    const searchTerm = (q || query).trim();
    if (searchTerm.length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setBackendSupported(null);
    try {
      const data = await api.viewpointsCreate(searchTerm, true) as ViewpointResult & { ok?: boolean };
      if (data.ok === false) {
        setBackendSupported(false);
        setError(new ApiError(501, data.error || 'Il backend non supporta ancora il task "viewpoints".'));
      } else {
        setBackendSupported(true);
        setResult({
          synthesis: data.synthesis || '',
          shared_facts: data.shared_facts || [],
          divergences: data.divergences || [],
          uncertainties: data.uncertainties || [],
          sources_used: data.sources_used || [],
        });
      }
    } catch (e) {
      const ae = e instanceof ApiError ? e : new ApiError(0, String(e));
      setError(ae);
      if (ae.isNotFound || ae.isServer) setBackendSupported(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageIntro
        title="Punti di vista"
        description="Confronta fonti diverse (anche opposte) su una persona, un fatto, un evento o una domanda. L'IA legge ogni fonte separatamente, estrae affermazioni con riferimenti e produce una sintesi che conserva le differenze senza appiattirle."
        aiNote="L'IA distingue fatti condivisi, fatti compatibili ma non equivalenti, divergenze, contraddizioni e silenzi. Non trasforma la maggioranza in verità automatica e non genera affermazioni senza supporto."
        steps={[
          'Inserisci una persona, fatto o domanda',
          'L\u2019IA confronta le fonti archiviate',
          'Esamina sintesi, fatti condivisi, divergenze e lacune',
        ]}
      />

      {backendSupported === false && (
        <Card variant="info">
          <strong>Backend non disponibile</strong>
          <p className="text-sm mt-2">
            Il backend non risponde o l'endpoint <code>/api/viewpoints/create</code> non è accessibile.
            Verificare che il backend sia attivo sulla porta 8001.
          </p>
        </Card>
      )}

      <Section>
        <div className="flex" style={{ gap: 'var(--s-2)' }}>
          <Input
            placeholder="Es: sorte di Gaiaschi Luigi dopo la cattura"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runViewpoint()}
            className="input--lg"
            aria-label="Query per punti di vista"
          />
          <Button onClick={() => runViewpoint()} disabled={loading}>
            <Eye size={16} /> {loading ? 'Analisi…' : 'Confronta fonti'}
          </Button>
        </div>
      </Section>

      {error && <ErrorState message={error.userMessage} onRetry={() => runViewpoint()} />}
      {loading && <LoadingState label="L'IA legge e confronta le fonti…" />}

      {result && (
        <>
          {result.synthesis && (
            <Section title="Sintesi discorsiva">
              <Card variant="info">
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{result.synthesis}</div>
              </Card>
            </Section>
          )}

          {result.shared_facts && result.shared_facts.length > 0 && (
            <Section title="Fatti condivisi">
              {result.shared_facts.map((f, i) => (
                <Card key={i}>
                  <div className="flex flex--center" style={{ gap: 'var(--s-2)' }}>
                    <CheckCircle size={16} style={{ color: 'var(--c-success)' }} />
                    <span>{f.fact}</span>
                  </div>
                  <div className="text-xs text-muted mt-2">Fonti: {f.sources.join(', ')}</div>
                </Card>
              ))}
            </Section>
          )}

          {result.divergences && result.divergences.length > 0 && (
            <Section title="Divergenze">
              {result.divergences.map((d, i) => (
                <Card key={i}>
                  <div className="flex flex--center" style={{ gap: 'var(--s-2)' }}>
                    <AlertTriangle size={16} style={{ color: 'var(--c-warning)' }} />
                    <strong>{d.fact}</strong>
                  </div>
                  <div className="mt-2">
                    {d.versions.map((v, j) => (
                      <div key={j} className="text-sm" style={{ marginBottom: 'var(--s-1)' }}>
                        <Tag variant="neutral">{v.source}</Tag> {v.value}
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </Section>
          )}

          {result.uncertainties && result.uncertainties.length > 0 && (
            <Section title="Incertezze e lacune">
              {result.uncertainties.map((u, i) => (
                <Card key={i} variant="alt">
                  <div className="flex flex--center" style={{ gap: 'var(--s-2)' }}>
                    <HelpCircle size={16} style={{ color: 'var(--c-text-muted)' }} />
                    <strong>{u.topic}</strong>
                  </div>
                  <div className="text-sm text-muted mt-2">{u.reason}</div>
                </Card>
              ))}
            </Section>
          )}

          {result.sources_used && result.sources_used.length > 0 && (
            <Section title="Fonti utilizzate">
              <Card>
                {result.sources_used.map((s, i) => (
                  <div key={i} className="text-sm" style={{ marginBottom: 'var(--s-1)' }}>
                    <FileText size={12} aria-hidden="true" /> {s.url ? <a href={s.url} target="_blank" rel="noopener">{s.name}</a> : s.name}
                  </div>
                ))}
              </Card>
            </Section>
          )}

          {result.shared_facts?.length === 0 && result.divergences?.length === 0 && !result.synthesis && (
            <EmptyState message="Nessun dato sufficiente per il confronto. Eseguire prima una ricerca AI per raccogliere fonti." />
          )}
        </>
      )}
    </>
  );
}
