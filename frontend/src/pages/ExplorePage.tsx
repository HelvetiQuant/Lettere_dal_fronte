import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Search, AlertCircle } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { SearchResult, ValidatedSearchResult, InternatoRecord, CadutoRecord, DecoratoRecord, MenzioneRecord, DocumentoRecord, FonteNarrativa, LetteraPersonale, EventRecord, ExternalSourceHit, ConfirmationItem } from '@/api/types';
import { Card, Tag, Input, Button, LoadingState, EmptyState, ErrorState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { SourceCard, EvidenceStatus } from '@/components/sources/SourceCard';
import { ResultGroup } from '@/components/dossier/DossierParts';

interface MergedResults extends SearchResult {
  external_results?: ExternalSourceHit[];
  confirmations?: ConfirmationItem[];
  status?: 'ok' | 'needs_confirmation';
}

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState(params.get('q') || '');
  const [results, setResults] = useState<MergedResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const doSearch = async (q: string) => {
    if (q.trim().length < 2) return;
    setLoading(true);
    setError(null);
    setParams({ q: q.trim() });
    try {
      const [dbData, validatedData] = await Promise.allSettled([
        api.search(q.trim(), 50),
        api.searchValidated(q.trim(), 50, true),
      ]);

      const merged: MergedResults = {};
      if (dbData.status === 'fulfilled') {
        Object.assign(merged, dbData.value);
      }
      if (validatedData.status === 'fulfilled') {
        merged.external_results = validatedData.value.external_results || [];
        merged.confirmations = validatedData.value.confirmations || [];
        merged.status = validatedData.value.status;
      }
      setResults(merged);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const q = params.get('q');
    if (q) { setQuery(q); doSearch(q); }
  }, []);

  const internati = results?.internati || [];
  const caduti = results?.caduti || [];
  const decorati = results?.decorati || [];
  const menzioni = results?.menzioni || [];
  const documenti = results?.documenti || [];
  const fontiNarrative = results?.fonti_narrative || [];
  const lettere = results?.lettere_personali || [];
  const events = results?.events || [];
  const external = results?.external_results || [];
  const confirmations = results?.confirmations || [];
  const needsConfirmation = results?.status === 'needs_confirmation';
  const hasAny = internati.length || caduti.length || decorati.length || menzioni.length || documenti.length || fontiNarrative.length || lettere.length || events.length || external.length;

  return (
    <>
      <PageIntro
        title="Esplora"
        description="Cerca in tutti i database dell'archivio: internati, caduti, decorati, menzioni, documenti, fonti narrative, lettere e fonti esterne. Ogni risultato è collegato alla fonte di provenienza."
        aiNote="L'IA valida i risultati incrociando dataset diversi e segnala discrepanze, omonimie e dati da confermare."
        steps={['Scrivi un nome, un luogo o un evento', 'Esamina i risultati per categoria', 'Apri il dossier per i dettagli']}
      />

      <Section>
        <div className="flex" style={{ gap: 'var(--s-2)' }}>
          <Input
            placeholder="Cerca persone, eventi, luoghi…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch(query)}
            className="input--lg"
            aria-label="Campo di ricerca"
          />
          <Button onClick={() => doSearch(query)}><Search size={16} /> Cerca</Button>
        </div>
      </Section>

      {error && <ErrorState message={error.userMessage} onRetry={() => doSearch(query)} />}
      {loading && <LoadingState label="Ricerca in corso…" />}

      {!loading && needsConfirmation && (
        <Card variant="info">
          <div className="flex flex--center" style={{ gap: 'var(--s-2)', color: 'var(--c-warning)' }}>
            <AlertCircle size={20} aria-hidden="true" />
            <strong>Risultati da confermare</strong>
          </div>
          <p className="text-sm mt-2">La pipeline di validazione ha rilevato possibili discrepanze nei seguenti campi:</p>
          <ul className="text-sm mt-2" style={{ paddingLeft: 'var(--s-5)' }}>
            {confirmations.map((c: ConfirmationItem, i: number) => (
              <li key={i}>
                <strong>{c.field}</strong> in {c.record_table} #{c.record_id}:
                valore attuale "{c.current_value}", valore suggerito "{c.corrected_value}"
                (confidenza: {(c.confidence * 100).toFixed(0)}%)
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!loading && results && !hasAny && (
        <EmptyState message="Nessun risultato trovato. Prova con un altro termine di ricerca." />
      )}

      {!loading && results && hasAny && (
        <>
          <ResultGroup<InternatoRecord>
            title="Internati"
            items={internati}
            render={(s) => (
              <Card key={s.id}>
                <div onClick={() => navigate(`/soldato/internati/${s.id}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <strong>{s.cognome} {s.nome}</strong>
                  {s.grado && <Tag variant="accent">{s.grado}</Tag>}
                  <div className="text-sm text-muted mt-2">
                    {s.data_nascita && <div>Nato: {s.data_nascita} a {s.luogo_nascita || '?'}</div>}
                    {s.luogo_internamento && <div>Internato a: {s.luogo_internamento}</div>}
                    {s.sorte && <div>Sorte: {s.sorte}</div>}
                  </div>
                </div>
              </Card>
            )}
          />

          <ResultGroup<CadutoRecord>
            title="Caduti"
            items={caduti}
            render={(c) => (
              <Card key={c.id}>
                <div onClick={() => navigate(`/soldato/caduti/${c.id}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <strong>{c.nominativo}</strong>
                  {c.grado && <Tag variant="neutral">{c.grado}</Tag>}
                  <div className="text-sm text-muted mt-2">
                    {c.anno_morte && <div>Caduto: {c.anno_morte} a {c.luogo_morte || '?'}</div>}
                    {c.reparto && <div>Reparto: {c.reparto}</div>}
                  </div>
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
                  {d.grado && <div className="text-sm text-muted mt-2">{d.grado}</div>}
                </div>
              </Card>
            )}
          />

          <ResultGroup<EventRecord>
            title="Eventi"
            items={events}
            render={(ev) => (
              <Card key={ev.nome}>
                <div onClick={() => navigate(`/eventi/${encodeURIComponent(ev.nome)}`)} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                  <strong>{ev.nome}</strong>
                  {ev.data_inizio && <div className="text-sm text-muted mt-2">{ev.data_inizio}{ev.data_fine ? ` — ${ev.data_fine}` : ''}</div>}
                  {ev.luogo && <div className="text-sm text-muted">{ev.luogo}</div>}
                </div>
              </Card>
            )}
          />

          <ResultGroup<MenzioneRecord>
            title="Menzioni"
            items={menzioni}
            render={(m) => (
              <Card key={m.id}>
                <strong>{m.nominativo || 'Menzione'}</strong>
                {m.fonte && <Tag variant="neutral">{m.fonte}</Tag>}
                {m.testo && <div className="text-sm text-muted mt-2">{m.testo.slice(0, 120)}…</div>}
              </Card>
            )}
          />

          <ResultGroup<DocumentoRecord>
            title="Documenti"
            items={documenti}
            render={(d) => (
              <Card key={d.id}>
                <strong>{d.titolo || 'Documento'}</strong>
                {d.tipo && <Tag variant="neutral">{d.tipo}</Tag>}
                {d.url && <a href={d.url} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>Apri →</a>}
              </Card>
            )}
          />

          <ResultGroup<FonteNarrativa>
            title="Fonti narrative"
            items={fontiNarrative}
            render={(f) => (
              <Card key={f.id}>
                <strong>{f.titolo || 'Fonte'}</strong>
                {f.autore && <div className="text-sm text-muted mt-2">{f.autore}</div>}
                {f.url && <a href={f.url} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>Apri →</a>}
              </Card>
            )}
          />

          <ResultGroup<LetteraPersonale>
            title="Lettere"
            items={lettere}
            render={(l) => (
              <Card key={l.id}>
                <strong>{l.mittente || 'Lettera'}</strong>
                {l.destinatario && <div className="text-sm text-muted mt-2">A: {l.destinatario}</div>}
                {l.data && <div className="text-sm text-muted">{l.data}</div>}
              </Card>
            )}
          />

          <ResultGroup<ExternalSourceHit>
            title="Fonti esterne"
            items={external}
            render={(hit, i) => (
              <SourceCard key={i} provider={hit.provider} title={hit.title} description={hit.description} url={hit.url} score={hit.score} />
            )}
          />
        </>
      )}
    </>
  );
}
