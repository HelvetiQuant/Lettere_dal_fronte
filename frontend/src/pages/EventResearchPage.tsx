import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { NarrativeReport, EventSource, EventResolution, HistoricalMap } from '@/api/types';
import { Card, Tag, LoadingState, ErrorState, Button } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { HistoricalMap as HistoricalMapView } from '@/components/graph/HistoricalMap';

type TabId = 'narrativo' | 'cronologia' | 'fonti' | 'documenti' | 'mappa' | 'punti-vista' | 'persone';

const TABS: { id: TabId; label: string }[] = [
  { id: 'narrativo', label: 'Dossier narrativo' },
  { id: 'cronologia', label: 'Cronologia' },
  { id: 'fonti', label: 'Fonti e verifica' },
  { id: 'documenti', label: 'Documenti' },
  { id: 'mappa', label: 'Mappa storica' },
  { id: 'punti-vista', label: 'Punti di vista' },
  { id: 'persone', label: 'Persone collegate' },
];

function VerificationBadge({ status }: { status: string }) {
  const variant = status === 'verificata' ? 'success' : status === 'probabile' ? 'success' : status === 'candidata' ? 'warning' : 'neutral';
  const label = status === 'verificata' ? 'Verificata' : status === 'probabile' ? 'Probabile' : status === 'candidata' ? 'Candidata' : 'Non verificata';
  return <Tag variant={variant as 'success' | 'warning' | 'neutral'}>{label}</Tag>;
}

function SourceCard({ source }: { source: EventSource }) {
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 'var(--s-2)' }}>
        <div style={{ flex: 1 }}>
          <strong>{source.title || 'Senza titolo'}</strong>
          <div className="text-sm text-muted mt-1">{source.author_or_institution}</div>
          {source.archive_reference && (
            <div className="text-sm mt-1" style={{ fontFamily: 'var(--f-mono)' }}>{source.archive_reference}</div>
          )}
          {source.date && <div className="text-sm text-muted">Data: {source.date}</div>}
          {source.summary && (
            <div className="text-sm mt-2" style={{
              display: '-webkit-box',
              WebkitLineClamp: 5,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              lineHeight: '1.5',
              color: 'var(--c-text)',
              fontStyle: 'italic',
              borderLeft: '2px solid var(--c-divider)',
              paddingLeft: 'var(--s-2)',
            }}>
              {source.summary}
            </div>
          )}
          {source.url && (
            <a href={source.url} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>
              Apri fonte →
            </a>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-1)', alignItems: 'flex-end' }}>
          <VerificationBadge status={source.verification_status} />
          <Tag variant="neutral">{source.source_type}</Tag>
          {source.temporal_compatible && <Tag variant="success">Periodo ✓</Tag>}
          {source.geographic_compatible && <Tag variant="success">Luogo ✓</Tag>}
        </div>
      </div>
      {source.verification_note && (
        <div className="text-xs text-muted mt-2" style={{ borderTop: '1px solid var(--c-divider)', paddingTop: 'var(--s-1)' }}>
          {source.verification_note}
        </div>
      )}
    </Card>
  );
}

