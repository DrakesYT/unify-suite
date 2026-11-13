import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Page } from "./types";

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

const PAGE_SIZE = 200; // the API's largest page
const MAX_PAGES = 50;

/** Like `usePoll` for a paged list, but follows `next_cursor` to the end: every record is loaded,
 *  so lists show all of them and the figures computed from them are complete. `path` carries no
 *  `limit` or `cursor`. */
export function usePollAll<T>(path: string | null) {
  const [data, setData] = useState<Page<T> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (path === null) return;
    try {
      const items: T[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < MAX_PAGES; page++) {
        const query: string = `${path.includes("?") ? "&" : "?"}limit=${PAGE_SIZE}${
          cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""
        }`;
        const res: Page<T> = await api<Page<T>>(`${path}${query}`);
        items.push(...res.items);
        cursor = res.next_cursor;
        if (!cursor) break;
      }
      setData({ items, next_cursor: cursor });
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
