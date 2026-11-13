import type { ReactNode } from "react";
import { Spark } from "./charts/Spark";
import { CheckIcon, ChartIcon, UsersIcon, WalletIcon } from "./icons";
import { compactMoney } from "../format";
import type { LeadStatus, SalesSummary } from "../types";
import { ACCENT } from "../pages/dashboard/chartStyle";
import { TargetBar } from "./SalesTarget";
import { CHIP_TONE, type ChipTone } from "./chipTone";
import { Card, IconChip } from "./ui";

type Week = SalesSummary["weeks"][number];

function Kpi({
  title,
  icon,
  tone,
  value,
  series,
  seriesName = title,
  delta,
  note,
  fmt = String,
}: {
  title: string;
  icon: ReactNode;
  tone: ChipTone;
  value: string;
  series: number[];
  /** What the trend line counts, when that is not the card's own number. */
  seriesName?: string;
  delta: number; // this week minus last week, in the series' own unit
  /** Replaces the "vs last week" line when the trend measures something else than `value`. */
  note?: string;
  fmt?: (n: number) => string;
}) {
  const up = delta > 0;
  return (
    <div className="flex min-w-0 flex-col rounded-2xl border border-white/[0.07] bg-navy-900/80 p-4 card-shadow">
      <span className="flex min-w-0 items-center gap-2.5">
        <IconChip icon={icon} tone={tone} size="sm" />
        <span className="truncate text-sm font-medium text-slate-300">{title}</span>
      </span>
      <p className="mt-3 truncate text-2xl font-bold tracking-tight text-white tabular-nums">
        {value}
      </p>
      <span className="mt-auto flex items-end gap-3 pt-3">
        <span
          className={`max-w-[60%] shrink-0 truncate rounded-full px-2 py-0.5 text-[11px] font-semibold ${
            up ? CHIP_TONE.emerald : "bg-white/[0.05] text-slate-400"
          }`}
        >
          {note ??
            (delta === 0
              ? "Same as last week"
              : `${up ? "+" : "−"}${fmt(Math.abs(delta))} vs last week`)}
        </span>
        <Spark series={series} name={seriesName} />
      </span>
    </div>
  );
}

const FUNNEL: { key: string; name: string; from: LeadStatus[]; fill: string; opacity: number }[] = [
  {
    key: "all",
    name: "Leads",
    from: ["new", "contacted", "qualified", "won", "lost"],
    fill: ACCENT,
    opacity: 0.35,
  },
  {
    key: "contacted",
    name: "Contacted",
    from: ["contacted", "qualified", "won"],
    fill: ACCENT,
    opacity: 0.55,
  },
  { key: "qualified", name: "Qualified", from: ["qualified", "won"], fill: ACCENT, opacity: 0.8 },
  { key: "won", name: "Won", from: ["won"], fill: "#34d399", opacity: 0.9 },
];

