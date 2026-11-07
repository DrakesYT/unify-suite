import { CountUp } from "../CountUp";

/** One small number with a label; `accent` colours the value cyan, `delta` is an optional note. */
export function StatCard({
  label,
  value,
  delta,
  accent = false,
  danger = false,
}: {
  label: string;
  value: string | number;
  delta?: string;
  accent?: boolean;
  danger?: boolean;
}) {
  const tone = danger ? "text-red-300" : accent ? "text-[var(--chart-accent)]" : "text-white";
  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone}`}>
        <CountUp value={value} />
      </p>
      {delta && (
        <span className="mt-1 inline-block rounded-full bg-white/[0.05] px-2 py-0.5 text-[11px] text-slate-400">
          {delta}
        </span>
      )}
    </div>
  );
}

/** The one oversized number on a page. */
export function HeroStat({
  label,
  value,
  caption,
}: {
  label: string;
  value: string;
  caption?: string;
}) {
  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900 p-5">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-5xl font-semibold tracking-tight text-[var(--chart-accent)] tabular-nums">
        <CountUp value={value} />
      </p>
      {caption && <p className="mt-2 text-xs text-slate-500">{caption}</p>}
    </div>
  );
}
