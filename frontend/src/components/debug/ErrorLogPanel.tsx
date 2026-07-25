import { useState, useEffect, useRef } from 'react';
import { errorLogger, type LogEntry } from '@/utils/errorLogger';

export function ErrorLogPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<'all' | 'error' | 'warn'>('error');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    errorLogger.install();
    const unsub = errorLogger.subscribe((entry) => {
      setLogs(prev => [...prev, entry].slice(-200));
    });
    setLogs(errorLogger.getLogs());
    return unsub;
  }, []);

  const filtered = filter === 'all' ? logs : logs.filter(l => l.level === filter);
  const errorCount = logs.filter(l => l.level === 'error').length;
  const warnCount = logs.filter(l => l.level === 'warn').length;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{
          position: 'fixed',
          bottom: 12,
          right: 12,
          zIndex: 9999,
          padding: '8px 14px',
          borderRadius: 8,
          border: 'none',
          background: errorCount > 0 ? '#dc2626' : warnCount > 0 ? '#f59e0b' : '#6b7280',
          color: '#fff',
          fontSize: 12,
 fontWeight: 600,
          cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {errorCount > 0 && <span>🔴 {errorCount}</span>}
        {warnCount > 0 && <span>🟡 {warnCount}</span>}
        Log
      </button>
    );
  }

  return (
    <div style={{
      position: 'fixed',
      bottom: 0,
      right: 0,
      width: 700,
      maxWidth: '100vw',
      height: 400,
      maxHeight: '50vh',
      background: '#1a1a2e',
      color: '#e0e0e0',
      fontFamily: 'Consolas, Monaco, monospace',
      fontSize: 11,
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      borderTopLeftRadius: 12,
      border: '1px solid #333',
      boxShadow: '0 -4px 20px rgba(0,0,0,0.4)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 12px',
        borderBottom: '1px solid #333',
        background: '#16213e',
      }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <strong style={{ fontSize: 13 }}>Live Error Log</strong>
          <span style={{ color: '#dc2626' }}>🔴 {errorCount}</span>
          <span style={{ color: '#f59e0b' }}>🟡 {warnCount}</span>
          <span style={{ color: '#6b7280' }}>Total: {logs.length}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['error', 'warn', 'all'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: '2px 8px',
                fontSize: 10,
                border: '1px solid #444',
                borderRadius: 4,
                background: filter === f ? '#2563eb' : 'transparent',
                color: filter === f ? '#fff' : '#999',
                cursor: 'pointer',
              }}
            >
              {f.toUpperCase()}
            </button>
          ))}
          <button
            onClick={() => errorLogger.download()}
            style={{
              padding: '2px 8px',
              fontSize: 10,
              border: '1px solid #444',
              borderRadius: 4,
              background: 'transparent',
              color: '#999',
              cursor: 'pointer',
            }}
          >
            ⬇ Download
          </button>
          <button
            onClick={() => errorLogger.clear()}
            style={{
              padding: '2px 8px',
              fontSize: 10,
              border: '1px solid #444',
              borderRadius: 4,
              background: 'transparent',
              color: '#999',
              cursor: 'pointer',
            }}
          >
            Clear
          </button>
          <button
            onClick={() => setOpen(false)}
            style={{
              padding: '2px 8px',
              fontSize: 10,
              border: '1px solid #444',
              borderRadius: 4,
              background: 'transparent',
              color: '#999',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Log entries */}
      <div ref={scrollRef} style={{
        flex: 1,
        overflowY: 'auto',
        padding: '4px 8px',
      }}>
        {filtered.length === 0 && (
          <div style={{ color: '#666', padding: 20, textAlign: 'center' }}>
            Nessun log per il filtro "{filter}".
          </div>
        )}
        {filtered.map((entry, i) => {
          const color = entry.level === 'error' ? '#ff6b6b' :
                        entry.level === 'warn' ? '#fbbf24' : '#94a3b8';
          return (
            <div
              key={i}
              style={{
                borderBottom: '1px solid #222',
                padding: '6px 4px',
                lineHeight: 1.5,
              }}
            >
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <span style={{ color: '#6b7280', fontSize: 10 }}>
                  {entry.timestamp.substring(11, 23)}
                </span>
                <span style={{ color, fontWeight: 600, fontSize: 10 }}>
                  [{entry.source}]
                </span>
                <span style={{ color: '#e0e0e0' }}>
                  {entry.message}
                </span>
              </div>
              {entry.url && (
                <div style={{ color: '#6b7280', paddingLeft: 80, fontSize: 10 }}>
                  → {entry.method || 'GET'} {entry.url}
                  {entry.status && <span style={{ color }}>: {entry.status}</span>}
                </div>
              )}
              {entry.route && (
                <div style={{ color: '#4a5568', paddingLeft: 80, fontSize: 10 }}>
                  Route: {entry.route}
                </div>
              )}
              {entry.detail && (
                <details style={{ paddingLeft: 80, marginTop: 2 }}>
                  <summary style={{ color: '#6b7280', fontSize: 10, cursor: 'pointer' }}>
                    Detail
                  </summary>
                  <pre style={{
                    color: '#999',
                    fontSize: 10,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                    margin: '4px 0',
                    maxHeight: 150,
                    overflow: 'auto',
                  }}>
                    {entry.detail}
                  </pre>
                </details>
              )}
              {entry.componentStack && (
                <details style={{ paddingLeft: 80, marginTop: 2 }}>
                  <summary style={{ color: '#7c3aed', fontSize: 10, cursor: 'pointer' }}>
                    React Component Stack
                  </summary>
                  <pre style={{
                    color: '#a78bfa',
                    fontSize: 10,
                    whiteSpace: 'pre-wrap',
                    margin: '4px 0',
                    maxHeight: 200,
                    overflow: 'auto',
                  }}>
                    {entry.componentStack}
                  </pre>
                </details>
              )}
              {entry.context && (
                <details style={{ paddingLeft: 80, marginTop: 2 }}>
                  <summary style={{ color: '#6b7280', fontSize: 10, cursor: 'pointer' }}>
                    Context
                  </summary>
                  <pre style={{
                    color: '#999',
                    fontSize: 10,
                    whiteSpace: 'pre-wrap',
                    margin: '4px 0',
                  }}>
                    {JSON.stringify(entry.context, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
