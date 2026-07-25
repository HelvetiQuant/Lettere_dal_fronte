/**
 * Live Error Logger — intercetta e registra tutti gli errori del frontend.
 *
 * Cattura:
 * - window.onerror (errori JS non catturati)
 * - unhandledrejection (promise reject non catturate)
 * - console.error (tutti i console.error)
 * - fetch 404/500 (risposte HTTP non ok)
 * - React render errors (via ErrorBoundary)
 *
 * Output: log live su console + buffer in memoria + endpoint POST /api/log/frontend
 * File di log: scaricabile dal browser, inviato al backend se disponibile.
 */

type LogLevel = 'error' | 'warn' | 'info';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  source: string;       // 'window.onerror' | 'unhandledrejection' | 'console.error' | 'fetch' | 'react' | 'api'
  message: string;
  detail?: string;      // stack trace, error details
  url?: string;         // URL della richiesta fetch o della pagina
  method?: string;      // HTTP method per errori fetch
  status?: number;      // HTTP status per errori fetch
  componentStack?: string; // React component stack per ErrorBoundary
  context?: Record<string, unknown>; // contesto aggiuntivo
  userAgent?: string;
  route?: string;       // route corrente
}

class ErrorLogger {
  private buffer: LogEntry[] = [];
  private maxBuffer = 500;
  private listeners: ((entry: LogEntry) => void)[] = [];
  private originalConsoleError: typeof console.error;
  private originalFetch: typeof fetch;
  private installed = false;

  constructor() {
    this.originalConsoleError = console.error.bind(console);
    this.originalFetch = window.fetch.bind(window);
  }

