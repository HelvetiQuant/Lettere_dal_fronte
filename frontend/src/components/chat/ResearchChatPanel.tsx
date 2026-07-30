import { useState, useRef, useEffect, useCallback, Component } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ResearchChatResponse, ResearchDossier } from '@/api/types';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  dossier?: ResearchDossier;
  provider?: string;
  latencyMs?: number;
}

class ChatErrorBoundary extends Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err: unknown) { console.error('ChatErrorBoundary:', err); }
  render() {
    if (this.state.hasError) {
      return <div style={{ padding: 12, color: 'var(--color-danger-600)' }}>Errore rendering chat. Ricarica la pagina.</div>;
    }
    return this.props.children;
  }
}

export function ResearchChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [expandedDossier, setExpandedDossier] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, 50);
  }, []);

  const send = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    const userMsgId = `u-${Date.now()}`;
    setInput('');
    setLoading(true);
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', text: msg }]);
    scrollToBottom();

    try {
      const res: ResearchChatResponse = await api.chatResearch(msg, conversationId);
      if (!conversationId) setConversationId(res.conversation_id);
      const aiMsgId = `a-${Date.now()}`;
      setMessages(prev => [...prev, {
        id: aiMsgId,
        role: 'assistant',
        text: res.answer,
        dossier: res.dossier,
        provider: res.ai_used ? res.ai_model : 'fallback',
      }]);
    } catch (e) {
      const err = e instanceof ApiError ? e.userMessage : String(e);
      const errMsgId = `e-${Date.now()}`;
      setMessages(prev => [...prev, {
        id: errMsgId,
        role: 'assistant',
        text: `Errore: ${err}`,
      }]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const examples = [
    'cerca Francesco Siracusa nato a Messina classe 1886',
    'trovami informazioni su Antonio Smiraldi della prima guerra mondiale',
    'cerca un soldato di nome Giovanni Rossi del 5° alpini',
  ];

  return (
    <ChatErrorBoundary>
    <div className="chat-panel" style={{
      border: '1px solid var(--color-neutral-300)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
      background: 'var(--color-surface)',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--color-neutral-300)',
        background: 'var(--color-neutral-50)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>
          Ricerca persone — Chat AI
        </span>
        <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
          DB locali · 27 provider · web · AI
        </span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{
        maxHeight: 500,
        overflowY: 'auto',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        minHeight: 250,
      }}>
        {messages.length === 0 && (
          <div style={{
            textAlign: 'center',
            color: 'var(--color-text-muted)',
            fontSize: 13,
            padding: '20px 0',
          }}>
            <p style={{ fontWeight: 600, marginBottom: 8 }}>Ricerca militare storica</p>
            <p>Scrivi il nome di un soldato o persona da cercare.</p>
            <p>L'AI cercherà in tutti i database, 27 provider esterni e archivi web.</p>
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
              {examples.map((ex, i) => (
                <button
                  key={i}
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: '6px 14px', maxWidth: '90%' }}
                  onClick={() => { setInput(ex); }}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={m.id}>
            <div style={{
              display: 'flex',
              justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{
                maxWidth: '85%',
                padding: '10px 14px',
                borderRadius: 'var(--radius-md)',
                fontSize: 13.5,
                lineHeight: 1.6,
                background: m.role === 'user'
                  ? 'var(--color-accent-600)'
                  : 'var(--color-surface)',
                color: m.role === 'user' ? '#fff' : 'var(--color-text)',
                border: m.role === 'user'
                  ? '1px solid var(--color-accent-600)'
                  : '1px solid var(--color-neutral-300)',
                whiteSpace: 'pre-wrap',
              }}>
                {m.text}
                {m.role === 'assistant' && m.provider && (
                  <div style={{
                    fontSize: 10,
                    marginTop: 6,
                    color: 'var(--color-text-muted)',
                    borderTop: '1px solid var(--color-neutral-200)',
                    paddingTop: 4,
                  }}>
                    {m.provider}
                  </div>
                )}
              </div>
            </div>
            {/* Dossier toggle */}
            {m.role === 'assistant' && m.dossier && (
              <div style={{ marginTop: 4, marginLeft: 12 }}>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 11, padding: '4px 10px' }}
                  onClick={() => setExpandedDossier(expandedDossier === i ? null : i)}
                >
                  {expandedDossier === i ? '▼' : '▶'} Dossier ({m.dossier.candidati?.length || 0} candidati, {m.dossier.fonti?.length || 0} fonti)
                </button>
                {expandedDossier === i && m.dossier && (
                  <DossierDetails dossier={m.dossier} />
                )}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-md)',
              fontSize: 13.5,
              background: 'var(--color-surface)',
              border: '1px solid var(--color-neutral-300)',
              opacity: 0.7,
            }}>
              Ricerca in corso… (DB locali · 27 provider · web)
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{
        display: 'flex',
        gap: 8,
        alignItems: 'flex-end',
        padding: '10px 14px',
        borderTop: '1px solid var(--color-neutral-300)',
      }}>
        <textarea
          className="input"
          placeholder="es. cerca Francesco Siracusa nato a Messina classe 1886 prima guerra mondiale"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          style={{
            fontSize: 14,
            padding: '10px 14px',
            minHeight: 42,
            flex: 1,
            resize: 'none',
            maxHeight: 120,
          }}
          rows={1}
        />
        <button
          className="btn btn-primary"
          onClick={send}
          disabled={loading || !input.trim()}
          style={{ padding: '0 18px', fontSize: 14, minHeight: 42 }}
        >
          Cerca
        </button>
      </div>
    </div>
    </ChatErrorBoundary>
  );
}

function DossierDetails({ dossier }: { dossier: ResearchDossier }) {
  const statoColors: Record<string, string> = {
    confermata: 'var(--color-success-600)',
    probabile: 'var(--color-warning-600)',
    possibile: 'var(--color-accent-600)',
    non_identificata: 'var(--color-danger-600)',
    dati_insufficienti: 'var(--color-text-muted)',
  };
  const statoColor = statoColors[dossier.stato_identificazione] || 'var(--color-text-muted)';

  return (
    <div style={{
      marginTop: 8,
      padding: 12,
      background: 'var(--color-neutral-50)',
      borderRadius: 'var(--radius-md)',
      border: '1px solid var(--color-neutral-200)',
      fontSize: 12.5,
      lineHeight: 1.5,
    }}>
      {/* Status */}
      <div style={{ marginBottom: 10 }}>
        <strong>Stato: </strong>
        <span style={{ color: statoColor, fontWeight: 600 }}>
          {dossier.stato_identificazione}
        </span>
        {dossier.ai_used && (
          <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--color-text-muted)' }}>
            AI: {dossier.ai_model}
          </span>
        )}
      </div>

      {/* Variants */}
      {dossier.varianti && dossier.varianti.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <strong>Varianti generate:</strong>{' '}
          {dossier.varianti.slice(0, 8).map(v => v.text).join(' · ')}
        </div>
      )}

      {/* Candidates */}
      {dossier.candidati && dossier.candidati.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <strong>Candidati ({dossier.candidati.length}):</strong>
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {dossier.candidati.slice(0, 8).map((c, i) => (
              <div key={i} style={{
                padding: '6px 10px',
                background: 'var(--color-surface)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-neutral-200)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600 }}>{c.nome_originale}</span>
                  <span style={{
                    fontSize: 10,
                    color: statoColors[c.stato === 'CONFIRMED' ? 'confermata' :
                      c.stato === 'PROBABLE' ? 'probabile' :
                      c.stato === 'POSSIBLE' ? 'possibile' : 'dati_insufficienti'] || 'var(--color-text-muted)',
                  }}>
                    {c.stato}
                  </span>
                </div>
                {c.compatibilita && c.compatibilita.length > 0 && (
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
                    {c.compatibilita.join(' · ')}
                  </div>
                )}
                {c.contraddizioni && c.contraddizioni.length > 0 && (
                  <div style={{ fontSize: 11, color: 'var(--color-danger-600)', marginTop: 2 }}>
                    ⚠ {c.contraddizioni.join(' · ')}
                  </div>
                )}
                {c.fonti && c.fonti.length > 0 && (
                  <div style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 2 }}>
                    Fonti: {c.fonti.slice(0, 3).map(f => f.istituzione).join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Excluded homonyms */}
      {dossier.omonimi_esclusi && dossier.omonimi_esclusi.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <strong>Omonimi esclusi:</strong> {dossier.omonimi_esclusi.length}
        </div>
      )}

      {/* Contradictions */}
      {dossier.contraddizioni && dossier.contraddizioni.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <strong>Contraddizioni:</strong>
          <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
            {dossier.contraddizioni.slice(0, 5).map((c, i) => (
              <li key={i} style={{ fontSize: 11 }}>
                {typeof c === 'object' && c !== null
                  ? `${(c as Record<string, unknown>).candidato || ''}: ${(c as Record<string, unknown>).contraddizione || ''}`
                  : String(c)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Archival requests */}
      {dossier.richieste && dossier.richieste.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <strong>Richieste archivistiche:</strong>
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {dossier.richieste.map((r, i) => (
              <div key={i} style={{
                padding: '6px 10px',
                background: 'var(--color-surface)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-neutral-200)',
              }}>
                <div style={{ fontWeight: 600 }}>{r.ente}</div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                  {r.fondo} — {r.documento_richiesto}
                </div>
                <div style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 2 }}>
                  {r.dati_conosciuti}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Negative searches */}
      {dossier.ricerche_negative && dossier.ricerche_negative.length > 0 && (
        <div style={{ marginBottom: 6, fontSize: 11, color: 'var(--color-text-muted)' }}>
          Ricerche negative: {dossier.ricerche_negative.length} archivi senza risultato
        </div>
      )}
    </div>
  );
}
