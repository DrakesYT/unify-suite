import type { ReactNode } from "react";
import { Link } from "react-router";
import { ArrowRight } from "../../components/icons";

/** A dashboard panel: title row with icon, an optional "open the page" link, then content. */
export function Panel({
  title,
  icon,
  to,
  linkText = "Open",
  aside,
  children,
  className = "",
}: {
  title: string;
  icon: ReactNode;
  to?: string;
  linkText?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex min-w-0 flex-col rounded-2xl border border-white/[0.07] bg-navy-900/75 p-5 shadow-[inset_0_1px_0_rgb(255_255_255/0.04)] ${className}`}
    >
      <header className="mb-4 flex items-center gap-2.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-purple/15 text-violet-300">
          {icon}
        </span>
        <h2 className="text-[15px] font-semibold text-white">{title}</h2>
        <div className="flex-1" />
        {aside}
        {to && (
          <Link
            to={to}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-accent-cyan"
          >
            {linkText} <ArrowRight size={13} />
          </Link>
        )}
      </header>
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "text-white",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="min-w-0 rounded-xl bg-navy-950/60 px-3.5 py-3 ring-1 ring-white/5">
      <p className="truncate text-[11px] tracking-wide text-slate-500 uppercase">{label}</p>
      <p className={`mt-1 truncate text-xl font-semibold ${tone}`}>{value}</p>
      {hint && <p className="mt-0.5 truncate text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Skeleton({ className = "h-40" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-white/[0.04] ${className}`} />;
}

export function Quiet({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>;
}
