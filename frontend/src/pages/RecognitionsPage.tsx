import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Award, FileText, AlertTriangle, CheckCircle, Phone, Mail, Upload, Clock } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { SearchResult, InternatoRecord } from '@/api/types';
import { Card, Tag, Input, Button, LoadingState, ErrorState, EmptyState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';

interface Candidate {
  id: number;
  nome: string;
  cognome: string;
  grado?: string;
  luogo_internamento?: string;
  sorte?: string;
  compatibility: 'potential' | 'verified';
  satisfiedRequirements: string[];
  missingDocuments: string[];
}

const REQUIREMENTS = [
  'Documento di identità del richiedente',
  'Certificato di morte o presunzione di morte',
  'Certificato di nascita dell\u2019internato',
  'Documento che attesti lo status di IMI',
  'Albo d\u2019Oro o decorazione',
  'Documentazione del campo di prigionia',
  'Prova del legame di parentela',
];

export function RecognitionsPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<Candidate | null>(null);

  useEffect(() => {
    const q = params.get('q');
    if (q) { setQuery(q); searchCandidates(q); }
  }, []);

  const searchCandidates = async (q?: string) => {
    const searchTerm = (q || query).trim();
    if (searchTerm.length < 2) return;
    setLoading(true);
    setError(null);
    setCandidates([]);
    try {
      const searchResult: SearchResult = await api.search(searchTerm, 30);
      const internati = searchResult.internati || [];
      setCandidates(internati.map((s: InternatoRecord) => ({
        id: s.id,
        nome: s.nome,
        cognome: s.cognome,
        grado: s.grado,
        luogo_internamento: s.luogo_internamento,
        sorte: s.sorte,
        compatibility: 'potential',
        satisfiedRequirements: [],
        missingDocuments: REQUIREMENTS.slice(),
      })));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageIntro
        title="Riconoscimenti"
        description="Identifica potenziali candidati a riconoscimenti amministrativi, valuta i requisiti soddisfatti, elenca i documenti mancanti e prepara un fascicolo completo. L'esito appartiene sempre all'amministrazione competente."
        aiNote="L'IA cerca nei database i candidati compatibili, verifica i requisiti normativi e aiuta a compilare il fascicolo. Non promette mai l'esito: l'approvazione spetta all'ufficio competente."
        steps={[
          'Cerca un candidato per nome',
          'Verifica requisiti e documenti mancanti',
          'Prepara il fascicolo con contatti e consensi',
        ]}
      />

      <Card variant="info">
        <div className="flex flex--center" style={{ gap: 'var(--s-2)' }}>
          <AlertTriangle size={16} style={{ color: 'var(--c-warning)' }} />
          <span className="text-sm">
            <strong>Avviso:</strong> Questa funzione supporta la preparazione della pratica.
            L'esito del riconoscimento spetta esclusivamente all\u2019amministrazione competente
            (Ministero della Difesa, ANRP, Prefettura).
          </span>
        </div>
      </Card>

      <Section>
        <div className="flex" style={{ gap: 'var(--s-2)' }}>
          <Input
            placeholder="Cerca candidato per nome…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && searchCandidates()}
            className="input--lg"
            aria-label="Cerca candidato"
          />
          <Button onClick={() => searchCandidates()} disabled={loading}>
            <Award size={16} /> {loading ? 'Ricerca…' : 'Cerca candidati'}
          </Button>
        </div>
      </Section>

      {error && <ErrorState message={error.userMessage} onRetry={() => searchCandidates()} />}
      {loading && <LoadingState label="Ricerca candidati nei database…" />}

      {!loading && !error && candidates.length === 0 && query && (
        <EmptyState message="Nessun candidato trovato." />
      )}

      {candidates.length > 0 && !selected && (
        <Section title={`Candidati (${candidates.length})`}>
          <div className="grid grid--auto">
            {candidates.map((c) => (
              <Card key={c.id}>
                <div onClick={() => setSelected(c)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <div className="flex flex--between flex--center">
                    <strong>{c.cognome} {c.nome}</strong>
                    <Tag variant="warning">Potenzialmente compatibile</Tag>
                  </div>
                  <div className="text-sm text-muted mt-2">
                    {c.grado && <div>Grado: {c.grado}</div>}
                    {c.luogo_internamento && <div>Campo: {c.luogo_internamento}</div>}
                    {c.sorte && <div>Sorte: {c.sorte}</div>}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {selected && (
        <>
          <Button variant="ghost" size="sm" onClick={() => setSelected(null)} className="mb-3">← Torna ai candidati</Button>

          <Section title={`Fascicolo: ${selected.cognome} ${selected.nome}`}>
            <Card>
              <div className="grid grid--2">
                <div><strong>Grado:</strong> {selected.grado || '—'}</div>
                <div><strong>Campo:</strong> {selected.luogo_internamento || '—'}</div>
                <div><strong>Sorte:</strong> {selected.sorte || '—'}</div>
                <div><strong>Stato:</strong> <Tag variant="warning">Potenzialmente compatibile</Tag></div>
              </div>
            </Card>
          </Section>

          <Section title="Requisiti e documenti">
            <Card>
              <h3>Requisiti soddisfatti</h3>
              {selected.satisfiedRequirements.length === 0 ? (
                <EmptyState message="Nessun requisito ancora verificato." />
              ) : (
                <ul style={{ paddingLeft: 'var(--s-5)' }}>
                  {selected.satisfiedRequirements.map((r, i) => (
                    <li key={i} className="text-sm flex flex--center" style={{ gap: 'var(--s-2)', marginBottom: 'var(--s-1)' }}>
                      <CheckCircle size={14} style={{ color: 'var(--c-success)' }} /> {r}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <h3>Documenti mancanti</h3>
              <ul style={{ paddingLeft: 'var(--s-5)' }}>
                {selected.missingDocuments.map((d, i) => (
                  <li key={i} className="text-sm flex flex--center" style={{ gap: 'var(--s-2)', marginBottom: 'var(--s-1)' }}>
                    <FileText size={14} style={{ color: 'var(--c-text-muted)' }} /> {d}
                  </li>
                ))}
              </ul>
            </Card>
          </Section>

          <Section title="Contatti del discendente">
            <Card>
              <div className="grid grid--2">
                <div>
                  <label className="text-sm text-muted">Nome del discendente</label>
                  <Input placeholder="Nome e cognome" />
                </div>
                <div>
                  <label className="text-sm text-muted">Telefono</label>
                  <Input placeholder="Telefono" />
                </div>
                <div>
                  <label className="text-sm text-muted">Email</label>
                  <Input placeholder="Email" type="email" />
                </div>
                <div>
                  <label className="text-sm text-muted">Relazione con l\u2019internato</label>
                  <Input placeholder="Es: nipote, figlio" />
                </div>
              </div>
            </Card>
          </Section>

          <Section title="Comunicazioni e consensi">
            <Card>
              <div className="flex flex--wrap" style={{ gap: 'var(--s-2)' }}>
                <Button variant="secondary" size="sm"><Upload size={12} /> Carica documento</Button>
                <Button variant="secondary" size="sm"><Clock size={12} /> Registra comunicazione</Button>
                <Button variant="secondary" size="sm"><Mail size={12} /> Genera bozza email</Button>
              </div>
              <div className="text-xs text-muted mt-3">
                Ogni comunicazione viene registrata con timestamp, fonte, ufficio e contatto.
              </div>
            </Card>
          </Section>

          <Section title="Genera fascicolo">
            <Card variant="info">
              <p className="text-sm">
                Il fascicolo completo includerà: dati dell\u2019internato, fonti archivistiche,
                requisiti verificati, documenti caricati, comunicazioni registrate e contatti del discendente.
              </p>
              <Button className="mt-3"><FileText size={14} /> Genera fascicolo completo</Button>
            </Card>
          </Section>
        </>
      )}
    </>
  );
}
