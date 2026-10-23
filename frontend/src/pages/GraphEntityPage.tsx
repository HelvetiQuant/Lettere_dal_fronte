import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { GraphEntityResponse, GraphEdgeDTO } from '@/api/types';
import { Card, Tag, LoadingState, ErrorState, Button } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { ForceGraph } from '@/components/graph/ForceGraph';
import type { GraphNodeData, GraphEdgeData } from '@/components/graph/ForceGraph';

export function GraphEntityPage() {
  const { sourceTable, sourceId } = useParams<{ sourceTable: string; sourceId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<GraphEntityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');

  useEffect(() => {
    if (!sourceTable || !sourceId) return;
    api.graphEntity(sourceTable, parseInt(sourceId), { max_nodes: 100, max_edges: 200 })
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, [sourceTable, sourceId]);

  const edges = data?.edges || [];
  const filteredEdges = filterStatus === 'all'
    ? edges
    : edges.filter((e) => e.status === filterStatus);

  // Build ForceGraph data from canonical graph response
  const graphNodes: GraphNodeData[] = useMemo(() => {
    if (!data) return [];
    return data.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      label: n.label,
    }));
  }, [data]);

  const graphEdges: GraphEdgeData[] = useMemo(() => {
    if (!data) return [];
    return data.edges
      .filter((e) => filterStatus === 'all' || e.status === filterStatus)
      .map((e) => ({
        source: e.source.id,
        target: e.target.id,
        relation: e.relation.label,
        confidence: e.confidence ?? 0,
        status: e.status,
      }));
  }, [data, filterStatus]);

  const statusColors: Record<string, 'neutral' | 'warning' | 'accent' | 'success' | 'danger'> = {
    confirmed: 'success',
    probable: 'accent',
    candidate: 'neutral',
    to_review: 'warning',
    rejected: 'danger',
    conflicting: 'warning',
    unverifiable: 'neutral',
    broken: 'danger',
  };

  return (
    <>
      <PageIntro
        title={data?.root?.label || `Grafo: ${sourceTable}#${sourceId}`}
        description={`Nodi: ${data?.nodes?.length || 0} · Relazioni: ${data?.edges?.length || 0}${data?.truncated ? ' (troncato)' : ''}`}
        aiNote="Il grafo canonico preserva la provenienza di ogni collegamento. Nessun candidato legacy viene promosso a confermato senza revisione esplicita."
        steps={['Esamina i nodi e le relazioni', 'Verifica lo stato epistemico di ogni arco', 'Usa i filtri per isolare i candidati da revisionare']}
      />

      {error && <ErrorState message={error.userMessage} />}
      {loading && <LoadingState />}

      {!loading && !error && data && (
        <>
          {graphNodes.length > 0 && (
            <Section title="Visualizzazione grafo">
              <ForceGraph nodes={graphNodes} edges={graphEdges} minHeight={500} />
            </Section>
          )}

          <Section title="Nodo radice">
            <Card>
              <div className="grid grid--2">
                <div><strong>ID:</strong> {data.root.id}</div>
                <div><strong>Tipo:</strong> {data.root.type}</div>
                <div><strong>Tabella:</strong> {data.root.source_table}</div>
                <div><strong>Record:</strong> #{data.root.source_id}</div>
              </div>
            </Card>
          </Section>

          {data.issues.length > 0 && (
            <Section title="Problemi di integrità">
              {data.issues.map((issue, i) => (
                <Card key={i}>
                  <Tag variant={issue.severity === 'error' ? 'danger' : issue.severity === 'warning' ? 'warning' : 'neutral'}>
                    {issue.severity}
                  </Tag>
                  <span className="ml-2">{issue.message}</span>
                </Card>
              ))}
            </Section>
          )}

          <div className="flex flex--wrap mb-4" style={{ gap: 'var(--s-1)' }}>
            <Button
              variant={filterStatus === 'all' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setFilterStatus('all')}
            >
              Tutti ({edges.length})
            </Button>
            {['confirmed', 'probable', 'candidate', 'to_review', 'rejected', 'conflicting'].map((s) => (
              <Button
                key={s}
                variant={filterStatus === s ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setFilterStatus(s)}
              >
                {s} ({edges.filter((e) => e.status === s).length})
              </Button>
            ))}
          </div>

          <Section title="Relazioni">
            <div className="grid grid--auto">
              {filteredEdges.map((edge: GraphEdgeDTO) => (
                <Card key={edge.id}>
                  <div className="flex flex--wrap" style={{ gap: 'var(--s-1)', alignItems: 'center' }}>
                    <Tag variant={statusColors[edge.status] || 'neutral'}>{edge.status}</Tag>
                    {edge.confidence_label && (
                      <Tag variant="neutral">confidenza: {edge.confidence_label}</Tag>
                    )}
                    <Tag variant="neutral">{edge.source_system}</Tag>
                  </div>
                  <div className="mt-2">
                    <strong>{edge.source.label}</strong>
                    <span className="text-muted mx-2">→ {edge.relation.label} →</span>
                    <strong
                      style={{ cursor: 'pointer', textDecoration: 'underline' }}
                      onClick={() => {
                        if (edge.target.source_table && edge.target.source_id) {
                          navigate(`/grafo/${edge.target.source_table}/${edge.target.source_id}`);
                        }
                      }}
                    >
                      {edge.target.label}
                    </strong>
                  </div>
                  <div className="text-sm text-muted mt-2">{edge.explanation}</div>
                  {edge.evidence.length > 0 && (
                    <div className="mt-2">
                      <span className="text-sm"><strong>Evidenze:</strong></span>
                      <ul className="text-sm" style={{ marginLeft: 'var(--s-3)' }}>
                        {edge.evidence.slice(0, 3).map((ev, i) => (
                          <li key={i}>
                            {ev.label}{ev.value ? `: ${ev.value}` : ''}
                            {ev.source_table && <span className="text-muted"> [{ev.source_table}#{ev.source_id}]</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {edge.contrary_signals.length > 0 && (
                    <div className="mt-2">
                      <span className="text-sm"><strong>Segnali contrari:</strong></span>
                      <ul className="text-sm" style={{ marginLeft: 'var(--s-3)' }}>
                        {edge.contrary_signals.slice(0, 2).map((ev, i) => (
                          <li key={i}>{ev.label}{ev.value ? `: ${ev.value}` : ''}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {edge.review.required && !edge.review.decision && (
                    <div className="mt-2">
                      <Tag variant="warning">Revisione richiesta</Tag>
                    </div>
                  )}
                  {edge.review.decision && (
                    <div className="mt-2">
                      <Tag variant={edge.review.decision === 'accepted' ? 'success' : edge.review.decision === 'rejected' ? 'danger' : 'warning'}>
                        Revisione: {edge.review.decision}
                      </Tag>
                      {edge.review.reviewed_by && <span className="text-sm text-muted ml-2">da {edge.review.reviewed_by}</span>}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </Section>

          <Section title="Tutti i nodi">
            <div className="grid grid--auto">
              {data.nodes.map((node) => (
                <Card key={node.id}>
                  <div
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/grafo/${node.source_table}/${node.source_id}`)}
                  >
                    <strong>{node.label}</strong>
                    <div className="flex flex--wrap mt-1" style={{ gap: 'var(--s-1)' }}>
                      <Tag variant="neutral">{node.type}</Tag>
                      <Tag variant="neutral">{node.source_table}#{node.source_id}</Tag>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </Section>
        </>
      )}
    </>
  );
}
