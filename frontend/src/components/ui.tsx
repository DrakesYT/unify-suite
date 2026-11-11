import { useState, type ReactNode } from "react";
import { label } from "../format";
import { CHIP_TONE, type ChipTone } from "./chipTone";

const TONES: Record<string, string> = {
  completed: "bg-emerald-500/15 text-emerald-300",
  succeeded: "bg-emerald-500/15 text-emerald-300",
  approved: "bg-emerald-500/15 text-emerald-300",
  matched: "bg-emerald-500/15 text-emerald-300",
  waiting_approval: "bg-amber-500/15 text-amber-300",
  pending: "bg-slate-500/15 text-slate-300",
  running: "bg-accent-soft/15 text-accent-soft",
  mismatch: "bg-amber-500/15 text-amber-300",
  no_po: "bg-amber-500/15 text-amber-300",
  skipped: "bg-slate-500/10 text-slate-500",
  rejected: "bg-red-500/15 text-red-300",
  failed: "bg-red-500/15 text-red-300",
  hot: "bg-rose-500/20 text-rose-300",
  warm: "bg-amber-500/15 text-amber-300",
  cold: "bg-sky-500/15 text-sky-300",
  won: "bg-emerald-500/15 text-emerald-300",
  lost: "bg-slate-500/15 text-slate-400",
  critical: "bg-red-500/20 text-red-300",
  high: "bg-amber-500/15 text-amber-300",
  open: "bg-accent-soft/15 text-accent-soft",
  investigating: "bg-accent-purple/20 text-violet-200",
  escalated: "bg-amber-500/15 text-amber-300",
  resolved: "bg-emerald-500/15 text-emerald-300",
  ordered: "bg-emerald-500/15 text-emerald-300",
  pending_approval: "bg-amber-500/15 text-amber-300",
  draft: "bg-slate-500/15 text-slate-300",
  on_track: "bg-emerald-500/15 text-emerald-300",
  late: "bg-red-500/15 text-red-300",
  delivered: "bg-sky-500/15 text-sky-300",
  overdue: "bg-red-500/15 text-red-300",
  on_hold: "bg-amber-500/15 text-amber-300",
  not_due: "bg-slate-500/15 text-slate-300",
  sent: "bg-emerald-500/15 text-emerald-300",
  over_budget: "bg-amber-500/15 text-amber-300",
  positive: "bg-emerald-500/15 text-emerald-300",
  neutral: "bg-slate-500/15 text-slate-300",
  negative: "bg-red-500/15 text-red-300",
  mixed: "bg-amber-500/15 text-amber-300",
};

