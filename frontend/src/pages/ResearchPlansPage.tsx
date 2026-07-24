import { useState, useEffect } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ResearchPlan, ResearchV2PlansResponse, ResearchV2PlanResponse } from '@/api/types';
import { Card, Tag, LoadingState, ErrorState, EmptyState, Button } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';

export function ResearchPlansPage() {
  const [plans, setPlans] = useState<ResearchPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<ResearchV2PlanResponse | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);

  useEffect(() => {
    api.researchV2Plans(undefined, 50)
      .then((d: ResearchV2PlansResponse) => setPlans(d.plans || []))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, []);

  const openPlan = async (id: number) => {
    setSelectedLoading(true);
    setSelected(null);
    try {
      const d = await api.researchV2Plan(id);
      setSelected(d);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setSelectedLoading(false);
    }
  };

  return (
    <>
      <PageIntro
        title="Piani di ricerca"
        description="Tutti i piani di ricerca federata V2. Apri un piano per esaminare cicli, tracce, frammenti e sintesi."
        aiNote="Ogni piano conserva il ciclo completo di ricerca: decisioni dell'IA, fonti interrogate, fatti estratti e conflitti rilevati."
        steps={['Sfoglia i piani', 'Apri un piano per i dettagli', 'Esamina cicli e risultati']}
      />
      {error && <ErrorState message={error.userMessage} />}
      {loading && <LoadingState />}
      {!loading && !error && plans.length === 0 && <EmptyState message="Nessun piano di ricerca." />}
      {!loading && !error && plans.length > 0 && (
        <div className="grid grid--auto">
          {plans.map((p) => (
            <Card key={p.id}>
              <div className="flex flex--between flex--center">
                <strong>#{p.id}</strong>
                <Tag variant={p.status === 'completed' ? 'success' : p.status === 'running' ? 'accent' : 'neutral'}>{p.status}</Tag>
              </div>
              <div className="text-sm mt-2">{p.original_input}</div>
              <div className="text-xs text-muted mt-2">{p.created_at}</div>
              <Button variant="ghost" size="sm" className="mt-2" onClick={() => openPlan(p.id)}>Apri piano →</Button>
            </Card>
          ))}
        </div>
      )}
      {selectedLoading && <LoadingState label="Caricamento piano…" />}
      {selected && (
        <Section title={`Piano #${selected.plan.id}`}>
          <Card>
            <strong>{selected.plan.original_input}</strong>
            <div className="text-sm text-muted mt-2">Status: {selected.plan.status}</div>
            <div className="text-sm text-muted">Cicli: {selected.cycles?.length || 0}</div>
            <div className="text-sm text-muted">Sessioni: {selected.sessions?.length || 0}</div>
          </Card>
        </Section>
      )}
    </>
  );
}
