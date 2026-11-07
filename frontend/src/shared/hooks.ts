import { useCallback, useEffect, useState } from "react";
export type PollState<T> = {
  data: T | null;
  error: string;
  loading: boolean;
  updatedAt: number | null;
  refresh: () => void;
  replace: (data: T) => void;
};
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "设备暂时无法连接，请重试。";
export function usePoll<T>(
  read: (signal?: AbortSignal) => Promise<T>,
  interval: number,
  enabled = true,
): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const replace = useCallback((next: T) => {
    setData(next);
    setUpdatedAt(Date.now());
    setError("");
  }, []);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: number | undefined;
    let controller: AbortController;
    async function load() {
      controller = new AbortController();
      setLoading(true);
      try {
        const next = await read(controller.signal);
        if (!cancelled) replace(next);
      } catch (failure) {
        if (!cancelled) setError(errorMessage(failure));
      } finally {
        if (!cancelled) {
          setLoading(false);
          if (interval > 0) timer = window.setTimeout(load, interval);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, [read, interval, enabled, revision, replace]);
  return { data, error, loading, updatedAt, refresh, replace };
}
