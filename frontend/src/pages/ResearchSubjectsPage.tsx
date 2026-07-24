import { useState, useEffect } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ResearchSubject } from '@/api/types';
import { Card, Tag, LoadingState, ErrorState, EmptyState, Input } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';

export function ResearchSubjectsPage() {
  const [subjects, setSubjects] = useState<ResearchSubject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    api.researchSubjects(undefined, undefined, 100)
      .then((d) => setSubjects(d.subjects || []))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, []);

  const filtered = filter
    ? subjects.filter(s => s.name.toLowerCase().includes(filter.toLowerCase()))
    : subjects;

  return (
    <>
      <PageIntro
        title="Soggetti di ricerca"
        description="Tutti i soggetti indicizzati dal sistema Research-to-Index. Ogni soggetto ha fonti collegate, lacune e un livello di confidenza."
        aiNote="L'IA crea soggetti di ricerca quando una query non trova risultati nel DB locale, indicizza fonti esterne e calcola la confidenza."
        steps={['Filtra per nome o tipo', 'Esamina confidenza e status', 'Consulta fonti e lacune collegate']}
      />
      {error && <ErrorState message={error.userMessage} />}
      <Input placeholder="Filtra per nome…" value={filter} onChange={(e) => setFilter(e.target.value)} className="mb-3" />
      {loading && <LoadingState />}
      {!loading && !error && filtered.length === 0 && <EmptyState message="Nessun soggetto trovato." />}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid grid--auto">
          {filtered.map((s) => (
            <Card key={s.id}>
              <div className="flex flex--between flex--center">
                <strong>{s.name}</strong>
                <Tag variant={s.status === 'confirmed' ? 'success' : s.status === 'open' ? 'accent' : 'neutral'}>{s.status}</Tag>
              </div>
              <div className="text-sm text-muted mt-2">Tipo: {s.subject_type}</div>
              <div className="text-sm text-muted">Confidenza: {(s.confidence * 100).toFixed(0)}%</div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
