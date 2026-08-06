import { useState, useEffect } from 'react';
import { Activity, Database, FileText, Download, Link2, Globe, StopCircle, Shield, AlertTriangle, CheckCircle } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { StatusResponse, SourceStatsResponse } from '@/api/types';
import { Card, Tag, LoadingState, ErrorState, PartialDataNotice } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { OperationConfirm } from '@/components/forms/OperationConfirm';

export function AdminPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [sourceStats, setSourceStats] = useState<SourceStatsResponse | null>(null);
  const [corrections, setCorrections] = useState<{ total: number; corrections: Record<string, unknown>[] } | null>(null);
  const [narrator, setNarrator] = useState<{ version: string; circuit_breaker_open?: boolean; evidence_locked?: boolean; hallucination_check?: boolean; error?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [partial, setPartial] = useState(false);

  const refresh = () => {
    setLoading(true);
    Promise.allSettled([api.status(), api.sourceStats(), api.corrections(10), api.narratorStatus()])
      .then(([statusRes, srcRes, corrRes, narrRes]) => {
        if (statusRes.status === 'fulfilled') setStatus(statusRes.value);
        else setPartial(true);
        if (srcRes.status === 'fulfilled') setSourceStats(srcRes.value);
        else setPartial(true);
        if (corrRes.status === 'fulfilled') setCorrections(corrRes.value);
        if (narrRes.status === 'fulfilled') setNarrator(narrRes.value);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { refresh(); }, []);

  return (
    <>
      <PageIntro
        title="Amministrazione"
        description="Stato del sistema, statistiche fonti e operazioni batch. Ogni operazione richiede preparazione e conferma esplicita."
        aiNote="Le operazioni batch possono richiedere minuti o ore. Il sistema mostra lo stato in tempo reale e permette l'arresto quando supportato."
        steps={['Verifica lo stato del sistema', 'Prepara e conferma un\u2019operazione', 'Monitora l\u2019avanzamento']}
      />

      {error && <ErrorState message={error.userMessage} onRetry={refresh} />}
      {partial && <PartialDataNotice message="Alcuni dati non sono disponibili dal backend." />}
      {loading && <LoadingState />}

      {!loading && (
        <>
          <Section title="Stato sistema">
            <Card>
              <div className="flex flex--center mb-3" style={{ gap: 'var(--s-2)' }}>
                <Activity size={18} aria-hidden="true" />
                <span className="text-sm">
                  {status?.running ? (
                    <Tag variant="accent">Operazione in corso: {status.running}</Tag>
                  ) : (
                    <Tag variant="success">Sistema inattivo</Tag>
                  )}
                </span>
              </div>
              <div className="grid grid--2">
                <div><strong>Internati totali:</strong> {status?.total_internati?.toLocaleString('it-IT') || '—'}</div>
                <div><strong>Da revisionare:</strong> {status?.needs_review?.toLocaleString('it-IT') || '—'}</div>
              </div>
              {status?.letters && status.letters.length > 0 && (
                <div className="mt-3">
                  <h3>Lettere alfabetiche</h3>
                  <div className="flex flex--wrap mt-2" style={{ gap: 'var(--s-1)' }}>
                    {status.letters.map((l) => (
                      <Tag key={l.letter} variant={l.downloaded ? 'success' : 'neutral'}>
                        {l.letter}: {l.done}/{l.total}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          </Section>

          {sourceStats && (
            <Section title="Statistiche fonti esterne">
              <Card>
                <div className="grid grid--2">
                  <div><strong>Fonti totali:</strong> {sourceStats.total_sources}</div>
                  <div><strong>Provider:</strong> {sourceStats.providers}</div>
                  <div><strong>Cache:</strong> {sourceStats.cache_count} file ({(sourceStats.cache_total_bytes / 1024 / 1024).toFixed(1)} MB)</div>
                </div>
                {sourceStats.provider_names && sourceStats.provider_names.length > 0 && (
                  <div className="flex flex--wrap mt-2" style={{ gap: 'var(--s-1)' }}>
                    {sourceStats.provider_names.map((p) => <Tag key={p} variant="neutral">{p}</Tag>)}
                  </div>
                )}
              </Card>
            </Section>
          )}

          <Section title="Operazioni batch">
            <div className="grid grid--2">
              <OperationConfirm
                name="Build entità e collegamenti"
                description="Estrae entità (persone, luoghi, eventi) dai record e costruisce collegamenti cross-dataset. Può richiedere diversi minuti."
                onConfirm={() => api.entitaBuild()}
                onStop={() => api.entitaStop()}
                running={status?.running === 'entita_build'}
              />
              <OperationConfirm
                name="Scraping decorati"
                description="Scarica e indicizza i decorati dagli Albi della Memoria ISTORECO. Richiede connessione a cimeetrincee.it."
                onConfirm={() => api.decoratiScrape()}
                onStop={() => api.decoratiStop()}
                running={status?.running === 'decorati_scrape'}
              />
              <OperationConfirm
                name="Estrazione fondi archivistici"
                description="Estrae testo dai PDF dei fondi dell'Ufficio Storico SME. Richiede PDF scaricati. Usa OCR se necessario."
                onConfirm={() => api.fondiExtractAll()}
                onStop={() => api.fondiStop()}
                running={status?.running === 'fondi_extract'}
              />
              <OperationConfirm
                name="Scraping fonti esterne"
                description="Avvia lo scraping di una fonte esterna specifica (richiede fonte_id o URL)."
                onConfirm={() => api.fontiScrape()}
              />
            </div>
          </Section>

          {narrator && (
            <Section title="Narratore V7.3">
              <Card>
                <div className="flex flex--center mb-3" style={{ gap: 'var(--s-2)' }}>
                  <Shield size={18} aria-hidden="true" />
                  <span className="text-sm">
                    <Tag variant="accent">Versione {narrator.version}</Tag>
                  </span>
                </div>
                <div className="grid grid--2">
                  <div>
                    <strong>Circuit Breaker:</strong>{' '}
                    {narrator.error ? (
                      <Tag variant="warning">Errore</Tag>
                    ) : narrator.circuit_breaker_open ? (
                      <Tag variant="warning">Aperto (AI non disponibile)</Tag>
                    ) : (
                      <Tag variant="success">Chiuso (AI operativa)</Tag>
                    )}
                  </div>
                  <div>
                    <strong>Evidence-Locked:</strong>{' '}
                    {narrator.evidence_locked ? (
                      <Tag variant="success"><CheckCircle size={12} /> Attivo</Tag>
                    ) : (
                      <Tag variant="neutral">Non attivo</Tag>
                    )}
                  </div>
                  <div>
                    <strong>Hallucination Check:</strong>{' '}
                    {narrator.hallucination_check ? (
                      <Tag variant="success"><CheckCircle size={12} /> Attivo</Tag>
                    ) : (
                      <Tag variant="neutral">Non attivo</Tag>
                    )}
                  </div>
                  <div>
                    <strong>Fallback deterministico:</strong>{' '}
                    <Tag variant="success"><CheckCircle size={12} /> Attivo</Tag>
                  </div>
                </div>
                {narrator.error && (
                  <div className="mt-2 text-sm" style={{ color: 'var(--c-warning)' }}>
                    <AlertTriangle size={12} /> {narrator.error}
                  </div>
                )}
              </Card>
            </Section>
          )}

          {corrections && (
            <Section title="Correzioni dati (V7.3 overlay)">
              <Card>
                <div className="flex flex--center mb-3" style={{ gap: 'var(--s-2)' }}>
                  <FileText size={18} aria-hidden="true" />
                  <span className="text-sm">
                    <Tag variant="accent">{corrections.total} correzioni totali</Tag>
                  </span>
                </div>
                {corrections.corrections.length > 0 ? (
                  <div className="mt-2">
                    <table className="table" style={{ width: '100%', fontSize: '0.875rem' }}>
                      <thead>
                        <tr>
                          <th>Tabella</th>
                          <th>Record</th>
                          <th>Campo</th>
                          <th>Valore originale</th>
                          <th>Valore corretto</th>
                          <th>Fonte</th>
                          <th>Data</th>
                        </tr>
                      </thead>
                      <tbody>
                        {corrections.corrections.map((c, i) => (
                          <tr key={i}>
                            <td>{String(c.table_name || '—')}</td>
                            <td>{String(c.record_id || '—')}</td>
                            <td>{String(c.field_name || '—')}</td>
                            <td style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {String(c.old_value || '—')}
                            </td>
                            <td style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              <strong>{String(c.new_value || '—')}</strong>
                            </td>
                            <td>{String(c.source || '—')}</td>
                            <td style={{ fontSize: '0.75rem' }}>{String(c.created_at || '—').slice(0, 10)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm" style={{ color: 'var(--c-text-muted)' }}>
                    Nessuna correzione registrata. Le correzioni sono overlay non distruttivi
                    (i dati originali non vengono mai modificati direttamente).
                  </p>
                )}
              </Card>
            </Section>
          )}

          <Section title="Azioni rapide">
            <div className="flex flex--wrap" style={{ gap: 'var(--s-2)' }}>
              <button className="btn btn--secondary btn--sm" onClick={refresh}>
                <Database size={12} /> Aggiorna stato
              </button>
              <button className="btn btn--secondary btn--sm" onClick={() => api.fondiAvailable().then(() => refresh())}>
                <Download size={12} /> Verifica fondi disponibili
              </button>
            </div>
          </Section>
        </>
      )}
    </>
  );
}
