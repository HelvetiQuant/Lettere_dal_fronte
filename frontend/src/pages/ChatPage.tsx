import { useState, useEffect } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ChatHealthDTO } from '@/api/types';
import { LoadingState, ErrorState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ResearchChatPanel } from '@/components/chat/ResearchChatPanel';

type Tab = 'general' | 'research';

export function ChatPage() {
  const [health, setHealth] = useState<ChatHealthDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState<Tab>('research');

  useEffect(() => {
    api.chatHealth()
      .then(h => setHealth(h))
      .catch(e => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <PageIntro
        title="Chat storica AI"
        description="Conversa con l'AI specializzata in eventi bellici del Novecento e ricerca militari. Il modello usa LM Studio locale con fallback automatico ai provider cloud."
        aiNote="L'AI usa il runtime locale (LM Studio / Qwen) con fallback automatico a OpenAI, Anthropic, Mistral, Perplexity, Gemini quando LM Studio non è attivo."
        steps={['Seleziona la modalità: ricerca persone o chat generale', 'Per la ricerca persone: scrivi nome, cognome, anno e luogo di nascita', 'L\u2019AI cerca in DB locali, 27 provider esterni e archivi web', 'Ricevi un dossier strutturato con candidati, fonti e richieste archivistiche']}
      />

      {error && <ErrorState message={error.userMessage} />}
      {loading && <LoadingState />}

      {!loading && !error && health && (
        <Section title="Stato runtime">
          <div className="grid grid--2">
            <div>
              <strong>Provider:</strong> {health.provider}
            </div>
            <div>
              <strong>Modello:</strong> {health.model || 'non rilevato'}
            </div>
            <div>
              <strong>Locale:</strong> {health.local ? 'Sì' : 'No'}
            </div>
            <div>
              <strong>Stato:</strong>{' '}
              <span style={{
                color: health.available ? 'var(--color-success-600)' : 'var(--color-danger-600)',
                fontWeight: 600,
              }}>
                {health.available ? 'Disponibile' : 'Non disponibile'}
              </span>
            </div>
          </div>
          {!health.available && (
            <div className="mt-4" style={{
              padding: 12,
              background: 'var(--color-warning-50)',
              borderRadius: 'var(--radius-md)',
              fontSize: 13,
            }}>
              <strong>LM Studio non rilevato.</strong> Fallback automatico ai provider cloud attivo.
              {!health.detail.includes('Connection') && ` Dettaglio: ${health.detail}`}
            </div>
          )}
        </Section>
      )}

      {/* Tab selector */}
      {!loading && !error && (
        <div style={{ display: 'flex', gap: 0, marginBottom: 0 }}>
          <button
            className={`btn ${tab === 'research' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: 'var(--radius-md) var(--radius-md) 0 0', fontSize: 14, padding: '8px 20px' }}
            onClick={() => setTab('research')}
          >
            Ricerca persone
          </button>
          <button
            className={`btn ${tab === 'general' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: 'var(--radius-md) var(--radius-md) 0 0', fontSize: 14, padding: '8px 20px' }}
            onClick={() => setTab('general')}
          >
            Chat generale
          </button>
        </div>
      )}

      {/* Tab content */}
      {!loading && !error && tab === 'research' && (
        <Section>
          <ResearchChatPanel />
        </Section>
      )}

      {!loading && !error && tab === 'general' && (
        <Section title="Conversazione generale">
          <ChatPanel
            title="Chat storica AI — generale"
            placeholder="Fai una domanda sulla Prima o Seconda Guerra Mondiale…"
          />
        </Section>
      )}
    </>
  );
}
