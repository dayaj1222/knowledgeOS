import { useCallback, useEffect, useRef, useState } from "react";
import { notifyError } from "./components/notifications";

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

/**
 * App-wide error rule: failures surface through the notification system,
 * never as raw inline text. Call with a fetch error string — it toasts once
 * per distinct message and resets when the error clears.
 */
export function useToastError(message: string | null) {
  const last = useRef<string | null>(null);
  useEffect(() => {
    if (message && message !== last.current) {
      last.current = message;
      notifyError(message);
    }
    if (!message) last.current = null;
  }, [message]);
}

export function Spinner() {
  return <div className="spinner" aria-label="loading" />;
}
