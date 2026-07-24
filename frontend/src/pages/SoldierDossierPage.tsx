import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Brain, Eye, Network, Award, FileText, ExternalLink } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { InternatiDetailResponse, InternatiLinksResponse, LeBICompareResponse, TimelineEntry, FonteIndiceRecord } from '@/api/types';
import { Card, Tag, Button, LoadingState, ErrorState, EmptyState, PartialDataNotice } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { DossierFacts, Timeline } from '@/components/dossier/DossierParts';
import { SourceCitation, EvidenceStatus } from '@/components/sources/SourceCard';

export function SoldierDossierPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<InternatiDetailResponse | null>(null);
  const [links, setLinks] = useState<InternatiLinksResponse | null>(null);
  const [lebi, setLebi] = useState<LeBICompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [partial, setPartial] = useState(false);

  useEffect(() => {
    if (!type || !id) return;
    const numId = parseInt(id, 10);
    setLoading(true);

    if (type === 'internati') {
      Promise.allSettled([
        api.internatiDetail(numId),
        api.internatiLinks(numId).catch(() => null),
        api.lebiCompare(numId).catch(() => null),
      ]).then(([detailRes, linksRes, lebiRes]) => {
        if (detailRes.status === 'fulfilled') setData(detailRes.value);
        else setError(detailRes.reason instanceof ApiError ? detailRes.reason : new ApiError(0, String(detailRes.reason)));
        if (linksRes.status === 'fulfilled' && linksRes.value) setLinks(linksRes.value);
        else setPartial(true);
        if (lebiRes.status === 'fulfilled' && lebiRes.value) setLebi(lebiRes.value);
        setLoading(false);
      });
    } else {
      setLoading(false);
      setError(new ApiError(404, 'Tipo non supportato. Usa: internati, caduti, decorati'));
    }
  }, [type, id]);

  if (loading) return <LoadingState label="Caricamento dossier…" />;
  if (error) return <ErrorState message={error.userMessage} onRetry={() => window.location.reload()} />;
  if (!data) return <EmptyState message="Nessun dato disponibile." />;

  const s = data;
  const facts: { label: string; value: string }[] = [];
  if (s.cognome) facts.push({ label: 'Cognome', value: s.cognome });
  if (s.nome) facts.push({ label: 'Nome', value: s.nome });
  if (s.data_nascita) facts.push({ label: 'Data nascita', value: s.data_nascita });
  if (s.luogo_nascita) facts.push({ label: 'Luogo nascita', value: s.luogo_nascita });
  if (s.grado) facts.push({ label: 'Grado', value: s.grado });
  if (s.matricola) facts.push({ label: 'Matricola', value: s.matricola });
  if (s.luogo_cattura) facts.push({ label: 'Luogo cattura', value: s.luogo_cattura });
  if (s.data_cattura) facts.push({ label: 'Data cattura', value: s.data_cattura });
  if (s.luogo_internamento) facts.push({ label: 'Luogo internamento', value: s.luogo_internamento });
  if (s.sorte) facts.push({ label: 'Sorte', value: s.sorte });

  const fonti = s.fonti_indice || [];
  const eventi = s.eventi || [];
  const lebiRecords = lebi?.records || [];
  const allLinks = links?.links || [];

  return (
    <>
      <PageIntro
        title={`${s.cognome} ${s.nome}`}
        description={`Dossier completo di ${s.cognome} ${s.nome}. Identità, servizio, cattura, internamento, fonti, collegamenti e confronto con LeBI.`}
        aiNote="L'IA ha estratto e collegato i dati da più dataset. Usa le azioni per avviare ricerche, confrontare fonti o valutare un riconoscimento."
        steps={['Esamina i dati biografici', 'Verifica le fonti di ogni dato', 'Confronta con LeBI e avvia ricerche']}
      />

      {partial && <PartialDataNotice message="Alcuni dati non sono disponibili (collegamenti o LeBI non caricati)." />}

      <Section title="Identità e servizio">
        <Card><DossierFacts facts={facts} /></Card>
      </Section>

      <div className="flex flex--wrap mb-4" style={{ gap: 'var(--s-2)' }}>
        <Button size="sm" onClick={() => navigate(`/ricerca?q=${encodeURIComponent(`${s.cognome} ${s.nome}`)}`)}>
          <Brain size={14} /> Avvia Ricerca AI
        </Button>
        <Button variant="secondary" size="sm" onClick={() => navigate(`/punti-di-vista?q=${encodeURIComponent(`${s.cognome} ${s.nome}`)}`)}>
          <Eye size={14} /> Confronta fonti
        </Button>
        <Button variant="secondary" size="sm" onClick={() => navigate(`/collegamenti?q=${encodeURIComponent(`${s.cognome} ${s.nome}`)}`)}>
          <Network size={14} /> Collegamenti euristici
        </Button>
        <Button variant="secondary" size="sm" onClick={() => navigate(`/riconoscimenti?q=${encodeURIComponent(`${s.cognome} ${s.nome}`)}`)}>
          <Award size={14} /> Valuta riconoscimento
        </Button>
      </div>

      {eventi.length > 0 && (
        <Section title="Eventi collegati">
          <Card>
            {eventi.map((ev, i) => (
              <div key={i} style={{ marginBottom: 'var(--s-2)' }}>
                <strong>{ev.nome}</strong>
                {ev.descrizione && <div className="text-sm text-muted">{ev.descrizione}</div>}
              </div>
            ))}
          </Card>
        </Section>
      )}

      <Section title="Fonti">
        {fonti.length > 0 ? (
          <div className="grid grid--auto">
            {fonti.map((f: FonteIndiceRecord, i: number) => (
              <Card key={i}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div>
                    <strong>{f.titolo || 'Fonte'}</strong>
                    {f.archivio && <div className="text-sm text-muted mt-2">{f.archivio}</div>}
                    {f.tipo_fonte && <Tag variant="neutral">{f.tipo_fonte}</Tag>}
                  </div>
                  {f.url_catalogo && <a href={f.url_catalogo} target="_blank" rel="noopener"><ExternalLink size={14} /></a>}
                </div>
                {f.note && <div className="text-sm text-muted mt-2">{f.note}</div>}
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState message="Nessuna fonte collegata a questo soldato." />
        )}
      </Section>

      {allLinks.length > 0 && (
        <Section title="Collegamenti registrati">
          <Card>
            {allLinks.map((l, i) => (
              <div key={i} className="text-sm" style={{ marginBottom: 'var(--s-2)' }}>
                <Tag variant="accent">{l.link_type}</Tag>
                {' '}{l.from_table}#{l.from_id} → {l.to_table}#{l.to_id}
                {l.confidence && <span className="text-muted"> (conf. {(l.confidence * 100).toFixed(0)}%)</span>}
              </div>
            ))}
          </Card>
        </Section>
      )}

      {lebiRecords.length > 0 && (
        <Section title="Confronto LeBI (Lessico Biografico IMI — ANRP)">
          {lebiRecords.map((rec, i) => (
            <Card key={i}>
              <div className="flex flex--between flex--center">
                <strong>{rec.nome} {rec.cognome}</strong>
                <EvidenceStatus status={rec.match ? 'confirmed' : 'conflict'} />
              </div>
              {rec.camp && <div className="text-sm text-muted mt-2">Campo: {rec.camp}</div>}
              {rec.pdf_url && <a href={rec.pdf_url} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>
                <FileText size={12} /> PDF LeBI →
              </a>}
              {rec.fields && rec.fields.length > 0 && (
                <div className="mt-3">
                  <table style={{ width: '100%', fontSize: 'var(--fs-sm)' }}>
                    <thead><tr><th>Campo</th><th>IMI</th><th>LeBI</th><th>Match</th></tr></thead>
                    <tbody>
                      {rec.fields.map((f, j) => (
                        <tr key={j}>
                          <td>{f.label}</td>
                          <td>{f.imi_value}</td>
                          <td>{f.lebi_value}</td>
                          <td>{f.match ? '✓' : '✗'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ))}
        </Section>
      )}
    </>
  );
}
