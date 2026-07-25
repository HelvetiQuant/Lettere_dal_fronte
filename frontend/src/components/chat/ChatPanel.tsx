import { useState, useRef, useEffect, useCallback } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ChatMessageDTO, ChatHealthDTO } from '@/api/types';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  provider?: string;
  latencyMs?: number;
}

interface ChatPanelProps {
  context?: string;
  contextLabel?: string;
  title?: string;
  placeholder?: string;
}

export function ChatPanel({
  context,
  contextLabel,
  title = 'Chat con AI storica',
  placeholder = 'Scrivi una domanda sugli eventi bellici del Novecento…',
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<ChatHealthDTO | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.chatHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

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

    setInput('');
    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', text: msg }]);
    scrollToBottom();

    const history: ChatMessageDTO[] = messages.map(m => ({
      role: m.role,
      content: m.text,
    }));

    try {
      const res = await api.chat(msg, {
        history,
        context,
        context_label: contextLabel,
      });
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: res.risposta,
        provider: res.provider,
        latencyMs: res.latency_ms,
      }]);
    } catch (e) {
      const err = e instanceof ApiError ? e.userMessage : String(e);
      setMessages(prev => [...prev, {
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

  return (
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
        <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
        {health && (
          <span style={{
            fontSize: 11,
            color: health.available ? 'var(--color-success-600)' : 'var(--color-danger-600)',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: health.available ? 'var(--color-success-600)' : 'var(--color-danger-600)',
              display: 'inline-block',
            }} />
            {health.available ? `${health.provider} · ${health.model}` : 'offline'}
          </span>
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{
        maxHeight: 400,
        overflowY: 'auto',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minHeight: 200,
      }}>
        {messages.length === 0 && (
          <div style={{
            textAlign: 'center',
            color: 'var(--color-text-muted)',
            fontSize: 13,
            padding: '20px 0',
          }}>
            Fai una domanda sulla storia militare del Novecento.
            <br />
            L'AI usa il modello locale {health?.model || 'Qwen2.5'} tramite LM Studio.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            display: 'flex',
            justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '80%',
              padding: '10px 14px',
              borderRadius: 'var(--radius-md)',
              fontSize: 13.5,
              lineHeight: 1.55,
              background: m.role === 'user'
                ? 'var(--color-accent-600)'
                : 'var(--color-surface)',
              color: m.role === 'user' ? '#fff' : 'var(--color-text)',
              border: m.role === 'user'
                ? '1px solid var(--color-accent-600)'
                : '1px solid var(--color-neutral-300)',
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
                  {m.provider}{m.latencyMs ? ` · ${m.latencyMs}ms` : ''}
                </div>
              )}
            </div>
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
              AI sta scrivendo…
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
          placeholder={placeholder}
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
          Invia
        </button>
      </div>
    </div>
  );
}
