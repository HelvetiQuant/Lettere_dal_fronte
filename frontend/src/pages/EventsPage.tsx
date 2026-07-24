import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { EventRecord, EventDossierResponse, CadutoRecord, DecoratoRecord, InternatoRecord, DocumentoRecord, FonteIndiceRecord } from '@/api/types';
import { Card, Tag, LoadingState, EmptyState, ErrorState, Button } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { ResultGroup } from '@/components/dossier/DossierParts';

export function EventsPage() {
  const navigate = useNavigate();
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api.events1gm()
      .then((d) => setEvents(d.eventi || []))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <PageIntro
        title="Eventi"
        description="Battaglie, operazioni e momenti chiave della Prima Guerra Mondiale. Ogni evento è collegato a caduti, decorati, internati, documenti e fonti."
        aiNote="L’IA collega automaticamente persone, luoghi e documenti agli eventi, ricostruendo cronologie e contesti."
        steps={['Sfoglia l’elenco degli eventi', 'Apri un evento per il dossier completo', 'Esplora le persone e le fonti collegate']}
      />
      {error && <ErrorState message={error.userMessage} onRetry={() => { setError(null); setLoading(true); window.location.reload(); }} />}
      {loading && <LoadingState />}
      {!loading && !error && events.length === 0 && <EmptyState message="Nessun evento disponibile nel database." />}
      {!loading && !error && events.length > 0 && (
        <div className="grid grid--auto">
          {events.map((ev) => (
            <Card key={ev.nome}>
              <div onClick={() => navigate(`/eventi/${encodeURIComponent(ev.nome)}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                <div style={{ fontFamily: 'var(--f-heading)', fontWeight: 600, fontSize: 18 }}>{ev.nome}</div>
                {ev.data_inizio && <span className="text-sm text-muted">{ev.data_inizio}{ev.data_fine ? ` — ${ev.data_fine}` : ''}</span>}
                {ev.luogo && <div className="text-sm text-muted">{ev.luogo}</div>}
                <div className="flex flex--wrap mt-2" style={{ gap: 'var(--s-1)' }}>
                  {ev.caduti ? <Tag variant="neutral">Caduti: {ev.caduti}</Tag> : null}
                  {ev.decorati ? <Tag variant="warning">Decorati: {ev.decorati}</Tag> : null}
                  {ev.internati ? <Tag variant="accent">Internati: {ev.internati}</Tag> : null}
                  {ev.documenti ? <Tag variant="neutral">Documenti: {ev.documenti}</Tag> : null}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

export function EventDossierPage() {
  const { eventName } = useParams<{ eventName: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<EventDossierResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!eventName) return;
    const name = decodeURIComponent(eventName);
    api.eventDossier(name)
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, [eventName]);

  const ev = data?.event;
  const caduti = data?.caduti?.items || [];
  const decorati = data?.decorati?.items || [];
  const internati = data?.internati?.items || [];
  const documenti = data?.documenti?.items || [];
  const fonti = data?.fonti?.items || [];

  return (
    <>
      <PageIntro
        title={ev?.nome || decodeURIComponent(eventName || '')}
        description={ev?.descrizione || 'Dossier evento con tutti i dati collegati: caduti, decorati, internati, documenti e fonti.'}
        aiNote="L’IA ha collegato automaticamente persone, documenti e fonti a questo evento. Usa Punti di vista per confrontare le fonti, o Collegamenti per esplorare il grafo."
        steps={['Esamina la descrizione e la cronologia', 'Naviga le persone collegate', 'Consulta le fonti e i documenti']}
      />

      {error && <ErrorState message={error.userMessage} />}
      {loading && <LoadingState />}

      {!loading && !error && ev && (
        <>
          <Section title="Dettagli evento">
            <Card>
              <div className="grid grid--2">
                {ev.data_inizio && <div><strong>Data inizio:</strong> {ev.data_inizio}</div>}
                {ev.data_fine && <div><strong>Data fine:</strong> {ev.data_fine}</div>}
                {ev.luogo && <div><strong>Luogo:</strong> {ev.luogo}</div>}
              </div>
            </Card>
          </Section>

          <div className="flex flex--wrap mb-4" style={{ gap: 'var(--s-2)' }}>
            <Button variant="secondary" size="sm" onClick={() => navigate(`/punti-di-vista?q=${encodeURIComponent(ev.nome)}`)}>
              Confronta fonti (Punti di vista)
            </Button>
            <Button variant="secondary" size="sm" onClick={() => navigate(`/collegamenti?q=${encodeURIComponent(ev.nome)}`)}>
              Genera collegamenti euristici
            </Button>
          </div>

          <ResultGroup<CadutoRecord>
            title="Caduti"
            items={caduti}
            render={(c) => (
              <Card key={c.id}>
                <div onClick={() => navigate(`/soldato/caduti/${c.id}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <strong>{c.nominativo}</strong>
                  {c.grado && <Tag variant="neutral">{c.grado}</Tag>}
                  <div className="text-sm text-muted mt-2">{c.luogo_morte} ({c.anno_morte})</div>
                </div>
              </Card>
            )}
          />

          <ResultGroup<DecoratoRecord>
            title="Decorati"
            items={decorati}
            render={(d) => (
              <Card key={d.id}>
                <div onClick={() => navigate(`/soldato/decorati/${d.id}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <strong>{d.cognome} {d.nome}</strong>
                  {d.decorazione && <Tag variant="warning">{d.decorazione}</Tag>}
                </div>
              </Card>
            )}
          />

          <ResultGroup<InternatoRecord>
            title="Internati"
            items={internati}
            render={(s) => (
              <Card key={s.id}>
                <div onClick={() => navigate(`/soldato/internati/${s.id}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <strong>{s.cognome} {s.nome}</strong>
                  {s.luogo_internamento && <div className="text-sm text-muted mt-2">{s.luogo_internamento}</div>}
                </div>
              </Card>
            )}
          />

          <ResultGroup<DocumentoRecord & { url?: string } >
            title="Documenti"
            items={documenti}
            render={(d, i) => (
              <Card key={i}>
                <strong>{d.titolo || 'Documento'}</strong>
                {d.tipo && <Tag variant="neutral">{d.tipo}</Tag>}
                {d.url && <a href={d.url} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>Apri →</a>}
              </Card>
            )}
          />

          <ResultGroup<FonteIndiceRecord>
            title="Fonti"
            items={fonti}
            render={(f, i) => (
              <Card key={i}>
                <strong>{f.titolo || 'Fonte'}</strong>
                {f.archivio && <div className="text-sm text-muted mt-2">{f.archivio}</div>}
                {f.url_catalogo && <a href={f.url_catalogo} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>Catalogo →</a>}
              </Card>
            )}
          />
        </>
      )}
    </>
  );
}
