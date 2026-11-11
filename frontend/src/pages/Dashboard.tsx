import { useId, type ReactNode } from "react";
import { Link } from "react-router";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { AuraPanel } from "../components/AuraPanel";
import { CountUp } from "../components/CountUp";
import {
  ArrowRight,
  BoltIcon,
  CartIcon,
  ChartIcon,
  CheckIcon,
  InfoIcon,
  ShieldIcon,
  TicketIcon,
  UsersIcon,
  WalletIcon,
} from "../components/icons";
import { ErrorNote } from "../components/ui";
import { compactMoney } from "../format";
import { useAuth } from "../session";
import type {
  ActivityItem,
  Approval,
  Charts,
  Kpis,
  Money,
  Overview,
  Page,
  PurchaseRequest,
  SalesSummary,
  Ticket,
} from "../types";
import { usePoll } from "../usePoll";
import { ACCENT } from "./dashboard/chartStyle";
import { AgentBoard } from "./dashboard/AgentBoard";
import { ApprovalsBoard } from "./dashboard/ApprovalsBoard";
import { DealBoard } from "./dashboard/DealBoard";
import { HiringBoard } from "./dashboard/HiringBoard";
import { MoneyBoard } from "./dashboard/MoneyBoard";
import { Skeleton } from "./dashboard/parts";
import { SupportBoard } from "./dashboard/SupportBoard";

type Insight = Overview["insights"][number];

/** Soft icon chip colours; the light theme deepens the text shade automatically. */
const TONE = {
  violet: "bg-violet-500/12 text-violet-300",
  amber: "bg-amber-500/15 text-amber-300",
  sky: "bg-sky-500/15 text-sky-300",
  rose: "bg-rose-500/15 text-rose-300",
  emerald: "bg-emerald-500/15 text-emerald-300",
  red: "bg-red-500/15 text-red-300",
} as const;
type Tone = keyof typeof TONE;

const INSIGHT_LOOK: Record<Insight["tone"], { tone: Tone; icon: ReactNode; word: string }> = {
  alert: { tone: "red", icon: <ShieldIcon size={17} />, word: "Urgent" },
  warn: { tone: "amber", icon: <BoltIcon size={17} />, word: "Check soon" },
  good: { tone: "emerald", icon: <CheckIcon size={17} />, word: "Good news" },
  info: { tone: "violet", icon: <InfoIcon size={17} />, word: "For your info" },
};

function sumText(values: Money[]): string {
  return values.length
    ? values.map((v) => compactMoney(v.amount_minor, v.currency)).join(" + ")
    : compactMoney(0, "USD");
}

/** Greeting, today's date and the live-data note. */
function Greeting({ name }: { name: string }) {
  const first = name.split(" ")[0] || name;
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  return (
    <div className="min-w-0 py-1">
      <p className="text-xs font-medium text-slate-500">{today}</p>
      <h1 className="mt-2 text-3xl leading-[1.12] font-bold tracking-tight text-white md:text-[2.6rem]">
        Hi, {first}!
        <br />
        <span className="text-slate-300">What needs you today?</span>
      </h1>
      <p className="mt-3 max-w-md text-sm text-slate-400">
        Five departments, one AI workforce. Agents do the routine work; you approve what matters.
      </p>
      <span className="mt-4 flex items-center gap-2 text-xs text-slate-500">
        {/* The one moving dot: this page really is live (it polls every 5 s). */}
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
        </span>
        Live data · refreshes every 5 s
      </span>
    </div>
  );
}

