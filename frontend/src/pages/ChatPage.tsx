import { useState, useEffect } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ChatHealthDTO } from '@/api/types';
import { LoadingState, ErrorState } from '@/components/feedback/States';
import { PageIntro, Section } from '@/components/layout/PageIntro';
import { ChatPanel } from '@/components/chat/ChatPanel';

export function ChatPage() {
  const [health, setHealth] = useState<ChatHealthDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

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
        description="Conversa con l'AI specializzata in eventi bellici del Novecento. Il modello gira localmente tramite LM Studio."
        aiNote="L\u2019AI usa il runtime locale (LM Studio) con il modello Qwen2.5. Nessun dato viene inviato a server esterni quando local_only è attivo."
        steps={['Verifica che LM Studio sia in esecuzione', 'Fai domande su eventi, persone, luoghi del Novecento', 'L\u2019AI risponde con accuratezza storica']}
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
              <strong>LM Studio non rilevato.</strong> Avvia LM Studio su http://127.0.0.1:1234 e carica un modello.
              {!health.detail.includes('Connection') && ` Dettaglio: ${health.detail}`}
            </div>
          )}
        </Section>
      )}

      {!loading && !error && (
        <Section title="Conversazione">
          <ChatPanel
            title="Chat storica AI — generale"
            placeholder="Fai una domanda sulla Prima o Seconda Guerra Mondiale…"
          />
        </Section>
      )}
    </>
  );
}
