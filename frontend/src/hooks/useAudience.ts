import { useState, useCallback } from 'react';

export type Audience = 'public' | 'researcher';

const STORAGE_KEY = 'vdf_audience';

export function useAudience(): [Audience, (a: Audience) => void] {
  const [audience, setAudience] = useState<Audience>(() => {
    if (typeof localStorage !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'public' || stored === 'researcher') return stored;
    }
    return 'public';
  });

  const change = useCallback((a: Audience) => {
    setAudience(a);
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, a);
  }, []);

  return [audience, change];
}