  install() {
    if (this.installed) return;
    this.installed = true;

    // 1. window.onerror — errori JS non catturati
    window.addEventListener('error', (event: ErrorEvent) => {
      this.log({
        level: 'error',
        source: 'window.onerror',
        message: event.message || 'Unknown error',
        detail: event.error?.stack || event.filename + ':' + event.lineno + ':' + event.colno,
        url: event.filename,
        context: {
          lineno: event.lineno,
          colno: event.colno,
          type: event.type,
        },
      });
    });

    // 2. unhandledrejection — promise reject non catturate
    window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      this.log({
        level: 'error',
        source: 'unhandledrejection',
        message: reason?.message || String(reason),
        detail: reason?.stack || JSON.stringify(reason, null, 2),
        context: {
          reasonType: typeof reason,
          reasonName: reason?.name,
        },
      });
    });

    // 3. console.error — intercetta tutti i console.error
    console.error = (...args: unknown[]) => {
      const message = args.map(a => {
        if (a instanceof Error) return `${a.name}: ${a.message}\n${a.stack || ''}`;
        if (typeof a === 'object') {
          try { return JSON.stringify(a, null, 2); } catch { return String(a); }
        }
        return String(a);
      }).join(' ');

      this.log({
        level: 'error',
        source: 'console.error',
        message,
      });

      // Chiama anche il console.error originale
      this.originalConsoleError(...args);
    };

    // 4. fetch — intercetta risposte HTTP non ok
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const method = init?.method || 'GET';

      try {
        const response = await this.originalFetch(input, init);

        if (!response.ok) {
          let detail = '';
          try {
            const clone = response.clone();
            const body = await clone.text();
            detail = body.substring(0, 500);
          } catch { /* ignore */ }

          this.log({
            level: response.status >= 500 ? 'error' : 'warn',
            source: 'fetch',
            message: `HTTP ${response.status} ${response.statusText}`,
            url,
            method,
            status: response.status,
            detail,
          });
        }

        return response;
      } catch (err) {
        this.log({
          level: 'error',
          source: 'fetch',
          message: `Network error: ${(err as Error).message}`,
          url,
          method,
          detail: (err as Error).stack,
        });
        throw err;
      }
    };

    this.log({
      level: 'info',
      source: 'logger',
      message: 'ErrorLogger installed — monitoring all errors',
    });
  }

  log(entry: Partial<LogEntry>) {
    const fullEntry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: entry.level || 'error',
      source: entry.source || 'unknown',
      message: entry.message || '',
      detail: entry.detail,
      url: entry.url,
      method: entry.method,
      status: entry.status,
      componentStack: entry.componentStack,
      context: entry.context,
      userAgent: navigator.userAgent,
      route: window.location.pathname + window.location.search,
    };

    this.buffer.push(fullEntry);
    if (this.buffer.length > this.maxBuffer) {
      this.buffer.shift();
    }

    // Notifica listeners (per UI live)
    this.listeners.forEach(fn => fn(fullEntry));

    // Stampa in console con formato leggibile
    const prefix = `[${fullEntry.timestamp}] [${fullEntry.level.toUpperCase()}] [${fullEntry.source}]`;
    if (fullEntry.level === 'error') {
      this.originalConsoleError(`${prefix} ${fullEntry.message}`, fullEntry.detail || '');
    } else if (fullEntry.level === 'warn') {
      console.warn(`${prefix} ${fullEntry.message}`, fullEntry.detail || '');
    }
  }

  /** Registra errore React da ErrorBoundary */
  logReactError(error: Error, errorInfo: { componentStack: string }, componentName?: string) {
    this.log({
      level: 'error',
      source: 'react',
      message: `${error.name}: ${error.message}`,
      detail: error.stack,
      componentStack: errorInfo.componentStack,
      context: {
        componentName,
        errorType: error.constructor.name,
      },
    });
  }

  /** Registra errore API da ApiError */
  logApiError(error: { status: number; detail: string; url?: string; userMessage: string }, apiMethod?: string) {
    this.log({
      level: 'error',
      source: 'api',
      message: `API ${apiMethod || 'call'} failed: ${error.userMessage || error.detail}`,
      url: error.url,
      status: error.status,
      detail: error.detail,
      context: {
        apiMethod,
        isNetwork: error.status === 0,
        isServer: error.status >= 500,
        isNotFound: error.status === 404,
      },
    });
  }

  /** Ottieni tutti i log */
  getLogs(): LogEntry[] {
    return [...this.buffer];
  }

  /** Ottieni solo errori */
  getErrors(): LogEntry[] {
    return this.buffer.filter(e => e.level === 'error');
  }

  /** Pulisci buffer */
  clear() {
    this.buffer = [];
  }

  /** Scarica log come file */
  download(filename = `frontend-errors-${Date.now()}.log`) {
    const lines = this.buffer.map(e => {
      let line = `[${e.timestamp}] [${e.level.toUpperCase()}] [${e.source}] ${e.message}`;
      if (e.url) line += `\n  URL: ${e.method || 'GET'} ${e.url}`;
      if (e.status) line += `\n  Status: ${e.status}`;
      if (e.route) line += `\n  Route: ${e.route}`;
      if (e.detail) line += `\n  Detail: ${e.detail}`;
      if (e.componentStack) line += `\n  ComponentStack: ${e.componentStack}`;
      if (e.context) line += `\n  Context: ${JSON.stringify(e.context, null, 2)}`;
      if (e.userAgent) line += `\n  UA: ${e.userAgent}`;
      line += '\n';
      return line;
    });
    const blob = new Blob(lines.join('\n'), { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  /** Invia log al backend */
  async sendToBackend(): Promise<boolean> {
    try {
      const resp = await this.originalFetch('/api/log/frontend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs: this.buffer }),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  /** Subscribe a nuovi log (per UI live) */
  subscribe(fn: (entry: LogEntry) => void): () => void {
    this.listeners.push(fn);
    return () => { this.listeners = this.listeners.filter(f => f !== fn); };
  }

  /** Statistiche */
  getStats() {
    const errors = this.buffer.filter(e => e.level === 'error');
    const warns = this.buffer.filter(e => e.level === 'warn');
    const bySource: Record<string, number> = {};
    for (const e of this.buffer) {
      bySource[e.source] = (bySource[e.source] || 0) + 1;
    }
    return {
      total: this.buffer.length,
      errors: errors.length,
      warnings: warns.length,
      bySource,
    };
  }
}

export const errorLogger = new ErrorLogger();

/** React Error Boundary che registra tutti gli errori di render */
import React from 'react';

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
