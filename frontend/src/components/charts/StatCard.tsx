import type { ReactNode } from "react";
import { CountUp } from "../CountUp";
import { CHIP_TONE, type ChipTone } from "../chipTone";
import { IconChip } from "../ui";

const surface =
  "min-w-0 rounded-2xl border border-white/[0.07] bg-navy-900/80 p-4 card-shadow flex flex-col";

/** One number in the dashboard style: icon chip and label, the figure, an optional pill note. */
export function StatCard({
  label,
  value,
  delta,
  icon,
  tone = "violet",
  accent = false,
  danger = false,
}: {
  label: string;
  value: string | number;
  delta?: string;
  icon?: ReactNode;
  tone?: ChipTone;
  accent?: boolean;
  danger?: boolean;
}) {
  const valueTone = danger ? "text-red-300" : accent ? "text-[var(--chart-accent)]" : "text-white";
  return (
    <div className={surface}>
      <span className="flex min-w-0 items-center gap-2.5">
        {icon && <IconChip icon={icon} tone={tone} size="sm" />}
        <span className="truncate text-sm font-medium text-slate-300">{label}</span>
      </span>
      <p className={`mt-3 truncate text-2xl font-bold tracking-tight tabular-nums ${valueTone}`}>
        <CountUp value={value} />
      </p>
      {delta && (
        <span
          className={`mt-2 max-w-full self-start truncate rounded-full px-2 py-0.5 text-[11px] font-semibold ${CHIP_TONE[tone]}`}
        >
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
  icon,
  tone = "violet",
}: {
  label: string;
  value: string;
  caption?: string;
  icon?: ReactNode;
  tone?: ChipTone;
}) {
  return (
    <div className={`${surface} p-5`}>
      <span className="flex min-w-0 items-center gap-2.5">
        {icon && <IconChip icon={icon} tone={tone} size="sm" />}
        <span className="truncate text-sm font-medium text-slate-300">{label}</span>
      </span>
      <p className="mt-3 text-5xl font-bold tracking-tight text-[var(--chart-accent)] tabular-nums">
        <CountUp value={value} />
      </p>
      {caption && <p className="mt-2 text-xs text-slate-500">{caption}</p>}
    </div>
  );
}
