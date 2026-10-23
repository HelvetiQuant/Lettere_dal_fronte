import { ApiError, TimeoutError } from './errors';

const BASE = import.meta.env.VITE_API_BASE || '';
const DEFAULT_TIMEOUT = 30_000;

function buildUrl(path: string): string {
  if (BASE && BASE.startsWith('http')) return BASE + path;
  return path;
}

function buildUrlWithParams(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const base = buildUrl(path);
  if (!params) return base;
  const url = new URL(base, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }
  return url.toString();
}

async function request<T>(
  method: string,
  path: string,
  opts: {
    params?: Record<string, string | number | boolean | undefined>;
    body?: unknown;
    timeout?: number;
    signal?: AbortSignal;
    retry?: boolean;
  } = {},
): Promise<T> {
  const { params, body, timeout = DEFAULT_TIMEOUT, signal, retry = false } = opts;
  const url = buildUrlWithParams(path, params);

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => { timedOut = true; controller.abort('timeout'); }, timeout);
  const combinedSignal = signal || controller.signal;

  try {
    const res = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: combinedSignal,
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(
        res.status,
        errBody.detail || res.statusText,
        res.headers.get('x-request-id') || undefined,
        url,
      );
    }

    const text = await res.text();
    return text ? JSON.parse(text) : ({} as T);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof DOMException && e.name === 'AbortError') {
      if (timedOut) {
        if (retry && method === 'GET') {
          timedOut = false;
          return request<T>(method, path, { ...opts, retry: false });
        }
        throw new TimeoutError(url);
      }
      throw new ApiError(0, 'Richiesta cancellata', undefined, url);
    }
    throw new ApiError(0, (e as Error).message || 'Errore di rete', undefined, url);
  } finally {
    clearTimeout(timeoutId);
  }
}

export function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>, signal?: AbortSignal, timeout?: number): Promise<T> {
  return request<T>('GET', path, { params, signal, retry: true, timeout });
}

export function post<T>(path: string, body?: unknown, signal?: AbortSignal, timeout?: number): Promise<T> {
  return request<T>('POST', path, { body, signal, timeout });
}

export function patch<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>('PATCH', path, { body, signal });
}

export function del<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>('DELETE', path, { signal });
}
