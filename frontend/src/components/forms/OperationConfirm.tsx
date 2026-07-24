import { useState } from 'react';
import { Button } from '@/components/feedback/States';

export function OperationConfirm({ name, description, onConfirm, onStop, running }: {
  name: string;
  description: string;
  onConfirm: () => Promise<unknown>;
  onStop?: () => Promise<unknown>;
  running?: boolean;
}) {
  const [stage, setStage] = useState<'idle' | 'preparing' | 'confirming' | 'running' | 'done' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handlePrepare = () => {
    setStage('preparing');
    setMessage('');
  };

  const handleConfirm = async () => {
    setStage('confirming');
    try {
      await onConfirm();
      setStage('done');
      setMessage('Operazione completata.');
      setTimeout(() => setStage('idle'), 4000);
    } catch (e) {
      setStage('error');
      setMessage((e as Error).message || 'Errore durante l\'operazione.');
    }
  };

  const handleStop = async () => {
    if (!onStop) return;
    try { await onStop(); setMessage('Arresto richiesto.'); }
    catch (e) { setMessage((e as Error).message); }
  };

  if (stage === 'idle' && !running) {
    return (
      <div className="card">
        <div style={{ fontWeight: 600 }}>{name}</div>
        <p className="text-sm text-muted mt-2">{description}</p>
        <Button variant="secondary" size="sm" onClick={handlePrepare} style={{ marginTop: 'var(--s-3)' }}>Prepara</Button>
      </div>
    );
  }

  return (
    <div className="card">
      <div style={{ fontWeight: 600 }}>{name}</div>
      <p className="text-sm text-muted mt-2">{description}</p>
      {stage === 'preparing' && (
        <div style={{ marginTop: 'var(--s-3)' }}>
          <p className="text-sm">Confermare l'avvio dell'operazione?</p>
          <div className="flex mt-2">
            <Button variant="primary" size="sm" onClick={handleConfirm}>Conferma e avvia</Button>
            <Button variant="ghost" size="sm" onClick={() => setStage('idle')}>Annulla</Button>
          </div>
        </div>
      )}
      {(stage === 'confirming' || stage === 'running' || running) && (
        <div className="state-partial mt-2">Operazione in corso…</div>
      )}
      {stage === 'done' && <div className="state-partial mt-2" style={{ background: 'var(--c-success-100)', color: 'var(--c-success)' }}>{message}</div>}
      {stage === 'error' && <div className="state-error mt-2">{message}</div>}
      {(onStop && (running || stage === 'confirming')) && (
        <Button variant="danger" size="sm" onClick={handleStop} style={{ marginTop: 'var(--s-2)' }}>Arresta</Button>
      )}
    </div>
  );
}