export function Badge({ value }: { value: string }) {
  const tone = TONES[value] ?? "bg-slate-500/15 text-slate-300";
  // A status that changes while on screen (a poll moved it on) pops once; a fresh page does not.
  const [first] = useState(value);
  const changed = value !== first;
  return (
    <span
      key={value}
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${tone} ${changed ? "anim-changed" : ""}`}
    >
      {label(value)}
    </span>
  );
}

/** A rounded square holding an icon, tinted by tone. */
export function IconChip({
  icon,
  tone = "violet",
  size = "md",
}: {
  icon: ReactNode;
  tone?: ChipTone;
  size?: "sm" | "md";
}) {
  const box = size === "sm" ? "h-8 w-8" : "h-9 w-9";
  return (
    <span className={`grid ${box} shrink-0 place-items-center rounded-xl ${CHIP_TONE[tone]}`}>
      {icon}
    </span>
  );
}

/** The green dot that says a page polls for fresh data. */
export function LiveNote() {
  return (
    <span className="flex items-center gap-2 text-xs text-slate-500">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
      </span>
      Live data · refreshes every 5 s
    </span>
  );
}

export function Card({
  title,
  icon,
  actions,
  children,
  tour,
}: {
  title?: string;
  /** Shown in a tinted chip before the title, like the dashboard panels. */
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  tour?: string; // anchor for the guided tour
}) {
  return (
    <section
      data-tour={tour}
      className="hover-tint min-w-0 rounded-2xl border border-white/[0.07] bg-navy-900/80 p-5 card-shadow"
    >
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <span className="flex min-w-0 items-center gap-2.5">
              {icon && <IconChip icon={icon} size="sm" />}
              <h2 className="text-[15px] font-semibold text-white">{title}</h2>
            </span>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

/** Page title in the dashboard style: icon tile, small kicker line, large bold title, live note. */
export function PageHeader({
  title,
  subtitle,
  eyebrow,
  icon,
  live = false,
  actions,
}: {
  title: string;
  subtitle?: string;
  /** Small line above the title: the department or the agent that works here. */
  eyebrow?: string;
  icon?: ReactNode;
  /** The page polls every 5 s; say so. */
  live?: boolean;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="flex min-w-0 items-start gap-4">
        {icon && (
          <span className="mt-1 hidden h-12 w-12 shrink-0 place-items-center rounded-2xl bg-navy-900 text-accent-soft ring-1 ring-white/[0.07] card-shadow sm:grid">
            {icon}
          </span>
        )}
        <div className="min-w-0">
          {eyebrow && <p className="text-xs font-medium text-slate-500">{eyebrow}</p>}
          <h1 className="mt-0.5 text-2xl leading-tight font-bold tracking-tight text-white md:text-[2rem]">
            {title}
          </h1>
          {subtitle && <p className="mt-1.5 max-w-3xl text-sm text-slate-400">{subtitle}</p>}
        </div>
      </div>
      {(live || actions) && (
        <div className="flex items-center gap-3">
          {live && <LiveNote />}
          {actions}
        </div>
      )}
    </header>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300">{message}</p>;
}

/** Lines of an uploaded document that tried to give the AI orders (found by code, never obeyed). */
export function InjectionWarning({ lines }: { lines?: string[] }) {
  if (!lines || lines.length === 0) return null;
  return (
    <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 p-3">
      <p className="text-xs font-semibold text-red-200">Possible prompt injection — ignored</p>
      <p className="mt-1 text-sm text-red-100">
        This document contains text addressed to the AI. The agent did not follow it; check the
        document before approving.
      </p>
      <ul className="mt-2 space-y-1 text-sm text-red-50">
        {lines.map((line) => (
          <li key={line} className="rounded bg-navy-950/70 px-2 py-1 font-mono text-xs">
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Empty({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-4 py-8 text-center">
      <span className="mb-1 grid h-10 w-10 place-items-center rounded-full bg-accent-purple/10 text-violet-300">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 7h16M4 12h10M4 17h7" />
        </svg>
      </span>
      <p className="text-sm text-slate-300">{children}</p>
      {hint && <p className="max-w-sm text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

/** Placeholder rows while the first poll is on its way. */
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2.5 py-2" aria-label="Loading" role="status">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex animate-pulse items-center gap-3">
          <div className="h-8 w-8 shrink-0 rounded-lg bg-white/[0.05]" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 rounded bg-white/[0.07]" style={{ width: `${70 - i * 12}%` }} />
            <div className="h-2.5 w-1/3 rounded bg-white/[0.04]" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Press feedback: a slight squeeze that lands faster than it lets go (tone stays the main cue).
export const buttonClass =
  "rounded-lg px-4 py-2 text-sm font-medium transition duration-200 active:scale-[0.97] active:duration-75 motion-reduce:active:scale-100 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100";
export const primaryButton = `${buttonClass} bg-accent-purple text-on-accent hover:bg-accent-purple/85`;
export const ghostButton = `${buttonClass} border border-navy-800 text-slate-200 hover:bg-navy-800`;
export const dangerButton = `${buttonClass} bg-red-500/80 text-on-accent hover:bg-red-500`;
export const inputClass =
  "w-full rounded-lg border border-navy-800 bg-navy-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-purple focus:outline-none";
