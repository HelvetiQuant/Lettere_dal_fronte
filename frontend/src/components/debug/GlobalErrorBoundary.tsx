import React from 'react';
import { errorLogger } from '@/utils/errorLogger';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class GlobalErrorBoundary extends React.Component<
  { children: React.ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    errorLogger.logReactError(error, errorInfo, this.constructor.name);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20, fontFamily: 'monospace', fontSize: 14 }}>
          <h2 style={{ color: '#dc2626' }}>Errore di rendering</h2>
          <p style={{ color: '#991b1b' }}>{this.state.error?.message}</p>
          <pre style={{ fontSize: 12, overflow: 'auto', maxHeight: 300, background: '#f3f4f6', padding: 12, borderRadius: 8 }}>
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            style={{ marginTop: 12, padding: '8px 16px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
          >
            Ricarica pagina
          </button>
          <button
            onClick={() => errorLogger.download()}
            style={{ marginTop: 12, marginLeft: 8, padding: '8px 16px', background: '#6b7280', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
          >
            Scarica log errori
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