function AmbiguityWarning({ resolution }: { resolution: EventResolution }) {
  if (!resolution.ambiguity_warning) return null;
  return (
    <Card>
      <div style={{ borderLeft: '3px solid var(--c-warning)', paddingLeft: 'var(--s-3)' }}>
        <strong style={{ color: 'var(--c-warning)' }}>⚠ Avviso di disambiguazione</strong>
        <p className="mt-2">{resolution.ambiguity_warning}</p>
        {resolution.proposed_distinctions.length > 0 && (
          <div className="mt-2">
            <strong>Distinzioni proposte:</strong>
            <ul style={{ marginTop: 'var(--s-1)', paddingLeft: 'var(--s-4)' }}>
              {resolution.proposed_distinctions.map((d, i) => (
                <li key={i}>
                  <Tag variant={d.type === 'evento_generale' ? 'accent' : d.type === 'episodio_specifico' ? 'success' : 'neutral'}>
                    {d.type.replace(/_/g, ' ')}
                  </Tag>{' '}
                  <strong>{d.nome}</strong>
                  {d.periodo && <span className="text-sm text-muted"> — {d.periodo}</span>}
                  {d.luogo && <span className="text-sm text-muted"> — {d.luogo}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

export function EventResearchPage() {
  const { eventName } = useParams<{ eventName: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<NarrativeReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('narrativo');
  const [useAI, setUseAI] = useState(true);
  const [mapData, setMapData] = useState<HistoricalMap | null>(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const loadReport = useCallback((ai: boolean) => {
    if (!eventName) return;
    const name = decodeURIComponent(eventName);
    setLoading(true);
    api.eventNarrative(name, ai, 'gpt')
      .then((r) => setReport(r))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, [eventName]);

  useEffect(() => {
    loadReport(false);
  }, [loadReport]);

  const loadMap = useCallback(() => {
    if (!eventName) return;
    const name = decodeURIComponent(eventName);
    setMapLoading(true);
    setMapError(null);
    api.eventMap(name)
      .then((m) => setMapData(m))
      .catch((e) => setMapError(e instanceof ApiError ? e.userMessage : String(e)))
      .finally(() => setMapLoading(false));
  }, [eventName]);

  useEffect(() => {
    if (activeTab === 'mappa' && !mapData && !mapLoading) {
      loadMap();
    }
  }, [activeTab, mapData, mapLoading, loadMap]);

  const ev = report?.resolution;
  const sources = report?.evidence_package?.sources || [];
  const archivalSources = report?.fonti_archivistiche || [];
  const biblioSources = report?.fonti_bibliografiche || [];
  const people = report?.persone_collegate || [];
  const graphNodes = report?.grafo?.nodes || [];
  const graphEdges = report?.grafo?.edges || [];
  const cronologia = report?.cronologia || [];
  const luoghi = report?.luoghi || [];
  const reparti = report?.reparti || [];
  const fattiConcordanti = (report?.fatti_concordanti || []).filter((f) => !(f.fonti || []).includes('EVENT-META'));
  const versioniDivergenti = report?.versioni_divergenti || [];
  const elementiIncerti = report?.elementi_incerti || [];
  const concordantSummary = report?.sintesi_concordanti || '';
  const documents = report?.evidence_package?.related_documents || [];

  return (
    <>
      <PageIntro
        title={ev?.canonical || decodeURIComponent(eventName || '')}
        description="Dossier storico generato dalla pipeline di ricerca evidenze. Ogni affermazione è collegata alle fonti che la sostengono."
        aiNote={report?.ai_used ? `Narrazione generata con AI (${report.ai_model}). Nessuna memoria generale usata come fonte.` : 'Narrazione generata esclusivamente dai dati strutturati senza AI.'}
        steps={['Risoluzione e disambiguazione evento', 'Raccolta fonti (interne, archivistiche, istituzionali, web)', 'Estrazione claim verificabili', 'Generazione narrazione da evidenze']}
      />

      {error && <ErrorState message={error.userMessage} />}
      {loading && <LoadingState />}

      {!loading && !error && ev && (
        <>
          {/* Ambiguity warning */}
          {ev.ambiguity_warning && <AmbiguityWarning resolution={ev} />}

          {/* AI toggle */}
          <div className="flex flex--wrap mb-4" style={{ gap: 'var(--s-2)', alignItems: 'center' }}>
            <Button
              variant={useAI ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => { const next = !useAI; setUseAI(next); loadReport(next); }}
            >
              {useAI ? 'AI attiva (GPT-4.1)' : 'Modalità senza AI'}
            </Button>
            <span className="text-sm text-muted">
              {report?.ai_used ? `Generato con ${report.ai_model}` : 'Narrazione da dati strutturati'}
            </span>
          </div>

          {/* Tabs */}
          <div className="flex flex--wrap mb-4" style={{ gap: 'var(--s-1)', borderBottom: '2px solid var(--c-divider)', paddingBottom: 'var(--s-2)' }}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  padding: 'var(--s-1) var(--s-3)',
                  border: 'none',
                  background: activeTab === tab.id ? 'var(--c-accent)' : 'transparent',
                  color: activeTab === tab.id ? 'white' : 'var(--c-text)',
                  borderRadius: 'var(--r-sm)',
                  cursor: 'pointer',
                  fontWeight: activeTab === tab.id ? 600 : 400,
                  fontSize: 'var(--fs-sm)',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === 'narrativo' && (
            <>
              {report?.sections.map((sec, i) => (
                <Section key={i} title={sec.section}>
                  <Card>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{sec.text}</div>
                    {sec.source_ids.length > 0 && (
                      <div className="mt-2" style={{ borderTop: '1px solid var(--c-divider)', paddingTop: 'var(--s-1)' }}>
                        <span className="text-xs text-muted">Fonti: </span>
                        {sec.source_ids.map((sid) => (
                          <Tag key={sid} variant="neutral">{sid}</Tag>
                        ))}
                      </div>
                    )}
                  </Card>
                </Section>
              ))}
            </>
          )}

          {activeTab === 'cronologia' && (
            <Section title="Cronologia e fasi">
              {cronologia.length > 0 ? (
                <Card>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-2)' }}>
                    {cronologia.map((c, i) => (
                      <div key={i} style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'baseline', borderBottom: i < cronologia.length - 1 ? '1px solid var(--c-divider)' : 'none', paddingBottom: 'var(--s-2)' }}>
                        <span style={{ fontFamily: 'var(--f-mono)', fontSize: 'var(--fs-sm)', minWidth: 120, color: 'var(--c-text-muted)' }}>{c.data}</span>
                        <span>{c.descrizione || c.fase}</span>
                        {(c.fonti || []).length > 0 && (c.fonti || []).map((f) => <Tag key={f} variant="neutral">{f}</Tag>)}
                      </div>
                    ))}
                  </div>
                </Card>
              ) : (
                <Card><p className="text-muted">Nessun dato cronologico attestato nelle fonti recuperate.</p></Card>
              )}
              {reparti.length > 0 && (
                <Section title="Reparti e soggetti coinvolti">
                  <Card>
                    <ul>
                      {reparti.map((r, i) => (
                        <li key={i}><strong>{r.nome}</strong> — {r.ruolo}</li>
                      ))}
                    </ul>
                  </Card>
                </Section>
              )}
            </Section>
          )}

          {activeTab === 'fonti' && (
            <>
              <Section title={`Fonti archivistiche (${archivalSources.length})`}>
                <div className="grid grid--auto">
                  {archivalSources.map((s) => <SourceCard key={s.source_id} source={s} />)}
                </div>
              </Section>
              <Section title={`Fonti bibliografiche e web (${biblioSources.length})`}>
                <div className="grid grid--auto">
                  {biblioSources.map((s) => <SourceCard key={s.source_id} source={s} />)}
                </div>
              </Section>
              <Section title="Verifica fonti">
                <Card>
                  <div className="grid grid--2">
                    <div><strong>Verificate:</strong> {sources.filter(s => s.verification_status === 'verificata').length}</div>
                    <div><strong>Probabili:</strong> {sources.filter(s => s.verification_status === 'probabile').length}</div>
                    <div><strong>Candidate:</strong> {sources.filter(s => s.verification_status === 'candidata').length}</div>
                    <div><strong>Compatibilità temporale:</strong> {sources.filter(s => s.temporal_compatible).length}/{sources.length}</div>
                    <div><strong>Compatibilità geografica:</strong> {sources.filter(s => s.geographic_compatible).length}/{sources.length}</div>
                  </div>
                </Card>
              </Section>
            </>
          )}

          {activeTab === 'documenti' && (
            <Section title={`Documenti collegati (${documents.length})`}>
              {documents.length > 0 ? (
                <div className="grid grid--auto">
                  {documents.map((d: Record<string, unknown>, i: number) => (
                    <Card key={i}>
                      <strong>{(d.title as string) || 'Documento'}</strong>
                      {d.provider && <Tag variant="neutral">{d.provider as string}</Tag>}
                      {d.doc_type && <Tag variant="accent">{d.doc_type as string}</Tag>}
                      {d.place && <div className="text-sm text-muted mt-1">{d.place as string}</div>}
                      {d.source_url && <a href={d.source_url as string} target="_blank" rel="noopener" className="text-sm mt-2" style={{ display: 'inline-block' }}>Apri →</a>}
                    </Card>
                  ))}
                </div>
              ) : (
                <Card><p className="text-muted">Nessun documento collegato recuperato.</p></Card>
              )}
            </Section>
          )}

          {activeTab === 'mappa' && (
            <Section title="Luoghi e spostamenti">
              {luoghi.length > 0 ? (
                <Card>
                  <ul>
                    {luoghi.map((l, i) => (
                      <li key={i}><strong>{l.nome}</strong> — {l.ruolo}</li>
                    ))}
                  </ul>
                </Card>
              ) : (
                <Card><p className="text-muted">Nessun luogo attestato nelle fonti recuperate.</p></Card>
              )}
            </Section>
          )}

          {activeTab === 'punti-vista' && (
            <>
              <Section title="Fatti concordanti tra le fonti">
                {concordantSummary && (
                  <Card>
                    <div style={{ whiteSpace: 'pre-wrap', marginBottom: 'var(--s-3)' }}>{concordantSummary}</div>
                  </Card>
                )}
                {fattiConcordanti.length > 0 ? (
                  <Card>
                    <ul>
                      {fattiConcordanti.map((f, i) => (
                        <li key={i}>{f.fatto} {(f.fonti || []).map((src) => <Tag key={src} variant="success">{src}</Tag>)}</li>
                      ))}
                    </ul>
                  </Card>
                ) : (
                  !concordantSummary && <Card><p className="text-muted">Nessun fatto concordante tra fonti indipendenti.</p></Card>
                )}
              </Section>
              <Section title="Versioni divergenti">
                {versioniDivergenti.length > 0 ? (
                  <Card>
                    {versioniDivergenti.map((v, i) => (
                      <div key={i} style={{ marginBottom: 'var(--s-3)', paddingBottom: 'var(--s-2)', borderBottom: i < versioniDivergenti.length - 1 ? '1px solid var(--c-divider)' : 'none' }}>
                        <strong>{v.fatto}</strong>
                        <div className="mt-1"><Tag variant="accent">A</Tag> {v.versione_a} <Tag variant="neutral">{v.fonte_a}</Tag></div>
                        <div className="mt-1"><Tag variant="warning">B</Tag> {v.versione_b} <Tag variant="neutral">{v.fonte_b}</Tag></div>
                      </div>
                    ))}
                  </Card>
                ) : (
                  <Card><p className="text-muted">Nessuna versione divergente rilevata.</p></Card>
                )}
              </Section>
              <Section title="Elementi incerti o non verificabili">
                {elementiIncerti.length > 0 ? (
                  <Card>
                    <ul>
                      {elementiIncerti.map((e, i) => (
                        <li key={i}><strong>{e.elemento}</strong> — {e.motivo} {(e.fonti || []).map((src) => <Tag key={src} variant="warning">{src}</Tag>)}</li>
                      ))}
                    </ul>
                  </Card>
                ) : (
                  <Card><p className="text-muted">Nessun elemento incerto rilevato.</p></Card>
                )}
              </Section>
            </>
          )}

          {activeTab === 'mappa' && (
            <>
              {mapLoading && <LoadingState />}
              {mapError && <ErrorState message={mapError} />}
              {!mapLoading && !mapError && mapData && (
                <>
                  <Section title={mapData.title}>
                    <Card>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--s-2)' }}>
                        <div className="text-sm text-muted">
                          {mapData.locations.length} luoghi · {mapData.lines.length} linee · {mapData.movements.length} movimenti · {mapData.phases.length} fasi
                        </div>
                        <a
                          href={api.eventMapSvgUrl(decodeURIComponent(eventName || ''))}
                          download
                          className="text-sm"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s-1)', padding: 'var(--s-1) var(--s-2)', border: '1px solid var(--c-accent)', borderRadius: 'var(--r-sm)', textDecoration: 'none', color: 'var(--c-accent)' }}
                        >
                          ⬇ Scarica SVG
                        </a>
                      </div>
                      <HistoricalMapView
                        locations={mapData.locations}
                        lines={mapData.lines}
                        movements={mapData.movements}
                        phases={mapData.phases}
                        isPartial={mapData.is_partial}
                        partialNote={mapData.partial_note}
                      />
                    </Card>
                  </Section>

                  {mapData.phases.length > 0 && (
                    <Section title="Fasi della battaglia">
                      <Card>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-2)' }}>
                          {mapData.phases.map((phase, i) => (
                            <div key={i} style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'center' }}>
                              <div style={{ width: 16, height: 16, borderRadius: '50%', background: phase.color, flexShrink: 0 }} />
                              <div>
                                <strong>{phase.name}</strong>
                                <span className="text-sm text-muted"> — {phase.start_date} → {phase.end_date}</span>
                                <div className="text-sm text-muted">{phase.description}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </Card>
                    </Section>
                  )}

                  {mapData.locations.length > 0 && (
                    <Section title={`Luoghi mappati (${mapData.locations.length})`}>
                      <Card>
                        <div className="grid grid--auto">
                          {mapData.locations.map((loc, i) => (
                            <div key={i} style={{ padding: 'var(--s-2)', border: '1px solid var(--c-divider)', borderRadius: 'var(--r-sm)' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-1)' }}>
                                <span style={{ fontFamily: 'var(--f-mono)', fontWeight: 700, color: 'var(--c-accent)' }}>{loc.label_number}</span>
                                <strong>{loc.name}</strong>
                              </div>
                              <div className="text-xs text-muted mt-1">
                                {loc.lat.toFixed(4)}°N, {loc.lon.toFixed(4)}°E
                              </div>
                              <div className="flex flex--wrap mt-1" style={{ gap: 'var(--s-1)' }}>
                                <Tag variant="neutral">{loc.role}</Tag>
                                <Tag variant={loc.verification === 'verified' ? 'success' : loc.verification === 'probable' ? 'warning' : 'neutral'}>
                                  {loc.verification === 'verified' ? 'verificato' : loc.verification === 'probable' ? 'probabile' : 'ipotetico'}
                                </Tag>
                              </div>
                            </div>
                          ))}
                        </div>
                      </Card>
                    </Section>
                  )}

                  {mapData.legend.length > 0 && (
                    <Section title="Legenda">
                      <Card>
                        <div className="grid grid--2">
                          {mapData.legend.map((item, i) => (
                            <div key={i} className="text-sm">
                              <strong>{item.symbol}</strong> — {item.meaning}
                            </div>
                          ))}
                        </div>
                      </Card>
                    </Section>
                  )}

                  {mapData.sub_maps.length > 0 && (
                    <Section title="Sotto-mappe per fase">
                      {mapData.sub_maps.map((sub, i) => (
                        <Card key={i}>
                          <strong>{sub.title}</strong>
                          <div className="text-sm text-muted mt-1">
                            {sub.locations.length} luoghi · {sub.lines.length} linee · {sub.movements.length} movimenti
                          </div>
                          <HistoricalMapView
                            locations={sub.locations}
                            lines={sub.lines}
                            movements={sub.movements}
                            isPartial={sub.is_partial}
                            partialNote={sub.partial_note}
                          />
                        </Card>
                      ))}
                    </Section>
                  )}
                </>
              )}
            </>
          )}

          {activeTab === 'persone' && (
            <Section title={`Persone collegate (${people.length})`}>
              {people.length > 0 ? (
                <div className="grid grid--auto">
                  {people.slice(0, 50).map((p: Record<string, unknown>, i: number) => (
                    <Card key={i}>
                      <div onClick={() => {
                        const ptype = p.type as string;
                        const pid = p.id as number;
                        if (ptype === 'caduto') navigate(`/soldato/caduti/${pid}`);
                        else if (ptype === 'decorato') navigate(`/soldato/decorati/${pid}`);
                        else if (ptype === 'internato') navigate(`/soldato/internati/${pid}`);
                      }} style={{ cursor: 'pointer' }} role="button" tabIndex={0}>
                        <Tag variant={p.type === 'caduto' ? 'neutral' : p.type === 'decorato' ? 'warning' : 'accent'}>
                          {p.type as string}
                        </Tag>{' '}
                        <strong>{p.nominativo as string}</strong>
                        {p.grado && <span className="text-sm text-muted"> — {p.grado as string}</span>}
                        {p.luogo_morte && <div className="text-sm text-muted mt-1">Caduto a: {p.luogo_morte as string}</div>}
                        {p.decorazione && <div className="text-sm text-muted mt-1">Decorazione: {p.decorazione as string}</div>}
                        {p.luogo_internamento && <div className="text-sm text-muted mt-1">Internamento: {p.luogo_internamento as string}</div>}
                      </div>
                    </Card>
                  ))}
                </div>
              ) : (
                <Card><p className="text-muted">Nessuna persona collegata recuperata.</p></Card>
              )}
            </Section>
          )}
        </>
      )}
    </>
  );
}
