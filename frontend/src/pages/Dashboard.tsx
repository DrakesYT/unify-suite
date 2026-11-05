import type { ReactNode } from "react";
import { Link } from "react-router";
import { AuraPanel } from "../components/AuraPanel";
import {
  CartIcon,
  ChartIcon,
  SparkleIcon,
  TicketIcon,
  UsersIcon,
  WalletIcon,
} from "../components/icons";
import { ErrorNote } from "../components/ui";
import { compactMoney } from "../format";
import { useAuth } from "../session";
import type { ActivityItem, Approval, Charts, Kpis, Money, Overview, Page } from "../types";
import { usePoll } from "../usePoll";
import { AgentBoard } from "./dashboard/AgentBoard";
import { ApprovalsBoard } from "./dashboard/ApprovalsBoard";
import { DealBoard } from "./dashboard/DealBoard";
import { HiringBoard } from "./dashboard/HiringBoard";
import { MoneyBoard } from "./dashboard/MoneyBoard";
import { Skeleton } from "./dashboard/parts";
import { SupportBoard } from "./dashboard/SupportBoard";

const INSIGHT_TONE: Record<Overview["insights"][number]["tone"], string> = {
  alert: "bg-red-400",
  warn: "bg-amber-400",
  good: "bg-emerald-400",
  info: "bg-accent-cyan",
};

function sumText(values: Money[]): string {
  return values.length
    ? values.map((v) => compactMoney(v.amount_minor, v.currency)).join(" + ")
    : compactMoney(0, "USD");
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** The facts that most need a look, worded by code from live data (never invented). */
function InsightsBanner({ insights }: { insights: Overview["insights"] | undefined }) {
  return (
    <div
      data-tour="insights"
      className="rounded-2xl bg-gradient-to-r from-accent-purple/60 via-fuchsia-500/30 to-accent-cyan/60 p-px"
    >
      <div className="flex flex-col gap-2 rounded-2xl bg-navy-950/90 px-4 py-3 md:flex-row md:items-center md:gap-4">
        <span
          className="flex shrink-0 items-center gap-2 text-sm font-semibold text-white"
          title="Computed by code from live records. No model guesses here."
        >
          <SparkleIcon size={17} className="text-accent-cyan" />
          Insights
        </span>
        <div className="flex flex-wrap gap-x-1 gap-y-1">
          {!insights && <Skeleton className="h-6 w-72" />}
          {insights?.map((i) => (
            <Link
              key={i.text}
              to={i.link}
              className="flex items-center gap-2 rounded-full px-2.5 py-1 text-sm text-slate-200 hover:bg-white/5 hover:text-white"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${INSIGHT_TONE[i.tone]}`} />
              {i.text}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function Kpi({
  title,
  value,
  hint,
  to,
  icon,
}: {
  title: string;
  value: string | number;
  hint: string;
  to: string;
  icon: ReactNode;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-3 rounded-2xl border border-white/[0.07] bg-navy-900/75 p-4 transition hover:border-accent-purple/40"
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent-purple/25 to-accent-cyan/15 text-accent-cyan">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[11px] tracking-wide text-slate-500 uppercase">
          {title}
        </span>
        <span className="block truncate text-lg font-semibold text-white">{value}</span>
        <span className="block truncate text-xs text-slate-500">{hint}</span>
      </span>
    </Link>
  );
}

export function Dashboard() {
  const { user } = useAuth();
  const overview = usePoll<Overview>("/dashboard/overview");
  const kpis = usePoll<Kpis>("/dashboard/kpis");
  const charts = usePoll<Charts>("/dashboard/charts");
  const feed = usePoll<ActivityItem[]>("/dashboard/activity");
  const approvals = usePoll<Page<Approval>>("/approvals?status=pending&limit=5");
  const o = overview.data;
  const k = kpis.data;
  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-white">
            {greeting()}, {user?.full_name.split(" ")[0]}
          </h1>
          <p className="mt-1 text-sm text-slate-400">{today} · all five departments at a glance</p>
        </div>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          Live data · refreshes every 5 s
        </span>
      </header>
      <ErrorNote message={overview.error ?? kpis.error} />
      <InsightsBanner insights={o?.insights} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_370px]">
        <div className="min-w-0 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-5">
            <Kpi
              title="Sales pipeline"
              value={k ? sumText(k.sales_pipeline) : "…"}
              hint="open deals"
              to="/sales"
              icon={<ChartIcon />}
            />
            <Kpi
              title="Unpaid invoices"
              value={k ? sumText(k.unpaid_invoices) : "…"}
              hint="supplier invoices not yet paid"
              to="/payments"
              icon={<WalletIcon />}
            />
            <Kpi
              title="Open vacancies"
              value={k?.open_vacancies ?? "…"}
              hint="jobs open"
              to="/hr"
              icon={<UsersIcon />}
            />
            <Kpi
              title="Open tickets"
              value={k?.open_tickets ?? "…"}
              hint="open, investigating, escalated"
              to="/support"
              icon={<TicketIcon />}
            />
            <Kpi
              title="Purchase requests"
              value={k?.pending_purchase_requests ?? "…"}
              hint="waiting for approval"
              to="/procurement"
              icon={<CartIcon />}
            />
          </div>

          {o ? (
            <>
              <div className="grid gap-5 lg:grid-cols-2">
                <HiringBoard hiring={o.hiring} />
                <DealBoard crm={o.crm} />
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                <SupportBoard support={o.support} />
                <ApprovalsBoard page={approvals.data} />
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                <MoneyBoard data={o.money} />
                <AgentBoard agents={o.agents} charts={charts.data} feed={feed.data} />
              </div>
            </>
          ) : (
            <div className="grid gap-5 lg:grid-cols-2">
              {[0, 1, 2, 3].map((n) => (
                <Skeleton key={n} className="h-80" />
              ))}
            </div>
          )}
        </div>
        <AuraPanel agents={o?.agents} />
      </div>
    </div>
  );
}
