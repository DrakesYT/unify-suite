import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export const POLL_MS = 5000;

/** GET `path` now and every 5 s (the app's live-update rule). `null` = nothing to load yet. */
export function usePoll<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (path === null) return;
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load");
    }
  }, [path]);

  useEffect(() => {
    const tick = () => void reload();
    const first = setTimeout(tick, 0);
    const every = setInterval(tick, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(every);
    };
  }, [reload]);

  return { data, error, reload };
}
