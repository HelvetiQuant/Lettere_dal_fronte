import { useState, useEffect } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ResearchGap } from '@/api/types';
import { Card, Tag, LoadingState, ErrorState, EmptyState } from '@/components/feedback/States';
import { PageIntro } from '@/components/layout/PageIntro';

export function ResearchGapsPage() {
  const [gaps, setGaps] = useState<ResearchGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api.researchGaps('open', undefined)
      .then((d) => setGaps(d.gaps || []))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <PageIntro
        title="Lacune"
        description="Lacune di ricerca identificate dal sistema. Ogni lacuna indica un dato mancante, una fonte non ancora consultata o un'informazione da verificare."
        aiNote="L'IA identifica automaticamente le lacune dopo ogni ricerca e suggerisce i provider più promettenti per colmarle."
        steps={['Esamina le lacune aperte', 'Verifica la priorità', 'Consulta i suggerimenti per colmare ogni lacuna']}
      />
      {error && <ErrorState message={error.userMessage} />}
      {loading && <LoadingState />}
      {!loading && !error && gaps.length === 0 && <EmptyState message="Nessuna lacuna aperta." />}
      {!loading && !error && gaps.length > 0 && (
        <div className="grid grid--auto">
          {gaps.map((g) => (
            <Card key={g.id}>
              <div className="flex flex--between flex--center">
                <strong>{g.subject_name || `Soggetto #${g.subject_id}`}</strong>
                <Tag variant={g.priority >= 7 ? 'danger' : g.priority >= 4 ? 'warning' : 'neutral'}>
                  Priorità: {g.priority}
                </Tag>
              </div>
              <div className="text-sm mt-2">{g.description}</div>
              <div className="text-xs text-muted mt-2">Tipo: {g.gap_type}</div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