/** The facts that most need a look, worded by code from live data (never invented), as cards. */
function NeedsALook({ insights }: { insights: Insight[] | undefined }) {
  return (
    <section data-tour="insights" className="min-w-0">
      <h2
        className="mb-2.5 text-sm font-semibold text-white"
        title="Worded by code from live records. No model guesses here."
      >
        Needs a look
      </h2>
      <div className="stagger grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {!insights && [0, 1, 2].map((n) => <Skeleton key={n} className="h-28" />)}
        {insights?.length === 0 && (
          <p className="rounded-2xl border border-white/[0.07] bg-navy-900/80 p-4 text-sm text-slate-400 card-shadow">
            Nothing needs you right now.
          </p>
        )}
        {insights?.map((i) => {
          const look = INSIGHT_LOOK[i.tone];
          return (
            <Link
              key={i.text}
              to={i.link}
              className="hover-lift group flex min-w-0 flex-col gap-3 rounded-2xl border border-white/[0.07] bg-navy-900/80 p-4 card-shadow"
            >
              <span className="flex items-center justify-between">
                <span className={`grid h-9 w-9 place-items-center rounded-xl ${TONE[look.tone]}`}>
                  {look.icon}
                </span>
                <ArrowRight
                  size={15}
                  className="text-slate-500 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent-soft"
                />
              </span>
              <span className="min-w-0">
                <span className="block text-[11px] font-medium text-slate-500">{look.word}</span>
                <span className="mt-0.5 line-clamp-2 block text-sm font-medium text-slate-100">
                  {i.text}
                </span>
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

const TREND_WEEKS = 8;
const WEEK_MS = 7 * 24 * 3600 * 1000;

/** How many of these rows were created in each of the last 8 rolling weeks (oldest first). */
function weeklyCounts(rows: { created_at: string }[]): number[] {
  const now = Date.now();
  const counts = new Array<number>(TREND_WEEKS).fill(0);
  for (const row of rows) {
    const age = Math.floor((now - new Date(row.created_at).getTime()) / WEEK_MS);
    if (age >= 0 && age < TREND_WEEKS) counts[TREND_WEEKS - 1 - age] += 1;
  }
  return counts;
}

/** A small filled trend line (real weekly numbers only). */
function Spark({ series, name }: { series: number[]; name: string }) {
  const id = useId().replace(/:/g, "");
  const data = series.map((v, i) => ({ i, v }));
  return (
    <div
      className="h-8 min-w-12 flex-1"
      role="img"
      aria-label={`${name}, last ${series.length} weeks: ${series.join(", ")}`}
      title={`${name}, last ${series.length} weeks`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 3, right: 2, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.28} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={ACCENT}
            strokeWidth={2}
            fill={`url(#spark-${id})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** A KPI card: icon chip and label, the figure, this week's change (when known) and a trend line. */
function Kpi({
  title,
  value,
  hint,
  to,
  icon,
  tone,
  week,
  series,
  seriesName,
}: {
  title: string;
  value: string | number;
  hint: string;
  to: string;
  icon: ReactNode;
  tone: Tone;
  week?: string;
  series?: number[];
  seriesName?: string;
}) {
  return (
    <Link
      to={to}
      className="hover-lift group flex min-w-0 flex-col rounded-2xl border border-white/[0.07] bg-navy-900/80 p-4 card-shadow"
    >
      <span className="flex items-center gap-2.5">
        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${TONE[tone]}`}>
          {icon}
        </span>
        <span className="truncate text-sm font-medium text-slate-300">{title}</span>
      </span>
      <span className="mt-3 block truncate text-2xl font-bold tracking-tight text-white tabular-nums">
        <CountUp value={value} />
      </span>
      <span className="block truncate text-xs text-slate-500">{hint}</span>
      {(week || series) && (
        <span className="mt-auto flex items-end gap-3 pt-3">
          {week && (
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${TONE[tone]}`}
            >
              {week}
            </span>
          )}
          {series && seriesName && <Spark series={series} name={seriesName} />}
        </span>
      )}
    </Link>
  );
}

const lastOf = (series: number[] | undefined) => series?.[series.length - 1];

export function Dashboard() {
  const { user } = useAuth();
  const overview = usePoll<Overview>("/dashboard/overview");
  const kpis = usePoll<Kpis>("/dashboard/kpis");
  const charts = usePoll<Charts>("/dashboard/charts");
  const feed = usePoll<ActivityItem[]>("/dashboard/activity");
  const approvals = usePoll<Page<Approval>>("/approvals?status=pending&limit=5");
  // Trend lines reuse list endpoints; a role without access just sees the card without a line.
  const sales = usePoll<SalesSummary>("/sales/summary");
  const tickets = usePoll<Page<Ticket>>("/support/tickets?limit=200");
  const requests = usePoll<Page<PurchaseRequest>>("/procurement/requests?limit=200");
  const o = overview.data;
  const k = kpis.data;
  const s = sales.data;
  const ticketWeeks = tickets.data ? weeklyCounts(tickets.data.items) : undefined;
  const requestWeeks = requests.data ? weeklyCounts(requests.data.items) : undefined;
  const pipelineWeek = s?.weeks.length ? s.weeks[s.weeks.length - 1].new_value_minor : undefined;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,460px)_minmax(0,1fr)]">
        <Greeting name={user?.full_name ?? ""} />
        <NeedsALook insights={o?.insights} />
      </div>
      <ErrorNote message={overview.error ?? kpis.error} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_370px]">
        <div className="min-w-0 space-y-6">
          <div className="stagger grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
            <Kpi
              title="Sales pipeline"
              value={k ? sumText(k.sales_pipeline) : "…"}
              hint="open deals"
              to="/sales"
              icon={<ChartIcon size={16} />}
              tone="violet"
              week={
                s && pipelineWeek !== undefined
                  ? `+${compactMoney(pipelineWeek, s.currency)} this week`
                  : undefined
              }
              series={s?.weeks.map((w) => w.new_value_minor / 100)}
              seriesName="Pipeline value added per week"
            />
            <Kpi
              title="Unpaid invoices"
              value={k ? sumText(k.unpaid_invoices) : "…"}
              hint="supplier invoices not yet paid"
              to="/payments"
              icon={<WalletIcon size={16} />}
              tone="amber"
            />
            <Kpi
              title="Open vacancies"
              value={k?.open_vacancies ?? "…"}
              hint="jobs open"
              to="/hr"
              icon={<UsersIcon size={16} />}
              tone="sky"
            />
            <Kpi
              title="Open tickets"
              value={k?.open_tickets ?? "…"}
              hint="open, investigating, escalated"
              to="/support"
              icon={<TicketIcon size={16} />}
              tone="rose"
              week={ticketWeeks ? `+${lastOf(ticketWeeks)} this week` : undefined}
              series={ticketWeeks}
              seriesName="New tickets per week"
            />
            <Kpi
              title="Purchase requests"
              value={k?.pending_purchase_requests ?? "…"}
              hint="waiting for approval"
              to="/procurement"
              icon={<CartIcon size={16} />}
              tone="emerald"
              week={requestWeeks ? `+${lastOf(requestWeeks)} this week` : undefined}
              series={requestWeeks}
              seriesName="New purchase requests per week"
            />
          </div>

          {o ? (
            // The boards arrive top to bottom once, when the first poll lands (later polls don't replay it).
            <div className="stagger space-y-6">
              <AgentBoard agents={o.agents} charts={charts.data} feed={feed.data} />
              <div className="grid gap-6 lg:grid-cols-2">
                <DealBoard crm={o.crm} onTargetChanged={() => void overview.reload()} />
                <HiringBoard hiring={o.hiring} />
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <ApprovalsBoard page={approvals.data} />
                <SupportBoard support={o.support} />
              </div>
              <MoneyBoard data={o.money} />
            </div>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
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