function Funnel({ summary }: { summary: SalesSummary }) {
  const count = (from: LeadStatus[]) =>
    summary.stages.filter((s) => from.includes(s.stage)).reduce((n, s) => n + s.count, 0);
  const rows = FUNNEL.map((f) => ({ ...f, n: count(f.from) }));
  const total = rows[0].n;
  if (total === 0) return <p className="py-8 text-center text-sm text-slate-500">No leads yet.</p>;

  const W = 360;
  const H = 46;
  const GAP = 6;
  const widthOf = (n: number) => Math.max(W * 0.12, (n / total) * W);
  return (
    <svg
      viewBox={`0 0 ${W} ${rows.length * (H + GAP)}`}
      className="mx-auto w-full max-w-[300px]"
      role="img"
      aria-label={`Sales funnel: ${rows.map((r) => `${r.name} ${r.n}`).join(", ")}`}
    >
      {rows.map((r, i) => {
        const top = widthOf(i === 0 ? r.n : rows[i - 1].n);
        const bottom = widthOf(r.n);
        const y = i * (H + GAP);
        const x0 = (W - top) / 2;
        const x1 = (W - bottom) / 2;
        return (
          <g key={r.key}>
            <polygon
              points={`${x0},${y} ${x0 + top},${y} ${x1 + bottom},${y + H} ${x1},${y + H}`}
              fill={r.fill}
              fillOpacity={r.opacity}
            />
            <text
              x={W / 2}
              y={y + H / 2 + 5}
              textAnchor="middle"
              fontSize={15}
              fontWeight={600}
              fill="#fff"
            >
              {r.n}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** KPI cards with trend lines and a funnel, built only from real lead rows. */
export function SalesInsights({
  summary,
  onTargetChanged,
}: {
  summary: SalesSummary;
  onTargetChanged: () => void;
}) {
  const { weeks, stages, currency } = summary;
  const last = weeks[weeks.length - 1];
  const prev: Week | undefined = weeks[weeks.length - 2];
  const stage = (s: LeadStatus) => stages.find((x) => x.stage === s)!;
  const open = (["new", "contacted", "qualified"] as LeadStatus[]).map(stage);
  const openValue = open.reduce((n, s) => n + s.value_minor, 0);
  const won = stage("won");
  const lost = stage("lost");
  const closed = won.count + lost.count;
  const all = stages.reduce((n, s) => n + s.count, 0);

  const funnelRows = FUNNEL.map((f) => ({
    ...f,
    n: stages.filter((s) => f.from.includes(s.stage)).reduce((n, s) => n + s.count, 0),
  }));

  return (
    <div className="mb-6 space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi
          title="Open pipeline"
          icon={<ChartIcon size={16} />}
          tone="violet"
          value={compactMoney(openValue, currency)}
          // The open pipeline has no history (status changes are not stored), so the line shows
          // the value of leads added each week, and says so, instead of a "vs last week" change.
          series={weeks.map((w) => w.new_value_minor / 100)}
          seriesName="Pipeline value added per week"
          delta={last.new_value_minor}
          note={
            last.new_value_minor
              ? `+${compactMoney(last.new_value_minor, currency)} added this week`
              : "Nothing added this week"
          }
        />
        <Kpi
          title="New leads this week"
          icon={<UsersIcon size={16} />}
          tone="sky"
          value={String(last.new_leads)}
          series={weeks.map((w) => w.new_leads)}
          delta={last.new_leads}
          note={`${prev?.new_leads ?? 0} last week`}
        />
        <Kpi
          title="Deals won"
          icon={<CheckIcon size={16} />}
          tone="emerald"
          value={String(won.count)}
          series={weeks.map((w) => w.won)}
          seriesName="Deals won per week"
          delta={last.won}
          note={`${last.won} this week · ${prev?.won ?? 0} last week`}
        />
        <Kpi
          title="Won value"
          icon={<WalletIcon size={16} />}
          tone="amber"
          value={compactMoney(won.value_minor, currency)}
          series={weeks.map((w) => w.won_minor / 100)}
          seriesName="Value won per week"
          delta={last.won_minor}
          note={`${compactMoney(last.won_minor, currency)} this week · ${compactMoney(prev?.won_minor ?? 0, currency)} last week`}
        />
      </div>
      <p className="-mt-2 text-xs text-slate-500">
        Trend lines show the last 8 weeks: leads and value by the week they were added, wins by the
        week of the lead&apos;s last update.
      </p>
      <TargetBar
        target={summary.target}
        onTargetChanged={onTargetChanged}
        className="rounded-2xl! bg-navy-900/80! px-5! py-4! card-shadow"
      />
      <Card title="Sales funnel" icon={<ChartIcon size={16} />}>
        <div className="grid items-center gap-6 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <Funnel summary={summary} />
          <ul className="space-y-3">
            {funnelRows.map((r) => (
              <li key={r.key} className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-slate-300">{r.name}</span>
                <span className="text-slate-100 tabular-nums">
                  {r.n}
                  <span className="ml-2 text-xs text-slate-500">
                    {all ? Math.round((100 * r.n) / all) : 0}%
                  </span>
                </span>
              </li>
            ))}
            <li className="border-t border-navy-800 pt-3 text-xs text-slate-500">
              Each stage counts leads that reached it or later. Lost deals ({lost.count}) are in
              Leads only, since the app does not record where they dropped out.
            </li>
          </ul>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-navy-800 pt-4 text-center md:grid-cols-4">
          {[
            ["Win rate", closed ? `${Math.round((100 * won.count) / closed)}%` : "—"],
            [
              "Average won deal",
              won.count ? compactMoney(Math.round(won.value_minor / won.count), currency) : "—",
            ],
            ["Open deals", String(open.reduce((n, s) => n + s.count, 0))],
            ["Lost deals", String(lost.count)],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-slate-400">{k}</dt>
              <dd className="mt-0.5 text-lg font-semibold text-white tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  );
}
