import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Brain, Eye, Network, Award, FileText, ExternalLink, Zap } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { InternatiDetailResponse, InternatiLinksResponse, LeBICompareResponse, TimelineEntry, FonteIndiceRecord, CadutoRecord, DecoratoRecord, V7ResearchResult } from '@/api/types';
import { Card, Tag, Button, LoadingState, ErrorState, EmptyState, PartialDataNotice } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { DossierFacts, Timeline } from '@/components/dossier/DossierParts';
import { SourceCitation, EvidenceStatus } from '@/components/sources/SourceCard';

export function SoldierDossierPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<InternatiDetailResponse | null>(null);
  const [caduto, setCaduto] = useState<CadutoRecord | null>(null);
  const [decorato, setDecorato] = useState<DecoratoRecord | null>(null);
  const [links, setLinks] = useState<InternatiLinksResponse | null>(null);
  const [lebi, setLebi] = useState<LeBICompareResponse | null>(null);
  const [v7Result, setV7Result] = useState<V7ResearchResult | null>(null);
  const [v7Loading, setV7Loading] = useState(false);
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
    } else if (type === 'caduti') {
      api.cadutiDetail(numId)
        .then((d) => { setCaduto(d); setLoading(false); })
        .catch((e) => {
          setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
          setLoading(false);
        });
    } else if (type === 'decorati') {
      api.decoratiDetail(numId)
        .then((d) => { setDecorato(d); setLoading(false); })
        .catch((e) => {
          setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
          setLoading(false);
        });
    } else {
      setLoading(false);
      setError(new ApiError(404, 'Tipo non supportato. Usa: internati, caduti, decorati'));
    }
  }, [type, id]);

  if (loading) return <LoadingState label="Caricamento dossier…" />;
  if (error) return <ErrorState message={error.userMessage} onRetry={() => window.location.reload()} />;

  // Build facts and displayName from whichever type we have
  const fullName = data ? `${data.cognome} ${data.nome}` : caduto ? caduto.nominativo : decorato ? `${decorato.cognome} ${decorato.nome}` : '';
  const facts: { label: string; value: string }[] = [];
  if (data) {
    const s = data;
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
  } else if (caduto) {
    if (caduto.nominativo) facts.push({ label: 'Nominativo', value: caduto.nominativo });
    if (caduto.grado) facts.push({ label: 'Grado', value: caduto.grado });
    if (caduto.reparto) facts.push({ label: 'Reparto', value: caduto.reparto });
    if (caduto.anno_morte) facts.push({ label: 'Anno morte', value: String(caduto.anno_morte) });
    if (caduto.luogo_morte) facts.push({ label: 'Luogo morte', value: caduto.luogo_morte });
  } else if (decorato) {
    if (decorato.cognome) facts.push({ label: 'Cognome', value: decorato.cognome });
    if (decorato.nome) facts.push({ label: 'Nome', value: decorato.nome });
    if (decorato.grado) facts.push({ label: 'Grado', value: decorato.grado });
    if (decorato.decorazione) facts.push({ label: 'Decorazione', value: decorato.decorazione });
    if (decorato.motivazione) facts.push({ label: 'Motivazione', value: decorato.motivazione });
  } else {
    return <EmptyState message="Nessun dato disponibile." />;
  }

  const fonti = data?.fonti_indice || [];
  const eventi = data?.eventi || [];
  const lebiRecords = lebi?.records || [];
  const allLinks = links?.links || [];

  const runV7 = async () => {
    if (!fullName.trim()) return;
    setV7Loading(true);
    setV7Result(null);
    try {
      const result = await api.v7Research(fullName.trim(), 'PERSON_LOOKUP');
      setV7Result(result);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setV7Loading(false);
    }
  };

  return (
    <>
      <PageIntro
        title={fullName}
        description={`Dossier completo di ${fullName}. Identità, servizio, fonti, collegamenti e pipeline V7.`}
        aiNote="L'IA ha estratto e collegato i dati da più dataset. Usa le azioni per avviare ricerche V7, confrontare fonti o valutare un riconoscimento."
        steps={['Esamina i dati biografici', 'Verifica le fonti di ogni dato', 'Avvia pipeline V7 per dossier narrativo']}
      />

      {partial && <PartialDataNotice message="Alcuni dati non sono disponibili (collegamenti o LeBI non caricati)." />}

      <Section title="Identità e servizio">
        <Card><DossierFacts facts={facts} /></Card>
      </Section>

      <div className="flex flex--wrap mb-4" style={{ gap: 'var(--s-2)' }}>
        <Button size="sm" onClick={runV7} disabled={v7Loading}>
          <Zap size={14} /> {v7Loading ? 'Pipeline V7…' : 'Pipeline V7'}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => navigate(`/ricerca?q=${encodeURIComponent(fullName)}`)}>
          <Brain size={14} /> Ricerca AI
        </Button>
        {type === 'internati' && (
          <Button variant="secondary" size="sm" onClick={() => navigate(`/punti-di-vista?q=${encodeURIComponent(fullName)}`)}>
            <Eye size={14} /> Confronta fonti
          </Button>
        )}
        {type === 'internati' && (
          <Button variant="secondary" size="sm" onClick={() => navigate(`/collegamenti?q=${encodeURIComponent(fullName)}`)}>
            <Network size={14} /> Collegamenti euristici
          </Button>
        )}
        {type === 'internati' && (
          <Button variant="secondary" size="sm" onClick={() => navigate(`/riconoscimenti?q=${encodeURIComponent(fullName)}`)}>
            <Award size={14} /> Valuta riconoscimento
          </Button>
        )}
      </div>

      {v7Loading && <LoadingState label="Pipeline V7 in esecuzione…" />}
      {v7Result && (
        <Section title={`V7 Report — ${v7Result.run_id}`} >
          <Card>
            <div className="flex flex--wrap" style={{ gap: 'var(--s-2)' }}>
              <Tag variant="neutral">Obs: {v7Result.observation_count}</Tag>
              <Tag variant="neutral">Claims: {v7Result.snapshot?.person_claims?.length || 0}</Tag>
              {v7Result.snapshot?.identity_status && (
                <Tag variant={v7Result.snapshot.identity_status === 'RESOLVED_IDENTITY' ? 'success' : 'warning'}>
                  {v7Result.snapshot.identity_status.replace('_IDENTITY', '')}
                </Tag>
              )}
              {v7Result.errors.length > 0 && <Tag variant="warning">Errors: {v7Result.errors.length}</Tag>}
            </div>
          </Card>
          {v7Result.report && (
            <div className="mt-2">
              <Card variant="info">
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{v7Result.report}</div>
              </Card>
            </div>
          )}
        </Section>
      )}

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
