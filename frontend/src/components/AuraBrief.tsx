import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import type { Brief } from "../types";
import { Orb } from "./AuraOrb";
import { RefreshIcon } from "./icons";

const CACHE_MS = 10 * 60_000; // a brief is reused for 10 minutes per user (fewer model calls)
const TONE: Record<Brief["items"][number]["tone"], string> = {
  alert: "bg-red-400",
  warn: "bg-amber-400",
  good: "bg-emerald-400",
  info: "bg-accent-soft",
};

function readCache(userId: string): Brief | null {
  try {
    const raw = sessionStorage.getItem(`unify.brief.${userId}`);
    if (!raw) return null;
    const { at, brief } = JSON.parse(raw) as { at: number; brief: Brief };
    return Date.now() - at < CACHE_MS ? brief : null;
  } catch {
    return null;
  }
}

function writeCache(userId: string, brief: Brief): void {
  try {
    sessionStorage.setItem(`unify.brief.${userId}`, JSON.stringify({ at: Date.now(), brief }));
  } catch {
    // Blocked storage: the brief is simply fetched again next time.
  }
}

function title(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Morning brief";
  if (hour < 18) return "Afternoon brief";
  return "Evening brief";
}

/** The facts are collected by code and shown at once; the model's wording replaces the code's
 * when it arrives, after code has checked every number in it. */
export function AuraBrief({ userId }: { userId: string }) {
  const [cached] = useState(() => readCache(userId));
  const [brief, setBrief] = useState<Brief | null>(cached);
  const [writing, setWriting] = useState(cached === null);
  const [error, setError] = useState<string | null>(null);

  const fetchModel = useCallback(
    (live: () => boolean) =>
      api<Brief>("/ai/brief")
        .then((b) => {
          if (!live()) return;
          setBrief(b);
          writeCache(userId, b);
        })
        .catch((e) => live() && setError(e instanceof Error ? e.message : "Brief unavailable"))
        .finally(() => live() && setWriting(false)),
    [userId],
  );

  useEffect(() => {
    if (cached) return;
    let live = true;
    api<Brief>("/ai/brief?writer=code")
      .then((b) => live && setBrief((prev) => prev ?? b))
      .catch(() => undefined);
    void fetchModel(() => live);
    return () => {
      live = false;
    };
  }, [cached, fetchModel]);

  const refresh = () => {
    setWriting(true);
    setError(null);
    void fetchModel(() => true);
  };

  return (
    <div className="flex gap-2.5">
      <Orb size={26} />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm bg-navy-800/80 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-[11px] font-semibold text-accent-soft">{title()}</p>
          <button
            onClick={refresh}
            disabled={writing}
            aria-label="Write the brief again"
            title="Write the brief again"
            className="text-slate-500 hover:text-white disabled:opacity-40"
          >
            <RefreshIcon size={14} className={writing ? "animate-spin" : ""} />
          </button>
        </div>
        {!brief && !error && (
          <div className="mt-2 space-y-1.5">
            <div className="h-3 w-4/5 animate-pulse rounded bg-white/10" />
            <div className="h-3 w-full animate-pulse rounded bg-white/5" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-white/5" />
          </div>
        )}
        {brief && (
          <>
            <p className="mt-1 font-semibold text-white">{brief.headline}</p>
            <p className="mt-1 text-slate-300">{brief.summary}</p>
            <ul className="mt-2 space-y-1">
              {brief.items.map((item) => (
                <li key={item.id}>
                  <Link
                    to={item.link}
                    className="flex items-start gap-2 text-xs text-slate-300 hover:text-white"
                  >
                    <span
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${TONE[item.tone]}`}
                    />
                    {item.text}
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
        {error && <p className="mt-1 text-xs text-red-300">{error}</p>}
        <p className="mt-2 text-[10px] leading-snug text-slate-500">
          {writing
            ? "Aura is writing this with the Vultr model…"
            : brief?.written_by === "model"
              ? `Worded by ${brief.model} on Vultr from live facts; every number checked by code.`
              : "Written by code from live data (the AI wording was not available)."}
        </p>
      </div>
    </div>
  );
}
