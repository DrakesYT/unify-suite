import { Link } from "react-router";
import { AuraPanel } from "../components/AuraPanel";
import { ErrorNote } from "../components/ui";
import { compactMoney } from "../format";
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
  info: "bg-slate-400",
};

function sumText(values: Money[]): string {
  return values.length
    ? values.map((v) => compactMoney(v.amount_minor, v.currency)).join(" + ")
    : compactMoney(0, "USD");
}

/** The facts that most need a look, worded by code from live data (never invented). */
function InsightsBanner({ insights }: { insights: Overview["insights"] | undefined }) {
  return (
    <div
      data-tour="insights"
      className="flex flex-col gap-2 rounded-2xl border border-white/[0.07] bg-navy-900/75 px-4 py-3 md:flex-row md:items-center md:gap-4"
    >
      <span
        className="shrink-0 text-sm font-semibold text-white"
        title="Worded by code from live records. No model guesses here."
      >
        Needs a look
      </span>
      <div className="flex flex-wrap gap-x-1 gap-y-1">
        {!insights && <Skeleton className="h-6 w-72" />}
        {insights?.map((i) => (
          <Link
            key={i.text}
            to={i.link}
            className="flex items-center gap-2 rounded-full px-2.5 py-1 text-sm text-slate-200 transition-colors hover:bg-white/5 hover:text-white"
          >
            <span className={`h-1.5 w-1.5 rounded-full ${INSIGHT_TONE[i.tone]}`} />
            {i.text}
          </Link>
        ))}
      </div>
    </div>
  );
}

/** A plain number: label, figure, what it counts. */
function Kpi({
  title,
  value,
  hint,
  to,
}: {
  title: string;
  value: string | number;
  hint: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="group min-w-0 rounded-2xl border border-white/[0.07] bg-navy-900/75 px-4 py-3.5 transition-colors hover:border-white/15"
    >
      <span className="block truncate text-xs text-slate-400">{title}</span>
      <span className="mt-1 block truncate text-2xl font-semibold text-white tabular-nums">
        {value}
      </span>
      <span className="block truncate text-xs text-slate-500">{hint}</span>
    </Link>
  );
}

export function Dashboard() {
  const overview = usePoll<Overview>("/dashboard/overview");
  const kpis = usePoll<Kpis>("/dashboard/kpis");
  const charts = usePoll<Charts>("/dashboard/charts");
  const feed = usePoll<ActivityItem[]>("/dashboard/activity");
  const approvals = usePoll<Page<Approval>>("/approvals?status=pending&limit=5");
  const o = overview.data;
  const k = kpis.data;
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-white">
            Overview <span className="font-normal text-slate-500">· {today}</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">All five departments at a glance</p>
        </div>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          {/* The one moving dot: this page really is live (it polls every 5 s). */}
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          Live data · refreshes every 5 s
        </span>
      </header>
      <ErrorNote message={overview.error ?? kpis.error} />
      <InsightsBanner insights={o?.insights} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_370px]">
        <div className="min-w-0 space-y-5">
          <div className="stagger grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-5">
            <Kpi
              title="Sales pipeline"
              value={k ? sumText(k.sales_pipeline) : "…"}
              hint="open deals"
              to="/sales"
            />
            <Kpi
              title="Unpaid invoices"
              value={k ? sumText(k.unpaid_invoices) : "…"}
              hint="supplier invoices not yet paid"
              to="/payments"
            />
            <Kpi
              title="Open vacancies"
              value={k?.open_vacancies ?? "…"}
              hint="jobs open"
              to="/hr"
            />
            <Kpi
              title="Open tickets"
              value={k?.open_tickets ?? "…"}
              hint="open, investigating, escalated"
              to="/support"
            />
            <Kpi
              title="Purchase requests"
              value={k?.pending_purchase_requests ?? "…"}
              hint="waiting for approval"
              to="/procurement"
            />
          </div>

          {o ? (
            // The boards arrive top to bottom once, when the first poll lands (later polls don't replay it).
            <div className="stagger space-y-5">
              <AgentBoard agents={o.agents} charts={charts.data} feed={feed.data} />
              <div className="grid gap-5 lg:grid-cols-2">
                <DealBoard crm={o.crm} onTargetChanged={() => void overview.reload()} />
                <HiringBoard hiring={o.hiring} />
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                <ApprovalsBoard page={approvals.data} />
                <SupportBoard support={o.support} />
              </div>
              <MoneyBoard data={o.money} />
            </div>
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
