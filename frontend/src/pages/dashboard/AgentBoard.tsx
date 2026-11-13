import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BoltIcon } from "../../components/icons";
import { ago, label, shortDay } from "../../format";
import type { ActivityItem, Charts, Overview } from "../../types";
import { ACCENT, AXIS, FAILED, TOOLTIP } from "./chartStyle";
import { Panel, Skeleton } from "./parts";

const FEED_ROWS = 7;

function describe(item: ActivityItem): string {
  const [entity, verb] = item.action.split(".");
  return `${label(verb ?? item.action)} ${label(entity)}`;
}

/** The dashboard's main chart: what the agents did each day this week, next to the latest
 * audit events. */
export function AgentBoard({
  agents,
  charts,
  feed,
}: {
  agents: Overview["agents"];
  charts: Charts | null;
  feed: ActivityItem[] | null;
}) {
  const rate = agents.calls ? Math.round((100 * agents.succeeded) / agents.calls) : null;
  return (
    <Panel
      title="Agent activity, last 7 days"
      icon={<BoltIcon size={17} />}
      to="/activity"
      linkText="Command Center"
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <p className="mb-3 flex flex-wrap items-baseline gap-x-3 text-sm text-slate-400">
            <span>
              <span className="text-2xl font-semibold text-white tabular-nums">{agents.calls}</span>{" "}
              calls in the last 24 h
            </span>
            {rate !== null && <span className="text-slate-300">{rate}% succeeded</span>}
            {agents.failed > 0 && <span className="text-red-300">{agents.failed} failed</span>}
          </p>
          {charts ? (
            <ResponsiveContainer width="100%" height={210}>
              <BarChart
                data={charts.agent_calls_by_day.map((d) => ({ ...d, day: shortDay(d.day) }))}
                margin={{ top: 4, right: 0, bottom: 0, left: -24 }}
              >
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis dataKey="day" {...AXIS} />
                <YAxis allowDecimals={false} {...AXIS} />
                <Tooltip {...TOOLTIP} cursor={{ fill: "var(--chart-cursor)" }} />
                <Bar dataKey="succeeded" stackId="a" fill={ACCENT} maxBarSize={36} />
                <Bar
                  dataKey="failed"
                  stackId="a"
                  fill={FAILED}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={36}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Skeleton className="h-[210px]" />
          )}
          <p className="mt-2 flex gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-sm" style={{ background: ACCENT }} /> succeeded
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-sm" style={{ background: FAILED }} /> failed
            </span>
          </p>
        </div>
        <div className="min-w-0">
          <p className="mb-1 text-xs text-slate-500">Recent activity</p>
          <ul className="divide-y divide-white/5 text-sm">
            {(feed ?? []).slice(0, FEED_ROWS).map((item) => (
              <li key={item.id} className="flex items-baseline justify-between gap-3 py-1.5">
                <span className="min-w-0 truncate text-slate-300">
                  <span className="text-slate-500">{item.actor_name ?? "System"}</span> ·{" "}
                  {describe(item)}
                </span>
                <span className="shrink-0 text-xs text-slate-500">{ago(item.at)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Panel>
  );
}
