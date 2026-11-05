import { Link } from "react-router";
import { Badge } from "../../components/ui";
import { ChartIcon } from "../../components/icons";
import { compactMoney, label, money } from "../../format";
import type { LeadStatus, Money, Overview } from "../../types";
import { Panel, Stat } from "./parts";

const STAGE_BAR: Record<LeadStatus, string> = {
  new: "bg-slate-400",
  contacted: "bg-sky-400",
  qualified: "bg-accent-purple",
  won: "bg-emerald-400",
  lost: "bg-rose-400/70",
};

function sumText(values: Money[]): string {
  return values.length
    ? values.map((v) => compactMoney(v.amount_minor, v.currency)).join(" + ")
    : "—";
}

/** Half-circle gauge: won this quarter against the quarterly target. */
function TargetGauge({ target }: { target: Overview["crm"]["target"] }) {
  const share = target.target_minor ? target.won_minor / target.target_minor : 0;
  const pct = Math.round(share * 100);
  const r = 62;
  const arc = Math.PI * r;
  const filled = arc * Math.min(share, 1);
  return (
    <div className="flex flex-col items-center rounded-xl bg-navy-950/60 px-3 pt-3 pb-2 ring-1 ring-white/5">
      <svg
        viewBox="0 0 150 86"
        className="w-full max-w-[170px]"
        role="img"
        aria-label={`${pct}% of target`}
      >
        <defs>
          <linearGradient id="gauge-fill" x1="0" x2="1">
            <stop offset="0" stopColor="#8b5cf6" />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <path
          d={`M ${75 - r} 78 A ${r} ${r} 0 0 1 ${75 + r} 78`}
          fill="none"
          stroke="rgb(255 255 255 / 0.07)"
          strokeWidth="11"
          strokeLinecap="round"
        />
        <path
          d={`M ${75 - r} 78 A ${r} ${r} 0 0 1 ${75 + r} 78`}
          fill="none"
          stroke="url(#gauge-fill)"
          strokeWidth="11"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${arc}`}
        />
        <text x="75" y="62" textAnchor="middle" className="fill-white text-[19px] font-semibold">
          {compactMoney(target.won_minor, target.currency)}
        </text>
        <text x="75" y="78" textAnchor="middle" className="fill-slate-400 text-[10px]">
          {pct}% of target
        </text>
      </svg>
      <p className="mt-1 text-center text-[11px] text-slate-500">
        Won in {target.quarter} · target {compactMoney(target.target_minor, target.currency)}
        <span className="block text-slate-600">(company setting)</span>
      </p>
    </div>
  );
}

export function DealBoard({ crm }: { crm: Overview["crm"] }) {
  return (
    <Panel title="CRM deal board" icon={<ChartIcon size={17} />} to="/sales">
      <div className="grid grid-cols-5 gap-1.5">
        {crm.stages.map((s) => (
          <div
            key={s.stage}
            className="min-w-0 rounded-lg bg-navy-950/60 px-2 py-2 ring-1 ring-white/5"
          >
            <div className={`mb-1.5 h-0.5 rounded-full ${STAGE_BAR[s.stage]}`} />
            <p className="truncate text-[11px] text-slate-400 capitalize">{s.stage}</p>
            <p className="text-lg leading-tight font-semibold text-white">{s.count}</p>
            <p className="truncate text-[10px] text-slate-500">{sumText(s.value)}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_1.2fr]">
        <Stat
          label="Open pipeline"
          value={sumText(crm.pipeline)}
          hint="new + contacted + qualified"
        />
        <Stat
          label="Win rate"
          value={crm.win_rate === null ? "—" : `${crm.win_rate}%`}
          hint={crm.won + crm.lost ? `${crm.won} won · ${crm.lost} lost` : "no deals closed yet"}
          tone="text-accent-cyan"
        />
        <TargetGauge target={crm.target} />
      </div>
      <p className="mt-4 mb-1.5 text-[11px] tracking-wide text-slate-500 uppercase">
        Biggest open deals
      </p>
      <ul className="divide-y divide-white/5">
        {crm.top_deals.slice(0, 4).map((d) => (
          <li key={d.lead_id}>
            <Link
              to={`/sales#lead-${d.lead_id}`}
              className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/[0.03]"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-slate-100">{d.company}</span>
                <span className="block truncate text-xs text-slate-500">
                  {d.contact} · {label(d.status)}
                </span>
              </span>
              {d.rating && <Badge value={d.rating} />}
              <span className="text-sm font-medium whitespace-nowrap text-slate-200">
                {money(d.amount_minor, d.currency)}
              </span>
            </Link>
          </li>
        ))}
        {crm.top_deals.length === 0 && (
          <li className="py-3 text-sm text-slate-500">No open deals.</li>
        )}
      </ul>
    </Panel>
  );
}
