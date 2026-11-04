import { Link } from "react-router";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AuraPanel } from "../components/AuraPanel";
import { Card, ErrorNote, PageHeader } from "../components/ui";
import { label, money, when } from "../format";
import type { ActivityItem, Charts, Kpis, Money } from "../types";
import { usePoll } from "../usePoll";

const PALETTE = ["#8b5cf6", "#22d3ee", "#f59e0b", "#34d399", "#f472b6", "#94a3b8", "#60a5fa"];
const AXIS = { stroke: "#475569", fontSize: 12 };
const TOOLTIP = {
  contentStyle: { background: "#0c1229", border: "1px solid #1e293b", borderRadius: 8 },
};

function moneyList(values: Money[]): string {
  return values.length
    ? values.map((v) => money(v.amount_minor, v.currency)).join(" + ")
    : money(0, "USD");
}

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
      className="rounded-xl border border-navy-800 bg-navy-900 p-4 transition hover:border-accent-purple/50"
    >
      <p className="text-xs tracking-wide text-slate-400 uppercase">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </Link>
  );
}

function Donut({ data }: { data: { label: string; value: number }[] }) {
  if (!data.length) return <p className="py-10 text-center text-sm text-slate-500">No data yet</p>;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          innerRadius={48}
          outerRadius={75}
          paddingAngle={2}
        >
          {data.map((d, i) => (
            <Cell key={d.label} fill={PALETTE[i % PALETTE.length]} stroke="none" />
          ))}
        </Pie>
        <Tooltip {...TOOLTIP} formatter={(v: number, n: string) => [v, label(n)]} />
        <Legend
          formatter={(v: string) => <span className="text-xs text-slate-300">{label(v)}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function describe(item: ActivityItem): string {
  const [entity, verb] = item.action.split(".");
  return `${label(verb ?? item.action)} ${label(entity)}`;
}

export function Dashboard() {
  const kpis = usePoll<Kpis>("/dashboard/kpis");
  const charts = usePoll<Charts>("/dashboard/charts");
  const feed = usePoll<ActivityItem[]>("/dashboard/activity");
  const k = kpis.data;
  const c = charts.data;

  return (
    <>
      <PageHeader
        title="Executive dashboard"
        subtitle="Live across all five departments. Refreshes every 5 s."
      />
      <ErrorNote message={kpis.error} />
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
            <Kpi
              title="Sales pipeline"
              value={k ? moneyList(k.sales_pipeline) : "…"}
              hint="open leads"
              to="/sales"
            />
            <Kpi
              title="Unpaid invoices"
              value={k ? moneyList(k.unpaid_invoices) : "…"}
              hint="not yet paid"
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
          {k && k.pending_approvals > 0 && (
            <Link
              to="/approvals"
              className="block rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 hover:border-amber-400/60"
            >
              {k.pending_approvals} {k.pending_approvals === 1 ? "decision is" : "decisions are"}{" "}
              waiting in the Approval Center →
            </Link>
          )}
          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Leads by rating">{c && <Donut data={c.leads_by_rating} />}</Card>
            <Card title="Tickets by category">{c && <Donut data={c.tickets_by_category} />}</Card>
            <Card title="Invoices by PO match">{c && <Donut data={c.invoices_by_match} />}</Card>
          </div>
          <Card title="Agent calls, last 7 days">
            {c && (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={c.agent_calls_by_day.map((d) => ({ ...d, day: d.day.slice(5) }))}>
                  <CartesianGrid stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="day" {...AXIS} />
                  <YAxis allowDecimals={false} {...AXIS} />
                  <Tooltip {...TOOLTIP} cursor={{ fill: "#141c3a" }} />
                  <Legend
                    formatter={(v: string) => <span className="text-xs text-slate-300">{v}</span>}
                  />
                  <Bar dataKey="succeeded" stackId="a" fill="#22d3ee" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="failed" stackId="a" fill="#f87171" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
          <Card title="Recent activity">
            <ul className="divide-y divide-navy-800 text-sm">
              {(feed.data ?? []).map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-baseline justify-between gap-2 py-2"
                >
                  <span className="text-slate-200">
                    <span className="text-slate-400">{item.actor_name ?? "System"}</span> ·{" "}
                    {describe(item)}
                  </span>
                  <span className="text-xs text-slate-500">{when(item.at)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <AuraPanel />
      </div>
    </>
  );
}
