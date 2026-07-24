import { useState, useEffect, useCallback, useRef } from 'react';
import { ApiError } from '@/api/errors';

type Status = 'idle' | 'loading' | 'success' | 'error';

interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  status: Status;
}

export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> & { refetch: () => void; reset: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, status: 'idle' });
  const mountedRef = useRef(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const execute = useCallback(() => {
    setState((prev) => ({ ...prev, status: 'loading', error: null }));
    fnRef.current()
      .then((data) => {
        if (mountedRef.current) setState({ data, error: null, status: 'success' });
      })
      .catch((e) => {
        if (mountedRef.current) {
          const error = e instanceof ApiError ? e : new ApiError(0, String(e));
          setState({ data: null, error, status: 'error' });
        }
      });
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    execute();
    return () => { mountedRef.current = false; };
  }, [execute]);

  const reset = useCallback(() => {
    setState({ data: null, error: null, status: 'idle' });
  }, []);

  return { ...state, refetch: execute, reset };
}
