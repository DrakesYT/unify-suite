import type { ReactNode } from "react";
import { label } from "../format";

const TONES: Record<string, string> = {
  completed: "bg-emerald-500/15 text-emerald-300",
  succeeded: "bg-emerald-500/15 text-emerald-300",
  approved: "bg-emerald-500/15 text-emerald-300",
  matched: "bg-emerald-500/15 text-emerald-300",
  waiting_approval: "bg-amber-500/15 text-amber-300",
  pending: "bg-slate-500/15 text-slate-300",
  running: "bg-accent-cyan/15 text-accent-cyan",
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
  open: "bg-accent-cyan/15 text-accent-cyan",
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
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${tone}`}>
      {label(value)}
    </span>
  );
}

export function Card({
  title,
  actions,
  children,
  tour,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  tour?: string; // anchor for the guided tour
}) {
  return (
    <section data-tour={tour} className="rounded-xl border border-navy-800 bg-navy-900 p-5">
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 className="text-sm font-semibold tracking-wide text-slate-300 uppercase">
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
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
      <p className="text-xs font-semibold text-red-200 uppercase">
        Possible prompt injection — ignored
      </p>
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

export const buttonClass =
  "rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
export const primaryButton = `${buttonClass} bg-accent-purple text-white hover:bg-accent-purple/85`;
export const ghostButton = `${buttonClass} border border-navy-800 text-slate-200 hover:bg-navy-800`;
export const dangerButton = `${buttonClass} bg-red-500/80 text-white hover:bg-red-500`;
export const inputClass =
  "w-full rounded-lg border border-navy-800 bg-navy-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-purple focus:outline-none";
