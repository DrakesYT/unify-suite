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
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-navy-800 bg-navy-900 p-5">
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

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>;
}

export const buttonClass =
  "rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
export const primaryButton = `${buttonClass} bg-accent-purple text-white hover:bg-accent-purple/85`;
export const ghostButton = `${buttonClass} border border-navy-800 text-slate-200 hover:bg-navy-800`;
export const dangerButton = `${buttonClass} bg-red-500/80 text-white hover:bg-red-500`;
export const inputClass =
  "w-full rounded-lg border border-navy-800 bg-navy-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-purple focus:outline-none";
