import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Network, Check, X, Info } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { InternatiLinksResponse, EntitaDetailResponse } from '@/api/types';
import { Card, Tag, Input, Button, LoadingState, ErrorState, EmptyState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { ForceGraph, type GraphNodeData, type GraphEdgeData } from '@/components/graph/ForceGraph';

interface GraphNode {
  id: string;
  type: string;
  label: string;
}
interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  reason: string;
  confidence: number;
  status: 'suggested' | 'to_verify' | 'confirmed' | 'rejected';
}

const NODE_TYPE_LABELS: Record<string, string> = {
  persona: 'Persona', fatto: 'Fatto', evento: 'Evento', luogo: 'Luogo',
  data: 'Data', reparto: 'Reparto', campo: 'Campo/Prigionia',
  documento: 'Documento', fonte: 'Fonte', pratica: 'Pratica',
};

export function HeuristicLinksPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [filterType, setFilterType] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');

  useEffect(() => {
    const q = params.get('q');
    if (q) { setQuery(q); searchLinks(q); }
  }, []);

  const searchLinks = async (q?: string) => {
    const searchTerm = (q || query).trim();
    if (searchTerm.length < 2) return;
    setLoading(true);
    setError(null);
    setNodes([]);
    setEdges([]);
    try {
      const searchResult = await api.search(searchTerm, 20);
      const internati = searchResult.internati || [];
      if (internati.length === 0) {
        setLoading(false);
        return;
      }
      const firstId = internati[0].id;
      const [linksRes, entitaRes] = await Promise.allSettled([
        api.internatiLinks(firstId),
        api.entitaSearch(searchTerm, 20).catch(() => null),
      ]);

      const newNodes: GraphNode[] = [];
      const newEdges: GraphEdge[] = [];

      newNodes.push({ id: `internati:${firstId}`, type: 'persona', label: `${internati[0].cognome} ${internati[0].nome}` });

      if (linksRes.status === 'fulfilled' && linksRes.value) {
        const links: InternatiLinksResponse = linksRes.value;
        for (const l of links.links || []) {
          const targetId = `${l.to_table}:${l.to_id}`;
          if (!newNodes.find(n => n.id === targetId)) {
            newNodes.push({ id: targetId, type: l.to_table, label: `${l.to_table} #${l.to_id}` });
          }
          newEdges.push({
            source: `${l.from_table}:${l.from_id}`,
            target: targetId,
            relation: l.link_type,
            reason: `Collegamento registrato in ${l.from_table}`,
            confidence: l.confidence || 0.5,
            status: l.confidence && l.confidence >= 0.8 ? 'confirmed' : 'to_verify',
          });
        }
      }

      setLoading(false);
      setNodes(newNodes);
      setEdges(newEdges);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      setLoading(false);
    }
  };

  const filteredNodes = filterType ? nodes.filter(n => n.type === filterType) : nodes;
  const filteredEdges = filterStatus ? edges.filter(e => e.status === filterStatus) : edges;

  const updateEdgeStatus = (idx: number, status: GraphEdge['status']) => {
    setEdges(prev => prev.map((e, i) => i === idx ? { ...e, status } : e));
  };

  return (
    <>
      <PageIntro
        title="Collegamenti euristici"
        description="Costruisce un grafo tra fonti diverse che citano le stesse persone, fatti, eventi, luoghi, date, reparti o documenti. Ogni arco ha tipo di relazione, motivazione, fonti di supporto, attendibilità e stato."
        aiNote="L'IA suggerisce collegamenti tra entità sulla base di co-occorrenze, corrispondenze nominative e risultati del Research Orchestrator. Il ricercatore conferma o respinge ogni suggerimento."
        steps={[
          'Cerca una persona, fatto o evento',
          'Esamina i nodi e i collegamenti nel grafo',
          'Conferma o respingi i suggerimenti',
        ]}
      />

      <Section>
        <div className="flex" style={{ gap: 'var(--s-2)' }}>
          <Input
            placeholder="Es: Gaiaschi Luigi"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && searchLinks()}
            className="input--lg"
            aria-label="Query per collegamenti"
          />
          <Button onClick={() => searchLinks()} disabled={loading}>
            <Network size={16} /> {loading ? 'Costruzione…' : 'Costruisci grafo'}
          </Button>
        </div>
      </Section>

      {error && <ErrorState message={error.userMessage} onRetry={() => searchLinks()} />}
      {loading && <LoadingState label="Costruzione del grafo in corso…" />}

      {!loading && nodes.length === 0 && !error && (
        <EmptyState message="Nessun nodo trovato. Eseguire una ricerca per generare il grafo." />
      )}

      {nodes.length > 0 && (
        <>
          <Section title="Filtri">
            <Card>
              <div className="flex flex--wrap" style={{ gap: 'var(--s-3)' }}>
                <div>
                  <label className="text-sm text-muted">Tipo nodo</label>
                  <select className="select" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                    <option value="">Tutti</option>
                    {Object.entries(NODE_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm text-muted">Stato arco</label>
                  <select className="select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                    <option value="">Tutti</option>
                    <option value="suggested">Suggerito</option>
                    <option value="to_verify">Da verificare</option>
                    <option value="confirmed">Confermato</option>
                    <option value="rejected">Respinto</option>
                  </select>
                </div>
              </div>
            </Card>
          </Section>

          <Section title="Grafo interattivo">
            <ForceGraph
              nodes={filteredNodes as GraphNodeData[]}
              edges={filteredEdges as GraphEdgeData[]}
              minHeight={750}
              maxHeight={90}
            />
          </Section>

          <Section title={`Nodi (${filteredNodes.length})`}>
            <details>
              <summary className="text-sm text-muted" style={{ cursor: 'pointer', padding: 'var(--s-1) 0' }}>
                Mostra elenco nodi
              </summary>
              <div className="grid grid--auto" style={{ marginTop: 'var(--s-2)' }}>
                {filteredNodes.map((n) => (
                  <Card key={n.id}>
                    <Tag variant="accent">{NODE_TYPE_LABELS[n.type] || n.type}</Tag>
                    <div style={{ fontWeight: 600, marginTop: 6 }}>{n.label}</div>
                    <div className="text-xs text-muted">{n.id}</div>
                  </Card>
                ))}
              </div>
            </details>
          </Section>

          <Section title={`Collegamenti (${filteredEdges.length})`}>
            {filteredEdges.length === 0 ? (
              <EmptyState message="Nessun collegamento con i filtri selezionati." />
            ) : (
              <div className="grid grid--auto">
                {filteredEdges.map((e, i) => (
                  <Card key={i}>
                    <div className="flex flex--between flex--center">
                      <div>
                        <strong>{e.relation}</strong>
                        <div className="text-sm text-muted mt-2">
                          {nodes.find(n => n.id === e.source)?.label || e.source} → {nodes.find(n => n.id === e.target)?.label || e.target}
                        </div>
                        <div className="text-xs text-muted mt-2">{e.reason}</div>
                      </div>
                      <div className="flex flex--col" style={{ gap: 'var(--s-1)', alignItems: 'flex-end' }}>
                        <Tag variant={e.status === 'confirmed' ? 'success' : e.status === 'rejected' ? 'danger' : e.status === 'suggested' ? 'accent' : 'warning'}>
                          {e.status}
                        </Tag>
                        <span className="text-xs text-muted">{(e.confidence * 100).toFixed(0)}%</span>
                        <div className="flex" style={{ gap: 'var(--s-1)' }}>
                          <button className="btn btn--success btn--sm" onClick={() => updateEdgeStatus(i, 'confirmed')} aria-label="Conferma">
                            <Check size={12} />
                          </button>
                          <button className="btn btn--danger btn--sm" onClick={() => updateEdgeStatus(i, 'rejected')} aria-label="Respingi">
                            <X size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </Section>
        </>
      )}
    </>
  );
}
