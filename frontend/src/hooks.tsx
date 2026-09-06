import { useCallback, useEffect, useRef, useState } from "react";

export function useFetch<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Stable ref to the latest fn, so load() doesn't go stale.
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fnRef.current()
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]); // fetch on mount + whenever the fn identity changes

  return { data, error, loading, reload: load };
}

export function Spinner() {
  return <div className="spinner" aria-label="loading" />;
}
